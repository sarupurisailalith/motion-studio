---
description: Render an existing HTML animation to MP4 deterministically and run the QA gates
argument-hint: <path/to/composition.html> [--subframes 4] [--audio file] [--gl]
---

Render and QA: $ARGUMENTS

Scripts: `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/` (render.py, check.py, vendor.py).

1. Check the file implements the contract (`window.MOTION`, `window.ready`, `window.seek(t)`).
   If it's a free-running animation (rAF loop, CSS animations, GSAP playing, THREE.Clock),
   refactor it so every value derives from `t` — see the `motion-video` skill's determinism
   rules — keeping the look identical. If it loads libraries or fonts from a CDN, vendor
   them locally.
2. `render.py <file> --check-only` → fix any FAIL. Then `--sheet` and look at the sheet.
3. Full render with the user's flags (default `--subframes 3`; add `--gl` for WebGL).
4. `check.py renders/<name>.mp4` (`--loop` if MOTION.loop). Fix FAILs, explain or fix WARNs.
5. Report: output path, duration/resolution/fps/size, gate results, contact sheet path.
