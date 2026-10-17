"""E10.9: every engine recipe in templates/recipes/ passes the gates as shipped and is linked
from genres.md. p5 / Zdog are vendored at test time; tests skip cleanly when offline."""
import shutil, unittest

import helpers
from helpers import parse_report, run_script, tmpdir

RECIPES = helpers.TEMPLATES / "recipes"
CAT = helpers.SKILL / "catalog"


def recipe_project(name):
    d = tmpdir()
    engine = "zdog" if name.startswith("zdog") else "p5"
    helpers.with_vendor(d, engine)
    for f in ("kit.js", "kit-p5.js", "kit-zdog.js", "kit-layers.js"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    if engine == "zdog":
        (d / "models").mkdir()
        for m in ("pip", "chart-bars"):
            shutil.copy2(CAT / "models" / f"{m}.js", d / "models" / f"{m}.js")
    if "glyph" in name:
        ttf = helpers.find_ttf()
        if not ttf:
            raise unittest.SkipTest("no local .ttf font for the glyph recipe")
        (d / "assets").mkdir()
        shutil.copyfile(ttf, d / "assets" / "display.ttf")
    shutil.copy2(RECIPES / name, d / name)
    return d / name


class RecipeDocs(unittest.TestCase):
    def test_genres_links_every_recipe(self):
        genres = (helpers.SKILL / "references" / "genres.md").read_text()
        names = sorted(p.name for p in RECIPES.glob("*.html"))
        self.assertGreaterEqual(len(names), 5)
        for n in names:
            self.assertIn(f"recipes/{n}", genres)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Recipes(unittest.TestCase):
    def test_every_recipe_passes_the_gates(self):
        for p in sorted(RECIPES.glob("*.html")):
            with self.subTest(recipe=p.name):
                html = recipe_project(p.name)
                g = parse_report(run_script("render.py", html, "--check-only").stdout)["gates"]
                self.assertEqual(g["determinism"], "pass", g)
                self.assertTrue(g["loop_seam"].startswith("pass"), g)
                self.assertTrue(g["safe_area"].startswith("pass"), g)
                self.assertTrue(g["text_duration"].startswith("pass"), g)
                self.assertEqual(g["page_errors"], "none", g)

    def test_beat_pulse_follows_beats_js(self):
        html = recipe_project("p5-beat-pulse.html")
        shutil.copy2(helpers.FIXTURES / "kit" / "beats.js", html.parent / "beats.js")
        html.write_text(html.read_text().replace('<script src="kit.js">', '<script src="beats.js"></script>\n<script src="kit.js">'))
        r = run_script("render.py", html, "--hits")
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        hits = json.loads((html.parent / "renders" / "p5-beat-pulse_hits.json").read_text())["hits"]
        self.assertTrue(hits)
        self.assertTrue(all(h["label"] == "downbeat" for h in hits))


if __name__ == "__main__":
    unittest.main()
