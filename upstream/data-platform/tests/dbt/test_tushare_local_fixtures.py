"""Tushare Phase B real-consumption tests for local raw fixtures.

Plan: ~/.claude/plans/wise-cooking-wolf.md §6.4.4.

Drives the weekly + monthly dbt staging models against the on-disk
small JSON fixtures shipped under
``tests/dbt/fixtures/raw/tushare/{weekly,monthly}/dt=20260415/``. The
tests generate parquet + manifest files under ``tmp_path`` with RawWriter
so the repository does not track runtime raw-zone artifacts.

For each of ``weekly`` and ``monthly``, the test asserts:

1. Fixture metadata and row source files exist.
2. The generated ``_manifest.json`` matches the RawWriter-written shape
   (``artifacts[0].{dataset, partition_date, path, row_count, run_id,
   source_id, written_at}``).
3. ``_source.json`` exists and satisfies the Phase B §7 traceability
   8-key contract + ``completeness_status == "未见明显遗漏"``.
4. The parquet file generated for the manifest exists under ``tmp_path``.
5. The parquet schema matches the canonical ``TUSHARE_BAR_SCHEMA``
   (from ``data_platform.adapters.tushare.assets``).
6. ``stg_<dataset>`` runs to success against the on-disk fixture
   through the Jinja-rendered dbt SQL + DuckDB.
7. Staged row count equals the manifest's ``row_count`` (proves the
   staging path really read the parquet, not an empty/wrong dataset).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from data_platform.adapters.tushare.assets import TUSHARE_BAR_SCHEMA
from data_platform.raw import RawWriter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
STAGING_DIR = DBT_PROJECT_DIR / "models" / "staging"
FIXTURE_METADATA_ROOT = PROJECT_ROOT / "tests" / "dbt" / "fixtures" / "raw" / "tushare"

PHASE_B_DATASETS: tuple[str, ...] = ("weekly", "monthly")
PARTITION_DIR = "dt=20260415"
PARTITION_DATE = date(2026, 4, 15)
RUN_IDS = {
    "weekly": "aa0b0001-0000-4000-9000-000000000001",
    "monthly": "aa0b0001-0000-4000-9000-000000000002",
}

_REQUIRED_TRACEABILITY_KEYS = frozenset(
    {
        "corpus_root",
        "dataset_path",
        "datasets",
        "selected_ts_codes",
        "date_window",
        "audit_timestamp",
        "completeness_status",
        "coverage_note",
    }
)


@dataclass(frozen=True)
class LocalRawFixture:
    raw_zone_root: Path
    partition_dir: Path
    manifest: dict[str, Any]
    parquet_path: Path


def _render_staging_model(model_name: str, raw_zone_path: Path) -> str:
    """Render the dbt model Jinja template into executable SQL.

    Mirrors the helper in ``test_tushare_staging_models.py`` so both
    test files exercise the real dbt macros + raw-zone path logic.
    """

    jinja2 = pytest.importorskip("jinja2")

    environment = jinja2.Environment()
    environment.globals["config"] = lambda **_kwargs: ""
    environment.globals["env_var"] = lambda name, default=None: (
        str(raw_zone_path) if name == "DP_RAW_ZONE_PATH" else default
    )

    path_module = environment.from_string(
        (DBT_PROJECT_DIR / "macros" / "dp_raw_path.sql").read_text()
    ).make_module({})
    environment.globals["dp_raw_path"] = path_module.dp_raw_path
    environment.globals["dp_raw_manifest_path"] = path_module.dp_raw_manifest_path

    latest_module = environment.from_string(
        (DBT_PROJECT_DIR / "macros" / "stg_latest_raw.sql").read_text()
    ).make_module({})
    environment.globals["stg_latest_raw"] = latest_module.stg_latest_raw

    return environment.from_string(
        (STAGING_DIR / f"{model_name}.sql").read_text()
    ).render().strip()


@pytest.mark.parametrize("dataset", PHASE_B_DATASETS)
def test_fixture_source_rows_generate_rawwriter_manifest(
    tmp_path: Path,
    dataset: str,
) -> None:
    metadata_partition_dir = FIXTURE_METADATA_ROOT / dataset / PARTITION_DIR
    assert metadata_partition_dir.is_dir(), f"missing fixture dir: {metadata_partition_dir}"
    assert (metadata_partition_dir / "_rows.json").is_file()

    fixture = _write_local_raw_fixture(dataset, tmp_path)
    manifest_path = fixture.partition_dir / "_manifest.json"
    assert manifest_path.is_file(), f"missing manifest: {manifest_path}"

    manifest = fixture.manifest
    assert manifest["dataset"] == dataset
    assert manifest["source_id"] == "tushare"
    assert manifest["partition_date"] == "2026-04-15"
    assert len(manifest["artifacts"]) == 1
    artifact = manifest["artifacts"][0]
    # Match the RawWriter-written manifest artifact shape exactly.
    for key in ("dataset", "partition_date", "path", "row_count", "run_id", "source_id", "written_at"):
        assert key in artifact, f"manifest artifact missing key: {key}"
    assert artifact["run_id"] == RUN_IDS[dataset]
    assert artifact["row_count"] == _declared_row_count(dataset)
    assert fixture.parquet_path.is_file()


@pytest.mark.parametrize("dataset", PHASE_B_DATASETS)
def test_source_json_has_all_eight_traceability_keys(dataset: str) -> None:
    source_path = FIXTURE_METADATA_ROOT / dataset / PARTITION_DIR / "_source.json"
    assert source_path.is_file(), f"missing traceability sidecar: {source_path}"

    source = json.loads(source_path.read_text(encoding="utf-8"))
    missing = _REQUIRED_TRACEABILITY_KEYS - set(source.keys())
    assert not missing, f"{dataset} _source.json missing keys: {missing}"
    assert source["completeness_status"] == "未见明显遗漏"
    assert source["datasets"] == [dataset]


@pytest.mark.parametrize("dataset", PHASE_B_DATASETS)
def test_generated_parquet_schema_matches_tushare_bar_schema(
    tmp_path: Path,
    dataset: str,
) -> None:
    """Codex review #1 P3 fix: previously this test only compared
    column-name SETS — type drift (e.g. ``vol`` switching from string
    to int64, or ``trade_date`` becoming a ``date32`` column) would
    pass undetected. Now we assert each column's pyarrow type is
    bit-identical to ``TUSHARE_BAR_SCHEMA.field(name).type``, which
    is the contract staging models depend on (TUSHARE_RAW_NUMERIC_TYPE
    is ``pa.string()``; staging is responsible for the type-cast).
    """

    fixture = _write_local_raw_fixture(dataset, tmp_path)
    parquet_path = fixture.parquet_path
    assert parquet_path.is_file(), f"manifest-referenced parquet missing: {parquet_path}"

    table = pq.read_table(parquet_path)
    expected_columns = set(TUSHARE_BAR_SCHEMA.names)
    # ``dt`` is auto-added by hive partitioning at read time; strip it
    # so the comparison is against the canonical TUSHARE_BAR_SCHEMA.
    actual_columns = set(table.column_names) - {"dt"}
    assert actual_columns == expected_columns, (
        f"{dataset} parquet column set drifted from TUSHARE_BAR_SCHEMA: "
        f"expected {sorted(expected_columns)}, got {sorted(actual_columns)}"
    )

    # Type-level lock-in: every TUSHARE_BAR_SCHEMA-declared column's
    # pyarrow type must match the parquet column's pyarrow type
    # exactly. Catching name-only matches with mismatched types is
    # the precise gap codex review #1 P3 flagged.
    type_drift: list[str] = []
    for field_name in TUSHARE_BAR_SCHEMA.names:
        expected_type = TUSHARE_BAR_SCHEMA.field(field_name).type
        actual_type = table.schema.field(field_name).type
        if not actual_type.equals(expected_type):
            type_drift.append(
                f"{field_name}: expected {expected_type!s}, got {actual_type!s}"
            )
    assert not type_drift, (
        f"{dataset} parquet column types drifted from TUSHARE_BAR_SCHEMA "
        f"(staging model TUSHARE_RAW_NUMERIC_TYPE expects pa.string() "
        f"for all numeric columns; staging is responsible for casting): "
        f"{type_drift}"
    )


@pytest.mark.parametrize("dataset", PHASE_B_DATASETS)
def test_staging_model_runs_against_generated_fixture(
    tmp_path: Path,
    dataset: str,
) -> None:
    """End-to-end: stg_<dataset> must execute against the on-disk
    fixture and return the expected row count. This is the critical
    real-consumption gate — if the staging model can't read the
    fixture, the fixture is effectively dead weight.
    """

    duckdb = pytest.importorskip("duckdb")

    # ``dp_raw_path`` expects DP_RAW_ZONE_PATH to be the raw-zone ROOT
    # (containing the ``tushare/`` subdir), not the tushare subdir itself.
    fixture = _write_local_raw_fixture(dataset, tmp_path)
    model_sql = _render_staging_model(f"stg_{dataset}", fixture.raw_zone_root)

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f'create view "stg_{dataset}" as {model_sql}')
        staged_rows = connection.execute(
            f'select count(*) from "stg_{dataset}"'
        ).fetchone()[0]
    finally:
        connection.close()

    expected_row_count = fixture.manifest["artifacts"][0]["row_count"]
    assert staged_rows == expected_row_count, (
        f"stg_{dataset} staged {staged_rows} rows but fixture manifest "
        f"declares row_count={expected_row_count}; the staging model "
        f"is not reading the on-disk fixture correctly"
    )


@pytest.mark.parametrize("dataset", PHASE_B_DATASETS)
def test_generated_fixture_all_rows_share_declared_ts_code(
    tmp_path: Path,
    dataset: str,
) -> None:
    """Sanity: the fixture's parquet contents must match the
    ``selected_ts_codes`` declared in ``_source.json`` — otherwise the
    traceability claim is fraudulent."""

    metadata_partition_dir = FIXTURE_METADATA_ROOT / dataset / PARTITION_DIR
    source = json.loads((metadata_partition_dir / "_source.json").read_text(encoding="utf-8"))
    declared_ts_codes = set(source["selected_ts_codes"])

    fixture = _write_local_raw_fixture(dataset, tmp_path)
    table = pq.read_table(fixture.parquet_path)
    actual_ts_codes = set(table.column("ts_code").to_pylist())

    assert actual_ts_codes.issubset(declared_ts_codes), (
        f"{dataset} parquet contains ts_codes {actual_ts_codes} not "
        f"declared in _source.json selected_ts_codes {declared_ts_codes}"
    )


def _write_local_raw_fixture(dataset: str, tmp_path: Path) -> LocalRawFixture:
    rows = _load_rows(dataset)
    raw_zone_root = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_root,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    artifact = writer.write_arrow(
        "tushare",
        dataset,
        PARTITION_DATE,
        RUN_IDS[dataset],
        pa.Table.from_pylist(rows, schema=TUSHARE_BAR_SCHEMA),
    )
    manifest_path = artifact.path.parent / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return LocalRawFixture(
        raw_zone_root=raw_zone_root,
        partition_dir=artifact.path.parent,
        manifest=manifest,
        parquet_path=artifact.path,
    )


def _load_rows(dataset: str) -> list[dict[str, Any]]:
    rows_path = FIXTURE_METADATA_ROOT / dataset / PARTITION_DIR / "_rows.json"
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    assert isinstance(rows, list)
    return rows


def _declared_row_count(dataset: str) -> int:
    source_path = FIXTURE_METADATA_ROOT / dataset / PARTITION_DIR / "_source.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    return int(source["row_count"])
