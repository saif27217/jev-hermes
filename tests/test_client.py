"""Offline tests for the Jev client. No network, no API key required."""

import json

import pytest

from conftest import answer, envelope


# --------------------------------------------------------------------------
# Transport, payload and error handling
# --------------------------------------------------------------------------

def test_payload_is_top_level_not_nested(jev, fake_transport):
    """The whole point of this client is the top-level payload shape."""
    fake_transport.push(envelope({"urgent": answer("noul", noul=0.9)}))
    jev.ask_jev("some state", {"urgent": {"type": "noul", "instructions": "Is it urgent?"}})

    sent = fake_transport.payloads[0]
    assert set(sent) == {"model", "state", "questions"}
    assert "decisionsRequest" not in sent
    assert sent["state"] == "some state"
    assert sent["questions"]["urgent"]["type"] == "noul"


def test_authorization_header_uses_bearer_key(jev, fake_transport, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    fake_transport.push(envelope({"x": answer("noul", noul=0.5)}))
    jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}})

    req = fake_transport.requests[0]
    assert req.get_header("Authorization") == "Bearer sk-or-v1-test"
    assert req.get_header("Content-type") == "application/json"
    assert req.method == "POST"


def test_structured_state_is_passed_through_unchanged(jev, fake_transport):
    fake_transport.push(envelope({"x": answer("noul", noul=0.5)}))
    state = {"ticket": {"messages": [{"text": "hi"}]}, "policy": {"refund": True}}
    jev.ask_jev(state, {"x": {"type": "noul", "instructions": "q"}})
    assert fake_transport.payloads[0]["state"] == state


def test_missing_api_key_is_a_clear_error(jev, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(jev.JevError, match="OPENROUTER_API_KEY is not set"):
        jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}})


def test_placeholder_key_is_rejected(jev, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "***")
    with pytest.raises(jev.JevError, match="not set"):
        jev.get_api_key()


def test_empty_questions_rejected(jev, fake_transport):
    with pytest.raises(jev.JevError, match="must not be empty"):
        jev.ask_jev("s", {})
    assert fake_transport.payloads == []


def test_missing_answer_raises_instead_of_returning_none(jev, fake_transport):
    fake_transport.push(envelope({"other": answer("noul", noul=0.5)}))
    with pytest.raises(jev.JevError, match="did not answer: expected"):
        jev.ask_jev("s", {"expected": {"type": "noul", "instructions": "q"}})


def test_malformed_answer_rejected(jev, fake_transport):
    fake_transport.push(envelope({"x": "not-a-dict"}))
    with pytest.raises(jev.JevError, match="Malformed answer"):
        jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}})


@pytest.mark.parametrize("bad", [1.5, -0.1, None, "0.5"])
def test_out_of_range_noul_rejected(jev, fake_transport, bad):
    fake_transport.push(envelope({"x": answer("noul", noul=bad)}))
    with pytest.raises(jev.JevError, match="out of range"):
        jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}})


def test_retries_on_429_then_succeeds(jev, fake_transport):
    err = jev.urllib.error.HTTPError(jev.ENDPOINT, 429, "slow down", {}, None)
    fake_transport.push(err, envelope({"x": answer("noul", noul=0.7)}))
    body = jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}}, retries=2)
    assert body["answers"]["x"]["noul"] == 0.7
    assert len(fake_transport.payloads) == 2


def test_retries_exhausted_raises_with_status(jev, fake_transport):
    errs = [jev.urllib.error.HTTPError(jev.ENDPOINT, 503, "down", {}, None) for _ in range(3)]
    fake_transport.push(*errs)
    with pytest.raises(jev.JevError, match="HTTP 503"):
        jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}}, retries=2)
    assert len(fake_transport.payloads) == 3


def test_client_error_is_not_retried(jev, fake_transport):
    err = jev.urllib.error.HTTPError(jev.ENDPOINT, 400, "bad", {}, None)
    fake_transport.push(err)
    with pytest.raises(jev.JevError, match="HTTP 400"):
        jev.ask_jev("s", {"x": {"type": "noul", "instructions": "q"}}, retries=2)
    assert len(fake_transport.payloads) == 1


# --------------------------------------------------------------------------
# Typed helpers
# --------------------------------------------------------------------------

def test_noul_returns_probability(jev, fake_transport):
    fake_transport.push(envelope({"decision": answer("noul", noul=0.23)}))
    assert jev.noul("ticket text", "Is this time-sensitive?") == 0.23
    q = fake_transport.payloads[0]["questions"]["decision"]
    assert q == {"type": "noul", "instructions": "Is this time-sensitive?"}


def test_noul_accepts_name_and_criteria(jev, fake_transport):
    fake_transport.push(envelope({"refund": answer("noul", noul=0.9)}))
    assert jev.noul("s", "Refund asked?", name="refund", criteria={"true": {"what": "yes"}}) == 0.9
    q = fake_transport.payloads[0]["questions"]["refund"]
    assert q["criteria"] == {"true": {"what": "yes"}}


def test_choice_returns_triple(jev, fake_transport):
    fake_transport.push(envelope({
        "skill": answer("choice", choice="pdf", confidence=1.0, probabilities={"pdf": 1.0, "web": 0.0})
    }))
    key, conf, probs = jev.choice("s", "skill", "Which fits?", {"pdf": "PDF work", "web": "Web work"})
    assert (key, conf) == ("pdf", 1.0)
    assert probs["pdf"] == 1.0


def test_score_returns_float_position(jev, fake_transport):
    fake_transport.push(envelope({
        "sev": answer("score", score=1.86, confidence=0.79,
                      legend={"0": "Calm", "1": "Frustrated", "2": "Angry"},
                      probabilities={"0": 0.0, "1": 0.14, "2": 0.86})
    }))
    pos, conf, probs = jev.score("s", "sev", "How frustrated?", ["Calm", "Frustrated", "Angry"])
    assert pos == 1.86 and isinstance(pos, float)
    assert conf == 0.79
    assert probs["2"] == 0.86


def test_score_levels_sent_as_criteria_list(jev, fake_transport):
    fake_transport.push(envelope({"sev": answer("score", score=0.0)}))
    jev.score("s", "sev", "How frustrated?", ["Calm", "Frustrated", "Angry"])
    assert fake_transport.payloads[0]["questions"]["sev"]["criteria"] == ["Calm", "Frustrated", "Angry"]


def test_ask_many_returns_answers_without_envelope(jev, fake_transport):
    fake_transport.push(envelope({"a": answer("noul", noul=1.0), "b": answer("noul", noul=0.0)}))
    out = jev.ask_many("s", {"a": {"type": "noul", "instructions": "q"}, "b": {"type": "noul", "instructions": "q"}})
    assert set(out) == {"a", "b"}
    assert "usage" not in out


def test_all_questions_go_in_one_request(jev, fake_transport):
    """Rule 2: never one call per question."""
    fake_transport.push(envelope({
        "a": answer("noul", noul=1.0), "b": answer("noul", noul=1.0),
        "c": answer("noul", noul=1.0), "d": answer("noul", noul=1.0),
    }))
    qs = {k: {"type": "noul", "instructions": "q"} for k in "abcd"}
    jev.ask_many("s", qs)
    assert len(fake_transport.payloads) == 1
    assert len(fake_transport.payloads[0]["questions"]) == 4


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

@pytest.fixture()
def gate_probs(jev, fake_transport):
    def _set(**probs):
        fake_transport.push(envelope({k: answer("noul", noul=v) for k, v in probs.items()}))
        return fake_transport
    return _set


def test_gate_approves_when_every_check_is_clear(jev, fake_transport, gate_probs):
    gate_probs(customer_asked=0.99, right_order=0.97, policy_covers=0.93)
    out = jev.gate("s", {"customer_asked": "a", "right_order": "b", "policy_covers": "c"})
    assert out["outcome"] == "approve"
    assert len(fake_transport.payloads) == 1


def test_gate_reviews_when_a_check_is_unclear(jev, fake_transport, gate_probs):
    gate_probs(customer_asked=0.99, right_order=0.73, policy_covers=0.89)
    out = jev.gate("s", {"customer_asked": "a", "right_order": "b", "policy_covers": "c"})
    assert out["outcome"] == "review"
    assert out["checks"]["right_order"] == 0.73


def test_gate_blocks_on_a_clearly_false_check(jev, gate_probs):
    gate_probs(customer_asked=0.99, right_order=0.97, policy_covers=0.04)
    out = jev.gate("s", {"customer_asked": "a", "right_order": "b", "policy_covers": "c"})
    assert out["outcome"] == "block"
    assert "policy_covers" in out["reason"]


def test_same_probabilities_flip_with_threshold(jev, gate_probs):
    """Rule 4: thresholds are the knob. Identical answers, different outcome."""
    checks = {"customer_asked": "a", "right_order": "b", "policy_covers": "c"}
    gate_probs(customer_asked=0.99, right_order=0.76, policy_covers=0.89)
    strict = jev.gate("s", checks, approve_at=0.9)
    gate_probs(customer_asked=0.99, right_order=0.73, policy_covers=0.87)
    loose = jev.gate("s", checks, approve_at=0.7)
    assert (strict["outcome"], loose["outcome"]) == ("review", "approve")


def test_failing_precheck_blocks_without_a_request(jev, fake_transport):
    out = jev.gate("s", {"a": "x"}, precheck=lambda: "amount over policy ceiling")
    assert out["outcome"] == "block"
    assert fake_transport.payloads == []
    assert out["checks"] is None


def test_passing_precheck_proceeds(jev, gate_probs):
    gate_probs(a=0.99, b=0.99)
    out = jev.gate("s", {"a": "x", "b": "y"}, precheck=lambda: None)
    assert out["outcome"] == "approve"


def test_gate_sends_every_check_as_noul(jev, fake_transport, gate_probs):
    gate_probs(a=0.95, b=0.95)
    jev.gate("s", {"a": "cond one", "b": "cond two"})
    sent = fake_transport.payloads[0]["questions"]
    assert all(q["type"] == "noul" for q in sent.values())
    assert sent["a"]["instructions"] == "cond one"


# --------------------------------------------------------------------------
# Cascade verification
# --------------------------------------------------------------------------

def _cascade(jev, fake_transport, choice, confidence):
    """The shipped answer_verify set asks two questions; both must be answered."""
    fake_transport.push(envelope({
        "support": answer("choice", choice=choice, confidence=confidence,
                          probabilities={choice: confidence}),
        "grounded_in_own_words": answer("noul", noul=0.9),
    }))
    return jev.cascade_verify({"question": "q", "sources": "s", "assistant_answer": "a"})


def test_cascade_accepts_grounded_answer(jev, fake_transport):
    assert _cascade(jev, fake_transport, "supported", 0.95)["route"] == "accept"


def test_cascade_escalates_unsupported_answer(jev, fake_transport):
    assert _cascade(jev, fake_transport, "unsupported", 0.9)["route"] == "escalate"


def test_cascade_hands_off_when_sources_are_silent(jev, fake_transport):
    assert _cascade(jev, fake_transport, "declined", 0.9)["route"] == "handoff"


def test_cascade_escalates_low_confidence_even_when_supported(jev, fake_transport):
    assert _cascade(jev, fake_transport, "supported", 0.55)["route"] == "escalate"


def test_cascade_accept_threshold_is_tunable(jev, fake_transport):
    assert _cascade(jev, fake_transport, "supported", 0.72)["route"] == "escalate"
    fake_transport.push(envelope({
        "support": answer("choice", choice="supported", confidence=0.72, probabilities={"supported": 0.72}),
        "grounded_in_own_words": answer("noul", noul=0.9),
    }))
    out = jev.cascade_verify({"q": 1}, accept_at=0.7)
    assert out["route"] == "accept"


def test_cascade_accepts_a_bare_question_definition(jev, fake_transport):
    fake_transport.push(envelope({"support": answer("choice", choice="supported", confidence=0.9)}))
    out = jev.cascade_verify({"q": 1}, {"type": "choice", "instructions": "ok?", "criteria": {"supported": "y"}})
    assert out["route"] == "accept"


def test_cascade_rejects_a_wrongly_shaped_verifier(jev):
    with pytest.raises(jev.JevError, match="answer_verify set, or a single question"):
        jev.cascade_verify({"q": 1}, {"not_support": {"type": "choice"}})


# --------------------------------------------------------------------------
# Saved decision sets
# --------------------------------------------------------------------------

def test_shipped_decisions_all_load_and_are_wellformed(jev):
    names = jev.list_decisions()
    assert {"answer_verify", "doc_triage", "skill_routing", "sop_audit_triage"} <= set(names)
    for name in names:
        qs = jev.load_decision(name)
        assert qs, f"{name} is empty"
        for qname, q in qs.items():
            assert q["type"] in {"choice", "noul", "score"}, f"{name}/{qname} bad type"
            assert q.get("instructions"), f"{name}/{qname} missing instructions"


def test_choice_decisions_have_at_least_two_criteria(jev):
    """Rule: 3-7 options is the sweet spot, but 2 is the floor for a choice."""
    for name in ("skill_routing", "answer_verify", "doc_triage", "sop_audit_triage"):
        for qname, q in jev.load_decision(name).items():
            if q["type"] == "choice":
                assert len(q["criteria"]) >= 2, f"{name}/{qname} has {len(q['criteria'])} criteria"


def test_load_decision_accepts_extension(jev):
    assert jev.load_decision("answer_verify.json") == jev.load_decision("answer_verify")


def test_missing_decision_names_the_alternatives(jev):
    with pytest.raises(jev.JevError, match="no decision set 'nope'. Available: answer_verify"):
        jev.load_decision("nope")


def test_answer_verify_covers_the_three_routes(jev):
    """The cascade's routing depends on exactly these three keys existing."""
    assert set(jev.load_decision("answer_verify")["support"]["criteria"]) == {"supported", "unsupported", "declined"}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_list_runs(jev, capsys):
    assert jev.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "sop_audit_triage" in out
    assert "total)" in out


def test_cli_parse_criteria(jev):
    assert jev.parse_criteria("pdf:PDF work,web:Web research") == {"pdf": "PDF work", "web": "Web research"}
    assert jev.parse_criteria("Low,Med,High", as_list=True) == ["Low", "Med", "High"]


def test_cli_parse_criteria_rejects_missing_colon(jev):
    with pytest.raises(SystemExit):
        jev.parse_criteria("pdf-PDF work")


def test_cli_requires_a_state(jev):
    with pytest.raises(SystemExit):
        jev.main(["--noul", "urgent", "Is it urgent?"])


def test_cli_score_without_criteria_errors(jev):
    with pytest.raises(SystemExit):
        jev.main(["--state", "s", "--score", "sev", "How bad?"])


def test_cli_state_file_parses_json(jev, fake_transport, tmp_path):
    fake_transport.push(envelope({"urgent": answer("noul", noul=0.8)}))
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"ticket": {"text": "hello"}}))
    assert jev.main(["--state-file", str(f), "--noul", "urgent", "Is it urgent?"]) == 0
    assert fake_transport.payloads[0]["state"] == {"ticket": {"text": "hello"}}


def test_cli_state_file_falls_back_to_text(jev, fake_transport, tmp_path):
    fake_transport.push(envelope({"urgent": answer("noul", noul=0.8)}))
    f = tmp_path / "state.txt"
    f.write_text("plain text state")
    jev.main(["--state-file", str(f), "--noul", "urgent", "Is it urgent?"])
    assert fake_transport.payloads[0]["state"] == "plain text state"


def test_cli_decision_and_inline_questions_merge(jev, fake_transport):
    fake_transport.push(envelope({
        "is_sop_audit": answer("noul", noul=0.9),
        "audit_scope": answer("choice", choice="single", confidence=0.8),
        "has_reference": answer("noul", noul=0.9),
        "is_platform_migration": answer("noul", noul=0.1),
        "urgent": answer("noul", noul=0.5),
    }))
    assert jev.main(["--state", "s", "--decision", "sop_audit_triage", "--noul", "urgent", "Urgent?"]) == 0
    assert "urgent" in fake_transport.payloads[0]["questions"]


def test_cli_gate_prints_outcome(jev, fake_transport, capsys):
    fake_transport.push(envelope({
        "amount_within_policy": answer("noul", noul=0.99),
        "customer_asked": answer("noul", noul=0.97),
    }))
    rc = jev.main(["--state", "s", "--gate",
                   "--noul", "amount_within_policy", "Is the amount within policy?",
                   "--noul", "customer_asked", "Did the customer ask?"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("APPROVE")
    assert "customer_asked: 0.97" in out


def test_cli_reports_errors_without_traceback(jev, fake_transport, capsys):
    err = jev.JevError("boom")
    fake_transport.push(err)
    rc = jev.main(["--state", "s", "--noul", "x", "q"])
    assert rc == 1
    assert "error: boom" in capsys.readouterr().err


def test_cli_verbose_shows_probabilities_and_request_id(jev, fake_transport, capsys):
    fake_transport.push(envelope({"skill": answer("choice", choice="pdf", confidence=1.0, probabilities={"pdf": 1.0})}))
    jev.main(["--state", "s", "--verbose", "--choice", "skill", "Which?", "--criteria", "pdf:PDFs"])
    out = capsys.readouterr().out
    assert "probabilities" in out and "Request ID" in out


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def test_print_decision_renders_all_three_types(jev, capsys):
    jev.print_decision(envelope({
        "pick": answer("choice", choice="pdf", confidence=0.99, probabilities={"pdf": 0.99}),
        "urgent": answer("noul", noul=0.88),
        "sev": answer("score", score=1.9, confidence=0.8),
    }))
    out = capsys.readouterr().out
    assert "[pick] -> pdf" in out
    assert "[urgent] -> YES (p=0.88)" in out
    assert "[sev] -> 1.9" in out


def test_print_gate_lists_each_check(jev, capsys):
    jev.print_gate({"outcome": "review", "reason": "unclear", "checks": {"a": 0.5, "b": 0.9}})
    out = capsys.readouterr().out
    assert out.startswith("REVIEW")
    assert "a: 0.50" in out and "b: 0.90" in out
