"""Fixes from the W3 dogfood trial (_docs/v0.2/dogfood.md, friction items 1, 2, 5, 9)."""
import json, subprocess, sys, unittest

import numpy as np

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir

sys.path.insert(0, str(helpers.SCRIPTS))
SR = 48000


def tiny_video(path, seconds=2):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=duration={seconds}:size=160x120:rate=30", "-pix_fmt", "yuv420p", str(path)],
                   check=True)


def sparse_sfx(path, seconds=12.0, hits=(1.0, 4.0, 7.0, 10.0)):
    """Four 60 ms clicks in 12 s of silence: an SFX-only piece."""
    import _audio
    x = np.zeros(int(seconds * SR))
    rng = np.random.default_rng(1)
    for t in hits:
        i, n = int(t * SR), int(0.06 * SR)
        x[i:i + n] = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.01 * SR)) * 0.3
    _audio.write_wav(path, x)


@helpers.needs_ffmpeg
class CheckSheetName(unittest.TestCase):
    """Friction 2: check.py must not overwrite the contact sheet --deliver wrote."""

    def test_qa_sheet_does_not_clobber_deliver_sheet(self):
        d = tmpdir()
        mp4 = d / "comp_9x16.mp4"
        tiny_video(mp4)
        deliver_sheet = d / "comp_9x16_sheet.png"
        deliver_sheet.write_bytes(b"from --deliver")
        r = run_script("check.py", mp4)
        rep = parse_report(r.stdout)
        self.assertEqual(deliver_sheet.read_bytes(), b"from --deliver")
        self.assertTrue(rep["contact_sheet"].endswith("comp_9x16_qa_sheet.png"), rep["contact_sheet"])
        self.assertTrue((d / "comp_9x16_qa_sheet.png").exists())

    def test_json_flag_writes_report_file(self):
        d = tmpdir()
        mp4 = d / "v.mp4"
        tiny_video(mp4)
        out = d / "qa.json"
        r = run_script("check.py", mp4, "--no-sheet", "--json", out)
        self.assertEqual(json.loads(out.read_text()), parse_report(r.stdout))

    def test_help_documents_gates(self):
        h = run_script("check.py", "--help").stdout
        for word in ("blank", "pops", "frozen", "loop_seam", "audio", "sync", "--max-hold", "--json"):
            self.assertIn(word, h)


@helpers.needs_ffmpeg
class SparseLoudness(unittest.TestCase):
    """Friction 9: an SFX-only mix must not be chased to -14 LUFS integrated through the limiter.
    Measured on v0.2: that crushed 4 clicks from a 19.6 dB to a 10.8 dB crest factor and still
    reported FAIL. Sparse mode peak-normalises instead and leaves the transients intact."""

    def test_sfx_only_mix_is_peak_normalised_not_crushed(self):
        import _audio
        d = tmpdir()
        sparse_sfx(d / "sfx.wav")
        r = run_script("mix.py", "--duration", 12, "--sfx", d / "sfx.wav", "--out", d / "mix.wav")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        rep = json.loads(r.stdout)
        self.assertEqual(rep["mode"], "sparse")
        self.assertTrue(-2.0 <= rep["true_peak"] <= -1.0, rep["true_peak"])
        self.assertIn("max_momentary", rep)
        crest = lambda x: 20 * np.log10(np.abs(x).max() / np.sqrt((x ** 2).mean()))
        mono = lambda x: x if x.ndim == 1 else x.mean(axis=1)
        a = mono(_audio.load(d / "sfx.wav", SR))[SR:int(1.06 * SR)]
        b = mono(_audio.load(d / "mix.wav", SR))[SR:int(1.06 * SR)]
        self.assertAlmostEqual(crest(b), crest(a), delta=1.0)   # no limiting on the clicks

    def test_music_mix_still_integrated(self):
        d = tmpdir()
        import _audio
        t = np.arange(int(12 * SR)) / SR
        _audio.write_wav(d / "m.wav", 0.03 * np.sin(2 * np.pi * 440 * t))
        rep = json.loads(run_script("mix.py", "--duration", 12, "--music", d / "m.wav", "--out", d / "mix.wav").stdout)
        self.assertEqual(rep["mode"], "integrated")
        self.assertAlmostEqual(rep["lufs"], -14.0, delta=0.2)

    def test_check_accepts_sparse_audio(self):
        d = tmpdir()
        sparse_sfx(d / "sfx.wav")
        mp4 = d / "v.mp4"
        tiny_video(mp4, 12)
        run_script("mix.py", "--duration", 12, "--sfx", d / "sfx.wav", "--out", d / "mix.wav", "--mux", mp4)
        rep = parse_report(run_script("check.py", mp4, "--no-sheet").stdout)
        self.assertTrue(rep["gates"]["audio"].startswith("pass"), rep["gates"]["audio"])
        self.assertIn("sparse", rep["gates"]["audio"])


@helpers.slow
@helpers.needs_chromium
class DeterminismDiagnostics(unittest.TestCase):
    """Friction 1: a determinism FAIL must say how much changed and where."""

    def test_fail_names_pixels_and_box(self):
        rep = parse_report(run_script("render.py", copy_fixture("golden/broken_clock.html", tmpdir()),
                                      "--check-only").stdout)
        g = rep["gates"]["determinism"]
        self.assertTrue(g.startswith("FAIL"), g)
        self.assertRegex(g, r"\d+ px")
        self.assertRegex(g, r"x=\d+-\d+, y=\d+-\d+")


class DeterminismTolerance(unittest.TestCase):
    """Sub-visible anti-aliasing noise (max 1/255 on an edge) is not a determinism failure;
    a visible change is. Same tolerance as the loop-seam gate (> 24/255 on > 8 px)."""

    def test_classify(self):
        import io
        from PIL import Image
        import render
        def png(arr):
            b = io.BytesIO(); Image.fromarray(arr.astype("uint8")).save(b, "PNG"); return b.getvalue()
        base = np.full((100, 100, 3), 128)
        noise = base.copy(); noise[40:60, 40:60] += 1          # 400 px, 1/255
        real = base.copy(); real[10:30, 10:30] = 255            # 400 px, 127/255
        self.assertIsNone(render.visible_diff(png(base), png(noise)))
        n, mx, box = render.visible_diff(png(base), png(real))
        self.assertEqual((n, mx, box), (400, 127, (10, 29, 10, 29)))


class TemplateFont(unittest.TestCase):
    """Friction 5: no silent fallback from an uninstalled 'Inter'."""

    def test_template_font_is_an_explicit_system_stack(self):
        src = (helpers.TEMPLATES / "composition.html").read_text()
        line = next(l for l in src.splitlines() if "--font-display:" in l)
        self.assertNotIn('"Inter"', line)
        self.assertIn("system-ui", line)


if __name__ == "__main__":
    unittest.main()
