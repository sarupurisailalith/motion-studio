---
description: Make a motion video end to end — brief, storyboard, build, render, QA, deliver an MP4
argument-hint: <what the video is about> [duration] [aspect e.g. 9:16] [style refs]
---

Make a motion-graphics video for: $ARGUMENTS

Use the `motion-video` skill and follow its workflow in order (brief → storyboard → build from
template → stills/contact-sheet review → full render → check.py → fresh critic → deliver).
Scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/`.

- If the request is missing something only the user can supply (real brand assets, exact
  copy or numbers, the song, target platform/aspect), ask for it in one short batch before
  building; otherwise choose confident defaults and state them.
- Use the closest genre playbook to choose a concept, timing and transition approach before
  writing the brief.
- Work in a new folder named after the piece (e.g. `./motion/<slug>/`).
- Show the storyboard and a contact sheet before the full render if the user is present.
- Finish with the MP4 path, the HTML source path, and one line on any assumptions.
