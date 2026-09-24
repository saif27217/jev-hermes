# jev-hermes

**Fast, cheap, typed decisions for AI agents and scripts — via TypeSafe's Jev model on OpenRouter.**

Jev is a *decision model*, not a chat model. You give it a situation and a set of narrow
questions; it returns calibrated probabilities instead of prose. Code owns the workflow;
Jev owns the judgment.

One request costs about **$0.00002** and returns in about **0.4 seconds**. That is roughly
1/250th the cost of one frontier-model call, which makes it practical to ask a model
"is this actually safe to do?" before every action.

```
state  ──►  POST /api/alpha/decisions  ──►  {choice | score | noul}  ──►  your code branches
                                              ~0.4s, ~$0.00002
```

## What it does

- **Routes** an incoming request to the right workflow — with a confidence score attached
- **Gates** an action before your code performs it: approve / block / review
- **Verifies** a cheap model's draft answer against its sources, and escalates only the failures
- **Classifies** and extracts typed labels from messy text
- **Scores** on a rubric — returns a position on your scale, not just a label
- **Guards** against prompt injection, by keeping untrusted text separate from policy

## Why a decision model instead of asking a chat model

| | Chat model | Jev |
|---|---|---|
| Returns | prose you must parse | typed answers + `confidence` |
| Cost | ~$0.005/call | ~$0.00002/call |
| Latency | seconds | ~0.4s |
| Multiple questions | one call each, or hope | all in one request, in parallel |
| Failing loudly | usually fails silently | raises when it cannot answer |

## Quick start

```bash
git clone https://github.com/saif27217/jev-hermes && cd jev-hermes
export OPENROUTER_API_KEY=sk-or-v1-...        # same key as OpenRouter chat

# ask a single yes/no question
python3 scripts/jev_client.py --state "Incoming ticket: payouts failing 3 days" \
    --noul urgent "Is this time-sensitive?"

# run a saved, reusable question set
python3 scripts/jev_client.py --list
python3 scripts/jev_client.py --state "New SOP to audit against a kit insert" \
    --decision sop_audit_triage

# gate an action: every question as a yes/no check -> approve | block | review
python3 scripts/jev_client.py --state-file ticket.json --noul customer_asked "Did they ask?" \
    --noul within_policy "Is the amount within policy?" --gate
```

No installation, no dependencies. The client is Python standard library only — copy
`scripts/jev_client.py` anywhere and it runs.

## Use it as a library

```python
import sys; sys.path.insert(0, "scripts")
from jev_client import noul, choice, score, gate, cascade_verify, ask_jev, load_decision

noul("ticket text", "Is this time-sensitive?")                    # -> 0.23
choice(state, "skill", "Which fits?", {"pdf": "PDF work", "web": "Web work"})
                                                                  # -> ("pdf", 1.0, {...})
score(state, "sev", "How frustrated?", ["Calm", "Frustrated", "Angry"])
                                                                  # -> (1.86, 0.79, {...})
gate(state, {"a": "cond one", "b": "cond two"}, approve_at=0.9)   # -> verdict + probabilities
cascade_verify({"question": ..., "sources": ..., "assistant_answer": ...})
                                                                  # -> accept | escalate | handoff
```

## The three primitives

| Type | Ask | Returns |
|---|---|---|
| `choice` | which of these options? | `choice` + `probabilities` + `confidence` |
| `score` | which level on this spectrum? | `score` (**float**) + `legend` + `probabilities` + `confidence` |
| `noul` | is this true? | `noul` (0–1 yes-probability; **no** `confidence`) |

## The five rules that make it work

1. **One snap judgment per question.** Ask only what a knowledgeable person decides in a
   second. "Analyze this and decide" is a signal the question needs splitting.
2. **Ask every question in ONE request.** Questions share the `state`, run in parallel, and
   never see each other's answers. Extra questions cost tokens only, so asking ones you might
   need on another branch is nearly free. *Measured: 1 question = 288 in-tokens / 441 ms;
   4 questions = 486 in-tokens / 387 ms.*
3. **Decompose, then weight in code.** One question per factor; combine with your own weights.
   To change behaviour, tune weights — not prompts.
4. **Threshold on `confidence` by risk.** High → act, medium → confirm/review, low → escalate.
   Stakes set the number, not habit. *Measured: identical probabilities gave `review` at
   `approve_at=0.9` and `approve` at `0.7`.*
5. **Code decides, Jev judges.** Deterministic checks, rules, and side effects stay in code.
   A second request is justified only by a real dependency — when the next question's *options*
   are not knowable until the first answer arrives.

## Repository layout

```
jev-hermes/
├── README.md                  you are here (For humans)
├── AGENTS.md                  canonical agent doc — the skill for any agent touching this repo
├── sync.sh                    mirror the canonical Hermes skill into this repo (ONE-WAY)
├── MANIFEST.sha256            hashes of mirrored files; CI fails if the mirror drifts
├── scripts/
│   ├── jev_client.py          stdlib-only client, CLI, typed helpers, gate + cascade   [mirrored]
│   └── decisions/             reusable saved question sets
│       ├── skill_routing.json      route a task to a workflow family
│       ├── answer_verify.json      verify a draft answer against its sources
│       ├── doc_triage.json         classify an incoming document
│       └── sop_audit_triage.json   triage a SOP-audit request
├── docs/
│   ├── design.md              how to design decisions for ANY new use case            [mirrored]
│   ├── api.md                 full wire format, field shapes, errors                  [mirrored]
│   └── recipes.md             worked patterns incl. gating and cascades               [mirrored]
├── examples/                  4 runnable scripts, one per pattern
├── tests/
│   ├── test_client.py         54 offline tests — no network, no API key needed
│   └── test_live_smoke.py     7 real API tests, skipped unless JEV_LIVE=1
└── .github/workflows/ci.yml   offline tests on 4 Python versions + mirror + decision-set checks
```

Files marked *[mirrored]* are exact copies of the canonical skill and must never be edited
here — see **Keeping the mirror honest** below.

## Saved question sets

A question set is a JSON file in `scripts/decisions/`. Write one, and it is reusable forever
via `--decision <name>` or `load_decision("<name>")`.

```json
{
  "within_repeat_limit": {
    "type": "noul",
    "instructions": "Using `policy` only, is `case.repeat_count` at most `policy.max_repeat_rate`?"
  },
  "reason_documented": {
    "type": "noul",
    "instructions": "Does `case.comment` give an actual reason? A blank comment is not a reason.",
    "criteria": {
      "true":  {"what": "States a concrete analytical or clinical reason"},
      "false": {"what": "Blank, or a placeholder like 'repeat'", "not_for": "A stated reason you disagree with"}
    }
  }
}
```

`examples/04_design_your_own.py` builds a set from scratch and saves it in this format.

## Designing a new use case

1. Build the **`state`** — only the context the questions need. Use a dict and point questions
   at fields with backticked paths: `` `ticket.messages[0].text` ``. Keep untrusted text in its
   own field, never mixed with policy.
2. Ask what a careful reviewer would check. Make each check its own `noul`. Rich `criteria`
   objects (`what` / `examples` / `not_for`) sharpen borderline calls.
3. Set **thresholds** from the cost of each kind of mistake. Far-apart thresholds (0.9 / 0.1)
   send only the genuinely unclear cases to a human.
4. **Branch in code** on the answers; log both the answer and its `probabilities`.
5. **Save the set** to `scripts/decisions/<name>.json` — reusable from then on.

Full method: [`docs/design.md`](docs/design.md) · Worked patterns: [`docs/recipes.md`](docs/recipes.md)

## Running the tests

```bash
pip install -r requirements-dev.txt

pytest tests/test_client.py -q                 # 54 offline tests, ~0.1s, no key needed
JEV_LIVE=1 pytest tests/test_live_smoke.py -q  # 7 tests against the real API
./sync.sh --check                              # is the mirror still in sync?
```

The offline suite installs a stub that makes any real network call fail loudly, so it can
never silently start depending on the API.

## Keeping the mirror honest

The canonical copy of `scripts/jev_client.py` and `docs/*.md` lives in a Hermes skill at
`~/.hermes/skills/openrouter-jev/`. This repo is the published mirror, plus the tests,
examples, README, and CI that don't belong in a skill directory.

**One direction of truth: skill → repo.**

```bash
./sync.sh          # copy the skill in, refresh MANIFEST.sha256
./sync.sh --check  # verify the working tree against the manifest
```

CI runs the `--check` equivalent (`sha256sum -c MANIFEST.sha256`) on every push, so a stale or
hand-edited mirror fails the build instead of drifting quietly.

## Verified dependencies

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | uses `str \| None` syntax; tested on 3.10–3.13 |
| Jev model | `typesafe/jev-1.13` | pin this. `~typesafe/jev-latest` follows the newest release |
| Endpoint | `POST https://openrouter.ai/api/alpha/decisions` | an **alpha** path — not `/v1/chat/completions` |
| Auth | `OPENROUTER_API_KEY` | the same key works for chat and decisions |
| Third-party packages | none | standard library only, by design |

## Known issues

- **The endpoint is on an alpha path** (`/api/alpha/decisions`). It is not in OpenRouter's
  public model list, so the model will not appear in a model picker and the route may change
  without notice. The client raises a clear `JevError` rather than failing quietly — but pin
  the model slug and tolerate the URL.
- **`noul` has no `confidence` field.** Threshold the `noul` value itself; there is no second
  signal to cross-check.
- **`score` returns a float, not an index.** `1.99` sits almost exactly on the last criterion.
  Compare with `>=` thresholds, never equality.
- **A `noul` near 0.5 is not "medium".** It means the proposition is borderline as stated —
  usually a sign to add `criteria` rather than to accept the number.
- **Latency is not the win here; cost is.** 0.4s is fine for gating and routing, too slow to
  sit in a per-token streaming loop.

## Documentation

- [`AGENTS.md`](AGENTS.md) — canonical doc for any agent working in this repo
- [`docs/design.md`](docs/design.md) — designing decisions for a new use case
- [`docs/api.md`](docs/api.md) — wire format, field shapes, error codes
- [`docs/recipes.md`](docs/recipes.md) — worked patterns
- [`examples/README.md`](examples/README.md) — what each example demonstrates

## License

MIT — see [`LICENSE`](LICENSE).
