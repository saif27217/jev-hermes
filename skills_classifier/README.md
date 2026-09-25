# skills_classifier

Route a user request to the right Hermes skill using **Jev** — TypeSafe's cheap
decision model — instead of injecting every skill description into the prompt
on every turn.

This folder is the working prototype and its measurements. It is **reference
material**, not part of the mirrored client (`sync.sh` does not touch it).

> **Read [`LIMITATIONS.md`](LIMITATIONS.md) first.** Prompt caching (37× discount
> on a stable prefix) collapses the headline token saving to ~30% on the bill,
> and a domain flip can make the router 3–8× *more* expensive. The verdict is
> **do not build the hybrid**.

---

## The question it answers

Hermes injects every skill's name + description into the prompt on **every
turn**, and the chat model then picks which one to load. Measured on this
machine:

| | |
|---|---|
| injected skills (archived excluded) | **274** |
| roster size, every turn | **59,335 chars ≈ 14,833 tokens** |
| one full `SKILL.md` load | **~2,874 tokens** average |

So the *selection* step costs ~14.8K tokens per turn, forever. This prototype
tests whether a ~$0.0001 Jev call can replace most of that.

---

## Method

**Stage 1 — domain.** One Jev `choice` over 12 skill domains
(`lab_clinical`, `research`, `rag_data`, `content_media`, `market_finance`,
`devops_infra`, `hermes_dev`, `integration_mcp`, `automation_cron`,
`bio_science`, `office_files`, `none`). Returns the domain plus three flags
(needs-auth, multi-domain, recurring). Decision set: `skill_router.json`.

**Taxonomy build.** All 318 skills were classified into those domains by Jev
once, batched 10 per request (`classify_skills.py` → `skill_domains.json`).
This replaced a hand-written regex map and is a distinct improvement: it fixed
the `none` bucket (was swallowing 59 skills, now 16 genuine ones).

**Stage 2 — skill.** Within the routed domain, a lexical prefilter caps the
candidates (default 12), then a second Jev `choice` picks the skill
(`stage2_router.py`).

---

## Measured results

### Stage 1 — domain accuracy

| Set | Result |
|---|---|
| Curated (20 standalone requests) | **20/20 (100%)** |
| Real traffic (17 requests from session history) | **16/17 (94%)** |

One criteria fix was needed after the first real-traffic run (67% → 94%):
`hermes_dev` was missing from the taxonomy, so Hermes/plugin/skill-authoring
work was scattered into `research`/`none`; and `none` was catching any dev task
phrased as "planning".

### Stage 2 — skill accuracy

| Metric | CAP 12 | CAP 40 |
|---|---|---|
| domain correct | 10/11 | 10/11 |
| skill recall@1 | **7/11 (64%)** | 8/11 (73%) |
| skill recall@3 | 8/11 (73%) | 9/11 (82%) |

Widening the candidate window raises recall — so **the candidate prefilter, not
Jev, is the bottleneck**. Jev never sees more than 12 of a domain's ~40 skills.

### Where each miss actually happens

From `diagnose.py` (case → expected skill → its Jev label → in domain? → in window?):

| Case | Expected | Label | Cause |
|---|---|---|---|
| append doc to Google Docs | `composio-google-docs` | integration_mcp ✓ | **prefilter dropped it** |
| create plan md | `plan` | hermes_dev ✗ | skill grouped in a domain the request does not route to |
| reel-view feature | `hermes-graphics` | devops_infra ✓ | **stage 1 routed the wrong domain** |
| query vdc | `qdrant-rag` | rag_data ✓ | Jev chose `soffos-rag` — near-duplicate, ground truth arguable |

Two of the four are debatable ground truth (`composio-mcp` vs
`composio-google-docs`; `soffos-rag` vs `qdrant-rag` are both RAG-query
skills), so real recall is likely nearer 80%.

### Token / cost comparison

| Approach | tokens per turn | vs baseline |
|---|---|---|
| Current (inject full roster) | **14,833** | — |
| Stage 1 only (Jev domain) | 1,671 | 89% less |
| Stage 1 + Jev stage 2 | 2,812 | 81% less |
| **Hybrid: stage 1 + domain shortlist, model picks** | **3,184** | **81% less** |

Over a 5-turn conversation: **74,165 → 15,920 tokens** (hybrid).

> These are **raw tokens, not billed cost.** With prompt caching on, the stable
> roster bills at ~$0.000112/turn, so the true saving is ~30%, not 81%. See
> [`LIMITATIONS.md`](LIMITATIONS.md) §1.

---

## Verdict

1. **Stage 1 (Jev → domain) works and is worth keeping** — 94% on real traffic
   at 1,671 tokens.
2. **Jev stage 2 (pick the exact skill) is the fragile part** — 64–73% recall@1.
   The full-roster model sees everything, so it resolves near-duplicates and
   context-dependent fragments that a 12-candidate Jev choice cannot.
3. **Jev-classifying all skills improves the taxonomy but does not by itself
   raise stage-2 recall**, because the losses are downstream of grouping
   (prefilter window, stage-1 domain on fragments, near-duplicates).
4. **Recommended design (caching-aware):** do **not** build the hybrid. The
   roster is cached at ~37× off, so replacing it saves ~30% of the bill at best
   and costs more on domain flips — while adding latency and a silent-miss
   failure mode. If roster savings are wanted, **shorten the roster content
   itself** (prune dead skills, trim descriptions). Full analysis:
   [`LIMITATIONS.md`](LIMITATIONS.md).

Known limit: context-dependent fragments ("yes add it to the plan", a UI
request with no project named) cannot be routed from the message alone — stage 1
must receive the recent turns as `state`, not just the current message.

---

## Files

| File | Purpose |
|---|---|
| `skill_router.json` | Stage-1 decision set — 12 domains + 3 flags |
| `classify_skills.py` | Classify every skill into a domain with Jev → `skill_domains.json` |
| `build_roster.py` | Build the roster from disk; measure the baseline cost |
| `stage2_router.py` | Domain map + stage-2 Jev choice + `--domains` listing |
| `measure_stage2.py` | Quality + token measurement |
| `diagnose.py` | Attribute each miss: label error vs prefilter vs stage 1 |
| `cache_cost_probe.py` | Measure billed cost: stable prefix vs varying prefix (live) |
| `LIMITATIONS.md` | Negative results and measured limits — read before building |
| `test_skill_router.py` | Curated 20-request set (stage 1) |
| `test_skill_router_real.py` | 17 real requests recovered from session history |
| `skill_domains.json` | Jev's 318 skill→domain labels |
| `skill_roster.json` | Generated roster (regenerate with `build_roster.py`) |

## Run it

```bash
export OPENROUTER_API_KEY=sk-or-v1-...     # same key as OpenRouter chat

python3 build_roster.py                    # offline: baseline numbers
python3 stage2_router.py --domains         # offline: domain membership
python3 classify_skills.py                 # re-classify all skills (live)
python3 test_skill_router.py               # stage-1 curated set (live)
python3 test_skill_router_real.py          # stage-1 real traffic (live)
CAP=40 python3 measure_stage2.py           # stage 2 quality + tokens (live)
python3 diagnose.py                         # offline: miss attribution
```

Requires the canonical client at
`~/.hermes/skills/openrouter-jev/scripts/jev_client.py`.

## Caveats

- Ground truth is hand-labelled on 11–20 cases. Small sample.
- The current model's own skill-pick accuracy was not directly measured; treat
  it as the upper bound since it reads the whole roster.
- Hex domains are a fixed taxonomy; a request spanning two domains routes to one.
- Token estimates use chars/4.
