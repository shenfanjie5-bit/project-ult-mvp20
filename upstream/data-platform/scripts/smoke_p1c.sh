#!/usr/bin/env bash
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

if [[ -z "${DP_PG_DSN:-}" ]]; then
  echo "P1c smoke failed: DP_PG_DSN is required" >&2
  exit 2
fi

SMOKE_WORK_DIR="${DP_SMOKE_WORK_DIR:-${TMPDIR:-/tmp}/data-platform-p1c-smoke}"
LOG_DIR="${DP_SMOKE_LOG_DIR:-${SMOKE_WORK_DIR}/logs}"

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
export DP_SMOKE_WORK_DIR="${SMOKE_WORK_DIR}"
export DP_RAW_ZONE_PATH="${DP_RAW_ZONE_PATH:-${SMOKE_WORK_DIR}/raw}"
export DP_ICEBERG_WAREHOUSE_PATH="${DP_ICEBERG_WAREHOUSE_PATH:-${SMOKE_WORK_DIR}/warehouse}"
export DP_DUCKDB_PATH="${DP_DUCKDB_PATH:-${SMOKE_WORK_DIR}/data_platform.duckdb}"
export DP_ICEBERG_CATALOG_NAME="${DP_ICEBERG_CATALOG_NAME:-data_platform_p1c_smoke}"
export DP_ENV="${DP_ENV:-}"

validate_smoke_target() {
  "${PYTHON}" - <<'PY'
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def fail(message: str) -> None:
    print(f"P1c smoke failed: {message}", file=sys.stderr)
    raise SystemExit(2)


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def database_name(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        dsn = "postgresql://" + dsn.removeprefix("jdbc:postgresql://")

    parsed = urlsplit(dsn)
    if not parsed.scheme or not parsed.netloc:
        fail("DP_PG_DSN must be a PostgreSQL URL with an explicit smoke database")

    name = unquote(parsed.path.lstrip("/"))
    if not name:
        fail("DP_PG_DSN must include an explicit smoke database name")
    return name


truthy = {"1", "true", "yes"}
if os.environ.get("DP_ENV") != "test":
    fail("DP_ENV must be test for smoke-p1c")

if os.environ.get("DP_SMOKE_P1C_CONFIRM_DESTRUCTIVE", "").lower() not in truthy:
    fail("set DP_SMOKE_P1C_CONFIRM_DESTRUCTIVE=1 to confirm the isolated overwrite")

db_name = database_name(os.environ["DP_PG_DSN"])
if re.fullmatch(r"dp_p1c_smoke(?:_[A-Za-z0-9]+)?", db_name) is None:
    fail(
        "DP_PG_DSN database must match dp_p1c_smoke or dp_p1c_smoke_<suffix>; "
        f"got {db_name!r}"
    )

catalog_name = os.environ["DP_ICEBERG_CATALOG_NAME"]
if re.fullmatch(r"data_platform_p1c_smoke(?:_[A-Za-z0-9]+)?", catalog_name) is None:
    fail(
        "DP_ICEBERG_CATALOG_NAME must match data_platform_p1c_smoke or "
        f"data_platform_p1c_smoke_<suffix>; got {catalog_name!r}"
    )

smoke_work_dir = Path(os.environ["DP_SMOKE_WORK_DIR"]).expanduser().resolve(strict=False)
smoke_token = re.compile(r"(?:^|[^A-Za-z0-9])(?:p1c[-_]?smoke|smoke[-_]?p1c)(?:$|[^A-Za-z0-9])")
if smoke_token.search(str(smoke_work_dir)) is None:
    fail("DP_SMOKE_WORK_DIR path must include p1c-smoke, p1c_smoke, smoke-p1c, or smoke_p1c")

for key in ("DP_RAW_ZONE_PATH", "DP_ICEBERG_WAREHOUSE_PATH", "DP_DUCKDB_PATH"):
    path = Path(os.environ[key]).expanduser().resolve(strict=False)
    if not is_relative_to(path, smoke_work_dir):
        fail(f"{key} must be inside DP_SMOKE_WORK_DIR")
PY
}

validate_smoke_target

mkdir -p \
  "${DP_RAW_ZONE_PATH}" \
  "${DP_ICEBERG_WAREHOUSE_PATH}" \
  "$(dirname "${DP_DUCKDB_PATH}")" \
  "${LOG_DIR}"

step_index=0

run_step() {
  local name="$1"
  shift
  step_index=$((step_index + 1))
  local log_file="${LOG_DIR}/step_${step_index}.log"

  printf '[smoke-p1c] step %d: %s\n' "${step_index}" "${name}"
  if "$@" >"${log_file}" 2>&1; then
    if [[ "${name}" == "runner" ]]; then
      cat "${log_file}"
    fi
    return 0
  fi

  local exit_code=$?
  {
    printf '\n[smoke-p1c] step failed: %s (exit %d)\n' "${name}" "${exit_code}"
    printf '[smoke-p1c] last 80 log lines from %s:\n' "${log_file}"
    tail -n 80 "${log_file}" || true
  } >&2
  exit "${exit_code}"
}

run_step "migrate" "${PYTHON}" -m data_platform.ddl.runner --upgrade
run_step "init catalog" "${PYTHON}" "${ROOT_DIR}/scripts/init_iceberg_catalog.py"
run_step "runner" "${PYTHON}" -m data_platform.smoke.p1c
