# Style guide from a reference

Fill this in **before the storyboard** whenever the user gives a reference (a video or stills),
and save it as `P/style_guide.md`. It turns "make it feel like this" into numbers and rules the
brief can use.

**What you take, what you keep.** Take the reference's **rhythm, motion and composition**. Keep
the user's **brand**: their colours, type, logo, copy, assets and claims. Never copy the
reference's footage, characters, artwork, logo, wording or a signature move frame for frame.
References are for study, and only ones the user supplied (local files; never fetch one).

## 0. Measure first
```bash
python3 $S/reference.py <ref.mp4 | stills folder | a.png b.png …> P      # local files only
```
→ `P/docs/reference/<name>/`: `cuts.json`, `sheet.png` (1 fps), `shots.png` (one frame per shot),
`shots/`. Look at both sheets, then fill the sections below. Only hard cuts register: if the
sheet shows morphs, masks or match cuts that `cuts.json` missed, say so in §2 and count them by eye.

```
<source>        Path, length, aspect, fps. Who supplied it, and that it's for study only.

<numbers>       From cuts.json (video only):
                hard cuts/min ……  median shot …… s (min …… / max ……)
                still share ……  longest still …… s at …… s
                mean frame delta ……  hard jumps/s ……
                Cuts the detector missed (seen on the sheet): …… at …… s

<rhythm>        How time is spent: shot-length pattern (e.g. "long 3 s open,
                then 0.4–0.6 s cuts, 1.5 s held end card"), where the
                breathers fall, how cuts sit on the music (on the beat, on
                the off-beat, on phrases), how long text stays up.
                → feeds <structure> and the hold limits in <motion rules>.

<motion>        Easing feel (snappy ease-out, soft spring, linear drift),
                typical speeds (fraction of the frame per second), overshoot
                yes/no, what moves at the same time, camera vocabulary
                (push, pan, locked off), transition grammar (hard cut /
                morph / mask wipe / whip / match cut).
                → feeds <motion rules> with numbers (spring ω/ζ, durations).

<composition>   Framing and scale (subject fills the frame / small in space),
                grid and alignment, negative space, type placement and size
                relative to the frame, density (elements on screen at once),
                depth and layering, how each aspect ratio is handled.
                → feeds <art direction> composition rules and <formats>.

<keep ours>     The user's palette (hex + role), fonts, logo, copy and assets
                that replace the reference's. Name every place the reference's
                own look would leak in (its colours, its typeface, its mascot)
                and what replaces it.

<don't copy>    The specific shots, artwork, characters, wording and
                signature moves that stay the reference's.

<pacing target> Ours should land within 30 % of the reference's hard cuts/min
                and motion share (1 − still share), unless the brief says
                otherwise (e.g. "calmer than the reference"). After the render:
                check.py renders/<slug>_<fmt>.mp4 --against
                P/docs/reference/<name>/cuts.json
                A pacing WARN is a prompt to look, not a verdict: a piece built
                on morphs has few hard cuts by design.
```

Stills only (no video): skip `<numbers>` and `<rhythm>` beyond what the frames imply, and put
the weight on `<composition>`: grid, scale, type size, colour proportions (in our palette).
