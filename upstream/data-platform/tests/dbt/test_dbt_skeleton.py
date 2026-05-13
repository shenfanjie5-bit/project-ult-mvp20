from __future__ import annotations

import os
from pathlib import Path

import pytest

from data_platform.adapters.tushare import TUSHARE_ASSETS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "src" / "data_platform" / "dbt"
STAGING_DIR = DBT_PROJECT_DIR / "models" / "staging"
INTERMEDIATE_DIR = DBT_PROJECT_DIR / "models" / "intermediate"
MARTS_V2_DIR = DBT_PROJECT_DIR / "models" / "marts_v2"
MARTS_LINEAGE_DIR = DBT_PROJECT_DIR / "models" / "marts_lineage"
MARTS_DERIVATIONS_DIR = DBT_PROJECT_DIR / "models" / "marts_derivations"
MARTS_DERIVATION_LINEAGE_DIR = (
    DBT_PROJECT_DIR / "models" / "marts_derivation_lineage"
)
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
# Provider-neutral canonical_v2 + canonical_lineage marts. Lock-step list with
# `data_platform.ddl.iceberg_tables.CANONICAL_V2_TABLE_SPECS` and
# `CANONICAL_LINEAGE_TABLE_SPECS`. After M1.13, canonical_v2.fact_event covers
# 16 source interfaces (M1-G2 safe subset + namechange + block_trade + 8 M1.13
# candidates: pledge_stat, pledge_detail, repurchase, stk_holdertrade, stk_surv,
# limit_list_ths, limit_list_d, hm_detail). Legacy `dbt/models/marts/` was
# retired in M1.14.
MART_V2_MODEL_NAMES = [
    "mart_dim_security_v2",
    "mart_stock_basic_v2",
    "mart_dim_index_v2",
    "mart_fact_price_bar_v2",
    "mart_fact_financial_indicator_v2",
    "mart_fact_market_daily_feature_v2",
    "mart_fact_index_price_bar_v2",
    "mart_fact_forecast_event_v2",
    "mart_fact_event_v2",
    "mart_fact_holding_position_v2",
    "mart_fact_northbound_turnover_v2",
]
MART_LINEAGE_MODEL_NAMES = [
    "mart_lineage_dim_security",
    "mart_lineage_stock_basic",
    "mart_lineage_dim_index",
    "mart_lineage_fact_price_bar",
    "mart_lineage_fact_financial_indicator",
    "mart_lineage_fact_market_daily_feature",
    "mart_lineage_fact_index_price_bar",
    "mart_lineage_fact_forecast_event",
    "mart_lineage_fact_event",
    "mart_lineage_fact_holding_position",
    "mart_lineage_fact_northbound_turnover",
]
MART_DERIVATION_MODEL_NAMES = [
    "mart_deriv_top_holder_qoq_change",
    "mart_deriv_fund_co_holding",
    "mart_deriv_northbound_holding_z_score",
]
MART_DERIVATION_LINEAGE_MODEL_NAMES = [
    "mart_deriv_lineage_top_holder_qoq_change",
    "mart_deriv_lineage_fund_co_holding",
    "mart_deriv_lineage_northbound_holding_z_score",
]


def test_dbt_skeleton_files_are_present() -> None:
    required_paths = [
        DBT_PROJECT_DIR / "dbt_project.yml",
        DBT_PROJECT_DIR / "profiles.yml.example",
        DBT_PROJECT_DIR / "macros" / "dp_raw_path.sql",
        DBT_PROJECT_DIR / "macros" / "stg_latest_raw.sql",
        DBT_PROJECT_DIR / "macros" / "staging_tests.sql",
        DBT_PROJECT_DIR / "macros" / "intermediate_tests.sql",
        STAGING_DIR / "_sources.yml",
        STAGING_DIR / "_schema.yml",
        INTERMEDIATE_DIR / "_schema.yml",
        DBT_PROJECT_DIR / "models" / "intermediate" / ".gitkeep",
        MARTS_V2_DIR / "_schema.yml",
        MARTS_LINEAGE_DIR / "_schema.yml",
        MARTS_DERIVATIONS_DIR / "_schema.yml",
        MARTS_DERIVATION_LINEAGE_DIR / "_schema.yml",
        DBT_PROJECT_DIR / "seeds" / ".gitkeep",
        PROJECT_ROOT / "scripts" / "dbt.sh",
        *[STAGING_DIR / f"stg_{asset.dataset}.sql" for asset in TUSHARE_ASSETS],
        *[INTERMEDIATE_DIR / f"{model_name}.sql" for model_name in INTERMEDIATE_MODEL_NAMES],
        *[MARTS_V2_DIR / f"{model_name}.sql" for model_name in MART_V2_MODEL_NAMES],
        *[MARTS_LINEAGE_DIR / f"{model_name}.sql" for model_name in MART_LINEAGE_MODEL_NAMES],
        *[
            MARTS_DERIVATIONS_DIR / f"{model_name}.sql"
            for model_name in MART_DERIVATION_MODEL_NAMES
        ],
        *[
            MARTS_DERIVATION_LINEAGE_DIR / f"{model_name}.sql"
            for model_name in MART_DERIVATION_LINEAGE_MODEL_NAMES
        ],
    ]

    missing_paths = [path for path in required_paths if not path.exists()]
    sql_models = sorted(
        path.relative_to(DBT_PROJECT_DIR).as_posix()
        for path in (DBT_PROJECT_DIR / "models").glob("**/*.sql")
    )

    assert missing_paths == []
    assert os.access(PROJECT_ROOT / "scripts" / "dbt.sh", os.X_OK)
    assert sql_models == sorted(
        [
            *(f"models/staging/stg_{asset.dataset}.sql" for asset in TUSHARE_ASSETS),
            *(f"models/intermediate/{model_name}.sql" for model_name in INTERMEDIATE_MODEL_NAMES),
            *(f"models/marts_v2/{model_name}.sql" for model_name in MART_V2_MODEL_NAMES),
            *(
                f"models/marts_lineage/{model_name}.sql"
                for model_name in MART_LINEAGE_MODEL_NAMES
            ),
            *(
                f"models/marts_derivations/{model_name}.sql"
                for model_name in MART_DERIVATION_MODEL_NAMES
            ),
            *(
                f"models/marts_derivation_lineage/{model_name}.sql"
                for model_name in MART_DERIVATION_LINEAGE_MODEL_NAMES
            ),
        ]
    )

    dbt_project = (DBT_PROJECT_DIR / "dbt_project.yml").read_text()
    assert "name: data_platform" in dbt_project
    assert "profile: data_platform" in dbt_project
    # Accept both legacy and dbt 1.11+ semver array format
    assert "require-dbt-version:" in dbt_project
    assert 'test-paths: ["tests"]' in dbt_project
    assert "+materialized: view" in dbt_project
    assert "+materialized: table" in dbt_project

    profile = (DBT_PROJECT_DIR / "profiles.yml.example").read_text()
    assert "DP_DUCKDB_PATH" in profile
    assert "DP_PG_DSN" in profile
    assert 'extensions: ["iceberg", "httpfs"]' in profile
    assert "type: postgres" in profile


def test_dp_raw_path_macros_strip_trailing_slash() -> None:
    jinja2 = pytest.importorskip("jinja2")

    environment = jinja2.Environment()
    environment.globals["env_var"] = lambda _name, _default=None: "/tmp/dp_raw/"
    template = environment.from_string(
        (DBT_PROJECT_DIR / "macros" / "dp_raw_path.sql").read_text()
    )
    module = template.make_module({})

    assert module.dp_raw_path("tushare", "stock_basic") == (
        "/tmp/dp_raw/tushare/stock_basic/**/*.parquet"
    )
    assert module.dp_raw_manifest_path("tushare", "stock_basic") == (
        "/tmp/dp_raw/tushare/stock_basic/**/_manifest.json"
    )


def test_stg_stock_basic_preserves_p1a_contract() -> None:
    model_sql = (STAGING_DIR / "stg_stock_basic.sql").read_text()
    macro_sql = (DBT_PROJECT_DIR / "macros" / "stg_latest_raw.sql").read_text()
    lowered_model_sql = model_sql.lower()

    assert '{{ config(materialized="view") }}' in model_sql
    assert "{{ stg_latest_raw(" in model_sql
    assert '"stock_basic"' in model_sql
    assert "strptime(nullif(trim(cast(\\\"list_date\\\" as varchar)), ''), '%Y%m%d')::date" in (
        model_sql
    )
    assert "as \\\"is_active\\\"" in model_sql
    assert "source_run_id" in macro_sql
    assert "raw_loaded_at" in macro_sql
    assert "select *" not in lowered_model_sql
    assert "canonical." not in lowered_model_sql
    assert "formal." not in lowered_model_sql
    assert "iceberg_scan" not in lowered_model_sql
