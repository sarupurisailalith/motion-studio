#!/usr/bin/env python3
"""
mix.py — mix music + sfx + voice-over, master to -14 LUFS / -1 dBTP, and mux into videos.

  - Every stem is decoded with ffmpeg (any format), resampled to 48 kHz stereo and padded with
    silence or trimmed to --duration. Without --duration the composition's length is read from
    renders/deliver.json (the item for a --mux video), else renders/*_hits.json, looked for next
    to the --mux videos, in P/renders/ for --out P/audio/mix.wav, and in ./renders/.
  - Music is ducked under the VO (default -14 dB, 50 ms attack with 50 ms lookahead, 300 ms release).
  - Master: two-pass ffmpeg loudnorm (I=-14, TP=-1.5, LRA=11, linear), then measured with ebur128;
    if it is off by more than 0.1 LU or the true peak is above -1.1 dBTP, a corrective gain and a
    true-peak limiter (4x oversampled) are applied and it is measured again.
  - Sparse mode (automatic when there is no music and no VO, i.e. SFX only): short sounds in silence
    can't reach -14 LUFS without heavy limiting (it crushed clicks by ~9 dB and still missed), so
    the mix is peak-normalised to -1.5 dBTP with no limiting; the loudness is whatever that gives
    and is reported ("mode": "sparse", "lufs", "max_momentary"). check.py's audio gate accepts it.
  - Output: 48 kHz stereo 24-bit WAV.

Usage:
  python3 mix.py --duration 12 --music audio/music.wav --sfx audio/sfx.wav --out audio/mix.wav
  python3 mix.py --sfx audio/sfx.wav --out audio/mix.wav    # duration from renders/*_hits.json
  python3 mix.py --duration 12 --music m.wav --vo vo.wav --out mix.wav --stems
        # also writes mix_music_only.wav and mix_no_vo.wav (each mastered to -14 LUFS)
  python3 mix.py --duration 12 --music m.wav --sfx s.wav --out mix.wav --mux renders/comp.mp4 renders/comp_9x16.mp4
        # replaces each video's audio with the mix (AAC 48 kHz 192k), video stream copied untouched;
        # a renders/deliver.json listing that video gets its audio / size_bytes refreshed

Levels: --music-db / --sfx-db / --vo-db trim each stem before the master (default 0 dB).
"""
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio  # noqa: E402

TARGET_I, TARGET_TP, LRA = -14.0, -1.5, 11.0   # loudnorm aims 0.5 dB under the -1 dBTP limit
LIMIT_TP = -1.0


def log(*a):
    print("[mix]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------ ducking
def duck_envelope(vo_mono, sr, depth_db=-14.0, attack=0.05, release=0.3, hold=0.15):
    """Linear gain (one value per sample) for the music: depth_db while the VO is active.
    Activity = 10 ms RMS above max(-50 dBFS, loudest - 30 dB), held for `hold` s. The gain slews
    in dB, reaching full depth `attack` s after the VO starts (it starts `attack` s early:
    lookahead) and recovering over `release` s."""
    vo = np.asarray(vo_mono, np.float64)
    if vo.ndim > 1:
        vo = vo.mean(axis=1)
    hop = max(1, int(sr * 0.01))
    nf = int(np.ceil(len(vo) / hop))
    fr = np.pad(vo, (0, nf * hop - len(vo))).reshape(nf, hop)
    rdb = 20 * np.log10(np.sqrt(np.mean(fr ** 2, axis=1)) + 1e-12)
    active = rdb > max(-50.0, rdb.max() - 30.0)
    h = int(round(hold / 0.01))
    if h and active.any():
        idx = np.where(active)[0]
        for i in idx:
            active[i:i + h + 1] = True
    look = int(round(attack / 0.01))
    if look:
        active = np.concatenate([active[look:], np.zeros(look, bool)]) | active
    target = np.where(active, depth_db, 0.0)
    down = abs(depth_db) * 0.01 / max(attack, 1e-3)
    up = abs(depth_db) * 0.01 / max(release, 1e-3)
    g = np.zeros(nf)
    cur = 0.0
    for i in range(nf):
        d = target[i] - cur
        cur += max(-down, min(up, d))
        g[i] = cur
    gdb = np.interp(np.arange(len(vo)), np.arange(nf) * hop, g)
    return 10 ** (gdb / 20)


# ------------------------------------------------------------------------------ mastering
def true_peak_limit(x, sr, ceiling_db=-1.5, window=0.003):
    """Brick-wall gain riding on a 4x-oversampled peak estimate (lookahead = window)."""
    n = len(x)
    up = np.abs(np.fft.irfft(np.fft.rfft(x, axis=0), 4 * n, axis=0) * 4).reshape(n, 4, -1).max(axis=(1, 2))
    c = 10 ** (ceiling_db / 20)
    g = np.minimum(1.0, c / np.maximum(up, 1e-12))
    if g.min() >= 1.0:
        return x
    r = 2 * max(1, int(window * sr / 2))  # even, so the centred average below keeps length n
    gm = np.min(np.lib.stride_tricks.sliding_window_view(np.pad(g, r, constant_values=1.0), 2 * r + 1), axis=1)
    # centred moving average over r+1 samples of a min over 2r+1: never above the needed gain
    gs = np.convolve(np.pad(gm, r // 2, mode="edge"), np.ones(r + 1) / (r + 1), "valid")
    return x * np.minimum(gs, 1.0)[:, None]


def master_sparse(x, sr, out):
    """SFX-only: peak-normalise to TARGET_TP (true peak), no limiting. -> (lufs, tp, max momentary)."""
    peak = float(np.abs(x).max())
    if peak == 0:
        sys.exit("the mix is silent; nothing to master")
    y = x * (10 ** (TARGET_TP / 20) / peak)
    for _ in range(4):                       # sample peak -> true peak: inter-sample overs
        _audio.write_wav(out, y, sr)
        lufs, tp = _audio.ebur128(out)
        if tp <= TARGET_TP + 0.2:
            break
        y = y * 10 ** ((TARGET_TP - tp) / 20)
    return lufs, tp, _audio.max_momentary(out)


def master(x, sr, out, tmp):
    """Two-pass loudnorm, then verify/correct. Writes `out`; returns (lufs, true_peak)."""
    n = len(x)
    peak = float(np.abs(x).max())
    if peak == 0:
        sys.exit("the mix is silent; nothing to master")
    src = Path(tmp) / "pre.wav"
    _audio.write_wav(src, x * (0.9 / peak), sr)  # loudness is normalised anyway; keep headroom
    m = _audio.loudnorm_measure(src, TARGET_I, TARGET_TP, LRA)
    af = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={LRA}:measured_I={m['input_i']}:"
          f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true")
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-af", af, "-ar", str(sr), "-ac", "2",
                        "-f", "f32le", "-"], capture_output=True)
    if p.returncode != 0:
        sys.exit("loudnorm failed: " + p.stderr.decode(errors="replace")[-400:])
    y = _audio.fit(np.frombuffer(p.stdout, np.float32).reshape(-1, 2).astype(np.float64), n)
    for _ in range(8):
        _audio.write_wav(out, y, sr)
        lufs, tp = _audio.ebur128(out)
        if abs(lufs - TARGET_I) <= 0.1 and tp <= LIMIT_TP - 0.1:
            break
        y = true_peak_limit(y * 10 ** ((TARGET_I - lufs) / 20), sr, TARGET_TP)
    return lufs, tp


def load_stem(path, n, db):
    if not Path(path).exists():
        sys.exit(f"not found: {path}")
    return _audio.fit(_audio.load(path, _audio.SR, channels=2).astype(np.float64), n) * 10 ** (db / 20)


def mux(video, wav):
    video = Path(video)
    if not video.exists():
        sys.exit(f"not found: {video}")
    tmp = video.with_name(f".{video.stem}.mux{video.suffix}")
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(wav), "-map", "0:v:0",
                        "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-shortest", "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if p.returncode != 0:
        tmp.unlink(missing_ok=True)
        sys.exit(f"mux into {video} failed: {p.stderr.strip()[-400:]}")
    os.replace(tmp, video)


def refresh_deliver(video):
    """If a deliver.json next to `video` (render.py --deliver) lists it, update that item's
    `audio` and `size_bytes` so the bundle stays true after the mux. Item paths are relative
    to the project (the folder above renders/). Returns the deliver.json path when updated."""
    video = Path(video).resolve()
    dj = video.parent / "deliver.json"
    if not dj.exists():
        return None
    try:
        data = json.loads(dj.read_text())
    except ValueError:
        log(f"WARN {dj} is not valid JSON; not updated")
        return None
    changed = False
    for item in data.get("items", []):
        rel = item.get("video")
        if not rel or not _same_video(rel, video, dj):
            continue
        streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json",
                                  str(video)], capture_output=True, text=True).stdout
        try:
            item["audio"] = any(s.get("codec_type") == "audio" for s in json.loads(streams).get("streams", []))
        except ValueError:
            item["audio"] = True
        item["size_bytes"] = video.stat().st_size
        changed = True
    if changed:
        dj.write_text(json.dumps(data, indent=2))
        return dj
    return None


def _same_video(rel, video, dj):
    return any((base / rel).resolve() == video for base in (dj.parent.parent, dj.parent))


def find_duration(out, videos=()):
    """--duration default -> (seconds, source file), or (None, None). deliver.json first (the items
    for the muxed videos, else all of them), then *_hits.json; exits if a file's durations disagree."""
    videos = [Path(v).resolve() for v in videos]
    o = Path(out).resolve().parent
    dirs = list(dict.fromkeys([v.parent for v in videos] + [o.parent / "renders", o / "renders",
                                                            Path.cwd().resolve() / "renders"]))

    def one(vals, src):
        vals = sorted({round(float(v), 6) for v in vals if isinstance(v, (int, float)) and v > 0})
        if len(vals) > 1:
            sys.exit(f"{src} has different durations ({', '.join(f'{v:g}' for v in vals)}); pass --duration")
        return vals[0] if vals else None

    for d in dirs:
        dj = d / "deliver.json"
        try:
            items = json.loads(dj.read_text()).get("items", []) if dj.is_file() else []
        except ValueError:
            items = []
        mine = [i for i in items if i.get("video") and any(_same_video(i["video"], v, dj) for v in videos)]
        dur = one([i.get("duration") for i in mine or items], dj)
        if dur:
            return dur, dj
    for d in dirs:
        hits = sorted(d.glob("*_hits.json")) if d.is_dir() else []
        vals = []
        for h in hits:
            try:
                vals.append(json.loads(h.read_text()).get("duration"))
            except ValueError:
                pass
        dur = one(vals, d / "*_hits.json")
        if dur:
            return dur, hits[0] if len(hits) == 1 else d / "*_hits.json"
    return None, None


def video_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                          str(path)], capture_output=True, text=True).stdout
    try:
        return float(json.loads(out)["format"]["duration"])
    except (ValueError, KeyError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float,
                    help="length of the mix in seconds (default: from renders/deliver.json or renders/*_hits.json)")
    ap.add_argument("--out", type=Path, required=True, help="output WAV")
    ap.add_argument("--music", type=Path)
    ap.add_argument("--sfx", type=Path)
    ap.add_argument("--vo", type=Path)
    ap.add_argument("--music-db", type=float, default=0.0)
    ap.add_argument("--sfx-db", type=float, default=0.0)
    ap.add_argument("--vo-db", type=float, default=0.0)
    ap.add_argument("--duck-db", type=float, default=-14.0, help="music gain under the VO (-12..-18 typical)")
    ap.add_argument("--stems", action="store_true", help="also write <out>_music_only.wav and <out>_no_vo.wav")
    ap.add_argument("--mux", type=Path, nargs="+", metavar="VIDEO", help="replace the audio of these videos (and refresh a sibling deliver.json)")
    a = ap.parse_args()

    _audio.need_ffmpeg()
    if not (a.music or a.sfx or a.vo):
        sys.exit("nothing to mix: give at least one of --music, --sfx, --vo")
    if a.duration is None:
        a.duration, src = find_duration(a.out, a.mux or ())
        if a.duration is None:
            sys.exit("no --duration and no renders/deliver.json or renders/*_hits.json to read it from; "
                     "pass --duration (MOTION.duration)")
        log(f"duration {a.duration:g}s from {src}")
    if a.duration <= 0:
        sys.exit("--duration must be > 0")
    sr = _audio.SR
    n = int(round(a.duration * sr))
    music = load_stem(a.music, n, a.music_db) if a.music else None
    sfx = load_stem(a.sfx, n, a.sfx_db) if a.sfx else None
    vo = load_stem(a.vo, n, a.vo_db) if a.vo else None

    ducked = music * duck_envelope(vo.mean(axis=1), sr, a.duck_db)[:, None] if (music is not None and vo is not None) else music
    full = sum(s for s in (ducked, sfx, vo) if s is not None)

    report = {"out": str(a.out), "duration": a.duration, "stems": {}, "muxed": []}
    with tempfile.TemporaryDirectory(prefix="motion-mix-") as tmp:
        sparse = music is None and vo is None
        if sparse:
            lufs, tp, mmax = master_sparse(full, sr, a.out)
            log(f"{a.out.name}: SFX only (sparse): max momentary {mmax:.1f} LUFS, integrated {lufs:.1f}, "
                f"true peak {tp:.1f} dBTP")
            report.update(mode="sparse", lufs=lufs, true_peak=tp, max_momentary=mmax)
        else:
            lufs, tp = master(full, sr, a.out, tmp)
            log(f"{a.out.name}: {lufs:.1f} LUFS, true peak {tp:.1f} dBTP")
            report.update(mode="integrated", lufs=lufs, true_peak=tp)
        if a.stems:
            variants = {"music_only": [music], "no_vo": [music, sfx]}
            for name, parts in variants.items():
                parts = [s for s in parts if s is not None]
                if not parts:
                    log(f"skip {name}: no stems for it")
                    continue
                path = a.out.with_name(f"{a.out.stem}_{name}.wav")
                li, ti = master(sum(parts), sr, path, tmp)
                report["stems"][name] = {"path": str(path), "lufs": li, "true_peak": ti}
                log(f"{path.name}: {li:.1f} LUFS, true peak {ti:.1f} dBTP")

    for v in a.mux or []:
        vd = video_duration(v)
        if vd and abs(vd - a.duration) > 0.05:
            log(f"WARN {v} is {vd:.2f}s but the mix is {a.duration:.2f}s; the shorter one sets the length")
        mux(v, a.out)
        report["muxed"].append(str(v))
        log(f"muxed -> {v}")
        dj = refresh_deliver(v)
        if dj:
            log(f"updated audio/size_bytes in {dj}")

    if report["mode"] == "sparse":
        ok = report["true_peak"] <= LIMIT_TP
        report["status"] = "pass" if ok else "FAIL true peak above -1 dBTP"
    else:
        ok = abs(report["lufs"] - TARGET_I) <= 0.2 and report["true_peak"] <= LIMIT_TP
        report["status"] = "pass" if ok else "FAIL loudness/true peak outside -14 ±0.2 LUFS / -1 dBTP"
    print(json.dumps(report, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
