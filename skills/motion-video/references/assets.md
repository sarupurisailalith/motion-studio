# Local assets: intake and use

`scripts/ingest.py PROJECT PATH... [--attached] [--max-dim 3840] [--clip-max-dim N] [--clip-fps N]` copies files
and folders (or Claude app chat uploads, with `--attached`) into the project. Nothing is
referenced in place, so the project folder renders anywhere. Re-running merges by original path.
Exit 1 means a file was `missing` or `unreadable`. Those are listed by name in the summary JSON.

```
<project>/assets/
  assets.json   assets.js (window.ASSETS = …)   fonts.css
  images/  svg/  fonts/  audio/  docs/  video/<id>/00000.jpg …
```

Every entry has `id` (slug of the file name, `-2`, `-3` on clashes), `kind`, `path` (relative
to the project), `source` (`local`|`attached`) and `orig`. Look up assets by id, not by file name.

| kind | What ingest.py does | Extra fields |
|---|---|---|
| image | PNG, JPEG and WebP kept. TIFF, BMP, GIF (first frame), HEIC/AVIF → PNG. EXIF rotation applied. Long side capped at `--max-dim`. | `w h alpha` |
| svg | Sanitised: scripts, `on*` handlers, `<foreignObject>`, external `href`/`url()`/`@import` and DTD entities removed. Shapes kept. | `w h` |
| font | TTF/OTF/WOFF/WOFF2 checked; name read from the font. | `family style weight` |
| video | Decoded to a JPEG frame sequence at `--clip-fps` (default: the piece's fps from MOTION or brief.md, else 30; variable-rate footage is resampled to a constant rate). Long side capped at `--clip-max-dim` (default `--max-dim`). Its sound becomes an `audio` entry `<id>-audio`, sample-aligned to frame 0 | `w h fps frame_count duration pattern audio` |
| audio | → 48 kHz stereo 16-bit WAV (a clip's own sound also has `of`: the clip id) | `duration sr` |
| doc | PDF/TXT/etc. copied (an unknown type is stored as a doc with a note) | — |

## Using each kind in a composition

**Fonts.** `<link rel="stylesheet" href="assets/fonts.css">`, then use the `family` from
assets.json. `window.ready` must await `document.fonts.ready` (composition.html already does; add it in the three template if you use web fonts there).
For a weight that was never ingested the browser fakes bold. Don't rely on that.

**Images.** `<img src="assets/images/hero-shot.png">`. Await every image in `window.ready`
(`img.decode()`). Size boxes from `w/h` so nothing reflows when the image arrives.

**SVG.** Use `<img src="assets/svg/logo.svg">` for a static mark, or inline the file's markup
when you need to animate parts of it (stroke draw, per-path reveals). The file is already
sanitised, so inlining is safe.

**Video clips.** Load the inventory with `<script src="assets/assets.js"></script>`, then:

```js
const clip = ASSETS.assets.find(a => a.id === 'demo');
window.ready = (async () => { await K.loadClip(clip); /* fonts, images … */ })();
// in seek(t) / draw:
K.drawClip(ctx, clip, t - clipStart, x, y, w, h);   // or K.clipFrame(clip, t) → <img>
```

Clips longer than ~20 s: `K.loadClip(clip, { window: 2 })` keeps only ~2 s each side decoded
(full preload of a 2 min 1080p clip is ~25 GB of bitmaps); then `seek` must
`await K.clipSeek(clip, t)` before drawing. Footage-led pieces: `references/footage.md`.

Frame = `clamp(floor(t * fps), 0, frame_count - 1)`. Hold or loop by mapping `t` yourself.
Clips are frame sequences because `<video>.currentTime` seeking isn't frame-exact. It lands on
nearby keyframes, differs between runs, and fails the determinism gate. A sequence is just
images, so every seek is exact and repeatable. Use `--clip-fps` equal to the piece's fps for
1:1 frames. A lower rate saves disk space but shows the clip at a lower frame rate.

**Audio.** Audio isn't loaded by the page. A clip's own sound (`<clip>-audio`) feeds
`transcribe.py` and `cut.py voice` (footage.md). Use `assets/audio/<id>.wav` with the audio pipeline
(`beats.py --track`, `mix.py --music/--vo`; see `audio.md`) and mux it at render time.

**Docs.** Read brand guides and copy docs for colours, type and wording. Quote copy exactly. Never
paraphrase claims.

## Rules

- **Supplied assets are used as-is.** Never redraw, trace, recolour, restyle or "approximate"
  a logo, screenshot or product shot. Crop, scale, mask, frame and move them only. If an asset
  is missing or unusable, ask for it. Don't build a stand-in.
- Everything the picture depends on loads before `window.ready` resolves. No network at render.
- Confirm the user owns the assets or may use them. Fonts are used for this render only and
  never redistributed.
- Don't edit `assets.json`, `assets.js` or `fonts.css` by hand. Re-run ingest.py instead.
