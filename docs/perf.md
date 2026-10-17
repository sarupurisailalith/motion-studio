# Performance baseline (E0.3)

Measured 2026-10-14 with `python3 tests/bench.py`. Wall time includes Chromium start-up, page load,
the ffmpeg encode and concatenation of worker segments. Full renders use `--skip-checks`; the gates
are timed on their own (`--check-only`). frames/s = output frames / wall time; samples/s counts
every sub-frame screenshot.

## Machine

- **os**: Darwin 25.6.0 (arm64)
- **cpu**: Apple M4
- **cores**: 10
- **memory**: 24 GB
- **python**: 3.14.0
- **chromium**: 156.0.8078.4
- **ffmpeg**: ffmpeg version 8.0

## Results

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
- These numbers are the baseline for the E8 performance work (canvas fast path, CDP capture,
  smarter workers). Re-run on the same machine to compare.

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
