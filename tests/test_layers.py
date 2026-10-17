"""Layered multi-engine compositions (E10.12) and gate proxies for canvas text (E10.13)."""
import shutil, unittest

import helpers
from helpers import parse_report, run_script, tmpdir
from test_kit import Browser

FIX = helpers.FIXTURES / "engines"
CAT = helpers.SKILL / "catalog"


def layered_project():
    d = tmpdir()
    helpers.with_vendor(d, "zdog", "p5")
    for f in ("kit.js", "kit-p5.js", "kit-zdog.js", "kit-layers.js", "layered-composition.html"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    (d / "models").mkdir()
    for m in ("pip", "pine", "round-tree", "rock", "ground-block"):
        shutil.copy2(CAT / "models" / f"{m}.js", d / "models" / f"{m}.js")
    return d / "layered-composition.html"


def caption_project(outside=False):
    d = tmpdir()
    for f in ("kit.js", "kit-layers.js"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    html = d / "canvas_caption.html"
    src = (FIX / "canvas_caption.html").read_text()
    html.write_text(src.replace("const OUTSIDE = false;", f"const OUTSIDE = {'true' if outside else 'false'};"))
    return html


def gates(html, *args):
    return parse_report(run_script("render.py", html, "--check-only", *args).stdout)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Layered(unittest.TestCase):
    def test_p5_sky_behind_zdog_forest_passes_in_two_formats(self):
        rep = gates(layered_project(), "--format", "16x9,9x16")
        for fmt, f in rep["formats"].items():
            g = f["gates"]
            self.assertEqual(g["determinism"], "pass", (fmt, g))
            self.assertTrue(g["loop_seam"].startswith("pass"), (fmt, g))
            self.assertEqual(g["safe_area"], "pass", (fmt, g))
            self.assertEqual(g["text_duration"], "pass", (fmt, g))
            self.assertEqual(g["page_errors"], "none", (fmt, g))


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Proxy(unittest.TestCase):
    """E10.13 acceptance: a canvas-drawn caption outside K.safe.ui fails safe_area; inside passes."""

    def test_inside_passes(self):
        g = gates(caption_project(), "--format", "9x16")["formats"]["9x16"]["gates"]
        self.assertEqual(g["safe_area"], "pass", g)
        self.assertEqual(g["text_duration"], "pass", g)
        self.assertEqual(g["determinism"], "pass", g)

    def test_outside_fails(self):
        g = gates(caption_project(outside=True), "--format", "9x16")["formats"]["9x16"]["gates"]
        self.assertTrue(g["safe_area"].startswith("FAIL"), g)
        self.assertIn("#canvas-caption", g["safe_area"])
        self.assertIn("bottom", g["safe_area"])


@helpers.slow
@helpers.needs_chromium
class LayersKit(Browser):
    def test_stacking_order_blend_and_box(self):
        page, errors = self.open(caption_project(), viewport={"width": 1080, "height": 1920})
        r = page.evaluate("""(() => {
          const a = document.createElement('canvas'), b = document.createElement('div');
          const s = K.layers([{ name: 'back', el: a, seek: () => {} }, { name: 'front', el: b, blend: 'multiply', seek: () => {} }],
                             { install: false });
          return s.ready.then(() => [a.style.zIndex, b.style.zIndex, b.style.mixBlendMode, b.dataset.layer, a.style.width]); })()""")
        self.assertEqual(r, ["1", "2", "multiply", "front", "1080px"])
        self.assertEqual(errors, [])

    def test_layers_validate(self):
        page, _ = self.open(caption_project(), viewport={"width": 1080, "height": 1920})
        msg = page.evaluate("(() => { try { K.layers([{ name: 'x' }], { install: false }); } catch (e) { return e.message; } })()")
        self.assertIn("seek", msg)
        msg = page.evaluate("""(() => { try { K.layers([{ name: 'x', seek(){} }, { name: 'x', seek(){} }], { install: false }); }
          catch (e) { return e.message; } })()""")
        self.assertIn("unique", msg)

    def test_proxy_tracks_box_and_alpha(self):
        page, _ = self.open(caption_project(), viewport={"width": 1080, "height": 1920})
        r = page.evaluate("""(() => { const p = K.proxy('pp', { x: 10, y: 20, w: 30, h: 40 });
          const a = [p.el.style.left, p.el.style.top, p.el.style.width, p.el.style.height, p.el.style.opacity,
                     p.el.hasAttribute('data-safe'), p.el.hasAttribute('data-text'), p.el.textContent];
          p.set({ x: 0, y: 0, w: 1, h: 1 }, 0.5); a.push(p.el.style.opacity); p.hide(); a.push(p.el.style.opacity);
          return a; })()""")
        self.assertEqual(r, ["10px", "20px", "30px", "40px", "1", True, True, "", "0.5", "0"])


if __name__ == "__main__":
    unittest.main()
