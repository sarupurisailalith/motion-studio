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

```
/motion 15s 9:16 launch teaser for my app, warm off-white, one orange accent
/motion-brief kinetic-type video of a 20-second quote, square, for LinkedIn
/motion-inspire liquid glass launch video
/motion-render ./my-animation.html --subframes 4 --audio track.wav
```
Or just ask: "make a 30-second recipe explainer video for filter coffee".

## The one rule
Every frame is a pure function of its time. No clocks, timers, CSS animations, or
unseeded randomness. That's what makes renders exact, repeatable and fixable by small edits.

## Licence
Code and docs: MIT.
