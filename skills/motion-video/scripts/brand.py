#!/usr/bin/env python3
"""
brand.py — build brand.json from LOCAL files already ingested into a project (logo, screenshots,
fonts, brand-guide PDF or text). No network: it reads PROJECT/assets/assets.json only.

Usage:
  python3 brand.py motion/promo                       # analyse -> brand.json, brand.js, docs/brand_swatch.png
  python3 brand.py motion/promo --logo acme-logo      # say which asset id is the logo / wordmark
  python3 brand.py motion/promo --role bg=#0e0f12 --role accent=#ff4d1f --font display="Acme Sans" --confirm
                                                      # E3.5: record the user's confirmation / overrides

What it reads (ids from assets.json; run ingest.py first):
  image / svg   palette ranked by painted area (logo weighted x3); transparent pixels ignored
  font          families and weights -> fonts.display (heaviest / "Display"-named) and fonts.ui
  doc           .pdf (pypdf if installed, else pdftotext if on PATH), .txt/.md: hex / rgb() colours,
                font names next to "font/typeface/typography", labelled copy (tagline, headline …)

Writes:
  brand.json    {version, source:"local", colors:[{hex, share, sources, neutral, guide?}],
                 fonts:{display, ui}, wordmark, roles, copy, guide, notes, confirmed}
                (the same schema a URL gatherer would write, so later steps work on either source)
  brand.js      window.BRAND = <brand.json>;   (for file:// previews)
  docs/brand_swatch.png   palette chips + two font samples, for the brand confirmation step
  docs/brand-guide.txt    text extracted from the guide (read it for exact copy; quote, never paraphrase)

Re-running keeps roles, font overrides and "confirmed" from the previous brand.json.
Prints a summary JSON. Requires Pillow.
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow missing: pip install Pillow")


def log(*a):
    print("[brand]", *a, flush=True)


LOGO_HINT = re.compile(r"logo|wordmark|brandmark|mark|lockup", re.I)
HEX_RE = re.compile(r"(?<![0-9A-Za-z&])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9A-Za-z])")
RGB_RE = re.compile(r"\brgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", re.I)
RGB_WORDS_RE = re.compile(r"\bRGB\s*:?\s*(\d{1,3})[\s,/]+(\d{1,3})[\s,/]+(\d{1,3})\b", re.I)
FONT_LINE_RE = re.compile(r"(?:font|typeface|typography|type ?family)[^:\n—–-]*[:—–-]\s*([A-Z][\w ]{1,40}?)\s*(?:[,.(\n]|$)", re.I | re.M)
COPY_RE = re.compile(r"^\s*(tagline|slogan|headline|claim|mission|cta|call to action|boilerplate)\s*[:—–-]\s*[\"“']?(.+?)[\"”']?\s*$",
                     re.I | re.M)
MERGE_DIST = 28            # RGB distance under which two colours count as one
MAX_COLORS = 8


# ---------------------------------------------------------------- colour maths

def hex_of(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def rgb_of(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def is_neutral(rgb):
    mx, mn = max(rgb), min(rgb)
    return (mx - mn) < 24 or mx < 28 or mn > 236     # greys, near-black, near-white


def luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def image_palette(path: Path, k=10):
    """Painted-area palette of a raster: [(rgb, pixel_fraction)], transparent pixels ignored."""
    im = Image.open(path)
    im.load()
    im = im.convert("RGBA")
    im.thumbnail((160, 160))
    raw = im.tobytes()
    opaque = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 4) if raw[i + 3] >= 128]
    if not opaque:
        return []
    strip = Image.new("RGB", (len(opaque), 1))
    strip.putdata(opaque)
    q = strip.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = q.getcolors(k * 4) or []
    total = len(opaque)
    return [(tuple(pal[i * 3:i * 3 + 3]), n / total) for n, i in counts]


SVG_COLOR_RE = re.compile(r"(?:fill|stroke|stop-color|color)\s*[:=]\s*[\"']?\s*(#[0-9a-fA-F]{3,6}\b|rgb\([^)]*\))", re.I)


def svg_palette(path: Path):
    """SVG colours by how often they're used (no rasteriser needed): [(rgb, fraction)]."""
    text = path.read_text(errors="ignore")
    found = []
    for v in SVG_COLOR_RE.findall(text):
        if v.startswith("#") and len(v) in (4, 7):
            found.append(rgb_of(v))
        else:
            m = RGB_RE.search(v)
            if m:
                found.append(tuple(min(255, int(x)) for x in m.groups()))
    if not found:
        return []
    out = {}
    for c in found:
        out[c] = out.get(c, 0) + 1
    return [(c, n / len(found)) for c, n in out.items()]


def merge(entries):
    """entries: [(rgb, weight, source_id)] -> clusters [{rgb, w, sources}] by weight, merged by distance."""
    clusters = []
    for rgb, w, src in sorted(entries, key=lambda e: -e[1]):
        for c in clusters:
            if dist(c["rgb"], rgb) < MERGE_DIST:
                tot = c["w"] + w
                c["rgb"] = tuple((a * c["w"] + b * w) / tot for a, b in zip(c["rgb"], rgb))
                c["w"] = tot
                if src not in c["sources"]:
                    c["sources"].append(src)
                break
        else:
            clusters.append({"rgb": rgb, "w": w, "sources": [src]})
    return clusters


# ---------------------------------------------------------------- guide text

def pdf_text(path: Path, notes):
    try:
        import pypdf  # optional
        return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages)
    except ImportError:
        pass
    except Exception as e:
        notes.append(f"{path.name}: pypdf could not read it ({e})")
        return ""
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout
        notes.append(f"{path.name}: pdftotext failed ({r.stderr.strip()[:200]})")
        return ""
    notes.append(f"{path.name}: can't read PDF text here. Install one of: pip install pypdf  |  "
                 "poppler (pdftotext). Colours come from the images only; or paste the guide's colours and fonts")
    return ""


def guide_facts(text: str):
    colors = []
    for m in HEX_RE.finditer(text):
        colors.append(hex_of(rgb_of(m.group(1))))
    for rx in (RGB_RE, RGB_WORDS_RE):
        for m in rx.finditer(text):
            vals = [int(x) for x in m.groups()]
            if all(v <= 255 for v in vals):
                colors.append(hex_of(vals))
    fonts = []
    for m in FONT_LINE_RE.finditer(text):
        name = m.group(1).strip()
        if name.lower() not in ("the", "a", "our", "use", "primary", "secondary") and name not in fonts:
            fonts.append(name)
    copy = [{"label": m.group(1).lower(), "text": m.group(2).strip()} for m in COPY_RE.finditer(text)]
    seen, uniq = set(), []
    for c in colors:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return {"colors": uniq, "fonts": fonts, "copy": copy}


# ---------------------------------------------------------------- fonts and wordmark

DISPLAY_HINT = re.compile(r"display|headline|heading|title|poster", re.I)
UI_HINT = re.compile(r"text|ui|body|sans|mono|book", re.I)


def pick_fonts(font_assets, guide_fonts, overrides):
    fams = {}
    for a in font_assets:
        f = fams.setdefault(a.get("family", a["id"]), {"family": a.get("family", a["id"]), "weights": [], "assets": []})
        f["weights"] = sorted(set(f["weights"] + [a.get("weight", 400)]))
        f["assets"].append(a["id"])
    out = {"display": None, "ui": None}
    names = list(fams)
    if names:
        disp = next((n for n in names if DISPLAY_HINT.search(n)), None) or \
            max(names, key=lambda n: (max(fams[n]["weights"]), n))
        ui = next((n for n in names if n != disp and UI_HINT.search(n)), None) or \
            next((n for n in names if n != disp), disp)
        for role, n in (("display", disp), ("ui", ui)):
            ws = fams[n]["weights"]
            w = max(ws) if role == "display" else min(ws, key=lambda x: abs(x - 400))
            out[role] = {"family": n, "weight": w, "weights": ws, "assets": fams[n]["assets"], "supplied": True}
    for role, n in zip(("display", "ui"), guide_fonts):
        if out[role] is None:
            out[role] = {"family": n, "weight": 700 if role == "display" else 400, "weights": [], "assets": [],
                         "supplied": False}
    for role, fam in overrides.items():
        prev = out.get(role) or {}
        match = fams.get(fam)
        out[role] = {"family": fam, "weight": prev.get("weight", 700 if role == "display" else 400),
                     "weights": match["weights"] if match else [], "assets": match["assets"] if match else [],
                     "supplied": bool(match), "override": True}
    return out


def pick_logo(assets, want):
    if want:
        return next((a for a in assets if a["id"] == want), None)
    marks = [a for a in assets if a["kind"] in ("svg", "image") and LOGO_HINT.search(a["id"])]
    if marks:
        return sorted(marks, key=lambda a: (a["kind"] != "svg", a["id"]))[0]
    svgs = [a for a in assets if a["kind"] == "svg"]
    return svgs[0] if len(svgs) == 1 else None


# ---------------------------------------------------------------- swatch sheet

def label_font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:   # Pillow < 10.1
        return ImageFont.load_default()


def font_file(project, fonts_entry, inv):
    for aid in (fonts_entry or {}).get("assets", []):
        a = next((x for x in inv if x["id"] == aid), None)
        if a and Path(project, a["path"]).suffix.lower() in (".ttf", ".otf"):
            if a.get("weight") == fonts_entry["weight"]:
                return Path(project, a["path"])
    for aid in (fonts_entry or {}).get("assets", []):
        a = next((x for x in inv if x["id"] == aid), None)
        if a and Path(project, a["path"]).suffix.lower() in (".ttf", ".otf"):
            return Path(project, a["path"])
    return None


def swatch(project: Path, brand, inv, out: Path):
    cols = brand["colors"][:MAX_COLORS]
    W, chip = 1600, 180
    H = 90 + chip + 120 + 2 * 170 + 40
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    d.text((40, 30), f"Brand check: {project.name}  (reply 'ok' or override roles / fonts)", fill="#222222", font=label_font(30))
    x = 40
    cw = (W - 80 - 16 * (max(1, len(cols)) - 1)) / max(1, len(cols))
    roles = {v: k for k, v in brand.get("roles", {}).items()}
    for c in cols:
        rgb = rgb_of(c["hex"])
        d.rounded_rectangle([x, 90, x + cw, 90 + chip], radius=16, fill=rgb, outline="#dddddd")
        tag = f"{c['hex']}  {round(100 * c['share'])}%" + ("  guide" if c.get("guide") else "")
        d.text((x, 90 + chip + 14), tag, fill="#222222", font=label_font(22))
        if c["hex"] in roles:
            d.text((x, 90 + chip + 44), roles[c["hex"]], fill="#666666", font=label_font(22))
        x += cw + 16
    y = 90 + chip + 120
    for role, sample in (("display", "Display Aa 0123"), ("ui", "UI text — The quick brown fox 0123")):
        f = brand["fonts"].get(role)
        name = f"{role}: {f['family']} {f['weight']}" if f else f"{role}: (no font supplied; system stack)"
        d.text((40, y), name + ("" if not f or f.get("supplied") else "  [not supplied: ingest the font file]"),
               fill="#666666", font=label_font(22))
        path = font_file(project, f, inv) if f else None
        try:
            fnt = ImageFont.truetype(str(path), 96 if role == "display" else 64) if path else label_font(64)
        except Exception:
            fnt = label_font(64)
        d.text((40, y + 36), sample, fill="#111111", font=fnt)
        y += 170
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)


# ---------------------------------------------------------------- main

def parse_kv(items, what):
    out = {}
    for it in items or []:
        if "=" not in it:
            sys.exit(f"--{what} wants NAME=VALUE, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="project folder (holds assets/assets.json from ingest.py)")
    ap.add_argument("--logo", help="asset id of the logo / wordmark (default: guessed from ids like *logo*)")
    ap.add_argument("--guide", action="append", default=[], help="asset id of a brand guide doc (default: every doc)")
    ap.add_argument("--role", action="append", default=[], metavar="NAME=#HEX",
                    help="colour role, e.g. bg=#0e0f12, ink=#f3f1ec, accent=#ff4d1f (repeatable)")
    ap.add_argument("--font", action="append", default=[], metavar="ROLE=FAMILY",
                    help="override a font role: display=… or ui=… (repeatable)")
    ap.add_argument("--confirm", action="store_true", help="mark the brand as confirmed by the user (E3.5)")
    ap.add_argument("--no-swatch", action="store_true", help="skip docs/brand_swatch.png")
    a = ap.parse_args()

    project = a.project
    inv_file = project / "assets" / "assets.json"
    if not inv_file.exists():
        sys.exit(f"{inv_file} not found: ingest the brand files first (ingest.py {project} <files…>)")
    inv = json.loads(inv_file.read_text()).get("assets", [])
    out_file = project / "brand.json"
    prev = {}
    if out_file.exists():
        try:
            prev = json.loads(out_file.read_text())
        except ValueError:
            log(f"warning: {out_file} is not valid JSON; starting fresh")
    notes = []

    # guide text first (its colours are authoritative)
    docs = [x for x in inv if x["kind"] == "doc" and (not a.guide or x["id"] in a.guide)]
    missing = [g for g in a.guide if g not in {x["id"] for x in inv}]
    for g in missing:
        notes.append(f"--guide {g}: no such asset id")
    texts = []
    for doc in docs:
        p = project / doc["path"]
        ext = p.suffix.lower()
        if ext == ".pdf":
            texts.append(pdf_text(p, notes))
        elif ext in (".txt", ".md", ".csv", ".json"):
            texts.append(p.read_text(errors="ignore"))
    text = "\n".join(t for t in texts if t)
    guide = guide_facts(text) if text else {"colors": [], "fonts": [], "copy": []}
    if text:
        (project / "docs").mkdir(parents=True, exist_ok=True)
        (project / "docs" / "brand-guide.txt").write_text(text)

    # palette from images and SVGs
    logo = pick_logo(inv, a.logo)
    if a.logo and not logo:
        notes.append(f"--logo {a.logo}: no such asset id")
    entries = []
    for x in inv:
        if x["kind"] not in ("image", "svg"):
            continue
        p = project / x["path"]
        try:
            pal = image_palette(p) if x["kind"] == "image" else svg_palette(p)
        except Exception as e:
            notes.append(f"{x['id']}: could not read colours ({e})")
            continue
        weight = 3.0 if logo and x["id"] == logo["id"] else 1.0
        entries += [(rgb, f * weight, x["id"]) for rgb, f in pal]
    clusters = merge(entries)
    total = sum(c["w"] for c in clusters) or 1.0
    colors = [{"hex": hex_of(c["rgb"]), "share": round(c["w"] / total, 4), "sources": c["sources"],
               "neutral": is_neutral(c["rgb"])} for c in clusters]
    colors = [c for c in colors if c["share"] >= 0.005]
    for g in guide["colors"]:   # the guide's exact hex wins over the measured one
        near = min(colors, key=lambda c: dist(rgb_of(c["hex"]), rgb_of(g)), default=None)
        if near and not near.get("guide") and dist(rgb_of(near["hex"]), rgb_of(g)) < MERGE_DIST:
            near.update({"measured": near["hex"], "hex": g, "guide": True})
        elif not any(c["hex"] == g for c in colors):
            colors.append({"hex": g, "share": 0.0, "sources": ["guide"], "neutral": is_neutral(rgb_of(g)), "guide": True})
    colors.sort(key=lambda c: (not c.get("guide"), -c["share"]))
    if not colors:
        notes.append("no colours found: ingest a logo or screenshots, or set roles with --role")

    font_overrides = {**(prev.get("font_overrides") or {}), **parse_kv(a.font, "font")}
    bad = [r for r in font_overrides if r not in ("display", "ui")]
    if bad:
        sys.exit(f"--font roles are display and ui, got {bad}")
    fonts = pick_fonts([x for x in inv if x["kind"] == "font"], guide["fonts"], font_overrides)
    for role in ("display", "ui"):
        if fonts[role] and not fonts[role]["supplied"]:
            notes.append(f"font {fonts[role]['family']!r} ({role}) is named but not supplied: ingest the font file, "
                         "or the piece falls back to the system stack")

    wordmark = None
    if logo:
        lp = project / logo["path"]
        try:
            pal = image_palette(lp) if logo["kind"] == "image" else svg_palette(lp)
        except Exception:
            pal = []
        top = [hex_of(c["rgb"]) for c in merge([(rgb, f, logo["id"]) for rgb, f in pal])][:3]
        mean = sum(luminance(rgb) * f for rgb, f in pal) / (sum(f for _, f in pal) or 1)
        # "on": the background it reads best on (higher WCAG contrast against black or white)
        wordmark = {"asset": logo["id"], "kind": logo["kind"], "path": logo["path"],
                    "w": logo.get("w"), "h": logo.get("h"), "colors": top,
                    "on": "dark" if (mean + 0.05) / 0.05 > 1.05 / (mean + 0.05) else "light", "alpha": logo.get("alpha")}

    # roles: a suggestion from the palette (most painted neutral = bg, the most contrasting neutral = ink,
    # the top chromatic colour = accent), overlaid with the user's --role choices (kept across runs)
    role_overrides = dict(prev.get("role_overrides") or {})
    for k, v in parse_kv(a.role, "role").items():
        if not re.fullmatch(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}", v):
            sys.exit(f"--role {k}={v}: use a hex colour like #ff4d1f")
        role_overrides[k] = hex_of(rgb_of(v))
    roles = {}
    neutrals = sorted((c for c in colors if c["neutral"]), key=lambda c: -c["share"])
    chroma = sorted((c for c in colors if not c["neutral"]), key=lambda c: (not c.get("guide"), -c["share"]))
    if neutrals:
        roles["bg"] = neutrals[0]["hex"]
    bg = role_overrides.get("bg", roles.get("bg"))
    if bg:
        far = [c for c in neutrals if abs(luminance(rgb_of(c["hex"])) - luminance(rgb_of(bg))) > 0.4]
        if far:
            roles["ink"] = far[0]["hex"]
    if chroma:
        roles["accent"] = chroma[0]["hex"]
    roles.update(role_overrides)

    brand = {"version": 1, "source": "local", "colors": colors[:MAX_COLORS + len(guide["colors"])],
             "fonts": fonts, "font_overrides": font_overrides, "role_overrides": role_overrides, "wordmark": wordmark, "roles": roles,
             "copy": guide["copy"], "guide": {"docs": [d["id"] for d in docs], "colors": guide["colors"],
                                              "fonts": guide["fonts"], "text": "docs/brand-guide.txt" if text else None},
             "notes": notes, "confirmed": bool(a.confirm or (prev.get("confirmed") and not a.role and not a.font))}
    out_file.write_text(json.dumps(brand, indent=2) + "\n")
    (project / "brand.js").write_text(f"window.BRAND = {json.dumps(brand)};\n")
    if not a.no_swatch:
        swatch(project, brand, inv, project / "docs" / "brand_swatch.png")
    for n in notes:
        log("note:", n)
    print(json.dumps({"brand": str(out_file), "swatch": None if a.no_swatch else str(project / "docs" / "brand_swatch.png"),
                      "colors": [c["hex"] for c in brand["colors"]], "roles": roles,
                      "fonts": {k: (v or {}).get("family") for k, v in fonts.items()},
                      "wordmark": wordmark and wordmark["asset"], "copy": len(guide["copy"]),
                      "confirmed": brand["confirmed"], "notes": notes}, indent=2))


if __name__ == "__main__":
    main()
