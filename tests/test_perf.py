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


def greys(mp4):
    """Mean grey level of each decoded frame."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-vf", "scale=1:1:flags=area", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, 3)[:, 0].astype(int).tolist()


class WorkersDefault(unittest.TestCase):
    def test_default_is_cpu_count_max_6(self):
        import os, sys
        sys.path.insert(0, str(helpers.SCRIPTS))
        import render as R
        self.assertEqual(R.build_parser().parse_args(["x.html"]).workers, max(1, min(6, os.cpu_count() or 2)))


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Workers(unittest.TestCase):
    """E8.3: worker segments start on frame boundaries; no frame is duplicated or lost."""

    def test_every_frame_once_in_order(self):
        html = fixture("frames.html")
        for w in (1, 3, 6):  # 6 asks for more workers than seconds: clamped to 3
            with self.subTest(workers=w):
                mp4 = html.parent / f"w{w}.mp4"
                r = render(html, "--skip-checks", "--workers", w, "-o", mp4)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(f"with {min(w, 3)} worker(s)", r.stdout)
                g = greys(mp4)
                self.assertEqual(len(g), 72)
                self.assertEqual([round((v - 10) / 3) for v in g], list(range(72)))

    def test_gate_catches_a_wrong_count(self):
        import sys
        sys.path.insert(0, str(helpers.SCRIPTS))
        import render as R
        mp4 = tmpdir() / "ten.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
                        "-pix_fmt", "yuv420p", str(mp4)], check=True)
        self.assertEqual(R.count_frames(mp4), 10)
        R.gate_frame_count(mp4, 10, None)
        with self.assertRaises(SystemExit) as e:
            R.gate_frame_count(mp4, 11, None)
        self.assertIn("has 10 frames, expected 11", str(e.exception))
        R.gate_frame_count(mp4, 11, "track.wav")  # -shortest with a short track: a warning only

    def test_frame_count_gate_with_subframes(self):
        html = fixture("frames.html")
        r = render(html, "--skip-checks", "--workers", "3", "--subframes", "3", "--shutter", "0.01")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(greys(html.parent / "renders" / "frames.mp4")), 72)


if __name__ == "__main__":
    unittest.main()
