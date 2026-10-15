# Security policy

## Supported versions

Security fixes go into the latest release on the `main` branch.

## Reporting a vulnerability

Please report security issues privately, not in a public issue:

- **Preferred:** GitHub private vulnerability reporting, via
  <https://github.com/sarupurisailalith/motion-studio/security/advisories/new>
- **Or email:** sarupurisailalith@gmail.com, with "Motion Studio security" in the subject

Include the version, the steps to reproduce and what an attacker could do. You'll get an
acknowledgement within 3 working days and a plan for a fix after the issue is confirmed.

## Scope

Motion Studio runs local Python scripts, headless Chromium and ffmpeg on files you give it. In
scope are issues such as a crafted asset (SVG, font, video, audio) that escapes the project
folder or runs code during `ingest.py`, the local render server being reachable from outside
`127.0.0.1`, or a script writing outside the project folder.
