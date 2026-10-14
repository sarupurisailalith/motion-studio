---
description: Turn a rough video idea into a production-grade motion brief (no rendering)
argument-hint: <rough idea>
---

Write a complete motion-video brief for: $ARGUMENTS

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/brief-template.md` and
   `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/genres.md`.
2. Pick the closest genre playbook and choose a visual rule, beat structure and transition
   approach that fit the user's subject.
3. Produce the brief with every template field filled — exact duration/aspect/fps, a one-line
   concept, hex palette with roles, fonts, locked copy (mark anything the user must supply as
   `[[TODO: …]]`), a beat/timecode storyboard table, motion rules with numbers, audio plan,
   banned list, verification steps and the approval gate.
4. End by listing the inputs still needed from the user.

Save it as `brief.md` in a new folder `./motion/<slug>/` so `/motion` can build from it.
