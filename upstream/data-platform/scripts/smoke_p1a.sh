#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v dbt >/dev/null 2>&1 && [[ -d "${ROOT_DIR}/.venv/bin" ]]; then
  export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
fi

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON="${ROOT_DIR}/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

allow_skip="${DP_SMOKE_P1A_ALLOW_SKIP:-}"
if [[ -z "${DP_PG_DSN:-}" ]]; then
  case "${allow_skip}" in
    1|true|TRUE|yes|YES)
      echo "P1a smoke skipped: DP_PG_DSN is required for PostgreSQL"
      exit 0
      ;;
  esac
  echo "P1a smoke failed: DP_PG_DSN is required; DATABASE_URL is not used by this destructive smoke path" >&2
  exit 2
fi

SMOKE_WORK_DIR="${DP_SMOKE_WORK_DIR:-${TMPDIR:-/tmp}/data-platform-p1a-smoke}"
LOG_DIR="${DP_SMOKE_LOG_DIR:-${SMOKE_WORK_DIR}/logs}"
PROFILES_DIR="${SMOKE_WORK_DIR}/dbt_profiles"
DBT_TARGET_DIR="${SMOKE_WORK_DIR}/dbt_target"

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
export DP_SMOKE_WORK_DIR="${SMOKE_WORK_DIR}"
export DP_RAW_ZONE_PATH="${DP_RAW_ZONE_PATH:-${SMOKE_WORK_DIR}/raw}"
export DP_ICEBERG_WAREHOUSE_PATH="${DP_ICEBERG_WAREHOUSE_PATH:-${SMOKE_WORK_DIR}/warehouse}"
export DP_DUCKDB_PATH="${DP_DUCKDB_PATH:-${SMOKE_WORK_DIR}/data_platform.duckdb}"
export DP_ICEBERG_CATALOG_NAME="${DP_ICEBERG_CATALOG_NAME:-data_platform_p1a_smoke}"
export DP_ENV="${DP_ENV:-}"
export DP_CANONICAL_USE_V2=1
export DBT_PROFILES_DIR="${PROFILES_DIR}"

validate_smoke_target() {
  "${PYTHON}" - <<'PY'
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def fail(message: str) -> None:
    print(f"P1a smoke failed: {message}", file=sys.stderr)
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
    fail("DP_ENV must be test for smoke-p1a")

if os.environ.get("DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE", "").lower() not in truthy:
    fail("set DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE=1 to confirm the isolated overwrite")

db_name = database_name(os.environ["DP_PG_DSN"])
if re.fullmatch(r"dp_p1a_smoke(?:_[A-Za-z0-9]+)?", db_name) is None:
    fail(
        "DP_PG_DSN database must match dp_p1a_smoke or dp_p1a_smoke_<suffix>; "
        f"got {db_name!r}"
    )

catalog_name = os.environ["DP_ICEBERG_CATALOG_NAME"]
if re.fullmatch(r"data_platform_p1a_smoke(?:_[A-Za-z0-9]+)?", catalog_name) is None:
    fail(
        "DP_ICEBERG_CATALOG_NAME must match data_platform_p1a_smoke or "
        f"data_platform_p1a_smoke_<suffix>; got {catalog_name!r}"
    )

smoke_work_dir = Path(os.environ["DP_SMOKE_WORK_DIR"]).expanduser().resolve(strict=False)
smoke_token = re.compile(r"(?:^|[^A-Za-z0-9])(?:p1a[-_]?smoke|smoke[-_]?p1a)(?:$|[^A-Za-z0-9])")
if smoke_token.search(str(smoke_work_dir)) is None:
    fail("DP_SMOKE_WORK_DIR path must include p1a-smoke, p1a_smoke, smoke-p1a, or smoke_p1a")

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
  "${LOG_DIR}" \
  "${PROFILES_DIR}" \
  "${DBT_TARGET_DIR}"

cat > "${PROFILES_DIR}/profiles.yml" <<YAML
data_platform:
  target: smoke
  outputs:
    smoke:
      type: duckdb
      path: "{{ env_var('DP_DUCKDB_PATH') }}"
      threads: 1
YAML

step_index=0
started_at="$(date +%s)"

run_step() {
  local name="$1"
  shift
  step_index=$((step_index + 1))
  local log_file="${LOG_DIR}/step_${step_index}.log"

  printf '[smoke-p1a] step %d: %s\n' "${step_index}" "${name}"
  if "$@" >"${log_file}" 2>&1; then
    return 0
  fi

  local exit_code=$?
  {
    printf '\n[smoke-p1a] step failed: %s (exit %d)\n' "${name}" "${exit_code}"
    printf '[smoke-p1a] last 50 log lines from %s:\n' "${log_file}"
    tail -n 50 "${log_file}" || true
  } >&2
  exit "${exit_code}"
}

seed_tushare_fixture() {
  "${PYTHON}" - <<'PY'
from __future__ import annotations

from datetime import date
import uuid

import pandas as pd
import pyarrow as pa

from data_platform.adapters.tushare import (
    TUSHARE_NAMECHANGE_ASSET,
    TUSHARE_STOCK_COMPANY_ASSET,
    TushareAdapter,
)
from data_platform.raw import RawWriter


class MockTushareClient:
    def stock_basic(self, **_kwargs: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "Ping An Bank",
                    "area": "Shenzhen",
                    "industry": "Banking",
                    "market": "Main Board",
                    "list_status": "L",
                    "list_date": "19910403",
                    "delist_date": None,
                    "is_hs": "S",
                    "act_name": "fixture",
                    "act_ent_type": "fixture",
                    "cnspell": "payh",
                    "curr_type": "CNY",
                    "enname": "Ping An Bank Co Ltd",
                    "exchange": "SZSE",
                    "fullname": "Ping An Bank Co Ltd",
                },
                {
                    "ts_code": "000002.SZ",
                    "symbol": "000002",
                    "name": "Vanke A",
                    "area": "Shenzhen",
                    "industry": "Real Estate",
                    "market": "Main Board",
                    "list_status": "L",
                    "list_date": "19910129",
                    "delist_date": None,
                    "is_hs": "S",
                    "act_name": "fixture",
                    "act_ent_type": "fixture",
                    "cnspell": "wka",
                    "curr_type": "CNY",
                    "enname": "China Vanke Co Ltd",
                    "exchange": "SZSE",
                    "fullname": "China Vanke Co Ltd",
                },
                {
                    "ts_code": "300001.SZ",
                    "symbol": "300001",
                    "name": "Teruide",
                    "area": "Qingdao",
                    "industry": "Electrical Equipment",
                    "market": "ChiNext",
                    "list_status": "L",
                    "list_date": "20091030",
                    "delist_date": None,
                    "is_hs": "N",
                    "act_name": "fixture",
                    "act_ent_type": "fixture",
                    "cnspell": "tld",
                    "curr_type": "CNY",
                    "enname": "Qingdao TGOOD Electric Co Ltd",
                    "exchange": "SZSE",
                    "fullname": "Qingdao TGOOD Electric Co Ltd",
                },
            ]
        )


adapter = TushareAdapter(token="mock-token", client=MockTushareClient())
table = adapter.fetch("tushare_stock_basic", {})
writer = RawWriter()
for empty_asset in (TUSHARE_STOCK_COMPANY_ASSET, TUSHARE_NAMECHANGE_ASSET):
    writer.write_arrow(
        adapter.source_id(),
        empty_asset.dataset,
        date(2026, 4, 15),
        str(uuid.uuid4()),
        pa.table(
            {
                field.name: pa.array([], type=field.type)
                for field in empty_asset.schema
            },
            schema=empty_asset.schema,
        ),
    )
artifact = writer.write_arrow(
    adapter.source_id(),
    "stock_basic",
    date(2026, 4, 15),
    str(uuid.uuid4()),
    table,
)
print(artifact.path)
PY
}

query_canonical_with_duckdb() {
  "${PYTHON}" - <<'PY'
from __future__ import annotations

import json

from data_platform.serving.reader import get_canonical_stock_basic


expected_columns = [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "market",
    "list_date",
    "is_active",
    "canonical_loaded_at",
]

table = get_canonical_stock_basic()
if table.num_rows != 3:
    raise SystemExit(f"expected 3 canonical_v2.stock_basic rows, got {table.num_rows}")
if table.schema.names != expected_columns:
    raise SystemExit(
        "unexpected canonical_v2.stock_basic columns: "
        + json.dumps(table.schema.names, sort_keys=True)
    )

print(json.dumps({"columns": table.schema.names, "row_count": table.num_rows}))
PY
}

run_step "migrate" "${PYTHON}" -m data_platform.ddl.runner --upgrade
run_step "init catalog" "${PYTHON}" "${ROOT_DIR}/scripts/init_iceberg_catalog.py"
run_step "ensure tables" "${PYTHON}" -m data_platform.ddl.iceberg_tables --ensure
run_step "fetch tushare fixture" seed_tushare_fixture
run_step "dbt run" "${ROOT_DIR}/scripts/dbt.sh" run --profiles-dir "${PROFILES_DIR}" --target-path "${DBT_TARGET_DIR}" --select +mart_stock_basic_v2 +mart_lineage_stock_basic
run_step "canonical write" "${PYTHON}" -m data_platform.serving.canonical_writer --table stock_basic
run_step "reader query" query_canonical_with_duckdb

duration_s=$(($(date +%s) - started_at))
printf 'P1a smoke OK duration_s=%d log_dir=%s\n' "${duration_s}" "${LOG_DIR}"
