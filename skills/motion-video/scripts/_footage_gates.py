"""
_footage_gates.py — footage gates for render.py --check-only (E12.11 a, d) and story.py checks
(private module). They run only for footage pieces: window.FOOTAGE is set (footage-composition.html
does it) or an element carries data-cue / data-claim.

  cue_timing   FAIL  every [data-cue="w12"] element first shows (opacity > 0) within ±2 frames of
                     word w12's time on the piece's timeline: transcript.json mapped through
                     edl.json (data-cue-offset="0.1" declares a deliberate lead/lag in seconds)
  claim_trace  FAIL  every visible [data-text] has a data-claim that holds up:
                       "w3-w9" / "w3"  the text is exactly those transcript words (a quote)
                       "source:N"      line N of docs/source.md exists and holds every number in
                                       the text (or, with no numbers, one of its longer words)
                       "label"         plain wording with no numbers (names, section labels)
The project folder is the composition's folder (transcript.json, edl.json, docs/source.md).
"""
import json, re
from pathlib import Path

CUE_TOL_FRAMES = 2
CUE_WINDOW = 0.6          # s searched either side of each expected start


# ------------------------------------------------------------------------------ project data
def load(project: Path):
    project = Path(project)
    tr = edl = None
    if (project / "transcript.json").exists():
        tr = json.loads((project / "transcript.json").read_text())
    if (project / "edl.json").exists():
        e = json.loads((project / "edl.json").read_text())
        edl = {"edl": e} if isinstance(e, list) else e
    src = project / "docs" / "source.md"
    lines = src.read_text(encoding="utf-8").splitlines() if src.exists() else None
    return tr, edl, lines


def timeline_t(tr, edl, t):
    """Source time on the transcript's clip -> piece time through the EDL (None if cut)."""
    events = (edl or {}).get("edl") or []
    if not events:
        return t
    clip = tr.get("clip") or (edl or {}).get("clip")
    for e in events:
        if e.get("clip") == clip and e["in"] - 1e-6 <= t < e["out"] - 1e-6:
            return e.get("at", 0) + (t - e["in"]) / float(e.get("speed", 1) or 1)
    return None


def norm_tokens(s):
    return [t for t in re.split(r"[^\w%]+", s.lower().replace("’", "'").replace("'", "")) if t]


NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _nums(s):
    return {n.replace(",", "") for n in NUM.findall(s)}


def check_claim(text, claim, tr, lines):
    """None if the claim holds up, else the reason (str)."""
    text = " ".join(text.split())
    claim = (claim or "").strip()
    if not text:
        return None
    if not claim:
        return "no data-claim (quote 'wA-wB', 'source:N' or 'label')"
    if claim == "label":
        return "a label can't carry numbers: cite it ('source:N') or quote it ('wA-wB')" if _nums(text) else None
    m = re.fullmatch(r"source:(\d+)", claim)
    if m:
        if lines is None:
            return "docs/source.md not found"
        n = int(m.group(1))
        if not 1 <= n <= len(lines) or not lines[n - 1].strip():
            return f"docs/source.md has no line {n}"
        line = lines[n - 1]
        missing = _nums(text) - _nums(line)
        if missing:
            return f"{', '.join(sorted(missing))} not in docs/source.md line {n}"
        if not _nums(text):
            long_words = [w for w in norm_tokens(text) if len(w) >= 4]
            if long_words and not set(long_words) & set(norm_tokens(line)):
                return f"no word of it appears in docs/source.md line {n}"
        return None
    m = re.fullmatch(r"([a-z]+\d+)(?:-([a-z]+\d+))?", claim, re.I)
    if m:
        if not tr:
            return "transcript.json not found"
        ids = [w["id"] for w in tr.get("words", [])]
        a, b = m.group(1), m.group(2) or m.group(1)
        if a not in ids or b not in ids:
            return f"word {a if a not in ids else b} not in transcript.json"
        i, j = ids.index(a), ids.index(b)
        if j < i:
            return f"{a}-{b} runs backwards"
        said = norm_tokens(" ".join(w["w"] for w in tr["words"][i:j + 1]))
        if norm_tokens(text) != said:
            return f"text doesn't match words {a}-{b} ({' '.join(said)!r})"
        return None
    return f"unknown claim {claim!r}"


# ------------------------------------------------------------------------------ page gates
DETECT_JS = "() => !!(window.FOOTAGE || document.querySelector('[data-cue],[data-claim]'))"

CUES_JS = """() => [...document.querySelectorAll('[data-cue]')].map((el, i) => ({
  i, cue: el.dataset.cue, off: parseFloat(el.dataset.cueOffset || 0) || 0,
  name: el.id ? '#' + el.id : (el.className ? el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0] : el.tagName.toLowerCase()) + `[data-cue=${el.dataset.cue}]`,
}))"""

VIS_JS = """async ({ frames, fps }) => {
  const vis = (el) => {
    if (!el.getClientRects().length) return 0;
    if (getComputedStyle(el).visibility === 'hidden') return 0;
    let o = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 ? o : 0;
  };
  const els = [...document.querySelectorAll('[data-cue]')];
  const out = {};
  for (const f of frames) {
    await window.seek(f / fps);
    out[f] = els.map(el => vis(el) > 0.01);
  }
  return out;
}"""

CLAIMS_JS = """async (ts) => {
  const vis = (el) => {
    if (!el.getClientRects().length) return 0;
    if (getComputedStyle(el).visibility === 'hidden') return 0;
    let o = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
    return o;
  };
  const els = [...document.querySelectorAll('[data-text]')];
  const seen = new Map();
  for (const t of ts) {
    await window.seek(t);
    els.forEach((el, i) => {
      if (vis(el) <= 0.01) return;
      const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
      const key = i + '|' + text;
      if (!seen.has(key)) seen.set(key, { text, claim: el.getAttribute('data-claim'), t,
        name: el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') });
    });
  }
  return [...seen.values()];
}"""


async def gate_cue_timing(page, tr, edl, D, fps):
    cues = await page.evaluate(CUES_JS)
    if not cues:
        return "pass (no [data-cue] elements)"
    if not tr:
        return "FAIL [data-cue] elements but no transcript.json next to the composition"
    words = {w["id"]: w for w in tr.get("words", [])}
    n = int(round(D * fps))
    want, fails = {}, []
    for c in cues:
        w = words.get(c["cue"])
        if not w:
            fails.append(f"{c['name']}: word {c['cue']} not in transcript.json")
            continue
        t = timeline_t(tr, edl, float(w["t0"]))
        if t is None:
            fails.append(f"{c['name']}: word {c['cue']} ({w['w']!r}) was cut by edl.json")
            continue
        want[c["i"]] = (t + c["off"]) * fps
    span = int(round(CUE_WINDOW * fps))
    frames = sorted({f for e in want.values() for f in range(int(round(e)) - span - 1, int(round(e)) + span + 1)
                     if 0 <= f < n})
    vis = await page.evaluate(VIS_JS, {"frames": frames, "fps": fps}) if frames else {}
    vis = {int(k): v for k, v in vis.items()}
    worst = 0.0
    for c in cues:
        if c["i"] not in want:
            continue
        e = want[c["i"]]
        lo = int(round(e)) - span - 1
        win = [f for f in frames if lo <= f <= int(round(e)) + span]
        if win and lo >= 0 and vis.get(win[0], [False] * (c["i"] + 1))[c["i"]]:
            fails.append(f"{c['name']}: already visible {CUE_WINDOW + 1 / fps:.2f} s before word {c['cue']} "
                         f"(t={e / fps:.3f})")
            continue
        first = next((f for f in win if vis[f][c["i"]]), None)
        if first is None:
            fails.append(f"{c['name']}: not visible within ±{CUE_WINDOW} s of word {c['cue']} (t={e / fps:.3f})")
            continue
        off = first - e
        worst = max(worst, abs(off))
        if abs(off) > CUE_TOL_FRAMES + 1e-6:
            fails.append(f"{c['name']}: starts {off:+.1f} frames from word {c['cue']} (t={e / fps:.3f}, "
                         f"limit ±{CUE_TOL_FRAMES})")
    if fails:
        more = f"; … {len(fails) - 8} more" if len(fails) > 8 else ""
        return "FAIL " + "; ".join(fails[:8]) + more
    return f"pass ({len(want)} cues, worst {worst:.1f} frames)"


async def gate_claim_trace(page, tr, lines, D, fps):
    ts = sorted({round(k / fps, 6) for k in range(0, int(round(D * fps)), max(1, int(round(fps / 10))))})
    seen = await page.evaluate(CLAIMS_JS, ts)
    if not seen:
        return "pass (no visible [data-text] elements)"
    fails = []
    for s in seen:
        why = check_claim(s["text"], s["claim"], tr, lines)
        if why:
            fails.append(f"{s['name']} {s['text'][:40]!r} at t={s['t']:.2f}: {why}")
    if fails:
        more = f"; … {len(fails) - 8} more" if len(fails) > 8 else ""
        return "FAIL " + "; ".join(fails[:8]) + more
    return f"pass ({len(seen)} texts traced)"


async def run(page, project, D, fps, report):
    """Adds cue_timing and claim_trace to report['gates'] for footage pieces; else nothing."""
    if not await page.evaluate(DETECT_JS):
        return
    tr, edl, lines = load(project)
    report["gates"]["cue_timing"] = await gate_cue_timing(page, tr, edl, D, fps)
    report["gates"]["claim_trace"] = await gate_claim_trace(page, tr, lines, D, fps)
