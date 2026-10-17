"""Builds a synthetic footage project for the E12 tests: a ~20 s talking-clip stand-in (ffmpeg
testsrc picture + speech-like bursts, no real person), its script, docs/source.md and story.json.
Then ingest -> transcribe (script) -> cut suggest -> story.py, like the real workflow."""
import json, shutil, subprocess
from pathlib import Path

import helpers
import speechlike

SCRIPT = [
    "Meet Lumen, the notebook that files itself.",
    "um writing notes is easy",
    "finding them again is the hard part.",
    "Lumen reads every page you write",
    "and tags it for you.",
    "Search answers in under a second.",
    "Exports go out three times faster.",
    "It works offline too.",
    "Try it free at lumen.example.",
]
SOURCE = [
    "Lumen exports notebooks 3x faster than v1 (lumen.example/changelog)",
    "Search returns results in under 1 second on a 10,000-note library (lumen.example/docs/search)",
    "Free plan available at lumen.example (lumen.example/pricing)",
]


def story(tr):
    """Cues keyed to word ids found by text, so the story stays right if timings move."""
    ids = {}
    for w in tr["words"]:
        ids.setdefault(w["w"].strip(".,").lower(), w["id"])
    W = lambda s: ids[s]
    return {"version": 1, "clip": "talk", "focus": [0.5, 0.45], "captions": True, "segments": [
        {"id": "s0", "role": "hook", "from": W("meet"), "to": W("itself"), "layout": "full",
         "claim": "Lumen files your notes", "names": ["Lumen"], "emphasis": [W("lumen")],
         "cues": [{"kind": "keyword", "text": "Lumen", "at": W("lumen"), "until": W("itself"), "sfx": "pop"},
                  {"kind": "lower-third", "name": "Lumen", "role": "The self-filing notebook", "at": W("notebook")}]},
        {"id": "s1", "role": "problem", "from": W("writing"), "to": W("part"), "layout": "split",
         "claim": "finding notes is hard",
         "cues": [{"kind": "quote", "from": W("finding"), "to": W("part"), "at": W("finding")}]},
        {"id": "s2", "role": "feature", "from": W("reads"), "to": W("offline"), "layout": "corner",
         "claim": "it tags, searches fast and exports faster",
         "cues": [{"kind": "feature-list", "title": "What it does", "at": W("reads"), "until": W("offline"),
                   "items": [{"text": "tags it for you", "at": W("tags")},
                             {"text": "Search in under 1 second", "at": W("search"), "claim": "source:2"},
                             {"text": "Exports 3x faster", "at": W("exports"), "claim": "source:1"}]}]},
        {"id": "s3", "role": "cta", "from": W("try"), "to": W("lumen.example"), "layout": "shape",
         "claim": "free plan",
         "cues": [{"kind": "cta", "line": "Try it free", "url": "lumen.example", "at": W("try"), "claim": "source:3"}]},
    ]}


def build(d=None, video_size="640x360"):
    """-> project folder with assets, transcript, edl, story, docs/source.md (no composition)."""
    d = Path(d or helpers.tmpdir())
    raw = d / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    phrases = [ln.split() for ln in SCRIPT]
    x, marks, dur = speechlike.speech(phrases, seed=11, phrase_gap=(0.45, 0.8))
    speechlike.write(raw / "voice.wav", x)
    (raw / "script.txt").write_text("\n".join(SCRIPT) + "\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={video_size}:rate=30:duration={dur:.3f}", "-i", str(raw / "voice.wav"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(raw / "talk.mp4")],
                   check=True, capture_output=True)
    P = d / "proj"
    P.mkdir(exist_ok=True)
    r = helpers.run_script("ingest.py", P, raw / "talk.mp4", "--clip-fps", "30")
    assert r.returncode == 0, r.stdout + r.stderr
    (P / "docs").mkdir(exist_ok=True)
    (P / "docs" / "source.md").write_text("\n".join(SOURCE) + "\n")
    env_run("transcribe.py", P, "talk", "--script", raw / "script.txt")
    env_run("cut.py", "suggest", P)
    tr = json.loads((P / "transcript.json").read_text())
    (P / "story.json").write_text(json.dumps(story(tr), indent=2))
    env_run("story.py", P)
    return P, marks


def env_run(name, *args):
    import os, sys
    r = subprocess.run([sys.executable, str(helpers.SCRIPTS / name), *map(str, args)], capture_output=True,
                       text=True, env=dict(os.environ, MOTION_NO_WHISPER="1"), timeout=600)
    assert r.returncode == 0, f"{name} failed:\n{r.stdout}\n{r.stderr}"
    return r


def add_composition(P):
    for f in ("footage-composition.html", "kit.js", "kit-footage.js"):
        shutil.copy2(helpers.TEMPLATES / f, P / f)
    return P / "footage-composition.html"
