"""Canonical Iceberg writers for Lite-mode staging outputs."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Final, NoReturn, Sequence
from urllib.parse import unquote, urlparse
from uuid import uuid4

import duckdb
import pyarrow as pa  # type: ignore[import-untyped]
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.table import Table

from data_platform.config import get_settings
from data_platform.serving.catalog import load_catalog


logger = logging.getLogger(__name__)

TABLE_V2_MARTS = "v2_marts"
TABLE_STOCK_BASIC = "stock_basic"
CANONICAL_LOADED_AT_COLUMN = "canonical_loaded_at"
CANONICAL_MART_SNAPSHOT_SET_FILE = "_mart_snapshot_set.json"
FORBIDDEN_PAYLOAD_FIELDS = frozenset(
    {"submitted_at", "ingest_seq", "source_run_id", "raw_loaded_at"}
)
"""Columns that must never appear on canonical business payload writes.

Includes both Layer-B ingest-queue fields (`submitted_at`, `ingest_seq`)
and raw-zone lineage fields (`source_run_id`, `raw_loaded_at`). The
`canonical_lineage.*` namespace legitimately carries the lineage block,
so the bypass at `_forbidden_payload_fields_for` strips those from the
forbidden set when the identifier is in `canonical_lineage`.
"""

_CANONICAL_LINEAGE_NAMESPACE = "canonical_lineage"
_CANONICAL_LINEAGE_ALLOWED_FIELDS = frozenset({"source_run_id", "raw_loaded_at"})


def _forbidden_payload_fields_for(identifier: str) -> frozenset[str]:
    """Return the forbidden-payload-fields set for one canonical identifier.

    Canonical_lineage specs legitimately carry `source_run_id` /
    `raw_loaded_at`; the ingest-queue boundary still applies there.
    """

    namespace = identifier.split(".", maxsplit=1)[0]
    if namespace == _CANONICAL_LINEAGE_NAMESPACE:
        return FORBIDDEN_PAYLOAD_FIELDS - _CANONICAL_LINEAGE_ALLOWED_FIELDS
    return FORBIDDEN_PAYLOAD_FIELDS


_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Result of one canonical table overwrite."""

    table: str
    snapshot_id: int
    row_count: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class CanonicalLoadSpec:
    """DuckDB relation to canonical Iceberg table load contract."""

    identifier: str
    duckdb_relation: str
    required_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        identifier = self.identifier.strip()
        duckdb_relation = self.duckdb_relation.strip()
        if not identifier:
            msg = "canonical identifier must not be empty"
            raise ValueError(msg)
        if not duckdb_relation:
            msg = "DuckDB relation must not be empty"
            raise ValueError(msg)
        if not self.required_columns:
            msg = "canonical load required_columns must not be empty"
            raise ValueError(msg)

        _validate_qualified_identifier(identifier)
        _validate_qualified_identifier(duckdb_relation)
        for column in self.required_columns:
            _validate_identifier(column)

        forbidden_fields = sorted(
            _forbidden_payload_fields_for(identifier).intersection(
                column.lower() for column in self.required_columns
            )
        )
        if forbidden_fields:
            msg = "canonical load spec must not include forbidden payload fields: "
            raise ValueError(msg + ", ".join(forbidden_fields))

        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "duckdb_relation", duckdb_relation)


@dataclass(frozen=True, slots=True)
class _PreparedCanonicalLoad:
    spec: CanonicalLoadSpec
    table: Table
    table_arrow: pa.Table


class _JsonErrorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _quote_qualified_identifier(identifier: str) -> str:
    return ".".join(_quote_identifier(part) for part in identifier.split("."))


def _validate_qualified_identifier(identifier: str) -> None:
    parts = identifier.split(".")
    if not parts:
        msg = f"invalid SQL identifier: {identifier!r}"
        raise ValueError(msg)
    for part in parts:
        _validate_identifier(part)


def _quote_identifier(identifier: str) -> str:
    _validate_identifier(identifier)
    return f'"{identifier}"'


def _validate_identifier(identifier: str) -> None:
    if _IDENTIFIER_PATTERN.fullmatch(identifier):
        return
    msg = f"invalid SQL identifier: {identifier!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Canonical V2 + canonical lineage load specs.
#
# The v2 spec is provider-neutral by construction: canonical identifiers
# (security_id / index_id / entity_id) instead of provider-shaped names;
# raw-zone lineage columns move to the matching canonical_lineage spec.
#
# Coverage: 11 paired specs covering all canonical mart tables — dim_security,
# stock_basic, dim_index, fact_price_bar, fact_financial_indicator,
# fact_market_daily_feature, fact_index_price_bar, fact_forecast_event,
# fact_event, fact_holding_position, and fact_northbound_turnover. fact_event
# currently covers 8 source interfaces after M1.8 block_trade promotion; the
# 8 unstaged candidates remain blocked upstream.
#
# Per M1-A design + M1-B spike + M1.3 second batch + M1.6 event promotion.
# ---------------------------------------------------------------------------

CANONICAL_V2_DIM_SECURITY_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.dim_security",
    duckdb_relation="mart_dim_security_v2",
    required_columns=(
        "security_id",
        "symbol",
        "display_name",
        "market",
        "industry",
        "list_date",
        "is_active",
        "area",
        "fullname",
        "exchange",
        "curr_type",
        "list_status",
        "delist_date",
        "setup_date",
        "province",
        "city",
        "reg_capital",
        "employees",
        "main_business",
        "latest_namechange_name",
        "latest_namechange_start_date",
        "latest_namechange_end_date",
        "latest_namechange_ann_date",
        "latest_namechange_reason",
    ),
)

CANONICAL_LINEAGE_DIM_SECURITY_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_dim_security",
    duckdb_relation="mart_lineage_dim_security",
    required_columns=(
        "security_id",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_STOCK_BASIC_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.stock_basic",
    duckdb_relation="mart_stock_basic_v2",
    required_columns=(
        "security_id",
        "symbol",
        "display_name",
        "area",
        "industry",
        "market",
        "list_date",
        "is_active",
    ),
)

CANONICAL_LINEAGE_STOCK_BASIC_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_stock_basic",
    duckdb_relation="mart_lineage_stock_basic",
    required_columns=(
        "security_id",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_DIM_INDEX_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.dim_index",
    duckdb_relation="mart_dim_index_v2",
    required_columns=(
        "index_id",
        "index_name",
        "index_market",
        "index_category",
        "first_effective_date",
        "latest_effective_date",
    ),
)

CANONICAL_LINEAGE_DIM_INDEX_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_dim_index",
    duckdb_relation="mart_lineage_dim_index",
    required_columns=(
        "index_id",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_PRICE_BAR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_price_bar",
    duckdb_relation="mart_fact_price_bar_v2",
    required_columns=(
        "security_id",
        "trade_date",
        "freq",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
        "adj_factor",
    ),
)

CANONICAL_LINEAGE_FACT_PRICE_BAR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_price_bar",
    duckdb_relation="mart_lineage_fact_price_bar",
    required_columns=(
        "security_id",
        "trade_date",
        "freq",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_FINANCIAL_INDICATOR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_financial_indicator",
    duckdb_relation="mart_fact_financial_indicator_v2",
    required_columns=(
        "security_id",
        "end_date",
        "ann_date",
        "f_ann_date",
        "report_type",
        "comp_type",
        "update_flag",
        "is_latest",
        "basic_eps",
        "diluted_eps",
        "total_revenue",
        "revenue",
        "operate_profit",
        "total_profit",
        "n_income",
        "n_income_attr_p",
        "money_cap",
        "total_cur_assets",
        "total_assets",
        "total_cur_liab",
        "total_liab",
        "total_hldr_eqy_exc_min_int",
        "total_liab_hldr_eqy",
        "net_profit",
        "n_cashflow_act",
        "n_cashflow_inv_act",
        "n_cash_flows_fnc_act",
        "n_incr_cash_cash_equ",
        "free_cashflow",
        "eps",
        "dt_eps",
        "grossprofit_margin",
        "netprofit_margin",
        "roe",
        "roa",
        "debt_to_assets",
        "or_yoy",
        "netprofit_yoy",
    ),
)

CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_financial_indicator",
    duckdb_relation="mart_lineage_fact_financial_indicator",
    required_columns=(
        "security_id",
        "end_date",
        "report_type",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_market_daily_feature",
    duckdb_relation="mart_fact_market_daily_feature_v2",
    required_columns=(
        "security_id",
        "trade_date",
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
        "up_limit",
        "down_limit",
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
    ),
)

CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_market_daily_feature",
    duckdb_relation="mart_lineage_fact_market_daily_feature",
    required_columns=(
        "security_id",
        "trade_date",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_INDEX_PRICE_BAR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_index_price_bar",
    duckdb_relation="mart_fact_index_price_bar_v2",
    required_columns=(
        "index_id",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
        "exchange",
        "is_open",
        "pretrade_date",
    ),
)

CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_index_price_bar",
    duckdb_relation="mart_lineage_fact_index_price_bar",
    required_columns=(
        "index_id",
        "trade_date",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_FORECAST_EVENT_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_forecast_event",
    duckdb_relation="mart_fact_forecast_event_v2",
    required_columns=(
        "security_id",
        "announcement_date",
        "report_period",
        "forecast_type",
        "p_change_min",
        "p_change_max",
        "net_profit_min",
        "net_profit_max",
        "last_parent_net",
        "first_ann_date",
        "summary",
        "change_reason",
        "update_flag",
    ),
)

CANONICAL_LINEAGE_FACT_FORECAST_EVENT_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_forecast_event",
    duckdb_relation="mart_lineage_fact_forecast_event",
    required_columns=(
        "security_id",
        "announcement_date",
        "report_period",
        "update_flag",
        "forecast_type",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

# Provider-neutral event fact. Mirrors the 11-column v2
# spec in iceberg_tables.py. `canonical_loaded_at` is injected by the writer
# and intentionally NOT listed in required_columns.
CANONICAL_V2_FACT_EVENT_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_event",
    duckdb_relation="mart_fact_event_v2",
    required_columns=(
        "event_type",
        "entity_id",
        "event_date",
        "event_key",
        "title",
        "summary",
        "event_subtype",
        "related_date",
        "reference_url",
        "rec_time",
    ),
)

# Lineage sibling for canonical_v2.fact_event. Each row carries its true
# `source_interface_id` (per-row, not a composite string).
CANONICAL_LINEAGE_FACT_EVENT_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_lineage.lineage_fact_event",
    duckdb_relation="mart_lineage_fact_event",
    required_columns=(
        "event_type",
        "entity_id",
        "event_date",
        "event_key",
        "source_provider",
        "source_interface_id",
        "source_run_id",
        "raw_loaded_at",
    ),
)

CANONICAL_V2_FACT_HOLDING_POSITION_LOAD_SPEC: Final[CanonicalLoadSpec] = CanonicalLoadSpec(
    identifier="canonical_v2.fact_holding_position",
    duckdb_relation="mart_fact_holding_position_v2",
    required_columns=(
        "holding_source",
        "holder_id",
        "holder_name",
        "holder_type",
        "security_id",
        "report_date",
        "announced_date",
        "holding_amount",
        "holding_ratio",
        "holding_float_ratio",
        "holding_change",
        "market_value",
        "exchange",
    ),
)

CANONICAL_LINEAGE_FACT_HOLDING_POSITION_LOAD_SPEC: Final[CanonicalLoadSpec] = (
    CanonicalLoadSpec(
        identifier="canonical_lineage.lineage_fact_holding_position",
        duckdb_relation="mart_lineage_fact_holding_position",
        required_columns=(
            "holding_source",
            "holder_id",
            "security_id",
            "report_date",
            "announced_date",
            "source_provider",
            "source_interface_id",
            "source_run_id",
            "raw_loaded_at",
        ),
    )
)

CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC: Final[CanonicalLoadSpec] = (
    CanonicalLoadSpec(
        identifier="canonical_v2.fact_northbound_turnover",
        duckdb_relation="mart_fact_northbound_turnover_v2",
        required_columns=(
            "security_id",
            "trade_date",
            "security_name",
            "market_type",
            "rank",
            "close",
            "change",
            "amount",
            "net_amount",
            "buy_amount",
            "sell_amount",
        ),
    )
)

CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC: Final[CanonicalLoadSpec] = (
    CanonicalLoadSpec(
        identifier="canonical_lineage.lineage_fact_northbound_turnover",
        duckdb_relation="mart_lineage_fact_northbound_turnover",
        required_columns=(
            "security_id",
            "trade_date",
            "market_type",
            "rank",
            "source_provider",
            "source_interface_id",
            "source_run_id",
            "raw_loaded_at",
        ),
    )
)

CANONICAL_V2_MART_LOAD_SPECS: Final[tuple[CanonicalLoadSpec, ...]] = (
    CANONICAL_V2_DIM_SECURITY_LOAD_SPEC,
    CANONICAL_V2_STOCK_BASIC_LOAD_SPEC,
    CANONICAL_V2_DIM_INDEX_LOAD_SPEC,
    CANONICAL_V2_FACT_PRICE_BAR_LOAD_SPEC,
    CANONICAL_V2_FACT_FINANCIAL_INDICATOR_LOAD_SPEC,
    CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC,
    CANONICAL_V2_FACT_INDEX_PRICE_BAR_LOAD_SPEC,
    CANONICAL_V2_FACT_FORECAST_EVENT_LOAD_SPEC,
    CANONICAL_V2_FACT_EVENT_LOAD_SPEC,
    CANONICAL_V2_FACT_HOLDING_POSITION_LOAD_SPEC,
    CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC,
)

CANONICAL_LINEAGE_MART_LOAD_SPECS: Final[tuple[CanonicalLoadSpec, ...]] = (
    CANONICAL_LINEAGE_DIM_SECURITY_LOAD_SPEC,
    CANONICAL_LINEAGE_STOCK_BASIC_LOAD_SPEC,
    CANONICAL_LINEAGE_DIM_INDEX_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_PRICE_BAR_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_FORECAST_EVENT_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_EVENT_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_HOLDING_POSITION_LOAD_SPEC,
    CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC,
)

# Canonical PK columns per (v2, lineage) load-spec pair. The pairing validator
# uses these to build composite key tuples for row-set comparison. NOTE: lineage
# spec may declare additional canonical PK columns beyond what canonical_v2
# carries (fact_financial_indicator: lineage uses `report_type` for uniqueness,
# while canonical_v2 keeps the full feature set).
CANONICAL_V2_PAIRING_KEY_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "canonical_v2.dim_security": ("security_id",),
    "canonical_v2.stock_basic": ("security_id",),
    "canonical_v2.dim_index": ("index_id",),
    "canonical_v2.fact_price_bar": ("security_id", "trade_date", "freq"),
    "canonical_v2.fact_financial_indicator": ("security_id", "end_date", "report_type"),
    "canonical_v2.fact_market_daily_feature": ("security_id", "trade_date"),
    "canonical_v2.fact_index_price_bar": ("index_id", "trade_date"),
    "canonical_v2.fact_forecast_event": (
        "security_id",
        "announcement_date",
        "report_period",
        "update_flag",
        "forecast_type",
    ),
    "canonical_v2.fact_event": (
        "event_type",
        "entity_id",
        "event_date",
        "event_key",
    ),
    "canonical_v2.fact_holding_position": (
        "holding_source",
        "holder_id",
        "security_id",
        "report_date",
        "announced_date",
    ),
    "canonical_v2.fact_northbound_turnover": (
        "security_id",
        "trade_date",
        "market_type",
        "rank",
    ),
}


def load_canonical_table(
    catalog: SqlCatalog,
    duckdb_path: Path,
    spec: CanonicalLoadSpec,
    *,
    allow_empty: bool = False,
) -> WriteResult:
    """Load one DuckDB relation into a single canonical Iceberg table.

    Mart specs (`canonical_v2.*` or `canonical_lineage.*`) MUST be
    published via `load_canonical_v2_marts` so the paired snapshot
    manifest stays consistent. This function is reserved for non-mart
    canonical tables (entity stores + schema-evolution single-table
    overwrites consumed by `serving.schema_evolution`).
    """

    _reject_public_mart_load(spec)
    start = perf_counter()
    prepared = _prepare_canonical_load(
        catalog,
        duckdb_path,
        spec,
        allow_empty=allow_empty,
    )
    result, _refreshed_table = _overwrite_prepared_load(prepared, started_at=start)
    return result


def _reject_public_mart_load(spec: CanonicalLoadSpec) -> None:
    v2_mart_identifiers = {
        mart_spec.identifier for mart_spec in CANONICAL_V2_MART_LOAD_SPECS
    }
    lineage_mart_identifiers = {
        mart_spec.identifier for mart_spec in CANONICAL_LINEAGE_MART_LOAD_SPECS
    }
    if spec.identifier in v2_mart_identifiers or spec.identifier in lineage_mart_identifiers:
        msg = (
            f"{spec.identifier} is part of the canonical_v2 / canonical_lineage "
            "mart snapshot set; publish via load_canonical_v2_marts"
        )
        raise ValueError(msg)


def _prepare_canonical_load(
    catalog: SqlCatalog,
    duckdb_path: Path,
    spec: CanonicalLoadSpec,
    *,
    allow_empty: bool,
    canonical_loaded_at: datetime | None = None,
) -> _PreparedCanonicalLoad:
    table = catalog.load_table(spec.identifier)
    target_columns = _table_field_names(table)
    table_arrow = _read_duckdb_relation(
        duckdb_path,
        spec,
        target_columns,
        canonical_loaded_at=canonical_loaded_at,
    )
    _validate_no_forbidden_payload_fields(table_arrow, spec.identifier)
    _validate_payload_fields_match_target(spec.identifier, table, table_arrow)
    _validate_non_empty_staging(spec, table_arrow, allow_empty=allow_empty)
    return _PreparedCanonicalLoad(spec=spec, table=table, table_arrow=table_arrow)


def _overwrite_prepared_load(
    prepared: _PreparedCanonicalLoad,
    *,
    started_at: float,
) -> tuple[WriteResult, Table]:
    prepared.table.overwrite(prepared.table_arrow)
    refreshed_table = prepared.table.refresh()
    snapshot_id = _current_snapshot_id(refreshed_table, prepared.spec.identifier)
    duration_ms = int((perf_counter() - started_at) * 1000)
    result = WriteResult(
        table=prepared.spec.identifier,
        snapshot_id=snapshot_id,
        row_count=prepared.table_arrow.num_rows,
        duration_ms=duration_ms,
    )
    logger.info(
        "canonical_write",
        extra={
            "table": result.table,
            "rows": result.row_count,
            "snapshot": result.snapshot_id,
        },
    )
    return result, refreshed_table


def load_canonical_v2_marts(
    catalog: SqlCatalog,
    duckdb_path: Path,
    *,
    allow_empty: bool = False,
) -> list[WriteResult]:
    """Load canonical_v2 mart tables and their canonical_lineage siblings together.

    Canonical_v2 rows are provider-neutral by construction; the matching lineage
    rows carry source/run metadata 1:1 keyed on the canonical PK. This function
    writes both sets in lock-step inside one Python frame so the
    `_mart_snapshot_set.json` v2 sidecar pins them as a co-published pair.

    Coverage: 11 paired specs — dim_security, stock_basic, dim_index,
    fact_price_bar, fact_financial_indicator, fact_market_daily_feature,
    fact_index_price_bar, fact_forecast_event, fact_event, fact_holding_position,
    and fact_northbound_turnover. The pairing-key validator
    (`_validate_canonical_v2_mart_pairings`) enforces 1:1 row matching on the
    composite PK declared in `CANONICAL_V2_PAIRING_KEY_COLUMNS`.
    """

    if len(CANONICAL_V2_MART_LOAD_SPECS) != len(CANONICAL_LINEAGE_MART_LOAD_SPECS):
        msg = (
            "canonical_v2 and canonical_lineage mart spec sets must be the same "
            "length (paired publish); "
            f"got v2={len(CANONICAL_V2_MART_LOAD_SPECS)} "
            f"lineage={len(CANONICAL_LINEAGE_MART_LOAD_SPECS)}"
        )
        raise RuntimeError(msg)

    paired_canonical_loaded_at = datetime.now(UTC).replace(tzinfo=None)
    prepared_v2_loads = [
        _prepare_canonical_load(
            catalog,
            duckdb_path,
            spec,
            allow_empty=allow_empty,
            canonical_loaded_at=paired_canonical_loaded_at,
        )
        for spec in CANONICAL_V2_MART_LOAD_SPECS
    ]
    prepared_lineage_loads = [
        _prepare_canonical_load(
            catalog,
            duckdb_path,
            spec,
            allow_empty=allow_empty,
            canonical_loaded_at=paired_canonical_loaded_at,
        )
        for spec in CANONICAL_LINEAGE_MART_LOAD_SPECS
    ]
    _validate_canonical_v2_mart_pairings(prepared_v2_loads, prepared_lineage_loads)

    results: list[WriteResult] = []
    canonical_v2_snapshot_set: dict[str, dict[str, int | str]] = {}
    canonical_lineage_snapshot_set: dict[str, dict[str, int | str]] = {}
    load_id = str(uuid4())
    original_snapshot_ids = {
        prepared.spec.identifier: _current_snapshot_id_or_none(prepared.table)
        for prepared in (*prepared_v2_loads, *prepared_lineage_loads)
    }
    attempted_overwrites: list[_PreparedCanonicalLoad] = []

    try:
        for prepared_v2, prepared_lineage in zip(
            prepared_v2_loads,
            prepared_lineage_loads,
            strict=True,
        ):
            attempted_overwrites.append(prepared_v2)
            v2_result, v2_refreshed = _overwrite_prepared_load(
                prepared_v2,
                started_at=perf_counter(),
            )
            attempted_overwrites.append(prepared_lineage)
            lineage_result, lineage_refreshed = _overwrite_prepared_load(
                prepared_lineage,
                started_at=perf_counter(),
            )
            results.append(v2_result)
            results.append(lineage_result)
            canonical_v2_snapshot_set[_table_name_from_identifier(v2_result.table)] = {
                "identifier": v2_result.table,
                "snapshot_id": v2_result.snapshot_id,
                "metadata_location": str(
                    _local_path_from_location(v2_refreshed.metadata_location)
                ),
            }
            canonical_lineage_snapshot_set[_table_name_from_identifier(lineage_result.table)] = {
                "identifier": lineage_result.table,
                "snapshot_id": lineage_result.snapshot_id,
                "metadata_location": str(
                    _local_path_from_location(lineage_refreshed.metadata_location)
                ),
            }

        _write_canonical_v2_snapshot_set_manifest(
            prepared_v2_loads[0].table,
            load_id=load_id,
            canonical_v2_tables=canonical_v2_snapshot_set,
            canonical_lineage_tables=canonical_lineage_snapshot_set,
        )
    except Exception:
        _rollback_attempted_overwrites(attempted_overwrites, original_snapshot_ids)
        raise
    return results


def load_canonical_v2_stock_basic_smoke(
    catalog: SqlCatalog,
    duckdb_path: Path,
    *,
    allow_empty: bool = False,
) -> list[WriteResult]:
    """Publish the stock_basic v2/lineage pair for the destructive P1a smoke.

    The public canonical_v2 serving path is `load_canonical_v2_marts`. This
    narrower path exists only for the isolated smoke database, where the fixture
    seeds stock_basic and its immediate dbt dependencies instead of every mart
    input family.
    """

    paired_canonical_loaded_at = datetime.now(UTC).replace(tzinfo=None)
    prepared_v2 = _prepare_canonical_load(
        catalog,
        duckdb_path,
        CANONICAL_V2_STOCK_BASIC_LOAD_SPEC,
        allow_empty=allow_empty,
        canonical_loaded_at=paired_canonical_loaded_at,
    )
    prepared_lineage = _prepare_canonical_load(
        catalog,
        duckdb_path,
        CANONICAL_LINEAGE_STOCK_BASIC_LOAD_SPEC,
        allow_empty=allow_empty,
        canonical_loaded_at=paired_canonical_loaded_at,
    )
    prepared_loads = (prepared_v2, prepared_lineage)
    _validate_canonical_v2_mart_pairings([prepared_v2], [prepared_lineage])

    load_id = str(uuid4())
    original_snapshot_ids = {
        prepared.spec.identifier: _current_snapshot_id_or_none(prepared.table)
        for prepared in prepared_loads
    }
    attempted_overwrites: list[_PreparedCanonicalLoad] = []
    try:
        attempted_overwrites.append(prepared_v2)
        v2_result, v2_refreshed = _overwrite_prepared_load(
            prepared_v2,
            started_at=perf_counter(),
        )
        attempted_overwrites.append(prepared_lineage)
        lineage_result, lineage_refreshed = _overwrite_prepared_load(
            prepared_lineage,
            started_at=perf_counter(),
        )
        _write_canonical_v2_snapshot_set_manifest(
            prepared_v2.table,
            load_id=load_id,
            canonical_v2_tables={
                _table_name_from_identifier(v2_result.table): {
                    "identifier": v2_result.table,
                    "snapshot_id": v2_result.snapshot_id,
                    "metadata_location": str(
                        _local_path_from_location(v2_refreshed.metadata_location)
                    ),
                }
            },
            canonical_lineage_tables={
                _table_name_from_identifier(lineage_result.table): {
                    "identifier": lineage_result.table,
                    "snapshot_id": lineage_result.snapshot_id,
                    "metadata_location": str(
                        _local_path_from_location(lineage_refreshed.metadata_location)
                    ),
                }
            },
        )
    except Exception:
        _rollback_attempted_overwrites(attempted_overwrites, original_snapshot_ids)
        raise
    return [v2_result, lineage_result]


def _validate_canonical_v2_mart_pairings(
    prepared_v2_loads: Sequence[_PreparedCanonicalLoad],
    prepared_lineage_loads: Sequence[_PreparedCanonicalLoad],
) -> None:
    for prepared_v2, prepared_lineage in zip(
        prepared_v2_loads,
        prepared_lineage_loads,
        strict=True,
    ):
        key_columns = _canonical_v2_pairing_keys(prepared_v2.spec, prepared_lineage.spec)
        _validate_canonical_v2_mart_pairing(
            prepared_v2,
            prepared_lineage,
            key_columns=key_columns,
        )


def _canonical_v2_pairing_keys(
    v2_spec: CanonicalLoadSpec,
    lineage_spec: CanonicalLoadSpec,
) -> tuple[str, ...]:
    """Return the composite canonical PK columns shared by a v2/lineage pair.

    Falls back to the leading column shared between both specs when the v2
    identifier is not registered in `CANONICAL_V2_PAIRING_KEY_COLUMNS`.
    """

    declared = CANONICAL_V2_PAIRING_KEY_COLUMNS.get(v2_spec.identifier)
    if declared is not None:
        missing_in_v2 = [col for col in declared if col not in v2_spec.required_columns]
        missing_in_lineage = [
            col for col in declared if col not in lineage_spec.required_columns
        ]
        if missing_in_v2 or missing_in_lineage:
            msg = (
                "canonical_v2 / canonical_lineage spec is missing declared pairing "
                f"key columns for {v2_spec.identifier} + {lineage_spec.identifier}: "
                f"missing_in_v2={missing_in_v2}, missing_in_lineage={missing_in_lineage}"
            )
            raise RuntimeError(msg)
        return declared

    key_column = v2_spec.required_columns[0]
    lineage_key_column = lineage_spec.required_columns[0]
    if key_column == lineage_key_column:
        return (key_column,)

    msg = (
        "canonical_v2 and canonical_lineage mart specs must share the same "
        "leading canonical key column or be registered in "
        "CANONICAL_V2_PAIRING_KEY_COLUMNS; "
        f"got {v2_spec.identifier}.{key_column} and "
        f"{lineage_spec.identifier}.{lineage_key_column}"
    )
    raise RuntimeError(msg)


def _validate_canonical_v2_mart_pairing(
    prepared_v2: _PreparedCanonicalLoad,
    prepared_lineage: _PreparedCanonicalLoad,
    *,
    key_columns: tuple[str, ...],
) -> None:
    if not key_columns:
        msg = (
            "canonical_v2 / canonical_lineage pairing requires at least one "
            f"canonical key column; got empty tuple for {prepared_v2.spec.identifier}"
        )
        raise RuntimeError(msg)

    key_label = ",".join(key_columns)
    v2_keys = _canonical_key_values(prepared_v2, key_columns)
    lineage_keys = _canonical_key_values(prepared_lineage, key_columns)
    if len(v2_keys) != len(lineage_keys):
        msg = (
            "canonical_v2 and canonical_lineage row_count mismatch for paired "
            f"publish {prepared_v2.spec.identifier} + {prepared_lineage.spec.identifier} "
            f"on ({key_label}): v2={len(v2_keys)} lineage={len(lineage_keys)} "
            f"lineage_coverage={_lineage_coverage(v2_keys, lineage_keys):.1%}"
        )
        raise ValueError(msg)

    _validate_unique_canonical_keys(prepared_v2.spec.identifier, key_label, v2_keys)
    _validate_unique_canonical_keys(
        prepared_lineage.spec.identifier,
        key_label,
        lineage_keys,
    )

    v2_key_set = set(v2_keys)
    lineage_key_set = set(lineage_keys)
    if v2_key_set == lineage_key_set:
        return

    missing_lineage_keys = sorted(v2_key_set - lineage_key_set, key=str)
    extra_lineage_keys = sorted(lineage_key_set - v2_key_set, key=str)
    details = [
        f"lineage_coverage={_lineage_coverage(v2_keys, lineage_keys):.1%}",
    ]
    if missing_lineage_keys:
        details.append(
            "missing lineage key(s): " + ", ".join(_format_key_sample(missing_lineage_keys))
        )
    if extra_lineage_keys:
        details.append(
            "extra lineage key(s): " + ", ".join(_format_key_sample(extra_lineage_keys))
        )
    msg = (
        "canonical_v2 and canonical_lineage key set mismatch for paired publish "
        f"{prepared_v2.spec.identifier} + {prepared_lineage.spec.identifier} "
        f"on ({key_label}): "
        + "; ".join(details)
    )
    raise ValueError(msg)


def _canonical_key_values(
    prepared: _PreparedCanonicalLoad,
    key_columns: tuple[str, ...],
) -> list[tuple[object, ...]]:
    """Build a list of composite canonical-key tuples from the payload."""

    schema_names = set(prepared.table_arrow.schema.names)
    missing = [col for col in key_columns if col not in schema_names]
    if missing:
        msg = (
            f"{prepared.spec.identifier} payload is missing canonical key "
            f"column(s) {missing}"
        )
        raise ValueError(msg)

    column_values: list[list[object]] = [
        list(prepared.table_arrow.column(col).to_pylist()) for col in key_columns
    ]
    row_count = len(column_values[0]) if column_values else 0

    composite: list[tuple[object, ...]] = []
    for row_idx in range(row_count):
        row_key = tuple(column_values[col_idx][row_idx] for col_idx in range(len(key_columns)))
        if any(value is None for value in row_key):
            msg = (
                f"{prepared.spec.identifier} payload contains null canonical key "
                f"in column(s) {','.join(key_columns)} at row {row_idx}"
            )
            raise ValueError(msg)
        composite.append(row_key)
    return composite


def _validate_unique_canonical_keys(
    identifier: str,
    key_label: str,
    values: Sequence[tuple[object, ...]],
) -> None:
    duplicate_keys = [key for key, count in Counter(values).items() if count > 1]
    if not duplicate_keys:
        return

    msg = (
        f"{identifier} has duplicate canonical key(s) in ({key_label}): "
        + ", ".join(_format_key_sample(sorted(duplicate_keys, key=str)))
    )
    raise ValueError(msg)


def _lineage_coverage(v2_keys: Sequence[object], lineage_keys: Sequence[object]) -> float:
    v2_key_set = set(v2_keys)
    if not v2_key_set:
        return 1.0
    return len(v2_key_set.intersection(lineage_keys)) / len(v2_key_set)


def _format_key_sample(keys: Sequence[object], *, limit: int = 5) -> list[str]:
    formatted = [str(key) for key in keys[:limit]]
    if len(keys) > limit:
        formatted.append("...")
    return formatted


def _current_snapshot_id_or_none(table: Table) -> int | None:
    snapshot = table.current_snapshot()
    if snapshot is None:
        return None
    return int(snapshot.snapshot_id)


def _rollback_attempted_overwrites(
    attempted_overwrites: Sequence[_PreparedCanonicalLoad],
    original_snapshot_ids: dict[str, int | None],
) -> None:
    rolled_back_identifiers: set[str] = set()
    for prepared in reversed(attempted_overwrites):
        identifier = prepared.spec.identifier
        if identifier in rolled_back_identifiers:
            continue
        rolled_back_identifiers.add(identifier)
        original_snapshot_id = original_snapshot_ids[identifier]
        if original_snapshot_id is None:
            logger.warning(
                "canonical_v2_rollback_skipped_no_prior_snapshot",
                extra={"table": identifier},
            )
            continue
        try:
            prepared.table.refresh().manage_snapshots().rollback_to_snapshot(
                original_snapshot_id
            ).commit()
            logger.info(
                "canonical_v2_rollback",
                extra={"table": identifier, "snapshot": original_snapshot_id},
            )
        except Exception:
            logger.warning(
                "canonical_v2_rollback_failed",
                extra={"table": identifier, "snapshot": original_snapshot_id},
                exc_info=True,
            )


def _write_canonical_v2_snapshot_set_manifest(
    table: Table,
    *,
    load_id: str,
    canonical_v2_tables: dict[str, dict[str, int | str]],
    canonical_lineage_tables: dict[str, dict[str, int | str]],
) -> None:
    manifest_path = _mart_snapshot_set_manifest_path(table)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "load_id": load_id,
        "published_at": datetime.now(UTC).isoformat(),
        "canonical_v2_tables": canonical_v2_tables,
        "canonical_lineage_tables": canonical_lineage_tables,
    }
    temp_path = manifest_path.with_name(f".{manifest_path.name}.{load_id}.tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temp_path.replace(manifest_path)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = _JsonErrorArgumentParser(
            description="Load staging data into canonical Iceberg tables."
        )
        parser.add_argument("--table", required=True, help="canonical table to load")
        parser.add_argument(
            "--allow-empty",
            action="store_true",
            help="intentionally publish an empty canonical table",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="emit JSON output",
        )
        args = parser.parse_args(argv)
        result: WriteResult | list[WriteResult]
        if args.table == TABLE_V2_MARTS:
            result = load_canonical_v2_marts(
                load_catalog(),
                get_settings().duckdb_path,
                allow_empty=args.allow_empty,
            )
        elif args.table == TABLE_STOCK_BASIC:
            _require_test_env_for_stock_basic_smoke()
            result = load_canonical_v2_stock_basic_smoke(
                load_catalog(),
                get_settings().duckdb_path,
                allow_empty=args.allow_empty,
            )
        else:
            msg = f"unsupported canonical table: {args.table}"
            raise ValueError(msg)
    except Exception as exc:
        error_payload = {"error": type(exc).__name__, "detail": str(exc)}
        print(json.dumps(error_payload, sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps(_serialize_result(result), sort_keys=True))
    return 0


def _require_test_env_for_stock_basic_smoke() -> None:
    if os.environ.get("DP_ENV") == "test":
        return
    msg = (
        "stock_basic single-table publication is restricted to DP_ENV=test "
        "P1a smoke runs; use --table v2_marts for canonical_v2 publication"
    )
    raise ValueError(msg)


def _read_duckdb_relation(
    duckdb_path: Path,
    spec: CanonicalLoadSpec,
    target_columns: Sequence[str],
    *,
    canonical_loaded_at: datetime | None = None,
) -> pa.Table:
    select_expressions: list[str] = []
    for column in spec.required_columns:
        quoted_column = _quote_identifier(column)
        select_expressions.append(f"{quoted_column} AS {quoted_column}")
    if CANONICAL_LOADED_AT_COLUMN in target_columns:
        quoted_column = _quote_identifier(CANONICAL_LOADED_AT_COLUMN)
        if canonical_loaded_at is None:
            select_expressions.append(
                f"CAST(current_timestamp AS TIMESTAMP) AS {quoted_column}"
            )
        else:
            loaded_at_literal = canonical_loaded_at.isoformat(
                sep=" ",
                timespec="microseconds",
            )
            select_expressions.append(
                f"TIMESTAMP '{loaded_at_literal}' AS {quoted_column}"
            )

    sql = f"""
SELECT
    {",\n    ".join(select_expressions)}
FROM {_quote_qualified_identifier(spec.duckdb_relation)}
"""
    connection = duckdb.connect(str(duckdb_path))
    try:
        return connection.execute(sql).to_arrow_table()
    finally:
        connection.close()


def _validate_no_forbidden_payload_fields(
    table_arrow: pa.Table, identifier: str
) -> None:
    forbidden_fields = sorted(
        _forbidden_payload_fields_for(identifier).intersection(
            field_name.lower() for field_name in table_arrow.schema.names
        )
    )
    if not forbidden_fields:
        return

    msg = "canonical payload must not include forbidden payload fields: "
    raise ValueError(msg + ", ".join(forbidden_fields))


def _validate_payload_fields_match_target(
    identifier: str,
    table: Table,
    table_arrow: pa.Table,
) -> None:
    target_fields = set(_table_field_names(table))
    payload_fields = set(table_arrow.schema.names)
    if target_fields == payload_fields:
        return

    missing = sorted(target_fields - payload_fields)
    extra = sorted(payload_fields - target_fields)
    details = []
    if missing:
        details.append("missing payload fields: " + ", ".join(missing))
    if extra:
        details.append("extra payload fields: " + ", ".join(extra))
    msg = f"{identifier} payload field set does not match target schema"
    if details:
        msg = msg + " (" + "; ".join(details) + ")"
    raise ValueError(msg)


def _validate_non_empty_staging(
    spec: CanonicalLoadSpec,
    table_arrow: pa.Table,
    *,
    allow_empty: bool,
) -> None:
    if table_arrow.num_rows > 0 or allow_empty:
        return

    msg = (
        f"{spec.duckdb_relation} produced zero rows; refusing to overwrite "
        f"{spec.identifier} without allow_empty=True"
    )
    raise ValueError(msg)


def _table_field_names(table: Table) -> list[str]:
    table_schema = table.schema
    schema = table_schema() if callable(table_schema) else table_schema
    if isinstance(schema, pa.Schema):
        return list(schema.names)

    as_arrow = getattr(schema, "as_arrow", None)
    if callable(as_arrow):
        arrow_schema = as_arrow()
        if isinstance(arrow_schema, pa.Schema):
            return list(arrow_schema.names)

    fields = getattr(schema, "fields", None)
    if fields is not None:
        return [str(field.name) for field in fields]

    msg = "Iceberg table schema cannot be inspected for field names"
    raise TypeError(msg)


def _current_snapshot_id(table: Table, identifier: str) -> int:
    snapshot = table.current_snapshot()
    if snapshot is None:
        msg = f"{identifier} overwrite did not create a current snapshot"
        raise RuntimeError(msg)
    return int(snapshot.snapshot_id)


def _mart_snapshot_set_manifest_path(table: Table) -> Path:
    table_location = _local_path_from_location(table.location())
    return table_location.parent / CANONICAL_MART_SNAPSHOT_SET_FILE


def _local_path_from_location(location: str) -> Path:
    parsed = urlparse(location)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:
        msg = "canonical mart snapshot set manifest requires a local file Iceberg warehouse"
        raise ValueError(msg)
    return Path(location)


def _table_name_from_identifier(identifier: str) -> str:
    return identifier.rsplit(".", maxsplit=1)[-1]


def _serialize_result(result: WriteResult | list[WriteResult]) -> object:
    if isinstance(result, list):
        return [asdict(item) for item in result]
    return asdict(result)


__all__ = [
    "CANONICAL_LINEAGE_DIM_INDEX_LOAD_SPEC",
    "CANONICAL_LINEAGE_DIM_SECURITY_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_EVENT_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_FINANCIAL_INDICATOR_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_FORECAST_EVENT_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_HOLDING_POSITION_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_INDEX_PRICE_BAR_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC",
    "CANONICAL_LINEAGE_FACT_PRICE_BAR_LOAD_SPEC",
    "CANONICAL_LINEAGE_MART_LOAD_SPECS",
    "CANONICAL_LINEAGE_STOCK_BASIC_LOAD_SPEC",
    "CANONICAL_MART_SNAPSHOT_SET_FILE",
    "CANONICAL_V2_DIM_INDEX_LOAD_SPEC",
    "CANONICAL_V2_DIM_SECURITY_LOAD_SPEC",
    "CANONICAL_V2_FACT_EVENT_LOAD_SPEC",
    "CANONICAL_V2_FACT_FINANCIAL_INDICATOR_LOAD_SPEC",
    "CANONICAL_V2_FACT_FORECAST_EVENT_LOAD_SPEC",
    "CANONICAL_V2_FACT_HOLDING_POSITION_LOAD_SPEC",
    "CANONICAL_V2_FACT_INDEX_PRICE_BAR_LOAD_SPEC",
    "CANONICAL_V2_FACT_MARKET_DAILY_FEATURE_LOAD_SPEC",
    "CANONICAL_V2_FACT_NORTHBOUND_TURNOVER_LOAD_SPEC",
    "CANONICAL_V2_FACT_PRICE_BAR_LOAD_SPEC",
    "CANONICAL_V2_MART_LOAD_SPECS",
    "CANONICAL_V2_PAIRING_KEY_COLUMNS",
    "CANONICAL_V2_STOCK_BASIC_LOAD_SPEC",
    "CanonicalLoadSpec",
    "WriteResult",
    "load_canonical_table",
    "load_canonical_v2_stock_basic_smoke",
    "load_canonical_v2_marts",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
