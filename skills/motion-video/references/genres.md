# Genre playbooks

Pick the closest format and adapt its timing, visual rule and build notes to the user's brief.

### 1 One-shape UI-morph loop ("Dribbble-level UI motion")
- **Timing and structure:** As one possible grid, 120 BPM for 7 bars gives 28 beats over 14 s. A persistent element can morph through a short sequence of UI states, such as button → loader → player → slider → chart → button.
- **Look and motion:** Warm-gray or off-white canvas, black and white components, at most one accent, and a single UI font (Geist or Inter). A visible cursor drives every change with real clicks and drags. The camera zooms so each state fills the frame. Last frame = first frame.
- **Tech:** Single HTML, `seek(t)`, closed-form springs, Playwright plus ffmpeg tmix.

### 2 Product launch / brand film ("Apple-keynote", one continuous take)
- **Length and format:** 15–25 s, 16:9 1920×1080 or square 1440×1440, 60 fps.
- **Transitions:** Scenes are made out of the previous scene, with no fades, blurs or cuts. Floods are the main tool: a colour fills from an object and contracts into the next one. Other devices are iris opens, goo splits and merges, buttons that expand into pages, text rising from a mask line, and liquid-glass panels.
- **Timing:** Each scene is pinned to a beat number, and the song's drop is placed on a named beat, for example "song starts 8 beats before its drop" or "the zoom lands on the drop".
- **Content:** Use supplied photos and clips where appropriate. Include explicit CTA and brand-lock beats.

### 3 Developer-tool / feature showreel with an exact sequence
- **Structure:** Fixed timecodes in roughly 2 s blocks, each carrying one verified feature and one short on-screen line.
- **Accuracy:** Accuracy guardrails list which claims are allowed, for example "do not call it stable v1" or "every number comes from the facts file".
- **Rule:** Every transition demonstrates a feature instead of swapping title cards.

### 4 Kinetic typography / spoken-word / speech film
- **Format:** 20.00 s, 1080×1080, 60 fps, single HTML.
- **Text:** Exact locked copy is given in order, with "no extra slogans".
- **Visual rule:** One central rule turns words into objects. A baseline can become an orbit, or words can become architectural members or magnetic field elements.
- **Choreography:** Phrase-group reveals in reading order. Reading holds come before any ornamental motion: "hold the completed phrase motionless for 700 ms", and "at least one 400 ms moment of absolute stillness". The camera budget is limited, for example only pullback, roll and velocity-match. The active phrase is at least 64 px high.
- **Typography:** A high-contrast serif for speech, a heavy grotesque for load-bearing words, and a monospace for timing marks.

### 5 Data / science / math explainer
- **Simulate rather than draw:** "The random walk should be an actual random walk".
- **Data:** Real numbers with stated uncertainty, a locked numeric example, and logic guardrails, for example "don't claim p#+1 is always prime".
- **Audio:** Voiceover from TTS plus burned-in captions for sound-off viewing. The music ducks under the voice.
- **Style:** Choose a visual metaphor that explains the mechanism without hiding uncertainty.

### 6 Recipe / process explainer
- **Shape:** "Empty glass to completed cocktail", about 30 s, with ingredients and measurements shown as they pour. Live counters and a checklist.

### 7 History / timeline / epic chronicle
- **Structure:** A horizontal axis with the camera pushing along it. Each node is lit and scaled, shows a large year, and has one event line.
- **Music as clock:** BPM rises with the era, and every cut lands on a beat.
- **Look:** Alternating art styles per chapter and evolving ornament sets. A HUD carries the chapter seal, the dynasty or era name, and a year counter.

### 8 Showreel / "motion designer résumé"
Give the showreel a structure beyond a sequence of effects:
- **A one-line concept:** For example, one mark changes roles as each skill is demonstrated.
- **A technique checklist:** at least 6 techniques from type, morph, mask transition, parallax/3D, particles gather/scatter, and counters or line-draws.
- **A 0.5 s-grid storyboard table.**
- **A through-line object:** for example an orange dot.

### 9 Music video / lyric video
- **Analysis:** The soundtrack is analysed first. Stems are separated with Demucs. Lyrics are word-aligned with (mlx-/faster-)whisper. The rule is one lyric line per scene.
- **Typography:** Lyric type ranges from subtitle-small to screen-filling. Big lyrics need a quieter background, with characters placed on the opposite side.
- **Look:** A papery or hand-drawn look is a frequent style.

### 10 3D hero / cinematic scene (Three.js)
- **Format:** A vertical short film (1080×1920, 30 fps, about 37 s) or a 3D hero object.
- **Narrative:** An emotional arc driven by light, for example a window sealed by word-blocks, then darkness, then one block falling and colored shafts appearing.
- **Lighting:** "Light it like a product shoot: soft key from one side, rim behind."
- **Camera:** 35–55° elevation. Never look straight down on a large surface.

### 11 Generative / shader / demoscene
- **Rendering:** One WebGL2 fragment-shader raymarcher. A single page serves as both the live player and the offline render source. Offline render is 16 samples per pixel.
- **Sync:** A JSON beat map holds hits, breaks and kick/snare/hat onsets. Kicks pulse the light and hats add surface detail.

### 12 Interactive explainer object (explode view)
- **Interaction:** Model the object and its interior parts in 3D. An Explode button moves parts apart; labels and hover highlights explain them. Add orbit and zoom controls.

### 13 Pixel art / game-feel / reward moment
- **Pixel-art rendering:** Logical resolution 128×96, integer upscale, `imageSmoothingEnabled=false`, about 24-colour palette. Pose parameters are animated smoothly but quantised so the motion reads at 8–12 fps while running at 60. The particle pool does no allocation.
- **Reward moment:** Five phases — idle, upgrade, charge (about 1 s), burst, reveal/settle. It uses squash and stretch, a hit-stop of 50–100 ms, layered shockwaves, and confetti only once at the peak.

### 14 Story / narrative short (hand-drawn, papery)
- **Medium:** Canvas 2D only, no libraries, with music synthesised in Web Audio.
- **Sync:** One timeline drives both picture and sound, so "the robot's hands hit the keys that are actually sounding".
- **Style:** Crayon, watercolour, torn paper, chalk, or shadow theatre. Some briefs mix 2.5D compositing with depth-estimated parallax and 4K supersampling.

### 15 Physics / mechanism simulation
- **Rule:** The mechanism really computes its result. "Do not compute the answer in JS arithmetic; read it from the toggle states".
- **Recording:** A DEMO button runs scripted cases so the piece can be screen-recorded hands-off.

### 16 Audio-reactive / self-scoring
- **Pattern:** Score first. Export every beat as data. Run an FFT on the film's own mix so the EQ bars show the real track. Grade one still per beat on a 1–10 scale.
