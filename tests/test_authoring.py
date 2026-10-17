"""v0.3 authoring tests: kit spring presets (E7.2), image helpers + device frames (E3.4),
typography (E7.3), GSAP / GLSL templates (E7.5), the kit examples, scaffold.py + doctor.py (E7.4)
and brand.py (E3.8 / E3.5)."""
import json, os, shutil, sys, unittest
from pathlib import Path

import helpers
from helpers import parse_report, run_script, tmpdir
from test_kit import Browser, project

EXAMPLES = helpers.TEMPLATES / "examples"


def gates_pass(testcase, report, fmt=""):
    g = report["gates"]
    testcase.assertEqual(g["determinism"], "pass", (fmt, g))
    testcase.assertTrue(g["loop_seam"].startswith("pass"), (fmt, g))
    testcase.assertTrue(g["safe_area"].startswith("pass"), (fmt, g))
    testcase.assertTrue(g["text_duration"].startswith("pass"), (fmt, g))
    testcase.assertEqual(g["page_errors"], "none", (fmt, g))


def with_kit(src, d=None):
    d = Path(d or tmpdir())
    dst = d / src.name
    shutil.copy2(src, dst)
    shutil.copy2(helpers.TEMPLATES / "kit.js", d / "kit.js")
    return dst


# ------------------------------------------------------------------------------ kit (browser)

@helpers.slow
@helpers.needs_chromium
class Springs(Browser):
    SETTLE = """(p => { let last = 0; for (let i = 1; i < 4000; i++) { const t = i / 2000;
        if (Math.abs(p(t) - 1) > 0.02) last = t; } return last; })"""

    def test_presets_match_their_numbers(self):
        page, errors = self.open(project())
        for name in ("snappy", "ui", "soft", "camera"):
            with self.subTest(preset=name):
                p = page.evaluate(f"(({{w, z, settle, overshoot}}) => ({{w, z, settle, overshoot}}))(K.SPRING.{name})")
                got = page.evaluate(f"{self.SETTLE}(K.SPRING.{name})")
                self.assertAlmostEqual(got, p["settle"], delta=0.01, msg=f"{name} settle")
                peak = page.evaluate(f"Math.max(...Array.from({{length: 3000}}, (_, i) => K.SPRING.{name}(i / 2000)))")
                self.assertAlmostEqual(peak - 1, p["overshoot"], delta=0.003, msg=f"{name} overshoot")
                self.assertGreaterEqual(p["z"], 0.7)            # craft.md: keep z >= .7 for UI
        self.assertEqual(page.evaluate("K.SPRING.camera.settle > K.SPRING.ui.settle"), True)
        self.assertEqual(errors, [])

    def test_spring_and_track_accept_presets(self):
        page, _ = self.open(project())
        self.assertEqual(page.evaluate("K.spring(0.1, K.SPRING.ui) === K.spring(0.1, 16.9, 0.72)"), True)
        self.assertEqual(page.evaluate("K.spring(0.1)"), 0.6097155118230713)   # default unchanged
        self.assertEqual(page.evaluate(
            "K.springTrack([[0, 0], [1, 10]], 1.2, K.SPRING.camera) === K.springTrack([[0, 0], [1, 10]], 1.2, 9.7, 1)"), True)
        self.assertEqual(page.evaluate("Object.isFrozen(K.SPRING) && Object.isFrozen(K.SPRING.ui)"), True)

    def test_wobble_and_squash(self):
        page, _ = self.open(project())
        self.assertEqual(page.evaluate("[K.wobble(0), K.wobble(-1)]"), [0, 0])
        self.assertLess(abs(page.evaluate("K.wobble(2, {amp: 10})")), 1e-6)       # decays
        self.assertEqual(page.evaluate("K.squash(-0.1)"), {"sx": 1, "sy": 1})
        for dt in (0.01, 0.05, 0.2):
            s = page.evaluate(f"K.squash({dt})")
            self.assertAlmostEqual(s["sx"] * s["sy"], 1, places=9)               # volume-preserving
        self.assertAlmostEqual(page.evaluate("K.squash(1e-6).sx"), 1.12, places=3)


IMG = """(() => { const c = document.createElement('canvas'); c.width = 200; c.height = 100;
  const g = c.getContext('2d'); g.fillStyle = '#ff0000'; g.fillRect(0, 0, 100, 100);
  g.fillStyle = '#0000ff'; g.fillRect(100, 0, 100, 100); window.TESTIMG = c; return true; })()"""
PIXEL = """(([x, y]) => Array.from(window.CTX.getImageData(x, y, 1, 1).data.slice(0, 3)))"""


@helpers.slow
@helpers.needs_chromium
class Images(Browser):
    def setUp(self):
        self.page, self.errors = self.open(project())
        self.page.evaluate(IMG)
        self.page.evaluate("""(() => { const c = document.createElement('canvas'); c.width = 400; c.height = 400;
            window.CTX = c.getContext('2d'); })()""")

    def ev(self, js):
        return self.page.evaluate(js)

    def test_fit_rect_cover_focal_and_clamp(self):
        g = self.ev("K.fitRect({x: 0, y: 0, w: 200, h: 100}, {x: 10, y: 20, w: 100, h: 100}, {})")
        self.assertEqual(g["s"], 1)
        self.assertEqual(g["view"], {"x": 10, "y": 20, "w": 100, "h": 100})
        self.assertEqual(g["src"], {"x": 50, "y": 0, "w": 100, "h": 100})        # centred
        g = self.ev("K.fitRect({x: 0, y: 0, w: 200, h: 100}, {x: 0, y: 0, w: 100, h: 100}, {fx: 0})")
        self.assertEqual(g["src"]["x"], 0)                                        # left edge, never past it
        g = self.ev("K.fitRect({x: 0, y: 0, w: 200, h: 100}, {x: 0, y: 0, w: 100, h: 100}, {fx: 1, zoom: 2})")
        self.assertEqual((g["s"], g["src"]["x"], g["src"]["w"]), (2, 150, 50))   # clamped at the right edge

    def test_fit_rect_contain_never_crops(self):
        g = self.ev("K.fitRect({x: 0, y: 0, w: 200, h: 100}, {x: 0, y: 0, w: 100, h: 100}, {fit: 'contain'})")
        self.assertEqual(g["src"], {"x": 0, "y": 0, "w": 200, "h": 100})
        self.assertEqual(g["view"], {"x": 0, "y": 25, "w": 100, "h": 50})

    def test_canvas_cover_and_crop_pixels(self):
        self.ev("K.cover(CTX, TESTIMG, {x: 0, y: 0, w: 100, h: 100}, {fx: 0})")
        self.assertEqual(self.ev(f"{PIXEL}([50, 50])"), [255, 0, 0])
        self.ev("K.cover(CTX, TESTIMG, {x: 0, y: 0, w: 100, h: 100}, {fx: 1})")
        self.assertEqual(self.ev(f"{PIXEL}([50, 50])"), [0, 0, 255])
        self.ev("K.crop(CTX, TESTIMG, {x: 120, y: 0, w: 80, h: 100}, {x: 200, y: 0, w: 100, h: 100})")
        self.assertEqual(self.ev(f"{PIXEL}([250, 50])"), [0, 0, 255])              # only the blue half
        self.ev("K.cover(CTX, TESTIMG, {x: 0, y: 200, w: 100, h: 100}, {radius: 40})")
        self.assertEqual(self.ev("CTX.getImageData(1, 201, 1, 1).data[3]"), 0)     # rounded corner left clear
        self.assertEqual(self.errors, [])

    def test_dom_cover_places_the_image(self):
        r = self.ev("""(() => { const el = document.createElement('div');
            el.style.cssText = 'position:absolute;left:0;top:0;width:100px;height:100px'; document.body.appendChild(el);
            const img = new Image(); img.width = 200; img.height = 100;
            Object.defineProperty(img, 'naturalWidth', {value: 200}); Object.defineProperty(img, 'naturalHeight', {value: 100});
            K.cover(el, img, null, {fx: 1, radius: 12});
            return [img.parentNode === el, img.style.left, img.style.width, el.style.overflow, el.style.borderRadius]; })()""")
        self.assertEqual(r, [True, "-100px", "200px", "hidden", "12px"])

    def test_unloaded_image_throws(self):
        msg = self.ev("(() => { try { K.cover(CTX, new Image(), {x:0,y:0,w:9,h:9}); } catch (e) { return e.message; } })()")
        self.assertIn("not loaded", msg)

    def test_device_geometry_dom_and_canvas_agree(self):
        for kind in ("browser", "phone"):
            with self.subTest(kind=kind):
                g = self.ev(f"K.deviceGeom('{kind}', {{x: 0, y: 0, w: 390, h: 844}})")
                dom = self.ev(f"""(() => {{ const d = K.device('{kind}', {{w: 390, h: 844, url: 'example.test'}});
                    document.body.appendChild(d.el);
                    return {{ w: d.screen.offsetWidth, h: d.screen.offsetHeight, x: d.screen.offsetLeft, y: d.screen.offsetTop,
                              cls: d.el.className, imgs: d.el.querySelectorAll('img').length }}; }})()""")
                self.assertEqual((dom["x"], dom["y"], dom["w"], dom["h"]),
                                 (g["screen"]["x"], g["screen"]["y"], g["screen"]["w"], g["screen"]["h"]))
                self.assertEqual(dom["imgs"], 0)                                  # CSS-built, no images
                seen = self.ev(f"""(() => {{ let s = null; K.drawDevice(CTX, '{kind}', {{x: 0, y: 0, w: 390, h: 844}}, {{}},
                    r => {{ s = r; K.cover(CTX, TESTIMG, r); }}); return s; }})()""")
                self.assertEqual(seen, g["screen"])
        self.assertIn("unknown kind", self.ev("(() => { try { K.deviceGeom('watch', {x:0,y:0,w:1,h:1}); } catch (e) { return e.message; } })()"))


@helpers.slow
@helpers.needs_chromium
class Typography(Browser):
    def setUp(self):
        self.page, self.errors = self.open(project())

    def ev(self, js):
        return self.page.evaluate(js)

    def test_glyphs_split_graphemes(self):
        r = self.ev("""(() => { const el = document.createElement('div'); document.body.appendChild(el);
            const s = K.glyphs(el, 'Hi 👋🏽!', {tracking: -40});
            return [s.length, s.map(x => x.textContent).join(''), el.style.letterSpacing]; })()""")
        self.assertEqual(r, [5, "Hi 👋🏽!", "-0.04em"])

    def test_fit_text_dom_and_canvas(self):
        dom = self.ev("""(() => { const el = document.createElement('div');
            el.style.cssText = 'position:absolute;font:800 20px sans-serif;white-space:nowrap'; el.textContent = 'Make it move';
            document.body.appendChild(el); const px = K.fitText(el, 600, {max: 400});
            el.style.width = 'max-content'; return [px, el.scrollWidth]; })()""")
        self.assertLessEqual(dom[1], 600)
        self.assertGreater(dom[1], 600 * 0.95)
        cv = self.ev("""(() => { const ctx = document.createElement('canvas').getContext('2d'); ctx.font = '800 20px sans-serif';
            const px = K.fitText(ctx, 600, {text: 'Make it move', tracking: -40});
            return [px, K.layoutText(ctx, 'Make it move', {tracking: -40}).width, ctx.font]; })()""")
        self.assertLessEqual(cv[1], 600)
        self.assertGreater(cv[1], 600 * 0.95)
        self.assertIn(f"{cv[0]:g}px", cv[2])
        self.assertEqual(self.ev("K.fitText(document.createElement('canvas').getContext('2d'), 1, {text: 'WIDE', min: 12})"), 12)

    def test_layout_text_tracking_and_align(self):
        r = self.ev("""(() => { const ctx = document.createElement('canvas').getContext('2d'); ctx.font = '100px sans-serif';
            const a = K.layoutText(ctx, 'ABC'), b = K.layoutText(ctx, 'ABC', {tracking: 100}), c = K.layoutText(ctx, 'ABC', {align: 'center'});
            return [a.glyphs[0].x, b.width - a.width, b.glyphs[2].x - a.glyphs[2].x, c.glyphs[0].x, -a.width / 2]; })()""")
        self.assertEqual(r[0], 0)
        self.assertAlmostEqual(r[1], 20, places=6)        # 2 gaps x 0.1 em x 100 px
        self.assertAlmostEqual(r[2], 20, places=6)
        self.assertAlmostEqual(r[3], r[4], places=6)

    def test_rise_mask_reveal(self):
        self.assertEqual(self.ev("K.rise(0, 0, {at: 1, travel: 100}).y"), 100)
        self.assertEqual(self.ev("K.rise(0, 0, {at: 1, travel: 100}).shown"), False)
        self.assertEqual(self.ev("K.rise(5, 3, {at: 1, travel: 100}).y"), 0)
        self.assertEqual(self.ev("K.rise(9, 0, {at: 1, travel: 100, out: 6}).y"), -100)
        self.assertLess(self.ev("K.rise(1.1, 2, {at: 1, gap: 0.1, travel: 100}).p"), 0.001)   # staggered
        shown = self.ev("""(() => { const el = document.createElement('div'); const s = K.glyphs(el, 'AB');
            return [K.maskRise(s, 0, {at: 1, travel: 100}), K.maskRise(s, 3, {at: 1, travel: 100}), s[0].style.transform]; })()""")
        self.assertEqual(shown, [False, True, "translateY(0px)"])

    def test_typed_from_t(self):
        ts = [i / 10 for i in range(0, 40)]
        rows = self.ev(f"{ts}.map(t => K.typed('Hello, world', t, {{at: 0.5, cps: 12, seed: 3}}))")
        ns = [r["n"] for r in rows]
        self.assertEqual(ns, sorted(ns))                                            # monotonic
        self.assertEqual(rows[0]["text"], "")
        self.assertEqual(rows[-1]["text"], "Hello, world")
        self.assertTrue(all("Hello, world".startswith(r["text"]) for r in rows))
        self.assertEqual(rows, self.ev(f"{ts}.reverse().map(t => K.typed('Hello, world', t, {{at: 0.5, cps: 12, seed: 3}})).reverse()"))
        end = rows[-1]["end"]
        self.assertTrue(all(r["caret"] for r in rows if 0 < r["n"] < 12))           # solid while typing
        blink = self.ev(f"[0, 0.3, 0.6, 0.9, 1.2].map(d => K.typed('Hello, world', {end} + 0.5 + d, {{at: 0.5, cps: 12, seed: 3}}).caret)")
        self.assertIn(True, blink)
        self.assertIn(False, blink)                                                 # blinks when idle

    def test_scramble_seeded_and_settles(self):
        a = self.ev("K.scramble('BRAND NEW', 0.3, {at: 0, dur: 1, seed: 5})")
        self.assertEqual(a, self.ev("K.scramble('BRAND NEW', 0.3, {at: 0, dur: 1, seed: 5})"))
        self.assertNotEqual(a, self.ev("K.scramble('BRAND NEW', 0.3, {at: 0, dur: 1, seed: 6})"))
        self.assertEqual(a[5], " ")                                                 # spaces stay
        self.assertEqual(len(a), 9)
        self.assertEqual(self.ev("K.scramble('BRAND NEW', 1.0, {at: 0, dur: 1, seed: 5})"), "BRAND NEW")
        settled = self.ev("[0.2, 0.4, 0.6, 0.8].map(t => [...K.scramble('BRAND NEW', t, {at: 0, dur: 1, seed: 5, chars: '#'})].filter(c => c === '#').length)")
        self.assertEqual(settled, sorted(settled, reverse=True))
        self.assertEqual(self.ev("K.scramble('AB', 0.99, {snap: 1, chars: '#'})"), "##")
        self.assertEqual(self.ev("K.scramble('AB', 1, {snap: 1, chars: '#'})"), "AB")

    def test_draw_glyphs_restores_alpha(self):
        r = self.ev("""(() => { const ctx = document.createElement('canvas').getContext('2d'); ctx.font = '40px sans-serif';
            ctx.globalAlpha = 0.5; const lay = K.layoutText(ctx, 'Hey');
            K.drawGlyphs(ctx, lay, 10, 50, (g, i) => i === 1 ? null : {dy: 2, alpha: 0.5}, {mask: true});
            return ctx.globalAlpha; })()""")
        self.assertEqual(r, 0.5)


# ------------------------------------------------------------------------------ templates and examples

@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Templates(unittest.TestCase):
    def test_glsl_template_passes_gates(self):
        html = with_kit(helpers.TEMPLATES / "glsl-composition.html")
        r = run_script("render.py", html, "--check-only", "--gl", "--format", "16x9,9x16")
        for fmt, rep in parse_report(r.stdout)["formats"].items():
            gates_pass(self, rep, fmt)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_glsl_without_gl_names_the_flag(self):
        src = (helpers.TEMPLATES / "glsl-composition.html").read_text()
        self.assertIn("render with render.py --gl", src)
        self.assertIn("preserveDrawingBuffer: true", src)

    def test_gsap_template_passes_gates(self):
        d = tmpdir()
        html = with_kit(helpers.TEMPLATES / "gsap-composition.html", d)
        v = run_script("vendor.py", d, "gsap", timeout=300)
        if v.returncode != 0 or not (d / "vendor" / "gsap.min.js").exists():
            self.skipTest("could not vendor gsap (npm/network unavailable)")
        r = run_script("render.py", html, "--check-only", "--format", "16x9,9x16,1x1,4x5")
        for fmt, rep in parse_report(r.stdout)["formats"].items():
            gates_pass(self, rep, fmt)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_gsap_template_contract(self):
        src = (helpers.TEMPLATES / "gsap-composition.html").read_text()
        self.assertIn("paused: true", src)
        self.assertIn("tl.seek(t, false)", src)
        self.assertIn('<script src="vendor/gsap.min.js"></script>', src)
        self.assertNotIn("cdn", src.lower())                                        # never from a CDN

    def test_kinetic_type_example_passes_gates(self):
        html = with_kit(EXAMPLES / "kinetic-type.html")
        r = run_script("render.py", html, "--check-only", "--format", "16x9,9x16")
        for fmt, rep in parse_report(r.stdout)["formats"].items():
            gates_pass(self, rep, fmt)

    def test_kinetic_type_uses_kit_calls(self):
        src = (EXAMPLES / "kinetic-type.html").read_text()
        for call in ("K.glyphs", "K.fitText", "K.maskRise", "K.scramble", "K.typed", "K.SPRING"):
            self.assertIn(call, src)

    def test_device_demo_passes_gates(self):
        html = with_kit(EXAMPLES / "device-demo.html")
        r = run_script("render.py", html, "--check-only", "--format", "16x9,9x16")
        for fmt, rep in parse_report(r.stdout)["formats"].items():
            gates_pass(self, rep, fmt)
        src = html.read_text()
        for call in ("K.drawDevice", "K.device(", "K.cover", "K.SPRING"):
            self.assertIn(call, src)


# ------------------------------------------------------------------------------ scaffold / doctor

class Scaffold(unittest.TestCase):
    def test_creates_project(self):
        root = tmpdir()
        r = run_script("scaffold.py", "Launch Teaser!", "--template", "gsap", "--formats", "9x16,1x1",
                       "--duration", "12", "--fps", "30", "--root", root)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        p = root / "launch-teaser"
        self.assertEqual(Path(out["project"]), p)
        for f in ("launch-teaser.html", "kit.js", "brief.md"):
            self.assertTrue((p / f).is_file(), f)
        for d in ("assets", "audio", "docs", "renders"):
            self.assertTrue((p / d).is_dir(), d)
        self.assertIn("width: 1080, height: 1920, fps: 30, duration: 12,", (p / "launch-teaser.html").read_text())
        brief = (p / "brief.md").read_text()
        self.assertIn("<art direction>", brief)
        self.assertIn("12 s at 30 fps, 1080×1920", brief)
        self.assertIn("9x16 (1080×1920), 1x1 (1080×1080)", brief)
        self.assertTrue(any("vendor.py" in n and "gsap" in n for n in out["next"]))
        self.assertEqual((p / "kit.js").read_bytes(), (helpers.TEMPLATES / "kit.js").read_bytes())

    def test_every_template_scaffolds(self):
        for tpl in ("2d", "three", "gsap", "glsl"):
            with self.subTest(template=tpl):
                root = tmpdir()
                r = run_script("scaffold.py", "x", "--template", tpl, "--root", root, "--duration", "4.5")
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("duration: 4.5", (root / "x" / "x.html").read_text())
                self.assertEqual(json.loads(r.stdout)["gl"], tpl in ("three", "glsl"))

    def test_keeps_existing_files(self):
        root = tmpdir()
        run_script("scaffold.py", "p", "--root", root)
        (root / "p" / "brief.md").write_text("mine")
        (root / "p" / "p.html").write_text("edited")
        r = run_script("scaffold.py", "p", "--root", root)
        self.assertEqual((root / "p" / "brief.md").read_text(), "mine")
        self.assertEqual((root / "p" / "p.html").read_text(), "edited")
        self.assertEqual(len(json.loads(r.stdout)["kept"]), 3)
        run_script("scaffold.py", "p", "--root", root, "--force")
        self.assertEqual((root / "p" / "brief.md").read_text(), "mine")              # brief is never overwritten
        self.assertNotEqual((root / "p" / "p.html").read_text(), "edited")

    def test_bad_args(self):
        for args, msg in ((["--template", "flash"], "unknown --template"), (["--formats", "21x9"], "unknown format"),
                          (["--duration", "0"], "positive")):
            r = run_script("scaffold.py", "p", "--root", tmpdir(), *args)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(msg, r.stderr)

    def test_list(self):
        r = run_script("scaffold.py", "--list")
        for k in ("2d", "three", "gsap", "glsl"):
            self.assertIn(k, r.stdout)

    @helpers.slow
    @helpers.needs_chromium
    @helpers.needs_ffmpeg
    def test_scaffolded_2d_project_passes_gates(self):
        root = tmpdir()
        run_script("scaffold.py", "p", "--root", root, "--formats", "1x1")
        r = run_script("render.py", root / "p" / "p.html", "--check-only")
        gates_pass(self, parse_report(r.stdout))


class Doctor(unittest.TestCase):
    def test_json_report(self):
        r = run_script("doctor.py", "--json")
        rep = json.loads(r.stdout)
        names = [c["name"] for c in rep["required"]]
        for n in ("playwright", "numpy", "pillow", "chromium (playwright)", "ffmpeg", "ffprobe"):
            self.assertIn(n, names)
        self.assertEqual(r.returncode, 0 if rep["ok"] else 1)
        self.assertTrue(all(c["fix"] for c in rep["required"] + rep["optional"] if not c["ok"]))

    def test_missing_ffmpeg_gives_one_install_line(self):
        env = dict(os.environ, PATH=str(Path(sys.executable).parent))  # hide ffmpeg (unless it sits next to python)
        import subprocess
        r = subprocess.run([sys.executable, str(helpers.SCRIPTS / "doctor.py"), "--json"], capture_output=True,
                           text=True, env=env, timeout=120)
        rep = json.loads(r.stdout)
        ff = next(c for c in rep["required"] if c["name"] == "ffmpeg")
        if ff["ok"]:
            self.skipTest("ffmpeg lives next to the python binary")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(sum("ffmpeg" in line for line in rep["install"]), 1)      # ffmpeg + ffprobe: one command

    def test_never_installs(self):
        src = (helpers.SCRIPTS / "doctor.py").read_text()
        self.assertNotIn("subprocess", src)
        for s in ("brand.py", "scaffold.py", "doctor.py"):
            text = (helpers.SCRIPTS / s).read_text()
            for mod in ("urllib", "socket", "http.client", "requests"):
                self.assertNotIn(f"import {mod}", text, f"{s} must not use the network")


# ------------------------------------------------------------------------------ brand.py

def minimal_pdf(path, lines):
    """A one-page PDF with real text (Helvetica), written by hand, so tests need no PDF library."""
    text = "BT /F1 12 Tf 40 760 Td 14 TL " + " ".join(f"({l}) '" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(out)


def brand_inputs(d, pdf=False):
    from PIL import Image, ImageDraw
    d.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([20, 20, 380, 180], fill=(250, 80, 30, 255))   # measured ~ the guide's #ff4d1f
    im.save(d / "acme-logo.png")
    s = Image.new("RGB", (1200, 800), (250, 250, 248))
    g = ImageDraw.Draw(s)
    g.rectangle([0, 0, 1200, 120], fill=(14, 15, 18))
    g.rectangle([100, 300, 500, 380], fill=(255, 77, 31))
    s.save(d / "home.png")
    lines = ["Acme brand guide", "Primary colour: #FF4D1F", "Ink: RGB 14 15 18", "Mint: #3DDC97",
             "Headline font: Acme Grotesk", 'Tagline: "Ship it faster"']
    if pdf:
        minimal_pdf(d / "guide.pdf", lines)
    else:
        (d / "guide.txt").write_text("\n".join(lines) + "\n")
    return d


def brand_project(pdf=False):
    root = tmpdir()
    inp = brand_inputs(root / "in", pdf)
    proj = root / "p"
    r = run_script("ingest.py", proj, inp)
    assert r.returncode == 0, r.stdout + r.stderr
    return proj


def brand(proj, *args, env=None):
    import subprocess
    r = subprocess.run([sys.executable, str(helpers.SCRIPTS / "brand.py"), str(proj), *args],
                       capture_output=True, text=True, env=env, timeout=120)
    return r, json.loads((proj / "brand.json").read_text()) if (proj / "brand.json").exists() else None


class Brand(unittest.TestCase):
    def test_palette_guide_wordmark_copy(self):
        proj = brand_project()
        r, b = brand(proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        hexes = [c["hex"] for c in b["colors"]]
        self.assertEqual(hexes[:3], ["#ff4d1f", "#0e0f12", "#3ddc97"])                  # guide colours first, exact
        accent = b["colors"][0]
        self.assertTrue(accent["guide"])
        self.assertNotEqual(accent["measured"], "#ff4d1f")                               # measured from the logo
        self.assertGreater(accent["share"], 0.3)
        mint = next(c for c in b["colors"] if c["hex"] == "#3ddc97")
        self.assertEqual((mint["share"], mint["sources"]), (0.0, ["guide"]))             # named only in the guide
        self.assertIn("#fafaf8", hexes)
        self.assertAlmostEqual(sum(c["share"] for c in b["colors"]), 1, delta=0.02)
        self.assertEqual(b["roles"], {"bg": "#fafaf8", "ink": "#0e0f12", "accent": "#ff4d1f"})
        self.assertEqual(b["wordmark"]["asset"], "acme-logo")
        self.assertEqual(b["wordmark"]["on"], "dark")
        self.assertEqual(b["copy"], [{"label": "tagline", "text": "Ship it faster"}])
        self.assertEqual(b["fonts"]["display"]["family"], "Acme Grotesk")
        self.assertFalse(b["fonts"]["display"]["supplied"])
        self.assertTrue(any("not supplied" in n for n in b["notes"]))
        self.assertFalse(b["confirmed"])
        self.assertTrue((proj / "docs" / "brand_swatch.png").stat().st_size > 1000)
        self.assertIn("Ship it faster", (proj / "docs" / "brand-guide.txt").read_text())
        self.assertTrue((proj / "brand.js").read_text().startswith("window.BRAND = {"))

    def test_confirm_and_overrides_persist(self):
        proj = brand_project()
        brand(proj)
        r, b = brand(proj, "--role", "bg=#0E0F12", "--role", "accent=#3ddc97", "--font", "display=Acme Grotesk", "--confirm")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(b["roles"]["bg"], "#0e0f12")
        self.assertEqual(b["roles"]["accent"], "#3ddc97")
        self.assertEqual(b["roles"]["ink"], "#fafaf8")                                   # re-derived against the new bg
        self.assertTrue(b["confirmed"])
        _, b2 = brand(proj)                                                              # plain re-run keeps them
        self.assertEqual((b2["roles"], b2["confirmed"]), (b["roles"], True))
        _, b3 = brand(proj, "--role", "ink=#ffffff")                                     # a change needs re-confirming
        self.assertFalse(b3["confirmed"])
        r, _ = brand(proj, "--role", "bg=red")
        self.assertNotEqual(r.returncode, 0)

    def test_supplied_font_fills_roles(self):
        from test_ingest import find_system_ttf
        ttf = find_system_ttf()
        if ttf is None:
            self.skipTest("no system .ttf font found to copy")
        root = tmpdir()
        shutil.copyfile(ttf, root / "Brand Sans.ttf")
        proj = root / "p"
        run_script("ingest.py", proj, root / "Brand Sans.ttf")
        r, b = brand(proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        fam = json.loads((proj / "assets" / "assets.json").read_text())["assets"][0]["family"]
        self.assertEqual((b["fonts"]["display"]["family"], b["fonts"]["ui"]["family"]), (fam, fam))
        self.assertTrue(b["fonts"]["display"]["supplied"])
        self.assertIn("no colours found", " ".join(b["notes"]))

    def test_pdf_guide(self):
        import importlib.util
        if not (importlib.util.find_spec("pypdf") or shutil.which("pdftotext")):
            self.skipTest("neither pypdf nor pdftotext installed")
        proj = brand_project(pdf=True)
        r, b = brand(proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("#3ddc97", [c["hex"] for c in b["colors"]])
        self.assertEqual(b["copy"][0]["text"], "Ship it faster")

    def test_pdf_without_reader_degrades_with_message(self):
        import importlib.util
        if importlib.util.find_spec("pypdf"):
            self.skipTest("pypdf installed; the no-reader path can't be simulated")
        proj = brand_project(pdf=True)
        r, b = brand(proj, env=dict(os.environ, PATH=str(Path(sys.executable).parent)))
        if shutil.which("pdftotext", path=str(Path(sys.executable).parent)):
            self.skipTest("pdftotext sits next to python")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any("pip install pypdf" in n for n in b["notes"]), b["notes"])
        self.assertIn("#fafaf8", [c["hex"] for c in b["colors"]])                     # images still analysed

    def test_needs_ingest_first(self):
        r = run_script("brand.py", tmpdir())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ingest", r.stderr)


if __name__ == "__main__":
    unittest.main()
