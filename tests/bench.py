#!/usr/bin/env python3
"""bench.py — render-speed baseline (E0.3). Not part of unittest discovery.

Renders the 2D template (6 s, 1080x1080, 60 fps = 360 frames) in several modes, and the Three.js
template with --gl when three.js can be vendored, then writes docs/perf.md (a markdown table
with the date and machine info). Renders skip the gates (--skip-checks); the gates are timed
separately with --check-only.

Usage:
  python3 tests/bench.py                 # all modes -> docs/perf.md
  python3 tests/bench.py --dry-run       # print the table, don't write docs/perf.md
  python3 tests/bench.py --modes plain-w1,check-only
"""
import argparse, datetime, json, os, platform, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: E402

MODES = [  # name, template, extra args, subframes
    ("plain-w1", "2d", ["--workers", "1"], 1),
    ("plain-w2", "2d", ["--workers", "2"], 1),
    ("plain-w4", "2d", ["--workers", "4"], 1),
    ("subframes3-w4", "2d", ["--subframes", "3", "--workers", "4"], 3),
    ("check-only", "2d", ["--check-only"], 1),
    ("check-only-4fmt", "2d", ["--check-only", "--format", "16x9,9x16,1x1,4x5"], 1),
    ("three-gl-w2", "three", ["--gl", "--workers", "2"], 1),
]


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
        return d / ("composition.html" if kind == "2d" else "three-composition.html")
    d.mkdir(parents=True)
    shutil.copy2(helpers.TEMPLATES / "kit.js", d)
    if kind == "2d":
        return Path(shutil.copy2(helpers.TEMPLATES / "composition.html", d))
    html = Path(shutil.copy2(helpers.TEMPLATES / "three-composition.html", d))
    v = helpers.run_script("vendor.py", d, "three", timeout=300)
    if v.returncode != 0 or not (d / "vendor" / "three.module.js").exists():
        return None
    return html


def run(name, kind, args, sub, root):
    html = project(kind, root)
    if html is None:
        return {"mode": name, "skipped": "could not vendor three.js"}
    M = {"2d": (6.0, 60, "1080x1080"), "three": (8.0, 30, "1920x1080")}[kind]
    frames = int(round(M[0] * M[1]))
    full = "--check-only" not in args
    cmd = [str(html), *args] + (["--skip-checks", "-o", str(root / f"{name}.mp4")] if full else [])
    t0 = time.perf_counter()
    r = helpers.run_script("render.py", *cmd, timeout=3600)
    wall = time.perf_counter() - t0
    if r.returncode != 0:
        return {"mode": name, "skipped": "render failed: " + r.stderr.strip()[-300:]}
    out = {"mode": name, "template": kind, "size": M[2], "fps": M[1], "duration": M[0], "frames": frames,
           "args": " ".join(args), "wall_s": round(wall, 1)}
    if full:
        out["frames_per_s"] = round(frames / wall, 1)
        out["samples_per_s"] = round(frames * sub / wall, 1)
    return out


def table(rows, info):
    today = datetime.date.today().isoformat()
    L = ["# Performance baseline (E0.3)", "",
         f"Measured {today} with `python3 tests/bench.py`. Wall time includes Chromium start-up, page load,",
         "the ffmpeg encode and concatenation of worker segments. Full renders use `--skip-checks`; the gates",
         "are timed on their own (`--check-only`). frames/s = output frames / wall time; samples/s counts",
         "every sub-frame screenshot.", "",
         "## Machine", ""]
    L += [f"- **{k}**: {v}" for k, v in info.items()]
    L += ["", "## Results", "",
          "| mode | template | size @ fps | frames | flags | wall (s) | frames/s | samples/s |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "skipped" in r:
            L.append(f"| {r['mode']} | — | — | — | — | skipped: {r['skipped']} | — | — |")
            continue
        L.append(f"| {r['mode']} | {r['template']} | {r['size']} @ {r['fps']} | {r['frames']} | `{r['args']}` | "
                 f"{r['wall_s']} | {r.get('frames_per_s', '—')} | {r.get('samples_per_s', '—')} |")
    L += ["", "## Notes", "",
          "- `check-only` runs determinism, loop seam, safe_area and text_duration. text_duration seeks every",
          "  frame (360 seeks here), so it grows linearly with duration × fps.",
          "- These numbers are the baseline for the E8 performance work (canvas fast path, CDP capture,",
          "  smarter workers). Re-run on the same machine to compare.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modes", help="comma-separated subset of: " + ", ".join(m[0] for m in MODES))
    ap.add_argument("--dry-run", action="store_true", help="print the table; don't write docs/perf.md")
    a = ap.parse_args()
    want = set(a.modes.split(",")) if a.modes else None
    root = Path(tempfile.mkdtemp(prefix="motion-bench-"))
    rows = []
    try:
        for name, kind, args, sub in MODES:
            if want and name not in want:
                continue
            log(f"{name} …")
            rows.append(run(name, kind, args, sub, root))
            log(json.dumps(rows[-1]))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    md = table(rows, machine())
    if a.dry_run:
        print(md)
    else:
        out = helpers.ROOT / "docs" / "perf.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md)
        log(f"-> {out}")


if __name__ == "__main__":
    main()
