"""render.py: the contrast gate (E5.6), --thorough (D.9), --sheet stills folder (D.2) and the
--deliver phone sheet (D.4)."""
import json, sys, unittest

import numpy as np

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir

sys.path.insert(0, str(helpers.SCRIPTS))


class ContrastUnits(unittest.TestCase):
    def test_wcag_ratios(self):
        import render
        white = np.array([[255, 255, 255]] * 4)
        self.assertAlmostEqual(render.text_contrast([0, 0, 0], 1.0, white), 21.0, places=2)
        self.assertAlmostEqual(render.text_contrast([0x77, 0x77, 0x77], 1.0, white), 4.48, places=2)
        # half-transparent black on white is mid grey, well under black's 21:1
        self.assertLess(render.text_contrast([0, 0, 0], 0.5, white), 5.0)

    def test_percentile_of_the_area(self):
        import render
        # 85 % white, 15 % black behind black text: the 10th percentile lands on black (1:1)
        bg = np.array([[255, 255, 255]] * 85 + [[0, 0, 0]] * 15)
        self.assertAlmostEqual(render.text_contrast([0, 0, 0], 1.0, bg), 1.0)
        bg = np.array([[255, 255, 255]] * 95 + [[0, 0, 0]] * 5)
        self.assertAlmostEqual(render.text_contrast([0, 0, 0], 1.0, bg), 21.0, places=2)


def fixture(name):
    return copy_fixture("render/" + name, tmpdir())


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class ContrastGate(unittest.TestCase):
    def test_low_contrast_warns_with_times(self):
        r = run_script("render.py", fixture("low_contrast.html"), "--check-only")
        g = parse_report(r.stdout)["gates"]["contrast"]
        self.assertTrue(g.startswith("WARN"), g)
        self.assertIn("#pale 1.4:1 at t=0.000", g)
        self.assertIn("#moving", g)
        self.assertIn("t=1.000", g)            # the panel leaves at 1 s: white on light
        self.assertNotIn("#ok", g)

    def test_text_on_moving_pill_passes(self):
        r = run_script("render.py", fixture("good_contrast.html"), "--check-only")
        self.assertEqual(parse_report(r.stdout)["gates"]["contrast"], "pass")

    def test_no_data_text(self):
        r = run_script("render.py", copy_fixture("golden/broken_seam.html", tmpdir()), "--check-only")
        self.assertTrue(parse_report(r.stdout)["gates"]["contrast"].startswith("pass"))

    def test_thorough(self):
        r = run_script("render.py", fixture("low_contrast.html"), "--check-only", "--thorough")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"determinism: \d+ times \(fixed seed 7")
        self.assertTrue(parse_report(r.stdout)["gates"]["contrast"].startswith("WARN"))


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class ReviewOutputs(unittest.TestCase):
    def test_sheet_stills_in_subfolder(self):
        """D.2: --sheet keeps renders/ to the sheet; its 16 stills go to renders/stills/."""
        html = copy_fixture("render/fmt.html", tmpdir())
        r = run_script("render.py", html, "--format", "1x1", "--sheet")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = html.parent / "renders"
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["fmt_1x1_sheet.png", "stills"])
        self.assertEqual(len(list((out / "stills").glob("fmt_1x1_t*.png"))), 16)

    def test_deliver_writes_phone_sheet(self):
        """D.4: --deliver writes _sheet_phone.png per format and lists it in deliver.json."""
        html = copy_fixture("render/fmt.html", tmpdir())
        r = run_script("render.py", html, "--format", "9x16", "--deliver", "--duration", "0.5", "--workers", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        (item,) = json.loads((html.parent / "renders" / "deliver.json").read_text())["items"]
        self.assertEqual(item["sheet_phone"], "renders/fmt_9x16_sheet_phone.png")
        from PIL import Image
        with Image.open(html.parent / item["sheet_phone"]) as im:
            self.assertEqual(im.width, 4 * 270 + 3 * 6)


if __name__ == "__main__":
    unittest.main()
