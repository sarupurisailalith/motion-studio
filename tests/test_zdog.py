"""Zdog engine (E10.2–E10.5) and the model catalog (E11.1, E11.2, E11.4, E11.6).
Zdog is vendored at test time (helpers.vendored); every test here skips cleanly when offline."""
import json, shutil, unittest
from pathlib import Path

import helpers
from helpers import parse_report, run_script, tmpdir
from test_kit import Browser

CAT = helpers.SKILL / "catalog"
KIT_FIX = helpers.FIXTURES / "engines"
FORMATS = "16x9,9x16,1x1,4x5"


def zdog_project(html_src, models=("pip", "bolt", "parcel"), name=None):
    """A temp project: html + kit.js + kit-zdog.js + models/ + vendor/ (zdog)."""
    d = tmpdir()
    helpers.with_vendor(d, "zdog")
    for f in ("kit.js", "kit-zdog.js"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    (d / "models").mkdir()
    for m in models:
        shutil.copy2(CAT / "models" / f"{m}.js", d / "models" / f"{m}.js")
    html = d / (name or Path(html_src).name)
    shutil.copy2(html_src, html)
    return html


def check(html, *args):
    r = run_script("render.py", html, "--check-only", *args)
    return r, parse_report(r.stdout)


def assert_all_pass(test, gates, ctx=""):
    test.assertEqual(gates["determinism"], "pass", (ctx, gates))
    if "loop_seam" in gates:
        test.assertTrue(gates["loop_seam"].startswith("pass"), (ctx, gates))
    test.assertTrue(gates["safe_area"].startswith("pass"), (ctx, gates))
    test.assertTrue(gates["text_duration"].startswith("pass"), (ctx, gates))
    test.assertEqual(gates["page_errors"], "none", (ctx, gates))


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class ZdogTemplate(unittest.TestCase):
    def test_demo_passes_every_gate_in_all_formats(self):
        html = zdog_project(helpers.TEMPLATES / "zdog-composition.html", ("pip", "parcel"))
        r, rep = check(html, "--format", FORMATS)
        self.assertEqual(r.returncode, 0, r.stderr)
        for fmt, f in rep["formats"].items():
            assert_all_pass(self, f["gates"], fmt)

    def test_no_illustration_timers_or_drag(self):
        src = (helpers.TEMPLATES / "zdog-composition.html").read_text()
        script = src.split("COMPOSITION SETTINGS")[1].split("RUNTIME (shared")[0]
        for bad in ("Zdog.Illustration", "Dragger", "setTimeout", "setInterval", "Date.now", "Math.random"):
            self.assertNotIn(bad, script, bad)
        self.assertIn("K.Z.render(", src)
        self.assertIn("vendor/zdog.dist.min.js", src)


@helpers.slow
@helpers.needs_chromium
class ZdogKit(Browser):
    """Each K.Z helper (E10.3) on a small fixture page."""

    def page(self):
        return self.open(zdog_project(KIT_FIX / "zdog_kit.html"), viewport={"width": 200, "height": 200})

    def test_canonical_sort_makes_group_ties_history_free(self):
        page, errors = self.page()
        shot = lambda: page.screenshot(clip={"x": 0, "y": 0, "width": 200, "height": 200})
        for naive in (True, False):
            page.evaluate(f"window.NAIVE = {'true' if naive else 'false'}")
            page.evaluate("window.seek(1.5)"); page.evaluate("window.seek(1.5)")
            fresh = shot()
            page.evaluate("window.seek(0.5)"); page.evaluate("window.seek(1.5)")
            after = shot()
            if naive:
                self.assertNotEqual(fresh, after, "fixture should expose Group.updateSort history")
            else:
                self.assertEqual(fresh, after, "K.Z.render must give the same picture in any seek order")
        self.assertEqual(errors, [])

    def test_layer_bias_orders_draws(self):
        page, _ = self.page()
        order = page.evaluate("""(() => {
          const s = new Zdog.Anchor();
          const near = new Zdog.Shape({ addTo: s, translate: { z: 50 }, stroke: 4 });
          const far = new Zdog.Shape({ addTo: s, translate: { z: -50 }, stroke: 4 });
          s.updateGraph(); const before = s.flatGraph.indexOf(near) > s.flatGraph.indexOf(far);
          K.Z.layer(near, K.Z.LAYERS.FAR); s.updateGraph();
          return [before, s.flatGraph.indexOf(near) < s.flatGraph.indexOf(far)];
        })()""")
        self.assertEqual(order, [True, True])

    def test_level_roll(self):
        page, _ = self.page()
        import math
        for yaw, pitch in ((0.3, 0.16), (-0.5, 0.3), (0, 0.4)):
            want = -math.atan2(math.sin(yaw) * math.sin(pitch), math.cos(yaw))
            self.assertAlmostEqual(page.evaluate(f"K.Z.levelRoll({yaw}, {pitch})"), want, places=12)
        # with the roll, the world x axis projects level on screen
        dy = page.evaluate("""(() => {
          const s = new Zdog.Anchor(), c = K.Z.camera(s), p = new Zdog.Anchor({ addTo: c.world, translate: { x: 100 } });
          c.set({ yaw: 0.5, pitch: 0.3, level: true }); s.updateGraph(); return p.renderOrigin.y; })()""")
        self.assertAlmostEqual(dy, 0, places=9)

    def test_squash_preserves_volume_and_pivot(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          const a = new Zdog.Anchor({ translate: { y: 10 } });
          K.Z.squash(a, 0.24, { y: 38 });
          const s = a.scale, pivotAfter = 38 * s.y + a.translate.y;
          return [s.x * s.y * s.z, pivotAfter, s.y]; })()""")
        self.assertAlmostEqual(r[0], 1.0, places=9)
        self.assertAlmostEqual(r[1], 38 + 10, places=9)   # the pivot (feet) stays put
        self.assertAlmostEqual(r[2], 0.76, places=9)

    def test_shadow_follows_and_shrinks(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          const w = new Zdog.Anchor(), c = new Zdog.Anchor({ addTo: w, translate: { x: 5 } });
          const sh = K.Z.shadow(c, x => x > 0 ? -20 : 0, { falloff: 100 });
          const ground = sh.update().scale;
          c.translate.y = -70; sh.update();
          return [ground, sh.shape.scale, sh.shape.translate.x, sh.shape.translate.y]; })()""")
        self.assertEqual(r[0], 1)
        self.assertAlmostEqual(r[1], 0.5, places=9)
        self.assertEqual(r[2], 5)
        self.assertAlmostEqual(r[3], -20.3, places=9)

    def test_extrude_stacks_layers(self):
        page, _ = self.page()
        zs = page.evaluate("""(() => {
          const s = new Zdog.Anchor(), f = new Zdog.Rect({ addTo: s, width: 10, height: 10, color: '#FF0000', fill: true });
          const g = K.Z.extrude(f, 8, 4);
          return [g instanceof Zdog.Group, g.children.map(c => c.translate.z), g.children[0].color, f.addTo === g]; })()""")
        self.assertTrue(zs[0])
        self.assertEqual(zs[1], [-8, -6, -4, -2, 0])
        self.assertNotEqual(zs[2], "#FF0000")      # sides are shaded darker
        self.assertTrue(zs[3])

    def test_shade(self):
        page, _ = self.page()
        lit, dark = page.evaluate("[K.Z.shade('#808080', K.Z.LIGHT), K.Z.shade('#808080', {y: 1})]")
        self.assertEqual(lit, "#808080")
        self.assertLess(int(dark[1:3], 16), 0x80)
        faces = page.evaluate("K.Z.boxFaces('#3F7CFF')")
        self.assertEqual(set(faces), {"color", "topFace", "bottomFace", "leftFace", "rightFace", "rearFace", "frontFace"})

    def test_project_matches_render(self):
        page, _ = self.page()
        p = page.evaluate("""(() => {
          const s = new Zdog.Anchor(), a = new Zdog.Anchor({ addTo: s, translate: { x: 10, y: -5 } });
          K.Z.render(s, ctx, { zoom: 3, cx: 100, cy: 120 }); return K.Z.project(a); })()""")
        self.assertEqual((p["x"], p["y"]), (130, 105))

    def test_make_resolves_palette_slots(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          const s = new Zdog.Anchor(), m = K.Z.make('pip', s, { palette: { primary: '#3366FF' }, scale: 2 });
          const cols = new Set(); s.updateGraph(); s.flatGraph.forEach(i => i.color && cols.add(i.color));
          return [m.palette.primary, m.palette.shade, m.size.h, [...cols], Object.keys(m.joints)]; })()""")
        self.assertEqual(r[0], "#3366FF")
        self.assertNotEqual(r[1], "#C93A12")        # a brand primary derives its own shade
        self.assertEqual(r[2], 160)
        self.assertIn("#3366FF", r[3])
        self.assertNotIn("#FF4D1F", r[3])           # the model's default primary is gone
        for j in ("root", "hips", "spine", "neck", "head", "armL", "armR", "legL", "legR"):
            self.assertIn(j, r[4])

    def test_unknown_model_and_clip_errors(self):
        page, _ = self.page()
        msg = page.evaluate("(() => { try { K.Z.make('nope', new Zdog.Anchor()); } catch (e) { return e.message; } })()")
        self.assertIn("catalog.py use", msg)
        msg = page.evaluate("""(() => { const m = K.Z.make('pip', new Zdog.Anchor()), r = K.Z.rig(m.joints);
          try { r.pose(0, [{ clip: 'moonwalk' }]); } catch (e) { return e.message; } })()""")
        self.assertIn("unknown clip", msg)


@helpers.slow
@helpers.needs_chromium
class Rig(Browser):
    """E10.4: clips are additive, time-shiftable, blendable and reusable across characters."""

    def page(self):
        return self.open(zdog_project(KIT_FIX / "zdog_kit.html"), viewport={"width": 200, "height": 200})

    def test_pose_is_additive_and_resets(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          const m = K.Z.make('pip', new Zdog.Anchor()), rig = K.Z.rig(m.joints), j = m.joints;
          rig.pose(0.6, [{ clip: 'hop', at: 0.3, h: 30 }]); const air = j.root.translate.y;
          rig.pose(0.6, [{ clip: 'hop', at: 0.3, h: 30 }, { clip: 'hop', at: 0.3, h: 30 }]); const twice = j.root.translate.y;
          rig.pose(0.6, [{ clip: 'hop', at: 0.3, h: 30, weight: 0.5 }]); const half = j.root.translate.y;
          rig.pose(0.6, [{ clip: 'hop', at: 1.3, h: 30 }]); const before = j.root.translate.y;
          rig.pose(5, [{ clip: 'hop', at: 0.3, h: 30 }]); const after = [j.root.translate.y, j.hips.scale.y];
          return [air, twice, half, before, after]; })()""")
        air, twice, half, before, after = r
        self.assertLess(air, -10)
        self.assertAlmostEqual(twice, 2 * air, places=9)
        self.assertAlmostEqual(half, air / 2, places=9)
        self.assertEqual(before, 0)                        # time-shifted: not started yet
        self.assertEqual(after, [0, 1])                    # ends exactly at rest (seam-safe)

    def test_loop_clip_crossfade(self):
        page, _ = self.page()
        r = page.evaluate("""(() => {
          const m = K.Z.make('pip', new Zdog.Anchor()), rig = K.Z.rig(m.joints), j = m.joints;
          const L = [{ clip: 'run', at: 0, until: 2, out: 0.5 }];
          const at = t => (rig.pose(t, L), j.legL.rotate.x);
          return [at(0.09), at(1.75), at(3)]; })()""")
        self.assertAlmostEqual(r[0], 0.9, places=2)      # quarter stride: full swing
        self.assertLess(abs(r[1]), abs(r[0]))             # fading out
        self.assertEqual(r[2], 0)

    def test_beat_snapped_clips(self):
        d = zdog_project(KIT_FIX / "zdog_kit.html").parent
        shutil.copy2(helpers.FIXTURES / "kit" / "beats.js", d / "beats.js")
        html = d / "zdog_kit.html"
        html.write_text(html.read_text().replace('<script src="kit.js">', '<script src="beats.js"></script>\n<script src="kit.js">'))
        page, _ = self.open(html, viewport={"width": 200, "height": 200})
        same = page.evaluate("""(() => {
          const m = K.Z.make('pip', new Zdog.Anchor()), rig = K.Z.rig(m.joints), j = m.joints;
          rig.pose(K.T(4) + 0.3, [{ clip: 'hop', at: '4b' }]); const a = j.root.translate.y;
          rig.pose(K.T(4) + 0.3, [{ clip: 'hop', at: K.T(4) }]); return [a, j.root.translate.y]; })()""")
        self.assertEqual(same[0], same[1])
        self.assertLess(same[0], 0)

    def test_second_character_reuses_clips_and_passes_gates(self):
        """bolt (a different model) plays 6 library clips with no timing code of its own."""
        src = (KIT_FIX / "zdog_kit.html").read_text()
        scene = """
const actor = K.Z.make('bolt', scene, { translate: { y: 60 } }), brig = K.Z.rig(actor.joints);
function draw(t) {
  brig.pose(t, [{ clip: 'idle', period: 1 }, { clip: 'hop', at: 0.1, h: 20, air: 0.4 },
    { clip: 'wave', at: 0.9, len: 0.6 }, { clip: 'point', at: 0.2, len: 0.5, side: 'L' },
    { clip: 'run', at: 0.5, until: 0.9, out: 0.2 }, { clip: 'land', at: 1.3 }]);
  K.Z.render(scene, ctx, { zoom: 1, cx: 100, cy: 70 });
}"""
        start = src.index("window.NAIVE = false;")
        end = src.index("window.ready = Promise.resolve();")
        d = zdog_project(KIT_FIX / "zdog_kit.html").parent
        html = d / "bolt.html"
        html.write_text(src[:start] + scene + "\n" + src[end:])
        r, rep = check(html)
        assert_all_pass(self, rep["gates"], "bolt")


class Catalog(unittest.TestCase):
    def test_every_entry_is_complete(self):
        cat = json.loads((CAT / "catalog.json").read_text())
        ids = [e["id"] for e in cat["models"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 12)
        for e in cat["models"]:
            with self.subTest(model=e["id"]):
                for k in ("id", "kind", "tags", "size", "joints", "palette", "clips", "source", "license", "preview", "notes"):
                    self.assertIn(k, e)
                self.assertIn(e["kind"], ("character", "prop", "icon", "scene-kit"))
                js = (CAT / "models" / f"{e['id']}.js").read_text()
                self.assertIn(f"K.Z.model('{e['id']}'", js)
                self.assertNotIn("metafizzy", js.lower())   # originals only (E11.3 not seeded)
                for slot in e["palette"]:
                    self.assertIn(slot, js)
                # colours come from palette slots: hex only in the palette defaults line
                body = js.split("build(", 1)[1]
                self.assertNotRegex(body, r"'#(?!000000|FFFFFF)[0-9A-Fa-f]{6}'", "hard-coded hex in build()")
                png = CAT / e["preview"]
                self.assertTrue(png.exists(), png)
                self.assertLess(png.stat().st_size, 50_000)
        self.assertEqual(sorted(p.stem for p in (CAT / "models").glob("*.js")), sorted(ids))

    def test_characters_share_the_joint_convention(self):
        cat = json.loads((CAT / "catalog.json").read_text())
        chars = [e for e in cat["models"] if e["kind"] == "character"]
        self.assertGreaterEqual(len(chars), 2)
        for e in chars:
            self.assertGreaterEqual(len(e["clips"]), 5)
            self.assertEqual(e["joints"][:3], ["root", "hips", "spine"])

    def test_search_and_list(self):
        r = run_script("catalog.py", "search", "mascot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("pip"), r.stdout)
        r = run_script("catalog.py", "search", "tree", "--json")
        self.assertEqual({e["id"] for e in json.loads(r.stdout)} >= {"pine", "round-tree"}, True)
        r = run_script("catalog.py", "search", "spaceship")
        self.assertIn("no catalog match", r.stdout)
        r = run_script("catalog.py", "list", "--kind", "icon", "--json")
        self.assertTrue(all(e["kind"] == "icon" for e in json.loads(r.stdout)))

    def test_use_copies_models_and_kit(self):
        d = tmpdir()
        r = run_script("catalog.py", "use", d, "pip", "pine")
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in ("models/pip.js", "models/pine.js", "kit.js", "kit-zdog.js"):
            self.assertTrue((d / f).exists(), f)
        self.assertNotEqual(run_script("catalog.py", "use", d, "nope").returncode, 0)


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class Turntables(unittest.TestCase):
    """E11.4: every catalog model renders in a turntable that passes the gates."""

    def test_every_model_turntable_passes(self):
        vend = helpers.vendored("zdog")
        cat = json.loads((CAT / "catalog.json").read_text())
        for e in cat["models"]:
            with self.subTest(model=e["id"]):
                d = tmpdir()
                shutil.copytree(vend, d / "vendor")
                r = run_script("catalog.py", "turntable", e["id"], d)
                self.assertEqual(r.returncode, 0, r.stderr)
                _, rep = check(d / f"{e['id']}_turntable.html")
                assert_all_pass(self, rep["gates"], e["id"])


if __name__ == "__main__":
    unittest.main()
