# AGENTS.md — canonical agent documentation for `jev-hermes`

This file is the skill for any AI agent (or human) touching this repository. It is written to
be loaded as procedural context: every section answers "if you want to X, do Y".

---

## 1. Project identity

**What it is.** A standard-library Python client plus a design method for TypeSafe's **Jev**
decision model, called through OpenRouter's Decisions API. It turns a situation into typed,
calibrated judgements (`choice`, `score`, `noul`) for routing, gating, verification,
classification, and grading.

**Owner.** `saif27217`. Contact via GitHub issues.

**Why it exists.** Asking a chat model "should I do this?" is expensive, slow, and returns
prose that is hard to branch on. Jev costs ~$0.00002 per request, returns in ~0.4s, and hands
back numbers with a `confidence` field. That is cheap enough to guard *every* action rather
than a sample of them.

**What makes it different.** No dependencies. No SDK. No parsing of free text. The client is
one file you can copy anywhere, and the repo ships the *method* for designing new decisions,
not just a wrapper around an endpoint.

**Two things this repo is not:**
- It is **not the canonical copy of the client.** That lives in a Hermes skill (see §8.1).
- It is **not** a general LLM wrapper. Jev returns types, never prose, and never a reasoning
  trace. If you need generated text, use a chat model.

---

## 2. Decision matrix

First lookup for common requests.

| If the user asks... | Do this |
|---|---|
| "Is the mirror in sync?" | `./sync.sh --check` |
| "I changed the client / docs in the skill" | `./sync.sh` then commit `MANIFEST.sha256` with it |
| "I want to change `scripts/jev_client.py` here" | Don't. Edit the skill (§8.1), then `./sync.sh` |
| "Does it still work?" | `pytest tests/test_client.py -q` then `JEV_LIVE=1 pytest tests/test_live_smoke.py -q` |
| "Add a new decision set" | New file in `scripts/decisions/`, then §9.1. Check CI's shape rules |
| "Is this the right model name?" | §5.1 — pin `typesafe/jev-1.13`, never hardcode `~typesafe/jev-latest` |
| "It returned 400" | §8.2 — usually a top-level field nested under `decisionsRequest` |
| "It returned 401" | §8.4 — a test fixture is overwriting the key, or the key is unset |
| "Costs look wrong" | §8.6 — `output_tokens` are free; only input is billed |
| "A test made a real network call" | §8.5 — the offline guard is disabled by `JEV_LIVE=1` |
| "Why did the gate say review?" | §8.7 — thresholds, not the model. `approve_at` / `block_at` |

---

## 3. Repository layout

| Path | Read it when | Modify it when |
|---|---|---|
| `README.md` | you need the human-facing overview | a user-visible feature or limitation changes |
| `AGENTS.md` | always — this file | you learn something a future agent must not rediscover |
| `sync.sh` | you need to know the mirror direction | the set of mirrored files changes |
| `MANIFEST.sha256` | CI failed on the mirror check | never by hand — `./sync.sh` writes it |
| `scripts/jev_client.py` | you need the API surface | **never here** — edit the skill, then `./sync.sh` |
| `scripts/decisions/*.json` | you need a reusable question set | **never here** — edit the skill, then `./sync.sh` |
| `docs/design.md` | you are designing a NEW decision | **never here** — edit the skill, then `./sync.sh` |
| `docs/api.md` | you need field shapes or error codes | **never here** — edit the skill, then `./sync.sh` |
| `docs/recipes.md` | you want a worked pattern to copy | **never here** — edit the skill, then `./sync.sh` |
| `examples/*.py` | you want a runnable end-to-end script | you add a genuinely new pattern |
| `tests/test_client.py` | you are changing client behaviour | behaviour changes — add a test first |
| `tests/test_live_smoke.py` | you are validating against reality | the real API's contract changes |
| `tests/conftest.py` | tests fail in a confusing way | you add a shared fixture |
| `.github/workflows/ci.yml` | CI is failing or you add a check | you add a test target or a Python version |
| `.env.example` | you are setting the repo up | an env var is added or renamed |

---

## 4. Runtime architecture

```
your script / agent
  │
  ├─ build state        dict or string; untrusted text in its own field, policy in another
  ├─ pick question set  load_decision("name") or an inline dict
  │
  ├─ ask_jev(state, questions, model, timeout, retries)
  │     ├─ get_api_key()          OPENROUTER_API_KEY, refuses "***"
  │     ├─ POST ENDPOINT          top-level {model, state, questions} — NOT nested
  │     ├─ retry on 429/5xx       exponential backoff, 2 attempts by default
  │     ├─ validate               every question answered? every answer well-typed?
  │     └─ → {"model","answers","usage","id","provider"}
  │
  └─ branch in code
        ├─ gate(state, checks)            every check a noul → approve | block | review
        ├─ cascade_verify(state)          draft vs sources → accept | escalate | handoff
        └─ your own thresholds            tune these, not the questions
```

**Key invariant:** `ask_jev` **raises `JevError`** rather than returning a partial or
uncertain result. A missing answer, a malformed answer, an out-of-range `noul`, a non-2xx, or
a transport failure all raise. Never catch `JevError` and treat it as a negative answer — it
is an *absence* of answer, and downstream code must handle it as such.

**Retry policy.** `RETRY_STATUS = {429, 500, 502, 503, 504}` only. A 400 or 401 is returned
immediately — retrying a malformed payload just burns time. Backoff is `2**attempt` seconds,
and tests monkeypatch `time.sleep` so they never actually wait.

---

## 5. Setup procedures

### 5.1 From a fresh clone

```bash
git clone https://github.com/saif27217/jev-hermes && cd jev-hermes
export OPENROUTER_API_KEY=sk-or-v1-...        # same key as OpenRouter chat
python3 scripts/jev_client.py --list          # smoke check: no network needed

pip install -r requirements-dev.txt           # only for the test suite
pytest tests/test_client.py -q
```

There is no install step for the client itself — it is standard library only. Copy
`scripts/jev_client.py` into any project and it works.

### 5.2 Choosing a model slug

```python
ENDPOINT    = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL  = "typesafe/jev-1.13"      # pinned — use this
ROLLING_MODEL  = "~typesafe/jev-latest"   # follows the newest release; avoid in production
```

Pin the version. The rolling alias changes behaviour under you, and since thresholds are tuned
against a model's calibration, a silent upgrade invalidates them.

### 5.3 Running the tests without a system pytest

PEP 668 environments (Debian, Homebrew Python) refuse a bare `pip install`. Use `uv`:

```bash
uv run --with pytest pytest tests/test_client.py -q
JEV_LIVE=1 uv run --with pytest pytest tests/test_live_smoke.py -q
```

---

## 6. Common operations

### 6.1 Ask one question

```python
from jev_client import noul
p = noul("Incoming ticket: payouts failing 3 days", "Is this time-sensitive?")
```

### 6.2 Ask several questions — one request, always

```python
from jev_client import ask_many
answers = ask_many(state, {
    "is_compliant":        {"type": "noul",   "instructions": "Does it meet the stated requirement?"},
    "severity":            {"type": "score",  "instructions": "How severe?",
                            "criteria": ["Low", "Medium", "High"]},
    "category":            {"type": "choice", "instructions": "Which category?",
                            "criteria": {"sop": "Standard operating procedure", "kit": "Kit insert"}},
})
```

Do **not** loop and call once per question. Questions run in parallel in a single request;
asking four costs ~40% more tokens than asking one and adds no latency.

### 6.3 Gate an action

```python
from jev_client import gate
result = gate(state, {"within_policy": "...", "customer_asked": "..."},
              approve_at=0.9, block_at=0.1, precheck=lambda: "deterministic blocker or None")
if result["outcome"] == "approve":  act()
elif result["outcome"] == "block":  refuse(result["reason"])
else:                               send_to_human(result["checks"])
```

A `precheck` that returns a string blocks **without spending a request**. Put every
deterministic check there.

### 6.4 Verify a draft before escalating

```python
from jev_client import cascade_verify
out = cascade_verify({"question": q, "sources": s, "assistant_answer": draft}, accept_at=0.8)
# out["route"] is "accept" | "escalate" | "handoff"
```

`handoff` means the sources do not address the question at all — retrieve more, then retry.
`escalate` means the draft disagrees with its sources, or `confidence` was below `accept_at`.

---

## 7. Verification procedures

Run these after any change. All four must pass.

```bash
pytest tests/test_client.py -q                  # 54 offline tests, ~0.1s
JEV_LIVE=1 pytest tests/test_live_smoke.py -q   # 7 tests against the real API
./sync.sh --check                               # mirror matches MANIFEST.sha256
python -m compileall -q scripts                 # byte-compiles on this Python version
```

If you changed `scripts/jev_client.py` (i.e. the skill), also confirm the sync happened:

```bash
./sync.sh && git diff --stat          # MANIFEST.sha256 must move with the client
```

CI additionally validates every decision set: valid JSON, a known `type`, non-empty
`instructions`, and at least two `criteria` for any `choice`.

---

## 8. Pitfalls and known issues

### 8.1 The client here is a MIRROR — editing it here is the #1 mistake

`scripts/jev_client.py`, `scripts/decisions/*.json`, and `docs/*.md` are exact copies of a
Hermes skill:

- **Canonical:** `~/.hermes/skills/openrouter-jev/` (`scripts/jev_client.py`, `scripts/decisions/`, `references/*.md`)
- **Mirror:** this repo (`scripts/`, `docs/`)

Editing the mirror "works" and then the next `./sync.sh` silently reverts it. This actually
happened during the repo's first build: the client was copied into the repo *before* two
hardening patches landed in the skill, and two tests failed against the stale copy. The fix
was `./sync.sh`, not a patch here.

**Rule:** edit the skill, then `./sync.sh`, then commit the manifest with the change.

### 8.2 HTTP 400 — almost always a nested payload

The API takes **top-level** `model`, `state`, `questions`. SDK examples sometimes show a
`decisionsRequest` wrapper; the raw REST endpoint rejects it. The client already builds the
correct shape — if you get a 400, you are calling the endpoint by hand or the model slug is
wrong. `test_payload_is_top_level_not_nested` guards this.

### 8.3 `noul` near 0.5 is not "medium" — it is under-specified

A 0.5 means the proposition is genuinely borderline *as written*. The fix is usually to add a
`criteria` object with `true` / `false` definitions, not to accept the number or to move a
threshold.

### 8.4 HTTP 401 in the test suite

Two autouse fixtures in `tests/conftest.py` interact with the environment:

- `_dummy_key` sets `OPENROUTER_API_KEY=sk-or-v1-test` — **skipped when `JEV_LIVE=1`**, so the
  real key survives for the live suite.
- `_no_real_network` makes `urlopen` raise — **also skipped when `JEV_LIVE=1`**.

If both are active during a live run, the real key gets overwritten and every request 401s
with `User not found`. That is the symptom: check the `JEV_LIVE` guards, not the key.

### 8.5 The offline suite must never reach the network

`_no_real_network` is an autouse fixture. Any offline test that tries a real request fails with
`offline test attempted a real network call — use fake_transport`. **Do not weaken it.** It is
what makes the suite trustworthy without a key and impossible to accidentally bill.

### 8.6 Cost accounting

`output_tokens` are **free** for Jev; only `input_tokens` are billed at $0.042/M. Measured
values from this repo: ~314 in-tokens → `$0.0000132`; ~540 → `$0.0000227`. So roughly
**44,000 requests per dollar**. A stale doc in the original skill claimed "178 per $1" — that
figure was wrong by ~250× and self-contradictory with the per-call cost on the same line. If
you see a per-dollar figure anywhere, recompute it: `1 / (input_tokens × 0.042 / 1e6)`.

### 8.7 A gate says `review` — that is thresholds, not the model

`gate` returns `review` when no check is `>= approve_at` and none is `<= block_at`. Identical
probabilities flip outcome at different thresholds (verified: 0.99/0.76/0.89 → `review` at
`approve_at=0.9`, `approve` at `0.7`). Tune the threshold to match the cost of each mistake;
do not rewrite the questions to chase an outcome.

### 8.8 `score` is a float, and `noul` has no `confidence`

- `score` returns a probability-weighted position (`1.99`), not an integer index. Compare with
  `>=`; never `==`.
- `noul` answers carry **no** `confidence` field. Threshold the `noul` value itself.

### 8.9 The endpoint is on an alpha path

`/api/alpha/decisions` is not `/v1/chat/completions`, and the model is not in OpenRouter's
public model list — it will not appear in a model picker. The route may change without notice.
Pin the model; keep the `JevError` handling strict so a breakage is loud.

### 8.10 `answer_verify` asks two questions but the cascade reads one

`cascade_verify` sends the whole `answer_verify` set (`support` **and** `grounded_in_own_words`)
and routes on `support`. `ask_jev` requires **every** question to be answered, so a truncated
response raises. Tests must push both answers — this caused five initial test failures.

### 8.11 CLI `--criteria` pairing is positional

`--criteria` values are consumed in the order `--choice` first, then `--score`. Passing a
`--score` without a `--criteria` is now a hard error rather than an empty `criteria` list that
the API rejects.

---

## 9. Extension recipes

### 9.1 Add a reusable decision set

1. Write the questions — one atomic judgement each, rich `criteria` where a boundary is fuzzy.
2. Run it live against a few real states before saving:
   ```python
   from jev_client import ask_many
   print(ask_many(state, my_questions))
   ```
3. Save to the **skill**: `~/.hermes/skills/openrouter-jev/scripts/decisions/<name>.json`
4. `./sync.sh`
5. Verify: `pytest tests/test_client.py -q` (the shipped-sets test enumerates every file) then
   `JEV_LIVE=1 pytest tests/test_live_smoke.py -q`

CI enforces the shape: valid JSON, `type` in `{choice, score, noul}`, non-empty `instructions`,
≥2 `criteria` for a `choice`.

### 9.2 Add a new primitive wrapper

Add it to the skill's `scripts/jev_client.py`, keep the return value unpacked and typed (see
`choice` / `score`), and add offline tests using the `fake_transport` fixture — never a live
call. Then `./sync.sh`.

### 9.3 Add an example

One runnable script per pattern in `examples/`, with a `sys.path` shim, a module docstring
stating the run command, and a mention in `examples/README.md`. Prefer real-looking states over
`foo`/`bar`. If it writes a file, gitignore it and say so in the docstring.

### 9.4 Use it from outside this repo

```bash
cp ~/projects/jev-hermes/scripts/jev_client.py /path/to/your/project/
export OPENROUTER_API_KEY=sk-or-v1-...
```

Or vendor the repo path and `sys.path.insert(0, ".../scripts")`. There is nothing to install.

---

## 10. Self-test commands

Copy-paste health check. Expect: 54 passed, 7 passed, "clean", and no output from compileall.

```bash
cd ~/projects/jev-hermes
pytest tests/test_client.py -q
JEV_LIVE=1 pytest tests/test_live_smoke.py -q
./sync.sh --check
python -m compileall -q scripts && echo "compiles clean"
python3 scripts/jev_client.py --list
for f in $(find . -name '*.sh'); do bash -n "$f" || echo "SYNTAX FAIL: $f"; done
```

If `./sync.sh --check` fails, run `./sync.sh` and commit the changed files together.

---

## 11. Handoff notes

Context a fresh agent needs, in the order it becomes relevant.

1. **This is a mirror, not the source.** The client lives in a Hermes skill. Read §8.1 before
   editing any file under `scripts/` or `docs/`.
2. **Never edit `MANIFEST.sha256`.** `./sync.sh` owns it. CI fails if it does not match.
3. **The suite is deliberately two-tier.** Offline tests are fenced from the network and need
   no key; live tests need `JEV_LIVE=1` plus a real key and cost a fraction of a cent.
4. **Thresholds are the tuning surface.** When behaviour is wrong, the first question is
   whether the *judgement* was wrong or the *threshold* was. Print `result["checks"]` and look.
5. **`JevError` is never a "no".** It is the absence of an answer. Handle it explicitly.
6. **Cost is the reason this exists.** If a design needs a chat model anyway, Jev is not the
   right tool; it is for typed judgements cheap enough to run on every event.
7. **The API is alpha and unlisted.** A sudden 404 on the endpoint is a plausible future
   failure mode; `JevError` surfaces it, and the fallback is to fall through to a chat model
   rather than to guess.

### Quick reference card

| Want to... | Do... |
|---|---|
| ask one yes/no question | `noul(state, "…")` |
| ask several at once | `ask_many(state, {...})` |
| pick from options | `choice(state, name, "…", {...})` |
| rate on a scale | `score(state, name, "…", [...])` |
| approve / block / review | `gate(state, {...}, approve_at=0.9, block_at=0.1)` |
| check a draft against sources | `cascade_verify({...}, accept_at=0.8)` |
| reuse a saved set | `load_decision("name")` or CLI `--decision name` |
| see what sets exist | `python3 scripts/jev_client.py --list` |
| sync the mirror | `./sync.sh` · check: `./sync.sh --check` |
| test without a key | `pytest tests/test_client.py -q` |
| test for real | `JEV_LIVE=1 pytest tests/test_live_smoke.py -q` |
| design a new decision | `docs/design.md`, then §9.1 |

**If you find an inconsistency between this file and reality, fix this file.**
The single sources of truth are the canonical skill at `~/.hermes/skills/openrouter-jev/` and
the live API behaviour. Everything else is documentation of those.