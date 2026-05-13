from __future__ import annotations

from collections.abc import Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import platform
import sys
from threading import Barrier
from time import perf_counter
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pyiceberg
import pytest
import sqlalchemy
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.exceptions import CommitFailedException
from pyiceberg.table import Table
from pyiceberg.types import StringType
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from data_platform.serving.catalog import _sqlalchemy_postgres_uri


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPIKE_REPORT_PATH = PROJECT_ROOT / "docs" / "spike" / "iceberg-write-chain.md"
TABLE_IDENTIFIER = "canonical.stock_basic"
BASE_SCHEMA = pa.schema(
    [
        pa.field("ts_code", pa.string()),
        pa.field("name", pa.string()),
    ]
)
EXTENDED_SCHEMA = pa.schema(
    [
        pa.field("ts_code", pa.string()),
        pa.field("name", pa.string()),
        pa.field("extra", pa.string()),
    ]
)
SPIKE_CASES = {
    "test_add_column_backward_compat": "add_column_backward_compat",
    "test_time_travel_by_snapshot": "time_travel_by_snapshot",
    "test_concurrent_overwrite": "concurrent_overwrite",
}


@dataclass(frozen=True, slots=True)
class IcebergSpikeContext:
    catalog_name: str
    catalog_uri: str
    warehouse_path: Path
    pg_schema: str

    def load_catalog(self) -> SqlCatalog:
        return SqlCatalog(
            self.catalog_name,
            uri=self.catalog_uri,
            warehouse=str(self.warehouse_path),
            pool_pre_ping="true",
            init_catalog_tables="true",
        )


@dataclass(frozen=True, slots=True)
class SpikeCaseResult:
    name: str
    status: str
    duration_ms: int
    detail: str


@dataclass(frozen=True, slots=True)
class WorkerResult:
    status: str
    error_type: str | None = None
    detail: str | None = None


SPIKE_RESULTS: dict[str, SpikeCaseResult] = {}


@pytest.fixture()
def iceberg_context(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> Generator[IcebergSpikeContext]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        detail = (
            "PostgreSQL Iceberg spike tests require DATABASE_URL or DP_PG_DSN; "
            "the sandbox must not start database processes"
        )
        pytest.skip(detail)

    schema_name = f"dp_spike_{uuid4().hex}"
    catalog_name = f"data_platform_spike_{uuid4().hex}"
    warehouse_path = tmp_path / "iceberg-warehouse"
    admin_engine = create_engine(
        _sqlalchemy_postgres_uri(admin_dsn),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        detail = (
            "PostgreSQL Iceberg spike tests require a reachable database and "
            f"CREATE SCHEMA permission: {exc}"
        )
        pytest.skip(detail)

    try:
        yield IcebergSpikeContext(
            catalog_name=catalog_name,
            catalog_uri=_catalog_uri_with_schema(admin_dsn, schema_name),
            warehouse_path=warehouse_path,
            pg_schema=schema_name,
        )
    finally:
        try:
            with admin_engine.connect() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        finally:
            admin_engine.dispose()


@pytest.mark.spike
def test_add_column_backward_compat(iceberg_context: IcebergSpikeContext) -> None:
    with _spike_case("test_add_column_backward_compat"):
        catalog = iceberg_context.load_catalog()
        table = _create_stock_basic_table(catalog)

        table.append(_stock_basic_table([("000001.SZ", "v1")]))
        table = table.refresh()
        v1_snapshot_id = _current_snapshot_id(table)

        table.update_schema().add_column("extra", StringType()).commit()
        table = table.refresh()
        table.overwrite(_stock_basic_table([("000002.SZ", "v2", "new")], with_extra=True))
        table = table.refresh()

        old_version = table.scan(snapshot_id=v1_snapshot_id).to_arrow()
        assert old_version.schema.names == ["ts_code", "name"]
        assert "extra" not in old_version.schema.names
        assert old_version.to_pylist() == [{"ts_code": "000001.SZ", "name": "v1"}]


@pytest.mark.spike
def test_time_travel_by_snapshot(iceberg_context: IcebergSpikeContext) -> None:
    with _spike_case("test_time_travel_by_snapshot"):
        catalog = iceberg_context.load_catalog()
        table = _create_stock_basic_table(catalog)
        expected_versions: list[tuple[int, list[dict[str, str]]]] = []

        for version in range(1, 4):
            rows = [(f"{version:06d}.SZ", f"version-{version}-{index}") for index in range(version)]
            expected_rows = [{"ts_code": ts_code, "name": name} for ts_code, name in rows]
            if version == 1:
                table.append(_stock_basic_table(rows))
            else:
                table.overwrite(_stock_basic_table(rows))
            table = table.refresh()
            expected_versions.append((_current_snapshot_id(table), expected_rows))

        for snapshot_id, expected_rows in expected_versions:
            snapshot_table = table.scan(snapshot_id=snapshot_id).to_arrow()
            assert snapshot_table.num_rows == len(expected_rows)
            assert snapshot_table.to_pylist() == expected_rows


@pytest.mark.spike
def test_concurrent_overwrite(iceberg_context: IcebergSpikeContext) -> None:
    with _spike_case("test_concurrent_overwrite"):
        catalog = iceberg_context.load_catalog()
        table = _create_stock_basic_table(catalog)
        table.append(_stock_basic_table([("000000.SZ", "seed")]))
        table = table.refresh()

        barrier = Barrier(2)
        worker_rows = [
            [("000101.SZ", "worker-1-a"), ("000102.SZ", "worker-1-b")],
            [
                ("000201.SZ", "worker-2-a"),
                ("000202.SZ", "worker-2-b"),
                ("000203.SZ", "worker-2-c"),
            ],
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(_overwrite_from_stale_table, iceberg_context, barrier, rows)
                for rows in worker_rows
            ]
            results = [future.result(timeout=30) for future in futures]

        unexpected = [result for result in results if result.status == "unexpected"]
        assert unexpected == []
        assert sum(1 for result in results if result.status == "ok") >= 1
        assert sum(1 for result in results if result.status == "commit_failed") >= 1

        final_table = iceberg_context.load_catalog().load_table(TABLE_IDENTIFIER)
        final_rows = final_table.scan().to_arrow()
        assert final_rows.num_rows in {len(rows) for rows in worker_rows}


def _create_stock_basic_table(catalog: SqlCatalog) -> Table:
    catalog.create_namespace_if_not_exists(("canonical",))
    return catalog.create_table(TABLE_IDENTIFIER, schema=BASE_SCHEMA)


def _stock_basic_table(
    rows: Sequence[tuple[str, str] | tuple[str, str, str]],
    *,
    with_extra: bool = False,
) -> pa.Table:
    if with_extra:
        return pa.table(
            {
                "ts_code": [row[0] for row in rows],
                "name": [row[1] for row in rows],
                "extra": [row[2] for row in rows],
            },
            schema=EXTENDED_SCHEMA,
        )

    return pa.table(
        {
            "ts_code": [row[0] for row in rows],
            "name": [row[1] for row in rows],
        },
        schema=BASE_SCHEMA,
    )


def _current_snapshot_id(table: Table) -> int:
    snapshot = table.current_snapshot()
    assert snapshot is not None
    return snapshot.snapshot_id


def _overwrite_from_stale_table(
    iceberg_context: IcebergSpikeContext,
    barrier: Barrier,
    rows: Sequence[tuple[str, str]],
) -> WorkerResult:
    catalog = iceberg_context.load_catalog()
    stale_table = catalog.load_table(TABLE_IDENTIFIER)
    barrier.wait(timeout=10)

    try:
        stale_table.overwrite(_stock_basic_table(rows))
    except CommitFailedException as exc:
        return WorkerResult(status="commit_failed", error_type=type(exc).__name__, detail=str(exc))
    except Exception as exc:
        return WorkerResult(status="unexpected", error_type=type(exc).__name__, detail=str(exc))
    return WorkerResult(status="ok")


def _catalog_uri_with_schema(dsn: str, schema_name: str) -> str:
    url = make_url(_sqlalchemy_postgres_uri(dsn))
    query = dict(url.query)
    query["options"] = f"-csearch_path={schema_name}"
    return url.set(query=query).render_as_string(hide_password=False)


class _spike_case:
    def __init__(self, test_name: str) -> None:
        self.test_name = test_name
        self.start_time = 0.0

    def __enter__(self) -> None:
        self.start_time = perf_counter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        duration_ms = int((perf_counter() - self.start_time) * 1000)
        if exc is None:
            _record_case(self.test_name, "pass", duration_ms, "pass")
            return False

        status = "skip" if isinstance(exc, pytest.skip.Exception) else "fail"
        detail = f"{type(exc).__name__}: {exc}"
        _record_case(self.test_name, status, duration_ms, detail)
        return False


def _record_case(test_name: str, status: str, duration_ms: int, detail: str) -> None:
    case_name = SPIKE_CASES[test_name]
    SPIKE_RESULTS[test_name] = SpikeCaseResult(
        name=case_name,
        status=status,
        duration_ms=duration_ms,
        detail=detail,
    )
    _write_spike_report()


def _write_spike_report() -> None:
    SPIKE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    completed = sum(
        1 for test_name in SPIKE_CASES if SPIKE_RESULTS.get(test_name, None) is not None
    )
    passed = sum(1 for result in SPIKE_RESULTS.values() if result.status == "pass")
    success_rate = (passed / len(SPIKE_CASES)) * 100
    success_rate_text = (
        f"{success_rate:.0f}%" if success_rate.is_integer() else f"{success_rate:.1f}%"
    )
    overall_status = "pass" if passed == len(SPIKE_CASES) else "fail"
    passing_conclusion = (
        f"- P1a Iceberg 写入链 spike 成功率: {success_rate_text}"
        if overall_status == "pass"
        else "- Passing run conclusion: pending"
    )
    risk_note = (
        "PG-backed SQL catalog validated for schema evolution, snapshot time travel, "
        "and optimistic commit conflict handling."
        if overall_status == "pass"
        else "Spike is incomplete or failing; inspect the pytest output and the rows below."
    )

    rows = []
    for test_name, case_name in SPIKE_CASES.items():
        result = SPIKE_RESULTS.get(test_name)
        if result is None:
            rows.append(f"| `{case_name}` | not-run | 0 | pending |")
            continue
        rows.append(
            f"| `{result.name}` | {result.status} | {result.duration_ms} | "
            f"{_escape_markdown_table_cell(result.detail)} |"
        )

    content = "\n".join(
        [
            "# Iceberg Write Chain Spike",
            "",
            f"Generated at: {datetime.now(UTC).isoformat(timespec='seconds')}",
            "",
            "## Environment",
            "",
            f"- Python: {sys.version.split()[0]}",
            f"- Platform: {platform.platform()}",
            f"- PyIceberg: {pyiceberg.__version__}",
            f"- PyArrow: {pa.__version__}",
            f"- SQLAlchemy: {sqlalchemy.__version__}",
            "",
            "## Results",
            "",
            "| Case | Status | Duration ms | Detail |",
            "|------|--------|-------------|--------|",
            *rows,
            "",
            "## Conclusion",
            "",
            f"- Completed cases: {completed}/{len(SPIKE_CASES)}",
            f"- Conclusion: {overall_status}",
            passing_conclusion,
            "",
            "## Risk Notes",
            "",
            f"- {risk_note}",
            "- Lite filesystem warehouse only; S3/MinIO is intentionally out of scope.",
            "- PostgreSQL metadata schema is temporary and dropped after each test.",
            "",
        ]
    )
    SPIKE_REPORT_PATH.write_text(content, encoding="utf-8")


def _escape_markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
