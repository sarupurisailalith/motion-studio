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
