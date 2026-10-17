---
name: motion-video
description: Make motion-graphics videos (MP4) by writing the animation as code — HTML/SVG/Canvas/GSAP/Three.js/Zdog/p5.js/shaders — then rendering it frame-by-frame deterministically with headless Chromium and ffmpeg. Use for launch/brand films, product or app demos, UI motion loops, kinetic typography, explainers (science, recipe, process, data), timelines, logo intros, 3D hero scenes, mascot and character animation, generative loops, shader loops, lyric/music videos and social clips (9:16, 1:1, 4:5, 16:9), with synced sound effects and music. Also use to render/QA an existing HTML animation into a video.
---

# Motion Video

You are a motion designer who builds in code. **The picture is a pure function of time**: a
renderer asks for every frame by number, ffmpeg encodes, and automated gates catch defects
before a human looks. Taste comes from a tight brief and concrete numbers, not from effects.

`SKILL_DIR` = the folder holding this file (in Claude Code: `${CLAUDE_PLUGIN_ROOT}/skills/motion-video`).
Needs Python 3 with `pip install playwright numpy pillow`, `python3 -m playwright install chromium`,
and ffmpeg. Check once with `python3 SKILL_DIR/scripts/doctor.py` (prints the exact install command
for anything missing; installs nothing). `S=SKILL_DIR/scripts`;
project folder `P = ./motion/<slug>/`, composition `P/<slug>.html`, duration `D`.

## Workflow

### 1. Brief (always — decide fast, but decide)
Fill every field of `references/brief-template.md` (deliverable, formats, renderer, one-line concept,
hex palette, fonts, locked copy, storyboard, motion rules, audio + hits, banned list, review
rounds if wanted, approval gate). Adapt the closest playbook in `references/genres.md`.
- Ask only for real assets, exact copy/numbers, the song, platform. Default the rest and say
  so. Never invent claims, metrics or quotes. Domain-standard defaults (a published recipe
  ratio, a unit conversion, a well-known public fact) are not invented: use them when the genre
  needs them, mark them `[[DEFAULT: confirm or replace]]` in the brief and list them in the final
  reply. Numbers about the user's product, company or results (metrics, prices, benchmarks,
  quotes) are never defaulted: ask, or leave them out.
- **Reference given** (a video or stills the user supplied; local files only, never fetch one):
  `python3 $S/reference.py <ref> P` → `P/docs/reference/<name>/` (cuts.json, sheet.png,
  shots.png). Look at the sheets, then fill `references/style_guide.md` into `P/style_guide.md`
  **before the storyboard**: take its rhythm, motion and composition; keep the user's brand.
- **Assets** (logo, screenshots, fonts, clips, audio, brand PDF; local paths or chat uploads):
  `python3 $S/ingest.py P <paths…> [--attached]` copies and normalises them into `P/assets/`
  with `assets.json`. Refer to them by id; use them as-is, never redraw or stand in for one.
  Read `references/assets.md` (fonts, images, SVG, clips via `K.loadClip`).
- **Brand check** (when a logo, screenshots, fonts or a brand guide were supplied):
  `python3 $S/brand.py P` → `P/brand.json` + `P/docs/brand_swatch.png` (palette chips, two font
  samples). Show the swatch; the user confirms or overrides (`brand.py P --role accent=#hex
  --font display="Family" --confirm`). Write the confirmed hexes, roles and fonts into the brief's
  `<art direction>`. Unattended: use the suggestion and say so.
- **Footage-led** (a talking clip recut with graphics; the brief has `<footage>`): follow
  `references/footage.md` (transcribe.py → cut.py → story.json → `templates/footage-composition.html`).

### 2. Storyboard, then sign-off
Table: `time | on screen | purpose | exit | carried object`. About one idea per 1–2 s; hook in
the first 0.5–2 s; frame 0 is a finished picture; a breather before the climax; a held final
lockup (≈1 s). With music, pin scene changes to beats. If the user is present, show the
storyboard and format list and wait for approval; otherwise continue, write the assumption into
the brief's `<start>` and repeat it in the final reply.

### 3. Build from a template
The brief's `<renderer>` picks the template.
`python3 $S/scaffold.py <name> --template <renderer> --formats 9x16,1x1 --duration D`
creates `P` with the template (MOTION size, fps, duration set), `kit.js` plus the add-on kits it
loads, a `brief.md` skeleton (kept if one exists) and `assets/ audio/ docs/ renders/`. Or copy the
template **and `templates/kit.js`** (plus its add-on kits) into `P` by hand. Then replace the demo scene.
| renderer | Template | Use for |
|---|---|---|
| `2d` | `templates/composition.html` | DOM/SVG/Canvas 2D: type, UI, explainers, most motion graphics. Preview player built in (Space, ←/→, F formats, G safe areas, `?t=3.2`). |
| `gsap` | `templates/gsap-composition.html` | One **paused** master timeline; `seek(t)` = `tl.seek(t, false)`. `vendor.py P gsap` first. |
| `glsl` | `templates/glsl-composition.html` | Fragment shader on one full-frame triangle, `uTime` from `seek(t)`, loops by phase; DOM type on top. Render with `--gl`. |
| `zdog` | `templates/zdog-composition.html` + `kit-zdog.js` | Characters, mascots, icons, props in flat-round 3D. `vendor.py P zdog`; models via `catalog.py use P <ids>`. Read `references/zdog.md`. |
| `p5` | `templates/p5-composition.html` + `kit-p5.js` | Generative loops, flow fields, glyph type. `vendor.py P p5`. Read the p5 rules in `references/gotchas.md`. |
| `three` | `templates/three-composition.html` | Three.js. `python3 $S/vendor.py P three` first; render with `--gl`. Preview needs http: `python3 -m http.server` in `P` (ES modules don't load from `file://`). |
| `layered` | `templates/layered-composition.html` + `kit-layers.js` | Several engines on one timeline (`K.layers`): one engine per depth plane, at most one WebGL layer. |
| `footage` | `templates/footage-composition.html` + `kit-footage.js` | A talking clip recut with graphics (brief has `<footage>`). Read `references/footage.md`. |

Kit examples: `templates/examples/kinetic-type.html` (type kit + springs), `device-demo.html`
(a screenshot in browser and phone frames, Canvas and DOM).

**3D models (zdog / layered):** search the catalog before modelling anything:
`python3 $S/catalog.py search <words>` (or read `catalog/catalog.json`; previews are
`catalog/<id>.png`). List the matches in the brief's `<assets>`; model something new only when
nothing fits or the user asks for a bespoke asset, and offer a good new model for the catalog.
Recipes per genre (flow field, noise terrain, glyph type, beat pulse, mascot explainer) are in
`templates/recipes/` (see `references/genres.md`).

**Contract** (render.py depends on it): `window.MOTION = {width,height,fps,duration,loop,hits?}`,
`window.ready` (Promise: fonts, images, beats, clips decoded), `window.seek(t)` draws the exact
frame for `t`, in any order, any number of times.

**Kit** (`window.K`, see the comments in kit.js): closed-form springs and `springTrack`, `track`
keyframes, `bezier`, seeded `rand`, `noise`, `stagger`, `wrap`; beats `K.T/K.U/K.at`
(needs `beats.js` above the kit script); `K.resolveHits`; clips `K.loadClip/K.clipFrame/K.drawClip`.
Spring presets `K.SPRING.snappy|ui|soft|camera` (pass one where `w, z` go), `K.wobble`/`K.squash`
for one impact. Images `K.cover`/`K.crop` (ctx or element; focal point, zoom, radius; crop and
scale only) and device frames `K.device` (DOM) / `K.drawDevice` (Canvas). Type `K.glyphs`,
`K.layoutText`/`K.drawGlyphs`, `K.fitText`, `K.rise`/`K.maskRise`, `K.typed`, `K.scramble`.
Add-ons, loaded after kit.js: `kit-zdog.js` (`K.Z`: render, camera, layers, squash, shadow,
models, rig + clips), `kit-p5.js` (`K.sketch`, `K.loopNoise`, `K.presim`), `kit-layers.js`
(`K.layers`, `K.proxy` for canvas-drawn text the gates must see, `K.textBox`).

**Formats** (`references/formats.md`): call `K.init(MOTION)` right after defining MOTION. One
timeline; only layout changes per format, via `K.pick({ '9x16': …, default: … })` and
`K.FORMAT.isPortrait`. Place text from `K.safe.ui` (9x16 reserves top 12 %, bottom 22 %,
right 14 % for platform chrome) and centre portrait groups on it.
- Mark titles, captions, logos, CTAs with `data-safe` (box must stay inside `K.safe.ui`) and
  every text element with `data-text` (must be readable ≥ 8 frames, at ≥ 4.5:1 contrast with
  what's rendered behind its words). Put `data-text` on the element that shows the words, not an
  always-opaque mask.
- The gates read opacity, not masks: text sliding in from off-stage or rising through a mask
  stays at **opacity 0 until it is in place**, and returns to 0 after it leaves.

**Determinism rules** (breaking one is the #1 cause of broken renders): no CSS
transitions/animations, no `setTimeout`/`setInterval`/rAF-held state, no `Date.now()`/
`performance.now()`/`THREE.Clock`, no integrated physics (pre-simulate at fixed dt, index by
frame), no unseeded `Math.random`, no `<video>.currentTime` (ingest clips as frame sequences),
no network at render (local fonts, vendored libraries). Retargeting springs: `K.springTrack`.
Read `references/craft.md` while building and `references/gotchas.md` for engine traps.

### 4. Review loop (cheap → expensive)
```bash
R="python3 $S/render.py"; F=9x16,1x1          # the brief's formats
$R P/<slug>.html --format $F --check-only      # gates: determinism, loop_seam, safe_area, text_duration, contrast, page errors
$R P/<slug>.html --format $F --sheet           # 4x4 sheet per format: LOOK at each (add --phone for critic rounds)
$R P/<slug>.html --stills 0,2.5,4,7.9          # specific moments
$R P/<slug>.html --strip 2:3:6 --subframes 4   # blurred strip across a transition
$R P/<slug>.html --poster 7.5                  # the thumbnail frame (value after the HTML path)
$R P/<slug>.html --contact beats               # one still per downbeat (needs beats.js)
```
Gates sample fixed times (determinism: 8 from a fixed seed; safe_area and contrast: every 0.25 s),
so a pass is evidence, not proof; `--check-only --thorough` samples densely before a hero render.
`--sheet` keeps its 16 stills in `renders/stills/`.
By default run `--check-only`, then `--sheet`, and look at **one sheet per format**; the other
renders are for diagnosing a specific problem or for critic rounds. Judge like a harsh director:
is every paused frame a poster? Type readable, nothing overlapping, clipped or off-brand? Fix
every FAIL, then the worst issue first; patch, don't rewrite; re-check.

### 5. Render, deliver, QA
```bash
$R P/<slug>.html --format $F --deliver --subframes 3 [--gl] [--workers 4] [--scale 2]
python3 $S/check.py P/renders/<slug>_<fmt>.mp4 [--loop] [--max-hold 1.0] [--sync P/audio/sfx_events.json]
```
- `--deliver` → `renders/<slug>_<fmt>.mp4`, `_poster.png`, `_sheet.png`, `_sheet_phone.png` per
  format and `renders/deliver.json` (ffprobe facts). Without `--format`: one native render, no suffix.
- `--subframes N` = real motion blur (3–4 for UI, 6–8 for fast whips). `--scale 2` supersamples
  (crisper type; 4× slower). `--gl` for WebGL/Three/shaders. `--preview` = first 5 s, half res.
- check.py gates: blank frames, single-frame pops, frozen stretches (no 40 px region visibly
  moves), loop seam, loudness, `sync`; with a reference, `--against
  P/docs/reference/<name>/cuts.json` flags pacing > 30 % slower or busier. Fix every FAIL; fix or
  explain every WARN. Cost ≈ 0.1–0.3 s per sample per worker.

### 6. Sound (only if the brief has music or SFX)
Follow `references/audio.md` (or `/motion-audio`). Music is user-supplied only; never fetch
songs. No track → silent or SFX only, and say so. In short: `beats.py --track song --duration D
--out P` **before** the picture is final when anything is beat-timed → `render.py --hits` →
`sfx.py P/renders/<slug>_hits.json --out P/audio/sfx.wav` (project sounds in `P/audio/palette.py`;
user-supplied takes with `--samples DIR`) → `mix.py [--duration D] --out P/audio/mix.wav
[--music P/music.wav] [--sfx P/audio/sfx.wav] --mux <every mp4>` (−14 LUFS, refreshes deliver.json) → `check.py --sync P/audio/sfx_events.json`. Quick path for "just put
this track under it": `render.py … --audio track.wav`.

### 7. Critic rounds (only on request)
Skip unless the user asks ("review it", `--review [N]`) or the brief's `<review>` sets rounds:
they cost several image reads and a re-render each. Rounds = N, else `<review>`, else 2 (3 for
hero pieces); stop at the first `ship` after that; cap 4 (then deliver and list what's open).
The builder never grades its own work: each round, give the `motion-critic` agent the brief, MP4s, `_sheet.png`,
`_sheet_phone.png`, strips / `_beats_sheet.png`, `check.py --json` reports and `P/critique.md`; append
its output unchanged to `P/critique.md`; fix its top 3; re-run 4–5.
**No agents** (Claude app chat): do the pass yourself, explicitly fresh — re-read only the brief
and the renders, not the code — and apply the critic section below.

### 8. Deliver and show
Show the MP4s (send or open them when the host allows). Report the paths in
`P/renders/deliver.json`, the HTML source (the editable master), one line of assumptions and,
if rounds ran, the last scores and verdict; otherwise offer "say *review it* for critic rounds".

## Token economy
- Write the composition once; afterwards change it with small edits, never a full rewrite.
- Read a reference only when needed: audio.md with sound, assets.md with assets, formats.md
  with several formats, genres.md for the brief, craft.md and gotchas.md while building,
  style_guide.md only when the user gave a reference, zdog.md only when the renderer is zdog
  (or layered with a Zdog layer).
- Look only at the images a step names; each image read is expensive. `render.py --quiet`.
- Quote numbers from reports (gates, LUFS, offsets), not whole logs.

## Critic rubric (chat fallback; same as agents/motion-critic.md)
Judge only what's on screen and heard, against the brief; every sheet, every format; readability
on the phone sheet. Any FAIL from check.py, `--check-only` or sync.py is a FAIL gate. Score 1–10,
each with one line of evidence (timestamp or sheet tile):
- **hook**: first 2 s; frame 0 finished, something moves by 0.5 s.
- **readability**: legible at phone size, ≥ 8 clean frames, inside the safe area, not clipped.
- **motion**: arrive fast, land soft; no linear or mushy moves, pops, dead holds > 1 s.
- **variety**: something new every 2–4 s.
- **brand**: supplied assets as-is (a redrawn or stand-in asset scores ≤ 5); brief hexes and
  fonts; no banned effects; no unsupplied claim, number or logo (flagged domain-standard defaults
  are fine). Motion and timing faults belong under motion, not brand.
- **sync**: cuts and hits on beats/SFX, sync offsets ≤ 20 ms (`n/a` if silent).
- **concept**: the one-line idea is legible; the hero is the most memorable thing.

WARNs (`frozen`, `contrast`, `pacing`) are measurements: confirm them on the frames before
docking a score. Every fix must fit the frame: text and key subjects inside `K.safe.ui`.
Verdict: `ship` only if every applicable score is ≥ 8 **and** 0 FAIL gates; else `one more pass`.
Output (appended to `critique.md`; round N = earlier `## Round` headings + 1):
```
## Round N
| dimension | score | evidence |   (one row per dimension above)
**Gates:** 0 FAIL | each FAIL
**Top 3 fixes**  1. RN.1 `[mm:ss.ff]` problem → concrete fix (element, number, easing)
**Ledger update**  - R1.1 fixed | partly | still there — note   (round 1: "none")
**Keep**  - 1–3 things that work
**Verdict:** ship | one more pass
```

## Quality bar
- One concept, executed relentlessly, beats ten effects. If the hero isn't the most memorable thing, start over.
- Things arrive fast and land soft, leave faster than they came, overlap so the frame never
  fully stops; at most a tiny overshoot; no dead holds > 0.5–1 s.
- Transitions are made *of* the previous scene (morph, flood, mask, iris); crossfades are a last resort.
- Default banned list: lens flares, camera shake, RGB-split glitch, random particle bursts, generic
  gradients, bouncy/elastic easing, purple-blue neon, spinning logos, fake dashboards, AI clichés.
- Works with the sound off: on-screen text carries the message; captions ≤ 7 words.
