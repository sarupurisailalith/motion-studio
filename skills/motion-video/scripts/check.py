#!/usr/bin/env python3
"""
check.py — automated QA on a rendered video (the "smoke test" before a human looks).

Frames are analysed in grey at 320 px wide. "diff" = mean absolute change per pixel (0-255)
between consecutive frames, over the whole frame. "local motion" = the largest change in any
40 x 40 px tile (at 320 px) over 0.1 s, ignoring per-pixel changes of 3 levels or less
(encoder noise). A 10 px box moving 30 px/s in a 1080 px frame still counts as motion.

Gates, each reported as pass, WARN or FAIL (any FAIL -> exit code 1):
  blank      FAIL  frames that are one flat colour (pixel std < 1): broken scene, missing asset
  pops       WARN  single-frame jumps: a diff > 3x both neighbours and > 6 (glitchy cut, mis-seek)
  frozen     WARN  longest stretch where local motion stays < 0.25 is longer than --max-hold s
                   (dead time). Anything that visibly moves anywhere in the frame breaks a
                   stretch; an intended breather longer than the limit is fine: say so.
  loop_seam  WARN  last -> first frame change > 3x the median diff (only with --loop)
  audio      WARN  integrated loudness within -14 ±2.5 LUFS. Quieter audio still passes as
                   "sparse" when its true peak is within 3 dB of full scale (SFX-only pieces that
                   mix.py peak-normalised: short sounds can't get louder without distortion)
  sync       FAIL  with --sync sfx_events.json: each transient SFX within ±20 ms of its hit (sync.py)
  pacing     WARN  with --against docs/reference/<name>/cuts.json (reference.py): our hard cuts per
                   minute or our motion share (1 - still share) is more than 30 % below the
                   reference's ("slower") or above it ("busier"). Hard cuts only: morphs and
                   match cuts don't count, so read it as a hint, not a verdict.
  av_sync    FAIL  with --edl edl.json (footage): each EDL segment's voice within 1 frame of its
                   source audio, by cross-correlation (cut.py sync)

Also reported: still_share (share of 0.1 s windows with no local motion), motion_mean (mean diff).

Outputs: the JSON report on stdout (and in --json FILE), plus a 4x4 QA contact sheet
<video stem>_qa_sheet.png next to the video (never the _sheet.png that render.py --deliver writes).

Usage: python3 check.py renders/comp.mp4 [--loop] [--max-hold 1.0] [--json renders/comp_qa.json]
       python3 check.py renders/comp.mp4 --sync audio/sfx_events.json
       python3 check.py renders/comp.mp4 --against docs/reference/ref/cuts.json
       python3 check.py renders/comp.mp4 --edl edl.json        # footage: lip sync at every cut
"""
import argparse, json, re, subprocess, sys
from collections import deque
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

ANALYSIS_W = 320       # px, grey analysis width
TILE = 40              # px at ANALYSIS_W: the region local motion is measured over
NOISE_FLOOR = 3.0      # per-pixel change (0-255) treated as encoder noise
STILL_LEVEL = 0.25     # a 0.1 s window is "still" when no tile's mean change exceeds this
SCENE_THRESHOLD = 0.3  # ffmpeg scene score above which a frame starts a new shot
PACE_TOLERANCE = 0.30  # --against: flag more than 30 % slower or busier


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,nb_frames:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def video_stream(info):
    return next(s for s in info["streams"] if s["codec_type"] == "video")


def iter_gray(path, w=ANALYSIS_W, info=None):
    """Yield the frames of `path` one by one as float32 grey arrays w px wide (streamed, so long
    or tall videos don't have to fit in memory)."""
    v = video_stream(info or probe(path))
    W, H = int(v["width"]), int(v["height"])
    h = max(2, int(round(H * w / W / 2) * 2))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray",
                             "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = w * h
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w).astype(np.float32)
    finally:
        proc.stdout.close()
        proc.wait()


def tile_change(a, b, tile=TILE, floor=NOISE_FLOOR):
    """Largest mean change of any ~tile x tile region between two grey frames, ignoring
    per-pixel changes <= floor (the grid spans the whole frame; edge tiles absorb the rest)."""
    d = np.maximum(np.abs(a - b) - floor, 0.0)
    h, w = d.shape
    ys = np.linspace(0, h, max(1, h // tile) + 1).astype(int)
    xs = np.linspace(0, w, max(1, w // tile) + 1).astype(int)
    sums = np.add.reduceat(np.add.reduceat(d, ys[:-1], axis=0), xs[:-1], axis=1)
    return float((sums / np.outer(np.diff(ys), np.diff(xs))).max())


def motion_stats(path, w=ANALYSIS_W):
    """One streamed pass over the video. Returns fps, info, the frame count n, and per frame:
    std (flatness), d (global mean diff to the next frame, len n - 1), local (tile_change to
    the frame 0.1 s = lag frames later, len n - lag), plus the first and last frames."""
    info = probe(path)
    v = video_stream(info)
    num, den = map(int, v["r_frame_rate"].split("/"))
    fps = num / den
    lag = max(1, int(round(fps / 10)))
    stds, d, local = [], [], []
    ring = deque(maxlen=lag + 1)
    first = prev = None
    for f in iter_gray(path, w, info):
        stds.append(float(f.std()))
        if prev is None:
            first = f
        else:
            d.append(float(np.abs(f - prev).mean()))
        ring.append(f)
        if len(ring) == lag + 1:
            local.append(tile_change(ring[0], ring[-1]))
        prev = f
    return {"fps": fps, "info": info, "n": len(stds), "lag": lag, "std": np.array(stds),
            "d": np.array(d), "local": np.array(local), "first": first, "last": prev}


def pops(d, fps):
    """Times (s) of single-frame jumps: a diff > 3x both neighbours and > 6."""
    out = []
    for i in range(1, len(d) - 1):
        nb = max(d[i - 1], d[i + 1], 0.5)
        if d[i] > 3 * nb and d[i] > 6:
            out.append(round((i + 1) / fps, 3))
    return out


def longest_still(st):
    """(longest still stretch in s, its start in s, still share) from motion_stats output."""
    still = st["local"] < STILL_LEVEL
    longest, run, start, where = 0, 0, 0, 0
    for i, s in enumerate(still):
        if s:
            if run == 0:
                start = i
            run += 1
            if run > longest:
                longest, where = run, start
        else:
            run = 0
    # r consecutive still windows of `lag` frame steps span r + lag - 1 frame steps
    hold = (longest + st["lag"] - 1) / st["fps"] if longest else 0.0
    share = float(still.mean()) if len(still) else 0.0
    return hold, where / st["fps"], share


def scene_cuts(path, threshold=SCENE_THRESHOLD):
    """Hard cuts via ffmpeg's scene score: [(t, score)] for each frame scoring above threshold.
    Match cuts, morphs, whip pans and crossfades usually stay below it and don't register."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-vf",
                        f"select='gt(scene\\,{threshold})',metadata=print:file=-", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    cuts, t = [], None
    for line in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"lavfi\.scene_score=([\d.]+)", line)
        if m and t is not None:
            cuts.append((round(t, 3), round(float(m.group(1)), 3)))
            t = None
    return cuts


def pacing(ours, ref):
    """Compare {cuts_per_min, motion_share} dicts -> (status, detail lines)."""
    lines, flags = [], []
    for key, label in (("cuts_per_min", "hard cuts/min"), ("motion_share", "motion share")):
        a, b = ours[key], ref.get(key)
        if b is None:
            lines.append(f"{label}: no reference value")
            continue
        if b <= 0:
            lines.append(f"{label} {a:g} vs reference {b:g} (reference has none: not compared)")
            continue
        ratio = a / b
        lines.append(f"{label} {a:g} vs reference {b:g} ({ratio:.2f}x)")
        if ratio < 1 - PACE_TOLERANCE:
            flags.append(f"{label} {a:g} is {100 * (1 - ratio):.0f} % below the reference's {b:g} (slower)")
        elif ratio > 1 + PACE_TOLERANCE:
            flags.append(f"{label} {a:g} is {100 * (ratio - 1):.0f} % above the reference's {b:g} (busier)")
    return ("pass" if not flags else "WARN " + "; ".join(flags)), lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path, help="the rendered MP4")
    ap.add_argument("--loop", action="store_true", help="the piece loops: add the loop_seam gate")
    ap.add_argument("--max-hold", type=float, default=1.0, help="longest acceptable still stretch (s, default 1.0)")
    ap.add_argument("--no-sheet", action="store_true", help="skip the QA contact sheet")
    ap.add_argument("--json", type=Path, metavar="FILE", help="also write the JSON report to FILE")
    ap.add_argument("--sync", type=Path, metavar="SFX_EVENTS", help="sfx_events.json: add the sync gate")
    ap.add_argument("--against", type=Path, metavar="CUTS_JSON",
                    help="a reference.py cuts.json: add the pacing gate (cut rate and still share)")
    ap.add_argument("--edl", type=Path, metavar="EDL", help="edl.json (footage pieces): add the av_sync gate")
    a = ap.parse_args()

    st = motion_stats(a.video)
    fps, info, n, d = st["fps"], st["info"], st["n"], st["d"]
    if n == 0:
        sys.exit(f"no video frames decoded from {a.video}")
    res = {"video": str(a.video), "frames": n, "fps": round(fps, 3), "gates": {}}

    # blank
    blank = np.where(st["std"] < 1.0)[0]
    res["gates"]["blank"] = "pass" if len(blank) == 0 else f"FAIL {len(blank)} flat frames, first at {blank[0] / fps:.2f}s"

    # pops
    p = pops(d, fps)
    res["gates"]["pops"] = "pass" if not p else f"WARN {len(p)} single-frame jumps at {p[:10]} s (intentional cuts are ok; check each)"

    # frozen
    hold, where, share = longest_still(st)
    res["gates"]["frozen"] = ("pass" if hold <= a.max_hold else
                              f"WARN longest still stretch {hold:.2f}s at {where:.2f}s (limit {a.max_hold}s; nothing in "
                              "the frame visibly moves: if it's an intended breather, say so)")
    res["still_share"] = round(share, 3)
    res["motion_mean"] = round(float(d.mean()), 3) if len(d) else 0.0

    # loop seam
    if a.loop:
        seam = float(np.abs(st["last"] - st["first"]).mean())
        typical = (float(np.median(d)) if len(d) else 0.0) + 1e-6
        res["gates"]["loop_seam"] = "pass" if seam <= max(3 * typical, 1.0) else f"WARN last->first change {seam:.2f} vs typical {typical:.2f}"

    # audio loudness
    if any(s["codec_type"] == "audio" for s in info["streams"]):
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a.video), "-af", "ebur128=peak=true", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
        if m:
            lufs = float(m[-1])
            tpm = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err[err.rfind("Summary:"):])
            tp = float(tpm[-1]) if tpm else None
            res["lufs"] = lufs
            res["true_peak"] = tp
            if -16.5 <= lufs <= -12.5:
                res["gates"]["audio"] = "pass"
            elif lufs < -16.5 and tp is not None and tp >= -4.0:
                res["gates"]["audio"] = f"pass (sparse: integrated {lufs} LUFS, true peak {tp} dBTP)"
            else:
                res["gates"]["audio"] = f"WARN integrated {lufs} LUFS (target -14), true peak {tp} dBTP"

    # picture/sound sync (same measurement as sync.py)
    if a.sync:
        if not any(s["codec_type"] == "audio" for s in info["streams"]):
            res["gates"]["sync"] = "FAIL no audio stream to check against the hits"
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import _audio, sync
            rep = sync.run(_audio.load(a.video, _audio.SR), _audio.SR, a.sync)
            res["sync"] = rep["hits"]
            res["gates"]["sync"] = rep["status"]

    # pacing against a reference (reference.py cuts.json)
    if a.against:
        try:
            ref = json.loads(a.against.read_text())
        except (OSError, ValueError) as e:
            sys.exit(f"--against: can't read {a.against}: {e}")
        if ref.get("kind") != "video" or "motion" not in ref:
            res["gates"]["pacing"] = "skipped (the reference is stills, not a video: no cut rate to compare)"
        else:
            dur = n / fps if fps else 0.0
            cuts = scene_cuts(a.video, ref.get("threshold", SCENE_THRESHOLD))
            ours = {"cuts_per_min": round(len(cuts) / dur * 60, 2) if dur else 0.0,
                    "motion_share": round(1 - share, 3)}
            theirs = {"cuts_per_min": ref.get("cuts_per_min"),
                      "motion_share": round(1 - ref["motion"]["still_share"], 3)}
            status, lines = pacing(ours, theirs)
            res["gates"]["pacing"] = status
            res["pacing"] = {"reference": str(a.against), "ours": ours, "reference_values": theirs,
                             "cuts": [c[0] for c in cuts], "detail": lines}

    # footage A/V sync: every EDL segment's voice vs its source audio (same as cut.py sync)
    if a.edl:
        if not any(s["codec_type"] == "audio" for s in info["streams"]):
            res["gates"]["av_sync"] = "FAIL no audio stream to check against the EDL"
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import _audio, cut
            rep = cut.avsync(_audio.load(a.video, _audio.SR), _audio.SR, cut.load_edl(a.edl), a.edl.parent)
            res["av_sync"] = rep["segments"]
            res["gates"]["av_sync"] = rep["status"]

    # contact sheet
    if not a.no_sheet:
        sheet = a.video.with_name(a.video.stem + "_qa_sheet.png")   # never render.py's _sheet.png
        step = max(1, n // 16)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(a.video), "-vf",
                        f"select='not(mod(n\\,{step}))',scale=400:-1,tile=4x4:padding=6:color=black",
                        "-frames:v", "1", "-fps_mode", "vfr", str(sheet)], check=False)
        res["contact_sheet"] = str(sheet)

    print(json.dumps(res, indent=2))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2))
    sys.exit(1 if any(str(v).startswith("FAIL") for v in res["gates"].values()) else 0)


if __name__ == "__main__":
    main()
