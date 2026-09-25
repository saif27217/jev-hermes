#!/usr/bin/env python3
import json, os, urllib.request, pathlib, sys, time

KEY = os.environ["OPENROUTER_API_KEY"]
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
D = pathlib.Path(__file__).resolve().parent

roster = json.loads((D / "skill_roster.json").read_text())
ROSTER = "SKILL ROSTER\n" + "\n".join(
    f"- {r['skill']}: {r['description']}" for r in roster if r["description"]
)
labels = json.loads((D / "skill_domains.json").read_text())
doms = sorted(set(labels.values()))


def shortlist(dom):
    rs = [r for r in roster if r["description"] and labels.get(r["skill"]) == dom]
    return f"SKILL SHORTLIST [{dom}]\n" + "\n".join(
        f"- {r['skill']}: {r['description']}" for r in rs
    )


def call(prefix, user):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prefix},
            {"role": "user", "content": user},
        ],
        "max_tokens": 5,
        "temperature": 0,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def probe(name, prefixes):
    print(f"\n=== {name} ===")
    tot = 0.0
    for i, (pfx, user) in enumerate(prefixes):
        t = time.time()
        try:
            resp = call(pfx, user)
        except Exception as e:
            print(f"  call {i+1}: ERROR {e}")
            continue
        u = resp.get("usage", {}) or {}
        det = u.get("prompt_tokens_details") or {}
        cached = det.get("cached_tokens", u.get("cached_tokens"))
        cost = u.get("cost")
        tot += cost or 0
        print(
            f"  call {i+1}: prompt={u.get('prompt_tokens')} cached={cached} "
            f"completion={u.get('completion_tokens')} cost=${cost} ({time.time()-t:.1f}s)"
        )
    print(f"  TOTAL cost: ${tot:.6f}")


msgs = ["say ok", "say ok 2", "say ok 3"]
probe("STABLE prefix (full roster x3)", [(ROSTER, m) for m in msgs])
probe("VARYING prefix (different shortlist each call)",
      [(shortlist(doms[i % len(doms)]), msgs[i % len(msgs)]) for i in range(len(doms))])
