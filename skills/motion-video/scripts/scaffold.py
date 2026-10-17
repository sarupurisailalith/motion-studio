#!/usr/bin/env python3
"""
scaffold.py — create a Motion Studio project folder from a template.

Usage:
  python3 scaffold.py "Launch teaser" --template 2d --formats 9x16,1x1 --duration 12
  python3 scaffold.py promo --template gsap --fps 30 --root ./motion
  python3 scaffold.py --list                       # templates and what each needs

Creates <root>/<slug>/ (default root ./motion):
  <slug>.html   the template, with MOTION width/height (the first format), fps and duration set
  kit.js        the shared motion kit (+ any addon kit files the template needs)
  brief.md      a brief skeleton: deliverable and formats filled, every other field [[TODO: …]]
  assets/  audio/  docs/  renders/
Never overwrites an existing file (use --force for the HTML and kit files; brief.md is always kept).
Never downloads: when a template needs a vendored library it prints the vendor.py command to run.
Prints a summary JSON {project, html, created, kept, next}.
"""
import argparse, json, re, shutil, sys, unicodedata
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL / "templates"

# Template registry. To add one: its HTML file, the vendor.py package it needs (or None), whether it
# renders with --gl, and any extra files copied next to it (addon kits such as kit-zdog.js).
TEMPLATES = {
    "2d":    {"file": "composition.html", "vendor": None, "gl": False, "extra": [],
              "use": "DOM / SVG / Canvas 2D: type, UI, explainers, most motion graphics"},
    "three": {"file": "three-composition.html", "vendor": "three", "gl": True, "extra": [],
              "use": "Three.js 3D (preview needs http: python3 -m http.server)"},
    "gsap":  {"file": "gsap-composition.html", "vendor": "gsap", "gl": False, "extra": [],
              "use": "GSAP: one paused master timeline seeked per frame"},
    "glsl":  {"file": "glsl-composition.html", "vendor": None, "gl": True, "extra": [],
              "use": "fragment shader on one full-frame triangle, uTime from seek(t)"},
    "zdog":  {"file": "zdog-composition.html", "vendor": "zdog", "gl": False, "extra": ["kit-zdog.js"],
              "models": ["pip", "parcel"],
              "use": "Zdog flat-round 3D: characters, mascots, icons, props (read references/zdog.md)"},
    "p5":    {"file": "p5-composition.html", "vendor": "p5", "gl": False, "extra": ["kit-p5.js"],
              "use": "p5.js: generative loops, flow fields, glyph type (p5 rules in references/gotchas.md)"},
    "layered": {"file": "layered-composition.html", "vendor": "p5 zdog", "gl": False,
                "extra": ["kit-p5.js", "kit-zdog.js", "kit-layers.js"], "models": ["pip", "pine", "round-tree", "rock", "ground-block"],
                "use": "several engines on one timeline (K.layers), one engine per depth plane"},
}
# Not scaffolded: footage (its MOTION comes from transcript/EDL data; follow references/footage.md).
FORMATS = {"16x9": (1920, 1080), "9x16": (1080, 1920), "1x1": (1080, 1080), "4x5": (1080, 1350)}
MOTION_RE = re.compile(r"(window\.MOTION\s*=\s*(?:K\.init\()?\{\s*)width:\s*\d+,\s*height:\s*\d+,\s*fps:\s*\d+,\s*duration:\s*[\d.]+")


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "piece"


def brief_fields():
    """Field names in references/brief-template.md, in order (e.g. ['inputs', 'assets', …])."""
    text = (SKILL / "references" / "brief-template.md").read_text()
    return re.findall(r"^<([a-z][a-z ]*)>", text, re.M)


def brief_skeleton(title, fmt_list, duration, fps, tpl):
    w, h = FORMATS[fmt_list[0]]
    filled = {
        "deliverable": f"{duration:g} s at {fps} fps, {w}×{h} native, loop [[TODO: yes/no]], MP4 per format "
                       f"+ editable HTML source, sound [[TODO: on/off]].",
        "formats": ", ".join(f"{f} ({FORMATS[f][0]}×{FORMATS[f][1]})" for f in fmt_list)
                   + ". One timeline; per-format layout via K.pick. Text carries data-safe data-text and "
                   "stays inside K.safe.ui. [[TODO: per-format layout notes]]",
        "build": f"Template: {tpl} ({TEMPLATES[tpl]['file']}). seek(t) pure; closed-form springs "
                 "(K.SPRING presets); seeded randomness; local assets only.",
        "review": "none",
    }
    lines = [f"# Brief: {title}", "", "Fill every field (references/brief-template.md explains each). "
             "Anything only the user can supply stays [[TODO: …]].", "", "```"]
    for f in brief_fields():
        lines.append(f"<{f}>".ljust(16) + filled.get(f, "[[TODO: …]]"))
    lines.append("```")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="project name (slugged for the folder and HTML file)")
    ap.add_argument("--template", default="2d", help=f"one of {', '.join(TEMPLATES)} (default 2d)")
    ap.add_argument("--formats", default="16x9", help="comma list from 16x9,9x16,1x1,4x5; the first is the native size")
    ap.add_argument("--duration", type=float, help="seconds (default: the template's)")
    ap.add_argument("--fps", type=int, help="frames per second (default: the template's)")
    ap.add_argument("--root", type=Path, default=Path("motion"), help="parent folder (default ./motion)")
    ap.add_argument("--force", action="store_true", help="overwrite the HTML and kit files if they exist")
    ap.add_argument("--list", action="store_true", help="list templates and exit")
    a = ap.parse_args()

    if a.list:
        for k, t in TEMPLATES.items():
            needs = ", ".join(x for x in (t["vendor"] and f"vendor.py {t['vendor']}", t["gl"] and "render --gl") if x)
            print(f"{k:6s} {t['file']:24s} {t['use']}" + (f"  [needs: {needs}]" if needs else ""))
        return
    if not a.name:
        ap.error("name is required (or --list)")
    if a.template not in TEMPLATES:
        sys.exit(f"unknown --template {a.template!r}: use one of {', '.join(TEMPLATES)}")
    fmts = [f.strip() for f in a.formats.split(",") if f.strip()]
    bad = [f for f in fmts if f not in FORMATS]
    if bad or not fmts:
        sys.exit(f"unknown format(s) {bad}: use {', '.join(FORMATS)}")
    if a.duration is not None and a.duration <= 0:
        sys.exit("--duration must be positive")
    if a.fps is not None and not 1 <= a.fps <= 240:
        sys.exit("--fps must be 1..240")

    tpl = TEMPLATES[a.template]
    s = slug(a.name)
    proj = a.root / s
    created, kept = [], []
    for sub in ("assets", "audio", "docs", "renders"):
        (proj / sub).mkdir(parents=True, exist_ok=True)

    src = (TEMPLATES_DIR / tpl["file"]).read_text()
    m = MOTION_RE.search(src)
    if not m:
        sys.exit(f"{tpl['file']}: can't find the window.MOTION settings to fill in")
    old = re.findall(r"(\w+):\s*([\d.]+)", m.group(0)[len(m.group(1)):])
    vals = dict(old)
    w, h = FORMATS[fmts[0]]
    fps = a.fps or int(vals["fps"])
    dur = a.duration or float(vals["duration"])
    src = src[:m.start()] + m.group(1) + f"width: {w}, height: {h}, fps: {fps}, duration: {dur:g}" + src[m.end():]

    def put(path: Path, write, force):
        if path.exists() and not force:
            kept.append(str(path))
            return
        write(path)
        created.append(str(path))

    html = proj / f"{s}.html"
    put(html, lambda p: p.write_text(src), a.force)
    for f in ["kit.js", *tpl["extra"]]:
        put(proj / f, lambda p, f=f: shutil.copy2(TEMPLATES_DIR / f, p), a.force)
    put(proj / "brief.md", lambda p: p.write_text(brief_skeleton(a.name, fmts, dur, fps, a.template)), False)

    S = f"python3 {SKILL / 'scripts'}"
    nxt = []
    if tpl["vendor"]:
        nxt.append(f"{S}/vendor.py {proj} {tpl['vendor']}   (downloads {tpl['vendor']} from npm once, into {proj}/vendor/)")
    if tpl.get("models"):
        nxt.append(f"{S}/catalog.py use {proj} {' '.join(tpl['models'])}   (the demo's catalog models; swap for your own)")
    nxt.append(f"{S}/render.py {html} --format {','.join(fmts)} --check-only" + (" --gl" if tpl["gl"] else ""))
    print(json.dumps({"project": str(proj), "html": str(html), "template": a.template, "formats": fmts,
                      "fps": fps, "duration": dur, "gl": tpl["gl"], "created": created, "kept": kept, "next": nxt},
                     indent=2))


if __name__ == "__main__":
    main()
