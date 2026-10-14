# The motion brief

Fill every field before writing code. Defaults are fine; blanks are not.

```
<inputs>        What to ask the user for, each with a default if skipped:
                product/brand name, locked copy or transcript, real assets
                (logo, screenshots, clips, photos), facts file, song (BPM,
                drop position, licence), references.
<deliverable>   Duration (exact, e.g. 20.00 s), resolution and aspect(s),
                fps, loop yes/no, MP4 plus editable source, file-size cap,
                sound on/off.
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
                caption rules, ducking, LUFS target.
<build>         seek(t) pure function; closed-form springs (sum per target
                change); seeded randomness; embedded assets; per-frame
                Playwright capture; N subframes + tmix; ffmpeg encode
                settings.
<gotchas>       Known engine traps for this style.
<verify>        5 s test → stills per beat or contact sheet → pop scan →
                loop-seam diff → contrast and loudness measures → fresh-
                critic pass → fix the worst first → full render.
<start>         The approval gate: e.g. "show the beat map and 6 stills
                before rendering", or "don't ask, decide and keep going".
```
