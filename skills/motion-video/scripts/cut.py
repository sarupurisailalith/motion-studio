#!/usr/bin/env python3
"""
cut.py — the edit decision list (EDL) for footage-led pieces: suggest cuts from the transcript,
build the matching voice stem, and measure A/V sync after the mix.

edl.json (cut.py writes it; edit it by hand freely, then re-run `voice`):
  {"version": 1, "fps": 30, "clip": "talk",
   "edl": [{"id": "e0", "clip": "talk", "in": 0.40, "out": 3.20, "at": 0.00, "speed": 1, "jump": false}, ...],
   "removed": [{"t0", "t1", "reason": "filler|pause|retake", "words": "..."}],   # what suggest cut
   "duration": 12.4}
  A bare list [{clip, in, out, at?, speed?}] is accepted too. Times in seconds; in/out on the
  clip's own timeline, at on the piece's timeline (missing at = straight after the previous
  event). Every time is rounded to whole frames. speed != 1 is for silent b-roll only: speech
  is never time-stretched, so those events are muted in the voice stem. edl.js mirrors the file
  as window.EDL for file:// previews; K.edl(t) in kit-footage.js reads it.

Subcommands:
  suggest PROJECT   cuts from transcript.json: fillers (um, uh, "you know" ...), pauses longer
                    than --pause (kept at --keep-pause), and retakes (a phrase restarted within
                    a few words). Writes edl.json + edl.js for the user to accept or edit.
  voice PROJECT     the voice stem for mix.py --vo: each event's clip audio placed at its `at`,
                    5-10 ms crossfades centred on every cut (no drift), never stretched.
                    --clean (E12.12): high-pass 80 Hz + gentle FFT denoise on each source, then
                    per-segment loudness matched to the median (reported; ±1 LU is the target).
  sync MEDIA        E12.11(c): cross-correlate each EDL segment of the final mix (a WAV or a
                    rendered MP4) with its source audio; FAIL when any is more than --tol-frames
                    (default 1 frame) off. check.py --edl runs the same measurement.

Usage:
  python3 cut.py suggest motion/promo                      # -> edl.json, edl.js
  python3 cut.py voice motion/promo --clean                # -> audio/voice.wav (+ edl.js refreshed)
  python3 cut.py sync motion/promo/renders/promo_16x9.mp4 --edl motion/promo/edl.json
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio, _speech  # noqa: E402

SR = _audio.SR


def log(*a):
    print("[cut]", *a, file=sys.stderr, flush=True)


def assets_of(project: Path):
    f = project / "assets" / "assets.json"
    if not f.exists():
        sys.exit(f"no {f}: ingest the clip first (ingest.py)")
    return {e["id"]: e for e in json.loads(f.read_text()).get("assets", [])}


def clip_audio_path(project, assets, clip):
    e = assets.get(clip)
    if not e:
        sys.exit(f"EDL clip {clip!r} is not in assets.json")
    if e.get("kind") == "audio":
        return project / e["path"]
    a = e.get("audio")
    if not a or a not in assets:
        return None
    return project / assets[a]["path"]


# ------------------------------------------------------------------------------ the EDL file
def fr(t, fps):
    """Round a time to the nearest whole frame."""
    return round(round(float(t) * fps) / fps, 6)


def normalise(data, fps=None):
    """edl.json (object or bare list) -> object with every event complete and frame-rounded."""
    if isinstance(data, list):
        data = {"version": 1, "edl": data}
    fps = float(fps or data.get("fps") or 30)
    events, cursor = [], 0.0
    for i, ev in enumerate(data.get("edl") or []):
        for k in ("clip", "in", "out"):
            if k not in ev:
                sys.exit(f"EDL event {i} has no {k!r}: {json.dumps(ev)}")
        e = dict(ev)
        e["in"], e["out"] = fr(e["in"], fps), fr(e["out"], fps)
        e["speed"] = float(e.get("speed", 1) or 1)
        if e["out"] <= e["in"]:
            sys.exit(f"EDL event {i}: out ({e['out']}) must be after in ({e['in']})")
        e["at"] = fr(e["at"], fps) if e.get("at") is not None else fr(cursor, fps)
        if events and e["at"] < cursor - 0.5 / fps:
            sys.exit(f"EDL event {i} at {e['at']} s overlaps the previous event (ends {cursor:.3f} s)")
        e["id"] = e.get("id") or f"e{i}"
        prev = events[-1] if events else None
        e["jump"] = bool(prev and prev["clip"] == e["clip"] and abs(prev["out"] - e["in"]) > 0.5 / fps
                         and abs(prev["at"] + (prev["out"] - prev["in"]) / prev["speed"] - e["at"]) < 0.5 / fps)
        events.append(e)
        cursor = round(e["at"] + (e["out"] - e["in"]) / e["speed"], 6)
    data.update(version=1, fps=int(fps) if fps.is_integer() else fps, edl=events,
                duration=round(cursor, 6))
    return data


def write_edl(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.with_suffix(".js").write_text(f"window.EDL = {json.dumps(data)};\n")


def load_edl(path: Path, fps=None):
    if not path.exists():
        sys.exit(f"not found: {path} (run cut.py suggest first, or write it by hand)")
    return normalise(json.loads(path.read_text()), fps)


# ------------------------------------------------------------------------------ suggest
def retakes(words, max_between=4, n_min=2):
    """A phrase restarted: words[i:i+n] repeated at j (j >= i+n, at most max_between words
    between). -> [(i, j)] where the first attempt words[i:j] should go."""
    keys = [_speech.norm(w["w"]) for w in words]
    out, i = [], 0
    while i < len(words):
        hit = None
        for j in range(i + n_min, min(len(words), i + n_min + max_between + 1)):
            n = 0
            while j + n < len(words) and i + n < j and keys[i + n] == keys[j + n] and keys[i + n]:
                n += 1
            if n >= n_min:
                hit = j
                break
        if hit is not None:
            out.append((i, hit))
            i = hit
        else:
            i += 1
    return out


def suggest(tr, clip, fps, pause=0.6, keep_pause=0.25, fillers=True, retake=True, head=0.15, tail=0.25):
    words, dur = tr.get("words") or [], float(tr.get("duration") or 0)
    if not words and not tr.get("phrases"):
        sys.exit("the transcript has no words or phrases: nothing to cut")
    spans = [(w["t0"], w["t1"]) for w in words] or [(p["t0"], p["t1"]) for p in tr["phrases"]]
    start, end = max(0.0, spans[0][0] - head), min(dur or spans[-1][1] + tail, spans[-1][1] + tail)
    removed = []
    idx = {w["id"]: i for i, w in enumerate(words)}

    def gap_mid(i):   # middle of the gap before word i
        return (words[i - 1]["t1"] + words[i]["t0"]) / 2 if i > 0 else max(start, words[i]["t0"] - head)

    def gap_mid_after(i):
        return (words[i]["t1"] + words[i + 1]["t0"]) / 2 if i + 1 < len(words) else min(end, words[i]["t1"] + tail)

    if fillers:
        for f in tr.get("fillers") or []:
            i, j = idx.get(f["id"]), idx.get(f.get("to", f["id"]))
            if i is None or j is None:
                continue
            removed.append({"t0": gap_mid(i), "t1": gap_mid_after(j), "reason": "filler", "words": f["w"]})
    if retake and words:
        for i, j in retakes(words):
            removed.append({"t0": gap_mid(i), "t1": gap_mid(j), "reason": "retake",
                            "words": " ".join(w["w"] for w in words[i:j])})
    for s in tr.get("silences") or []:
        if s["dur"] > pause and s["t0"] > start + 1e-6 and s["t1"] < end - 1e-6:
            removed.append({"t0": s["t0"] + keep_pause / 2, "t1": s["t1"] - keep_pause / 2,
                            "reason": "pause", "words": f"{s['dur']:.2f} s pause"})
    removed.sort(key=lambda r: r["t0"])
    merged = []
    for r in removed:
        r = dict(r, t0=fr(max(start, r["t0"]), fps), t1=fr(min(end, r["t1"]), fps))
        if r["t1"] - r["t0"] < 1 / fps:
            continue
        if merged and r["t0"] <= merged[-1]["t1"] + 1e-6:
            m = merged[-1]
            m["t1"] = max(m["t1"], r["t1"])
            m["reason"] = m["reason"] if r["reason"] in m["reason"] else m["reason"] + "+" + r["reason"]
            m["words"] += " | " + r["words"]
        else:
            merged.append(r)
    events, t = [], fr(start, fps)
    for r in merged + [{"t0": fr(end, fps), "t1": None}]:
        if r["t0"] - t >= 1 / fps:
            events.append({"clip": clip, "in": t, "out": r["t0"]})
        if r["t1"] is not None:
            t = r["t1"]
    data = normalise({"version": 1, "fps": fps, "clip": clip, "edl": events}, fps)
    data["removed"] = merged
    return data


# ------------------------------------------------------------------------------ voice stem
def clean_source(path, tmp):
    """E12.12: high-pass 80 Hz + gentle FFT denoise over the whole source (filter state never
    resets at a cut). Never changes timing."""
    out = Path(tmp) / (Path(path).stem + "_clean.wav")
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af",
                        "highpass=f=80:poles=2,afftdn=nr=10:nf=-45:tn=1", "-ar", str(SR), "-c:a", "pcm_f32le",
                        str(out)], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("voice cleanup failed: " + p.stderr.strip()[-400:])
    # afftdn delays its output by part of an FFT window: measure that against the original and
    # take it back out, so a cleaned cut lands on exactly the same sample as a raw one
    x, c = _audio.load(path, SR, 1).astype(np.float64), _audio.load(out, SR, 1).astype(np.float64)
    m = min(len(x), len(c), 30 * SR)
    w = int(0.1 * SR)
    if m > 2 * w:
        k, strength = _gcc(x[w:m - w], c[:m])
        lag = k - w
        if strength >= 6 and lag:
            c = np.concatenate([c[lag:], np.zeros(lag)]) if lag > 0 else np.concatenate([np.zeros(-lag), c[:lag]])
            _audio.write_wav(out, c)
    return out


def seg_lufs(x, tmp, name):
    """Integrated loudness of a (mono) segment, or None when it is too short to gate (< 0.5 s)."""
    if len(x) < 0.5 * SR:
        return None
    f = Path(tmp) / f"{name}.wav"
    _audio.write_wav(f, x)
    i, _ = _audio.ebur128(f)
    return i if np.isfinite(i) else None


def voice(project, data, xfade_ms=8.0, clean=False, duration=None):
    """-> (stereo float array, report). Each event's source [in - x/2, out + x/2] is placed at
    at - x/2 with sin^2 / cos^2 ramps over x, so every cut sits exactly on its frame."""
    assets = assets_of(project)
    xf = max(0.0, xfade_ms) / 1000.0
    total = float(duration or data["duration"])
    y = np.zeros(int(round(total * SR)) + 1)
    rep = {"events": [], "notes": []}
    cache = {}
    with tempfile.TemporaryDirectory(prefix="motion-cut-") as tmp:
        def source(clip):
            if clip not in cache:
                p = clip_audio_path(project, assets, clip)
                if p is None:
                    cache[clip] = None
                else:
                    cache[clip] = _audio.load(clean_source(p, tmp) if clean else p, SR, 1).astype(np.float64)
            return cache[clip]

        segs = []
        for e in data["edl"]:
            x = source(e["clip"])
            if x is None:
                rep["notes"].append(f"{e['id']}: clip {e['clip']!r} has no audio; silent")
                continue
            if abs(e["speed"] - 1) > 1e-9:
                rep["notes"].append(f"{e['id']}: speed {e['speed']:g} (b-roll) is muted; speech is never stretched")
                continue
            h = xf / 2
            i0, i1 = int(round((e["in"] - h) * SR)), int(round((e["out"] + h) * SR))
            seg = np.zeros(i1 - i0)
            a, b = max(0, i0), min(len(x), i1)
            if b > a:
                seg[a - i0:b - i0] = x[a:b]
            segs.append((e, seg, int(round((e["at"] - h) * SR))))
        gains = {}
        if clean:   # per-segment loudness match (E12.12), measured on the cut segment itself
            core = {e["id"]: seg_lufs(seg[int(xf / 2 * SR):len(seg) - int(xf / 2 * SR)], tmp, e["id"])
                    for e, seg, _ in segs}
            known = [v for v in core.values() if v is not None]
            target = float(np.median(known)) if known else None
            last = 0.0
            for e, _, _ in segs:
                v = core[e["id"]]
                g = float(np.clip(target - v, -12, 12)) if (target is not None and v is not None) else last
                gains[e["id"]], last = g, g
            rep["target_lufs"] = round(target, 2) if target is not None else None
        n = int(round(xf * SR))
        for e, seg, j in segs:
            seg = seg * 10 ** (gains.get(e["id"], 0.0) / 20)
            if n:
                r = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
                seg[:n] *= r
                seg[-n:] *= r[::-1]
            lo = max(0, j)
            hi = min(len(y), j + len(seg))
            if hi > lo:
                y[lo:hi] += seg[lo - j:hi - j]
            rep["events"].append({"id": e["id"], "at": e["at"], "dur": round(e["out"] - e["in"], 6),
                                  "gain_db": round(gains.get(e["id"], 0.0), 2)})
        y = y[:int(round(total * SR))]
        if clean:
            after = [seg_lufs(y[int(round(e["at"] * SR)):int(round((e["at"] + e["out"] - e["in"]) * SR))], tmp,
                              "after_" + e["id"]) for e, _, _ in segs]
            vals = [v for v in after if v is not None]
            for ev, v in zip(rep["events"], after):
                ev["lufs"] = round(v, 2) if v is not None else None
            rep["lufs_spread"] = round(max(vals) - min(vals), 2) if vals else None
    return np.stack([y, y], axis=1), rep


# ------------------------------------------------------------------------------ A/V sync (E12.11 c)
def _gcc(ref, sig):
    """Lag (samples) of ref inside sig by phase-transform cross-correlation, and its peak
    strength relative to the correlation's spread (higher = more certain)."""
    n = 1 << int(np.ceil(np.log2(len(ref) + len(sig))))
    R = np.fft.rfft(sig, n) * np.conj(np.fft.rfft(ref, n))
    cc = np.fft.irfft(R / (np.abs(R) + 1e-9), n)[:len(sig) - len(ref) + 1]
    k = int(np.argmax(cc))
    return k, float(cc[k] / (np.std(cc) + 1e-12))


def avsync(mix_mono, sr, data, project, tol_frames=1.0, search=0.25):
    """For each EDL event with audio: where its source audio sits in the mix vs its `at`.
    -> {"status", "segments": [{id, at, offset_ms, frames, status}]}."""
    assets = assets_of(project)
    fps = float(data["fps"])
    lo_sr = 16000
    mix = _resample(mix_mono, sr, lo_sr)
    out, worst, cache = [], 0.0, {}
    for e in data["edl"]:
        if abs(e["speed"] - 1) > 1e-9:
            continue
        if e["clip"] not in cache:
            p = clip_audio_path(project, assets, e["clip"])
            cache[e["clip"]] = _audio.load(p, lo_sr, 1) if p else None
        src = cache[e["clip"]]
        if src is None:
            continue
        m = 0.02                                   # skip the crossfades at both ends
        ref = src[int((e["in"] + m) * lo_sr):int((e["out"] - m) * lo_sr)]
        if len(ref) < 0.2 * lo_sr or np.sqrt(np.mean(ref.astype(np.float64) ** 2)) < 1e-4:
            out.append({"id": e["id"], "at": e["at"], "status": "skipped (too short or silent)"})
            continue
        a0 = int((e["at"] + m - search) * lo_sr)
        pad = max(0, -a0)
        sig = np.concatenate([np.zeros(pad), mix[max(0, a0):a0 + len(ref) + int(2 * search * lo_sr)]])
        if len(sig) < len(ref):
            sig = np.pad(sig, (0, len(ref) - len(sig)))
        k, strength = _gcc(ref.astype(np.float64), sig.astype(np.float64))
        off = (k - int(search * lo_sr)) / lo_sr
        frames = off * fps
        if strength < 6:
            st = "FAIL voice not found in the mix"
        elif abs(frames) > tol_frames:
            st = f"FAIL {off * 1000:+.1f} ms ({frames:+.2f} frames)"
        else:
            st = "pass"
        worst = max(worst, abs(frames)) if strength >= 6 else worst
        out.append({"id": e["id"], "at": e["at"], "offset_ms": round(off * 1000, 2), "frames": round(frames, 3),
                    "strength": round(strength, 1), "status": st})
    fails = [s for s in out if s["status"].startswith("FAIL")]
    if not out:
        status = "skipped (no EDL segment with audio)"
    elif fails:
        status = f"FAIL {len(fails)} of {len(out)} segments off by more than {tol_frames:g} frame(s): " + \
                 ", ".join(f"{s['id']} {s['status'][5:]}" for s in fails[:6])
    else:
        status = f"pass ({len(out)} segments, worst {worst:.2f} frames)"
    return {"status": status, "segments": out}


def _resample(x, sr, to):
    if sr == to:
        return np.asarray(x, np.float64)
    n = int(round(len(x) * to / sr))
    return np.interp(np.arange(n) * sr / to, np.arange(len(x)), np.asarray(x, np.float64))


# ------------------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest", help="cuts from transcript.json -> edl.json")
    s.add_argument("project", type=Path)
    s.add_argument("--transcript", type=Path, help="default PROJECT/transcript.json")
    s.add_argument("--clip", help="video id (default: the transcript's clip)")
    s.add_argument("--fps", type=float, help="frame grid for cuts (default: the clip's fps)")
    s.add_argument("--pause", type=float, default=_speech.LONG_PAUSE, help="cut pauses longer than this (s)")
    s.add_argument("--keep-pause", type=float, default=0.25, help="silence kept where a pause is cut (s)")
    s.add_argument("--no-fillers", action="store_true")
    s.add_argument("--no-retakes", action="store_true")
    s.add_argument("--out", type=Path, help="default PROJECT/edl.json")
    v = sub.add_parser("voice", help="voice stem from edl.json -> audio/voice.wav")
    v.add_argument("project", type=Path)
    v.add_argument("--edl", type=Path, help="default PROJECT/edl.json")
    v.add_argument("--out", type=Path, help="default PROJECT/audio/voice.wav")
    v.add_argument("--xfade-ms", type=float, default=8.0, help="crossfade at each cut (5-10 ms)")
    v.add_argument("--clean", action="store_true", help="high-pass, gentle denoise, per-segment loudness match")
    v.add_argument("--duration", type=float, help="stem length (default: the EDL's duration)")
    y = sub.add_parser("sync", help="A/V sync of the final mix vs the EDL")
    y.add_argument("media", type=Path, help="mix WAV or rendered MP4")
    y.add_argument("--edl", type=Path, required=True)
    y.add_argument("--project", type=Path, help="default: the EDL's folder")
    y.add_argument("--tol-frames", type=float, default=1.0)
    a = ap.parse_args()
    _audio.need_ffmpeg()

    if a.cmd == "suggest":
        tr_path = a.transcript or a.project / "transcript.json"
        if not tr_path.exists():
            sys.exit(f"not found: {tr_path} (run transcribe.py first)")
        tr = json.loads(tr_path.read_text())
        clip = a.clip or tr.get("clip") or tr.get("audio")
        if not clip:
            sys.exit("which clip? pass --clip <video id>")
        fps = a.fps or float(assets_of(a.project).get(clip, {}).get("fps") or 30)
        data = suggest(tr, clip, fps, a.pause, a.keep_pause, not a.no_fillers, not a.no_retakes)
        out = a.out or a.project / "edl.json"
        write_edl(out, data)
        cut = sum(r["t1"] - r["t0"] for r in data["removed"])
        log(f"{len(data['edl'])} events, {len(data['removed'])} cuts ({cut:.2f} s removed) -> {out}")
        print(json.dumps({"edl": str(out), "events": len(data["edl"]), "duration": data["duration"],
                          "removed": data["removed"]}, indent=2))
    elif a.cmd == "voice":
        path = a.edl or a.project / "edl.json"
        data = load_edl(path)
        write_edl(path, data)                     # frame-rounded, ids and at filled in, edl.js refreshed
        x, rep = voice(a.project, data, a.xfade_ms, a.clean, a.duration)
        out = a.out or a.project / "audio" / "voice.wav"
        _audio.write_wav(out, x)
        for n in rep["notes"]:
            log(n)
        log(f"{len(rep['events'])} segments -> {out}" + (f" (loudness spread {rep['lufs_spread']} LU)"
                                                          if rep.get("lufs_spread") is not None else ""))
        rep.update(out=str(out), duration=round(len(x) / SR, 6))
        if a.clean and rep.get("lufs_spread") is not None:
            rep["status"] = "pass" if rep["lufs_spread"] <= 2.0 else f"WARN loudness spread {rep['lufs_spread']} LU"
        print(json.dumps(rep, indent=2))
    else:
        data = load_edl(a.edl)
        rep = avsync(_audio.load(a.media, SR, 1), SR, data, a.project or a.edl.parent, a.tol_frames)
        print(json.dumps(rep, indent=2))
        sys.exit(1 if rep["status"].startswith("FAIL") else 0)


if __name__ == "__main__":
    main()
