#!/usr/bin/env bash
# Run a codex prompt file through `codex exec` non-interactively.
#
# Usage:
#   scripts/codex_run_prompt.sh <prompt-file>
#
# - Reads model + reasoning_effort from ~/.codex/config.toml (default gpt-5.5 xhigh).
# - Sandbox: workspace-write via --full-auto (no approval prompts).
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

# stdin pipe: codex exec reads instructions from stdin when no PROMPT arg
exec codex exec \
  --full-auto \
  --skip-git-repo-check \
  -C "$WORKDIR" \
  < "$PROMPT_FILE"
