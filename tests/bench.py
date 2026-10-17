#!/usr/bin/env python3
"""bench.py — render-speed benchmark (E0.3 baseline, E8 results). Not part of unittest discovery.

Renders the 2D template (6 s, 1080x1080, 60 fps = 360 frames) in several modes, a one-canvas 2D
page (tests/fixtures/perf/canvas2d.html, same size and length) and the Three.js template with
--gl when three.js can be vendored, then writes the results table into docs/perf.md (between the
bench markers when they exist, else the whole file). Renders skip the gates (--skip-checks) and
the render cache (--no-cache) unless the mode measures it; the gates are timed with --check-only.
Modes ending in -v02 use --capture screenshot, the v0.2 capture path, for comparison.

Usage:
  python3 tests/bench.py                 # all modes -> docs/perf.md
  python3 tests/bench.py --dry-run       # print the table, don't write docs/perf.md
  python3 tests/bench.py --modes plain-w1,check-only
"""
import argparse, datetime, json, os, platform, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

V02 = ["--capture", "screenshot"]
MODES = [  # name, template, extra args, subframes
    ("plain-w1-v02", "2d", ["--workers", "1", *V02], 1),
    ("plain-w1", "2d", ["--workers", "1"], 1),
    ("plain-w2", "2d", ["--workers", "2"], 1),
    ("plain-w4-v02", "2d", ["--workers", "4", *V02], 1),
    ("plain-w4", "2d", ["--workers", "4"], 1),
    ("plain-default", "2d", [], 1),
    ("subframes3-w4", "2d", ["--subframes", "3", "--workers", "4"], 3),
    ("canvas-w1-v02", "canvas", ["--format", "1x1", "--workers", "1", *V02], 1),
    ("canvas-w1-cdp", "canvas", ["--format", "1x1", "--workers", "1", "--capture", "cdp"], 1),
    ("canvas-w1", "canvas", ["--format", "1x1", "--workers", "1"], 1),
    ("check-only-v02", "2d", ["--check-only", *V02], 1),
    ("check-only", "2d", ["--check-only"], 1),
    ("check-only-4fmt", "2d", ["--check-only", "--format", "16x9,9x16,1x1,4x5"], 1),
    ("three-gl-w2-v02", "three", ["--gl", "--workers", "2", *V02], 1),
    ("three-gl-w2-cdp", "three", ["--gl", "--workers", "2", "--capture", "cdp"], 1),
    ("three-gl-w2", "three", ["--gl", "--workers", "2"], 1),
    ("three-gl-default", "three", ["--gl"], 1),
    ("rerun-audio-only", "2d", ["--audio", "b.wav"], 1),   # after a render with a.wav: the cache hit
]
# modes timed after an untimed first render (same flags, other audio)
PREP = {"rerun-audio-only": ["--audio", "a.wav"]}


def log(*a):
    print("[bench]", *a, file=sys.stderr, flush=True)


def machine():
    cpu = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        r = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True)
        cpu = r.stdout.strip() or cpu
    mem = ""
    try:
        if sys.platform == "darwin":
            mem = f"{int(subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True).stdout) / 2**30:.0f} GB"
        else:
            mem = f"{os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30:.0f} GB"
    except (ValueError, OSError):
        pass
    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            chrome = b.version
            b.close()
    except Exception as e:  # pragma: no cover
        chrome = f"unavailable ({e})"
    return {"os": f"{platform.system()} {platform.release()} ({platform.machine()})", "cpu": cpu,
            "cores": os.cpu_count(), "memory": mem, "python": platform.python_version(),
            "chromium": chrome, "ffmpeg": re.sub(r" Copyright.*", "", ff)}


def project(kind, root):
    d = root / kind
    if d.exists():
        return d / {"2d": "composition.html", "canvas": "canvas2d.html", "three": "three-composition.html"}[kind]
    d.mkdir(parents=True)
    shutil.copy2(helpers.TEMPLATES / "kit.js", d)
    if kind == "2d":
        for name, hz in (("a.wav", 440), ("b.wav", 660)):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration=6",
                            "-ac", "2", str(d / name)], check=True)
        return Path(shutil.copy2(helpers.TEMPLATES / "composition.html", d))
    if kind == "canvas":  # --format 1x1 sizes it 1080x1080; 6 s at 60 fps like the 2D template
        html = d / "canvas2d.html"
        html.write_text((helpers.FIXTURES / "perf" / "canvas2d.html").read_text()
                        .replace("fps: 30, duration: 1", "fps: 60, duration: 6"))
        return html
    html = Path(shutil.copy2(helpers.TEMPLATES / "three-composition.html", d))
    v = helpers.run_script("vendor.py", d, "three", timeout=300)
    if v.returncode != 0 or not (d / "vendor" / "three.module.js").exists():
        return None
    return html


def run(name, kind, args, sub, root):
    html = project(kind, root)
    if html is None:
        return {"mode": name, "skipped": "could not vendor three.js"}
    M = {"2d": (6.0, 60, "1080x1080"), "canvas": (6.0, 60, "1080x1080"), "three": (8.0, 30, "1920x1080")}[kind]
    frames = int(round(M[0] * M[1]))
    full = "--check-only" not in args
    args = [str(html.parent / x) if x.endswith(".wav") else x for x in args]
    tail = ["--skip-checks", "-o", str(root / f"{name}.mp4")] + ([] if name in PREP else ["--no-cache"])
    if name in PREP:
        prep = [str(html.parent / x) if x.endswith(".wav") else x for x in PREP[name]]
        helpers.run_script("render.py", str(html), *prep, *tail, timeout=3600)
    cmd = [str(html), *args] + (tail if full else [])
    t0 = time.perf_counter()
    r = helpers.run_script("render.py", *cmd, timeout=3600)
    wall = time.perf_counter() - t0
    if r.returncode != 0:
        return {"mode": name, "skipped": "render failed: " + r.stderr.strip()[-300:]}
    shown = " ".join(Path(x).name if x.endswith(".wav") else x for x in args)
    out = {"mode": name, "template": kind, "size": M[2], "fps": M[1], "duration": M[0], "frames": frames,
           "args": shown, "wall_s": round(wall, 1)}
    if full:
        out["frames_per_s"] = round(frames / wall, 1)
        out["samples_per_s"] = round(frames * sub / wall, 1)
    return out


def table(rows, info, repeat):
    today = datetime.date.today().isoformat()
    L = [f"Measured {today} with `python3 tests/bench.py" + (f" --repeat {repeat}" if repeat > 1 else "") + "`. "
         "Wall time includes Chromium start-up,",
         "page load, the ffmpeg encode and concatenation of worker segments"
         + (f"; the median of {repeat} runs (all runs in brackets)" if repeat > 1 else "") + ". "
         "load = 1-min load average when the mode started.", "",
         "Machine: " + ", ".join(f"{k} {v}" for k, v in info.items()), "",
         "| mode | template | size @ fps | frames | flags | wall (s) | frames/s | samples/s | load |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "skipped" in r:
            L.append(f"| {r['mode']} | — | — | — | — | skipped: {r['skipped']} | — | — | — |")
            continue
        runs = f" [{', '.join(str(w) for w in r['runs'])}]" if len(r.get("runs", [])) > 1 else ""
        L.append(f"| {r['mode']} | {r['template']} | {r['size']} @ {r['fps']} | {r['frames']} | `{r['args']}` | "
                 f"{r['wall_s']}{runs} | {r.get('frames_per_s', '—')} | {r.get('samples_per_s', '—')} | {r['load']} |")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", help="comma-separated subset of: " + ", ".join(m[0] for m in MODES))
    ap.add_argument("--dry-run", action="store_true", help="print the table; don't write docs/perf.md")
    ap.add_argument("--repeat", type=int, default=1, help="run each mode N times (interleaved) and report the median")
    a = ap.parse_args()
    want = set(a.modes.split(",")) if a.modes else None
    root = Path(tempfile.mkdtemp(prefix="motion-bench-"))
    modes = [m for m in MODES if not want or m[0] in want]
    runs = {m[0]: [] for m in modes}
    try:
        for i in range(a.repeat):
            for name, kind, args, sub in modes:
                log(f"{name} ({i + 1}/{a.repeat}) …")
                load = round(os.getloadavg()[0], 1)
                r = run(name, kind, args, sub, root)
                r["load"] = load
                runs[name].append(r)
                log(json.dumps(r))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    rows = []
    for name, rs in runs.items():
        ok = [r for r in rs if "skipped" not in r]
        if not ok:
            rows.append(rs[0])
            continue
        med = sorted(ok, key=lambda r: r["wall_s"])[len(ok) // 2]
        rows.append(dict(med, runs=[r["wall_s"] for r in ok]))
    md = table(rows, machine(), a.repeat)
    if a.dry_run:
        print(md)
        return
    out = helpers.ROOT / "docs" / "perf.md"
    old = out.read_text() if out.exists() else ""
    start, end = "<!-- bench:start -->", "<!-- bench:end -->"
    if start in old and end in old:  # keep the hand-written parts of docs/perf.md
        md = old[:old.index(start) + len(start)] + "\n" + md + "\n" + old[old.index(end):]
    out.parent.mkdir(exist_ok=True)
    out.write_text(md)
    log(f"-> {out}")


if __name__ == "__main__":
    main()
