#!/usr/bin/env bash
# Mirror the canonical Hermes skills into this repo. ONE-WAY: skill -> repo.
#
# Two providers, each with its own canonical skill directory:
#   openrouter-jev  ->  scripts/  docs/            (paid, alpha endpoint)
#   jev-opencode    ->  opencode/                 (free, keyless, systemone endpoint)
#
# The skills are the single sources of truth. This repo is the published mirror
# (plus tests, README, AGENTS.md, CI). Never hand-edit mirrored paths here —
# edit the skill and re-run this.
#
#   ./sync.sh           copy both skills in and refresh MANIFEST.sha256
#   ./sync.sh --check   verify the working tree matches the manifest (no writes)
#
# CI runs the --check equivalent via `sha256sum -c MANIFEST.sha256`.

set -euo pipefail

OR_SKILL="${JEV_SKILL_DIR:-$HOME/.hermes/skills/openrouter-jev}"
OC_SKILL="${JEV_OPENCODE_SKILL_DIR:-$HOME/.hermes/skills/jev-opencode}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { printf 'sync: %s\n' "$1" >&2; exit 1; }

for d in "$OR_SKILL" "$OC_SKILL"; do
  [ -d "$d" ] || die "canonical skill not found at $d (set JEV_SKILL_DIR / JEV_OPENCODE_SKILL_DIR)"
  [ -f "$d/scripts/jev_client.py" ] || die "$d has no scripts/jev_client.py"
done

# Relative paths recorded in MANIFEST.sha256, per provider.
OR_MIRRORED=(scripts/jev_client.py docs/design.md docs/api.md docs/recipes.md
             docs/comparison.md)
OC_MIRRORED=(opencode/scripts/jev_client.py opencode/docs/design.md
             opencode/docs/api.md opencode/docs/recipes.md
             opencode/docs/comparison.md)

if [ "${1:-}" = "--check" ]; then
  cd "$REPO"
  [ -f MANIFEST.sha256 ] || die "no MANIFEST.sha256; run ./sync.sh first"
  if sha256sum -c --quiet MANIFEST.sha256; then
    echo "sync: clean — mirror matches MANIFEST.sha256"
  else
    die "mirror is stale or hand-edited. Re-run ./sync.sh and commit."
  fi
  exit 0
fi

# Clear caches so they cannot be mirrored or committed.
find "$OR_SKILL" "$OC_SKILL" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

mirror() {  # mirror <skill> <outdir-for-scripts> <outdir-for-docs>
  local skill="$1" sdir="$2" ddir="$3"
  mkdir -p "$sdir/decisions" "$ddir"
  install -m 644 "$skill/scripts/jev_client.py" "$sdir/jev_client.py"
  cp "$skill"/scripts/decisions/*.json "$sdir/decisions/"
  cp "$skill"/references/design.md  "$ddir/design.md"
  cp "$skill"/references/api.md     "$ddir/api.md"
  cp "$skill"/references/recipes.md "$ddir/recipes.md"
  cp "$skill"/references/comparison.md "$ddir/comparison.md"
}

mirror "$OR_SKILL" scripts   docs
mirror "$OC_SKILL" opencode/scripts opencode/docs

# Refresh the manifest: every mirrored file, including the decision sets, so a
# hand-edited question set fails CI instead of drifting quietly.
cd "$REPO"
: > MANIFEST.sha256
# Explicit, deterministic list — no globbing surprises.
{
  for f in "${OR_MIRRORED[@]}"; do printf '%s\n' "$f"; done
  for f in scripts/decisions/*.json; do printf '%s\n' "$f"; done
  for f in "${OC_MIRRORED[@]}"; do printf '%s\n' "$f"; done
  for f in opencode/scripts/decisions/*.json; do printf '%s\n' "$f"; done
} | sort -u | while read -r f; do
  [ -f "$f" ] || die "expected mirrored file missing: $f"
  sha256sum "$f"
done >> MANIFEST.sha256

echo "sync: mirrored"
echo "  from $OR_SKILL -> scripts/, docs/"
echo "  from $OC_SKILL -> opencode/scripts/, opencode/docs/"
sha256sum -c --quiet MANIFEST.sha256 && echo "sync: manifest verified"
printf 'sync: %s mirrored files, %s openrouter decisions, %s opencode decisions\n' \
  "$(wc -l < MANIFEST.sha256)" \
  "$(find scripts/decisions -name '*.json' | wc -l)" \
  "$(find opencode/scripts/decisions -name '*.json' | wc -l)"
git status --short 2>/dev/null || true
