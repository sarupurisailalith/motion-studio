import unittest

import helpers


class Smoke(unittest.TestCase):
    def test_layout(self):
        self.assertTrue((helpers.SCRIPTS / "render.py").exists())
        self.assertTrue((helpers.TEMPLATES / "composition.html").exists())

    def test_run_script(self):
        r = helpers.run_script("check.py", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_frontmatter(self):
        """E9.2: CI's frontmatter check passes on the repo and catches a missing block or key."""
        import frontmatter
        self.assertEqual(frontmatter.problems(), [])
        d = helpers.tmpdir()
        (d / "skills" / "x").mkdir(parents=True)
        (d / "skills" / "x" / "SKILL.md").write_text("# no frontmatter\n")
        (d / "commands").mkdir()
        (d / "commands" / "c.md").write_text("---\nargument-hint: x\n---\nbody\n")
        bad = frontmatter.problems(d)
        self.assertEqual(len(bad), 2, bad)
        self.assertIn("no frontmatter", " ".join(bad))
        self.assertIn("'description'", " ".join(bad))

    def test_parse_report(self):
        self.assertEqual(helpers.parse_report('[render] x\n{\n "a": 1\n}\n'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
