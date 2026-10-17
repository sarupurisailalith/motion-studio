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


_VENDOR_CACHE = {}


def vendored(*names) -> Path:
    """A vendor/ folder holding the named vendor.py packages (zdog, p5, ...), downloaded once per
    test run into a temp dir. Raises unittest.SkipTest (with the reason) when npm or the
    network is unavailable, so offline runs skip these tests cleanly."""
    key = tuple(sorted(names))
    if key not in _VENDOR_CACHE:
        if not shutil.which("npm"):
            _VENDOR_CACHE[key] = unittest.SkipTest("npm not on PATH: can't vendor " + ", ".join(key))
        else:
            d = tmpdir()
            try:
                r = run_script("vendor.py", d, *key, timeout=300)
                ok = r.returncode == 0
            except subprocess.TimeoutExpired:
                ok, r = False, None
            missing = not ok or not (d / "vendor" / "vendor.json").exists()
            _VENDOR_CACHE[key] = (unittest.SkipTest(
                f"vendor.py {' '.join(key)} failed (offline?): " + ((r.stderr or r.stdout)[-300:] if r else "timeout"))
                if missing else d / "vendor")
    v = _VENDOR_CACHE[key]
    if isinstance(v, unittest.SkipTest):
        raise v
    return v


def with_vendor(dst_dir, *names) -> Path:
    """Copy vendored(*names) into dst_dir/vendor (skips the calling test when offline)."""
    src = vendored(*names)
    shutil.copytree(src, Path(dst_dir) / "vendor", dirs_exist_ok=True)
    return Path(dst_dir) / "vendor"


def find_ttf():
    """Any local TrueType font (test fixtures that call loadFont / Zfont need one), or None."""
    for d in ["/System/Library/Fonts/Supplemental", "/Library/Fonts", "/usr/share/fonts",
              "/usr/local/share/fonts", str(Path.home() / "Library/Fonts"), "C:/Windows/Fonts"]:
        p = Path(d)
        if p.is_dir():
            for f in sorted(p.rglob("*.ttf")):
                return f
    return None
