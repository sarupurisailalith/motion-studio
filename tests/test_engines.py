"""v0.3 engines (E10): vendor entries for Zdog and p5 (E10.1) and the render.py false
`requestfailed` fix (E10.8). Engine templates and kits are tested in test_zdog.py,
test_p5.py and test_layers.py. Tests that need zdog / p5 vendor them at test time
(helpers.vendored) and skip when offline."""
import json, unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir


@helpers.slow
class Vendor(unittest.TestCase):
    def test_zdog_and_p5_pinned_with_licences(self):
        v = helpers.vendored("zdog", "p5")
        m = json.loads((v / "vendor.json").read_text())
        self.assertEqual(m["packages"]["zdog"], "1.1.3")
        self.assertEqual(m["packages"]["zfont"], "1.2.8")
        self.assertEqual(m["packages"]["p5"], "2.3.4")
        for f in ("zdog.dist.min.js", "zfont.min.js", "p5.min.js"):
            self.assertTrue((v / f).is_file(), f)
            self.assertIn(f, m["files"])
        self.assertIn("Zdog v1.1.3", (v / "zdog.dist.min.js").read_text()[:200])
        self.assertIn('"2.3.4"', (v / "p5.min.js").read_text()[:300])
        lic = {p.relative_to(v / "LICENSES").as_posix().lower() for p in (v / "LICENSES").rglob("*") if p.is_file()}
        self.assertIn("p5/license.txt", lic)
        self.assertIn("zfont/license", lic)
        self.assertIn("typr.js/license", lic)
        self.assertIn("zdog/package.json", lic)          # zdog ships no LICENSE file: its MIT field
        self.assertIn("LESSER GENERAL PUBLIC LICENSE",
                      next((v / "LICENSES" / "p5").iterdir()).read_text()[:400])

    def test_reproducible(self):
        """A second install of the same pins gives byte-identical files (sha256 in vendor.json)."""
        a = json.loads((helpers.vendored("zdog", "p5") / "vendor.json").read_text())["files"]
        d = tmpdir()
        r = run_script("vendor.py", d, "zdog", timeout=300)
        if r.returncode != 0:
            self.skipTest("vendor.py zdog failed (offline?)")
        b = json.loads((d / "vendor" / "vendor.json").read_text())["files"]
        self.assertEqual(a["zdog.dist.min.js"], b["zdog.dist.min.js"])
        self.assertEqual(a["zfont.min.js"], b["zfont.min.js"])

    def test_unknown_package_lists_choices(self):
        r = run_script("vendor.py", tmpdir(), "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("zdog", r.stderr)
        self.assertIn("p5", r.stderr)


class VendorDocs(unittest.TestCase):
    def test_privacy_and_notice_list_downloads(self):
        privacy = (helpers.ROOT / "PRIVACY.md").read_text()
        notice = (helpers.ROOT / "NOTICE").read_text()
        for name in ("zdog", "zfont", "p5"):
            self.assertIn(f"`{name}`", privacy)
            self.assertIn(name, notice)
        self.assertIn("LGPL-2.1", notice)

    def test_no_engine_library_in_the_repo(self):
        """p5 (LGPL) and Zdog are downloaded per project, never committed to the plugin."""
        for p in helpers.ROOT.rglob("*.js"):
            if ".git" in p.parts:
                continue
            head = p.read_text(errors="ignore")[:400]
            self.assertNotIn("Zdog v1.1.3", head, p)
            self.assertNotIn('r="2.3.4"', head, p)
            self.assertNotIn(p.name, ("p5.min.js", "zdog.dist.min.js", "zfont.min.js"), p)


class RendererDocs(unittest.TestCase):
    """E10.14: the brief's <renderer> field picks the template; docs list every renderer."""
    RENDERERS = {"2d": "composition.html", "zdog": "zdog-composition.html", "p5": "p5-composition.html",
                 "three": "three-composition.html", "layered": "layered-composition.html"}

    def test_brief_template_has_renderer_field(self):
        brief = (helpers.SKILL / "references" / "brief-template.md").read_text()
        self.assertIn("<renderer>", brief)
        for r in self.RENDERERS:
            self.assertRegex(brief, rf"\n\s+{r}\s", r)

    def test_skill_and_motion_map_renderers_to_templates(self):
        skill = (helpers.SKILL / "SKILL.md").read_text()
        motion = (helpers.ROOT / "commands" / "motion.md").read_text()
        for r, tpl in self.RENDERERS.items():
            self.assertTrue((helpers.TEMPLATES / tpl).exists(), tpl)
            self.assertIn(f"`{r}`", skill)
            self.assertIn(tpl, skill)
            self.assertIn(tpl, motion)
        self.assertIn("catalog.py search", skill)
        self.assertIn("catalog.py search", motion)


def refetch(missing=False):
    d = tmpdir()
    html = copy_fixture("engines/refetch.html", d)
    copy_fixture("engines/data.txt", d)
    if missing:
        html.write_text(html.read_text().replace("const MISSING = false;", "const MISSING = true;"))
    return html


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class RequestFailed(unittest.TestCase):
    """E10.8: a cancelled request for a URL that then loads is not a page error."""

    def test_cancelled_then_loaded_is_not_an_error(self):
        r = run_script("render.py", refetch(), "--check-only")
        self.assertEqual(parse_report(r.stdout)["gates"]["page_errors"], "none")
        self.assertNotIn("Traceback", r.stderr)   # the local server ignores the cancelled socket

    def test_genuinely_missing_asset_still_fails(self):
        r = run_script("render.py", refetch(missing=True), "--check-only")
        errs = parse_report(r.stdout)["gates"]["page_errors"]
        self.assertIsInstance(errs, list)
        self.assertTrue(any("gone.txt" in e for e in errs), errs)
        self.assertFalse(any("data.txt" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
