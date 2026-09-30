"""Make scripts/ importable and expose shared helpers for the test suite."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# Both providers ship a file called `jev_client.py`. Importing the second one by plain
# name returns the first from sys.modules, so the OpenRouter suite would silently test the
# Zen client (observed: 4 bogus failures when both files are collected in one session).
# Each provider therefore gets its own module name, registered here.
CLIENT_MODULES = {
    "jev_client": ROOT / "scripts" / "jev_client.py",            # OpenRouter
    "oc_jev_client": ROOT / "opencode" / "scripts" / "jev_client.py",  # OpenCode Zen
}


def load_client(which: str = "jev_client"):
    """Import one provider's client under a unique name, bypassing sys.modules caching."""
    name = which if which in CLIENT_MODULES else "jev_client"
    path = CLIENT_MODULES[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# `zen_live` marks the OpenCode Zen smoke tests. That provider's free model needs no
# key and is expected to run in CI, so those tests opt out of the offline network
# guard explicitly instead of the guard being weakened for everyone.
def pytest_configure(config):
    config.addinivalue_line("markers", "zen_live: reaches the free keyless OpenCode Zen endpoint")


@pytest.fixture(autouse=True)
def _dummy_key(monkeypatch):
    """Every offline test runs with a fake key so the transport fake is what fails, not auth.

    Skipped under JEV_LIVE=1, where the real key must survive. Tests that exercise
    missing/placeholder keys delete or overwrite it themselves.
    """
    if os.environ.get("JEV_LIVE") != "1":
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch, jev, request):
    """Fail loudly if an offline test reaches the real API.

    Runs before `fake_transport`, which overwrites this stub when a test asks for it.
    Disabled under JEV_LIVE=1, where reaching the API is the whole point.

    Also disabled for tests marked `zen_live` (the OpenCode Zen suite). That model is
    free and keyless, so its smoke tests are meant to run without a secret — but they
    must opt in explicitly, so this guard keeps protecting every other test.
    """
    if os.environ.get("JEV_LIVE") == "1":
        return
    if request.node.get_closest_marker("zen_live"):
        return

    def _refuse(*_a, **_kw):
        raise AssertionError("offline test attempted a real network call — use fake_transport")

    monkeypatch.setattr(jev.urllib.request, "urlopen", _refuse)


@pytest.fixture()
def jev():
    """The OpenRouter client, loaded fresh per test so module state never leaks."""
    return load_client("jev_client")


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
