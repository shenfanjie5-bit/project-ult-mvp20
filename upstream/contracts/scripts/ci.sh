#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON:-python3}"
CONTRACTS_BASELINE="${CONTRACTS_BASELINE:-artifacts/baselines/0.1.3/json_schema}"

"${PYTHON_BIN}" -m pip install -e '.[dev,shared-fixtures]'

CONTRACTS_VERSION="${CONTRACTS_VERSION:-$("${PYTHON_BIN}" - <<'PY'
import contracts

print(contracts.__version__)
PY
)}"

"${PYTHON_BIN}" -c 'import contracts, contracts.schemas, contracts.protocols, contracts.export, contracts.compat'

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/contracts-ci.XXXXXX")"
trap 'rm -rf "${tmpdir}"' EXIT

collect_output="${tmpdir}/pytest-collect.txt"
"${PYTHON_BIN}" -m pytest --collect-only -q | tee "${collect_output}"
"${PYTHON_BIN}" - "${collect_output}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

collect_output = Path(sys.argv[1]).read_text(encoding="utf-8")
collected_count = 0
for line in collect_output.splitlines():
    file_count_match = re.search(r":\s*([1-9][0-9]*)$", line)
    if file_count_match is not None:
        collected_count += int(file_count_match.group(1))
        continue

    summary_match = re.search(r"\b([1-9][0-9]*)\s+tests?\s+collected\b", line)
    if summary_match is not None:
        collected_count += int(summary_match.group(1))
        continue

    if "::test" in line:
        collected_count += 1

if collected_count == 0:
    print("error: pytest --collect-only did not collect any tests", file=sys.stderr)
    raise SystemExit(1)
PY

"${PYTHON_BIN}" -m pytest -q

"${PYTHON_BIN}" -m contracts.export \
  --output-dir "${tmpdir}/json_schema" \
  --version "${CONTRACTS_VERSION}"

if [[ ! -d "${CONTRACTS_BASELINE}" ]]; then
  echo "error: CONTRACTS_BASELINE does not exist or is not a directory: ${CONTRACTS_BASELINE}" >&2
  echo "Set CONTRACTS_BASELINE to a JSON Schema baseline directory." >&2
  exit 2
fi

"${PYTHON_BIN}" -m contracts.compat \
  --baseline "${CONTRACTS_BASELINE}" \
  --current "${tmpdir}/json_schema"
