# Motion Studio

Make motion-graphics videos with Claude by writing the animation as code and rendering it
frame-exact to MP4.

```
brief (+ your assets) → storyboard → deterministic composition (HTML/SVG/Canvas/GSAP/Three.js)
      → stills & contact sheet review → headless render per format (+ motion blur)
      → SFX on visual hits + −14 LUFS mix → QA gates (incl. sync) → MP4s  (+ scored critic rounds on request)
```

## What's inside

| Path | What it does |
|---|---|
| `skills/motion-video/` | The workflow skill: brief template, genre playbooks, craft numbers, production notes, engine gotchas, formats, audio and assets references, two starter templates, and the scripts below. |
| `skills/motion-video/templates/` | `composition.html` (2D) and `three-composition.html` (Three.js), both built on `kit.js`: the shared motion kit (springs, keyframes, seeded noise, formats and safe areas, beat timing, hits, video clips). Copy the template **and** `kit.js`. |
| `skills/motion-video/scripts/render.py` | Headless-Chromium renderer: seeks every frame via `window.seek(t)`, sub-frame motion blur, parallel workers, `--format 16x9,9x16,1x1,4x5`, `--deliver` bundle, review renders (`--sheet --phone --strip --poster --contact beats`), `--hits`, and the gates: determinism, loop seam, safe area, text duration. |
| `skills/motion-video/scripts/check.py` | QA on the MP4: blank frames, single-frame pops, frozen stretches, loop seam, loudness, `--sync`, contact sheet. |
| `skills/motion-video/scripts/beats.py` | Beat grid from your track (BPM, downbeats, sections; cuts the best window) or a fixed `--grid`. Writes `beats.js` for the kit. |
| `skills/motion-video/scripts/sfx.py` | Synthesized SFX palette (whoosh, tick, thud, riser, impact …) placed sample-accurately on `MOTION.hits`. |
| `skills/motion-video/scripts/mix.py` | Mixes music, SFX and voice-over, ducks music under VO, masters to −14 LUFS / −1 dBTP, muxes into every format. |
| `skills/motion-video/scripts/sync.py` | Measures where each SFX lands vs. its hit (±20 ms gate) and plots it. |
| `skills/motion-video/scripts/ingest.py` | Copies and normalises your logo, screenshots, fonts, clips (→ frame sequences), audio and docs into `assets/` with an inventory. |
| `skills/motion-video/scripts/vendor.py` | Copies three.js / GSAP / lottie locally so renders never hit the network. |
| `commands/` | `/motion`, `/motion-inspire`, `/motion-brief`, `/motion-assets`, `/motion-audio`, `/motion-render`. |
| `agents/motion-critic.md` | Fresh-eyes reviewer: scores 7 dimensions with evidence, top 3 timestamped fixes, a critique ledger, and a ship / one-more-pass verdict. |

## Requirements

```bash
pip install playwright numpy pillow
python3 -m playwright install chromium
# ffmpeg on PATH (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)
# npm, only if you vendor three.js or GSAP
# optional: pip install librosa (beats.py uses it for tempo if present; a numpy fallback is built in)
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
In app chat only the skill loads (no slash commands, no critic agent): ask in plain words. If you ask for
a review, Claude runs the critic rounds itself as an explicitly fresh pass using the rubric in the skill.

## Use

There are two ways to work: give everything to one command and get an MP4 back, or go step by
step with the smaller commands when you want to shape the idea first.

| Command | Input | Output |
|---|---|---|
| `/motion` | What the video is about (or a `brief.md`), plus any of: duration, formats, style, asset files, a music track | The finished MP4 per format with sound, posters, contact sheets, `deliver.json`, the critic's scores and the HTML source |
| `/motion-inspire` | A subject or style | Three original concepts and a recommended pick |
| `/motion-brief` | A rough idea, plus any asset files | `motion/<slug>/brief.md`, a production brief with a storyboard |
| `/motion-assets` | Files, folders or chat attachments (logo, screenshots, fonts, clips, audio, brand guide) | `motion/<slug>/assets/` with `assets.json`, ready to use by id |
| `/motion-audio` | A composition, plus an optional `--track` and `--vo` | SFX on the composition's hits, a −14 LUFS mix muxed into every rendered format, a sync report |
| `/motion-render` | An existing HTML animation, plus formats and flags | QA-checked MP4s (one per format), optionally the deliver bundle |

Commands are namespaced by the plugin, so `/motion-studio:motion` also works if another
plugin has a `/motion`. You can also skip commands and ask in plain words, e.g. "make a
30-second recipe explainer video for filter coffee". The skill triggers by itself.

### One command: idea → MP4

Put everything you know in one line. Whatever you leave out gets a sensible default, and
Claude tells you what it chose.

```
/motion 15s launch teaser for Tally, a habit-tracking app, for Reels and the feed (9:16 + 1:1).
Warm off-white background, one orange accent (#FF6A1A), tagline "Small days add up".
Logo: ~/Desktop/tally/logo.svg. Music: ~/Music/tally-theme.mp3
```

What happens:

1. **Questions, only if needed.** If something only you can provide is missing (your logo,
   exact copy or numbers, a music track), Claude asks for it in one batch. Otherwise it
   carries on. Files you name or attach are copied into the project's `assets/` and used
   as-is, never redrawn.
2. **Brief.** Claude picks the closest genre playbook (here a launch teaser) and writes a
   brief: a one-line concept, a hex palette, fonts, locked copy, formats, motion rules, the
   sound plan (music + which visual hits get a sound effect) and a banned list.
3. **Storyboard.** A timed beat table, for example:

   | time | on screen |
   |---|---|
   | 0.0–1.5 s | A single orange dot lands on an empty calendar grid |
   | 1.5–6.0 s | The days fill one by one, accelerating into a streak |
   | 6.0–11.0 s | The streak bends into the Tally app UI |
   | 11.0–15.0 s | "Small days add up", then the logo lockup and a held end frame |

   If you're watching, Claude shows you this and the format list, and waits for your OK.
4. **Build.** One HTML composition in `motion/tally-teaser/`, built from a template so that
   every frame is a pure function of time. One timeline serves every format; only the layout
   changes (9:16 keeps text clear of the Reels/TikTok buttons and captions). Scenes are cut
   to your track's beats.
5. **Review.** Gates first (determinism, loop seam, safe area, text on screen ≥ 8 frames),
   then one contact sheet per format. Claude looks at it and fixes problems before spending
   time on the full render.
6. **Render + sound + QA.** A frame-by-frame render with motion blur in each format, sound
   effects synthesized on the visual hits, a mix with your track mastered to −14 LUFS and
   muxed into every file, then `check.py`: blank frames, one-frame pops, frozen stretches,
   loudness, and picture/sound sync (±20 ms).
7. **Deliver.** Claude shows you the videos. You get:
   ```
   motion/tally-teaser/
   ├── brief.md
   ├── critique.md                     ← critic rounds, if you asked for them
   ├── tally-teaser.html               ← editable master: change copy/colours, re-render
   ├── kit.js  beats.js  music.wav
   ├── assets/                         ← your logo, as supplied
   ├── audio/  sfx.wav  mix.wav
   └── renders/
       ├── deliver.json                ← what's in the bundle (size, fps, audio …)
       ├── tally-teaser_9x16.mp4   tally-teaser_9x16_poster.png   tally-teaser_9x16_sheet.png
       └── tally-teaser_1x1.mp4    tally-teaser_1x1_poster.png    tally-teaser_1x1_sheet.png
   ```

To change something afterwards, just ask ("make the streak faster", "swap the accent to
teal"). Claude edits the HTML and re-renders. Nothing is rebuilt from scratch.

**Want a second opinion?** Say "review it" (or add `--review` to `/motion`, or `--review 3` for
three rounds). The `motion-critic` agent then reviews the renders with fresh eyes and scores
hook, readability, motion, variety, brand, sync and concept (1–10), with the top 3 timestamped
fixes and a *ship / one more pass* verdict. Claude fixes, re-renders and repeats (2 rounds for a
social clip, 3 for a hero piece by default, at most 4). Every round goes into `critique.md`.
Critic rounds are off by default because each one costs several image reads and a re-render.

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
directly if you want to change the copy, palette, formats, sound plan or timing.

**3. Bring your assets** (optional)
```
/motion-assets ~/Desktop/brand/logo.svg ~/Desktop/brand/fonts/ ~/Desktop/pour.mov
```
Everything is copied into `motion/pour-over-explainer/assets/` and listed in `assets.json`:
images resized, SVGs sanitised, fonts checked, clips turned into frame sequences (so every
frame renders exactly). Missing or unreadable files are named. Files attached in Claude app
chat work the same way.

**4. Build from the brief**
```
/motion build motion/pour-over-explainer/brief.md
```
`/motion` uses the existing brief instead of writing a new one, asks only about its remaining
`[[TODO: …]]` items, then runs the same build → review → render → sound → QA steps
described above.

**5. Sound** (on its own, e.g. after changing the timing or swapping the track)
```
/motion-audio motion/pour-over-explainer/pour-over-explainer.html --track ~/Music/calm.mp3
```
Beat grid from your track, SFX on the composition's `MOTION.hits`, a −14 LUFS mix muxed into
every rendered format, and a sync report (worst offset in ms). Music must be yours to use;
Claude never downloads songs.

**6. Re-render or render your own animation**
```
/motion-render motion/pour-over-explainer/pour-over-explainer.html --format 1x1,9x16 --deliver
/motion-render ./my-existing-animation.html --gl --subframes 6 --audio track.wav
```
This works with any HTML animation. If the file runs on its own clock (rAF loop, CSS
animations, a playing GSAP timeline), Claude first changes it so every frame is computed
from `t`, keeping the look identical. Common flags: `--subframes N` (motion blur),
`--audio file` (muxed and normalized to −14 LUFS), `--gl` (WebGL/Three.js),
`--scale 2` (supersampled, crisper type), `--format 16x9,9x16,1x1,4x5` (one file per format),
`--deliver` (adds a poster and contact sheet per format and `renders/deliver.json`).

### Previewing a composition
Open the 2D composition HTML in a browser: it plays, Space pauses, ←/→ step frames, **F**
cycles formats and **G** shows the safe areas. The Three.js template uses ES modules, which
browsers block from `file://`, so serve its folder first and open it over http:
```bash
cd motion/<slug> && python3 -m http.server 8000   # then open http://localhost:8000/<slug>.html
```

## The one rule
Every frame is a pure function of its time. No clocks, timers, CSS animations, or
unseeded randomness. That's what makes renders exact, repeatable and fixable by small edits.

## Licence
Code and docs: MIT.
