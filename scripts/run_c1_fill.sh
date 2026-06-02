#!/usr/bin/env bash
# Phase C1 driver: hybrid codex closed-loop fill for AI_COMPUTE A-shares.
#
#   1. regenerate a fresh prompt per stock (current DB incl. ingested annual
#      reports + re-collected analyst data → correct source fingerprints).
#   2. run codex (low reasoning effort) 3-way parallel; each codex edits only
#      its own stock overlay (distinct files → no write contention; DB is read
#      only as injected evidence).
#
# Logs: /tmp/c1_logs/<ts>.log    Prompts: /tmp/c1_prompts/<ts>.md
# xhigh re-runs for flagged stocks are driven separately after verify.

set -uo pipefail
cd "$(dirname "$0")/.."
export CODEX_WORKDIR="$(pwd)"
PY=.venv/bin/python
IND=AI_COMPUTE
PARALLEL="${C1_PARALLEL:-3}"
RUNNER="${C1_RUNNER:-scripts/codex_run_prompt_low.sh}"

# Stock list: CLI args override the default full-10 list (so a re-run can
# target just the stocks that need it).
if [ "$#" -gt 0 ]; then
  STOCKS=("$@")
else
  STOCKS=(000063.SZ 000977.SZ 002463.SZ 002916.SZ 300308.SZ 300394.SZ \
          300502.SZ 601138.SH 688041.SH 688256.SH)
fi

mkdir -p /tmp/c1_prompts /tmp/c1_logs

echo "=== C1: regenerate prompts ==="
for ts in "${STOCKS[@]}"; do
  out="/tmp/c1_prompts/${ts}.md"
  $PY scripts/codex_prompt_gen.py --industry "$IND" --ts-code "$ts" --out "$out" \
      >/dev/null 2>&1
  if grep -q "✅ 已全部填完\|没有可填字段" "$out" 2>/dev/null; then
    echo "  $ts: nothing to fill (skip)"
    : > "/tmp/c1_logs/${ts}.SKIP"
  else
    n=$(grep -cE "^- \`L" "$out" 2>/dev/null || echo "?")
    echo "  $ts: prompt ready (${n} fillable)"
  fi
done

echo ""
echo "=== C1: codex ${RUNNER##*/} x${PARALLEL} parallel ==="
run_one() {
  ts="$1"
  [ -f "/tmp/c1_logs/${ts}.SKIP" ] && { echo "[skip] $ts"; return 0; }
  echo "[$(date +%H:%M:%S)] START $ts"
  bash "$RUNNER" "/tmp/c1_prompts/${ts}.md" > "/tmp/c1_logs/${ts}.log" 2>&1
  rc=$?
  echo "[$(date +%H:%M:%S)] DONE  $ts (exit $rc)"
}
export -f run_one
export CODEX_WORKDIR RUNNER

printf '%s\n' "${STOCKS[@]}" | xargs -P "$PARALLEL" -I{} bash -c 'run_one "$@"' _ {}

echo ""
echo "=== C1 fill done ==="
