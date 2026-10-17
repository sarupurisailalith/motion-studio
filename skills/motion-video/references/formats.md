# Formats: one timeline, several aspect ratios

One composition renders to every delivery shape. The timeline is shared, and only the layout
changes per format. `render.py --format 16x9,9x16` renders each one in turn.

| name | size | typical use |
|---|---|---|
| `16x9` | 1920 × 1080 | YouTube, web hero, decks |
| `9x16` | 1080 × 1920 | Reels, TikTok, Shorts, Stories |
| `1x1` | 1080 × 1080 | feeds |
| `4x5` | 1080 × 1350 | Instagram and LinkedIn feed |
| `native` | `MOTION.width × MOTION.height` | the default when no format is requested |

### Safe areas (`K.safe`, integer stage px)
- **`title`**: a 5 % inset on every side, in every format. Keep everything that matters inside it.
- **`ui`**: where text must stay so platform chrome doesn't cover it. It equals `title` except:
  - `9x16`: x 6 %, y 12 %, w 80 %, h 66 %. The top 12 % holds the account and search bar. The bottom 22 %
    holds the caption, music ticker and progress bar. The right 14 % holds the like, comment and share
    buttons. The rect therefore sits slightly left of centre and above it.
  - `4x5`: x 5 %, y 8 %, w 90 %, h 80 %, for the feed header and caption overlays.
- `native` uses `title` for both rects, even when it happens to be portrait. To check against
  platform chrome, render with `--format 9x16`.

### Kit usage
Copy the template **and `kit.js`** into the project folder (the template loads `kit.js` from its own
folder; without it nothing renders). Load it before the scene script. Then:
```js
window.MOTION = { width: 1080, height: 1080, fps: 60, duration: 6, loop: true };
K.init(window.MOTION);                    // FIRST: applies ?format=..&w=..&h=.., sets K.FORMAT/K.safe
const { width: W, height: H } = window.MOTION;
const L = K.pick({                        // per-format numbers; default covers the rest
  default: { font: 190, titleY: 0.24 },
  '9x16':  { font: 170, titleY: 0.34 },
});
const S = K.safe.ui;                      // { x, y, w, h }: place captions and HUDs from it
```
- `K.FORMAT` = `{ name, W, H, isPortrait, aspect }`. Branch on `K.FORMAT.isPortrait` for
  one-off tweaks, and use `K.pick` for tables of numbers.
- `K.pick(map)` throws if the map has neither the current format nor `default`. A missing layout
  should fail loudly rather than fall back to a 16:9 layout in portrait.
- In the Three template, `K.init` sizes the renderer and the camera aspect. Widen the vertical FOV
  in portrait (`K.pick({ '9x16': 52, default: 35 })`).

### Markup the gates read (render.py `--check-only`)
- `data-safe` on any element whose box must stay inside `K.safe.ui`. Use it on titles, captions,
  logos and CTAs. The box is checked after the camera transform, so leave margin for pushes
  (a 1.035 push moves an edge 3.5 % further from the centre). Put text masks on the element itself,
  sized to the word, not full-width.
- `data-text` on any text element. A visible run (opacity ≥ 0.9, on stage) shorter than 8 frames
  warns. Put it on the element that actually shows the words (the glyph row), not on a mask or
  wrapper that stays opaque while the text is clipped out of it.
- `contrast` (same `data-text` elements, every 0.25 s while visible): the words are hidden, the
  frame is rendered, and the text colour (with its opacity) is compared with the pixels behind
  each line of words. Below 4.5:1 over 90 % of that area warns, with the element and time. A
  pill or panel that is part of the element (or under it) counts as background, so text on a
  moving background passes when it carries its own backing. The colour is read from the
  `data-text` element itself, so put the attribute where the text colour is set. Text drawn into
  a canvas, and gradient or transparent fills (`background-clip: text`), can't be measured and
  are listed as such.
- **Both gates read effective opacity and boxes, not masks or clipping.** `safe_area` checks every
  `[data-safe]` element whose opacity is > 0, wherever it is. So text that slides in from off-stage
  (or rises from below a mask) must stay at **opacity 0 until it is in place**, and go back to 0
  once it has left. Otherwise the gate sees it outside `K.safe.ui` mid-flight and fails, and
  `text_duration` counts frames when nothing is readable. When the text is fully clipped anyway,
  switching opacity costs no pixels (the 2D template does this for its title).
- HUDs and chrome-like overlays go **outside** the camera container, so pushes never move them.

### Layout rules
- Use one timeline for every format and never fork the timing. Only positions, sizes and type scale
  change.
- Switch layout with `K.pick`; never use separate HTML files per format.
- Portrait stacks content vertically. Centre the group on the `ui` rect's centre (about 45 %
  down in 9x16), not on the frame's centre.
- Size type from the frame's short side: 9x16, 1x1 and 4x5 are all 1080 px wide, so portrait type ≈ the 1x1 size (up to ~10 % larger for a single hero word); 16x9 can go larger. Always measure the widest word against `K.safe.ui.w`.
- If a shot is designed landscape-first, keep the key subject inside the centre 9:16 band so a
  crop still works.
- **Non-text content in the platform-UI bands** (9x16: top 12 %, bottom 22 %, right 14 %; 4x5:
  the strips outside `ui`): backgrounds, texture, illustration and the edges of a hero image may
  extend into them, and full-bleed backgrounds should. The platform will cover part of them, so
  nothing there may carry meaning: no text, numbers, logo, CTA, the product's key detail or a
  face's eyes. The hero's focal point stays inside `K.safe.ui`; a hero may be cropped by a band,
  never depend on what the band hides.
- Check every format on the contact sheet. "Looks composed" applies to each one separately.

### Preview keys (`composition.html`)
- **F** cycles `native → 16x9 → 9x16 → 1x1 → 4x5 → native`. It reloads the page with the same
  `format/w/h` parameters render.py uses, so preview and render match.
- **G** toggles the safe-area overlay: dashed is `title`, solid is `ui`. The Three template has
  F only, and previews only over http (`python3 -m http.server` in the project folder, then open
  `http://localhost:8000/<file>.html`): ES modules don't load from `file://`.
- None of the preview UI exists with `?render=1`.
