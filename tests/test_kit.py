"""W1-B kit tests: shared kit.js, formats (E2.2), preview switcher (E2.3), beat time (E7.1),
hits (E1.3) and clip helpers (E3.7). Each test drives the real templates in Chromium."""
import shutil
import unittest
from pathlib import Path

import helpers
from helpers import tmpdir

KIT = helpers.TEMPLATES / "kit.js"
COMP = helpers.TEMPLATES / "composition.html"
KIT_FIX = helpers.FIXTURES / "kit"

# K.spring(0.1) computed with the v0.1 inline kit, before the move to kit.js
SPRING_0_1 = 0.6097155118230713


def project(template=COMP, beats=False, d=None):
    """Copy a template + kit.js (and optionally the beats fixture) into a temp dir."""
    d = Path(d or tmpdir())
    html = d / template.name
    shutil.copy2(template, html)
    shutil.copy2(KIT, d / "kit.js")
    if beats:
        shutil.copy2(KIT_FIX / "beats.js", d / "beats.js")
        src = html.read_text()
        tag = '<script src="kit.js"></script>'
        assert tag in src, "template must load kit.js"
        html.write_text(src.replace(tag, '<script src="beats.js"></script>\n' + tag, 1))
    return html


class Browser(unittest.TestCase):
    """One Chromium for the whole class; open() gives a fresh page per call."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def open(self, html, query="?render=1", viewport=None):
        """Open html (a Path) with a query string; returns (page, errors)."""
        ctx = self.browser.new_context(viewport=viewport or {"width": 1080, "height": 1080})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(Path(html).as_uri() + query)
        page.wait_for_function("window.MOTION && window.seek && window.ready")
        page.evaluate("window.ready")
        return page, errors


@helpers.slow
@helpers.needs_chromium
class Extract(Browser):
    def test_kit_is_external(self):
        self.assertTrue(KIT.exists(), "templates/kit.js missing")
        self.assertNotIn("const K = (() =>", COMP.read_text())
        self.assertIn('<script src="kit.js"></script>', COMP.read_text())

    def test_kit_values_unchanged(self):
        page, errors = self.open(project())
        self.assertEqual(page.evaluate("window.K.spring(0.1)"), SPRING_0_1)
        self.assertEqual(page.evaluate("K.rand(3, 7)"), 0.20799961290322244)
        self.assertEqual(page.evaluate("K.bezier(.16,1,.3,1)(0.3)"), 0.8771741996361885)
        self.assertEqual(errors, [])


FORMATS = {"16x9": (1920, 1080), "9x16": (1080, 1920), "1x1": (1080, 1080), "4x5": (1080, 1350)}


def fmt_query(name):
    w, h = FORMATS[name]
    return f"?render=1&format={name}&w={w}&h={h}"


SAFE_BOXES = """() => {
  const s = document.getElementById('stage').getBoundingClientRect();
  return [...document.querySelectorAll('[data-safe]')].map(el => {
    const r = el.getBoundingClientRect();
    return { id: el.id, x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
  });
}"""


@helpers.slow
@helpers.needs_chromium
class Formats(Browser):
    def test_native_without_params(self):
        page, _ = self.open(project())
        f = page.evaluate("K.FORMAT")
        self.assertEqual(f["name"], "native")
        self.assertEqual((f["W"], f["H"]), (1080, 1080))
        self.assertEqual(page.evaluate("K.safe.title"), {"x": 54, "y": 54, "w": 972, "h": 972})

    def test_9x16_params(self):
        page, errors = self.open(project(), fmt_query("9x16"), {"width": 1080, "height": 1920})
        self.assertEqual(page.evaluate("[MOTION.width, MOTION.height]"), [1080, 1920])
        self.assertEqual(page.evaluate("K.FORMAT"),
                         {"name": "9x16", "W": 1080, "H": 1920, "isPortrait": True, "aspect": 0.5625})
        self.assertEqual(page.evaluate("K.safe.ui"), {"x": 65, "y": 230, "w": 864, "h": 1267})
        box = page.evaluate("(() => { const r = stage.getBoundingClientRect(); return [r.width, r.height]; })()")
        self.assertEqual(box, [1080, 1920])
        self.assertEqual(errors, [])

    def test_4x5_safe_ui(self):
        page, _ = self.open(project(), fmt_query("4x5"))
        self.assertEqual(page.evaluate("K.safe.ui"), {"x": 54, "y": 108, "w": 972, "h": 1080})

    def test_pick(self):
        page, _ = self.open(project(), fmt_query("9x16"))
        self.assertEqual(page.evaluate("K.pick({'9x16': 1, default: 2})"), 1)
        page, _ = self.open(project(), fmt_query("16x9"))
        self.assertEqual(page.evaluate("K.pick({'9x16': 1, default: 2})"), 2)
        self.assertTrue(page.evaluate("(() => { try { K.pick({'1x1': 1}); return false; } catch (e) { return true; } })()"))

    def test_demo_in_every_format(self):
        """Loop seam holds and every [data-safe] element stays inside K.safe.ui."""
        for name, (w, h) in FORMATS.items():
            with self.subTest(format=name):
                page, errors = self.open(project(), fmt_query(name), {"width": w, "height": h})
                D = page.evaluate("MOTION.duration")
                shots = []
                for t in (0, D):
                    page.evaluate("t => window.seek(t)", t)
                    shots.append(page.screenshot(clip={"x": 0, "y": 0, "width": w, "height": h}))
                self.assertEqual(shots[0], shots[1], "loop seam broken")
                ui = page.evaluate("K.safe.ui")
                self.assertGreaterEqual(len(page.evaluate(SAFE_BOXES)), 2)
                for i in range(25):
                    t = D * i / 24
                    page.evaluate("t => window.seek(t)", t)
                    for b in page.evaluate(SAFE_BOXES):
                        msg = f"{b['id']} at t={t:.2f}: {b} not inside {ui}"
                        self.assertGreaterEqual(b["x"], ui["x"] - 0.5, msg)
                        self.assertGreaterEqual(b["y"], ui["y"] - 0.5, msg)
                        self.assertLessEqual(b["x"] + b["w"], ui["x"] + ui["w"] + 0.5, msg)
                        self.assertLessEqual(b["y"] + b["h"], ui["y"] + ui["h"] + 0.5, msg)
                self.assertEqual(errors, [])


OVERLAY_RECTS = """() => [...document.querySelectorAll('#safe-overlay rect')].map(r => ({
  name: r.dataset.rect, x: +r.getAttribute('x'), y: +r.getAttribute('y'),
  w: +r.getAttribute('width'), h: +r.getAttribute('height') }))"""


@helpers.slow
@helpers.needs_chromium
class Preview(Browser):
    def test_no_preview_ui_in_render_mode(self):
        page, _ = self.open(project(), fmt_query("9x16"))
        self.assertEqual(page.evaluate("!!document.getElementById('preview-ui')"), False)
        self.assertEqual(page.evaluate("!!document.getElementById('safe-overlay')"), False)

    def test_g_toggles_safe_overlay(self):
        page, errors = self.open(project(), "?format=9x16&w=1080&h=1920&t=1")
        disp = "getComputedStyle(document.getElementById('safe-overlay')).display"
        self.assertEqual(page.evaluate(disp), "none")
        page.keyboard.press("g")
        self.assertEqual(page.evaluate(disp), "block")
        rects = {r.pop("name"): r for r in page.evaluate(OVERLAY_RECTS)}
        self.assertEqual(rects, page.evaluate("K.safe"))
        page.keyboard.press("g")
        self.assertEqual(page.evaluate(disp), "none")
        self.assertIn("9x16", page.inner_text("#preview-ui"))
        self.assertEqual(errors, [])

    def test_f_cycles_formats(self):
        html = project()
        page, _ = self.open(html, "?t=1")
        self.assertIn("native", page.inner_text("#preview-ui"))
        expected = ["16x9", "9x16", "1x1", "4x5"]
        for name in expected:
            with page.expect_navigation():
                page.keyboard.press("f")
            w, h = FORMATS[name]
            self.assertEqual(page.evaluate("location.search"), f"?t=1&format={name}&w={w}&h={h}")
            page.wait_for_function("window.ready")
        with page.expect_navigation():
            page.keyboard.press("f")
        self.assertEqual(page.evaluate("location.search"), "?t=1")


BEATS_ERROR = 'K.T/K.U need beats.js — run beats.py and add <script src="beats.js"> before the kit'

CATCH = "(() => { try { %s; return null; } catch (e) { return e.message; } })()"


@helpers.slow
@helpers.needs_chromium
class Beats(Browser):
    def test_beat_conversions(self):
        page, errors = self.open(project(beats=True))
        self.assertEqual(page.evaluate("K.BEATS.bpm"), 120)
        self.assertEqual(page.evaluate("K.T(4)"), 2.1)
        self.assertEqual(page.evaluate("K.U(2.1)"), 4)
        self.assertTrue(page.evaluate("K.at === K.T"))
        self.assertEqual(errors, [])

    def test_helpers_accept_beat_strings(self):
        page, _ = self.open(project(beats=True))
        self.assertEqual(page.evaluate("K.track([['0b', 0], ['4b', 10]], 1.1, K.ease.linear)"), 5)
        self.assertEqual(page.evaluate("K.springTrack([[0, 0], ['4b', 1]], 2.0)"), 0)
        self.assertGreater(page.evaluate("K.springTrack([[0, 0], ['4b', 1]], 2.2)"), 0)
        self.assertAlmostEqual(page.evaluate("K.stagger(2.1, '2b', 2, '1b')"), 0.0)

    def test_missing_beats_throws_contract_error(self):
        page, errors = self.open(project())
        self.assertIsNone(page.evaluate("K.BEATS"))
        self.assertEqual(page.evaluate(CATCH % "K.T(1)"), BEATS_ERROR)
        self.assertEqual(page.evaluate(CATCH % "K.U(1)"), BEATS_ERROR)
        self.assertEqual(errors, [])   # the template must not load beats.js by default


HITS = "MOTION.hits = [[2,'b','click'],['4b','a','thud',{gain:-3}],[1,'c',null]]"


@helpers.slow
@helpers.needs_chromium
class Hits(Browser):
    def test_resolve_sorted_with_beats(self):
        page, _ = self.open(project(beats=True))
        self.assertEqual(page.evaluate(f"{HITS}; K.resolveHits()"), [
            {"t": 1, "label": "c", "sfx": None, "opts": {}},
            {"t": 2, "label": "b", "sfx": "click", "opts": {}},
            {"t": 2.1, "label": "a", "sfx": "thud", "opts": {"gain": -3}},
        ])

    def test_beat_string_without_beats_throws(self):
        page, _ = self.open(project())
        self.assertEqual(page.evaluate(CATCH % f"{HITS}; K.resolveHits()"), BEATS_ERROR)

    def test_no_hits_is_empty(self):
        page, _ = self.open(project())
        self.assertEqual(page.evaluate("delete MOTION.hits; K.resolveHits()"), [])

    def test_template_demo_has_hits(self):
        page, _ = self.open(project())
        hits = page.evaluate("K.resolveHits()")
        self.assertGreaterEqual(len(hits), 3)
        D = page.evaluate("MOTION.duration")
        for h in hits:
            self.assertTrue(0 <= h["t"] < D, h)


def clip_project():
    """clip.html + kit.js + a 10-frame JPEG sequence (frame i = (i*25, 0, 255-i*25)) + assets.js."""
    import json
    from PIL import Image
    d = tmpdir()
    shutil.copy2(KIT_FIX / "clip.html", d / "clip.html")
    shutil.copy2(KIT, d / "kit.js")
    frames = d / "assets" / "video" / "c"
    frames.mkdir(parents=True)
    for i in range(10):
        Image.new("RGB", (64, 64), (i * 25, 0, 255 - i * 25)).save(frames / f"{i:05d}.jpg", quality=95)
    asset = {"id": "c", "kind": "video", "path": "assets/video/c/", "source": "local", "orig": "/x/c.mp4",
             "w": 64, "h": 64, "fps": 10, "frame_count": 10, "duration": 1.0,
             "pattern": "assets/video/c/%05d.jpg"}
    (d / "assets.js").write_text("window.ASSETS = " + json.dumps({"version": 1, "assets": [asset]}) + ";\n")
    return d / "clip.html"


@helpers.slow
@helpers.needs_chromium
class Clips(Browser):
    def centre(self, page, t):
        import io
        from PIL import Image
        page.evaluate("t => window.seek(t)", t)
        png = page.screenshot(clip={"x": 0, "y": 0, "width": 200, "height": 200})
        return Image.open(io.BytesIO(png)).convert("RGB").getpixel((100, 100))

    def assertColour(self, got, want, tol=6):
        for g, w in zip(got, want):
            self.assertLessEqual(abs(g - w), tol, f"{got} != {want}")

    def test_frame_lookup(self):
        page, errors = self.open(clip_project(), "?render=1", {"width": 200, "height": 200})
        self.assertColour(self.centre(page, 0.35), (75, 0, 180))      # frame 3
        self.assertColour(self.centre(page, 5.0), (225, 0, 30))       # past the end -> last frame
        self.assertColour(self.centre(page, 0.0), (0, 0, 255))        # frame 0
        self.assertEqual(page.evaluate("K.clipFrame(clip, 0.35).src.endsWith('00003.jpg')"), True)
        self.assertEqual(errors, [])

    def test_out_of_order_seeks_identical(self):
        page, _ = self.open(clip_project(), "?render=1", {"width": 200, "height": 200})
        ts = [0.05, 0.95, 0.35, 0.6, 0.05, 0.35]
        seen = {}
        for t in ts:
            px = self.centre(page, t)
            self.assertEqual(seen.setdefault(t, px), px, f"t={t}")

    def test_clip_comp_passes_determinism_gate(self):
        r = helpers.run_script("render.py", clip_project(), "--check-only")
        rep = helpers.parse_report(r.stdout)
        self.assertEqual(rep["gates"]["determinism"], "pass", rep["gates"])
        self.assertEqual(rep["gates"]["page_errors"], "none", rep["gates"])


if __name__ == "__main__":
    unittest.main()
