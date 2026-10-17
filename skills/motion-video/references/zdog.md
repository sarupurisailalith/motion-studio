# Zdog: characters, props and icons in flat-round 3D

Read this only when the brief's `<renderer>` is `zdog` (or `layered` with a Zdog layer).
Zdog (MIT, Metafizzy) draws round, flat-shaded pseudo-3D on a 2D canvas. It suits mascots,
friendly explainers, icons, product props and diorama scenes. It does not suit realism,
lighting or perspective; use Three.js for those.

## Set up

```bash
python3 $S/vendor.py P zdog                       # vendor/zdog.dist.min.js + zfont.min.js (pinned, MIT)
python3 $S/catalog.py search <what the brief needs>   # reuse before modelling (rule below)
python3 $S/catalog.py use P pip parcel pine        # models/*.js + kit-zdog.js (+ kit.js)
cp SKILL_DIR/templates/zdog-composition.html P/<slug>.html
```
Script order: `vendor/zdog.dist.min.js` → `kit.js` → `kit-zdog.js` → `models/*.js` → scene.
Render without `--gl`: Zdog is Canvas 2D. About 2 s of CPU per second of 30 fps 1080p.

## The contract, Zdog style

- Never use `Zdog.Illustration`, `Dragger` or `requestAnimationFrame` for the picture. Build the
  graph once, then `pose(t)` sets every transform from `K.track` / `K.springTrack` / rig clips,
  and `K.Z.render(scene, ctx, view)` draws one frame.
- `K.Z.render` rebuilds every Group's sort list first (`canonicalSort`). Without that,
  `Group.updateSort` re-sorts last frame's order in place, so ties depend on seek history and the
  determinism gate fails.
- One canvas at `W × dpr` (`K.Z.canvas(W, H)`), so `--scale 2` stays crisp. `view = {zoom, cx, cy}`
  puts the scene origin at (cx, cy) CSS px with `zoom` px per model unit; lay it out with `K.pick`
  and `K.safe.ui` like any template.
- Text people must read goes in the DOM over the canvas (`data-safe data-text`), or is drawn on
  the canvas with a `K.proxy` box (kit-layers.js) so the gates still see it. Zfont 3D type is for
  display words only, and needs a local `.ttf` (ingest.py), never a URL.

## K.Z reference (kit-zdog.js)

| helper | what it does |
|---|---|
| `render(scene, ctx, {zoom, cx, cy, background, clear})` | canonical sort, `updateGraph`, draw (`clear: false` draws over a shared canvas); keeps the view for `project` |
| `project(anchor)` | screen `{x, y, z}` (CSS px) after the last render: pin DOM text, `K.proxy` boxes or hits to 3D points |
| `camera(scene)` → `{world, set({yaw, pitch, target, level})}` | orbit camera; add the set to `world`; `pitch > 0` looks down |
| `levelRoll(yaw, pitch)` | `−atan2(sin yaw·sin pitch, cos yaw)`: keeps a course along x level (`level: true`); leans verticals, so keep yaw small |
| `layer(item, bias)`, `LAYERS` | fixed depth bias per plane (FAR −40000 … FORE +10000) so big ground solids never trade places with the character |
| `squash(anchor, amt, pivot)` | volume-preserving (x·y·z = 1); the pivot (feet) stays put |
| `shadow(caster, surfaceFn, opts)` → `{shape, update()}` | contact shadow on `surfaceFn(x, z)`, shrinking with height |
| `extrude(shape, depth, layers, {side})` | fake extrusion: stepped copies back along −z (Zdog has none) |
| `shade(hex, normal, light)`, `boxFaces(hex)`, `mix(a, b, p)` | flat Lambert face colours from one base colour |
| `show(item, on)` | hide or show a whole subtree |
| `model(id, def)`, `make(id, addTo, {palette, scale, translate})` | catalog models (below) |
| `rig(joints)`, `CLIPS`, `clip(name, params)`, `settle(u, l)` | character animation (below) |

## Rig and clips

Characters share one joint convention: `root` (feet, travel and facing), `hips` (squash pivot
at the feet), `spine`, `neck`, `head`, `armL/R`, `forearmL/R`, `legL/R`. `K.Z.rig(m.joints)`
captures the rest pose; each frame `rig.pose(t, layers)` resets to rest and adds every layer:

```js
rig.pose(t, [
  { clip: 'idle', period: D / 3 },                            // loops: keep periods dividing D
  { clip: 'run', at: 1.2, until: 4.6, out: 0.3, stride: '0.5b' },
  { clip: 'hop', at: '8b', h: 30 },                           // beat-snapped (needs beats.js)
  { clip: 'wave', at: 8.7, len: 1.5 },
]);
```
Layers are additive offsets, so they stack, blend (`weight`, `in` / `out` fades) and time-shift
(`at`, `speed`). Library: `idle, anticipate, hop, leap, land, run, wave, point, turn-to-camera,
drop-in, spin-reveal`. Starting numbers (from the Pip spikes): stride 0.36 s; crouch 0.15–0.25 s;
squash ≤ 0.24, then `l·e^(−7τ)·cos(16τ)` (tapered to exactly 0, so loops stay seamless); arm
overlap `springTrack` ω 14–16, ζ 0.75–0.8. Banned: elastic easing, landing camera shake.
A one-shot clip holds its last value after it ends; entrances (`drop-in`, `spin-reveal`) hold
their first value before `at`. Extra per-shot touches (head follows the camera, blinks) go after
`rig.pose`, as `+=` on the joint.

## The catalog (search first)

`SKILL_DIR/catalog/catalog.json` lists original models (characters `pip`, `bolt`; props `parcel,
coin, phone, chart-bars, house, plant`; scenery `pine, round-tree, rock, stepping-stone,
ground-block, stream`; icons `icon-star, icon-heart, icon-check`) with tags, size, joints,
palette slots, supported clips and a preview still `catalog/<id>.png`.

- **Rule:** search the catalog first (`catalog.py search …`, or read `catalog.json` and look at
  the previews) and list the matches in the brief's `<assets>`. Model something new only when
  nothing fits or the user asks for a bespoke asset. A good new model can be proposed for the
  catalog (same convention, a turntable that passes the gates, a preview).
- **Convention** `models/<id>.js`: `K.Z.model(id, { palette: {slot: hex}, build(addTo, opts) })`,
  where `build` returns `{ root, joints, size: {w, h, d}, anchors }` (plus optional `animate(t, D)`
  or `blink(t, times)`). Colours come only from palette slots (`primary, shade, accent, ink, light,
  neutral`); `K.Z.make(id, addTo, { palette: brand })` recolours a model from the brief's palette
  (a brand `primary` without `shade` gets a derived shade). Characters use the joint names above,
  so every clip works on every character.
- `catalog.py turntable <id> <dir>` builds a turntable page for one model (render it with
  `render.py --check-only` or `--sheet`); `catalog.py previews` regenerates the stills.
- Supplied brand assets are never redrawn as Zdog models (E3.9). A catalog model is a generic
  stand-in only where the brief allows illustration.

## Modelling tips

- **Stroke is volume:** a `Shape` with no path and a big `stroke` is a sphere; a two-point path
  is a capsule. Most characters are spheres and capsules.
- **Faces and decals in a Group** (`updateSort: true`) so pupils always draw over eye whites.
- **Symmetry:** build one side, then `copyGraph({ translate: { x: -x } })`.
- **Diorama:** think in front-facing layers (sky, ridge, mid trees, stage, foreground), each with
  `K.Z.layer` bias, and swing the camera only ±0.5 rad so the layers read as depth.
- **Camera vocabulary:** orbit-track (yaw follows the action, small pitch) plus `zoom`. There is
  no dolly or perspective: depth reads only through rotation and overlap.

## Mixing engines

- **Separate canvases** (the usual way): `K.layers` in `templates/layered-composition.html`, one
  engine per depth plane.
- **One shared 2D canvas** (validated): inside a p5 `draw`, call
  `K.Z.render(scene, p.drawingContext, { zoom, cx, cy, clear: false })` between p5 calls, e.g.
  p5 sky → Zdog character → p5 mist in front. K.Z.render saves and restores the context, so p5's
  own transform survives. Use it when an atmosphere layer must pass in front of the character.
- **Zdog (or p5) canvas as a Three.js texture** (validated with `--gl`): draw the Zdog scene to an
  offscreen canvas (`dpr: 1`, power-of-two size) inside `seek(t)`, set `texture.needsUpdate = true`,
  then `renderer.render`. Good for a character on a 3D screen or a sign in a Three scene.
- Both pass determinism and the loop seam (`tests/fixtures/engines/spike_*.html`).

## Limits and gotchas

- Orthographic only: no perspective, no fog, no dolly.
- No lighting or textures: shading is baked per face (`boxFaces`, `shade`) and does not relight
  as things rotate. Fake a key light with a lighter blob (see `round-tree`).
- Sorting is per shape by average z: large flat shapes (ground slabs, walls) z-fight with small
  ones in front of them. Fix with `K.Z.layer` biases or by splitting the big shape.
- `Cone`, `Cylinder` and `Hemisphere` break under non-uniform scale (their outlines are computed
  for a uniform scale): squash characters made of strokes and boxes, not cones.
- No SVG import and no real extrusion: `K.Z.extrude` stacks copies; keep the depth small.
- Zfont reads a local `.ttf` through `fetch`, so a Zfont page needs http (render.py serves it;
  preview with `python3 -m http.server`).
- `shape.scale` may be a number or a vector; `K.Z.squash` sets a vector.
