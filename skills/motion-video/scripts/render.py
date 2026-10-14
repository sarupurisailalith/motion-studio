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
  python3 render.py comp.html --sheet                 # contact sheet of 16 evenly spaced stills
  python3 render.py comp.html --subframes 4           # motion blur (4 samples / frame)
  python3 render.py comp.html --audio track.wav       # mux audio (+ loudnorm to -14 LUFS)
  python3 render.py comp.html --check-only            # determinism + loop-seam gates, no video
  python3 render.py comp.html --workers 4             # parallel render (default: half the CPUs, max 4)

Requires: pip install playwright && python3 -m playwright install chromium ; ffmpeg on PATH.
"""
import argparse, asyncio, hashlib, json, math, os, random, shutil, subprocess, sys, time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("playwright missing: pip install playwright && python3 -m playwright install chromium")


def log(*a):
    print("[render]", *a, flush=True)


_SERVERS = {}


def serve(directory: Path) -> str:
    """Serve the composition folder over http://127.0.0.1 (ES modules, fetch and
    video seeking do not work from file://). One server per folder, reused."""
    import functools, http.server, threading
    directory = directory.resolve()
    if directory not in _SERVERS:
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        handler = functools.partial(Quiet, directory=str(directory))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _SERVERS[directory] = f"http://127.0.0.1:{srv.server_address[1]}/"
    return _SERVERS[directory]


async def open_page(pw, html: Path, width=None, height=None, scale=1.0, gl=False):
    args = ["--hide-scrollbars", "--force-color-profile=srgb", "--disable-lcd-text",
            "--font-render-hinting=none", "--autoplay-policy=no-user-gesture-required"]
    if gl:
        args += ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    browser = await pw.chromium.launch(args=args)
    # first open at a provisional size to read MOTION, then resize precisely
    ctx = await browser.new_context(viewport={"width": width or 1080, "height": height or 1080},
                                    device_scale_factor=scale)
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url}"))
    url = serve(html.parent) + html.name + "?render=1"
    await page.goto(url, wait_until="load")
    try:
        await page.wait_for_function("window.MOTION && window.seek && window.ready", timeout=30000)
    except Exception:
        sys.exit("composition never exposed window.MOTION / window.seek / window.ready.\n  "
                 + "\n  ".join(errors[:20] or ["(no page errors captured)"]))
    await page.evaluate("window.ready")
    motion = await page.evaluate("window.MOTION")
    W, H = int(width or motion["width"]), int(height or motion["height"])
    await page.set_viewport_size({"width": int(motion["width"]), "height": int(motion["height"])})
    return browser, page, motion, errors


async def snap(page, t: float, clip=None) -> bytes:
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


async def check_determinism(page, D, fps, samples=6):
    """Seek the same times in shuffled order twice; hashes must match."""
    ts = sorted({round(random.Random(7).uniform(0, D), 4) for _ in range(samples)} | {0.0, round(D / 2, 4)})
    first = {}
    for t in ts:
        first[t] = hashlib.sha1(await snap(page, t)).hexdigest()
    shuffled = ts[:]
    random.Random(11).shuffle(shuffled)
    bad = []
    for t in shuffled:
        h = hashlib.sha1(await snap(page, t)).hexdigest()
        if h != first[t]:
            bad.append(t)
    return bad


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


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--fps", type=int)
    ap.add_argument("--duration", type=float)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--subframes", type=int, default=1, help="motion-blur samples per frame (1=off, 3-8 typical)")
    ap.add_argument("--shutter", type=float, default=0.5, help="fraction of a frame the blur spans (0.5 = 180°)")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--scale", type=float, default=1.0, help="device scale factor (2 = supersample, downscaled on encode)")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)),
                    help="parallel headless browsers (segments are concatenated)")
    ap.add_argument("--gl", action="store_true", help="enable SwiftShader WebGL (Three.js / shaders) in headless")
    ap.add_argument("--preview", action="store_true", help="quick test: first 5 s, half resolution, 30 fps")
    ap.add_argument("--stills", help="comma-separated times (s) to save as PNG")
    ap.add_argument("--sheet", action="store_true", help="save a 4x4 contact sheet of evenly spaced stills")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--skip-checks", action="store_true")
    a = ap.parse_args()

    if not a.html.exists():
        sys.exit(f"not found: {a.html}")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    stem = a.html.with_suffix("")
    outdir = a.html.parent / "renders"
    outdir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        scale = 0.5 if a.preview else a.scale
        browser, page, M, errors = await open_page(pw, a.html, scale=scale, gl=a.gl)
        fps = a.fps or (30 if a.preview else int(M.get("fps", 60)))
        D = a.duration or float(M["duration"])
        if a.preview:
            D = min(D, a.start + 5.0)
        W, H = int(M["width"]), int(M["height"])
        log(f"{a.html.name}: {W}x{H} @ {fps}fps, {D - a.start:.2f}s, loop={M.get('loop', False)}, scale={scale}")
        report = {"file": str(a.html), "width": W, "height": H, "fps": fps, "duration": D, "gates": {}}

        # ---- stills / contact sheet (fast review loop) ----
        if a.stills or a.sheet:
            ts = [float(x) for x in a.stills.split(",")] if a.stills else [D * i / 16 for i in range(16)]
            paths = []
            for t in ts:
                p = outdir / f"{stem.name}_t{t:07.3f}.png"
                p.write_bytes(await snap(page, t))
                paths.append(p)
            log(f"saved {len(paths)} stills -> {outdir}")
            if a.sheet:
                sheet = outdir / f"{stem.name}_sheet.png"
                tw = 480
                lst = outdir / "_sheet_list.txt"
                lst.write_text("".join(f"file '{p.resolve()}'\nduration 1\n" for p in paths))
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                                "-vf", f"scale={tw}:-1,tile=4x{(len(paths) + 3) // 4}:padding=6:color=black",
                                "-frames:v", "1", str(sheet)], check=True)
                lst.unlink()
                log(f"contact sheet -> {sheet}")
            await browser.close()
            if errors:
                log("PAGE ERRORS:\n  " + "\n  ".join(errors[:20]))
            return

        # ---- gates ----
        if not a.skip_checks:
            bad = await check_determinism(page, D, fps)
            report["gates"]["determinism"] = "pass" if not bad else f"FAIL at t={bad}"
            log("gate determinism:", report["gates"]["determinism"])
            if M.get("loop"):
                st, detail = await check_seam(page, float(M["duration"]))
                report["gates"]["loop_seam"] = f"{st} ({detail})"
                log("gate loop_seam:", report["gates"]["loop_seam"])
        if a.check_only:
            report["gates"]["page_errors"] = errors or "none"
            print(json.dumps(report, indent=2))
            await browser.close()
            return

        # ---- full render ----
        out = a.out or (outdir / (stem.name + ("_preview" if a.preview else "") + ".mp4"))
        scale_to = (W, H) if scale != 1.0 and not a.preview else None
        await browser.close()
        n_frames = int(round((D - a.start) * fps))  # export [start, D) — never duplicate the loop endpoint
        sub = max(1, a.subframes)
        loopD = float(M["duration"]) if M.get("loop") else None
        workers = max(1, min(a.workers, n_frames // max(fps, 1) or 1))
        bounds = [round(i * n_frames / workers) for i in range(workers + 1)]
        segdir = outdir / f".{stem.name}_segments"
        segdir.mkdir(exist_ok=True)
        t_start = time.time()
        done = [0]

        async def work(wi):
            lo, hi = bounds[wi], bounds[wi + 1]
            b, pg, _, errs = await open_page(pw, a.html, scale=scale, gl=a.gl)
            seg = segdir / f"seg{wi:03d}.mp4"
            proc = subprocess.Popen(ffmpeg_cmd(seg, fps, sub, a.crf, None, scale_to), stdin=subprocess.PIPE)
            for n in range(lo, hi):
                base = a.start + n / fps
                for k in range(sub):
                    # samples spread backward across the shutter so frame n ends at its own time
                    off = 0.0 if sub == 1 else -(a.shutter / fps) * (sub - 1 - k) / (sub - 1)
                    t = base + off
                    t = (t - loopD * math.floor(t / loopD)) if loopD else max(0.0, t)
                    proc.stdin.write(await snap(pg, t))
                done[0] += 1
                if done[0] % (fps * 2) == 0:
                    el = time.time() - t_start
                    log(f"{done[0]}/{n_frames} frames ({el:.0f}s elapsed, ~{el / done[0] * (n_frames - done[0]):.0f}s left)")
            proc.stdin.close()
            rc = proc.wait()
            await b.close()
            errors.extend(errs)
            if rc != 0:
                raise RuntimeError(f"ffmpeg failed on segment {wi} ({rc})")
            return seg

        log(f"rendering {n_frames} frames x {sub} samples with {workers} worker(s)")
        segs = await asyncio.gather(*(work(i) for i in range(workers)))
        lst = segdir / "list.txt"
        lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
        cat = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
        if a.audio:
            cat += ["-i", str(a.audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest"]
            if not a.no_loudnorm:
                cat += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
        else:
            cat += ["-c", "copy"]
        cat += ["-movflags", "+faststart", str(out)]
        subprocess.run(cat, check=True)
        shutil.rmtree(segdir, ignore_errors=True)
        report["output"] = str(out)
        report["frames"] = n_frames
        report["gates"]["page_errors"] = errors or "none"
        log(f"done -> {out}  ({out.stat().st_size / 1e6:.1f} MB, {time.time() - t_start:.0f}s)")
        if errors:
            log("PAGE ERRORS (fix these):\n  " + "\n  ".join(errors[:20]))
        (outdir / (out.stem + "_report.json")).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
