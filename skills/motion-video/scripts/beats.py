#!/usr/bin/env python3
"""
beats.py — beat grid for a composition: from a music track, or a fixed grid with no audio.

With --track it finds BPM, beats, downbeats, per-bar energy and sections, picks the
highest-energy window of --duration seconds that starts on a downbeat, and cuts it to
music.wav (48 kHz stereo, 0.5 s fade-out). All times in beats.json are composition time
(t = 0 is the first video frame), so the window starts on beat 0 and `offset` is ~0.
beats.js holds the same data as `window.BEATS = {...};` for file:// previews.

Analysis uses librosa's beat tracker for the tempo if librosa is installed, otherwise a numpy
fallback (spectral-flux onset envelope -> autocorrelation with a prior around 120 BPM). Both
then refine period and phase on a 1.3 ms onset envelope and pick downbeats by accent strength.
Assumes a steady tempo and 4 beats per bar.

Usage:
  python3 beats.py --track song.mp3 --duration 15 --out audio/        # music.wav + beats.json + beats.js
  python3 beats.py --track song.mp3 --duration 15 --bpm 128           # trust a known BPM
  python3 beats.py --grid --bpm 120 --duration 12 --out audio/        # grid only, no audio

Only use tracks the user supplied and has the rights to. Never download music.
"""
import argparse, json, math, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio  # noqa: E402

BPB = 4          # beats per bar
HOP_HI = 64      # samples per hop of the fine onset envelope (1.33 ms at 48 kHz)


def log(*a):
    print("[beats]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------ envelopes
def flux_envelope(mono, sr, n_fft=2048, hop=512):
    """Spectral-flux onset strength (log magnitude, half-wave rectified), one value per hop."""
    win = np.hanning(n_fft).astype(np.float32)
    x = np.pad(mono.astype(np.float32), (n_fft // 2, n_fft // 2))
    n = 1 + (len(x) - n_fft) // hop
    out = np.zeros(n, np.float32)
    for c in range(0, n, 2048):  # chunked STFT keeps memory flat on long tracks
        lo, hi = max(0, c - 1), min(n, c + 2048)
        idx = (np.arange(lo, hi)[:, None] * hop) + np.arange(n_fft)[None, :]
        mag = np.log1p(100 * np.abs(np.fft.rfft(x[idx] * win, axis=1)))
        out[lo + 1:hi] = np.maximum(np.diff(mag, axis=0), 0).sum(axis=1)
    out -= np.convolve(out, np.ones(16) / 16, "same")
    return np.maximum(out, 0), sr / hop


def fine_envelope(mono, sr, hop=HOP_HI):
    """Rise in log RMS per short hop (1.3 ms): peaks on the first hop of each attack."""
    n = len(mono) // hop
    rms = np.sqrt(np.mean(mono[:n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    lg = np.log(rms + 1e-3 * (rms.max() + 1e-12))
    nov = np.maximum(np.diff(lg, prepend=lg[:1]), 0) * np.sqrt(rms / (rms.max() + 1e-12))
    return nov / (nov.max() + 1e-12), sr / hop


def accent_envelope(mono, sr, hop=HOP_HI):
    """Rise in linear RMS per short hop: how loud each attack is (for octave and downbeat choice)."""
    n = len(mono) // hop
    rms = np.sqrt(np.mean(mono[:n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    rms = np.convolve(rms, np.ones(4) / 4, "same")
    nov = np.maximum(np.diff(rms, prepend=rms[:1]), 0)
    return nov / (nov.max() + 1e-12), sr / hop


def _strength(onset, fr, times, r=6):
    return np.array([onset[max(0, int(round(t * fr)) - r):int(round(t * fr)) + r + 1].max(initial=0) for t in times])


def _maxfilt(x, r):
    if r <= 0:
        return x
    p = np.pad(x, r)
    return np.max(np.lib.stride_tricks.sliding_window_view(p, 2 * r + 1), axis=1)


# ------------------------------------------------------------------------------ analysis
def coarse_bpm(mono, sr, lo=60.0, hi=200.0):
    try:
        import librosa  # optional
        tempo, _ = librosa.beat.beat_track(y=mono.astype(np.float32), sr=sr)
        t = float(np.atleast_1d(tempo)[0])
        if lo <= t <= hi:
            return t
    except Exception:
        pass
    onset, fr = flux_envelope(mono, sr)
    g = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    onset = np.convolve(onset, g / g.sum(), "same")  # widen peaks so fractional lags don't split
    onset = onset - onset.mean()
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    acf = lambda lag: np.interp(lag, np.arange(len(ac)), ac)
    bpm = np.arange(lo, hi + 0.05, 0.1)
    lag = 60 * fr / bpm
    # autocorrelation at the beat lag, times a log-normal prior around 120 BPM
    score = acf(lag) * np.exp(-0.5 * (np.log2(bpm / 120.0) / 1.0) ** 2)
    return float(bpm[int(np.argmax(score))])


def _grid_scores(onset, fr, period, nbeats_max, phases):
    k = np.arange(nbeats_max)
    idx = phases[:, None] + np.round(k * period * fr).astype(int)[None, :]
    valid = idx < len(onset)
    return np.where(valid, onset[np.minimum(idx, len(onset) - 1)], 0).sum(axis=1) / np.maximum(valid.sum(1), 1)


def fit_grid(onset, fr, period0, fixed=False):
    """Best (period, phase) for a steady grid on the fine envelope."""
    def search(periods, e):
        best = (-1.0, period0, 0)
        for p in periods:
            phases = np.arange(int(p * fr))
            s = _grid_scores(e, fr, p, int(len(e) / (p * fr)) + 1, phases)
            j = int(np.argmax(s))
            if s[j] > best[0]:
                best = (float(s[j]), float(p), int(j))
        return best
    if fixed:
        periods = [period0]
    else:
        periods = np.arange(period0 * 0.97, period0 * 1.03, 0.0002)
        _, p1, _ = search(periods, _maxfilt(onset, 8))
        nb = max(1, len(onset) / (p1 * fr))
        periods = np.arange(p1 - 0.0003, p1 + 0.0003, max(1e-6, 0.5 / fr / nb))
    _, p, _ = search(periods, _maxfilt(onset, 2))
    _, p, ph = search([p], onset)  # exact phase on the raw envelope
    return p, ph / fr


def metric_level(mono, sr, period, phase, lo=60.0, hi=200.0, ratio=0.4):
    """Octave check: 2 if the off-beats are strong enough to be beats themselves,
    0.5 if every other beat is weak (the real beat is half as fast), else 1."""
    onset, fr = accent_envelope(mono, sr)
    length = len(mono) / sr

    def strength(start, step):
        return _strength(onset, fr, np.arange(start, length - 0.05, step))
    on = strength(phase, period)
    off = strength(phase + period / 2, period)
    if 60 / period * 2 <= hi and on.mean() > 0 and off.mean() / on.mean() >= ratio:
        return 2
    a, b = on[0::2].mean(), on[1::2].mean()
    if 60 / period / 2 >= lo and max(a, b) > 0 and min(a, b) / max(a, b) < ratio:
        return 0.5
    return 1


def analyze(mono, sr, bpm=None):
    """-> {bpm, period, beats, downbeats, energy} in source-track time (seconds)."""
    onset, fr = fine_envelope(mono, sr)
    p0 = 60.0 / (bpm or coarse_bpm(mono, sr))
    period, phase = fit_grid(onset, fr, p0, fixed=bool(bpm))
    if not bpm:
        level = metric_level(mono, sr, period, phase)
        if level != 1:
            period, phase = fit_grid(onset, fr, period / level)
    length = len(mono) / sr
    beats = phase + period * np.arange(int((length - phase) / period) + 1)
    beats = beats[beats < length]
    # downbeat = the bar position with the strongest average onset
    strength = _strength(*accent_envelope(mono, sr), beats)
    j = int(np.argmax([strength[i::BPB].mean() if len(strength[i::BPB]) else 0 for i in range(BPB)]))
    downbeats = beats[j::BPB]
    energy = bar_energy(mono, sr, downbeats[0] if len(downbeats) else 0.0, period * BPB,
                        max(1, len(downbeats)))
    return {"bpm": 60.0 / period, "period": period, "beats": beats.tolist(),
            "downbeats": downbeats.tolist(), "downbeat_index": j, "energy": energy}


def bar_energy(x, sr, start, bar, nbars):
    """Normalised (0..1) RMS of each bar [start + i*bar, start + (i+1)*bar), clipped to x."""
    out = []
    for i in range(nbars):
        a, b = max(0, int((start + i * bar) * sr)), min(len(x), int((start + (i + 1) * bar) * sr))
        out.append(float(np.sqrt(np.mean(np.square(x[a:b], dtype=np.float64)))) if b > a else 0.0)
    m = max(out) if out and max(out) > 0 else 1.0
    return [round(v / m, 4) for v in out]


def sections_from_energy(energy, bar, first, duration, min_bars=4, jump=0.25):
    """Split bars where energy jumps by > `jump`, merge sections shorter than min_bars."""
    if not energy:
        return [{"start": 0.0, "end": round(duration, 6), "label": "main"}]
    bounds = [0] + [i for i in range(1, len(energy)) if abs(energy[i] - energy[i - 1]) > jump] + [len(energy)]
    segs = [[bounds[i], bounds[i + 1]] for i in range(len(bounds) - 1)]
    merged = []
    for s in segs:
        if merged and (s[1] - s[0] < min_bars or merged[-1][1] - merged[-1][0] < min_bars):
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    means = [float(np.mean(energy[a:b])) for a, b in merged]
    out = []
    for i, (a, b) in enumerate(merged):
        if len(merged) == 1:
            label = "main"
        elif i == 0 and means[0] < max(means):
            label = "intro"
        elif i == len(merged) - 1 and means[i] < max(means):
            label = "outro"
        elif means[i] == max(means):
            label = "drop"
        else:
            label = "build" if i + 1 < len(means) and means[i + 1] > means[i] else "break"
        out.append({"start": round(max(0.0, first + a * bar), 6),
                    "end": round(min(duration, first + b * bar), 6), "label": label})
    out[0]["start"], out[-1]["end"] = 0.0, round(duration, 6)
    return out


def choose_window(mono, sr, downbeats, duration):
    """Earliest downbeat whose window has (within 2 %) the highest mean power. None if none fits."""
    length = len(mono) / sr
    cand = [t for t in downbeats if t + duration <= length + 1e-6]
    if not cand:
        return None
    c = np.concatenate([[0.0], np.cumsum(np.square(mono, dtype=np.float64))])
    n = int(round(duration * sr))
    power = [(c[min(len(mono), int(round(t * sr)) + n)] - c[int(round(t * sr))]) / n for t in cand]
    best = max(power)
    return next(t for t, pw in zip(cand, power) if pw >= best * 0.98)


# ------------------------------------------------------------------------------ output
def build(bpm, period, offset, duration, beats_rel=None, energy=None, sections=None,
          source=None, audio=None, window=None, downbeat_index=0):
    if beats_rel is None:
        beats_rel = [offset + k * period for k in range(int(math.ceil((duration - offset) / period - 1e-9)))]
    beats_rel = [round(t, 6) for t in beats_rel if -1e-9 <= t < duration - 1e-9]
    beats_rel = [abs(t) if t == 0 else t for t in beats_rel]
    bar = period * BPB
    first_bar = offset - math.ceil(offset / bar - 1e-3) * bar
    nbars = int(math.ceil((duration - first_bar) / bar - 1e-9))
    return {"version": 1, "source": source, "audio": audio, "bpm": round(bpm, 3), "period": round(period, 6),
            "offset": round(offset, 6) + 0.0, "beats": beats_rel, "downbeats": beats_rel[downbeat_index::BPB],
            "beats_per_bar": BPB,
            "sections": sections or sections_from_energy([1.0] * nbars, bar, first_bar, duration),
            "energy": energy if energy is not None else [1.0] * nbars,
            "window": window, "duration": round(duration, 6)}


def write(out_dir, data):
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2)
    (out_dir / "beats.json").write_text(text + "\n")
    (out_dir / "beats.js").write_text("window.BEATS = " + text + ";\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", type=Path, help="music file (any format ffmpeg reads)")
    ap.add_argument("--grid", action="store_true", help="fixed grid, no audio (needs --bpm and --duration)")
    ap.add_argument("--duration", type=float, help="composition length in seconds")
    ap.add_argument("--bpm", type=float, help="known BPM (skips tempo detection)")
    ap.add_argument("--out", type=Path, default=Path("."), help="output folder (default: cwd)")
    a = ap.parse_args()

    if a.grid == bool(a.track):
        ap.error("use exactly one of --track or --grid")
    if a.bpm is not None and not (20 <= a.bpm <= 400):
        sys.exit(f"--bpm {a.bpm} is out of range (20..400)")

    if a.grid:
        if not a.bpm or not a.duration:
            sys.exit("--grid needs --bpm and --duration")
        data = build(a.bpm, 60.0 / a.bpm, 0.0, a.duration)
        write(a.out, data)
        log(f"grid {a.bpm:g} BPM, {len(data['beats'])} beats -> {a.out / 'beats.json'}")
        print(json.dumps({k: data[k] for k in ("bpm", "period", "offset", "duration")}))
        return

    if not a.track.exists():
        sys.exit(f"not found: {a.track}")
    stereo = _audio.load(a.track, _audio.SR, channels=2)
    sr = _audio.SR
    mono = stereo.mean(axis=1)
    length = len(mono) / sr
    D = a.duration or length
    if D > length + 1e-6:
        sys.exit(f"track is shorter than --duration: {length:.2f}s < {D:.2f}s")

    log(f"analysing {a.track.name} ({length:.1f}s)")
    res = analyze(mono, sr, a.bpm)
    bpm = a.bpm or res["bpm"]
    period = 60.0 / a.bpm if a.bpm else res["period"]
    start = choose_window(mono, sr, res["downbeats"], D)
    if start is None:
        log("WARN no downbeat leaves room for the full window; starting at 0")
        start = 0.0
    s = int(round(start * sr))
    n = int(round(D * sr))
    start = s / sr
    music = _audio.fit(stereo[s:], n).astype(np.float64)
    fade = min(0.5, D)
    k = int(round(fade * sr))
    music[n - k:] *= np.linspace(1, 0, k)[:, None]
    _audio.write_wav(a.out / "music.wav", music, sr)

    k0 = next((k for k, t in enumerate(res["beats"]) if t >= start - 1e-6), 0)
    beats_rel = [t - start for t in res["beats"][k0:] if t < start + D]
    di = (res["downbeat_index"] - k0) % BPB  # index of the first downbeat inside the window
    offset = beats_rel[0] if beats_rel else 0.0
    bar = period * BPB
    first_bar = offset + di * period - math.ceil((offset + di * period) / bar - 1e-3) * bar
    nbars = int(math.ceil((D - first_bar) / bar - 1e-9))
    energy = bar_energy(music.mean(axis=1), sr, first_bar, bar, nbars)
    data = build(bpm, period, offset, D, beats_rel, energy,
                 sections_from_energy(energy, bar, first_bar, D), a.track.name, "music.wav",
                 {"start": round(start, 6), "duration": round(D, 6)}, di)
    write(a.out, data)
    log(f"{data['bpm']} BPM, window {start:.3f}s +{D:g}s, {len(data['beats'])} beats, "
        f"{len(data['sections'])} sections -> {a.out}")
    print(json.dumps({k: data[k] for k in ("bpm", "period", "offset", "window", "duration")}))


if __name__ == "__main__":
    main()
