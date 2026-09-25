#!/usr/bin/env python3
"""Measure stage-2 quality (recall@1/@3) and token cost; compare to baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage2_router import route, INDEX  # noqa: E402

BASELINE_ROSTER_TOKENS = 0
try:
    _roster = json.loads((Path(__file__).resolve().parent / "skill_roster.json").read_text())
    BASELINE_ROSTER_TOKENS = sum(
        len(r["skill"]) + len(r["description"]) + 4 for r in _roster if r["description"]
    ) // 4
except Exception:
    BASELINE_ROSTER_TOKENS = 16641

# (request, expected_domain, expected_skill) — only cases where both are unambiguous
LABELED = [
    ("Caveman lite on, lets safely proceed with the - /home/sak/hermes-graphics/hermes-graphics-fix-plan-v1.md", "devops_infra", "hermes-graphics"),
    ("Lets append this doc to google docs and share the link - /home/sak/hermes-graphics/hermes-graphics-fix-plan-v1.md", "integration_mcp", "composio-google-docs"),
    ("Create a lean hermes-graphics-fix-plan-v1.md first and use it as guide, create the plan first, dont act yet", "devops_infra", "plan"),
    ("based on this skill : access-shbg-dxi/, sop-audit rewrite the following sop accurately, since it belongs to a different analyzer, i want it to be rewritten for DXI specifically", "lab_clinical", "sop-platform-migration"),
    ("Can you access the hermes plugins masterplace", "hermes_dev", "hermes-agent"),
    ("Lets explore - browser/, web/, teams_pipeline/, spotify/memory , observability/ , and hindsight, babysitter, and skill factory plugins", "hermes_dev", "hermes-agent"),
    ("i want you to go deeper into each SOP, and find more stuff that could clearly be improved, be smart about it, lets begin with 1 - ALBUMIN", "lab_clinical", "sop-auditor"),
    ("use book-to-skill to create detailed highly token efficient skill and subskills for the following important pdf - iso15189:2022", "hermes_dev", "book-to-skill"),
    ("i want you to allow selecting an image or video from grid or list view, and it directly opens in reel view first, so that we can scroll from that point onwards", "devops_infra", "hermes-graphics"),
    ("Upload these images to Google Drive", "integration_mcp", "composio-mcp"),
    ("Query the vdc collection for everything on the SHBG assay", "rag_data", "qdrant-rag"),
]


def main() -> int:
    r1 = r3 = dom_ok = 0
    tot_tokens = tot_cost = 0.0
    rows = []
    for req, exp_dom, exp_skill in LABELED:
        res = route(req)
        top3 = [s for s, _ in res.get("top3", [])]
        hit1 = res.get("skill") == exp_skill
        hit3 = exp_skill in top3
        dok = res.get("domain") == exp_dom
        r1 += hit1
        r3 += hit3
        dom_ok += dok
        tot_tokens += res.get("tokens", 0)
        tot_cost += res.get("cost", 0) or 0
        rows.append((req, exp_dom, exp_skill, res, hit1, hit3, dok))

    n = len(LABELED)
    print(f"STAGE 2 TEST — {n} labeled requests\n")
    for req, ed, es, res, h1, h3, dok in rows:
        m = "OK " if h1 else ("T3 " if h3 else "MISS")
        print(f"[{m}] {req[:58]}")
        print(f"      dom {res['domain']:15s}{'ok' if dok else 'MISS'}  ->  skill={res['skill']}  (want {es})")
        if not h1:
            print(f"      top3: {[s for s,_ in res.get('top3',[])]}")
    print()
    print(f"domain correct : {dom_ok}/{n}")
    print(f"skill recall@1 : {r1}/{n}  ({r1/n*100:.0f}%)")
    print(f"skill recall@3 : {r3}/{n}  ({r3/n*100:.0f}%)")
    print()
    print("TOKEN / COST COMPARISON (per selection)")
    print(f"  baseline roster injected per turn : {BASELINE_ROSTER_TOKENS:>7,} tokens")
    print(f"  router (stage1+stage2) per route  : {tot_tokens/n:>7,.0f} tokens")
    print(f"  router saving per turn            : {BASELINE_ROSTER_TOKENS - tot_tokens/n:>7,.0f} tokens  ({(1 - (tot_tokens/n)/BASELINE_ROSTER_TOKENS)*100:.0f}% less)")
    print(f"  router cost per route             : ${tot_cost/n:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
