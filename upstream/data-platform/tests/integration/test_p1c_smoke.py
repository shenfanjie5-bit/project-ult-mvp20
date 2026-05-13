from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from data_platform.smoke.p1c import (
    P1C_CANDIDATE_COUNT,
    P1C_FORMAL_OBJECT_TYPE,
    P1C_FORMAL_TABLE_IDENTIFIER,
    P1cSmokeResult,
    run_p1c_smoke,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DURATION_STEPS = {
    "submit",
    "validate",
    "freeze",
    "publish_manifest",
    "formal_latest",
}


@dataclass(frozen=True, slots=True)
class P1cTestContext:
    dsn: str
    engine: Any


def test_p1c_smoke_end_to_end(p1c_context: P1cTestContext) -> None:
    first = run_p1c_smoke(partition_date=date(2026, 4, 16))
    second = run_p1c_smoke(partition_date=date(2026, 4, 16))

    _assert_smoke_result(first, "CYCLE_20260416", p1c_context.engine)
    _assert_smoke_result(second, "CYCLE_20260417", p1c_context.engine)
    assert first.cycle_id != second.cycle_id
    assert first.manifest_snapshot_id != second.manifest_snapshot_id

    from data_platform.cycle import get_publish_manifest
    from data_platform.serving.formal import get_formal_by_id, get_formal_latest

    first_manifest = get_publish_manifest(first.cycle_id)
    second_manifest = get_publish_manifest(second.cycle_id)
    assert (
        first_manifest.formal_table_snapshots[P1C_FORMAL_TABLE_IDENTIFIER].snapshot_id
        == first.manifest_snapshot_id
    )
    assert (
        second_manifest.formal_table_snapshots[P1C_FORMAL_TABLE_IDENTIFIER].snapshot_id
        == second.manifest_snapshot_id
    )

    latest = get_formal_latest(P1C_FORMAL_OBJECT_TYPE)
    first_by_id = get_formal_by_id(first.cycle_id, P1C_FORMAL_OBJECT_TYPE)
    second_by_id = get_formal_by_id(second.cycle_id, P1C_FORMAL_OBJECT_TYPE)

    assert latest.snapshot_id == second.manifest_snapshot_id
    assert latest.snapshot_id == second_by_id.snapshot_id
    assert first_by_id.snapshot_id == first.manifest_snapshot_id
    assert latest.payload.column("cycle_id").to_pylist() == [second.cycle_id]
    assert first_by_id.payload.column("cycle_id").to_pylist() == [first.cycle_id]


def test_smoke_p1c_script_requires_dp_pg_dsn(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DP_PG_DSN", None)
    env["DP_SMOKE_WORK_DIR"] = str(tmp_path / "p1c-smoke")
    env["PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "smoke_p1c.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 2
    assert "DP_PG_DSN is required" in result.stderr


def test_smoke_p1c_script_rejects_unsafe_target_before_database(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DP_PG_DSN"] = "postgresql://dp:dp@localhost/postgres"
    env["DP_SMOKE_WORK_DIR"] = str(tmp_path / "p1c-smoke")
    env["DP_ENV"] = "dev"
    env["PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "smoke_p1c.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 2
    assert "DP_ENV must be test for smoke-p1c" in result.stderr


@pytest.fixture()
def p1c_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[P1cTestContext]:
    _require_p1c_dependencies()

    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("P1c smoke integration requires DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="P1c smoke integration requires SQLAlchemy",
    )
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="P1c smoke integration requires SQLAlchemy",
    ).SQLAlchemyError
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="P1c smoke integration requires the migration runner",
    )

    database_name = f"dp_p1c_smoke_test_{uuid4().hex}"
    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_created = False
    try:
        try:
            with admin_engine.connect() as connection:
                connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
            database_created = True
        except sqlalchemy_error as exc:
            pytest.skip(
                "P1c smoke integration requires permission to create a test database: "
                f"{exc}"
            )

        test_dsn = _database_dsn(admin_dsn, database_name)
        runner_module.MigrationRunner().apply_pending(test_dsn)

        monkeypatch.setenv("DP_PG_DSN", test_dsn)
        monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "raw"))
        monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "warehouse"))
        monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "p1c.duckdb"))
        monkeypatch.setenv("DP_ICEBERG_CATALOG_NAME", f"p1c_smoke_{uuid4().hex}")
        _reset_settings_cache()
        _initialize_catalog()

        engine = _create_engine(test_dsn)
        try:
            yield P1cTestContext(dsn=test_dsn, engine=engine)
        finally:
            engine.dispose()
            _reset_settings_cache()
    finally:
        if database_created:
            with admin_engine.connect() as connection:
                connection.execute(
                    sqlalchemy.text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :database_name
                          AND pid <> pg_backend_pid()
                        """
                    ),
                    {"database_name": database_name},
                )
                connection.execute(
                    sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"')
                )
        admin_engine.dispose()


def _assert_smoke_result(
    result: P1cSmokeResult,
    expected_cycle_id: str,
    engine: Any,
) -> None:
    assert result.cycle_id == expected_cycle_id
    assert result.candidate_count == P1C_CANDIDATE_COUNT
    assert result.manifest_snapshot_id > 0
    assert REQUIRED_DURATION_STEPS.issubset(result.duration_ms)
    assert _selection_count(engine, result.cycle_id) == result.candidate_count


def _selection_count(engine: Any, cycle_id: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                _text(
                    """
                    SELECT count(*)::integer
                    FROM data_platform.cycle_candidate_selection
                    WHERE cycle_id = :cycle_id
                    """
                ),
                {"cycle_id": cycle_id},
            ).scalar_one()
        )


def _initialize_catalog() -> None:
    from data_platform.serving.catalog import DEFAULT_NAMESPACES, ensure_namespaces, load_catalog

    catalog = load_catalog()
    ensure_namespaces(catalog, DEFAULT_NAMESPACES)


def _require_p1c_dependencies() -> None:
    for module_name in ("pyarrow", "pyiceberg", "sqlalchemy", "pydantic_settings"):
        pytest.importorskip(module_name, reason=f"P1c smoke integration requires {module_name}")


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="P1c smoke integration requires SQLAlchemy",
    )
    from data_platform.serving.catalog import _sqlalchemy_postgres_uri

    return sqlalchemy.create_engine(_sqlalchemy_postgres_uri(dsn), **kwargs)


def _database_dsn(admin_dsn: str, database_name: str) -> str:
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="P1c smoke integration requires SQLAlchemy",
    ).make_url
    return (
        make_url(_plain_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _plain_postgres_uri(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        return "postgresql://" + dsn.removeprefix("jdbc:postgresql://")
    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql://" + dsn.removeprefix("postgresql+psycopg://")
    if dsn.startswith("postgres://"):
        return "postgresql://" + dsn.removeprefix("postgres://")
    return dsn


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="P1c smoke integration requires SQLAlchemy",
    )
    return sqlalchemy.text(sql)


def _reset_settings_cache() -> None:
    from data_platform.config import reset_settings_cache

    reset_settings_cache()
