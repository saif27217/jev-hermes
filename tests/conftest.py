"""Make scripts/ importable and expose shared helpers for the test suite."""

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _dummy_key(monkeypatch):
    """Every offline test runs with a fake key so the transport fake is what fails, not auth.

    Skipped under JEV_LIVE=1, where the real key must survive. Tests that exercise
    missing/placeholder keys delete or overwrite it themselves.
    """
    if os.environ.get("JEV_LIVE") != "1":
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch, jev):
    """Fail loudly if an offline test reaches the real API.

    Runs before `fake_transport`, which overwrites this stub when a test asks for it.
    Disabled under JEV_LIVE=1, where reaching the API is the whole point.
    """
    if os.environ.get("JEV_LIVE") == "1":
        return

    def _refuse(*_a, **_kw):
        raise AssertionError("offline test attempted a real network call — use fake_transport")

    monkeypatch.setattr(jev.urllib.request, "urlopen", _refuse)


@pytest.fixture()
def jev():
    """The client module, reloaded per test so module state never leaks."""
    return importlib.import_module("jev_client")


def answer(kind: str, **fields):
    """Build an answer payload the way the API shapes it."""
    return {"type": kind, **fields}


def envelope(answers: dict, **extra):
    """Wrap answers in a full API response envelope."""
    body = {
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "answers": answers,
        "usage": {"input_tokens": 300, "output_tokens": 20, "cost": 0.0000126},
        "id": "gen-dec-1-test",
    }
    body.update(extra)
    return body


@pytest.fixture()
def fake_transport(monkeypatch, jev):
    """Replace the HTTP hop. Records payloads; scripted to return queued envelopes.

    Each queued item is either an envelope dict or an exception class to raise.
    """

    class Transport:
        def __init__(self):
            self.queue = []
            self.payloads = []
            self.requests = []

        def push(self, *items):
            self.queue.extend(items)
            return self

        def __call__(self, req, timeout=None):
            body = json.loads(req.data.decode())
            self.payloads.append(body)
            self.requests.append(req)
            item = self.queue.pop(0) if self.queue else envelope({})
            if isinstance(item, Exception) or (isinstance(item, type) and issubclass(item, Exception)):
                raise item
            return _Response(json.dumps(item).encode())

    transport = Transport()
    monkeypatch.setattr(jev.urllib.request, "urlopen", transport)
    monkeypatch.setattr(jev.time, "sleep", lambda _s: None)  # no real backoff in tests
    return transport


class _Response:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
