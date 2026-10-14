#!/usr/bin/env python3
"""
sfx.py — synthesized sound effects placed sample-accurately on the composition's visual hits.

Reads hits.json (written by `render.py --hits`), synthesizes every hit from a seeded palette
(noise + oscillators, no samples, no network) and writes one stereo track the length of the
video plus sfx_events.json (onset / peak / end of every sound, used by sync.py).

Palette: whoosh swoosh tick click pop thud blip riser swell impact shimmer type-key
Anchors: riser/swell end on the hit, whoosh/swoosh peak on it, everything else starts on it.
Per-hit opts: gain (dB), pan (-1..1), pitch (semitones), len (s), anchor, reverb (0..1).

Usage:
  python3 sfx.py renders/comp_hits.json --out audio/sfx.wav            # -> sfx.wav + sfx_events.json
  python3 sfx.py renders/comp_hits.json --out audio/sfx.wav --seed 7   # a different take
  python3 sfx.py --list                                                # print the palette

Output: 48 kHz stereo 24-bit WAV. Same hits + same seed -> bit-identical file.
"""
import argparse, json, math, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio  # noqa: E402

PEAK = 10 ** (-6 / 20)  # every sound is normalised to -6 dBFS before its gain
TRANSIENT = {"tick", "click", "pop", "thud", "blip", "impact", "type-key"}


def log(*a):
    print("[sfx]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------ DSP helpers
def _t(sr, L):
    return np.arange(int(round(L * sr))) / sr


def _fft_filter(x, sr, lo=None, hi=None):
    """Zero-phase band filter with soft (raised-cosine, 1 octave) edges."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    g = np.ones_like(f)
    if lo:
        r = np.clip(np.log2(np.maximum(f, 1e-9) / (lo / 2)), 0, 1)
        g *= 0.5 - 0.5 * np.cos(np.pi * r)
    if hi:
        r = np.clip(np.log2(np.maximum(f, 1e-9) / hi), 0, 1)
        g *= 0.5 + 0.5 * np.cos(np.pi * r)
    return np.fft.irfft(X * g, n)


def _bandpass_sweep(x, fc, q, sr):
    """Chamberlin state-variable band-pass with a per-sample centre frequency."""
    f = (2 * np.sin(np.pi * np.minimum(fc, sr / 6) / sr)).tolist()
    damp = 1.0 / q
    low = band = 0.0
    out = [0.0] * len(x)
    for i, v in enumerate(x.tolist()):
        high = v - low - damp * band
        band += f[i] * high
        low += f[i] * band
        out[i] = band
    return np.array(out)


def _osc(freq, sr):
    """Sine with a (possibly time-varying) frequency array, starting at phase 0."""
    return np.sin(2 * np.pi * np.cumsum(freq) / sr)


def _ramp_in(n, sr, s):
    k = max(1, int(s * sr))
    e = np.ones(n)
    e[:k] = np.linspace(0, 1, k, endpoint=False)[:n] if k <= n else np.linspace(0, 1, n)
    return e


def _ramp_out(n, sr, s):
    k = min(n, max(1, int(s * sr)))
    e = np.ones(n)
    e[n - k:] = np.linspace(1, 0, k)
    return e


def _rc_env(t, L, peak_at):
    """Raised-cosine envelope: 0 at 0 and L, 1 at peak_at."""
    rise = np.clip(t / peak_at, 0, 1)
    fall = np.clip((L - t) / (L - peak_at), 0, 1)
    return np.where(t < peak_at, np.sin(rise * np.pi / 2) ** 2, np.sin(fall * np.pi / 2) ** 2)


def _burst(sr, rng, L, tau, hp):
    t = _t(sr, L)
    return _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / tau), sr, lo=hp)


# ------------------------------------------------------------------------------ the palette
# Each recipe: fn(sr, rng, opts) -> (mono float array, onset_s, peak_s), times inside the buffer.

def whoosh(sr, rng, o):
    L = o.get("len", 0.6)
    t = _t(sr, L)
    fc = 400 + 2200 * np.sin(np.pi * t / L)
    y = _bandpass_sweep(rng.standard_normal(len(t)), fc, 1.5, sr) * _rc_env(t, L, L / 2)
    return y, 0.0, L / 2


def swoosh(sr, rng, o):
    L = o.get("len", 0.35)
    t = _t(sr, L)
    fc = 3000 * (900 / 3000) ** (t / L)
    y = _bandpass_sweep(rng.standard_normal(len(t)), fc, 2.0, sr) * _rc_env(t, L, 0.4 * L)
    return y, 0.0, 0.4 * L


def tick(sr, rng, o):
    return _burst(sr, rng, o.get("len", 0.03), 0.0015, 3000), 0.0, 0.0


def click(sr, rng, o):
    L = o.get("len", 0.04)
    t = _t(sr, L)
    y = _burst(sr, rng, L, 0.003, 1500) + 0.5 * np.sin(2 * np.pi * 2200 * t) * np.exp(-t / 0.004)
    return y, 0.0, 0.0


def pop(sr, rng, o):
    L = o.get("len", 0.12)
    t = _t(sr, L)
    y = _osc(200 + 500 * np.exp(-t / 0.012), sr) * np.exp(-t / 0.03) * _ramp_in(len(t), sr, 0.0005)
    return y * _ramp_out(len(t), sr, 0.005), 0.0, 0.002


def thud(sr, rng, o):
    L = o.get("len", 0.4)
    t = _t(sr, L)
    body = _osc(40 + 30 * np.exp(-t / 0.05), sr) * np.exp(-t / 0.12)
    knock = _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / 0.004), sr, hi=2000) * 0.3
    y = (body + knock) * _ramp_in(len(t), sr, 0.001) * _ramp_out(len(t), sr, 0.01)
    return y, 0.0, 0.004


def blip(sr, rng, o):
    L = o.get("len", 0.08)
    t = _t(sr, L)
    y = np.sin(2 * np.pi * 880 * t) * _ramp_in(len(t), sr, 0.002) * _ramp_out(len(t), sr, 0.01)
    return y, 0.0, 0.002


def riser(sr, rng, o):
    L = o.get("len", 2.0)
    t = _t(sr, L)
    u = t / L
    noise = _bandpass_sweep(rng.standard_normal(len(t)), 300 * 20 ** u, 2.0, sr)
    noise /= np.abs(noise).max() + 1e-12
    saw = 2 * ((np.cumsum(110 * 4 ** u) / sr) % 1.0) - 1
    y = (noise + 0.35 * saw) * u ** 2.5 * _ramp_out(len(t), sr, 0.008)
    return y, 0.0, max(0.0, L - 0.008)


def swell(sr, rng, o):
    L = o.get("len", 2.0)
    t = _t(sr, L)
    u = t / L
    y = np.zeros(len(t))
    for f in (220.0, 277.18, 329.63, 440.0):
        for cents in (-4, 4):
            y += np.sin(2 * np.pi * f * 2 ** (cents / 1200) * t + rng.uniform(0, 2 * np.pi))
    y *= (u * u * (3 - 2 * u)) ** 2 * _ramp_out(len(t), sr, 0.02)
    return y, 0.0, max(0.0, L - 0.02)


def impact(sr, rng, o):
    L = o.get("len", 1.0)
    t = _t(sr, L)
    boom = _osc(35 + 20 * np.exp(-t / 0.06), sr) * np.exp(-t / 0.25)
    crack = _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / 0.01), sr, lo=1500) * 0.8
    tail = _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / 0.25), sr, hi=4000) * 0.15
    y = (boom + crack + tail) * _ramp_in(len(t), sr, 0.0005) * _ramp_out(len(t), sr, 0.02)
    return y, 0.0, 0.002


def shimmer(sr, rng, o):
    L = o.get("len", 1.2)
    t = _t(sr, L)
    y = np.zeros(len(t))
    for f in rng.uniform(2000, 4000, 6):
        y += np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
    trem = (1 + 0.5 * np.sin(2 * np.pi * 7 * t)) / 1.5
    att = min(0.05, L / 4)
    env = np.minimum(t / att, 1) * (1 - t / L) ** 1.5
    return y * trem * env, 0.0, att


def type_key(sr, rng, o):
    a = _burst(sr, rng, 0.012, 0.0008, 2000)
    k = int(0.015 * sr)
    y = np.zeros(max(int(round(o.get("len", 0.05) * sr)), k + len(a)))
    y[:len(a)] += a
    y[k:k + len(a)] += 0.7 * _burst(sr, rng, 0.012, 0.0008, 2000)
    return y, 0.0, 0.0


PALETTE = {"whoosh": whoosh, "swoosh": swoosh, "tick": tick, "click": click, "pop": pop, "thud": thud,
           "blip": blip, "riser": riser, "swell": swell, "impact": impact, "shimmer": shimmer,
           "type-key": type_key}
ANCHOR = {n: ("end" if n in ("riser", "swell") else "peak" if n in ("whoosh", "swoosh") else "start")
          for n in PALETTE}
DESCRIBE = {"whoosh": "band-passed noise sweep, raised-cosine envelope (scene change)",
            "swoosh": "shorter, brighter falling sweep (fast slide)",
            "tick": "tiny high noise tick (counter, small UI step)",
            "click": "noise click + 2.2 kHz body (button press)",
            "pop": "pitched pop, fast pitch drop (element appears)",
            "thud": "low sine 70->40 Hz, exponential decay (something lands)",
            "blip": "880 Hz sine, 80 ms (notification, toggle)",
            "riser": "noise + rising saw, ramps up into the hit (build-up)",
            "swell": "detuned pad, ramps up into the hit (soft build)",
            "impact": "boom + crack + short tail (the big hit)",
            "shimmer": "high detuned sines with tremolo (sparkle, reveal)",
            "type-key": "two tiny clicks 15 ms apart (one keystroke)"}


# ------------------------------------------------------------------------------ rendering
def _reverb(y, sr, rng, amount):
    t = _t(sr, 1.0)
    ir = _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / 0.3), sr, hi=6000)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-12
    n = len(y) + len(ir) - 1
    nfft = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(y, nfft) * np.fft.rfft(ir, nfft), nfft)[:n]
    wet *= np.abs(y).max() / (np.abs(wet).max() + 1e-12)
    out = wet * amount
    out[:len(y)] += y
    return out


def synth(name, sr, rng, opts):
    """One finished mono sound: recipe -> pitch -> reverb -> -6 dBFS -> gain. Returns (y, onset, peak)."""
    y, onset, peak = PALETTE[name](sr, rng, opts)
    st = float(opts.get("pitch", 0) or 0)
    if st:
        ratio = 2 ** (st / 12)
        n = max(1, int(round(len(y) / ratio)))
        y = np.interp(np.arange(n) * ratio, np.arange(len(y)), y)
        onset, peak = onset / ratio, peak / ratio
    rv = float(opts.get("reverb", 0) or 0)
    if rv > 0:
        y = _reverb(y, sr, rng, min(rv, 1.0))
    y = y / (np.abs(y).max() + 1e-12) * PEAK * 10 ** (float(opts.get("gain", 0) or 0) / 20)
    return y, onset, peak


def load_hits(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read hits file {path}: {e}")
    hits = []
    for h in data.get("hits", []):
        if isinstance(h, list):  # tolerate the raw MOTION.hits form with numeric times
            h = {"t": h[0], "label": h[1], "sfx": h[2] if len(h) > 2 else None,
                 "opts": h[3] if len(h) > 3 else {}}
        if not isinstance(h.get("t"), (int, float)):
            sys.exit(f"hit {h.get('label')!r} has non-numeric time {h.get('t')!r}; "
                     "write hits.json with render.py --hits (it resolves beat times)")
        hits.append({"t": float(h["t"]), "label": h.get("label", ""), "sfx": h.get("sfx"),
                     "opts": h.get("opts") or {}})
    return data, hits


def render(hits, duration, sr=48000, seed=1):
    """-> (stereo float array, events list, silent list)."""
    n = int(round(duration * sr))
    out = np.zeros((n, 2))
    events, silent = [], []
    for i, h in enumerate(hits):
        name = h["sfx"]
        if name is None:
            silent.append({"t": h["t"], "label": h["label"]})
            continue
        if name not in PALETTE:
            sys.exit(f"unknown sfx {name!r} on hit {h['label']!r}; palette: {', '.join(PALETTE)}")
        rng = np.random.default_rng([seed, i])
        y, onset, peak = synth(name, sr, rng, h["opts"])
        anchor = h["opts"].get("anchor") or ANCHOR[name]
        if anchor not in ("start", "peak", "end"):
            sys.exit(f"hit {h['label']!r}: anchor must be start, peak or end (got {anchor!r})")
        ref = {"start": onset, "peak": peak, "end": len(y) / sr}[anchor]
        s = int(round((h["t"] - ref) * sr))
        pan = min(1.0, max(-1.0, float(h["opts"].get("pan", 0) or 0)))
        th = (pan + 1) * math.pi / 4
        a, b = max(0, s), min(n, s + len(y))
        if b > a:
            seg = y[a - s:b - s]
            out[a:b, 0] += seg * math.cos(th)
            out[a:b, 1] += seg * math.sin(th)
        events.append({"t": h["t"], "label": h["label"], "sfx": name,
                       "onset": round((s + onset * sr) / sr, 6), "peak": round((s + peak * sr) / sr, 6),
                       "end": round((s + len(y)) / sr, 6), "gain": float(h["opts"].get("gain", 0) or 0)})
    return out, events, silent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hits", nargs="?", type=Path, help="hits.json from render.py --hits")
    ap.add_argument("--out", type=Path, help="output WAV (sfx_events.json is written next to it)")
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--list", action="store_true", help="print the palette and exit")
    a = ap.parse_args()

    if a.list:
        for n in PALETTE:
            print(f"{n:9s} anchor={ANCHOR[n]:5s} {'transient' if n in TRANSIENT else '         '}  {DESCRIBE[n]}")
        return
    if not a.hits or not a.out:
        ap.error("need HITS.json and --out (or --list)")

    data, hits = load_hits(a.hits)
    duration = data.get("duration")
    if not duration:
        duration = max([h["t"] for h in hits] + [0]) + 2.0
        log(f"hits file has no duration; using {duration:.2f}s")
    out, events, silent = render(hits, float(duration), a.sr, a.seed)
    peak = float(np.abs(out).max())
    if peak > 0.999:
        log(f"WARN overlapping sounds peak at {20 * math.log10(peak):+.1f} dBFS; scaling the track down")
        out *= 0.999 / peak
    _audio.write_wav(a.out, out, a.sr)
    ev_path = a.out.with_name("sfx_events.json")
    ev_path.write_text(json.dumps({"version": 1, "sr": a.sr, "events": events}, indent=2))
    log(f"{len(events)} sounds, {len(silent)} silent -> {a.out}")
    print(json.dumps({"out": str(a.out), "events": str(ev_path), "duration": float(duration),
                      "sounds": len(events), "silent": silent,
                      "peak_dbfs": round(20 * math.log10(max(float(np.abs(out).max()), 1e-12)), 2)}, indent=2))


if __name__ == "__main__":
    main()
