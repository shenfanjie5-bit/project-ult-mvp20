#!/usr/bin/env bash
# Claude Opus 4.8 (low effort) headless fill — the Anthropic-side sibling of
# codex_run_prompt_low.sh. Runs the SAME (engine-agnostic) codex_prompt_gen
# prompt through `claude -p` so the bulk-onboard qualitative fill can fan out
# across TWO providers (codex/OpenAI + claude/Anthropic) instead of one.
#
# Usage:
#   scripts/claude_run_prompt_low.sh <prompt-file>
#
# - Model: `--model opus` (alias — the env's ANTHROPIC_BASE_URL gateway rejects
#   the full `claude-opus-4-8` id, but the alias resolves correctly).
# - Effort: CLAUDE_EFFORT=low (matches the codex low-reasoning setting).
# - Permissions: --dangerously-skip-permissions so it can Edit the overlay yaml
#   non-interactively (same trust posture as codex --full-auto).
# - Working directory: $CODEX_WORKDIR (env) or current $(pwd) — claude edits
#   files relative to its cwd, so it must run from the repo root.
# - Prompt is piped via stdin (size not bounded by argv).

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
cd "$WORKDIR"

exec env CLAUDE_EFFORT=low claude \
  -p \
  --model opus \
  --dangerously-skip-permissions \
  --permission-mode bypassPermissions \
  < "$PROMPT_FILE"
