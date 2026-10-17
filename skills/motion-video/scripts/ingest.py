#!/usr/bin/env python3
"""
ingest.py — copy local files (or files attached in Claude app chat) into a project's assets/
folder, normalise them for deterministic rendering, and keep an inventory (assets.json).

Everything is copied, never referenced in place, so the project folder is self-contained.
Re-running merges by original path: the same file is updated in place, never duplicated.

Usage:
  python3 ingest.py motion/promo ~/Desktop/logo.svg ~/Desktop/shots/   # files and folders
  python3 ingest.py motion/promo /mnt/user-data/uploads/* --attached     # chat uploads
  python3 ingest.py motion/promo hero.png --max-dim 3840                  # cap long side (px)
  python3 ingest.py motion/promo demo.mov --clip-fps 30                   # clip -> JPEG frames (+ its audio)
  python3 ingest.py motion/promo talk.mp4 --clip-max-dim 1280             # smaller frames for a corner card

Writes (under PROJECT/assets/):
  assets.json   inventory {version, assets:[{id, kind, path, source, orig, ...}]}
  assets.js     window.ASSETS = <assets.json>;   (for file:// previews)
  fonts.css     one @font-face per ingested font (rewritten every run)
  images/ svg/ fonts/ audio/ docs/ video/<id>/00000.jpg ...
  A clip's own sound becomes a second entry (kind audio, id <clip id>-audio, assets/audio/<that id>.wav,
  48 kHz) sample-aligned to the clip's frame 0; the video entry links to it as "audio".

Prints log lines, then a summary JSON {ingested, missing, unreadable, notes}.
Exit 1 if any input was missing or unreadable (the rest are still ingested).

Requires: Pillow; ffmpeg/ffprobe on PATH for video and audio.
"""
import argparse, io, json, os, re, shutil, subprocess, sys, tempfile, unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow missing: pip install Pillow")


def log(*a):
    print("[ingest]", *a, flush=True)


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".avif"}
SVG_EXT = {".svg"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".aif", ".aiff"}
DOC_EXT = {".pdf", ".txt", ".md", ".rtf", ".doc", ".docx", ".json", ".csv"}


class Unreadable(Exception):
    """Raised by a handler when an input can't be decoded."""


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    for kind, exts in (("image", IMAGE_EXT), ("svg", SVG_EXT), ("font", FONT_EXT),
                       ("video", VIDEO_EXT), ("audio", AUDIO_EXT)):
        if ext in exts:
            return kind
    return "doc"


def slug(stem: str) -> str:
    s = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "asset"


def walk(paths, skip_under: Path):
    """Yield (input_arg, file) for every file; folders are recursed, dotfiles skipped."""
    for p in paths:
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for f in sorted(files):
                    if f.startswith("."):
                        continue
                    fp = Path(root) / f
                    if skip_under in fp.resolve().parents:
                        continue
                    yield fp
        else:
            yield p


# ---------------------------------------------------------------- handlers
# Each handler gets (src, id, assets_dir, opts) and returns (entry_fields, notes).
# entry_fields["path"] is relative to assets_dir's parent (the project).

def handle_copy(src, aid, adir, sub, opts):
    dst = adir / sub / (aid + src.suffix.lower())
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return {"path": f"assets/{sub}/{dst.name}"}, []


def _decode_fallback(src: Path, tmpdir: Path):
    """Pillow can't read it (HEIC, odd TIFFs ...): try ffmpeg, then macOS sips. -> PNG path or None."""
    out = tmpdir / "decoded.png"
    cmds = []
    if shutil.which("ffmpeg"):
        cmds.append(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", "1", str(out)])
    if shutil.which("sips"):
        cmds.append(["sips", "-s", "format", "png", str(src), "--out", str(out)])
    for cmd in cmds:
        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
            with Image.open(out) as im:
                im.load()
            return out
        except Exception:
            continue
    return None


def _has_alpha(im) -> bool:
    if im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA").getchannel("A").getextrema()[0] < 255
    return False


def handle_image(src, aid, adir, opts):
    notes = []
    with tempfile.TemporaryDirectory() as td:
        try:
            im = Image.open(src)
            im.load()
        except Exception:
            dec = _decode_fallback(src, Path(td))
            if dec is None:
                raise Unreadable("not a readable image (tried Pillow, ffmpeg" +
                                 (", sips" if shutil.which("sips") else "") + ")")
            im = Image.open(dec)
            im.load()
        fmt = (im.format or "").upper()
        if fmt == "GIF" and getattr(im, "n_frames", 1) > 1:
            notes.append(f"animated GIF ({im.n_frames} frames): kept the first frame only")
            im.seek(0)
        icc = im.info.get("icc_profile")
        out_fmt, ext = {"JPEG": ("JPEG", ".jpg"), "WEBP": ("WEBP", ".webp")}.get(fmt, ("PNG", ".png"))
        changed = out_fmt != fmt
        if im.getexif().get(0x0112, 1) not in (0, 1):  # EXIF orientation: bake it in
            im, changed = ImageOps.exif_transpose(im), True
            notes.append("applied the EXIF rotation")
        w, h = im.size
        if max(w, h) > opts.max_dim:
            k = opts.max_dim / max(w, h)
            w, h = max(1, round(w * k)), max(1, round(h * k))
            if im.mode not in ("RGB", "RGBA", "L", "LA"):
                im = im.convert("RGBA" if _has_alpha(im) else "RGB")
            im = im.resize((w, h), Image.LANCZOS)
            notes.append(f"downscaled to {w}x{h} (--max-dim {opts.max_dim})")
            changed = True
        alpha = out_fmt != "JPEG" and _has_alpha(im)

        dst = adir / "images" / (aid + ext)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not changed:
            shutil.copyfile(src, dst)
        else:
            if out_fmt == "JPEG":
                im = im.convert("RGB")
            elif im.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
                im = im.convert("RGBA" if alpha else "RGB")
            kw = {"icc_profile": icc} if icc else {}
            if out_fmt == "JPEG":
                kw.update(quality=95, subsampling=0)
            elif out_fmt == "WEBP":
                kw.update(quality=95)
            im.save(dst, out_fmt, **kw)
        im.close()
    return {"path": f"assets/images/{dst.name}", "w": w, "h": h, "alpha": alpha}, notes


# ---- SVG sanitising: no scripts, no event handlers, no external references.

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XHTML_NS = "http://www.w3.org/1999/xhtml"
DROP_ELEMENTS = {"script", "foreignobject", "iframe", "embed", "object", "handler", "listener",
                 "audio", "video", "frame", "frameset", "link", "meta", "base"}
ANIM_ELEMENTS = {"set", "animate", "animatetransform", "animatemotion", "animatecolor"}
URL_ATTRS = {"href", "src", "action", "formaction", "data", "codebase", "from-uri"}
SAFE_DATA = re.compile(r"^data:image/(png|jpe?g|gif|webp);", re.I)
BAD_SCHEME = re.compile(r"(javascript|vbscript|livescript)\s*:|data:\s*text/html", re.I)


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _squash(v: str) -> str:
    return re.sub(r"[\s\x00-\x1f]+", "", v)


def _safe_ref(v: str) -> bool:
    v = v.strip()
    return v.startswith("#") or bool(SAFE_DATA.match(v))


def _clean_css(text: str) -> str:
    text = re.sub(r"@import\b[^;]*;?", "", text, flags=re.I)
    text = re.sub(r"expression\s*\(", "(", text, flags=re.I)

    def url(m):
        target = m.group(2).strip()
        return m.group(0) if _safe_ref(target) else "none"
    return re.sub(r"url\(\s*(['\"]?)(.*?)\1\s*\)", url, text, flags=re.I | re.S)


def _scrub(el):
    for child in list(el):
        if not isinstance(child.tag, str):  # comments / PIs
            el.remove(child)
            continue
        name = _local(child.tag)
        attrname = _local(child.get("attributeName", ""))
        anim_bad = name in ANIM_ELEMENTS and (
            attrname in URL_ATTRS or attrname.startswith("on") or
            any(BAD_SCHEME.search(_squash(child.get(k, ""))) or "url(" in child.get(k, "").lower()
                for k in ("to", "from", "values", "by")))
        if name in DROP_ELEMENTS or child.tag.startswith("{%s}" % XHTML_NS) or anim_bad:
            el.remove(child)
            continue
        _scrub(child)
    for k in list(el.attrib):
        name, v = _local(k), el.attrib[k]
        if name.startswith("on") or BAD_SCHEME.search(_squash(v)):
            del el.attrib[k]
        elif name in URL_ATTRS:
            if not _safe_ref(v):
                del el.attrib[k]
        elif "url(" in v.lower() or "@import" in v.lower():
            el.attrib[k] = _clean_css(v)
    if _local(el.tag) == "style" and el.text:
        el.text = _clean_css(el.text)
        if BAD_SCHEME.search(_squash(el.text)):
            el.text = BAD_SCHEME.sub("", el.text)


def _px(v):
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$", v or "")
    return float(m.group(1)) if m else None


def handle_svg(src, aid, adir, opts):
    data = src.read_bytes()
    doctype = re.search(rb"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", data, re.S | re.I)
    if doctype and doctype.group(1) or re.search(rb"<!ENTITY", data, re.I):
        raise Unreadable("SVG declares DTD entities (refused for safety)")
    if doctype:
        data = data[:doctype.start()] + data[doctype.end():]
    try:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
            if prefix and not re.match(r"ns\d+$", prefix):
                try:
                    ET.register_namespace(prefix, uri)
                except ValueError:
                    pass
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise Unreadable(f"not valid SVG/XML ({e})")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    if _local(root.tag) != "svg":
        raise Unreadable("root element is not <svg>")
    for el in root.iter():  # un-namespaced SVG -> proper SVG namespace (renders in <img>)
        if isinstance(el.tag, str) and not el.tag.startswith("{"):
            el.tag = "{%s}%s" % (SVG_NS, el.tag)
    _scrub(root)

    w, h = _px(root.get("width")), _px(root.get("height"))
    vb = re.split(r"[\s,]+", (root.get("viewBox") or "").strip())
    if len(vb) == 4 and (w is None or h is None):
        try:
            vw, vh = float(vb[2]), float(vb[3])
            if w is None and h is None:
                w, h = vw, vh
            elif w is None:
                w = h * vw / vh
            else:
                h = w * vh / vw
        except (ValueError, ZeroDivisionError):
            pass
    dst = adir / "svg" / (aid + ".svg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    notes = [] if w and h else ["no width/height or viewBox: size unknown"]
    return {"path": f"assets/svg/{dst.name}", "w": round(w) if w else None,
            "h": round(h) if h else None}, notes


# ---- fonts

WEIGHTS = [("hairline", 100), ("thin", 100), ("extralight", 200), ("ultralight", 200),
           ("semilight", 300), ("light", 300), ("semibold", 600), ("demibold", 600),
           ("extrabold", 800), ("ultrabold", 800), ("bold", 700), ("medium", 500),
           ("extrablack", 900), ("black", 900), ("heavy", 900)]
CSS_FORMAT = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}
FONT_MAGIC = {b"\x00\x01\x00\x00": ".ttf", b"true": ".ttf", b"OTTO": ".otf",
              b"wOFF": ".woff", b"wOF2": ".woff2"}


def font_weight(style: str) -> int:
    s = re.sub(r"[\s_-]+", "", (style or "").lower())
    for key, w in WEIGHTS:
        if key in s:
            return w
    return 400


def font_style(style: str) -> str:
    s = (style or "").lower()
    return "italic" if "italic" in s or "oblique" in s else "normal"


def handle_font(src, aid, adir, opts):
    from PIL import ImageFont
    notes = []
    ext = src.suffix.lower()
    head = src.read_bytes()[:4]
    if FONT_MAGIC.get(head) is None:
        raise Unreadable("not a TrueType/OpenType/WOFF font file")
    try:
        family, style = ImageFont.truetype(str(src), 12).getname()
    except Exception:
        if FONT_MAGIC[head] not in (".woff", ".woff2"):
            raise Unreadable("font file could not be loaded (corrupt?)")
        # this Pillow/FreeType build can't parse WOFF/WOFF2; browsers can. Guess names from the file.
        parts = [x for x in re.split(r"[-_ ]+", src.stem) if x]
        is_style = [font_weight(x) != 400 or font_style(x) == "italic" or x.lower() == "regular"
                    for x in parts]
        style = " ".join(x for x, st in zip(parts, is_style) if st) or "Regular"
        family = " ".join(x for x, st in zip(parts, is_style) if not st) or src.stem
        notes.append(f"couldn't read the font's name table here; guessed family '{family}', style '{style}' "
                     "from the file name. Check it")
    if not family:
        raise Unreadable("font has no family name")
    dst = adir / "fonts" / (aid + ext)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return {"path": f"assets/fonts/{dst.name}", "family": family, "style": style or "Regular",
            "weight": font_weight(style)}, notes


# ---- video and audio (ffmpeg)

def _ffprobe(src: Path):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise Unreadable("ffmpeg/ffprobe not on PATH (needed for video and audio)")
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,avg_frame_rate,r_frame_rate,sample_rate,start_time:"
                        "format=duration,start_time",
                        "-of", "json", str(src)], capture_output=True, text=True)
    if p.returncode != 0:
        raise Unreadable("ffprobe can't read it: " + (p.stderr.strip().splitlines() or ["unknown error"])[-1])
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise Unreadable("ffprobe returned no stream info")


def _ffmpeg(args, what):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise Unreadable(f"ffmpeg couldn't {what}: " + (p.stderr.strip().splitlines() or ["unknown error"])[-1])


def _num(x):
    return int(x) if float(x).is_integer() else x


def _rate(r):
    num, _, den = str(r or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _clip_audio(src, info, aid, adir, n_frames, fps):
    """The clip's first audio stream -> assets/audio/<aid>.wav (48 kHz stereo 16-bit), sample 0 =
    the clip's frame 0, exactly n_frames / fps long. Returns (audio entry fields, notes)."""
    import numpy as np, wave
    fmt0 = float(info.get("format", {}).get("start_time") or 0)
    v = next(st for st in info["streams"] if st.get("codec_type") == "video")
    v0 = float(v.get("start_time") or 0) - fmt0      # where frame 0 sits on the file's timeline
    # first_pts=0: pad a late-starting audio stream with silence so it lines up with the file timeline
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-map", "0:a:0", "-vn", "-sn",
                        "-af", "aresample=48000:async=1:first_pts=0", "-ac", "2", "-ar", "48000",
                        "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        raise Unreadable("ffmpeg couldn't decode the clip's audio: "
                         + (p.stderr.decode(errors="replace").strip().splitlines() or ["unknown error"])[-1])
    x = np.frombuffer(p.stdout, "<i2").reshape(-1, 2)
    k, n = int(round(v0 * 48000)), int(round(n_frames / fps * 48000))
    x = x[k:] if k >= 0 else np.concatenate([np.zeros((-k, 2), "<i2"), x])
    x = x[:n] if len(x) >= n else np.concatenate([x, np.zeros((n - len(x), 2), "<i2")])
    dst = adir / "audio" / (aid + ".wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{aid}.partial.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(np.ascontiguousarray(x).tobytes())
    os.replace(tmp, dst)
    notes = [f"audio offset {v0 * 1000:+.1f} ms vs the first frame: aligned"] if abs(v0) >= 0.0005 else []
    return {"path": f"assets/audio/{dst.name}", "duration": round(n / 48000, 4), "sr": 48000}, notes


def handle_video(src, aid, adir, opts):
    info = _ffprobe(src)
    streams = info.get("streams", [])
    vs = next((st for st in streams if st.get("codec_type") == "video"), None)
    if vs is None:
        raise Unreadable("no video stream")
    notes = []
    clip_fps = opts.clip_fps
    r, avg = _rate(vs.get("r_frame_rate")), _rate(vs.get("avg_frame_rate"))
    if r and avg and abs(r - avg) / r > 0.01:
        # phone footage is often VFR (e.g. 60 fps nominal, ~30 average): the fps filter below
        # resamples it to a constant rate, so frame k is always time k / clip_fps
        notes.append(f"variable frame rate source (nominal {r:g}, average {avg:.2f} fps): "
                     f"resampled to a constant {clip_fps:g} fps; cut on frame boundaries")
    if getattr(opts, "clip_fps_from", None) == "default":
        notes.append(f"frames at {clip_fps:g} fps (no MOTION.fps or brief fps found): re-ingest with "
                     "--clip-fps <piece fps> for 1:1 frames")
    final = adir / "video" / aid
    work = adir / "video" / f".{aid}.partial"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    m = opts.clip_max_dim or opts.max_dim
    vf = (f"fps={clip_fps},"
          f"scale='min(iw,{m})':'min(ih,{m})':force_original_aspect_ratio=decrease:flags=lanczos")
    try:
        # passthrough: frame 0 is the first real picture (no held copies padding a late video
        # start), so the clip audio is trimmed to match it in _clip_audio
        args = ["-i", str(src), "-an", "-sn", "-vf", vf, "-q:v", "2", "-start_number", "0",
                str(work / "%05d.jpg")]
        try:
            _ffmpeg(args[:6] + ["-fps_mode", "passthrough"] + args[6:], "extract frames")
        except Unreadable:   # ffmpeg < 5.1 has no -fps_mode
            _ffmpeg(args[:6] + ["-vsync", "passthrough"] + args[6:], "extract frames")
        frames = sorted(work.glob("*.jpg"))
        if not frames:
            raise Unreadable("no frames could be decoded")
        with Image.open(frames[0]) as im:
            w, h = im.size
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    shutil.rmtree(final, ignore_errors=True)
    os.replace(work, final)
    n = len(frames)
    if max(w, h) < max(int(vs.get("width") or 0), int(vs.get("height") or 0)):
        notes.append(f"frames downscaled to {w}x{h} (--{'clip-' if opts.clip_max_dim else ''}max-dim {m})")
    fps = _num(clip_fps)
    rel = f"assets/video/{aid}/"
    fields = {"path": rel, "w": w, "h": h, "fps": fps, "frame_count": n,
              "duration": round(n / clip_fps, 4), "pattern": rel + "%05d.jpg"}
    if any(st.get("codec_type") == "audio" for st in streams):
        fields["_audio"] = lambda audio_id: _clip_audio(src, info, audio_id, adir, n, clip_fps)
    else:
        notes.append("the clip has no audio stream (no clip audio written)")
    return fields, notes


def handle_audio(src, aid, adir, opts):
    info = _ffprobe(src)
    if not any(st.get("codec_type") == "audio" for st in info.get("streams", [])):
        raise Unreadable("no audio stream")
    dst = adir / "audio" / (aid + ".wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{aid}.partial.wav")
    try:
        _ffmpeg(["-i", str(src), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(tmp)],
                "convert the audio")
        dur = float(_ffprobe(tmp).get("format", {}).get("duration") or 0)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, dst)
    return {"path": f"assets/audio/{dst.name}", "duration": round(dur, 3), "sr": 48000}, []


def handle_doc(src, aid, adir, opts):
    fields, notes = handle_copy(src, aid, adir, "docs", opts)
    if src.suffix.lower() not in DOC_EXT:
        notes.append(f"unknown file type '{src.suffix or '(none)'}': stored as a doc")
    return fields, notes


HANDLERS = {"image": handle_image, "svg": handle_svg, "font": handle_font,
            "video": handle_video, "audio": handle_audio, "doc": handle_doc}


# ---------------------------------------------------------------- inventory

def load_inventory(adir: Path):
    f = adir / "assets.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            if isinstance(data.get("assets"), list):
                return data
        except (ValueError, AttributeError):
            log(f"warning: {f} is not valid JSON; starting a new inventory")
    return {"version": 1, "assets": []}


def remove_stored(project: Path, entry):
    p = project / entry.get("path", "")
    if not entry.get("path") or project.resolve() not in p.resolve().parents:
        return
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()


def write_inventory(adir: Path, inv):
    text = json.dumps(inv, indent=2)
    tmp = adir / "assets.json.tmp"
    tmp.write_text(text + "\n")
    os.replace(tmp, adir / "assets.json")
    (adir / "assets.js").write_text(f"window.ASSETS = {json.dumps(inv)};\n")


def write_fonts_css(adir: Path, inv):
    """Rewritten from the inventory every run, so it never holds duplicates or stale fonts."""
    out = ["/* fonts.css: written by ingest.py from assets.json. Do not edit; re-run ingest.py. */",
           '/* <link rel="stylesheet" href="assets/fonts.css"> then wait for document.fonts.ready */', ""]
    for e in inv["assets"]:
        if e.get("kind") != "font":
            continue
        rel = e["path"][len("assets/"):] if e["path"].startswith("assets/") else e["path"]
        fam = e.get("family", e["id"]).replace("\\", "\\\\").replace('"', '\\"')
        fmt = CSS_FORMAT.get(Path(rel).suffix.lower(), "truetype")
        out += ["@font-face {",
                f'  font-family: "{fam}";',
                f'  src: url("{rel}") format("{fmt}");',
                f"  font-weight: {e.get('weight', 400)};",
                f"  font-style: {font_style(e.get('style', ''))};",
                "  font-display: block;",
                "}", ""]
    (adir / "fonts.css").write_text("\n".join(out))


def ingest_clip_audio(project, adir, inv, by_orig, entry, clip_audio, source, summary):
    """E12.1: the clip's own sound as a linked audio entry (orig = '<clip orig>#audio')."""
    key = entry["orig"] + "#audio"
    old = by_orig.get(key)
    if clip_audio is None:
        if old:  # the new version of the clip has no audio: drop the stale one
            remove_stored(project, old)
            inv["assets"].remove(old)
            del by_orig[key]
        return None
    taken = {e["id"] for e in inv["assets"]}
    aid = old["id"] if old else entry["id"] + "-audio"
    n = 1
    while not old and aid in taken:
        n += 1
        aid = f"{entry['id']}-audio-{n}"
    try:
        fields, notes = clip_audio(aid)
    except Unreadable as e:
        summary["notes"].append({"id": entry["id"], "note": f"clip audio not written ({e})"})
        return None
    a = {"id": aid, "kind": "audio", "path": fields.pop("path"), "source": source, "orig": key,
         "of": entry["id"]}
    a.update(fields)
    if old:
        inv["assets"][inv["assets"].index(old)] = a
    else:
        inv["assets"].append(a)
    by_orig[key] = a
    entry["audio"] = aid
    for note in notes:
        summary["notes"].append({"id": aid, "note": note})
    summary["ingested"].append(a)
    return a


FPS_RE = re.compile(r"window\.MOTION\s*=\s*(?:K\.init\()?\{[^}]*?\bfps\s*:\s*(\d+(?:\.\d+)?)", re.S)


def piece_fps(project: Path):
    """The piece's fps, for --clip-fps: MOTION.fps of the project's composition(s), else an
    'NN fps' in brief.md, else None. -> (fps, where) or (None, None)."""
    found = set()
    for html in sorted(project.glob("*.html")):
        try:
            found |= {float(m) for m in FPS_RE.findall(html.read_text(errors="replace"))}
        except OSError:
            continue
    if len(found) == 1:
        return found.pop(), "MOTION.fps"
    brief = project / "brief.md"
    if not found and brief.exists():
        rates = {float(m) for m in re.findall(r"\b(\d{2})(?:\.0+)?\s*fps\b", brief.read_text(errors="replace"), re.I)}
        if len(rates) == 1:
            return rates.pop(), "brief.md"
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="project folder (the one holding the composition HTML)")
    ap.add_argument("paths", type=Path, nargs="+", help="files and/or folders to ingest")
    ap.add_argument("--attached", action="store_true",
                    help="mark these as files attached in Claude app chat (source: attached)")
    ap.add_argument("--max-dim", type=int, default=3840,
                    help="cap the long side of images and clips at this many px (default 3840)")
    ap.add_argument("--clip-max-dim", type=int,
                    help="cap the long side of clip frames separately (e.g. 1280 for a corner card; "
                         "default: --max-dim)")
    ap.add_argument("--clip-fps", type=float,
                    help="frame rate of the JPEG sequence extracted from video clips (default: the piece's "
                         "fps from the project's MOTION or brief.md, else 30)")
    a = ap.parse_args()
    if a.max_dim < 16 or (a.clip_max_dim is not None and a.clip_max_dim < 16):
        sys.exit("--max-dim / --clip-max-dim must be at least 16")
    if a.clip_fps is not None and a.clip_fps <= 0:
        sys.exit("--clip-fps must be positive")

    project = a.project
    if a.clip_fps is None:
        fps, where = piece_fps(project)
        a.clip_fps = fps or 30.0
        a.clip_fps_from = where or "default"
    adir = project / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    inv = load_inventory(adir)
    by_orig = {e.get("orig"): e for e in inv["assets"]}
    source = "attached" if a.attached else "local"
    summary = {"project": str(project), "ingested": [], "missing": [], "unreadable": [], "notes": []}

    present = []
    for p in a.paths:
        if not p.exists():
            log(f"missing: {p}")
            summary["missing"].append(str(p))
        else:
            present.append(p)

    seen = set()
    for src in walk(present, adir.resolve()):
        orig = str(src.resolve())
        if orig in seen:
            continue
        seen.add(orig)
        kind = kind_of(src)
        old = by_orig.get(orig)
        if old:
            aid = old["id"]
        else:
            base, n, taken = slug(src.stem), 1, {e["id"] for e in inv["assets"]}
            aid = base
            while aid in taken:
                n += 1
                aid = f"{base}-{n}"
        try:
            fields, notes = HANDLERS.get(kind, handle_doc)(src, aid, adir, a)
        except Unreadable as e:
            log(f"unreadable: {src} ({e})")
            summary["unreadable"].append({"path": str(src), "reason": str(e)})
            continue  # a previous good copy (if any) stays in the inventory
        if old and old.get("path") != fields["path"]:
            remove_stored(project, old)
        clip_audio = fields.pop("_audio", None)
        entry = {"id": aid, "kind": kind, "path": fields.pop("path"), "source": source, "orig": orig}
        entry.update(fields)
        if old:
            inv["assets"][inv["assets"].index(old)] = entry
        else:
            inv["assets"].append(entry)
        by_orig[orig] = entry
        for n in notes:
            summary["notes"].append({"id": aid, "note": n})
        log(f"{kind:5s} {aid:24s} <- {src}")
        summary["ingested"].append(entry)
        if kind == "video":
            derived = ingest_clip_audio(project, adir, inv, by_orig, entry, clip_audio, source, summary)
            if derived:
                log(f"audio {derived['id']:24s} <- {src} (clip audio)")

    write_inventory(adir, inv)
    write_fonts_css(adir, inv)
    summary["total"] = len(inv["assets"])
    print(json.dumps(summary, indent=2))
    sys.exit(1 if summary["missing"] or summary["unreadable"] else 0)


if __name__ == "__main__":
    main()
