# Jev on OpenCode Zen — API Reference

Everything here was measured live against `https://opencode.ai/zen/v1/systemone` (Sept 2026).

## Endpoint

```
POST https://opencode.ai/zen/v1/systemone
```

**This is not `/v1/chat/completions`.** Jev is a *System One* model, not a chat model. Posting a
`jev-*` id to the chat endpoint returns **HTTP 500** (`{"type":"error","error":{"message":"Internal
server error"}}`) on every attempt — streaming, with or without `max_tokens`, with attribution
headers. The id *is* listed by `GET /zen/v1/models`, and Zen's own docs table maps jev to
`/zen/v1/systemone` with AI SDK package `-`, so it will look selectable and fail on use.

Hermes has no `systemone` adapter (the `opencode-zen` model-provider plugin only sets
`base_url` plus reasoning translations), so a jev model cannot be a Hermes session model. Call
it from code.

## Authentication

**None required for `jev-1.13-free`.** Send no `Authorization` header at all.

Sending a *bogus or placeholder* bearer is worse than sending nothing: `Bearer ***` returns
**401 `AuthError: Invalid API key.`** even on the free model. An empty `Bearer ` is ignored and
returns 200. So:

- `OPENCODE_ZEN_API_KEY` unset, empty, or a placeholder → omit the header.
- A real key is sent if present; a 401 then retries keyless automatically.

## Request format

Top-level `model`, `state`, `questions` — **not** nested under a wrapper.

```json
{
  "model": "jev-1.13-free",
  "state": "Lab SOP audit: VDC/BIO/128 Serum Osmolality against the osmometer manual",
  "questions": {
    "question_name": {
      "type": "choice" | "noul" | "score",
      "instructions": "What to decide",
      "criteria": "type-specific"
    }
  }
}
```

### Field: `model`

| Value | Meaning |
|-------|---------|
| `jev-1.13-free` | **Free, keyless.** `cost: "0"`. Use this. |
| `jev-1.13` | Paid, $0.042/1M input. Returns `402 Insufficient account funds` with no workspace credits. |

Zen has no `~jev-latest` rolling alias; the version is in the id.

### Field: `state`

String, object, or array — same as OpenRouter. Verified working on both:

- plain string: `"Payouts failed 3 days"`
- structured object with backticked paths: `{"policy": "…", "ticket": {"note": "…"}}` and
  `instructions: {"question": "…", "inspect": "`ticket.draft`", "focus": "…"}`

### Field: `questions`

A record of question definitions, keyed by your variable name. Every question sees the same
`state`, is answered **independently**, and runs **in parallel**. Verified: three mixed-type
questions in one request took 1.19s total.

## Question types

### `choice`

```json
{"type": "choice", "instructions": "Which document class is the source of truth?",
 "criteria": {"sop": "Lab SOP", "kit": "Kit insert / IFU", "manual": "Operator manual"}}
```

Response — same shape as OpenRouter:

```json
{"type": "choice", "choice": "manual", "confidence": 0.36,
 "probabilities": {"kit": 0.04, "manual": 0.57, "sop": 0.39}}
```

A single-criterion `choice` is accepted (returns `confidence: 1`), though it is pointless —
prefer a `noul`.

### `noul`

```json
{"type": "noul", "instructions": "Was a patient result released on this lot?",
 "criteria": {"true": "A patient result was reported from this run.",
              "false": "Only controls were run; no patient sample was tested."}}
```

Response: `{"type": "noul", "noul": 0.16}` — no `confidence` field, same as OpenRouter.

### `score`

Levels may be strings **or** objects with `what`/`signals`. Verified both; `legend` echoes
whatever you passed.

```json
{"type": "score", "instructions": "How severe if a patient result was released?",
 "criteria": ["Low", "Medium", "High", "Critical"]}
```

Response:

```json
{"type": "score", "score": 2.48, "confidence": 0.48,
 "legend": {"0": "Low", "1": "Medium", "2": "High", "3": "Critical"},
 "probabilities": {"0": 0.01, "1": 0.04, "2": 0.41, "3": 0.54}}
```

`score` is a **float** position (probability-weighted), so compare with `>=`, never `==`.

**`criteria` is REQUIRED for `score`** (and for `choice`). Omitting it is not a warning —
the upstream returns **422 `Endpoint is unavailable`**, which reads like an outage and is
not one. Measured: 5/5 attempts failed with a `criteria`-less `score`, while `noul` and
`choice` in the same second succeeded.

## Response format

```json
{
  "model": "jev-1.13-free",
  "answers": { "q": { ... } },
  "usage": {"input_tokens": 440, "output_tokens": 69},
  "cost": "0"
}
```

**`cost` is a top-level string, not a member of `usage`** — that is a Zen difference from
OpenRouter, where cost lives in `usage`. There is no `id` and no `provider` field on this
endpoint. Parse it with `float(body["cost"])`.

## Errors

| Code | Body | Meaning | Fix |
|------|------|---------|-----|
| 400 | `{"detail":{"error_type":"api_usage_error"}}` | unknown question `type` | use `choice`/`score`/`noul` |
| 401 | `{"error":{"type":"AuthError","message":"Invalid API key."}}` | bad or placeholder bearer | drop the header (free model) |
| 401 | `{"error":{"type":"ModelError","message":"Model jev-9.9 is not supported"}}` | bad model id | use `jev-1.13-free` |
| 402 | `Insufficient account funds` | paid model, no credits | use the free model |
| 422 | `Upstream request failed: Endpoint is unavailable.` | empty `questions`; missing `state`; **or a `score` with no `criteria`** | give `score` its `criteria` array — this is the common one |
| 403 | `FreeTierError: … can only be used from within OpenCode` | *other* free models, not jev | jev is not affected; others are client-gated |

A 401 is worth one keyless retry, since a stale env key must not break a free call. 400/401/422
are otherwise returned immediately — retrying a malformed payload only burns time.

Cloudflare blocks the default `Python-urllib/3.x` user agent on this host with `HTTP 403
error code: 1010`. The client sets an explicit `User-Agent`; any hand-rolled call must too.

## Pricing

| Model | Input | Output | Cached read |
|-------|-------|--------|-------------|
| `jev-1.13-free` | Free | Free | Free |
| `jev-1.13` | $0.042/1M | Free | — |

Free is unconditional on the response (`"cost": "0"`), and the docs describe it as a
limited-time offer. Do not build a dependency that assumes it stays free.

## Measured behaviour

Latency on this host: **0.89–1.20s** per request (OpenRouter's jev is ~0.24s), input tokens
271–440 for typical 1–3 question sets. Context window 32K.

## Privacy

Zen's privacy page: models are hosted in the US with zero-retention and no training — **except**
during their free periods, where collected data may be used to improve the model. `jev-1.13-free`
falls in that category. Keep states de-identified.
