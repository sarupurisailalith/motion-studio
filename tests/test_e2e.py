"""W2.1 cross-component end-to-end tests: the real template + kit.js through every script.

1. Multi-format picture with synced sound: render.py --check-only (4 gates, 2 formats) ->
   beats.py --grid -> render.py --hits (beat-timed hits) -> sfx.py -> render.py --deliver ->
   mix.py --mux (refreshes deliver.json) -> check.py --sync --loop on each MP4.
2. An ingested video clip (ingest.py) drawn with K.loadClip/K.drawClip passes determinism.
"""
import json, subprocess, unittest

import helpers
from helpers import copy_fixture, parse_report, run_script, tmpdir

FORMATS = ["9x16", "1x1"]


def must(test, r):
    test.assertEqual(r.returncode, 0, f"{r.args}\nstdout:\n{r.stdout[-2000:]}\nstderr:\n{r.stderr[-3000:]}")
    return r


def short_template(d):
    """The 2D template (+ kit.js) played 3x fast: 2 s, still a seamless loop, with beats.js
    loaded before the kit and hits in seconds and in beats."""
    html = copy_fixture(helpers.TEMPLATES / "composition.html", d)
    copy_fixture(helpers.TEMPLATES / "kit.js", d)
    src = html.read_text()
    swaps = [
        ('<script src="kit.js"></script>', '<script src="beats.js"></script>\n<script src="kit.js"></script>'),
        ("width: 1080, height: 1080, fps: 60, duration: 6, loop: true,",
         "width: 1080, height: 1080, fps: 60, duration: 2, loop: true,"),
        ("hits: [[1.5, 'title-in', 'tick'], [2.0, 'pill', 'swoosh'], [4.4, 'square', 'thud']],",
         "hits: [[0.5, 'title-in', 'tick'], ['2b', 'pill', 'swoosh'], [1.47, 'square', 'thud']],"),
        ("const D = window.MOTION.duration;\n  // camera", "const D = window.MOTION.duration * 3;\n  // camera"),
        ("window.seek = async (t) => { await window.ready; render(t); };",
         "window.seek = async (t) => { await window.ready; render(t * 3); };"),
    ]
    for old, new in swaps:
        assert old in src, f"template changed; update test_e2e: {old!r}"
        src = src.replace(old, new)
    html.write_text(src)
    return html


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class EndToEnd(unittest.TestCase):
    def test_multiformat_render_with_synced_audio(self):
        P = tmpdir()
        must(self, run_script("beats.py", "--grid", "--bpm", 120, "--duration", 2, "--out", P))
        self.assertTrue((P / "beats.js").exists())
        html = short_template(P)

        # 1. every gate in both formats
        r = must(self, run_script("render.py", html, "--check-only", "--format", ",".join(FORMATS)))
        reps = parse_report(r.stdout)["formats"]
        self.assertEqual(sorted(reps), sorted(FORMATS))
        for fmt, rep in reps.items():
            g = rep["gates"]
            self.assertEqual(g["determinism"], "pass", (fmt, g))
            self.assertTrue(g["loop_seam"].startswith("pass"), (fmt, g))
            self.assertEqual(g["safe_area"], "pass", (fmt, g))
            self.assertEqual(g["text_duration"], "pass", (fmt, g))
            self.assertEqual(g["page_errors"], "none", (fmt, g))

        # 2-3. hits (one written in beats: '2b' = 1.0 s at 120 BPM) -> sfx
        must(self, run_script("render.py", html, "--hits"))
        hits_json = P / "renders" / "composition_hits.json"
        hits = json.loads(hits_json.read_text())["hits"]
        self.assertEqual([(h["t"], h["sfx"]) for h in hits], [(0.5, "tick"), (1.0, "swoosh"), (1.47, "thud")])
        (P / "audio").mkdir()
        must(self, run_script("sfx.py", hits_json, "--out", P / "audio" / "sfx.wav"))
        events = P / "audio" / "sfx_events.json"
        self.assertTrue(events.exists())

        # 4. delivery bundle
        must(self, run_script("render.py", html, "--format", ",".join(FORMATS), "--deliver", "--workers", 2))
        deliver = json.loads((P / "renders" / "deliver.json").read_text())
        videos = [P / it["video"] for it in deliver["items"]]
        self.assertEqual([it["format"] for it in deliver["items"]], FORMATS)
        for it, v in zip(deliver["items"], videos):
            self.assertTrue(v.exists(), v)
            self.assertTrue((P / it["poster"]).exists() and (P / it["sheet"]).exists(), it)
            self.assertIs(it["audio"], False)

        # 5. mix + mux into both; deliver.json follows
        must(self, run_script("mix.py", "--duration", 2, "--sfx", P / "audio" / "sfx.wav",
                              "--out", P / "audio" / "mix.wav", "--mux", *videos))
        deliver = json.loads((P / "renders" / "deliver.json").read_text())
        for it, v in zip(deliver["items"], videos):
            self.assertIs(it["audio"], True, it)
            self.assertEqual(it["size_bytes"], v.stat().st_size, it)

        # 6. QA on each delivered file: loudness and sync
        for v in videos:
            c = must(self, run_script("check.py", v, "--loop", "--sync", events, "--no-sheet"))
            g = parse_report(c.stdout)["gates"]
            self.assertEqual(g["audio"], "pass", (v.name, g))
            self.assertEqual(g["sync"], "pass", (v.name, g))
            self.assertFalse([k for k, s in g.items() if str(s).startswith("FAIL")], (v.name, g))

    def test_ingested_clip_is_deterministic(self):
        P = tmpdir()
        src = tmpdir() / "demo clip.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x180:rate=30:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(src)], check=True)
        r = must(self, run_script("ingest.py", P, src, "--clip-fps", 30))
        clip = next(a for a in json.loads((P / "assets" / "assets.json").read_text())["assets"]
                    if a["kind"] == "video")
        self.assertEqual(clip["frame_count"], 30, r.stdout)
        copy_fixture(helpers.TEMPLATES / "kit.js", P)
        html = P / "clip.html"
        html.write_text(CLIP_COMP.replace("CLIP_ID", clip["id"]))

        r = must(self, run_script("render.py", html, "--check-only"))
        g = parse_report(r.stdout)["gates"]
        self.assertEqual(g["determinism"], "pass", g)
        self.assertEqual(g["page_errors"], "none", g)

        # the clip really plays: different source frames give different pictures
        must(self, run_script("render.py", html, "--stills", "0.1,0.6"))
        from PIL import Image, ImageChops
        a, b = (Image.open(P / "renders" / f"clip_t{t}.png").convert("RGB") for t in ("000.100", "000.600"))
        self.assertIsNotNone(ImageChops.difference(a, b).getbbox())


CLIP_COMP = """<!doctype html>
<html><head><meta charset="utf-8"><title>clip</title>
<style>html,body{margin:0;background:#000;overflow:hidden}canvas{display:block}</style></head>
<body><canvas id="c" width="640" height="360"></canvas>
<script src="assets/assets.js"></script>
<script src="kit.js"></script>
<script>
window.MOTION = K.init({ width: 640, height: 360, fps: 30, duration: 1, loop: false });
const clip = ASSETS.assets.find(a => a.id === 'CLIP_ID');
const ctx = document.getElementById('c').getContext('2d');
window.ready = (async () => { await K.loadClip(clip); })();
window.seek = async t => {
  await window.ready;
  ctx.fillStyle = '#111'; ctx.fillRect(0, 0, 640, 360);
  K.drawClip(ctx, clip, t, 80, 45, 480, 270);
};
</script></body></html>
"""

if __name__ == "__main__":
    unittest.main()
