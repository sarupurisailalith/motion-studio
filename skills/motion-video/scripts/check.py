#!/usr/bin/env python3
"""
check.py — automated QA on a rendered video (the "smoke test" before a human looks).

Gates (each pass/warn/fail):
  blank      frames that are a single flat colour (broken scene, missing asset)
  pops       single-frame jumps: frame-diff spike > 3x its neighbours (glitchy cut, mis-seek)
  frozen     stretches with no visible change longer than --max-hold seconds (dead time)
  loop_seam  last frame -> first frame jump vs. typical motion (only with --loop)
  audio      integrated loudness (LUFS) if the file has audio

Also writes a contact sheet (4x4) next to the video for visual review.

Usage: python3 check.py renders/comp.mp4 [--loop] [--max-hold 1.0]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,nb_frames:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def frames_gray(path, w=160):
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    W, H = int(v["width"]), int(v["height"])
    h = int(round(H * w / W / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    num, den = map(int, v["r_frame_rate"].split("/"))
    return arr, num / den, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--max-hold", type=float, default=1.0, help="longest acceptable still stretch (s)")
    ap.add_argument("--no-sheet", action="store_true")
    a = ap.parse_args()

    fr, fps, info = frames_gray(a.video)
    n = len(fr)
    res = {"video": str(a.video), "frames": n, "fps": round(fps, 3), "gates": {}}

    # blank
    stds = fr.reshape(n, -1).std(axis=1)
    blank = np.where(stds < 1.0)[0]
    res["gates"]["blank"] = "pass" if len(blank) == 0 else f"FAIL {len(blank)} flat frames, first at {blank[0] / fps:.2f}s"

    # diffs
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))  # d[i] = change from frame i to i+1
    pops = []
    for i in range(1, len(d) - 1):
        nb = max(d[i - 1], d[i + 1], 0.5)
        if d[i] > 3 * nb and d[i] > 6:
            pops.append(round((i + 1) / fps, 3))
    res["gates"]["pops"] = "pass" if not pops else f"WARN {len(pops)} single-frame jumps at {pops[:10]} s (intentional cuts are ok; check each)"

    # frozen
    still = d < 0.15
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
    hold = longest / fps
    res["gates"]["frozen"] = "pass" if hold <= a.max_hold else f"WARN longest still stretch {hold:.2f}s at {where / fps:.2f}s (limit {a.max_hold}s)"
    res["still_share"] = round(float(still.mean()), 3)
    res["motion_mean"] = round(float(d.mean()), 3)

    # loop seam
    if a.loop:
        seam = float(np.abs(fr[-1] - fr[0]).mean())
        typical = float(np.median(d)) + 1e-6
        res["gates"]["loop_seam"] = "pass" if seam <= max(3 * typical, 1.0) else f"WARN last->first change {seam:.2f} vs typical {typical:.2f}"

    # audio loudness
    if any(s["codec_type"] == "audio" for s in info["streams"]):
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a.video), "-af", "ebur128", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
        if m:
            lufs = float(m[-1])
            res["lufs"] = lufs
            res["gates"]["audio"] = "pass" if -16.5 <= lufs <= -12.5 else f"WARN integrated {lufs} LUFS (target -14)"

    # contact sheet
    if not a.no_sheet:
        sheet = a.video.with_name(a.video.stem + "_sheet.png")
        step = max(1, n // 16)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(a.video), "-vf",
                        f"select='not(mod(n\\,{step}))',scale=400:-1,tile=4x4:padding=6:color=black",
                        "-frames:v", "1", "-fps_mode", "vfr", str(sheet)], check=False)
        res["contact_sheet"] = str(sheet)

    print(json.dumps(res, indent=2))
    sys.exit(1 if any(str(v).startswith("FAIL") for v in res["gates"].values()) else 0)


if __name__ == "__main__":
    main()
