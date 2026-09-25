#!/usr/bin/env python3
"""Classify every skill into a domain with Jev, once, and save the index.

Batches BATCH skills per request: the state lists the skills numbered, and one
choice question per skill picks from the same 12-domain criteria.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "skills" / "openrouter-jev" / "scripts"))
from jev_client import ask_jev, JevError  # noqa: E402

SCRATCH = Path(__file__).resolve().parent
ROSTER = json.loads((SCRATCH / "skill_roster.json").read_text())
ROUTER_Q = json.loads((SCRATCH / "skill_router.json").read_text())
CRITERIA = ROUTER_Q["domain"]["criteria"]
OUT = SCRATCH / "skill_domains.json"

BATCH = 10
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main() -> int:
    skills = [r for r in ROSTER if r["description"]]
    if LIMIT:
        skills = skills[:LIMIT]

    labels: dict[str, str] = {}
    answered = 0
    probs_log = []
    t0 = time.time()

    for group in chunks(skills, BATCH):
        lines = []
        for i, r in enumerate(group, 1):
            desc = " ".join(r["description"].split())[:200]
            lines.append(f"{i}. {r['skill']} — {desc}")
        state = {"skills": "\n".join(lines)}

        qs = {}
        for i, r in enumerate(group, 1):
            qs[f"s{i}"] = {
                "type": "choice",
                "instructions": f"Which domain best fits skill {i} in `skills`?",
                "criteria": CRITERIA,
            }
        try:
            body = ask_jev(state, qs)
        except JevError as e:
            print(f"  batch failed: {e}")
            continue

        for i, r in enumerate(group, 1):
            a = body["answers"].get(f"s{i}")
            if not a:
                continue
            labels[r["skill"]] = a["choice"]
            answered += 1
            probs_log.append((r["skill"], a["choice"], a.get("confidence", 0)))

    OUT.write_text(json.dumps(labels, indent=1, sort_keys=True))
    dist: dict[str, int] = {}
    for d in labels.values():
        dist[d] = dist.get(d, 0) + 1

    print(f"classified {answered}/{len(skills)} skills in {time.time()-t0:.1f}s")
    print(f"\ndistribution:")
    for d, n in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"  {d:18s} {n:3d}")
    low = [p for p in probs_log if p[2] < 0.6]
    print(f"\nlow-confidence (<0.6): {len(low)}")
    for sk, d, c in low[:15]:
        print(f"  {c:.2f}  {sk[:40]:42s} -> {d}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
