---
description: Add sound to a motion composition — beat grid, SFX on its visual hits, a −14 LUFS mix muxed into every rendered format, and a sync check
argument-hint: <path/to/composition.html> [--track song.mp3] [--vo voice.wav]
---

Add sound to: $ARGUMENTS

`S=${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts`. Read
`${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/audio.md` first. `P` = the folder holding
the composition `P/<slug>.html`; `D` = `MOTION.duration`. Same paths as `/motion`.

1. **Music is user-supplied only.** Never download or "find" a track. No track → SFX only (or
   silent), and say so.
2. **Beat grid** (only with `--track`, or when the piece is cut to a fixed BPM):
   `python3 $S/beats.py --track <song> --duration D --out P` (→ `P/music.wav`, `beats.json`,
   `beats.js`), or `--grid --bpm N --duration D --out P`. The picture is **not final** until
   this has run when any scene or hit is timed in beats (`K.T`, `'16b'`): add
   `<script src="beats.js"></script>` above the kit script, re-run
   `render.py P/<slug>.html --check-only`, and re-render before mixing.
3. **Hits.** The composition needs `MOTION.hits` (one per real visual event; palette in
   audio.md). Then `python3 $S/render.py P/<slug>.html --hits` → `P/renders/<slug>_hits.json`.
4. **SFX.** `python3 $S/sfx.py P/renders/<slug>_hits.json --out P/audio/sfx.wav`
   (→ `P/audio/sfx.wav` + `P/audio/sfx_events.json`). Keep both files together. A sound the
   palette lacks → register it in `P/audio/palette.py` and pass `--palette P/audio/palette.py`
   (audio.md "Project palettes"; it is never loaded without the flag). Takes supplied by the user or a connector → `--samples <folder>` with files named
   `<name>_<n>.<ext>`.
5. **Picture.** Every format must exist as `P/renders/<slug>_<fmt>.mp4` (or `<slug>.mp4`). If
   none exists, or the timing changed, render first:
   `python3 $S/render.py P/<slug>.html --format F --deliver --subframes 3`.
6. **Mix and mux.** `python3 $S/mix.py [--duration D] --out P/audio/mix.wav [--music P/music.wav]
   [--sfx P/audio/sfx.wav] [--vo <voice>] [--sfx-db -6] --mux <every rendered mp4>`. This
   masters to −14 LUFS / ≤ −1 dBTP, replaces each video's audio (AAC 48 kHz) and refreshes
   `audio` / `size_bytes` in `P/renders/deliver.json`. Without `--duration` it reads D from
   `P/renders/deliver.json` or the hits file. Add `--stems` for music-only / no-VO masters.
7. **Check.** `python3 $S/check.py <each mp4> --sync P/audio/sfx_events.json` (`--loop` if
   MOTION.loop). For a plot: `python3 $S/sync.py <mp4> P/audio/sfx_events.json --png
   P/renders/<slug>_sync.png`. A FAIL ("off by" or "not audible") → move the hit, raise its
   `gain`, or drop it; then repeat 3–7.
8. **Report** the integrated LUFS and true peak, the worst sync offset (ms) and its hit label,
   any silent-on-purpose hits, and the muxed file paths.
