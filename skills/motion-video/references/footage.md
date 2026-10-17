# Footage-led pieces (a talking clip → a new edit)

Use this when the brief has a `<footage>` section: someone talks on camera about a product, and
the piece is a **new edit** of that clip, not a layer pasted over it. The speaker is cut,
reframed and recomposed with type, shapes and cards timed to the words. Everything is data
written before the build and loaded before `window.ready`, so renders stay deterministic.

## Pipeline

```bash
S=SKILL_DIR/scripts; P=motion/<slug>
python3 $S/ingest.py $P talk.mp4                          # frames at the piece fps + assets/audio/talk-audio.wav
python3 $S/transcribe.py $P talk [--script script.txt]    # transcript.json/.js: words w0.., phrases, fillers, pauses
python3 $S/cut.py suggest $P                              # edl.json/.js: cuts fillers, pauses > 0.6 s, retakes
#   show the cut list (edl.json "removed") with the storyboard; the user accepts or edits it
#   write story.json (below), then:
python3 $S/story.py $P                                    # checks every cue and claim, writes story.js
cp SKILL_DIR/templates/{footage-composition.html,kit.js,kit-footage.js} $P/   # rename the html to <slug>.html
python3 $S/render.py $P/<slug>.html --format 16x9,9x16 --check-only   # + cue_timing, claim_trace
python3 $S/cut.py voice $P --clean                        # audio/voice.wav from the same EDL
python3 $S/render.py $P/<slug>.html --format 16x9,9x16 --deliver --subframes 2
python3 $S/mix.py --duration D --vo $P/audio/voice.wav [--music …] [--sfx …] --out $P/audio/mix.wav --mux <every mp4>
python3 $S/check.py $P/renders/<slug>_16x9.mp4 --edl $P/edl.json      # av_sync: every cut within 1 frame
```

- **Ingest.** The clip's sound becomes its own entry (`<clip>-audio`, 48 kHz), sample 0 = frame 0;
  the video entry links it as `audio`. `--clip-fps` defaults to the piece's fps (MOTION or
  brief.md). Phone footage is often variable frame rate: ingest resamples it to a constant
  rate and every cut is rounded to a frame. `--clip-max-dim 1280` keeps frames small when the
  speaker only ever fills a corner card.
- **Transcribe.** With `pip install faster-whisper` you get real word timings (the first run
  downloads model weights from Hugging Face; say so before running it). Without it, ask for the
  script (exact words as spoken, one phrase per line) and pass `--script`: phrases are split at
  silences and words placed on the dips between them. With neither, only phrases and pauses are
  written: enough for cuts, not for word cues or captions.
- **Cut.** Suggestions only. Never cut inside a word, never time-stretch speech (`speed` is for
  silent b-roll). Jump cuts in the same clip are flagged `jump: true`; cover them with
  `K.punch(t)` (punch-in) or a graphic or cutaway that starts on the cut.
- **Voice.** `cut.py voice` places each segment's clip audio at its `at` with 8 ms crossfades
  centred on the cut, so picture and voice can't drift. `--clean` adds an 80 Hz high-pass, a
  gentle denoise and a per-segment loudness match (target ±1 LU).

## story.json (the story map, signed off with the storyboard)

```json
{"version": 1, "clip": "talk", "focus": [0.5, 0.4], "captions": true,
 "segments": [
  {"id": "s0", "role": "hook", "from": "w0", "to": "w7", "layout": "full",
   "claim": "Lumen files your notes for you", "emphasis": ["w3"], "names": ["Lumen"],
   "cues": [{"kind": "keyword", "text": "Lumen", "at": "w3", "until": "w7", "sfx": "pop"},
            {"kind": "lower-third", "name": "Ada Park", "role": "Founder, Lumen", "at": "w5"}]},
  {"id": "s1", "role": "proof", "from": "w20", "to": "w31", "layout": "corner",
   "cues": [{"kind": "stat", "value": "3x", "label": "faster exports", "at": "w24", "claim": "source:2"}]}]}
```

- **Roles:** hook, problem, product, feature, proof, objection, cta. One key claim each.
- **Layouts** (speaker placement per segment; changes morph over 0.5 s): `full`, `corner`
  (card), `split` (half), `shape` (circle mask), `pig` (picture-in-graphic). Defaults by role:
  hook/objection full, problem/feature split, product pig, proof corner, cta shape. `focus` is
  where the face sits in the clip (fractions), used for every crop.
- **Cues** (each starts on a word id, `at`; `until` is a word id, `w12+0.5`, or seconds):
  `keyword {text}`, `stat {value, label}`, `lower-third {name, role}`, `feature-list {title,
  items:[{text, at}]}`, `quote {from, to}`, `cta {line, url}`, `screenshot {asset}`. Add
  `"sfx": "pop"` to put a hit on it.
- **Claims.** Every on-screen claim is either a **quote** (the text equals the words at its cue,
  or a quote's from..to) or a **sourced fact**: `"claim": "source:N"` = line N of
  `docs/source.md`, one fact per line with where it came from (a supplied doc, the brief, a page
  the user pasted). Numbers on screen must appear in that line. Names and section labels need no
  claim unless they hold a number. Nothing is fetched by the plugin; facts come from the user.
- `story.py` checks all of this (and that no cue sits on a word the EDL cut) and writes story.js.
  Fix every problem it lists before building.

## Building

The template's layer stack is background → speaker (canvas) → graphics → captions. Change the
look in the template (palette, fonts, panel) and timing in story.json / edl.json, not in code.
For a custom scene, use the kit (`kit-footage.js` header lists the API):

```js
K.footage();                                  // TRANSCRIPT + EDL + ASSETS
const s = await K.edlSeek(t);                 // in seek(t): decode the frame the edit needs
K.drawSpeaker(ctx, K.footageAsset(s.clip), s.clipT, K.speakerRect('corner'), { focus, zoom: K.punch(t) });
K.statCard(layer, { value: '3x', label: 'faster exports', at: 'w24', claim: 'source:2' });
K.captions(captionLayer);                     // ≤ 7 words a group, current word highlighted
K.footageUpdate(t);                           // every component made above
```

- Long clips: `K.loadClip(clip, { window: 2 })` (the template does this) keeps ~2 s each side
  decoded; `seek` must `await K.edlSeek(t)` (or `K.clipSeek(clip, t)`) before drawing.
- Captions sit on a plate at the bottom of `K.safe.ui`; graphics go in `K.graphicsArea(rect)`,
  the free side of the frame, so they never cover the speaker's rect.
- Every graphic carries `data-cue` (its word) and `data-claim`; don't remove them.

## Gates (in addition to the usual ones)

| gate | where | rule |
|---|---|---|
| `cue_timing` | `render.py --check-only` | each `[data-cue]` element first shows within ±2 frames of its word (through the EDL) |
| `claim_trace` | `render.py --check-only` | each visible `[data-text]` has a `data-claim` that holds up (quote, `source:N`, or a number-free `label`) |
| `av_sync` | `check.py --edl edl.json` (or `cut.py sync`) | every EDL segment of the final mix within 1 frame of its source audio |

Not covered yet: face tracking and auto-reframe (`focus` is a fixed point), person mattes, and a
face-cover gate.
