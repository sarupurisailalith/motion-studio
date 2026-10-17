"""Tests for the v0.3 audio additions: new SFX presets and loopable beds (E1.8, E1.9), project
palettes (E1.10), sample-based SFX (E12.13) and mix.py's --duration default (D.3).

All test audio is generated in code (numpy) and written to helpers.tmpdir().
"""
import json, sys, textwrap, unittest
from pathlib import Path

import numpy as np

import helpers
from test_audio import SR, hit, read_wav, write_hits, write_wav16

sys.path.insert(0, str(helpers.SCRIPTS))

NEW = ["scrape", "whoomp", "crackle", "creak", "splash", "rustle", "chime", "zip", "sizzle"]

# a project palette: one transient recipe, one soft one
PALETTE = textwrap.dedent('''
    import numpy as np
    import sfx

    def knock(sr, rng, o):
        """two wooden knocks"""
        t = np.arange(int(0.12 * sr)) / sr
        y = np.sin(2 * np.pi * 420 * t) * np.exp(-t / 0.015)
        y[int(0.06 * sr):] += 0.7 * y[:len(y) - int(0.06 * sr)]
        return y, 0.0, 0.001

    def hum(sr, rng, o):
        t = np.arange(int(o.get("len", 0.5) * sr)) / sr
        return np.sin(2 * np.pi * 120 * t) * np.hanning(len(t)), 0.0, len(t) / sr / 2

    sfx.register("knock", knock, "start", transient=True)
    sfx.register("hum", hum, "peak", "soft electrical hum")
''')


def sfx_run(d, hits, duration, *extra):
    h = write_hits(d / "hits.json", hits, duration)
    r = helpers.run_script("sfx.py", h, "--out", d / "sfx.wav", *extra)
    return r


def seam_ok(x):
    """A loop seam is click-free if the jump across it is no bigger than the signal's own
    sample-to-sample motion and the level around it neither drops out nor bursts."""
    z = np.concatenate([x, x])
    n = len(x)
    jump = np.abs(np.diff(z))
    k = int(0.005 * SR)
    rms = lambda a: float(np.sqrt(np.mean(np.square(a))))
    wins = [rms(z[i:i + k]) for i in range(0, 2 * n - k, k)]
    at = rms(z[n - k // 2:n + k // 2])
    return jump[n - 1] <= np.percentile(jump, 99.9) and 0.25 * np.median(wins) <= at <= 4 * np.median(wins)


# ---------------------------------------------------------------------------------------- E1.8 / E1.9
@helpers.needs_ffmpeg
class Presets(unittest.TestCase):
    def test_list_and_anchors(self):
        import sfx
        r = helpers.run_script("sfx.py", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        for n in NEW:
            self.assertIn(n, r.stdout)
            self.assertTrue(sfx.DESCRIBE[n])
        self.assertEqual(sfx.ANCHOR["whoomp"], "peak")
        self.assertEqual(sfx.ANCHOR["zip"], "end")
        self.assertEqual(sfx.ANCHOR["scrape"], "start")
        self.assertLessEqual({"splash", "chime"}, sfx.TRANSIENT)
        import sync
        self.assertIs(sync.TRANSIENT, sfx.TRANSIENT)

    def test_len_and_determinism(self):
        import sfx
        for n in NEW:
            a = sfx.synth(n, SR, np.random.default_rng([1, 0]), {"len": 0.5})[0]
            b = sfx.synth(n, SR, np.random.default_rng([1, 0]), {"len": 0.5})[0]
            self.assertTrue(np.array_equal(a, b), n)
            self.assertTrue(np.isfinite(a).all(), n)
            self.assertAlmostEqual(len(a) / SR, 0.5, delta=0.01, msg=n)

    def test_anchor_placement(self):
        d = helpers.tmpdir()
        r = sfx_run(d, [hit(1.0, "flame", "whoomp"), hit(2.0, "in", "zip"), hit(2.5, "cut", "scrape", len=0.4)], 3.5)
        self.assertEqual(r.returncode, 0, r.stderr)
        ev = {e["label"]: e for e in json.loads((d / "sfx_events.json").read_text())["events"]}
        self.assertAlmostEqual(ev["flame"]["peak"], 1.0, delta=0.001)
        self.assertAlmostEqual(ev["in"]["end"], 2.0, delta=0.001)
        self.assertAlmostEqual(ev["cut"]["onset"], 2.5, delta=0.001)
        self.assertAlmostEqual(ev["cut"]["end"] - ev["cut"]["onset"], 0.4, delta=0.01)
        self.assertEqual({e["source"] for e in ev.values()}, {"synth"})

    def test_bed_seams(self):
        import sfx
        for n in ("crackle", "sizzle"):
            for pitch in (0, 2):
                y = sfx.synth(n, SR, np.random.default_rng([3, 0]), {"len": 1.5, "loop": True, "pitch": pitch})[0]
                self.assertTrue(seam_ok(y), (n, pitch))
            y = sfx.synth(n, SR, np.random.default_rng([3, 0]), {"len": 1.5})[0]
            self.assertLess(abs(y[0]) + abs(y[-1]), 1e-6, n)   # one-shot: faded edges

    def test_loop_track_seam(self):
        # a loop piece: the bed spans the whole track, and the track itself loops without a click
        d = helpers.tmpdir()
        r = sfx_run(d, [hit(0.0, "fire", "crackle", len=2.0, loop=True), hit(0.7, "pan", "sizzle", len=2.0, loop=True)], 2.0)
        self.assertEqual(r.returncode, 0, r.stderr)
        x, _ = read_wav(d / "sfx.wav")
        self.assertTrue(seam_ok(x[:, 0]) and seam_ok(x[:, 1]))
        self.assertGreater(np.abs(x[:int(0.6 * SR)]).max(), 1e-3)  # the sizzle wrapped to the start

    def test_new_transients_sync(self):
        d = helpers.tmpdir()
        sfx_run(d, [hit(0.5, "drop", "splash"), hit(1.5, "bell", "chime"), hit(2.5, "door", "creak")], 3.5)
        r = helpers.run_script("sync.py", d / "sfx.wav", d / "sfx_events.json")
        rep = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0, rep)
        st = {h["label"]: h for h in rep["hits"]}
        self.assertEqual(st["door"]["status"], "info")
        for k in ("drop", "bell"):
            self.assertEqual(st[k]["status"], "pass")
            self.assertLessEqual(abs(st[k]["offset_ms"]), 2, st[k])


# ---------------------------------------------------------------------------------------- E1.10
@helpers.needs_ffmpeg
class ProjectPalette(unittest.TestCase):
    def project(self):
        p = helpers.tmpdir()
        (p / "audio").mkdir()
        (p / "renders").mkdir()
        (p / "audio" / "palette.py").write_text(PALETTE)
        write_hits(p / "renders" / "comp_hits.json", [hit(0.5, "rap", "knock"), hit(1.2, "lamp", "hum"),
                                                     hit(2.0, "land", "thud")], 3.0)
        return p

    def test_autoload_and_transient(self):
        p = self.project()
        r = helpers.run_script("sfx.py", p / "renders" / "comp_hits.json", "--out", p / "audio" / "sfx.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("knock", r.stderr)
        ev = {e["label"]: e for e in json.loads((p / "audio" / "sfx_events.json").read_text())["events"]}
        self.assertIs(ev["rap"]["transient"], True)
        self.assertIs(ev["lamp"]["transient"], False)
        self.assertAlmostEqual(ev["lamp"]["peak"], 1.2, delta=0.001)
        # sync.py gates the registered transient: aligned passes, 40 ms late fails on it
        events = p / "audio" / "sfx_events.json"
        r = helpers.run_script("sync.py", p / "audio" / "sfx.wav", events)
        rep = json.loads(r.stdout)
        self.assertEqual(r.returncode, 0, rep)
        self.assertEqual([h["status"] for h in rep["hits"] if h["label"] == "rap"], ["pass"])
        x, _ = read_wav(p / "audio" / "sfx.wav")
        late = p / "late.wav"
        write_wav16(late, np.concatenate([np.zeros((int(0.04 * SR), 2)), x])[:len(x)])
        rep = json.loads(helpers.run_script("sync.py", late, events, "--ref", p / "audio" / "sfx.wav").stdout)
        self.assertTrue([h for h in rep["hits"] if h["label"] == "rap"][0]["status"].startswith("FAIL"), rep)

    def test_explicit_and_no_palette(self):
        p = self.project()
        pal = p / "audio" / "palette.py"
        alt = p / "elsewhere.py"
        alt.write_text(pal.read_text())
        pal.unlink()
        out = helpers.tmpdir() / "sfx.wav"
        r = helpers.run_script("sfx.py", p / "renders" / "comp_hits.json", "--out", out, "--palette", alt)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = helpers.run_script("sfx.py", p / "renders" / "comp_hits.json", "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown sfx 'knock'", r.stderr)
        self.assertIn("type-key, scrape", r.stderr)   # the full palette is listed
        r = helpers.run_script("sfx.py", "--list", "--palette", alt)
        self.assertIn("soft electrical hum", r.stdout)
        self.assertRegex(r.stdout, r"knock\s+anchor=start transient\s+two wooden knocks")

    def test_bad_palette(self):
        p = helpers.tmpdir()
        (p / "pal.py").write_text("import sfx\nsfx.register('x', print, 'middle')\n")
        r = helpers.run_script("sfx.py", "--list", "--palette", p / "pal.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("anchor must be start, peak or end", r.stderr)
        r = helpers.run_script("sfx.py", "--list", "--palette", p / "missing.py")
        self.assertIn("palette not found", r.stderr)

    def test_old_events_fall_back(self):
        import sync
        ev = [{"t": 0.5, "label": "a", "sfx": "thud", "onset": 0.5}, {"t": 1, "label": "b", "sfx": "hum", "onset": 1.0}]
        rep = sync.measure(np.zeros(2 * SR), SR, ev)
        self.assertEqual([h["status"] for h in rep["hits"]], ["FAIL not audible", "info"])


# ---------------------------------------------------------------------------------------- E12.13
def take(attack, dur=0.4, lead=0.25, tail=0.3, f=70.0, rising=False):
    """A test 'recording': silence, a tone with the given attack (s), silence."""
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(t / max(attack, 1e-4), 1) * (np.exp(-t / 0.12) if not rising else (t / dur) ** 2)
    y = np.sin(2 * np.pi * f * t) * env * 0.3
    return np.concatenate([np.zeros(int(lead * SR)), y, np.zeros(int(tail * SR))])


@helpers.needs_ffmpeg
class Samples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = helpers.tmpdir()
        write_wav16(cls.s / "thud_1.wav", take(0.08))                  # soft attack
        write_wav16(cls.s / "thud_2.wav", take(0.0005))                # crisp: the one to pick
        write_wav16(cls.s / "riser_1.wav", take(0.001, 1.0))           # decays: wrong shape
        write_wav16(cls.s / "riser_2.wav", take(0.001, 1.0, rising=True, f=300))
        write_wav16(cls.s / "doorbell_1.wav", take(0.001, 0.6, f=660))  # a name only the samples have
        (cls.s / "notes.txt").write_text("ignored")

    def run_sfx(self, hits, *extra):
        d = helpers.tmpdir()
        r = sfx_run(d, hits, 4.0, "--samples", self.s, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        ev = {e["label"]: e for e in json.loads((d / "sfx_events.json").read_text())["events"]}
        return d, ev, json.loads(r.stdout)

    def test_pick_and_place(self):
        d, ev, out = self.run_sfx([hit(0.5, "land", "thud"), hit(2.0, "build", "riser"),
                                   hit(2.5, "ring", "doorbell"), hit(3.0, "tap", "click")])
        self.assertEqual(ev["land"]["source"], "thud_2.wav")
        self.assertEqual(ev["build"]["source"], "riser_2.wav")
        self.assertEqual(ev["ring"]["source"], "doorbell_1.wav")
        self.assertEqual(ev["tap"]["source"], "synth")
        self.assertEqual(out["sampled"], 3)
        self.assertAlmostEqual(ev["build"]["end"], 2.0, delta=0.001)
        x, _ = read_wav(d / "sfx.wav")
        m = np.abs(x).max(axis=1)
        first = np.where(m > 10 ** (-40 / 20))[0][0] / SR
        self.assertLessEqual(abs(first - 0.5), 0.002)                     # leading silence trimmed
        self.assertAlmostEqual(20 * np.log10(m[int(0.4 * SR):int(1.2 * SR)].max()), -9, delta=0.3)  # -6 dBFS, centre pan
        r = helpers.run_script("sync.py", d / "sfx.wav", d / "sfx_events.json")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_len_cut_and_determinism(self):
        d1, ev, _ = self.run_sfx([hit(0.5, "land", "thud", len=0.15)])
        self.assertAlmostEqual(ev["land"]["end"] - ev["land"]["onset"], 0.15, delta=0.005)
        d2, _, _ = self.run_sfx([hit(0.5, "land", "thud", len=0.15)])
        self.assertEqual((d1 / "sfx.wav").read_bytes(), (d2 / "sfx.wav").read_bytes())

    def test_unknown_still_fails(self):
        d = helpers.tmpdir()
        r = sfx_run(d, [hit(0.5, "x", "kazoo")], 2.0, "--samples", self.s)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("samples: doorbell, riser, thud", r.stderr)

    def test_missing_dir(self):
        r = sfx_run(helpers.tmpdir(), [hit(0.5, "x", "thud")], 2.0, "--samples", self.s / "nope")
        self.assertIn("samples folder not found", r.stderr)


# ---------------------------------------------------------------------------------------- D.3
@helpers.needs_ffmpeg
class MixDuration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = helpers.tmpdir()
        sfx_run(cls.d, [hit(0.5, "a", "thud")], 2.0)

    def project(self):
        p = helpers.tmpdir()
        (p / "renders").mkdir()
        (p / "audio").mkdir()
        return p

    def length(self, wav):
        return len(read_wav(wav)[0]) / SR

    def test_from_hits(self):
        p = self.project()
        write_hits(p / "renders" / "comp_hits.json", [], 3.0)
        write_hits(p / "renders" / "comp_9x16_hits.json", [], 3.0)
        r = helpers.run_script("mix.py", "--sfx", self.d / "sfx.wav", "--out", p / "audio" / "mix.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("duration 3s from", r.stderr)
        self.assertAlmostEqual(self.length(p / "audio" / "mix.wav"), 3.0, delta=1 / SR)
        self.assertEqual(json.loads(r.stdout)["duration"], 3.0)

    def test_disagreeing_hits(self):
        p = self.project()
        write_hits(p / "renders" / "a_hits.json", [], 3.0)
        write_hits(p / "renders" / "b_hits.json", [], 4.0)
        r = helpers.run_script("mix.py", "--sfx", self.d / "sfx.wav", "--out", p / "audio" / "mix.wav")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pass --duration", r.stderr)

    def test_from_deliver_for_mux(self):
        from test_audio import make_video
        p = self.project()
        v = make_video(p / "renders" / "comp_1x1.mp4", 2.0)
        write_hits(p / "renders" / "comp_hits.json", [], 9.0)     # deliver.json wins
        (p / "renders" / "deliver.json").write_text(json.dumps({"version": 1, "items": [
            {"format": "1x1", "video": "renders/comp_1x1.mp4", "duration": 2.0},
            {"format": "16x9", "video": "renders/comp_16x9.mp4", "duration": 2.5}]}))
        r = helpers.run_script("mix.py", "--sfx", self.d / "sfx.wav", "--out", helpers.tmpdir() / "mix.wav", "--mux", v)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["duration"], 2.0)

    def test_nothing_to_read(self):
        r = helpers.run_script("mix.py", "--sfx", self.d / "sfx.wav", "--out", self.project() / "audio" / "mix.wav")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pass --duration", r.stderr)

    def test_explicit_wins(self):
        p = self.project()
        write_hits(p / "renders" / "comp_hits.json", [], 3.0)
        r = helpers.run_script("mix.py", "--duration", 1.5, "--sfx", self.d / "sfx.wav", "--out", p / "audio" / "mix.wav")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertAlmostEqual(self.length(p / "audio" / "mix.wav"), 1.5, delta=1 / SR)


if __name__ == "__main__":
    unittest.main()
