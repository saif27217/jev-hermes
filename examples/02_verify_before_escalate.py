#!/usr/bin/env python3
"""Verify a draft answer before escalating it to a frontier model or a human.

The cascade: a cheap model drafts, Jev checks the draft against the retrieved
sources, and only the failures escalate. Paying frontier prices for the few hard
cases is far cheaper than paying them for everything.

    export OPENROUTER_API_KEY=sk-or-v1-...
    python3 examples/02_verify_before_escalate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from jev_client import cascade_verify  # noqa: E402

SOURCES = """
Serum osmolality, measured by freezing-point depression, reference interval 275-295 mOsm/kg.
Osmolal gap (measured minus calculated) should be less than 10 mOsm/kg.
Samples with gross lipaemia or haemolysis are unsuitable.
"""

DRAFTS = [
    ("grounded", "The reference interval for serum osmolality is 275-295 mOsm/kg; the "
                 "osmolal gap should be under 10 mOsm/kg."),
    ("off by a mile", "The reference interval for serum osmolality is 300-320 mOsm/kg."),
    ("not covered by the sources", "Serum osmolality should be measured in EDTA plasma "
                                   "at 37 degrees."),
    ("plausible padding", "The reference interval is 275-295 mOsm/kg, and osmolality is "
                          "increased in all patients with diabetes insipidus."),
]

ROUTES = {
    "accept": "ship it — sources support every claim",
    "escalate": "send to the frontier model or a human for a second look",
    "handoff": "sources do not address the question at all — retrieve more, then retry",
}


def main() -> int:
    for label, draft in DRAFTS:
        print(f"\n--- {label} ---")
        print(f"  draft: {draft[:72]}{'...' if len(draft) > 72 else ''}")
        out = cascade_verify({
            "question": "What is the reference interval for serum osmolality?",
            "sources": SOURCES,
            "assistant_answer": draft,
        })
        print(f"  verdict: {out['choice']} (conf {out['confidence']:.2f})")
        print(f"  route:   {out['route']} -> {ROUTES[out['route']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
