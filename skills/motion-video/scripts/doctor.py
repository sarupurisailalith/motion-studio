#!/usr/bin/env python3
"""
doctor.py — check what Motion Studio needs and print the exact commands to install anything missing.
It only looks: it never installs, downloads or changes anything.

Usage:
  python3 doctor.py           # human-readable report; exit 1 if a required piece is missing
  python3 doctor.py --json    # the same as JSON {ok, required:[…], optional:[…], install:[…]}

Required: Python >= 3.8, playwright (+ its Chromium build), numpy, Pillow, ffmpeg and ffprobe.
Optional: npm (vendor.py: three / gsap / lottie), librosa (beats.py tempo),
          pypdf or pdftotext (brand.py reads brand-guide PDFs).
"""
import argparse, importlib.util, json, platform, shutil, sys
from pathlib import Path

PY = Path(sys.executable).name if sys.executable else "python3"


def has_module(name):
    return importlib.util.find_spec(name) is not None


def chromium_path():
    """Path of the Playwright Chromium build, or None. Starts the Playwright driver; downloads nothing."""
    if not has_module("playwright"):
        return None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = Path(p.chromium.executable_path)
            return str(path) if path.exists() else None
    except Exception:
        return None


def system_install(tool):
    """The package-manager line for a system tool on this OS."""
    osname = platform.system()
    names = {"ffmpeg": ("ffmpeg", "ffmpeg", "Gyan.FFmpeg"), "npm": ("node", "nodejs npm", "OpenJS.NodeJS.LTS"),
             "pdftotext": ("poppler", "poppler-utils", None)}[tool]
    if osname == "Darwin":
        return f"brew install {names[0]}"
    if osname == "Windows":
        return f"winget install {names[2]}" if names[2] else f"install {tool} (see its website)"
    return f"sudo apt install {names[1]}   (or your distro's package manager)"


def checks():
    pip = f"{PY} -m pip install"
    req, opt = [], []

    def add(lst, name, ok, fix, detail=""):
        lst.append({"name": name, "ok": bool(ok), "fix": None if ok else fix, "detail": detail})

    add(req, "python>=3.8", sys.version_info >= (3, 8), "install Python 3.8 or newer", platform.python_version())
    for mod, pkg in (("playwright", "playwright"), ("numpy", "numpy"), ("PIL", "pillow")):
        add(req, pkg, has_module(mod), f"{pip} {pkg}")
    chrome = chromium_path()
    add(req, "chromium (playwright)", chrome, f"{PY} -m playwright install chromium", chrome or "")
    for tool in ("ffmpeg", "ffprobe"):
        add(req, tool, shutil.which(tool), system_install("ffmpeg"), shutil.which(tool) or "")

    add(opt, "npm", shutil.which("npm"), system_install("npm"), "vendor.py (three / gsap / lottie)")
    add(opt, "librosa", has_module("librosa"), f"{pip} librosa", "beats.py tempo estimate (numpy fallback otherwise)")
    pdf = has_module("pypdf") or shutil.which("pdftotext")
    add(opt, "pypdf or pdftotext", pdf, f"{pip} pypdf", "brand.py reads brand-guide PDFs")
    return req, opt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    a = ap.parse_args()
    req, opt = checks()
    ok = all(c["ok"] for c in req)
    install = []
    for c in req:   # one command per fix, in a working order (pip before playwright install)
        if c["fix"] and c["fix"] not in install:
            install.append(c["fix"])
    pips = [c["fix"].split(" install ", 1)[1] for c in req if c["fix"] and " -m pip install " in c["fix"]]
    if len(pips) > 1:   # merge the pip lines into one
        install = [f"{PY} -m pip install {' '.join(pips)}"] + [i for i in install if " -m pip install " not in i]
    if any(c["name"] == "playwright" and not c["ok"] for c in req):
        line = f"{PY} -m playwright install chromium"
        install = [i for i in install if i != line] + [line]   # needs the package first
    if a.json:
        print(json.dumps({"ok": ok, "required": req, "optional": opt, "install": install}, indent=2))
    else:
        for title, lst in (("required", req), ("optional", opt)):
            print(f"{title}:")
            for c in lst:
                mark = "ok " if c["ok"] else ("MISSING" if title == "required" else "-- not installed")
                extra = f"  ({c['detail']})" if c["detail"] else ""
                print(f"  {mark:16s} {c['name']}{extra}" + ("" if c["ok"] else f"\n                   -> {c['fix']}"))
        if ok:
            print("\nReady: everything required is installed.")
        else:
            print("\nMissing required pieces. Run, then re-run doctor.py:")
            for line in install:
                print("  " + line)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
