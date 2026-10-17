---
description: Make a motion video end to end — brief (or build from an existing brief.md), storyboard, build, render, QA, show the MP4s (critic review rounds only on request)
argument-hint: <what the video is about | path/to/brief.md> [duration] [aspect e.g. 9:16] [style refs] [asset files] [--review [N]]
---

Make a motion-graphics video for: $ARGUMENTS

Use the `motion-video` skill. `S=${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts`.
Project folder: `./motion/<slug>/` (`P`); composition `P/<slug>.html`, `D` = its duration.

**Token economy** (always): write the composition once, then change it only with small edits,
never a full rewrite. Read a reference only when the piece needs it (audio.md only with sound,
assets.md only with assets, formats.md only for multiple formats). Look at only the images a step
names. Pass `--quiet` to render.py. Keep script output out of replies; quote numbers, not logs.

1. **Inputs.** If `$ARGUMENTS` contains a path to a `brief.md`, or the cwd is a
   `motion/<slug>/` folder with one, build from that brief: don't rewrite it, ask only about
   its remaining `[[TODO: …]]` items (one batch). Otherwise write the brief from
   `references/brief-template.md` and the closest playbook in `references/genres.md`, save
   `P/brief.md`, and ask in one batch only for what the user alone can supply (real assets,
   exact copy or numbers, the song, platform). Default the rest and state it.
   Asset paths or chat attachments → `python3 $S/ingest.py P <paths…>` first (`--attached`
   for uploads), and use the asset ids in the brief. Never invent assets or claims.
   Set the brief's `<renderer>` (2d | zdog | p5 | three | layered; default 2d). For zdog or
   layered, run `python3 $S/catalog.py search <subject words>` and list the matches in
   `<assets>` (as `catalog:<id>`) before building; model new only when nothing fits.
2. **Dependencies**, once: `python3 $S/render.py --help` and `ffmpeg -version`. On failure,
   print and stop: `pip install playwright numpy pillow`,
   `python3 -m playwright install chromium`, ffmpeg (`brew install ffmpeg` /
   `apt install ffmpeg` / `winget install ffmpeg`).
3. **Sign-off gate.** Show the storyboard table and the format list (`F`, e.g. `9x16,1x1`,
   from `<formats>`). If the user is present, stop and wait for approval. In unattended runs,
   continue and state the assumption.
4. **Build.** Copy the template for the brief's `<renderer>` **and** `templates/kit.js` into `P`:
   2d `composition.html`; zdog `zdog-composition.html` + `kit-zdog.js` (`vendor.py P zdog`,
   `catalog.py use P <ids>`, read `references/zdog.md`); p5 `p5-composition.html` + `kit-p5.js`
   (`vendor.py P p5`, p5 rules in `references/gotchas.md`); three `three-composition.html`
   (`vendor.py P three`, render with `--gl`); layered `layered-composition.html` + the kits of
   its layers + `kit-layers.js`. If a track was supplied, run
   `python3 $S/beats.py --track <song> --duration D --out P` before timing any scene, and
   include `beats.js` before the kit script. Lay out per format with `K.pick`, keep
   `[data-safe]` text inside `K.safe.ui`, put the brief's hits in `MOTION.hits`.
5. **Review.** `R="python3 $S/render.py"`. `$R P/<slug>.html --format F --check-only` (gates:
   determinism, loop seam, safe_area, text_duration) → fix every FAIL. Then `--format F --sheet`
   and look at **one sheet per format**: a self-check for broken frames, clipping, unreadable
   type. Use `--stills`/`--strip A:B:N`/`--phone` only to diagnose a specific problem.
6. **Render.** `$R P/<slug>.html --format F --deliver --subframes 3` (`--gl` for WebGL) →
   `P/renders/<slug>_<fmt>.mp4`, posters, sheets, `deliver.json`.
7. **Audio** (only if the brief has music or SFX; detail in `/motion-audio`):
   `$R P/<slug>.html --hits` → `python3 $S/sfx.py P/renders/<slug>_hits.json --out P/audio/sfx.wav`
   → `python3 $S/mix.py --duration D --out P/audio/mix.wav [--music P/music.wav]
   [--sfx P/audio/sfx.wav] --mux <every P/renders/<slug>_<fmt>.mp4>`.
   Music is user-supplied only; never fetch songs.
8. **QA.** `python3 $S/check.py <each mp4> --json P/renders/<slug>_<fmt>_qa.json` (`--loop` if
   MOTION.loop; with SFX add `--sync P/audio/sfx_events.json`). Fix FAILs; fix or explain WARNs
   (`frozen` is coarse: look at the frames before "fixing" it).
9. **Critic rounds: only on request.** Skip this step unless `$ARGUMENTS` has `--review [N]`,
   the user asks ("review it", "polish it", "critic"), or the brief's `<review>` sets rounds.
   Rounds = N, else the brief's `<review>`, else 2 (3 for hero pieces). Each round:
   run the `motion-critic` agent with the brief, the MP4s, `_sheet.png`, `_sheet_phone.png`,
   any strips or `_beats_sheet.png`, the `_qa.json` files and `P/critique.md` (create it with a
   `# Critique: <slug>` line if missing). Append its output unchanged to `P/critique.md`. Fix the top 3 (patch, don't rewrite), then 5–8 again.
   - No agents (Claude app chat): do a separate, explicitly fresh pass yourself. Re-read
     only the brief and the renders, not the code, and apply the rubric, verdict rule and
     output format in the skill's critic section (SKILL.md, "Critic rubric"; the same as
     `${CLAUDE_PLUGIN_ROOT}/agents/motion-critic.md`).
   - Stop at the first `ship` once the rounds are done. Cap: 4; if still `one more pass`,
     deliver and list what's open.
10. **Deliver and show.** Show the MP4s to the user (send or open the files when the host
    allows it). Report the video, poster and sheet paths from `P/renders/deliver.json`, the HTML
    source path, one line of assumptions, and (if critic rounds ran) the last scores table and
    verdict. Without rounds, end with: "Say *review it* for scored critic rounds, or name what to
    change." Edits afterwards: patch the HTML and re-run 5–8 only.
