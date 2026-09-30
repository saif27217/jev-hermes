#!/usr/bin/env python3
"""Compare two options from their spec sheets and report which is better for a goal.

The `option_pick` set is generic: give it a `goal`, an `option_a` and an
`option_b`, and it returns the same nine judgements for routers, phones,
reagents, instruments, anything you would otherwise argue about in prose.

Runs on the free, keyless Zen endpoint - no key, no account:

    python3 examples/05_compare_options.py

The worked case is real: two AX1500 routers, which one reaches a dead-zone
bedroom. See docs/comparison.md for how to read the output.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "opencode" / "scripts"))

from jev_client import ask_jev, load_decision, print_decision  # noqa: E402

# --- state: name the parts. Questions read `goal`, `option_a`, `option_b` -------------
STATE = {
    "goal": "long-distance / long-range home Wi-Fi coverage",
    "option_a": {
        "name": "TP-Link Archer AX12 (AX1500)",
        "specs": "Wi-Fi 6 dual-band, 5GHz 1201 / 2.4GHz 300 Mbps, "
                 "4 external antennas (gain not stated), OFDMA+MU-MIMO+Beamforming, "
                 "WPA3, 1x Gb WAN + 3x Gb LAN, EasyMesh support, AP mode",
    },
    "option_b": {
        "name": "Tenda RX2 Pro (AX1500)",
        "specs": "Wi-Fi 6 dual-band, 5GHz 1201 / 2.4GHz 300 Mbps, "
                 "5x 6 dBi external antennas, OFDMA+MU-MIMO+Beamforming, "
                 "WPA3, 1x Gb WAN + 3x Gb LAN, no mesh/EasyMesh/extender listed",
    },
    "context": "House layout, wall material and distance to the far room are all unknown.",
}

# --- one request, every question. Never loop. ----------------------------------------
body = ask_jev(STATE, load_decision("option_pick"))
answers = body["answers"]

print(f"cost={body['cost']}  usage={body['usage']}\n")
print_decision(body)

# --- read in the order that matters ---------------------------------------------------
# 1. Is the data even enough to answer? If not, say so and stop.
if answers["specs_sufficient"]["noul"] < 0.5:
    print("\n! Spec sheets do not settle this - the winner below is on stated specs only,")
    print("  not measured performance. Say that when you report it.")

# 2. Same marketing numbers? Then the decision rests on secondary features.
if answers["headline_specs_equal"]["noul"] > 0.5:
    print("! Headline specs are identical - this turns on features, not speed figures.")

# 3. One box vs the long run. They legitimately disagree; report both.
print(f"\nbest single unit : {answers['winner_single']['choice']} "
      f"(conf {answers['winner_single']['confidence']})")
print(f"best buy overall : {answers['winner_purchase']['choice']} "
      f"(conf {answers['winner_purchase']['confidence']})")

# 4. Scores: direction only. A gap under ~0.5 is inside wording noise.
a, b = answers["a_score"]["score"], answers["b_score"]["score"]
verdict = "A" if a - b > 0.5 else "B" if b - a > 0.5 else "too close to call"
print(f"score gap        : {a:.2f} vs {b:.2f} -> {verdict}")

if answers["goal_needs_scaling"]["noul"] > 0.5 and answers["a_expansion_path"]["noul"] > 0.5:
    print("! The goal needs scaling and one option has the expansion path - weight that")
    print("  above the spec edge. This is usually the real decision.")
