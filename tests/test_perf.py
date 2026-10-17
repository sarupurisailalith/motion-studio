"""E8: render speed without changing the picture.

Every fast path is checked against the v0.2 path (--capture screenshot): the decoded frames of the
two MP4s (ffmpeg framemd5) must be identical, so a fast path can only change how long a render
takes. Fixtures in tests/fixtures/perf/."""
import subprocess, unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir


def fixture(name):
    return copy_fixture("perf/" + name, tmpdir())


def render(html, *args):
    return run_script("render.py", html, *args)


def frames(mp4):
    """One md5 per decoded video frame."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-map", "0:v", "-f", "framemd5", "-"],
                       capture_output=True, text=True, check=True)
    return [line.rsplit(",", 1)[1].strip() for line in r.stdout.splitlines() if line and not line.startswith("#")]


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Capture(unittest.TestCase):
    """E8.1 canvas fast path and E8.2 CDP capture: same frames as --capture screenshot."""

    def both(self, html, *args):
        """Render with the default capture and with --capture screenshot; -> (stdout, frames, frames)."""
        out = []
        for mode in ("auto", "screenshot"):
            mp4 = html.parent / f"{html.stem}_{mode}.mp4"
            r = render(html, "--skip-checks", "--workers", "1", "--capture", mode, "-o", mp4, *args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out.append((r.stdout, frames(mp4)))
        self.assertEqual(len(out[0][1]), len(out[1][1]))
        return out[0][0], out[0][1], out[1][1]

    def test_canvas_fast_path_same_frames(self):
        log, fast, old = self.both(fixture("canvas2d.html"))
        self.assertIn("capture: canvas fast path", log)
        self.assertEqual(fast, old)

    def test_canvas_fast_path_with_subframes(self):
        log, fast, old = self.both(fixture("canvas2d.html"), "--subframes", "3", "--duration", "0.5")
        self.assertIn("capture: canvas fast path", log)
        self.assertEqual(fast, old)

    def test_pages_that_dont_qualify_fall_back(self):
        for name, why in [("canvas_overlay.html", "another element renders (<div>)"),
                          ("canvas_late.html", "canvas pixels differ from the screenshot"),
                          ("canvas_alpha.html", "canvas pixels differ from the screenshot")]:
            with self.subTest(name):
                log, fast, old = self.both(fixture(name))
                self.assertIn("canvas fast path off: " + why, log)
                self.assertEqual(fast, old)

    def test_page_that_stops_qualifying_mid_render(self):
        log, fast, old = self.both(fixture("canvas_fade.html"))
        self.assertIn("leaves the canvas fast path (the page stopped qualifying at t=0.533)", log)
        self.assertEqual(fast, old)

    def test_dom_page_cdp_same_frames(self):
        html = copy_fixture("golden/blank_frame.html", tmpdir())
        log, fast, old = self.both(html)
        self.assertIn("capture: CDP screenshots (canvas fast path off: 0 <canvas> elements)", log)
        self.assertEqual(fast, old)

    def test_css_animation_uses_page_screenshot(self):
        log, fast, old = self.both(fixture("css_anim.html"))
        self.assertEqual(fast, old)

    def test_cdp_only(self):
        html = fixture("canvas2d.html")
        r = render(html, "--skip-checks", "--workers", "1", "--capture", "cdp", "-o", html.parent / "cdp.mp4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("capture: CDP screenshots\n", r.stdout)
        ref = html.parent / "ref.mp4"
        self.assertEqual(render(html, "--skip-checks", "--workers", "1", "--capture", "screenshot", "-o", ref).returncode, 0)
        self.assertEqual(frames(html.parent / "cdp.mp4"), frames(ref))

    def test_stills_byte_identical(self):
        """Saved PNGs (stills, posters) are the exact v0.2 bytes, not just the same pixels."""
        d = tmpdir()
        html = copy_fixture(helpers.TEMPLATES / "composition.html", d)
        copy_fixture(helpers.TEMPLATES / "kit.js", d)
        got = {}
        for mode in ("auto", "screenshot"):
            r = render(html, "--stills", "0.5,2.25", "--poster", "--capture", mode)
            self.assertEqual(r.returncode, 0, r.stderr)
            got[mode] = {p.name: p.read_bytes() for p in sorted((d / "renders").glob("*.png"))}
        self.assertEqual(len(got["auto"]), 3)
        self.assertEqual(got["auto"], got["screenshot"])

    def test_gates_unchanged(self):
        for name, gate in [("golden/broken_clock.html", "determinism"), ("golden/broken_seam.html", "loop_seam")]:
            with self.subTest(name):
                html = copy_fixture(name, tmpdir())
                reps = []
                for mode in ("auto", "screenshot"):
                    r = render(html, "--check-only", "--capture", mode)
                    reps.append(parse_report(r.stdout)["gates"][gate])
                self.assertTrue(reps[0].startswith("FAIL"), reps[0])
                self.assertTrue(reps[1].startswith("FAIL"), reps[1])
                if gate == "loop_seam":  # broken_clock's diff box depends on wall-clock timing
                    self.assertEqual(reps[0], reps[1])

    def test_three_template_canvas_fast_path(self):
        d = tmpdir()
        html = copy_fixture(helpers.TEMPLATES / "three-composition.html", d)
        copy_fixture(helpers.TEMPLATES / "kit.js", d)
        v = run_script("vendor.py", d, "three", timeout=300)
        if v.returncode != 0 or not (d / "vendor" / "three.module.js").exists():
            self.skipTest("could not vendor three.js (npm/network unavailable)")
        log, fast, old = self.both(html, "--gl", "--duration", "1")
        self.assertIn("capture: canvas fast path", log)
        self.assertEqual(fast, old)


if __name__ == "__main__":
    unittest.main()
