#!/usr/bin/env python3
"""
vendor.py — copy browser builds of common animation libraries next to a composition,
so renders never touch the network.

Usage: python3 vendor.py <project_dir> three gsap [lottie] [zdog] [p5] [p5-webgpu]
Creates <project_dir>/vendor/{three.module.js, three-addons/..., gsap.min.js, zdog.dist.min.js,
zfont.min.js, p5.min.js, ...}, each package's licence files under vendor/LICENSES/<package>/,
and vendor/vendor.json (package versions + sha256 of every vendored file).
Needs npm (uses a throwaway temp dir). Downloads the pinned versions in NPM from the npm registry.

Licences: zdog and zfont are MIT; p5.js is LGPL-2.1, so it is only ever downloaded into your
project as the unmodified upstream file with its licence next to it. Never inline or modify it.
"""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

# name -> [(file inside the npm package, vendored name)]. The package is the first spec in
# NPM[name], unless the source is written "<package>:<path>".
PKGS = {
    "three": [("build/three.module.js", "three.module.js"),      # imports ./three.core.js
              ("build/three.core.js", "three.core.js"),
              ("examples/jsm", "three-addons")],
    "gsap": [("dist/gsap.min.js", "gsap.min.js"),
             ("dist/CustomEase.min.js", "CustomEase.min.js"),
             ("dist/MotionPathPlugin.min.js", "MotionPathPlugin.min.js")],
    "lottie": [("build/player/lottie.min.js", "lottie.min.js")],
    "zdog": [("dist/zdog.dist.min.js", "zdog.dist.min.js"),
             ("zfont:dist/zfont.min.js", "zfont.min.js")],         # Zfont: text for Zdog (bundles typr.js)
    "p5": [("lib/p5.min.js", "p5.min.js")],
    "p5-webgpu": [("lib/p5.webgpu.min.js", "p5.webgpu.min.js")],   # optional add-on, load after p5.min.js
}
# Exact versions: the install never resolves a range, so every vendored build is reproducible.
NPM = {"three": ["three@0.186.1"], "gsap": ["gsap@3.15.0"], "lottie": ["lottie-web@5.13.0"],
       "zdog": ["zdog@1.1.3", "zfont@1.2.8"], "p5": ["p5@2.3.4"], "p5-webgpu": ["p5@2.3.4"]}
# Licence files copied to vendor/LICENSES/<package>/: whichever of these each package ships.
# zdog's npm package has no LICENSE file; its licence is the "license": "MIT" field of
# package.json and the "Licensed MIT" line of its README, so those two are kept for it.
LICENSE_FILES = ["LICENSE", "LICENSE.md", "LICENSE.txt"]   # matched case-insensitively
EXTRA_LICENSE_FILES = {"zdog": ["package.json", "README.md"]}
BUNDLED = {"zfont": ["typr.js"]}   # zfont.min.js bundles typr.js (MIT): keep its licence too


def pkg_name(spec):
    return spec.rsplit("@", 1)[0]


def sha256(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    proj = Path(sys.argv[1]); want = sys.argv[2:]
    bad = [w for w in want if w not in NPM]
    if bad:
        sys.exit(f"unknown package(s) {', '.join(bad)}; choose from: {', '.join(NPM)}")
    specs = list(dict.fromkeys(s for w in want for s in NPM[w]))
    vend = proj / "vendor"; vend.mkdir(parents=True, exist_ok=True)
    manifest_path = vend / "vendor.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        manifest = {"version": 1, "packages": {}, "files": {}}
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["npm", "init", "-y"], cwd=td, check=True, capture_output=True)
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--prefer-offline", *specs], cwd=td, check=True)
        mods = Path(td) / "node_modules"
        for w in want:
            for src, dst in PKGS[w]:
                pkg, _, path = src.rpartition(":")
                s, d = mods / (pkg or pkg_name(NPM[w][0])) / path, vend / dst
                if not s.exists():
                    continue
                if s.is_dir():
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
                    manifest["files"][dst] = sha256(d)
                print("vendored", d)
        for name in dict.fromkeys(n for s in specs for n in [pkg_name(s), *BUNDLED.get(pkg_name(s), [])]):
            root = mods / name
            if not (root / "package.json").exists():
                continue
            manifest["packages"][name] = json.loads((root / "package.json").read_text()).get("version")
            keep = {n.lower() for n in LICENSE_FILES + EXTRA_LICENSE_FILES.get(name, [])}
            for f in sorted(root.iterdir()):   # real names (case-insensitive file systems agree)
                if f.is_file() and f.name.lower() in keep:
                    out = vend / "LICENSES" / name / f.name
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, out)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("manifest", manifest_path)


if __name__ == "__main__":
    main()
