#!/usr/bin/env python3
"""Check that every SKILL.md, command and agent file starts with YAML frontmatter that has the
keys Claude Code reads (skills/agents: name + description; commands: description).

Usage: python3 tests/frontmatter.py      (exit 1 and a list of problems on failure; CI runs it)
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"skills/*/SKILL.md": ("name", "description"),
            "agents/*.md": ("name", "description"),
            "commands/*.md": ("description",)}


def problems(root=ROOT):
    out = []
    for pattern, keys in REQUIRED.items():
        for f in sorted(root.glob(pattern)):
            m = re.match(r"---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)
            rel = f.relative_to(root)
            if not m:
                out.append(f"{rel}: no frontmatter (--- block at the top)")
                continue
            fields = dict(re.findall(r"^([A-Za-z_-]+):[ \t]*(.*)$", m.group(1), re.M))
            out += [f"{rel}: frontmatter has no non-empty '{k}'" for k in keys if not fields.get(k, "").strip()]
    if not any(root.glob("skills/*/SKILL.md")):
        out.append("no skills/*/SKILL.md found")
    return out


if __name__ == "__main__":
    bad = problems()
    print("\n".join(bad) or "frontmatter ok")
    sys.exit(1 if bad else 0)
