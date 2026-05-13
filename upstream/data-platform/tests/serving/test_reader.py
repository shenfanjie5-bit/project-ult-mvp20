from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Iterator

import duckdb
import pyarrow as pa
import pytest
from pyiceberg.catalog.memory import InMemoryCatalog

from data_platform.serving import reader
from data_platform.serving.canonical_datasets import USE_CANONICAL_V2_ENV_VAR
from data_platform.serving.canonical_writer import CANONICAL_V2_MART_LOAD_SPECS
from data_platform.serving.reader import (
    CanonicalTableNotFound,
    UnsupportedFilter,
    get_canonical_stock_basic,
    read_canonical,
    read_iceberg_snapshot,
    with_duckdb_connection,
)


StockBasicRow = tuple[str, str, str, str, str, str, date, bool, str, datetime]


@dataclass(frozen=True, slots=True)
class FakeSettings:
    duckdb_path: Path
    iceberg_warehouse_path: Path


@pytest.fixture
def stock_basic_duckdb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    duckdb_path = tmp_path / "canonical.duckdb"
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute(
            """
CREATE TABLE stock_basic (
    ts_code VARCHAR,
    symbol VARCHAR,
    name VARCHAR,
    area VARCHAR,
    industry VARCHAR,
    market VARCHAR,
    list_date DATE,
    is_active BOOLEAN,
    source_run_id VARCHAR,
    canonical_loaded_at TIMESTAMP
)
"""
        )
        connection.executemany(
            """
INSERT INTO stock_basic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""",
            stock_basic_rows(),
        )
        connection.execute(
            """
CREATE TABLE fact_price_bar (
    ts_code VARCHAR,
    trade_date DATE,
    freq VARCHAR,
    open DECIMAL(38, 18),
    close DECIMAL(38, 18),
    source_run_id VARCHAR,
    raw_loaded_at TIMESTAMP,
    canonical_loaded_at TIMESTAMP
)
"""
        )
        connection.executemany(
            """
INSERT INTO fact_price_bar VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""",
            price_bar_rows(),
        )
    finally:
        connection.close()

    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=duckdb_path,
            iceberg_warehouse_path=tmp_path / "warehouse",
        ),
    )
    monkeypatch.setattr(reader, "_load_iceberg_extension", lambda connection: None)
    monkeypatch.setattr(
        reader,
        "_canonical_table_expression",
        lambda table: reader._quote_identifier(table),
    )
    reader._duckdb_connection.cache_clear()
    yield duckdb_path
    reader._duckdb_connection.cache_clear()


def test_read_canonical_selects_requested_columns(stock_basic_duckdb: Path) -> None:
    table = read_canonical("stock_basic", columns=["ts_code", "name"])

    assert table.schema.names == ["ts_code", "name"]
    assert table.column("ts_code").to_pylist() == [
        "000001.SZ",
        "000002.SZ",
        "300001.SZ",
    ]


def test_read_canonical_applies_equals_filter(stock_basic_duckdb: Path) -> None:
    table = read_canonical("stock_basic", filters=[("market", "=", "主板")])

    assert table.num_rows == 2
    assert table.column("ts_code").to_pylist() == ["000001.SZ", "000002.SZ"]


def test_read_canonical_applies_in_filter(stock_basic_duckdb: Path) -> None:
    table = read_canonical(
        "stock_basic",
        columns=["ts_code", "market"],
        filters=[("market", "in", ["主板", "创业板"])],
    )

    assert table.num_rows == 3
    assert table.schema.names == ["ts_code", "market"]


def test_get_canonical_stock_basic_filters_active_rows_by_default(
    stock_basic_duckdb: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)

    active = get_canonical_stock_basic()
    all_rows = get_canonical_stock_basic(active_only=False)

    assert active.num_rows == 2
    assert active.column("ts_code").to_pylist() == ["000001.SZ", "300001.SZ"]
    assert all_rows.num_rows == 3


def test_get_canonical_stock_basic_default_uses_legacy_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = pa.table({"ts_code": ["000001.SZ"], "name": ["平安银行"]})
    calls: list[tuple[str, list[tuple[str, str, object]] | None]] = []

    def fake_read_canonical(
        table: str,
        columns: list[str] | None = None,
        filters: list[tuple[str, str, object]] | None = None,
    ) -> pa.Table:
        assert columns is None
        calls.append((table, filters))
        return expected

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    monkeypatch.setattr(reader, "read_canonical", fake_read_canonical)

    payload = get_canonical_stock_basic(active_only=True)

    assert payload == expected
    assert calls == [("stock_basic", [("is_active", "=", True)])]


def test_get_canonical_stock_basic_v2_uses_manifest_and_legacy_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "warehouse"
    legacy_metadata = (
        warehouse_path
        / "canonical"
        / "stock_basic"
        / "metadata"
        / "00001.metadata.json"
    )
    v2_metadata = (
        warehouse_path
        / "canonical_v2"
        / "stock_basic"
        / "metadata"
        / "00002.metadata.json"
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical",
        payload_key="tables",
        table_name="stock_basic",
        metadata_location=legacy_metadata,
        snapshot_id=101,
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical_v2",
        payload_key="canonical_v2_tables",
        table_name="stock_basic",
        metadata_location=v2_metadata,
        snapshot_id=202,
    )
    executed: list[tuple[str, list[object]]] = []
    expected = pa.table(
        {
            "security_id": ["000001.SZ"],
            "symbol": ["000001"],
            "display_name": ["平安银行"],
            "area": ["深圳"],
            "industry": ["银行"],
            "market": ["主板"],
            "list_date": [date(1991, 4, 3)],
            "is_active": [True],
            "canonical_loaded_at": [datetime(2024, 1, 1, 12, 0, 0)],
        }
    )

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected

    class FakeConnection:
        def execute(self, sql: str, parameters: list[object]) -> FakeResult:
            executed.append((sql, parameters))
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    payload = get_canonical_stock_basic(active_only=True)

    assert payload.schema.names == [
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
    assert payload.column("ts_code").to_pylist() == ["000001.SZ"]
    assert payload.column("name").to_pylist() == ["平安银行"]
    assert "security_id" not in payload.schema.names
    assert "display_name" not in payload.schema.names
    assert len(executed) == 1
    sql, parameters = executed[0]
    assert str(v2_metadata) in sql
    assert "snapshot_from_id = 202" in sql
    assert str(legacy_metadata) not in sql
    assert '"is_active" = ?' in sql
    assert parameters == [True]


def test_get_canonical_stock_basic_v2_all_rows_omits_active_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "warehouse"
    v2_metadata = (
        warehouse_path
        / "canonical_v2"
        / "stock_basic"
        / "metadata"
        / "00002.metadata.json"
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical_v2",
        payload_key="canonical_v2_tables",
        table_name="stock_basic",
        metadata_location=v2_metadata,
        snapshot_id=202,
    )
    executed: list[tuple[str, list[object]]] = []
    expected = pa.table(
        {
            "security_id": ["000001.SZ"],
            "symbol": ["000001"],
            "display_name": ["平安银行"],
            "area": ["深圳"],
            "industry": ["银行"],
            "market": ["主板"],
            "list_date": [date(1991, 4, 3)],
            "is_active": [True],
            "canonical_loaded_at": [datetime(2024, 1, 1, 12, 0, 0)],
        }
    )

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected

    class FakeConnection:
        def execute(self, sql: str, parameters: list[object]) -> FakeResult:
            executed.append((sql, parameters))
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    get_canonical_stock_basic(active_only=False)

    assert len(executed) == 1
    sql, parameters = executed[0]
    assert str(v2_metadata) in sql
    assert "WHERE" not in sql
    assert parameters == []


def test_get_canonical_stock_basic_v2_fails_closed_without_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=tmp_path / "warehouse",
        ),
    )

    with pytest.raises(CanonicalTableNotFound):
        get_canonical_stock_basic(active_only=False)


def test_read_canonical_reads_fact_price_bar_with_filter(stock_basic_duckdb: Path) -> None:
    table = read_canonical(
        "fact_price_bar",
        columns=["ts_code", "trade_date", "freq"],
        filters=[("freq", "=", "daily")],
    )

    assert table.schema.names == ["ts_code", "trade_date", "freq"]
    assert table.num_rows == 1
    assert table.column("ts_code").to_pylist() == ["000001.SZ"]
    assert table.column("freq").to_pylist() == ["daily"]


def test_read_canonical_raises_for_missing_table(stock_basic_duckdb: Path) -> None:
    with pytest.raises(CanonicalTableNotFound) as exc_info:
        read_canonical("missing_table")

    assert exc_info.value.table == "missing_table"


def test_read_iceberg_snapshot_uses_duckdb_time_travel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = (
        tmp_path
        / "warehouse"
        / "formal"
        / "recommendation_snapshot"
        / "metadata"
        / "00002.metadata.json"
    )
    expected_payload = pa.table({"version": ["published"]})
    executed_sql: list[str] = []

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected_payload

    class FakeConnection:
        def execute(self, sql: str) -> FakeResult:
            executed_sql.append(sql)
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setattr(
        reader,
        "_latest_metadata_location_for_identifier",
        lambda table_identifier: metadata_path,
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    payload = read_iceberg_snapshot("formal.recommendation_snapshot", 123)

    assert payload == expected_payload
    assert len(executed_sql) == 1
    assert f"iceberg_scan('{metadata_path}', snapshot_from_id = 123)" in executed_sql[0]


def test_read_iceberg_snapshot_reads_pinned_snapshot_not_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_duckdb_iceberg_extension()

    schema = pa.schema([pa.field("version", pa.string())])
    warehouse_path = tmp_path / "warehouse"
    catalog = InMemoryCatalog("test", warehouse=f"file://{warehouse_path}")
    catalog.create_namespace_if_not_exists(("formal",))
    catalog.create_table("formal.recommendation_snapshot", schema=schema)
    table = catalog.load_table("formal.recommendation_snapshot")

    table.overwrite(pa.table({"version": ["published"]}, schema=schema))
    published_snapshot = table.refresh().current_snapshot()
    if published_snapshot is None:
        raise AssertionError("published formal snapshot was not created")

    table.overwrite(pa.table({"version": ["unpublished-head"]}, schema=schema))
    head_snapshot = table.refresh().current_snapshot()
    if head_snapshot is None:
        raise AssertionError("formal head snapshot was not created")

    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    reader._duckdb_connection.cache_clear()
    try:
        payload = read_iceberg_snapshot(
            "formal.recommendation_snapshot",
            int(published_snapshot.snapshot_id),
        )
    finally:
        reader._duckdb_connection.cache_clear()

    assert int(published_snapshot.snapshot_id) != int(head_snapshot.snapshot_id)
    assert payload.column("version").to_pylist() == ["published"]


@pytest.mark.parametrize(
    "filters",
    [
        [("market", ">", "主板")],
        [("market", "like", "主%")],
        [("market", "in", "主板")],
    ],
)
def test_read_canonical_rejects_unsupported_filters(
    stock_basic_duckdb: Path,
    filters: list[tuple[str, str, object]],
) -> None:
    with pytest.raises(UnsupportedFilter):
        read_canonical("stock_basic", filters=filters)


def test_with_duckdb_connection_uses_cached_connection(stock_basic_duckdb: Path) -> None:
    with with_duckdb_connection() as first:
        with with_duckdb_connection() as second:
            assert second is first


def test_read_canonical_uses_legacy_manifest_when_v2_flag_is_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "warehouse"
    legacy_metadata = (
        warehouse_path
        / "canonical"
        / "fact_price_bar"
        / "metadata"
        / "00001.metadata.json"
    )
    v2_metadata = (
        warehouse_path
        / "canonical_v2"
        / "fact_price_bar"
        / "metadata"
        / "00002.metadata.json"
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical",
        payload_key="tables",
        table_name="fact_price_bar",
        metadata_location=legacy_metadata,
        snapshot_id=101,
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical_v2",
        payload_key="canonical_v2_tables",
        table_name="fact_price_bar",
        metadata_location=v2_metadata,
        snapshot_id=202,
    )
    executed: list[tuple[str, list[object]]] = []
    expected = pa.table({"ts_code": ["000001.SZ"]})

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected

    class FakeConnection:
        def execute(self, sql: str, parameters: list[object]) -> FakeResult:
            executed.append((sql, parameters))
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    payload = read_canonical("fact_price_bar", columns=["ts_code"])

    assert payload == expected
    assert len(executed) == 1
    sql, parameters = executed[0]
    assert str(legacy_metadata) in sql
    assert "snapshot_from_id = 101" in sql
    assert str(v2_metadata) not in sql
    assert parameters == []


def test_read_canonical_dataset_uses_canonical_v2_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "warehouse"
    legacy_metadata = (
        warehouse_path
        / "canonical"
        / "fact_price_bar"
        / "metadata"
        / "00001.metadata.json"
    )
    v2_metadata = (
        warehouse_path
        / "canonical_v2"
        / "fact_price_bar"
        / "metadata"
        / "00002.metadata.json"
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical",
        payload_key="tables",
        table_name="fact_price_bar",
        metadata_location=legacy_metadata,
        snapshot_id=101,
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical_v2",
        payload_key="canonical_v2_tables",
        table_name="fact_price_bar",
        metadata_location=v2_metadata,
        snapshot_id=202,
    )
    executed: list[tuple[str, list[object]]] = []
    expected = pa.table({"security_id": ["SEC_A"]})

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected

    class FakeConnection:
        def execute(self, sql: str, parameters: list[object]) -> FakeResult:
            executed.append((sql, parameters))
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    payload = reader.read_canonical_dataset(
        "price_bar",
        columns=["security_id"],
        filters=[("freq", "=", "daily")],
    )

    assert payload == expected
    assert len(executed) == 1
    sql, parameters = executed[0]
    assert str(v2_metadata) in sql
    assert "snapshot_from_id = 202" in sql
    assert str(legacy_metadata) not in sql
    assert parameters == ["daily"]


def test_read_canonical_dataset_routes_event_timeline_to_v2_under_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M1.5-2 lock: event_timeline reads from canonical_v2.fact_event under flag.

    Mirrors the structure of `test_read_canonical_dataset_uses_canonical_v2_manifest`
    but exercises the new event_timeline → canonical_v2.fact_event mapping
    landed by M1-G2. If a future regression silently drops event_timeline
    from the v2 mapping (or routes it back to legacy `canonical.fact_event`
    under the v2 flag), this test fails.
    """

    warehouse_path = tmp_path / "warehouse"
    legacy_metadata = (
        warehouse_path
        / "canonical"
        / "fact_event"
        / "metadata"
        / "00001.metadata.json"
    )
    v2_metadata = (
        warehouse_path
        / "canonical_v2"
        / "fact_event"
        / "metadata"
        / "00002.metadata.json"
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical",
        payload_key="tables",
        table_name="fact_event",
        metadata_location=legacy_metadata,
        snapshot_id=101,
    )
    _write_mart_manifest(
        warehouse_path,
        namespace="canonical_v2",
        payload_key="canonical_v2_tables",
        table_name="fact_event",
        metadata_location=v2_metadata,
        snapshot_id=202,
    )
    executed: list[tuple[str, list[object]]] = []
    expected = pa.table({"entity_id": ["000001.SZ"]})

    class FakeResult:
        def to_arrow_table(self) -> pa.Table:
            return expected

    class FakeConnection:
        def execute(self, sql: str, parameters: list[object]) -> FakeResult:
            executed.append((sql, parameters))
            return FakeResult()

    @contextmanager
    def fake_duckdb_connection() -> Iterator[FakeConnection]:
        yield FakeConnection()

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader,
        "get_settings",
        lambda: FakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=warehouse_path,
        ),
    )
    monkeypatch.setattr(reader, "with_duckdb_connection", fake_duckdb_connection)

    payload = reader.read_canonical_dataset(
        "event_timeline",
        columns=["entity_id"],
    )

    assert payload == expected
    assert len(executed) == 1
    sql, _parameters = executed[0]
    assert str(v2_metadata) in sql
    assert "snapshot_from_id = 202" in sql
    assert str(legacy_metadata) not in sql, (
        "event_timeline must read canonical_v2.fact_event under v2 flag, "
        "NOT legacy canonical.fact_event"
    )


def test_reader_tracks_all_writer_published_marts() -> None:
    expected_v2_mart_tables = {
        spec.identifier.rsplit(".", maxsplit=1)[-1]
        for spec in CANONICAL_V2_MART_LOAD_SPECS
    }
    v2_namespace_tables = reader._CANONICAL_MART_TABLES_BY_NAMESPACE[
        reader.CANONICAL_V2_NAMESPACE
    ]

    assert expected_v2_mart_tables <= v2_namespace_tables
    assert {
        "fact_market_daily_feature",
        "fact_index_price_bar",
        "fact_forecast_event",
    } <= v2_namespace_tables


def test_read_canonical_dataset_uses_explicit_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy-mode mapping resolution. Asserts that `read_canonical_dataset`
    funnels through `read_canonical(<bare>)` for legacy-namespace mappings.
    Under `DP_CANONICAL_USE_V2=1` the resolution path differs (it goes
    through `_read_table_expression` directly with the v2 identifier), so
    this test pins the legacy code path explicitly."""

    monkeypatch.delenv(USE_CANONICAL_V2_ENV_VAR, raising=False)
    calls: list[str] = []
    expected = pa.table({"ts_code": ["000001.SZ"]})

    def fake_read_canonical(
        table: str,
        columns: list[str] | None = None,
        filters: list[tuple[str, str, object]] | None = None,
    ) -> pa.Table:
        calls.append(table)
        assert columns == ["ts_code"]
        assert filters is None
        return expected

    monkeypatch.setattr(reader, "read_canonical", fake_read_canonical)

    payload = reader.read_canonical_dataset("market_daily_feature", columns=["ts_code"])

    assert payload == expected
    assert calls == ["fact_market_daily_feature"]


def stock_basic_rows() -> list[StockBasicRow]:
    loaded_at = datetime(2026, 4, 15, 10, 30, 0)
    return [
        (
            "000001.SZ",
            "000001",
            "平安银行",
            "深圳",
            "银行",
            "主板",
            date(1991, 4, 3),
            True,
            "run-1",
            loaded_at,
        ),
        (
            "000002.SZ",
            "000002",
            "万科A",
            "深圳",
            "房地产",
            "主板",
            date(1991, 1, 29),
            False,
            "run-1",
            loaded_at,
        ),
        (
            "300001.SZ",
            "300001",
            "特锐德",
            "青岛",
            "电气设备",
            "创业板",
            date(2009, 10, 30),
            True,
            "run-1",
            loaded_at,
        ),
    ]


def _write_mart_manifest(
    warehouse_path: Path,
    *,
    namespace: str,
    payload_key: str,
    table_name: str,
    metadata_location: Path,
    snapshot_id: int,
) -> None:
    manifest_path = warehouse_path / namespace / reader.CANONICAL_MART_SNAPSHOT_SET_FILE
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                payload_key: {
                    table_name: {
                        "identifier": f"{namespace}.{table_name}",
                        "metadata_location": str(metadata_location),
                        "snapshot_id": snapshot_id,
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def price_bar_rows() -> list[tuple[str, date, str, str, str, str, datetime, datetime]]:
    loaded_at = datetime(2026, 4, 15, 10, 30, 0)
    return [
        (
            "000001.SZ",
            date(2026, 4, 15),
            "daily",
            "10.000000000000000000",
            "10.500000000000000000",
            "run-1",
            loaded_at,
            loaded_at,
        ),
        (
            "000001.SZ",
            date(2026, 4, 15),
            "weekly",
            "10.000000000000000000",
            "10.500000000000000000",
            "run-1",
            loaded_at,
            loaded_at,
        ),
    ]


def _require_duckdb_iceberg_extension() -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("LOAD iceberg")
    except duckdb.Error as exc:
        pytest.skip(
            "DuckDB iceberg extension is not available in this sandbox without "
            f"network install: {exc}"
        )
    finally:
        connection.close()
