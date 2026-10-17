"""check.py's local-motion frozen gate (D.1), reference.py (E4.1) and check.py --against (E4.3)."""
import json, subprocess, sys, unittest

import numpy as np

import helpers
from helpers import parse_report, run_script, tmpdir

sys.path.insert(0, str(helpers.SCRIPTS))


def encode(path, *inputs, graph=None):
    """Encode lavfi sources like render.py does (x264, CRF 16, yuv420p)."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for src in inputs:
        cmd += ["-f", "lavfi", "-i", src]
    if graph:
        cmd += ["-filter_complex", graph]
    cmd += ["-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


def still_clip(path, seconds=2):
    return encode(path, f"color=c=0xf2efe9:s=1080x1080:r=60:d={seconds}")


def box_clip(path, box_px, speed, seconds=2):
    """A dark box_px square moving `speed` px/s across a light 1080 x 1080 frame at 60 fps."""
    return encode(path, f"color=c=0xf2efe9:s=1080x1080:r=60:d={seconds}",
                  f"color=c=0x111111:s={box_px}x{box_px}:r=60:d={seconds}",
                  graph=f"[0][1]overlay=x='100+{speed}*t':y=500")


def check(video, *args):
    r = run_script("check.py", video, "--no-sheet", *args)
    return r, parse_report(r.stdout)


class LocalMotionUnits(unittest.TestCase):
    """D.1: the frozen measurement is local (max over 40 px tiles) and ignores encoder noise."""

    def test_small_change_is_seen_locally(self):
        import check as c
        a = np.full((180, 320), 200.0, np.float32)
        b = a.copy()
        b[50:56, 50:56] = 20.0                          # a 6 px dot: 0.06 % of the frame
        self.assertLess(np.abs(a - b).mean(), 0.15)     # the old whole-frame mean called this still
        self.assertGreater(c.tile_change(a, b), c.STILL_LEVEL)

    def test_noise_below_floor_ignored(self):
        import check as c
        rng = np.random.default_rng(0)
        a = np.full((180, 320), 120.0, np.float32)
        b = a + rng.integers(-3, 4, a.shape)             # +-3 levels everywhere: encoder noise
        self.assertEqual(c.tile_change(a, b), 0.0)

    def test_hold_length_matches_frame_steps(self):
        import check as c
        # 61 identical frames at 60 fps = 60 frame steps = 1.0 s, with a 6-frame window
        st = {"fps": 60.0, "lag": 6, "local": np.zeros(61 - 6)}
        hold, at, share = c.longest_still(st)
        self.assertAlmostEqual(hold, 1.0)
        self.assertEqual((at, share), (0.0, 1.0))

    def test_pacing_tolerance(self):
        import check as c
        ref = {"cuts_per_min": 20.0, "motion_share": 0.8}
        self.assertEqual(c.pacing({"cuts_per_min": 15.0, "motion_share": 0.8}, ref)[0], "pass")    # 25 % slower
        slow = c.pacing({"cuts_per_min": 12.0, "motion_share": 0.8}, ref)[0]                     # 40 % slower
        self.assertTrue(slow.startswith("WARN") and "slower" in slow, slow)
        busy = c.pacing({"cuts_per_min": 20.0, "motion_share": 1.0}, {**ref, "motion_share": 0.5})[0]
        self.assertTrue(busy.startswith("WARN") and "busier" in busy, busy)
        self.assertEqual(c.pacing({"cuts_per_min": 9.0, "motion_share": 0.8},
                                  {"cuts_per_min": 0.0, "motion_share": 0.8})[0], "pass")      # one-shot ref


@helpers.needs_ffmpeg
class FrozenGate(unittest.TestCase):
    """D.1 acceptance: a 60 px box at 240 px/s is not "still" (it was at 160 px / 0.15 mean)."""

    def test_dogfood_box_moves(self):
        v = box_clip(tmpdir() / "box.mp4", 60, 240)
        _, rep = check(v, "--max-hold", "0.5")
        self.assertEqual(rep["gates"]["frozen"], "pass")
        self.assertEqual(rep["still_share"], 0.0)

    def test_tiny_slow_mover_moves(self):
        v = box_clip(tmpdir() / "dot.mp4", 10, 30)
        _, rep = check(v, "--max-hold", "0.5")
        self.assertEqual(rep["gates"]["frozen"], "pass")

    def test_static_frame_is_frozen(self):
        v = still_clip(tmpdir() / "still.mp4")
        _, rep = check(v, "--max-hold", "0.5")
        g = rep["gates"]["frozen"]
        self.assertTrue(g.startswith("WARN"), g)
        self.assertIn("1.98s at 0.00s", g)     # 120 frames = 119 frame steps at 60 fps
        self.assertEqual(rep["still_share"], 1.0)


def cuts_clip(path):
    """Four shots of 1.5 / 1 / 1 / 1.5 s (hard cuts at 1.5, 2.5, 3.5) at 640 x 360, 30 fps."""
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1.5:s=640x360:r=30",
                    "-f", "lavfi", "-i", "smptebars=d=1:s=640x360:r=30",
                    "-f", "lavfi", "-i", "color=c=red:d=1:s=640x360:r=30",
                    "-f", "lavfi", "-i", "testsrc2=d=1.5:s=640x360:r=30",
                    "-filter_complex", "[0][1][2][3]concat=n=4:v=1[v]", "-map", "[v]",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@helpers.needs_ffmpeg
class Reference(unittest.TestCase):
    """E4.1 reference.py and E4.3 check.py --against."""

    @classmethod
    def setUpClass(cls):
        cls.d = tmpdir()
        cls.video = cuts_clip(cls.d / "ref.mp4")
        cls.proj = cls.d / "proj"
        cls.r = run_script("reference.py", cls.video, cls.proj)
        cls.out = cls.proj / "docs" / "reference" / "ref"

    def test_outputs_and_cuts(self):
        self.assertEqual(self.r.returncode, 0, self.r.stderr)
        data = json.loads((self.out / "cuts.json").read_text())
        self.assertEqual(data["kind"], "video")
        self.assertEqual(len(data["cuts"]), 3)
        for got, want in zip(data["cuts"], (1.5, 2.5, 3.5)):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertEqual([s["length"] for s in data["shots"]], [1.5, 1.0, 1.0, 1.5])
        self.assertAlmostEqual(data["cuts_per_min"], 36.0, delta=0.5)
        for k in ("mean_delta", "still_share", "longest_still", "hard_jumps_per_s"):
            self.assertIn(k, data["motion"])
        self.assertIn("morphs", data["note"])
        for s in data["shots"]:
            self.assertTrue((self.out / s["frame"]).exists(), s)
        self.assertTrue((self.out / "sheet.png").exists())
        self.assertTrue((self.out / "shots.png").exists())

    def test_stills_folder(self):
        r = run_script("reference.py", self.out / "shots", self.proj, "--name", "boards")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((self.proj / "docs" / "reference" / "boards" / "cuts.json").read_text())
        self.assertEqual((data["kind"], data["count"]), ("images", 4))
        self.assertTrue((self.proj / "docs" / "reference" / "boards" / "sheet.png").exists())

    def test_refuses_urls(self):
        r = run_script("reference.py", "https://example.com/ref.mp4", self.proj)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("local files only", r.stderr)

    def test_against_same_pacing_passes(self):
        _, rep = check(self.video, "--against", self.out / "cuts.json")
        self.assertEqual(rep["gates"]["pacing"], "pass", rep.get("pacing"))
        self.assertEqual(rep["pacing"]["ours"]["cuts_per_min"], rep["pacing"]["reference_values"]["cuts_per_min"])

    def test_against_slower_piece_warns(self):
        v = box_clip(self.d / "oner.mp4", 60, 240, seconds=3)      # no cuts in 3 s
        r, rep = check(v, "--against", self.out / "cuts.json")
        self.assertEqual(r.returncode, 0)                           # WARN, not FAIL
        g = rep["gates"]["pacing"]
        self.assertTrue(g.startswith("WARN") and "slower" in g, g)

    def test_against_stills_skips(self):
        run_script("reference.py", self.out / "shots", self.proj, "--name", "boards2")
        _, rep = check(self.video, "--against", self.proj / "docs" / "reference" / "boards2" / "cuts.json")
        self.assertTrue(rep["gates"]["pacing"].startswith("skipped"), rep["gates"]["pacing"])


class Help(unittest.TestCase):
    def test_help_mentions_new_flags(self):
        self.assertIn("--against", run_script("check.py", "--help").stdout)
        h = run_script("reference.py", "--help")
        self.assertEqual(h.returncode, 0, h.stderr)
        self.assertIn("never downloads", h.stdout)


if __name__ == "__main__":
    unittest.main()
