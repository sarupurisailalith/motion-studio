# Audio: music, SFX, mix, sync

Sound is half the piece. Picture leads, sound confirms: every sound lands on something you can see.

### Licensing (read first)
- Never download or fetch copyrighted songs, and never "find a track online". Use only tracks the user supplies and has the rights to.
- No music supplied → render silent and say so plainly. Offer to add a track later, or SFX only.
- Synthesized SFX (`sfx.py`) are generated from noise and oscillators. They are yours to use.
- Sample files for `sfx.py --samples` are supplied by the user or a connector they use, with the rights to use them.
  Never download sounds from the web yourself.

### Beat maths
- Beat length `B = 60 / BPM` s. Bar = 4 beats. Frames per beat = `fps · 60 / BPM`.
- Choose a BPM where a beat is a whole number of frames, so beat times land on frames:
  60 fps → 90 (40 f), 100 (36 f), 120 (30 f), 144 (25 f), 150 (24 f). 30 fps → 90, 100, 120, 150.
- A supplied track keeps its own BPM (e.g. 128 at 60 fps = 28.125 f/beat). Author in beats with `K.T(u)` anyway: the frame
  rounding error is ≤ ½ frame (8 ms at 60 fps), well inside the ±20 ms sync tolerance.
- `K.T(u) = offset + u · period` (beats → s), `K.U(t)` the inverse, `K.at` = `K.T`. They need `beats.js` loaded before the kit.
- Big moves on downbeats (every 4th beat), small ones on beats, glyph staggers on ⅛ or 1/16 notes. Moves start ~0.05 s early so they *land* on the beat.

### Pipeline (copy-paste; run in the project folder)
```bash
S=SKILL_DIR/scripts
# 1. beat grid: from the user's track (cuts the best window, starting on a downbeat) …
python3 $S/beats.py --track song.mp3 --duration 12 --out .           # music.wav + beats.json + beats.js
#    … or a fixed grid with no music
python3 $S/beats.py --grid --bpm 120 --duration 12 --out .
# 2. in the composition: <script src="beats.js"></script> above the kit script, then
#    MOTION.hits = [[1.25,'logo-land','thud'], ['16b','drop','impact',{gain:-3}], [4,'card-in',null]]
# 3. hits -> SFX track
python3 $S/render.py comp.html --hits                                # renders/comp_hits.json
python3 $S/sfx.py renders/comp_hits.json --out audio/sfx.wav         # audio/sfx.wav + audio/sfx_events.json
# 4. render picture (any formats), then mix, master and mux into every video
python3 $S/render.py comp.html --format 16x9,9x16 --deliver        # + posters, sheets, renders/deliver.json
python3 $S/mix.py --duration 12 --music music.wav --sfx audio/sfx.wav --out audio/mix.wav \
    --mux renders/comp_16x9.mp4 renders/comp_9x16.mp4
# 5. measure sync (and loudness) on the delivered file
python3 $S/check.py renders/comp_16x9.mp4 --sync audio/sfx_events.json
python3 $S/sync.py renders/comp_16x9.mp4 audio/sfx_events.json --png renders/comp_sync.png   # per-hit plot
```
- The grid must exist before `--hits` when hits are written in beats (`'16b'`), and before the picture is final when
  any scene is timed with `K.T`. Re-run steps 3–5 after any timing change.
- `mix.py --mux` also refreshes `audio` and `size_bytes` for that video in `renders/deliver.json`, if one lists it.
- `mix.py --duration` can be left out: it reads `D` from `renders/deliver.json` (the item for the `--mux` video) or
  `renders/*_hits.json` (next to the `--mux` videos, in `P/renders/` for `--out P/audio/mix.wav`, or `./renders/`).
- These are the paths `/motion` and `/motion-audio` use: `P/beats.js`, `P/music.wav`, `P/renders/<slug>_hits.json`,
  `P/audio/sfx.wav` + `sfx_events.json`, `P/audio/mix.wav`.
- Keep `sfx.wav` next to `sfx_events.json`: `sync.py` uses it to find each sound under the music. Without it, it falls
  back to nearest-onset matching, which busy music can fool.
- `mix.py --stems` also writes `mix_music_only.wav` and `mix_no_vo.wav` (each at −14 LUFS) for re-edits.
- `render.py --audio track.wav` is still the quick path for "just put this track under it".

### SFX palette (`sfx.py --list`)
| name | default anchor | sync-checked | use for |
|---|---|---|---|
| `whoosh` | peak | info | a real scene change or big camera move |
| `swoosh` | peak | info | a fast slide, a panel or card flying in |
| `tick` | start | ±20 ms | a counter step, a small UI tick |
| `click` | start | ±20 ms | a button press, a toggle |
| `pop` | start | ±20 ms | an element appearing (badge, bubble, dot) |
| `thud` | start | ±20 ms | something landing (logo, card, heavy type) |
| `blip` | start | ±20 ms | a notification, a status change |
| `riser` | end | info | a build into a reveal (it *ends* on the hit) |
| `swell` | end | info | a soft build into a calm reveal |
| `impact` | start | ±20 ms | the one big hit (drop, logo slam) |
| `shimmer` | start | info | a sparkle, a success state, a final reveal |
| `type-key` | start | ±20 ms | one keystroke of on-screen typing |
| `scrape` | start | info | carving, sanding, chalk on a board, dragging; `len` = the stroke |
| `whoomp` | peak | info | ignition, a gas flame catching, a soft burst or bloom |
| `crackle` | start | info | fire, embers, a fireplace; bed: `len` s, `loop: true` for loop pieces |
| `creak` | start | info | a door or lid opening, wood bending, a rope taking weight |
| `splash` | start | ±20 ms | a drop hitting water, a pour landing, a dunk |
| `rustle` | start | info | leaves moving, a page turn, paper or cloth handled; `len` s |
| `chime` | start | ±20 ms | a success state, a bell, a magic touch (gentler than `shimmer`) |
| `zip` | end | info | a fast zip-in (it *ends* on the hit), a zipper, a quick reveal |
| `sizzle` | start | info | frying, a lit fuse, static; bed: `len` s, `loop: true` for loop pieces |

Hit opts: `gain` dB, `pan` −1..1, `pitch` semitones, `len` s, `anchor` `start|peak|end`, `reverb` 0..1, `loop` true|false.
`sfx: null` marks a visual hit with no sound on purpose (listed as `silent`). Same hits + same `--seed` → the same file, bit for bit;
change `--seed` for a different take.

**Beds** (`crackle`, `sizzle`): a texture under a whole scene. Give `len` the scene length. For a loop piece
(MOTION.loop) put it at `0` with `len: D, loop: true`: no fades, and anything that runs past the end wraps to the
start, so the track loops without a click. Keep a bed low (`gain: -12` or so) and put the hits on top.

### Project palettes (`P/audio/palette.py`)
A sound the palette lacks: write it once for the project instead of forking `sfx.py`. `sfx.py` auto-loads
`palette.py` next to `--out` (`P/audio/palette.py`; `--palette FILE` for another, `--no-palette` to skip it):
```python
import numpy as np
import sfx                                   # the running sfx.py: its helpers (_t, _fft_filter, _osc, ...) too

def knock(sr, rng, o):                       # -> (mono float array, onset s, peak s) inside the buffer
    t = sfx._t(sr, o.get("len", 0.12))
    return np.sin(2 * np.pi * 420 * t) * np.exp(-t / 0.015), 0.0, 0.001

sfx.register("knock", knock, "start", "wooden knock (a door, a table)", transient=True)
```
Use only `rng` for randomness (it is seeded per hit, so the file stays bit-identical). `transient=True` puts the
sound under the ±20 ms sync gate (sfx.py writes it into `sfx_events.json`, which `sync.py` reads). `sfx.py --list
--palette FILE` shows the merged palette; an unknown name still fails with the full list.

### Sample-based SFX (`--samples DIR`)
When the user (or a connector they use) supplies recorded or generated takes, put them in one folder named
`<name>_<n>.<ext>` (`whoosh_1.wav`, `whoosh_2.mp3`, `splash_1.wav`, …) and add `--samples P/audio/samples`.
- Every hit whose `sfx` has files there uses a take instead of the synth; other names are still synthesised. A name only
  the folder has (`doorbell_1.wav`) works too (anchor `start`, not sync-gated).
- Each take is decoded with ffmpeg, mixed to mono, trimmed of leading / trailing silence and normalised like the synth.
  Per hit the best take wins: a crisp attack for start-anchored sounds, a rise into the end for end-anchored ones, the
  length closest to `len` (a longer take is cut to `len`). Ties go to the lower `<n>`.
- Anchors, `gain` / `pan` / `pitch` / `reverb`, `sfx_events.json` and the sync check work the same; each event records
  its `source` file. Synthesis stays the default; no API keys or network are involved.

### Sound-design rules
- One whoosh per *real* scene change. Not on every element; never two overlapping.
- Clicks, ticks and type-keys only on real UI actions you can see (a press, a keystroke, a value changing).
- Risers end on the hit, whooshes peak on it, everything else starts on it (the default anchors do this).
- SFX sit *under* the music: start with `--sfx-db -6` and raise only what must cut through. One `impact` per piece.
- Fewer, better sounds: 1 sound per 1–2 s is plenty in a 15 s spot. Silence before a big hit makes it bigger.
- Pitch repeated sounds (±1–2 semitones) or vary `gain` so a run of pops doesn't sound like a machine gun.
- Pan with the motion (an element entering from the left → `pan: -0.4`), never hard left or right.
- Low, tonal sounds (`thud`, `blip`) under a bass-heavy track can't be timed reliably; if `sync` says "not audible", the
  listener can't hear it either: raise it, move it, or drop it.

### Voice
- A voice-over recorded without picture: `transcribe.py P <audio-id> --script vo.txt --snap P/beats.json [--every 2]`
  splits it into phrases at silences and moves each phrase (never stretched) onto a beat → `P/audio/vo.wav` + `vo.json`
  (phrase and word times on the new timeline; `vo.js` for captions: `K.footage({ transcript: window.VO, edl: null })`). Mix it with `mix.py --vo P/audio/vo.wav`.
- On-camera speech is never re-timed: cut it with an EDL and build the stem with `cut.py voice` (`references/footage.md`).
- Captions from word timings: `K.captions` in `kit-footage.js` (≤ 7 words, current word highlighted).

### Mix numbers
- Master: −14 LUFS integrated ±0.2, true peak ≤ −1 dBTP, AAC 48 kHz 192 kb/s in the MP4. `mix.py` does all of this.
- Voice-over: music ducks −14 dB under the VO (`--duck-db`, −12 to −18), 50 ms attack, 300 ms release.
- Music fade-out: 0.5 s at the end (`beats.py` does it). Start the piece on a downbeat (`beats.py` cuts there).
- Sync tolerance: ±20 ms for transient SFX (`tick click pop thud blip impact type-key splash chime`, plus any a project
  palette registers with `transient=True`). Others are reported, not gated.
