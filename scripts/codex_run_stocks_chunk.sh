#!/usr/bin/env bash
# Run a slice of an industry's stocks via codex.
#
# Usage:
#   codex_run_stocks_chunk.sh <INDUSTRY> <COUNT> [reverse|forward]
#
# - <COUNT>: how many stocks to process from the chosen end.
# - reverse (default): take from end of `ls | sort -r` so this worker meets
#   the in-flight forward dispatch.sh in the middle (prompt_gen will skip
#   already-filled overlays).

set -euo pipefail

IND="$1"
COUNT="${2:-9999}"
ORDER="${3:-reverse}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON=".venv/bin/python"
PROMPT_DIR=/tmp/codex_prompts
mkdir -p "$PROMPT_DIR"

DIR="config/stock_overlays/$IND"
if [ ! -d "$DIR" ]; then
  echo "no overlay dir: $DIR" >&2; exit 1
fi

if [ "$ORDER" = "reverse" ]; then
  LIST=$(ls "$DIR"/*.yaml | sort -r | head -"$COUNT")
else
  LIST=$(ls "$DIR"/*.yaml | sort | head -"$COUNT")
fi

for f in $LIST; do
  TS=$(basename "$f" .yaml)
  OUT="$PROMPT_DIR/stock_${IND}_${TS}.md"
  $PYTHON scripts/codex_prompt_gen.py --industry "$IND" --ts-code "$TS" --out "$OUT" || continue
  if grep -q "✅ 已全部填完" "$OUT"; then
    echo "[$ORDER $(date +%H:%M:%S)] ✓ skip $IND/$TS (filled)"
    continue
  fi
  echo "[$ORDER $(date +%H:%M:%S)] → $IND / $TS"
  scripts/codex_run_prompt.sh "$OUT" || echo "  ⚠ codex failed for $TS"
done

echo "[$ORDER $(date +%H:%M:%S)] DONE $IND"
