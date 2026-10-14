---
description: Turn a rough video idea (plus any asset files) into a production-grade motion brief (no rendering)
argument-hint: <rough idea> [asset files or folders]
---

Write a complete motion-video brief for: $ARGUMENTS

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/brief-template.md` and
   `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/genres.md`.
2. Pick a slug and create `./motion/<slug>/`.
3. **Assets.** If `$ARGUMENTS` names files or folders, or the user attached files in chat,
   run `python3 ${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/ingest.py ./motion/<slug>
   <paths…>` (add `--attached` for chat uploads). Read `assets/assets.json`. Name any
   missing or unreadable file. Never invent assets; ask the user to confirm they own them
   or may use them.
4. Pick the closest genre playbook and choose a visual rule, beat structure and transition
   approach that fit the user's subject.
5. Fill every template field — exact duration and fps, a one-line concept, hex palette with
   roles, fonts, locked copy (mark anything the user must supply as `[[TODO: …]]`), a
   beat/timecode storyboard table that references asset ids, motion rules with numbers,
   banned list, approval gate, and:
   - `<assets>`: each ingested id mapped to its beat(s); "supplied assets are used as-is".
     None given → `[[TODO: logo, screenshots …]]` for what the piece needs.
   - `<formats>`: from 16x9 / 9x16 / 1x1 / 4x5 (default: the user's platform, else 16x9),
     with per-format layout notes and the safe-area rule.
   - `<audio>`: track (user-supplied only) or silent, plus the `MOTION.hits` list with
     palette sfx names.
   - `<verify>`: include the safe_area, text_duration and (with SFX) sync gates.
   - `<review>`: "none" unless the user wants scored critic rounds (then 2 social, 3 hero).
6. Save it as `./motion/<slug>/brief.md`, then list the inputs still needed from the user
   (every `[[TODO: …]]`). Next step: edit the file if wanted, then
   `/motion ./motion/<slug>/brief.md`.
