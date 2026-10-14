# Motion Studio

Make motion-graphics videos with Claude by writing the animation as code and rendering it
frame-exact to MP4.

```
brief → storyboard → deterministic composition (HTML/SVG/Canvas/GSAP/Three.js)
      → stills & contact sheet review → headless render (+ motion blur) → QA gates → critic → MP4
```

## What's inside

| Path | What it does |
|---|---|
| `skills/motion-video/` | The workflow skill: brief template, genre playbooks, craft numbers, production notes, engine gotchas, two starter templates, and the render/QA scripts. |
| `skills/motion-video/scripts/render.py` | Headless-Chromium renderer: seeks every frame via `window.seek(t)`, optional sub-frame motion blur, parallel workers, audio mux + −14 LUFS, stills/contact-sheet mode, determinism and loop-seam gates. |
| `skills/motion-video/scripts/check.py` | QA on the MP4: blank frames, single-frame pops, frozen stretches, loop seam, loudness, contact sheet. |
| `skills/motion-video/scripts/vendor.py` | Copies three.js / GSAP / lottie locally so renders never hit the network. |
| `commands/` | `/motion`, `/motion-brief`, `/motion-render`, `/motion-inspire`. |
| `agents/motion-critic.md` | Fresh-eyes reviewer that returns a timestamped fix list and a ship verdict. |

## Requirements

```bash
pip install playwright numpy pillow
python3 -m playwright install chromium
# ffmpeg on PATH (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)
# npm, only if you vendor three.js or GSAP
```

## Install

**Claude Code**
```
/plugin marketplace add sarupurisailalith/motion-studio
/plugin install motion-studio@motion-studio
```
or for local testing: `git clone https://github.com/sarupurisailalith/motion-studio && claude --plugin-dir ./motion-studio`.

**Claude app (claude.ai / desktop)** — zip the skill folder and upload it under Settings → Capabilities → Skills:
```bash
cd skills && zip -r ../motion-video.zip motion-video
```
The app's sandbox can render short pieces; long or WebGL-heavy renders are faster in Claude Code on your machine.

## Use

There are two ways to work: give everything to one command and get an MP4 back, or go step by
step with the smaller commands when you want to shape the idea first.

| Command | Input | Output |
|---|---|---|
| `/motion` | What the video is about, plus any of: duration, aspect, style | The finished MP4 and its HTML source |
| `/motion-inspire` | A subject or style | Three original concepts and a recommended pick |
| `/motion-brief` | A rough idea | `motion/<slug>/brief.md`, a production brief with a storyboard |
| `/motion-render` | An existing HTML animation | A QA-checked MP4 |

Commands are namespaced by the plugin, so `/motion-studio:motion` also works if another
plugin has a `/motion`. You can also skip commands and ask in plain words, e.g. "make a
30-second recipe explainer video for filter coffee". The skill triggers by itself.

### One command: idea → MP4

Put everything you know in one line. Whatever you leave out gets a sensible default, and
Claude tells you what it chose.

```
/motion 15s 9:16 launch teaser for Tally, a habit-tracking app. Warm off-white background,
one orange accent (#FF6A1A), tagline "Small days add up". For Instagram Reels.
```

What happens:

1. **Questions, only if needed.** If something only you can provide is missing (your logo,
   exact copy or numbers, a music track), Claude asks for it in one batch. Otherwise it
   carries on.
2. **Brief.** Claude picks the closest genre playbook (here a launch teaser) and writes a
   brief: a one-line concept, a hex palette, fonts, locked copy, motion rules and a banned
   list.
3. **Storyboard.** A timed beat table, for example:

   | time | on screen |
   |---|---|
   | 0.0–1.5 s | A single orange dot lands on an empty calendar grid |
   | 1.5–6.0 s | The days fill one by one, accelerating into a streak |
   | 6.0–11.0 s | The streak bends into the Tally app UI |
   | 11.0–15.0 s | "Small days add up", then the logo lockup and a held end frame |

   If you're watching, Claude shows you this before building.
4. **Build.** An HTML composition in `motion/tally-teaser/`, built from a template so that
   every frame is a pure function of time.
5. **Review.** Determinism checks, then a 4×4 contact sheet of stills. Claude looks at it
   and fixes problems before spending time on the full render.
6. **Render + QA.** A headless frame-by-frame render with motion blur, then `check.py`, which
   catches blank frames, one-frame pops, frozen stretches and loudness problems.
7. **Critic.** The `motion-critic` agent reviews the render with fresh eyes and returns
   timestamped fixes plus a *ship / one more pass* verdict. At most 2–3 fix rounds.
8. **Deliver.** You get:
   ```
   motion/tally-teaser/
   ├── brief.md
   ├── tally-teaser.html          ← editable master: change copy/colours, re-render
   └── renders/
       ├── tally-teaser.mp4
       └── tally-teaser_sheet.png
   ```

To change something afterwards, just ask ("make the streak faster", "swap the accent to
teal"). Claude edits the HTML and re-renders. Nothing is rebuilt from scratch.

### Step by step: inspire → brief → build → render

Use this when you don't have a concept yet, or you want to approve the plan before anything
gets built.

**1. Explore concepts** (optional)
```
/motion-inspire 20-second explainer on how a pour-over coffee extracts
```
You get three different concepts. Each has a one-line visual rule, duration and aspect,
3–5 timed beats, a transition approach and a build technique. One is recommended.

**2. Lock the brief**
```
/motion-brief concept 2: water as a single amber line that stays continuous through every scene; 20s, 1:1
```
This writes `motion/pour-over-explainer/brief.md`. Anything only you can supply is marked
`[[TODO: …]]`, and the brief ends with a list of what's still needed. Edit the file
directly if you want to change the copy, palette or timing.

**3. Build from the brief**
```
/motion build motion/pour-over-explainer/brief.md
```
`/motion` uses the existing brief instead of writing a new one, then runs the same
build → review → render → QA → critic steps described above.

**4. Re-render or render your own animation**
```
/motion-render motion/pour-over-explainer/pour-over-explainer.html --subframes 6 --audio track.wav
/motion-render ./my-existing-animation.html --gl
```
This works with any HTML animation. If the file runs on its own clock (rAF loop, CSS
animations, a playing GSAP timeline), Claude first changes it so every frame is computed
from `t`, keeping the look identical. Common flags: `--subframes N` (motion blur),
`--audio file` (muxed and normalized to −14 LUFS), `--gl` (WebGL/Three.js),
`--scale 2` (supersampled, crisper type).

## The one rule
Every frame is a pure function of its time. No clocks, timers, CSS animations, or
unseeded randomness. That's what makes renders exact, repeatable and fixable by small edits.

## Licence
Code and docs: MIT.
