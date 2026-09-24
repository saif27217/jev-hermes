#!/usr/bin/env python3
"""Jev decisions client — TypeSafe Jev via OpenRouter's Decisions API.

Stdlib only. See references/design.md for how to design question sets.

    from jev_client import noul, choice, score, gate, cascade_verify, ask_jev, load_decision

    noul("ticket text", "Is this time-sensitive?")                 # -> float
    choice(state, "skill", "Which fits?", {...})                   # -> (key, confidence, probs)
    gate(state, checks, approve_at=0.9, block_at=0.1)              # -> approve|block|review
    load_decision("sop_audit_triage")                              # -> questions dict

CLI:
    python3 jev_client.py --list
    python3 jev_client.py --state "..." --noul urgent "Is this urgent?"
    python3 jev_client.py --state "..." --decision sop_audit_triage
    python3 jev_client.py --state-file ticket.json --decision answer_verify --gate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
ROLLING_MODEL = "~typesafe/jev-latest"
DECISIONS_DIR = Path(__file__).resolve().parent / "decisions"
RETRY_STATUS = {429, 500, 502, 503, 504}


class JevError(RuntimeError):
    """Any failure that must never be mistaken for an answer."""


# --------------------------------------------------------------------------
# Core call
# --------------------------------------------------------------------------

def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or key == "***":
        raise JevError("OPENROUTER_API_KEY is not set. export OPENROUTER_API_KEY=sk-or-v1-...")
    return key


def ask_jev(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
    retries: int = 2,
) -> dict[str, Any]:
    """Send one request. Ask every independent question here — extra questions are nearly free.

    Returns the raw response: {"model", "answers", "usage", "id", "provider"}.
    Raises JevError on transport failure, non-2xx, or a missing/malformed answer.
    """
    if not questions:
        raise JevError("questions must not be empty")

    payload = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    body: dict[str, Any] | None = None

    for attempt in range(retries + 1):
        req = urllib.request.Request(
            ENDPOINT,
            data=payload,
            headers={
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            if e.code in RETRY_STATUS and attempt < retries:
                time.sleep(2 ** attempt)          # 1s, then 2s
                continue
            raise JevError(f"Decisions HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise JevError(f"Decisions request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise JevError(f"Decisions returned non-JSON: {e}") from e

    if body is None:
        raise JevError("Decisions request produced no response")

    answers = body.get("answers") or {}
    missing = [k for k in questions if k not in answers]
    if missing:
        raise JevError(f"Jev did not answer: {', '.join(missing)}")
    for key, ans in answers.items():
        if not isinstance(ans, dict) or "type" not in ans:
            raise JevError(f"Malformed answer for {key!r}: {ans!r}")
        if ans["type"] == "noul":
            p = ans.get("noul")
            if not isinstance(p, (int, float)) or not 0 <= p <= 1:
                raise JevError(f"noul answer for {key!r} out of range: {p!r}")

    return body


def ask_many(state: Any, questions: dict[str, dict[str, Any]], **kw: Any) -> dict[str, Any]:
    """All answers from one request, sans envelope: {id: answer_dict}."""
    return ask_jev(state, questions, **kw)["answers"]


def noul(
    state: Any,
    instructions: str | dict[str, Any],
    name: str = "decision",
    criteria: dict[str, Any] | None = None,
    **kw: Any,
) -> float:
    """Yes-probability for one yes/no proposition.

        noul(state, "Does this message convey urgency?")                 # -> 0.23
        noul(state, "Does it request a refund?", name="refund_requested") # keyed

    Pass `criteria` as {"true": {...}, "false": {...}} to sharpen the boundary. For several
    questions at once use ask_many() — one request, nearly free.
    """
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria is not None:
        question["criteria"] = criteria
    return float(ask_jev(state, {name: question}, **kw)["answers"][name]["noul"])


def choice(
    state: Any,
    name: str,
    instructions: str,
    criteria: dict[str, str],
    **kw: Any,
) -> tuple[str, float, dict[str, float]]:
    """(picked key, confidence, probabilities)."""
    a = ask_jev(state, {name: {"type": "choice", "instructions": instructions, "criteria": criteria}}, **kw)["answers"][name]
    return a["choice"], float(a.get("confidence", 0.0)), a.get("probabilities", {})


def score(
    state: Any,
    name: str,
    instructions: str,
    levels: list[Any],
    **kw: Any,
) -> tuple[float, float, dict[str, float]]:
    """(float position, confidence, probabilities). Position may fall between levels."""
    a = ask_jev(state, {name: {"type": "score", "instructions": instructions, "criteria": levels}}, **kw)["answers"][name]
    return float(a["score"]), float(a.get("confidence", 0.0)), a.get("probabilities", {})


# --------------------------------------------------------------------------
# Composite helpers
# --------------------------------------------------------------------------

def gate(
    state: Any,
    checks: dict[str, str],
    *,
    approve_at: float = 0.9,
    block_at: float = 0.1,
    precheck: Callable[[], str | None] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    """Turn several `noul` checks into approve | block | review.

    `checks` maps a name to a yes/no proposition — each an atomic condition that must hold for
    the action to be safe, never the whole decision ("should we approve this?"). A failing
    `precheck` blocks without spending a request. Thresholds this far apart send only the
    genuinely unclear calls to a human.
    """
    if precheck is not None:
        problem = precheck()
        if problem:
            return {"outcome": "block", "reason": problem, "checks": None, "usage": None}

    questions = {k: {"type": "noul", "instructions": v} for k, v in checks.items()}
    body = ask_jev(state, questions, **kw)
    probs = {k: float(v["noul"]) for k, v in body["answers"].items()}

    if all(p >= approve_at for p in probs.values()):
        outcome, reason = "approve", "every check clear"
    elif any(p <= block_at for p in probs.values()):
        outcome, reason = "block", "clearly false: " + ", ".join(k for k, p in probs.items() if p <= block_at)
    else:
        outcome, reason = "review", "no check is clearly true or clearly false"

    return {"outcome": outcome, "reason": reason, "checks": probs, "usage": body.get("usage")}


def cascade_verify(
    state: dict[str, Any],
    verifier: dict[str, dict[str, Any]] | None = None,
    *,
    accept_at: float = 0.8,
    **kw: Any,
) -> dict[str, Any]:
    """Verdict for a draft answer: accept | escalate | handoff.

    `state` must carry the sources, the question, and the draft answer. Defaults to the
    shipped `answer_verify` set. `accept_at` is the tuning knob: raise if wrong answers
    ship, lower if the handoff queue is mostly correct.
    """
    verifier = verifier or load_decision("answer_verify")
    if "support" not in verifier:
        if "type" not in verifier:                      # a bare {"type": "choice", ...} also counts
            raise JevError("verifier must be the answer_verify set, or a single question definition containing 'type'")
        verifier = {"support": verifier}
    a = ask_jev(state, verifier, **kw)["answers"]["support"]
    conf = float(a.get("confidence", 0.0))
    if a["choice"] == "supported" and conf >= accept_at:
        route = "accept"
    elif a["choice"] == "declined":
        route = "handoff"                               # sources do not cover it
    else:
        route = "escalate"
    return {"route": route, "choice": a["choice"], "confidence": conf,
            "probabilities": a.get("probabilities", {})}


# --------------------------------------------------------------------------
# Saved question sets
# --------------------------------------------------------------------------

def load_decision(name: str) -> dict[str, dict[str, Any]]:
    """Load `scripts/decisions/<name>.json`. Name may include the .json suffix."""
    path = DECISIONS_DIR / (name if name.endswith(".json") else f"{name}.json")
    if not path.is_file():
        available = ", ".join(list_decisions()) or "(none)"
        raise JevError(f"no decision set {name!r}. Available: {available}")
    return json.loads(path.read_text())


def list_decisions() -> list[str]:
    if not DECISIONS_DIR.is_dir():
        return []
    return sorted(p.stem for p in DECISIONS_DIR.glob("*.json"))


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def print_decision(body: dict[str, Any], *, verbose: bool = False) -> None:
    print(f"Model: {body.get('model', '?')}")
    print(f"Provider: {body.get('provider', '?')}")
    for name, a in (body.get("answers") or {}).items():
        t = a.get("type")
        if t == "choice":
            print(f"  [{name}] -> {a['choice']} (conf: {a.get('confidence', 0):.2f})")
            if verbose and a.get("probabilities"):
                print(f"    probabilities: {a['probabilities']}")
        elif t == "noul":
            p = a["noul"]
            print(f"  [{name}] -> {'YES' if p >= 0.5 else 'NO'} (p={p:.2f})")
        elif t == "score":
            print(f"  [{name}] -> {a['score']} (conf: {a.get('confidence', 0):.2f})")
            if verbose and a.get("legend"):
                print(f"    legend: {a['legend']}")
    u = body.get("usage") or {}
    if u:
        print(f"Cost: ${u.get('cost', 0):.6f} | Tokens: {u.get('input_tokens', '?')}in/{u.get('output_tokens', '?')}out")
    if verbose:
        print(f"Request ID: {body.get('id', '?')}")


def print_gate(result: dict[str, Any]) -> None:
    print(f"{result['outcome'].upper()}: {result['reason']}")
    for k, p in (result["checks"] or {}).items():
        print(f"  {k}: {p:.2f}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_criteria(spec: str, *, as_list: bool = False) -> Any:
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if as_list:
        return parts
    out = {}
    for p in parts:
        if ":" not in p:
            raise SystemExit(f"--criteria entries need key:description — got {p!r}")
        k, v = p.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Jev decisions client (TypeSafe via OpenRouter).")
    ap.add_argument("--state", help="State text to evaluate")
    ap.add_argument("--state-file", help="Read state from a file (parsed as JSON when it parses, else text)")
    ap.add_argument("--json", "-j", help="Path to a questions JSON file")
    ap.add_argument("--decision", "-d", help="Name of a saved question set in scripts/decisions/")
    ap.add_argument("--list", "-l", action="store_true", help="List saved question sets and exit")

    ap.add_argument("--choice", nargs=2, action="append", metavar=("NAME", "INSTRUCTIONS"))
    ap.add_argument("--criteria", action="append", metavar="KEY:DESC[,KEY:DESC]",
                    help="Criteria for the preceding --choice, or levels for --score")
    ap.add_argument("--noul", nargs=2, action="append", metavar=("NAME", "INSTRUCTIONS"))
    ap.add_argument("--score", nargs=2, action="append", metavar=("NAME", "INSTRUCTIONS"),
                    help="Levels come from --criteria (comma-separated, low to high)")

    ap.add_argument("--gate", action="store_true", help="Treat all questions as noul checks -> approve|block|review")
    ap.add_argument("--approve-at", type=float, default=0.9, help="Gate approve threshold (default 0.9)")
    ap.add_argument("--block-at", type=float, default=0.1, help="Gate block threshold (default 0.1)")

    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Default {DEFAULT_MODEL} (or {ROLLING_MODEL})")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        names = list_decisions()
        print(f"Saved question sets in {DECISIONS_DIR}:")
        for n in names:
            print(f"  {n}")
        print(f"  ({len(names)} total)")
        return 0

    if args.state is None and args.state_file is None:
        ap.error("one of --state or --state-file is required")
    if args.state_file:
        raw = Path(args.state_file).read_text()
        try:
            state: Any = json.loads(raw)
        except json.JSONDecodeError:
            state = raw
    else:
        state = args.state

    questions: dict[str, Any] = {}
    if args.json:
        questions = json.loads(Path(args.json).read_text())
    if args.decision:
        questions = {**load_decision(args.decision), **questions}

    criteria_queue = list(args.criteria or [])
    for name, instr in args.choice or []:
        crit = parse_criteria(criteria_queue.pop(0)) if criteria_queue else {}
        questions[name] = {"type": "choice", "instructions": instr, "criteria": crit}
    for name, instr in args.noul or []:
        questions[name] = {"type": "noul", "instructions": instr}
    for name, instr in args.score or []:
        if not criteria_queue:
            ap.error(f"--score {name!r} needs --criteria with comma-separated levels, low to high")
        levels = parse_criteria(criteria_queue.pop(0), as_list=True)
        questions[name] = {"type": "score", "instructions": instr, "criteria": levels}
    if criteria_queue:
        ap.error(f"unused --criteria values: {criteria_queue}")

    if not questions:
        ap.error("no questions given: use --json, --decision, or --choice/--noul/--score")

    kw = {"model": args.model, "timeout": args.timeout, "retries": args.retries}
    try:
        if args.gate:
            checks = {k: v["instructions"] for k, v in questions.items()}
            print_gate(gate(state, checks, approve_at=args.approve_at, block_at=args.block_at, **kw))
        else:
            body = ask_jev(state, questions, **kw)
            print_decision(body, verbose=args.verbose)
            if len(questions) == 1:
                print(f"\nState: {str(state)[:80]}{'...' if len(str(state)) > 80 else ''}")
    except JevError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
