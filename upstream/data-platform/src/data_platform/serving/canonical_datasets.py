"""Provider-neutral canonical dataset to Iceberg table mapping.

Two mapping tables are maintained side-by-side:

* `CANONICAL_DATASET_TABLE_MAPPINGS` is the legacy `canonical.*` namespace.
* `CANONICAL_DATASET_TABLE_MAPPINGS_V2` is the provider-neutral
  `canonical_v2.*` namespace introduced by M1.3.

Reader callers select between the two via the `DP_CANONICAL_USE_V2`
environment variable. When unset (default), readers continue to consume the
legacy namespace; when set to a truthy value (`1`, `true`, `yes`, `on`),
readers consume `canonical_v2.*`. The flip is intentionally opt-in so the
legacy code paths and existing tests stay green until explicit cutover.

`event_timeline` maps to `canonical_v2.fact_event` for 8 source interfaces
currently in `int_event_timeline.sql` (anns, suspend_d, dividend,
share_float, stk_holdernumber, disclosure_date, namechange, block_trade).
Full event_timeline coverage is not achieved: the 8 candidate Tushare sources
(pledge_*, repurchase, stk_holdertrade, limit_list_*, hm_detail, stk_surv)
remain BLOCKED_NO_STAGING.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from data_platform.provider_catalog.registry import CANONICAL_DATASETS


class UnsupportedCanonicalDataset(LookupError):
    """Raised when a canonical dataset has no implemented Iceberg table."""

    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"canonical dataset is not mapped to an Iceberg table: {dataset_id}")


def _split_table_identifier(identifier: str) -> tuple[str, str]:
    if not isinstance(identifier, str):
        msg = f"table identifier must be a string: {identifier!r}"
        raise TypeError(msg)
    parts = tuple(part.strip() for part in identifier.split("."))
    if len(parts) != 2 or any(not part for part in parts):
        msg = f"table identifier must be namespace.table: {identifier!r}"
        raise ValueError(msg)
    return parts


def _table_name_from_identifier(identifier: str) -> str:
    if not isinstance(identifier, str):
        msg = f"table identifier must be a string: {identifier!r}"
        raise TypeError(msg)
    parts = tuple(part.strip() for part in identifier.split("."))
    if len(parts) == 1 and parts[0]:
        return parts[0]
    return _split_table_identifier(identifier)[1]


@dataclass(frozen=True, slots=True)
class CanonicalDatasetTable:
    """Explicit storage mapping for one provider-neutral canonical dataset."""

    dataset_id: str
    table_identifier: str

    def __post_init__(self) -> None:
        if self.dataset_id not in CANONICAL_DATASETS:
            msg = f"unknown canonical dataset: {self.dataset_id!r}"
            raise ValueError(msg)
        namespace, table_name = _split_table_identifier(self.table_identifier)
        object.__setattr__(self, "table_identifier", f"{namespace}.{table_name}")

    @property
    def namespace(self) -> str:
        return self.table_identifier.split(".", maxsplit=1)[0]

    @property
    def table_name(self) -> str:
        return self.table_identifier.split(".", maxsplit=1)[1]


CANONICAL_DATASET_TABLE_MAPPINGS: Final[tuple[CanonicalDatasetTable, ...]] = (
    CanonicalDatasetTable("security_master", "canonical.dim_security"),
    CanonicalDatasetTable("security_profile", "canonical.dim_security"),
    CanonicalDatasetTable("price_bar", "canonical.fact_price_bar"),
    CanonicalDatasetTable("adjustment_factor", "canonical.fact_price_bar"),
    CanonicalDatasetTable("market_daily_feature", "canonical.fact_market_daily_feature"),
    CanonicalDatasetTable("index_master", "canonical.dim_index"),
    CanonicalDatasetTable("index_price_bar", "canonical.fact_index_price_bar"),
    CanonicalDatasetTable("event_timeline", "canonical.fact_event"),
    CanonicalDatasetTable("financial_indicator", "canonical.fact_financial_indicator"),
    CanonicalDatasetTable("financial_forecast_event", "canonical.fact_forecast_event"),
)

# `event_timeline -> canonical_v2.fact_event` covers 8 source interfaces in
# int_event_timeline.sql: anns, suspend_d, dividend, share_float,
# stk_holdernumber, disclosure_date, namechange, and block_trade. Full
# event_timeline coverage is not achieved: the 8 candidate Tushare sources
# remain BLOCKED_NO_STAGING.
CANONICAL_DATASET_TABLE_MAPPINGS_V2: Final[tuple[CanonicalDatasetTable, ...]] = (
    CanonicalDatasetTable("security_master", "canonical_v2.dim_security"),
    CanonicalDatasetTable("security_profile", "canonical_v2.dim_security"),
    CanonicalDatasetTable("price_bar", "canonical_v2.fact_price_bar"),
    CanonicalDatasetTable("adjustment_factor", "canonical_v2.fact_price_bar"),
    CanonicalDatasetTable("market_daily_feature", "canonical_v2.fact_market_daily_feature"),
    CanonicalDatasetTable("index_master", "canonical_v2.dim_index"),
    CanonicalDatasetTable("index_price_bar", "canonical_v2.fact_index_price_bar"),
    CanonicalDatasetTable("event_timeline", "canonical_v2.fact_event"),
    CanonicalDatasetTable("financial_indicator", "canonical_v2.fact_financial_indicator"),
    CanonicalDatasetTable("financial_forecast_event", "canonical_v2.fact_forecast_event"),
    CanonicalDatasetTable("holding_position", "canonical_v2.fact_holding_position"),
    CanonicalDatasetTable(
        "northbound_turnover_daily",
        "canonical_v2.fact_northbound_turnover",
    ),
)

# Per-dataset canonical alias column. Used by reader callers that need to
# project / join on the dataset's canonical identifier without hard-coding the
# provider-shaped column name.
_LEGACY_ALIAS_COLUMN: Final[dict[str, str]] = {
    "security_master": "ts_code",
    "security_profile": "ts_code",
    "price_bar": "ts_code",
    "adjustment_factor": "ts_code",
    "market_daily_feature": "ts_code",
    "index_master": "index_code",
    "index_price_bar": "index_code",
    "event_timeline": "ts_code",
    "financial_indicator": "ts_code",
    "financial_forecast_event": "ts_code",
}
_V2_ALIAS_COLUMN: Final[dict[str, str]] = {
    "security_master": "security_id",
    "security_profile": "security_id",
    "price_bar": "security_id",
    "adjustment_factor": "security_id",
    "market_daily_feature": "security_id",
    "index_master": "index_id",
    "index_price_bar": "index_id",
    "event_timeline": "entity_id",
    "financial_indicator": "security_id",
    "financial_forecast_event": "security_id",
    "holding_position": "security_id",
    "northbound_turnover_daily": "security_id",
}

USE_CANONICAL_V2_ENV_VAR: Final[str] = "DP_CANONICAL_USE_V2"
_TRUTHY_ENV_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def use_canonical_v2() -> bool:
    """Return whether the v2 namespace is currently selected for readers."""

    return os.environ.get(USE_CANONICAL_V2_ENV_VAR, "").strip().lower() in _TRUTHY_ENV_VALUES


def _legacy_dataset_to_table() -> dict[str, CanonicalDatasetTable]:
    return {mapping.dataset_id: mapping for mapping in CANONICAL_DATASET_TABLE_MAPPINGS}


def _v2_dataset_to_table() -> dict[str, CanonicalDatasetTable]:
    return {mapping.dataset_id: mapping for mapping in CANONICAL_DATASET_TABLE_MAPPINGS_V2}


def _selected_dataset_to_table() -> dict[str, CanonicalDatasetTable]:
    """Return the active dataset → table map per the env flag.

    The legacy map is the fallback for any dataset_id that is not yet present
    in the v2 map (e.g., `event_timeline` while M1-F derivation rules remain
    open).
    """

    legacy = _legacy_dataset_to_table()
    if not use_canonical_v2():
        return legacy
    v2 = _v2_dataset_to_table()
    merged = dict(legacy)
    merged.update(v2)
    return merged


def _legacy_table_to_datasets() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for mapping in CANONICAL_DATASET_TABLE_MAPPINGS:
        result[mapping.table_name] = (*result.get(mapping.table_name, ()), mapping.dataset_id)
    return result


def _v2_table_to_datasets() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for mapping in CANONICAL_DATASET_TABLE_MAPPINGS_V2:
        result[mapping.table_name] = (*result.get(mapping.table_name, ()), mapping.dataset_id)
    return result


def _selected_table_to_datasets() -> dict[str, tuple[str, ...]]:
    if not use_canonical_v2():
        return _legacy_table_to_datasets()
    merged = _legacy_table_to_datasets()
    for table_name, dataset_ids in _v2_table_to_datasets().items():
        merged[table_name] = dataset_ids
    return merged


def canonical_table_for_dataset(dataset_id: str) -> str:
    """Return the physical canonical Iceberg table name for a dataset id."""

    return canonical_table_mapping_for_dataset(dataset_id).table_name


def canonical_table_identifier_for_dataset(dataset_id: str) -> str:
    """Return the qualified canonical Iceberg table identifier for a dataset id."""

    return canonical_table_mapping_for_dataset(dataset_id).table_identifier


def canonical_table_mapping_for_dataset(dataset_id: str) -> CanonicalDatasetTable:
    """Return the explicit table mapping for a provider-neutral dataset id."""

    mappings = _selected_dataset_to_table()
    try:
        return mappings[dataset_id]
    except KeyError as exc:
        raise UnsupportedCanonicalDataset(dataset_id) from exc


def canonical_alias_column_for_dataset(dataset_id: str) -> str:
    """Return the canonical-identifier column name for a dataset.

    Returns the v2 canonical name (`security_id`/`index_id`) when
    `DP_CANONICAL_USE_V2` is set AND the dataset has a v2 mapping; otherwise
    returns the provider-shaped legacy name (`ts_code`/`index_code`).
    """

    if use_canonical_v2() and dataset_id in _V2_ALIAS_COLUMN:
        return _V2_ALIAS_COLUMN[dataset_id]
    if dataset_id not in _LEGACY_ALIAS_COLUMN:
        raise UnsupportedCanonicalDataset(dataset_id)
    return _LEGACY_ALIAS_COLUMN[dataset_id]


def canonical_datasets_for_table(table: str) -> tuple[str, ...]:
    """Return provider-neutral dataset ids served from a physical table."""

    table_name = _table_name_from_identifier(table)
    return _selected_table_to_datasets().get(table_name, ())


def canonical_dataset_for_table(table: str) -> str:
    """Return the primary provider-neutral dataset id for a physical table."""

    dataset_ids = canonical_datasets_for_table(table)
    if not dataset_ids:
        msg = f"canonical table is not mapped to a dataset id: {table}"
        raise LookupError(msg)
    return dataset_ids[0]


def canonical_mart_table_names() -> frozenset[str]:
    """Return implemented canonical mart table names, excluding stock/basic entity stores."""

    if use_canonical_v2():
        return frozenset(
            mapping.table_name for mapping in CANONICAL_DATASET_TABLE_MAPPINGS_V2
        )
    return frozenset(
        mapping.table_name for mapping in CANONICAL_DATASET_TABLE_MAPPINGS
    )


__all__ = [
    "CANONICAL_DATASET_TABLE_MAPPINGS",
    "CANONICAL_DATASET_TABLE_MAPPINGS_V2",
    "CanonicalDatasetTable",
    "UnsupportedCanonicalDataset",
    "USE_CANONICAL_V2_ENV_VAR",
    "canonical_alias_column_for_dataset",
    "canonical_dataset_for_table",
    "canonical_datasets_for_table",
    "canonical_mart_table_names",
    "canonical_table_for_dataset",
    "canonical_table_identifier_for_dataset",
    "canonical_table_mapping_for_dataset",
    "use_canonical_v2",
]
