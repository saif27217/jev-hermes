# LIMITATIONS

Negative results and measured limits of the Jev skill-routing approach.
Written so nobody rebuilds this without reading the numbers first.

Everything below is measured on this machine, on `openrouter-shark` →
`deepseek/deepseek-v4.1-flash` via `https://openrouter.ai/api/v1`, with
`prompt_caching: cache_ttl: 5m` enabled.

---

## 1. Prompt caching kills the headline saving

The router's case rests on "81% fewer tokens per turn". That is a **raw-token**
number. Billing does not follow it, because the skill roster sits in a
**stable, cacheable prefix** while a routed shortlist does not.

Measured (`cache_cost_probe.py`):

| Prefix | prompt tokens | cached tokens | billed cost |
|---|---|---|---|
| Full roster, cold | 13,898 | 0 | $0.004173 |
| Full roster, warm | 13,900 | 13,824 | **$0.000112** |
| Domain shortlist, varying | 200–2,973 | **0** | $0.00006–$0.0009 |

- A cache hit is **37× cheaper** (97.3% off): ~$0.30/M cold vs ~$0.0081/M cached.
- **Every** varying shortlist call missed the cache (`cached=0`).

### Effect on the per-turn bill

| Approach | per-turn billed |
|---|---|
| Baseline, warm roster | $0.000112 |
| Hybrid (Jev stage 1 $0.00006 + cached shortlist ~$0.00002) | $0.00008 |

Real saving: **~30%**, not 81%. The Jev call alone costs about **half** of the
prefix it replaces.

### Where it inverts

A **domain flip** between turns forces the shortlist prefix to change → cache
miss → that turn costs **$0.0003–$0.0009**, i.e. **3–8× more expensive** than
the cached roster.

---

## 2. The roster is not the cost problem

Because the roster caches at 37× off, it is effectively free after the first
turn. Optimising it is low ROI. The real per-turn cost is the **uncached,
growing conversation history** — which Hermes already attacks via compression.

If roster savings are still wanted, the correct lever is **shortening the
roster content itself** (prune dead skills, trim verbose descriptions): a
one-time edit, no new dependency, no latency, no miss risk.

---

## 3. Stage 2 (Jev picks the exact skill) is unreliable

| Metric | CAP=12 | CAP=40 |
|---|---|---|
| Skill recall@1 | 64% | 73% |
| Skill recall@3 | 73% | 82% |

Raising the candidate window from 12 to 40 improved recall — so the bottleneck
is the **lexical prefilter that trims candidates before Jev sees them**, not Jev
itself. The rest of the errors were skill→domain mislabels and stage-1 domain
misses, and near-duplicate skills Jev cannot separate (`soffos-rag` vs
`qdrant-rag`).

**Conclusion: do not use Jev to pick the exact skill.** Hand the domain
shortlist to the model instead.

---

## 4. Stage 1 (domain) limits

- **Fragments fail.** Context-dependent continuations ("Yes add it as well to
  the plan") have no standalone domain signal. The reel-view request routed at
  **confidence 0.32** — wrong. In production stage 1 must receive the recent
  turns as `state`, not the single message.
- **Alpha endpoint.** Routing depends on `POST /api/alpha/decisions` on every
  turn. If it changes, rate-limits, or the key lapses, skill routing breaks.
  Baseline needs no network for selection.
- **Calibration must be respected.** Low confidence tracks the misses (0.32,
  0.47, 0.50). Ignoring it converts uncertain routes into silent wrong routes.
- **Cost/latency, always.** ~1,671 tokens and ~0.4 s added to every turn, even
  when no skill is needed.

---

## 5. Silent-miss failure mode

The current system cannot invisibly skip a skill: the model sees the whole
roster. A domain-miss silently yields the wrong skill or none — neither the
model nor the user is told. This is a **new** failure mode, and it is the
strongest argument against the hybrid.

Safe only with **fail-open routing** (low confidence or `JevError` → inject the
full roster) **plus route logging** (domain, confidence, shortlist, outcome).

---

## 6. Taxonomy maintenance

- 12 domains must be kept current; every new skill needs reclassification or it
  lands in `none` and becomes invisible.
- Real mislabels observed: `plan` → `hermes_dev`, while the request routed to
  `devops_infra`.
- 69 of 318 classifications came back below 0.6 confidence — mostly archived or
  genuinely ambiguous skills.

---

## 7. Benchmark caveats

- Ground truth is hand-assigned judgement on 11–20 cases, not an external
  reference. Two of the four stage-2 "misses" are debatable
  (`composio-mcp` vs `composio-google-docs`; `soffos-rag` vs `qdrant-rag`).
- The domain map is heuristic.
- Baseline skill-pick accuracy was **not** directly measured; the model reads
  100% of the roster, so treat it as the accuracy upper bound.
- Caching measured on **one** provider/model/trial. Other models price caching
  differently; results may not generalise.
- Cold-start cost ($0.004) is why the hybrid still wins on *short* chats and
  loses on steady state.

---

## Verdict

**Do not build the hybrid.** Best case ~30% cheaper with added latency and a
new silent failure mode; worst case (domain flips) 3–8× more expensive. The
token win was real; the money win mostly evaporates under prompt caching.

Keep, if anything: **stage 1 domain routing only**, with fail-open thresholds
and route logging — never Jev stage 2.
