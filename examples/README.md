# Examples

Each script is standalone and runnable. All of them need `OPENROUTER_API_KEY`
in the environment; each costs well under a cent.

| Script | Shows | Key idea |
|---|---|---|
| `01_gate_tool_call.py` | approve / block / review around an action | Atomic checks + far-apart thresholds; a deterministic precheck blocks for free; injected instructions inside the data do **not** become the policy |
| `02_verify_before_escalate.py` | draft → verify → escalate | Jev checks a cheap model's draft against the sources; only failures escalate |
| `03_route_to_workflow.py` | routing, all questions in one request | Every independent question in a single call; composite judgement combined in code |
| `04_design_your_own.py` | the full design loop, then saving the set | Turn a reviewer's checklist into `noul` questions and reuse them forever |

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python3 examples/01_gate_tool_call.py
python3 examples/02_verify_before_escalate.py
python3 examples/03_route_to_workflow.py
python3 examples/04_design_your_own.py
```

`04` writes `scripts/decisions/repeat_test_authorisation.json` as a side effect —
that is the point of the example. Delete it if you don't want it.
