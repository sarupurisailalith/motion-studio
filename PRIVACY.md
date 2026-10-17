# Privacy

Motion Studio runs entirely on your own machine. It has no server, no account and no telemetry.

## What it collects

Nothing. The plugin does not collect, store, sell or share any personal data, usage data or
conversation content, and it never sends anything to the author or to any third party.

## What it reads and writes

- **Reads:** only the files you name or attach (logo, screenshots, fonts, clips, audio, a brand
  guide, a `brief.md`, a reference video or stills for `reference.py`) and the compositions it
  builds for you. `reference.py` analyses local files only and never downloads a reference.
- **Writes:** only inside your project, under `motion/<slug>/` (brief, assets, composition HTML,
  renders and their reuse cache in `renders/.cache/`, reports).
- It does not read Claude's memory, chat history or conversation summaries.

## Network

Rendering and QA don't need the network. A composition is served to headless Chromium from
`http://127.0.0.1` on a random local port that only your machine can reach, and compositions the
plugin builds load their libraries from a local `vendor/` folder. If you render your own HTML that
links to remote URLs (a CDN script, a web font), Chromium fetches those like any browser would.
The plugin's own downloads happen only when you set things up:

| When | What is downloaded | From |
|---|---|---|
| You install the requirements | `playwright`, `numpy`, `pillow` (and optionally `librosa`, `pypdf`, `faster-whisper`) | PyPI |
| You run `python3 -m playwright install chromium` | A Chromium build | Playwright's download host |
| You (or the agent, for a Three.js/GSAP/Lottie/Zdog/p5.js piece) run `vendor.py` | Exact pinned versions of `three`, `gsap`, `lottie-web`, `zdog` + `zfont`, `p5`, with their licence files, into that project's `vendor/` folder | The npm registry |
| You choose to install `faster-whisper` (optional, for word timings) and run `transcribe.py` | On its first use, faster-whisper downloads the speech model weights you name (default `small`); later runs use the cached copy. Your audio is transcribed locally and never uploaded | Hugging Face (huggingface.co) |

Those requests go to the services listed above under their own privacy policies. Motion Studio
sends them no data about you or your project.

## Retention

Everything the plugin makes stays in your project folder until you delete it.

## Children

Motion Studio is a developer tool and is not directed at children under 18.

## Contact

Questions about privacy: open an issue at
<https://github.com/sarupurisailalith/motion-studio/issues> or email sarupurisailalith@gmail.com.

_Last updated: 2026-10-17_
