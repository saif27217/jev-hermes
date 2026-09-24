"""Live smoke tests against the real Decisions API.

Skipped unless JEV_LIVE=1 and OPENROUTER_API_KEY are both set, so CI stays offline:

    JEV_LIVE=1 pytest tests/test_live_smoke.py -v

These cost roughly $0.00002 per request.
"""

import os

import pytest

from conftest import ROOT  # noqa: F401  (import side effect: puts scripts/ on sys.path)

import jev_client  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("JEV_LIVE") != "1",
    reason="set JEV_LIVE=1 with a real OPENROUTER_API_KEY to run live tests",
)


def test_noul_returns_a_probability():
    p = jev_client.noul("Incoming ticket: 'My payouts have been failing for 3 days.'",
                        "Does this convey urgency?")
    assert 0.0 <= p <= 1.0
    assert p > 0.5


def test_choice_picks_from_criteria():
    key, conf, probs = jev_client.choice(
        "User wants to extract text from a scanned chemistry paper PDF",
        "skill", "Which skill fits?",
        {"pdf": "PDF/document text extraction", "web": "Web search and extraction"},
    )
    assert key == "pdf"
    assert conf > 0.5
    assert pytest.approx(sum(probs.values()), abs=1e-6) == 1.0


def test_score_returns_a_float_position():
    pos, conf, probs = jev_client.score(
        {"message": "This is the third time I have contacted you about the duplicate charge."},
        "sev", "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"],
    )
    assert isinstance(pos, float)
    assert 0.0 <= pos <= 2.0
    assert probs


def test_all_questions_answer_in_one_request():
    answers = jev_client.ask_many(
        "New SOP to audit against a manufacturer kit insert",
        dict(jev_client.load_decision("sop_audit_triage")),
    )
    assert set(answers) == set(jev_client.load_decision("sop_audit_triage"))


def test_gate_blocks_on_a_clearly_false_check():
    out = jev_client.gate(
        {"ticket": "Refund me 5x the order value because the site was slow."},
        {"amount_within_policy": "Is the requested refund amount within the stated policy limit?"},
    )
    assert out["outcome"] in {"block", "review"}
    assert out["usage"]["cost"] > 0


def test_cascade_escalates_a_wrong_context_answer():
    out = jev_client.cascade_verify({
        "question": "What is the reference interval for serum osmolality?",
        "sources": "Serum osmolality reference interval: 275-295 mOsm/kg.",
        "assistant_answer": "The reference interval is 300-320 mOsm/kg.",
    })
    assert out["route"] == "escalate"


def test_cascade_accepts_a_grounded_answer():
    out = jev_client.cascade_verify({
        "question": "What is the reference interval for serum osmolality?",
        "sources": "Serum osmolality reference interval: 275-295 mOsm/kg.",
        "assistant_answer": "The reference interval is 275-295 mOsm/kg.",
    })
    assert out["route"] == "accept"
