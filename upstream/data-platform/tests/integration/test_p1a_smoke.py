from __future__ import annotations

from collections.abc import Iterator
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from data_platform.ddl.runner import _sqlalchemy_postgres_uri


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROW_COUNT = 3
EXPECTED_COLUMNS = [
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


@pytest.fixture()
def postgres_dsn() -> Iterator[str]:
    admin_dsn = os.environ.get("DATABASE_URL")
    if not admin_dsn:
        pytest.skip("P1a smoke integration requires DATABASE_URL")

    admin_engine = create_engine(_sqlalchemy_postgres_uri(admin_dsn), isolation_level="AUTOCOMMIT")
    database_name = f"dp_p1a_smoke_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        pytest.skip(f"P1a smoke integration requires a usable PostgreSQL DATABASE_URL: {exc}")

    test_dsn = make_url(admin_dsn).set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        yield test_dsn
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def test_p1a_smoke_pipeline_is_repeatable(
    tmp_path: Path,
    postgres_dsn: str,
) -> None:
    env = _smoke_env(tmp_path, postgres_dsn)

    first = _run_smoke(env)
    second = _run_smoke(env)
    payload = _query_canonical_payload(env)

    assert "P1a smoke OK" in first.stdout
    assert "P1a smoke OK" in second.stdout
    assert _duration_seconds(second.stdout) < 300
    assert payload["catalog_row_count"] == FIXTURE_ROW_COUNT
    assert payload["duckdb_row_count"] == FIXTURE_ROW_COUNT
    assert payload["duckdb_columns"] == EXPECTED_COLUMNS


def test_p1a_smoke_requires_dp_pg_dsn(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)
    env["DATABASE_URL"] = "postgresql://dp:dp@localhost/data_platform"

    result = _run_smoke_raw(env)

    assert result.returncode == 2
    assert "DP_PG_DSN is required" in result.stderr
    assert "DATABASE_URL is not used" in result.stderr


def test_p1a_smoke_allows_explicit_skip_without_dp_pg_dsn(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)
    env["DP_SMOKE_P1A_ALLOW_SKIP"] = "1"

    result = _run_smoke_raw(env)

    assert result.returncode == 0
    assert "P1a smoke skipped" in result.stdout


def test_p1a_smoke_seed_fixture_writes_contract_valid_run_id(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", _seed_tushare_fixture_source()],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    artifact_path = Path(result.stdout.strip().splitlines()[-1])
    run_id = artifact_path.name.removesuffix(".parquet")
    parsed_run_id = UUID(run_id)
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text())

    assert parsed_run_id.version == 4
    assert run_id == str(parsed_run_id)
    assert run_id.startswith("p1a-smoke-") is False
    assert manifest["artifacts"][0]["run_id"] == run_id
    assert manifest["artifacts"][0]["row_count"] == FIXTURE_ROW_COUNT


def test_p1a_smoke_refuses_non_smoke_database(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)
    env.update(
        {
            "DP_PG_DSN": "postgresql://dp:dp@localhost/data_platform",
            "DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE": "1",
        }
    )

    result = _run_smoke_raw(env)

    assert result.returncode == 2
    assert "database must match dp_p1a_smoke" in result.stderr


def test_p1a_smoke_requires_destructive_confirmation(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)
    env["DP_PG_DSN"] = "postgresql://dp:dp@localhost/dp_p1a_smoke_local"

    result = _run_smoke_raw(env)

    assert result.returncode == 2
    assert "DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE=1" in result.stderr


def test_p1a_smoke_requires_test_env(tmp_path: Path) -> None:
    env = _base_script_env(tmp_path)
    env.update(
        {
            "DP_PG_DSN": "postgresql://dp:dp@localhost/dp_p1a_smoke_local",
            "DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE": "1",
        }
    )
    env.pop("DP_ENV")

    result = _run_smoke_raw(env)

    assert result.returncode == 2
    assert "DP_ENV must be test" in result.stderr


def _smoke_env(tmp_path: Path, postgres_dsn: str) -> dict[str, str]:
    smoke_dir = tmp_path / "p1a-smoke"
    env = _base_script_env(tmp_path)
    env.update(
        {
            "DP_PG_DSN": postgres_dsn,
            "DP_SMOKE_WORK_DIR": str(smoke_dir),
            "DP_RAW_ZONE_PATH": str(smoke_dir / "raw"),
            "DP_ICEBERG_WAREHOUSE_PATH": str(smoke_dir / "warehouse"),
            "DP_DUCKDB_PATH": str(smoke_dir / "data_platform.duckdb"),
            "DP_ICEBERG_CATALOG_NAME": "data_platform_p1a_smoke",
            "DP_CANONICAL_USE_V2": "1",
            "DP_ENV": "test",
            "DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE": "1",
            "PYTHON": sys.executable,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
    )
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _base_script_env(tmp_path: Path) -> dict[str, str]:
    smoke_dir = tmp_path / "p1a-smoke"
    env = os.environ.copy()
    env.update(
        {
            "DP_SMOKE_WORK_DIR": str(smoke_dir),
            "DP_RAW_ZONE_PATH": str(smoke_dir / "raw"),
            "DP_ICEBERG_WAREHOUSE_PATH": str(smoke_dir / "warehouse"),
            "DP_DUCKDB_PATH": str(smoke_dir / "data_platform.duckdb"),
            "DP_ICEBERG_CATALOG_NAME": "data_platform_p1a_smoke",
            "DP_CANONICAL_USE_V2": "1",
            "DP_ENV": "test",
            "PYTHON": sys.executable,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
    )
    env.pop("DP_PG_DSN", None)
    env.pop("DATABASE_URL", None)
    env.pop("DP_SMOKE_P1A_ALLOW_SKIP", None)
    env.pop("DP_SMOKE_P1A_CONFIRM_DESTRUCTIVE", None)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run_smoke_raw(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "smoke_p1a.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _run_smoke(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = _run_smoke_raw(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped" not in result.stdout.lower()
    return result


def _seed_tushare_fixture_source() -> str:
    script = (PROJECT_ROOT / "scripts" / "smoke_p1a.sh").read_text()
    match = re.search(
        r"seed_tushare_fixture\(\) \{\n\s+\"\$\{PYTHON\}\" - <<'PY'\n(?P<source>.*?)\nPY\n\}",
        script,
        re.DOTALL,
    )
    assert match is not None
    return match.group("source")


def _query_canonical_payload(env: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from __future__ import annotations

import json

from data_platform.serving.catalog import load_catalog
from data_platform.serving.reader import get_canonical_stock_basic

catalog_table = load_catalog().load_table("canonical_v2.stock_basic").scan().to_arrow()
duckdb_table = get_canonical_stock_basic()
print(
    json.dumps(
        {
            "catalog_row_count": catalog_table.num_rows,
            "duckdb_columns": duckdb_table.schema.names,
            "duckdb_row_count": duckdb_table.num_rows,
        },
        sort_keys=True,
    )
)
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _duration_seconds(output: str) -> int:
    match = re.search(r"duration_s=(\d+)", output)
    assert match is not None, output
    return int(match.group(1))
