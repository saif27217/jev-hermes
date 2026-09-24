#!/usr/bin/env python3
"""Route a task to a workflow — all questions in one request.

Demonstrates rule 2: every independent question goes in a single call. The extra
questions cost tokens only (they run in parallel), so ask the ones you might need
on other branches. Measured: 1 question = 288 in-tokens / 441 ms,
4 questions = 486 in-tokens / 387 ms.

    export OPENROUTER_API_KEY=sk-or-v1-...
    python3 examples/03_route_to_workflow.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from jev_client import ask_jev, load_decision, print_decision  # noqa: E402

REQUESTS = [
    "New SOP to audit against a manufacturer kit insert",
    "Give me the top posts from a subreddit as a daily digest",
]

WORKFLOWS = {
    "clinical_audit": "clinical/sop-kit-insert-audit",
    "documentation": "productivity/pptx or edu-ppt",
    "web_research": "web/multi-subreddit-research-workflow",
    "pdf": "productivity/pdf",
    "data_analysis": "data-science/...",
    "audio": "media/audio-transcriber",
}


def main() -> int:
    questions = dict(load_decision("skill_routing"))   # the saved, reusable set
    print(f"questions in one request: {', '.join(questions)}")

    for req in REQUESTS:
        print(f"\n--- {req!r} ---")
        body = ask_jev({"request": req}, questions)
        print_decision(body)

        answers = body["answers"]
        skill = answers["primary_skill"]["choice"]
        conf = answers["primary_skill"]["confidence"]

        # Composite judgement: one question per factor, combined here in code.
        reasons = []
        if conf < 0.5:
            reasons.append(f"weak classification ({conf:.2f})")
        if answers["needs_multi_skill"]["noul"] > 0.5:
            reasons.append(f"multi-skill ({answers['needs_multi_skill']['noul']:.2f})")
        plan = f"plan a multi-step workflow — {', '.join(reasons)}" if reasons else WORKFLOWS.get(skill, skill)

        print(f"  -> {plan}")
        if answers["is_urgent"]["noul"] > 0.7:
            print("  -> flagged urgent: handle first")
        print(f"  cost: ${body['usage']['cost']:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
