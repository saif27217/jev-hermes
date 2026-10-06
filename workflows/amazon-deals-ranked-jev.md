---
name: amazon-deals-ranked-jev
description: "Use when ranking product deals by value-to-cost."
version: "1.0.0"
author: "saif27217"
license: "MIT"
metadata:
  hermes:
    tags: ["deals", "ranking", "jev", "termux-browser-pilot", "extraction"]
    related_skills: ["openrouter-jev", "jev-opencode", "termux-browser-pilot"]
---

# amazon-deals-ranked-jev

Extract product pages via Termux Browser Pilot, score value-to-cost via Jev decisions API, deliver ranked results.

## Pipeline

### 1. Extract (Termux Browser Pilot)

- Start daemon on Termux device (SSH access required)
- Navigate in batches of 5: `cli.py goto <url> --json` → captures title + ASIN
- Dump HTML: `cli.py html` → `~/data_N.html` (NOT `/tmp` — doesn't exist on Termux)
- Extract prices: regex `₹` patterns from `cli.py text` output
- Sleep 5s between pages for JS render
- Supplement specs via web search when Amazon HTML lacks them (bot-protection blocks standard selectors)

### 2. Score (Jev Decisions API)

- Endpoint: `POST https://openrouter.ai/api/alpha/decisions`
- Fallback: `POST https://opencode.ai/zen/v1/systemone` (free, keyless, can be down)
- Auth: `Authorization: Bearer $OPENROUTER_API_KEY`
- Model: `typesafe/jev-1.13`

**Payload format (critical):**
```json
{
  "model": "typesafe/jev-1.13",
  "state": {"products": [{"name": "...", "price": 100, "specs": "..."}]},
  "questions": {
    "product_key_value": {
      "type": "score",
      "instructions": "Product: RsX, specs... Rate value-to-cost.",
      "criteria": [
        {"key": "1", "description": "worst_value"},
        {"key": "3", "description": "poor_value"},
        {"key": "5", "description": "moderate_value"},
        {"key": "7", "description": "good_value"},
        {"key": "9", "description": "best_value"}
      ]
    }
  }
}
```

- All questions in ONE request (parallel, shared state)
- 15 questions ≈ 4150 in tokens, $0.000174, 0.5s
- `criteria` must be **array of objects**, NOT a string
- Score levels 0-4 → 1-10 scale: `(level / 4.0) * 8 + 1`

### 3. Rank (Python)

- Convert levels, sort descending
- Verdicts: BUY ≥ 6, MAYBE ≥ 4, PASS < 4
- Group by category to identify winners
- Save JSON with model, cost, ranked list

## Key pitfalls

- `/tmp` doesn't exist on Termux — use `~/` or `~/termux-browser-pilot/`
- Amazon bot-protection: `productTitle`, `a-offscreen` selectors may not match — use `goto --json` for titles
- `jev_client.py` exists in both `openrouter-jev` and `jev-opencode` skills — use `importlib.util.spec_from_file_location` to load the correct one
- Zen free tier can return 422 "Endpoint is unavailable" — fall back to OpenRouter
- SSH stdin redirect to Termux files doesn't always work — write scripts remotely

## Example output

```
Model: typesafe/jev-1.13-20260917
Cost: $0.000174
1. [BUY  ] 7.8/10 (level 3.41, conf 0.57) — Rs948 — Ugreen 2.5 HDD Enclosure (basic)
2. [BUY  ] 7.8/10 (level 3.41, conf 0.57) — Rs399 — Portronics Mport 30 Plus
3. [BUY  ] 7.5/10 (level 3.23, conf 0.69) — Rs2,699 — Cpplus E31Q CCTV
...
15. [MAYBE] 4.4/10 (level 1.69, conf 0.27) — Rs19,407 — Ugreen 80Gbps NVMe Enclosure
```
