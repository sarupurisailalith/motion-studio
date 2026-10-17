#!/usr/bin/env python3
"""
sync.py — measure picture/sound sync: where each SFX actually starts in the audio vs. its hit.

Decodes the audio (a WAV/mix, or the audio track of a rendered video) and locates every hit
in sfx_events.json within ±100 ms of its expected onset:
  - stem (default when the sfx stem is found: sfx.wav next to the events file, or --ref):
    each sound's onset pattern is cut from the stem and matched in the audio, weighting the
    bands where the SFX is louder than the music; a whitened waveform match then makes it
    sample-exact when both agree. Holds up under music as long as the SFX is audible.
  - onset (fallback, no stem): nearest onset on a 1.3 ms energy envelope. Fine for an SFX-only
    track; under busy music a drum hit can be nearer than the SFX, so keep the stem around.
A transient sound (tick, click, pop, thud, blip, impact, type-key, splash, chime, or one a project
palette registered with transient=True) more than --tol-ms off, or not audible at all, is a FAIL.
Non-transient sounds (whoosh, riser, swell, ...) are reported with status "info" and never fail.
Each event's "transient" flag (written by sfx.py) decides; older events files fall back to the
built-in set.

Usage:
  python3 sync.py audio/mix.wav audio/sfx_events.json
  python3 sync.py renders/comp.mp4 audio/sfx_events.json --png renders/comp_sync.png
  python3 sync.py renders/comp.mp4 audio/sfx_events.json --ref audio/sfx_take2.wav

Prints a JSON report to stdout; exit 1 on FAIL. check.py --sync runs the same measurement.
"""
import argparse, json, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio  # noqa: E402
from sfx import TRANSIENT  # noqa: E402  (one list of gated sounds, shared with sfx.py)
HOP = 64
SEARCH = 0.100   # s either side of the expected onset


def log(*a):
    print("[sync]", *a, file=sys.stderr, flush=True)


def envelope(mono, hop=HOP):
    """Frame energy in dB, one value per hop."""
    n = len(mono) // hop
    e = np.mean(np.asarray(mono[:n * hop], np.float64).reshape(n, hop) ** 2, axis=1)
    return 10 * np.log10(e + 1e-12)


def onsets(mono, sr, hop=HOP, rise_db=6.0):
    """Onset times (s), sample-refined. An onset is a local maximum (±7 ms) of the rise in
    frame energy over the mean of the 10 frames before, at least `rise_db`, on a frame no quieter than
    50 dB under the loudest frame (and above -70 dBFS)."""
    L = envelope(mono, hop)
    if len(L) < 8:
        return []
    floor = max(-70.0, L.max() - 50.0)
    E = 10 ** (L / 10)
    prev = np.mean(np.lib.stride_tricks.sliding_window_view(np.pad(E, (10, 0), mode="edge"), 10), axis=1)[:len(L)]
    rise = L - 10 * np.log10(prev + 1e-12)
    rise[L < floor] = 0
    out = []
    r = 5
    for k in np.where(rise >= rise_db)[0]:
        lo, hi = max(0, k - r), min(len(rise), k + r + 1)
        if rise[k] < rise[lo:hi].max() or (rise[lo:k] == rise[k]).any():
            continue
        out.append(_refine(mono, sr, k, hop))
    return out


def _refine(mono, sr, k, hop):
    """First sample of frame k-1..k+1 clearly above the pre-onset level."""
    a = max(0, (k - 1) * hop)
    pre = mono[max(0, a - 8 * hop):a]
    noise = float(np.sqrt(np.mean(np.square(pre, dtype=np.float64)))) if len(pre) else 0.0
    peak = float(np.abs(mono[k * hop:k * hop + int(0.005 * sr)]).max(initial=0.0))
    thr = max(4 * noise, 0.1 * peak, 1e-6)
    seg = np.abs(mono[a:(k + 2) * hop])
    i = np.argmax(seg >= thr) if (seg >= thr).any() else hop
    return (a + int(i)) / sr


def _cut(x, lo, hi):
    out = np.zeros(hi - lo)
    a, b = max(0, lo), min(len(x), hi)
    if b > a:
        out[a - lo:b - lo] = x[a:b]
    return out


def _stft_pow(x, nwin=256, hop=HOP):
    n = 1 + (len(x) - nwin) // hop
    if n <= 0:
        return np.zeros((1, nwin // 2 + 1))
    idx = np.arange(n)[:, None] * hop + np.arange(nwin)[None, :]
    return np.abs(np.fft.rfft(x[idx] * np.hanning(nwin), axis=1)) ** 2


def _envelope_match(mix, ref, s0, sr):
    """Template match of the sound's onset pattern. Both signals -> per-band log-power rise
    (1.3 ms hops), weighted per band by sfx/(sfx + music) power, then cross-correlated over
    ±SEARCH. Returns (lags in s, score per lag); score 1.0 = the pattern exactly as in the stem."""
    m = int(SEARCH * sr)
    a, b = s0 - int(0.03 * sr), s0 + int(0.06 * sr)
    Ps, Pw = _stft_pow(_cut(ref, a, b)), _stft_pow(_cut(mix, a - m, b + m))
    S, M = Ps.mean(axis=0), np.median(Pw, axis=0)
    w = S / (S + M + 1e-20)
    floor = 1e-4 * max(float(Pw.max()), float(Ps.max()), 1e-20)
    onset = lambda P: np.maximum(np.diff(np.log(P + floor), axis=0, prepend=np.log(P[:1] + floor)), 0) @ w
    Os, Ow = onset(Ps), onset(Pw)
    c = np.correlate(Ow, Os, "valid") / (float(Os @ Os) + 1e-20)
    return (np.arange(len(c)) * HOP - m) / sr, c


def _waveform_match(mix, ref, s0, sr):
    """Sample-exact lag by cross-correlating waveforms, whitened by the local mix spectrum
    (so bands where the music dominates count less). Unreliable for tonal sounds, which is why
    measure() only trusts it when the onset pattern agrees."""
    m = int(SEARCH * sr)
    a, b = s0 - int(0.005 * sr), s0 + int(0.055 * sr)
    seg, win = _cut(ref, a, b), _cut(mix, a - m, b + m)
    if not np.any(seg) or not np.any(win):
        return None
    nfft = 1 << (len(win) + len(seg)).bit_length()
    X, S = np.fft.rfft(win, nfft), np.fft.rfft(seg, nfft)
    P = np.convolve(np.abs(X) ** 2, np.ones(16) / 16, "same")
    c = np.fft.irfft(X * np.conj(S) / (P + 1e-9 * P.max()), nfft)[:len(win) - len(seg) + 1]
    return (int(np.argmax(c)) - m) / sr


def locate(mix, ref, onset, sr, min_score=0.3):
    """Where the stem's sound at `onset` (s) is in the mix -> (time in s or None, score)."""
    s0 = int(round(onset * sr))
    lags, c = _envelope_match(mix, ref, s0, sr)
    i = int(np.argmax(c))
    best, lag = float(c[i]), float(lags[i])
    if 0 < i < len(c) - 1:  # parabolic refinement between hops
        y0, y1, y2 = c[i - 1], c[i], c[i + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            lag += 0.5 * (y0 - y2) / den * HOP / sr
    wl = _waveform_match(mix, ref, s0, sr)
    if wl is not None:
        j = int(round((wl - lags[0]) * sr / HOP))
        near = float(c[max(0, j - 2):j + 3].max(initial=0.0)) if 0 <= j < len(c) else 0.0
        if near >= max(min_score, 0.5 * best):
            lag, best = wl, max(near, best)
    if best < min_score or abs(lag) >= SEARCH - 2 * HOP / sr:  # pinned to the search edge: no real match
        return None, best
    return onset + lag, best


def measure(mono, sr, events, tol_ms=20, ref=None):
    """-> {"hits": [{label, sfx, t, expected, detected, offset_ms, status}], "checked", "status", "method"}.
    With `ref` (the mono sfx stem that sfx.py wrote), each sound is located by locate(), which
    holds up under music. Without it, the nearest onset is used."""
    mono = np.asarray(mono, np.float64)
    found = None if ref is not None else np.array(onsets(mono, sr))
    ref = None if ref is None else np.asarray(ref, np.float64)
    hits, bad = [], []
    for e in events:
        exp = float(e.get("onset", e["t"]))
        if ref is not None:
            det, _ = locate(mono, ref, exp, sr)
        else:
            near = found[np.abs(found - exp) <= SEARCH] if len(found) else found
            det = float(near[np.argmin(np.abs(near - exp))]) if len(near) else None
        off = round((det - exp) * 1000, 2) if det is not None else None
        if not e.get("transient", e.get("sfx") in TRANSIENT):
            status = "info"
        elif det is None:
            status = "FAIL not audible"
        elif abs(off) > tol_ms:
            status = f"FAIL {off:+.1f} ms"
        else:
            status = "pass"
        if status.startswith("FAIL"):
            bad.append(f"{e.get('label')} ({'not audible' if det is None else f'{off:+.1f} ms'})")
        hits.append({"label": e.get("label"), "sfx": e.get("sfx"), "t": e.get("t"), "expected": round(exp, 6),
                     "detected": None if det is None else round(det, 6), "offset_ms": off, "status": status})
    checked = sum(1 for h in hits if h["status"] != "info")
    status = "pass" if not bad else f"FAIL {len(bad)}/{checked} hits off by more than {tol_ms:g} ms: " + ", ".join(bad[:6])
    return {"hits": hits, "checked": checked, "tol_ms": tol_ms, "status": status,
            "method": "stem" if ref is not None else "onset"}


def find_ref(events_path, explicit=None):
    """The sfx stem for cross-correlation: --ref, else sfx.wav next to the events file."""
    if explicit:
        if not Path(explicit).exists():
            sys.exit(f"not found: {explicit}")
        return Path(explicit)
    cand = Path(events_path).with_name("sfx.wav")
    return cand if cand.exists() else None


def load_ref(path, sr):
    return None if path is None else _audio.load(path, sr, channels=1)


def run(media_mono, sr, events_path, tol_ms=20, ref=None):
    """What sync.py and check.py --sync both do: events + optional stem -> report."""
    ref_path = find_ref(events_path, ref)
    rep = measure(media_mono, sr, load_events(events_path), tol_ms, load_ref(ref_path, sr))
    rep["ref"] = None if ref_path is None else str(ref_path)
    return rep


def load_events(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read {path}: {e}")
    return data.get("events", [])


def plot(mono, sr, report, path, width=1600, height=420):
    """Envelope (dB) with expected (green) and detected (red) onsets. Pillow only."""
    from PIL import Image, ImageDraw
    L = envelope(mono)
    dur = len(mono) / sr
    im = Image.new("RGB", (width, height), (18, 18, 22))
    dr = ImageDraw.Draw(im)
    top, bot = 30, height - 30
    y = lambda v: bot - (min(0.0, max(-60.0, v)) + 60) / 60 * (bot - top)
    x = lambda t: int(t / max(dur, 1e-9) * (width - 1))
    cols = np.array_split(L, width) if len(L) >= width else [np.array([v]) for v in L]
    pts = [(int(i * width / len(cols)), y(float(c.max()))) for i, c in enumerate(cols) if len(c)]
    for db in (-60, -40, -20, 0):
        dr.line([(0, y(db)), (width, y(db))], fill=(45, 45, 52))
        dr.text((4, y(db) - 12), f"{db} dB", fill=(110, 110, 120))
    dr.line(pts, fill=(140, 170, 230), width=1)
    for h in report["hits"]:
        bad = h["status"].startswith("FAIL")
        dr.line([(x(h["expected"]), top), (x(h["expected"]), bot)], fill=(80, 200, 120), width=1)
        if h["detected"] is not None:
            dr.line([(x(h["detected"]), top + 14), (x(h["detected"]), bot)], fill=(235, 80, 70) if bad else (230, 200, 90), width=1)
        off = "" if h["offset_ms"] is None else f" {h['offset_ms']:+.1f}ms"
        dr.text((x(h["expected"]) + 3, top - 22 if bad else top - 12), f"{h['label']}{off}",
                fill=(235, 80, 70) if bad else (200, 200, 210))
    for s in range(int(dur) + 1):
        dr.text((x(s) + 2, bot + 8), f"{s}s", fill=(110, 110, 120))
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media", type=Path, help="audio file or rendered video")
    ap.add_argument("events", type=Path, help="sfx_events.json from sfx.py")
    ap.add_argument("--png", type=Path, help="write an envelope + hit plot")
    ap.add_argument("--tol-ms", type=float, default=20.0)
    ap.add_argument("--ref", type=Path, help="the sfx stem (default: sfx.wav next to the events file, if any)")
    a = ap.parse_args()
    if not a.media.exists():
        sys.exit(f"not found: {a.media}")
    mono = _audio.load(a.media, _audio.SR, channels=1)
    rep = run(mono, _audio.SR, a.events, a.tol_ms, a.ref)
    rep = {"media": str(a.media), "events": str(a.events), **rep}
    if a.png:
        plot(mono, _audio.SR, rep, a.png)
        rep["png"] = str(a.png)
    log(rep["status"])
    print(json.dumps(rep, indent=2))
    sys.exit(1 if rep["status"].startswith("FAIL") else 0)


if __name__ == "__main__":
    main()
