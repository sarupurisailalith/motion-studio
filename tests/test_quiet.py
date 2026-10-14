"""render.py --quiet: keep results (outputs, errors, the JSON report), drop progress chatter,
so an agent driving the pipeline reads fewer tokens."""
import unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Quiet(unittest.TestCase):
    def test_check_only_quiet_keeps_report_drops_gate_lines(self):
        html = copy_fixture("golden/blank_frame.html", tmpdir())
        loud = run_script("render.py", html, "--check-only")
        quiet = run_script("render.py", html, "--check-only", "--quiet")
        self.assertIn("[render] gate determinism", loud.stdout)
        self.assertNotIn("[render]", quiet.stdout)
        self.assertEqual(parse_report(quiet.stdout)["gates"], parse_report(loud.stdout)["gates"])

    def test_full_render_quiet_keeps_done_line_only(self):
        html = copy_fixture("golden/blank_frame.html", tmpdir())
        r = run_script("render.py", html, "--skip-checks", "--workers", "1", "--fps", "60", "--quiet")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.startswith("[render]")]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("done ->", lines[0])
        self.assertTrue((html.parent / "renders" / "blank_frame.mp4").exists())

    def test_page_errors_still_shown_when_quiet(self):
        d = tmpdir()
        html = d / "err.html"
        src = (helpers.FIXTURES / "golden" / "blank_frame.html").read_text()
        html.write_text(src.replace("window.ready = Promise.resolve();",
                                    "window.ready = Promise.resolve(); console.error('boom');"))
        r = run_script("render.py", html, "--stills", "0", "--quiet")
        self.assertIn("boom", r.stdout)


if __name__ == "__main__":
    unittest.main()
