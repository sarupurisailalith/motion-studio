"""Synthetic, speech-like test audio (no real voices): each "word" is a burst of a buzzy
harmonic tone with a moving formant, 8 ms attack and 25 ms release, separated by short dips
inside a phrase and longer pauses between phrases. The true word marks come back with it."""
import numpy as np

SR = 48000


def speech(phrases, seed=1, lead=0.4, word_gap=(0.07, 0.12), phrase_gap=(0.5, 0.9), tail=0.5,
           floor_db=-62.0, level=0.3):
    """phrases = [["Hello", "there"], ...] (or [[(word, extra_pause_after), ...]]).
    -> (mono float32, marks=[(word, t0, t1)], duration)."""
    rng = np.random.default_rng(seed)
    t, parts, marks = lead, [], []
    for pi, words in enumerate(phrases):
        for wi, w in enumerate(words):
            pause = 0.0
            if isinstance(w, tuple):
                w, pause = w
            d = 0.12 + 0.045 * len(w) + rng.uniform(-0.02, 0.03)
            marks.append((w, round(t, 4), round(t + d, 4)))
            parts.append((t, d, rng.uniform(110, 180), rng.uniform(0.6, 1.0)))
            t += d + (rng.uniform(*word_gap) if wi < len(words) - 1 else 0) + pause
        if pi < len(phrases) - 1:
            t += rng.uniform(*phrase_gap)
    dur = t + tail
    n = int(round(dur * SR))
    x = rng.normal(0, 10 ** (floor_db / 20), n)
    for t0, d, f0, amp in parts:
        i0, m = int(round(t0 * SR)), int(round(d * SR))
        tt = np.arange(m) / SR
        tone = sum(np.sin(2 * np.pi * f0 * k * tt) / k for k in range(1, 12))
        formant = 0.6 + 0.4 * np.sin(2 * np.pi * (3 + 2 * amp) * tt)
        env = np.minimum(1, np.minimum(tt / 0.008, (d - tt) / 0.025)).clip(0, 1)
        x[i0:i0 + m] += level * amp * tone / 3 * formant * env
    return x.astype(np.float32), marks, dur


def write(path, x, sr=SR):
    import wave
    q = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(q.tobytes())
    return path
