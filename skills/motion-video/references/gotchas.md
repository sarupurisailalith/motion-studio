# Failure modes & engine gotchas

Read before building, and again when a QA gate fails.

**Common visual traps:** particle bursts, glows, lens flares, camera shake, RGB split/glitch, crossfades/blur-ins, bouncy easing, gradients on UI chrome, dead time, fake dashboards, spinning logos, tiny unreadable code, mismatched icon strokes and generic AI imagery. These are context-specific: game rewards and glitch music videos can use shake, flashes and particles in measured doses.

Engineering gotchas:
- **`will-change` on camera-scaled elements:** text renders blurry.
- **`opacity`/`filter` on a `preserve-3d` element:** it flattens and both faces show. Fade the wrapper instead.
- **CSS 3D flips of large elements:** these get projected into a screen-filling plane. Do 3D flips in WebGL.
- **Visibility inheritance:** a child with `visibility:visible` shows through a hidden parent, so use `inherit`.
- **`globalAlpha` leaks:** a helper that sets `globalAlpha` must restore it, or fading cards pop.
- **Swapped text inside a morphing shape:** it needs its own clip mask and its own enter and exit timing, or it overlaps. Outgoing titles must leave before incoming titles take the same space.
- **Beat-snapped rotation:** a pattern rotating one notch per beat reads as stutter, so rotate it continuously.
- **Floods:** a fast ease-out flood reads as a jump, so use a soft start. A flood still retreating when the next scene starts reads as a hard cut.
- **Seamless handoffs:** these only work if the last frame of scene A is the first frame of scene B. Draw the outgoing scene under the transition, and give scenes that share an object one shared zoom function.
- **Camera transform on morphs:** the morphing disc must stay inside the same camera transform as the scene it leaves, or it jumps.
- **Mask polarity:** in a CSS radial mask, opaque reveals and transparent hides. Inverting it shows internals everywhere except under the cursor.
- **Alpha and mask edges:** a PNG mask without an alpha channel fills the whole box. Limbs cut by the frame edge show straight edges, so extend the mask past the frame.
- **Top-down 3D camera:** do not position it exactly overhead (the orientation flips 90°), and zero the velocity at stops (overshoot inverts it).
- **Looping tweens:** cancel looping "shake/breathe" tweens and reset them on state change, or they set a value one frame late.
- **Canvas textures:** these need at least 1.5× their maximum on-screen size.
- **Unbounded cursor speed:** keep it under about 65 px/frame, and aim at where the target will be when the cursor lands.
- **Fake ink:** "Do not cross-fade orange into ink". Move an accent element between states instead.
- **Over-strong feedback:** keep impact reactions weak and short, touching only some particles for a few frames, or the subject becomes unreadable.
- **Gates read opacity, not masks:** `render.py --check-only`'s `safe_area` checks any `[data-safe]` element with opacity > 0, and `text_duration` counts frames at opacity ≥ 0.9. Text flying in from off-stage or rising through a mask must sit at opacity 0 until it is in place (and after it leaves), or the gates report false overflows and fake reading time. Put `data-text` on the glyphs' row, not on an always-opaque mask.
- **Fractional mask edges:** an `overflow:hidden` mask at a fractional pixel position under a scaled camera can keep a 1 px row of stale glyph pixels after some seek orders. Round mask positions to whole pixels.
- **Three.js preview from `file://`:** ES modules are blocked there, so the page stays black. Serve the folder (`python3 -m http.server`) to preview; render.py already serves it over http.
- **Sub-pixel CSS `scale()` on small elements:** rounded, bordered or anti-aliased boxes scaled by a non-integer factor can rasterise differently on a second seek, which fails the determinism gate. Animate `width`/`height` (or draw to canvas) and keep positions on whole pixels.
- **Readability:** keep things readable on screen for at least 8 clean frames. A glitch lasts only 1–2 frames and only on a real cut.
- **Honesty:** never invent features, numbers, fake customers, reviews or results. Label generated imagery as a concept. Check music and SFX licences. Never write API keys into files.
- **Slop:** "a video with no bugs is not the same as a good video"; "frame one is a finished picture, never a word halfway through flying in"; and "if the hero object isn't the most memorable thing, start over."
