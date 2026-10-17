# Changelog

All notable changes to Motion Studio. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/). Backlog ids (E…) refer to the project backlog.

## [0.3.1] — 2026-10-18

### Fixed
- Titles and captions in `composition.html`, `p5-composition.html` and the `p5-glyph-points`
  recipe now shrink to fit the UI-safe width (after the camera push) when the system font is
  wider than macOS's, so 9x16 renders on Linux and Windows no longer fail the `safe_area` gate.
- CI uses `actions/checkout@v5` and `actions/setup-python@v6` (Node 24).

## [0.3.0] — 2026-10-18

Footage-led videos, two new engines (Zdog, p5.js), a brand kit, faster renders and more QA gates.
Every v0.2 command line and composition works as before; no new network access at render time.

### Added
- **Footage-led videos** (a talking clip recut with graphics; brief `<footage>`, `renderer: footage`):
  - `ingest.py` keeps a clip's own sound as a linked `<id>-audio` WAV (48 kHz), sample-aligned to
    frame 0; `--clip-max-dim`; `--clip-fps` defaults to the piece's fps; variable-frame-rate footage
    is resampled to a constant rate.
  - `transcribe.py`: word timings (faster-whisper if installed, optional), script alignment or a
    phrases-only fallback; fillers and long pauses listed; `--snap beats.json` puts voice-over
    phrases on beats without stretching (`vo.wav` + `vo.json`).
  - `cut.py`: `suggest` (an edit list from fillers, pauses and retakes), `voice` (the voice stem
    from the same edit list, crossfaded cuts, `--clean` high-pass, denoise and loudness match),
    `sync` (A/V sync per segment).
  - `story.py` checks `story.json` cues and on-screen claims against the transcript, the edit list
    and `docs/source.md`.
  - `templates/kit-footage.js` (edit-list playback, word-timed cues, captions, lower third, keyword
    pop, stat card, feature list, pull quote, CTA card, speaker layouts) and
    `templates/footage-composition.html`; `references/footage.md`.
  - Windowed clip loading for long clips (`K.loadClip(a, {window})`, `K.clipSeek`, `K.clipStats`).
  - Gates: `cue_timing` and `claim_trace` in `render.py --check-only` for footage pieces;
    `check.py --edl` adds `av_sync`.
- **Zdog engine**: `vendor.py zdog` (zdog 1.1.3 + zfont 1.2.8), `templates/zdog-composition.html`,
  `kit-zdog.js` (`K.Z`: render with canonical sort, project, camera, depth layers, squash, shadow,
  extrude, shade), a character rig with 11 clips (idle, anticipate, hop, leap, land, run, wave,
  point, turn-to-camera, drop-in, spin-reveal), and `references/zdog.md`.
- **Model catalog**: 17 original Zdog models (characters, props, scenery, icons), `catalog.json`,
  `catalog.py` (search / use / turntable / previews), preview stills and a "search the catalog
  first" rule.
- **p5.js engine**: `vendor.py p5` (p5.js 2.3.4, LGPL-2.1, downloaded unmodified per project),
  `templates/p5-composition.html`, `kit-p5.js` (`K.sketch`, `K.loopNoise`, `K.presim`), p5
  determinism rules in `gotchas.md`.
- **Layered template** (`templates/layered-composition.html`, `K.layers`) and `K.proxy` /
  `K.textBox` so the gates see canvas-drawn text.
- **More templates**: `gsap-composition.html` (one paused master timeline) and
  `glsl-composition.html` (fragment shader, `uTime` from `seek`). Engine recipes in
  `templates/recipes/` and kit examples in `templates/examples/`.
- Brief `<renderer>` field (2d | gsap | glsl | zdog | p5 | three | layered | footage); `/motion`,
  `scaffold.py` and SKILL.md pick the template from it.
- **Brand kit**: `brand.py` builds `brand.json` from local brand files (ranked palette, fonts,
  wordmark, guide colours and copy from text, or PDF via optional pypdf / pdftotext) plus a swatch
  image; `/motion`, `/motion-brief` and `/motion-assets` show it for confirmation before building.
- **Kit**: spring presets `K.SPRING.snappy|ui|soft|camera`, `K.wobble` / `K.squash`; images
  `K.cover` / `K.crop` and device frames `K.device` / `K.drawDevice`; typography `K.glyphs`,
  `K.layoutText` / `K.drawGlyphs`, `K.fitText`, `K.rise` / `K.maskRise`, `K.typed`, `K.scramble`.
- `scaffold.py` (a project folder from a template) and `doctor.py` (checks dependencies and prints
  install commands; installs nothing).
- **Audio**: presets `scrape`, `whoomp`, `crackle`, `creak`, `splash`, `rustle`, `chime`, `zip`,
  `sizzle` (`crackle` / `sizzle` are seamless beds with `loop: true`); project palettes via
  `sfx.register` in a palette file loaded with `--palette` (never run implicitly); `sfx.py --samples DIR` places supplied
  takes on the hits; `sfx_events.json` records `transient` and `source`.
- **Reference analysis**: `reference.py` studies a local reference video or stills (cuts, shot
  lengths, motion stats; never downloads), `references/style_guide.md`, and `check.py --against`
  for a pacing WARN.
- `contrast` gate: visible `[data-text]` must reach 4.5:1 against the rendered pixels behind it.
- `render.py --thorough` (denser determinism and contrast sampling).
- CI workflow (ruff, frontmatter check, full test suite), `ruff.toml` and `CREDITS.md`.

### Changed
- **Faster rendering, same pixels**: frames are captured over CDP (about 1.8× on one worker for DOM
  pages), and a page that is one full-frame `<canvas>` is read straight from the canvas after a
  pixel check (2–3× on 2D-canvas pages, about 1.3× for Three.js under `--gl`). `--capture
  screenshot` restores the v0.2 path.
- `--workers` defaults to the CPU count (max 6); a frame-count gate fails a render with a missing
  or duplicated frame.
- Render cache: a rerun with unchanged page files and flags (e.g. only `--audio` changed) reuses
  `renders/.cache/` and only re-muxes; `--no-cache` always renders.
- `check.py` `frozen` gate measures local motion (any 40 px region at 320 px over 0.1 s), so small
  or slow movers no longer read as still.
- `mix.py --duration` defaults from `renders/deliver.json` or `renders/*_hits.json`.
- `--deliver` also writes `_sheet_phone.png` (`sheet_phone` in `deliver.json`); `--sheet` without
  `--stills` writes its stills to `renders/stills/`.
- `/motion` uses `scaffold.py` and `doctor.py`; docs on flagged domain defaults, the platform-UI
  bands, critic fixes vs. `K.safe.ui`, and recording unattended sign-off in `<start>`.

### Fixed
- `render.py` no longer reports a cancelled request as a page error when the same URL then loads
  (p5 `loadFont`), and the local server no longer prints a traceback for cancelled requests.

## [0.2.2] — 2026-10-15

Directory-submission readiness. No change to commands, compositions or render output.

### Added
- `PRIVACY.md` (no data collected, what is read/written, every download and where it comes from)
  and `SECURITY.md` (private vulnerability reporting).
- README: "No generative media models", "What runs on your machine", "Troubleshooting" and
  "Privacy and security" sections.
- `plugin.json`: `displayName`, `homepage`, `repository`, `documentationUrl`, `supportUrl`,
  `privacyPolicyUrl`; `marketplace.json`: `description`.

### Changed
- `vendor.py` installs exact pinned versions (`three@0.186.1`, `gsap@3.15.0`,
  `lottie-web@5.13.0`) instead of whatever is latest.

### Removed
- The launch film MP4 from `docs/assets/`; the README plays it from a GitHub attachment.

## [0.2.1] — 2026-10-15

### Changed
- Licence: MIT → **Apache License 2.0**, with a `NOTICE` file that redistributions and derived
  works must keep (Section 4(d)). Added `CITATION.cff` (GitHub's "Cite this repository").
  Copies obtained before this release stay under MIT. Videos made with the plugin need no credit.

## [0.2.0] — 2026-10-14

Sound, multi-format delivery, review discipline and your own assets. Every v0.1 command line
and composition works as before.

### Added
- **`render.py --quiet`**: prints only results (output paths, errors, the JSON report) so agents
  driving the pipeline read fewer tokens.
- **Token economy rules** in `/motion` and SKILL.md: write the composition once and then patch it,
  read references only when the piece needs them, look at one contact sheet per format by default,
  quote numbers instead of logs.
- **Shared motion kit** `templates/kit.js` (`window.K`), loaded by both templates; projects copy the
  template and kit.js. The Three.js template gains the kit.
- **Beat grid** `beats.py --track song --duration D` (BPM, downbeats, sections, energy; cuts the best
  window on a downbeat; librosa optional, numpy fallback) and `--grid --bpm N`. Writes `beats.json`
  + `beats.js` (E1.1).
- **Hits** `MOTION.hits` with times in seconds or beats, `K.resolveHits()`, `render.py --hits` →
  `renders/<stem>_hits.json` (E1.3).
- **Synthesized SFX** `sfx.py`: a seeded 12-sound palette placed sample-accurately on the hits, with
  gain, pan, pitch, length, anchor and reverb; `sfx_events.json` for sync checks (E1.4).
- **Mixer/master** `mix.py`: music + SFX + VO, ducking under VO, two-pass loudnorm to −14 LUFS /
  ≤ −1 dBTP, `--stems`, `--mux` into every rendered format (E1.5).
- **Sync check** `sync.py` (±20 ms for transient SFX, stem-matched under music, `--png` plot) and
  `check.py --sync` (E1.6).
- **Audio reference** `references/audio.md`: beat maths, sound-design rules, mix numbers, licensing (E1.7).
- **Formats** `render.py --format 16x9,9x16,1x1,4x5` with per-format gates and `_<fmt>` outputs (E2.1);
  kit layout helpers `K.init`, `K.FORMAT`, `K.pick`, `K.safe` (title and platform-UI safe rects) (E2.2);
  preview format switcher (F) and safe-area overlay (G) (E2.3); `references/formats.md`.
- **Gates** `safe_area` (`[data-safe]` inside `K.safe.ui`) (E2.4) and `text_duration`
  (`[data-text]` visible ≥ 8 frames) (E5.6, duration only) in `render.py --check-only`.
- **Delivery bundle** `render.py --deliver`: poster and contact sheet per format plus
  `renders/deliver.json` with ffprobe facts (E2.5).
- **Review renders** `--strip A:B:N`, `--poster [T]`, `--phone`, `--contact beats` (E5.5).
- **Scored critic** rubric (7 dimensions, evidence per score, top 3 fixes, verdict rule) in
  `agents/motion-critic.md` and, for Claude app chat, in SKILL.md (E5.1); critique ledger
  `critique.md` (E5.2); critic rounds **on request** (`--review [N]`, "review it" or the brief's
  `<review>`): 2 social, 3 hero, cap 4 (E5.3); storyboard
  sign-off gate in `/motion` (E5.4).
- **Beat-time authoring** `K.T`, `K.U`, `K.at`; `track`/`springTrack`/`stagger` accept `'8b'` strings (E7.1).
- **Build from an existing brief**: `/motion path/to/brief.md` (E7.6).
- **Local assets** `ingest.py` (images, sanitised SVG, fonts + `fonts.css`, clips → frame sequences,
  audio → 48 kHz WAV, docs) with `assets.json` / `assets.js`, `/motion-assets`, `references/assets.md`
  (E3.6, E3.7); kit clip helpers `K.loadClip`, `K.clipFrame`, `K.drawClip`.
- **Commands** `/motion-assets` and `/motion-audio`.
- **Tests** (stdlib unittest): golden compositions and broken fixtures (E0.2), per-component suites,
  and an end-to-end test (multi-format render with synced, mastered audio; an ingested clip).
- **Benchmark** `tests/bench.py` and `docs/perf.md` (E0.3).

### Fixed (from the dogfood trial)
- `render.py` determinism gate sampled only 3 distinct times (a re-seeded RNG); it now samples 8,
  uses the loop-seam tolerance (fails on > 8 px off by > 24/255; sub-visible anti-aliasing noise
  passes), and a FAIL names the pixel count and the box that changed.
- `check.py` no longer overwrites the contact sheet `--deliver` wrote: its QA sheet is
  `<stem>_qa_sheet.png`. New `--json FILE`; `--help` documents every gate and threshold.
- `mix.py` no longer crushes SFX-only mixes through the limiter chasing −14 LUFS (measured: a
  click lost ~9 dB of crest and the mix still failed). With no music and no VO it peak-normalises
  to −1.5 dBTP (`"mode": "sparse"`), and `check.py` accepts such audio.
- The 2D template no longer names an uninstalled "Inter": it uses an explicit system font stack.
- Docs: portrait type sizing made consistent (formats.md vs brief template); help text for every
  `render.py` flag; critic inputs use `check.py --json` reports; `critique.md` is created if missing;
  new gotcha on sub-pixel CSS `scale()`.

### Changed
- `/motion` runs ingest → brief → sign-off → build → review (gates, one sheet per format) →
  `--deliver` → sound → QA → shows the videos; critic rounds run only when asked for.
- `mix.py --mux` refreshes `audio` and `size_bytes` in a sibling `renders/deliver.json`.
- `/motion-brief` and the brief template gain `<assets>`, `<formats>`, `<review>` and the hit list.
- `/motion-render` documents formats, the deliver bundle, review renders and the new gates.
- The 2D demo centres its title + shape group on `K.safe.ui` and scales it up in 9:16;
  `data-text` sits on the glyph row so the text gate measures the visible word.
- The Three.js template awaits `document.fonts.ready` and documents previewing over http.
- SKILL.md rewritten around the v0.2 workflow; README walkthroughs cover formats, sound,
  assets and the deliver bundle.

## [0.1.0]

First release: brief → storyboard → deterministic HTML composition → frame-exact headless render
with motion blur → QA gates → critic → MP4. Commands `/motion`, `/motion-inspire`, `/motion-brief`,
`/motion-render`; the `motion-critic` agent.
