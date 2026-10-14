"""
_audio.py — shared audio helpers for beats.py, sfx.py, mix.py, sync.py (private module).

Sample format choice:
  - Everything inside the scripts is float32 numpy, shape (n,) mono or (n, 2) stereo, range ±1.
  - Decoding (any format: wav/mp3/m4a/mp4/...) goes through ffmpeg to raw f32le, so the
    scripts never care about the source codec or bit depth.
  - Writing uses the stdlib `wave` module at 24-bit PCM: 144 dB of dynamic range is plenty
    of headroom for stems and masters, every tool reads it, and the bytes are deterministic
    (same samples -> same file), which the seeded SFX renderer relies on.
"""
import json, re, shutil, subprocess, sys, wave
from pathlib import Path

import numpy as np

SR = 48000


def need_ffmpeg():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        sys.exit("ffmpeg/ffprobe not found on PATH")


def load(path, sr=SR, channels=1):
    """Decode any audio (or the audio of a video) to float32 at `sr`.
    channels=1 -> shape (n,); channels=2 -> shape (n, 2). Exits if there is no audio."""
    need_ffmpeg()
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", str(channels),
                        "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if p.returncode != 0:
        sys.exit(f"could not decode audio from {path}: {p.stderr.decode(errors='replace').strip()[-300:]}")
    x = np.frombuffer(p.stdout, np.float32).copy()
    if x.size == 0:
        sys.exit(f"no audio in {path}")
    return x if channels == 1 else x.reshape(-1, channels)


def write_wav(path, x, sr=SR):
    """Write float audio (mono or (n, ch)) as 24-bit PCM WAV. Values are clipped to ±1."""
    x = np.asarray(x, np.float64)
    if x.ndim == 1:
        x = x[:, None]
    q = np.round(np.clip(x, -1.0, 1.0) * 8388607.0).astype("<i4")
    b = q.reshape(-1).view(np.uint8).reshape(-1, 4)[:, :3]  # little-endian low 3 bytes
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(3)
        w.setframerate(sr)
        w.writeframes(b.tobytes())


def fit(x, n):
    """Pad with silence or trim to exactly n samples (works for mono and stereo)."""
    if len(x) >= n:
        return x[:n]
    pad = [(0, n - len(x))] + [(0, 0)] * (x.ndim - 1)
    return np.pad(x, pad)


def db(x, floor=-200.0):
    return np.maximum(20 * np.log10(np.maximum(np.abs(x), 1e-12)), floor)


def ebur128(path):
    """Measure integrated loudness (LUFS) and true peak (dBTP) with ffmpeg's ebur128 filter."""
    need_ffmpeg()
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                          "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    f = lambda m: float("-inf") if (not m or m.group(1) == "-inf") else float(m.group(1))
    return f(i), f(tp)


def max_momentary(path):
    """Loudest 400 ms window (EBU momentary loudness, LUFS) of a file, via ffmpeg ebur128."""
    need_ffmpeg()
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                          "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    vals = [float(v) for v in re.findall(r"\bM:\s*(-?[\d.]+)", err[:err.rfind("Summary:")])]
    return max(vals) if vals else float("-inf")


def loudnorm_measure(path, I=-14.0, TP=-1.5, LRA=11.0):
    """First pass of ffmpeg loudnorm; returns its measured JSON."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    if not m:
        sys.exit("loudnorm measurement failed:\n" + err[-500:])
    return json.loads(m.group(0))
