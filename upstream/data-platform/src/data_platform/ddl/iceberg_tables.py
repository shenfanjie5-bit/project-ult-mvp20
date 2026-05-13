"""Iceberg table registration for Canonical/Formal/Analytical storage points."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Final, Sequence

import pyarrow as pa  # type: ignore[import-untyped]
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.partitioning import PartitionSpec
from pyiceberg.table import Table

from data_platform.serving.catalog import (
    DEFAULT_NAMESPACES,
    RAW_NAMESPACE,
    ensure_namespaces,
    load_catalog,
)


FORBIDDEN_SCHEMA_FIELDS: Final[frozenset[str]] = frozenset(
    {"submitted_at", "ingest_seq", "source_run_id", "raw_loaded_at"}
)
"""Columns that must never appear on canonical Iceberg specs.

Includes both Layer-B ingest-queue fields and raw-zone lineage fields.
The `canonical_lineage.*` namespace legitimately carries the lineage
block, so the bypass at `_forbidden_schema_fields_for` strips those from
the forbidden set when the spec lives in `canonical_lineage`.
"""

_CANONICAL_LINEAGE_NAMESPACE: Final[str] = "canonical_lineage"
_CANONICAL_LINEAGE_ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(
    {"source_run_id", "raw_loaded_at"}
)


def _forbidden_schema_fields_for(namespace: str) -> frozenset[str]:
    """Return the forbidden-schema-fields set for one Iceberg namespace.

    Canonical_lineage.* legitimately carries `source_run_id` /
    `raw_loaded_at`; the ingest-queue boundary still applies there.
    """

    if namespace == _CANONICAL_LINEAGE_NAMESPACE:
        return FORBIDDEN_SCHEMA_FIELDS - _CANONICAL_LINEAGE_ALLOWED_FIELDS
    return FORBIDDEN_SCHEMA_FIELDS
CANONICAL_NAMESPACE: Final[str] = "canonical"
CANONICAL_V2_NAMESPACE: Final[str] = "canonical_v2"
CANONICAL_LINEAGE_NAMESPACE: Final[str] = "canonical_lineage"
TIMESTAMP_TYPE: Final[pa.TimestampType] = pa.timestamp("us")
DECIMAL_TYPE: Final[pa.Decimal128Type] = pa.decimal128(38, 18)


@dataclass(frozen=True, slots=True)
class TableSpec:
    """Declarative Iceberg table storage point."""

    namespace: str
    name: str
    schema: pa.Schema
    partition_by: list[str] | None = None
    properties: dict[str, str] | None = None

    def __post_init__(self) -> None:
        namespace = self.namespace.strip()
        name = self.name.strip()
        if not namespace:
            msg = "Iceberg table namespace must not be empty"
            raise ValueError(msg)
        if not name:
            msg = "Iceberg table name must not be empty"
            raise ValueError(msg)
        if namespace.split(".", maxsplit=1)[0].lower() == RAW_NAMESPACE:
            msg = "raw namespace must not be created in the Iceberg catalog"
            raise ValueError(msg)

        forbidden_fields = sorted(
            _forbidden_schema_fields_for(namespace).intersection(
                field_name.lower() for field_name in self.schema.names
            )
        )
        if forbidden_fields:
            msg = "Iceberg table schema must not include forbidden schema fields: "
            raise ValueError(msg + ", ".join(forbidden_fields))

        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "name", name)
        if self.partition_by is not None:
            object.__setattr__(self, "partition_by", list(self.partition_by))
        if self.properties is not None:
            object.__setattr__(self, "properties", dict(self.properties))


CANONICAL_ENTITY_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_NAMESPACE,
    name="canonical_entity",
    schema=pa.schema(
        [
            pa.field("canonical_entity_id", pa.string()),
            pa.field("created_at", TIMESTAMP_TYPE),
        ]
    ),
)

ENTITY_ALIAS_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_NAMESPACE,
    name="entity_alias",
    schema=pa.schema(
        [
            pa.field("alias", pa.string()),
            pa.field("canonical_entity_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("created_at", TIMESTAMP_TYPE),
        ]
    ),
)

# ---------------------------------------------------------------------------
# Canonical V2 namespace.
#
# Provider-neutral by construction: canonical identifiers
# (security_id / index_id / entity_id) instead of provider-shaped names;
# raw-zone lineage columns (source_run_id / raw_loaded_at) move to
# canonical_lineage. Per M1-A design
# (`assembly/reports/stabilization/canonical-v2-lineage-separation-design-20260428.md`)
# and M1-B spike (`p1-iceberg-write-chain-spike-proof-20260428.md`).
#
# Coverage: 11 mart tables (dim_security, stock_basic, dim_index,
# fact_price_bar, fact_financial_indicator, fact_market_daily_feature,
# fact_index_price_bar, fact_forecast_event, fact_event,
# fact_holding_position, fact_northbound_turnover). fact_event currently
# covers 8 source interfaces after M1.8 block_trade promotion. Legacy
# `canonical.*` namespace remains active until retirement readiness
# pre-conditions close (see m1-legacy-canonical-retirement-readiness-20260428.md).
# ---------------------------------------------------------------------------

CANONICAL_V2_DIM_SECURITY_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="dim_security",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("symbol", pa.string()),
            pa.field("display_name", pa.string()),
            pa.field("market", pa.string()),
            pa.field("industry", pa.string()),
            pa.field("list_date", pa.date32()),
            pa.field("is_active", pa.bool_()),
            pa.field("area", pa.string()),
            pa.field("fullname", pa.string()),
            pa.field("exchange", pa.string()),
            pa.field("curr_type", pa.string()),
            pa.field("list_status", pa.string()),
            pa.field("delist_date", pa.date32()),
            pa.field("setup_date", pa.date32()),
            pa.field("province", pa.string()),
            pa.field("city", pa.string()),
            pa.field("reg_capital", DECIMAL_TYPE),
            pa.field("employees", DECIMAL_TYPE),
            pa.field("main_business", pa.string()),
            pa.field("latest_namechange_name", pa.string()),
            pa.field("latest_namechange_start_date", pa.date32()),
            pa.field("latest_namechange_end_date", pa.date32()),
            pa.field("latest_namechange_ann_date", pa.date32()),
            pa.field("latest_namechange_reason", pa.string()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_STOCK_BASIC_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="stock_basic",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("symbol", pa.string()),
            pa.field("display_name", pa.string()),
            pa.field("area", pa.string()),
            pa.field("industry", pa.string()),
            pa.field("market", pa.string()),
            pa.field("list_date", pa.date32()),
            pa.field("is_active", pa.bool_()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_DIM_INDEX_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="dim_index",
    schema=pa.schema(
        [
            pa.field("index_id", pa.string()),
            pa.field("index_name", pa.string()),
            pa.field("index_market", pa.string()),
            pa.field("index_category", pa.string()),
            pa.field("first_effective_date", pa.date32()),
            pa.field("latest_effective_date", pa.date32()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_FACT_PRICE_BAR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_price_bar",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("freq", pa.string()),
            pa.field("open", DECIMAL_TYPE),
            pa.field("high", DECIMAL_TYPE),
            pa.field("low", DECIMAL_TYPE),
            pa.field("close", DECIMAL_TYPE),
            pa.field("pre_close", DECIMAL_TYPE),
            pa.field("change", DECIMAL_TYPE),
            pa.field("pct_chg", DECIMAL_TYPE),
            pa.field("vol", DECIMAL_TYPE),
            pa.field("amount", DECIMAL_TYPE),
            pa.field("adj_factor", DECIMAL_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_V2_FACT_FINANCIAL_INDICATOR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_financial_indicator",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("end_date", pa.date32()),
            pa.field("ann_date", pa.date32()),
            pa.field("f_ann_date", pa.date32()),
            pa.field("report_type", pa.string()),
            pa.field("comp_type", pa.string()),
            pa.field("update_flag", pa.string()),
            pa.field("is_latest", pa.bool_()),
            pa.field("basic_eps", DECIMAL_TYPE),
            pa.field("diluted_eps", DECIMAL_TYPE),
            pa.field("total_revenue", DECIMAL_TYPE),
            pa.field("revenue", DECIMAL_TYPE),
            pa.field("operate_profit", DECIMAL_TYPE),
            pa.field("total_profit", DECIMAL_TYPE),
            pa.field("n_income", DECIMAL_TYPE),
            pa.field("n_income_attr_p", DECIMAL_TYPE),
            pa.field("money_cap", DECIMAL_TYPE),
            pa.field("total_cur_assets", DECIMAL_TYPE),
            pa.field("total_assets", DECIMAL_TYPE),
            pa.field("total_cur_liab", DECIMAL_TYPE),
            pa.field("total_liab", DECIMAL_TYPE),
            pa.field("total_hldr_eqy_exc_min_int", DECIMAL_TYPE),
            pa.field("total_liab_hldr_eqy", DECIMAL_TYPE),
            pa.field("net_profit", DECIMAL_TYPE),
            pa.field("n_cashflow_act", DECIMAL_TYPE),
            pa.field("n_cashflow_inv_act", DECIMAL_TYPE),
            pa.field("n_cash_flows_fnc_act", DECIMAL_TYPE),
            pa.field("n_incr_cash_cash_equ", DECIMAL_TYPE),
            pa.field("free_cashflow", DECIMAL_TYPE),
            pa.field("eps", DECIMAL_TYPE),
            pa.field("dt_eps", DECIMAL_TYPE),
            pa.field("grossprofit_margin", DECIMAL_TYPE),
            pa.field("netprofit_margin", DECIMAL_TYPE),
            pa.field("roe", DECIMAL_TYPE),
            pa.field("roa", DECIMAL_TYPE),
            pa.field("debt_to_assets", DECIMAL_TYPE),
            pa.field("or_yoy", DECIMAL_TYPE),
            pa.field("netprofit_yoy", DECIMAL_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

# NOTE: canonical_v2.fact_event is defined later (after fact_forecast_event).
# It currently covers 8 source interfaces in int_event_timeline.sql (anns,
# suspend_d, dividend, share_float, stk_holdernumber, disclosure_date,
# namechange, block_trade). The 8 candidate Tushare sources remain
# BLOCKED_NO_STAGING.

CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_market_daily_feature",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("close", DECIMAL_TYPE),
            pa.field("turnover_rate", DECIMAL_TYPE),
            pa.field("turnover_rate_f", DECIMAL_TYPE),
            pa.field("volume_ratio", DECIMAL_TYPE),
            pa.field("pe", DECIMAL_TYPE),
            pa.field("pe_ttm", DECIMAL_TYPE),
            pa.field("pb", DECIMAL_TYPE),
            pa.field("ps", DECIMAL_TYPE),
            pa.field("ps_ttm", DECIMAL_TYPE),
            pa.field("dv_ratio", DECIMAL_TYPE),
            pa.field("dv_ttm", DECIMAL_TYPE),
            pa.field("total_share", DECIMAL_TYPE),
            pa.field("float_share", DECIMAL_TYPE),
            pa.field("free_share", DECIMAL_TYPE),
            pa.field("total_mv", DECIMAL_TYPE),
            pa.field("circ_mv", DECIMAL_TYPE),
            pa.field("up_limit", DECIMAL_TYPE),
            pa.field("down_limit", DECIMAL_TYPE),
            pa.field("buy_sm_vol", DECIMAL_TYPE),
            pa.field("buy_sm_amount", DECIMAL_TYPE),
            pa.field("sell_sm_vol", DECIMAL_TYPE),
            pa.field("sell_sm_amount", DECIMAL_TYPE),
            pa.field("buy_md_vol", DECIMAL_TYPE),
            pa.field("buy_md_amount", DECIMAL_TYPE),
            pa.field("sell_md_vol", DECIMAL_TYPE),
            pa.field("sell_md_amount", DECIMAL_TYPE),
            pa.field("buy_lg_vol", DECIMAL_TYPE),
            pa.field("buy_lg_amount", DECIMAL_TYPE),
            pa.field("sell_lg_vol", DECIMAL_TYPE),
            pa.field("sell_lg_amount", DECIMAL_TYPE),
            pa.field("buy_elg_vol", DECIMAL_TYPE),
            pa.field("buy_elg_amount", DECIMAL_TYPE),
            pa.field("sell_elg_vol", DECIMAL_TYPE),
            pa.field("sell_elg_amount", DECIMAL_TYPE),
            pa.field("net_mf_vol", DECIMAL_TYPE),
            pa.field("net_mf_amount", DECIMAL_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_V2_FACT_INDEX_PRICE_BAR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_index_price_bar",
    schema=pa.schema(
        [
            pa.field("index_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("open", DECIMAL_TYPE),
            pa.field("high", DECIMAL_TYPE),
            pa.field("low", DECIMAL_TYPE),
            pa.field("close", DECIMAL_TYPE),
            pa.field("pre_close", DECIMAL_TYPE),
            pa.field("change", DECIMAL_TYPE),
            pa.field("pct_chg", DECIMAL_TYPE),
            pa.field("vol", DECIMAL_TYPE),
            pa.field("amount", DECIMAL_TYPE),
            pa.field("exchange", pa.string()),
            pa.field("is_open", pa.bool_()),
            pa.field("pretrade_date", pa.date32()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_V2_FACT_FORECAST_EVENT_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_forecast_event",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("announcement_date", pa.date32()),
            pa.field("report_period", pa.date32()),
            pa.field("forecast_type", pa.string()),
            pa.field("p_change_min", DECIMAL_TYPE),
            pa.field("p_change_max", DECIMAL_TYPE),
            pa.field("net_profit_min", DECIMAL_TYPE),
            pa.field("net_profit_max", DECIMAL_TYPE),
            pa.field("last_parent_net", DECIMAL_TYPE),
            pa.field("first_ann_date", pa.date32()),
            pa.field("summary", pa.string()),
            pa.field("change_reason", pa.string()),
            pa.field("update_flag", pa.string()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

# Provider-neutral event fact. Covers 8 sources currently in
# int_event_timeline.sql: anns ('announcement'), suspend_d ('suspend'),
# dividend, share_float, stk_holdernumber ('holder_number'), disclosure_date,
# namechange ('name_change'), and block_trade. The 8 candidate sources remain
# BLOCKED_NO_STAGING.
CANONICAL_V2_FACT_EVENT_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_event",
    schema=pa.schema(
        [
            pa.field("event_type", pa.string()),
            pa.field("entity_id", pa.string()),
            pa.field("event_date", pa.date32()),
            pa.field("event_key", pa.string()),
            pa.field("title", pa.string()),
            pa.field("summary", pa.string()),
            pa.field("event_subtype", pa.string()),
            pa.field("related_date", pa.date32()),
            pa.field("reference_url", pa.string()),
            pa.field("rec_time", pa.string()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_FACT_HOLDING_POSITION_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_holding_position",
    schema=pa.schema(
        [
            pa.field("holding_source", pa.string()),
            pa.field("holder_id", pa.string()),
            pa.field("holder_name", pa.string()),
            pa.field("holder_type", pa.string()),
            pa.field("security_id", pa.string()),
            pa.field("report_date", pa.date32()),
            pa.field("announced_date", pa.date32()),
            pa.field("holding_amount", DECIMAL_TYPE),
            pa.field("holding_ratio", DECIMAL_TYPE),
            pa.field("holding_float_ratio", DECIMAL_TYPE),
            pa.field("holding_change", DECIMAL_TYPE),
            pa.field("market_value", DECIMAL_TYPE),
            pa.field("exchange", pa.string()),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_V2_NAMESPACE,
    name="fact_northbound_turnover",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("security_name", pa.string()),
            pa.field("market_type", pa.string()),
            pa.field("rank", pa.int32()),
            pa.field("close", DECIMAL_TYPE),
            pa.field("change", DECIMAL_TYPE),
            pa.field("amount", DECIMAL_TYPE),
            pa.field("net_amount", DECIMAL_TYPE),
            pa.field("buy_amount", DECIMAL_TYPE),
            pa.field("sell_amount", DECIMAL_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_V2_TABLE_SPECS: Final[tuple[TableSpec, ...]] = (
    CANONICAL_V2_DIM_SECURITY_SPEC,
    CANONICAL_V2_STOCK_BASIC_SPEC,
    CANONICAL_V2_DIM_INDEX_SPEC,
    CANONICAL_V2_FACT_PRICE_BAR_SPEC,
    CANONICAL_V2_FACT_FINANCIAL_INDICATOR_SPEC,
    CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_SPEC,
    CANONICAL_V2_FACT_INDEX_PRICE_BAR_SPEC,
    CANONICAL_V2_FACT_FORECAST_EVENT_SPEC,
    CANONICAL_V2_FACT_EVENT_SPEC,
    CANONICAL_V2_FACT_HOLDING_POSITION_SPEC,
    CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_SPEC,
)

# ---------------------------------------------------------------------------
# Canonical lineage namespace.
#
# 1:1 sibling of canonical_v2 business rows on the canonical PK. Provider-
# aware lineage lives here so canonical business rows stay provider-neutral.
# ---------------------------------------------------------------------------

CANONICAL_LINEAGE_DIM_SECURITY_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_dim_security",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_STOCK_BASIC_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_stock_basic",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_DIM_INDEX_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_dim_index",
    schema=pa.schema(
        [
            pa.field("index_id", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_FACT_PRICE_BAR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_price_bar",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("freq", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_financial_indicator",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("end_date", pa.date32()),
            pa.field("report_type", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_market_daily_feature",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_index_price_bar",
    schema=pa.schema(
        [
            pa.field("index_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
    # NOTE: partition_by=["trade_date"] is deferred to M2.1 per M1-B §4.3
    # (FakeCatalog/PyIceberg pyarrow_to_schema needs field-id metadata that
    # the in-process test schemas do not carry; production wiring through a
    # real catalog will add partition spec via CTAS or table-evolve later).
)

CANONICAL_LINEAGE_FACT_FORECAST_EVENT_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_forecast_event",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("announcement_date", pa.date32()),
            pa.field("report_period", pa.date32()),
            pa.field("update_flag", pa.string()),
            pa.field("forecast_type", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

# Lineage sibling for canonical_v2.fact_event. Each row
# carries its true `source_interface_id` (per-row, not a composite string).
# See event-timeline-canonical-v2-derivation-rules-20260428.md.
CANONICAL_LINEAGE_FACT_EVENT_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_event",
    schema=pa.schema(
        [
            pa.field("event_type", pa.string()),
            pa.field("entity_id", pa.string()),
            pa.field("event_date", pa.date32()),
            pa.field("event_key", pa.string()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_FACT_HOLDING_POSITION_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_holding_position",
    schema=pa.schema(
        [
            pa.field("holding_source", pa.string()),
            pa.field("holder_id", pa.string()),
            pa.field("security_id", pa.string()),
            pa.field("report_date", pa.date32()),
            pa.field("announced_date", pa.date32()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_SPEC: Final[TableSpec] = TableSpec(
    namespace=CANONICAL_LINEAGE_NAMESPACE,
    name="lineage_fact_northbound_turnover",
    schema=pa.schema(
        [
            pa.field("security_id", pa.string()),
            pa.field("trade_date", pa.date32()),
            pa.field("market_type", pa.string()),
            pa.field("rank", pa.int32()),
            pa.field("source_provider", pa.string()),
            pa.field("source_interface_id", pa.string()),
            pa.field("source_run_id", pa.string()),
            pa.field("raw_loaded_at", TIMESTAMP_TYPE),
            pa.field("canonical_loaded_at", TIMESTAMP_TYPE),
        ]
    ),
)

CANONICAL_LINEAGE_TABLE_SPECS: Final[tuple[TableSpec, ...]] = (
    CANONICAL_LINEAGE_DIM_SECURITY_SPEC,
    CANONICAL_LINEAGE_STOCK_BASIC_SPEC,
    CANONICAL_LINEAGE_DIM_INDEX_SPEC,
    CANONICAL_LINEAGE_FACT_PRICE_BAR_SPEC,
    CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_SPEC,
    CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_SPEC,
    CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_SPEC,
    CANONICAL_LINEAGE_FACT_FORECAST_EVENT_SPEC,
    CANONICAL_LINEAGE_FACT_EVENT_SPEC,
    CANONICAL_LINEAGE_FACT_HOLDING_POSITION_SPEC,
    CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_SPEC,
)

DEFAULT_TABLE_SPECS: Final[tuple[TableSpec, ...]] = (
    CANONICAL_ENTITY_SPEC,
    ENTITY_ALIAS_SPEC,
    *CANONICAL_V2_TABLE_SPECS,
    *CANONICAL_LINEAGE_TABLE_SPECS,
)


def register_table(catalog: SqlCatalog, spec: TableSpec, replace: bool = False) -> Table:
    """Register one Iceberg table, creating its namespace first."""

    if replace:
        msg = (
            "replace=True is disabled for Iceberg table registration; use an "
            "atomic catalog replacement or an explicit migration tool instead"
        )
        raise NotImplementedError(msg)

    ensure_namespaces(catalog, [spec.namespace])
    identifier = _table_identifier(spec)

    return _create_table_if_not_exists(catalog, identifier, spec)


def ensure_tables(catalog: SqlCatalog, specs: Sequence[TableSpec]) -> list[Table]:
    """Idempotently ensure all requested Iceberg tables exist."""

    return [register_table(catalog, spec) for spec in specs]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure data-platform Iceberg namespaces and table storage points."
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="create missing namespaces and tables",
    )
    args = parser.parse_args(argv)

    if not args.ensure:
        parser.error("only --ensure is supported")

    try:
        catalog = load_catalog()
        ensure_namespaces(catalog, DEFAULT_NAMESPACES)
        ensure_tables(catalog, DEFAULT_TABLE_SPECS)
    except Exception as exc:
        print(f"failed to ensure Iceberg tables: {exc}", file=sys.stderr)
        return 1

    ensured_tables = ", ".join(_table_identifier(spec) for spec in DEFAULT_TABLE_SPECS)
    print(f"ensured Iceberg tables: {ensured_tables}")
    return 0


def _table_identifier(spec: TableSpec) -> str:
    return f"{spec.namespace}.{spec.name}"


def _create_table(catalog: SqlCatalog, identifier: str, spec: TableSpec) -> Table:
    properties = spec.properties or {}
    if spec.partition_by:
        table = catalog.create_table(
            identifier,
            schema=spec.schema,
            partition_spec=_identity_partition_spec(spec.schema, spec.partition_by),
            properties=properties,
        )
    else:
        table = catalog.create_table(identifier, schema=spec.schema, properties=properties)
    _validate_table_schema(identifier, table, spec)
    return table


def _create_table_if_not_exists(catalog: SqlCatalog, identifier: str, spec: TableSpec) -> Table:
    properties = spec.properties or {}
    if spec.partition_by:
        table = catalog.create_table_if_not_exists(
            identifier,
            schema=spec.schema,
            partition_spec=_identity_partition_spec(spec.schema, spec.partition_by),
            properties=properties,
        )
    else:
        table = catalog.create_table_if_not_exists(
            identifier, schema=spec.schema, properties=properties
        )
    _validate_table_schema(identifier, table, spec)
    return table


def _validate_table_schema(identifier: str, table: Table, spec: TableSpec) -> None:
    actual_schema = _table_schema_as_pyarrow(table)
    expected_fields = _schema_field_contract(spec.schema)
    actual_fields = _schema_field_contract(actual_schema)
    if actual_fields == expected_fields:
        return

    msg = (
        f"Iceberg table {identifier} schema drift: expected "
        f"{_format_schema_contract(expected_fields)}, found "
        f"{_format_schema_contract(actual_fields)}"
    )
    raise ValueError(msg)


def _table_schema_as_pyarrow(table: Table) -> pa.Schema:
    table_schema = table.schema
    schema = table_schema() if callable(table_schema) else table_schema
    if isinstance(schema, pa.Schema):
        return schema
    as_arrow = getattr(schema, "as_arrow", None)
    if callable(as_arrow):
        arrow_schema = as_arrow()
        if isinstance(arrow_schema, pa.Schema):
            return arrow_schema

    msg = "Iceberg table schema cannot be converted to a PyArrow schema"
    raise TypeError(msg)


def _schema_field_contract(schema: pa.Schema) -> list[tuple[str, pa.DataType, bool]]:
    return [
        (field.name, _normalize_iceberg_arrow_type(field.type), field.nullable)
        for field in schema
    ]


def _normalize_iceberg_arrow_type(data_type: pa.DataType) -> pa.DataType:
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return pa.string()
    return data_type


def _format_schema_contract(fields: Sequence[tuple[str, pa.DataType, bool]]) -> str:
    return ", ".join(
        f"{name}: {field_type}{'' if nullable else ' not null'}"
        for name, field_type, nullable in fields
    )


def _identity_partition_spec(schema: pa.Schema, partition_by: Sequence[str]) -> PartitionSpec:
    from pyiceberg.io.pyarrow import pyarrow_to_schema
    from pyiceberg.partitioning import PartitionField
    from pyiceberg.transforms import IdentityTransform

    iceberg_schema = pyarrow_to_schema(schema)
    field_ids_by_name = {field.name: field.field_id for field in iceberg_schema.fields}
    unknown_fields = [
        field_name for field_name in partition_by if field_name not in field_ids_by_name
    ]
    if unknown_fields:
        msg = "partition fields are not present in the table schema: "
        raise ValueError(msg + ", ".join(unknown_fields))

    return PartitionSpec(
        *[
            PartitionField(
                source_id=field_ids_by_name[field_name],
                field_id=1000 + index,
                transform=IdentityTransform(),
                name=field_name,
            )
            for index, field_name in enumerate(partition_by)
        ]
    )


__all__ = [
    "CANONICAL_ENTITY_SPEC",
    "CANONICAL_LINEAGE_DIM_INDEX_SPEC",
    "CANONICAL_LINEAGE_DIM_SECURITY_SPEC",
    "CANONICAL_LINEAGE_FACT_EVENT_SPEC",
    "CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_SPEC",
    "CANONICAL_LINEAGE_FACT_FORECAST_EVENT_SPEC",
    "CANONICAL_LINEAGE_FACT_HOLDING_POSITION_SPEC",
    "CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_SPEC",
    "CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_SPEC",
    "CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_SPEC",
    "CANONICAL_LINEAGE_FACT_PRICE_BAR_SPEC",
    "CANONICAL_LINEAGE_NAMESPACE",
    "CANONICAL_LINEAGE_STOCK_BASIC_SPEC",
    "CANONICAL_LINEAGE_TABLE_SPECS",
    "CANONICAL_V2_DIM_INDEX_SPEC",
    "CANONICAL_V2_DIM_SECURITY_SPEC",
    "CANONICAL_V2_FACT_EVENT_SPEC",
    "CANONICAL_V2_FACT_FINANCIAL_INDICATOR_SPEC",
    "CANONICAL_V2_FACT_FORECAST_EVENT_SPEC",
    "CANONICAL_V2_FACT_HOLDING_POSITION_SPEC",
    "CANONICAL_V2_FACT_INDEX_PRICE_BAR_SPEC",
    "CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_SPEC",
    "CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_SPEC",
    "CANONICAL_V2_FACT_PRICE_BAR_SPEC",
    "CANONICAL_V2_NAMESPACE",
    "CANONICAL_V2_STOCK_BASIC_SPEC",
    "CANONICAL_V2_TABLE_SPECS",
    "DEFAULT_TABLE_SPECS",
    "ENTITY_ALIAS_SPEC",
    "TableSpec",
    "ensure_tables",
    "register_table",
]


if __name__ == "__main__":
    raise SystemExit(main())
