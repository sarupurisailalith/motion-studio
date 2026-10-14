# Production workflow

- **Deterministic rendering:** Every animated value is a function of timeline time. Expose `window.seek(t)` (often async, awaiting image and video decodes), `window.ready`, and `window.frame(n)` for n = 0…N−1 at t = n/fps. Some briefs call it `renderAt(t)` or `draw(f)`. Seeking must work out of order. Rules: no CSS transitions or animations, no setInterval or rAF state, no accumulated physics, no unseeded `Math.random` (use a seeded hash per id and time), and no React state across frames. A `?t=` URL parameter freezes an exact moment.
- **GSAP variant:** Use a single paused GSAP master timeline and seek it per frame.
- **Capture:** Playwright, or puppeteer-core, calls seek per frame and screenshots, piping PNGs into ffmpeg. For WebGL headless, use Chromium `--use-angle=swiftshader`, or the Mac GPU for raymarching.
- **Encode:** H.264, yuv420p, CRF 16, declared pixel aspect ratio. Add a separate audio mux, plus a high-quality master and a share-size version. Some briefs cap size, for example "≤30 MB at 1280×720 30 fps".
- **Footage in the DOM:** Re-encode all-intra (`ffmpeg -g 1`), load as a blob URL (python http.server can't range-seek) and await `seeked`. Alternatively extract a 30 fps JPEG sequence and draw frame `floor(t*30)`.
- **Package everything:** Fonts and artwork are embedded or pinned locally, with no network at render time.
- **Formats seen:** 1440×1440 (dominant for X), 1920×1080, 1080×1080, 1080×1920 vertical, 1080×1350 (LinkedIn), 4:3 1440×1080, and 2.39:1 4K. Multi-aspect rules: keep content inside a 9:16-safe centre, export all aspects in parallel from one timeline, and keep text clear of the TikTok/IG UI.
- **Frame rates:** 60 fps for UI and kinetic work. 30 fps for 3D, long-form or size-capped work. 24 fps for the brand-film "cinematic" look. Japanese "on twos" (8–12 fps feel) for hand-drawn and claymation.
- **Beat maths:** `B = 60/BPM`. 120 BPM × 7 bars = 28 beats = 14 s, and at 60 fps × 4 subframes that is 3,360 browser renders. Choose the BPM so a grid cell is an integer number of frames.
- **Loop seam:** Render frame 0 vs frame N, where one changed pixel means a failure. Export `[0, duration)` without duplicating the endpoint. Match cursor position and velocity at the wrap, using `t - D*floor(t/D)`. Choose rotating-pattern speeds that land on the same phase at the end. Make the audio loop too.
- **Verification loop:**
  1. Render a 5 s test first.
  2. Render one still per beat or per major scene and check it as a contact sheet. Some briefs specify a sheet every 0.2 s plus 16–20 fps sheets around each transition.
  3. Scan for single-frame pops: frame-difference spikes 3× their neighbours.
  4. Measure frozen time, loudness and contrast (4.5:1).
  5. Compare motion stats against a reference: hard jumps per second and share of still frames.
- **Fresh-critic loop:** A fresh reviewer gets the render, brief and QA output. It returns a ranked, timestamped list ending in "ship" or "one more pass", and later reviews check earlier items as fixed, partly fixed or still there. Keep a ledger of each round.
- **Approval gates:** "Ask me for the inputs, then show the beat map and 4–8 stills before rendering." Also "write the storyboard table (time / on screen / purpose / exit / carried object) before animation."
- **Parallelism:** Write shared pieces first (palette, fonts, shared 3D models, handoff pixel positions). Then run parallel builders or sub-agents per section or scene. Each scene has its own test page.
- **Reference study:** Run a numeric per-frame pass (frame delta, brightness, edges) to find cuts. Make an overview contact sheet plus dense 1 s sheets at transitions. Write a note per video. References are study-only: never copy them.
- **Possible tools:** GSAP, Three.js, Canvas 2D, Blender Python, Python and ffmpeg compositors, speech alignment and stem separation tools.
