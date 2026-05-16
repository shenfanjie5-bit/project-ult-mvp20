#!/usr/bin/env bash
# Run a Z4 prompt file through `claude` (Claude Code CLI) non-interactively.
#
# Same call-shape as scripts/codex_run_prompt.sh so codex_dispatch.sh +
# codex_run_stocks_chunk.sh can switch backend via:
#
#   CODEX_CMD=scripts/claude_run_prompt.sh ./scripts/codex_dispatch.sh ...
#
# Usage:
#   scripts/claude_run_prompt.sh <prompt-file>
#
# Defaults:
#   - Model: $CLAUDE_MODEL (default: sonnet) — sonnet is the right speed/cost
#     trade-off for structured overlay-fill tasks. Override with
#     `CLAUDE_MODEL=opus` for harder cases.
#   - Working directory: $CLAUDE_WORKDIR (env) or current $(pwd).
#   - Per-run budget cap: $CLAUDE_MAX_BUDGET_USD (default 0.80).
#   - Tool whitelist via --allowedTools: only Read, Edit, Write, plus a
#     pinned Bash allow-list for our verify + compile scripts. The LLM
#     cannot run arbitrary shell — equivalent to codex --full-auto's
#     workspace-write sandbox.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <prompt-file>" >&2
  exit 1
fi

PROMPT_FILE="$1"
if [ ! -f "$PROMPT_FILE" ]; then
  echo "prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

WORKDIR="${CLAUDE_WORKDIR:-$(pwd)}"
# Default to Opus 4.7 (1M context) — user-selected for Z4 universe-wide
# run. Override via CLAUDE_MODEL=sonnet for cheaper batches when the prompt
# is mostly mechanical extraction (cheap_extract / cheap_classify tiers).
MODEL="${CLAUDE_MODEL:-claude-opus-4-7}"
MAX_BUDGET="${CLAUDE_MAX_BUDGET_USD:-2.00}"

cd "$WORKDIR"

# Tool whitelist mirrors what the Z4 prompt actually needs:
#   - Read / Edit / Write   : modify overlay yaml in-place
#   - Bash(verify+compile)  : run the closed-loop verifier / compile-overlays
#   - Glob / Grep           : occasional file lookups inside config/
# The LLM cannot run other shell commands (curl/wget/etc.) — matches the
# X5 closed-loop "no external network" rule the prompt itself enforces.
ALLOWED_TOOLS=(
  Read
  Edit
  Write
  Glob
  Grep
  "Bash(.venv/bin/python scripts/verify_overlay_closed_loop.py*)"
  "Bash(.venv/bin/python -m mvp20.cli compile-overlays*)"
  "Bash(git diff --check*)"
  "Bash(git status*)"
)

exec claude -p \
  --model "$MODEL" \
  --no-session-persistence \
  --max-budget-usd "$MAX_BUDGET" \
  --output-format text \
  --allowedTools "${ALLOWED_TOOLS[@]}" \
  < "$PROMPT_FILE"
