#!/usr/bin/env python3
"""Test harness for the Sak-specific skill router prototype.

Runs real task strings through Jev's `skill_router` decision set and
compares the predicted domain against a hand-labelled ground truth.
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
CASES = [
    ("Audit the VDC/BIO/128 Albumin SOP against the supplied kit insert, produce the Exact Suggested Changes table", "lab_clinical", "core SOP workload"),
    ("Our Access TSH kit insert has a new reference range; check if the SHBG SOP needs updating", "lab_clinical", "kit-insert vetting"),
    ("Get today's top 10 GitHub repositories by stars", "research", "web/trend scan"),
    ("Write a LinkedIn post about our new cobas e analyzer going live", "content_media", "social content"),
    ("The daily AI-trends cron job failed with a token-expiry error - fix it", "devops_infra", "troubleshooting a failing job"),
    ("Upload these 15 images to Google Drive in batches of 20", "integration_mcp", "platform action"),
    ("Make a 6-slide infographic carousel on thyroid function testing", "content_media", "carousel"),
    ("Search PubMed for recent HbA1c method-comparison papers", "research", "literature search"),
    ("Render a 30-second motion-graphics video from this script", "content_media", "video"),
    ("What is RELIANCE trading at and is it a buy right now?", "market_finance", "market decision"),
    ("Transcribe this voice memo and summarise it", "content_media", "audio"),
    ("Rank these 7 use cases for me by value", "none", "pure reasoning"),
    ("Create a Google Doc summarising the audit findings in a table", "integration_mcp", "Google Docs via platform"),
    ("Query the vdc collection for everything on the SHBG assay", "rag_data", "RAG query"),
    ("Run a differential expression analysis on this count matrix then make a volcano plot", "bio_science", "omics"),
]

# Boundary cases — deliberately ambiguous. Reported separately.
HARD = [
    ("What does the SHBG SOP say about sample stability?", "lab_clinical", "question about SOP contents, not an audit"),
    ("Make a PPTX deck of the audit findings", "office_files", "local file vs slides"),
    ("Send the audit summary to the lab team on Slack", "integration_mcp", "platform send"),
    ("Set up a daily job that checks for kit-insert updates", "automation_cron", "build recurring, lab topic"),
    ("Find and fix the bug in our Flask SOP-audit web app", "devops_infra", "code debugging"),
]


def run(cases):
    rows = []
    for req, expected, note in cases:
        try:
            body = ask_jev({"request": req}, QUESTIONS)
            a = body["answers"]["domain"]
            pred = a["choice"]
            conf = float(a.get("confidence", 0.0))
            probs = a.get("probabilities", {})
            flags = {k: round(float(v["noul"]), 2) for k, v in body["answers"].items() if v.get("type") == "noul"}
            usage = body.get("usage", {})
        except JevError as e:
            rows.append({"request": req, "expected": expected, "pred": f"ERROR:{e}", "conf": 0.0, "ok": False, "note": note})
            continue
        rows.append({
            "request": req,
            "expected": expected,
            "pred": pred,
            "conf": conf,
            "ok": pred == expected,
            "note": note,
            "flags": flags,
            "top3": sorted(probs.items(), key=lambda kv: -kv[1])[:3],
            "cost": usage.get("cost"),
        })
    return rows


def report(title, rows, elapsed):
    ok = sum(1 for r in rows if r["ok"])
    print(f"\n{title}  —  {ok}/{len(rows)} correct  ({(ok/len(rows))*100:.0f}%)   {elapsed:.1f}s\n")
    for r in rows:
        mark = "PASS" if r["ok"] else "MISS"
        print(f"[{mark}] {r['request'][:66]}")
        print(f"        expected={r['expected']:16s} pred={r['pred']:16s} conf={r['conf']:.2f}  ({r['note']})")
        if not r["ok"]:
            print(f"        top3: {r.get('top3', 'n/a')}")
    return sum(r.get("cost") or 0 for r in rows)


def main() -> int:
    t0 = time.time()
    rows = run(CASES)
    c1 = report("SKILL ROUTER TEST (fixed set)", rows, time.time() - t0)
    t1 = time.time()
    hard = run(HARD)
    c2 = report("SKILL ROUTER TEST (boundary set)", hard, time.time() - t1)
    print(f"\nTotal cost: ${c1 + c2:.6f} for {len(CASES) + len(HARD)} routed requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
