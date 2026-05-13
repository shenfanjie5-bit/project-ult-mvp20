"""SQL migration runner for PostgreSQL-backed data-platform metadata."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from data_platform.config import get_settings


MIGRATION_FILENAME_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql$")
METADATA_TABLE_NAME = "dp_schema_migrations"
DEFAULT_ADVISORY_LOCK_ID = 91234


@dataclass(frozen=True, slots=True)
class Migration:
    """A SQL migration loaded from disk."""

    version: str
    name: str
    path: Path
    sql: str


class MigrationError(RuntimeError):
    """Raised when one migration fails inside its transaction."""

    def __init__(self, version: str, sql: str, cause: BaseException) -> None:
        self.version = version
        self.sql = sql
        self.cause = cause
        super().__init__(f"migration {version} failed: {cause}")


class MigrationRunner:
    """Apply ordered SQL migrations against PostgreSQL."""

    def __init__(
        self,
        *,
        migrations_path: Path | None = None,
        advisory_lock_id: int = DEFAULT_ADVISORY_LOCK_ID,
    ) -> None:
        self.migrations_path = migrations_path or Path(__file__).with_name("migrations")
        self.advisory_lock_id = int(advisory_lock_id)

    def apply_pending(self, dsn: str) -> list[str]:
        """Apply pending migrations and return the newly applied versions."""

        migrations = self._load_migrations()
        engine = self._create_engine(dsn)
        try:
            with engine.connect() as connection:
                self._acquire_lock(connection)
                try:
                    self._ensure_metadata_table(connection)
                    applied_versions = self._fetch_applied_versions(connection)
                    connection.commit()

                    pending_migrations = [
                        migration
                        for migration in migrations
                        if migration.version not in applied_versions
                    ]
                    applied_now: list[str] = []
                    for migration in pending_migrations:
                        self._apply_migration(connection, migration)
                        applied_now.append(migration.version)
                    return applied_now
                finally:
                    self._release_lock(connection)
        finally:
            engine.dispose()

    def list_pending(self, dsn: str) -> list[str]:
        """Return pending migration versions without mutating the database."""

        migrations = self._load_migrations()
        engine = self._create_engine(dsn)
        try:
            with engine.connect() as connection:
                self._acquire_lock(connection)
                try:
                    if self._metadata_table_exists(connection):
                        applied_versions = self._fetch_applied_versions(connection)
                    else:
                        applied_versions = set()
                    connection.commit()
                    return [
                        migration.version
                        for migration in migrations
                        if migration.version not in applied_versions
                    ]
                finally:
                    self._release_lock(connection)
        finally:
            engine.dispose()

    def _create_engine(self, dsn: str) -> Engine:
        return create_engine(_sqlalchemy_postgres_uri(dsn))

    def _load_migrations(self) -> list[Migration]:
        if not self.migrations_path.exists():
            msg = f"migrations path does not exist: {self.migrations_path}"
            raise FileNotFoundError(msg)

        migrations: list[Migration] = []
        seen_versions: set[str] = set()
        for path in sorted(self.migrations_path.glob("*.sql")):
            match = MIGRATION_FILENAME_PATTERN.fullmatch(path.name)
            if match is None:
                msg = (
                    "migration filenames must use NNNN_<snake_case>.sql: "
                    f"{path.name}"
                )
                raise ValueError(msg)

            version = match.group("version")
            if version in seen_versions:
                msg = f"duplicate migration version: {version}"
                raise ValueError(msg)
            seen_versions.add(version)

            migrations.append(
                Migration(
                    version=version,
                    name=match.group("name"),
                    path=path,
                    sql=path.read_text(encoding="utf-8"),
                )
            )

        return migrations

    def _acquire_lock(self, connection: Connection) -> None:
        connection.execute(text(f"SELECT pg_advisory_lock({self.advisory_lock_id})")).scalar_one()
        connection.commit()

    def _release_lock(self, connection: Connection) -> None:
        connection.execute(text(f"SELECT pg_advisory_unlock({self.advisory_lock_id})")).scalar_one()
        connection.commit()

    def _ensure_metadata_table(self, connection: Connection) -> None:
        with connection.begin():
            connection.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {METADATA_TABLE_NAME} (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
            )

    def _metadata_table_exists(self, connection: Connection) -> bool:
        result = connection.execute(
            text(f"SELECT to_regclass('public.{METADATA_TABLE_NAME}')")
        ).scalar_one()
        return result is not None

    def _fetch_applied_versions(self, connection: Connection) -> set[str]:
        rows = connection.execute(
            text(f"SELECT version FROM {METADATA_TABLE_NAME} ORDER BY version")
        ).scalars()
        return {str(row) for row in rows}

    def _apply_migration(self, connection: Connection, migration: Migration) -> None:
        try:
            with connection.begin():
                connection.exec_driver_sql(migration.sql)
                connection.execute(
                    text(
                        f"INSERT INTO {METADATA_TABLE_NAME} (version) "
                        "VALUES (:version)"
                    ),
                    {"version": migration.version},
                )
        except Exception as exc:
            raise MigrationError(migration.version, migration.sql, exc) from exc


def _resolve_dsn() -> str:
    return str(get_settings().pg_dsn)


def _sqlalchemy_postgres_uri(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgres://")
    return dsn


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply data-platform PostgreSQL migrations.")
    parser.add_argument("--upgrade", action="store_true", help="apply pending migrations")
    parser.add_argument("--dry-run", action="store_true", help="list pending migrations only")
    args = parser.parse_args(argv)

    if not args.upgrade:
        parser.error("only --upgrade is supported")

    runner = MigrationRunner()
    dsn = _resolve_dsn()
    versions = runner.list_pending(dsn) if args.dry_run else runner.apply_pending(dsn)
    for version in versions:
        print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
