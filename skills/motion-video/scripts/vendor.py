#!/usr/bin/env python3
"""
vendor.py — copy browser builds of common animation libraries next to a composition,
so renders never touch the network.

Usage: python3 vendor.py <project_dir> three gsap [lottie]
Creates <project_dir>/vendor/{three.module.js, three-addons/..., gsap.min.js, ...}
Needs npm (uses a throwaway temp dir).
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path

PKGS = {
    "three": [("build/three.module.js", "three.module.js"),      # imports ./three.core.js
              ("build/three.core.js", "three.core.js"),
              ("examples/jsm", "three-addons")],
    "gsap": [("dist/gsap.min.js", "gsap.min.js"),
             ("dist/CustomEase.min.js", "CustomEase.min.js"),
             ("dist/MotionPathPlugin.min.js", "MotionPathPlugin.min.js")],
    "lottie": [("build/player/lottie.min.js", "lottie.min.js")],
}
NPM = {"three": "three", "gsap": "gsap", "lottie": "lottie-web"}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    proj = Path(sys.argv[1]); want = sys.argv[2:]
    vend = proj / "vendor"; vend.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["npm", "init", "-y"], cwd=td, check=True, capture_output=True)
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", *[NPM[w] for w in want]], cwd=td, check=True)
        for w in want:
            root = Path(td) / "node_modules" / NPM[w]
            for src, dst in PKGS[w]:
                s, d = root / src, vend / dst
                if not s.exists():
                    continue
                if s.is_dir():
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
                print("vendored", d)


if __name__ == "__main__":
    main()
