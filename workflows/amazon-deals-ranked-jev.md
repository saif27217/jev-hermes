---
name: amazon-deals-ranked-jev
description: "Use when ranking product deals by value-to-cost."
---

# amazon-deals-ranked-jev

Extract Amazon product pages via Termux Browser Pilot, score value-to-cost via Jev decisions API, deliver ranked results.

## Pipeline

### 1. Extract (Termux Browser Pilot) — frequency-based price extraction

- Start daemon: `ssh -p 8022 <termux_host> "~/termux-browser-pilot/start-daemon.sh"`
- Navigate: `cli.py goto <url> --json` → captures title + ASIN
- Wait 8-10s for JS render (product detail pages need more than search pages)
- **Extract text ON THE PHONE** — `cli.py text | grep <product_keywords> | head -30 > extracted/<name>.txt`
- Only ~1-2KB per product comes back (not full HTML)
- Pull all files in one SSH call at the end
- Key: filter with product-relevant keywords (₹, MB/s, GB, TB, USB, warranty, speed, specs...) AND exclude navigation noise (Cart, Account, Delivery, Menu...)
- Works on Amazon bot-protection pages — rendered text includes product content
- Prices come from rendered text (₹ patterns), titles from goto JSON
- Amazon URLs may redirect — verify product name matches expected

**Price extraction strategy (learned 2026-10-07):**

| Method | How it works | Pitfall |
|--------|-------------|---------|
| **Percent savings anchor** (`₹X with N% savings`) | Picks first matching line | Ads/recommendations inject fake prices — hijacks the anchor |
| **First price** (first ₹>=150) | Simple, fast | Fails when MRP > deal price (picks MRP first) |
| **Frequency-based** ✅ | Count all prices, pick most frequent ≥150 | Fails when MRP appears more often than deal price (rare) |

**Recommended:** frequency-based as primary, first-price as fallback. Verify edge cases manually.

Frequency extraction pattern (bash):
```bash
txt=$(python3 cli.py text 2>/dev/null)
price=$(echo "$txt" | grep -E '₹[0-9]' | grep -vE '/ count|per count|per month|Warranty|warranty|Extended' | \
    grep -oE '₹[0-9][0-9,]*' | tr -d '₹,' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
```

### 2. Score (Jev Decisions API) — 4-lens methodology

- Endpoint: `POST https://openrouter.ai/api/alpha/decisions`
- Fallback: `POST https://opencode.ai/zen/v1/systemone` (free, keyless, can be down)
- Auth: `Authorization: Bearer $OPENROUTER_API_KEY`
- Model: `typesafe/jev-1.13`

**4 scoring lenses per product:**
1. **Investment** — value retention, durability, warranty, long-term cost per use
2. **Productivity** — time saved, workflow improvement, efficiency gains
3. **Use-case fit** — how well it solves its specific problem
4. **Scarcity** — discount % vs MRP, deal quality, price advantage

Composite = average of 4 lenses. BUY ≥ 6.5, MAYBE ≥ 5, PASS < 5.

**Payload format (critical):**
```json
{
  "model": "typesafe/jev-1.13",
  "state": {"products": [{"name": "...", "price": 100, "mrp": 200, "discount": 50, "specs": "...", "use_case": "..."}]},
  "questions": {
    "product_lens": {
      "type": "score",
      "instructions": "Product: RsX (MRP RsY, Z% off), specs... Use case: ... Rate from <lens>.",
      "criteria": [
        {"key": "1", "description": "worst"},
        {"key": "3", "description": "poor"},
        {"key": "5", "description": "moderate"},
        {"key": "7", "description": "good"},
        {"key": "9", "description": "best"}
      ]
    }
  }
}
```

- All questions in ONE request (parallel, shared state)
- 56 questions (4 lenses × 14 products) ≈ 14K in tokens, $0.0006, 0.8s
- `criteria` must be **array of objects**, NOT a string
- Score levels 0-4 → 1-10 scale: `(level / 4.0) * 8 + 1`

### 3. Rank (Python)

- Compute composite = mean of 4 lens scores
- Sort descending
- Group by category to identify lens winners
- Save JSON with model, cost, per-lens scores, composite

## Key pitfalls

- `/tmp` doesn't exist on Termux — use `~/` or `~/termux-browser-pilot/`
- Full HTML dumps are wasteful — grep-on-phone keeps tokens minimal
- Amazon bot-protection: `productTitle`, `a-offscreen` selectors may not match — use rendered text + grep
- Amazon URLs may redirect to different products — verify title matches
- `jev_client.py` exists in both `openrouter-jev` and `jev-opencode` skills — use `importlib.util.spec_from_file_location` to load the correct one
- Zen free tier can return 422 — fall back to OpenRouter
- Duplicate entries in product list inflate question count — deduplicate before scoring
