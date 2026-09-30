# Examples

Each script is standalone and runnable. `01`-`04` need `OPENROUTER_API_KEY` in the
environment; each costs well under a cent. `05` uses the **free, keyless** Zen
endpoint, so it runs with no setup at all.

| Script | Shows | Key idea |
|---|---|---|
| `01_gate_tool_call.py` | approve / block / review around an action | Atomic checks + far-apart thresholds; a deterministic precheck blocks for free; injected instructions inside the data do **not** become the policy |
| `02_verify_before_escalate.py` | draft → verify → escalate | Jev checks a cheap model's draft against the sources; only failures escalate |
| `03_route_to_workflow.py` | routing, all questions in one request | Every independent question in a single call; composite judgement combined in code |
| `04_design_your_own.py` | the full design loop, then saving the set | Turn a reviewer's checklist into `noul` questions and reuse them forever |
| `05_compare_options.py` | two options from spec sheets | The generic `option_pick` set; read `specs_sufficient` before the winner, and never let a `<0.5` score gap decide |

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
python3 examples/01_gate_tool_call.py
python3 examples/02_verify_before_escalate.py
python3 examples/03_route_to_workflow.py
python3 examples/04_design_your_own.py

# free, keyless - no key needed
python3 examples/05_compare_options.py
```

`04` writes `scripts/decisions/repeat_test_authorisation.json` as a side effect —
that is the point of the example. Delete it if you don't want it.
