# Craft: what makes it look professional

Concrete numbers beat adjectives. Use these as defaults; deviate on purpose.

### Easing and springs (the most common topic)
- Closed-form critically damped spring: `1 - (1 + ωt)·e^(−ωt)`, with ω between 12 and 40, "so nothing ever passes its target". Use exponential ease-in/out for wipes, presses and exits.
- When a value changes target many times, sum one spring step-response per change. The value then stays a pure function of t.
- Damping numbers: shape ζ 0.72 with settle 0.35 s, camera ζ 1.0 with settle 0.6 s. The camera settles more slowly than the shape.
- Kit presets (settle = within 2 % of the target): `K.SPRING.snappy` ω 38.8 ζ 1, 0.15 s (presses, toggles) · `.ui` ω 16.9 ζ 0.72, 0.35 s, 3.8 % overshoot (shapes, cards) · `.soft` ω 11.7 ζ 1, 0.5 s (big panels) · `.camera` ω 9.7 ζ 1, 0.6 s. Impacts: `K.squash(dt)` (volume-preserving, 12 % peak) or `K.wobble(dt)`, on one element only.
- The morph curve `cubic-bezier(.45,0,.15,1)` over 0.8 s, with the camera zoom riding the same curve so the shape changes "barely notice". For editorial entrances use `cubic-bezier(.16,1,.3,1)` over 0.6–0.8 s.
- "Arrive fast, land soft": cover 12–19% of the remaining distance per frame.
- "Tiny overshoot at most". "No repeated bouncing or large elastic overshoots". Elastic deformation is reserved for one element only.
- Leading-edge stretch: the two edges of a tab indicator or toggle knob ride different springs, so the leading edge stretches ahead of the trailing one.
- Direct manipulation: while a drag is held, the value follows the cursor. On release, a spring starts from the release position and velocity.
- Rhythm of speed: "things land slowly enough to read, leave fast, and the next thing slows as it arrives; no linear motion". Overlap moves so the frame never stops and starts all at once.

### Staggering and timing numbers
- Per-word pull-up: 0.6 s each with a 0.08 s stagger and a 20 px rise. A paragraph follows at +0.5 s and the CTA at +0.7 s.
- Per-glyph stagger of a 1/16 note at 120 BPM (125 ms). Letters drop at one every 0.05 s. General stagger of 2–4 frames. UI card timing: 280 ms cards, 220 ms title, 160 ms metadata, 60 ms stagger.
- Moves start 0.05 s before their beat so they land on it.
- Composition density: about 12–15 compositions per 30 s, each lasting 1.4–3.5 s. "Most visual ideas last about 1 s". A feature should stay on screen at least 2.5 s in app demos.
- Hold limits: no hold longer than 0.5 s (showreel), 1 s (launch) or 1.5 s (brand film). There is also a frozen-time budget: at most about 1 s per 30 s, and no still stretch longer than about 0.5 s.
- Put a 0.3–0.5 s anticipation "tame" before each highlight.
- Colour changes fade over about 0.35 s. Carousel swaps glide for about 0.55 s. A flood takes about 0.3–0.35 s and must overscale past the corners.
- Content enters after its container starts morphing and leaves before the next morph. Content swaps use a 12 px blur plus a 0.15 s fade.

### Camera
- The camera never fully rests: a slow push of 1.03–1.07 on every scene, a "slow handheld float", or a micro-breath of scale 1.000→1.012→1.000 on the final hold.
- Use one camera transform on a container, keyed by [time, zoom, x, y]. Interpolate zoom in log space.
- Give the camera one eased move per scene. Never zoom in and straight back out. Never reverse direction. Never zoom into an off-centre dot; open the dot as an iris instead.
- Limit the camera vocabulary and give each move a purpose: pullback, roll (one 70° roll with the active phrase counter-rotated) and velocity-match. Alternatively, lock the camera entirely "like a drafting table".
- Punch-in of 1.0→1.08 and horizontal smash-pans only on beats, never random drift.
- Reframe "screen-studio style" so each UI state fills the frame, and scale the cursor with it.
- In 3D, keep elevation at 35–55°. In a top-down game view, look slightly ahead of travel and pull back with speed.

### Transitions between scenes
- **Shared-element handoffs:** a carried object lands on exactly the same pixels on both sides of a cut. Measure positions at runtime.
- **Floods:** a colour floods from an object, holds, and contracts into the next object. Switch a huge flood circle to a full-frame rect once it covers the frame. Ease a closing iris by area, not radius.
- **Other devices:** iris opens with 6 blades, goo split and merge (blur plus alpha threshold, then composite the source on top so content stays sharp), masks cut from the outgoing word's outlines, and one horizontal scan line.
- **Foreground as transition:** the front object moves toward the camera while the next scene waits underneath.
- **Cut rules:** match size, direction and subject across a cut. Reserve hard beat cuts for moments that benefit from an abrupt change.

### Text reveal styles
- Letters rise through a mask line one by one. This is the most common reveal.
- Typing derived from time: `chars = floor(progress × length)`, with a caret that blinks only when idle and a natural keystroke rhythm (`K.typed(text, t, {at, cps})`). Rises: `K.glyphs` + `K.maskRise` (DOM) or `K.layoutText` + `K.rise` + `K.drawGlyphs(…, {mask: true})` (Canvas); size headlines with `K.fitText`. Scrambles: `K.scramble(text, t, {at, dur, seed, snap})`.
- Captions light word by word on TTS or whisper timestamps (grey→white over 0.2 s). Keep them to 7 words or fewer, one idea per shot, with hand-placed line breaks.
- Other styles: rolling word swaps (vertical), scrambles (seeded Fisher–Yates per glyph) that snap on the beat, counters with tabular numerals, and print misregistration (±2–4 px magenta and green at 40%) on accent frames only.
- Type sizing rules: "Text should feel like product advertising, not oversized presentation headings". Display tracking of −40 to −80 (or −0.07 em at line-height 0.85), mono at +20. No full stops on headlines.

### Texture, glow and grade
- Fresh grain every frame, halation on bright edges, vignette about 0.65× at the corners, warm lifted blacks, and a 1 px chroma fringe with edge-clamped shifts. These are applied as a numpy post-pass.
- Soft light without hard edges: conic-gradient rays in 2–3 layers, a flash capped at 0.8 intensity with `screen` blend, glow placed behind the subject, and shockwaves as three strokes (wide and faint, medium, thin and bright).
- Pencil look: resample strokes, perturb them with slow sines whose phase changes 8×/s, stroke twice (full width at 90%, half width at 40%), knock out paper tooth, then multiply.
- Hologram as line density only: a white core at 30% of line width, and scan lines on an 8 px pitch whose thickness follows the lighting. Explicitly no blur halo.
- Liquid glass: each glass element clones the scene behind it and filters it through an SVG feImage displacement map with 3 feDisplacementMaps at slightly different scales (chromatic edges), plus a rim light. `backdrop-filter:url()` misreads this in Chromium. A cheaper version is a pre-blurred photo clipped to the shape, plus a tint and a gradient rim.
- Cel-shaded 3D: MeshToonMaterial with a 3–4 step ramp. Outlines come from post-process normal and depth edge detection, not from the inverted-hull trick. Supersample 1.5×.
- 3D brand colour: measure the rendered background pixel and adjust until it matches the brand hex.

### Motion blur
- Render N subframes per output frame and blend them (ffmpeg `tmix`). N is 3 (at t−, t, t+1/240 s), 4, 6, 8, or 16 spp for raymarching. Use 8 subframes for fast whips because 4 ghosts on them.
- Counters read the frame's time, not the subframe's time, or the digits smear. Keep stationary text sharp. Motion blur may affect trailing geometry, never the active text.

### Sound
- Analyse the beat grid with numpy, start on a downbeat, and calibrate to the real kick hits. Every cut lands on a downbeat and every UI hit on a beat.
- Place each SFX by its measured transient peak, not its file start. Use one soft whoosh per real scene change and clicks only on real on-screen actions. Keep effects quieter than the music.
- Mix: loudnorm to −14 LUFS (−16 in some). The narrator sits 10–15 dB over the music, with the music ducked −18 dB under speech. Always export a music-only version.
- Synthesis: choose Web Audio or numpy for generated sound, or use licensed SFX files. Initialise Web Audio only on the first click and add a mute toggle.
- "The video must make sense with the sound off."
