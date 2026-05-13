"""Asset definitions for the Tushare adapter."""

from __future__ import annotations

import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.adapters.base import AssetSpec, PartitionType, schema_hash
from data_platform.provider_catalog import tushare_interface_metadata_for_raw_dataset

TUSHARE_STOCK_BASIC_ASSET_NAME = "tushare_stock_basic"
TUSHARE_DAILY_ASSET_NAME = "tushare_daily"
TUSHARE_WEEKLY_ASSET_NAME = "tushare_weekly"
TUSHARE_MONTHLY_ASSET_NAME = "tushare_monthly"
TUSHARE_ADJ_FACTOR_ASSET_NAME = "tushare_adj_factor"
TUSHARE_DAILY_BASIC_ASSET_NAME = "tushare_daily_basic"
TUSHARE_INCOME_ASSET_NAME = "tushare_income"
TUSHARE_BALANCESHEET_ASSET_NAME = "tushare_balancesheet"
TUSHARE_CASHFLOW_ASSET_NAME = "tushare_cashflow"
TUSHARE_FINA_INDICATOR_ASSET_NAME = "tushare_fina_indicator"
TUSHARE_INDEX_BASIC_ASSET_NAME = "tushare_index_basic"
TUSHARE_INDEX_DAILY_ASSET_NAME = "tushare_index_daily"
TUSHARE_INDEX_WEIGHT_ASSET_NAME = "tushare_index_weight"
TUSHARE_INDEX_MEMBER_ASSET_NAME = "tushare_index_member"
TUSHARE_INDEX_CLASSIFY_ASSET_NAME = "tushare_index_classify"
TUSHARE_TRADE_CAL_ASSET_NAME = "tushare_trade_cal"
TUSHARE_STOCK_COMPANY_ASSET_NAME = "tushare_stock_company"
TUSHARE_NAMECHANGE_ASSET_NAME = "tushare_namechange"
TUSHARE_ANNS_ASSET_NAME = "tushare_anns"
TUSHARE_SUSPEND_D_ASSET_NAME = "tushare_suspend_d"
TUSHARE_DIVIDEND_ASSET_NAME = "tushare_dividend"
TUSHARE_SHARE_FLOAT_ASSET_NAME = "tushare_share_float"
TUSHARE_STK_HOLDERNUMBER_ASSET_NAME = "tushare_stk_holdernumber"
TUSHARE_DISCLOSURE_DATE_ASSET_NAME = "tushare_disclosure_date"
# Plan §5 expansion: 4 new datasets (stk_limit / block_trade / moneyflow / forecast)
TUSHARE_STK_LIMIT_ASSET_NAME = "tushare_stk_limit"
TUSHARE_BLOCK_TRADE_ASSET_NAME = "tushare_block_trade"
TUSHARE_MONEYFLOW_ASSET_NAME = "tushare_moneyflow"
TUSHARE_FORECAST_ASSET_NAME = "tushare_forecast"
# M1.13 expansion: 8 new event_timeline datasets (precondition 9 closure).
TUSHARE_PLEDGE_STAT_ASSET_NAME = "tushare_pledge_stat"
TUSHARE_PLEDGE_DETAIL_ASSET_NAME = "tushare_pledge_detail"
TUSHARE_REPURCHASE_ASSET_NAME = "tushare_repurchase"
TUSHARE_STK_HOLDERTRADE_ASSET_NAME = "tushare_stk_holdertrade"
TUSHARE_STK_SURV_ASSET_NAME = "tushare_stk_surv"
TUSHARE_LIMIT_LIST_THS_ASSET_NAME = "tushare_limit_list_ths"
TUSHARE_LIMIT_LIST_D_ASSET_NAME = "tushare_limit_list_d"
TUSHARE_HM_DETAIL_ASSET_NAME = "tushare_hm_detail"
# M4.5 holdings intake expansion.
TUSHARE_TOP10_HOLDERS_ASSET_NAME = "tushare_top10_holders"
TUSHARE_TOP10_FLOATHOLDERS_ASSET_NAME = "tushare_top10_floatholders"
TUSHARE_FUND_PORTFOLIO_ASSET_NAME = "tushare_fund_portfolio"
TUSHARE_HSGT_TOP10_ASSET_NAME = "tushare_hsgt_top10"
TUSHARE_HSGT_HOLD_TOP10_ASSET_NAME = "tushare_hsgt_hold_top10"

ALLOW_NULL_IDENTITY_METADATA_KEY = b"data_platform.allow_null_identity"
ALLOW_NULL_IDENTITY_METADATA_VALUE = b"true"
FINANCIAL_VERSION_FIELDS: tuple[str, ...] = (
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type",
    "comp_type",
    "update_flag",
)


def _string_field(name: str, *, allow_null_identity: bool = False) -> pa.Field:
    metadata = None
    if allow_null_identity:
        metadata = {ALLOW_NULL_IDENTITY_METADATA_KEY: ALLOW_NULL_IDENTITY_METADATA_VALUE}
    return pa.field(name, pa.string(), metadata=metadata)


TUSHARE_STOCK_BASIC_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("symbol", pa.string()),
        ("name", pa.string()),
        ("area", pa.string()),
        ("industry", pa.string()),
        ("fullname", pa.string()),
        ("enname", pa.string()),
        ("cnspell", pa.string()),
        ("market", pa.string()),
        ("exchange", pa.string()),
        ("curr_type", pa.string()),
        ("list_status", pa.string()),
        ("list_date", pa.string()),
        ("delist_date", pa.string()),
        ("is_hs", pa.string()),
        ("act_name", pa.string()),
        ("act_ent_type", pa.string()),
    ]
)

TUSHARE_RAW_NUMERIC_TYPE = pa.string()
TUSHARE_FINANCIAL_NUMERIC_TYPE = pa.decimal128(38, 18)

TUSHARE_BAR_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("open", TUSHARE_RAW_NUMERIC_TYPE),
        ("high", TUSHARE_RAW_NUMERIC_TYPE),
        ("low", TUSHARE_RAW_NUMERIC_TYPE),
        ("close", TUSHARE_RAW_NUMERIC_TYPE),
        ("pre_close", TUSHARE_RAW_NUMERIC_TYPE),
        ("change", TUSHARE_RAW_NUMERIC_TYPE),
        ("pct_chg", TUSHARE_RAW_NUMERIC_TYPE),
        ("vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_ADJ_FACTOR_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("adj_factor", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_DAILY_BASIC_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("close", TUSHARE_RAW_NUMERIC_TYPE),
        ("turnover_rate", TUSHARE_RAW_NUMERIC_TYPE),
        ("turnover_rate_f", TUSHARE_RAW_NUMERIC_TYPE),
        ("volume_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("pe", TUSHARE_RAW_NUMERIC_TYPE),
        ("pe_ttm", TUSHARE_RAW_NUMERIC_TYPE),
        ("pb", TUSHARE_RAW_NUMERIC_TYPE),
        ("ps", TUSHARE_RAW_NUMERIC_TYPE),
        ("ps_ttm", TUSHARE_RAW_NUMERIC_TYPE),
        ("dv_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("dv_ttm", TUSHARE_RAW_NUMERIC_TYPE),
        ("total_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("float_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("free_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("total_mv", TUSHARE_RAW_NUMERIC_TYPE),
        ("circ_mv", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_INDEX_BASIC_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("fullname", pa.string()),
        ("market", pa.string()),
        ("publisher", pa.string()),
        ("index_type", pa.string()),
        ("category", pa.string()),
        ("base_date", pa.string()),
        ("base_point", TUSHARE_RAW_NUMERIC_TYPE),
        ("list_date", pa.string()),
        ("weight_rule", pa.string()),
        ("desc", pa.string()),
        ("exp_date", pa.string()),
    ]
)

TUSHARE_INDEX_DAILY_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("close", TUSHARE_RAW_NUMERIC_TYPE),
        ("open", TUSHARE_RAW_NUMERIC_TYPE),
        ("high", TUSHARE_RAW_NUMERIC_TYPE),
        ("low", TUSHARE_RAW_NUMERIC_TYPE),
        ("pre_close", TUSHARE_RAW_NUMERIC_TYPE),
        ("change", TUSHARE_RAW_NUMERIC_TYPE),
        ("pct_chg", TUSHARE_RAW_NUMERIC_TYPE),
        ("vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_INDEX_WEIGHT_SCHEMA = pa.schema(
    [
        ("index_code", pa.string()),
        ("con_code", pa.string()),
        ("trade_date", pa.string()),
        ("weight", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_INDEX_MEMBER_SCHEMA = pa.schema(
    [
        ("index_code", pa.string()),
        ("index_name", pa.string()),
        ("con_code", pa.string()),
        ("con_name", pa.string()),
        ("in_date", pa.string()),
        ("out_date", pa.string()),
        ("is_new", pa.string()),
    ]
)

TUSHARE_INDEX_CLASSIFY_SCHEMA = pa.schema(
    [
        ("index_code", pa.string()),
        ("industry_name", pa.string()),
        ("level", pa.string()),
        ("industry_code", pa.string()),
        ("is_pub", pa.string()),
        ("parent_code", pa.string()),
        ("src", pa.string()),
    ]
)

TUSHARE_TRADE_CAL_SCHEMA = pa.schema(
    [
        ("exchange", pa.string()),
        ("cal_date", pa.string()),
        ("is_open", pa.string()),
        ("pretrade_date", pa.string()),
    ]
)

TUSHARE_STOCK_COMPANY_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("exchange", pa.string()),
        ("chairman", pa.string()),
        ("manager", pa.string()),
        ("secretary", pa.string()),
        ("reg_capital", TUSHARE_RAW_NUMERIC_TYPE),
        ("setup_date", pa.string()),
        ("province", pa.string()),
        ("city", pa.string()),
        ("introduction", pa.string()),
        ("website", pa.string()),
        ("email", pa.string()),
        ("office", pa.string()),
        ("employees", TUSHARE_RAW_NUMERIC_TYPE),
        ("main_business", pa.string()),
        ("business_scope", pa.string()),
    ]
)

TUSHARE_NAMECHANGE_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        ("ann_date", pa.string()),
        ("change_reason", pa.string()),
    ]
)

TUSHARE_ANNS_SCHEMA = pa.schema(
    [
        _string_field("ts_code", allow_null_identity=True),
        ("ann_date", pa.string()),
        ("name", pa.string()),
        ("title", pa.string()),
        ("url", pa.string()),
        ("rec_time", pa.string()),
    ]
)

TUSHARE_SUSPEND_D_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("suspend_timing", pa.string()),
        ("suspend_type", pa.string()),
    ]
)

TUSHARE_DIVIDEND_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("end_date", pa.string()),
        ("ann_date", pa.string()),
        ("div_proc", pa.string()),
        ("stk_div", TUSHARE_RAW_NUMERIC_TYPE),
        ("stk_bo_rate", TUSHARE_RAW_NUMERIC_TYPE),
        ("stk_co_rate", TUSHARE_RAW_NUMERIC_TYPE),
        ("cash_div", TUSHARE_RAW_NUMERIC_TYPE),
        ("cash_div_tax", TUSHARE_RAW_NUMERIC_TYPE),
        ("record_date", pa.string()),
        ("ex_date", pa.string()),
        ("pay_date", pa.string()),
        ("div_listdate", pa.string()),
        ("imp_ann_date", pa.string()),
        ("base_date", pa.string()),
        ("base_share", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_SHARE_FLOAT_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("float_date", pa.string()),
        ("float_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("float_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("holder_name", pa.string()),
        ("share_type", pa.string()),
    ]
)

TUSHARE_STK_HOLDERNUMBER_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("holder_num", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_DISCLOSURE_DATE_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("pre_date", pa.string()),
        ("actual_date", pa.string()),
        ("modify_date", pa.string()),
    ]
)

# Plan §5 expansion: stk_limit — every-trading-day price-limit band.
# Market-data class (identity: ts_code + trade_date). Numeric fields
# stay pa.string() per TUSHARE_RAW_NUMERIC_TYPE; staging model casts.
TUSHARE_STK_LIMIT_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("up_limit", TUSHARE_RAW_NUMERIC_TYPE),
        ("down_limit", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

# Plan §5 expansion: block_trade — block trade executions.
#
# Identity widens to the full row shape ((ts_code, trade_date, buyer,
# seller, price, vol, amount)) because the same (ts_code, trade_date)
# CAN repeat (multiple distinct block trade executions on the same
# day), mirroring how anns disambiguates multiple announcements per
# (ts_code, ann_date) via (title, url).
#
# Codex review #1 P2 fix: ts_code is NOT allow_null_identity here.
# anns allows null ts_code because an exchange-wide bulk announcement
# can lack a security key; a block trade by definition has a
# counterparty security — accepting ts_code=None would let a
# malformed upstream row slip into Raw Zone with no way to match it
# back to an instrument. Keep ts_code as a regular required string
# and enforce not_null at the dbt staging layer.
TUSHARE_BLOCK_TRADE_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("price", TUSHARE_RAW_NUMERIC_TYPE),
        ("vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("buyer", pa.string()),
        ("seller", pa.string()),
    ]
)

# Plan §5 expansion: moneyflow — per-stock daily fund flow breakdown
# by order size bucket (sm / md / lg / elg × buy / sell + net_mf).
# Market-data class (identity: ts_code + trade_date). 18 numeric
# columns all pa.string().
TUSHARE_MONEYFLOW_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("trade_date", pa.string()),
        ("buy_sm_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_sm_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_sm_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_sm_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_md_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_md_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_md_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_md_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_lg_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_lg_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_lg_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_lg_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_elg_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy_elg_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_elg_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_elg_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_mf_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_mf_amount", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

# Plan §5 expansion: forecast — earnings forecast notification.
# Multi-version via update_flag; identity = ts_code + ann_date +
# end_date + update_flag. NOT FINANCIAL family: forecast lacks
# f_ann_date / report_type / comp_type, so it gets its own
# FORECAST_DATASET_FIELDS + FORECAST_VERSION_FIELDS below. Numeric
# fields stay pa.string() (coarse percentage ranges and profit
# bands; no need for decimal(38,18) scale).
TUSHARE_FORECAST_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("type", pa.string()),
        ("p_change_min", TUSHARE_RAW_NUMERIC_TYPE),
        ("p_change_max", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_profit_min", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_profit_max", TUSHARE_RAW_NUMERIC_TYPE),
        ("last_parent_net", TUSHARE_RAW_NUMERIC_TYPE),
        ("first_ann_date", pa.string()),
        ("summary", pa.string()),
        ("change_reason", pa.string()),
        ("update_flag", pa.string()),
    ]
)

# M1.13 expansion: 8 event_timeline candidate schemas (precondition 9
# closure). Column lists lifted verbatim from
# `event-timeline-m1-11-candidate-schema-checkin-20260429.md` per
# evidence file §1–§8. Numeric fields stay pa.string() per
# TUSHARE_RAW_NUMERIC_TYPE convention; staging models cast.

# §1 pledge_stat — quarterly pledge summary snapshot.
TUSHARE_PLEDGE_STAT_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("end_date", pa.string()),
        ("pledge_count", TUSHARE_RAW_NUMERIC_TYPE),
        ("unrest_pledge", TUSHARE_RAW_NUMERIC_TYPE),
        ("rest_pledge", TUSHARE_RAW_NUMERIC_TYPE),
        ("total_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("pledge_ratio", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

# §2 pledge_detail — per-pledge agreement events.
TUSHARE_PLEDGE_DETAIL_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("holder_name", pa.string()),
        ("pledge_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        ("is_release", pa.string()),
        ("release_date", pa.string()),
        ("pledgor", pa.string()),
        ("holding_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("pledged_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("p_total_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("h_total_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("is_buyback", pa.string()),
    ]
)

# §3 repurchase — share repurchase announcements (multi-stage).
TUSHARE_REPURCHASE_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("proc", pa.string()),
        ("exp_date", pa.string()),
        ("vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("high_limit", TUSHARE_RAW_NUMERIC_TYPE),
        ("low_limit", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

# §4 stk_holdertrade — insider/major-shareholder trades.
TUSHARE_STK_HOLDERTRADE_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("holder_name", pa.string()),
        ("holder_type", pa.string()),
        ("in_de", pa.string()),
        ("change_vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("change_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("after_share", TUSHARE_RAW_NUMERIC_TYPE),
        ("after_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("avg_price", TUSHARE_RAW_NUMERIC_TYPE),
        ("total_share", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

# §5 stk_surv — institutional surveys / analyst visits.
TUSHARE_STK_SURV_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("surv_date", pa.string()),
        ("fund_visitors", pa.string()),
        ("rece_place", pa.string()),
        ("rece_mode", pa.string()),
        ("rece_org", pa.string()),
        ("org_type", pa.string()),
        ("comp_rece", pa.string()),
    ]
)

# §6 limit_list_ths — 同花顺 intra-day limit-pool snapshots.
TUSHARE_LIMIT_LIST_THS_SCHEMA = pa.schema(
    [
        ("trade_date", pa.string()),
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("price", TUSHARE_RAW_NUMERIC_TYPE),
        ("pct_chg", TUSHARE_RAW_NUMERIC_TYPE),
        ("open_num", pa.string()),
        ("lu_desc", pa.string()),
        ("limit_type", pa.string()),
        ("tag", pa.string()),
        ("status", pa.string()),
        ("limit_order", TUSHARE_RAW_NUMERIC_TYPE),
        ("limit_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("turnover_rate", TUSHARE_RAW_NUMERIC_TYPE),
        ("free_float", TUSHARE_RAW_NUMERIC_TYPE),
        ("lu_limit_order", pa.string()),
        ("limit_up_suc_rate", TUSHARE_RAW_NUMERIC_TYPE),
        ("turnover", pa.string()),
        ("market_type", pa.string()),
    ]
)

# §7 limit_list_d — daily limit-hit / blow-up records.
TUSHARE_LIMIT_LIST_D_SCHEMA = pa.schema(
    [
        ("trade_date", pa.string()),
        ("ts_code", pa.string()),
        ("industry", pa.string()),
        ("name", pa.string()),
        ("close", TUSHARE_RAW_NUMERIC_TYPE),
        ("pct_chg", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("limit_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("float_mv", TUSHARE_RAW_NUMERIC_TYPE),
        ("total_mv", TUSHARE_RAW_NUMERIC_TYPE),
        ("turnover_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("fd_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("first_time", pa.string()),
        ("last_time", pa.string()),
        ("open_times", pa.string()),
        ("up_stat", pa.string()),
        ("limit_times", pa.string()),
        ("limit", pa.string()),
    ]
)

# §8 hm_detail — hot-money entity per-stock daily trades.
TUSHARE_HM_DETAIL_SCHEMA = pa.schema(
    [
        ("trade_date", pa.string()),
        ("ts_code", pa.string()),
        ("ts_name", pa.string()),
        ("buy_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("hm_name", pa.string()),
        ("hm_orgs", pa.string()),
    ]
)

# M4.5 holdings intake expansion. Numeric fields stay pa.string() at
# Raw/staging, matching the existing event and market-data convention.
TUSHARE_TOP10_HOLDERS_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("holder_name", pa.string()),
        ("hold_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_float_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_change", TUSHARE_RAW_NUMERIC_TYPE),
        ("holder_type", pa.string()),
    ]
)

TUSHARE_TOP10_FLOATHOLDERS_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("holder_name", pa.string()),
        ("hold_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_float_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("hold_change", TUSHARE_RAW_NUMERIC_TYPE),
        ("holder_type", pa.string()),
    ]
)

TUSHARE_FUND_PORTFOLIO_SCHEMA = pa.schema(
    [
        ("ts_code", pa.string()),
        ("ann_date", pa.string()),
        ("end_date", pa.string()),
        ("symbol", pa.string()),
        ("mkv", TUSHARE_RAW_NUMERIC_TYPE),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("stk_mkv_ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("stk_float_ratio", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_HSGT_TOP10_SCHEMA = pa.schema(
    [
        ("trade_date", pa.string()),
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("close", TUSHARE_RAW_NUMERIC_TYPE),
        ("change", TUSHARE_RAW_NUMERIC_TYPE),
        ("rank", TUSHARE_RAW_NUMERIC_TYPE),
        ("market_type", pa.string()),
        ("amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("net_amount", TUSHARE_RAW_NUMERIC_TYPE),
        ("buy", TUSHARE_RAW_NUMERIC_TYPE),
        ("sell", TUSHARE_RAW_NUMERIC_TYPE),
    ]
)

TUSHARE_HSGT_HOLD_TOP10_SCHEMA = pa.schema(
    [
        ("code", pa.string()),
        ("trade_date", pa.string()),
        ("ts_code", pa.string()),
        ("name", pa.string()),
        ("vol", TUSHARE_RAW_NUMERIC_TYPE),
        ("ratio", TUSHARE_RAW_NUMERIC_TYPE),
        ("exchange", pa.string()),
    ]
)


def _financial_schema(numeric_fields: tuple[str, ...]) -> pa.Schema:
    return pa.schema(
        [
            *(pa.field(field_name, pa.string()) for field_name in FINANCIAL_VERSION_FIELDS),
            *(pa.field(field_name, TUSHARE_FINANCIAL_NUMERIC_TYPE) for field_name in numeric_fields),
        ]
    )


TUSHARE_INCOME_NUMERIC_FIELDS: tuple[str, ...] = (
    "basic_eps",
    "diluted_eps",
    "total_revenue",
    "revenue",
    "operate_profit",
    "total_profit",
    "income_tax",
    "n_income",
    "n_income_attr_p",
    "minority_gain",
    "ebit",
    "ebitda",
)
TUSHARE_BALANCESHEET_NUMERIC_FIELDS: tuple[str, ...] = (
    "money_cap",
    "accounts_receiv",
    "inventories",
    "total_cur_assets",
    "fix_assets",
    "total_assets",
    "total_cur_liab",
    "total_liab",
    "total_hldr_eqy_exc_min_int",
    "total_hldr_eqy_inc_min_int",
    "total_liab_hldr_eqy",
)
TUSHARE_CASHFLOW_NUMERIC_FIELDS: tuple[str, ...] = (
    "net_profit",
    "c_fr_sale_sg",
    "c_inf_fr_operate_a",
    "c_paid_goods_s",
    "st_cash_out_act",
    "n_cashflow_act",
    "n_cashflow_inv_act",
    "n_cash_flows_fnc_act",
    "n_incr_cash_cash_equ",
    "c_cash_equ_beg_period",
    "c_cash_equ_end_period",
    "free_cashflow",
)
TUSHARE_FINA_INDICATOR_NUMERIC_FIELDS: tuple[str, ...] = (
    "eps",
    "dt_eps",
    "total_revenue_ps",
    "revenue_ps",
    "ocfps",
    "bps",
    "grossprofit_margin",
    "netprofit_margin",
    "roe",
    "roe_waa",
    "roa",
    "debt_to_assets",
    "or_yoy",
    "netprofit_yoy",
)
TUSHARE_INCOME_SCHEMA = _financial_schema(TUSHARE_INCOME_NUMERIC_FIELDS)
TUSHARE_BALANCESHEET_SCHEMA = _financial_schema(TUSHARE_BALANCESHEET_NUMERIC_FIELDS)
TUSHARE_CASHFLOW_SCHEMA = _financial_schema(TUSHARE_CASHFLOW_NUMERIC_FIELDS)
TUSHARE_FINA_INDICATOR_SCHEMA = _financial_schema(TUSHARE_FINA_INDICATOR_NUMERIC_FIELDS)

TUSHARE_STOCK_BASIC_FIELDS = tuple(TUSHARE_STOCK_BASIC_SCHEMA.names)
TUSHARE_STOCK_BASIC_FIELDS_CSV = ",".join(TUSHARE_STOCK_BASIC_FIELDS)
TUSHARE_BAR_FIELDS = tuple(TUSHARE_BAR_SCHEMA.names)
TUSHARE_BAR_FIELDS_CSV = ",".join(TUSHARE_BAR_FIELDS)
TUSHARE_ADJ_FACTOR_FIELDS = tuple(TUSHARE_ADJ_FACTOR_SCHEMA.names)
TUSHARE_ADJ_FACTOR_FIELDS_CSV = ",".join(TUSHARE_ADJ_FACTOR_FIELDS)
TUSHARE_DAILY_BASIC_FIELDS = tuple(TUSHARE_DAILY_BASIC_SCHEMA.names)
TUSHARE_DAILY_BASIC_FIELDS_CSV = ",".join(TUSHARE_DAILY_BASIC_FIELDS)
TUSHARE_INDEX_BASIC_FIELDS = tuple(TUSHARE_INDEX_BASIC_SCHEMA.names)
TUSHARE_INDEX_BASIC_FIELDS_CSV = ",".join(TUSHARE_INDEX_BASIC_FIELDS)
TUSHARE_INDEX_DAILY_FIELDS = tuple(TUSHARE_INDEX_DAILY_SCHEMA.names)
TUSHARE_INDEX_DAILY_FIELDS_CSV = ",".join(TUSHARE_INDEX_DAILY_FIELDS)
TUSHARE_INDEX_WEIGHT_FIELDS = tuple(TUSHARE_INDEX_WEIGHT_SCHEMA.names)
TUSHARE_INDEX_WEIGHT_FIELDS_CSV = ",".join(TUSHARE_INDEX_WEIGHT_FIELDS)
TUSHARE_INDEX_MEMBER_FIELDS = tuple(TUSHARE_INDEX_MEMBER_SCHEMA.names)
TUSHARE_INDEX_MEMBER_FIELDS_CSV = ",".join(TUSHARE_INDEX_MEMBER_FIELDS)
TUSHARE_INDEX_CLASSIFY_FIELDS = tuple(TUSHARE_INDEX_CLASSIFY_SCHEMA.names)
TUSHARE_INDEX_CLASSIFY_FIELDS_CSV = ",".join(TUSHARE_INDEX_CLASSIFY_FIELDS)
TUSHARE_TRADE_CAL_FIELDS = tuple(TUSHARE_TRADE_CAL_SCHEMA.names)
TUSHARE_TRADE_CAL_FIELDS_CSV = ",".join(TUSHARE_TRADE_CAL_FIELDS)
TUSHARE_STOCK_COMPANY_FIELDS = tuple(TUSHARE_STOCK_COMPANY_SCHEMA.names)
TUSHARE_STOCK_COMPANY_FIELDS_CSV = ",".join(TUSHARE_STOCK_COMPANY_FIELDS)
TUSHARE_NAMECHANGE_FIELDS = tuple(TUSHARE_NAMECHANGE_SCHEMA.names)
TUSHARE_NAMECHANGE_FIELDS_CSV = ",".join(TUSHARE_NAMECHANGE_FIELDS)
TUSHARE_ANNS_FIELDS = tuple(TUSHARE_ANNS_SCHEMA.names)
TUSHARE_ANNS_FIELDS_CSV = ",".join(TUSHARE_ANNS_FIELDS)
TUSHARE_SUSPEND_D_FIELDS = tuple(TUSHARE_SUSPEND_D_SCHEMA.names)
TUSHARE_SUSPEND_D_FIELDS_CSV = ",".join(TUSHARE_SUSPEND_D_FIELDS)
TUSHARE_DIVIDEND_FIELDS = tuple(TUSHARE_DIVIDEND_SCHEMA.names)
TUSHARE_DIVIDEND_FIELDS_CSV = ",".join(TUSHARE_DIVIDEND_FIELDS)
TUSHARE_SHARE_FLOAT_FIELDS = tuple(TUSHARE_SHARE_FLOAT_SCHEMA.names)
TUSHARE_SHARE_FLOAT_FIELDS_CSV = ",".join(TUSHARE_SHARE_FLOAT_FIELDS)
TUSHARE_STK_HOLDERNUMBER_FIELDS = tuple(TUSHARE_STK_HOLDERNUMBER_SCHEMA.names)
TUSHARE_STK_HOLDERNUMBER_FIELDS_CSV = ",".join(TUSHARE_STK_HOLDERNUMBER_FIELDS)
TUSHARE_DISCLOSURE_DATE_FIELDS = tuple(TUSHARE_DISCLOSURE_DATE_SCHEMA.names)
TUSHARE_DISCLOSURE_DATE_FIELDS_CSV = ",".join(TUSHARE_DISCLOSURE_DATE_FIELDS)
TUSHARE_INCOME_FIELDS = tuple(TUSHARE_INCOME_SCHEMA.names)
TUSHARE_INCOME_FIELDS_CSV = ",".join(TUSHARE_INCOME_FIELDS)
TUSHARE_BALANCESHEET_FIELDS = tuple(TUSHARE_BALANCESHEET_SCHEMA.names)
TUSHARE_BALANCESHEET_FIELDS_CSV = ",".join(TUSHARE_BALANCESHEET_FIELDS)
TUSHARE_CASHFLOW_FIELDS = tuple(TUSHARE_CASHFLOW_SCHEMA.names)
TUSHARE_CASHFLOW_FIELDS_CSV = ",".join(TUSHARE_CASHFLOW_FIELDS)
TUSHARE_FINA_INDICATOR_FIELDS = tuple(TUSHARE_FINA_INDICATOR_SCHEMA.names)
TUSHARE_FINA_INDICATOR_FIELDS_CSV = ",".join(TUSHARE_FINA_INDICATOR_FIELDS)
# Plan §5 expansion: 4 new datasets' FIELDS + FIELDS_CSV exports.
TUSHARE_STK_LIMIT_FIELDS = tuple(TUSHARE_STK_LIMIT_SCHEMA.names)
TUSHARE_STK_LIMIT_FIELDS_CSV = ",".join(TUSHARE_STK_LIMIT_FIELDS)
TUSHARE_BLOCK_TRADE_FIELDS = tuple(TUSHARE_BLOCK_TRADE_SCHEMA.names)
TUSHARE_BLOCK_TRADE_FIELDS_CSV = ",".join(TUSHARE_BLOCK_TRADE_FIELDS)
TUSHARE_MONEYFLOW_FIELDS = tuple(TUSHARE_MONEYFLOW_SCHEMA.names)
TUSHARE_MONEYFLOW_FIELDS_CSV = ",".join(TUSHARE_MONEYFLOW_FIELDS)
TUSHARE_FORECAST_FIELDS = tuple(TUSHARE_FORECAST_SCHEMA.names)
TUSHARE_FORECAST_FIELDS_CSV = ",".join(TUSHARE_FORECAST_FIELDS)
# M1.13 expansion: 8 new event_timeline datasets' FIELDS + FIELDS_CSV exports.
TUSHARE_PLEDGE_STAT_FIELDS = tuple(TUSHARE_PLEDGE_STAT_SCHEMA.names)
TUSHARE_PLEDGE_STAT_FIELDS_CSV = ",".join(TUSHARE_PLEDGE_STAT_FIELDS)
TUSHARE_PLEDGE_DETAIL_FIELDS = tuple(TUSHARE_PLEDGE_DETAIL_SCHEMA.names)
TUSHARE_PLEDGE_DETAIL_FIELDS_CSV = ",".join(TUSHARE_PLEDGE_DETAIL_FIELDS)
TUSHARE_REPURCHASE_FIELDS = tuple(TUSHARE_REPURCHASE_SCHEMA.names)
TUSHARE_REPURCHASE_FIELDS_CSV = ",".join(TUSHARE_REPURCHASE_FIELDS)
TUSHARE_STK_HOLDERTRADE_FIELDS = tuple(TUSHARE_STK_HOLDERTRADE_SCHEMA.names)
TUSHARE_STK_HOLDERTRADE_FIELDS_CSV = ",".join(TUSHARE_STK_HOLDERTRADE_FIELDS)
TUSHARE_STK_SURV_FIELDS = tuple(TUSHARE_STK_SURV_SCHEMA.names)
TUSHARE_STK_SURV_FIELDS_CSV = ",".join(TUSHARE_STK_SURV_FIELDS)
TUSHARE_LIMIT_LIST_THS_FIELDS = tuple(TUSHARE_LIMIT_LIST_THS_SCHEMA.names)
TUSHARE_LIMIT_LIST_THS_FIELDS_CSV = ",".join(TUSHARE_LIMIT_LIST_THS_FIELDS)
TUSHARE_LIMIT_LIST_D_FIELDS = tuple(TUSHARE_LIMIT_LIST_D_SCHEMA.names)
TUSHARE_LIMIT_LIST_D_FIELDS_CSV = ",".join(TUSHARE_LIMIT_LIST_D_FIELDS)
TUSHARE_HM_DETAIL_FIELDS = tuple(TUSHARE_HM_DETAIL_SCHEMA.names)
TUSHARE_HM_DETAIL_FIELDS_CSV = ",".join(TUSHARE_HM_DETAIL_FIELDS)
# M4.5 holdings intake expansion.
TUSHARE_TOP10_HOLDERS_FIELDS = tuple(TUSHARE_TOP10_HOLDERS_SCHEMA.names)
TUSHARE_TOP10_HOLDERS_FIELDS_CSV = ",".join(TUSHARE_TOP10_HOLDERS_FIELDS)
TUSHARE_TOP10_FLOATHOLDERS_FIELDS = tuple(TUSHARE_TOP10_FLOATHOLDERS_SCHEMA.names)
TUSHARE_TOP10_FLOATHOLDERS_FIELDS_CSV = ",".join(TUSHARE_TOP10_FLOATHOLDERS_FIELDS)
TUSHARE_FUND_PORTFOLIO_FIELDS = tuple(TUSHARE_FUND_PORTFOLIO_SCHEMA.names)
TUSHARE_FUND_PORTFOLIO_FIELDS_CSV = ",".join(TUSHARE_FUND_PORTFOLIO_FIELDS)
TUSHARE_HSGT_TOP10_FIELDS = tuple(TUSHARE_HSGT_TOP10_SCHEMA.names)
TUSHARE_HSGT_TOP10_FIELDS_CSV = ",".join(TUSHARE_HSGT_TOP10_FIELDS)
TUSHARE_HSGT_HOLD_TOP10_FIELDS = tuple(TUSHARE_HSGT_HOLD_TOP10_SCHEMA.names)
TUSHARE_HSGT_HOLD_TOP10_FIELDS_CSV = ",".join(TUSHARE_HSGT_HOLD_TOP10_FIELDS)

REFERENCE_DATA_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "index_basic": ("ts_code",),
    "index_daily": ("ts_code", "trade_date"),
    "index_weight": ("index_code", "con_code", "trade_date"),
    "index_member": ("index_code", "con_code", "in_date"),
    "index_classify": ("index_code",),
    "trade_cal": ("cal_date", "is_open"),
    "stock_company": ("ts_code",),
    "namechange": ("ts_code", "start_date"),
}

EVENT_METADATA_FIELDS: dict[str, tuple[str, ...]] = {
    "anns": TUSHARE_ANNS_FIELDS,
    "suspend_d": TUSHARE_SUSPEND_D_FIELDS,
    "dividend": TUSHARE_DIVIDEND_FIELDS,
    "share_float": TUSHARE_SHARE_FLOAT_FIELDS,
    "stk_holdernumber": TUSHARE_STK_HOLDERNUMBER_FIELDS,
    "disclosure_date": TUSHARE_DISCLOSURE_DATE_FIELDS,
    # Plan §5 expansion — block_trade follows the anns multi-row pattern.
    "block_trade": TUSHARE_BLOCK_TRADE_FIELDS,
    # M1.13 expansion — 8 candidate event_timeline sources promoted (precondition 9).
    "pledge_stat": TUSHARE_PLEDGE_STAT_FIELDS,
    "pledge_detail": TUSHARE_PLEDGE_DETAIL_FIELDS,
    "repurchase": TUSHARE_REPURCHASE_FIELDS,
    "stk_holdertrade": TUSHARE_STK_HOLDERTRADE_FIELDS,
    "stk_surv": TUSHARE_STK_SURV_FIELDS,
    "limit_list_ths": TUSHARE_LIMIT_LIST_THS_FIELDS,
    "limit_list_d": TUSHARE_LIMIT_LIST_D_FIELDS,
    "hm_detail": TUSHARE_HM_DETAIL_FIELDS,
}

FINANCIAL_DATASET_FIELDS: dict[str, tuple[str, ...]] = {
    "income": TUSHARE_INCOME_FIELDS,
    "balancesheet": TUSHARE_BALANCESHEET_FIELDS,
    "cashflow": TUSHARE_CASHFLOW_FIELDS,
    "fina_indicator": TUSHARE_FINA_INDICATOR_FIELDS,
}

# Plan §5 expansion: forecast is NOT FINANCIAL (its field set omits
# f_ann_date / report_type / comp_type). It's a separate family with
# its own version-tracking identity keyed on update_flag + type.
#
# Codex review #1 P2 fix: `type` is part of the identity. Empirically
# 2990 / 5389 corpus forecast files (55%) have the same
# (ts_code, ann_date, end_date, update_flag) across multiple rows
# that differ only in `type` (e.g. 000056.SZ/20240710/20240630/
# update_flag=0 ships both "续亏" and "不确定" forecasts side-by-side —
# a company can emit multiple forecast flavors for the same report
# period, and each is a distinct semantic record). Without `type` in
# identity the dbt unique test would false-fire on real data and the
# adapter would deduplicate legitimate rows.
FORECAST_DATASET_FIELDS: dict[str, tuple[str, ...]] = {
    "forecast": TUSHARE_FORECAST_FIELDS,
}
FORECAST_VERSION_FIELDS: tuple[str, ...] = (
    "ts_code",
    "ann_date",
    "end_date",
    "update_flag",
    "type",
)

HOLDINGS_DATASET_FIELDS: dict[str, tuple[str, ...]] = {
    "top10_holders": TUSHARE_TOP10_HOLDERS_FIELDS,
    "top10_floatholders": TUSHARE_TOP10_FLOATHOLDERS_FIELDS,
    "fund_portfolio": TUSHARE_FUND_PORTFOLIO_FIELDS,
    "hsgt_top10": TUSHARE_HSGT_TOP10_FIELDS,
    "hsgt_hold_top10": TUSHARE_HSGT_HOLD_TOP10_FIELDS,
}
EXPLICIT_TS_CODE_RAW_DATASETS = frozenset({"top10_holders", "top10_floatholders"})


def _tushare_asset_spec(
    *,
    name: str,
    dataset: str,
    partition: PartitionType,
    schema: pa.Schema,
) -> AssetSpec:
    metadata = dict(tushare_interface_metadata_for_raw_dataset(dataset))
    metadata["schema_hash"] = schema_hash(schema)
    if dataset in EXPLICIT_TS_CODE_RAW_DATASETS:
        metadata["required_fetch_params"] = ("ts_code",)
        metadata["raw_partition_scope"] = "explicit_ts_code"
        metadata["daily_refresh_scope_env"] = "DP_TUSHARE_TOP10_TS_CODES"
    return AssetSpec(
        name=name,
        dataset=dataset,
        partition=partition,
        schema=schema,
        metadata=metadata,
    )


TUSHARE_STOCK_BASIC_ASSET = _tushare_asset_spec(
    name=TUSHARE_STOCK_BASIC_ASSET_NAME,
    dataset="stock_basic",
    partition="static",
    schema=TUSHARE_STOCK_BASIC_SCHEMA,
)

TUSHARE_DAILY_ASSET = _tushare_asset_spec(
    name=TUSHARE_DAILY_ASSET_NAME,
    dataset="daily",
    partition="daily",
    schema=TUSHARE_BAR_SCHEMA,
)

TUSHARE_WEEKLY_ASSET = _tushare_asset_spec(
    name=TUSHARE_WEEKLY_ASSET_NAME,
    dataset="weekly",
    partition="daily",
    schema=TUSHARE_BAR_SCHEMA,
)

TUSHARE_MONTHLY_ASSET = _tushare_asset_spec(
    name=TUSHARE_MONTHLY_ASSET_NAME,
    dataset="monthly",
    partition="daily",
    schema=TUSHARE_BAR_SCHEMA,
)

TUSHARE_ADJ_FACTOR_ASSET = _tushare_asset_spec(
    name=TUSHARE_ADJ_FACTOR_ASSET_NAME,
    dataset="adj_factor",
    partition="daily",
    schema=TUSHARE_ADJ_FACTOR_SCHEMA,
)

TUSHARE_DAILY_BASIC_ASSET = _tushare_asset_spec(
    name=TUSHARE_DAILY_BASIC_ASSET_NAME,
    dataset="daily_basic",
    partition="daily",
    schema=TUSHARE_DAILY_BASIC_SCHEMA,
)

TUSHARE_INDEX_BASIC_ASSET = _tushare_asset_spec(
    name=TUSHARE_INDEX_BASIC_ASSET_NAME,
    dataset="index_basic",
    partition="static",
    schema=TUSHARE_INDEX_BASIC_SCHEMA,
)

TUSHARE_INDEX_DAILY_ASSET = _tushare_asset_spec(
    name=TUSHARE_INDEX_DAILY_ASSET_NAME,
    dataset="index_daily",
    partition="daily",
    schema=TUSHARE_INDEX_DAILY_SCHEMA,
)

TUSHARE_INDEX_WEIGHT_ASSET = _tushare_asset_spec(
    name=TUSHARE_INDEX_WEIGHT_ASSET_NAME,
    dataset="index_weight",
    partition="daily",
    schema=TUSHARE_INDEX_WEIGHT_SCHEMA,
)

TUSHARE_INDEX_MEMBER_ASSET = _tushare_asset_spec(
    name=TUSHARE_INDEX_MEMBER_ASSET_NAME,
    dataset="index_member",
    partition="daily",
    schema=TUSHARE_INDEX_MEMBER_SCHEMA,
)

TUSHARE_INDEX_CLASSIFY_ASSET = _tushare_asset_spec(
    name=TUSHARE_INDEX_CLASSIFY_ASSET_NAME,
    dataset="index_classify",
    partition="static",
    schema=TUSHARE_INDEX_CLASSIFY_SCHEMA,
)

TUSHARE_TRADE_CAL_ASSET = _tushare_asset_spec(
    name=TUSHARE_TRADE_CAL_ASSET_NAME,
    dataset="trade_cal",
    partition="daily",
    schema=TUSHARE_TRADE_CAL_SCHEMA,
)

TUSHARE_STOCK_COMPANY_ASSET = _tushare_asset_spec(
    name=TUSHARE_STOCK_COMPANY_ASSET_NAME,
    dataset="stock_company",
    partition="static",
    schema=TUSHARE_STOCK_COMPANY_SCHEMA,
)

TUSHARE_NAMECHANGE_ASSET = _tushare_asset_spec(
    name=TUSHARE_NAMECHANGE_ASSET_NAME,
    dataset="namechange",
    partition="daily",
    schema=TUSHARE_NAMECHANGE_SCHEMA,
)

TUSHARE_ANNS_ASSET = _tushare_asset_spec(
    name=TUSHARE_ANNS_ASSET_NAME,
    dataset="anns",
    partition="daily",
    schema=TUSHARE_ANNS_SCHEMA,
)

TUSHARE_SUSPEND_D_ASSET = _tushare_asset_spec(
    name=TUSHARE_SUSPEND_D_ASSET_NAME,
    dataset="suspend_d",
    partition="daily",
    schema=TUSHARE_SUSPEND_D_SCHEMA,
)

TUSHARE_DIVIDEND_ASSET = _tushare_asset_spec(
    name=TUSHARE_DIVIDEND_ASSET_NAME,
    dataset="dividend",
    partition="daily",
    schema=TUSHARE_DIVIDEND_SCHEMA,
)

TUSHARE_SHARE_FLOAT_ASSET = _tushare_asset_spec(
    name=TUSHARE_SHARE_FLOAT_ASSET_NAME,
    dataset="share_float",
    partition="daily",
    schema=TUSHARE_SHARE_FLOAT_SCHEMA,
)

TUSHARE_STK_HOLDERNUMBER_ASSET = _tushare_asset_spec(
    name=TUSHARE_STK_HOLDERNUMBER_ASSET_NAME,
    dataset="stk_holdernumber",
    partition="daily",
    schema=TUSHARE_STK_HOLDERNUMBER_SCHEMA,
)

TUSHARE_DISCLOSURE_DATE_ASSET = _tushare_asset_spec(
    name=TUSHARE_DISCLOSURE_DATE_ASSET_NAME,
    dataset="disclosure_date",
    partition="daily",
    schema=TUSHARE_DISCLOSURE_DATE_SCHEMA,
)

TUSHARE_INCOME_ASSET = _tushare_asset_spec(
    name=TUSHARE_INCOME_ASSET_NAME,
    dataset="income",
    partition="daily",
    schema=TUSHARE_INCOME_SCHEMA,
)

TUSHARE_BALANCESHEET_ASSET = _tushare_asset_spec(
    name=TUSHARE_BALANCESHEET_ASSET_NAME,
    dataset="balancesheet",
    partition="daily",
    schema=TUSHARE_BALANCESHEET_SCHEMA,
)

TUSHARE_CASHFLOW_ASSET = _tushare_asset_spec(
    name=TUSHARE_CASHFLOW_ASSET_NAME,
    dataset="cashflow",
    partition="daily",
    schema=TUSHARE_CASHFLOW_SCHEMA,
)

TUSHARE_FINA_INDICATOR_ASSET = _tushare_asset_spec(
    name=TUSHARE_FINA_INDICATOR_ASSET_NAME,
    dataset="fina_indicator",
    partition="daily",
    schema=TUSHARE_FINA_INDICATOR_SCHEMA,
)

# Plan §5 expansion: 4 new AssetSpec instances — appended below
# existing 24 so downstream list iteration order is stable for the
# older datasets.
TUSHARE_STK_LIMIT_ASSET = _tushare_asset_spec(
    name=TUSHARE_STK_LIMIT_ASSET_NAME,
    dataset="stk_limit",
    partition="daily",
    schema=TUSHARE_STK_LIMIT_SCHEMA,
)

TUSHARE_BLOCK_TRADE_ASSET = _tushare_asset_spec(
    name=TUSHARE_BLOCK_TRADE_ASSET_NAME,
    dataset="block_trade",
    partition="daily",
    schema=TUSHARE_BLOCK_TRADE_SCHEMA,
)

TUSHARE_MONEYFLOW_ASSET = _tushare_asset_spec(
    name=TUSHARE_MONEYFLOW_ASSET_NAME,
    dataset="moneyflow",
    partition="daily",
    schema=TUSHARE_MONEYFLOW_SCHEMA,
)

TUSHARE_FORECAST_ASSET = _tushare_asset_spec(
    name=TUSHARE_FORECAST_ASSET_NAME,
    dataset="forecast",
    partition="daily",
    schema=TUSHARE_FORECAST_SCHEMA,
)

# M1.13 expansion: 8 new AssetSpec instances for the candidate event_timeline
# sources promoted in this round (precondition 9 closure). Appended last so
# downstream list-iteration order is stable for the older 28 assets.
TUSHARE_PLEDGE_STAT_ASSET = _tushare_asset_spec(
    name=TUSHARE_PLEDGE_STAT_ASSET_NAME,
    dataset="pledge_stat",
    partition="daily",
    schema=TUSHARE_PLEDGE_STAT_SCHEMA,
)

TUSHARE_PLEDGE_DETAIL_ASSET = _tushare_asset_spec(
    name=TUSHARE_PLEDGE_DETAIL_ASSET_NAME,
    dataset="pledge_detail",
    partition="daily",
    schema=TUSHARE_PLEDGE_DETAIL_SCHEMA,
)

TUSHARE_REPURCHASE_ASSET = _tushare_asset_spec(
    name=TUSHARE_REPURCHASE_ASSET_NAME,
    dataset="repurchase",
    partition="daily",
    schema=TUSHARE_REPURCHASE_SCHEMA,
)

TUSHARE_STK_HOLDERTRADE_ASSET = _tushare_asset_spec(
    name=TUSHARE_STK_HOLDERTRADE_ASSET_NAME,
    dataset="stk_holdertrade",
    partition="daily",
    schema=TUSHARE_STK_HOLDERTRADE_SCHEMA,
)

TUSHARE_STK_SURV_ASSET = _tushare_asset_spec(
    name=TUSHARE_STK_SURV_ASSET_NAME,
    dataset="stk_surv",
    partition="daily",
    schema=TUSHARE_STK_SURV_SCHEMA,
)

TUSHARE_LIMIT_LIST_THS_ASSET = _tushare_asset_spec(
    name=TUSHARE_LIMIT_LIST_THS_ASSET_NAME,
    dataset="limit_list_ths",
    partition="daily",
    schema=TUSHARE_LIMIT_LIST_THS_SCHEMA,
)

TUSHARE_LIMIT_LIST_D_ASSET = _tushare_asset_spec(
    name=TUSHARE_LIMIT_LIST_D_ASSET_NAME,
    dataset="limit_list_d",
    partition="daily",
    schema=TUSHARE_LIMIT_LIST_D_SCHEMA,
)

TUSHARE_HM_DETAIL_ASSET = _tushare_asset_spec(
    name=TUSHARE_HM_DETAIL_ASSET_NAME,
    dataset="hm_detail",
    partition="daily",
    schema=TUSHARE_HM_DETAIL_SCHEMA,
)

TUSHARE_TOP10_HOLDERS_ASSET = _tushare_asset_spec(
    name=TUSHARE_TOP10_HOLDERS_ASSET_NAME,
    dataset="top10_holders",
    partition="daily",
    schema=TUSHARE_TOP10_HOLDERS_SCHEMA,
)

TUSHARE_TOP10_FLOATHOLDERS_ASSET = _tushare_asset_spec(
    name=TUSHARE_TOP10_FLOATHOLDERS_ASSET_NAME,
    dataset="top10_floatholders",
    partition="daily",
    schema=TUSHARE_TOP10_FLOATHOLDERS_SCHEMA,
)

TUSHARE_FUND_PORTFOLIO_ASSET = _tushare_asset_spec(
    name=TUSHARE_FUND_PORTFOLIO_ASSET_NAME,
    dataset="fund_portfolio",
    partition="daily",
    schema=TUSHARE_FUND_PORTFOLIO_SCHEMA,
)

TUSHARE_HSGT_TOP10_ASSET = _tushare_asset_spec(
    name=TUSHARE_HSGT_TOP10_ASSET_NAME,
    dataset="hsgt_top10",
    partition="daily",
    schema=TUSHARE_HSGT_TOP10_SCHEMA,
)

TUSHARE_HSGT_HOLD_TOP10_ASSET = _tushare_asset_spec(
    name=TUSHARE_HSGT_HOLD_TOP10_ASSET_NAME,
    dataset="hsgt_hold_top10",
    partition="daily",
    schema=TUSHARE_HSGT_HOLD_TOP10_SCHEMA,
)

TUSHARE_ASSETS = [
    TUSHARE_STOCK_BASIC_ASSET,
    TUSHARE_DAILY_ASSET,
    TUSHARE_WEEKLY_ASSET,
    TUSHARE_MONTHLY_ASSET,
    TUSHARE_ADJ_FACTOR_ASSET,
    TUSHARE_DAILY_BASIC_ASSET,
    TUSHARE_INDEX_BASIC_ASSET,
    TUSHARE_INDEX_DAILY_ASSET,
    TUSHARE_INDEX_WEIGHT_ASSET,
    TUSHARE_INDEX_MEMBER_ASSET,
    TUSHARE_INDEX_CLASSIFY_ASSET,
    TUSHARE_TRADE_CAL_ASSET,
    TUSHARE_STOCK_COMPANY_ASSET,
    TUSHARE_NAMECHANGE_ASSET,
    TUSHARE_ANNS_ASSET,
    TUSHARE_SUSPEND_D_ASSET,
    TUSHARE_DIVIDEND_ASSET,
    TUSHARE_SHARE_FLOAT_ASSET,
    TUSHARE_STK_HOLDERNUMBER_ASSET,
    TUSHARE_DISCLOSURE_DATE_ASSET,
    TUSHARE_INCOME_ASSET,
    TUSHARE_BALANCESHEET_ASSET,
    TUSHARE_CASHFLOW_ASSET,
    TUSHARE_FINA_INDICATOR_ASSET,
    # Plan §5 expansion
    TUSHARE_STK_LIMIT_ASSET,
    TUSHARE_BLOCK_TRADE_ASSET,
    TUSHARE_MONEYFLOW_ASSET,
    TUSHARE_FORECAST_ASSET,
    # M1.13 expansion (precondition 9 closure)
    TUSHARE_PLEDGE_STAT_ASSET,
    TUSHARE_PLEDGE_DETAIL_ASSET,
    TUSHARE_REPURCHASE_ASSET,
    TUSHARE_STK_HOLDERTRADE_ASSET,
    TUSHARE_STK_SURV_ASSET,
    TUSHARE_LIMIT_LIST_THS_ASSET,
    TUSHARE_LIMIT_LIST_D_ASSET,
    TUSHARE_HM_DETAIL_ASSET,
    # M4.5 holdings intake expansion.
    TUSHARE_TOP10_HOLDERS_ASSET,
    TUSHARE_TOP10_FLOATHOLDERS_ASSET,
    TUSHARE_FUND_PORTFOLIO_ASSET,
    TUSHARE_HSGT_TOP10_ASSET,
    TUSHARE_HSGT_HOLD_TOP10_ASSET,
]

__all__ = [
    "ALLOW_NULL_IDENTITY_METADATA_KEY",
    "ALLOW_NULL_IDENTITY_METADATA_VALUE",
    "EVENT_METADATA_FIELDS",
    "FINANCIAL_DATASET_FIELDS",
    "FINANCIAL_VERSION_FIELDS",
    "REFERENCE_DATA_IDENTITY_FIELDS",
    "TUSHARE_ADJ_FACTOR_ASSET",
    "TUSHARE_ADJ_FACTOR_ASSET_NAME",
    "TUSHARE_ADJ_FACTOR_FIELDS",
    "TUSHARE_ADJ_FACTOR_FIELDS_CSV",
    "TUSHARE_ADJ_FACTOR_SCHEMA",
    "TUSHARE_ANNS_ASSET",
    "TUSHARE_ANNS_ASSET_NAME",
    "TUSHARE_ANNS_FIELDS",
    "TUSHARE_ANNS_FIELDS_CSV",
    "TUSHARE_ANNS_SCHEMA",
    "TUSHARE_ASSETS",
    "TUSHARE_BALANCESHEET_ASSET",
    "TUSHARE_BALANCESHEET_ASSET_NAME",
    "TUSHARE_BALANCESHEET_FIELDS",
    "TUSHARE_BALANCESHEET_FIELDS_CSV",
    "TUSHARE_BALANCESHEET_NUMERIC_FIELDS",
    "TUSHARE_BALANCESHEET_SCHEMA",
    "TUSHARE_BAR_FIELDS",
    "TUSHARE_BAR_FIELDS_CSV",
    "TUSHARE_BAR_SCHEMA",
    "TUSHARE_CASHFLOW_ASSET",
    "TUSHARE_CASHFLOW_ASSET_NAME",
    "TUSHARE_CASHFLOW_FIELDS",
    "TUSHARE_CASHFLOW_FIELDS_CSV",
    "TUSHARE_CASHFLOW_NUMERIC_FIELDS",
    "TUSHARE_CASHFLOW_SCHEMA",
    "TUSHARE_DAILY_ASSET",
    "TUSHARE_DAILY_ASSET_NAME",
    "TUSHARE_DAILY_BASIC_ASSET",
    "TUSHARE_DAILY_BASIC_ASSET_NAME",
    "TUSHARE_DAILY_BASIC_FIELDS",
    "TUSHARE_DAILY_BASIC_FIELDS_CSV",
    "TUSHARE_DAILY_BASIC_SCHEMA",
    "TUSHARE_DISCLOSURE_DATE_ASSET",
    "TUSHARE_DISCLOSURE_DATE_ASSET_NAME",
    "TUSHARE_DISCLOSURE_DATE_FIELDS",
    "TUSHARE_DISCLOSURE_DATE_FIELDS_CSV",
    "TUSHARE_DISCLOSURE_DATE_SCHEMA",
    "TUSHARE_DIVIDEND_ASSET",
    "TUSHARE_DIVIDEND_ASSET_NAME",
    "TUSHARE_DIVIDEND_FIELDS",
    "TUSHARE_DIVIDEND_FIELDS_CSV",
    "TUSHARE_DIVIDEND_SCHEMA",
    "TUSHARE_FINA_INDICATOR_ASSET",
    "TUSHARE_FINA_INDICATOR_ASSET_NAME",
    "TUSHARE_FINA_INDICATOR_FIELDS",
    "TUSHARE_FINA_INDICATOR_FIELDS_CSV",
    "TUSHARE_FINA_INDICATOR_NUMERIC_FIELDS",
    "TUSHARE_FINA_INDICATOR_SCHEMA",
    "TUSHARE_FINANCIAL_NUMERIC_TYPE",
    "TUSHARE_INCOME_ASSET",
    "TUSHARE_INCOME_ASSET_NAME",
    "TUSHARE_INCOME_FIELDS",
    "TUSHARE_INCOME_FIELDS_CSV",
    "TUSHARE_INCOME_NUMERIC_FIELDS",
    "TUSHARE_INCOME_SCHEMA",
    "TUSHARE_INDEX_BASIC_ASSET",
    "TUSHARE_INDEX_BASIC_ASSET_NAME",
    "TUSHARE_INDEX_BASIC_FIELDS",
    "TUSHARE_INDEX_BASIC_FIELDS_CSV",
    "TUSHARE_INDEX_BASIC_SCHEMA",
    "TUSHARE_INDEX_CLASSIFY_ASSET",
    "TUSHARE_INDEX_CLASSIFY_ASSET_NAME",
    "TUSHARE_INDEX_CLASSIFY_FIELDS",
    "TUSHARE_INDEX_CLASSIFY_FIELDS_CSV",
    "TUSHARE_INDEX_CLASSIFY_SCHEMA",
    "TUSHARE_INDEX_DAILY_ASSET",
    "TUSHARE_INDEX_DAILY_ASSET_NAME",
    "TUSHARE_INDEX_DAILY_FIELDS",
    "TUSHARE_INDEX_DAILY_FIELDS_CSV",
    "TUSHARE_INDEX_DAILY_SCHEMA",
    "TUSHARE_INDEX_MEMBER_ASSET",
    "TUSHARE_INDEX_MEMBER_ASSET_NAME",
    "TUSHARE_INDEX_MEMBER_FIELDS",
    "TUSHARE_INDEX_MEMBER_FIELDS_CSV",
    "TUSHARE_INDEX_MEMBER_SCHEMA",
    "TUSHARE_INDEX_WEIGHT_ASSET",
    "TUSHARE_INDEX_WEIGHT_ASSET_NAME",
    "TUSHARE_INDEX_WEIGHT_FIELDS",
    "TUSHARE_INDEX_WEIGHT_FIELDS_CSV",
    "TUSHARE_INDEX_WEIGHT_SCHEMA",
    "TUSHARE_MONTHLY_ASSET",
    "TUSHARE_MONTHLY_ASSET_NAME",
    "TUSHARE_NAMECHANGE_ASSET",
    "TUSHARE_NAMECHANGE_ASSET_NAME",
    "TUSHARE_NAMECHANGE_FIELDS",
    "TUSHARE_NAMECHANGE_FIELDS_CSV",
    "TUSHARE_NAMECHANGE_SCHEMA",
    "TUSHARE_SHARE_FLOAT_ASSET",
    "TUSHARE_SHARE_FLOAT_ASSET_NAME",
    "TUSHARE_SHARE_FLOAT_FIELDS",
    "TUSHARE_SHARE_FLOAT_FIELDS_CSV",
    "TUSHARE_SHARE_FLOAT_SCHEMA",
    "TUSHARE_STOCK_BASIC_ASSET",
    "TUSHARE_STOCK_BASIC_ASSET_NAME",
    "TUSHARE_STOCK_BASIC_FIELDS",
    "TUSHARE_STOCK_BASIC_FIELDS_CSV",
    "TUSHARE_STOCK_BASIC_SCHEMA",
    "TUSHARE_STOCK_COMPANY_ASSET",
    "TUSHARE_STOCK_COMPANY_ASSET_NAME",
    "TUSHARE_STOCK_COMPANY_FIELDS",
    "TUSHARE_STOCK_COMPANY_FIELDS_CSV",
    "TUSHARE_STOCK_COMPANY_SCHEMA",
    "TUSHARE_STK_HOLDERNUMBER_ASSET",
    "TUSHARE_STK_HOLDERNUMBER_ASSET_NAME",
    "TUSHARE_STK_HOLDERNUMBER_FIELDS",
    "TUSHARE_STK_HOLDERNUMBER_FIELDS_CSV",
    "TUSHARE_STK_HOLDERNUMBER_SCHEMA",
    "TUSHARE_SUSPEND_D_ASSET",
    "TUSHARE_SUSPEND_D_ASSET_NAME",
    "TUSHARE_SUSPEND_D_FIELDS",
    "TUSHARE_SUSPEND_D_FIELDS_CSV",
    "TUSHARE_SUSPEND_D_SCHEMA",
    "TUSHARE_TRADE_CAL_ASSET",
    "TUSHARE_TRADE_CAL_ASSET_NAME",
    "TUSHARE_TRADE_CAL_FIELDS",
    "TUSHARE_TRADE_CAL_FIELDS_CSV",
    "TUSHARE_TRADE_CAL_SCHEMA",
    "TUSHARE_WEEKLY_ASSET",
    "TUSHARE_WEEKLY_ASSET_NAME",
    # Plan §5 expansion — 4 new datasets (stk_limit / block_trade /
    # moneyflow / forecast) + forecast family containers.
    "FORECAST_DATASET_FIELDS",
    "FORECAST_VERSION_FIELDS",
    "HOLDINGS_DATASET_FIELDS",
    "TUSHARE_BLOCK_TRADE_ASSET",
    "TUSHARE_BLOCK_TRADE_ASSET_NAME",
    "TUSHARE_BLOCK_TRADE_FIELDS",
    "TUSHARE_BLOCK_TRADE_FIELDS_CSV",
    "TUSHARE_BLOCK_TRADE_SCHEMA",
    "TUSHARE_FORECAST_ASSET",
    "TUSHARE_FORECAST_ASSET_NAME",
    "TUSHARE_FORECAST_FIELDS",
    "TUSHARE_FORECAST_FIELDS_CSV",
    "TUSHARE_FORECAST_SCHEMA",
    "TUSHARE_MONEYFLOW_ASSET",
    "TUSHARE_MONEYFLOW_ASSET_NAME",
    "TUSHARE_MONEYFLOW_FIELDS",
    "TUSHARE_MONEYFLOW_FIELDS_CSV",
    "TUSHARE_MONEYFLOW_SCHEMA",
    "TUSHARE_STK_LIMIT_ASSET",
    "TUSHARE_STK_LIMIT_ASSET_NAME",
    "TUSHARE_STK_LIMIT_FIELDS",
    "TUSHARE_STK_LIMIT_FIELDS_CSV",
    "TUSHARE_STK_LIMIT_SCHEMA",
    # M1.13 expansion — 8 candidate event_timeline sources promoted.
    "TUSHARE_HM_DETAIL_ASSET",
    "TUSHARE_HM_DETAIL_ASSET_NAME",
    "TUSHARE_HM_DETAIL_FIELDS",
    "TUSHARE_HM_DETAIL_FIELDS_CSV",
    "TUSHARE_HM_DETAIL_SCHEMA",
    "TUSHARE_FUND_PORTFOLIO_ASSET",
    "TUSHARE_FUND_PORTFOLIO_ASSET_NAME",
    "TUSHARE_FUND_PORTFOLIO_FIELDS",
    "TUSHARE_FUND_PORTFOLIO_FIELDS_CSV",
    "TUSHARE_FUND_PORTFOLIO_SCHEMA",
    "TUSHARE_HSGT_HOLD_TOP10_ASSET",
    "TUSHARE_HSGT_HOLD_TOP10_ASSET_NAME",
    "TUSHARE_HSGT_HOLD_TOP10_FIELDS",
    "TUSHARE_HSGT_HOLD_TOP10_FIELDS_CSV",
    "TUSHARE_HSGT_HOLD_TOP10_SCHEMA",
    "TUSHARE_HSGT_TOP10_ASSET",
    "TUSHARE_HSGT_TOP10_ASSET_NAME",
    "TUSHARE_HSGT_TOP10_FIELDS",
    "TUSHARE_HSGT_TOP10_FIELDS_CSV",
    "TUSHARE_HSGT_TOP10_SCHEMA",
    "TUSHARE_LIMIT_LIST_D_ASSET",
    "TUSHARE_LIMIT_LIST_D_ASSET_NAME",
    "TUSHARE_LIMIT_LIST_D_FIELDS",
    "TUSHARE_LIMIT_LIST_D_FIELDS_CSV",
    "TUSHARE_LIMIT_LIST_D_SCHEMA",
    "TUSHARE_LIMIT_LIST_THS_ASSET",
    "TUSHARE_LIMIT_LIST_THS_ASSET_NAME",
    "TUSHARE_LIMIT_LIST_THS_FIELDS",
    "TUSHARE_LIMIT_LIST_THS_FIELDS_CSV",
    "TUSHARE_LIMIT_LIST_THS_SCHEMA",
    "TUSHARE_PLEDGE_DETAIL_ASSET",
    "TUSHARE_PLEDGE_DETAIL_ASSET_NAME",
    "TUSHARE_PLEDGE_DETAIL_FIELDS",
    "TUSHARE_PLEDGE_DETAIL_FIELDS_CSV",
    "TUSHARE_PLEDGE_DETAIL_SCHEMA",
    "TUSHARE_PLEDGE_STAT_ASSET",
    "TUSHARE_PLEDGE_STAT_ASSET_NAME",
    "TUSHARE_PLEDGE_STAT_FIELDS",
    "TUSHARE_PLEDGE_STAT_FIELDS_CSV",
    "TUSHARE_PLEDGE_STAT_SCHEMA",
    "TUSHARE_REPURCHASE_ASSET",
    "TUSHARE_REPURCHASE_ASSET_NAME",
    "TUSHARE_REPURCHASE_FIELDS",
    "TUSHARE_REPURCHASE_FIELDS_CSV",
    "TUSHARE_REPURCHASE_SCHEMA",
    "TUSHARE_STK_HOLDERTRADE_ASSET",
    "TUSHARE_STK_HOLDERTRADE_ASSET_NAME",
    "TUSHARE_STK_HOLDERTRADE_FIELDS",
    "TUSHARE_STK_HOLDERTRADE_FIELDS_CSV",
    "TUSHARE_STK_HOLDERTRADE_SCHEMA",
    "TUSHARE_STK_SURV_ASSET",
    "TUSHARE_STK_SURV_ASSET_NAME",
    "TUSHARE_STK_SURV_FIELDS",
    "TUSHARE_STK_SURV_FIELDS_CSV",
    "TUSHARE_STK_SURV_SCHEMA",
    "TUSHARE_TOP10_FLOATHOLDERS_ASSET",
    "TUSHARE_TOP10_FLOATHOLDERS_ASSET_NAME",
    "TUSHARE_TOP10_FLOATHOLDERS_FIELDS",
    "TUSHARE_TOP10_FLOATHOLDERS_FIELDS_CSV",
    "TUSHARE_TOP10_FLOATHOLDERS_SCHEMA",
    "TUSHARE_TOP10_HOLDERS_ASSET",
    "TUSHARE_TOP10_HOLDERS_ASSET_NAME",
    "TUSHARE_TOP10_HOLDERS_FIELDS",
    "TUSHARE_TOP10_HOLDERS_FIELDS_CSV",
    "TUSHARE_TOP10_HOLDERS_SCHEMA",
]
