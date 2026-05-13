from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.dbt.test_marts_models import _create_mart_table


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
MARTS_DERIVATIONS_DIR = DBT_PROJECT_DIR / "models" / "marts_derivations"
MARTS_DERIVATION_LINEAGE_DIR = DBT_PROJECT_DIR / "models" / "marts_derivation_lineage"
TEST_STOCK_A = "TESTSTKA.SZ"
TEST_STOCK_B = "TESTSTKB.SZ"
TEST_STOCK_C = "TESTSTKC.SZ"


def test_top_holder_qoq_change_uses_canonical_lag_and_pairs_lineage() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        _create_holding_fixture_tables(connection)
        _insert_holding_row(
            connection,
            "top_holder",
            "holder-a",
            TEST_STOCK_A,
            date(2025, 12, 31),
            date(2026, 1, 15),
            90,
            9,
        )
        _insert_holding_row(
            connection,
            "top_holder",
            "holder-a",
            TEST_STOCK_A,
            date(2025, 12, 31),
            date(2026, 1, 31),
            100,
            10,
        )
        _insert_holding_row(
            connection,
            "top_holder",
            "holder-a",
            TEST_STOCK_A,
            date(2026, 3, 31),
            date(2026, 4, 30),
            125,
            12,
        )

        _create_mart_table(
            connection,
            "mart_deriv_top_holder_qoq_change",
            MARTS_DERIVATIONS_DIR,
        )
        _create_mart_table(
            connection,
            "mart_deriv_lineage_top_holder_qoq_change",
            MARTS_DERIVATION_LINEAGE_DIR,
        )

        qoq_row = connection.execute(
            """
            select
                previous_report_date,
                previous_announced_date,
                holding_amount_delta,
                holding_amount_delta_pct,
                holding_ratio_delta
            from mart_deriv_top_holder_qoq_change
            where report_date = date '2026-03-31'
            """
        ).fetchone()
        qoq_rows = connection.execute(
            """
            select report_date, announced_date, previous_report_date
            from mart_deriv_top_holder_qoq_change
            order by report_date, announced_date
            """
        ).fetchall()
        key_diff_count = _key_diff_count(
            connection,
            "mart_deriv_top_holder_qoq_change",
            "mart_deriv_lineage_top_holder_qoq_change",
            ["mart_key"],
        )
        missing_columns = _missing_columns(
            connection,
            "mart_deriv_top_holder_qoq_change",
            {"mart_key"},
        ) | _missing_columns(
            connection,
            "mart_deriv_lineage_top_holder_qoq_change",
            {
                "mart_key",
                "dataset",
                "snapshot_id",
                "as_of_date",
                "source_mart",
                "source_window_start_date",
                "source_window_end_date",
                "source_interface_ids",
                "source_row_count",
                "source_lineage_row_count",
                "source_lineage_summary",
                "source_run_ids",
                "raw_loaded_at_min",
                "raw_loaded_at_max",
            },
        )
        lineage_row = connection.execute(
            """
            select source_mart, source_interface_ids, source_row_count
            from mart_deriv_lineage_top_holder_qoq_change
            where report_date = date '2026-03-31'
            """
        ).fetchone()
    finally:
        connection.close()

    assert qoq_row == (date(2025, 12, 31), date(2026, 1, 31), 25, 0.25, 2)
    assert qoq_rows == [
        (date(2025, 12, 31), date(2026, 1, 31), None),
        (date(2026, 3, 31), date(2026, 4, 30), date(2025, 12, 31)),
    ]
    assert key_diff_count == 0
    assert missing_columns == set()
    assert lineage_row == ("mart_fact_holding_position_v2", "top10_holders", 2)


def test_fund_co_holding_orders_pairs_and_dedupes_inverse_pairs() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        _create_holding_fixture_tables(connection)
        for holder_id, security_id in [
            ("fund-1", TEST_STOCK_A),
            ("fund-1", TEST_STOCK_B),
            ("fund-1", TEST_STOCK_C),
            ("fund-2", TEST_STOCK_A),
            ("fund-2", TEST_STOCK_B),
        ]:
            _insert_holding_row(
                connection,
                "fund_portfolio",
                holder_id,
                security_id,
                date(2026, 3, 31),
                date(2026, 4, 30),
                10,
                1,
            )

        _create_mart_table(
            connection,
            "mart_deriv_fund_co_holding",
            MARTS_DERIVATIONS_DIR,
        )
        _create_mart_table(
            connection,
            "mart_deriv_lineage_fund_co_holding",
            MARTS_DERIVATION_LINEAGE_DIR,
        )

        pair_rows = connection.execute(
            """
            select
                security_id_left,
                security_id_right,
                co_holding_fund_count,
                security_left_fund_count,
                security_right_fund_count,
                round(jaccard_score, 6),
                latest_announced_date
            from mart_deriv_fund_co_holding
            order by security_id_left, security_id_right
            """
        ).fetchall()
        inverse_pair_count = connection.execute(
            """
            select count(*)
            from mart_deriv_fund_co_holding
            where security_id_left >= security_id_right
            """
        ).fetchone()[0]
        key_diff_count = _key_diff_count(
            connection,
            "mart_deriv_fund_co_holding",
            "mart_deriv_lineage_fund_co_holding",
            ["mart_key"],
        )
        missing_columns = _missing_columns(
            connection,
            "mart_deriv_fund_co_holding",
            {"mart_key", "row_id", "evidence_ref"},
        ) | _missing_columns(
            connection,
            "mart_deriv_lineage_fund_co_holding",
            {"mart_key", "dataset", "snapshot_id", "as_of_date"},
        )
    finally:
        connection.close()

    assert pair_rows == [
        (TEST_STOCK_A, TEST_STOCK_B, 2, 2, 2, 1.0, date(2026, 4, 30)),
        (TEST_STOCK_A, TEST_STOCK_C, 1, 2, 1, 0.5, date(2026, 4, 30)),
        (TEST_STOCK_B, TEST_STOCK_C, 1, 2, 1, 0.5, date(2026, 4, 30)),
    ]
    assert inverse_pair_count == 0
    assert key_diff_count == 0
    assert missing_columns == set()


def test_fund_co_holding_lineage_only_counts_contributing_pair_rows() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        _create_holding_fixture_tables(connection)
        for holder_id, security_id in [
            ("fund-1", TEST_STOCK_A),
            ("fund-1", TEST_STOCK_B),
            ("fund-2", TEST_STOCK_A),
            ("fund-2", TEST_STOCK_B),
        ]:
            _insert_holding_row(
                connection,
                "fund_portfolio",
                holder_id,
                security_id,
                date(2026, 3, 31),
                date(2026, 4, 30),
                10,
                1,
                source_run_id=f"run-{holder_id}-{security_id}",
            )
        _insert_holding_row(
            connection,
            "fund_portfolio",
            "fund-side-only",
            TEST_STOCK_A,
            date(2026, 3, 31),
            date(2026, 4, 30),
            10,
            1,
            source_run_id="run-side-only",
        )

        _create_mart_table(
            connection,
            "mart_deriv_fund_co_holding",
            MARTS_DERIVATIONS_DIR,
        )
        _create_mart_table(
            connection,
            "mart_deriv_lineage_fund_co_holding",
            MARTS_DERIVATION_LINEAGE_DIR,
        )

        lineage_row = connection.execute(
            """
            select source_row_count, source_lineage_row_count, source_run_ids
            from mart_deriv_lineage_fund_co_holding
            where report_date = date '2026-03-31'
              and security_id_left = ?
              and security_id_right = ?
            """,
            [TEST_STOCK_A, TEST_STOCK_B],
        ).fetchone()
    finally:
        connection.close()

    assert lineage_row[0:2] == (4, 4)
    assert set(lineage_row[2].split(",")) == {
        f"run-fund-1-{TEST_STOCK_A}",
        f"run-fund-1-{TEST_STOCK_B}",
        f"run-fund-2-{TEST_STOCK_A}",
        f"run-fund-2-{TEST_STOCK_B}",
    }


def test_northbound_z_score_filters_rows_when_window_stddev_is_null_or_zero() -> None:
    duckdb = pytest.importorskip("duckdb")

    connection = duckdb.connect(":memory:")
    try:
        _create_holding_fixture_tables(connection)
        for report_date, holding_ratio in [
            (date(2026, 4, 1), 1),
            (date(2026, 4, 2), 2),
            (date(2026, 4, 3), 3),
        ]:
            _insert_holding_row(
                connection,
                "northbound_hold",
                "northbound:sh",
                TEST_STOCK_A,
                report_date,
                report_date,
                100,
                holding_ratio,
            )

        _create_mart_table(
            connection,
            "mart_deriv_northbound_holding_z_score",
            MARTS_DERIVATIONS_DIR,
        )
        _create_mart_table(
            connection,
            "mart_deriv_lineage_northbound_holding_z_score",
            MARTS_DERIVATION_LINEAGE_DIR,
        )

        amount_row_count = connection.execute(
            """
            select count(*)
            from mart_deriv_northbound_holding_z_score
            where z_score_metric = 'holding_amount'
            """
        ).fetchone()[0]
        ratio_first_row_count = connection.execute(
            """
            select count(*)
            from mart_deriv_northbound_holding_z_score
            where report_date = date '2026-04-01'
              and z_score_metric = 'holding_ratio'
            """
        ).fetchone()[0]
        ratio_latest_z_score = connection.execute(
            """
            select observation_count, round(metric_stddev, 6), round(metric_z_score, 6)
            from mart_deriv_northbound_holding_z_score
            where report_date = date '2026-04-03'
              and z_score_metric = 'holding_ratio'
            """
        ).fetchone()
        key_diff_count = _key_diff_count(
            connection,
            "mart_deriv_northbound_holding_z_score",
            "mart_deriv_lineage_northbound_holding_z_score",
            ["mart_key"],
        )
        missing_columns = _missing_columns(
            connection,
            "mart_deriv_northbound_holding_z_score",
            {"mart_key", "row_id", "evidence_ref"},
        ) | _missing_columns(
            connection,
            "mart_deriv_lineage_northbound_holding_z_score",
            {"mart_key", "dataset", "snapshot_id", "as_of_date"},
        )
    finally:
        connection.close()

    assert amount_row_count == 0
    assert ratio_first_row_count == 0
    assert ratio_latest_z_score == (3, 1.0, 1.0)
    assert key_diff_count == 0
    assert missing_columns == set()


def _create_holding_fixture_tables(connection: Any) -> None:
    connection.execute(
        """
        create table mart_fact_holding_position_v2(
            holding_source varchar,
            holder_id varchar,
            holder_name varchar,
            holder_type varchar,
            security_id varchar,
            report_date date,
            announced_date date,
            holding_amount decimal(38, 18),
            holding_ratio decimal(38, 18),
            holding_float_ratio decimal(38, 18),
            holding_change decimal(38, 18),
            market_value decimal(38, 18),
            exchange varchar
        )
        """
    )
    connection.execute(
        """
        create table mart_lineage_fact_holding_position(
            holding_source varchar,
            holder_id varchar,
            security_id varchar,
            report_date date,
            announced_date date,
            source_provider varchar,
            source_interface_id varchar,
            source_run_id varchar,
            raw_loaded_at timestamp
        )
        """
    )


def _insert_holding_row(
    connection: Any,
    holding_source: str,
    holder_id: str,
    security_id: str,
    report_date: date,
    announced_date: date,
    holding_amount: int,
    holding_ratio: int,
    source_run_id: str | None = None,
) -> None:
    source_interface_id = {
        "top_holder": "top10_holders",
        "top_float_holder": "top10_floatholders",
        "fund_portfolio": "fund_portfolio",
        "northbound_hold": "hsgt_hold_top10",
    }[holding_source]
    connection.execute(
        """
        insert into mart_fact_holding_position_v2 values (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            holding_source,
            holder_id,
            holder_id,
            "fund" if holding_source == "fund_portfolio" else "holder",
            security_id,
            report_date,
            announced_date,
            holding_amount,
            holding_ratio,
            holding_ratio,
            None,
            None,
            None,
        ],
    )
    connection.execute(
        """
        insert into mart_lineage_fact_holding_position values (
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            holding_source,
            holder_id,
            security_id,
            report_date,
            announced_date,
            "fixture",
            source_interface_id,
            source_run_id or f"run-{source_interface_id}",
            datetime(2026, 5, 1, 0, 0, 0),
        ],
    )


def _key_diff_count(
    connection: Any,
    business_table: str,
    lineage_table: str,
    key_columns: list[str],
) -> int:
    key_select = ", ".join(key_columns)
    return connection.execute(
        f"""
        select count(*)
        from (
            select {key_select} from {business_table}
            except
            select {key_select} from {lineage_table}

            union all

            select {key_select} from {lineage_table}
            except
            select {key_select} from {business_table}
        )
        """
    ).fetchone()[0]


def _missing_columns(
    connection: Any,
    table_name: str,
    expected_columns: set[str],
) -> set[str]:
    actual_columns = {
        row[1] for row in connection.execute(f"pragma table_info('{table_name}')").fetchall()
    }
    return expected_columns - actual_columns
