# Comparing two options (`option_pick`)

Use when asked "which of these is better for X" and the input is a spec sheet,
feature list, or two product/reagent/instrument summaries. Jev compares; code
reports. It will not research - feed it the facts.

## State shape

Name the parts, or the questions are unanswerable:

```python
state = {
  "goal": "long-distance home Wi-Fi coverage",
  "option_a": {"name": "TP-Link Archer AX12", "specs": "...as published..."},
  "option_b": {"name": "Tenda RX2 Pro",      "specs": "...as published..."},
  "context": "single-floor flat; far bedroom is a dead zone",  # optional
}
```

Put the goal in `goal`, not in prose - the saved set reads it verbatim.
State every spec you have; jev cannot ask for the missing one.

## Read the output in this order

1. `specs_sufficient` - if low, **say so and stop**. Reporting a winner from
   insufficient data is the failure mode this question exists to catch.
2. `headline_specs_equal` - high means the marketing numbers are identical;
   the decision turns on secondary features only.
3. `winner_single` vs `winner_purchase` - these legitimately differ. One box
   wins reach; the other wins ownership. Report both, do not average them.
4. `a_score` / `b_score` - **direction only**. See the caveat below.

## Two rules learned the hard way

- **A `score` gap under ~0.5 is noise.** Reworded instructions moved the same
  pair from `2.51/2.50` to `2.17/2.42` in one session. Categorical answers
  (`noul`, `choice`) were stable across every phrasing; `score` was not.
  Never let a score gap smaller than the wording sensitivity decide anything.
- **Weight the expansion path.** `a_expansion_path` + `goal_needs_scaling`
  outrank a one-antenna spec edge in almost every purchase decision.

## Cost

9 questions, one request, ~1.2K in-tokens. Free on Zen; ~$0.00002 on
OpenRouter. Do not split into per-question calls.
