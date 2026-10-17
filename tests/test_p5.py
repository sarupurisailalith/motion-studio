"""p5.js engine (E10.6, E10.7): the template, the kit (K.sketch, K.loopNoise, K.presim) and the
determinism rules. p5 (LGPL-2.1) is vendored at test time; tests skip cleanly when offline."""
import shutil, unittest

import helpers
from helpers import parse_report, run_script, tmpdir
from test_kit import Browser

FIX = helpers.FIXTURES / "engines"
FORMATS = "16x9,9x16,1x1,4x5"


def p5_project(html_src, name=None, font=False):
    d = tmpdir()
    helpers.with_vendor(d, "p5")
    for f in ("kit.js", "kit-p5.js"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    if font:
        ttf = helpers.find_ttf()
        if not ttf:
            raise unittest.SkipTest("no local .ttf font for loadFont")
        (d / "assets").mkdir()
        shutil.copyfile(ttf, d / "assets" / "display.ttf")
    html = d / (name or html_src.name)
    shutil.copy2(html_src, html)
    return html


def gates(html, *args):
    r = run_script("render.py", html, "--check-only", *args)
    return parse_report(r.stdout)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class P5Template(unittest.TestCase):
    def test_demo_passes_every_gate_in_all_formats(self):
        rep = gates(p5_project(helpers.TEMPLATES / "p5-composition.html"), "--format", FORMATS)
        for fmt, f in rep["formats"].items():
            g = f["gates"]
            self.assertEqual(g["determinism"], "pass", (fmt, g))
            self.assertTrue(g["loop_seam"].startswith("pass"), (fmt, g))
            self.assertEqual(g["safe_area"], "pass", (fmt, g))
            self.assertEqual(g["text_duration"], "pass", (fmt, g))
            self.assertEqual(g["page_errors"], "none", (fmt, g))

    def test_template_follows_the_rules(self):
        src = (helpers.TEMPLATES / "p5-composition.html").read_text()
        scene = src.split("COMPOSITION SETTINGS")[1].split("RUNTIME (shared")[0]
        for bad in ("frameCount", "millis(", "deltaTime", "Math.random", "preload", "loop()"):
            self.assertNotIn(bad, scene, bad)
        self.assertIn("K.sketch(", scene)
        self.assertIn("K.loopNoise(", scene)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class P5Rules(unittest.TestCase):
    """E10.7 acceptance: the spike's naive variant fails the gates, the rule-following one passes.
    The fixture also loads a font with loadFont (E10.8: its cancelled first fetch is no error)."""

    def test_rule_following_sketch_passes(self):
        g = gates(p5_project(FIX / "p5_rules.html", font=True))["gates"]
        self.assertEqual(g["determinism"], "pass", g)
        self.assertTrue(g["loop_seam"].startswith("pass"), g)
        self.assertEqual(g["page_errors"], "none", g)

    def test_naive_sketch_fails(self):
        html = p5_project(FIX / "p5_rules.html", font=True)
        html.write_text(html.read_text().replace("const NAIVE = false;", "const NAIVE = true;"))
        g = gates(html)["gates"]
        self.assertTrue(g["determinism"].startswith("FAIL"), g)
        self.assertTrue(g["loop_seam"].startswith("FAIL"), g)


@helpers.slow
@helpers.needs_chromium
class P5Kit(Browser):
    def page(self):
        return self.open(p5_project(helpers.TEMPLATES / "p5-composition.html"), viewport={"width": 1080, "height": 1080})

    def test_loop_noise_is_periodic(self):
        page, _ = self.page()
        a, b, c = page.evaluate("[K.loopNoise(0, 6, 0.6), K.loopNoise(6, 6, 0.6), K.loopNoise(1.5, 6, 0.6)]")
        self.assertAlmostEqual(a["x"], b["x"], places=12)
        self.assertAlmostEqual(a["y"], b["y"], places=12)
        self.assertAlmostEqual(c["x"], 0, places=12)
        self.assertAlmostEqual(c["y"], 0.6, places=12)

    def test_presim_indexes_fixed_steps(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          let calls = 0;
          const sim = K.presim((s, i, dt) => (calls++, { x: s.x + s.v * dt, v: s.v + 10 * dt }), 1 / 30, 2, { x: 0, v: 0 }, { warmup: 1 });
          return [calls, sim.states.length, sim.at(0).x, sim.at(1).x === sim.at(1).x, sim.at(5) === sim.states[60],
                  sim.at(0.5) === sim.at(0.5), sim.at(0.999) === sim.states[29]]; })()""")
        self.assertEqual(r[0], 30 + 60)      # warm-up + D, once
        self.assertEqual(r[1], 61)
        self.assertGreater(r[2], 0)          # t = 0 is after the warm-up, not the cold start
        self.assertEqual(r[3:], [True, True, True, True])

    def test_sketch_reseeds_random(self):
        page, errors = self.page()
        same = page.evaluate("""(async () => {
          const vals = [];
          const s = K.sketch({ width: 10, height: 10, seed: 3, draw: (p, t) => vals.push(p.random()) });
          await s.seek(1); await s.seek(2); await s.seek(1);
          return vals; })()""")
        self.assertEqual(len(same), 3)
        self.assertEqual(same[0], same[1])
        self.assertEqual(same[0], same[2])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
