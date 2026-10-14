# Changelog

All notable changes to Motion Studio. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/). Backlog ids (E…) refer to the project backlog.

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
