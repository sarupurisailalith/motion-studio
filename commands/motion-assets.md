---
description: Bring your own logo, screenshots, fonts, clips, audio or brand guide into a motion project
argument-hint: <files, folders or attachments> [--project ./motion/<slug>]
---

Ingest these assets into a motion project: $ARGUMENTS

Script: `${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/ingest.py`. Reference:
`${CLAUDE_PLUGIN_ROOT}/skills/motion-video/references/assets.md`.

1. **Project folder.** Use `--project` if given. Otherwise use the most recently modified
   `./motion/<slug>/`. If there is none, or more than one could fit, ask which one, or
   suggest a new `./motion/<slug>/` named after the piece.
2. **Inputs.** Collect every file and folder path from the arguments. Files attached in
   Claude app chat (e.g. under `/mnt/user-data/uploads/`) are ingested the same way. Run those
   in a separate call with `--attached` so they're marked `source: "attached"`.
3. **Run** `python3 ingest.py <project> <paths...> [--attached]`. Defaults: `--max-dim 3840`
   (2× a 1920 px frame), `--clip-fps` = the piece's fps (from the composition's MOTION or
   brief.md, else 30). ingest.py copies everything into `<project>/assets/` and
   writes `assets.json`, `assets.js` and `fonts.css`. Re-running is safe: it merges by
   original path. A video's own sound is ingested too, as an audio entry `<id>-audio`
   (48 kHz WAV, aligned to the clip's first frame); a clip with no sound gets a note. When the
   clip is a person talking for a footage-led piece, `--clip-fps` follows the piece's fps by
   default and `--clip-max-dim 1280` keeps the frames small (see `references/footage.md`).
4. **Summarise** the printed JSON as a short table: id, kind, size or duration, alpha, and any
   notes (downscaled, GIF first frame only, font name guessed, unknown type stored as a doc,
   clip audio written or missing, variable frame rate resampled).
5. **Flag problems by name.** Anything under `missing` (wrong path) or `unreadable` (corrupt,
   unsupported, or an unsafe SVG). The exit code is 1 when either list is non-empty, but
   everything else was still ingested. Ask for a replacement. Never draw or generate a
   stand-in for a missing asset.
6. **Ask the user to confirm** that they own these assets or have permission to use them in
   this video. Font files are used only for this render and are never redistributed.
7. **Next step.** Suggest `/motion-brief` (or `/motion` if a brief already exists). The brief
   names which asset id appears in which beat. Supplied assets are used as-is.

Never invent assets, logos, screenshots or product UI. Never fetch anything from the network
here. If the user gives a URL instead of a file, ask them to download or screenshot it and
attach the file.
