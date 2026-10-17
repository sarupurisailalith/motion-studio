"""Tests for the audio stack (W1-A): sfx.py, beats.py, mix.py, sync.py, check.py --sync.

All test audio is generated in code (numpy) and written to helpers.tmpdir().
"""
import json, re, subprocess, sys, unittest, wave
from pathlib import Path

import numpy as np

import helpers

sys.path.insert(0, str(helpers.SCRIPTS))

SR = 48000


def read_wav(path):
    """-> (float array (n, ch), sr). Handles 16/24/32-bit PCM."""
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v / float(1 << 23)
    elif sw == 2:
        x = np.frombuffer(raw, "<i2") / 32768.0
    else:
        x = np.frombuffer(raw, "<i4") / float(1 << 31)
    return x.reshape(-1, ch), sr


def write_wav16(path, x, sr=SR):
    x = np.asarray(x)
    if x.ndim == 1:
        x = x[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def write_hits(path, hits, duration):
    Path(path).write_text(json.dumps({"version": 1, "source": "t.html", "fps": 60,
                                      "duration": duration, "hits": hits}))
    return path


def hit(t, label, sfx, **opts):
    return {"t": t, "label": label, "sfx": sfx, "opts": opts}


def ebur128(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    s = err[err.rfind("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    tp = float(re.search(r"True peak:\s+Peak:\s+(-?[\d.]+) dBFS", s).group(1))
    return i, tp


def ffprobe(path):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                      str(path)], capture_output=True, text=True, check=True).stdout)


def make_video(path, dur=2.0, fps=30):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=320x240:rate={fps}:duration={dur}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12)


# ---------------------------------------------------------------------------------------- A1
@helpers.needs_ffmpeg
class SFX(unittest.TestCase):
    NAMES = ["whoosh", "swoosh", "tick", "click", "pop", "thud", "blip", "riser", "swell",
             "impact", "shimmer", "type-key", "scrape", "whoomp", "crackle", "creak", "splash",
             "rustle", "chime", "zip", "sizzle"]

    def render(self, hits, duration, *extra, d=None):
        d = d or helpers.tmpdir()
        h = write_hits(d / "hits.json", hits, duration)
        r = helpers.run_script("sfx.py", h, "--out", d / "sfx.wav", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        x, sr = read_wav(d / "sfx.wav")
        ev = json.loads((d / "sfx_events.json").read_text())
        return x, sr, ev, json.loads(r.stdout), d

    def test_list(self):
        r = helpers.run_script("sfx.py", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        for n in self.NAMES:
            self.assertIn(n, r.stdout)

    def test_palette_api(self):
        import sfx
        self.assertEqual(sorted(sfx.PALETTE), sorted(self.NAMES))
        rng = np.random.default_rng(1)
        for name, fn in sfx.PALETTE.items():
            y, onset, peak = fn(SR, rng, {})
            self.assertEqual(y.ndim, 1, name)
            self.assertGreater(len(y), 0, name)
            self.assertTrue(0 <= onset <= peak <= len(y) / SR, name)

    def test_thud_timing(self):
        x, sr, ev, _, _ = self.render([hit(1.0, "a", "thud")], 3)
        self.assertEqual(sr, SR)
        self.assertLessEqual(abs(len(x) - 3 * SR), 1)
        above = np.where(np.abs(x).max(axis=1) > 10 ** (-40 / 20))[0]
        self.assertLessEqual(abs(above[0] / SR - 1.0), 0.001)
        self.assertEqual(ev["sr"], SR)
        e = ev["events"][0]
        self.assertEqual((e["label"], e["sfx"]), ("a", "thud"))
        self.assertAlmostEqual(e["onset"], 1.0, delta=0.001)

    def test_riser_ends_on_hit(self):
        x, _, _, _, _ = self.render([hit(2.0, "r", "riser")], 3)
        m = np.abs(x).max(axis=1)
        env = np.array([m[i:i + 480].max() for i in range(0, len(m) - 480, 480)])  # 10 ms blocks
        t_max = (np.argmax(env) * 480 + 240) / SR
        self.assertTrue(2.0 - 0.030 <= t_max <= 2.0, t_max)
        self.assertLess(m[int(2.05 * SR):].max(), 10 ** (-60 / 20))

    def test_whoosh_peak(self):
        _, _, ev, _, _ = self.render([hit(1.5, "w", "whoosh")], 3)
        self.assertAlmostEqual(ev["events"][0]["peak"], 1.5, delta=0.005)

    def test_silent_hit(self):
        x, _, ev, out, _ = self.render([hit(1.0, "card-in", None)], 2)
        self.assertEqual(np.abs(x).max(), 0)
        self.assertEqual(ev["events"], [])
        self.assertIn("card-in", json.dumps(out["silent"]))

    def test_determinism(self):
        hits = [hit(0.5, "a", "whoosh"), hit(1.0, "b", "impact", reverb=0.5), hit(1.6, "c", "type-key")]
        d1, d2, d3 = helpers.tmpdir(), helpers.tmpdir(), helpers.tmpdir()
        self.render(hits, 3, "--seed", "1", d=d1)
        self.render(hits, 3, "--seed", "1", d=d2)
        self.render(hits, 3, "--seed", "2", d=d3)
        a, b, c = [(d / "sfx.wav").read_bytes() for d in (d1, d2, d3)]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_gain_and_pan(self):
        x0, *_ = self.render([hit(0.5, "a", "pop")], 1.5)
        x6, *_ = self.render([hit(0.5, "a", "pop", gain=-6)], 1.5)
        diff = 20 * np.log10(np.abs(x0).max() / np.abs(x6).max())
        self.assertAlmostEqual(diff, 6.0, delta=0.5)
        xl, *_ = self.render([hit(0.5, "a", "pop", pan=-1)], 1.5)
        self.assertGreater(np.abs(xl[:, 0]).max(), 0.1)
        self.assertLess(np.abs(xl[:, 1]).max(), 1e-4)

    def test_pitch_and_len(self):
        _, _, ev, _, _ = self.render([hit(0.2, "a", "shimmer", len=0.5), hit(1.0, "b", "pop", pitch=12)], 2)
        a, b = ev["events"]
        self.assertAlmostEqual(a["end"] - a["onset"], 0.5, delta=0.02)
        self.assertLess(b["end"] - b["onset"], 0.1)


# ---------------------------------------------------------------------------------------- A2
def click_track(path, bpm=100.0, start=0.30, length=30.0, sr=SR, seed=0):
    """Clicks every beat from `start`, every 4th accented +12 dB, over quiet pink noise."""
    rng = np.random.default_rng(seed)
    n = int(length * sr)
    white = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    pink = np.fft.irfft(white / np.sqrt(np.maximum(f, 20)), n)
    x = pink / np.abs(pink).max() * 10 ** (-40 / 20)
    k = np.arange(int(0.03 * sr))
    click = np.sin(2 * np.pi * 1500 * k / sr) * np.exp(-k / (0.004 * sr))
    period, i = 60.0 / bpm, 0
    while start + i * period < length - 0.05:
        s = int(round((start + i * period) * sr))
        amp = 0.8 if i % 4 == 0 else 0.8 * 10 ** (-12 / 20)
        x[s:s + len(click)] += amp * click[:n - s]
        i += 1
    write_wav16(path, x, sr)
    return path


def drum_loop(bpm, start, length=30.0, hats=True, seed=0, sr=SR):
    """Kick on 1 and 3, snare on 2 and 4, optional 8th-note hats, over faint noise."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(length * sr)) * 0.003
    t = np.arange(int(0.25 * sr)) / sr
    kick = np.sin(2 * np.pi * np.cumsum(50 + 100 * np.exp(-t / 0.03)) / sr) * np.exp(-t / 0.15)
    snare = rng.standard_normal(len(t)) * np.exp(-t / 0.06) * 0.5
    hat = np.diff(rng.standard_normal(len(t) + 1)) * np.exp(-t / 0.01) * 0.15
    p, i = 60.0 / bpm, 0
    while start + i * p / 2 < length - 0.3:
        s = int((start + i * p / 2) * sr)
        if hats:
            x[s:s + len(t)] += hat
        if i % 2 == 0:
            b = i // 2
            x[s:s + len(t)] += (kick * (1.0 if b % 4 == 0 else 0.7)) if b % 2 == 0 else snare
        i += 1
    return x / np.abs(x).max() * 0.8


@helpers.needs_ffmpeg
class Beats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = helpers.tmpdir()
        cls.track = click_track(cls.d / "t.wav")

    def run_beats(self, *args):
        out = helpers.tmpdir()
        r = helpers.run_script("beats.py", *args, "--out", out)
        return r, out

    def load(self, out):
        b = json.loads((out / "beats.json").read_text())
        js = (out / "beats.js").read_text().strip()
        self.assertTrue(js.startswith("window.BEATS = ") and js.endswith(";"))
        self.assertEqual(json.loads(js[len("window.BEATS = "):-1]), b)
        return b

    def test_grid(self):
        r, out = self.run_beats("--grid", "--bpm", "120", "--duration", "4")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.load(out)
        self.assertEqual(b["beats"], [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        self.assertEqual(b["downbeats"], [0, 2.0])
        self.assertEqual(b["period"], 0.5)
        self.assertEqual(b["bpm"], 120)
        self.assertIsNone(b["audio"])
        self.assertIsNone(b["source"])
        self.assertIsNone(b["window"])
        self.assertEqual(b["version"], 1)
        self.assertEqual(b["beats_per_bar"], 4)
        self.assertFalse((out / "music.wav").exists())

    def check_window(self, b, out):
        start = b["window"]["start"]
        k = round((start - 0.30) / 2.4)
        self.assertLessEqual(abs(start - (0.30 + 2.4 * k)), 0.010, start)
        self.assertLessEqual(abs(b["offset"]), 0.010)
        x, sr = read_wav(out / "music.wav")
        self.assertEqual(sr, SR)
        self.assertEqual(x.shape[1], 2)
        self.assertLessEqual(abs(len(x) / sr - 12.0), 0.001)
        tail = x[-int(0.05 * sr):]
        before = x[-int(1.0 * sr):-int(0.5 * sr)]
        self.assertGreaterEqual(rms_db(before) - rms_db(tail), 20)
        self.assertEqual(b["audio"], "music.wav")
        self.assertEqual(b["duration"], 12.0)
        self.assertEqual(b["window"]["duration"], 12.0)
        # sections cover [0, duration] without gaps; one energy value per bar
        secs = b["sections"]
        self.assertEqual(secs[0]["start"], 0)
        self.assertEqual(secs[-1]["end"], 12.0)
        for p, q in zip(secs, secs[1:]):
            self.assertEqual(p["end"], q["start"])
        bars = int(np.ceil(12.0 / (b["period"] * b["beats_per_bar"]) - 1e-9))
        self.assertEqual(len(b["energy"]), bars)
        self.assertTrue(all(0 <= e <= 1 for e in b["energy"]))
        self.assertTrue(all(0 <= t < 12.0 for t in b["beats"]))
        self.assertTrue(set(b["downbeats"]) <= set(b["beats"]))

    def test_track(self):
        r, out = self.run_beats("--track", self.track, "--duration", "12")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.load(out)
        self.assertLessEqual(abs(b["bpm"] - 100), 1, b["bpm"])
        self.assertEqual(b["source"], "t.wav")
        self.check_window(b, out)

    def test_bpm_override(self):
        r, out = self.run_beats("--track", self.track, "--duration", "12", "--bpm", "100")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = self.load(out)
        self.assertEqual(b["bpm"], 100)
        self.assertEqual(b["period"], 0.6)
        self.check_window(b, out)

    def test_track_too_short(self):
        r, out = self.run_beats("--track", self.track, "--duration", "40")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("shorter", r.stderr)

    def test_bpm_five_tracks(self):
        import beats
        for bpm, start, hats in [(128, 0.1, True), (90, 1.0, True), (140, 0.42, False), (75, 0.05, True),
                                 (174, 0.2, False)]:
            res = beats.analyze(drum_loop(bpm, start, hats=hats, seed=bpm), SR)
            self.assertLessEqual(abs(res["bpm"] - bpm), 1, (bpm, res["bpm"]))
            bar = 240.0 / bpm
            err = (res["downbeats"][0] - start + bar / 2) % bar - bar / 2
            self.assertLessEqual(abs(err), 0.010, (bpm, err))

    def test_analyze_api(self):
        import beats, _audio
        mono = _audio.load(self.track)
        res = beats.analyze(mono, SR)
        self.assertLessEqual(abs(res["bpm"] - 100), 1)
        for key in ("beats", "downbeats", "energy"):
            self.assertIn(key, res)


# ---------------------------------------------------------------------------------------- A3
def sine(freq, dur, dbfs, sr=SR):
    t = np.arange(int(dur * sr)) / sr
    return np.sin(2 * np.pi * freq * t) * 10 ** (dbfs / 20)


def clicks(times, dur, sr=SR, amp=0.5):
    x = np.zeros(int(dur * sr))
    k = np.arange(int(0.01 * sr))
    c = np.sin(2 * np.pi * 2000 * k / sr) * np.exp(-k / (0.002 * sr)) * amp
    for t in times:
        s = int(t * sr)
        x[s:s + len(c)] += c[:len(x) - s]
    return x


@helpers.needs_ffmpeg
class Mix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = helpers.tmpdir()
        write_wav16(cls.d / "music.wav", np.stack([sine(440, 4, -30)] * 2, 1))
        write_wav16(cls.d / "sfx.wav", clicks([0.5, 1.5, 2.5, 3.5], 4))
        vo = np.zeros(int(4 * SR))
        vo[SR:2 * SR] = sine(220, 1, -12)
        write_wav16(cls.d / "vo.wav", vo)

    def mix(self, *args):
        out = helpers.tmpdir()
        r = helpers.run_script("mix.py", "--out", out / "mix.wav", *args)
        return r, out

    def assert_loudness(self, path):
        i, tp = ebur128(path)
        self.assertAlmostEqual(i, -14.0, delta=0.2, msg=str(path))
        self.assertLessEqual(tp, -1.0, str(path))

    def test_master_loudness(self):
        r, out = self.mix("--duration", 4, "--music", self.d / "music.wav", "--sfx", self.d / "sfx.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_loudness(out / "mix.wav")
        x, sr = read_wav(out / "mix.wav")
        self.assertEqual(sr, SR)
        self.assertEqual(x.shape[1], 2)

    def test_duck_envelope(self):
        import mix
        vo = np.zeros(4 * SR)
        vo[SR:2 * SR] = sine(220, 1, -12)
        g = 20 * np.log10(np.maximum(mix.duck_envelope(vo, SR), 1e-9))
        self.assertEqual(len(g), len(vo))
        t = np.arange(len(vo)) / SR
        self.assertLessEqual(g[(t >= 1.1) & (t <= 1.9)].max(), -12)
        outside = (t < 0.6) | (t > 2.5)
        self.assertLessEqual(np.abs(g[outside]).max(), 0.5)

    def test_stems(self):
        r, out = self.mix("--duration", 4, "--music", self.d / "music.wav", "--sfx", self.d / "sfx.wav",
                          "--vo", self.d / "vo.wav", "--stems")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("mix.wav", "mix_music_only.wav", "mix_no_vo.wav"):
            self.assert_loudness(out / name)

    def test_mux(self):
        v = make_video(helpers.tmpdir() / "v.mp4", 2.0)
        md5 = lambda: subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-map", "0:v", "-f", "md5", "-"],
                                     capture_output=True, text=True, check=True).stdout
        before = md5()
        r, out = self.mix("--duration", 2, "--music", self.d / "music.wav", "--mux", v)
        self.assertEqual(r.returncode, 0, r.stderr)
        info = ffprobe(v)
        a = [s for s in info["streams"] if s["codec_type"] == "audio"]
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["codec_name"], "aac")
        self.assertEqual(a[0]["sample_rate"], "48000")
        self.assertEqual(md5(), before)
        self.assertAlmostEqual(float(info["format"]["duration"]), 2.0, delta=1 / 30 + 1e-3)
        self.assertEqual(sorted(p.name for p in v.parent.iterdir()), ["v.mp4"])  # no temp files left

    def test_mux_refreshes_deliver_json(self):
        # render.py --deliver wrote renders/deliver.json before the mux: audio false, old size
        proj = helpers.tmpdir()
        (proj / "renders").mkdir()
        v = make_video(proj / "renders" / "comp_9x16.mp4", 2.0)
        make_video(proj / "renders" / "comp_1x1.mp4", 2.0)
        old = {"format": "1x1", "video": "renders/comp_1x1.mp4", "poster": "renders/comp_1x1_poster.png",
               "sheet": "renders/comp_1x1_sheet.png", "duration": 2.0, "fps": 30, "width": 320,
               "height": 240, "pix_fmt": "yuv420p", "audio": False, "size_bytes": 1}
        deliver = {"version": 1, "source": "comp.html", "items": [
            dict(old, format="9x16", video="renders/comp_9x16.mp4", poster="renders/comp_9x16_poster.png",
                 sheet="renders/comp_9x16_sheet.png"), old]}
        (proj / "renders" / "deliver.json").write_text(json.dumps(deliver))
        r, _ = self.mix("--duration", 2, "--music", self.d / "music.wav", "--mux", v)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads((proj / "renders" / "deliver.json").read_text())
        nine, one = got["items"]
        self.assertIs(nine["audio"], True)
        self.assertEqual(nine["size_bytes"], v.stat().st_size)
        self.assertEqual(nine["poster"], "renders/comp_9x16_poster.png")  # everything else kept
        self.assertEqual(one, old)                                       # not muxed: untouched
        self.assertEqual(got["version"], 1)

    def test_mux_without_deliver_json(self):
        v = make_video(helpers.tmpdir() / "v.mp4", 2.0)
        r, _ = self.mix("--duration", 2, "--music", self.d / "music.wav", "--mux", v)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((v.parent / "deliver.json").exists())

    def test_no_stems(self):
        r, _ = self.mix("--duration", 2)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--music", r.stderr)

    def test_duration_pad_and_trim(self):
        r, out = self.mix("--duration", 6, "--music", self.d / "music.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        x, _ = read_wav(out / "mix.wav")
        self.assertLessEqual(abs(len(x) - 6 * SR), 1)
        self.assertLess(np.abs(x[int(4.05 * SR):]).max(), 1e-3)  # padded with silence
        r, out = self.mix("--duration", 3, "--music", self.d / "music.wav")
        x, _ = read_wav(out / "mix.wav")
        self.assertLessEqual(abs(len(x) - 3 * SR), 1)


# ---------------------------------------------------------------------------------------- A4
@helpers.needs_ffmpeg
class Sync(unittest.TestCase):
    HITS = [hit(0.5, "land", "thud"), hit(1.0, "press", "click"), hit(1.5, "appear", "pop"),
            hit(2.0, "boom", "impact"), hit(2.6, "key", "type-key"), hit(3.0, "slide", "whoosh")]

    @classmethod
    def setUpClass(cls):
        cls.d = helpers.tmpdir()
        write_hits(cls.d / "hits.json", cls.HITS, 3.5)
        r = helpers.run_script("sfx.py", cls.d / "hits.json", "--out", cls.d / "sfx.wav")
        assert r.returncode == 0, r.stderr
        cls.events = cls.d / "sfx_events.json"
        x, _ = read_wav(cls.d / "sfx.wav")
        late = np.concatenate([np.zeros((int(0.040 * SR), 2)), x])[:len(x)]
        write_wav16(cls.d / "late.wav", late)

    def sync(self, media, *extra):
        r = helpers.run_script("sync.py", media, self.events, *extra)
        return r, json.loads(r.stdout)

    def test_aligned(self):
        r, rep = self.sync(self.d / "sfx.wav")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rep["status"], "pass")
        trans = [h for h in rep["hits"] if h["status"] != "info"]
        self.assertEqual(len(trans), 5)
        for h in trans:
            self.assertLessEqual(abs(h["offset_ms"]), 2, h)
            for k in ("label", "t", "expected", "detected", "offset_ms", "status"):
                self.assertIn(k, h)

    def test_late(self):
        r, rep = self.sync(self.d / "late.wav")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(rep["status"].startswith("FAIL"), rep["status"])
        trans = [h for h in rep["hits"] if h["status"] != "info"]
        self.assertEqual(len(trans), 5)
        for h in trans:
            self.assertAlmostEqual(h["offset_ms"], 40, delta=3)

    def test_nontransient_info(self):
        _, rep = self.sync(self.d / "late.wav")
        w = [h for h in rep["hits"] if h["label"] == "slide"]
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["status"], "info")

    def test_not_audible(self):
        silent = self.d / "silent.wav"
        write_wav16(silent, np.zeros((int(3.5 * SR), 2)))
        r, rep = self.sync(silent)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not audible", json.dumps(rep["hits"]))

    def test_under_music(self):
        music = drum_loop(110, 0.0, 3.5, hats=True, seed=3) * 0.5
        sfx, _ = read_wav(self.d / "sfx.wav")
        mixed = self.d / "under_music.wav"
        write_wav16(mixed, sfx * 0.6 + music[:len(sfx), None])
        r, rep = self.sync(mixed)
        self.assertEqual(rep["method"], "stem")
        self.assertEqual(r.returncode, 0, rep)
        for h in rep["hits"]:
            if h["status"] != "info":
                self.assertLessEqual(abs(h["offset_ms"]), 2, h)

    def test_blind_fallback(self):
        d = helpers.tmpdir()
        ev = helpers.copy_fixture(self.events, d)  # no sfx.wav next to it
        r = helpers.run_script("sync.py", self.d / "sfx.wav", ev)
        rep = json.loads(r.stdout)
        self.assertEqual(rep["method"], "onset")
        self.assertEqual(r.returncode, 0, rep)
        r = helpers.run_script("sync.py", self.d / "late.wav", ev)
        self.assertEqual(r.returncode, 1)

    def test_png(self):
        png = helpers.tmpdir() / "sync.png"
        r, _ = self.sync(self.d / "sfx.wav", "--png", png)
        self.assertEqual(r.returncode, 0)
        from PIL import Image
        with Image.open(png) as im:
            self.assertEqual(im.format, "PNG")
            self.assertGreater(im.width, 400)

    def test_measure_api(self):
        import sync, _audio
        rep = sync.measure(_audio.load(self.d / "sfx.wav"), SR, json.loads(self.events.read_text())["events"])
        self.assertEqual(rep["status"], "pass")

    def video_with(self, wav):
        v = make_video(helpers.tmpdir() / "v.mp4", 3.5)
        r = helpers.run_script("mix.py", "--duration", 3.5, "--sfx", wav, "--out", v.parent / "mix.wav", "--mux", v)
        self.assertEqual(r.returncode, 0, r.stderr)
        return v

    def test_video_and_check_gate(self):
        good, bad = self.video_with(self.d / "sfx.wav"), self.video_with(self.d / "late.wav")
        r, rep = self.sync(good)
        self.assertEqual(r.returncode, 0, rep)
        r = helpers.run_script("check.py", good, "--sync", self.events, "--no-sheet")
        rep = helpers.parse_report(r.stdout)
        self.assertEqual(rep["gates"]["sync"], "pass", rep)
        self.assertEqual(r.returncode, 0, rep)
        r = helpers.run_script("check.py", bad, "--sync", self.events, "--no-sheet")
        rep = helpers.parse_report(r.stdout)
        self.assertTrue(rep["gates"]["sync"].startswith("FAIL"), rep)
        self.assertEqual(r.returncode, 1)

    def test_check_without_sync_unchanged(self):
        v = make_video(helpers.tmpdir() / "v.mp4", 2.0)
        r = helpers.run_script("check.py", v, "--no-sheet")
        rep = helpers.parse_report(r.stdout)
        self.assertNotIn("sync", rep["gates"])


if __name__ == "__main__":
    unittest.main()
