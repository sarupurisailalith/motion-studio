"""
_speech.py — shared speech helpers for transcribe.py and cut.py (private module).

Everything here is numpy on mono float audio (see _audio.py) and deterministic:
  - activity():      10 ms frame levels and a voice-activity mask (adaptive threshold)
  - regions():       speech regions and the silences between them
  - word_slots():    word-sized sub-segments of a region, cut at the deepest short dips
  - align_script():  a user-supplied script spread over the regions (phrase lines, then words)
  - find_fillers():  um / uh / "you know" ... in a word list
  - group_phrases(): words -> phrases split at pauses
Word ids are "w<n>" (n = index in the transcript), phrase ids "p<n>".
"""
import re

import numpy as np

HOP = 0.010                 # s per activity frame
PHRASE_GAP = 0.30           # a pause at least this long ends a phrase
LONG_PAUSE = 0.60           # pauses longer than this are listed as cut candidates
MIN_SPEECH = 0.06           # shorter blips are noise, not speech
WORD_DIP = 0.03             # a dip this long inside a phrase may separate two words

FILLERS = {"um", "uh", "uhm", "umm", "er", "erm", "ah", "hmm", "hm", "mm", "mhm", "uh-huh"}
FILLER_PAIRS = {("you", "know"), ("i", "mean")}


def norm(w):
    """Lower-case word without surrounding punctuation (for matching, never for display)."""
    return re.sub(r"^[^\w%$€£]+|[^\w%]+$", "", w.lower().replace("’", "'"))


def activity(mono, sr, hop=HOP):
    """-> (level_db per frame, active mask, threshold_db). The threshold sits between the noise
    floor (10th percentile) and the speech level (95th percentile), at least 35 dB under speech."""
    n = max(1, int(round(hop * sr)))
    k = len(mono) // n
    if k == 0:
        return np.zeros(0), np.zeros(0, bool), -60.0
    fr = np.asarray(mono[:k * n], np.float64).reshape(k, n)
    lev = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-12)
    floor = max(float(np.percentile(lev, 10)), -90.0)
    loud = float(np.percentile(lev, 95))
    thr = max(floor + 0.4 * (loud - floor), loud - 35.0, -70.0)
    return lev, lev > thr, thr


def _runs(mask):
    """[(start, end)] frame index runs of True (end exclusive)."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.diff(m.astype(np.int8))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def regions(mono, sr, gap=PHRASE_GAP, min_speech=MIN_SPEECH, hop=HOP):
    """Speech regions [(t0, t1)] separated by silences of at least `gap` s, and those silences
    [{t0, t1, dur, long}] (leading and trailing silence included). Also returns the raw active
    mask (for word_slots)."""
    lev, act, _ = activity(mono, sr, hop)
    runs = [(a, b) for a, b in _runs(act) if (b - a) * hop >= min_speech]
    merged = []
    for a, b in runs:
        if merged and (a - merged[-1][1]) * hop < gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    dur = len(mono) / sr
    regs = [(round(float(a * hop), 3), round(float(min(b * hop, dur)), 3)) for a, b in merged]
    sil, prev = [], 0.0
    for t0, t1 in regs + [(round(dur, 3), None)]:
        if t0 - prev >= gap:
            sil.append({"t0": round(prev, 3), "t1": round(t0, 3), "dur": round(t0 - prev, 3),
                        "long": bool(t0 - prev > LONG_PAUSE)})
        prev = t1
    return regs, sil, act


def word_slots(act, t0, t1, k, hop=HOP, min_dip=WORD_DIP):
    """Split region [t0, t1) into k word slots at the k-1 longest inner dips of the active mask.
    Fewer dips than needed -> the longest slots are split evenly. -> ([(a, b)], exact: bool)."""
    a, b = int(round(t0 / hop)), int(round(t1 / hop))
    seg = act[a:b]
    if k <= 1 or len(seg) == 0:
        return [(t0, t1)], k <= 1
    dips = [(e - s, s, e) for s, e in _runs(~seg) if s > 0 and e < len(seg) and (e - s) * hop >= min_dip]
    use = sorted(sorted(dips, reverse=True)[:k - 1], key=lambda d: d[1])
    slots, start = [], 0
    for _, s, e in use:
        slots.append((start, s))
        start = e
    slots.append((start, len(seg)))
    exact = len(slots) == k
    while len(slots) < k:   # not enough dips: halve the longest slot
        i = max(range(len(slots)), key=lambda j: slots[j][1] - slots[j][0])
        s, e = slots[i]
        m = (s + e) // 2 if e - s > 1 else s
        slots[i:i + 1] = [(s, m), (m, e)]
    return [(round(float((a + s) * hop), 3), round(float((a + e) * hop), 3)) for s, e in slots], exact


def _weights(words):
    return np.array([max(1, len(norm(w))) + 1 for w in words], np.float64)


def spread(words, slots, exact):
    """Words over slots: one word per slot when the counts match, else by character weight."""
    if exact and len(slots) == len(words):
        return [(w, s0, s1, 1.0) for w, (s0, s1) in zip(words, slots)]
    t0, t1 = slots[0][0], slots[-1][1]
    c = np.concatenate([[0], np.cumsum(_weights(words))])
    c = t0 + (t1 - t0) * c / c[-1]
    return [(w, round(float(c[i]), 3), round(float(c[i + 1]), 3), 0.5) for i, w in enumerate(words)]


def split_script(text):
    """Script -> (lines, words). Blank lines and lines starting with '#' are ignored."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    return lines, [w for ln in lines for w in ln.split()]


def align_script(text, regs, act, hop=HOP):
    """Spread a script over speech regions. One script line per region when the counts match,
    else words go to regions by character weight vs speech time. Inside a region each word gets
    a dip-separated slot. -> [(word, t0, t1, conf)]."""
    lines, words = split_script(text)
    if not words or not regs:
        return []
    if len(lines) == len(regs):
        groups = [ln.split() for ln in lines]
    else:
        spoken = np.array([b - a for a, b in regs], np.float64)
        edges = np.cumsum(spoken) / spoken.sum()
        w = _weights(words)
        mid = (np.cumsum(w) - w / 2) / w.sum()
        idx = np.minimum(np.searchsorted(edges, mid), len(regs) - 1)
        groups = [[words[i] for i in np.where(idx == r)[0]] for r in range(len(regs))]
    out = []
    for (a, b), g in zip(regs, groups):
        if not g:
            continue
        slots, exact = word_slots(act, a, b, len(g), hop)
        out += spread(g, slots, exact)
    return out


def find_fillers(words):
    """words = [{id, w, t0, t1}] -> [{id, w, t0, t1}] (two-word fillers keep the first id, to the last t1)."""
    out, i = [], 0
    while i < len(words):
        n = norm(words[i]["w"])
        if n in FILLERS:
            out.append({k: words[i][k] for k in ("id", "w", "t0", "t1")})
        elif i + 1 < len(words) and (n, norm(words[i + 1]["w"])) in FILLER_PAIRS:
            out.append({"id": words[i]["id"], "w": words[i]["w"] + " " + words[i + 1]["w"],
                        "t0": words[i]["t0"], "t1": words[i + 1]["t1"], "to": words[i + 1]["id"]})
            i += 1
        i += 1
    return out


def group_phrases(words, gap=PHRASE_GAP):
    """Consecutive words -> phrases, split where the pause between two words is >= gap s."""
    phrases = []
    for w in words:
        if phrases and w["t0"] - phrases[-1]["t1"] < gap:
            p = phrases[-1]
            p["t1"], p["to"] = w["t1"], w["id"]
            p["text"] += " " + w["w"]
        else:
            phrases.append({"id": f"p{len(phrases)}", "t0": w["t0"], "t1": w["t1"], "from": w["id"],
                            "to": w["id"], "text": w["w"]})
        w["phrase"] = phrases[-1]["id"]
    return phrases


def snap_starts(words, act, hop=HOP, reach=0.15):
    """A word that starts in silence (a recogniser's early guess) moves to the next active frame
    within `reach` s. Ends are left alone."""
    for w in words:
        i = int(round(w["t0"] / hop))
        if 0 <= i < len(act) and not act[i]:
            j = next((j for j in range(i, min(len(act), i + int(reach / hop) + 1)) if act[j]), None)
            if j is not None and j * hop < w["t1"]:
                w["t0"] = round(j * hop, 3)
    return words
