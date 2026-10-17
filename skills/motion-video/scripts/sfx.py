#!/usr/bin/env python3
"""
sfx.py — synthesized sound effects placed sample-accurately on the composition's visual hits.

Reads hits.json (written by `render.py --hits`), synthesizes every hit from a seeded palette
(noise + oscillators, no samples, no network) and writes one stereo track the length of the
video plus sfx_events.json (onset / peak / end of every sound, used by sync.py).

Palette: whoosh swoosh tick click pop thud blip riser swell impact shimmer type-key
         scrape whoomp crackle creak splash rustle chime zip sizzle
Anchors: riser/swell/zip end on the hit, whoosh/swoosh/whoomp peak on it, everything else starts on it.
Per-hit opts: gain (dB), pan (-1..1), pitch (semitones), len (s), anchor, reverb (0..1),
  loop (true: no fades, and a sound running past the end wraps to the start; for beds like
  crackle / sizzle with len = the loop length, so the seam is click-free).

Project palettes: `--palette P/audio/palette.py` (auto-loaded from next to --out, or from
P/audio/ for P/renders/<slug>_hits.json) is a Python file that adds recipes with
  import sfx; sfx.register(name, fn, anchor, describe, transient=False)
where fn(sr, rng, opts) -> (mono float array, onset_s, peak_s). transient=True sync-checks it.

Samples: `--samples DIR` places audio files instead of synthesising, for every name that has
files named <name>_<n>.<ext> in DIR (supplied by the user or a connector). Each take is
trimmed of silence and normalised, the best take per hit is chosen (crisp attack for sounds
that start on the hit, a rise into the end for end-anchored ones, closest to opts.len), and
anchors and sfx_events.json work as for synthesis. Names without files are still synthesised.

Usage:
  python3 sfx.py renders/comp_hits.json --out audio/sfx.wav            # -> sfx.wav + sfx_events.json
  python3 sfx.py renders/comp_hits.json --out audio/sfx.wav --seed 7   # a different take
  python3 sfx.py renders/comp_hits.json --out audio/sfx.wav --samples audio/samples
  python3 sfx.py --list [--palette audio/palette.py]                   # print the palette

Output: 48 kHz stereo 24-bit WAV. Same hits + same seed (+ same samples) -> bit-identical file.
"""
import argparse, importlib.util, json, math, re, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio  # noqa: E402

PEAK = 10 ** (-6 / 20)  # every sound is normalised to -6 dBFS before its gain
TRANSIENT = {"tick", "click", "pop", "thud", "blip", "impact", "type-key", "splash", "chime"}
ANCHORS = ("start", "peak", "end")


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


def scrape(sr, rng, o):
    L = o.get("len", 0.6)
    t = _t(sr, L)
    n = len(t)
    ph = rng.uniform(0, 2 * np.pi, 2)  # wandering centre: the stroke's speed changes along it
    fc = 2300 + 600 * np.sin(2 * np.pi * 2.3 * t / max(L, 0.2) + ph[0]) + 250 * np.sin(2 * np.pi * 7.1 * t + ph[1])
    hiss = _bandpass_sweep(rng.standard_normal(n), fc, 2.6, sr)
    imp = np.zeros(n)  # grain: random micro-bursts, ~55/s
    k = max(1, rng.poisson(55 * L))
    imp[rng.integers(0, n, k)] = rng.uniform(0.4, 1.0, k)
    grain = np.convolve(imp, np.exp(-_t(sr, 0.02) / 0.006))[:n]
    grain = 0.35 + 0.65 * grain / (grain.max() + 1e-9)
    body = _fft_filter(rng.standard_normal(n), sr, lo=160, hi=650) * 0.35
    wob = 0.85 + 0.15 * np.sin(2 * np.pi * 3.7 * t + ph[0])
    env = _ramp_in(n, sr, 0.015) * _ramp_out(n, sr, min(0.08, L / 4)) * wob
    return (hiss * grain + body * grain ** 0.5) * env, 0.0, 0.015


def whoomp(sr, rng, o):
    L = o.get("len", 0.9)
    t = _t(sr, L)
    breath = _fft_filter(rng.standard_normal(len(t)), sr, lo=70, hi=1300) * (1 - np.exp(-t / 0.03)) * np.exp(-t / 0.26)
    drop = _osc(45 + 45 * np.exp(-t / 0.15), sr) * (1 - np.exp(-t / 0.02)) * np.exp(-t / 0.33) * 0.9
    return (0.8 * breath + drop) * _ramp_out(len(t), sr, 0.05), 0.0, 0.06


def _circ(x, k):
    """Circular convolution of x with kernel k (len(k) <= len(x)): the result is periodic in len(x)."""
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(k, len(x)), len(x))


def _bed_edges(y, sr, o):
    """Beds are periodic over their length; fade the edges unless they are meant to loop."""
    return y if o.get("loop") else y * _ramp_in(len(y), sr, 0.03) * _ramp_out(len(y), sr, 0.08)


def crackle(sr, rng, o):
    L = o.get("len", 2.0)
    t = _t(sr, L)
    n = len(t)
    hiss = _fft_filter(rng.standard_normal(n), sr, lo=300, hi=3000) * 0.12  # FFT filter = circular
    hiss *= 1 + 0.3 * np.sin(2 * np.pi * max(1, round(0.7 * L)) * t / L + rng.uniform(0, 2 * np.pi))
    y = hiss
    for rate, tau, amp in ((14, 0.0012, 1.0), (4, 0.005, 0.6)):  # snaps, then fatter pops
        imp = np.zeros(n)
        k = max(1, rng.poisson(rate * L))
        imp[rng.integers(0, n, k)] = rng.uniform(0.15, 1.0, k) ** 2
        kt = _t(sr, 8 * tau)
        y = y + amp * _circ(imp, rng.standard_normal(len(kt)) * np.exp(-kt / tau))
    return _bed_edges(_fft_filter(y, sr, lo=500, hi=7000), sr, o), 0.0, 0.0


def sizzle(sr, rng, o):
    L = o.get("len", 2.0)
    t = _t(sr, L)
    n = len(t)
    flutter = _fft_filter(rng.standard_normal(n), sr, hi=25)
    flutter = 0.6 + 0.4 * flutter / (np.abs(flutter).max() + 1e-12)
    hiss = _fft_filter(rng.standard_normal(n), sr, lo=4000, hi=11000) * flutter
    imp = np.zeros(n)
    k = max(1, rng.poisson(6 * L))
    imp[rng.integers(0, n, k)] = rng.uniform(0.5, 1.5, k)
    kt = _t(sr, 0.006)
    spit = _fft_filter(_circ(imp, rng.standard_normal(len(kt)) * np.exp(-kt / 0.0008)), sr, lo=3000)
    return _bed_edges(hiss + 0.4 * spit, sr, o), 0.0, 0.0


def creak(sr, rng, o):
    L = o.get("len", 0.8)
    t = _t(sr, L)
    ph = rng.uniform(0, 2 * np.pi, 2)
    f0 = 95 * (1 + 0.3 * np.sin(np.pi * t / L + ph[0]) + 0.08 * np.sin(2 * np.pi * 5.3 * t + ph[1]))
    frac = (np.cumsum(f0) / sr) % 1.0  # stick-slip: one sharp pulse per cycle, jittered
    pulses = np.exp(-frac / 0.06) * (1 + 0.3 * rng.standard_normal(len(t)))
    body = _bandpass_sweep(pulses, np.full(len(t), 900.0), 4.0, sr) + 0.5 * _fft_filter(pulses, sr, lo=1200, hi=3500)
    return body * _rc_env(t, L, 0.3 * L), 0.0, 0.3 * L


def splash(sr, rng, o):
    L = o.get("len", 0.7)
    t = _t(sr, L)
    n = len(t)
    y = _fft_filter(rng.standard_normal(n) * np.exp(-t / 0.08), sr, lo=400, hi=8000) * _ramp_in(n, sr, 0.003)
    for _ in range(12):  # bubbles: short sines whose pitch rises as they decay
        t0, f, d = rng.uniform(0.03, 0.6 * L), rng.uniform(400, 1600), rng.uniform(0.02, 0.05)
        a, b = int(t0 * sr), min(n, int((t0 + d) * sr))
        tb = t[:b - a]
        y[a:b] += 0.25 * np.exp(-t0 / 0.25) * np.sin(2 * np.pi * np.cumsum(f * (1 + 4 * tb)) / sr) * np.exp(-tb / (d / 3))
    return y * _ramp_out(n, sr, 0.03), 0.0, 0.005


def rustle(sr, rng, o):
    L = o.get("len", 0.8)
    t = _t(sr, L)
    n = len(t)
    imp = np.zeros(n)  # slow grain: overlapping soft bursts, ~25/s
    k = max(1, rng.poisson(25 * L))
    imp[rng.integers(0, n, k)] = rng.uniform(0.2, 1.0, k)
    grain = np.convolve(imp, np.hanning(int(0.03 * sr)))[:n]
    grain = 0.2 + grain / (grain.max() + 1e-9)
    y = _fft_filter(rng.standard_normal(n), sr, lo=1500, hi=7000) * grain
    return y * _rc_env(t, L, 0.35 * L), 0.0, 0.35 * L


def chime(sr, rng, o):
    L = o.get("len", 1.6)
    t = _t(sr, L)
    f0 = 1180 * 2 ** (rng.uniform(-0.5, 0.5) / 12)
    y = np.zeros(len(t))
    for r, a in ((1.0, 1.0), (2.756, 0.6), (5.404, 0.35), (8.933, 0.2)):  # free-bar partials
        y += a * np.sin(2 * np.pi * f0 * r * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / (0.9 / r ** 0.7))
    strike = _fft_filter(rng.standard_normal(len(t)) * np.exp(-t / 0.001), sr, lo=3000) * 0.3
    y = (y + strike) * _ramp_in(len(t), sr, 0.001) * _ramp_out(len(t), sr, 0.05)
    return y, 0.0, 0.002


def zip_(sr, rng, o):
    L = o.get("len", 0.18)
    t = _t(sr, L)
    u = t / L
    sweep = _bandpass_sweep(rng.standard_normal(len(t)), 800 * 7.5 ** u, 8.0, sr)
    teeth = 0.6 + 0.4 * np.sign(np.sin(2 * np.pi * np.cumsum(120 + 180 * u) / sr))
    y = sweep * teeth * u ** 1.5 * _ramp_out(len(t), sr, 0.006)
    return y, 0.0, max(0.0, L - 0.006)


PALETTE = {"whoosh": whoosh, "swoosh": swoosh, "tick": tick, "click": click, "pop": pop, "thud": thud,
           "blip": blip, "riser": riser, "swell": swell, "impact": impact, "shimmer": shimmer,
           "type-key": type_key, "scrape": scrape, "whoomp": whoomp, "crackle": crackle, "creak": creak,
           "splash": splash, "rustle": rustle, "chime": chime, "zip": zip_, "sizzle": sizzle}
ANCHOR = {n: ("end" if n in ("riser", "swell", "zip") else "peak" if n in ("whoosh", "swoosh", "whoomp")
              else "start") for n in PALETTE}
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
            "type-key": "two tiny clicks 15 ms apart (one keystroke)",
            "scrape": "gritty band-passed noise drag, len = the stroke (carving, sanding, chalk, dragging)",
            "whoomp": "breathy low bloom + 90->45 Hz drop (ignition, gas flame, soft burst)",
            "crackle": "sparse pops over low hiss, len s, loopable bed (fire, embers)",
            "creak": "slow pitch-wobbled friction tone (door, wood, rope)",
            "splash": "noise burst + bubbly rising blips (water, liquid pour lands)",
            "rustle": "filtered noise with slow grain, len s (leaves, paper, cloth)",
            "chime": "inharmonic bell partials, gentle decay (success, a bell, magic touch)",
            "zip": "fast rising narrow sweep, ends on the hit (zip-in, zipper, quick reveal)",
            "sizzle": "high band noise with flutter, len s, loopable bed (frying, fuse, static)"}
_registered = []


def register(name, fn, anchor="start", describe="", transient=False):
    """Add (or replace) a palette recipe from a project palette file.
    fn(sr, rng, opts) -> (mono float array, onset_s, peak_s), times inside the buffer;
    transient=True puts it under sync.py's ±tol gate."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"register: name must be a non-empty string, got {name!r}")
    if not callable(fn):
        raise ValueError(f"register({name!r}): fn must be callable")
    if anchor not in ANCHORS:
        raise ValueError(f"register({name!r}): anchor must be start, peak or end (got {anchor!r})")
    PALETTE[name], ANCHOR[name] = fn, anchor
    DESCRIBE[name] = describe or (fn.__doc__ or "").strip().split("\n")[0] or "(project palette)"
    (TRANSIENT.add if transient else TRANSIENT.discard)(name)
    _registered.append(name)


def load_palette(path):
    """Import a project palette file (it calls sfx.register). -> names it registered."""
    path = Path(path)
    if not path.is_file():
        sys.exit(f"palette not found: {path}")
    sys.modules.setdefault("sfx", sys.modules[__name__])  # `import sfx` in the file gets this module
    before, start = dict(PALETTE), len(_registered)
    spec = importlib.util.spec_from_file_location(f"_motion_palette_{abs(hash(str(path.resolve())))}", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"palette {path} failed to load: {type(e).__name__}: {e}")
    # register() calls, plus any direct PALETTE edits (older project files did PALETTE.update)
    names = list(dict.fromkeys(_registered[start:] + [n for n in PALETTE if before.get(n) is not PALETTE[n]]))
    over = [n for n in names if n in before]
    log(f"palette {path}: {', '.join(names) or 'nothing registered'}"
        + (f" (replaces {', '.join(over)})" if over else ""))
    return names


# ------------------------------------------------------------------------------ samples
SAMPLE_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aif", ".aiff"}


def _marks(y, sr, head_db=-40.0):
    """(onset, peak) in s: first sample within head_db of the peak, and the loudest 5 ms."""
    a = np.abs(y)
    onset = int(np.argmax(a >= a.max() * 10 ** (head_db / 20)))
    k = max(1, int(0.005 * sr))
    peak = int(np.argmax(np.convolve(y * y, np.ones(k) / k, "same")))
    return onset / sr, max(onset, peak) / sr


def trim(y, sr, head_db=-40.0, tail_db=-50.0):
    """Cut leading / trailing silence (1 ms pre-roll, ramped) -> trimmed array, or None if silent."""
    a = np.abs(y)
    pk = float(a.max(initial=0.0))
    if pk < 1e-6:
        return None
    on = int(np.argmax(a >= pk * 10 ** (head_db / 20)))
    end = int(np.where(a >= pk * 10 ** (tail_db / 20))[0][-1]) + int(0.005 * sr)
    pre = int(0.001 * sr)
    s = max(0, on - pre)
    y = y[s:min(len(y), end)]
    return y * _ramp_in(len(y), sr, (on - s) / sr) * _ramp_out(len(y), sr, 0.005)


def load_samples(d, sr):
    """DIR with <name>_<n>.<ext> files -> {name: [(file name, trimmed mono)]}, takes in n order."""
    d = Path(d)
    if not d.is_dir():
        sys.exit(f"samples folder not found: {d}")
    found = {}
    for p in d.iterdir():
        m = re.fullmatch(r"(.+)_(\d+)", p.stem)
        if p.is_file() and m and p.suffix.lower() in SAMPLE_EXT:
            found.setdefault(m.group(1), []).append((int(m.group(2)), p))
    takes = {}
    for name in sorted(found):
        for _, p in sorted(found[name]):
            y = trim(_audio.load(p, sr, channels=1).astype(np.float64), sr)
            if y is None:
                log(f"WARN {p.name} is silent; skipped")
                continue
            takes.setdefault(name, []).append((p.name, y))
    log(f"samples {d}: " + (", ".join(f"{n} x{len(v)}" for n, v in takes.items()) or "no <name>_<n> audio files"))
    return takes


def pick_take(takes, sr, anchor, want_len=None):
    """Best take for one hit -> (file name, y, onset, peak). Lower cost wins, ties go to the lower n:
    distance to want_len (log ratio), plus a crisp attack for start-anchored sounds or a rise into
    the end for end-anchored ones. A take longer than want_len is cut to it (end-anchored keep their end)."""
    best = None
    for fname, y in takes:
        onset, peak = _marks(y, sr)
        L = len(y) / sr
        cost = abs(math.log(L / want_len)) if want_len else 0.0
        if anchor == "start":
            cost += (peak - onset) / 0.05
        elif anchor == "end":
            cost += 2 * (1 - peak / L)
        if best is None or cost < best[0]:
            best = (cost, fname, y)
    _, fname, y = best
    k = int(round(want_len * sr)) if want_len else len(y)
    if k < len(y) * 0.95:
        y = y[-k:] * _ramp_in(k, sr, 0.02) if anchor == "end" else y[:k] * _ramp_out(k, sr, 0.03)
    return (fname, y) + _marks(y, sr)


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


def synth(name, sr, rng, opts, take=None):
    """One finished mono sound: recipe (or a sample take: (y, onset, peak)) -> pitch -> reverb ->
    -6 dBFS -> gain. Returns (y, onset, peak)."""
    y, onset, peak = take if take is not None else PALETTE[name](sr, rng, opts)
    st = float(opts.get("pitch", 0) or 0)
    if st:
        ratio = 2 ** (st / 12)
        n = max(1, int(round(len(y) / ratio)))
        # a looping bed resamples periodically, so its seam stays continuous
        y = np.interp(np.arange(n) * (len(y) / n if opts.get("loop") else ratio), np.arange(len(y)), y,
                      period=len(y) if opts.get("loop") else None)
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


def render(hits, duration, sr=48000, seed=1, samples=None):
    """-> (stereo float array, events list, silent list). `samples` = load_samples() output."""
    n = int(round(duration * sr))
    out = np.zeros((n, 2))
    events, silent = [], []
    samples = samples or {}
    for i, h in enumerate(hits):
        name = h["sfx"]
        if name is None:
            silent.append({"t": h["t"], "label": h["label"]})
            continue
        if name not in PALETTE and name not in samples:
            sys.exit(f"unknown sfx {name!r} on hit {h['label']!r}; palette: {', '.join(PALETTE)}"
                     + (f"; samples: {', '.join(samples)}" if samples else ""))
        anchor = h["opts"].get("anchor") or ANCHOR.get(name, "start")
        if anchor not in ANCHORS:
            sys.exit(f"hit {h['label']!r}: anchor must be start, peak or end (got {anchor!r})")
        rng = np.random.default_rng([seed, i])
        take, source = None, "synth"
        if name in samples:
            source, *take = pick_take(samples[name], sr, anchor, h["opts"].get("len"))
        y, onset, peak = synth(name, sr, rng, h["opts"], take)
        ref = {"start": onset, "peak": peak, "end": len(y) / sr}[anchor]
        s = int(round((h["t"] - ref) * sr))
        pan = min(1.0, max(-1.0, float(h["opts"].get("pan", 0) or 0)))
        th = (pan + 1) * math.pi / 4
        stereo = y[:, None] * [math.cos(th), math.sin(th)]
        if h["opts"].get("loop") and n:  # wrap around the track, so a loop piece's seam is continuous
            np.add.at(out, np.arange(s, s + len(y)) % n, stereo)
        else:
            a, b = max(0, s), min(n, s + len(y))
            if b > a:
                out[a:b] += stereo[a - s:b - s]
        events.append({"t": h["t"], "label": h["label"], "sfx": name,
                       "onset": round((s + onset * sr) / sr, 6), "peak": round((s + peak * sr) / sr, 6),
                       "end": round((s + len(y)) / sr, 6), "gain": float(h["opts"].get("gain", 0) or 0),
                       "transient": name in TRANSIENT, "source": source})
    return out, events, silent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hits", nargs="?", type=Path, help="hits.json from render.py --hits")
    ap.add_argument("--out", type=Path, help="output WAV (sfx_events.json is written next to it)")
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--palette", type=Path, help="project palette file that calls sfx.register "
                    "(default: palette.py next to --out, or P/audio/palette.py for P/renders/*_hits.json)")
    ap.add_argument("--no-palette", action="store_true", help="don't auto-load a project palette")
    ap.add_argument("--samples", type=Path, metavar="DIR",
                    help="place <name>_<n>.<ext> audio files from DIR instead of synthesising those names")
    ap.add_argument("--list", action="store_true", help="print the palette and exit")
    a = ap.parse_args()

    palette = a.palette
    if palette is None and not a.no_palette and a.out and a.hits:
        cands = [a.out.parent / "palette.py", a.hits.resolve().parent.parent / "audio" / "palette.py"]
        palette = next((c for c in cands if c.is_file()), None)
    if palette is not None:
        load_palette(palette)
    if a.list:
        for n in PALETTE:
            print(f"{n:9s} anchor={ANCHOR[n]:5s} {'transient' if n in TRANSIENT else '         '}  {DESCRIBE[n]}")
        return
    if not a.hits or not a.out:
        ap.error("need HITS.json and --out (or --list)")

    samples = load_samples(a.samples, a.sr) if a.samples else None
    data, hits = load_hits(a.hits)
    duration = data.get("duration")
    if not duration:
        duration = max([h["t"] for h in hits] + [0]) + 2.0
        log(f"hits file has no duration; using {duration:.2f}s")
    out, events, silent = render(hits, float(duration), a.sr, a.seed, samples)
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
                      "sampled": sum(e["source"] != "synth" for e in events),
                      "palette": None if palette is None else str(palette),
                      "peak_dbfs": round(20 * math.log10(max(float(np.abs(out).max()), 1e-12)), 2)}, indent=2))


if __name__ == "__main__":
    main()
