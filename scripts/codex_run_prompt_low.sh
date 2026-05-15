#!/usr/bin/env bash
# Same as codex_run_prompt.sh but forces reasoning_effort=low.
#
# Usage:
#   scripts/codex_run_prompt_low.sh <prompt-file>
#
# - Model + sandbox inherit from ~/.codex/config.toml (gpt-5.5).
# - reasoning_effort is overridden via `-c` to "low".
# - Working directory: $CODEX_WORKDIR (env) or current $(pwd).
# - Prompt is piped via stdin so size is not bounded by argv limits.

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

WORKDIR="${CODEX_WORKDIR:-$(pwd)}"

exec codex exec \
  --full-auto \
  --skip-git-repo-check \
  -c model_reasoning_effort=low \
  -C "$WORKDIR" \
  < "$PROMPT_FILE"
