#!/usr/bin/env python3
"""Diagnose each miss: is it a domain-label error or a candidate-prefilter error?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage2_router import INDEX, pick_candidates, assign, JEV_LABELS, ROSTER  # noqa: E402

from measure_stage2 import LABELED  # noqa: E402

BY_NAME = {r["skill"]: r for r in ROSTER if r["description"]}


def main() -> int:
    print(f"{'case':46s} {'expected skill':24s} {'its label':15s} {'in domain?':11s} {'in window?'}")
    print("-" * 110)
    for req, exp_dom, exp_skill in LABELED:
        r = BY_NAME.get(exp_skill)
        lbl = assign(exp_skill, r["category"] if r else "")
        in_dom = exp_skill in [x["skill"] for x in INDEX.get(exp_dom, [])]
        cands = [x["skill"] for x in pick_candidates(req, INDEX.get(exp_dom, []))]
        in_win = exp_skill in cands
        print(f"{req[:44]:46s} {exp_skill:24s} {lbl:15s} {str(in_dom):11s} {str(in_win)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
