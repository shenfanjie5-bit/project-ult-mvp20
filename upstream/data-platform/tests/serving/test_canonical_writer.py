from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Sequence

import duckdb
import pytest
from pyiceberg.catalog.memory import InMemoryCatalog

from data_platform.ddl.iceberg_tables import (
    CANONICAL_LINEAGE_TABLE_SPECS,
    CANONICAL_V2_TABLE_SPECS,
    TableSpec,
)
from data_platform.serving import canonical_writer, reader as reader_module
from data_platform.serving.canonical_datasets import (
    CANONICAL_DATASET_TABLE_MAPPINGS_V2,
    USE_CANONICAL_V2_ENV_VAR,
)
from data_platform.serving.canonical_writer import (
    CANONICAL_MART_SNAPSHOT_SET_FILE,
    CanonicalLoadSpec,
    load_canonical_v2_marts,
)
from data_platform.serving.reader import (
    CanonicalTableNotFound,
    canonical_snapshot_id_for_dataset,
    get_canonical_stock_basic,
    read_canonical_dataset,
)


StockBasicRow = tuple[str, str, str, str, str, str, date, bool, str]


@dataclass(frozen=True, slots=True)
class FakeSettings:
    duckdb_path: Path


def test_canonical_load_spec_rejects_queue_fields() -> None:
    with pytest.raises(ValueError, match="forbidden payload fields"):
        CanonicalLoadSpec(
            identifier="canonical_v2.bad",
            duckdb_relation="bad_relation",
            required_columns=("submitted_at",),
        )


def test_canonical_load_spec_rejects_raw_lineage_fields_on_business_namespace() -> None:
    """M1.12 step 4 — canonical_v2.* spec must reject raw-zone lineage payload."""

    with pytest.raises(ValueError, match="forbidden payload fields"):
        CanonicalLoadSpec(
            identifier="canonical_v2.bad",
            duckdb_relation="bad_relation",
            required_columns=("source_run_id", "ts_code"),
        )


def test_canonical_lineage_load_spec_permits_raw_lineage_fields() -> None:
    """M1.12 step 4 — canonical_lineage.* spec bypass permits source_run_id + raw_loaded_at."""

    spec = CanonicalLoadSpec(
        identifier="canonical_lineage.bad",
        duckdb_relation="bad_relation",
        required_columns=("ts_code", "source_run_id", "raw_loaded_at"),
    )
    assert spec.identifier == "canonical_lineage.bad"


def test_canonical_lineage_load_spec_still_rejects_queue_fields() -> None:
    """M1.12 step 4 — canonical_lineage.* spec still rejects ingest-queue boundary fields."""

    with pytest.raises(ValueError, match="forbidden payload fields"):
        CanonicalLoadSpec(
            identifier="canonical_lineage.bad",
            duckdb_relation="bad_relation",
            required_columns=("submitted_at", "raw_loaded_at"),
        )


def test_load_canonical_v2_marts_writes_manifest_with_paired_snapshot_ids(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)

    results = load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]
    result_by_table = {result.table: result for result in results}
    manifest_path = (
        tmp_path / "warehouse" / "canonical_v2" / CANONICAL_MART_SNAPSHOT_SET_FILE
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    v2_result = result_by_table["canonical_v2.dim_security"]
    lineage_result = result_by_table["canonical_lineage.lineage_dim_security"]
    assert manifest["version"] == 2
    assert manifest["canonical_v2_tables"]["dim_security"]["snapshot_id"] == (
        v2_result.snapshot_id
    )
    assert manifest["canonical_v2_tables"]["dim_security"]["identifier"] == (
        "canonical_v2.dim_security"
    )
    assert manifest["canonical_lineage_tables"]["lineage_dim_security"]["snapshot_id"] == (
        lineage_result.snapshot_id
    )
    assert manifest["canonical_lineage_tables"]["lineage_dim_security"]["identifier"] == (
        "canonical_lineage.lineage_dim_security"
    )
    v2_loaded_at = set(
        catalog.load_table("canonical_v2.dim_security")
        .scan()
        .to_arrow()
        .column("canonical_loaded_at")
        .to_pylist()
    )
    lineage_loaded_at = set(
        catalog.load_table("canonical_lineage.lineage_dim_security")
        .scan()
        .to_arrow()
        .column("canonical_loaded_at")
        .to_pylist()
    )
    assert len(v2_loaded_at) == 1
    assert lineage_loaded_at == v2_loaded_at


def test_load_canonical_v2_marts_pairs_forecast_event_by_update_flag(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute("DELETE FROM mart_fact_forecast_event_v2")
        connection.execute("DELETE FROM mart_lineage_fact_forecast_event")
        connection.execute(
            """
            INSERT INTO mart_fact_forecast_event_v2 VALUES
                ('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31',
                 'forecast', -10, 10, 100, 200, 150, DATE '2026-04-15',
                 'placeholder', 'placeholder', '0'),
                ('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31',
                 'forecast', -20, 20, 90, 210, 150, DATE '2026-04-15',
                 'placeholder', 'placeholder', '1')
            """
        )
        connection.execute(
            """
            INSERT INTO mart_lineage_fact_forecast_event VALUES
                ('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31',
                 '0', 'forecast', 'tushare', 'forecast', 'run-forecast-0',
                 TIMESTAMP '2026-04-15 10:00:00'),
                ('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31',
                 '1', 'forecast', 'tushare', 'forecast', 'run-forecast-1',
                 TIMESTAMP '2026-04-15 10:00:00')
            """
        )
    finally:
        connection.close()

    results = load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]
    result_by_table = {result.table: result for result in results}

    assert canonical_writer.CANONICAL_V2_PAIRING_KEY_COLUMNS[
        "canonical_v2.fact_forecast_event"
    ] == (
        "security_id",
        "announcement_date",
        "report_period",
        "update_flag",
        "forecast_type",
    )
    assert result_by_table["canonical_v2.fact_forecast_event"].row_count == 2
    assert (
        result_by_table["canonical_lineage.lineage_fact_forecast_event"].row_count == 2
    )


def test_load_canonical_v2_marts_pairs_holding_position_by_announced_date(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute("DELETE FROM mart_fact_holding_position_v2")
        connection.execute("DELETE FROM mart_lineage_fact_holding_position")
        connection.execute(
            """
            INSERT INTO mart_fact_holding_position_v2 VALUES
                ('fund_portfolio', 'FUND_PLACEHOLDER', 'Placeholder Fund', 'fund',
                 'SEC_PLACEHOLDER', DATE '2026-03-31', DATE '2026-04-10',
                 100, 1, 1, NULL, 1000, NULL),
                ('fund_portfolio', 'FUND_PLACEHOLDER', 'Placeholder Fund', 'fund',
                 'SEC_PLACEHOLDER', DATE '2026-03-31', DATE '2026-04-15',
                 110, 2, 2, NULL, 1100, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO mart_lineage_fact_holding_position VALUES
                ('fund_portfolio', 'FUND_PLACEHOLDER', 'SEC_PLACEHOLDER',
                 DATE '2026-03-31', DATE '2026-04-10', 'tushare',
                 'fund_portfolio', 'run-holding-0',
                 TIMESTAMP '2026-04-15 10:00:00'),
                ('fund_portfolio', 'FUND_PLACEHOLDER', 'SEC_PLACEHOLDER',
                 DATE '2026-03-31', DATE '2026-04-15', 'tushare',
                 'fund_portfolio', 'run-holding-1',
                 TIMESTAMP '2026-04-15 10:00:00')
            """
        )
    finally:
        connection.close()

    results = load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]
    result_by_table = {result.table: result for result in results}

    assert canonical_writer.CANONICAL_V2_PAIRING_KEY_COLUMNS[
        "canonical_v2.fact_holding_position"
    ] == (
        "holding_source",
        "holder_id",
        "security_id",
        "report_date",
        "announced_date",
    )
    assert result_by_table["canonical_v2.fact_holding_position"].row_count == 2
    assert (
        result_by_table["canonical_lineage.lineage_fact_holding_position"].row_count
        == 2
    )


def test_load_canonical_v2_marts_rejects_missing_lineage_key_before_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(
        duckdb_path,
        v2_security_ids=("SEC_A", "SEC_B"),
        lineage_security_ids=("SEC_A", "SEC_C"),
    )

    def fail_overwrite(*_args: object, **_kwargs: object) -> object:
        pytest.fail("unsafe canonical_v2 publication must fail before overwrite")

    monkeypatch.setattr(canonical_writer, "_overwrite_prepared_load", fail_overwrite)

    with pytest.raises(ValueError, match="missing lineage key"):
        load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]

    assert catalog.load_table("canonical_v2.dim_security").current_snapshot() is None
    assert (
        catalog.load_table("canonical_lineage.lineage_dim_security").current_snapshot()
        is None
    )


def test_load_canonical_v2_marts_rejects_duplicate_lineage_key(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(
        duckdb_path,
        v2_security_ids=("SEC_A", "SEC_B"),
        lineage_security_ids=("SEC_A", "SEC_A"),
    )

    with pytest.raises(ValueError, match="duplicate canonical key"):
        load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]

    assert catalog.load_table("canonical_v2.dim_security").current_snapshot() is None
    assert (
        catalog.load_table("canonical_lineage.lineage_dim_security").current_snapshot()
        is None
    )


def test_load_canonical_v2_marts_rejects_row_count_mismatch(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(
        duckdb_path,
        v2_security_ids=("SEC_A", "SEC_B"),
        lineage_security_ids=("SEC_A",),
    )

    with pytest.raises(ValueError, match="row_count mismatch"):
        load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]

    assert catalog.load_table("canonical_v2.dim_security").current_snapshot() is None
    assert (
        catalog.load_table("canonical_lineage.lineage_dim_security").current_snapshot()
        is None
    )


def test_load_canonical_v2_marts_rolls_back_snapshots_when_manifest_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)
    first_results = load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]
    first_snapshot_by_table = {result.table: result.snapshot_id for result in first_results}
    write_canonical_v2_mart_relations(
        duckdb_path,
        v2_security_ids=("SEC_C", "SEC_D"),
        lineage_security_ids=("SEC_C", "SEC_D"),
    )

    def fail_manifest_write(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("manifest write failed")

    monkeypatch.setattr(
        canonical_writer,
        "_write_canonical_v2_snapshot_set_manifest",
        fail_manifest_write,
    )

    with pytest.raises(RuntimeError, match="manifest write failed"):
        load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]

    v2_snapshot = catalog.load_table("canonical_v2.dim_security").current_snapshot()
    lineage_snapshot = catalog.load_table(
        "canonical_lineage.lineage_dim_security"
    ).current_snapshot()
    assert v2_snapshot is not None
    assert lineage_snapshot is not None
    assert v2_snapshot.snapshot_id == first_snapshot_by_table["canonical_v2.dim_security"]
    assert lineage_snapshot.snapshot_id == first_snapshot_by_table[
        "canonical_lineage.lineage_dim_security"
    ]


@dataclass(frozen=True, slots=True)
class _ReaderFakeSettings:
    duckdb_path: Path
    iceberg_warehouse_path: Path


def test_load_canonical_v2_marts_closed_loop_under_v2_flag_reads_pinned_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M1.10 closed-loop proof: write→read across all v2 + lineage marts.

    Drives `load_canonical_v2_marts()` once over a fixture catalog populated
    with all paired marts, then under `DP_CANONICAL_USE_V2=1` calls
    `read_canonical_dataset()` for each of the 10 dataset_ids in
    `CANONICAL_DATASET_TABLE_MAPPINGS_V2`. Every read must pin to the
    writer-published snapshot via the combined `_mart_snapshot_set.json`
    manifest. After the positive sweep, the manifest is deleted and the
    same reader call must fail closed — confirming no unpublished-head
    fallback for v2 mart tables.

    This is the controlled fixture proof that closes the audit gap for
    legacy retirement precondition 3 in `assembly/reports/stabilization/
    m1-10-controlled-v2-proof-preflight-20260429.md`. It is NOT a
    substitute for the Lite-compose controlled run, which remains gated
    behind explicit user approval.
    """

    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)

    results = load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]
    result_by_table = {result.table: result for result in results}

    expected_v2_identifiers = {
        spec.identifier for spec in canonical_writer.CANONICAL_V2_MART_LOAD_SPECS
    }
    expected_lineage_identifiers = {
        spec.identifier for spec in canonical_writer.CANONICAL_LINEAGE_MART_LOAD_SPECS
    }
    assert len(expected_v2_identifiers) == 11
    assert len(expected_lineage_identifiers) == 11
    assert expected_v2_identifiers <= result_by_table.keys()
    assert expected_lineage_identifiers <= result_by_table.keys()
    for identifier in (*expected_v2_identifiers, *expected_lineage_identifiers):
        assert catalog.load_table(identifier).current_snapshot() is not None, identifier

    manifest_path = (
        tmp_path / "warehouse" / "canonical_v2" / CANONICAL_MART_SNAPSHOT_SET_FILE
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == 2
    assert set(manifest["canonical_v2_tables"].keys()) == {
        identifier.rsplit(".", maxsplit=1)[-1]
        for identifier in expected_v2_identifiers
    }
    assert set(manifest["canonical_lineage_tables"].keys()) == {
        identifier.rsplit(".", maxsplit=1)[-1]
        for identifier in expected_lineage_identifiers
    }

    v2_canonical_names = {
        identifier.rsplit(".", maxsplit=1)[-1]
        for identifier in expected_v2_identifiers
    }
    lineage_canonical_names = {
        identifier.rsplit(".", maxsplit=1)[-1].removeprefix("lineage_")
        for identifier in expected_lineage_identifiers
    }
    assert v2_canonical_names == lineage_canonical_names

    for v2_spec, lineage_spec in zip(
        canonical_writer.CANONICAL_V2_MART_LOAD_SPECS,
        canonical_writer.CANONICAL_LINEAGE_MART_LOAD_SPECS,
        strict=True,
    ):
        v2_table = catalog.load_table(v2_spec.identifier).scan().to_arrow()
        lineage_table = catalog.load_table(lineage_spec.identifier).scan().to_arrow()
        v2_loaded_at = set(v2_table.column("canonical_loaded_at").to_pylist())
        lineage_loaded_at = set(lineage_table.column("canonical_loaded_at").to_pylist())
        assert v2_loaded_at == lineage_loaded_at, v2_spec.identifier

        pairing_keys = canonical_writer.CANONICAL_V2_PAIRING_KEY_COLUMNS.get(
            v2_spec.identifier
        )
        if pairing_keys is None:
            continue
        v2_pks = {
            tuple(v2_table.column(key).to_pylist()[row] for key in pairing_keys)
            for row in range(v2_table.num_rows)
        }
        lineage_pks = {
            tuple(lineage_table.column(key).to_pylist()[row] for key in pairing_keys)
            for row in range(lineage_table.num_rows)
        }
        assert v2_pks == lineage_pks, v2_spec.identifier

    monkeypatch.setenv(USE_CANONICAL_V2_ENV_VAR, "1")
    monkeypatch.setattr(
        reader_module,
        "get_settings",
        lambda: _ReaderFakeSettings(
            duckdb_path=tmp_path / "reader.duckdb",
            iceberg_warehouse_path=tmp_path / "warehouse",
        ),
    )
    reader_module._duckdb_connection.cache_clear()
    try:
        for mapping in CANONICAL_DATASET_TABLE_MAPPINGS_V2:
            v2_result = result_by_table[mapping.table_identifier]
            assert (
                canonical_snapshot_id_for_dataset(mapping.dataset_id)
                == v2_result.snapshot_id
            ), mapping.dataset_id
            payload = read_canonical_dataset(mapping.dataset_id)
            assert payload.num_rows >= 1, mapping.dataset_id

        stock_basic_table = get_canonical_stock_basic(active_only=True)
        assert stock_basic_table.num_rows >= 1

        manifest_path.unlink()
        reader_module._duckdb_connection.cache_clear()
        with pytest.raises(CanonicalTableNotFound):
            read_canonical_dataset("price_bar")
    finally:
        reader_module._duckdb_connection.cache_clear()


def test_overwrite_failure_does_not_refresh_or_report_snapshot(
    tmp_path: Path,
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)

    class FailingOverwrite(Exception):
        pass

    def failing_overwrite(*_args: object, **_kwargs: object) -> object:
        raise FailingOverwrite("overwrite failed")

    target_v2 = canonical_writer.CANONICAL_V2_MART_LOAD_SPECS[0].identifier
    target_lineage = canonical_writer.CANONICAL_LINEAGE_MART_LOAD_SPECS[0].identifier
    real_overwrite = canonical_writer._overwrite_prepared_load
    original_overwrite_calls: list[str] = []

    def tracking_overwrite(prepared: object, *, started_at: float) -> object:
        identifier = getattr(prepared, "spec").identifier
        original_overwrite_calls.append(identifier)
        if identifier == target_v2:
            raise FailingOverwrite("overwrite failed")
        return real_overwrite(prepared, started_at=started_at)

    import unittest.mock as mock
    with mock.patch.object(
        canonical_writer,
        "_overwrite_prepared_load",
        tracking_overwrite,
    ):
        with pytest.raises(FailingOverwrite, match="overwrite failed"):
            load_canonical_v2_marts(catalog, duckdb_path)  # type: ignore[arg-type]

    assert original_overwrite_calls == [target_v2]
    assert catalog.load_table(target_v2).current_snapshot() is None
    assert catalog.load_table(target_lineage).current_snapshot() is None


def test_cli_writes_v2_marts_result_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog = create_catalog(
        tmp_path,
        [*CANONICAL_V2_TABLE_SPECS, *CANONICAL_LINEAGE_TABLE_SPECS],
    )
    duckdb_path = tmp_path / "marts.duckdb"
    write_canonical_v2_mart_relations(duckdb_path)
    monkeypatch.setattr(canonical_writer, "load_catalog", lambda: catalog)
    monkeypatch.setattr(canonical_writer, "get_settings", lambda: FakeSettings(duckdb_path))

    exit_code = canonical_writer.main(["--table", "v2_marts", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    expected_count = len(canonical_writer.CANONICAL_V2_MART_LOAD_SPECS) + len(
        canonical_writer.CANONICAL_LINEAGE_MART_LOAD_SPECS
    )
    assert len(payload) == expected_count
    payload_tables = {item["table"] for item in payload}
    expected_tables = {
        spec.identifier
        for spec in (
            *canonical_writer.CANONICAL_V2_MART_LOAD_SPECS,
            *canonical_writer.CANONICAL_LINEAGE_MART_LOAD_SPECS,
        )
    }
    assert payload_tables == expected_tables


def test_cli_reports_failure_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = canonical_writer.main(["--table", "canonical_entity"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["error"] == "ValueError"
    assert "unsupported canonical table" in payload["detail"]


@pytest.mark.parametrize(
    "argv, expected_detail",
    [
        ([], "the following arguments are required: --table"),
        (["--table", "v2_marts", "--unknown"], "unrecognized arguments: --unknown"),
    ],
)
def test_cli_reports_argument_failures_as_json(
    argv: list[str],
    expected_detail: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = canonical_writer.main(argv)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["error"] == "ValueError"
    assert expected_detail in payload["detail"]


def create_catalog(tmp_path: Path, specs: Sequence[TableSpec]) -> InMemoryCatalog:
    warehouse_path = tmp_path / "warehouse"
    catalog = InMemoryCatalog("test", warehouse=f"file://{warehouse_path}")
    for spec in specs:
        catalog.create_namespace_if_not_exists((spec.namespace,))
        catalog.create_table(f"{spec.namespace}.{spec.name}", schema=spec.schema)
    return catalog


def write_mart_relations(duckdb_path: Path) -> None:
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_dim_security AS
            SELECT
                '000001.SZ'::VARCHAR AS ts_code,
                '000001'::VARCHAR AS symbol,
                'Ping An Bank'::VARCHAR AS name,
                'Main'::VARCHAR AS market,
                'Bank'::VARCHAR AS industry,
                DATE '1991-04-03' AS list_date,
                TRUE AS is_active,
                'Shenzhen'::VARCHAR AS area,
                'Ping An Bank Co Ltd'::VARCHAR AS fullname,
                'SZSE'::VARCHAR AS exchange,
                'CNY'::VARCHAR AS curr_type,
                'L'::VARCHAR AS list_status,
                NULL::DATE AS delist_date,
                DATE '1987-12-22' AS setup_date,
                'Guangdong'::VARCHAR AS province,
                'Shenzhen'::VARCHAR AS city,
                CAST(1000.000000000000000000 AS DECIMAL(38, 18)) AS reg_capital,
                CAST(100.000000000000000000 AS DECIMAL(38, 18)) AS employees,
                'Banking'::VARCHAR AS main_business,
                'Ping An Bank'::VARCHAR AS latest_namechange_name,
                DATE '2020-01-01' AS latest_namechange_start_date,
                NULL::DATE AS latest_namechange_end_date,
                DATE '2020-01-01' AS latest_namechange_ann_date,
                'rename'::VARCHAR AS latest_namechange_reason,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_dim_index AS
            SELECT
                '000300.SH'::VARCHAR AS index_code,
                'CSI 300'::VARCHAR AS index_name,
                'SSE'::VARCHAR AS index_market,
                'broad'::VARCHAR AS index_category,
                DATE '2026-04-15' AS first_effective_date,
                DATE '2026-04-15' AS latest_effective_date,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_price_bar AS
            SELECT
                '000001.SZ'::VARCHAR AS ts_code,
                DATE '2026-04-15' AS trade_date,
                'daily'::VARCHAR AS freq,
                CAST(10.000000000000000000 AS DECIMAL(38, 18)) AS open,
                CAST(11.000000000000000000 AS DECIMAL(38, 18)) AS high,
                CAST(9.000000000000000000 AS DECIMAL(38, 18)) AS low,
                CAST(10.500000000000000000 AS DECIMAL(38, 18)) AS close,
                CAST(10.100000000000000000 AS DECIMAL(38, 18)) AS pre_close,
                CAST(0.400000000000000000 AS DECIMAL(38, 18)) AS change,
                CAST(3.960000000000000000 AS DECIMAL(38, 18)) AS pct_chg,
                CAST(1000.000000000000000000 AS DECIMAL(38, 18)) AS vol,
                CAST(10500.000000000000000000 AS DECIMAL(38, 18)) AS amount,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS adj_factor,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_financial_indicator AS
            SELECT
                '000001.SZ'::VARCHAR AS ts_code,
                DATE '2026-03-31' AS end_date,
                DATE '2026-04-15' AS ann_date,
                DATE '2026-04-16' AS f_ann_date,
                '1'::VARCHAR AS report_type,
                '1'::VARCHAR AS comp_type,
                '0'::VARCHAR AS update_flag,
                TRUE AS is_latest,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS basic_eps,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS diluted_eps,
                CAST(100.000000000000000000 AS DECIMAL(38, 18)) AS total_revenue,
                CAST(90.000000000000000000 AS DECIMAL(38, 18)) AS revenue,
                CAST(80.000000000000000000 AS DECIMAL(38, 18)) AS operate_profit,
                CAST(70.000000000000000000 AS DECIMAL(38, 18)) AS total_profit,
                CAST(60.000000000000000000 AS DECIMAL(38, 18)) AS n_income,
                CAST(50.000000000000000000 AS DECIMAL(38, 18)) AS n_income_attr_p,
                CAST(40.000000000000000000 AS DECIMAL(38, 18)) AS money_cap,
                CAST(300.000000000000000000 AS DECIMAL(38, 18)) AS total_cur_assets,
                CAST(500.000000000000000000 AS DECIMAL(38, 18)) AS total_assets,
                CAST(200.000000000000000000 AS DECIMAL(38, 18)) AS total_cur_liab,
                CAST(250.000000000000000000 AS DECIMAL(38, 18)) AS total_liab,
                CAST(240.000000000000000000 AS DECIMAL(38, 18))
                    AS total_hldr_eqy_exc_min_int,
                CAST(500.000000000000000000 AS DECIMAL(38, 18)) AS total_liab_hldr_eqy,
                CAST(60.000000000000000000 AS DECIMAL(38, 18)) AS net_profit,
                CAST(55.000000000000000000 AS DECIMAL(38, 18)) AS n_cashflow_act,
                CAST(45.000000000000000000 AS DECIMAL(38, 18)) AS n_cashflow_inv_act,
                CAST(35.000000000000000000 AS DECIMAL(38, 18)) AS n_cash_flows_fnc_act,
                CAST(25.000000000000000000 AS DECIMAL(38, 18)) AS n_incr_cash_cash_equ,
                CAST(15.000000000000000000 AS DECIMAL(38, 18)) AS free_cashflow,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS eps,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS dt_eps,
                CAST(30.000000000000000000 AS DECIMAL(38, 18)) AS grossprofit_margin,
                CAST(20.000000000000000000 AS DECIMAL(38, 18)) AS netprofit_margin,
                CAST(10.000000000000000000 AS DECIMAL(38, 18)) AS roe,
                CAST(5.000000000000000000 AS DECIMAL(38, 18)) AS roa,
                CAST(50.000000000000000000 AS DECIMAL(38, 18)) AS debt_to_assets,
                CAST(12.000000000000000000 AS DECIMAL(38, 18)) AS or_yoy,
                CAST(8.000000000000000000 AS DECIMAL(38, 18)) AS netprofit_yoy,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_event AS
            SELECT
                'announcement'::VARCHAR AS event_type,
                '000001.SZ'::VARCHAR AS ts_code,
                DATE '2026-04-15' AS event_date,
                'Announcement'::VARCHAR AS title,
                'Quarterly report'::VARCHAR AS summary,
                NULL::VARCHAR AS event_subtype,
                NULL::DATE AS related_date,
                'https://example.test/report'::VARCHAR AS reference_url,
                '10:30:00'::VARCHAR AS rec_time,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_market_daily_feature AS
            SELECT
                '000001.SZ'::VARCHAR AS ts_code,
                DATE '2026-04-15' AS trade_date,
                CAST(10.500000000000000000 AS DECIMAL(38, 18)) AS close,
                CAST(1.000000000000000000 AS DECIMAL(38, 18)) AS turnover_rate,
                CAST(1.100000000000000000 AS DECIMAL(38, 18)) AS turnover_rate_f,
                CAST(1.200000000000000000 AS DECIMAL(38, 18)) AS volume_ratio,
                CAST(8.000000000000000000 AS DECIMAL(38, 18)) AS pe,
                CAST(9.000000000000000000 AS DECIMAL(38, 18)) AS pe_ttm,
                CAST(1.300000000000000000 AS DECIMAL(38, 18)) AS pb,
                CAST(2.000000000000000000 AS DECIMAL(38, 18)) AS ps,
                CAST(2.100000000000000000 AS DECIMAL(38, 18)) AS ps_ttm,
                CAST(3.000000000000000000 AS DECIMAL(38, 18)) AS dv_ratio,
                CAST(3.100000000000000000 AS DECIMAL(38, 18)) AS dv_ttm,
                CAST(1000.000000000000000000 AS DECIMAL(38, 18)) AS total_share,
                CAST(800.000000000000000000 AS DECIMAL(38, 18)) AS float_share,
                CAST(600.000000000000000000 AS DECIMAL(38, 18)) AS free_share,
                CAST(100000.000000000000000000 AS DECIMAL(38, 18)) AS total_mv,
                CAST(80000.000000000000000000 AS DECIMAL(38, 18)) AS circ_mv,
                CAST(11.550000000000000000 AS DECIMAL(38, 18)) AS up_limit,
                CAST(9.450000000000000000 AS DECIMAL(38, 18)) AS down_limit,
                CAST(10.000000000000000000 AS DECIMAL(38, 18)) AS buy_sm_vol,
                CAST(100.000000000000000000 AS DECIMAL(38, 18)) AS buy_sm_amount,
                CAST(9.000000000000000000 AS DECIMAL(38, 18)) AS sell_sm_vol,
                CAST(90.000000000000000000 AS DECIMAL(38, 18)) AS sell_sm_amount,
                CAST(20.000000000000000000 AS DECIMAL(38, 18)) AS buy_md_vol,
                CAST(200.000000000000000000 AS DECIMAL(38, 18)) AS buy_md_amount,
                CAST(18.000000000000000000 AS DECIMAL(38, 18)) AS sell_md_vol,
                CAST(180.000000000000000000 AS DECIMAL(38, 18)) AS sell_md_amount,
                CAST(30.000000000000000000 AS DECIMAL(38, 18)) AS buy_lg_vol,
                CAST(300.000000000000000000 AS DECIMAL(38, 18)) AS buy_lg_amount,
                CAST(25.000000000000000000 AS DECIMAL(38, 18)) AS sell_lg_vol,
                CAST(250.000000000000000000 AS DECIMAL(38, 18)) AS sell_lg_amount,
                CAST(40.000000000000000000 AS DECIMAL(38, 18)) AS buy_elg_vol,
                CAST(400.000000000000000000 AS DECIMAL(38, 18)) AS buy_elg_amount,
                CAST(35.000000000000000000 AS DECIMAL(38, 18)) AS sell_elg_vol,
                CAST(350.000000000000000000 AS DECIMAL(38, 18)) AS sell_elg_amount,
                CAST(13.000000000000000000 AS DECIMAL(38, 18)) AS net_mf_vol,
                CAST(130.000000000000000000 AS DECIMAL(38, 18)) AS net_mf_amount,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_index_price_bar AS
            SELECT
                '000300.SH'::VARCHAR AS index_code,
                DATE '2026-04-15' AS trade_date,
                CAST(4000.000000000000000000 AS DECIMAL(38, 18)) AS open,
                CAST(4050.000000000000000000 AS DECIMAL(38, 18)) AS high,
                CAST(3980.000000000000000000 AS DECIMAL(38, 18)) AS low,
                CAST(4020.000000000000000000 AS DECIMAL(38, 18)) AS close,
                CAST(3990.000000000000000000 AS DECIMAL(38, 18)) AS pre_close,
                CAST(30.000000000000000000 AS DECIMAL(38, 18)) AS change,
                CAST(0.750000000000000000 AS DECIMAL(38, 18)) AS pct_chg,
                CAST(200000.000000000000000000 AS DECIMAL(38, 18)) AS vol,
                CAST(900000.000000000000000000 AS DECIMAL(38, 18)) AS amount,
                'SSE'::VARCHAR AS exchange,
                TRUE AS is_open,
                DATE '2026-04-14' AS pretrade_date,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_forecast_event AS
            SELECT
                '000001.SZ'::VARCHAR AS ts_code,
                DATE '2026-04-15' AS ann_date,
                DATE '2026-03-31' AS end_date,
                'increase'::VARCHAR AS forecast_type,
                CAST(5.000000000000000000 AS DECIMAL(38, 18)) AS p_change_min,
                CAST(10.000000000000000000 AS DECIMAL(38, 18)) AS p_change_max,
                CAST(100.000000000000000000 AS DECIMAL(38, 18)) AS net_profit_min,
                CAST(110.000000000000000000 AS DECIMAL(38, 18)) AS net_profit_max,
                CAST(90.000000000000000000 AS DECIMAL(38, 18)) AS last_parent_net,
                DATE '2026-04-14' AS first_ann_date,
                'Forecast summary'::VARCHAR AS summary,
                'Demand change'::VARCHAR AS change_reason,
                '0'::VARCHAR AS update_flag,
                'run-001'::VARCHAR AS source_run_id,
                TIMESTAMP '2026-04-15 10:30:00' AS raw_loaded_at
            """
        )
    finally:
        connection.close()


def _write_canonical_v2_mart_placeholder_relations(
    duckdb_path: Path,
) -> None:
    """Create minimal valid relations for the canonical_v2 / canonical_lineage marts
    introduced by the M1.3 batch (everything other than dim_security).

    The existing dim_security-focused tests assume the other 7 paired marts
    exist with internally consistent rows. Each table gets a single placeholder
    row per canonical PK so the pairing validator succeeds for those marts and
    the test assertion focuses on the dim_security pair behavior.
    """

    connection = duckdb.connect(str(duckdb_path))
    try:
        # canonical_v2.stock_basic + canonical_lineage.lineage_stock_basic
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_stock_basic_v2 (
                "security_id" VARCHAR,
                "symbol" VARCHAR,
                "display_name" VARCHAR,
                "area" VARCHAR,
                "industry" VARCHAR,
                "market" VARCHAR,
                "list_date" DATE,
                "is_active" BOOLEAN
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_stock_basic_v2 VALUES "
            "('SEC_PLACEHOLDER', '000900', 'Placeholder Co', 'Shenzhen', 'Bank', "
            "'Main', DATE '2000-01-01', TRUE)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_stock_basic (
                "security_id" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_stock_basic VALUES "
            "('SEC_PLACEHOLDER', 'tushare', 'stock_basic+stock_company+namechange', "
            "'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.dim_index + canonical_lineage.lineage_dim_index
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_dim_index_v2 (
                "index_id" VARCHAR,
                "index_name" VARCHAR,
                "index_market" VARCHAR,
                "index_category" VARCHAR,
                "first_effective_date" DATE,
                "latest_effective_date" DATE
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_dim_index_v2 VALUES "
            "('IDX_PLACEHOLDER', 'Placeholder Index', 'CN_A', 'BROAD', "
            "DATE '2000-01-01', DATE '2026-04-15')"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_dim_index (
                "index_id" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_dim_index VALUES "
            "('IDX_PLACEHOLDER', 'tushare', "
            "'index_basic+index_member+index_weight+index_classify', "
            "'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_price_bar + canonical_lineage.lineage_fact_price_bar
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_price_bar_v2 (
                "security_id" VARCHAR,
                "trade_date" DATE,
                "freq" VARCHAR,
                "open" DECIMAL(38, 18),
                "high" DECIMAL(38, 18),
                "low" DECIMAL(38, 18),
                "close" DECIMAL(38, 18),
                "pre_close" DECIMAL(38, 18),
                "change" DECIMAL(38, 18),
                "pct_chg" DECIMAL(38, 18),
                "vol" DECIMAL(38, 18),
                "amount" DECIMAL(38, 18),
                "adj_factor" DECIMAL(38, 18)
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_price_bar_v2 VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', 'daily', "
            "1, 2, 1, 1.5, 1, 0.5, 50, 100, 150, 1)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_price_bar (
                "security_id" VARCHAR,
                "trade_date" DATE,
                "freq" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_price_bar VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', 'daily', "
            "'tushare', 'daily+adj_factor', 'run-placeholder', "
            "TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_financial_indicator + lineage_fact_financial_indicator
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_financial_indicator_v2 (
                "security_id" VARCHAR,
                "end_date" DATE,
                "ann_date" DATE,
                "f_ann_date" DATE,
                "report_type" VARCHAR,
                "comp_type" VARCHAR,
                "update_flag" VARCHAR,
                "is_latest" BOOLEAN,
                "basic_eps" DECIMAL(38, 18),
                "diluted_eps" DECIMAL(38, 18),
                "total_revenue" DECIMAL(38, 18),
                "revenue" DECIMAL(38, 18),
                "operate_profit" DECIMAL(38, 18),
                "total_profit" DECIMAL(38, 18),
                "n_income" DECIMAL(38, 18),
                "n_income_attr_p" DECIMAL(38, 18),
                "money_cap" DECIMAL(38, 18),
                "total_cur_assets" DECIMAL(38, 18),
                "total_assets" DECIMAL(38, 18),
                "total_cur_liab" DECIMAL(38, 18),
                "total_liab" DECIMAL(38, 18),
                "total_hldr_eqy_exc_min_int" DECIMAL(38, 18),
                "total_liab_hldr_eqy" DECIMAL(38, 18),
                "net_profit" DECIMAL(38, 18),
                "n_cashflow_act" DECIMAL(38, 18),
                "n_cashflow_inv_act" DECIMAL(38, 18),
                "n_cash_flows_fnc_act" DECIMAL(38, 18),
                "n_incr_cash_cash_equ" DECIMAL(38, 18),
                "free_cashflow" DECIMAL(38, 18),
                "eps" DECIMAL(38, 18),
                "dt_eps" DECIMAL(38, 18),
                "grossprofit_margin" DECIMAL(38, 18),
                "netprofit_margin" DECIMAL(38, 18),
                "roe" DECIMAL(38, 18),
                "roa" DECIMAL(38, 18),
                "debt_to_assets" DECIMAL(38, 18),
                "or_yoy" DECIMAL(38, 18),
                "netprofit_yoy" DECIMAL(38, 18)
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_financial_indicator_v2 VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-03-31', DATE '2026-04-30', "
            "DATE '2026-04-30', '1', 'CN', 'O', TRUE, "
            "1, 1, 1000, 1000, 100, 80, 60, 60, 500, 800, 1000, "
            "300, 400, 600, 1000, 60, 100, -10, -5, 85, 80, "
            "1, 1, 0.1, 0.06, 0.06, 0.06, 0.40, 0.05, 0.05)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_financial_indicator (
                "security_id" VARCHAR,
                "end_date" DATE,
                "report_type" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_financial_indicator VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-03-31', '1', "
            "'tushare', 'fina_indicator+income+balancesheet+cashflow', "
            "'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_market_daily_feature + lineage_fact_market_daily_feature
        # Build column list dynamically — many decimal columns.
        market_feature_columns = [
            "security_id VARCHAR",
            "trade_date DATE",
            "close DECIMAL(38, 18)",
            "turnover_rate DECIMAL(38, 18)",
            "turnover_rate_f DECIMAL(38, 18)",
            "volume_ratio DECIMAL(38, 18)",
            "pe DECIMAL(38, 18)",
            "pe_ttm DECIMAL(38, 18)",
            "pb DECIMAL(38, 18)",
            "ps DECIMAL(38, 18)",
            "ps_ttm DECIMAL(38, 18)",
            "dv_ratio DECIMAL(38, 18)",
            "dv_ttm DECIMAL(38, 18)",
            "total_share DECIMAL(38, 18)",
            "float_share DECIMAL(38, 18)",
            "free_share DECIMAL(38, 18)",
            "total_mv DECIMAL(38, 18)",
            "circ_mv DECIMAL(38, 18)",
            "up_limit DECIMAL(38, 18)",
            "down_limit DECIMAL(38, 18)",
            "buy_sm_vol DECIMAL(38, 18)",
            "buy_sm_amount DECIMAL(38, 18)",
            "sell_sm_vol DECIMAL(38, 18)",
            "sell_sm_amount DECIMAL(38, 18)",
            "buy_md_vol DECIMAL(38, 18)",
            "buy_md_amount DECIMAL(38, 18)",
            "sell_md_vol DECIMAL(38, 18)",
            "sell_md_amount DECIMAL(38, 18)",
            "buy_lg_vol DECIMAL(38, 18)",
            "buy_lg_amount DECIMAL(38, 18)",
            "sell_lg_vol DECIMAL(38, 18)",
            "sell_lg_amount DECIMAL(38, 18)",
            "buy_elg_vol DECIMAL(38, 18)",
            "buy_elg_amount DECIMAL(38, 18)",
            "sell_elg_vol DECIMAL(38, 18)",
            "sell_elg_amount DECIMAL(38, 18)",
            "net_mf_vol DECIMAL(38, 18)",
            "net_mf_amount DECIMAL(38, 18)",
        ]
        connection.execute(
            "CREATE OR REPLACE TABLE mart_fact_market_daily_feature_v2 ("
            + ", ".join(f'"{col.split()[0]}" {col.split(maxsplit=1)[1]}' for col in market_feature_columns)
            + ")"
        )
        market_feature_value_count = len(market_feature_columns) - 2  # exclude security_id, trade_date
        market_feature_values = ", ".join(["1"] * market_feature_value_count)
        connection.execute(
            "INSERT INTO mart_fact_market_daily_feature_v2 VALUES ("
            f"'SEC_PLACEHOLDER', DATE '2026-04-15', {market_feature_values})"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_market_daily_feature (
                "security_id" VARCHAR,
                "trade_date" DATE,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_market_daily_feature VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', 'tushare', "
            "'daily_basic+stk_limit+moneyflow', 'run-placeholder', "
            "TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_index_price_bar + lineage_fact_index_price_bar
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_index_price_bar_v2 (
                "index_id" VARCHAR,
                "trade_date" DATE,
                "open" DECIMAL(38, 18),
                "high" DECIMAL(38, 18),
                "low" DECIMAL(38, 18),
                "close" DECIMAL(38, 18),
                "pre_close" DECIMAL(38, 18),
                "change" DECIMAL(38, 18),
                "pct_chg" DECIMAL(38, 18),
                "vol" DECIMAL(38, 18),
                "amount" DECIMAL(38, 18),
                "exchange" VARCHAR,
                "is_open" BOOLEAN,
                "pretrade_date" DATE
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_index_price_bar_v2 VALUES "
            "('IDX_PLACEHOLDER', DATE '2026-04-15', 1000, 1010, 990, 1005, "
            "1000, 5, 0.5, 100, 100000, 'SZSE', TRUE, DATE '2026-04-14')"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_index_price_bar (
                "index_id" VARCHAR,
                "trade_date" DATE,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_index_price_bar VALUES "
            "('IDX_PLACEHOLDER', DATE '2026-04-15', 'tushare', 'index_daily', "
            "'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_forecast_event + lineage_fact_forecast_event
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_forecast_event_v2 (
                "security_id" VARCHAR,
                "announcement_date" DATE,
                "report_period" DATE,
                "forecast_type" VARCHAR,
                "p_change_min" DECIMAL(38, 18),
                "p_change_max" DECIMAL(38, 18),
                "net_profit_min" DECIMAL(38, 18),
                "net_profit_max" DECIMAL(38, 18),
                "last_parent_net" DECIMAL(38, 18),
                "first_ann_date" DATE,
                "summary" VARCHAR,
                "change_reason" VARCHAR,
                "update_flag" VARCHAR
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_forecast_event_v2 VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31', "
            "'forecast', -10, 10, 100, 200, 150, DATE '2026-04-15', "
            "'placeholder', 'placeholder', 'O')"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_forecast_event (
                "security_id" VARCHAR,
                "announcement_date" DATE,
                "report_period" DATE,
                "update_flag" VARCHAR,
                "forecast_type" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_forecast_event VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', DATE '2026-03-31', 'O', "
            "'forecast', 'tushare', 'forecast', 'run-placeholder', "
            "TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_event + lineage_fact_event. Both rows share the
        # same canonical PK
        # (event_type, entity_id, event_date, event_key) so the pairing
        # validator passes.
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_event_v2 (
                "event_type" VARCHAR,
                "entity_id" VARCHAR,
                "event_date" DATE,
                "event_key" VARCHAR,
                "title" VARCHAR,
                "summary" VARCHAR,
                "event_subtype" VARCHAR,
                "related_date" DATE,
                "reference_url" VARCHAR,
                "rec_time" VARCHAR
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_event_v2 VALUES "
            "('dividend', 'ENTITY_PLACEHOLDER', DATE '2026-04-15', "
            "'ek-placeholder', 'Dividend', 'cash_div=1.00', 'paid', "
            "DATE '2026-03-31', NULL, NULL)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_event (
                "event_type" VARCHAR,
                "entity_id" VARCHAR,
                "event_date" DATE,
                "event_key" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_event VALUES "
            "('dividend', 'ENTITY_PLACEHOLDER', DATE '2026-04-15', "
            "'ek-placeholder', 'tushare', 'dividend', 'run-placeholder', "
            "TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_holding_position + lineage_fact_holding_position
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_holding_position_v2 (
                "holding_source" VARCHAR,
                "holder_id" VARCHAR,
                "holder_name" VARCHAR,
                "holder_type" VARCHAR,
                "security_id" VARCHAR,
                "report_date" DATE,
                "announced_date" DATE,
                "holding_amount" DECIMAL(38, 18),
                "holding_ratio" DECIMAL(38, 18),
                "holding_float_ratio" DECIMAL(38, 18),
                "holding_change" DECIMAL(38, 18),
                "market_value" DECIMAL(38, 18),
                "exchange" VARCHAR
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_holding_position_v2 VALUES "
            "('fund_portfolio', 'FUND_PLACEHOLDER', 'Placeholder Fund', 'fund', "
            "'SEC_PLACEHOLDER', DATE '2026-03-31', DATE '2026-04-15', "
            "100, 1, 1, NULL, 1000, NULL)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_holding_position (
                "holding_source" VARCHAR,
                "holder_id" VARCHAR,
                "security_id" VARCHAR,
                "report_date" DATE,
                "announced_date" DATE,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_holding_position VALUES "
            "('fund_portfolio', 'FUND_PLACEHOLDER', 'SEC_PLACEHOLDER', "
            "DATE '2026-03-31', DATE '2026-04-15', 'tushare', 'fund_portfolio', "
            "'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )

        # canonical_v2.fact_northbound_turnover + lineage_fact_northbound_turnover
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_fact_northbound_turnover_v2 (
                "security_id" VARCHAR,
                "trade_date" DATE,
                "security_name" VARCHAR,
                "market_type" VARCHAR,
                "rank" INTEGER,
                "close" DECIMAL(38, 18),
                "change" DECIMAL(38, 18),
                "amount" DECIMAL(38, 18),
                "net_amount" DECIMAL(38, 18),
                "buy_amount" DECIMAL(38, 18),
                "sell_amount" DECIMAL(38, 18)
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_fact_northbound_turnover_v2 VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', 'Placeholder Co', '1', "
            "1, 10, 0.1, 1000, 100, 550, 450)"
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_fact_northbound_turnover (
                "security_id" VARCHAR,
                "trade_date" DATE,
                "market_type" VARCHAR,
                "rank" INTEGER,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_lineage_fact_northbound_turnover VALUES "
            "('SEC_PLACEHOLDER', DATE '2026-04-15', '1', 1, 'tushare', "
            "'hsgt_top10', 'run-placeholder', TIMESTAMP '2026-04-15 10:00:00')"
        )
    finally:
        connection.close()


def write_canonical_v2_mart_relations(
    duckdb_path: Path,
    *,
    v2_security_ids: Sequence[str] = ("SEC_A", "SEC_B"),
    lineage_security_ids: Sequence[str] = ("SEC_A", "SEC_B"),
) -> None:
    _write_canonical_v2_mart_placeholder_relations(duckdb_path)
    connection = duckdb.connect(str(duckdb_path))
    try:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_dim_security_v2 (
                "security_id" VARCHAR,
                "symbol" VARCHAR,
                "display_name" VARCHAR,
                "market" VARCHAR,
                "industry" VARCHAR,
                "list_date" DATE,
                "is_active" BOOLEAN,
                "area" VARCHAR,
                "fullname" VARCHAR,
                "exchange" VARCHAR,
                "curr_type" VARCHAR,
                "list_status" VARCHAR,
                "delist_date" DATE,
                "setup_date" DATE,
                "province" VARCHAR,
                "city" VARCHAR,
                "reg_capital" DECIMAL(38, 18),
                "employees" DECIMAL(38, 18),
                "main_business" VARCHAR,
                "latest_namechange_name" VARCHAR,
                "latest_namechange_start_date" DATE,
                "latest_namechange_end_date" DATE,
                "latest_namechange_ann_date" DATE,
                "latest_namechange_reason" VARCHAR
            )
            """
        )
        for index, security_id in enumerate(v2_security_ids, start=1):
            connection.execute(
                """
                INSERT INTO mart_dim_security_v2 VALUES (
                    ?, ?, ?, 'Main', 'Bank', DATE '1991-04-03', TRUE, 'Shenzhen',
                    ?, 'SZSE', 'CNY', 'L', NULL, DATE '1987-12-22', 'Guangdong',
                    'Shenzhen', CAST(1000.000000000000000000 AS DECIMAL(38, 18)),
                    CAST(100.000000000000000000 AS DECIMAL(38, 18)), 'Banking',
                    ?, DATE '2020-01-01', NULL, DATE '2020-01-01', 'rename'
                )
                """,
                [
                    security_id,
                    f"{index:06d}",
                    f"Security {index}",
                    f"Security {index} Co Ltd",
                    f"Security {index}",
                ],
            )

        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_lineage_dim_security (
                "security_id" VARCHAR,
                "source_provider" VARCHAR,
                "source_interface_id" VARCHAR,
                "source_run_id" VARCHAR,
                "raw_loaded_at" TIMESTAMP
            )
            """
        )
        for index, security_id in enumerate(lineage_security_ids, start=1):
            connection.execute(
                """
                INSERT INTO mart_lineage_dim_security VALUES (
                    ?, 'tushare', 'stock_basic', ?, TIMESTAMP '2026-04-15 10:30:00'
                )
                """,
                [security_id, f"run-{index:03d}"],
            )
    finally:
        connection.close()


def write_staging_stock_basic(
    duckdb_path: Path,
    rows: Sequence[StockBasicRow],
    *,
    include_queue_fields: bool = False,
) -> None:
    connection = duckdb.connect(str(duckdb_path))
    try:
        queue_columns = (
            ', "submitted_at" TIMESTAMP, "ingest_seq" BIGINT'
            if include_queue_fields
            else ""
        )
        connection.execute(
            f"""
            CREATE OR REPLACE TABLE stg_stock_basic (
                "ts_code" VARCHAR,
                "symbol" VARCHAR,
                "name" VARCHAR,
                "area" VARCHAR,
                "industry" VARCHAR,
                "market" VARCHAR,
                "list_date" DATE,
                "is_active" BOOLEAN,
                "source_run_id" VARCHAR
                {queue_columns}
            )
            """
        )
        for row in rows:
            if include_queue_fields:
                connection.execute(
                    """
                    INSERT INTO stg_stock_basic VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, 1
                    )
                    """,
                    row,
                )
            else:
                connection.execute(
                    """
                    INSERT INTO stg_stock_basic VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
    finally:
        connection.close()


def stock_basic_rows() -> list[StockBasicRow]:
    return [
        (
            "000001.SZ",
            "000001",
            "Ping An Bank",
            "Shenzhen",
            "Bank",
            "Main",
            date(1991, 4, 3),
            True,
            "run-001",
        ),
        (
            "000002.SZ",
            "000002",
            "Vanke A",
            "Shenzhen",
            "Real Estate",
            "Main",
            date(1991, 1, 29),
            True,
            "run-001",
        ),
    ]
