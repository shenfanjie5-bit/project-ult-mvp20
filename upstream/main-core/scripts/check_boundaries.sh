#!/usr/bin/env bash
set -euo pipefail

ruff check .

if ! command -v lint-imports >/dev/null 2>&1; then
  echo "lint-imports is required; run \`pip install -e .[dev]\` before checking boundaries" >&2
  exit 127
fi

lint-imports --config .importlinter

if command -v pytest >/dev/null 2>&1; then
  pytest tests/test_package_boundaries.py
else
  python3 -m pytest tests/test_package_boundaries.py
fi
