#!/usr/bin/env python3
"""
reference.py — study a reference the user supplied (a local video, or stills) for rhythm and motion.

Local files only: this script never downloads anything. If the reference is online, the user
saves a copy they have the right to use and passes the path. References are for study: take the
rhythm, motion and composition into references/style_guide.md, never the footage or the brand.

Video:
  - hard cuts from ffmpeg's scene score (a frame scoring > --threshold, default 0.3, starts a shot)
  - one frame per shot (its middle) -> shots/NNN_<t>.png and a shots.png sheet
  - a 1 fps sheet -> sheet.png (longer than 60 s: 60 evenly spaced frames)
  - cuts.json: cut times, shots with lengths, cuts per minute, shot-length stats, and motion stats
    measured exactly like check.py: mean frame delta, still share (0.1 s windows where no
    40 px region visibly moves), longest still stretch, hard jumps per second
  NOTE: only hard cuts register. Match cuts, morphs, masks, whip pans and crossfades usually
  stay below the threshold, so a "one-shot" result can still be a very busy edit: look at the sheets.

Stills (image files or a folder of them): a sheet.png of all of them and a cuts.json with
"kind": "images" (no cut or motion numbers; check.py --against skips the pacing gate).

Outputs land in PROJECT/docs/reference/<name>/ (name = the video's or folder's stem, or --name).

Usage:
  python3 reference.py ~/Downloads/ref.mp4 motion/promo
  python3 reference.py ref.mp4 motion/promo --threshold 0.4 --name launch-ref
  python3 reference.py shots/ motion/promo                  # a folder of stills
  python3 reference.py a.png b.jpg c.png motion/promo       # loose stills
Then: python3 check.py renders/promo_16x9.mp4 --against motion/promo/docs/reference/ref/cuts.json

Prints the cuts.json summary to stdout. Requires: ffmpeg/ffprobe, numpy, Pillow.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("numpy and Pillow are needed: pip install numpy pillow")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402  (shared motion measurement, so --against compares like with like)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".gif"}
MAX_SHEET = 60  # tiles in the overview sheet


def log(*a):
    print("[reference]", *a, file=sys.stderr, flush=True)


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "reference"


def tile(paths, out: Path, cell=320, cols=6, pad=6):
    """Tile images of any size into one PNG: each letterboxed into a cell x cell*ratio box."""
    ims = [Image.open(p).convert("RGB") for p in paths]
    if not ims:
        return None
    ratio = max(im.height / im.width for im in ims)
    ch = int(round(cell * min(ratio, 2.0)))
    cols = max(1, min(cols, len(ims)))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell + (cols - 1) * pad, rows * ch + (rows - 1) * pad), "black")
    for i, im in enumerate(ims):
        im.thumbnail((cell, ch))
        x = (i % cols) * (cell + pad) + (cell - im.width) // 2
        y = (i // cols) * (ch + pad) + (ch - im.height) // 2
        sheet.paste(im, (x, y))
    sheet.save(out)
    return out


def grab(video, t, out: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    str(out)], check=True)
    return out


def analyse_video(video: Path, outdir: Path, threshold: float):
    st = check.motion_stats(video)
    fps, n = st["fps"], st["n"]
    if n == 0:
        sys.exit(f"no video frames decoded from {video}")
    v = check.video_stream(st["info"])
    dur = n / fps
    cuts = check.scene_cuts(video, threshold)
    bounds = [0.0] + [t for t, _ in cuts if 0 < t < dur] + [dur]
    shotdir = outdir / "shots"
    if shotdir.exists():
        shutil.rmtree(shotdir)
    shotdir.mkdir(parents=True)
    shots, frames = [], []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:]), 1):
        mid = a + (b - a) / 2
        p = grab(video, mid, shotdir / f"{i:03d}_{mid:07.3f}.png")
        frames.append(p)
        shots.append({"start": round(a, 3), "end": round(b, 3), "length": round(b - a, 3),
                      "frame": p.relative_to(outdir).as_posix()})
    tile(frames, outdir / "shots.png", cell=320, cols=6)
    k = min(MAX_SHEET, max(1, int(dur)))
    with tempfile.TemporaryDirectory(prefix="motion-ref-") as td:
        ts = [dur * (i + 0.5) / k for i in range(k)]
        tile([grab(video, t, Path(td) / f"{i:04d}.png") for i, t in enumerate(ts)], outdir / "sheet.png",
             cell=240, cols=10)
    lengths = np.array([s["length"] for s in shots])
    hold, where, share = check.longest_still(st)
    jumps = check.pops(st["d"], fps)
    return {
        "version": 1, "kind": "video", "source": str(video), "duration": round(dur, 3), "fps": round(fps, 3),
        "width": int(v["width"]), "height": int(v["height"]), "threshold": threshold,
        "cuts": [t for t, _ in cuts if 0 < t < dur], "scores": [s for t, s in cuts if 0 < t < dur],
        "cuts_per_min": round((len(bounds) - 2) / dur * 60, 2),
        "shot_length": {"mean": round(float(lengths.mean()), 3), "median": round(float(np.median(lengths)), 3),
                        "min": round(float(lengths.min()), 3), "max": round(float(lengths.max()), 3)},
        "shots": shots,
        "motion": {"mean_delta": round(float(st["d"].mean()), 3) if len(st["d"]) else 0.0,
                   "still_share": round(share, 3), "longest_still": round(hold, 3),
                   "longest_still_at": round(where, 3),
                   "hard_jumps_per_s": round(len(jumps) / dur, 3)},
        "sheet": "sheet.png", "shots_sheet": "shots.png",
        "note": ("Hard cuts only: match cuts, morphs, masks, whip pans and crossfades usually don't "
                 "register as cuts. Motion stats use check.py's measurement (320 px grey, 40 px "
                 "regions, 0.1 s windows), so check.py --against compares like with like."),
    }


def analyse_images(images, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    tile(images, outdir / "sheet.png", cell=320, cols=6)
    return {"version": 1, "kind": "images", "source": [str(p) for p in images], "count": len(images),
            "sheet": "sheet.png",
            "note": "Stills: no cuts or motion to measure. Study composition, palette roles and type scale."}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", metavar="INPUT", help="a local video, image files or a folder of images, then the project folder")
    ap.add_argument("--threshold", type=float, default=check.SCENE_THRESHOLD,
                    help=f"ffmpeg scene score that counts as a hard cut (default {check.SCENE_THRESHOLD})")
    ap.add_argument("--name", help="output folder name under docs/reference/ (default: the input's stem)")
    a = ap.parse_args()
    if len(a.inputs) < 2:
        ap.error("give the reference (video, images or a folder) and then the project folder")
    *srcs, project = a.inputs
    project = Path(project)
    for s in srcs:
        if re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I):
            sys.exit(f"{s}: reference.py analyses local files only and never downloads. Save a copy you "
                     "have the right to use, then pass its path.")
    paths = [Path(s).expanduser() for s in srcs]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        sys.exit("not found: " + ", ".join(missing))
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe not found on PATH")

    images = []
    for p in paths:
        if p.is_dir():
            images += sorted(q for q in p.iterdir() if q.suffix.lower() in IMAGE_EXT)
        elif p.suffix.lower() in IMAGE_EXT and not (p.suffix.lower() == ".gif" and len(paths) == 1):
            images.append(p)
    videos = [p for p in paths if p.is_file() and p not in images]
    if videos and (len(videos) > 1 or images):
        sys.exit("give one video, or only stills (files or a folder)")
    if not videos and not images:
        sys.exit("no video or images found in " + ", ".join(srcs))

    name = slug(a.name or paths[0].stem if len(paths) == 1 else a.name or "stills")
    outdir = project / "docs" / "reference" / name
    outdir.mkdir(parents=True, exist_ok=True)
    if videos:
        log(f"analysing {videos[0]} (scene threshold {a.threshold})")
        data = analyse_video(videos[0], outdir, a.threshold)
    else:
        log(f"{len(images)} still(s)")
        data = analyse_images(images, outdir)
    (outdir / "cuts.json").write_text(json.dumps(data, indent=2))
    log(f"-> {outdir / 'cuts.json'}")
    summary = {k: data[k] for k in ("kind", "duration", "cuts_per_min", "shot_length", "motion", "count")
               if k in data}
    if "cuts" in data:
        summary["cuts"] = len(data["cuts"])
    summary["outputs"] = str(outdir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
