#!/usr/bin/env python3
"""Real-traffic test for the skill router.

Requests are verbatim user messages recovered from session history
(default profile, 2026-09-24 .. 2026-09-25). Ground truth is hand-labelled.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "skills" / "openrouter-jev" / "scripts"))
from jev_client import ask_jev, JevError  # noqa: E402

QUESTIONS = json.loads((Path(__file__).resolve().parent / "skill_router.json").read_text())

# (request, expected_domain, note)
REAL = [
    ("Caveman lite on, lets safely proceed with the - /home/sak/hermes-graphics/hermes-graphics-fix-plan-v1.md", "devops_infra", "execute a code fix plan"),
    ("Lets append this doc to google docs and share the link - /home/sak/hermes-graphics/hermes-graphics-fix-plan-v1.md", "integration_mcp", "Google Docs write"),
    ("Can you access claude-obsidian.onrender.com mcp, check our skills", "integration_mcp", "MCP access"),
    ("Create a lean hermes-graphics-fix-plan-v1.md first and use it as guide, create the plan first, dont act yet", "devops_infra", "ARGUABLE: planning a file"),
    # ("Yes add it as well to the plan", ...)  <- fragment, no standalone domain signal; excluded
    ("based on this skill : access-shbg-dxi/, sop-audit rewrite the following sop accurately, since it belongs to a different analyzer, i want it to be rewritten for DXI specifically", "lab_clinical", "SOP platform rewrite"),
    ("Can you access the hermes plugins masterplace", "hermes_dev", "Hermes internals"),
    ("Lets explore - browser/, web/, teams_pipeline/, spotify/memory , observability/ , and hindsight, babysitter, and skill factory plugins", "hermes_dev", "Hermes plugin survey"),
    ("i want you to go deeper into each SOP, and find more stuff that could clearly be improved, be smart about it, lets begin with 1 - ALBUMIN", "lab_clinical", "SOP deep audit"),
    ("Use loop engineering skill to figure the answer to the following: is this machine which I am buying at 1.3 lakhs an actual investment or a sink of my money?", "none", "decision/reasoning"),
    ("I want you to get the top 10 GitHub repost today. I want you to do this quick.", "research", "web trend scan"),
    ("use book-to-skill to create detailed highly token efficient skill and subskills for the following important pdf - iso15189:2022", "hermes_dev", "skill authoring from PDF"),
    ("i want you to allow selecting an image or video from grid or list view, and it directly opens in reel view first, so that we can scroll from that point onwards", "devops_infra", "app feature change"),
    ("Lets convert the repo to private", "integration_mcp", "ARGUABLE: GitHub account op"),
    ("Upload these images to Google Drive", "integration_mcp", "Drive upload"),
    ("Query the vdc collection for everything on the SHBG assay", "rag_data", "RAG query"),
    ("How can i figure out about my personality disorder if any", "none", "personal reasoning"),
    ("Lets self reflect so that we can figure it out..", "none", "personal reasoning"),
]


def main() -> int:
    rows = []
    t0 = time.time()
    for req, expected, note in REAL:
        try:
            body = ask_jev({"request": req}, QUESTIONS)
            a = body["answers"]["domain"]
            rows.append({
                "req": req, "expected": expected, "pred": a["choice"],
                "conf": float(a.get("confidence", 0.0)),
                "ok": a["choice"] == expected, "note": note,
                "top3": sorted(a.get("probabilities", {}).items(), key=lambda kv: -kv[1])[:3],
                "cost": body.get("usage", {}).get("cost"),
            })
        except JevError as e:
            rows.append({"req": req, "expected": expected, "pred": f"ERR", "conf": 0.0, "ok": False, "note": str(e), "top3": []})

    ok = sum(1 for r in rows if r["ok"])
    print(f"REAL-TRAFFIC TEST — {ok}/{len(rows)} correct ({ok/len(rows)*100:.0f}%)  {time.time()-t0:.1f}s\n")
    for r in rows:
        mark = "PASS" if r["ok"] else "MISS"
        print(f"[{mark}] {r['req'][:70]}")
        print(f"       exp={r['expected']:15s} pred={r['pred']:15s} conf={r['conf']:.2f}  ({r['note']})")
        if not r["ok"]:
            print(f"       top3: {r['top3']}")
    print(f"\nTotal cost: ${sum(r.get('cost') or 0 for r in rows):.6f} for {len(rows)} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
