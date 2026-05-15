#!/usr/bin/env bash
# Codex A/B (low thinking) batch:
# Runs the same 8 prompts /tmp/ab/prompt_*.md but with `reasoning_effort=low`
# (via scripts/codex_run_prompt_low.sh). Outputs go to /tmp/ab_low/.
#
# For each (stock, tier):
#   1. Re-use /tmp/ab/prompt_KEY.md if present; regenerate via codex_prompt_gen
#      if not (defensive). Skip if no fillable.
#   2. scripts/codex_run_prompt_low.sh PROMPT > /tmp/ab_low/codex_low_KEY.log
#   3. cp overlay yaml -> /tmp/ab_low/codex_low_KEY.yaml
#   4. git checkout -- config/stock_overlays/  (revert edits, preserve baseline)
#
# Strict: never touches /tmp/ab/, never modifies scripts/codex_run_prompt.sh.

set -uo pipefail

cd "$(dirname "$0")/.."

mkdir -p /tmp/ab_low

STOCKS=("AI_COMPUTE/000063.SZ" "AI_COMPUTE/NVDA.US")
TIERS=("cheap_extract" "cheap_classify" "analysis" "web_analysis")

for stock_path in "${STOCKS[@]}"; do
  IND="${stock_path%%/*}"
  TS="${stock_path##*/}"
  TS_SAN="${TS//./_}"
  for TIER in "${TIERS[@]}"; do
    KEY="${TS_SAN}_${TIER}"
    PROMPT="/tmp/ab/prompt_${KEY}.md"

    if [ ! -f "$PROMPT" ]; then
      echo "Prompt missing, regenerating: $PROMPT"
      .venv/bin/python scripts/codex_prompt_gen.py \
        --industry "$IND" --ts-code "$TS" --model-tier "$TIER" \
        --out "$PROMPT" 2>&1 | tail -1
    fi

    if grep -q "## ✅ 没有可填字段" "$PROMPT"; then
      echo "skip $KEY (no fillable)"
      continue
    fi

    if ! grep -q "待填字段" "$PROMPT"; then
      echo "WARN $KEY: prompt missing 待填字段 — skip"
      continue
    fi

    echo "=== codex-low: $KEY (start) ==="
    START=$(date +%s)
    if scripts/codex_run_prompt_low.sh "$PROMPT" \
         > "/tmp/ab_low/codex_low_${KEY}.log" 2>&1; then
      END=$(date +%s)
      echo "    duration: $((END - START))s"
    else
      END=$(date +%s)
      echo "    codex-low FAILED ($((END - START))s) — see /tmp/ab_low/codex_low_${KEY}.log"
    fi
    cp "config/stock_overlays/${stock_path}.yaml" \
       "/tmp/ab_low/codex_low_${KEY}.yaml"
    git checkout -- config/stock_overlays/ 2>&1 | tail -1
  done
done

echo "ALL DONE"
ls -1 /tmp/ab_low/codex_low_*.yaml 2>/dev/null
