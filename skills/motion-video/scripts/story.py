#!/usr/bin/env python3
"""
story.py — check story.json (the story map of a footage-led piece, E12.3) against the transcript,
the EDL and docs/source.md, then write story.js (window.STORY) for the composition.

story.json (written in the brief step, see references/footage.md):
  {"version": 1, "clip": "talk", "focus": [0.5, 0.4], "captions": true,
   "segments": [
     {"id": "s0", "role": "hook", "from": "w0", "to": "w7", "layout": "full",
      "claim": "the one thing this segment says", "emphasis": ["w3"], "names": ["Lumen"],
      "cues": [{"kind": "keyword", "text": "Lumen", "at": "w3", "until": "w7", "sfx": "pop"},
               {"kind": "stat", "value": "3x", "label": "faster exports", "at": "w5", "claim": "source:2"}]}]}

Checks (each problem is listed; exit 1 if any):
  - role is one of hook, problem, product, feature, proof, objection, cta; layout one of
    full, corner, split, shape, pig
  - every from / to / at / until / emphasis id is a word in transcript.json and, when edl.json
    exists, survives the edit (a cue on a cut word can't be timed)
  - every on-screen claim holds up: a keyword / stat / feature / CTA line either quotes the words
    at its cue, or cites "claim": "source:N" (line N of docs/source.md holds its numbers);
    quotes use from/to word ids; lower-third names and roles need no claim unless they hold a number
  - cue kinds: keyword, stat, lower-third, feature-list, quote, cta, screenshot (asset id in assets.json)

Usage: python3 story.py motion/promo            # checks, then writes motion/promo/story.js
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _footage_gates as fg  # noqa: E402

ROLES = {"hook", "problem", "product", "feature", "proof", "objection", "cta"}
LAYOUTS = {"full", "corner", "split", "shape", "pig"}
KINDS = {"keyword", "stat", "lower-third", "feature-list", "quote", "cta", "screenshot"}


def check(project: Path, story):
    tr, edl, lines = fg.load(project)
    if not tr:
        return [f"no {project / 'transcript.json'} (run transcribe.py first)"]
    words = {w["id"]: w for w in tr.get("words", [])}
    if not words:
        return ["transcript.json has no words: cues need word ids (use --script or faster-whisper)"]
    order = [w["id"] for w in tr["words"]]
    assets = {}
    if (project / "assets" / "assets.json").exists():
        assets = {e["id"]: e for e in json.loads((project / "assets" / "assets.json").read_text()).get("assets", [])}
    errs = []

    def word(ref, where, kept=True):
        if ref is None:
            return None
        rid = str(ref).split("+")[0].split("-")[0] if isinstance(ref, str) else None
        if isinstance(ref, (int, float)):
            return None                     # a time in seconds: allowed for until
        if rid not in words:
            errs.append(f"{where}: {ref!r} is not a word id in transcript.json")
            return None
        if kept and edl and fg.timeline_t(tr, edl, float(words[rid]["t0"])) is None:
            errs.append(f"{where}: word {rid} ({words[rid]['w']!r}) is cut by edl.json")
        return rid

    def quote_of(text, at):
        """The word range the text quotes, starting at `at`, or None."""
        want = fg.norm_tokens(text)
        if not want or at not in words:
            return None
        i = order.index(at)
        rng = order[i:i + len(want)]
        said = fg.norm_tokens(" ".join(words[k]["w"] for k in rng))
        return f"{rng[0]}-{rng[-1]}" if said == want else None

    def claim(text, c, at, where, required=True):
        ref = c or quote_of(text, at)
        if not ref:
            if required or fg._nums(text):
                errs.append(f"{where}: {text!r} is neither a quote of the words at {at} nor cited "
                            "('claim': 'source:N')")
            return
        why = fg.check_claim(text, ref, tr, lines)
        if why:
            errs.append(f"{where}: {text!r}: {why}")

    segs = story.get("segments")
    if not isinstance(segs, list) or not segs:
        return errs + ["story.json has no segments"]
    for si, s in enumerate(segs):
        sid = s.get("id", f"segments[{si}]")
        if s.get("role") not in ROLES:
            errs.append(f"{sid}: role {s.get('role')!r} (use {', '.join(sorted(ROLES))})")
        if s.get("layout") is not None and s["layout"] not in LAYOUTS:
            errs.append(f"{sid}: layout {s['layout']!r} (use {', '.join(sorted(LAYOUTS))})")
        a, b = word(s.get("from"), f"{sid}.from"), word(s.get("to"), f"{sid}.to", kept=False)
        if a and b and order.index(b) < order.index(a):
            errs.append(f"{sid}: to ({b}) comes before from ({a})")
        for e in s.get("emphasis") or []:
            word(e, f"{sid}.emphasis", kept=False)
        for ci, c in enumerate(s.get("cues") or []):
            where = f"{sid}.cues[{ci}] ({c.get('kind')})"
            k = c.get("kind")
            if k not in KINDS:
                errs.append(f"{where}: unknown kind (use {', '.join(sorted(KINDS))})")
                continue
            at = word(c.get("at") or (c.get("from") if k == "quote" else None), f"{where}.at")
            if c.get("until") is not None:
                word(c["until"], f"{where}.until", kept=False)
            if k == "keyword":
                claim(c.get("text", ""), c.get("claim"), at, where)
            elif k == "stat":
                claim(f"{c.get('value', '')} {c.get('label', '')}".strip(), c.get("claim"), at, where)
            elif k == "feature-list":
                for ii, it in enumerate(c.get("items") or []):
                    iat = word(it.get("at"), f"{where}.items[{ii}].at")
                    claim(it.get("text", ""), it.get("claim"), iat, f"{where}.items[{ii}]")
                if not c.get("items"):
                    errs.append(f"{where}: no items")
            elif k == "quote":
                f, t = word(c.get("from"), f"{where}.from"), word(c.get("to"), f"{where}.to")
                if f and t and order.index(t) < order.index(f):
                    errs.append(f"{where}: to comes before from")
            elif k == "cta":
                if c.get("line"):
                    claim(c["line"], c.get("lineClaim") or c.get("claim"), at, where)
                claim(c.get("url", ""), c.get("claim"), at, where, required=False)
            elif k == "lower-third":
                for fld in ("name", "role"):
                    if c.get(fld):
                        claim(c[fld], c.get("claim"), at, where, required=False)
            elif k == "screenshot":
                if c.get("asset") not in assets or assets[c["asset"]].get("kind") not in ("image", "svg"):
                    errs.append(f"{where}: asset {c.get('asset')!r} is not an image in assets.json")
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path)
    ap.add_argument("--story", type=Path, help="default PROJECT/story.json")
    a = ap.parse_args()
    path = a.story or a.project / "story.json"
    if not path.exists():
        sys.exit(f"not found: {path}")
    try:
        story = json.loads(path.read_text())
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON: {e}")
    errs = check(a.project, story)
    report = {"story": str(path), "segments": len(story.get("segments") or []),
              "cues": sum(len(s.get("cues") or []) for s in story.get("segments") or []), "problems": errs}
    if not errs:
        (a.project / "story.js").write_text(f"window.STORY = {json.dumps(story)};\n")
        report["story_js"] = str(a.project / "story.js")
    report["status"] = "pass" if not errs else f"FAIL {len(errs)} problem(s)"
    print(json.dumps(report, indent=2))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
