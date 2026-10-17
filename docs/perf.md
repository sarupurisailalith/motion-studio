# Performance

`python3 tests/bench.py` renders the 2D template (6 s, 1080x1080, 60 fps = 360 frames), a one-canvas
2D page of the same size and length (`tests/fixtures/perf/canvas2d.html`), and the Three.js template
(8 s, 1920x1080, 30 fps, `--gl`). Full renders use `--skip-checks --no-cache`; the gates are timed on
their own (`--check-only`). frames/s = output frames / wall time; samples/s counts every sub-frame
capture. Modes ending in `-v02` use `--capture screenshot`, the v0.2 capture path.

## E8 results

<!-- bench:start -->
Measured 2026-10-18 with `python3 tests/bench.py --repeat 2`. Wall time includes Chromium start-up,
page load, the ffmpeg encode and concatenation of worker segments; the median of 2 runs (all runs in brackets). load = 1-min load average when the mode started.

Machine: os Darwin 25.6.0 (arm64), cpu Apple M4, cores 10, memory 24 GB, python 3.14.0, chromium 156.0.8078.4, ffmpeg ffmpeg version 8.0

| mode | template | size @ fps | frames | flags | wall (s) | frames/s | samples/s | load |
|---|---|---|---|---|---|---|---|---|
| plain-w1-v02 | 2d | 1080x1080 @ 60 | 360 | `--workers 1 --capture screenshot` | 18.9 [18.9, 18.9] | 19.0 | 19.0 | 22.4 |
| plain-w1 | 2d | 1080x1080 @ 60 | 360 | `--workers 1` | 10.3 [10.3, 9.8] | 34.8 | 34.8 | 5.4 |
| plain-w2 | 2d | 1080x1080 @ 60 | 360 | `--workers 2` | 6.4 [6.4, 5.9] | 56.6 | 56.6 | 5.1 |
| plain-w4-v02 | 2d | 1080x1080 @ 60 | 360 | `--workers 4 --capture screenshot` | 6.3 [6.3, 6.1] | 57.1 | 57.1 | 5.4 |
| plain-w4 | 2d | 1080x1080 @ 60 | 360 | `--workers 4` | 4.9 [4.8, 4.9] | 73.9 | 73.9 | 13.1 |
| plain-default | 2d | 1080x1080 @ 60 | 360 | `` | 5.0 [4.8, 5.0] | 71.8 | 71.8 | 12.3 |
| subframes3-w4 | 2d | 1080x1080 @ 60 | 360 | `--subframes 3 --workers 4` | 11.7 [11.5, 11.7] | 30.7 | 92.1 | 11.5 |
| canvas-w1-v02 | canvas | 1080x1080 @ 60 | 360 | `--format 1x1 --workers 1 --capture screenshot` | 65.7 [65.7, 59.5] | 5.5 | 5.5 | 8.1 |
| canvas-w1-cdp | canvas | 1080x1080 @ 60 | 360 | `--format 1x1 --workers 1 --capture cdp` | 32.4 [32.4, 24.5] | 11.1 | 11.1 | 9.8 |
| canvas-w1 | canvas | 1080x1080 @ 60 | 360 | `--format 1x1 --workers 1` | 28.1 [28.1, 20.1] | 12.8 | 12.8 | 7.8 |
| check-only-v02 | 2d | 1080x1080 @ 60 | 360 | `--check-only --capture screenshot` | 1.5 [1.5, 1.5] | — | — | 6.1 |
| check-only | 2d | 1080x1080 @ 60 | 360 | `--check-only` | 1.0 [1.0, 0.9] | — | — | 8.7 |
| check-only-4fmt | 2d | 1080x1080 @ 60 | 360 | `--check-only --format 16x9,9x16,1x1,4x5` | 3.4 [3.4, 2.9] | — | — | 8.7 |
| three-gl-w2-v02 | three | 1920x1080 @ 30 | 240 | `--gl --workers 2 --capture screenshot` | 31.1 [31.1, 27.1] | 7.7 | 7.7 | 8.2 |
| three-gl-w2-cdp | three | 1920x1080 @ 30 | 240 | `--gl --workers 2 --capture cdp` | 25.6 [25.6, 24.1] | 9.4 | 9.4 | 10.6 |
| three-gl-w2 | three | 1920x1080 @ 30 | 240 | `--gl --workers 2` | 24.3 [23.2, 24.3] | 9.9 | 9.9 | 11.5 |
| three-gl-default | three | 1920x1080 @ 30 | 240 | `--gl` | 27.5 [25.0, 27.5] | 8.7 | 8.7 | 11.7 |
| rerun-audio-only | 2d | 1080x1080 @ 60 | 360 | `--audio b.wav` | 0.7 [0.7, 0.7] | 512.7 | 512.7 | 28.5 |
<!-- bench:end -->

**Caveat:** other renders were running on this machine throughout (load 5–28 on 10 cores), so wall
times are noisy; compare rows with similar load, and the `-v02` rows (same run) rather than the
baseline below. Every fast path was checked for identical decoded frames (`tests/test_perf.py`).

| item | change | measured |
|---|---|---|
| E8.2 CDP capture | one CDP `Page.captureScreenshot` (`optimizeForSpeed`) after one seek + rAF round trip; 60 Hz frame cap lifted without `--gl` | 2D template, 1 worker: 18.9 → 10.3 s (**1.8×**); 4 workers: 6.3 → 4.9 s (1.3×); `--check-only`: 1.5 → 1.0 s |
| E8.1 canvas fast path | one full-frame canvas read straight from the canvas, verified against a screenshot first | 2D canvas, 1 worker: 65.7 → 28.1 s (**2.3×**, CDP alone 32.4 s; best runs 59.5 → 20.1 s, 3.0×). Three.js `--gl`, 2 workers: 31.1 → 24.3 s (**1.3×**) |
| E8.3 workers | default = CPU count, max 6 (was half, max 4 → 4 here); frame-count gate | 2D: default 5.0 s = `--workers 4` 4.9 s (encode-bound past 4). Three `--gl`: 6 workers no faster than 2 on this loaded machine (SwiftShader is itself multi-threaded: 2/4/6 workers = 21.8/22.0/23.9 s, CPU 165/182/200 s) |
| E8.4 render cache | rerun with only `--audio` changed reuses `renders/.cache/` | 360-frame render 4.9 s → rerun 0.7 s with `--skip-checks` (1.25 s with the gates) |

E8.1's target was 2× on the Three.js demo. Under SwiftShader the WebGL draw itself costs about 60 ms
of CPU per 1080p frame, which every capture path pays, so reading the canvas instead of
compositing and screenshotting saves about a fifth of the CPU per frame (1.3× wall), not 2×. The
2× (and more) shows on 2D-canvas pages (Zdog, p5, hand-written canvas), where capture was the cost.

Measured and not shipped:
- **JPEG q100 over CDP**: no faster than PNG with `optimizeForSpeed` (~36 ms vs ~36 ms per 1080p
  Three.js frame, 6.7 vs 6.7 ms for the 2D template) and lossy, so no flag for it.
- **Raw RGBA piping**: 8 MB per 1080p frame through the Playwright/CDP channel took 265–390 ms per
  frame (base64 transport), far slower than an in-browser PNG (~5–20 ms) or a CDP screenshot.
- **Frame cap lifted with `--gl`**: ~25% more CPU for Three.js under CDP screenshots, so `--gl`
  keeps the 60 Hz cap.

## Baseline (E0.3, before E8)

Measured 2026-10-14 on the same machine (Apple M4, 10 cores, 24 GB, Chromium 156, ffmpeg 8.0),
v0.2 capture path, default workers 4.

| mode | template | size @ fps | frames | flags | wall (s) | frames/s | samples/s |
|---|---|---|---|---|---|---|---|
| plain-w1 | 2d | 1080x1080 @ 60 | 360 | `--workers 1` | 19.2 | 18.8 | 18.8 |
| plain-w2 | 2d | 1080x1080 @ 60 | 360 | `--workers 2` | 10.4 | 34.7 | 34.7 |
| plain-w4 | 2d | 1080x1080 @ 60 | 360 | `--workers 4` | 6.0 | 59.6 | 59.6 |
| subframes3-w4 | 2d | 1080x1080 @ 60 | 360 | `--subframes 3 --workers 4` | 15.3 | 23.5 | 70.4 |
| check-only | 2d | 1080x1080 @ 60 | 360 | `--check-only` | 0.9 | — | — |
| check-only-4fmt | 2d | 1080x1080 @ 60 | 360 | `--check-only --format 16x9,9x16,1x1,4x5` | 2.6 | — | — |
| three-gl-w2 | three | 1920x1080 @ 30 | 240 | `--gl --workers 2` | 22.0 | 10.9 | 10.9 |

## Notes

- `check-only` runs determinism, loop seam, safe_area and text_duration. text_duration seeks every
  frame (360 seeks here), so it grows linearly with duration × fps.
- Re-run on the same machine to compare: `python3 tests/bench.py --repeat 2` rewrites only the
  block between the bench markers.

## Engines (v0.3, E10.10)

Measured 2026-10-17 on the same machine, `render.py --skip-checks --workers 4` (wall time includes
browser start-up and the encode). The p5 and Zdog pages are the shipped templates and recipes.

| page | engine | size @ fps | frames | flags | wall (s) | frames/s |
|---|---|---|---|---|---|---|
| zdog-composition.html | Zdog (Canvas 2D) | 1080x1080 @ 30 | 180 | `--workers 4` | 6.0 | 30.0 |
| p5-composition.html (flow field, 280 lines) | p5 2D | 1080x1080 @ 30 | 180 | `--workers 4` | 17.0 | 10.6 |
| layered-composition.html | p5 + Zdog + DOM | 1920x1080 @ 30 | 180 | `--format 16x9 --workers 4` | 10.3 | 17.5 |
| recipes/p5-webgl-strands.html | p5 WEBGL + strands | 1080x1080 @ 30 | 120 | `--gl --workers 2` | 39.1 | 3.1 |
| recipes/p5-webgl-strands.html | p5 WEBGL + strands | 1080x1080 @ 30 | 120 | `--gl --workers 4` | 27.6 | 4.3 |
| recipes/p5-webgl-strands.html | p5 WEBGL + strands | 1080x1080 @ 30 | 120 | `--gl --check-only` | 9.4 | — |

- p5 WEBGL with lights, a perspective camera and a p5.strands shader (uniform driven by t) passes
  determinism and the loop seam under `--gl` (SwiftShader). It is CPU-bound: about 4 frames/s at
  1080x1080, so budget ~4 min per 30 s of 30 fps footage with 4 workers.
- The same page also rendered (and passed the gates) without `--gl` on this machine, because
  headless Chromium falls back to software GL; pass `--gl` anyway so the backend is explicit.
- p5 2D cost scales with what each frame redraws (the flow field integrates 280 × 40 segments per
  frame); Zdog scenes of a few hundred shapes run at ~30 frames/s.
- WebGPU (`vendor.py P p5-webgpu`) is not validated and stays experimental.
