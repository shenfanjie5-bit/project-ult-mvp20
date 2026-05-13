#!/usr/bin/env bash
# Batch driver for codex CLI to fill all overlays.
#
# Two phases:
#   1. industry overlays first (12 active industries, fills 14 L0 fields each)
#   2. company overlays after (353 stocks, fills 18 L1-L5 fields each)
#
# Per overlay we generate a self-contained prompt to /tmp, then invoke codex.
# `CODEX_CMD` env var lets the operator pick how codex is launched:
#
#   CODEX_CMD="codex --prompt-file"   (default; codex reads file)
#   CODEX_CMD="codex chat"             (pipe prompt via stdin)
#   CODEX_CMD="echo"                   (dry-run; just prints prompt path)
#
# Usage:
#   ./scripts/codex_dispatch.sh                         # phase 1 + 2
#   ./scripts/codex_dispatch.sh --industry-only         # phase 1 only
#   ./scripts/codex_dispatch.sh --company-only          # phase 2 only
#   ./scripts/codex_dispatch.sh --industry AI_COMPUTE   # one industry + its companies
#   CODEX_CMD=echo ./scripts/codex_dispatch.sh          # dry run
#
# Idempotent: each overlay prompt skips clean (data_status != Unknown) nodes;
# overlays already fully filled emit a "✅ 已全部填完" prompt that codex will
# return immediately without edits.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON=".venv/bin/python"
# Default to our wrapper that pipes the prompt file via stdin into
# `codex exec --full-auto`. The wrapper picks model/reasoning_effort
# from ~/.codex/config.toml (gpt-5.5 + xhigh by default).
CODEX_CMD="${CODEX_CMD:-scripts/codex_run_prompt.sh}"
PROMPT_DIR="${PROMPT_DIR:-/tmp/codex_prompts}"
mkdir -p "$PROMPT_DIR"

INDUSTRY_FILTER=""
PHASE_INDUSTRY=true
PHASE_COMPANY=true

while [ $# -gt 0 ]; do
  case "$1" in
    --industry-only)  PHASE_COMPANY=false ;;
    --company-only)   PHASE_INDUSTRY=false ;;
    --industry)       shift; INDUSTRY_FILTER="$1" ;;
    -h|--help)
      sed -n '2,25p' "$0"; exit 0 ;;
    *)
      echo "unknown arg: $1" >&2; exit 1 ;;
  esac
  shift
done

# Resolve list of active industries (graph_status: present) from industries.yaml
ACTIVE_INDUSTRIES=$($PYTHON -c "
import yaml
data = yaml.safe_load(open('config/mvp20.industries.yaml').read())
print('\n'.join(i['id'] for i in data.get('industries', [])
                if i.get('graph_status') == 'present'))
")

if [ -n "$INDUSTRY_FILTER" ]; then
  ACTIVE_INDUSTRIES="$INDUSTRY_FILTER"
fi

echo "============================================================"
echo "codex dispatch — CODEX_CMD=$CODEX_CMD"
echo "  industries: $(echo "$ACTIVE_INDUSTRIES" | wc -w | tr -d ' ')"
echo "  prompts → $PROMPT_DIR"
echo "============================================================"

# -- Phase 1: industry overlays ---------------------------------------------
if [ "$PHASE_INDUSTRY" = true ]; then
  echo ""; echo "### Phase 1: industry overlays (14 L0 fields each) ###"; echo ""
  for ind in $ACTIVE_INDUSTRIES; do
    OUT="$PROMPT_DIR/industry_${ind}.md"
    echo "→ $ind"
    $PYTHON scripts/codex_prompt_gen.py --industry "$ind" --out "$OUT" || continue
    if grep -q "✅ 已全部填完" "$OUT"; then
      echo "  ✅ skip (filled)"
      continue
    fi
    echo "  ▶ $CODEX_CMD $OUT"
    $CODEX_CMD "$OUT" || echo "  ⚠ codex failed for $ind"
  done
fi

# -- Phase 2: company overlays ----------------------------------------------
if [ "$PHASE_COMPANY" = true ]; then
  echo ""; echo "### Phase 2: company overlays (18 L1-L5 fields each) ###"; echo ""
  TOTAL=0
  SKIPPED=0
  PROCESSED=0
  for ind in $ACTIVE_INDUSTRIES; do
    DIR="config/stock_overlays/$ind"
    [ -d "$DIR" ] || { echo "skip $ind (no dir)"; continue; }
    for f in "$DIR"/*.yaml; do
      [ -f "$f" ] || continue
      TS_CODE=$(basename "$f" .yaml)
      TOTAL=$((TOTAL + 1))
      OUT="$PROMPT_DIR/stock_${ind}_${TS_CODE}.md"
      $PYTHON scripts/codex_prompt_gen.py --industry "$ind" --ts-code "$TS_CODE" --out "$OUT" || continue
      if grep -q "✅ 已全部填完" "$OUT"; then
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      PROCESSED=$((PROCESSED + 1))
      echo "→ $ind / $TS_CODE  ($PROCESSED processed, $SKIPPED skipped)"
      $CODEX_CMD "$OUT" || echo "  ⚠ codex failed for $TS_CODE"
    done
  done
  echo ""
  echo "Phase 2 totals: $PROCESSED processed, $SKIPPED skipped (filled), $TOTAL total"
fi

# -- Phase 3: verify --------------------------------------------------------
echo ""
echo "### Phase 3: verify & recompile ###"
echo ""
echo "Run these to confirm new coverage:"
echo "  $PYTHON -m mvp20.cli validate-overlays"
echo "  $PYTHON -m mvp20.cli compile-overlays --db runtime/hot.sqlite"
echo "  $PYTHON -m mvp20.cli audit-injection"
