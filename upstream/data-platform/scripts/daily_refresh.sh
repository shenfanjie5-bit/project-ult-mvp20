#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for venv_bin in \
  "${ROOT_DIR}/.venv/bin" \
  "${ROOT_DIR}/.venv-py313/bin" \
  "${ROOT_DIR}/.venv-py312/bin"; do
  if [[ -d "${venv_bin}" ]]; then
    export PATH="${venv_bin}:${PATH}"
  fi
done

if [[ -z "${PYTHON:-}" ]]; then
  for candidate in \
    "${ROOT_DIR}/.venv-py312/bin/python" \
    "${ROOT_DIR}/.venv-py313/bin/python" \
    "${ROOT_DIR}/.venv/bin/python" \
    "python3"; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PYTHON="${candidate}"
      break
    fi
  done
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

"${PYTHON}" -m data_platform.daily_refresh "$@"
echo "Daily refresh OK"
