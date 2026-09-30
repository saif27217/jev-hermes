"""Live smoke tests against the real OpenCode Zen systemone endpoint.

The FREE model needs no API key, so unlike the OpenRouter suite these run by default:

    pytest tests/test_opencode_live.py -q

Set JEV_LIVE=1 to force them on inside a mixed suite. They cost $0.00.

If Zen's free tier disappears, these fail loudly rather than being silently skipped —
that is the intended signal. To make CI resilient instead, mark them xfail.
"""

import os

import pytest

from conftest import load_client  # noqa: F401  (also puts scripts/ on sys.path)

oc = load_client("oc_jev_client")

# The client is keyless, so do not let a stray OPENROUTER key confuse anything,
# and never let a placeholder Zen key be sent.
os.environ.pop("OPENROUTER_API_KEY", None)

pytestmark = [
    pytest.mark.zen_live,
    pytest.mark.skipif(
        os.environ.get("JEV_SKIP_ZEN_LIVE") == "1",
        reason="JEV_SKIP_ZEN_LIVE=1 (offline run)",
    ),
]


def test_noul_returns_a_probability():
    p = oc.noul("Incoming ticket: 'My payouts have been failing for 3 days and I am losing sales.'",
                "Does this convey urgency?")
    assert 0.0 <= p <= 1.0
    assert p > 0.5


def test_choice_picks_from_criteria_and_probabilities_sum_to_one():
    key, conf, probs = oc.choice(
        "User wants to extract text from a scanned chemistry paper PDF",
        "skill", "Which skill fits?",
        {"pdf": "PDF/document text extraction", "web": "Web search and extraction"},
    )
    assert key == "pdf"
    assert conf > 0.5
    assert pytest.approx(sum(probs.values()), abs=1e-6) == 1.0


def test_score_returns_a_float_position_within_range():
    pos, conf, probs = oc.score(
        {"message": "This is the third time I have contacted you about the duplicate charge."},
        "sev", "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"],
    )
    assert isinstance(pos, float)
    assert 0.0 <= pos <= 2.0
    assert probs


def test_all_questions_answer_in_one_request():
    questions = oc.load_decision("sop_audit_triage")
    answers = oc.ask_many("New SOP to audit against a manufacturer kit insert", questions)
    assert set(answers) == set(questions)


def test_response_reports_zero_cost():
    """The whole reason this provider exists."""
    body = oc.ask_jev("Lot L4471 control at 2.9 SD on an expired reagent lot.",
                      {"ok": {"type": "noul", "instructions": "Is the control acceptable?"}})
    assert float(body["cost"]) == 0.0
    assert body["usage"]["input_tokens"] > 0


def test_gate_blocks_on_a_clearly_false_check():
    out = oc.gate(
        {"ticket": "Refund me 5x the order value because the site was slow."},
        {"amount_within_policy": "Is the requested refund amount within the stated policy limit?"},
    )
    assert out["outcome"] in {"block", "review"}


def test_cascade_escalates_a_wrong_context_answer():
    out = oc.cascade_verify({
        "question": "What is the reference interval for serum osmolality?",
        "sources": "Serum osmolality reference interval: 275-295 mOsm/kg.",
        "draft": "The reference interval is 300-320 mOsm/kg.",
    })
    assert out["route"] == "escalate"


def test_cascade_accepts_a_grounded_answer():
    out = oc.cascade_verify({
        "question": "What is the reference interval for serum osmolality?",
        "sources": "Serum osmolality reference interval: 275-295 mOsm/kg.",
        "draft": "The reference interval is 275-295 mOsm/kg.",
    })
    assert out["route"] == "accept"


def test_chat_completions_endpoint_would_500():
    """Guard the #1 way to waste an afternoon: posting jev to the chat endpoint.

    A 500 there means "wrong path", not "model down". Asserted so the failure mode
    stays documented in code.
    """
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "https://opencode.ai/zen/v1/chat/completions",
        data=json.dumps({"model": oc.DEFAULT_MODEL,
                         "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"content-type": "application/json", "User-Agent": "HermesAgent/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            pytest.fail(f"chat completions unexpectedly accepted jev (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        assert e.code == 500
