#!/usr/bin/env bash
# A/B test: codex CLI vs minimax-M2 on the 4 model_tier × 2 stocks matrix.
#
# Strategy:
#   For each (stock, tier):
#     1. Generate prompt via codex_prompt_gen.py
#     2. Skip if 0 fillable
#     3. Run codex (edits yaml inline) → backup to /tmp/ab/codex_KEY.yaml
#        → git checkout -- config/stock_overlays/
#     4. Run minimax_run_prompt.py → emits yaml patch
#        → apply_yaml_patch.py to overlay → backup to /tmp/ab/minimax_KEY.yaml
#        → git checkout -- config/stock_overlays/
#   Logs to /tmp/ab/{codex,minimax}_KEY.log
#
# Usage:
#   scripts/run_ab_test.sh [stock_tier_filter]
#   scripts/run_ab_test.sh 000063.SZ_cheap_extract   # run one cell only
#   scripts/run_ab_test.sh                            # run all 8 cells
#
# Env:
#   AB_SKIP_CODEX=1   skip codex runs (just minimax)
#   AB_SKIP_MINIMAX=1 skip minimax runs (just codex)
#   AB_DRY_RUN=1      generate prompts only, don't call any LLM

set -uo pipefail

cd "$(dirname "$0")/.."

# Load .env so MINIMAX_API_KEY is available
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

mkdir -p /tmp/ab

FILTER="${1:-}"

STOCKS=("AI_COMPUTE/000063.SZ" "AI_COMPUTE/NVDA.US")
TIERS=("cheap_extract" "cheap_classify" "analysis" "web_analysis")

run_cell() {
  local stock_path="$1"
  local tier="$2"
  local ind ts ts_san key prompt
  ind="${stock_path%%/*}"
  ts="${stock_path##*/}"
  ts_san="${ts//./_}"
  key="${ts_san}_${tier}"
  prompt="/tmp/ab/prompt_${key}.md"

  if [ -n "$FILTER" ] && [ "$FILTER" != "$key" ]; then
    return 0
  fi

  echo ""
  echo "============================================================"
  echo "  ${ind}/${ts}  tier=${tier}  key=${key}"
  echo "============================================================"

  # Step 1: generate prompt
  .venv/bin/python scripts/codex_prompt_gen.py \
    --industry "$ind" --ts-code "$ts" --model-tier "$tier" \
    --out "$prompt" 2>&1 | tail -1

  # Step 2: skip if no fillable
  if grep -q "## ✅ 没有可填字段" "$prompt"; then
    echo "  skip (no fillable)"
    return 0
  fi

  # Sanity: there should be a 待填字段 section
  if ! grep -q "待填字段" "$prompt"; then
    echo "  WARN: prompt missing 待填字段 header — skipping"
    return 0
  fi

  if [ "${AB_DRY_RUN:-0}" = "1" ]; then
    echo "  AB_DRY_RUN=1 → skip LLM calls"
    return 0
  fi

  # Step 3: codex run
  if [ "${AB_SKIP_CODEX:-0}" != "1" ]; then
    echo "--- codex run on $key ---"
    local codex_t0=$SECONDS
    if scripts/codex_run_prompt.sh "$prompt" > "/tmp/ab/codex_${key}.log" 2>&1; then
      echo "  codex ok ($((SECONDS - codex_t0))s)"
    else
      echo "  codex FAILED ($((SECONDS - codex_t0))s) — see /tmp/ab/codex_${key}.log"
    fi
    cp "config/stock_overlays/${stock_path}.yaml" "/tmp/ab/codex_${key}.yaml"
    git checkout -- config/stock_overlays/ 2>&1 | tail -1
  else
    echo "  AB_SKIP_CODEX=1 → skipping codex"
  fi

  # Step 4: minimax run
  if [ "${AB_SKIP_MINIMAX:-0}" != "1" ]; then
    echo "--- minimax run on $key ---"
    local mm_t0=$SECONDS
    if .venv/bin/python scripts/minimax_run_prompt.py "$prompt" \
        --out "/tmp/ab/minimax_${key}_response.md" \
        2> "/tmp/ab/minimax_${key}.log" ; then
      echo "  minimax ok ($((SECONDS - mm_t0))s)"
    else
      local rc=$?
      echo "  minimax FAILED (rc=$rc, $((SECONDS - mm_t0))s) — see /tmp/ab/minimax_${key}.log"
    fi
    local patch="/tmp/ab/minimax_${key}_response.patch.yaml"
    if [ -f "$patch" ]; then
      .venv/bin/python scripts/apply_yaml_patch.py \
        "config/stock_overlays/${stock_path}.yaml" "$patch" \
        2>&1 | tail -1
      cp "config/stock_overlays/${stock_path}.yaml" "/tmp/ab/minimax_${key}.yaml"
    else
      echo "  WARN: no patch file produced — copying original"
      cp "config/stock_overlays/${stock_path}.yaml" "/tmp/ab/minimax_${key}.yaml"
    fi
    git checkout -- config/stock_overlays/ 2>&1 | tail -1
  else
    echo "  AB_SKIP_MINIMAX=1 → skipping minimax"
  fi
}

for stock_path in "${STOCKS[@]}"; do
  for tier in "${TIERS[@]}"; do
    run_cell "$stock_path" "$tier"
  done
done

echo ""
echo "============================================================"
echo "  ALL DONE → see /tmp/ab/"
echo "============================================================"
ls -1 /tmp/ab/codex_*.yaml /tmp/ab/minimax_*.yaml 2>/dev/null | head -20
