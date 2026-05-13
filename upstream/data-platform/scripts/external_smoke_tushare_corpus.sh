#!/usr/bin/env bash
# External smoke lane for the local Tushare corpus.
#
# Thin shell wrapper around external_smoke_tushare_corpus.py — sets up
# the repo venv + forwards env vars. Intended for cron / launchd
# scheduled runs on developer machines; NOT a CI test.
#
# Usage:
#   ./scripts/external_smoke_tushare_corpus.sh
#
# Useful env vars:
#   DP_EXTERNAL_CORPUS_ROOT   override the default /Volumes/dockcase2tb/database_all
#   DP_EXTERNAL_SMOKE_STRICT  set to 1 to make "drive unmounted" a hard fail
#                             (default: drive-unmounted exits 0 as a skip)
#
# Exit codes:
#   0  all checks passed, OR drive unmounted + strict mode off (normal skip)
#   1  at least one check failed (or unmounted + strict mode on)
#   2  usage / prerequisite error

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -d "${ROOT_DIR}/.venv/bin" ]]; then
  export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
fi

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON="${ROOT_DIR}/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

# Ensure the data_platform package is importable — the schema-alignment
# check reads TUSHARE_*_SCHEMA from data_platform.adapters.tushare.assets.
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

exec "${PYTHON}" "${ROOT_DIR}/scripts/external_smoke_tushare_corpus.py"
