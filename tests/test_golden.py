"""E0.2 golden tests: the shipped template passes every gate; each broken fixture fails
exactly the gate it was built to trip."""
import unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir


def with_kit(html):
    """Templates load kit.js from their own folder: copy it next to the copied template."""
    copy_fixture(helpers.TEMPLATES / "kit.js", html.parent)
    return html


def check_only(html):
    r = run_script("render.py", html, "--check-only")
    return r, parse_report(r.stdout)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Golden(unittest.TestCase):
    def test_template_2d_passes_gates(self):
        html = with_kit(copy_fixture(helpers.TEMPLATES / "composition.html", tmpdir()))
        r, rep = check_only(html)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(rep["gates"]["determinism"], "pass")
        self.assertTrue(rep["gates"]["loop_seam"].startswith("pass"), rep["gates"]["loop_seam"])
        self.assertEqual(rep["gates"]["page_errors"], "none")

    def test_template_2d_all_formats_pass_every_gate(self):
        html = with_kit(copy_fixture(helpers.TEMPLATES / "composition.html", tmpdir()))
        r = run_script("render.py", html, "--check-only", "--format", "16x9,9x16,1x1,4x5")
        self.assertEqual(r.returncode, 0, r.stderr)
        for fmt, rep in parse_report(r.stdout)["formats"].items():
            g = rep["gates"]
            self.assertEqual(g["determinism"], "pass", fmt)
            self.assertTrue(g["loop_seam"].startswith("pass"), (fmt, g["loop_seam"]))
            self.assertEqual(g["safe_area"], "pass", fmt)
            self.assertEqual(g["text_duration"], "pass", fmt)
            self.assertEqual(g["page_errors"], "none", fmt)

    def test_template_2d_text_gate_sees_the_glyphs(self):
        """data-text sits on the glyph row (not the always-opaque mask): a word that only
        flashes for 3 frames must trip text_duration."""
        html = with_kit(copy_fixture(helpers.TEMPLATES / "composition.html", tmpdir()))
        src = html.read_text()
        old = "const y = (1 - inP) * fontPx * 1.3 - outP * fontPx * 1.3;"
        self.assertIn(old, src)
        html.write_text(src.replace(old, "const y = (t >= 3 && t < 3.05) ? 0 : fontPx * 1.3;"))
        _, rep = check_only(html)
        self.assertTrue(rep["gates"]["text_duration"].startswith("WARN"), rep["gates"])
        self.assertIn("#titleWord", rep["gates"]["text_duration"])

    def test_template_9x16_group_centred_in_ui_safe(self):
        """Portrait: the title + shape group is centred on K.safe.ui and scaled up."""
        from playwright.sync_api import sync_playwright
        html = with_kit(copy_fixture(helpers.TEMPLATES / "composition.html", tmpdir()))
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1080, "height": 1920})
            pg.goto(html.as_uri() + "?render=1&format=9x16&w=1080&h=1920")
            pg.evaluate("window.ready")
            pg.evaluate("window.seek(4.0)")   # title up, square at its low spot
            g = pg.evaluate("""(() => { const S = K.safe.ui, a = document.getElementById('title').getBoundingClientRect(),
                c = document.getElementById('blob').getBoundingClientRect();
                return { top: a.top, bottom: c.bottom, cy: S.y + S.h / 2, h: S.h }; })()""")
            b.close()
        mid = (g["top"] + g["bottom"]) / 2
        self.assertLess(abs(mid - g["cy"]), 0.04 * g["h"], g)
        self.assertGreater(g["bottom"] - g["top"], 0.5 * g["h"], g)   # fills the tall frame

    def test_template_exposes_kit(self):
        from playwright.sync_api import sync_playwright
        html = helpers.TEMPLATES / "composition.html"
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(html.as_uri() + "?render=1")
            self.assertEqual(pg.evaluate("window.K.seg(5, 0, 10)"), 0.5)
            b.close()

    def test_broken_clock_fails_determinism(self):
        _, rep = check_only(copy_fixture("golden/broken_clock.html", tmpdir()))
        self.assertTrue(rep["gates"]["determinism"].startswith("FAIL"), rep["gates"])

    def test_broken_seam_fails_loop_seam(self):
        _, rep = check_only(copy_fixture("golden/broken_seam.html", tmpdir()))
        self.assertEqual(rep["gates"]["determinism"], "pass")
        self.assertTrue(rep["gates"]["loop_seam"].startswith("FAIL"), rep["gates"])

    def test_blank_frame_fails_check(self):
        html = copy_fixture("golden/blank_frame.html", tmpdir())
        r = run_script("render.py", html, "--skip-checks", "--workers", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        mp4 = html.parent / "renders" / "blank_frame.mp4"
        c = run_script("check.py", mp4, "--no-sheet")
        self.assertEqual(c.returncode, 1, c.stdout)
        self.assertTrue(parse_report(c.stdout)["gates"]["blank"].startswith("FAIL"))

    def test_template_three_passes_gates(self):
        d = tmpdir()
        html = with_kit(copy_fixture(helpers.TEMPLATES / "three-composition.html", d))
        v = run_script("vendor.py", d, "three", timeout=300)
        if v.returncode != 0 or not (d / "vendor" / "three.module.js").exists():
            self.skipTest("could not vendor three.js (npm/network unavailable)")
        r = run_script("render.py", html, "--check-only", "--gl")
        rep = parse_report(r.stdout)
        self.assertEqual(rep["gates"]["determinism"], "pass")
        self.assertTrue(rep["gates"]["loop_seam"].startswith("pass"), rep["gates"]["loop_seam"])

    def test_template_three_uses_shared_kit(self):
        src = (helpers.TEMPLATES / "three-composition.html").read_text()
        self.assertIn('<script src="kit.js"></script>', src)
        self.assertIn("K.init(", src)
        self.assertIn("K.FORMAT", src)

    def test_template_three_9x16(self):
        """The Three template sizes its renderer from K.FORMAT and still loops in portrait."""
        d = tmpdir()
        with_kit(copy_fixture(helpers.TEMPLATES / "three-composition.html", d))
        v = run_script("vendor.py", d, "three", timeout=300)
        if v.returncode != 0 or not (d / "vendor" / "three.module.js").exists():
            self.skipTest("could not vendor three.js (npm/network unavailable)")
        a, b, fmt, errors = three_seam(d, "?render=1&format=9x16&w=1080&h=1920", 1080, 1920)
        self.assertEqual(fmt, {"name": "9x16", "W": 1080, "H": 1920, "canvas": [1080, 1920]})
        self.assertEqual(errors, [])
        self.assertLessEqual(visible_diff(a, b), 8, "loop seam broken in 9x16")


def three_seam(d, query, w, h):
    """Serve d over http (ES modules don't load from file://), open the Three template with
    query under SwiftShader, and return (png at 0, png at D, format facts, page errors)."""
    import functools, http.server, threading
    from playwright.sync_api import sync_playwright
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(d))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                         "--ignore-gpu-blocklist", "--force-color-profile=srgb"])
            pg = br.new_page(viewport={"width": w, "height": h})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/three-composition.html{query}")
            pg.wait_for_function("window.MOTION && window.seek && window.ready")
            pg.evaluate("window.ready")
            fmt = pg.evaluate("""(() => { const c = document.querySelector('canvas');
                return { name: K.FORMAT.name, W: K.FORMAT.W, H: K.FORMAT.H, canvas: [c.width, c.height] }; })()""")
            D = pg.evaluate("MOTION.duration")
            shots = []
            for t in (0, D):
                pg.evaluate("t => window.seek(t)", t)
                shots.append(pg.screenshot())
            br.close()
    finally:
        srv.shutdown()
    return shots[0], shots[1], fmt, errors


def visible_diff(a, b):
    """Pixels that differ by more than 24/255 (render.py's loop-seam threshold)."""
    import io
    import numpy as np
    from PIL import Image
    ia = np.asarray(Image.open(io.BytesIO(a)).convert("RGB"), dtype=np.int16)
    ib = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), dtype=np.int16)
    return int((np.abs(ia - ib).max(axis=2) > 24).sum())


if __name__ == "__main__":
    unittest.main()
