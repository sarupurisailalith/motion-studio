# The motion brief

Fill every field before writing code. Defaults are fine; blanks are not.

```
<inputs>        What to ask the user for, each with a default if skipped:
                product/brand name, locked copy or transcript, real assets
                (logo, screenshots, clips, photos), facts file, song (BPM,
                drop position, licence), references.
<assets>        Inventory ids from assets/assets.json (ingest.py) mapped to
                beats: id | kind | beat(s) | role, e.g. "logo | svg | 0–1.5 s,
                12–15 s | lockup". Supplied assets are used as-is: never
                redrawn, recoloured or replaced by a drawn stand-in. None
                supplied → say so; never invent UI, logos or numbers.
                zdog / layered: list the catalog models used ("catalog:pip |
                character | 0–6 s | hero"); search catalog.py first, and
                mark anything modelled new as "new: <what>".
<deliverable>   Duration (exact, e.g. 20.00 s), resolution and aspect(s),
                fps, loop yes/no, MP4 plus editable source, file-size cap,
                sound on/off.
<formats>       Formats to render, from 16x9 (1920×1080), 9x16 (1080×1920),
                1x1 (1080×1080), 4x5 (1080×1350). One timeline; per-format
                layout notes via K.pick (e.g. "9x16: stack title over
                product, type ≈ the 1x1 size"). Safe-area rule: text elements carry
                data-safe data-text and stay inside K.safe.ui (9x16 reserves
                top 12 %, bottom 22 %, right 14 % for platform UI).
<renderer>      One of (list grows; footage etc. may be added):
                  2d       DOM / SVG / Canvas 2D: type, UI, most motion graphics
                  zdog     flat-round 3D: characters, mascots, icons, props,
                           friendly explainers (references/zdog.md)
                  p5       generative loops, flow fields, glyph-driven type
                           (gotchas.md "p5.js")
                  three    product realism, lighting, perspective (--gl)
                  layered  a mix: one engine per depth plane, e.g. p5
                           atmosphere → zdog characters → DOM type
                Default 2d. Pick the simplest engine that carries the concept.
<concept>       ONE line: the formal idea or central visual rule, e.g. "one
                shape never cut", "the baseline is a trajectory", "the
                whole film happens inside the wordmark's period".
<art direction> Palette as hex with a role for each colour (bg / primary
                type / accent / secondary). Fonts with weights, tracking,
                min size. Texture (grain, paper, glass). Composition rules
                (safe margins in px, subject fills frame, negative space).
                Camera vocabulary.
<banned>        A concrete list of effects and clichés to avoid.
<structure>     Beat- or timecode-indexed storyboard: time | on screen |
                purpose | exit | carried object. About 1 idea per 1–2 s.
                Hook in the first 0.5–2 s, a breather before the climax,
                a held final lockup.
<motion rules>  Easing family with numbers (spring ω/ζ, bezier, durations),
                stagger, hold limits, transition grammar (morph / flood /
                mask / iris), what may overshoot.
<audio>         Music source/BPM, SFX policy (one whoosh per scene change,
                clicks on real actions), placement by measured peak, VO and
                caption rules, ducking, LUFS target (−14, TP ≤ −1 dBTP).
                Track supplied → beats.py --track song.mp3 --duration D
                writes music.wav + beats.js; time scenes with K.T(16).
                No track → silent, or beats.py --grid --bpm N --duration D.
                Hits list for MOTION.hits: when (s or 'Nb') | label | sfx
                (whoosh swoosh tick click pop thud blip riser swell impact
                shimmer type-key, or null for a silent visual hit).
<build>         seek(t) pure function; closed-form springs (sum per target
                change); seeded randomness; embedded assets; per-frame
                Playwright capture; N subframes + tmix; ffmpeg encode
                settings.
<gotchas>       Known engine traps for this style.
<verify>        5 s test → render.py --check-only (determinism, loop seam,
                safe_area, text_duration ≥ 8 frames) → --sheet (one per
                format) → full render per format → check.py (+ --sync
                sfx_events.json when there are SFX; sync ±20 ms) → show
                the video; critic rounds only if <review> asks.
<review>        Critic rounds: "none" by default (QA gates + one self-check
                of the sheet, then show the video). If the user wants a
                scored review: 2 for social clips, 3 for hero pieces (cap
                4), target every rubric score ≥ 8 and no FAIL gate; each
                round is appended to critique.md.
<start>         The approval gate: e.g. "show the beat map and 6 stills
                before rendering", or "don't ask, decide and keep going".
```
