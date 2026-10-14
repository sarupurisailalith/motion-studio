import unittest

import helpers


class Smoke(unittest.TestCase):
    def test_layout(self):
        self.assertTrue((helpers.SCRIPTS / "render.py").exists())
        self.assertTrue((helpers.TEMPLATES / "composition.html").exists())

    def test_run_script(self):
        r = helpers.run_script("check.py", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_parse_report(self):
        self.assertEqual(helpers.parse_report('[render] x\n{\n "a": 1\n}\n'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
