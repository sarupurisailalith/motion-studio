#!/usr/bin/env python3
"""
check.py — automated QA on a rendered video (the "smoke test" before a human looks).

Frames are analysed in grey at 160 px wide; "diff" = mean absolute change per pixel (0-255)
between consecutive frames.

Gates, each reported as pass, WARN or FAIL (any FAIL -> exit code 1):
  blank      FAIL  frames that are one flat colour (pixel std < 1): broken scene, missing asset
  pops       WARN  single-frame jumps: a diff > 3x both neighbours and > 6 (glitchy cut, mis-seek)
  frozen     WARN  longest run of diffs < 0.15 longer than --max-hold s (dead time). Coarse at
                   160 px: small or slow movers can read as "still"; judge the frames before acting.
  loop_seam  WARN  last -> first frame change > 3x the median diff (only with --loop)
  audio      WARN  integrated loudness within -14 ±2.5 LUFS. Quieter audio still passes as
                   "sparse" when its true peak is within 3 dB of full scale (SFX-only pieces that
                   mix.py peak-normalised: short sounds can't get louder without distortion)
  sync       FAIL  with --sync sfx_events.json: each transient SFX within ±20 ms of its hit (sync.py)

Outputs: the JSON report on stdout (and in --json FILE), plus a 4x4 QA contact sheet
<video stem>_qa_sheet.png next to the video (never the _sheet.png that render.py --deliver writes).

Usage: python3 check.py renders/comp.mp4 [--loop] [--max-hold 1.0] [--json renders/comp_qa.json]
       python3 check.py renders/comp.mp4 --sync audio/sfx_events.json
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path, help="the rendered MP4")
    ap.add_argument("--loop", action="store_true", help="the piece loops: add the loop_seam gate")
    ap.add_argument("--max-hold", type=float, default=1.0, help="longest acceptable still stretch (s, default 1.0)")
    ap.add_argument("--no-sheet", action="store_true", help="skip the QA contact sheet")
    ap.add_argument("--json", type=Path, metavar="FILE", help="also write the JSON report to FILE")
    ap.add_argument("--sync", type=Path, metavar="SFX_EVENTS", help="sfx_events.json: add the sync gate")
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
