#!/usr/bin/env python3
"""Stage 2 skill router: domain -> specific skill (Jev choice).

Deterministic domain map over the on-disk roster, lexical prefilter to cap
stage-2 candidates, then a Jev choice over the candidate skill descriptions.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "skills" / "openrouter-jev" / "scripts"))
from jev_client import ask_jev  # noqa: E402

SCRATCH = Path(__file__).resolve().parent
ROSTER = json.loads((SCRATCH / "skill_roster.json").read_text())
ROUTER_Q = json.loads((SCRATCH / "skill_router.json").read_text())

CAP = int(os.environ.get("CAP", "12"))  # max stage-2 candidates

JEV_LABELS = {}
_lbl = SCRATCH / "skill_domains.json"
if _lbl.exists():
    JEV_LABELS = json.loads(_lbl.read_text())

# category -> domain
CAT_MAP = {
    "clinical": "lab_clinical",
    "hermes-agent": "hermes_dev",
    "autonomous-ai-agents": "hermes_dev",
    "automation": "automation_cron",
    "data-pipelines": "automation_cron",
    "devops": "devops_infra",
    "mlops": "devops_infra",
    "software-development": "devops_infra",
    "content": "content_media",
    "creative": "content_media",
    "media": "content_media",
    "productivity": "office_files",
    "research": "research",
    "web": "research",
    "integration": "integration_mcp",
    "mcp": "integration_mcp",
    "email": "integration_mcp",
    "data-science": "rag_data",
    "python": "devops_infra",
    "google-workspace": "integration_mcp",
}

# name pattern overrides (checked in order, first hit wins)
NAME_RULES = [
    (r"sop", "lab_clinical"),
    (r"^clinical|clinical-|treatment-plans|iso-15|iso-13|laboratory", "lab_clinical"),
    (r"kit-insert|access-|beckman-|calcitonin|cortisol|apo-b|hmnr|igm-optilite|trop-t|imark|osmomat|remisol|pw40|vdc-bio", "lab_clinical"),
    (r"hermes|book-to-skill|autoskill|skill-|plugin|agent-skill|petdex|session-librarian|page-agent|pithagoras", "hermes_dev"),
    (r"composio|google-workspace|himalaya|sociamonials|hostinger|n8n|koofr|reddit|notebooklm|nlm|benchling|labarchive|omero|protocolsio|ginkgo|opentrons|pylabrobot|dnanexus|latchbio", "integration_mcp"),
    (r"indian-markets|best-stocks|index-funds|ccxt|tapetide|stock|market|fiscaldata|moneyprinter", "market_finance"),
    (r"me-skill|therapy|consciousness-council|what-if-oracle|noor-persona|biochem-persona|actualized-persona|spirituality|dhdna|caveman", "none"),
    (r"qdrant|rag|soffos|actualized|deep-rag|cellxgene|lamindb|anndata|polars|dask|vaex|analysis-catalog|jupyter", "rag_data"),
    (r"infographic|carousel|motion-graphics|generate-image|tts|audio|video|reel|linkedin|short-form|sepia|humanizer|blog|pexels|spotify|deepgram|image-prompt|video-prompt|html-to-video|design", "content_media"),
    (r"pubmed|paper|literature|citation|exa|tavily|bgpt|database-lookup|open-notebook|scholar|patent|movie-research|blogwatcher|context7|parallel-web|grounded|multi-source|wiki", "research"),
    (r"docx|pptx|xlsx|pdf|markitdown|latex|frosty|edu-ppt|nano-pdf|office|sheet-to", "office_files"),
    (r"cron|webhook|pipeline|monitor|daily-|brief", "automation_cron"),
    (r"biopython|scanpy|rdkit|pysam|pydeseq2|scvi|scvelo|arboreto|esm|gget|bioservices|deepchem|diffdock|molfeat|medchem|primekg|depmap|pytdc|glyco|histolab|pathml|flowio|matchms|pyopenms|bids|deeptools|geniml|gtars|tiledbvcf|etetoolkit|phylogen|pymatgen|openmm|molecular-dynamics|rowan|neurokit|pydicom|pyhealth|imaging-data|ginkgo", "bio_science"),
    (r"server|ssh|vps|vercel|container|s6|docker|deploy|openship|tailscale|termux|hermes-graphics|hermes-safe|hermes-upstream|kanban|leverage|local-model|runpod|modal|llama-cpp|huggingface|transformers|torch|dspy|outlines|pufferlib|stable-baselines|simpy|optimize-for-gpu|apple-silicon|nvidia|benchmark|cloud5|obliteratus", "devops_infra"),
    (r"astropy|astro|quantum|cirq|qiskit|pennylane|qutip|sympy|pymc|statsmodels|scikit|shap|networkx|matplotlib|seaborn|geopandas|geomaster|fluidsim|aeon|timesfm|umap|exploratory|statistical|hypothesis|scientific|scholar-evaluation|peer-review|research-grants|venue|latex-posters|iso-13485-certification|iso-15189-certification|market-research|treatment-plans|clinical-decision|clinical-reports|clinical-|citation-management|book-to-skill", "bio_science"),
]


def assign(skill: str, category: str) -> str:
    # Prefer the Jev-assigned label when the classification file exists.
    if skill in JEV_LABELS:
        return JEV_LABELS[skill]
    if category == ".archive":
        return "none"
    s = skill.lower()
    for pat, dom in NAME_RULES:
        if re.search(pat, s):
            return dom
    if category in CAT_MAP:
        return CAT_MAP[category]
    return "none"


def build_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for r in ROSTER:
        if not r["description"]:
            continue
        dom = assign(r["skill"], r["category"])
        idx.setdefault(dom, []).append(r)
    for dom in idx:
        idx[dom].sort(key=lambda r: r["skill"])
    return idx


def lexical_score(request: str, skill: str, desc: str) -> int:
    words = set(re.findall(r"[a-z]{3,}", request.lower()))
    hay = (skill + " " + desc).lower()
    return sum(1 for w in words if w in hay)


def pick_candidates(request: str, skills: list[dict]) -> list[dict]:
    if len(skills) <= CAP:
        return skills
    ranked = sorted(skills, key=lambda r: -lexical_score(request, r["skill"], r["description"]))
    return ranked[:CAP]


def route(request: str) -> dict:
    s1 = ask_jev({"request": request}, ROUTER_Q)
    a = s1["answers"]["domain"]
    domain = a["choice"]

    skills = INDEX.get(domain, [])
    if domain == "none" or not skills:
        return {"request": request, "domain": domain, "conf1": a.get("confidence"),
                "skill": None, "top3": [], "n_cand": 0,
                "tokens": (s1.get("usage") or {}).get("input_tokens", 0),
                "cost": (s1.get("usage") or {}).get("cost", 0)}

    cands = pick_candidates(request, skills)
    criteria = {r["skill"]: r["description"][:220] for r in cands}
    q2 = {"skill": {
        "type": "choice",
        "instructions": "Which skill from the roster best fits `request`?",
        "criteria": criteria,
    }}
    s2 = ask_jev({"request": request}, q2)
    a2 = s2["answers"]["skill"]
    probs = a2.get("probabilities", {})
    u1, u2 = s1.get("usage") or {}, s2.get("usage") or {}
    return {
        "request": request, "domain": domain, "conf1": a.get("confidence"),
        "skill": a2["choice"], "conf2": a2.get("confidence"),
        "top3": sorted(probs.items(), key=lambda kv: -kv[1])[:3],
        "n_cand": len(cands),
        "tokens": (u1.get("input_tokens", 0) + u2.get("input_tokens", 0)
                   + u1.get("output_tokens", 0) + u2.get("output_tokens", 0)),
        "cost": (u1.get("cost", 0) or 0) + (u2.get("cost", 0) or 0),
    }


INDEX = build_index()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--domains":
        for dom, skills in sorted(INDEX.items()):
            print(f"\n=== {dom} ({len(skills)}) ===")
            for r in skills:
                print(f"  {r['skill']:46s} [{r['category']}]")
    else:
        req = " ".join(sys.argv[1:]) or "audit the albumin SOP against the kit insert"
        print(json.dumps(route(req), indent=2))
