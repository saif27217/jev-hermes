"""Offline tests for the OpenCode Zen provider (`opencode/scripts/jev_client.py`).

Runs with no network and no API key — the free model needs neither.

    pytest tests/test_opencode_client.py -q
"""

import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from conftest import ROOT, load_client  # noqa: F401  (also puts scripts/ on sys.path)

# Both providers ship `jev_client.py`; the shared loader imports this one under a unique
# name so it can never collide with the OpenRouter client's module object.
oc = load_client("oc_jev_client")


class _Response:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def zen_body(answers, cost="0", model=oc.DEFAULT_MODEL):
    """Zen's real envelope: cost is a top-level STRING, not inside usage."""
    return {"model": model, "answers": answers, "usage": {"input_tokens": 300, "output_tokens": 20}, "cost": cost}


def transport_returning(body):
    class T:
        def __init__(self):
            self.requests = []
            self.payloads = []

        def __call__(self, req, timeout=None):
            self.requests.append(req)
            self.payloads.append(json.loads(req.data.decode()))
            return _Response(json.dumps(body).encode())

    t = T()
    return t


class TestEndpointContract(unittest.TestCase):
    def test_posts_to_systemone_with_free_model_and_no_auth(self):
        t = transport_returning(zen_body({"q": {"type": "noul", "noul": 0.5}}))
        with mock.patch.object(oc.urllib.request, "urlopen", t):
            with mock.patch.dict(os.environ, {}, clear=True):
                oc.ask_jev("state", {"q": {"type": "noul", "instructions": "?"}})

        req = t.requests[0]
        self.assertEqual(req.full_url, "https://opencode.ai/zen/v1/systemone")
        body = t.payloads[0]
        self.assertEqual(body["model"], "jev-1.13-free")
        self.assertEqual(set(body), {"model", "state", "questions"})   # top-level, not nested
        hdrs = {k.lower(): v for k, v in dict(req.headers).items()}
        self.assertNotIn("authorization", hdrs)                        # keyless by default
        self.assertIn("user-agent", hdrs)                              # Cloudflare 1010 guard

    def test_default_and_paid_models(self):
        self.assertEqual(oc.DEFAULT_MODEL, "jev-1.13-free")
        self.assertEqual(oc.PAID_MODEL, "jev-1.13")

    def test_cost_is_a_top_level_string(self):
        """Zen differs from OpenRouter here: cost is NOT inside usage."""
        body = zen_body({"q": {"type": "noul", "noul": 0.5}}, cost="0")
        self.assertEqual(body["cost"], "0")
        self.assertNotIn("cost", body["usage"])
        with mock.patch.object(oc.urllib.request, "urlopen", transport_returning(body)):
            out = oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}})
        buf = io.StringIO()
        with redirect_stdout(buf):
            oc.print_decision(out)
        self.assertIn("$0.000000", buf.getvalue())


class TestAuthBehaviour(unittest.TestCase):
    def test_placeholder_key_is_not_sent(self):
        """A placeholder bearer 401s even on the free model — it must never leave the process."""
        t = transport_returning(zen_body({"q": {"type": "noul", "noul": 0.5}}))
        with mock.patch.object(oc.urllib.request, "urlopen", t):
            with mock.patch.dict(os.environ, {"OPENCODE_ZEN_API_KEY": "***"}, clear=True):
                oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}})
        hdrs = {k.lower(): v for k, v in dict(t.requests[0].headers).items()}
        self.assertNotIn("authorization", hdrs)

    def test_stale_key_401_retries_keyless(self):
        calls = []

        def flaky(req, timeout=None):
            calls.append(dict(req.headers))
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 401, "no", {},
                                             io.BytesIO(b'{"error":{"type":"AuthError"}}'))
            return _Response(json.dumps(zen_body({"q": {"type": "noul", "noul": 0.9}})).encode())

        with mock.patch.object(oc.urllib.request, "urlopen", flaky):
            with mock.patch.dict(os.environ, {"OPENCODE_ZEN_API_KEY": "sk-stale-looking-key"}, clear=True):
                body = oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}})

        self.assertEqual(len(calls), 2)
        self.assertIn("Authorization", calls[0])
        self.assertNotIn("Authorization", calls[1])   # retried without the bad key
        self.assertEqual(body["answers"]["q"]["noul"], 0.9)

    def test_get_api_key_filters_placeholders(self):
        for bad in ("***", "", "  ", "none", "your_key_here"):
            with mock.patch.dict(os.environ, {"OPENCODE_ZEN_API_KEY": bad}, clear=True):
                self.assertIsNone(oc.get_api_key(), bad)
        with mock.patch.dict(os.environ, {"OPENCODE_ZEN_API_KEY": "sk-real-looking"}, clear=True):
            self.assertEqual(oc.get_api_key(), "sk-real-looking")


class TestErrorSurface(unittest.TestCase):
    def _raises(self, code, body=b"{}"):
        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "no", {}, io.BytesIO(body))
        return boom

    def test_bad_model_raises_immediately(self):
        with mock.patch.object(oc.urllib.request, "urlopen", self._raises(401, b'{"error":{"type":"ModelError"}}')):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(oc.JevError) as cm:
                    oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}}, model="jev-9.9", retries=0)
        self.assertIn("401", str(cm.exception))

    def test_insufficient_funds_raises(self):
        with mock.patch.object(oc.urllib.request, "urlopen", self._raises(402, b'{"error":"Insufficient account funds"}')):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(oc.JevError) as cm:
                    oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}}, model=oc.PAID_MODEL, retries=0)
        self.assertIn("402", str(cm.exception))

    def test_missing_answers_raise(self):
        with mock.patch.object(oc.urllib.request, "urlopen", transport_returning(zen_body({}))):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(oc.JevError) as cm:
                    oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}})
        self.assertIn("did not answer", str(cm.exception))

    def test_out_of_range_noul_raises(self):
        bad = zen_body({"q": {"type": "noul", "noul": 1.7}})
        with mock.patch.object(oc.urllib.request, "urlopen", transport_returning(bad)):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(oc.JevError):
                    oc.ask_jev("s", {"q": {"type": "noul", "instructions": "?"}})

    def test_empty_questions_rejected_without_network(self):
        with self.assertRaises(oc.JevError):
            oc.ask_jev("s", {})


class TestTypedHelpers(unittest.TestCase):
    def test_noul_returns_float(self):
        with mock.patch.object(oc, "ask_jev", return_value=zen_body({"decision": {"type": "noul", "noul": 0.23}})):
            self.assertAlmostEqual(oc.noul("s", "?"), 0.23)

    def test_choice_returns_key_conf_probs(self):
        b = zen_body({"q": {"type": "choice", "choice": "pdf", "confidence": 1.0,
                            "probabilities": {"pdf": 1.0, "web": 0.0}}})
        with mock.patch.object(oc, "ask_jev", return_value=b):
            self.assertEqual(oc.choice("s", "q", "Which?", {"pdf": "P", "web": "W"}),
                             ("pdf", 1.0, {"pdf": 1.0, "web": 0.0}))

    def test_score_is_float_position(self):
        with mock.patch.object(oc, "ask_jev", return_value=zen_body({"q": {"type": "score", "score": 2.48, "confidence": 0.48}})):
            pos, conf, _ = oc.score("s", "q", "How bad?", ["Low", "High"])
        self.assertIsInstance(pos, float)
        self.assertAlmostEqual(pos, 2.48)

    def test_ask_many_strips_envelope(self):
        with mock.patch.object(oc, "ask_jev", return_value=zen_body(
                {"a": {"type": "noul", "noul": 0.1}, "b": {"type": "noul", "noul": 0.9}})):
            out = oc.ask_many("s", {"a": {"type": "noul", "instructions": "?"},
                                    "b": {"type": "noul", "instructions": "?"}})
        self.assertEqual(set(out), {"a", "b"})


class TestGate(unittest.TestCase):
    CHECK = {"safe": {"type": "noul", "instructions": "Is it safe to release?"}}

    def _body(self, *probs):
        return zen_body({n: {"type": "noul", "noul": p} for n, p in zip(self.CHECK, probs)})

    def test_approve_block_review(self):
        for p, want in ((0.95, "approve"), (0.05, "block"), (0.55, "review")):
            with mock.patch.object(oc, "ask_jev", return_value=self._body(p)):
                self.assertEqual(oc.gate("s", self.CHECK)["outcome"], want)

    def test_choice_is_context_not_a_verdict_input(self):
        """Regression carried from the OpenRouter client: never flatten a choice into a noul."""
        q = {"scope": {"type": "choice", "instructions": "Which?",
                       "criteria": {"sop": "SOP", "kit": "Kit insert"}}}
        body = zen_body({"safe": {"type": "noul", "noul": 0.95},
                         "scope": {"type": "choice", "choice": "kit", "confidence": 0.9,
                                   "probabilities": {"sop": 0.1, "kit": 0.9}}})
        with mock.patch.object(oc, "ask_jev", return_value=body) as m:
            res = oc.gate("s", {**self.CHECK, **q})
        self.assertEqual(res["outcome"], "approve")
        self.assertEqual(res["context"]["scope"], "kit")
        self.assertEqual(m.call_args[0][1]["scope"]["criteria"], {"sop": "SOP", "kit": "Kit insert"})

    def test_gate_without_noul_raises(self):
        with self.assertRaises(oc.JevError):
            oc.gate("s", {"c": {"type": "choice", "instructions": "Which?",
                               "criteria": {"a": "A", "b": "B"}}})

    def test_precheck_blocks_without_spending_a_request(self):
        with mock.patch.object(oc, "ask_jev", side_effect=AssertionError("must not be called")):
            res = oc.gate("s", self.CHECK, precheck=lambda: "file locked")
        self.assertEqual(res["outcome"], "block")
        self.assertIsNone(res["usage"])

    def test_thresholds_are_the_knob(self):
        for approve_at, want in ((0.9, "review"), (0.5, "approve")):
            with mock.patch.object(oc, "ask_jev", return_value=self._body(0.6)):
                self.assertEqual(oc.gate("s", self.CHECK, approve_at=approve_at)["outcome"], want)


class TestCascade(unittest.TestCase):
    STATE = {"question": "q", "sources": "s", "draft": "d"}

    def _v(self, name, conf):
        return zen_body({"support": {"type": "choice", "choice": name, "confidence": conf,
                                     "probabilities": {}},
                         "grounded_in_own_words": {"type": "noul", "noul": 0.5}})

    def test_routes(self):
        with mock.patch.object(oc, "ask_jev", return_value=self._v("supported", 0.9)):
            self.assertEqual(oc.cascade_verify(self.STATE)["route"], "accept")
        with mock.patch.object(oc, "ask_jev", return_value=self._v("supported", 0.5)):
            self.assertEqual(oc.cascade_verify(self.STATE)["route"], "escalate")
        with mock.patch.object(oc, "ask_jev", return_value=self._v("declined", 0.9)):
            self.assertEqual(oc.cascade_verify(self.STATE)["route"], "handoff")


class TestDecisionSets(unittest.TestCase):
    def test_all_shipped_sets_load_and_are_wellformed(self):
        names = oc.list_decisions()
        self.assertIn("answer_verify", names)
        for name in names:
            qs = oc.load_decision(name)
            self.assertTrue(qs, name)
            for qid, q in qs.items():
                self.assertIn(q["type"], {"choice", "score", "noul"}, f"{name}.{qid}")
                self.assertTrue(q.get("instructions"), f"{name}.{qid}")
                if q["type"] == "choice":
                    self.assertIsInstance(q.get("criteria"), dict)
                    self.assertGreaterEqual(len(q["criteria"]), 2, f"{name}.{qid}")

    def test_sets_match_the_openrouter_provider(self):
        """Same question library on both providers — only the transport differs.

        Loaded by path under a distinct module name: `import_module("jev_client")` would
        return the already-imported Zen client and silently compare it with itself.
        """
        or_client = load_client("jev_client")

        for name in oc.list_decisions():
            self.assertEqual(oc.load_decision(name), or_client.load_decision(name),
                             f"{name} differs between providers")

    def test_unknown_name_lists_alternatives(self):
        with self.assertRaises(oc.JevError) as cm:
            oc.load_decision("nope")
        self.assertIn("answer_verify", str(cm.exception))


class TestCLI(unittest.TestCase):
    def test_list(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(oc.main(["--list"]), 0)
        self.assertIn("answer_verify", buf.getvalue())

    def test_criteria_parsing(self):
        self.assertEqual(oc.parse_criteria("pdf:PDF work,web:Web"), {"pdf": "PDF work", "web": "Web"})
        self.assertEqual(oc.parse_criteria("Low,High", as_list=True), ["Low", "High"])
        with self.assertRaises(SystemExit):
            oc.parse_criteria("no_colon_here")

    def test_unknown_decision_exits_1_without_traceback(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            self.assertEqual(oc.main(["--state", "x", "--decision", "nope"]), 1)
        self.assertIn("error:", buf.getvalue())

    def test_missing_state_is_a_usage_error(self):
        with self.assertRaises(SystemExit):
            oc.main(["--noul", "a", "Is it true?"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
