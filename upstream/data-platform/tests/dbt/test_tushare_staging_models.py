from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from uuid import UUID, uuid4

import pyarrow as pa
import pytest

from data_platform.adapters.tushare import TUSHARE_ASSETS, TushareAdapter
from data_platform.adapters.tushare.adapter import _IDENTITY_FIELDS_BY_DATASET
from data_platform.adapters.tushare.assets import (
    ALLOW_NULL_IDENTITY_METADATA_KEY,
    ALLOW_NULL_IDENTITY_METADATA_VALUE,
    FINANCIAL_DATASET_FIELDS,
    FINANCIAL_VERSION_FIELDS,
)
from data_platform.raw import RawWriter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
STAGING_DIR = DBT_PROJECT_DIR / "models" / "staging"
STAGING_SOURCES_PATH = STAGING_DIR / "_sources.yml"
STAGING_SCHEMA_PATH = STAGING_DIR / "_schema.yml"
DATE_FIELD_NAMES = {
    "actual_date",
    "ann_date",
    "base_date",
    "cal_date",
    "delist_date",
    "div_listdate",
    "end_date",
    "ex_date",
    "exp_date",
    "f_ann_date",
    "first_ann_date",
    "float_date",
    "imp_ann_date",
    "in_date",
    "list_date",
    "modify_date",
    "out_date",
    "pay_date",
    "pre_date",
    "pretrade_date",
    "record_date",
    # M1.13 expansion (precondition 9 closure) — release_date
    # (pledge_detail) and surv_date (stk_surv) are also YYYYMMDD strings.
    "release_date",
    "setup_date",
    "start_date",
    "surv_date",
    "trade_date",
}
PRICE_DATASETS = {"daily", "weekly", "monthly"}
PRICE_NUMERIC_FIELD_NAMES = {
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
}
DAILY_BASIC_NUMERIC_FIELD_NAMES = {
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
}
STK_LIMIT_NUMERIC_FIELD_NAMES = {"up_limit", "down_limit"}
MONEYFLOW_NUMERIC_FIELD_NAMES = {
    "buy_sm_vol",
    "buy_sm_amount",
    "sell_sm_vol",
    "sell_sm_amount",
    "buy_md_vol",
    "buy_md_amount",
    "sell_md_vol",
    "sell_md_amount",
    "buy_lg_vol",
    "buy_lg_amount",
    "sell_lg_vol",
    "sell_lg_amount",
    "buy_elg_vol",
    "buy_elg_amount",
    "sell_elg_vol",
    "sell_elg_amount",
    "net_mf_vol",
    "net_mf_amount",
}
FORECAST_NUMERIC_FIELD_NAMES = {
    "p_change_min",
    "p_change_max",
    "net_profit_min",
    "net_profit_max",
    "last_parent_net",
}
# M1.13 expansion (precondition 9 closure) — numeric field names that
# need to cast cleanly through the staging cast templates for each of
# the 8 promoted candidate event_timeline sources. Identity fields
# stay strings (in_de, is_release, proc, holder_type, hm_name,
# limit_type, status, tag, limit, etc.) — they're never cast to numeric
# at staging.
PLEDGE_STAT_NUMERIC_FIELD_NAMES = {
    "pledge_count",
    "unrest_pledge",
    "rest_pledge",
    "total_share",
    "pledge_ratio",
}
PLEDGE_DETAIL_NUMERIC_FIELD_NAMES = {
    "pledge_amount",
    "holding_amount",
    "pledged_amount",
    "p_total_ratio",
    "h_total_ratio",
}
REPURCHASE_NUMERIC_FIELD_NAMES = {
    "vol",
    "amount",
    "high_limit",
    "low_limit",
}
STK_HOLDERTRADE_NUMERIC_FIELD_NAMES = {
    "change_vol",
    "change_ratio",
    "after_share",
    "after_ratio",
    "avg_price",
    "total_share",
}
LIMIT_LIST_THS_NUMERIC_FIELD_NAMES = {
    "price",
    "pct_chg",
    "limit_order",
    "limit_amount",
    "turnover_rate",
    "free_float",
    "limit_up_suc_rate",
}
LIMIT_LIST_D_NUMERIC_FIELD_NAMES = {
    "close",
    "pct_chg",
    "amount",
    "limit_amount",
    "float_mv",
    "total_mv",
    "turnover_ratio",
    "fd_amount",
}
HM_DETAIL_NUMERIC_FIELD_NAMES = {
    "buy_amount",
    "sell_amount",
    "net_amount",
}
TOP10_HOLDERS_NUMERIC_FIELD_NAMES = {
    "hold_amount",
    "hold_ratio",
    "hold_float_ratio",
    "hold_change",
}
FUND_PORTFOLIO_NUMERIC_FIELD_NAMES = {
    "mkv",
    "amount",
    "stk_mkv_ratio",
    "stk_float_ratio",
}
HSGT_TOP10_NUMERIC_FIELD_NAMES = {
    "close",
    "change",
    "rank",
    "amount",
    "net_amount",
    "buy",
    "sell",
}
HSGT_HOLD_TOP10_NUMERIC_FIELD_NAMES = {
    "vol",
    "ratio",
}
FIXTURE_DECIMAL_STRING = "1.123456789012345678"


def test_adapter_declared_staging_models_are_present() -> None:
    adapter = TushareAdapter(token="test-token")
    expected_model_names = [f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS]

    assert adapter.get_staging_dbt_models() == expected_model_names
    for model_name in expected_model_names:
        assert (STAGING_DIR / f"{model_name}.sql").exists()


def test_staging_sql_uses_raw_manifest_only() -> None:
    macro_sql = (DBT_PROJECT_DIR / "macros" / "stg_latest_raw.sql").read_text()

    assert "read_json_auto" in macro_sql
    assert "read_parquet" in macro_sql
    assert "hive_partitioning=1" in macro_sql
    assert "filename=1" in macro_sql
    assert "union_by_name=1" in macro_sql
    assert "union all by name" in macro_sql
    assert 'partition_mode="partitioned"' in macro_sql
    assert "row_number() over" in macro_sql
    assert "partition by partition_date" in macro_sql
    assert "order by raw_loaded_at desc, partition_date desc, source_run_id desc" in macro_sql
    assert "select *" not in macro_sql.lower()

    static_datasets = {asset.dataset for asset in TUSHARE_ASSETS if asset.partition == "static"}
    for path in sorted(STAGING_DIR.glob("stg_*.sql")):
        dataset = path.stem.removeprefix("stg_")
        model_sql = path.read_text()
        lowered_sql = model_sql.lower()
        assert "{{ stg_latest_raw(" in model_sql
        if dataset in static_datasets:
            assert '"static"' in model_sql
        assert "select *" not in lowered_sql
        assert "canonical." not in lowered_sql
        assert "formal." not in lowered_sql
        assert "iceberg_scan" not in lowered_sql
        assert "current_timestamp" not in lowered_sql


def test_staging_yml_declares_each_tushare_model_and_basic_tests() -> None:
    yaml = pytest.importorskip("yaml")

    parsed_sources = yaml.safe_load(STAGING_SOURCES_PATH.read_text())
    parsed_schema = yaml.safe_load(STAGING_SCHEMA_PATH.read_text())
    source_tables = {
        table["name"]
        for source in parsed_sources["sources"]
        if source["name"] == "raw"
        for table in source["tables"]
    }
    models_by_name = {model["name"]: model for model in parsed_schema["models"]}

    for asset in TUSHARE_ASSETS:
        model_name = f"stg_{asset.dataset}"
        model = models_by_name[model_name]
        columns_by_name = {column["name"]: column for column in model["columns"]}
        identity_fields = _staging_identity_fields(asset.dataset)

        assert f"tushare_{asset.dataset}" in source_tables
        assert set(asset.schema.names).issubset(columns_by_name)
        assert "source_run_id" in columns_by_name
        assert "raw_loaded_at" in columns_by_name

        if len(identity_fields) == 1:
            identity_column = columns_by_name[identity_fields[0]]
            assert "unique" in _test_names(identity_column)
        else:
            assert any(
                _model_test_name(test) == "unique_combination_of_columns"
                and test["unique_combination_of_columns"]["combination_of_columns"]
                == list(identity_fields)
                for test in model.get("tests", [])
            )

        for field_name in identity_fields:
            field = asset.schema.field(field_name)
            if _allows_null_identity(field):
                continue
            assert "not_null" in _test_names(columns_by_name[field_name])

        for field in asset.schema:
            if field.name in DATE_FIELD_NAMES:
                assert "parsable_yyyymmdd_or_date" in _test_names(columns_by_name[field.name])


def test_rawwriter_fixtures_execute_all_staging_models_with_duckdb(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        for asset in TUSHARE_ASSETS:
            model_name = f"stg_{asset.dataset}"
            model_sql = _render_staging_model(model_name, raw_zone_path)
            connection.execute(f'create or replace view "{model_name}" as {model_sql}')

            row_count = connection.execute(f'select count(*) from "{model_name}"').fetchone()[0]
            column_names = [
                row[1]
                for row in connection.execute(f"pragma table_info('{model_name}')").fetchall()
            ]

            assert row_count == 1
            assert column_names == _expected_staging_columns(asset)

        type_row = connection.execute(
            """
            select
                typeof(ts_code),
                typeof(list_date),
                typeof(is_active)
            from stg_stock_basic
            """
        ).fetchone()
        income_type = connection.execute(
            "select typeof(total_revenue) from stg_income"
        ).fetchone()[0]
    finally:
        connection.close()

    assert type_row == ("VARCHAR", "DATE", "BOOLEAN")
    assert income_type == "DECIMAL(38,18)"


def test_index_staging_fixtures_cover_membership_relationships(tmp_path: Path) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    _write_all_tushare_raw_fixtures(raw_zone_path, tmp_path)

    connection = duckdb.connect(":memory:")
    try:
        for model_name in ("stg_index_basic", "stg_index_member", "stg_index_weight"):
            model_sql = _render_staging_model(model_name, raw_zone_path)
            connection.execute(f'create view "{model_name}" as {model_sql}')

        missing_index_rows = connection.execute(
            """
            select 'stg_index_member' as model_name, member.index_code
            from stg_index_member as member
            left join stg_index_basic as index_basic
                on member.index_code = index_basic.ts_code
            where index_basic.ts_code is null
            union all
            select 'stg_index_weight' as model_name, weight.index_code
            from stg_index_weight as weight
            left join stg_index_basic as index_basic
                on weight.index_code = index_basic.ts_code
            where index_basic.ts_code is null
            """
        ).fetchall()
    finally:
        connection.close()

    assert missing_index_rows == []


def test_partitioned_staging_keeps_latest_artifact_per_partition(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    daily_asset = _asset_by_dataset("daily")
    writer.write_arrow(
        "tushare",
        "daily",
        date(2026, 4, 14),
        str(uuid4()),
        _sample_table_with_values(
            daily_asset,
            {"ts_code": "000000.SZ", "trade_date": "20260414"},
        ),
    )
    first_partition_latest = writer.write_arrow(
        "tushare",
        "daily",
        date(2026, 4, 14),
        str(uuid4()),
        _sample_table_with_values(
            daily_asset,
            {"ts_code": "000001.SZ", "trade_date": "20260414"},
        ),
    )
    second_partition = writer.write_arrow(
        "tushare",
        "daily",
        date(2026, 4, 15),
        str(uuid4()),
        _sample_table_with_values(
            daily_asset,
            {"ts_code": "000002.SZ", "trade_date": "20260415"},
        ),
    )

    model_sql = _render_staging_model("stg_daily", raw_zone_path)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f"create view stg_daily as {model_sql}")
        rows = connection.execute(
            """
            select ts_code, trade_date, source_run_id
            from stg_daily
            order by trade_date, ts_code
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        ("000001.SZ", date(2026, 4, 14), first_partition_latest.run_id),
        ("000002.SZ", date(2026, 4, 15), second_partition.run_id),
    ]


@pytest.mark.parametrize("dataset", ("top10_holders", "top10_floatholders"))
def test_request_scoped_top10_staging_keeps_latest_artifact_per_symbol(
    tmp_path: Path,
    dataset: str,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    asset = _asset_by_dataset(dataset)
    partition_date = date(2026, 3, 31)
    request_a = {
        "period": "20260331",
        "ts_code": "000001.SZ",
        "fields": ",".join(asset.schema.names),
    }
    request_b = {
        "period": "20260331",
        "ts_code": "600519.SH",
        "fields": ",".join(asset.schema.names),
    }

    writer.write_arrow(
        "tushare",
        dataset,
        partition_date,
        str(uuid4()),
        _sample_table_with_values(
            asset,
            {
                "ts_code": "000001.SZ",
                "end_date": "20260331",
                "ann_date": "20260430",
                "holder_name": "OLD_SCOPE_A",
            },
        ),
        request_params=request_a,
    )
    latest_a = writer.write_arrow(
        "tushare",
        dataset,
        partition_date,
        str(uuid4()),
        _sample_table_with_values(
            asset,
            {
                "ts_code": "000001.SZ",
                "end_date": "20260331",
                "ann_date": "20260430",
                "holder_name": "LATEST_SCOPE_A",
            },
        ),
        request_params=request_a,
    )
    latest_b = writer.write_arrow(
        "tushare",
        dataset,
        partition_date,
        str(uuid4()),
        _sample_table_with_values(
            asset,
            {
                "ts_code": "600519.SH",
                "end_date": "20260331",
                "ann_date": "20260430",
                "holder_name": "LATEST_SCOPE_B",
            },
        ),
        request_params=request_b,
    )

    model_sql = _render_staging_model(f"stg_{dataset}", raw_zone_path)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f'create view "stg_{dataset}" as {model_sql}')
        rows = connection.execute(
            f"""
            select ts_code, end_date, holder_name, source_run_id
            from "stg_{dataset}"
            order by ts_code
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        ("000001.SZ", partition_date, "LATEST_SCOPE_A", latest_a.run_id),
        ("600519.SH", partition_date, "LATEST_SCOPE_B", latest_b.run_id),
    ]


def test_static_staging_keeps_latest_artifact_globally(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    stock_basic_asset = _asset_by_dataset("stock_basic")
    writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 14),
        str(uuid4()),
        _sample_table_with_values(
            stock_basic_asset,
            {"ts_code": "000001.SZ", "name": "OLD"},
        ),
    )
    latest_artifact = writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 15),
        str(uuid4()),
        _sample_table_with_values(
            stock_basic_asset,
            {"ts_code": "000001.SZ", "name": "NEW"},
        ),
    )

    model_sql = _render_staging_model("stg_stock_basic", raw_zone_path)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f"create view stg_stock_basic as {model_sql}")
        rows = connection.execute(
            """
            select ts_code, name, source_run_id
            from stg_stock_basic
            order by ts_code
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [("000001.SZ", "NEW", latest_artifact.run_id)]


def test_staging_sql_tolerates_schema_drifted_historical_artifact(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 15),
        str(uuid4()),
        pa.table({"ts_code": ["000009.SZ"], "list_date": ["19910403"]}),
    )
    latest_artifact = writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 15),
        str(uuid4()),
        _sample_table(_asset_by_dataset("stock_basic")),
    )

    model_sql = _render_staging_model("stg_stock_basic", raw_zone_path)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f"create view stg_stock_basic as {model_sql}")
        result = connection.execute(
            """
            select count(*), count(distinct source_run_id), min(source_run_id)
            from stg_stock_basic
            """
        ).fetchone()
        duplicate_count = connection.execute(
            """
            select count(*)
            from (
                select ts_code
                from stg_stock_basic
                group by ts_code
                having count(*) > 1
            )
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert result == (1, 1, latest_artifact.run_id)
    assert duplicate_count == 0


def test_staging_sql_tolerates_schema_drifted_latest_artifact(
    tmp_path: Path,
) -> None:
    duckdb = pytest.importorskip("duckdb")

    raw_zone_path = tmp_path / "raw"
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )
    latest_artifact = writer.write_arrow(
        "tushare",
        "stock_basic",
        date(2026, 4, 15),
        str(uuid4()),
        pa.table({"ts_code": ["000009.SZ"], "list_date": ["19910403"]}),
    )

    model_sql = _render_staging_model("stg_stock_basic", raw_zone_path)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f"create view stg_stock_basic as {model_sql}")
        row = connection.execute(
            """
            select ts_code, symbol, name, list_date, is_active, source_run_id
            from stg_stock_basic
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        "000009.SZ",
        None,
        None,
        date(1991, 4, 3),
        None,
        latest_artifact.run_id,
    )


def test_dbt_run_and_test_staging_with_rawwriter_fixture(tmp_path: Path) -> None:
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

    parse_result = _run_dbt_wrapper(
        [
            "parse",
            "--profiles-dir",
            str(profiles_dir),
            "--target-path",
            str(tmp_path / "parse"),
        ],
        env=env,
    )
    assert parse_result.returncode == 0, parse_result.stdout + parse_result.stderr

    # Standard dbt indirect selection can exercise downstream relationship
    # tests, so build descendants instead of changing test selection.
    run_result = _run_dbt_wrapper(
        [
            "run",
            "--profiles-dir",
            str(profiles_dir),
            "--target-path",
            str(tmp_path / "run"),
            "--select",
            "staging+",
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
        ],
        env=env,
    )
    assert test_result.returncode == 0, test_result.stdout + test_result.stderr


def _write_all_tushare_raw_fixtures(raw_zone_path: Path, tmp_path: Path) -> None:
    writer = RawWriter(
        raw_zone_path=raw_zone_path,
        iceberg_warehouse_path=tmp_path / "iceberg" / "warehouse",
    )

    for asset in TUSHARE_ASSETS:
        run_id = str(uuid4())
        artifact = writer.write_arrow(
            "tushare",
            asset.dataset,
            date(2026, 4, 15),
            run_id,
            _sample_table(asset),
        )
        manifest_path = artifact.path.parent / "_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_entry = manifest["artifacts"][0]

        assert manifest["source_id"] == "tushare"
        assert manifest["dataset"] == asset.dataset
        assert artifact_entry["run_id"] == run_id
        assert UUID(artifact_entry["run_id"]).version == 4
        assert artifact_entry["path"] == str(artifact.path)
        assert artifact_entry["row_count"] == 1


def _sample_table(asset: Any) -> pa.Table:
    return _sample_table_with_values(asset, {})


def _sample_table_with_values(asset: Any, overrides: dict[str, Any]) -> pa.Table:
    return pa.table(
        {
            field.name: [overrides.get(field.name, _sample_value(asset.dataset, field))]
            for field in asset.schema
        },
        schema=asset.schema,
    )


def _asset_by_dataset(dataset: str) -> Any:
    for asset in TUSHARE_ASSETS:
        if asset.dataset == dataset:
            return asset
    raise AssertionError(f"unknown Tushare dataset: {dataset}")


def _sample_value(dataset: str, field: pa.Field) -> str | Decimal | None:
    if field.name in DATE_FIELD_NAMES:
        if field.name == "end_date" and dataset in {
            "income",
            "balancesheet",
            "cashflow",
            "fina_indicator",
        }:
            return "20260331"
        if field.name == "f_ann_date":
            return "20260416"
        return "20260415"
    if field.name == "ts_code":
        # index_basic ts_code must match index_member index_code for
        # referential integrity (relationship test checks this FK).
        if dataset == "fund_portfolio":
            return "001753.OF"
        if dataset in {"index_basic", "index_daily"}:
            return "000300.SH"
        return "000001.SZ"
    if field.name == "index_code":
        return "000300.SH"
    if field.name == "con_code":
        return "000001.SZ"
    if field.name == "symbol":
        if dataset == "fund_portfolio":
            return "000001.SZ"
        return "000001"
    if field.name == "list_status":
        return "L"
    if field.name in {"report_type", "comp_type", "is_open"}:
        return "1"
    if field.name == "rank":
        return "1"
    if dataset == "trade_cal" and field.name == "exchange":
        return "SSE"
    if field.name == "update_flag":
        return "0"
    if (
        dataset in PRICE_DATASETS | {"index_daily"}
        and field.name in PRICE_NUMERIC_FIELD_NAMES
    ):
        return FIXTURE_DECIMAL_STRING
    if dataset == "daily_basic" and field.name in DAILY_BASIC_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "stk_limit" and field.name in STK_LIMIT_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "moneyflow" and field.name in MONEYFLOW_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "forecast" and field.name in FORECAST_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "adj_factor" and field.name == "adj_factor":
        return FIXTURE_DECIMAL_STRING
    if dataset == "stock_company" and field.name in {"reg_capital", "employees"}:
        return FIXTURE_DECIMAL_STRING
    # M1.13 expansion (precondition 9 closure) — numeric field samples
    # for the 8 promoted event_timeline sources. Identity-string fields
    # (in_de, is_release, proc, holder_type, holder_name, hm_name, etc.)
    # fall through to the default `<field.name>-fixture` and pass the
    # varchar staging cast.
    if dataset == "pledge_stat" and field.name in PLEDGE_STAT_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "pledge_detail" and field.name in PLEDGE_DETAIL_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "repurchase" and field.name in REPURCHASE_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "stk_holdertrade" and field.name in STK_HOLDERTRADE_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "limit_list_ths" and field.name in LIMIT_LIST_THS_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "limit_list_d" and field.name in LIMIT_LIST_D_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "hm_detail" and field.name in HM_DETAIL_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset in {"top10_holders", "top10_floatholders"} and (
        field.name in TOP10_HOLDERS_NUMERIC_FIELD_NAMES
    ):
        return FIXTURE_DECIMAL_STRING
    if dataset == "fund_portfolio" and field.name in FUND_PORTFOLIO_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "hsgt_top10" and field.name in HSGT_TOP10_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if dataset == "hsgt_hold_top10" and field.name in HSGT_HOLD_TOP10_NUMERIC_FIELD_NAMES:
        return FIXTURE_DECIMAL_STRING
    if pa.types.is_decimal(field.type):
        return Decimal("1.123456789012345678")
    return f"{field.name}-fixture"


def _render_staging_model(model_name: str, raw_zone_path: Path) -> str:
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

    return environment.from_string((STAGING_DIR / f"{model_name}.sql").read_text()).render().strip()


def _expected_staging_columns(asset: Any) -> list[str]:
    columns = list(asset.schema.names)
    if asset.dataset == "stock_basic":
        list_status_index = columns.index("list_status")
        columns.insert(list_status_index + 3, "is_active")
    columns.extend(["source_run_id", "raw_loaded_at"])
    return columns


def _test_names(column: dict[str, Any]) -> set[str]:
    return {_column_test_name(test) for test in column.get("tests", [])}


def _column_test_name(test: str | dict[str, Any]) -> str:
    if isinstance(test, str):
        return test
    return next(iter(test))


def _model_test_name(test: str | dict[str, Any]) -> str:
    if isinstance(test, str):
        return test
    return next(iter(test))


def _allows_null_identity(field: pa.Field) -> bool:
    metadata = field.metadata or {}
    return metadata.get(ALLOW_NULL_IDENTITY_METADATA_KEY) == ALLOW_NULL_IDENTITY_METADATA_VALUE


def _staging_identity_fields(dataset: str) -> tuple[str, ...]:
    if dataset in FINANCIAL_DATASET_FIELDS:
        return FINANCIAL_VERSION_FIELDS
    return _IDENTITY_FIELDS_BY_DATASET[dataset]


def _write_duckdb_only_profile(path: Path) -> None:
    path.write_text(
        """
data_platform:
  target: test
  outputs:
    test:
      type: duckdb
      path: "{{ env_var('DP_DUCKDB_PATH') }}"
      threads: 1
""".lstrip(),
        encoding="utf-8",
    )


def require_working_dbt() -> str:
    dbt = shutil.which("dbt")
    if dbt is None:
        local_dbt = PROJECT_ROOT / ".venv" / "bin" / "dbt"
        dbt = str(local_dbt) if local_dbt.exists() else None
    if dbt is None:
        pytest.skip("dbt executable is not installed in this environment")

    version_result = subprocess.run(
        [dbt, "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    version_output = version_result.stdout + version_result.stderr
    if version_result.returncode != 0:
        if os.environ.get("DP_DBT_RUNTIME_OPTIONAL") == "1":
            pytest.skip(
                "dbt runtime is explicitly optional in this environment; "
                f"startup failed:\n{version_output}"
            )
        if _is_python_314_mashumaro_startup_failure(version_output):
            pytest.skip(
                "dbt runtime is installed, but this sandbox is running Python 3.14 "
                "and the installed dbt dependency stack crashes in mashumaro during "
                f"startup:\n{version_output}"
            )
        pytest.fail(f"dbt --version failed:\n{version_output}")

    return dbt


def _is_python_314_mashumaro_startup_failure(version_output: str) -> bool:
    return (
        sys.version_info >= (3, 14)
        and "mashumaro.exceptions.UnserializableField" in version_output
    )


def _run_dbt_wrapper(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PROJECT_ROOT / "scripts" / "dbt.sh"), *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
