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
#   ./scripts/codex_dispatch.sh --a-share-only          # A-share stock overlays only
#   ./scripts/codex_dispatch.sh --model-tier cheap_extract
#   ./scripts/codex_dispatch.sh --company-only --parallel 3
#   CODEX_CMD=echo ./scripts/codex_dispatch.sh          # dry run
#
# Idempotent: each overlay prompt skips clean (data_status != Unknown) nodes;
# overlays already fully filled emit a "✅ 没有可填字段" prompt that codex will
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
PROMPT_FLAGS="${PROMPT_FLAGS:---preserve-known-baseline-missing --preserve-unknown-no-local-evidence}"
MODEL_TIER="${MODEL_TIER:-all}"
PARALLEL="${CODEX_PARALLEL:-1}"
mkdir -p "$PROMPT_DIR"

INDUSTRY_FILTER=""
PHASE_INDUSTRY=true
PHASE_COMPANY=true
A_SHARE_ONLY="${A_SHARE_ONLY:-false}"

is_a_share_ts_code() {
  case "$1" in
    *.SH|*.SZ|*.BJ) return 0 ;;
    *) return 1 ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --industry-only)  PHASE_COMPANY=false ;;
    --company-only)   PHASE_INDUSTRY=false ;;
    --industry)       shift; INDUSTRY_FILTER="$1" ;;
    --a-share-only)   A_SHARE_ONLY=true ;;
    --model-tier)     shift; MODEL_TIER="$1" ;;
    --parallel)       shift; PARALLEL="$1" ;;
    -h|--help)
      sed -n '2,28p' "$0"; exit 0 ;;
    *)
      echo "unknown arg: $1" >&2; exit 1 ;;
  esac
  shift
done

if ! [[ "$PARALLEL" =~ ^[0-9]+$ ]] || [ "$PARALLEL" -lt 1 ]; then
  echo "ERROR: --parallel / CODEX_PARALLEL must be a positive integer (got: $PARALLEL)" >&2
  exit 1
fi

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
echo "  prompt flags: $PROMPT_FLAGS"
echo "  model tier: $MODEL_TIER"
echo "  A-share only: $A_SHARE_ONLY"
echo "  company parallelism: $PARALLEL"
echo "============================================================"

run_company_job() {
  local ind="$1"
  local ts_code="$2"
  local out status_file
  out="$PROMPT_DIR/stock_${ind}_${ts_code}.md"
  status_file="${RESULT_DIR:-}/stock_${ind}_${ts_code}.status"

  echo "→ $ind / $ts_code"
  # shellcheck disable=SC2086
  if ! "$PYTHON" scripts/codex_prompt_gen.py --industry "$ind" --ts-code "$ts_code" --model-tier "$MODEL_TIER" $PROMPT_FLAGS --out "$out"; then
    echo "  ⚠ prompt generation failed for $ind / $ts_code"
    [ -n "${RESULT_DIR:-}" ] && echo "prompt_failed" > "$status_file"
    return 0
  fi
  if grep -q "✅ 已全部填完\|✅ 没有可填字段\|没有可填字段" "$out"; then
    echo "  ✅ skip (filled) $ind / $ts_code"
    [ -n "${RESULT_DIR:-}" ] && echo "skipped" > "$status_file"
    return 0
  fi
  echo "  ▶ $CODEX_CMD $out"
  if $CODEX_CMD "$out"; then
    [ -n "${RESULT_DIR:-}" ] && echo "processed" > "$status_file"
  else
    echo "  ⚠ codex failed for $ind / $ts_code"
    [ -n "${RESULT_DIR:-}" ] && echo "failed" > "$status_file"
  fi
}

count_company_status() {
  local wanted="$1"
  local count=0
  local f status
  for f in "$RESULT_DIR"/*.status; do
    [ -f "$f" ] || continue
    status="$(cat "$f")"
    case "$wanted:$status" in
      processed:processed|skipped:skipped|failed:failed|failed:prompt_failed)
        count=$((count + 1))
        ;;
    esac
  done
  echo "$count"
}

# -- Phase 1: industry overlays ---------------------------------------------
if [ "$PHASE_INDUSTRY" = true ]; then
  echo ""; echo "### Phase 1: industry overlays (14 L0 fields each) ###"; echo ""
  for ind in $ACTIVE_INDUSTRIES; do
    OUT="$PROMPT_DIR/industry_${ind}.md"
    echo "→ $ind"
    $PYTHON scripts/codex_prompt_gen.py --industry "$ind" --model-tier "$MODEL_TIER" $PROMPT_FLAGS --out "$OUT" || continue
    if grep -q "✅ 已全部填完\|✅ 没有可填字段\|没有可填字段" "$OUT"; then
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
  FAILED=0
  JOB_FILE="$(mktemp "$PROMPT_DIR/company_jobs.XXXXXX")"
  for ind in $ACTIVE_INDUSTRIES; do
    DIR="config/stock_overlays/$ind"
    [ -d "$DIR" ] || { echo "skip $ind (no dir)"; continue; }
    for f in "$DIR"/*.yaml; do
      [ -f "$f" ] || continue
      TS_CODE=$(basename "$f" .yaml)
      if [ "$A_SHARE_ONLY" = true ] && ! is_a_share_ts_code "$TS_CODE"; then
        continue
      fi
      TOTAL=$((TOTAL + 1))
      printf '%s %s\n' "$ind" "$TS_CODE" >> "$JOB_FILE"
    done
  done

  if [ "$TOTAL" -eq 0 ]; then
    echo "No company overlays matched filters."
  elif [ "$PARALLEL" -gt 1 ]; then
    RESULT_DIR="$(mktemp -d "$PROMPT_DIR/company_results.XXXXXX")"
    export PYTHON CODEX_CMD PROMPT_DIR PROMPT_FLAGS MODEL_TIER RESULT_DIR
    export -f run_company_job
    echo "Running $TOTAL company jobs with parallelism=$PARALLEL"
    xargs -P "$PARALLEL" -n 2 bash -c 'run_company_job "$1" "$2"' _ < "$JOB_FILE"
    PROCESSED="$(count_company_status processed)"
    SKIPPED="$(count_company_status skipped)"
    FAILED="$(count_company_status failed)"
  else
    while read -r ind TS_CODE; do
      OUT="$PROMPT_DIR/stock_${ind}_${TS_CODE}.md"
      # shellcheck disable=SC2086
      $PYTHON scripts/codex_prompt_gen.py --industry "$ind" --ts-code "$TS_CODE" --model-tier "$MODEL_TIER" $PROMPT_FLAGS --out "$OUT" || { FAILED=$((FAILED + 1)); continue; }
      if grep -q "✅ 已全部填完\|✅ 没有可填字段\|没有可填字段" "$OUT"; then
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      PROCESSED=$((PROCESSED + 1))
      echo "→ $ind / $TS_CODE  ($PROCESSED processed, $SKIPPED skipped)"
      $CODEX_CMD "$OUT" || { echo "  ⚠ codex failed for $TS_CODE"; FAILED=$((FAILED + 1)); }
    done < "$JOB_FILE"
  fi
  rm -f "$JOB_FILE"
  echo ""
  echo "Phase 2 totals: $PROCESSED processed, $SKIPPED skipped (filled), $FAILED failed, $TOTAL total"
fi

# -- Phase 3: verify --------------------------------------------------------
echo ""
echo "### Phase 3: verify & recompile ###"
echo ""
echo "Run these to confirm new coverage:"
echo "  $PYTHON -m mvp20.cli validate-overlays"
echo "  $PYTHON -m mvp20.cli compile-overlays --db runtime/hot.sqlite"
echo "  $PYTHON -m mvp20.cli audit-injection"
