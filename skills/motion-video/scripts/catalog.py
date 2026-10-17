#!/usr/bin/env python3
"""
catalog.py — the Zdog model catalog (E11): search it, copy models into a project, build a
turntable page for one model, and (re)generate the preview stills.

Usage:
  python3 catalog.py list [--kind character|prop|icon|scene-kit] [--tag tree] [--json]
  python3 catalog.py search <words…>          # ranked matches on id, tags, kind and notes
  python3 catalog.py use <project_dir> <id…>  # copy models/<id>.js + kit-zdog.js into the project
  python3 catalog.py turntable <id> <dir>     # <dir>/<id>_turntable.html (+ kit, model, vendor/ zdog)
  python3 catalog.py previews [<id…>] [--size 256] [--sheet out.png]
                                              # render catalog/<id>.png (needs network once for zdog)

The catalog is SKILL_DIR/catalog/catalog.json; models live in catalog/models/<id>.js and follow
the K.Z.model convention (references/zdog.md). Search the catalog before modelling anything new.
"""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CAT = SKILL / "catalog"
TEMPLATES = SKILL / "templates"


def load():
    return json.loads((CAT / "catalog.json").read_text())


def entry(cat, mid):
    for e in cat["models"]:
        if e["id"] == mid:
            return e
    sys.exit(f"no model {mid!r} in the catalog; have: {', '.join(e['id'] for e in cat['models'])}")


def show(rows, as_json):
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    for e in rows:
        joints = " rig" if e.get("joints") else ""
        print(f"{e['id']:<16} {e['kind']:<10} {', '.join(e['tags'])}{joints}  — {e['notes']}")


def score(e, words):
    hay = {"id": e["id"].lower(), "kind": e["kind"].lower(), "tags": " ".join(e["tags"]).lower(),
           "notes": e["notes"].lower()}
    s = 0
    for w in words:
        w = w.lower()
        s += 5 * (w == hay["id"]) + 3 * (w in hay["id"]) + 3 * (w in hay["tags"].split()) \
            + 2 * (w in hay["tags"]) + 2 * (w == hay["kind"]) + (w in hay["notes"])
    return s


def copy_kit(dst: Path):
    for f in ("kit.js", "kit-zdog.js"):
        if not (dst / f).exists() or f == "kit-zdog.js":
            shutil.copy2(TEMPLATES / f, dst / f)


def use(proj: Path, ids):
    cat = load()
    (proj / "models").mkdir(parents=True, exist_ok=True)
    for mid in ids:
        entry(cat, mid)
        shutil.copy2(CAT / "models" / f"{mid}.js", proj / "models" / f"{mid}.js")
        print("copied", proj / "models" / f"{mid}.js")
    copy_kit(proj)
    print("load after kit-zdog.js: " + " ".join(f'<script src="models/{m}.js"></script>' for m in ids))


def turntable(mid, d: Path, vendor=None):
    entry(load(), mid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "models").mkdir(exist_ok=True)
    shutil.copy2(CAT / "models" / f"{mid}.js", d / "models" / f"{mid}.js")
    copy_kit(d)
    src = (CAT / "turntable.html").read_text()
    old = "const MODEL = new URLSearchParams(location.search).get('model') || 'pip';"
    assert old in src, "turntable.html: MODEL line changed"
    html = d / f"{mid}_turntable.html"
    html.write_text(src.replace(old, f"const MODEL = new URLSearchParams(location.search).get('model') || {json.dumps(mid)};"))
    if vendor:
        shutil.copytree(vendor, d / "vendor", dirs_exist_ok=True)
    elif not (d / "vendor" / "zdog.dist.min.js").exists():
        r = subprocess.run([sys.executable, str(HERE / "vendor.py"), str(d), "zdog"], capture_output=True, text=True)
        if r.returncode:
            sys.exit("vendor.py zdog failed (needs npm and the network once):\n" + r.stderr[-800:])
    print("turntable", html)
    return html


def previews(ids, size, sheet):
    """Render one 3/4-view still per model at `size` px, palette-quantised to stay small."""
    from PIL import Image
    cat = load()
    ids = ids or [e["id"] for e in cat["models"]]
    with tempfile.TemporaryDirectory(prefix="motion-catalog-") as td:
        td = Path(td)
        vend = None
        made = []
        for mid in ids:
            d = td / mid
            html = turntable(mid, d, vendor=vend)
            vend = vend or d / "vendor"
            r = subprocess.run([sys.executable, str(HERE / "render.py"), str(html), "--stills", "0", "--quiet"],
                               capture_output=True, text=True)
            pngs = sorted((d / "renders").glob("*_t*.png"))
            if r.returncode or not pngs:
                sys.exit(f"render.py failed for {mid}:\n{r.stdout[-600:]}\n{r.stderr[-600:]}")
            im = Image.open(pngs[0]).convert("RGB").resize((size, size), Image.LANCZOS)
            out = CAT / f"{mid}.png"
            im.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)
            made.append(out)
            print(f"preview {out} ({out.stat().st_size // 1024} KB)")
        if sheet:
            cols = min(5, len(made))
            rows = (len(made) + cols - 1) // cols
            S = Image.new("RGB", (cols * size, rows * size), "black")
            for i, p in enumerate(made):
                S.paste(Image.open(p).convert("RGB"), ((i % cols) * size, (i // cols) * size))
            S.save(sheet, optimize=True)
            print("sheet", sheet)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--kind"); p.add_argument("--tag"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("search"); p.add_argument("words", nargs="+"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("use"); p.add_argument("project", type=Path); p.add_argument("ids", nargs="+")
    p = sub.add_parser("turntable"); p.add_argument("id"); p.add_argument("dir", type=Path)
    p = sub.add_parser("previews"); p.add_argument("ids", nargs="*"); p.add_argument("--size", type=int, default=256)
    p.add_argument("--sheet", type=Path, help="also write a contact sheet of every preview")
    a = ap.parse_args()
    if a.cmd == "list":
        rows = [e for e in load()["models"] if (not a.kind or e["kind"] == a.kind) and (not a.tag or a.tag in e["tags"])]
        show(rows, a.json)
    elif a.cmd == "search":
        ranked = sorted(((score(e, a.words), e) for e in load()["models"]), key=lambda x: -x[0])
        rows = [e for s, e in ranked if s > 0]
        if not rows and not a.json:
            print("no catalog match: model it new (references/zdog.md), and propose it for the catalog if it works")
        show(rows, a.json)
    elif a.cmd == "use":
        use(a.project, a.ids)
    elif a.cmd == "turntable":
        turntable(a.id, a.dir)
    elif a.cmd == "previews":
        previews(a.ids, a.size, a.sheet)


if __name__ == "__main__":
    main()
