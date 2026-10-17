#!/usr/bin/env python3
"""
render.py — deterministic frame-by-frame renderer for Motion Studio compositions.

Loads an HTML composition that exposes window.MOTION / window.ready / window.seek(t),
seeks every frame (optionally N sub-frames for motion blur), screenshots it in headless
Chromium, and pipes the PNGs straight into ffmpeg. Also runs the core QA gates.

Usage:
  python3 render.py comp.html                         # full render -> comp.mp4
  python3 render.py comp.html --preview               # 5 s test render at half res
  python3 render.py comp.html --stills 0,1.5,3,4.5    # PNG stills only (fast review)
  python3 render.py comp.html --sheet                 # contact sheet of 16 evenly spaced stills (stills
                                                      # -> renders/stills/)
  python3 render.py comp.html --subframes 4           # motion blur (4 samples / frame)
  python3 render.py comp.html --audio track.wav       # mux audio (+ loudnorm to -14 LUFS)
  python3 render.py comp.html --check-only            # gates only, no video: determinism, loop seam,
                                                      # safe_area ([data-safe] inside K.safe.ui),
                                                      # text_duration ([data-text] visible >= 8 frames),
                                                      # contrast ([data-text] >= 4.5:1 on what's behind it);
                                                      # footage pieces add cue_timing + claim_trace
  python3 render.py comp.html --check-only --thorough # denser sampling (slower)
  python3 render.py comp.html --workers 4             # parallel render (default: the CPUs, max 6)
  python3 render.py comp.html --capture screenshot    # v0.2 capture (default auto: CDP screenshots, or the
                                                      # canvas itself when the page is one canvas; same pixels)
  python3 render.py comp.html --no-cache              # always render (default: a rerun with unchanged page files
                                                      # and flags reuses renders/.cache/ and only re-muxes --audio)

  python3 render.py comp.html --format 16x9,9x16      # one render per format -> comp_16x9.mp4, comp_9x16.mp4
                                                      # (page gets ?format=&w=&h=; formats: 16x9 9x16 1x1 4x5)
  python3 render.py comp.html --format 16x9,9x16 --deliver   # + poster, sheet, phone sheet per format,
                                                             # renders/deliver.json
  python3 render.py comp.html --poster 4.5            # one PNG -> renders/comp_poster.png (no T: MOTION.poster)
  python3 render.py comp.html --strip 2:3:6 --subframes 4  # 6 blurred stills across a transition, one row
  python3 render.py comp.html --phone                 # contact sheet at phone size -> comp_sheet_phone.png
  python3 render.py comp.html --contact beats         # one still per downbeat (needs beats.js)
  python3 render.py comp.html --hits                  # resolve MOTION.hits -> renders/comp_hits.json, no render

Gates sample fixed times: determinism checks 8 times drawn from a fixed seed (the same every run),
contrast and safe_area every 0.25 s. A pass means those samples were clean, not that every frame is;
--thorough samples more densely.

Review renders (--stills --sheet --poster --strip --phone --contact) and --check-only combine with
--format; every output then gets the _<fmt> suffix (comp_9x16_poster.png). With --format, the
--check-only report is {"formats": {"9x16": {...}, ...}}; without it, output is exactly as in v0.1.

Requires: pip install playwright && python3 -m playwright install chromium ; ffmpeg on PATH.
"""
import argparse, asyncio, base64, hashlib, json, math, os, random, shutil, subprocess, sys, time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("playwright missing: pip install playwright && python3 -m playwright install chromium")


QUIET = False   # --quiet: drop progress chatter (vlog); results and errors still print (log)


def log(*a):
    print("[render]", *a, flush=True)


def vlog(*a):
    if not QUIET:
        log(*a)


# C2 formats: the single source of truth for names and sizes ("native" = MOTION.width/height)
FORMATS = {"16x9": (1920, 1080), "9x16": (1080, 1920), "1x1": (1080, 1080), "4x5": (1080, 1350)}

_SERVERS = {}
_SERVED = {}     # E8.4: served folder -> {relative path: sha256 at serve time, or None if missing}
_EXTERNAL = []   # URLs the pages fetched from anywhere but the local server (renders not cached)


def serve(directory: Path) -> str:
    """Serve the composition folder over http://127.0.0.1 (ES modules, fetch and
    video seeking do not work from file://). One server per folder, reused."""
    import functools, http.server, threading
    directory = directory.resolve()
    if directory not in _SERVERS:
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    pass   # the page cancelled the request (e.g. p5 loadFont's first fetch)
            def send_head(self):
                note_served(directory, self.translate_path(self.path))
                return super().send_head()
        handler = functools.partial(Quiet, directory=str(directory))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _SERVERS[directory] = f"http://127.0.0.1:{srv.server_address[1]}/"
    return _SERVERS[directory]


def watch_requests(page, errors):
    """E10.8: report a failed request as a page error unless the same URL also loads (status
    < 400). p5's loadFont fetches twice and cancels the first; that cancel is not an error.
    A URL that only ever fails is still reported."""
    loaded = set()

    def failed(r):
        if r.url not in loaded:
            errors.append(f"requestfailed: {r.url}")

    async def finished(r):
        resp = await r.response()
        if resp and resp.status < 400:
            loaded.add(r.url)
            while f"requestfailed: {r.url}" in errors:
                errors.remove(f"requestfailed: {r.url}")

    page.on("requestfailed", failed)
    page.on("requestfinished", finished)

CAPTURE = "auto"   # --capture: auto (CDP + canvas fast path) | cdp | screenshot (v0.2 path)
# auto/cdp without --gl: rAF and capture are not held to 60 Hz (seek + 2 rAFs + capture waited
# ~3 vsyncs). Not with --gl: SwiftShader then composites far more often and costs ~25% more CPU.
UNCAPPED = ["--disable-frame-rate-limit", "--disable-gpu-vsync"]
CAPTURE_LABEL = {"auto": "CDP screenshots", "cdp": "CDP screenshots", "screenshot": "page.screenshot (v0.2)"}
_CDP = {}

# seek, two rAFs (layout/paint committed), fonts; then [x, y] of the viewport when a bare CDP
# capture equals page.screenshot(animations="disabled", caret="hide"), else null
SEEK_PLAIN_JS = """async t => {
  await window.seek(t);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  if (document.fonts) await document.fonts.ready;
  if (window.frames.length || document.getAnimations().length ||
      document.querySelector('input,textarea,[contenteditable]')) return null;
  const w = document.createTreeWalker(document, NodeFilter.SHOW_ELEMENT);
  for (let n = w.nextNode(); n; n = w.nextNode()) if (n.shadowRoot) return null;
  const v = window.visualViewport;
  return v && v.scale === 1 ? [v.pageLeft, v.pageTop] : null;
}"""


# E8.1 canvas fast path. CANVAS_PROBE_JS: is the picture exactly one <canvas> filling the viewport
# at device-pixel size, with nothing else that renders? -> {kind, alpha} or {why}.
CANVAS_PROBE_JS = """() => {
  if (!document.body) return { why: 'no <body>' };
  const cs = document.querySelectorAll('canvas');
  if (cs.length !== 1) return { why: cs.length + ' <canvas> elements' };
  const c = cs[0], r = c.getBoundingClientRect(), dpr = window.devicePixelRatio;
  if (r.left || r.top || r.width !== innerWidth || r.height !== innerHeight)
    return { why: 'the canvas does not fill the viewport' };
  if (c.width !== Math.round(innerWidth * dpr) || c.height !== Math.round(innerHeight * dpr))
    return { why: `canvas is ${c.width}x${c.height}, not the viewport's device pixels` };
  if (window.frames.length) return { why: 'the page has iframes' };
  const up = new Set();
  for (let e = c; e; e = e.parentElement) up.add(e);
  const inert = new Set(['SCRIPT', 'STYLE', 'LINK', 'META', 'TEMPLATE', 'NOSCRIPT', 'TITLE']);
  for (const e of document.body.querySelectorAll('*'))
    if (!up.has(e) && !inert.has(e.tagName)) return { why: `another element renders (<${e.tagName.toLowerCase()}>)` };
  let ctx = null, kind = null;
  try {
    for (kind of ['webgl2', 'webgl', '2d']) if ((ctx = c.getContext(kind))) break;
  } catch (e) { return { why: 'canvas context unavailable (' + e.name + ')' }; }
  if (!ctx) return { why: 'no webgl/2d context on the canvas' };
  const at = ctx.getContextAttributes ? ctx.getContextAttributes() : null;
  if (!at) return { why: 'no canvas context attributes' };
  window.__motionCanvas = { c, up: [...up], n: document.getElementsByTagName('*').length };
  return { kind, alpha: at.alpha !== false };
}"""

# seek, then the canvas as a PNG data URL; null if the page no longer qualifies (new elements,
# canvas resized, CSS opacity/filter/transform on it) -> screenshot. No rAF wait: seek() draws
# the frame (the contract), WebGL without preserveDrawingBuffer is cleared once composited, and
# a page that draws later anyway fails canvas_path's comparison with the screenshot.
CANVAS_SNAP_JS = """async ({ t, alpha }) => {
  await window.seek(t);
  const m = window.__motionCanvas, c = m.c;
  if (!c.isConnected || document.getElementsByTagName('*').length !== m.n || window.frames.length ||
      c.width !== Math.round(innerWidth * devicePixelRatio) || c.height !== Math.round(innerHeight * devicePixelRatio) ||
      document.getAnimations().length) return null;
  for (const e of m.up) {
    const s = getComputedStyle(e);
    if (s.opacity !== '1' || s.filter !== 'none' || s.transform !== 'none' || s.visibility !== 'visible' ||
        s.mixBlendMode !== 'normal' || s.clipPath !== 'none' || s.maskImage !== 'none' || s.backdropFilter !== 'none')
      return null;
  }
  // copy to a CPU-side canvas: encoding from it is faster than c.toDataURL, and with an alpha
  // channel every pixel must be opaque (else the page behind would show in a screenshot)
  if (!m.o || m.o.width !== c.width || m.o.height !== c.height) {
    m.o = new OffscreenCanvas(c.width, c.height);
    m.x = m.o.getContext('2d', { willReadFrequently: true });
  }
  m.x.clearRect(0, 0, c.width, c.height);
  m.x.drawImage(c, 0, 0);
  if (alpha) {
    const d = m.x.getImageData(0, 0, c.width, c.height).data;
    for (let i = 3; i < d.length; i += 4) if (d[i] !== 255) return null;
  }
  const b = await m.o.convertToBlob({ type: 'image/png' });
  return await new Promise((ok, no) => {
    const f = new FileReader();
    f.onload = () => ok(f.result);
    f.onerror = () => no(f.error);
    f.readAsDataURL(b);
  });
}"""


async def canvas_snap(page, t, mode):
    """PNG straight from the composition's canvas (no compositor pass), or None when the page
    no longer qualifies (then the caller takes a screenshot)."""
    try:
        url = await page.evaluate(CANVAS_SNAP_JS, {"t": t, "alpha": mode["alpha"]})
    except Exception:  # e.g. a lost WebGL context: the screenshot path decides what happens
        return None
    return base64.b64decode(url[url.index(",") + 1:]) if url else None


def same_pixels(a: bytes, b: bytes) -> bool:
    import io
    import numpy as np
    from PIL import Image
    ia, ib = (np.asarray(Image.open(io.BytesIO(x)).convert("RGB")) for x in (a, b))
    return ia.shape == ib.shape and np.array_equal(ia, ib)


async def canvas_path(page, ts):
    """E8.1: (mode, None) when the canvas fast path is safe on this page, else (None, reason).
    Safe = the probe passes AND the canvas PNG equals the screenshot pixel for pixel at each t
    (seeked out of order, so a canvas drawn late, in a rAF, shows up as a mismatch)."""
    if CAPTURE != "auto":
        return None, f"--capture {CAPTURE}"
    await page.evaluate("t => window.seek(t)", ts[-1])   # contexts are made by now
    p = await page.evaluate(CANVAS_PROBE_JS)
    if "why" in p:
        return None, p["why"]
    for t in ts:
        c = await canvas_snap(page, t, p)
        if c is None or not same_pixels(c, await snap(page, t)):
            return None, f"canvas pixels differ from the screenshot at t={t:.3f}"
    return p, None


async def cdp_session(page):
    """One CDP session per page (None when it can't be opened: use page.screenshot)."""
    if page not in _CDP:
        try:
            _CDP[page] = await page.context.new_cdp_session(page)
        except Exception:
            _CDP[page] = None
    return _CDP[page]


async def open_page(pw, html: Path, fmt=None, width=None, height=None, scale=1.0, gl=False):
    args = ["--hide-scrollbars", "--force-color-profile=srgb", "--disable-lcd-text",
            "--font-render-hinting=none", "--autoplay-policy=no-user-gesture-required"]
    if gl:
        args += ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    elif CAPTURE != "screenshot":
        args += UNCAPPED
    browser = await pw.chromium.launch(args=args)
    if fmt:
        width, height = FORMATS[fmt]
    # first open at a provisional size to read MOTION, then resize precisely
    ctx = await browser.new_context(viewport={"width": width or 1080, "height": height or 1080},
                                    device_scale_factor=scale)
    page = await ctx.new_page()
    page.on("request", lambda r: note_request(r.url))
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    watch_requests(page, errors)
    url = page_url(html, fmt)
    await page.goto(url, wait_until="load")
    try:
        await page.wait_for_function("window.MOTION && window.seek && window.ready", timeout=30000)
    except Exception:
        sys.exit("composition never exposed window.MOTION / window.seek / window.ready.\n  "
                 + "\n  ".join(errors[:20] or ["(no page errors captured)"]))
    await page.evaluate("window.ready")
    motion = await page.evaluate("window.MOTION")
    if fmt and (int(motion["width"]), int(motion["height"])) != FORMATS[fmt]:
        await browser.close()
        sys.exit(f"--format {fmt}: the composition ignored ?format=&w=&h= (MOTION is "
                 f"{motion['width']}x{motion['height']}, expected {FORMATS[fmt][0]}x{FORMATS[fmt][1]}).\n"
                 "  Call K.init(MOTION) right after window.MOTION is defined (see templates/kit.js),\n"
                 "  or set MOTION.width/height from the w/h URL parameters yourself.")
    await page.set_viewport_size({"width": int(motion["width"]), "height": int(motion["height"])})
    return browser, page, motion, errors


async def snap(page, t: float, clip=None, fast=True) -> bytes:
    """PNG of the page at t. Default capture: seek and two rAFs in one round trip, then one CDP
    Page.captureScreenshot (`fast` = optimizeForSpeed: same pixels, bigger file). Whenever
    page.screenshot would do more (CSS animations to freeze, carets, shadow roots, iframes),
    and with --capture screenshot, this is the v0.2 page.screenshot path, so pixels never change."""
    if CAPTURE != "screenshot" and clip is None:
        at = await page.evaluate(SEEK_PLAIN_JS, t)
        cdp = await cdp_session(page) if at is not None else None
        if cdp is not None:
            vp = page.viewport_size
            r = await cdp.send("Page.captureScreenshot", {
                "format": "png", "captureBeyondViewport": False, "optimizeForSpeed": fast,
                "clip": {"x": at[0], "y": at[1], "width": vp["width"], "height": vp["height"], "scale": 1}})
            return base64.b64decode(r["data"])
        return await page.screenshot(type="png", animations="disabled", caret="hide")
    await page.evaluate("t => window.seek(t)", t)
    # two rAFs so layout/paint of the seeked state is committed before capture
    await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    return await page.screenshot(type="png", clip=clip, animations="disabled", caret="hide")


def ffmpeg_cmd(out: Path, fps: int, sub: int, crf: int, audio: Path = None, scale_to=None, loudnorm=True):
    in_rate = fps * sub
    vf = []
    if sub > 1:
        # blend each group of `sub` samples into one output frame
        vf.append(f"tmix=frames={sub}")
        vf.append(f"select='eq(mod(n\\,{sub})\\,{sub - 1})'")
        vf.append(f"setpts=N/({fps}*TB)")
    if scale_to:
        vf.append(f"scale={scale_to[0]}:{scale_to[1]}:flags=lanczos")
    vf.append("format=yuv420p")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(in_rate),
           "-c:v", "png", "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", ",".join(vf), "-r", str(fps), "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if audio:
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        if loudnorm:
            cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    cmd.append(str(out))
    return cmd


def visible_diff(a: bytes, b: bytes):
    """Where two PNG frames differ visibly: more than 8 px off by > 24/255 in some channel (the
    loop-seam tolerance; sub-visible anti-aliasing noise is ignored). -> (count, max, box) or None."""
    import io
    import numpy as np
    from PIL import Image
    ia = np.asarray(Image.open(io.BytesIO(a)).convert("RGB"), dtype=np.int16)
    ib = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), dtype=np.int16)
    if ia.shape != ib.shape:
        return ia.shape[0] * ia.shape[1], 255, (0, ia.shape[1] - 1, 0, ia.shape[0] - 1)
    diff = np.abs(ia - ib).max(axis=2)
    ys, xs = np.nonzero(diff > 24)
    if len(xs) <= 8:
        return None
    return int(len(xs)), int(diff.max()), (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max()))


async def check_determinism(page, D, fps, samples=6):
    """Seek the same times in shuffled order twice; frames must match visibly. Returns
    [(t, n_px, max_diff, (x0, x1, y0, y1))] for every time that differed."""
    rng = random.Random(7)
    ts = sorted({round(rng.uniform(0, D), 4) for _ in range(samples)} | {0.0, round(D / 2, 4)})
    vlog(f"determinism: {len(ts)} times (fixed seed 7, so the same times every run; a pass is evidence, "
         f"not proof{'' if samples > 6 else ': --thorough samples more'})")
    first = {}
    for t in ts:
        first[t] = await snap(page, t)
    shuffled = ts[:]
    random.Random(11).shuffle(shuffled)
    bad = []
    for t in shuffled:
        png = await snap(page, t)
        if hashlib.sha1(png).digest() != hashlib.sha1(first[t]).digest():
            d = visible_diff(first[t], png)
            if d:
                bad.append((t,) + d)
    return sorted(bad)


def thorough(a):
    """--thorough (D.9): denser gate sampling, slower. getattr: older callers' namespaces lack it."""
    return bool(getattr(a, "thorough", False))


def describe_determinism(bad):
    if not bad:
        return "pass"
    worst = max(bad, key=lambda b: b[1])
    t, n, mx, (x0, x1, y0, y1) = worst
    return (f"FAIL at t={[b[0] for b in bad]}: the same t drew different pixels on a second seek. "
            f"Worst t={t}: {n} px differ (max {mx}/255) in box x={x0}-{x1}, y={y0}-{y1}. "
            f"Look there for clock/rAF/random/CSS-transition state, or sub-pixel transforms "
            f"(see gotchas.md).")


async def check_seam(page, D):
    """For loops: picture at t=D must match picture at t=0.
    Returns (status, detail). Float noise (a few pixels off by a few levels, e.g.
    sin(2π) != 0 on the GPU) passes; anything visible fails."""
    a = await snap(page, 0.0)
    b = await snap(page, D)
    if a == b:
        return "pass", "pixel-exact"
    import io
    import numpy as np
    from PIL import Image
    ia = np.asarray(Image.open(io.BytesIO(a)).convert("RGB"), dtype=np.int16)
    ib = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"), dtype=np.int16)
    diff = np.abs(ia - ib).max(axis=2)
    n_vis, mx = int((diff > 24).sum()), int(diff.max())
    if n_vis <= 8:  # isolated AA-edge pixels from float error, not a real discontinuity
        return "pass", f"float noise only: {int((diff > 0).sum())} px changed, {n_vis} above threshold"
    ys, xs = np.nonzero(diff > 24)
    return "FAIL", (f"{n_vis} px visibly differ (max {mx}/255) in box x={xs.min()}-{xs.max()}, "
                    f"y={ys.min()}-{ys.max()} — something isn't periodic (text, counter, rotation, rand?)")


def out_name(stem: str, fmt, suffix: str) -> str:
    """Output file name: <stem>[_<fmt>]<suffix> (C2 naming)."""
    return stem + (f"_{fmt}" if fmt else "") + suffix


def page_url(html: Path, fmt=None) -> str:
    """URL the renderer loads. Without a format: exactly the v0.1 URL."""
    url = serve(html.parent) + html.name + "?render=1"
    if fmt:
        w, h = FORMATS[fmt]
        url += f"&format={fmt}&w={w}&h={h}"
    return url


def poster_time(M, D):
    """C1: MOTION.poster, else 0 for loops, else duration - 0.5."""
    p = M.get("poster")
    if isinstance(p, (int, float)) and not isinstance(p, bool):
        return float(p)
    return 0.0 if M.get("loop") else max(0.0, D - 0.5)


def parse_strip(spec):
    """'A:B:N' -> (A, B, N, 'A-B') with the user's own spelling of A and B for the file name."""
    parts = spec.split(":")
    try:
        if len(parts) != 3:
            raise ValueError
        a, b, n = float(parts[0]), float(parts[1]), int(parts[2])
        if n < 1 or b < a:
            raise ValueError
    except ValueError:
        sys.exit(f"--strip expects A:B:N (start s, end s >= start, N >= 1 stills), got {spec!r}")
    return a, b, n, f"{parts[0]}-{parts[1]}"


async def blurred_snap(page, t, sub, shutter, fps, loopD):
    """PNG at t; with sub > 1, the mean of `sub` samples spread backward across the shutter
    (same sampling as the video render)."""
    if sub <= 1:
        return await snap(page, t)
    import io
    import numpy as np
    from PIL import Image
    acc = None
    for k in range(sub):
        tk = t - (shutter / fps) * (sub - 1 - k) / (sub - 1)
        tk = (tk - loopD * math.floor(tk / loopD)) if loopD else max(0.0, tk)
        im = np.asarray(Image.open(io.BytesIO(await snap(page, tk))).convert("RGB"), dtype=np.float64)
        acc = im if acc is None else acc + im
    buf = io.BytesIO()
    Image.fromarray(np.clip(np.rint(acc / sub), 0, 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


async def sheet_from_times(page, ts, out: Path, tw: int, cols: int, grab=None):
    """Snap each t into a temp folder and tile the PNGs into `out` (no stills left behind)."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="motion-sheet-") as td:
        paths = []
        for i, t in enumerate(ts):
            p = Path(td) / f"{i:04d}.png"
            p.write_bytes(await (grab(t) if grab else snap(page, t)))
            paths.append(p)
        tile_sheet(paths, out, tw=tw, cols=cols)
    return out


async def deliver_sheets(page, D, outdir, stem, fmt):
    """--deliver: the contact sheet and the phone-size sheet (D.4) from one set of 16 stills."""
    import tempfile
    ts = [D * i / 16 for i in range(16)]
    with tempfile.TemporaryDirectory(prefix="motion-sheet-") as td:
        paths = []
        for i, t in enumerate(ts):
            p = Path(td) / f"{i:04d}.png"
            p.write_bytes(await snap(page, t))
            paths.append(p)
        sheet = outdir / out_name(stem, fmt, "_sheet.png")
        phone = outdir / out_name(stem, fmt, "_sheet_phone.png")
        tile_sheet(paths, sheet, tw=480, cols=4)
        tile_sheet(paths, phone, tw=270, cols=4)
    return sheet, phone


def is_review(a):
    return bool(a.stills or a.sheet or a.poster is not None or a.strip or a.phone or a.contact)


async def review(page, a, M, D, fps, stem, fmt, outdir):
    """Review renders (no video): --stills/--sheet (v0.1), --poster, --strip, --phone, --contact beats."""
    if a.stills or a.sheet:
        await review_stills(page, a, D, stem, fmt, outdir)
    W = int(M["width"])
    if a.poster is not None:
        t = poster_time(M, D) if a.poster == "" else float(a.poster)
        out = outdir / out_name(stem, fmt, "_poster.png")
        out.write_bytes(await snap(page, t, fast=False))
        log(f"poster (t={t:.3f}) -> {out}")
    if a.strip:
        t0, t1, n, tag = parse_strip(a.strip)
        ts = [t0] if n == 1 else [t0 + (t1 - t0) * i / (n - 1) for i in range(n)]
        sub = max(1, a.subframes)
        loopD = float(M["duration"]) if M.get("loop") else None
        out = outdir / out_name(stem, fmt, f"_strip_{tag}.png")
        await sheet_from_times(page, ts, out, tw=min(W, 480), cols=n,
                               grab=lambda t: blurred_snap(page, t, sub, a.shutter, fps, loopD))
        log(f"strip ({n} stills, {sub} sample(s) each) -> {out}")
    if a.phone:
        out = outdir / out_name(stem, fmt, "_sheet_phone.png")
        await sheet_from_times(page, [D * i / 16 for i in range(16)], out, tw=270, cols=4)
        log(f"phone-size contact sheet -> {out}")
    if a.contact == "beats":
        beats = await page.evaluate("window.BEATS || null")
        if not beats or not beats.get("downbeats"):
            sys.exit("--contact beats needs window.BEATS with downbeats: run beats.py and add "
                     '<script src="beats.js"></script> before the kit')
        ts = [float(t) for t in beats["downbeats"] if 0 <= float(t) < D]
        if not ts:
            sys.exit(f"--contact beats: no downbeat inside [0, {D}) s")
        out = outdir / out_name(stem, fmt, "_beats_sheet.png")
        await sheet_from_times(page, ts, out, tw=480, cols=min(4, len(ts)))
        log(f"beat contact sheet ({len(ts)} downbeats) -> {out}")


async def review_stills(page, a, D, stem, fmt, outdir):
    """--stills / --sheet: PNG stills and a 4x4 contact sheet (fast review loop)."""
    ts = [float(x) for x in a.stills.split(",")] if a.stills else [D * i / 16 for i in range(16)]
    sdir = outdir if a.stills else outdir / "stills"   # D.2: --sheet alone keeps its stills out of renders/
    sdir.mkdir(exist_ok=True)
    paths = []
    for t in ts:
        p = sdir / out_name(stem, fmt, f"_t{t:07.3f}.png")
        p.write_bytes(await snap(page, t, fast=False))
        paths.append(p)
    log(f"saved {len(paths)} stills -> {sdir}")
    if a.sheet:
        sheet = outdir / out_name(stem, fmt, "_sheet.png")
        tile_sheet(paths, sheet, tw=480, cols=4)
        log(f"contact sheet -> {sheet}")


def tile_sheet(paths, out: Path, tw: int, cols: int):
    """Tile PNGs (scaled to tw px wide) into one image, `cols` per row, 6 px black padding."""
    lst = out.parent / f"_{out.stem}_list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\nduration 1\n" for p in paths))
    rows = (len(paths) + cols - 1) // cols
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", f"scale={tw}:-1,tile={cols}x{rows}:padding=6:color=black",
                        "-frames:v", "1", str(out)], check=True)
    finally:
        lst.unlink()


HITS_JS = """() => {
  const K = window.K;
  if (K && typeof K.resolveHits === 'function') {
    try { return { kit: true, hits: K.resolveHits() }; }
    catch (e) { return { error: String(e && e.message || e) }; }
  }
  return { kit: false, hits: window.MOTION.hits || [] };
}"""


async def dump_hits(page, a, D, fps, stem, fmt, outdir):
    """--hits: resolve MOTION.hits (C3) and write renders/<stem>[_<fmt>]_hits.json. No render."""
    res = await page.evaluate(HITS_JS)
    if "error" in res:
        sys.exit(f"K.resolveHits() failed: {res['error']}")
    hits = []
    for i, h in enumerate(res["hits"] or []):
        if res["kit"]:
            t, label, sfx, opts = h.get("t"), h.get("label"), h.get("sfx"), h.get("opts")
        else:
            if not isinstance(h, list) or len(h) not in (3, 4):
                sys.exit(f"MOTION.hits[{i}] must be [when, label, sfx, opts?], got {json.dumps(h)}")
            t, label, sfx = h[:3]
            opts = h[3] if len(h) == 4 else None
            if isinstance(t, str):
                sys.exit(f"MOTION.hits[{i}] is beat-timed ({t!r}): beat-timed hits need the kit "
                         "(window.K.resolveHits). Load kit.js and beats.js, or use seconds.")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            sys.exit(f"MOTION.hits[{i}]: time must be a number of seconds, got {json.dumps(t)}")
        if opts is not None and not isinstance(opts, dict):
            sys.exit(f"MOTION.hits[{i}]: opts must be an object, got {json.dumps(opts)}")
        hits.append({"t": round(float(t), 6), "label": label, "sfx": sfx, "opts": opts or {}})
    hits.sort(key=lambda h: h["t"])
    data = {"version": 1, "source": a.html.name, "fps": fps, "duration": D, "hits": hits}
    out = outdir / out_name(stem, fmt, "_hits.json")
    out.write_text(json.dumps(data, indent=2))
    log(f"{len(hits)} hit(s) ({'K.resolveHits' if res['kit'] else 'numeric, no kit'}) -> {out}")
    return out


# Shared page helpers for the DOM gates (no screenshots): effective visibility and a short name.
DOM_HELPERS_JS = """
const __vis = (el) => {            // effective opacity, 0 when not rendered
  if (!el.getClientRects().length) return 0;               // display:none (self or ancestor)
  if (getComputedStyle(el).visibility === 'hidden') return 0;
  let o = 1;
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
  return o;
};
const __name = (el) => {
  if (el.id) return '#' + el.id;
  for (const k of ['data-safe', 'data-text']) {
    const v = el.getAttribute(k);
    if (v) return `[${k}="${v}"]`;
  }
  const tag = el.tagName.toLowerCase();
  const sib = el.parentElement ? [...el.parentElement.children].filter(c => c.tagName === el.tagName) : [el];
  const own = tag + (el.classList.length ? '.' + el.classList[0] : '') +
              (sib.length > 1 ? `:nth-of-type(${sib.indexOf(el) + 1})` : '');
  const p = el.parentElement;
  return (p && p.id ? '#' + p.id + ' > ' : '') + own;
};
"""

SAFE_AREA_JS = "async (ts) => {" + DOM_HELPERS_JS + """
  const K = window.K;
  if (!K) return { skip: 'no window.K' };
  const r0 = K.safe && (K.safe.ui || K.safe.title);
  if (!r0) return { skip: 'window.K has no safe rects' };
  const els = [...document.querySelectorAll('[data-safe]')];
  if (!els.length) return { none: true };
  const worst = new Map();
  for (const t of ts) {
    await window.seek(t);
    const R = (K.safe.ui || K.safe.title);
    els.forEach((el, i) => {
      if (__vis(el) <= 0) return;
      const b = el.getBoundingClientRect();
      if (b.width <= 0 || b.height <= 0) return;
      const over = { left: R.x - b.left, top: R.y - b.top,
                     right: b.right - (R.x + R.w), bottom: b.bottom - (R.y + R.h) };
      for (const side in over) {
        const px = Math.round(over[side]);
        const w = worst.get(i);
        if (px >= 1 && (!w || px > w.px)) worst.set(i, { name: __name(el), t, side, px });
      }
    });
  }
  return { fails: [...worst.values()] };
}"""

TEXT_DURATION_JS = "async ({ n, fps, W, H }) => {" + DOM_HELPERS_JS + """
  const els = [...document.querySelectorAll('[data-text]')];
  if (!els.length) return { none: true };
  const seen = els.map(() => []);
  for (let f = 0; f < n; f++) {
    await window.seek(f / fps);
    els.forEach((el, i) => {
      let on = __vis(el) >= 0.9;
      if (on) {
        const b = el.getBoundingClientRect();
        on = b.width > 0 && b.height > 0 && b.right > 0 && b.bottom > 0 && b.left < W && b.top < H;
      }
      seen[i].push(on);
    });
  }
  return { names: els.map(__name), seen };
}"""

MIN_TEXT_FRAMES = 8


def visible_runs(seen, loop):
    """[(start_frame, length)] of consecutive True values; for loops, a run touching both ends wraps."""
    runs, start = [], None
    for i, v in enumerate(seen + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - start))
            start = None
    if loop and len(runs) > 1 and runs[0][0] == 0 and runs[-1][0] + runs[-1][1] == len(seen):
        last = runs.pop()
        runs[0] = (last[0], last[1] + runs[0][1])
    return runs


async def gate_safe_area(page, D, fps):
    """E2.4: every visible [data-safe] element inside K.safe.ui (fallback title) at sampled times."""
    ts = {0.0, max(0.0, D - 1 / fps)}
    k = 0
    while k * 0.25 < D:
        ts.add(round(k * 0.25, 6))
        k += 1
    res = await page.evaluate(SAFE_AREA_JS, sorted(ts))
    if "skip" in res:
        return f"skipped ({res['skip']})"
    if res.get("none"):
        return "pass (no [data-safe] elements)"
    if not res["fails"]:
        return "pass"
    return "FAIL " + "; ".join(f"{f['name']} at t={f['t']:.3f} overflows {f['side']} by {f['px']} px"
                               for f in res["fails"])


async def gate_text_duration(page, D, fps, loop):
    """E5.6 (duration only): each [data-text] element's visible runs last >= 8 frames."""
    W, H = await page.evaluate("[window.MOTION.width, window.MOTION.height]")
    res = await page.evaluate(TEXT_DURATION_JS, {"n": int(round(D * fps)), "fps": fps, "W": W, "H": H})
    if res.get("none"):
        return "pass (no [data-text] elements)"
    short = []
    for name, seen in zip(res["names"], res["seen"]):
        for start, length in visible_runs(seen, loop):
            if length < MIN_TEXT_FRAMES:
                short.append(f"{name} visible for {length} frames at t={start / fps:.3f} (min {MIN_TEXT_FRAMES})")
    if not short:
        return "pass"
    more = f"; … {len(short) - 10} more" if len(short) > 10 else ""
    return "WARN " + "; ".join(short[:10]) + more


# E5.6 contrast: probe the visible [data-text] elements at t (their fill colour, effective opacity and
# the line boxes of their words), then hide only the glyphs so a screenshot shows what's behind them.
CONTRAST_PROBE_JS = "async ({ t, W, H }) => {" + DOM_HELPERS_JS + """
  document.getElementById('__motion_contrast')?.remove();   // read the real colours first
  await window.seek(t);
  const cv = (window.__mcCanvas ||= document.createElement('canvas'));
  cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const rgba = (c) => {              // any CSS colour -> [r, g, b, a] in sRGB 0-255, null if not a colour
    if (!c || c === 'none' || c.startsWith('url(')) return null;
    cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1);
    return [...cx.getImageData(0, 0, 1, 1).data];
  };
  const out = [];
  document.querySelectorAll('[data-text]').forEach((el, i) => {
    const vis = __vis(el);
    if (vis < 0.9) return;
    const cs = getComputedStyle(el);
    const isSvg = el instanceof SVGElement;
    const col = el instanceof HTMLCanvasElement ? null      // canvas/WebGL text: no CSS colour to read
              : rgba(isSvg ? cs.fill : (cs.webkitTextFillColor || cs.color));
    let rects = [];
    if (!isSvg) {
      const r = document.createRange(); r.selectNodeContents(el);
      rects = [...r.getClientRects()];
    }
    if (!rects.length) rects = [el.getBoundingClientRect()];
    rects = rects.map(b => [Math.max(0, b.left), Math.max(0, b.top), Math.min(W, b.right), Math.min(H, b.bottom)])
                 .filter(([x0, y0, x1, y1]) => x1 - x0 >= 1 && y1 - y0 >= 1);
    if (!rects.length) return;
    out.push({ i, name: __name(el), color: col, opacity: vis, rects });
  });
  if (out.length) {
    const s = document.createElement('style');
    s.id = '__motion_contrast';
    s.textContent = '[data-text],[data-text] *{color:transparent!important;-webkit-text-fill-color:transparent!important;' +
                    'fill:transparent!important;text-decoration-color:transparent!important;caret-color:transparent!important}';
    document.head.appendChild(s);
  }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return out;
}"""

CONTRAST_RESTORE_JS = "() => { const s = document.getElementById('__motion_contrast'); if (s) s.remove(); }"

MIN_CONTRAST = 4.5        # WCAG AA for body text
CONTRAST_AREA = 10        # percentile: 90 % of the area behind the words must reach MIN_CONTRAST


def rel_luminance(rgb):
    """WCAG 2.x relative luminance of sRGB values 0-255 (any array shape ending in 3)."""
    import numpy as np
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def text_contrast(color, alpha, bg):
    """Contrast ratio of text `color` (RGB 0-255) at opacity `alpha` over each background pixel in
    `bg` (N x 3) -> the CONTRAST_AREA-th percentile (the ratio 90 % of the area reaches)."""
    import numpy as np
    bg = np.asarray(bg, dtype=np.float64).reshape(-1, 3)
    fg = alpha * np.asarray(color[:3], dtype=np.float64) + (1 - alpha) * bg   # text blended over each pixel
    lf, lb = rel_luminance(fg), rel_luminance(bg)
    ratio = (np.maximum(lf, lb) + 0.05) / (np.minimum(lf, lb) + 0.05)
    return float(np.percentile(ratio, CONTRAST_AREA))


async def gate_contrast(page, D, fps, step=0.25):
    """E5.6 contrast: each visible [data-text] element (opacity >= 0.9) against the rendered pixels
    behind its words, every `step` s. Worst ratio per element; WARN below MIN_CONTRAST."""
    import io
    import numpy as np
    from PIL import Image
    W, H = await page.evaluate("[window.MOTION.width, window.MOTION.height]")
    if not await page.evaluate("document.querySelectorAll('[data-text]').length"):
        return "pass (no [data-text] elements)"
    ts = sorted({round(k * step, 6) for k in range(int(math.ceil(D / step)))} | {max(0.0, D - 1 / fps)})
    worst, unmeasured, checked = {}, set(), 0
    try:
        for t in ts:
            els = await page.evaluate(CONTRAST_PROBE_JS, {"t": t, "W": W, "H": H})
            if not els:
                continue
            x0 = min(r[0] for e in els for r in e["rects"])
            y0 = min(r[1] for e in els for r in e["rects"])
            x1 = max(r[2] for e in els for r in e["rects"])
            y1 = max(r[3] for e in els for r in e["rects"])
            clip = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
            png = await page.screenshot(type="png", clip=clip, animations="disabled", caret="hide")
            img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
            s = img.shape[1] / clip["width"]
            checked += 1
            for e in els:
                if not e["color"] or e["color"][3] == 0:
                    unmeasured.add(e["name"])
                    continue
                px = []
                for rx0, ry0, rx1, ry1 in e["rects"]:
                    a0, a1 = int((rx0 - x0) * s), int(math.ceil((rx1 - x0) * s))
                    b0, b1 = int((ry0 - y0) * s), int(math.ceil((ry1 - y0) * s))
                    px.append(img[b0:b1, a0:a1].reshape(-1, 3))
                bg = np.concatenate(px)
                if len(bg) > 20000:
                    bg = bg[:: len(bg) // 20000]
                if not len(bg):
                    continue
                ratio = text_contrast(e["color"], e["color"][3] / 255 * e["opacity"], bg)
                if e["name"] not in worst or ratio < worst[e["name"]][0]:
                    worst[e["name"]] = (ratio, t)
    finally:
        await page.evaluate(CONTRAST_RESTORE_JS)
    note = (f"; not measured (canvas text, gradient or transparent fill): {', '.join(sorted(unmeasured))}"
            if unmeasured else "")
    if not checked:
        return "pass (no [data-text] element visible at the sampled times)"
    low = sorted((r, t, n) for n, (r, t) in worst.items() if r < MIN_CONTRAST)
    if not low:
        return "pass" + (f" ({note[2:]})" if note else "")
    more = f"; … {len(low) - 10} more" if len(low) > 10 else ""
    return ("WARN " + "; ".join(f"{n} {r:.1f}:1 at t={t:.3f}" for r, t, n in low[:10]) + more
            + f" (min {MIN_CONTRAST}:1 over {100 - CONTRAST_AREA} % of the area behind the words)" + note)


async def run_gates(page, a, M, D, fps, report):
    if a.skip_checks:
        return
    bad = await check_determinism(page, D, fps, samples=max(30, int(D * 4)) if thorough(a) else 6)
    report["gates"]["determinism"] = describe_determinism(bad)
    vlog("gate determinism:", report["gates"]["determinism"])
    if M.get("loop"):
        st, detail = await check_seam(page, float(M["duration"]))
        report["gates"]["loop_seam"] = f"{st} ({detail})"
        vlog("gate loop_seam:", report["gates"]["loop_seam"])
    report["gates"]["safe_area"] = await gate_safe_area(page, D, fps)
    vlog("gate safe_area:", report["gates"]["safe_area"])
    report["gates"]["text_duration"] = await gate_text_duration(page, D, fps, bool(M.get("loop")))
    vlog("gate text_duration:", report["gates"]["text_duration"])
    report["gates"]["contrast"] = await gate_contrast(page, D, fps, step=0.1 if thorough(a) else 0.25)
    vlog("gate contrast:", report["gates"]["contrast"])
    # footage pieces only (window.FOOTAGE / data-cue / data-claim): cue_timing, claim_trace (E12.11)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _footage_gates
    await _footage_gates.run(page, a.html.parent, D, fps, report)
    for k in ("cue_timing", "claim_trace"):
        if k in report["gates"]:
            vlog(f"gate {k}:", report["gates"][k])


def mux_cmd(src, a, out: Path):
    """ffmpeg command: video from the input args `src` (stream copy) plus --audio, if any, -> out."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *src]
    if a.audio:
        cmd += ["-i", str(a.audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        if not a.no_loudnorm:
            cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    else:
        cmd += ["-c", "copy"]
    return cmd + ["-movflags", "+faststart", str(out)]


def count_frames(video: Path):
    """Video frames (packets) in a file, or None without ffprobe."""
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def gate_frame_count(out: Path, n_frames: int, audio):
    """E8.3: the output holds exactly the frames rendered (no duplicated or missing frame at a
    worker boundary). With --audio, -shortest may end the video early: say so, as before."""
    got = count_frames(out)
    if got is None or got == n_frames:
        return
    if audio and got < n_frames:
        log(f"WARN {out.name}: {got} of {n_frames} frames: --audio is shorter than the video (-shortest)")
        return
    sys.exit(f"frame count gate: {out} has {got} frames, expected {n_frames}")


def plan_workers(a, n_frames, fps):
    return max(1, min(a.workers, n_frames // max(fps, 1) or 1))


async def full_render(pw, a, html, fmt, M, D, fps, scale, out, errors, keep=None):
    """Render [start, D) in parallel segments and concatenate. Returns the frame count.
    keep: also write the video-only stream there (E8.4 render cache)."""
    W, H = int(M["width"]), int(M["height"])
    scale_to = (W, H) if scale != 1.0 and not a.preview else None
    n_frames = int(round((D - a.start) * fps))  # export [start, D) — never duplicate the loop endpoint
    sub = max(1, a.subframes)
    loopD = float(M["duration"]) if M.get("loop") else None
    workers = plan_workers(a, n_frames, fps)
    bounds = [round(i * n_frames / workers) for i in range(workers + 1)]
    segdir = out.parent / f".{out.stem}_segments"
    segdir.mkdir(exist_ok=True)
    t_start = time.time()
    done = [0]

    async def work(wi):
        lo, hi = bounds[wi], bounds[wi + 1]
        b, pg, _, errs = await open_page(pw, html, fmt=fmt, scale=scale, gl=a.gl)
        seg = segdir / f"seg{wi:03d}.mp4"
        mode, why = await canvas_path(pg, [a.start + (lo + hi) // 2 / fps, a.start + lo / fps])
        if wi == 0:
            vlog("capture: canvas fast path" if why is None else f"capture: {CAPTURE_LABEL[CAPTURE]}"
                 + (f" (canvas fast path off: {why})" if CAPTURE == "auto" else ""))
        proc = subprocess.Popen(ffmpeg_cmd(seg, fps, sub, a.crf, None, scale_to), stdin=subprocess.PIPE)
        for n in range(lo, hi):
            base = a.start + n / fps
            for k in range(sub):
                # samples spread backward across the shutter so frame n ends at its own time
                off = 0.0 if sub == 1 else -(a.shutter / fps) * (sub - 1 - k) / (sub - 1)
                t = base + off
                t = (t - loopD * math.floor(t / loopD)) if loopD else max(0.0, t)
                png = await canvas_snap(pg, t, mode) if why is None else None
                if png is None and why is None:
                    why = f"the page stopped qualifying at t={t:.3f}"
                    vlog(f"capture: worker {wi} leaves the canvas fast path ({why})")
                proc.stdin.write(png or await snap(pg, t))
            done[0] += 1
            if done[0] % (fps * 2) == 0:
                el = time.time() - t_start
                vlog(f"{done[0]}/{n_frames} frames ({el:.0f}s elapsed, ~{el / done[0] * (n_frames - done[0]):.0f}s left)")
        proc.stdin.close()
        rc = proc.wait()
        await b.close()
        errors.extend(errs)
        if rc != 0:
            raise RuntimeError(f"ffmpeg failed on segment {wi} ({rc})")
        got = count_frames(seg)
        if got is not None and got != hi - lo:  # E8.3 frame-count gate
            raise RuntimeError(f"segment {wi} has {got} frames, expected {hi - lo} (frames {lo}-{hi - 1})")
        return seg

    vlog(f"rendering {n_frames} frames x {sub} samples with {workers} worker(s)")
    segs = await asyncio.gather(*(work(i) for i in range(workers)))
    lst = segdir / "list.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    subprocess.run(mux_cmd(["-f", "concat", "-safe", "0", "-i", str(lst)], a, out), check=True)
    if keep:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(keep)], check=True)
    shutil.rmtree(segdir, ignore_errors=True)
    gate_frame_count(out, n_frames, a.audio)
    log(f"done -> {out}  ({out.stat().st_size / 1e6:.1f} MB, {time.time() - t_start:.0f}s)")
    return n_frames


def note_served(directory: Path, path: str):
    """Record a file the local server hands the page, hashed as served (E8.4)."""
    try:
        rel = Path(path).resolve().relative_to(directory).as_posix()
    except ValueError:
        return
    seen = _SERVED.setdefault(directory, {})
    sha = file_sha(Path(path))
    if seen.setdefault(rel, sha) != sha:
        seen[rel] = "changed during the render"


def note_request(url: str):
    if not url.startswith((*_SERVERS.values(), "data:", "blob:", "about:")):
        _EXTERNAL.append(url)


_SHA = {}


def file_sha(path: Path):
    """sha256 of a file (memoised on mtime and size), of a folder's names, or None if missing."""
    try:
        st = path.stat()
    except OSError:
        return None
    if path.is_dir():
        return "dir:" + hashlib.sha256("\n".join(sorted(os.listdir(path))).encode()).hexdigest()
    k = (str(path), st.st_mtime_ns, st.st_size)
    if k not in _SHA:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _SHA[k] = h.hexdigest()
    return _SHA[k]


def cache_key(a, fmt, M, D, fps, scale, chromium):
    """Everything besides the page's files that decides the video stream (not --audio)."""
    n_frames = int(round((D - a.start) * fps))
    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return {"version": 1, "render.py": file_sha(Path(__file__).resolve()), "chromium": chromium, "ffmpeg": ff,
            "format": fmt, "size": [int(M["width"]), int(M["height"])], "fps": fps, "start": a.start,
            "duration": D, "loop": bool(M.get("loop")), "subframes": max(1, a.subframes), "shutter": a.shutter,
            "crf": a.crf, "scale": scale, "preview": a.preview, "gl": a.gl, "capture": CAPTURE,
            "workers": plan_workers(a, n_frames, fps)}


class RenderCache:
    """E8.4: renders/.cache/<name>.mp4 keeps the last video-only stream of each output, with
    <name>.json: the key (flags, Chromium, ffmpeg, render.py) and the sha256 of every file the
    page fetched. When all of that still matches, the render is skipped and only the audio is
    muxed again, so a rerun after a mix change takes seconds. Renders that fetched anything
    from outside the folder, or had page errors, are not cached. --no-cache skips it."""

    def __init__(self, a, fmt, outdir, key):
        self.root, self.key = a.html.parent.resolve(), key
        d = outdir / ".cache"
        name = out_name(a.html.stem, fmt, "_preview" if a.preview else "")
        self.video, self.meta = d / f"{name}.mp4", d / f"{name}.json"
        self.video_tmp = d / f".{name}.tmp.mp4"
        self.a = a
        d.mkdir(exist_ok=True)

    def reuse(self, out):
        """Mux the cached video (+ --audio) into out and return its frame count, or None (miss)."""
        try:
            m = json.loads(self.meta.read_text())
        except (OSError, ValueError):
            return None
        if m.get("key") != self.key or file_sha(self.video) != m.get("video_sha"):
            return None
        for rel, sha in m["files"].items():
            if file_sha(self.root / rel) != sha:
                vlog(f"cache: {rel} changed, re-rendering")
                return None
        subprocess.run(mux_cmd(["-i", str(self.video)], self.a, out), check=True)
        gate_frame_count(out, m["frames"], self.a.audio)
        log(f"cache hit: page files and flags unchanged since the last render, video reused "
            f"({self.video.name}); --no-cache re-renders -> {out}")
        return m["frames"]

    def store(self, n_frames, errors):
        files = dict(_SERVED.get(self.root, {}))
        bad = (errors and "page errors") or (_EXTERNAL and f"it fetched {_EXTERNAL[0]}") or \
            next((f"{k} {v}" for k, v in files.items() if v == "changed during the render"), None)
        if bad or not self.video_tmp.exists():
            self.video_tmp.unlink(missing_ok=True)
            if bad:
                vlog(f"cache: not storing this render ({bad})")
            return
        os.replace(self.video_tmp, self.video)
        tmp = self.meta.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"key": self.key, "frames": n_frames, "video_sha": file_sha(self.video),
                                   "files": files}, indent=1, sort_keys=True))
        os.replace(tmp, self.meta)


async def render_one_format(pw, a, fmt, outdir):
    """Everything render.py does for one format (fmt=None: native, exactly v0.1).
    Returns the report dict, or None in review-only modes (stills / sheet)."""
    stem = a.html.stem
    scale = 0.5 if a.preview else a.scale
    browser, page, M, errors = await open_page(pw, a.html, fmt=fmt, scale=scale, gl=a.gl)
    fps = a.fps or (30 if a.preview else int(M.get("fps", 60)))
    D = a.duration or float(M["duration"])
    if a.preview:
        D = min(D, a.start + 5.0)
    W, H = int(M["width"]), int(M["height"])
    vlog(f"{a.html.name}{f' [{fmt}]' if fmt else ''}: {W}x{H} @ {fps}fps, {D - a.start:.2f}s, "
        f"loop={M.get('loop', False)}, scale={scale}")
    report = {"file": str(a.html), "width": W, "height": H, "fps": fps, "duration": D, "gates": {}}
    if fmt:
        report["format"] = fmt

    if a.hits:
        await dump_hits(page, a, D, fps, stem, fmt, outdir)
        await browser.close()
        return None

    # ---- review renders (fast loop, no video) ----
    if is_review(a):
        await review(page, a, M, D, fps, stem, fmt, outdir)
        await browser.close()
        if errors:
            log("PAGE ERRORS:\n  " + "\n  ".join(errors[:20]))
        return None

    # ---- gates ----
    await run_gates(page, a, M, D, fps, report)
    if a.check_only:
        report["gates"]["page_errors"] = errors or "none"
        await browser.close()
        return report

    # ---- full render ----
    deliver = None
    if a.deliver:  # poster + contact sheet from this page before it closes
        poster = outdir / out_name(stem, fmt, "_poster.png")
        poster.write_bytes(await snap(page, poster_time(M, D), fast=False))
        sheet, phone = await deliver_sheets(page, D, outdir, stem, fmt)
        deliver = {"format": fmt or "native", "poster": poster, "sheet": sheet, "sheet_phone": phone}
    if a.out:
        # one format: -o is used as given; several: each gets its _<fmt> suffix
        out = a.out if len(a.formats) <= 1 else a.out.with_name(out_name(a.out.stem, fmt, a.out.suffix))
    else:
        out = outdir / out_name(stem, fmt, ("_preview" if a.preview else "") + ".mp4")
    chromium = browser.version
    await browser.close()
    cache = None if a.no_cache else RenderCache(a, fmt, outdir, cache_key(a, fmt, M, D, fps, scale, chromium))
    n_frames = cache.reuse(out) if cache else None
    if n_frames is None:
        n_frames = await full_render(pw, a, a.html, fmt, M, D, fps, scale, out, errors,
                                     keep=cache and cache.video_tmp)
        if cache:
            cache.store(n_frames, errors)
    report["output"] = str(out)
    report["frames"] = n_frames
    report["gates"]["page_errors"] = errors or "none"
    if errors:
        log("PAGE ERRORS (fix these):\n  " + "\n  ".join(errors[:20]))
    (outdir / (out.stem + "_report.json")).write_text(json.dumps(report, indent=2))
    if deliver is not None:
        deliver["video"] = out
        a.delivered.append(deliver)
    return report


def ffprobe_facts(video: Path) -> dict:
    """duration, fps, width, height, pix_fmt, audio, size_bytes of a rendered file (E2.5)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height,pix_fmt,r_frame_rate",
                        "-of", "json", str(video)], capture_output=True, text=True, check=True)
    info = json.loads(r.stdout)
    streams = info.get("streams", [])
    v = next(st for st in streams if st.get("codec_type") == "video")
    num, _, den = v.get("r_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"duration": round(float(info["format"]["duration"]), 3),
            "fps": int(fps) if fps.is_integer() else round(fps, 3),
            "width": int(v["width"]), "height": int(v["height"]), "pix_fmt": v.get("pix_fmt"),
            "audio": any(st.get("codec_type") == "audio" for st in streams),
            "size_bytes": video.stat().st_size}


def write_deliver(a, outdir: Path):
    """renders/deliver.json (C8): one item per rendered format, paths relative to the project."""
    root = a.html.parent.resolve()
    rel = lambda p: Path(os.path.relpath(Path(p).resolve(), root)).as_posix()
    items = []
    for d in a.delivered:
        items.append({"format": d["format"], "video": rel(d["video"]), "poster": rel(d["poster"]),
                      "sheet": rel(d["sheet"]), "sheet_phone": rel(d["sheet_phone"]),
                      **ffprobe_facts(Path(d["video"]))})
    out = outdir / "deliver.json"
    out.write_text(json.dumps({"version": 1, "source": a.html.name, "items": items}, indent=2))
    log(f"delivery bundle ({len(items)} format(s)) -> {out}")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", type=Path, help="the composition (window.MOTION / ready / seek)")
    ap.add_argument("-o", "--out", type=Path, help="output MP4 (default renders/<stem>[_<fmt>].mp4)")
    ap.add_argument("--fps", type=int, help="override MOTION.fps")
    ap.add_argument("--duration", type=float, help="override MOTION.duration (s); handy for quick tests")
    ap.add_argument("--start", type=float, default=0.0, help="first time to render (s, default 0)")
    ap.add_argument("--subframes", type=int, default=1, help="motion-blur samples per frame (1=off, 3-8 typical)")
    ap.add_argument("--shutter", type=float, default=0.5, help="fraction of a frame the blur spans (default 0.5 = 180°)")
    ap.add_argument("--crf", type=int, default=16, help="x264 quality, lower = better/larger (default 16)")
    ap.add_argument("--scale", type=float, default=1.0, help="device scale factor (2 = supersample, downscaled on encode)")
    ap.add_argument("--audio", type=Path, help="mux this track (loudness-normalised to -14 LUFS); for SFX use mix.py")
    ap.add_argument("--no-loudnorm", action="store_true", help="mux --audio as-is")
    ap.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 2)),
                    help="parallel headless browsers, each rendering whole frames [lo, hi) "
                         "(default: the CPU count, max 6; at most one per second of video)")
    ap.add_argument("--gl", action="store_true", help="enable SwiftShader WebGL (Three.js / shaders) in headless")
    ap.add_argument("--capture", choices=["auto", "cdp", "screenshot"], default="auto",
                    help="frame capture: auto = CDP screenshots, plus the canvas fast path when the page is one "
                         "opaque <canvas> (checked against a screenshot); cdp = CDP screenshots only; "
                         "screenshot = the v0.2 path. Pixels are the same in every mode")
    ap.add_argument("--preview", action="store_true", help="quick test: first 5 s, half resolution, 30 fps")
    ap.add_argument("--stills", help="comma-separated times (s) to save as PNG")
    ap.add_argument("--sheet", action="store_true", help="save a 4x4 contact sheet of evenly spaced stills")
    ap.add_argument("--check-only", action="store_true",
                    help="gates only, no video: determinism (8 fixed times from seed 7, re-seeked shuffled), "
                         "loop_seam, safe_area (every 0.25 s), text_duration (every frame), contrast "
                         "(every 0.25 s), page errors. A pass is evidence, not proof: only those times are seen")
    ap.add_argument("--thorough", action="store_true",
                    help="denser gates (slower): determinism at max(30, 4 per s) times, contrast every 0.1 s")
    ap.add_argument("--skip-checks", action="store_true", help="skip the gates before a full render")
    ap.add_argument("--no-cache", action="store_true",
                    help="always render, and don't keep renders/.cache/ (by default a full render whose page "
                         "files and flags are unchanged reuses the last video and only re-muxes --audio)")
    ap.add_argument("--quiet", action="store_true",
                    help="print only results (output paths, errors, the JSON report): fewer tokens for agents")
    ap.add_argument("--format", metavar="LIST",
                    help="comma-separated formats to render in turn: " + ", ".join(FORMATS)
                    + " (default: native MOTION size, no suffix)")
    ap.add_argument("--deliver", action="store_true",
                    help="full render of every format plus a poster, contact sheet and phone sheet each, "
                         "and renders/deliver.json")
    ap.add_argument("--hits", action="store_true",
                    help="write renders/<stem>_hits.json from MOTION.hits (C3) and exit; no render")
    ap.add_argument("--poster", nargs="?", const="", metavar="T",
                    help="save one PNG at T s (default MOTION.poster, else 0 for loops, else duration - 0.5)")
    ap.add_argument("--strip", metavar="A:B:N",
                    help="N stills evenly spaced from A to B s, in one row (with --subframes: motion-blurred)")
    ap.add_argument("--phone", action="store_true", help="contact sheet at phone size (270 px tiles, 4 columns)")
    ap.add_argument("--contact", choices=["beats"], help="'beats': one still per downbeat of window.BEATS")
    return ap


# flags --hits refuses (it only combines with --format)
HITS_CONFLICTS = ("out", "audio", "preview", "stills", "sheet", "check_only", "poster", "strip", "phone", "contact",
                  "deliver")

# review / check modes that skip the full render, so --deliver refuses them
DELIVER_CONFLICTS = ("stills", "sheet", "check_only", "poster", "strip", "phone", "contact")


def parse_formats(spec):
    """'9x16,1x1' -> ['9x16', '1x1'] (order kept, duplicates dropped). None -> []."""
    if spec is None:
        return []
    names = []
    for n in (x.strip() for x in spec.split(",")):
        if n not in FORMATS:
            sys.exit(f"unknown format {n!r}; valid formats: {', '.join(FORMATS)}")
        if n not in names:
            names.append(n)
    if not names:
        sys.exit(f"--format needs at least one of: {', '.join(FORMATS)}")
    return names


async def main():
    a = build_parser().parse_args()
    global QUIET, CAPTURE
    QUIET, CAPTURE = a.quiet, a.capture
    a.formats = parse_formats(a.format)
    if a.strip:
        parse_strip(a.strip)  # fail fast on a bad spec
    if a.poster not in (None, ""):
        try:
            float(a.poster)
        except ValueError:
            sys.exit(f"--poster expects a time in seconds, got {a.poster!r}")
    a.delivered = []
    if a.deliver:
        bad = ["--" + k.replace("_", "-") for k in DELIVER_CONFLICTS if getattr(a, k, None) not in (None, False)]
        if bad:
            sys.exit(f"--deliver does a full render; it doesn't combine with {' '.join(bad)}")
    if a.hits:
        bad = ["--" + k.replace("_", "-") for k in HITS_CONFLICTS if getattr(a, k, None) not in (None, False)]
        if bad:
            sys.exit(f"--hits only combines with --format (got {' '.join(bad)})")
    if not a.html.exists():
        sys.exit(f"not found: {a.html}")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    outdir = a.html.parent / "renders"
    outdir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        if not a.formats:  # v0.1 path: native size, no suffix, one report object
            report = await render_one_format(pw, a, None, outdir)
            if a.check_only:
                print(json.dumps(report, indent=2))
            if a.deliver:
                write_deliver(a, outdir)
            return
        reports = {}
        for fmt in a.formats:
            reports[fmt] = await render_one_format(pw, a, fmt, outdir)
        if a.check_only:
            print(json.dumps({"formats": reports}, indent=2))
        if a.deliver:
            write_deliver(a, outdir)


if __name__ == "__main__":
    asyncio.run(main())
