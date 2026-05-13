from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pytest

from data_platform.adapters.tushare import TUSHARE_ASSETS
from data_platform.raw import RawWriter
from tests.dbt.test_tushare_staging_models import (
    _render_staging_model,
    _run_dbt_wrapper,
    _sample_table,
    _sample_table_with_values,
    _write_all_tushare_raw_fixtures,
    _write_duckdb_only_profile,
    require_working_dbt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
INTERMEDIATE_DIR = DBT_PROJECT_DIR / "models" / "intermediate"
INTERMEDIATE_MODEL_NAMES = [
    "int_event_timeline",
    "int_financial_reports_latest",
    "int_forecast_events",
    "int_index_membership",
    "int_index_price_bars",
    "int_market_daily_features",
    "int_price_bars_adjusted",
    "int_security_master",
]


def test_intermediate_sql_and_schema_contracts_are_present() -> None:
    yaml = pytest.importorskip("yaml")

    parsed_schema = yaml.safe_load((INTERMEDIATE_DIR / "_schema.yml").read_text())
    declared_models = {model["name"]: model for model in parsed_schema["models"]}

    assert set(declared_models) == set(INTERMEDIATE_MODEL_NAMES)
    assert "at_most_one_true_per_group" in (
        DBT_PROJECT_DIR / "macros" / "intermediate_tests.sql"
    ).read_text()

    for model_name in INTERMEDIATE_MODEL_NAMES:
        model_sql = (INTERMEDIATE_DIR / f"{model_name}.sql").read_text()
        lowered_sql = model_sql.lower()

        assert "{{ ref(" in model_sql
        assert "select *" not in lowered_sql
        assert "canonical." not in lowered_sql
        assert "formal." not in lowered_sql
        assert "iceberg_scan" not in lowered_sql

    security_sql = (INTERMEDIATE_DIR / "int_security_master.sql").read_text().lower()
    assert "canonical_entity_id" not in security_sql
    assert "submitted_at" not in security_sql
    assert "ingest_seq" not in security_sql

    event_columns = _schema_columns(declared_models["int_event_timeline"])
    assert "body" not in event_columns
    assert "content" not in event_columns
    assert "text" not in event_columns

    event_tests = declared_models["int_event_timeline"]["tests"]
    event_unique_test = next(
        test["unique_combination_of_columns"]
        for test in event_tests
        if _model_test_name(test) == "unique_combination_of_columns"
    )
    assert "source_run_id" not in event_unique_test["combination_of_columns"]

    financial_tests = declared_models["int_financial_reports_latest"]["tests"]
    assert any(_model_test_name(test) == "at_most_one_true_per_group" for test in financial_tests)

    membership_columns = {
        column["name"]: column for column in declared_models["int_index_membership"]["columns"]
    }
    index_code_relationship = _relationship_test(membership_columns["index_code"])
    assert index_code_relationship["to"] == "ref('stg_index_basic')"
    assert index_code_relationship["field"] == "ts_code"
    assert index_code_relationship["config"]["severity"] == "error"

    market_sql = (INTERMEDIATE_DIR / "int_market_daily_features.sql").read_text()
    assert "stg_daily_basic" in market_sql
    assert "stg_stk_limit" in market_sql
    assert "stg_moneyflow" in market_sql

    index_price_columns = {
        column["name"]: column for column in declared_models["int_index_price_bars"]["columns"]
    }
    index_price_relationship = _relationship_test(index_price_columns["index_code"])
    assert index_price_relationship["to"] == "ref('stg_index_basic')"
    assert index_price_relationship["field"] == "ts_code"
    assert index_price_relationship["config"]["severity"] == "error"

    forecast_tests = declared_models["int_forecast_events"]["tests"]
    forecast_unique_test = next(
        test["unique_combination_of_columns"]
        for test in forecast_tests
        if _model_test_name(test) == "unique_combination_of_columns"
    )
    assert forecast_unique_test["combination_of_columns"] == [
        "ts_code",
        "ann_date",
        "end_date",
        "update_flag",
        "forecast_type",
    ]


def test_intermediate_models_execute_with_duckdb_raw_fixture(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        _create_all_intermediate_tables(connection)

        price_rows = connection.execute(
            """
            select ts_code, trade_date, freq, adj_factor
            from int_price_bars_adjusted
            order by freq
            """
        ).fetchall()
        price_duplicate_count = connection.execute(
            """
            select count(*)
            from (
                select ts_code, trade_date, freq
                from int_price_bars_adjusted
                group by ts_code, trade_date, freq
                having count(*) > 1
            )
            """
        ).fetchone()[0]
        financial_row = connection.execute(
            """
            select is_latest, total_revenue, total_assets, n_cashflow_act, roe
            from int_financial_reports_latest
            """
        ).fetchone()
        security_columns = [
            row[1]
            for row in connection.execute("pragma table_info('int_security_master')").fetchall()
        ]
        security_row = connection.execute(
            """
            select ts_code, symbol, name, market, industry, list_date, is_active
            from int_security_master
            """
        ).fetchone()
        membership_row = connection.execute(
            """
            select index_code, con_code, trade_date, effective_date, weight
            from int_index_membership
            """
        ).fetchone()
        event_types = [
            row[0]
            for row in connection.execute(
                """
                select event_type
                from int_event_timeline
                order by event_type
                """
            ).fetchall()
        ]
        event_columns = [
            row[1]
            for row in connection.execute("pragma table_info('int_event_timeline')").fetchall()
        ]
        market_row = connection.execute(
            """
            select ts_code, trade_date, close, up_limit, net_mf_amount
            from int_market_daily_features
            """
        ).fetchone()
        index_price_row = connection.execute(
            """
            select index_code, trade_date, close, is_open, pretrade_date
            from int_index_price_bars
            """
        ).fetchone()
        forecast_row = connection.execute(
            """
            select ts_code, ann_date, end_date, forecast_type, p_change_min, update_flag
            from int_forecast_events
            """
        ).fetchone()
    finally:
        connection.close()

    assert len(price_rows) == 3
    assert {row[2] for row in price_rows} == {"daily", "weekly", "monthly"}
    assert all(row[0] == "000001.SZ" for row in price_rows)
    assert all(row[1] == date(2026, 4, 15) for row in price_rows)
    assert all(row[3] == "1.123456789012345678" for row in price_rows)
    assert price_duplicate_count == 0

    assert financial_row == (
        True,
        Decimal("1.123456789012345678"),
        Decimal("1.123456789012345678"),
        Decimal("1.123456789012345678"),
        Decimal("1.123456789012345678"),
    )
    assert {"canonical_entity_id", "submitted_at", "ingest_seq"}.isdisjoint(security_columns)
    assert security_row == (
        "000001.SZ",
        "000001",
        "name-fixture",
        "market-fixture",
        "industry-fixture",
        date(2026, 4, 15),
        True,
    )
    assert membership_row == (
        "000300.SH",
        "000001.SZ",
        date(2026, 4, 15),
        date(2026, 4, 15),
        "weight-fixture",
    )
    assert event_types == [
        "announcement",
        "block_trade",
        "disclosure_date",
        "dividend",
        "holder_number",
        # M1.13 expansion (precondition 9 closure) — 8 new event_type
        # values from the candidate event_timeline sources.
        "hot_money_trade",
        "institutional_survey",
        "name_change",
        "pledge_event",
        "pledge_summary",
        "price_limit_event",
        "price_limit_status",
        "share_float",
        "share_repurchase",
        "shareholder_trade",
        "suspend",
    ]
    assert {"body", "content", "text"}.isdisjoint(event_columns)
    assert market_row == (
        "000001.SZ",
        date(2026, 4, 15),
        "1.123456789012345678",
        "1.123456789012345678",
        "1.123456789012345678",
    )
    assert index_price_row == (
        "000300.SH",
        date(2026, 4, 15),
        "1.123456789012345678",
        "1",
        date(2026, 4, 15),
    )
    assert forecast_row == (
        "000001.SZ",
        date(2026, 4, 15),
        date(2026, 4, 15),
        "type-fixture",
        "1.123456789012345678",
        "0",
    )


def test_index_price_bars_join_trade_calendar_by_exchange() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(
            """
            create table stg_index_daily (
                ts_code varchar,
                trade_date date,
                close varchar,
                open varchar,
                high varchar,
                low varchar,
                pre_close varchar,
                change varchar,
                pct_chg varchar,
                vol varchar,
                amount varchar,
                source_run_id varchar,
                raw_loaded_at timestamp
            )
            """
        )
        connection.execute(
            """
            insert into stg_index_daily values (
                '399001.SZ',
                date '2026-04-15',
                '100.0',
                '99.0',
                '101.0',
                '98.0',
                '99.5',
                '0.5',
                '0.50',
                '1000',
                '100000',
                'index-run',
                timestamp '2026-04-15 18:00:00'
            )
            """
        )
        connection.execute(
            """
            create table stg_trade_cal (
                exchange varchar,
                cal_date date,
                is_open varchar,
                pretrade_date date,
                source_run_id varchar,
                raw_loaded_at timestamp
            )
            """
        )
        connection.execute(
            """
            insert into stg_trade_cal values
                (
                    'SSE',
                    date '2026-04-15',
                    '0',
                    date '2026-04-14',
                    'calendar-sse',
                    timestamp '2026-04-15 18:00:00'
                ),
                (
                    'SZSE',
                    date '2026-04-15',
                    '1',
                    date '2026-04-14',
                    'calendar-szse',
                    timestamp '2026-04-15 18:00:00'
                )
            """
        )

        model_sql = _render_intermediate_model("int_index_price_bars")
        connection.execute(f'create table "int_index_price_bars" as {model_sql}')
        row = connection.execute(
            """
            select index_code, exchange, is_open, source_run_id
            from int_index_price_bars
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == ("399001.SZ", "SZSE", "1", "index-run")


def test_financial_intermediate_combines_latest_metrics_by_source(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_raw_fixtures_with_misaligned_financial_versions(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        model_sql = _render_intermediate_model("int_financial_reports_latest")
        connection.execute(f'create table "int_financial_reports_latest" as {model_sql}')
        rows = connection.execute(
            """
            select
                ann_date,
                f_ann_date,
                update_flag,
                is_latest,
                total_revenue,
                total_assets,
                n_cashflow_act,
                roe
            from int_financial_reports_latest
            where ts_code = '000001.SZ'
              and end_date = date '2026-03-31'
              and report_type = '1'
            """
        ).fetchall()
        latest_count = connection.execute(
            """
            select count(*)
            from int_financial_reports_latest
            where ts_code = '000001.SZ'
              and end_date = date '2026-03-31'
              and report_type = '1'
              and is_latest
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert rows == [
        (
            date(2026, 4, 16),
            date(2026, 4, 16),
            "1",
            True,
            Decimal("2.000000000000000000"),
            Decimal("10.000000000000000000"),
            Decimal("20.000000000000000000"),
            Decimal("30.000000000000000000"),
        )
    ]
    assert latest_count == 1


def test_dbt_run_and_test_intermediate_with_rawwriter_fixture(tmp_path: Path) -> None:
    require_working_dbt()

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    _write_duckdb_only_profile(profiles_dir / "profiles.yml")

    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(profiles_dir)
    env["DP_RAW_ZONE_PATH"] = str(raw_zone_path)
    env["DP_DUCKDB_PATH"] = str(tmp_path / "data_platform.duckdb")

    run_result = _run_dbt_wrapper(
        [
            "run",
            "--profiles-dir",
            str(profiles_dir),
            "--target-path",
            str(tmp_path / "run"),
            "--select",
            "staging",
            "intermediate",
        ],
        env=env,
    )
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr

    test_result = _run_dbt_wrapper(
        [
            "test",
            "--profiles-dir",
            str(profiles_dir),
            "--target-path",
            str(tmp_path / "test"),
            "--select",
            "staging",
            "intermediate",
        ],
        env=env,
    )
    assert test_result.returncode == 0, test_result.stdout + test_result.stderr


def _schema_columns(model: dict[str, Any]) -> set[str]:
    return {column["name"] for column in model.get("columns", [])}


def _model_test_name(test: str | dict[str, Any]) -> str:
    if isinstance(test, str):
        return test
    return next(iter(test))


def _relationship_test(column: dict[str, Any]) -> dict[str, Any]:
    for test in column.get("tests", []):
        if isinstance(test, dict) and "relationships" in test:
            return test["relationships"]
    raise AssertionError(f"missing relationship test for column: {column['name']}")


def _create_all_staging_views(connection: Any, raw_zone_path: Path) -> None:
    for asset in TUSHARE_ASSETS:
        model_name = f"stg_{asset.dataset}"
        model_sql = _render_staging_model(model_name, raw_zone_path)
        connection.execute(f'create view "{model_name}" as {model_sql}')


def _create_all_intermediate_tables(connection: Any) -> None:
    for model_name in INTERMEDIATE_MODEL_NAMES:
        model_sql = _render_intermediate_model(model_name)
        connection.execute(f'create table "{model_name}" as {model_sql}')


def _render_intermediate_model(model_name: str) -> str:
    jinja2 = pytest.importorskip("jinja2")

    environment = jinja2.Environment()
    environment.globals["config"] = lambda **_kwargs: ""
    environment.globals["ref"] = lambda ref_name: f'"{ref_name}"'

    return (
        environment.from_string((INTERMEDIATE_DIR / f"{model_name}.sql").read_text())
        .render()
        .strip()
    )


def _write_raw_fixtures_with_misaligned_financial_versions(
    raw_zone_path: Path, tmp_path: Path
) -> None:
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )

    for asset in TUSHARE_ASSETS:
        table = _sample_table(asset)
        if asset.dataset == "income":
            table = pa.concat_tables(
                [
                    _sample_table_with_values(
                        asset,
                        {
                            "ann_date": "20260414",
                            "f_ann_date": "20260414",
                            "update_flag": "0",
                            "total_revenue": Decimal("1.000000000000000000"),
                        },
                    ),
                    _sample_table_with_values(
                        asset,
                        {
                            "ann_date": "20260416",
                            "f_ann_date": "20260416",
                            "update_flag": "1",
                            "total_revenue": Decimal("2.000000000000000000"),
                        },
                    ),
                ]
            )
        elif asset.dataset == "balancesheet":
            table = _sample_table_with_values(
                asset,
                {
                    "ann_date": "20260414",
                    "f_ann_date": None,
                    "update_flag": None,
                    "total_assets": Decimal("10.000000000000000000"),
                },
            )
        elif asset.dataset == "cashflow":
            table = _sample_table_with_values(
                asset,
                {
                    "ann_date": "20260414",
                    "f_ann_date": "20260414",
                    "update_flag": "0",
                    "n_cashflow_act": Decimal("20.000000000000000000"),
                },
            )
        elif asset.dataset == "fina_indicator":
            table = _sample_table_with_values(
                asset,
                {
                    "ann_date": "20260414",
                    "f_ann_date": "20260414",
                    "update_flag": "0",
                    "roe": Decimal("30.000000000000000000"),
                },
            )

        artifact = writer.write_arrow(
            "tushare",
            asset.dataset,
            date(2026, 4, 15),
            str(uuid4()),
            table,
        )
        manifest = json.loads((artifact.path.parent / "_manifest.json").read_text(encoding="utf-8"))
        assert manifest["artifacts"][0]["row_count"] == table.num_rows
