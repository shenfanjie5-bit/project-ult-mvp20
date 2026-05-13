from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

sqlalchemy = pytest.importorskip(
    "sqlalchemy",
    reason="PostgreSQL migration tests require SQLAlchemy",
)
make_url = pytest.importorskip(
    "sqlalchemy.engine",
    reason="PostgreSQL migration tests require SQLAlchemy",
).make_url
SQLAlchemyError = pytest.importorskip(
    "sqlalchemy.exc",
    reason="PostgreSQL migration tests require SQLAlchemy",
).SQLAlchemyError

from data_platform.ddl import runner as runner_module  # noqa: E402
from data_platform.ddl.runner import MigrationError, MigrationRunner  # noqa: E402


def write_migration(migrations_path: Path, filename: str, sql: str) -> None:
    migrations_path.mkdir(parents=True, exist_ok=True)
    (migrations_path / filename).write_text(sql, encoding="utf-8")


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL migration tests require DATABASE_URL or DP_PG_DSN")

    admin_engine = sqlalchemy.create_engine(
        runner_module._sqlalchemy_postgres_uri(admin_dsn),
        isolation_level="AUTOCOMMIT",
    )
    database_name = f"dp_migrations_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL migration tests require permission to create test databases: "
            f"{exc}"
        )

    test_dsn = (
        make_url(runner_module._sqlalchemy_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        yield test_dsn
    finally:
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
            connection.execute(sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def fetch_scalar(dsn: str, sql: str) -> object:
    engine = sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn))
    try:
        with engine.connect() as connection:
            return connection.execute(sqlalchemy.text(sql)).scalar_one()
    finally:
        engine.dispose()


def fetch_versions(dsn: str) -> list[str]:
    engine = sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn))
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                sqlalchemy.text("SELECT version FROM dp_schema_migrations ORDER BY version")
            ).scalars()
            return [str(row) for row in rows]
    finally:
        engine.dispose()


def test_load_migrations_requires_filename_format(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001-init.sql", "SELECT 1;")
    runner = MigrationRunner(migrations_path=tmp_path)

    with pytest.raises(ValueError, match="NNNN_<snake_case>"):
        runner._load_migrations()


def test_load_migrations_rejects_duplicate_versions(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001_init.sql", "SELECT 1;")
    write_migration(tmp_path, "0001_other.sql", "SELECT 2;")
    runner = MigrationRunner(migrations_path=tmp_path)

    with pytest.raises(ValueError, match="duplicate migration version: 0001"):
        runner._load_migrations()


def test_create_engine_rewrites_plain_postgres_dsn_to_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_dsns: list[str] = []
    fake_engine = object()

    def fake_create_engine(dsn: str) -> object:
        seen_dsns.append(dsn)
        return fake_engine

    monkeypatch.setattr(runner_module, "create_engine", fake_create_engine)

    assert MigrationRunner()._create_engine("postgresql://dp:dp@localhost/db") is fake_engine
    assert seen_dsns == ["postgresql+psycopg://dp:dp@localhost/db"]


def test_apply_pending_is_idempotent_and_creates_schema(postgres_dsn: str) -> None:
    runner = MigrationRunner()

    assert runner.apply_pending(postgres_dsn) == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert runner.apply_pending(postgres_dsn) == []
    assert fetch_versions(postgres_dsn) == ["0001", "0002", "0003", "0004", "0005", "0006"]
    assert fetch_scalar(postgres_dsn, "SELECT to_regclass('public.dp_schema_migrations')")
    assert (
        fetch_scalar(
            postgres_dsn,
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name = 'data_platform'",
        )
        == "data_platform"
    )


def test_dry_run_lists_pending_without_creating_metadata_table(
    postgres_dsn: str,
    tmp_path: Path,
) -> None:
    migrations_path = tmp_path / "migrations"
    write_migration(
        migrations_path,
        "0001_init.sql",
        "CREATE SCHEMA IF NOT EXISTS data_platform;",
    )
    runner = MigrationRunner(migrations_path=migrations_path)

    assert runner.list_pending(postgres_dsn) == ["0001"]
    assert fetch_scalar(postgres_dsn, "SELECT to_regclass('public.dp_schema_migrations')") is None


def test_failed_migration_rolls_back_version_record(
    postgres_dsn: str,
    tmp_path: Path,
) -> None:
    migrations_path = tmp_path / "migrations"
    write_migration(migrations_path, "0001_bad.sql", "CREATE TABLE broken (")
    runner = MigrationRunner(migrations_path=migrations_path)

    with pytest.raises(MigrationError) as exc_info:
        runner.apply_pending(postgres_dsn)

    assert exc_info.value.version == "0001"
    assert "CREATE TABLE broken" in exc_info.value.sql
    assert fetch_scalar(postgres_dsn, "SELECT count(*) FROM dp_schema_migrations") == 0


def test_concurrent_runners_serialize_with_advisory_lock(
    postgres_dsn: str,
    tmp_path: Path,
) -> None:
    migrations_path = tmp_path / "migrations"
    write_migration(
        migrations_path,
        "0001_init.sql",
        "SELECT pg_sleep(0.2); CREATE SCHEMA IF NOT EXISTS data_platform;",
    )
    runner = MigrationRunner(migrations_path=migrations_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(runner.apply_pending, postgres_dsn) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert sorted(results) == [[], ["0001"]]
    assert fetch_versions(postgres_dsn) == ["0001"]
