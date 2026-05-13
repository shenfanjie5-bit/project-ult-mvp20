from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pytest

from data_platform.raw import RawWriter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
DBT_MODELS_DIR = DBT_PROJECT_DIR / "models"
DBT_TESTS_DIR = DBT_PROJECT_DIR / "tests"
MODEL_CONTRACT_TESTS = {
    "accepted_values",
    "at_most_one_true_per_group",
    "not_null",
    "parsable_yyyymmdd_or_date",
    "relationships",
    "unique",
    "unique_combination_of_columns",
}
MODEL_KEY_TESTS = {"unique", "unique_combination_of_columns"}
EXPECTED_CUSTOM_DATA_TESTS = {
    "assert_event_mart_has_no_body_fields.sql",
    "assert_financial_latest_unique.sql",
    "assert_latest_raw_artifact_unique.sql",
    "assert_no_queue_fields_in_marts.sql",
    "assert_raw_manifest_fresh.sql",
}


def test_every_dbt_model_has_yaml_test_coverage() -> None:
    yaml = pytest.importorskip("yaml")

    declarations = _load_model_declarations(yaml)
    model_paths = sorted(DBT_MODELS_DIR.glob("**/*.sql"))

    missing_yaml = [
        _relative_model_path(path)
        for path in model_paths
        if path.stem not in declarations
    ]
    missing_contract_tests = [
        _relative_model_path(path)
        for path in model_paths
        if path.stem in declarations
        and MODEL_CONTRACT_TESTS.isdisjoint(_model_test_names(declarations[path.stem]))
    ]
    missing_key_tests = [
        _relative_model_path(path)
        for path in model_paths
        if path.stem in declarations
        and MODEL_KEY_TESTS.isdisjoint(_model_test_names(declarations[path.stem]))
    ]

    assert missing_yaml == []
    assert missing_contract_tests == []
    assert missing_key_tests == []


def test_custom_data_test_files_are_declared() -> None:
    assert DBT_TESTS_DIR.exists()
    assert EXPECTED_CUSTOM_DATA_TESTS <= {
        path.name for path in DBT_TESTS_DIR.glob("*.sql")
    }


def test_raw_manifest_data_tests_reject_invalid_run_id_missing_file_and_duplicate_latest(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    invalid_raw_zone_path = tmp_path / "invalid_raw"
    invalid_artifact = _write_minimal_raw_artifact(invalid_raw_zone_path, tmp_path)
    invalid_manifest_path = invalid_artifact.path.parent / "_manifest.json"
    invalid_manifest = json.loads(invalid_manifest_path.read_text(encoding="utf-8"))
    invalid_manifest["artifacts"][0]["run_id"] = "not-a-valid-run-id"
    invalid_manifest_path.write_text(
        json.dumps(invalid_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    invalid_rows = _fetch_data_test_rows(
        duckdb,
        "assert_raw_manifest_fresh",
        invalid_raw_zone_path,
    )

    duplicate_raw_zone_path = tmp_path / "duplicate_raw"
    first_duplicate_artifact = _write_minimal_raw_artifact(duplicate_raw_zone_path, tmp_path)
    second_duplicate_artifact = _write_minimal_raw_artifact(duplicate_raw_zone_path, tmp_path)
    duplicate_manifest_path = first_duplicate_artifact.path.parent / "_manifest.json"
    duplicate_manifest = json.loads(duplicate_manifest_path.read_text(encoding="utf-8"))
    for artifact in duplicate_manifest["artifacts"]:
        artifact["written_at"] = "2026-04-15T01:00:00+00:00"
    duplicate_manifest_path.write_text(
        json.dumps(duplicate_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    duplicate_rows = _fetch_data_test_rows(
        duckdb,
        "assert_latest_raw_artifact_unique",
        duplicate_raw_zone_path,
    )

    missing_raw_zone_path = tmp_path / "missing_raw"
    missing_artifact = _write_minimal_raw_artifact(missing_raw_zone_path, tmp_path)
    missing_artifact.path.unlink()
    missing_rows = _fetch_data_test_rows(
        duckdb,
        "assert_raw_manifest_fresh",
        missing_raw_zone_path,
    )

    assert second_duplicate_artifact.run_id != first_duplicate_artifact.run_id
    assert invalid_rows != []
    assert any(row[4] == "not-a-valid-run-id" for row in invalid_rows)
    assert duplicate_rows != []
    assert any(row[1] == "stock_basic" and row[4] == 2 for row in duplicate_rows)
    assert missing_rows != []
    assert any(row[-1] is False for row in missing_rows)


def test_raw_manifest_data_tests_reject_duplicate_manifest_row(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    duplicate_raw_zone_path = tmp_path / "duplicate_manifest_raw"
    duplicate_artifact = _write_minimal_raw_artifact(duplicate_raw_zone_path, tmp_path)
    duplicate_manifest_path = duplicate_artifact.path.parent / "_manifest.json"
    duplicate_manifest = json.loads(duplicate_manifest_path.read_text(encoding="utf-8"))
    duplicate_manifest["artifacts"].append(dict(duplicate_manifest["artifacts"][0]))
    duplicate_manifest_path.write_text(
        json.dumps(duplicate_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = _fetch_data_test_rows(
        duckdb,
        "assert_latest_raw_artifact_unique",
        duplicate_raw_zone_path,
    )

    assert rows != []
    assert any(row[1] == "stock_basic" and row[4] == 2 for row in rows)


def test_mart_custom_data_tests_reject_forbidden_columns() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            "create table mart_dim_security(ts_code varchar, submitted_at timestamp)"
        )
        connection.execute("create table mart_dim_index(index_code varchar)")
        connection.execute("create table mart_fact_price_bar(ts_code varchar)")
        connection.execute(
            """
            create table mart_fact_financial_indicator(
                ts_code varchar,
                end_date date,
                report_type varchar,
                is_latest boolean
            )
            """
        )
        connection.execute("create table mart_fact_event(event_type varchar, body varchar)")
        connection.execute("create table mart_fact_market_daily_feature(ts_code varchar)")
        connection.execute("create table mart_fact_index_price_bar(index_code varchar)")
        connection.execute("create table mart_fact_forecast_event(ts_code varchar)")
        connection.execute(
            """
            insert into mart_fact_financial_indicator values
                ('000001.SZ', date '2026-03-31', '1', true),
                ('000001.SZ', date '2026-03-31', '1', true)
            """
        )

        queue_rows = _execute_rendered_data_test(
            connection,
            "assert_no_queue_fields_in_marts",
            Path("/tmp/raw"),
        )
        event_rows = _execute_rendered_data_test(
            connection,
            "assert_event_mart_has_no_body_fields",
            Path("/tmp/raw"),
        )
        financial_rows = _execute_rendered_data_test(
            connection,
            "assert_financial_latest_unique",
            Path("/tmp/raw"),
        )
    finally:
        connection.close()

    assert queue_rows == [("mart_dim_security", "submitted_at")]
    assert event_rows == [("mart_fact_event", "body")]
    assert financial_rows == [("000001.SZ", date(2026, 3, 31), "1", 2)]


def _load_model_declarations(yaml: Any) -> dict[str, dict[str, Any]]:
    declarations: dict[str, dict[str, Any]] = {}
    for yaml_path in sorted(DBT_MODELS_DIR.glob("**/*.yml")):
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        for model in parsed.get("models", []):
            model_name = model["name"]
            if model_name in declarations:
                raise AssertionError(f"duplicate dbt model YAML declaration: {model_name}")
            declarations[model_name] = model
    return declarations


def _model_test_names(model: dict[str, Any]) -> set[str]:
    test_names = {_test_name(test) for test in model.get("tests", [])}
    for column in model.get("columns", []):
        test_names.update(_test_name(test) for test in column.get("tests", []))
    return test_names


def _test_name(test: str | dict[str, Any]) -> str:
    if isinstance(test, str):
        return test
    return next(iter(test))


def _relative_model_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _write_minimal_raw_artifact(raw_zone_path: Path, tmp_path: Path) -> Any:
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    return writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 15),
        str(uuid4()),
        pa.table({"ts_code": ["000001.SZ"]}),
    )


def _fetch_data_test_rows(
    duckdb: Any,
    test_name: str,
    raw_zone_path: Path,
) -> list[tuple[Any, ...]]:
    connection = duckdb.connect(":memory:")
    try:
        return _execute_rendered_data_test(connection, test_name, raw_zone_path)
    finally:
        connection.close()


def _execute_rendered_data_test(
    connection: Any,
    test_name: str,
    raw_zone_path: Path,
) -> list[tuple[Any, ...]]:
    return connection.execute(_render_data_test(test_name, raw_zone_path)).fetchall()


def _render_data_test(test_name: str, raw_zone_path: Path) -> str:
    jinja2 = pytest.importorskip("jinja2")

    environment = jinja2.Environment()
    environment.globals["config"] = lambda **_kwargs: ""
    environment.globals["ref"] = lambda ref_name: f'"{ref_name}"'
    environment.globals["env_var"] = lambda name, default=None: (
        str(raw_zone_path) if name == "DP_RAW_ZONE_PATH" else default
    )

    return (
        environment.from_string((DBT_TESTS_DIR / f"{test_name}.sql").read_text())
        .render()
        .strip()
    )
