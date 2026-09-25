#!/usr/bin/env python3
"""Build the skill roster from disk and measure the baseline cost.

Baseline = what Hermes injects every turn: name + description for every skill.
Also measures the cost of loading one full skill (SKILL.md).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path.home() / ".hermes" / "skills"
OUT = Path(__file__).resolve().parent / "skill_roster.json"


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    fm = m.group(1)
    out = {}
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+?)(?=\n[A-Za-z_]+:|\Z)", fm, re.DOTALL | re.MULTILINE)
        if km:
            val = km.group(1).strip().strip('"').strip("'")
            out[key] = " ".join(val.split())
    return out


def main() -> int:
    roster = []
    for p in sorted(ROOT.rglob("SKILL.md")):
        if ".archive" in p.parts:
            continue  # archived skills are not injected into the prompt
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        fm = parse_frontmatter(text)
        rel = p.relative_to(ROOT)
        parts = rel.parts
        category = parts[0] if len(parts) > 2 else ""
        roster.append({
            "skill": fm.get("name") or parts[-2],
            "description": fm.get("description", ""),
            "category": category,
            "path": str(p),
            "skill_md_chars": len(text),
            "desc_chars": len(fm.get("description", "")),
        })

    with_desc = [r for r in roster if r["description"]]
    roster_chars = sum(len(r["skill"]) + len(r["description"]) + 4 for r in with_desc)
    skill_md_chars = sum(r["skill_md_chars"] for r in roster)
    avg_skill_md = skill_md_chars / len(roster) if roster else 0

    print(f"skills total:            {len(roster)}")
    print(f"skills with description: {len(with_desc)}")
    print()
    print(f"BASELINE roster (name+desc, every turn):")
    print(f"  chars: {roster_chars:,}   ~tokens (chars/4): {roster_chars//4:,}")
    print()
    print(f"FULL skill load (one SKILL.md):")
    print(f"  total chars: {skill_md_chars:,}   ~tokens: {skill_md_chars//4:,}")
    print(f"  avg per skill: {avg_skill_md:,.0f} chars  ~{avg_skill_md/4:,.0f} tokens")
    print()

    # category rollup
    cats: dict[str, int] = {}
    for r in with_desc:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    top = sorted(cats.items(), key=lambda kv: -kv[1])[:20]
    print("top categories (by skill count):")
    for c, n in top:
        print(f"  {c or '(root)':28s} {n}")

    OUT.write_text(json.dumps(roster, indent=1))
    print(f"\nwrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
