#!/usr/bin/env bash
# Mirror the canonical Hermes skill into this repo. ONE-WAY: skill -> repo.
#
# The skill at ~/.hermes/skills/openrouter-jev is the single source of truth.
# This repo is the published mirror (plus tests, examples, README, AGENTS.md, CI).
# Never hand-edit scripts/ or docs/ here — edit the skill and re-run this.
#
#   ./sync.sh           copy the skill in and refresh MANIFEST.sha256
#   ./sync.sh --check   verify the working tree matches the manifest (no writes)
#
# CI runs the --check equivalent via `sha256sum -c MANIFEST.sha256`.

set -euo pipefail

SKILL="${JEV_SKILL_DIR:-$HOME/.hermes/skills/openrouter-jev}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRRORED=(scripts/jev_client.py docs/design.md docs/api.md docs/recipes.md)

die() { printf 'sync: %s\n' "$1" >&2; exit 1; }

[ -d "$SKILL" ] || die "canonical skill not found at $SKILL (set JEV_SKILL_DIR to override)"
[ -f "$SKILL/scripts/jev_client.py" ] || die "$SKILL has no scripts/jev_client.py"

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
find "$SKILL" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$REPO/scripts/decisions" "$REPO/docs"
install -m 644 "$SKILL/scripts/jev_client.py" "$REPO/scripts/jev_client.py"
cp "$SKILL"/scripts/decisions/*.json "$REPO/scripts/decisions/"
cp "$SKILL"/references/design.md "$REPO/docs/design.md"
cp "$SKILL"/references/api.md    "$REPO/docs/api.md"
cp "$SKILL"/references/recipes.md "$REPO/docs/recipes.md"

# Refresh the manifest for the files that are exact mirrors of the skill.
cd "$REPO"
: > MANIFEST.sha256
for f in "${MIRRORED[@]}"; do sha256sum "$f" >> MANIFEST.sha256; done

echo "sync: mirrored from $SKILL"
sha256sum -c --quiet MANIFEST.sha256 && echo "sync: manifest verified"
printf 'sync: %s mirrored files, %s decisions\n' \
  "${#MIRRORED[@]}" "$(find scripts/decisions -name '*.json' | wc -l)"
git status --short 2>/dev/null || true
