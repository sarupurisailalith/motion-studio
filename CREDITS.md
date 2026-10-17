# Credits

Where Motion Studio adapts ideas, formulas or code from others, the source is credited here and,
for code, in the file header too. Third-party code the plugin downloads for a project (via
`vendor.py`) keeps its own licence and is not part of this repository.

## Ideas and patterns

| Source | Licence | What we took | Where |
|---|---|---|---|
| [WCAG 2.x](https://www.w3.org/TR/WCAG21/) (W3C) | W3C document licence | The relative-luminance and contrast-ratio formulas and the 4.5:1 threshold behind the `contrast` gate. | `render.py` (`rel_luminance`, `text_contrast`) |

## Tools the scripts run on

Not bundled; installed by the user (see the README).

| Tool | Licence | Used for |
|---|---|---|
| [Playwright](https://playwright.dev/) and Chromium | Apache-2.0 / BSD-style | Headless rendering (`render.py`) |
| [FFmpeg](https://ffmpeg.org/) | LGPL-2.1+ (GPL in some builds) | Encoding, analysis, scene-cut detection |
| [NumPy](https://numpy.org/) | BSD-3-Clause | Frame and audio analysis |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | Image I/O and contact sheets |

Adding something adapted from elsewhere (for example the Zdog demo models planned for the 3D
catalog)? Add a row here and a header line in the file, and check the source's licence first.
