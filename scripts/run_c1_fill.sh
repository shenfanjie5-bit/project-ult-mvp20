#!/usr/bin/env bash
# Phase C1 driver: hybrid codex closed-loop fill for A-share overlays.
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
IND="${C1_INDUSTRY:-AI_COMPUTE}"
PARALLEL="${C1_PARALLEL:-3}"
RUNNER="${C1_RUNNER:-scripts/codex_run_prompt_low.sh}"
PROMPT_FLAGS="${PROMPT_FLAGS:---preserve-known-baseline-missing --preserve-unknown-no-local-evidence}"
MODEL_TIER="${MODEL_TIER:-all}"
PROMPT_DIR="${C1_PROMPT_DIR:-/tmp/c1_prompts}"
LOG_DIR="${C1_LOG_DIR:-/tmp/c1_logs}"
RESULT_DIR="${C1_RESULT_DIR:-/tmp/c1_results/$(date +%Y%m%d_%H%M%S)}"
LIST_ONLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/run_c1_fill.sh [--list-only|--dry-run] [TS_CODE ...]

Environment:
  C1_INDUSTRY       Overlay industry id (default: AI_COMPUTE)
  C1_PARALLEL       Number of concurrent codex workers (default: 3)
  C1_RUNNER         Worker script used for each generated prompt
  MODEL_TIER        Prompt model tier filter (default: all)
  PROMPT_FLAGS      Extra codex_prompt_gen.py governance flags
  C1_PROMPT_DIR     Prompt output directory (default: /tmp/c1_prompts)
  C1_LOG_DIR        Log output directory (default: /tmp/c1_logs)
  C1_RESULT_DIR     Per-run status directory (default: /tmp/c1_results/<timestamp>)

Explicit stock args are required when C1_INDUSTRY is not AI_COMPUTE.

Options:
  --list-only, --dry-run
                    Generate prompts and report fillable counts without
                    invoking the LLM runner or writing overlays.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --list-only|--dry-run)
      LIST_ONLY=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if ! [[ "$PARALLEL" =~ ^[0-9]+$ ]] || [ "$PARALLEL" -lt 1 ]; then
  echo "ERROR: C1_PARALLEL must be a positive integer (got: $PARALLEL)" >&2
  exit 1
fi

if [ "$LIST_ONLY" -ne 1 ] && [ ! -x "$RUNNER" ]; then
  echo "ERROR: runner not executable: $RUNNER" >&2
  exit 1
fi

# Stock list: CLI args override the default full-10 list (so a re-run can
# target just the stocks that need it).
if [ "$#" -gt 0 ]; then
  STOCKS=("$@")
else
  if [ "$IND" != "AI_COMPUTE" ]; then
    echo "ERROR: explicit stock args are required when C1_INDUSTRY is not AI_COMPUTE" >&2
    exit 1
  fi
  STOCKS=(000063.SZ 000977.SZ 002463.SZ 002916.SZ 300308.SZ 300394.SZ \
          300502.SZ 601138.SH 688041.SH 688256.SH)
fi

mkdir -p "$PROMPT_DIR" "$LOG_DIR" "$RESULT_DIR"

echo "=== C1: regenerate prompts ==="
echo "  industry: $IND"
echo "  prompts: $PROMPT_DIR"
echo "  logs:    $LOG_DIR"
echo "  status:  $RESULT_DIR"
for ts in "${STOCKS[@]}"; do
  out="$PROMPT_DIR/${ts}.md"
  status_file="$RESULT_DIR/${ts}.status"
  rm -f "$out" "$LOG_DIR/${ts}.log" "$LOG_DIR/${ts}.prompt.err" "$LOG_DIR/${ts}.SKIP" "$status_file"
  # shellcheck disable=SC2086
  if ! $PY scripts/codex_prompt_gen.py --industry "$IND" --ts-code "$ts" --model-tier "$MODEL_TIER" $PROMPT_FLAGS --out "$out" \
      > /dev/null 2> "$LOG_DIR/${ts}.prompt.err"; then
    echo "  $ts: prompt generation failed (see $LOG_DIR/${ts}.prompt.err)"
    echo "prompt_failed" > "$status_file"
    continue
  fi
  rm -f "$LOG_DIR/${ts}.prompt.err"
  if grep -q "✅ 已全部填完\|没有可填字段" "$out" 2>/dev/null; then
    echo "  $ts: nothing to fill (skip)"
    : > "$LOG_DIR/${ts}.SKIP"
    echo "skipped" > "$status_file"
  else
    n=$(sed -nE 's/^## 当前状态：([0-9]+) 条 .*$/\1/p' "$out" | head -1)
    if [ -z "$n" ]; then
      n=$(grep -cE '^- `L' "$out" 2>/dev/null || echo "?")
    fi
    echo "  $ts: prompt ready (${n} fillable)"
    echo "prompt_ready" > "$status_file"
  fi
done

if [ "$LIST_ONLY" -eq 1 ]; then
  echo ""
  echo "=== C1: list-only, no LLM runner invoked ==="
  count_status() {
    wanted="$1"
    count=0
    for f in "$RESULT_DIR"/*.status; do
      [ -f "$f" ] || continue
      status="$(cat "$f")"
      [ "$status" = "$wanted" ] && count=$((count + 1))
    done
    echo "$count"
  }

  READY="$(count_status prompt_ready)"
  SKIPPED="$(count_status skipped)"
  PROMPT_FAILED="$(count_status prompt_failed)"
  echo "  prompt_ready:   $READY"
  echo "  skipped:        $SKIPPED"
  echo "  prompt_failed:  $PROMPT_FAILED"

  if [ "$PROMPT_FAILED" -gt 0 ]; then
    echo "ERROR: prompt generation failed for one or more stocks; see $LOG_DIR" >&2
    exit 1
  fi
  exit 0
fi

echo ""
echo "=== C1: codex ${RUNNER##*/} x${PARALLEL} parallel ==="
run_one() {
  ts="$1"
  status_file="$RESULT_DIR/${ts}.status"
  status="$(cat "$status_file" 2>/dev/null || true)"
  case "$status" in
    skipped) echo "[skip] $ts"; return 0 ;;
    prompt_failed) echo "[skip] $ts (prompt failed)"; return 0 ;;
    prompt_ready) ;;
    *) echo "[skip] $ts (unexpected status: ${status:-missing})"; return 0 ;;
  esac
  echo "[$(date +%H:%M:%S)] START $ts"
  "$RUNNER" "$PROMPT_DIR/${ts}.md" > "$LOG_DIR/${ts}.log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "processed" > "$status_file"
  else
    echo "failed" > "$status_file"
    echo "$rc" > "$RESULT_DIR/${ts}.exitcode"
  fi
  echo "[$(date +%H:%M:%S)] DONE  $ts (exit $rc)"
  return "$rc"
}
export -f run_one
export CODEX_WORKDIR RUNNER PROMPT_DIR LOG_DIR RESULT_DIR

printf '%s\n' "${STOCKS[@]}" | xargs -P "$PARALLEL" -I{} bash -c 'run_one "$@"' _ {}
XARGS_RC=$?

echo ""
echo "=== C1 fill done ==="
count_status() {
  wanted="$1"
  count=0
  for f in "$RESULT_DIR"/*.status; do
    [ -f "$f" ] || continue
    status="$(cat "$f")"
    [ "$status" = "$wanted" ] && count=$((count + 1))
  done
  echo "$count"
}

PROCESSED="$(count_status processed)"
SKIPPED="$(count_status skipped)"
PROMPT_FAILED="$(count_status prompt_failed)"
FAILED="$(count_status failed)"
echo "  processed:      $PROCESSED"
echo "  skipped:        $SKIPPED"
echo "  prompt_failed:  $PROMPT_FAILED"
echo "  failed:         $FAILED"

if [ "$FAILED" -gt 0 ] || [ "$PROMPT_FAILED" -gt 0 ] || [ "$XARGS_RC" -ne 0 ]; then
  echo "ERROR: C1 fill completed with failures; see $LOG_DIR and $RESULT_DIR" >&2
  exit 1
fi

echo ""
echo "=== C1: normalize processed overlays ==="
NORMALIZED=0
for ts in "${STOCKS[@]}"; do
  status_file="$RESULT_DIR/${ts}.status"
  status="$(cat "$status_file" 2>/dev/null || true)"
  [ "$status" = "processed" ] || continue
  overlay_path="config/stock_overlays/${IND}/${ts}.yaml"
  [ -f "$overlay_path" ] || continue
  before_hash="$(shasum -a 256 "$overlay_path" | awk '{print $1}')"
  "$PY" - "$overlay_path" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "formula: Direction × Event Strength × Transmission Strength × Company Exposure × Business Share × Profit Sensitivity ×\n"
    "      Confidence × Time Factor × Surprise × Funding Amplifier - Priced-in Discount - Risk Discount",
    "formula: Direction × Event Strength × Transmission Strength × Company Exposure × Business Share × Profit Sensitivity × Confidence × Time Factor × Surprise × Funding Amplifier - Priced-in Discount - Risk Discount",
)
path.write_text(text, encoding="utf-8")
PY
  after_hash="$(shasum -a 256 "$overlay_path" | awk '{print $1}')"
  if [ "$before_hash" != "$after_hash" ]; then
    NORMALIZED=$((NORMALIZED + 1))
    echo "  $ts: restored wrapped scores.formula"
  fi
done
echo "  formula_normalized: $NORMALIZED"
