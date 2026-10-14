"""W1-C: render.py — v0.1 compatibility, --format, --hits, review renders, gates, --deliver.

Fixtures in tests/fixtures/render/ implement the C1-C4 contracts by hand (inline window.K),
so these tests never depend on the real kit."""
import json, subprocess, unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir


def fixture(name):
    """Copy a render fixture (or a golden one, 'golden/x.html') into a fresh temp dir."""
    rel = name if "/" in name else "render/" + name
    return copy_fixture(rel, tmpdir())


def render(html, *args):
    return run_script("render.py", html, *args)


def png_size(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,pix_fmt", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"][0]


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Compat(unittest.TestCase):
    """v0.1 command lines: same output names, same stdout shape."""

    def test_stills_names_unchanged(self):
        html = fixture("golden/blank_frame.html")
        r = render(html, "--stills", "0,0.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(p.name for p in (html.parent / "renders").iterdir())
        self.assertEqual(names, ["blank_frame_t000.000.png", "blank_frame_t000.500.png"])
        self.assertNotIn("{", r.stdout)  # stills mode prints no report

    def test_check_only_single_report(self):
        html = fixture("golden/blank_frame.html")
        r = render(html, "--check-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = parse_report(r.stdout)
        self.assertEqual(set(rep), {"file", "width", "height", "fps", "duration", "gates"})
        self.assertEqual((rep["width"], rep["height"], rep["fps"]), (320, 320, 30))
        self.assertEqual(rep["gates"]["determinism"], "pass")
        self.assertNotIn("format", rep)

    def test_full_render_names_unchanged(self):
        html = fixture("golden/blank_frame.html")
        r = render(html, "--workers", "1", "--duration", "0.3")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["blank_frame.mp4", "blank_frame_report.json"])
        rep = json.loads((out / "blank_frame_report.json").read_text())
        self.assertNotIn("format", rep)
        self.assertEqual(rep["frames"], 9)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Format(unittest.TestCase):
    def test_check_only_two_formats(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "9x16,1x1", "--check-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = parse_report(r.stdout)
        self.assertEqual(list(rep), ["formats"])
        self.assertEqual(list(rep["formats"]), ["9x16", "1x1"])
        f = rep["formats"]["9x16"]
        self.assertEqual((f["width"], f["height"], f["format"]), (1080, 1920, "9x16"))
        g = rep["formats"]["1x1"]
        self.assertEqual((g["width"], g["height"], g["format"]), (1080, 1080, "1x1"))
        for name, sub in rep["formats"].items():
            self.assertEqual(sub["gates"]["determinism"], "pass", name)

    def test_single_format_still_wrapped(self):
        html = fixture("fmt.html")
        rep = parse_report(render(html, "--format", "4x5", "--check-only", "--skip-checks").stdout)
        self.assertEqual(list(rep["formats"]), ["4x5"])
        self.assertEqual(rep["formats"]["4x5"]["height"], 1350)

    def test_sheet_named_and_portrait(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "9x16", "--sheet")
        self.assertEqual(r.returncode, 0, r.stderr)
        sheet = html.parent / "renders" / "fmt_9x16_sheet.png"
        self.assertTrue(sheet.exists(), r.stdout)
        w, h = png_size(sheet)
        self.assertGreater(h, w)
        self.assertTrue((html.parent / "renders" / "fmt_9x16_t000.000.png").exists())

    def test_full_render_two_formats(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "1x1,16x9", "--workers", "1", "--duration", "0.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        for name, (w, h) in {"1x1": (1080, 1080), "16x9": (1920, 1080)}.items():
            s = probe(out / f"fmt_{name}.mp4")
            self.assertEqual((s["width"], s["height"]), (w, h), name)
            rep = json.loads((out / f"fmt_{name}_report.json").read_text())
            self.assertEqual(rep["format"], name)
        self.assertFalse((out / "fmt.mp4").exists())

    def test_unknown_format_lists_valid_names(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "3x2", "--check-only")
        self.assertNotEqual(r.returncode, 0)
        for name in ("16x9", "9x16", "1x1", "4x5"):
            self.assertIn(name, r.stderr)

    def test_composition_ignoring_format_is_an_error(self):
        # a v0.1 composition that never reads ?format would be mislabelled -> refuse
        html = fixture("golden/blank_frame.html")
        r = render(html, "--format", "9x16", "--check-only")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("K.init", r.stderr)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Hits(unittest.TestCase):
    def test_hits_via_kit(self):
        html = fixture("hits.html")
        r = render(html, "--hits")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        data = json.loads((out / "hits_hits.json").read_text())
        self.assertEqual(data, {
            "version": 1, "source": "hits.html", "fps": 30, "duration": 2.0,
            "hits": [
                {"t": 0.25, "label": "card-in", "sfx": None, "opts": {}},
                {"t": 0.9, "label": "drop", "sfx": "impact", "opts": {"gain": -3}},
                {"t": 1.25, "label": "logo-land", "sfx": "thud", "opts": {}},
            ]})
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["hits_hits.json"])  # no render

    def test_numeric_hits_without_kit(self):
        html = fixture("hits_nok.html")
        r = render(html, "--hits")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((html.parent / "renders" / "hits_nok_hits.json").read_text())
        self.assertEqual(data["hits"], [
            {"t": 0.5, "label": "a", "sfx": "tick", "opts": {}},
            {"t": 1.5, "label": "b", "sfx": "pop", "opts": {"pan": 0.5}},
        ])

    def test_beat_hits_without_kit_fail(self):
        html = fixture("hits_nok_beat.html")
        r = render(html, "--hits")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("beat-timed hits need the kit (window.K.resolveHits)", r.stderr)
        self.assertFalse((html.parent / "renders" / "hits_nok_beat_hits.json").exists())

    def test_hits_rejects_other_modes(self):
        html = fixture("hits.html")
        r = render(html, "--hits", "--check-only")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--hits", r.stderr)

    def test_hits_with_format(self):
        html = fixture("fmt.html")
        r = render(html, "--hits", "--format", "1x1")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((html.parent / "renders" / "fmt_1x1_hits.json").read_text())
        self.assertEqual(data["hits"], [])


def pixels(path):
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Review(unittest.TestCase):
    def assertSamePicture(self, a, b):
        self.assertTrue((pixels(a) == pixels(b)).all(), f"{a.name} != {b.name}")

    def test_poster_at_time(self):
        html = fixture("fmt.html")
        r = render(html, "--poster", "0.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        poster = out / "fmt_poster.png"
        self.assertEqual(png_size(poster), (320, 320))
        render(html, "--stills", "0.5,1")
        self.assertSamePicture(poster, out / "fmt_t000.500.png")
        self.assertFalse((pixels(poster) == pixels(out / "fmt_t001.000.png")).all())

    def test_poster_default_times(self):
        for name, t in (("fmt.html", "001.500"),      # non-loop, no MOTION.poster -> D - 0.5
                        ("poster.html", "000.700"),   # MOTION.poster
                        ("loop.html", "000.000")):    # loop, no MOTION.poster -> 0
            html = fixture(name)
            r = render(html, "--poster")
            self.assertEqual(r.returncode, 0, r.stderr)
            render(html, "--stills", str(float(t)))
            out = html.parent / "renders"
            self.assertSamePicture(out / f"{html.stem}_poster.png", out / f"{html.stem}_t{t}.png")

    def test_strip(self):
        html = fixture("fmt.html")
        r = render(html, "--strip", "0:1:5")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        strip = out / "fmt_strip_0-1.png"
        w, h = png_size(strip)
        self.assertEqual(h, 320)
        self.assertAlmostEqual(w, 5 * 320, delta=40)
        sharp = pixels(strip)
        render(html, "--strip", "0:1:5", "--subframes", "4")
        blurred = pixels(strip)
        self.assertEqual(sharp.shape, blurred.shape)
        self.assertFalse((sharp == blurred).all())

    def test_bad_strip_spec(self):
        r = render(fixture("fmt.html"), "--strip", "0:1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A:B:N", r.stderr)

    def test_phone_sheet(self):
        html = fixture("fmt.html")
        r = render(html, "--phone")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        self.assertEqual(png_size(out / "fmt_sheet_phone.png"), (4 * 270 + 3 * 6, 4 * 270 + 3 * 6))
        self.assertEqual([p.name for p in out.iterdir()], ["fmt_sheet_phone.png"])

    def test_beats_contact_sheet(self):
        html = fixture("beats.html")
        r = render(html, "--contact", "beats")
        self.assertEqual(r.returncode, 0, r.stderr)
        w, h = png_size(html.parent / "renders" / "beats_beats_sheet.png")
        self.assertEqual((w, h), (4 * 480 + 3 * 6, 480))  # 4 downbeats inside the duration, one row

    def test_beats_contact_needs_beats(self):
        r = render(fixture("fmt.html"), "--contact", "beats")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("beats.js", r.stderr)

    def test_review_with_format(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "9x16", "--poster", "0.5", "--strip", "0:1:3", "--phone")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        self.assertEqual(png_size(out / "fmt_9x16_poster.png"), (1080, 1920))
        self.assertTrue((out / "fmt_9x16_strip_0-1.png").exists())
        self.assertTrue((out / "fmt_9x16_sheet_phone.png").exists())
        b = fixture("beats.html")
        r = render(b, "--format", "1x1", "--contact", "beats")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((b.parent / "renders" / "beats_1x1_beats_sheet.png").exists())


def gates(html, *args):
    r = render(html, "--check-only", *args)
    return r, parse_report(r.stdout)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Gates(unittest.TestCase):
    def test_clean_fixture_passes(self):
        _, rep = gates(fixture("fmt.html"))
        self.assertEqual(rep["gates"]["safe_area"], "pass")
        self.assertEqual(rep["gates"]["text_duration"], "pass")

    def test_clean_fixture_passes_in_portrait(self):
        _, rep = gates(fixture("fmt.html"), "--format", "9x16,4x5")
        for name in ("9x16", "4x5"):
            self.assertEqual(rep["formats"][name]["gates"]["safe_area"], "pass", name)

    def test_overflow_fails(self):
        r, rep = gates(fixture("unsafe.html"))
        self.assertEqual(r.returncode, 0)  # gates report, they don't change the exit code (v0.1)
        g = rep["gates"]["safe_area"]
        self.assertTrue(g.startswith("FAIL"), g)
        self.assertIn("#badge", g)
        self.assertIn("t=0.5", g)
        self.assertIn("right by 40 px", g)

    def test_flash_text_warns(self):
        _, rep = gates(fixture("flash_text.html"))
        g = rep["gates"]["text_duration"]
        self.assertTrue(g.startswith("WARN"), g)
        self.assertIn("#flash", g)
        self.assertIn("5 frames", g)

    def test_no_kit_skips_safe_area(self):
        _, rep = gates(fixture("golden/broken_clock.html"))
        self.assertEqual(rep["gates"]["safe_area"], "skipped (no window.K)")
        self.assertTrue(rep["gates"]["text_duration"].startswith("pass"))

    def test_gates_in_full_render_report(self):
        html = fixture("unsafe.html")
        r = render(html, "--workers", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((html.parent / "renders" / "unsafe_report.json").read_text())
        self.assertTrue(rep["gates"]["safe_area"].startswith("FAIL"))
        self.assertIn("text_duration", rep["gates"])
        r = render(html, "--workers", "1", "--skip-checks")
        rep = json.loads((html.parent / "renders" / "unsafe_report.json").read_text())
        self.assertNotIn("safe_area", rep["gates"])


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Deliver(unittest.TestCase):
    def test_deliver_two_formats(self):
        html = fixture("fmt.html")
        r = render(html, "--format", "1x1,9x16", "--deliver", "--duration", "0.5", "--workers", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        root = html.parent
        d = json.loads((root / "renders" / "deliver.json").read_text())
        self.assertEqual((d["version"], d["source"]), (1, "fmt.html"))
        self.assertEqual([i["format"] for i in d["items"]], ["1x1", "9x16"])
        sizes = {"1x1": (1080, 1080), "9x16": (1080, 1920)}
        for item in d["items"]:
            f = item["format"]
            self.assertEqual(item["video"], f"renders/fmt_{f}.mp4")
            self.assertEqual(item["poster"], f"renders/fmt_{f}_poster.png")
            self.assertEqual(item["sheet"], f"renders/fmt_{f}_sheet.png")
            for k in ("video", "poster", "sheet"):
                self.assertTrue((root / item[k]).exists(), item[k])
            self.assertEqual((item["width"], item["height"]), sizes[f])
            self.assertEqual(png_size(root / item["poster"]), sizes[f])
            self.assertEqual(item["pix_fmt"], "yuv420p")
            self.assertIs(item["audio"], False)
            self.assertEqual(item["fps"], 30)
            self.assertAlmostEqual(item["duration"], 0.5, delta=0.05)
            self.assertEqual(item["size_bytes"], (root / item["video"]).stat().st_size)
            self.assertGreater(item["size_bytes"], 0)

    def test_deliver_native(self):
        html = fixture("golden/blank_frame.html")
        r = render(html, "--deliver", "--duration", "0.3", "--workers", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads((html.parent / "renders" / "deliver.json").read_text())
        (item,) = d["items"]
        self.assertEqual(item["format"], "native")
        self.assertEqual(item["video"], "renders/blank_frame.mp4")
        self.assertEqual(item["poster"], "renders/blank_frame_poster.png")
        self.assertEqual((item["width"], item["height"]), (320, 320))

    def test_deliver_rejects_review_modes(self):
        r = render(fixture("fmt.html"), "--deliver", "--check-only")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--deliver", r.stderr)


if __name__ == "__main__":
    unittest.main()
