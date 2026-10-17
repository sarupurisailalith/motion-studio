#!/usr/bin/env python3
"""
transcribe.py — what is said and when: word timings, phrases, fillers and pauses for a clip's
voice (or any voice recording), written as data the composition loads before window.ready.

Engines (--engine auto picks the first that applies):
  whisper  faster-whisper, if installed (optional: pip install faster-whisper). Word timestamps;
           each word start is nudged onto the first voiced 10 ms frame if the recogniser put it
           in silence. Audio is decoded with ffmpeg to float32 (not PyAV). The first run
           downloads the model weights from Hugging Face (see PRIVACY.md); --model also takes a
           local model folder.
  script   --script FILE (the user's own words, one phrase per line is best): phrases are split
           at silences and the script is spread over them, one line per phrase when the counts
           match; inside a phrase each word gets the slot between the deepest short dips.
  silence  no words: phrases and silences only (enough for cut suggestions and VO snapping).
Without faster-whisper the script or silence path runs and says "install faster-whisper to
enable word timings".

Writes PROJECT/transcript.json (+ transcript.js = window.TRANSCRIPT for file:// previews):
  {version, audio, clip, engine, duration,
   words:   [{id: "w0", w, t0, t1, conf, phrase}],         # seconds on the clip's own timeline
   phrases: [{id: "p0", t0, t1, text, from, to}],          # from/to = first/last word id
   fillers: [{id, w, t0, t1}],  silences: [{t0, t1, dur, long}],  notes: [...]}
"long" marks pauses over 0.6 s (cut candidates, see cut.py suggest).

Voice-over snapping (E6.1): --snap beats.json moves each phrase (never stretches it) so its
start lands on the nearest free beat, and writes PROJECT/audio/vo.wav + PROJECT/vo.json
(+ vo.js = window.VO): the same schema, times on the new timeline, each phrase with its src_t0,
beat and shift. Use for a voice-over recorded without picture, never for on-camera speech.

Usage:
  python3 transcribe.py motion/promo talk-audio                    # an audio id from assets.json
  python3 transcribe.py motion/promo talk                          # a video id: uses its clip audio
  python3 transcribe.py motion/promo talk --script docs/script.txt --engine script
  python3 transcribe.py motion/promo vo-take --script vo.txt --snap motion/promo/beats.json --every 2
"""
import argparse, json, os, sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy missing: pip install numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _audio, _speech  # noqa: E402

WHISPER_HINT = ("install faster-whisper to enable word timings (pip install faster-whisper; its first "
                "run downloads model weights from Hugging Face)")


def log(*a):
    print("[transcribe]", *a, file=sys.stderr, flush=True)


def resolve_audio(project: Path, ref: str):
    """An assets.json id (audio, or a video with a linked clip audio) or a file path ->
    (path, audio id or None, clip id or None)."""
    inv_path = project / "assets" / "assets.json"
    if inv_path.exists():
        assets = {e["id"]: e for e in json.loads(inv_path.read_text()).get("assets", [])}
        e = assets.get(ref)
        if e and e.get("kind") == "video":
            if not e.get("audio") or e["audio"] not in assets:
                sys.exit(f"clip {ref!r} has no clip audio in assets.json (re-ingest it with ingest.py; "
                         "a clip without an audio stream can't be transcribed)")
            return project / assets[e["audio"]]["path"], e["audio"], ref
        if e and e.get("kind") == "audio":
            return project / e["path"], ref, e.get("of")
        if e:
            sys.exit(f"asset {ref!r} is a {e.get('kind')}, not audio or video")
    p = Path(ref)
    if p.exists():
        return p, None, None
    sys.exit(f"{ref!r} is neither an asset id in {inv_path} nor a file")


def whisper_available():
    if os.environ.get("MOTION_NO_WHISPER") == "1":   # tests: force the fallback path
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def run_whisper(path, a):
    from faster_whisper import WhisperModel
    audio = _audio.load(path, 16000, 1)              # ffmpeg -> float32; avoids PyAV mismatches
    log(f"faster-whisper {a.model} on {len(audio) / 16000:.1f} s of audio")
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    segs, _ = model.transcribe(audio, language=a.language, word_timestamps=True, beam_size=5,
                               condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in s.words or []:
            text = w.word.strip()
            if text:
                out.append((text, round(float(w.start), 3), round(float(w.end), 3),
                            round(float(w.probability), 3)))
    return out


def build(path, a, notes):
    """-> transcript dict (without audio/clip ids)."""
    mono = _audio.load(path, _audio.SR, 1)
    dur = len(mono) / _audio.SR
    regs, silences, act = _speech.regions(mono, _audio.SR)
    engine = a.engine
    if engine == "auto":
        engine = "whisper" if whisper_available() else ("script" if a.script else "silence")
        if engine != "whisper":
            notes.append(WHISPER_HINT)
            log(WHISPER_HINT)
    if engine == "whisper" and not whisper_available():
        sys.exit("--engine whisper: faster-whisper is not installed. " + WHISPER_HINT)
    if engine == "script" and not a.script:
        sys.exit("--engine script needs --script FILE (the words as spoken)")
    if engine == "whisper":
        raw = run_whisper(path, a)
        label = f"faster-whisper:{a.model}"
        if a.script:
            notes.append("--script ignored: faster-whisper heard the words itself")
    elif engine == "script":
        raw = _speech.align_script(Path(a.script).read_text(encoding="utf-8"), regs, act)
        label = "script"
        if not raw:
            notes.append("no speech found, or the script is empty: no words")
    else:
        raw, label = [], "silence"
    words = [{"id": f"{a.prefix}{i}", "w": w, "t0": t0, "t1": max(t1, t0), "conf": c}
             for i, (w, t0, t1, c) in enumerate(raw)]
    if engine == "whisper":
        _speech.snap_starts(words, act)
    if words:
        phrases = _speech.group_phrases(words)
    else:
        phrases = [{"id": f"p{i}", "t0": t0, "t1": t1, "text": "", "from": None, "to": None}
                   for i, (t0, t1) in enumerate(regs)]
    return {"version": 1, "engine": label, "duration": round(dur, 4), "sr": _audio.SR,
            "words": words, "phrases": phrases, "fillers": _speech.find_fillers(words),
            "silences": silences, "long_pause": _speech.LONG_PAUSE}, mono


def write_data(project: Path, name: str, var: str, data):
    text = json.dumps(data, indent=2)
    (project / f"{name}.json").write_text(text + "\n")
    (project / f"{name}.js").write_text(f"window.{var} = {json.dumps(data)};\n")
    return project / f"{name}.json"


# ------------------------------------------------------------------------------ E6.1 snapping
def snap(tr, mono, beats, a, notes):
    """Move each phrase (unstretched) onto a beat. -> (vo audio, vo dict)."""
    sr = _audio.SR
    grid = beats.get("downbeats") if a.snap_to == "downbeat" else beats.get("beats")
    grid = [float(b) for b in (grid or [])][::max(1, a.every)]
    if not grid:
        sys.exit(f"no {a.snap_to}s in {a.snap}")
    ph = tr["phrases"]
    pre, post = 0.03, 0.12
    out_ph, placed, cursor, shift = [], [], 0.0, None
    for i, p in enumerate(ph):
        lo = p["t0"] - pre if i == 0 else max(p["t0"] - pre, (ph[i - 1]["t1"] + p["t0"]) / 2)
        hi = p["t1"] + post if i == len(ph) - 1 else min(p["t1"] + post, (p["t1"] + ph[i + 1]["t0"]) / 2)
        lo, hi = max(0.0, lo), min(len(mono) / sr, hi)
        want = p["t0"] + (shift or 0.0)
        free = [b for b in grid if b - (p["t0"] - lo) >= cursor - 1e-9]
        if free:
            b = min(free, key=lambda x: (abs(x - want), x))
        else:
            b = cursor + (p["t0"] - lo)
            notes.append(f"{p['id']}: no {a.snap_to} left after {cursor:.2f} s; placed unsnapped")
        shift = b - p["t0"]
        cursor = hi + shift + a.min_gap
        placed.append((lo, hi, shift))
        q = dict(p, t0=round(p["t0"] + shift, 6), t1=round(p["t1"] + shift, 6), src_t0=p["t0"],
                 src_t1=p["t1"], beat=round(b, 6) if free else None, shift=round(shift, 6))
        out_ph.append(q)
    end = max(hi + s for lo, hi, s in placed) if placed else 0.0
    n = int(round((a.duration or float(beats.get("duration") or 0) or end + 0.5) * sr))
    y = np.zeros(max(n, int(round((end + 0.05) * sr))))
    for lo, hi, s in placed:
        i0, i1 = int(round(lo * sr)), int(round(hi * sr))
        seg = mono[i0:i1].astype(np.float64)
        f = min(len(seg) // 2, int(0.005 * sr))           # 5 ms edge fades: no clicks
        if f:
            seg[:f] *= np.linspace(0, 1, f)
            seg[-f:] *= np.linspace(1, 0, f)
        j = int(round((lo + s) * sr))
        y[j:j + len(seg)] += seg
    y = y[:n] if n else y
    by_phrase = {p["id"]: p["shift"] for p in out_ph}
    words = [dict(w, t0=round(w["t0"] + by_phrase[w["phrase"]], 6), t1=round(w["t1"] + by_phrase[w["phrase"]], 6))
             for w in tr["words"]]
    vo = {"version": 1, "source": tr.get("audio") or tr.get("path"), "engine": tr["engine"],
          "duration": round(len(y) / sr, 4), "snap": {"file": str(a.snap), "to": a.snap_to, "every": a.every},
          "stretch": 0.0, "words": words, "phrases": out_ph, "fillers": [], "silences": []}
    return y, vo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="project folder (holds assets/assets.json)")
    ap.add_argument("audio", help="audio id, video id (its clip audio) or an audio/video file")
    ap.add_argument("--engine", choices=["auto", "whisper", "script", "silence"], default="auto")
    ap.add_argument("--script", type=Path, help="the words as spoken (one phrase per line is best)")
    ap.add_argument("--model", default="small", help="faster-whisper model name or local folder (default small)")
    ap.add_argument("--language", help="spoken language code, e.g. en (default: detect)")
    ap.add_argument("--device", default="auto", help="faster-whisper device (auto, cpu, cuda)")
    ap.add_argument("--compute-type", default="default", help="faster-whisper compute type (e.g. int8 on CPU)")
    ap.add_argument("--prefix", default="w", help="word id prefix (default w -> w0, w1 ...)")
    ap.add_argument("--out", help="output name in the project (default transcript -> transcript.json/.js)")
    ap.add_argument("--snap", type=Path, metavar="BEATS_JSON", help="E6.1: snap phrase starts to this beat grid "
                    "and write audio/vo.wav + vo.json")
    ap.add_argument("--snap-to", choices=["beat", "downbeat"], default="beat")
    ap.add_argument("--every", type=int, default=1, help="use every Nth beat of the grid (default 1)")
    ap.add_argument("--min-gap", type=float, default=0.05, help="least silence between snapped phrases (s)")
    ap.add_argument("--duration", type=float, help="length of vo.wav (default: the beat grid's duration)")
    a = ap.parse_args()

    if a.script and not a.script.exists():
        sys.exit(f"not found: {a.script}")
    path, audio_id, clip = resolve_audio(a.project, a.audio)
    notes = []
    tr, mono = build(path, a, notes)
    tr = {"version": 1, "audio": audio_id, "clip": clip,
          "path": os.path.relpath(path, a.project) if audio_id else str(path), **tr, "notes": notes}
    out = write_data(a.project, a.out or "transcript", "TRANSCRIPT", tr)
    log(f"{tr['engine']}: {len(tr['words'])} words, {len(tr['phrases'])} phrases, "
        f"{len(tr['fillers'])} fillers, {sum(s['long'] for s in tr['silences'])} long pauses -> {out}")
    summary = {"transcript": str(out), "engine": tr["engine"], "words": len(tr["words"]),
               "phrases": len(tr["phrases"]), "fillers": len(tr["fillers"]),
               "long_pauses": sum(s["long"] for s in tr["silences"]), "notes": notes}
    if a.snap:
        if not a.snap.exists():
            sys.exit(f"not found: {a.snap}")
        y, vo = snap(tr, mono, json.loads(a.snap.read_text()), a, notes)
        wav = a.project / "audio" / "vo.wav"
        _audio.write_wav(wav, y)
        vo["path"] = "audio/vo.wav"
        vj = write_data(a.project, "vo", "VO", vo)
        log(f"{len(vo['phrases'])} phrases snapped to {a.snap_to}s (no time-stretch) -> {wav}, {vj}")
        summary.update(vo=str(wav), vo_json=str(vj))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
