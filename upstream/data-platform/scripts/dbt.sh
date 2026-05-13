#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_PROJECT_DIR="${ROOT_DIR}/src/data_platform/dbt"

export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-${DBT_PROJECT_DIR}}"

if [[ -n "${DP_DBT_EXECUTABLE:-}" ]]; then
  if command -v "${DP_DBT_EXECUTABLE}" >/dev/null 2>&1; then
    DBT_BIN="${DP_DBT_EXECUTABLE}"
  else
    echo "DP_DBT_EXECUTABLE is not executable: ${DP_DBT_EXECUTABLE}" >&2
    exit 127
  fi
elif [[ -n "${DBT_BIN:-}" ]]; then
  if command -v "${DBT_BIN}" >/dev/null 2>&1; then
    DBT_BIN="${DBT_BIN}"
  else
    echo "DBT_BIN is not executable: ${DBT_BIN}" >&2
    exit 127
  fi
elif [ -x "${ROOT_DIR}/.venv-py312/bin/dbt" ]; then
  DBT_BIN="${ROOT_DIR}/.venv-py312/bin/dbt"
elif [ -x "${ROOT_DIR}/.venv-py313/bin/dbt" ]; then
  DBT_BIN="${ROOT_DIR}/.venv-py313/bin/dbt"
elif command -v dbt >/dev/null 2>&1; then
  DBT_BIN="dbt"
elif [ -x "${ROOT_DIR}/.venv/bin/dbt" ]; then
  DBT_BIN="${ROOT_DIR}/.venv/bin/dbt"
else
  echo "dbt executable is not installed; expected DP_DBT_EXECUTABLE, dbt on PATH, .venv-py312/bin/dbt, .venv-py313/bin/dbt, or .venv/bin/dbt" >&2
  exit 127
fi

# dbt 1.8+ removed --project-dir flag; use DBT_PROJECT_DIR env var instead
# (already set above, compatible with dbt 1.5+)
export DBT_PROJECT_DIR

# For `dbt test`, inject --indirect-selection=cautious unless the caller
# already specified it. Prevents cross-layer relationship test failures.
ARGS=("$@")
if [[ "${1:-}" == "test" ]]; then
  has_indirect=false
  for arg in "$@"; do
    [[ "$arg" == "--indirect-selection" || "$arg" == --indirect-selection=* ]] && has_indirect=true
  done
  if [[ "$has_indirect" == "false" ]]; then
    ARGS=("${ARGS[@]:0:1}" "--indirect-selection" "cautious" "${ARGS[@]:1}")
  fi
fi

exec "${DBT_BIN}" "${ARGS[@]}"
