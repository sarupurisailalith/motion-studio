"""E12 footage-led videos (and E6.1/E6.2): transcribe.py, cut.py, story.py, the footage gates,
windowed clips (kit.js) and kit-footage.js / footage-composition.html.

All audio and video here is synthetic (ffmpeg testsrc + speech-like tone bursts): no real
voices, people or transcripts.
"""
import json, os, shutil, subprocess, sys, unittest, wave
from pathlib import Path

import numpy as np

import helpers
import speechlike as sp
from helpers import tmpdir

sys.path.insert(0, str(helpers.SCRIPTS))
import _footage_gates as fg  # noqa: E402

ENV = dict(os.environ, MOTION_NO_WHISPER="1")
FIX = helpers.FIXTURES / "footage"


def run(name, *args, env=ENV, timeout=600):
    return subprocess.run([sys.executable, str(helpers.SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, env=env, timeout=timeout)


def report(r):
    return helpers.parse_report(r.stdout)


def read_wav(path):
    with wave.open(str(path)) as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        b = np.frombuffer(w.readframes(n), np.uint8)
    if sw == 2:
        x = b.view("<i2").astype(np.float64) / 32768
    else:  # 24-bit
        b = b.reshape(-1, 3)
        x = ((b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)) << 8 >> 8) / 8388608
    return x.reshape(-1, ch)[:, 0], sr


def voice_project(phrases, seed=1, d=None, level=0.3, script=True, **kw):
    d = Path(d or tmpdir())
    x, marks, dur = sp.speech(phrases, seed=seed, level=level, **kw)
    wav = sp.write(d / f"voice{seed}.wav", x)
    lines = [" ".join(w if isinstance(w, str) else w[0] for w in p) for p in phrases]
    (d / "script.txt").write_text("\n".join(lines) + "\n")
    return d, wav, marks, dur


CLIPS = {   # three test clips: plain, with a filler, with a long pause and "you know"
    "a": [["Meet", "Lumen,", "the", "notebook"], ["that", "files", "itself."], ["Try", "it", "free", "today."]],
    "b": [["So", "um", "this", "is", "the", "part"], ["we", "rebuilt", "from", "scratch"], ["and", "it", "is", "fast"]],
    "c": [["Three", "clicks", "to", "publish"], [("Ninety", 1.0), "nine", "percent", "uptime"], ["you", "know", "it", "works"]],
}


@helpers.needs_ffmpeg
class Transcribe(unittest.TestCase):
    def test_script_word_starts_within_80ms(self):
        for k, ph in CLIPS.items():
            for one_line in (False, True):
                d, wav, marks, _ = voice_project(ph, seed=ord(k))
                if one_line:   # no phrase lines: words spread by weight, then by dips
                    (d / "script.txt").write_text(" ".join((d / "script.txt").read_text().split()))
                r = run("transcribe.py", d, wav, "--script", d / "script.txt")
                self.assertEqual(r.returncode, 0, r.stderr)
                tr = json.loads((d / "transcript.json").read_text())
                self.assertEqual([w["w"] for w in tr["words"]], [m[0] for m in marks])
                errs = [abs(w["t0"] - m[1]) for w, m in zip(tr["words"], marks)]
                self.assertLess(max(errs), 0.080, f"clip {k} one_line={one_line}: {errs}")
                self.assertEqual([w["id"] for w in tr["words"]], [f"w{i}" for i in range(len(marks))])
                self.assertTrue((d / "transcript.js").read_text().startswith("window.TRANSCRIPT = "))

    def test_fillers_and_long_pauses_listed(self):
        d, wav, _, _ = voice_project(CLIPS["b"], seed=2)
        run("transcribe.py", d, wav, "--script", d / "script.txt")
        tr = json.loads((d / "transcript.json").read_text())
        self.assertEqual([f["w"] for f in tr["fillers"]], ["um"])
        d, wav, _, _ = voice_project(CLIPS["c"], seed=3)
        run("transcribe.py", d, wav, "--script", d / "script.txt")
        tr = json.loads((d / "transcript.json").read_text())
        self.assertEqual([f["w"] for f in tr["fillers"]], ["you know"])
        self.assertTrue(any(s["long"] and s["dur"] >= 0.95 for s in tr["silences"]), tr["silences"])
        p = tr["phrases"][0]
        self.assertEqual((p["id"], p["from"]), ("p0", "w0"))

    def test_no_whisper_no_script_degrades_with_hint(self):
        d, wav, _, _ = voice_project(CLIPS["a"], seed=4)
        r = run("transcribe.py", d, wav)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("install faster-whisper to enable word timings", r.stderr)
        tr = json.loads((d / "transcript.json").read_text())
        self.assertEqual((tr["engine"], tr["words"]), ("silence", []))
        self.assertEqual(len(tr["phrases"]), 3)
        self.assertIn("install faster-whisper", tr["notes"][0])

    def test_whisper_engine_missing_exits_with_hint(self):
        d, wav, _, _ = voice_project(CLIPS["a"], seed=5)
        r = run("transcribe.py", d, wav, "--engine", "whisper")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("install faster-whisper", r.stderr)

    def test_video_id_uses_its_clip_audio(self):
        d, wav, marks, dur = voice_project(CLIPS["a"], seed=6)
        mp4 = d / "talk.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x64:rate=30:duration={dur}",
                        "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
                        str(d / "talk.mov")], check=True)
        r = helpers.run_script("ingest.py", d / "P", d / "talk.mov", "--clip-fps", "30")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run("transcribe.py", d / "P", "talk", "--script", d / "script.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        tr = json.loads((d / "P" / "transcript.json").read_text())
        self.assertEqual((tr["clip"], tr["audio"]), ("talk", "talk-audio"))
        self.assertLess(max(abs(w["t0"] - m[1]) for w, m in zip(tr["words"], marks)), 0.08)
        del mp4

    def test_snap_phrases_to_beats_unstretched(self):
        """E6.1: each phrase starts within 1 frame of a beat and is not time-stretched."""
        d, wav, marks, dur = voice_project(CLIPS["a"], seed=7)
        beats = {"bpm": 100, "period": 0.6, "offset": 0, "duration": 12,
                 "beats": [round(i * 0.6, 6) for i in range(20)], "downbeats": [round(i * 2.4, 6) for i in range(5)]}
        (d / "beats.json").write_text(json.dumps(beats))
        r = run("transcribe.py", d, wav, "--script", d / "script.txt", "--snap", d / "beats.json", "--every", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        vo = json.loads((d / "vo.json").read_text())
        self.assertEqual(vo["stretch"], 0.0)
        grid = beats["beats"][::2]
        src, sr = read_wav(wav)
        out, sr2 = read_wav(d / "audio" / "vo.wav")
        self.assertEqual(sr2, 48000)
        self.assertAlmostEqual(len(out) / sr2, 12.0, places=3)
        for p in vo["phrases"]:
            self.assertIn(p["beat"], grid)
            self.assertLessEqual(abs(p["t0"] - p["beat"]), 1 / 60)    # within 1 frame at 60 fps
            # the phrase audio is the source audio, sample for sample (no stretch), at its new place
            n = int((p["src_t1"] - p["src_t0"]) * 48000)
            a = src[int(p["src_t0"] * 48000):][:n]
            b = out[int(round(p["t0"] * 48000)):][:n]
            self.assertLess(float(np.abs(a - b).max()), 2e-3, p["id"])
        starts = [p["t0"] for p in vo["phrases"]]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue((d / "vo.js").exists())


def footage_project(phrases=None, seed=21, level=0.3, d=None, name="talk", fps=30):
    """ingested mp4 (testsrc + speech-like audio) + transcript.json -> (P, marks)."""
    d = Path(d or tmpdir())
    ph = phrases or [["So", "um", "this", "is", "the", "part"], ["we", "built", "we", "built", "it", "right"],
                     ["from", "scratch"], ["and", "it", "is", "fast"]]
    x, marks, dur = sp.speech(ph, seed=seed, level=level, phrase_gap=(0.7, 0.9))
    raw = d / f"raw_{name}"
    raw.mkdir(parents=True, exist_ok=True)
    sp.write(raw / "v.wav", x)
    (raw / "script.txt").write_text("\n".join(" ".join(p) for p in ph) + "\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate={fps}:duration={dur}",
                    "-i", str(raw / "v.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le",
                    str(raw / f"{name}.mov")], check=True)
    P = d / "P"
    r = helpers.run_script("ingest.py", P, raw / f"{name}.mov", "--clip-fps", fps)
    assert r.returncode == 0, r.stderr
    r = run("transcribe.py", P, name, "--script", raw / "script.txt", "--out", f"transcript_{name}" if name != "talk" else "transcript")
    assert r.returncode == 0, r.stderr
    return P, marks


@helpers.needs_ffmpeg
class Cut(unittest.TestCase):
    def test_suggest_cuts_filler_pause_retake(self):
        P, marks = footage_project()
        r = run("cut.py", "suggest", P)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = json.loads((P / "edl.json").read_text())
        reasons = " ".join(x["reason"] for x in e["removed"])
        for k in ("filler", "pause", "retake"):
            self.assertIn(k, reasons)
        self.assertTrue(any("we built" in x["words"] for x in e["removed"] if "retake" in x["reason"]), e["removed"])
        fps = e["fps"]
        for ev in e["edl"]:
            for k in ("in", "out", "at"):
                self.assertAlmostEqual(ev[k] * fps, round(ev[k] * fps), places=3)   # whole frames
        # contiguous timeline, jump flags on the cuts inside the clip
        for a, b in zip(e["edl"], e["edl"][1:]):
            self.assertAlmostEqual(a["at"] + a["out"] - a["in"], b["at"], places=4)
            self.assertTrue(b["jump"])
        self.assertTrue((P / "edl.js").read_text().startswith("window.EDL = "))
        # every kept word stays whole: no cut inside a word (except the removed ones)
        tr = json.loads((P / "transcript.json").read_text())
        for w in tr["words"]:
            inside = [ev for ev in e["edl"] if ev["in"] < w["t1"] and w["t0"] < ev["out"]]
            if inside:
                self.assertTrue(any(ev["in"] <= w["t0"] + 1e-6 and w["t1"] <= ev["out"] + 1e-6 for ev in inside), w)

    def test_voice_stem_matches_edl_and_syncs(self):
        P, _ = footage_project()
        run("cut.py", "suggest", P)
        r = run("cut.py", "voice", P)
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = report(r)
        e = json.loads((P / "edl.json").read_text())
        self.assertAlmostEqual(rep["duration"], e["duration"], places=3)
        r = run("cut.py", "sync", P / "audio" / "voice.wav", "--edl", P / "edl.json")
        self.assertEqual(r.returncode, 0, r.stdout)
        rep = report(r)
        self.assertTrue(rep["status"].startswith("pass"), rep)
        for s in rep["segments"]:
            if "offset_ms" in s:
                self.assertLess(abs(s["offset_ms"]), 1.0, s)

    def test_av_sync_fails_on_a_shifted_voice(self):
        """E12.11(c) failing fixture: the voice slipped 80 ms (2.4 frames at 30 fps)."""
        P, _ = footage_project()
        run("cut.py", "suggest", P)
        run("cut.py", "voice", P)
        x, sr = read_wav(P / "audio" / "voice.wav")
        sp.write(P / "late.wav", np.concatenate([np.zeros(int(0.08 * sr)), x])[:len(x)], sr)
        r = run("cut.py", "sync", P / "late.wav", "--edl", P / "edl.json")
        self.assertEqual(r.returncode, 1, r.stdout)
        rep = report(r)
        self.assertTrue(rep["status"].startswith("FAIL"), rep)
        self.assertTrue(any(abs(s.get("offset_ms", 0) - 80) < 1 for s in rep["segments"]), rep)

    def test_check_py_av_sync_gate_on_mp4(self):
        """check.py --edl: pass on the muxed mix (voice + music), FAIL when the voice slipped."""
        P, _ = footage_project()
        run("cut.py", "suggest", P)
        run("cut.py", "voice", P, "--clean")
        e = json.loads((P / "edl.json").read_text())
        D = e["duration"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"aevalsrc='0.2*sin(2*PI*220*t)+0.12*sin(2*PI*330*t)':s=48000:d={D}", str(P / "music.wav")], check=True)
        for name, vo in (("ok", P / "audio" / "voice.wav"), ("late", None)):
            if vo is None:
                x, sr = read_wav(P / "audio" / "voice.wav")
                vo = sp.write(P / "late.wav", np.concatenate([np.zeros(int(0.1 * sr)), x])[:len(x)], sr)
            mp4 = P / f"{name}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=30:d={D}",
                            "-pix_fmt", "yuv420p", str(mp4)], check=True)
            r = run("mix.py", "--duration", D, "--music", P / "music.wav", "--vo", vo, "--out", P / f"mix_{name}.wav",
                    "--mux", mp4)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = helpers.run_script("check.py", mp4, "--edl", P / "edl.json", "--no-sheet")
            g = report(r)["gates"]["av_sync"]
            if name == "ok":
                self.assertTrue(g.startswith("pass"), g)
            else:
                self.assertTrue(g.startswith("FAIL"), g)
                self.assertEqual(r.returncode, 1)

    def test_clean_matches_segment_loudness(self):
        """E12.12: two takes recorded 8 dB apart, cut together, come out within ±1 LU."""
        d = tmpdir()
        P, _ = footage_project(d=d, level=0.35, seed=31)
        footage_project(d=d, level=0.35 * 10 ** (-8 / 20), seed=32, name="take2")
        a = json.loads((P / "transcript.json").read_text())["phrases"]
        b = json.loads((P / "transcript_take2.json").read_text())["phrases"]
        edl = [{"clip": "talk", "in": round(a[0]["t0"] - 0.1, 2), "out": round(a[0]["t1"] + 0.1, 2)},
               {"clip": "take2", "in": round(b[1]["t0"] - 0.1, 2), "out": round(b[1]["t1"] + 0.1, 2)},
               {"clip": "talk", "in": round(a[2]["t0"] - 0.1, 2), "out": round(a[2]["t1"] + 0.1, 2)},
               {"clip": "take2", "in": round(b[3]["t0"] - 0.1, 2), "out": round(b[3]["t1"] + 0.1, 2)}]
        (P / "edl.json").write_text(json.dumps(edl))
        raw = report(run("cut.py", "voice", P, "--out", P / "raw.wav"))
        self.assertNotIn("lufs_spread", raw)
        r = run("cut.py", "voice", P, "--clean")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = report(r)
        lufs = [e["lufs"] for e in rep["events"] if e["lufs"] is not None]
        self.assertEqual(len(lufs), 4, rep)
        self.assertLessEqual(max(lufs) - min(lufs), 2.0, rep)          # ±1 LU around the median
        self.assertEqual(rep["status"], "pass")
        # never time-stretched: the stem is exactly the EDL's length, and cuts still sync
        e = json.loads((P / "edl.json").read_text())
        self.assertAlmostEqual(rep["duration"], e["duration"], places=3)
        r = run("cut.py", "sync", P / "audio" / "voice.wav", "--edl", P / "edl.json")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_bad_edl_refused(self):
        P, _ = footage_project()
        (P / "edl.json").write_text(json.dumps([{"clip": "talk", "in": 1, "out": 0.5}]))
        r = run("cut.py", "voice", P)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("must be after in", r.stderr)
        (P / "edl.json").write_text(json.dumps([{"clip": "talk", "in": 0, "out": 2, "at": 0},
                                                {"clip": "talk", "in": 3, "out": 4, "at": 1}]))
        r = run("cut.py", "voice", P)
        self.assertIn("overlaps", r.stderr)


class Claims(unittest.TestCase):
    TR = {"clip": "talk", "words": [{"id": "w0", "w": "Exports", "t0": 0, "t1": .3}, {"id": "w1", "w": "are", "t0": .4, "t1": .5},
                                    {"id": "w2", "w": "three", "t0": .6, "t1": .8}, {"id": "w3", "w": "times", "t0": .9, "t1": 1},
                                    {"id": "w4", "w": "faster.", "t0": 1.1, "t1": 1.4}]}
    LINES = ["Lumen exports notebooks 3x faster than v1 (lumen.example/changelog)", ""]

    def test_claims(self):
        ok = [("three times faster.", "w2-w4"), ("Exports", "w0"), ("“Exports are three times faster”", "w0-w4"),
              ("3x faster", "source:1"), ("Exports notebooks", "source:1"), ("Lumen", "label")]
        bad = [("four times faster", "w2-w4", "doesn't match"), ("99% faster", "source:1", "99"),
               ("3x faster", "source:2", "no line 2"), ("Up 40%", "label", "label"), ("3x", None, "no data-claim"),
               ("faster", "w9", "not in transcript"), ("Something else entirely", "source:1", "no word")]
        for text, c in ok:
            self.assertIsNone(fg.check_claim(text, c, self.TR, self.LINES), (text, c))
        for text, c, why in bad:
            self.assertIn(why, fg.check_claim(text, c, self.TR, self.LINES) or "", (text, c))

    def test_timeline_mapping(self):
        edl = {"edl": [{"clip": "talk", "in": 0.5, "out": 1.0, "at": 0}, {"clip": "talk", "in": 2.0, "out": 3.0, "at": 0.5}]}
        self.assertAlmostEqual(fg.timeline_t(self.TR, edl, 0.6), 0.1)
        self.assertAlmostEqual(fg.timeline_t(self.TR, edl, 2.5), 1.0)
        self.assertIsNone(fg.timeline_t(self.TR, edl, 1.5))
        self.assertEqual(fg.timeline_t(self.TR, None, 1.5), 1.5)


@helpers.needs_ffmpeg
class Story(unittest.TestCase):
    def setUp(self):
        self.P, _ = footage_project(seed=41)
        run("cut.py", "suggest", self.P)
        (self.P / "docs").mkdir(exist_ok=True)
        (self.P / "docs" / "source.md").write_text("Rebuilt in 2025 from scratch (example.com/blog)\n")

    def write(self, segs):
        (self.P / "story.json").write_text(json.dumps({"version": 1, "clip": "talk", "segments": segs}))
        return run("story.py", self.P)

    def test_good_story_writes_js(self):
        r = self.write([{"id": "s0", "role": "hook", "from": "w2", "to": "w5", "layout": "full",
                         "cues": [{"kind": "keyword", "text": "scratch", "at": "w13"},
                                  {"kind": "stat", "value": "2025", "label": "rebuilt", "at": "w13", "claim": "source:1"},
                                  {"kind": "quote", "from": "w12", "to": "w13"}]}])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue((self.P / "story.js").read_text().startswith("window.STORY = "))

    def test_bad_story_lists_every_problem(self):
        (self.P / "story.js").unlink(missing_ok=True)
        r = self.write([{"id": "s0", "role": "teaser", "from": "w1", "to": "w99", "layout": "pip",
                         "cues": [{"kind": "keyword", "text": "fastest ever", "at": "w2"},
                                  {"kind": "stat", "value": "99%", "label": "uptime", "at": "w2", "claim": "source:1"},
                                  {"kind": "sparkle", "at": "w2"}]}])
        self.assertEqual(r.returncode, 1)
        probs = " ".join(report(r)["problems"])
        for frag in ("role 'teaser'", "layout 'pip'", "w99", "cut by edl.json", "fastest ever", "99", "unknown kind"):
            self.assertIn(frag, probs)
        self.assertFalse((self.P / "story.js").exists())


# ------------------------------------------------------------------------------ browser tests
def gate_fixture(case, words=None, edl=None):
    d = tmpdir()
    shutil.copy2(FIX / "cues.html", d / "cues.html")
    for f in ("kit.js", "kit-footage.js"):
        shutil.copy2(helpers.TEMPLATES / f, d / f)
    words = words or [{"id": f"w{i}", "w": w, "t0": round(0.3 + 0.5 * i, 3), "t1": round(0.3 + 0.5 * i + 0.35, 3),
                       "phrase": "p0" if i < 4 else "p1"}
                      for i, w in enumerate(["Exports", "are", "three", "times", "faster.", "Try", "it", "now."])]
    tr = {"version": 1, "clip": "talk", "words": words}
    (d / "transcript.json").write_text(json.dumps(tr))
    (d / "transcript.js").write_text(f"window.TRANSCRIPT = {json.dumps(tr)};\n")
    (d / "edl.js").write_text(f"window.EDL = {json.dumps(edl)};\n")
    if edl:
        (d / "edl.json").write_text(json.dumps(edl))
    (d / "case.js").write_text(f"window.CASE = {json.dumps(case)};\n")
    (d / "docs").mkdir()
    (d / "docs" / "source.md").write_text("Exports are 3x faster than v1 (example.com/changelog)\n")
    return d / "cues.html"


@helpers.slow
@helpers.needs_chromium
class FootageGates(unittest.TestCase):
    CUES = [{"kind": "keyword", "text": "three times", "at": "w2", "until": "w4"},
            {"kind": "stat", "value": "3x", "label": "faster", "at": "w4", "until": "w6", "claim": "source:1"},
            {"kind": "lower-third", "name": "Ada", "role": "Founder", "at": "w5"}]

    def gates(self, html):
        r = helpers.run_script("render.py", html, "--check-only", "--quiet")
        return report(r)["gates"]

    def test_cue_timing_pass(self):
        g = self.gates(gate_fixture({"duration": 4.5, "cues": self.CUES, "captions": True}))
        self.assertTrue(g["cue_timing"].startswith("pass (3 cues, worst 0.0 frames)"), g)
        self.assertTrue(g["claim_trace"].startswith("pass"), g)
        self.assertTrue(g["contrast"].startswith("pass"), g)      # every component sits on a plate
        self.assertEqual(g["page_errors"], "none")

    def test_cue_timing_fail_when_late(self):
        g = self.gates(gate_fixture({"duration": 4.5, "cues": self.CUES, "late": 0.2}))
        self.assertTrue(g["cue_timing"].startswith("FAIL"), g)
        self.assertIn("+6.0 frames", g["cue_timing"])

    def test_cue_timing_through_edl(self):
        """Words on the source timeline, cues on the edited one: w4 at source 2.3 s plays at 1.1 s."""
        edl = {"fps": 30, "clip": "talk", "edl": [{"clip": "talk", "in": 0.3, "out": 1.2, "at": 0},
                                                  {"clip": "talk", "in": 2.1, "out": 4.2, "at": 0.9}]}
        cues = [{"kind": "stat", "value": "3x", "label": "faster", "at": "w4", "claim": "source:1"}]
        g = self.gates(gate_fixture({"duration": 3.0, "cues": cues}, edl=edl))
        self.assertTrue(g["cue_timing"].startswith("pass (1 cues"), g)

    def test_claim_trace_fail(self):
        cues = [{"kind": "keyword", "text": "99% faster", "at": "w2", "claim": "source:1"},
                {"kind": "lower-third", "name": "Ada", "role": "Up 40% this year", "at": "w5"}]
        g = self.gates(gate_fixture({"duration": 4.5, "cues": cues}))
        self.assertTrue(g["claim_trace"].startswith("FAIL"), g)
        self.assertIn("99 not in docs/source.md line 1", g["claim_trace"])
        self.assertIn("label can't carry numbers", g["claim_trace"])

    def test_plain_compositions_get_no_footage_gates(self):
        d = tmpdir()
        shutil.copy2(helpers.TEMPLATES / "composition.html", d / "c.html")
        shutil.copy2(helpers.TEMPLATES / "kit.js", d / "kit.js")
        g = self.gates(d / "c.html")
        self.assertNotIn("cue_timing", g)
        self.assertNotIn("claim_trace", g)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def open(self, html, vp=(640, 360)):
        ctx = self.browser.new_context(viewport={"width": vp[0], "height": vp[1]})
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(Path(html).as_uri() + "?render=1")
        page.wait_for_function("window.MOTION && window.seek && window.ready")
        page.evaluate("window.ready")
        return page, errors


def seq_project(n=60, size=(64, 48), fps=30):
    """A JPEG sequence clip (frame i has colour (i*4 % 256, 80, 255 - i*4 % 256)) + a windowed and
    a preloaded page drawing it."""
    from PIL import Image
    d = tmpdir()
    fr = d / "assets" / "video" / "c"
    fr.mkdir(parents=True)
    for i in range(n):
        Image.new("RGB", size, ((i * 4) % 256, 80, 255 - (i * 4) % 256)).save(fr / f"{i:05d}.jpg", quality=95)
    a = {"id": "c", "kind": "video", "path": "assets/video/c/", "fps": fps, "frame_count": n, "w": size[0], "h": size[1],
         "duration": n / fps, "pattern": "assets/video/c/%05d.jpg"}
    (d / "assets.js").write_text("window.ASSETS = " + json.dumps({"version": 1, "assets": [a]}) + ";\n")
    shutil.copy2(helpers.TEMPLATES / "kit.js", d / "kit.js")
    for mode, opts in (("full", "{}"), ("win", "{ window: 0.5, ahead: 0.2 }")):
        (d / f"{mode}.html").write_text(f"""<!doctype html><html><body style="margin:0">
<canvas id="c" width="200" height="200"></canvas>
<script src="assets.js"></script><script src="kit.js"></script><script>
window.MOTION = K.init({{ width: 200, height: 200, fps: {fps}, duration: {n / fps}, loop: false }});
const clip = ASSETS.assets[0], ctx = document.getElementById('c').getContext('2d');
window.ready = K.loadClip(clip, {opts});
window.seek = async t => {{ await window.ready; await K.clipSeek(clip, t); K.drawClip(ctx, clip, t, 0, 0, 200, 200); }};
</script></body></html>""")
    return d


@helpers.slow
@helpers.needs_chromium
class WindowedClips(Page):
    def test_windowed_identical_to_preload(self):
        d = seq_project()
        full, e1 = self.open(d / "full.html", (200, 200))
        win, e2 = self.open(d / "win.html", (200, 200))
        for t in [0, 1.95, 0.5, 1.0, 0.033, 1.5, 0.5, 0.0]:
            for p in (full, win):
                p.evaluate("t => window.seek(t)", t)
            self.assertEqual(full.screenshot(), win.screenshot(), f"t={t}")
        self.assertEqual(e1 + e2, [])

    def test_windowed_memory_stays_bounded(self):
        d = seq_project(n=900, size=(32, 24))      # 30 s at 30 fps
        page, errors = self.open(d / "win.html", (200, 200))
        cap = page.evaluate("K.clipStats(clip).cap")
        self.assertLessEqual(cap, 40)              # (2 * 0.5 + 0.2) s * 30 fps + 2
        peak = 0
        for f in list(range(0, 900, 7)) + [899, 3, 450]:
            page.evaluate("t => window.seek(t)", f / 30)
            peak = max(peak, page.evaluate("K.clipStats(clip).resident"))
        self.assertLessEqual(peak, cap)
        self.assertEqual(errors, [])

    def test_windowed_needs_clipseek(self):
        d = seq_project()
        page, _ = self.open(d / "win.html", (200, 200))
        err = page.evaluate("() => { try { K.drawClip(ctx, clip, 1.5); return ''; } catch (e) { return e.message; } }")
        self.assertIn("await K.clipSeek", err)

    def test_windowed_determinism_gate(self):
        d = seq_project()
        r = helpers.run_script("render.py", d / "win.html", "--check-only")
        g = report(r)["gates"]
        self.assertEqual((g["determinism"], g["page_errors"]), ("pass", "none"), g)


@helpers.slow
@helpers.needs_chromium
class KitFootage(Page):
    def test_edl_word_mapping_and_punch(self):
        edl = {"fps": 30, "clip": "talk", "edl": [{"clip": "talk", "in": 0.3, "out": 1.2, "at": 0, "jump": False},
                                                  {"clip": "talk", "in": 2.1, "out": 4.2, "at": 0.9, "jump": True}]}
        page, errors = self.open(gate_fixture({"duration": 3.0, "cues": []}, edl=edl))
        s = page.evaluate("K.edl(1.0)")
        self.assertEqual((s["i"], s["clip"], s["jump"]), (1, "talk", True))
        self.assertAlmostEqual(s["clipT"], 2.2, places=6)
        self.assertIsNone(page.evaluate("K.edl(3.5)"))
        self.assertAlmostEqual(page.evaluate("K.wordT('w4')"), 1.1, places=6)     # source 2.3 s
        self.assertAlmostEqual(page.evaluate("K.cue('w4+0.25')"), 1.35, places=6)
        self.assertIn("was cut", page.evaluate("() => { try { K.wordT('w2'); } catch (e) { return e.message; } }"))
        self.assertEqual(page.evaluate("[K.punch(0.5), K.punch(1.5, 1.1)]"), [1, 1.1])
        self.assertEqual(errors, [])

    def test_device_shot_uses_kit_device_frame(self):
        """deviceShot wraps kit.js K.device (E3.4) and covers the screen with the supplied image."""
        from PIL import Image
        html = gate_fixture({"duration": 4.5, "cues": [
            {"kind": "screenshot", "src": "shot.png", "w": 90, "h": 195, "at": "w1", "until": "w5"}]})
        Image.new("RGB", (90, 195), (20, 120, 220)).save(html.parent / "shot.png")
        page, errors = self.open(html)
        page.evaluate("window.seek(1.5)")
        got = page.evaluate("""() => { const w = document.querySelector('.k-device-shot');
          const s = w.querySelector('.k-device-phone .k-device-screen img');
          return { cue: w.dataset.cue, img: !!s && s.naturalWidth, vis: getComputedStyle(w).visibility }; }""")
        self.assertEqual(got, {"cue": "w1", "img": 90, "vis": "visible"})
        self.assertEqual(errors, [])

    def test_caption_groups(self):
        words = [{"id": f"w{i}", "w": w, "t0": 0.2 + 0.3 * i, "t1": 0.2 + 0.3 * i + 0.25, "phrase": "p0"}
                 for i, w in enumerate("one two three four five six seven eight nine. ten eleven".split())]
        page, _ = self.open(gate_fixture({"duration": 4.5, "cues": [], "captions": True}, words=words))
        groups = page.evaluate("K.captionGroups(K.timelineWords()).map(g => g.words.map(w => w.w).join(' '))")
        self.assertEqual(groups, ["one two three four five six seven", "eight nine.", "ten eleven"])
        self.assertTrue(all(len(g.split()) <= 7 for g in groups))
        self.assertEqual(page.evaluate("[...document.querySelectorAll('.k-caption')].map(e => e.dataset.claim)"),
                         ["w0-w6", "w7-w8", "w9-w10"])


@helpers.slow
@helpers.needs_chromium
@helpers.needs_ffmpeg
class FootageTemplate(unittest.TestCase):
    """E12.8: the template on a synthetic ~20 s project — every gate in 16x9 and 9x16, then a full
    render, the voice stem from the same EDL, a mix and check.py with the A/V sync gate."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import footage_demo
        cls.P, _ = footage_demo.build()
        cls.html = footage_demo.add_composition(cls.P)

    def test_gates_pass_in_16x9_and_9x16(self):
        r = helpers.run_script("render.py", self.html, "--format", "16x9,9x16", "--check-only", "--quiet")
        rep = report(r)
        for fmt, f in rep["formats"].items():
            for name, g in f["gates"].items():
                self.assertTrue(g == "none" or str(g).startswith("pass"), f"{fmt} {name}: {g}")
            self.assertIn("cue_timing", f["gates"])

    def test_renders_end_to_end_with_lip_sync(self):
        P = self.P
        r = helpers.run_script("render.py", self.html, "--format", "16x9", "--workers", "4", "--quiet", "--skip-checks",
                               timeout=1800)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mp4 = P / "renders" / "footage-composition_16x9.mp4"
        D = json.loads((P / "edl.json").read_text())["duration"]
        self.assertGreater(D, 18)
        self.assertEqual(run("cut.py", "voice", P, "--clean").returncode, 0)
        r = run("mix.py", "--duration", D, "--vo", P / "audio" / "voice.wav", "--out", P / "audio" / "mix.wav", "--mux", mp4)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = helpers.run_script("check.py", mp4, "--edl", P / "edl.json", "--no-sheet")
        rep = report(r)
        self.assertTrue(rep["gates"]["av_sync"].startswith("pass"), rep["gates"])
        self.assertEqual(rep["gates"]["blank"], "pass")
        self.assertAlmostEqual(rep["frames"] / 30, D, delta=0.1)


if __name__ == "__main__":
    unittest.main()
