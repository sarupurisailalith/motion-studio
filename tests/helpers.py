"""Shared test helpers for Motion Studio.

Run everything:   python3 -m unittest discover -s tests -v     (or tests/run.sh)
Skip slow tests:  MOTION_FAST=1 python3 -m unittest discover -s tests -v
"""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "motion-video"
SCRIPTS = SKILL / "scripts"
TEMPLATES = SKILL / "templates"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

FAST = os.environ.get("MOTION_FAST") == "1"


def run_script(name, *args, cwd=None, timeout=600):
    """Run SCRIPTS/<name> with this Python. Never raises on a non-zero exit."""
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout)


def tmpdir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="motion-test-"))
    if os.environ.get("MOTION_KEEP_TMP") != "1":
        import atexit
        atexit.register(shutil.rmtree, d, ignore_errors=True)
    return d


def copy_fixture(rel, dst_dir) -> Path:
    """Copy a file or folder from tests/fixtures (or an absolute path) into dst_dir."""
    src = Path(rel) if Path(rel).is_absolute() else FIXTURES / rel
    dst = Path(dst_dir) / src.name
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return dst


def parse_report(stdout: str) -> dict:
    """The JSON object a script prints after its log lines (render.py, check.py)."""
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("{"):
            return json.loads("\n".join(lines[i:]))
    raise ValueError("no JSON report in output:\n" + stdout[-2000:])


def _has_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


HAS_CHROMIUM = _has_chromium()
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

slow = unittest.skipIf(FAST, "slow test (MOTION_FAST=1)")
needs_chromium = unittest.skipUnless(HAS_CHROMIUM, "playwright chromium not installed")
needs_ffmpeg = unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not on PATH")
