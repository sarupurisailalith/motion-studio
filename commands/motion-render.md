---
description: Render an existing HTML animation to MP4 (one or more formats) deterministically and run the QA gates
argument-hint: <path/to/composition.html> [--format 16x9,9x16] [--deliver] [--subframes 4] [--audio file] [--gl]
---

Render and QA: $ARGUMENTS

`S=${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts` (render.py, check.py, vendor.py, mix.py).
`R="python3 $S/render.py"`. Outputs go to `renders/` next to the HTML.

1. **Contract.** The file must expose `window.MOTION`, `window.ready`, `window.seek(t)`. If it runs
   on its own clock (rAF loop, CSS animations, a playing GSAP timeline, THREE.Clock), refactor it so
   every value derives from `t` (the `motion-video` skill's determinism rules), keeping the look
   identical. Vendor CDN libraries (`vendor.py <folder> three|gsap`) and use local fonts.
   `--format` needs the page to call `K.init(MOTION)` (copy `templates/kit.js` next to it);
   without the kit, render natively.
2. **Gates.** `$R <file> [--format F] --check-only` → determinism, loop seam, page errors, and with
   the kit `safe_area` (`[data-safe]` inside `K.safe.ui`), `text_duration` (`[data-text]`
   readable ≥ 8 frames) and `contrast` (`[data-text]` ≥ 4.5:1 against what's behind it). Fix every
   FAIL; explain or fix each WARN. `--thorough` samples more densely (slower; a pass is not proof).
3. **Look.** `$R <file> [--format F] --sheet` (one sheet per format; `--phone` when reviewing readability), and as needed `--stills 1,2.5`,
   `--strip A:B:N` (across a transition), `--poster [T]` (put it after the HTML path),
   `--contact beats` (needs beats.js). Open the PNGs and judge them.
4. **Render** with the user's flags (default `--subframes 3`; `--gl` for WebGL; `--workers N`, default
   the CPU count up to 6; `--scale 2` for crisper type). A rerun where only `--audio` changed reuses the
   cached video (`renders/.cache/`, `--no-cache` to force); `--capture screenshot` is the v0.2 capture path. `--format 16x9,9x16,1x1,4x5` renders each format
   (`renders/<stem>_<fmt>.mp4`); `--deliver` adds a poster, sheet and phone sheet per format plus
   `renders/deliver.json`. `--audio track.wav` muxes and normalises to −14 LUFS; for SFX or a
   mix across formats use `/motion-audio` (`mix.py --mux` keeps deliver.json current).
5. **QA.** `python3 $S/check.py renders/<stem>[_<fmt>].mp4` per file (`--loop` if MOTION.loop;
   `--sync audio/sfx_events.json` with SFX). Fix FAILs; explain or fix WARNs.
6. **Report:** output paths (or deliver.json), duration/resolution/fps/size per format, gate
   results, contact sheet paths.
