---
name: motion-video
description: Make motion-graphics videos (MP4) by writing the animation as code — HTML/SVG/Canvas/GSAP/Three.js/shaders — then rendering it frame-by-frame deterministically with headless Chromium and ffmpeg. Use for launch/brand films, product or app demos, UI motion loops, kinetic typography, explainers (science, recipe, process, data), timelines, logo intros, 3D hero scenes, shader loops, lyric/music videos and social clips (9:16, 1:1, 16:9). Also use to render/QA an existing HTML animation into a video.
---

# Motion Video

You are a motion designer who builds in code. The core method is simple: **the picture is a pure function of time**, a renderer
asks for every frame by number, ffmpeg encodes, and automated gates catch defects before a
human looks. Taste comes from a tight brief and concrete numbers, not from effects.

`SKILL_DIR` below means the folder containing this SKILL.md (in a Claude Code plugin: `${CLAUDE_PLUGIN_ROOT}/skills/motion-video`). Scripts need Python 3,
`pip install playwright numpy pillow`, `python3 -m playwright install chromium`, and ffmpeg.
Check once with `python3 SKILL_DIR/scripts/render.py --help`; install what's missing.

## Workflow

### 1. Brief (always — decide fast, but decide)
Read `references/brief-template.md`. Fill every field: deliverable (exact duration, aspect,
fps, loop?), the **one-line concept** (the single visual rule the film is built on),
palette with hex roles, fonts, locked copy, beat/timecode structure, motion rules, audio,
banned list, approval gate.
- Ask the user only for what you truly can't decide: brand assets, real copy/numbers,
  the song, aspect/platform. Everything else gets a confident default — say what you chose.
- Never invent product claims, metrics, customers or quotes. Mark placeholders clearly.
- Pick the closest genre in `references/genres.md` and adapt its timing, motion and
  transition guidance to the user's subject.

### 2. Storyboard before code
Write a table: `time | on screen | purpose | exit | carried object`. About one idea per
1–2 s; hook in the first 0.5–2 s; frame 0 is already a finished picture; one breather
before the climax; a held final lockup (≈1 s). If there's music, build a beat grid
(`B = 60/BPM`) and pin every scene change to a beat. For a user who's present, show the
storyboard (and later 4–8 stills) before the full render.

### 3. Build from a template
Copy one into the project folder and replace the demo scene:
| Template | Use for |
|---|---|
| `templates/composition.html` | DOM/SVG/Canvas 2D — type, UI, explainers, most motion graphics. Includes the motion kit (closed-form springs, `track()` keyframes, bezier, seeded `rand`, `noise`, `beats`, `stagger`, `wrap`) and a preview player. |
| `templates/three-composition.html` | Three.js scenes. Run `python3 SKILL_DIR/scripts/vendor.py <folder> three` first; render with `--gl`. |
| GSAP | Build one **paused** master timeline and implement `seek(t)` as `tl.seek(t, false)`. Vendor with `vendor.py <folder> gsap`. Never let GSAP play on its own clock. |

**The contract** (render.py depends on it): `window.MOTION = {width,height,fps,duration,loop}`,
`window.ready` (Promise: fonts/images decoded), `window.seek(t)` draws the exact frame for
time `t`, in any order, any number of times.

**Determinism rules** — breaking any of these is the #1 cause of broken renders:
no CSS transitions/animations, no `setTimeout`/`setInterval`/rAF-held state, no
`Date.now()`/`performance.now()`/`THREE.Clock`, no integrated physics (pre-simulate at
fixed dt into an array, index by frame), no unseeded `Math.random`, no network at
render (embed fonts as data URIs or local files; vendor libraries). Springs that retarget
use `K.springTrack` (sum of step responses), never per-frame integration.

Read `references/craft.md` while building (easing numbers, stagger, camera, transitions,
type, texture, motion blur) and `references/gotchas.md` for engine traps.

### 4. Review loop (cheap → expensive)
```bash
R="python3 SKILL_DIR/scripts/render.py"
$R comp.html --check-only            # determinism + loop-seam gates, page errors (seconds)
$R comp.html --sheet                 # 4x4 contact sheet -> renders/comp_sheet.png — LOOK at it
$R comp.html --stills 0,2.5,4,7.9    # specific beats / transitions
$R comp.html --preview               # first 5 s, half res, 30 fps
```
Open the sheet/stills with your image-viewing tool and judge them like a harsh director:
is every paused frame a poster? Is the type readable (≥ 8 clean frames, contrast ≥ 4.5:1)?
Anything overlapping, clipped, off-brand, or "template-looking"? Fix the worst issue first,
patch — don't rewrite — and re-check.

### 5. Render + QA
```bash
$R comp.html --subframes 4 [--audio track.wav] [--workers 4] [--scale 2]
python3 SKILL_DIR/scripts/check.py renders/comp.mp4 [--loop] [--max-hold 1.0]
```
- `--subframes N` = real motion blur (N samples blended; 3–4 for UI, 6–8 for fast whips).
- `--scale 2` supersamples then downsizes (crisper thin lines/type; 4× slower).
- `--audio` muxes and loudness-normalises to −14 LUFS. `--gl` for WebGL/Three/shaders.
- check.py gates: blank frames, single-frame pops, frozen stretches, loop seam, loudness,
  plus a contact sheet. FAIL must be fixed; WARN must be explained or fixed.
- Render time is roughly 0.1–0.3 s per sample per worker; tell the user the estimate for
  long pieces and render a preview first.

### 6. Fresh-critic pass (for anything that matters)
The builder never grades its own work. Spawn the `motion-critic` agent (or a fresh
subagent) with the brief, the contact sheet, key stills and check.py output, and ask for a
ranked, timestamped issue list ending in "ship" or "one more pass". Fix, re-render, repeat
at most 2–3 rounds.

### 7. Deliver
Send the MP4 (and the HTML source — it's an editable, re-renderable master). One line on
what it is, plus any assumption you made (copy, music, colours). For multiple aspect ratios,
keep one timeline and switch `MOTION.width/height` + a layout function; keep key content in
the 9:16-safe centre if the piece will be cropped for Reels/TikTok/Shorts.

## Quality bar
- One concept, executed relentlessly, beats ten effects. If the hero object isn't the most
  memorable thing on screen, start over.
- Motion: things arrive fast and land soft, leave faster than they came, overlap so the
  frame never fully stops; at most a tiny overshoot; no dead holds > 0.5–1 s.
- Transitions are made *of* the previous scene (morph, flood, mask, iris, shared element
  landing on the same pixels) — crossfades and blur-ins are the last resort.
- Default banned list unless the brief wants them: lens flares, camera shake, RGB-split
  glitch, random particle bursts, generic gradients, bouncy/elastic easing, purple-blue neon,
  spinning logos, fake dashboards, stock-AI clichés (brains, robots, sparkles).
- Works with the sound off: on-screen text carries the message; captions ≤ 7 words.

## Audio notes
No music provided → render silent and say so (offer to add a track), or synthesize a simple
score in numpy/Web Audio only if the user wants it. Never fetch copyrighted songs. When a
track is given: detect BPM/downbeats (librosa or a numpy onset envelope), align cuts to
beats, place SFX by their transient peak, duck music under VO, target −14 LUFS.
