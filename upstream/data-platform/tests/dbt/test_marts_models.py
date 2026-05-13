from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pytest

from data_platform.raw import RawWriter
from tests.dbt.test_intermediate_models import (
    _create_all_intermediate_tables,
    _create_all_staging_views,
)
from tests.dbt.test_tushare_staging_models import (
    _asset_by_dataset,
    _run_dbt_wrapper,
    _sample_table_with_values,
    _write_all_tushare_raw_fixtures,
    _write_duckdb_only_profile,
    require_working_dbt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
MARTS_V2_DIR = DBT_PROJECT_DIR / "models" / "marts_v2"
MARTS_LINEAGE_DIR = DBT_PROJECT_DIR / "models" / "marts_lineage"
TEST_STOCK_CODE = "TESTSTK.SZ"



def test_event_v2_and_lineage_marts_preserve_namechange_fixture(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        _create_all_intermediate_tables(connection)

        expected_namechange_row = connection.execute(
            """
            select ts_code, start_date
            from stg_namechange
            """
        ).fetchone()
        int_namechange_count = connection.execute(
            """
            select count(*)
            from int_event_timeline
            where event_type = 'name_change'
              and source_interface_id = 'namechange'
            """
        ).fetchone()[0]

        _create_mart_table(connection, "mart_fact_event_v2", MARTS_V2_DIR)
        _create_mart_table(connection, "mart_lineage_fact_event", MARTS_LINEAGE_DIR)

        v2_event_types = {
            row[0]
            for row in connection.execute(
                """
                select distinct event_type
                from mart_fact_event_v2
                """
            ).fetchall()
        }
        lineage_source_interface_ids = {
            row[0]
            for row in connection.execute(
                """
                select distinct source_interface_id
                from mart_lineage_fact_event
                """
            ).fetchall()
        }
        v2_columns = _table_columns(connection, "mart_fact_event_v2")
        lineage_columns = _table_columns(connection, "mart_lineage_fact_event")
        v2_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_fact_event_v2
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
        lineage_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_lineage_fact_event
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
        v2_namechange_row = connection.execute(
            """
            select entity_id, event_date
            from mart_fact_event_v2
            where event_type = 'name_change'
            """
        ).fetchone()
        lineage_namechange_row = connection.execute(
            """
            select entity_id, event_date, source_interface_id
            from mart_lineage_fact_event
            where event_type = 'name_change'
            """
        ).fetchone()
    finally:
        connection.close()

    lineage_column_names = {
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    }

    assert int_namechange_count == 1
    assert "name_change" in v2_event_types
    assert "namechange" in lineage_source_interface_ids
    assert lineage_column_names.isdisjoint(v2_columns)
    assert lineage_column_names.issubset(lineage_columns)
    assert v2_pk_rows == lineage_pk_rows
    assert v2_namechange_row == expected_namechange_row
    assert lineage_namechange_row == (*expected_namechange_row, "namechange")


def test_event_v2_and_lineage_marts_preserve_block_trade_fixture(tmp_path: Path) -> None:
    """M1.8 — block_trade flows through int_event_timeline → mart_fact_event_v2
    + mart_lineage_fact_event with v2/lineage canonical PK parity.

    The intermediate uniqueness contract was widened in M1.8 to include
    `summary` (encoding buyer/seller/price/vol/amount), allowing intra-day
    block_trade rows to flow through. Row identity is enforced here at the
    mart-level event_key + canonical PK parity (v2_pk_rows == lineage_pk_rows
    below), and at writer-side validation."""

    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)
    _write_same_day_block_trade_rows(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        _create_all_intermediate_tables(connection)

        expected_block_trade_row = connection.execute(
            """
            select ts_code, trade_date
            from stg_block_trade
            order by buyer, seller
            """
        ).fetchall()
        int_block_trade_count = connection.execute(
            """
            select count(*)
            from int_event_timeline
            where event_type = 'block_trade'
              and source_interface_id = 'block_trade'
            """
        ).fetchone()[0]
        int_block_trade_duplicate_count = connection.execute(
            """
            select count(*)
            from (
                select event_type, ts_code, event_date, title, related_date, reference_url
                from int_event_timeline
                where event_type = 'block_trade'
                group by event_type, ts_code, event_date, title, related_date, reference_url
                having count(*) > 1
            )
            """
        ).fetchone()[0]
        int_block_trade_summary_count = connection.execute(
            """
            select count(distinct summary)
            from int_event_timeline
            where event_type = 'block_trade'
            """
        ).fetchone()[0]

        _create_mart_table(connection, "mart_fact_event_v2", MARTS_V2_DIR)
        _create_mart_table(connection, "mart_lineage_fact_event", MARTS_LINEAGE_DIR)

        v2_event_types = {
            row[0]
            for row in connection.execute(
                """
                select distinct event_type
                from mart_fact_event_v2
                """
            ).fetchall()
        }
        lineage_source_interface_ids = {
            row[0]
            for row in connection.execute(
                """
                select distinct source_interface_id
                from mart_lineage_fact_event
                """
            ).fetchall()
        }
        v2_columns = _table_columns(connection, "mart_fact_event_v2")
        lineage_columns = _table_columns(connection, "mart_lineage_fact_event")
        v2_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_fact_event_v2
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
        lineage_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_lineage_fact_event
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
        v2_block_trade_row = connection.execute(
            """
            select entity_id, event_date
            from mart_fact_event_v2
            where event_type = 'block_trade'
            order by event_key
            """
        ).fetchall()
        lineage_block_trade_row = connection.execute(
            """
            select entity_id, event_date, source_interface_id
            from mart_lineage_fact_event
            where event_type = 'block_trade'
            order by event_key
            """
        ).fetchall()
        v2_block_trade_event_keys = connection.execute(
            """
            select count(distinct event_key)
            from mart_fact_event_v2
            where event_type = 'block_trade'
            """
        ).fetchone()[0]
    finally:
        connection.close()

    lineage_column_names = {
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    }

    assert int_block_trade_count == 2
    assert int_block_trade_duplicate_count == 1
    assert int_block_trade_summary_count == 2
    assert "block_trade" in v2_event_types
    assert "block_trade" in lineage_source_interface_ids
    assert lineage_column_names.isdisjoint(v2_columns)
    assert lineage_column_names.issubset(lineage_columns)
    assert v2_pk_rows == lineage_pk_rows
    assert v2_block_trade_event_keys == 2
    assert v2_block_trade_row == expected_block_trade_row
    assert lineage_block_trade_row == [
        (*row, "block_trade") for row in expected_block_trade_row
    ]


def _write_same_day_block_trade_rows(raw_zone_path: Path, tmp_path: Path) -> None:
    asset = _asset_by_dataset("block_trade")
    block_trade_rows = pa.concat_tables(
        [
            _sample_table_with_values(
                asset,
                {
                    "ts_code": TEST_STOCK_CODE,
                    "trade_date": "20260415",
                    "buyer": "buyer-a",
                    "seller": "seller-a",
                    "price": "10.10",
                    "vol": "100",
                    "amount": "1010",
                },
            ),
            _sample_table_with_values(
                asset,
                {
                    "ts_code": TEST_STOCK_CODE,
                    "trade_date": "20260415",
                    "buyer": "buyer-b",
                    "seller": "seller-b",
                    "price": "10.20",
                    "vol": "200",
                    "amount": "2040",
                },
            ),
        ]
    )
    RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    ).write_arrow(
        "tushare",
        "block_trade",
        date(2026, 4, 15),
        str(uuid4()),
        block_trade_rows,
    )


# M1.13 expansion (precondition 9 closure) — 8 parity tests mirroring
# `test_event_v2_and_lineage_marts_preserve_block_trade_fixture`.
# Each test writes 1 raw row (the M1.11 sign-off rows) for one
# candidate event_timeline source, materializes int_event_timeline →
# mart_fact_event_v2 + mart_lineage_fact_event, then asserts:
#   - int_event_timeline carries the correct event_type literal +
#     source_interface_id
#   - mart_fact_event_v2.event_type contains the new value
#   - mart_lineage_fact_event.source_interface_id contains the new
#     value
#   - lineage columns are present only on the lineage mart
#   - canonical PK (event_type, entity_id, event_date, event_key) is
#     identical between v2 and lineage marts (writer-side pairing
#     guarantee).


def _assert_event_v2_and_lineage_pair_preserved(
    tmp_path: Path,
    *,
    expected_event_type: str,
    expected_source_interface_id: str,
) -> None:
    """Run the materialization + parity assertions for one M1.13 source."""

    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        _create_all_intermediate_tables(connection)

        int_count = connection.execute(
            f"""
            select count(*)
            from int_event_timeline
            where event_type = '{expected_event_type}'
              and source_interface_id = '{expected_source_interface_id}'
            """
        ).fetchone()[0]

        _create_mart_table(connection, "mart_fact_event_v2", MARTS_V2_DIR)
        _create_mart_table(connection, "mart_lineage_fact_event", MARTS_LINEAGE_DIR)

        v2_event_types = {
            row[0]
            for row in connection.execute(
                "select distinct event_type from mart_fact_event_v2"
            ).fetchall()
        }
        lineage_source_interface_ids = {
            row[0]
            for row in connection.execute(
                "select distinct source_interface_id from mart_lineage_fact_event"
            ).fetchall()
        }
        v2_columns = _table_columns(connection, "mart_fact_event_v2")
        lineage_columns = _table_columns(connection, "mart_lineage_fact_event")
        v2_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_fact_event_v2
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
        lineage_pk_rows = connection.execute(
            """
            select event_type, entity_id, event_date, event_key
            from mart_lineage_fact_event
            order by event_type, entity_id, event_date, event_key
            """
        ).fetchall()
    finally:
        connection.close()

    lineage_column_names = {
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    }

    assert int_count == 1
    assert expected_event_type in v2_event_types
    assert expected_source_interface_id in lineage_source_interface_ids
    assert lineage_column_names.isdisjoint(v2_columns)
    assert lineage_column_names.issubset(lineage_columns)
    assert v2_pk_rows == lineage_pk_rows


def test_event_v2_and_lineage_marts_preserve_pledge_stat_fixture(tmp_path: Path) -> None:
    """M1.13 — pledge_stat flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="pledge_summary",
        expected_source_interface_id="pledge_stat",
    )


def test_event_v2_and_lineage_marts_preserve_pledge_detail_fixture(tmp_path: Path) -> None:
    """M1.13 — pledge_detail flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="pledge_event",
        expected_source_interface_id="pledge_detail",
    )


def test_event_v2_and_lineage_marts_preserve_repurchase_fixture(tmp_path: Path) -> None:
    """M1.13 — repurchase flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="share_repurchase",
        expected_source_interface_id="repurchase",
    )


def test_event_v2_and_lineage_marts_preserve_stk_holdertrade_fixture(tmp_path: Path) -> None:
    """M1.13 — stk_holdertrade flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="shareholder_trade",
        expected_source_interface_id="stk_holdertrade",
    )


def test_event_v2_and_lineage_marts_preserve_stk_surv_fixture(tmp_path: Path) -> None:
    """M1.13 — stk_surv flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="institutional_survey",
        expected_source_interface_id="stk_surv",
    )


def test_event_v2_and_lineage_marts_preserve_limit_list_ths_fixture(tmp_path: Path) -> None:
    """M1.13 — limit_list_ths flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="price_limit_status",
        expected_source_interface_id="limit_list_ths",
    )


def test_event_v2_and_lineage_marts_preserve_limit_list_d_fixture(tmp_path: Path) -> None:
    """M1.13 — limit_list_d flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="price_limit_event",
        expected_source_interface_id="limit_list_d",
    )


def test_event_v2_and_lineage_marts_preserve_hm_detail_fixture(tmp_path: Path) -> None:
    """M1.13 — hm_detail flows through int_event_timeline → marts."""
    _assert_event_v2_and_lineage_pair_preserved(
        tmp_path,
        expected_event_type="hot_money_trade",
        expected_source_interface_id="hm_detail",
    )

def test_holdings_marts_preserve_promoted_holdings_fixtures(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        _create_all_staging_views(connection, raw_zone_path)
        _create_mart_table(connection, "mart_fact_holding_position_v2", MARTS_V2_DIR)
        _create_mart_table(connection, "mart_fact_northbound_turnover_v2", MARTS_V2_DIR)
        _create_mart_table(
            connection,
            "mart_lineage_fact_holding_position",
            MARTS_LINEAGE_DIR,
        )
        _create_mart_table(
            connection,
            "mart_lineage_fact_northbound_turnover",
            MARTS_LINEAGE_DIR,
        )
        expected_hsgt_top10_security_id = connection.execute(
            "select ts_code from stg_hsgt_top10"
        ).fetchone()[0]
        expected_hsgt_hold_security_id = connection.execute(
            "select ts_code from stg_hsgt_hold_top10"
        ).fetchone()[0]

        holding_sources = {
            row[0]
            for row in connection.execute(
                """
                select distinct holding_source
                from mart_fact_holding_position_v2
                """
            ).fetchall()
        }
        holding_duplicate_count = connection.execute(
            """
            select count(*)
            from (
                select holding_source, holder_id, security_id, report_date, announced_date
                from mart_fact_holding_position_v2
                group by holding_source, holder_id, security_id, report_date, announced_date
                having count(*) > 1
            )
            """
        ).fetchone()[0]
        holding_position_duplicate_count = connection.execute(
            """
            select count(*)
            from (
                select position_id
                from mart_fact_holding_position_v2
                group by position_id
                having count(*) > 1
            )
            """
        ).fetchone()[0]
        holding_columns = _table_columns(connection, "mart_fact_holding_position_v2")
        northbound_row = connection.execute(
            """
            select security_id, trade_date, market_type, rank
            from mart_fact_northbound_turnover_v2
            """
        ).fetchone()
        holding_lineage_sources = {
            row[0]
            for row in connection.execute(
                """
                select distinct source_interface_id
                from mart_lineage_fact_holding_position
                """
            ).fetchall()
        }
        northbound_lineage_row = connection.execute(
            """
            select security_id, trade_date, market_type, rank, source_interface_id
            from mart_lineage_fact_northbound_turnover
            """
        ).fetchone()
    finally:
        connection.close()

    assert holding_sources == {
        "top_holder",
        "top_float_holder",
        "fund_portfolio",
        "northbound_hold",
    }
    assert holding_duplicate_count == 0
    assert holding_position_duplicate_count == 0
    assert {
        "position_id",
        "holder_id",
        "security_id",
        "report_date",
        "holding_ratio",
        "dataset",
        "snapshot_id",
        "as_of_date",
    }.issubset(holding_columns)
    assert northbound_row == (
        expected_hsgt_top10_security_id,
        date(2026, 4, 15),
        "market_type-fixture",
        1,
    )
    assert holding_lineage_sources == {
        "top10_holders",
        "top10_floatholders",
        "fund_portfolio",
        "hsgt_hold_top10",
    }
    assert northbound_lineage_row == (
        expected_hsgt_hold_security_id,
        date(2026, 4, 15),
        "market_type-fixture",
        1,
        "hsgt_top10",
    )


def test_dbt_run_and_test_marts_with_rawwriter_fixture(tmp_path: Path) -> None:
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
            "marts_v2",
            "marts_lineage",
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
            "marts_v2",
            "marts_lineage",
        ],
        env=env,
    )
    assert test_result.returncode == 0, test_result.stdout + test_result.stderr


def _create_mart_table(connection: Any, model_name: str, models_dir: Path) -> None:
    model_sql = _render_mart_model(model_name, models_dir)
    connection.execute(f'create table "{model_name}" as {model_sql}')


def _render_mart_model(model_name: str, models_dir: Path) -> str:
    jinja2 = pytest.importorskip("jinja2")

    environment = jinja2.Environment()
    environment.globals["config"] = lambda **_kwargs: ""
    environment.globals["ref"] = lambda ref_name: f'"{ref_name}"'

    return (
        environment.from_string((models_dir / f"{model_name}.sql").read_text())
        .render()
        .strip()
    )


def _table_columns(connection: Any, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"pragma table_info('{table_name}')").fetchall()}


def _schema_columns(model: dict[str, Any]) -> set[str]:
    return {column["name"] for column in model.get("columns", [])}


def _schema_column(model: dict[str, Any], column_name: str) -> dict[str, Any]:
    for column in model.get("columns", []):
        if column["name"] == column_name:
            return column
    raise AssertionError(f"missing schema column: {column_name}")


def _test_names(column: dict[str, Any]) -> set[str]:
    return {_model_test_name(test) for test in column.get("tests", [])}


def _model_test_name(test: str | dict[str, Any]) -> str:
    if isinstance(test, str):
        return test
    return next(iter(test))


def _relationship_test(column: dict[str, Any]) -> dict[str, Any]:
    for test in column.get("tests", []):
        if isinstance(test, dict) and "relationships" in test:
            return test["relationships"]
    raise AssertionError(f"missing relationship test for column: {column['name']}")
