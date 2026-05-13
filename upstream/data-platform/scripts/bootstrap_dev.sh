#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
CONSTRAINTS_FILE="${CONSTRAINTS_FILE:-constraints.txt}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade --constraint "${CONSTRAINTS_FILE}" pip setuptools wheel
python -m pip install --no-build-isolation --constraint "${CONSTRAINTS_FILE}" -e ".[dev]"

if [ -f ".pre-commit-config.yaml" ]; then
    pre-commit install
fi
