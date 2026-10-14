"""Tests for ingest.py (W1-D: local asset intake, E3.6 / E3.7).

Run: python3 -m unittest discover -s tests -p 'test_ingest.py' -v
"""
import json, shutil, subprocess, unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import helpers

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def make_png(path, size=(64, 32), mode="RGB", color=(200, 30, 30)):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)
    return path


def ingest(project, *paths):
    r = helpers.run_script("ingest.py", project, *paths, timeout=300)
    try:
        summary = helpers.parse_report(r.stdout)
    except ValueError:
        summary = None
    return r, summary


def inventory(project):
    return json.loads((Path(project) / "assets" / "assets.json").read_text())


def by_id(project):
    return {a["id"]: a for a in inventory(project)["assets"]}


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.tmpdir()
        self.proj = self.tmp / "proj"

    def test_help(self):
        r = helpers.run_script("ingest.py", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        for flag in ("--attached", "--max-dim", "--clip-fps"):
            self.assertIn(flag, r.stdout)

    def test_ids_dedupe_and_merge_by_orig(self):
        a = make_png(self.tmp / "in1" / "Logo Final.png")
        b = make_png(self.tmp / "in2" / "logo-final.png", color=(0, 0, 255))
        r, s = ingest(self.proj, a, b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        inv = by_id(self.proj)
        self.assertEqual(set(inv), {"logo-final", "logo-final-2"})
        self.assertEqual(inv["logo-final"]["orig"], str(a.resolve()))
        self.assertEqual(inv["logo-final"]["kind"], "image")
        self.assertEqual(inv["logo-final"]["source"], "local")
        self.assertEqual(inv["logo-final"]["path"], "assets/images/logo-final.png")
        self.assertTrue((self.proj / inv["logo-final-2"]["path"]).exists())
        self.assertEqual(inventory(self.proj)["version"], 1)

        # re-ingest the first one after it changed: still two assets, updated in place
        make_png(a, size=(80, 40))
        r, s = ingest(self.proj, a)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        inv = by_id(self.proj)
        self.assertEqual(len(inv), 2)
        self.assertEqual(inv["logo-final"]["w"], 80)

    def test_assets_js_mirrors_json(self):
        a = make_png(self.tmp / "a.png")
        ingest(self.proj, a)
        js = (self.proj / "assets" / "assets.js").read_text().strip()
        self.assertTrue(js.startswith("window.ASSETS = ") and js.endswith(";"), js[:80])
        self.assertEqual(json.loads(js[len("window.ASSETS = "):-1]), inventory(self.proj))

    def test_missing_input_reported_others_ingested(self):
        a = make_png(self.tmp / "ok.png")
        gone = self.tmp / "nope" / "missing.png"
        r, s = ingest(self.proj, gone, a)
        self.assertEqual(r.returncode, 1)
        self.assertIn(str(gone), " ".join(s["missing"]))
        self.assertIn("ok", by_id(self.proj))

    def test_attached_source(self):
        a = make_png(self.tmp / "upload.png")
        r = helpers.run_script("ingest.py", self.proj, a, "--attached")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(by_id(self.proj)["upload"]["source"], "attached")

    def test_folder_recursed_dotfiles_skipped(self):
        d = self.tmp / "folder"
        make_png(d / "top.png")
        make_png(d / "sub" / "deep.png")
        make_png(d / ".hidden.png")
        make_png(d / ".git" / "inside.png")
        (d / ".DS_Store").write_bytes(b"\0\0junk")
        r, s = ingest(self.proj, d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(set(by_id(self.proj)), {"top", "deep"})

    def test_summary_shape(self):
        a = make_png(self.tmp / "x.png")
        r, s = ingest(self.proj, a)
        for key in ("ingested", "missing", "unreadable", "notes"):
            self.assertIn(key, s)
        self.assertEqual(s["ingested"][0]["id"], "x")


class Images(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.tmpdir()
        self.proj = self.tmp / "proj"

    def test_large_png_capped_aspect_kept(self):
        src = make_png(self.tmp / "big.png", size=(5000, 3000))
        r = helpers.run_script("ingest.py", self.proj, src, "--max-dim", "3840")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["big"]
        self.assertEqual((e["w"], e["h"]), (3840, 2304))
        with Image.open(self.proj / e["path"]) as im:
            self.assertEqual(im.size, (3840, 2304))
            self.assertEqual(im.format, "PNG")

    def test_small_png_untouched(self):
        src = make_png(self.tmp / "small.png", size=(300, 200))
        ingest(self.proj, src)
        e = by_id(self.proj)["small"]
        self.assertEqual((e["w"], e["h"], e["alpha"]), (300, 200, False))
        self.assertEqual((self.proj / e["path"]).read_bytes(), src.read_bytes())

    def test_rgba_alpha(self):
        src = self.tmp / "cut.png"
        im = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
        im.putpixel((0, 0), (0, 0, 0, 0))
        im.save(src)
        ingest(self.proj, src)
        self.assertTrue(by_id(self.proj)["cut"]["alpha"])

    def test_jpeg_kept_as_jpeg(self):
        src = self.tmp / "photo.jpg"
        Image.new("RGB", (120, 80), (10, 120, 200)).save(src, quality=90)
        ingest(self.proj, src)
        e = by_id(self.proj)["photo"]
        self.assertTrue(e["path"].endswith(".jpg"), e["path"])
        with Image.open(self.proj / e["path"]) as im:
            self.assertEqual(im.format, "JPEG")
        self.assertFalse(e["alpha"])

    def test_jpeg_exif_rotation_applied(self):
        src = self.tmp / "portrait.jpg"
        im = Image.new("RGB", (120, 80), (10, 120, 200))
        exif = im.getexif()
        exif[0x0112] = 6
        im.save(src, exif=exif)
        ingest(self.proj, src)
        e = by_id(self.proj)["portrait"]
        self.assertEqual((e["w"], e["h"]), (80, 120))
        with Image.open(self.proj / e["path"]) as out:
            self.assertEqual(out.size, (80, 120))

    def test_tiff_bmp_gif_to_png(self):
        Image.new("RGB", (30, 20), (1, 2, 3)).save(self.tmp / "scan.tiff")
        Image.new("RGB", (30, 20), (1, 2, 3)).save(self.tmp / "old.bmp")
        frames = [Image.new("RGB", (30, 20), c) for c in ((255, 0, 0), (0, 0, 255))]
        frames[0].save(self.tmp / "anim.gif", save_all=True, append_images=frames[1:], duration=100)
        r, s = ingest(self.proj, self.tmp / "scan.tiff", self.tmp / "old.bmp", self.tmp / "anim.gif")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        inv = by_id(self.proj)
        for aid in ("scan", "old", "anim"):
            self.assertTrue(inv[aid]["path"].endswith(".png"), inv[aid]["path"])
            with Image.open(self.proj / inv[aid]["path"]) as im:
                self.assertEqual((im.format, im.size), ("PNG", (30, 20)))
        self.assertTrue(any(n["id"] == "anim" and "first frame" in n["note"] for n in s["notes"]), s["notes"])

    def test_bogus_heic_unreadable(self):
        bad = self.tmp / "phone.heic"
        bad.write_bytes(b"definitely not an image")
        ok = make_png(self.tmp / "fine.png")
        r, s = ingest(self.proj, bad, ok)
        self.assertEqual(r.returncode, 1)
        self.assertEqual([u["path"] for u in s["unreadable"]], [str(bad)])
        self.assertEqual(set(by_id(self.proj)), {"fine"})

    @unittest.skipUnless(shutil.which("sips"), "sips (macOS) not available to make a HEIC")
    def test_real_heic_converted(self):
        png = make_png(self.tmp / "h.png", size=(64, 48))
        heic = self.tmp / "camera.heic"
        p = subprocess.run(["sips", "-s", "format", "heic", str(png), "--out", str(heic)], capture_output=True)
        if p.returncode != 0 or not heic.exists():
            self.skipTest("sips can't write HEIC here")
        r, s = ingest(self.proj, heic)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["camera"]
        self.assertTrue(e["path"].endswith(".png"))
        self.assertEqual((e["w"], e["h"]), (64, 48))

    def test_svg_sanitised(self):
        src = helpers.copy_fixture("assets/evil.svg", self.tmp)
        r, s = ingest(self.proj, src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["evil"]
        self.assertEqual(e["kind"], "svg")
        self.assertEqual(e["path"], "assets/svg/evil.svg")
        self.assertEqual((e["w"], e["h"]), (200, 100))
        text = (self.proj / e["path"]).read_text()
        low = text.lower()
        for ns in ('xmlns="http://www.w3.org/2000/svg"', 'xmlns:xlink="http://www.w3.org/1999/xlink"'):
            low = low.replace(ns, "")
        for bad in ("<script", "onload", "onclick", "onmouseover", "javascript:", "http://", "https://",
                    "evil.example", "@import", "foreignobject", "iframe", "xml-stylesheet"):
            self.assertNotIn(bad, low)
        root = ET.fromstring(text)  # still valid XML
        self.assertTrue(root.tag.endswith("svg"))
        ids = {el.get("id") for el in root.iter()}
        for keep in ("box", "dot", "ref", "p", "t"):
            self.assertIn(keep, ids)
        self.assertIn("url(#g)", text)          # internal refs survive
        self.assertIn("#box", text)
        self.assertIn("fill: #0a8", text)       # harmless CSS survives

    def test_svg_size_from_attributes(self):
        src = self.tmp / "mark.svg"
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="512px" height="128" '
                       'viewBox="0 0 10 10"><rect width="10" height="10"/></svg>')
        ingest(self.proj, src)
        e = by_id(self.proj)["mark"]
        self.assertEqual((e["w"], e["h"]), (512, 128))
        self.assertNotIn("ns0:", (self.proj / e["path"]).read_text())

    def test_svg_with_entities_rejected(self):
        src = self.tmp / "bomb.svg"
        src.write_text('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">'
                       '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
                       '<svg xmlns="http://www.w3.org/2000/svg"><text>&b;</text></svg>')
        r, s = ingest(self.proj, src)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(s["unreadable"]), 1)

    def test_broken_svg_unreadable(self):
        src = self.tmp / "broken.svg"
        src.write_text("<svg><rect></svg")
        r, s = ingest(self.proj, src)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(s["unreadable"]), 1)


def find_system_ttf():
    """A real TrueType font from the OS (macOS / common Linux paths), or None."""
    for name in ("/System/Library/Fonts/Geneva.ttf", "/System/Library/Fonts/Monaco.ttf",
                 "/Library/Fonts/Arial Unicode.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(name).exists():
            return Path(name)
    for d in ("/System/Library/Fonts", "/Library/Fonts", "/usr/share/fonts"):
        for f in sorted(Path(d).rglob("*.ttf")) if Path(d).exists() else []:
            return f
    return None


def load_ingest_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ingest", helpers.SCRIPTS / "ingest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Fonts(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.tmpdir()
        self.proj = self.tmp / "proj"

    def test_weight_mapping(self):
        m = load_ingest_module()
        cases = {"Thin": 100, "Hairline": 100, "ExtraLight": 200, "Ultra Light": 200, "Light": 300,
                 "Regular": 400, "Book": 400, "Italic": 400, "Medium": 500, "SemiBold": 600,
                 "Demi Bold": 600, "Bold": 700, "Bold Italic": 700, "ExtraBold": 800,
                 "Ultra Bold": 800, "Black": 900, "Heavy": 900, "Weird": 400}
        for style, w in cases.items():
            self.assertEqual(m.font_weight(style), w, style)
        self.assertEqual(m.font_style("Bold Italic"), "italic")
        self.assertEqual(m.font_style("Oblique"), "italic")
        self.assertEqual(m.font_style("Bold"), "normal")

    def test_ttf_ingested_and_fonts_css(self):
        ttf = find_system_ttf()
        if ttf is None:
            self.skipTest("no system .ttf font found to copy")
        src = self.tmp / "Brand Sans.ttf"
        shutil.copyfile(ttf, src)
        from PIL import ImageFont
        family, style = ImageFont.truetype(str(src), 12).getname()

        r, s = ingest(self.proj, src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["brand-sans"]
        self.assertEqual(e["kind"], "font")
        self.assertEqual(e["path"], "assets/fonts/brand-sans.ttf")
        self.assertEqual((e["family"], e["style"]), (family, style))
        self.assertEqual(e["weight"], load_ingest_module().font_weight(style))

        css = (self.proj / "assets" / "fonts.css").read_text()
        self.assertEqual(css.count("@font-face"), 1)
        self.assertIn('font-family: "%s"' % family, css)
        self.assertIn('src: url("fonts/brand-sans.ttf")', css)
        self.assertIn("font-weight: %d" % e["weight"], css)
        self.assertIn("font-style: normal", css)

        # re-run (same font + another copy): rewritten, no duplicates
        src2 = self.tmp / "other" / "Brand Sans.ttf"
        src2.parent.mkdir()
        shutil.copyfile(ttf, src2)
        r, s = ingest(self.proj, src, src2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        css = (self.proj / "assets" / "fonts.css").read_text()
        self.assertEqual(css.count("@font-face"), 2)
        self.assertEqual(css.count('url("fonts/brand-sans.ttf")'), 1)
        self.assertIn('url("fonts/brand-sans-2.ttf")', css)

    def test_unreadable_font(self):
        bad = self.tmp / "fake.otf"
        bad.write_bytes(b"OTTO but not really a font")
        r, s = ingest(self.proj, bad)
        self.assertEqual(r.returncode, 1)
        self.assertEqual([u["path"] for u in s["unreadable"]], [str(bad)])
        self.assertNotIn("@font-face", (self.proj / "assets" / "fonts.css").read_text())


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True, capture_output=True)


class Media(unittest.TestCase):
    def setUp(self):
        self.tmp = helpers.tmpdir()
        self.proj = self.tmp / "proj"

    @helpers.needs_ffmpeg
    def test_video_to_frame_sequence(self):
        src = self.tmp / "Demo Clip.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=25",
               "-pix_fmt", "yuv420p", src)
        r = helpers.run_script("ingest.py", self.proj, src, "--clip-fps", "10", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["demo-clip"]
        self.assertEqual(e["kind"], "video")
        self.assertEqual(e["path"], "assets/video/demo-clip/")
        self.assertEqual(e["pattern"], "assets/video/demo-clip/%05d.jpg")
        self.assertEqual((e["fps"], e["frame_count"], e["w"], e["h"]), (10, 20, 640, 360))
        self.assertAlmostEqual(e["duration"], 2.0, places=3)
        frames = sorted(p.name for p in (self.proj / e["path"]).iterdir())
        self.assertEqual(frames[0], "00000.jpg")
        self.assertEqual(frames[-1], "00019.jpg")
        self.assertEqual(len(frames), 20)
        with Image.open(self.proj / e["path"] / "00000.jpg") as im:
            self.assertEqual(im.size, (640, 360))

        # re-ingest at a lower rate: the old frames are replaced, not mixed in
        r = helpers.run_script("ingest.py", self.proj, src, "--clip-fps", "5", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["demo-clip"]
        self.assertEqual(e["frame_count"], 10)
        self.assertEqual(len(list((self.proj / e["path"]).iterdir())), 10)

    @helpers.needs_ffmpeg
    def test_video_capped_by_max_dim(self):
        src = self.tmp / "wide.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc=duration=0.4:size=800x400:rate=10", "-pix_fmt", "yuv420p", src)
        r = helpers.run_script("ingest.py", self.proj, src, "--clip-fps", "10", "--max-dim", "400")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["wide"]
        self.assertEqual((e["w"], e["h"]), (400, 200))

    @helpers.needs_ffmpeg
    def test_audio_to_wav_48k(self):
        src = self.tmp / "tone.mp3"
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1.5:sample_rate=44100", src)
        r, s = ingest(self.proj, src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = by_id(self.proj)["tone"]
        self.assertEqual((e["kind"], e["path"], e["sr"]), ("audio", "assets/audio/tone.wav", 48000))
        self.assertAlmostEqual(e["duration"], 1.5, delta=0.06)
        import wave
        with wave.open(str(self.proj / e["path"])) as w:
            self.assertEqual(w.getframerate(), 48000)

    @helpers.needs_ffmpeg
    def test_corrupt_media_unreadable(self):
        bad_v = self.tmp / "broken.mp4"
        bad_v.write_bytes(b"\0" * 64)
        bad_a = self.tmp / "broken.mp3"
        bad_a.write_bytes(b"nope")
        r, s = ingest(self.proj, bad_v, bad_a)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(sorted(u["path"] for u in s["unreadable"]), sorted([str(bad_v), str(bad_a)]))
        self.assertFalse((self.proj / "assets" / "video" / "broken").exists())

    def test_docs_copied(self):
        pdf = self.tmp / "Brand Guide.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake\n")
        txt = self.tmp / "copy.txt"
        txt.write_text("Tagline: fast.")
        odd = self.tmp / "mystery.xyz"
        odd.write_text("?")
        r, s = ingest(self.proj, pdf, txt, odd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        inv = by_id(self.proj)
        self.assertEqual(inv["brand-guide"]["path"], "assets/docs/brand-guide.pdf")
        self.assertEqual(inv["copy"]["kind"], "doc")
        self.assertEqual((self.proj / inv["copy"]["path"]).read_text(), "Tagline: fast.")
        self.assertEqual(inv["mystery"]["kind"], "doc")
        self.assertTrue(any(n["id"] == "mystery" for n in s["notes"]), s["notes"])
        self.assertFalse(any(n["id"] in ("copy", "brand-guide") for n in s["notes"]), s["notes"])


if __name__ == "__main__":
    unittest.main()
