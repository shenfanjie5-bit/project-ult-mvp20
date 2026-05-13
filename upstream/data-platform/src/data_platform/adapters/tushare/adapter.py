"""Tushare adapter for Raw Zone structured Tushare assets."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from data_platform.adapters.base import AdapterFetchError, AssetSpec, BaseAdapter, FetchParams
from data_platform.adapters.tushare.assets import (
    ALLOW_NULL_IDENTITY_METADATA_KEY,
    ALLOW_NULL_IDENTITY_METADATA_VALUE,
    EVENT_METADATA_FIELDS,
    FINANCIAL_DATASET_FIELDS,
    FINANCIAL_VERSION_FIELDS,
    FORECAST_DATASET_FIELDS,
    FORECAST_VERSION_FIELDS,
    HOLDINGS_DATASET_FIELDS,
    REFERENCE_DATA_IDENTITY_FIELDS,
    TUSHARE_ASSETS,
    TUSHARE_STOCK_BASIC_ASSET_NAME,
)
from data_platform.raw import RawArtifact, RawWriter

TOKEN_ENV_VAR = "DP_TUSHARE_TOKEN"
STOCK_BASIC_IDENTITY_FIELDS = ("ts_code",)
MARKET_DATA_IDENTITY_FIELDS = ("ts_code", "trade_date")
MARKET_DATASETS = frozenset(
    {
        "daily",
        "weekly",
        "monthly",
        "adj_factor",
        "daily_basic",
        # Plan §5 expansion — stk_limit (per-day price-limit band) +
        # moneyflow (per-day fund flow breakdown) follow the same
        # (ts_code, trade_date) identity as daily_basic.
        "stk_limit",
        "moneyflow",
    }
)
EVENT_DATASETS = frozenset(EVENT_METADATA_FIELDS)  # includes block_trade via Plan §5
FINANCIAL_DATASETS = frozenset(FINANCIAL_DATASET_FIELDS)
# Plan §5 expansion — forecast is its own family (NOT financial;
# field set lacks f_ann_date / report_type / comp_type). See
# assets.FORECAST_DATASET_FIELDS / FORECAST_VERSION_FIELDS.
FORECAST_DATASETS = frozenset(FORECAST_DATASET_FIELDS)
HOLDINGS_DATASETS = frozenset(HOLDINGS_DATASET_FIELDS)
FINANCIAL_REQUIRED_FIELDS = (
    FINANCIAL_VERSION_FIELDS[0],
    FINANCIAL_VERSION_FIELDS[1],
    FINANCIAL_VERSION_FIELDS[3],
    FINANCIAL_VERSION_FIELDS[4],
    FINANCIAL_VERSION_FIELDS[5],
    FINANCIAL_VERSION_FIELDS[6],
)
FINANCIAL_DATE_FIELDS = frozenset({"ann_date", "f_ann_date", "end_date"})
STOCK_TS_CODE_DATASETS = frozenset(
    {
        "stock_basic",
        "daily",
        "weekly",
        "monthly",
        "adj_factor",
        "daily_basic",
        "stock_company",
        "namechange",
        *EVENT_DATASETS,  # includes block_trade per Plan §5
        "top10_holders",
        "top10_floatholders",
        "hsgt_top10",
        "hsgt_hold_top10",
        *FINANCIAL_DATASETS,
        *FORECAST_DATASETS,  # Plan §5 — forecast keyed on ts_code
        "stk_limit",  # Plan §5 — market-like, ts_code identity
        "moneyflow",  # Plan §5 — market-like, ts_code identity
    }
)
DATE_IDENTITY_FIELDS = frozenset(
    {"trade_date", "cal_date", "start_date", "in_date", "ann_date", "end_date", "float_date"}
)
STOCK_BASIC_TS_CODE_PATTERN = re.compile(r"\d{6}\.(?:SH|SZ|BJ)")
TRADE_DATE_PATTERN = re.compile(r"\d{8}")
FUND_PORTFOLIO_PAGE_LIMIT = 5_000
HK_HOLD_PAGE_LIMIT = 3_800
HK_HOLD_EXCHANGES = ("SH", "SZ")
EXPLICIT_TS_CODE_RAW_DATASETS = frozenset({"top10_holders", "top10_floatholders"})
EXPLICIT_TS_CODES_PARAM = "ts_codes"


@dataclass(frozen=True, slots=True)
class _TushareFetchSpec:
    asset: AssetSpec
    method_name: str
    identity_fields: tuple[str, ...]
    partition_date_field: str | None = None
    partition_request_params: tuple[str, ...] = ()
    date_param_names: tuple[str, ...] = ()


class AdapterConfigError(RuntimeError):
    """Raised when an adapter is missing required runtime configuration."""


class UpstreamSchemaError(ValueError):
    """Raised when an upstream Tushare response does not match the declared schema."""


class UpstreamDataQualityError(ValueError):
    """Raised when upstream Tushare values violate the Raw contract."""


class UpstreamEmptyResult(ValueError):
    """Raised when Tushare returns no rows for a Raw Zone event partition."""


class _TushareClient(Protocol):
    def stock_basic(self, **kwargs: Any) -> Any:
        """Return stock_basic rows from Tushare Pro."""

    def daily(self, **kwargs: Any) -> Any:
        """Return daily bar rows from Tushare Pro."""

    def weekly(self, **kwargs: Any) -> Any:
        """Return weekly bar rows from Tushare Pro."""

    def monthly(self, **kwargs: Any) -> Any:
        """Return monthly bar rows from Tushare Pro."""

    def adj_factor(self, **kwargs: Any) -> Any:
        """Return adjustment factor rows from Tushare Pro."""

    def daily_basic(self, **kwargs: Any) -> Any:
        """Return daily basic rows from Tushare Pro."""

    def index_basic(self, **kwargs: Any) -> Any:
        """Return index_basic rows from Tushare Pro."""

    def index_daily(self, **kwargs: Any) -> Any:
        """Return index_daily rows from Tushare Pro."""

    def index_weight(self, **kwargs: Any) -> Any:
        """Return index_weight rows from Tushare Pro."""

    def index_member(self, **kwargs: Any) -> Any:
        """Return index_member rows from Tushare Pro."""

    def index_classify(self, **kwargs: Any) -> Any:
        """Return index_classify rows from Tushare Pro."""

    def trade_cal(self, **kwargs: Any) -> Any:
        """Return trade_cal rows from Tushare Pro."""

    def stock_company(self, **kwargs: Any) -> Any:
        """Return stock_company rows from Tushare Pro."""

    def namechange(self, **kwargs: Any) -> Any:
        """Return namechange rows from Tushare Pro."""

    def anns(self, **kwargs: Any) -> Any:
        """Return announcement metadata rows from Tushare Pro."""

    def suspend_d(self, **kwargs: Any) -> Any:
        """Return suspend/resume event rows from Tushare Pro."""

    def dividend(self, **kwargs: Any) -> Any:
        """Return dividend event rows from Tushare Pro."""

    def share_float(self, **kwargs: Any) -> Any:
        """Return restricted-share unlock event rows from Tushare Pro."""

    def stk_holdernumber(self, **kwargs: Any) -> Any:
        """Return shareholder count event rows from Tushare Pro."""

    def disclosure_date(self, **kwargs: Any) -> Any:
        """Return disclosure calendar event rows from Tushare Pro."""

    def income(self, **kwargs: Any) -> Any:
        """Return income statement rows from Tushare Pro."""

    def balancesheet(self, **kwargs: Any) -> Any:
        """Return balance sheet rows from Tushare Pro."""

    def cashflow(self, **kwargs: Any) -> Any:
        """Return cash flow statement rows from Tushare Pro."""

    def fina_indicator(self, **kwargs: Any) -> Any:
        """Return financial indicator rows from Tushare Pro."""

    # Plan §5 expansion — 4 new dataset fetch methods.
    def stk_limit(self, **kwargs: Any) -> Any:
        """Return per-day price-limit band rows from Tushare Pro."""

    def block_trade(self, **kwargs: Any) -> Any:
        """Return block-trade execution rows from Tushare Pro."""

    def moneyflow(self, **kwargs: Any) -> Any:
        """Return per-day fund-flow breakdown rows from Tushare Pro."""

    def forecast(self, **kwargs: Any) -> Any:
        """Return earnings-forecast notification rows from Tushare Pro."""

    # M1.13 expansion — 8 new event_timeline candidate fetch methods.
    def pledge_stat(self, **kwargs: Any) -> Any:
        """Return pledge summary snapshot rows from Tushare Pro."""

    def pledge_detail(self, **kwargs: Any) -> Any:
        """Return pledge agreement detail rows from Tushare Pro."""

    def repurchase(self, **kwargs: Any) -> Any:
        """Return share repurchase announcement rows from Tushare Pro."""

    def stk_holdertrade(self, **kwargs: Any) -> Any:
        """Return shareholder trade announcement rows from Tushare Pro."""

    def stk_surv(self, **kwargs: Any) -> Any:
        """Return institutional survey rows from Tushare Pro."""

    def limit_list_ths(self, **kwargs: Any) -> Any:
        """Return 同花顺 intra-day limit-pool snapshot rows from Tushare Pro."""

    def limit_list_d(self, **kwargs: Any) -> Any:
        """Return daily limit-hit / blow-up event rows from Tushare Pro."""

    def hm_detail(self, **kwargs: Any) -> Any:
        """Return hot-money entity per-stock daily trade rows from Tushare Pro."""

    # M4.5 holdings intake expansion.
    def top10_holders(self, **kwargs: Any) -> Any:
        """Return top 10 shareholder rows from Tushare Pro."""

    def top10_floatholders(self, **kwargs: Any) -> Any:
        """Return top 10 free-float shareholder rows from Tushare Pro."""

    def fund_portfolio(self, **kwargs: Any) -> Any:
        """Return fund portfolio holdings rows from Tushare Pro."""

    def hsgt_top10(self, **kwargs: Any) -> Any:
        """Return northbound top turnover rows from Tushare Pro."""

    def hk_hold(self, **kwargs: Any) -> Any:
        """Return northbound holding rows from Tushare Pro."""


class TushareAdapter(BaseAdapter):
    """Tushare reference adapter exposing Raw Zone structured assets."""

    def __init__(
        self,
        *,
        token: str | None = None,
        client: _TushareClient | None = None,
        max_retries: int = 3,
    ) -> None:
        resolved_token = token or os.environ.get(TOKEN_ENV_VAR)
        if not resolved_token:
            msg = f"{TOKEN_ENV_VAR} is required for the Tushare adapter"
            raise AdapterConfigError(msg)

        self._token = resolved_token
        self._client = client
        self._quota_config: dict[str, Any] = {
            "requests_per_minute": 200,
            "daily_credit_quota": None,
        }
        super().__init__(max_retries=max_retries)

    def source_id(self) -> str:
        return "tushare"

    def get_assets(self) -> list[AssetSpec]:
        return list(TUSHARE_ASSETS)

    def get_resources(self) -> dict[str, Any]:
        return {"token_env": TOKEN_ENV_VAR}

    def get_staging_dbt_models(self) -> list[str]:
        return [f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS]

    def get_quota_config(self) -> dict[str, Any]:
        return dict(self._quota_config)

    def _fetch(self, asset_id: str, params: FetchParams) -> pa.Table:
        spec = _fetch_spec_by_asset_name(asset_id)
        request_params = dict(params)
        _validate_date_params(spec.asset.dataset, request_params, spec.date_param_names)
        _validate_required_fetch_params(spec.asset.dataset, request_params)
        request_params["fields"] = _fields_csv(spec.asset)

        fetch_method = getattr(self._get_client(), spec.method_name)
        if spec.asset.dataset == "fund_portfolio":
            return _fetch_fund_portfolio_table(fetch_method, request_params, spec.asset)
        if spec.asset.dataset == "hsgt_hold_top10":
            return _fetch_hk_hold_table(fetch_method, request_params, spec.asset)

        result = fetch_method(**request_params)
        if spec.asset.dataset in REFERENCE_DATA_IDENTITY_FIELDS:
            return _to_reference_table(spec.asset.dataset, result, spec.asset.schema)
        if spec.asset.dataset in EVENT_METADATA_FIELDS:
            return _to_event_table(spec.asset.dataset, result, spec.asset.schema)
        if spec.asset.dataset in FINANCIAL_DATASET_FIELDS:
            return _to_financial_table(spec.asset.dataset, result, spec.asset.schema)
        # Plan §5 expansion — forecast has multi-version identity but
        # field set distinct from FINANCIAL, so it gets its own branch.
        if spec.asset.dataset in FORECAST_DATASET_FIELDS:
            return _to_forecast_table(spec.asset.dataset, result, spec.asset.schema)
        if spec.asset.dataset in HOLDINGS_DATASET_FIELDS:
            return _to_holdings_table(spec.asset.dataset, result, spec.asset.schema)
        return _to_asset_table(result, spec.asset, spec.identity_fields)

    def _get_client(self) -> _TushareClient:
        if self._client is not None:
            return self._client

        try:
            import tushare as ts  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            msg = "tushare>=1.4 is required to fetch Tushare assets"
            raise AdapterConfigError(msg) from exc

        client = cast(_TushareClient, ts.pro_api(self._token))
        self._client = client
        return client


def run_tushare_asset(
    asset_id: str,
    partition_date: date,
    params: FetchParams | None = None,
    *,
    raw_writer: RawWriter | None = None,
) -> RawArtifact:
    """Fetch a Tushare asset and write it as a Raw Zone Parquet artifact."""

    adapter = TushareAdapter()
    asset = _asset_by_name(adapter, asset_id)
    fetch_params = _fetch_params_for_raw_partition(asset, partition_date, params)
    table, request_params = _fetch_raw_table_for_params(adapter, asset, fetch_params)

    if not isinstance(table, pa.Table):
        msg = f"Tushare fetch returned unsupported result for asset={asset.name!r}"
        raise TypeError(msg)

    if asset.partition == "daily":
        spec = _fetch_spec_by_asset_name(asset.name)
        _validate_raw_partition_date(table, asset, partition_date, spec.partition_date_field)

    request_params["fields"] = _fields_csv(asset)
    writer = raw_writer or RawWriter()
    return writer.write_arrow(
        adapter.source_id(),
        asset.dataset,
        partition_date,
        str(uuid.uuid4()),
        table,
        metadata=asset.metadata,
        request_params=request_params,
    )


def run_stock_basic(asset_id: str, partition_date: date) -> RawArtifact:
    """Compatibility wrapper for the original stock_basic Raw runner."""

    return run_tushare_asset(asset_id, partition_date)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Tushare assets into the Raw Zone.")
    parser.add_argument("--asset", required=True)
    parser.add_argument("--date", required=True, help="Raw partition date in YYYYMMDD format.")
    parser.add_argument(
        "--ts-code",
        action="append",
        help=(
            "Tushare ts_code filter. Required for top10_holders/top10_floatholders; "
            "repeat or comma-separate to write one combined raw partition artifact."
        ),
    )
    parser.add_argument(
        "--exchange",
        help="Optional Tushare exchange filter, e.g. SH or SZ for hk_hold-backed assets.",
    )
    args = parser.parse_args(argv)

    try:
        partition_date = _parse_partition_date(args.date)
        artifact = run_tushare_asset(
            args.asset,
            partition_date,
            params=_cli_fetch_params(args),
        )
    except Exception as exc:
        _print_error(exc, args.asset)
        return 1

    print(artifact.path)
    return 0


def _asset_by_name(adapter: TushareAdapter, asset_id: str) -> AssetSpec:
    for asset in adapter.get_assets():
        if asset.name == asset_id:
            return asset
    msg = f"unsupported Tushare asset: {asset_id!r}"
    raise ValueError(msg)


def _fetch_spec_by_asset_name(asset_id: str) -> _TushareFetchSpec:
    try:
        return _FETCH_SPECS_BY_ASSET_NAME[asset_id]
    except KeyError as exc:
        msg = f"unsupported Tushare asset: {asset_id!r}"
        raise ValueError(msg) from exc


def _fetch_params_for_raw_partition(
    asset: AssetSpec,
    partition_date: date,
    params: FetchParams | None,
) -> dict[str, Any]:
    fetch_params = dict(params or {})
    if asset.partition == "daily":
        spec = _fetch_spec_by_asset_name(asset.name)
        expected_trade_date = f"{partition_date:%Y%m%d}"
        for param_name in spec.partition_request_params:
            if param_name not in fetch_params:
                fetch_params[param_name] = expected_trade_date
                continue

            _validate_date_param(asset.dataset, param_name, fetch_params[param_name])
            if str(fetch_params[param_name]) != expected_trade_date:
                msg = (
                    f"Tushare {asset.dataset} {param_name} {fetch_params[param_name]!r} "
                    f"does not match Raw partition date {expected_trade_date!r}"
                )
                raise ValueError(msg)
    return fetch_params


def _fetch_raw_table_for_params(
    adapter: TushareAdapter,
    asset: AssetSpec,
    fetch_params: Mapping[str, Any],
) -> tuple[pa.Table, dict[str, Any]]:
    request_params = dict(fetch_params)
    if EXPLICIT_TS_CODES_PARAM not in request_params:
        table = adapter.fetch(asset.name, request_params)
        return cast(pa.Table, table), request_params

    if asset.dataset not in EXPLICIT_TS_CODE_RAW_DATASETS:
        msg = (
            f"Tushare {asset.dataset} raw partition does not support "
            f"{EXPLICIT_TS_CODES_PARAM!r}; pass a single ts_code instead"
        )
        raise ValueError(msg)
    if "ts_code" in request_params:
        msg = (
            f"Tushare {asset.dataset} raw partition accepts either ts_code or "
            f"{EXPLICIT_TS_CODES_PARAM}, not both"
        )
        raise ValueError(msg)

    ts_codes = _parse_ts_code_list(asset.dataset, request_params.pop(EXPLICIT_TS_CODES_PARAM))
    tables: list[pa.Table] = []
    for ts_code in ts_codes:
        table = adapter.fetch(asset.name, {**request_params, "ts_code": ts_code})
        if not isinstance(table, pa.Table):
            msg = f"Tushare fetch returned unsupported result for asset={asset.name!r}"
            raise TypeError(msg)
        tables.append(table)

    return pa.concat_tables(tables), {**request_params, EXPLICIT_TS_CODES_PARAM: ts_codes}


def _cli_fetch_params(args: argparse.Namespace) -> dict[str, Any] | None:
    params: dict[str, Any] = {}
    if args.exchange:
        params["exchange"] = args.exchange

    if args.ts_code:
        ts_codes: list[str] = []
        for value in args.ts_code:
            ts_codes.extend(part.strip() for part in value.split(","))
        ts_codes = [value for value in ts_codes if value]
        if len(ts_codes) == 1:
            params["ts_code"] = ts_codes[0]
        elif ts_codes:
            params[EXPLICIT_TS_CODES_PARAM] = tuple(ts_codes)

    return params or None


def _parse_partition_date(value: str) -> date:
    if not TRADE_DATE_PATTERN.fullmatch(value):
        msg = f"date must use YYYYMMDD format: {value!r}"
        raise ValueError(msg)

    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        msg = f"date must use YYYYMMDD format: {value!r}"
        raise ValueError(msg) from exc


def _to_stock_basic_table(value: Any) -> pa.Table:
    spec = _fetch_spec_by_asset_name(TUSHARE_STOCK_BASIC_ASSET_NAME)
    return _to_asset_table(value, spec.asset, spec.identity_fields)


def _to_reference_table(dataset: str, result: Any, schema: pa.Schema) -> pa.Table:
    try:
        spec = _FETCH_SPECS_BY_DATASET[dataset]
        identity_fields = REFERENCE_DATA_IDENTITY_FIELDS[dataset]
    except KeyError as exc:
        msg = f"unsupported Tushare reference dataset: {dataset!r}"
        raise ValueError(msg) from exc

    asset = AssetSpec(
        name=spec.asset.name,
        dataset=spec.asset.dataset,
        partition=spec.asset.partition,
        schema=schema,
    )
    return _to_asset_table(result, asset, identity_fields)


def _to_event_table(dataset: str, result: Any, schema: pa.Schema) -> pa.Table:
    try:
        spec = _FETCH_SPECS_BY_DATASET[dataset]
        identity_fields = EVENT_IDENTITY_FIELDS[dataset]
        event_date_fields = EVENT_DATE_FIELDS[dataset]
    except KeyError as exc:
        msg = f"unsupported Tushare event dataset: {dataset!r}"
        raise ValueError(msg) from exc

    asset = AssetSpec(
        name=spec.asset.name,
        dataset=spec.asset.dataset,
        partition=spec.asset.partition,
        schema=schema,
    )
    table = _to_asset_table(result, asset, identity_fields)
    if table.num_rows == 0:
        msg = f"Tushare {asset.dataset} response returned an empty table"
        raise UpstreamEmptyResult(msg)
    _validate_event_date_columns(table, asset, event_date_fields)
    return table


def _to_forecast_table(dataset: str, result: Any, schema: pa.Schema) -> pa.Table:
    """Plan §5 — route forecast through its own table builder.

    Mirrors ``_to_event_table`` shape but pulls identity from
    ``FORECAST_IDENTITY_FIELDS`` (which carries the version-aware
    ``FORECAST_VERSION_FIELDS`` tuple, i.e. ts_code + ann_date +
    end_date + update_flag) and date columns from
    ``FORECAST_DATE_FIELDS``. Not reusing ``_to_event_table`` because
    forecast is not semantically an event (it's a multi-version
    notification about a future financial report); conflating the two
    loses the distinction in stack traces + makes ``EVENT_IDENTITY_FIELDS``
    misleading.
    """
    try:
        spec = _FETCH_SPECS_BY_DATASET[dataset]
        identity_fields = FORECAST_IDENTITY_FIELDS[dataset]
        forecast_date_fields = FORECAST_DATE_FIELDS[dataset]
    except KeyError as exc:
        msg = f"unsupported Tushare forecast dataset: {dataset!r}"
        raise ValueError(msg) from exc

    asset = AssetSpec(
        name=spec.asset.name,
        dataset=spec.asset.dataset,
        partition=spec.asset.partition,
        schema=schema,
    )
    table = _to_asset_table(result, asset, identity_fields)
    if table.num_rows == 0:
        msg = f"Tushare {asset.dataset} response returned an empty table"
        raise UpstreamEmptyResult(msg)
    _validate_event_date_columns(table, asset, forecast_date_fields)
    return table


def _to_holdings_table(dataset: str, result: Any, schema: pa.Schema) -> pa.Table:
    try:
        spec = _FETCH_SPECS_BY_DATASET[dataset]
        identity_fields = HOLDINGS_IDENTITY_FIELDS[dataset]
        date_fields = HOLDINGS_DATE_FIELDS[dataset]
    except KeyError as exc:
        msg = f"unsupported Tushare holdings dataset: {dataset!r}"
        raise ValueError(msg) from exc

    asset = AssetSpec(
        name=spec.asset.name,
        dataset=spec.asset.dataset,
        partition=spec.asset.partition,
        schema=schema,
    )
    table = _to_asset_table(result, asset, identity_fields)
    if table.num_rows == 0:
        msg = f"Tushare {asset.dataset} response returned an empty table"
        raise UpstreamEmptyResult(msg)
    _validate_event_date_columns(table, asset, date_fields)
    return table


def _fetch_fund_portfolio_table(
    fetch_method: Any,
    request_params: Mapping[str, Any],
    asset: AssetSpec,
) -> pa.Table:
    """Fetch fund_portfolio through Tushare's limit/offset pagination surface."""

    return _fetch_paginated_holdings_table(
        fetch_method,
        request_params,
        asset,
        default_page_limit=FUND_PORTFOLIO_PAGE_LIMIT,
        pagination_label="fund_portfolio",
    )


def _fetch_hk_hold_table(
    fetch_method: Any,
    request_params: Mapping[str, Any],
    asset: AssetSpec,
) -> pa.Table:
    """Fetch hk_hold with exchange splitting and limit/offset pagination.

    Tushare documents a 3,800-row cap for hk_hold. A trade-date-only call can
    silently truncate, so the raw path splits the unscoped request by SH/SZ and
    paginates each exchange. If callers pass exchange explicitly, only that
    exchange is paginated.
    """

    scope_params = None
    if not _has_explicit_param(request_params, "exchange"):
        scope_params = tuple({"exchange": exchange} for exchange in HK_HOLD_EXCHANGES)
    return _fetch_paginated_holdings_table(
        fetch_method,
        request_params,
        asset,
        default_page_limit=HK_HOLD_PAGE_LIMIT,
        pagination_label="hk_hold",
        scope_params=scope_params,
    )


def _fetch_paginated_holdings_table(
    fetch_method: Any,
    request_params: Mapping[str, Any],
    asset: AssetSpec,
    *,
    default_page_limit: int,
    pagination_label: str,
    scope_params: Sequence[Mapping[str, Any]] | None = None,
) -> pa.Table:
    """Fetch a holdings endpoint through Tushare's limit/offset surface."""

    base_params = dict(request_params)
    page_limit = _positive_int_param(
        base_params.pop("limit", default_page_limit),
        "limit",
        pagination_label,
    )
    initial_offset = _non_negative_int_param(
        base_params.pop("offset", 0),
        "offset",
        pagination_label,
    )
    page_tables: list[pa.Table] = []
    seen_keys: set[tuple[Any, ...]] = set()
    scopes = tuple(scope_params or ({},))

    for scope in scopes:
        offset = initial_offset
        while True:
            page_params = {
                **base_params,
                **dict(scope),
                "limit": page_limit,
                "offset": offset,
            }
            page_result = fetch_method(**page_params)
            page_table = _to_holdings_page_table(asset, page_result)
            if page_table.num_rows == 0:
                break

            page_keys = _identity_key_set(page_table, HOLDINGS_IDENTITY_FIELDS[asset.dataset])
            repeated_keys = seen_keys.intersection(page_keys)
            if repeated_keys:
                msg = (
                    f"Tushare {pagination_label} pagination did not advance; "
                    "received duplicate identity key(s) after applying offset/splitting"
                )
                raise UpstreamDataQualityError(msg)

            page_tables.append(page_table)
            seen_keys.update(page_keys)
            if page_table.num_rows < page_limit:
                break
            offset += page_table.num_rows

    if not page_tables:
        msg = f"Tushare {pagination_label} response returned an empty table"
        raise UpstreamEmptyResult(msg)
    return pa.concat_tables(page_tables)


def _to_holdings_page_table(asset: AssetSpec, result: Any) -> pa.Table:
    identity_fields = HOLDINGS_IDENTITY_FIELDS[asset.dataset]
    date_fields = HOLDINGS_DATE_FIELDS[asset.dataset]
    table = _to_asset_table(result, asset, identity_fields)
    if table.num_rows:
        _validate_event_date_columns(table, asset, date_fields)
    return table


def _positive_int_param(value: Any, name: str, dataset: str = "fund_portfolio") -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        msg = f"Tushare {dataset} {name} must be a positive integer"
        raise ValueError(msg) from exc
    if parsed < 1:
        msg = f"Tushare {dataset} {name} must be a positive integer"
        raise ValueError(msg)
    return parsed


def _non_negative_int_param(value: Any, name: str, dataset: str = "fund_portfolio") -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        msg = f"Tushare {dataset} {name} must be a non-negative integer"
        raise ValueError(msg) from exc
    if parsed < 0:
        msg = f"Tushare {dataset} {name} must be a non-negative integer"
        raise ValueError(msg)
    return parsed


def _identity_key_set(
    table: pa.Table,
    identity_fields: tuple[str, ...],
) -> set[tuple[Any, ...]]:
    columns = [table[field_name].to_pylist() for field_name in identity_fields]
    return {
        tuple(column[row_index] for column in columns)
        for row_index in range(table.num_rows)
    }


def _to_financial_table(dataset: str, result: Any, schema: pa.Schema) -> pa.Table:
    try:
        spec = _FETCH_SPECS_BY_DATASET[dataset]
    except KeyError as exc:
        msg = f"unsupported Tushare financial dataset: {dataset!r}"
        raise ValueError(msg) from exc

    asset = AssetSpec(
        name=spec.asset.name,
        dataset=spec.asset.dataset,
        partition=spec.asset.partition,
        schema=schema,
    )
    field_names = _field_names_from_table_or_result(result)
    if field_names is not None:
        _validate_asset_fields(field_names, asset)

    rows = _financial_records_from_result(result, asset)
    normalized_rows = _normalize_financial_records(rows, asset)
    try:
        _validate_asset_records(normalized_rows, asset, FINANCIAL_REQUIRED_FIELDS)
    except UpstreamSchemaError:
        raise
    except ValueError as exc:
        raise UpstreamDataQualityError(str(exc)) from exc
    columns = {
        field.name: [row[field.name] for row in normalized_rows]
        for field in asset.schema
    }
    try:
        return pa.table(columns, schema=asset.schema)
    except (pa.ArrowInvalid, pa.ArrowTypeError) as exc:
        msg = f"Tushare {dataset} response could not be converted to financial schema: {exc}"
        raise UpstreamSchemaError(msg) from exc


def _to_asset_table(
    value: Any,
    asset: AssetSpec,
    identity_fields: tuple[str, ...],
) -> pa.Table:
    if isinstance(value, pa.Table):
        _validate_asset_fields(value.column_names, asset)
        _validate_asset_identity_columns(value, asset, identity_fields)
        return value.select(asset.schema.names).cast(asset.schema)

    field_names = _field_names_from_result(value)
    if field_names is not None:
        _validate_asset_fields(field_names, asset)

    rows = _records_from_result(value, asset)
    _validate_asset_records(rows, asset, identity_fields)
    columns = {
        field.name: [_normalize_value(row[field.name], field.type) for row in rows]
        for field in asset.schema
    }
    return pa.table(columns, schema=asset.schema)


def _validate_asset_fields(field_names: Sequence[str], asset: AssetSpec) -> None:
    available = set(field_names)
    missing = [field_name for field_name in asset.schema.names if field_name not in available]
    if missing:
        joined = ", ".join(missing)
        msg = f"Tushare {asset.dataset} response missing required fields: {joined}"
        raise UpstreamSchemaError(msg)


def _field_names_from_result(value: Any) -> list[str] | None:
    columns = getattr(value, "columns", None)
    if columns is None:
        return None

    try:
        return [str(field_name) for field_name in columns]
    except TypeError:
        return None


def _records_from_result(value: Any, asset: AssetSpec) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return _coerce_record_list(value, asset)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        records = to_dict("records")
        if isinstance(records, list):
            return _coerce_record_list(records, asset)

    msg = f"Tushare {asset.dataset} result must be a pandas DataFrame, Arrow table, or row list"
    raise TypeError(msg)


def _field_names_from_table_or_result(value: Any) -> list[str] | None:
    if isinstance(value, pa.Table):
        return list(value.column_names)
    return _field_names_from_result(value)


def _financial_records_from_result(value: Any, asset: AssetSpec) -> list[Mapping[str, Any]]:
    if isinstance(value, pa.Table):
        return _coerce_record_list(value.to_pylist(), asset)
    return _records_from_result(value, asset)


def _coerce_record_list(rows: list[Any], asset: AssetSpec) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            msg = (
                f"Tushare {asset.dataset} row "
                f"{index} must be a mapping, got {type(row).__name__}"
            )
            raise TypeError(msg)
        records.append(row)
    return records


def _normalize_financial_records(
    rows: Sequence[Mapping[str, Any]],
    asset: AssetSpec,
) -> list[Mapping[str, Any]]:
    normalized_rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        missing = [field_name for field_name in asset.schema.names if field_name not in row]
        if missing:
            joined = ", ".join(missing)
            msg = f"Tushare {asset.dataset} row {index} missing required fields: {joined}"
            raise UpstreamSchemaError(msg)

        normalized_rows.append(
            {
                field.name: _normalize_financial_value(row[field.name], field, index, asset)
                for field in asset.schema
            }
        )
    return normalized_rows


def _normalize_financial_value(
    value: Any,
    field: pa.Field,
    row_index: int,
    asset: AssetSpec,
) -> Any:
    if _is_nullish(value):
        return None
    if pa.types.is_string(field.type):
        normalized = _normalize_string(value)
        if normalized is not None and field.name in FINANCIAL_DATE_FIELDS:
            return normalized.strip()
        return normalized
    if pa.types.is_decimal(field.type):
        return _normalize_decimal(value, field.name, row_index, asset)
    return value


def _normalize_decimal(
    value: Any,
    field_name: str,
    row_index: int,
    asset: AssetSpec,
) -> Decimal | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        msg = (
            f"Tushare {asset.dataset} row {row_index} has invalid numeric field: "
            f"{field_name}"
        )
        raise UpstreamDataQualityError(msg) from exc


def _validate_asset_records(
    rows: Sequence[Mapping[str, Any]],
    asset: AssetSpec,
    identity_fields: tuple[str, ...],
) -> None:
    for index, row in enumerate(rows):
        missing = [field_name for field_name in asset.schema.names if field_name not in row]
        if missing:
            joined = ", ".join(missing)
            msg = f"Tushare {asset.dataset} row {index} missing required fields: {joined}"
            raise UpstreamSchemaError(msg)

        for field_name in identity_fields:
            _validate_identity_value(row[field_name], index, field_name, asset)


def _validate_asset_identity_columns(
    table: pa.Table,
    asset: AssetSpec,
    identity_fields: tuple[str, ...],
) -> None:
    for field_name in identity_fields:
        values = table[field_name].to_pylist()
        for index, value in enumerate(values):
            _validate_identity_value(value, index, field_name, asset)


def _validate_identity_value(
    value: Any,
    row_index: int,
    field_name: str,
    asset: AssetSpec,
) -> None:
    if _is_nullish(value):
        if _allows_null_identity(asset.schema, field_name):
            return
        msg = f"Tushare {asset.dataset} row {row_index} has null identity field: {field_name}"
        raise ValueError(msg)

    if not pd.api.types.is_scalar(value):
        msg = (
            f"Tushare {asset.dataset} row {row_index} has non-scalar identity field: "
            f"{field_name}"
        )
        raise ValueError(msg)

    normalized_value = str(value)
    if not normalized_value.strip():
        if _allows_null_identity(asset.schema, field_name):
            return
        msg = f"Tushare {asset.dataset} row {row_index} has blank identity field: {field_name}"
        raise ValueError(msg)

    if field_name == "ts_code" and asset.dataset in STOCK_TS_CODE_DATASETS and (
        normalized_value != normalized_value.strip()
        or not STOCK_BASIC_TS_CODE_PATTERN.fullmatch(normalized_value)
    ):
        msg = f"Tushare {asset.dataset} row {row_index} has malformed identity field: {field_name}"
        raise ValueError(msg)

    if field_name in DATE_IDENTITY_FIELDS and not _is_valid_trade_date(normalized_value):
        msg = f"Tushare {asset.dataset} row {row_index} has malformed identity field: {field_name}"
        raise ValueError(msg)


def _validate_date_params(
    dataset: str,
    params: Mapping[str, Any],
    param_names: tuple[str, ...],
) -> None:
    for param_name in param_names:
        value = params.get(param_name)
        if value is None:
            continue
        _validate_date_param(dataset, param_name, value)


def _validate_required_fetch_params(dataset: str, params: Mapping[str, Any]) -> None:
    if dataset in EXPLICIT_TS_CODE_RAW_DATASETS:
        if not _has_explicit_param(params, "ts_code"):
            msg = (
                f"Tushare {dataset} requires explicit ts_code for live/raw fetch; "
                "the Raw daily partition can derive period only, not a symbol universe"
            )
            raise ValueError(msg)
        _validate_ts_code_param(dataset, params["ts_code"])


def _validate_date_param(dataset: str, param_name: str, value: Any) -> None:
    if not pd.api.types.is_scalar(value) or _is_nullish(value):
        msg = f"Tushare {dataset} {param_name} must be a YYYYMMDD string"
        raise ValueError(msg)
    if not _is_valid_trade_date(str(value)):
        msg = f"Tushare {dataset} {param_name} must be a valid YYYYMMDD date: {value!r}"
        raise ValueError(msg)


def _validate_ts_code_param(dataset: str, value: Any) -> None:
    if not pd.api.types.is_scalar(value) or _is_nullish(value):
        msg = f"Tushare {dataset} ts_code must be a CN A-share code like 000001.SZ"
        raise ValueError(msg)
    normalized = str(value).strip()
    if normalized != str(value) or not STOCK_BASIC_TS_CODE_PATTERN.fullmatch(normalized):
        msg = f"Tushare {dataset} ts_code must be a CN A-share code like 000001.SZ"
        raise ValueError(msg)


def _parse_ts_code_list(dataset: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence):
        candidates = [str(part).strip() for part in value]
    else:
        msg = f"Tushare {dataset} {EXPLICIT_TS_CODES_PARAM} must be a non-empty list"
        raise ValueError(msg)

    ts_codes = tuple(candidate for candidate in candidates if candidate)
    if not ts_codes:
        msg = f"Tushare {dataset} {EXPLICIT_TS_CODES_PARAM} must be a non-empty list"
        raise ValueError(msg)
    for ts_code in ts_codes:
        _validate_ts_code_param(dataset, ts_code)
    return ts_codes


def _has_explicit_param(params: Mapping[str, Any], param_name: str) -> bool:
    value = params.get(param_name)
    if value is None or _is_nullish(value):
        return False
    return bool(str(value).strip())


def _validate_raw_partition_date(
    table: pa.Table,
    asset: AssetSpec,
    partition_date: date,
    partition_date_field: str | None,
) -> None:
    if partition_date_field is None:
        msg = f"Tushare {asset.dataset} daily partition date field is not configured"
        raise ValueError(msg)

    expected_trade_date = f"{partition_date:%Y%m%d}"
    if partition_date_field not in table.column_names:
        msg = f"Tushare {asset.dataset} response missing required fields: {partition_date_field}"
        raise ValueError(msg)

    for index, value in enumerate(table[partition_date_field].to_pylist()):
        if str(value) != expected_trade_date:
            msg = (
                f"Tushare {asset.dataset} row {index} {partition_date_field} {value!r} "
                f"does not match Raw partition date {expected_trade_date!r}"
            )
            raise ValueError(msg)


def _validate_event_date_columns(
    table: pa.Table,
    asset: AssetSpec,
    event_date_fields: tuple[str, ...],
) -> None:
    for field_name in event_date_fields:
        if field_name not in table.column_names:
            msg = f"Tushare {asset.dataset} response missing required fields: {field_name}"
            raise UpstreamSchemaError(msg)

        for index, value in enumerate(table[field_name].to_pylist()):
            if not pd.api.types.is_scalar(value) or _is_nullish(value):
                msg = (
                    f"Tushare {asset.dataset} row {index} has null event date field: "
                    f"{field_name}"
                )
                raise ValueError(msg)
            if not _is_valid_trade_date(str(value)):
                msg = (
                    f"Tushare {asset.dataset} row {index} has malformed event date field: "
                    f"{field_name}"
                )
                raise ValueError(msg)


def _allows_null_identity(schema: pa.Schema, field_name: str) -> bool:
    field = schema.field(field_name)
    metadata = field.metadata or {}
    return metadata.get(ALLOW_NULL_IDENTITY_METADATA_KEY) == ALLOW_NULL_IDENTITY_METADATA_VALUE


def _is_valid_trade_date(value: str) -> bool:
    if not TRADE_DATE_PATTERN.fullmatch(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return False
    return f"{parsed:%Y%m%d}" == value


def _fields_csv(asset: AssetSpec) -> str:
    return ",".join(asset.schema.names)


def _normalize_value(value: Any, data_type: pa.DataType) -> Any:
    if _is_nullish(value):
        return None
    if pa.types.is_string(data_type):
        return _normalize_string(value)
    return value


def _normalize_string(value: Any) -> str | None:
    if _is_nullish(value):
        return None
    return str(value)


def _is_nullish(value: Any) -> bool:
    if value is None:
        return True

    result = pd.isna(value)
    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def _print_error(exc: BaseException, asset_id: str) -> None:
    payload = {"error": str(exc), "asset": asset_id, "error_type": _error_type(exc)}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)


def _error_type(exc: BaseException) -> str:
    cause = exc.cause if isinstance(exc, AdapterFetchError) else exc
    if isinstance(cause, AdapterConfigError):
        return "config_error"
    if isinstance(cause, UpstreamDataQualityError):
        return "upstream_data_quality"
    if isinstance(cause, UpstreamSchemaError):
        return "upstream_missing_columns"
    if isinstance(cause, UpstreamEmptyResult):
        return "upstream_empty_table"
    return "runtime_error"


EVENT_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "anns": ("ts_code", "ann_date", "title", "url"),
    "suspend_d": ("ts_code", "trade_date"),
    "dividend": ("ts_code", "ann_date", "end_date"),
    "share_float": ("ts_code", "ann_date", "float_date"),
    "stk_holdernumber": ("ts_code", "ann_date", "end_date"),
    "disclosure_date": ("ts_code", "ann_date", "end_date"),
    # Plan §5 expansion — block_trade follows the anns precedent: same
    # (ts_code, trade_date) CAN repeat (multiple block trades same day,
    # distinct buyer/seller/price/vol/amount), so identity widens to
    # the full row shape to make dbt unique_combination_of_columns
    # enforceable without suppressing the real-world multiplicity.
    # anns does exactly this with (ts_code, ann_date, title, url).
    "block_trade": (
        "ts_code",
        "trade_date",
        "buyer",
        "seller",
        "price",
        "vol",
        "amount",
    ),
    # M1.13 expansion (precondition 9 closure) — 8 candidate
    # event_timeline sources promoted with empirically-verified identity
    # tuples per the M1.11 sign-off table. Wide identities mirror the
    # block_trade/anns pattern.
    "pledge_stat": (
        "ts_code",
        "end_date",
        "pledge_count",
        "unrest_pledge",
        "rest_pledge",
        "total_share",
        "pledge_ratio",
    ),
    "pledge_detail": (
        "ts_code",
        "ann_date",
        "holder_name",
        "pledgor",
        "start_date",
        "end_date",
        "pledge_amount",
        "is_release",
    ),
    "repurchase": (
        "ts_code",
        "ann_date",
        "end_date",
        "proc",
        "exp_date",
        "vol",
        "amount",
        "high_limit",
        "low_limit",
    ),
    "stk_holdertrade": (
        "ts_code",
        "ann_date",
        "holder_name",
        "holder_type",
        "in_de",
        "change_vol",
        "change_ratio",
        "after_share",
        "after_ratio",
        "avg_price",
        "total_share",
    ),
    "stk_surv": ("ts_code", "surv_date", "rece_org", "rece_mode"),
    "limit_list_ths": ("trade_date", "ts_code", "status"),
    "limit_list_d": ("trade_date", "ts_code", "limit"),
    "hm_detail": ("trade_date", "ts_code", "hm_name"),
}
EVENT_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "anns": ("ann_date",),
    "suspend_d": ("trade_date",),
    "dividend": ("ann_date",),
    "share_float": ("ann_date", "float_date"),
    "stk_holdernumber": ("ann_date", "end_date"),
    "disclosure_date": ("ann_date", "end_date"),
    "block_trade": ("trade_date",),  # Plan §5
    # M1.13 expansion — partition date columns for non-null + ISO-shape
    # validation. Per M1.11 evidence: pledge_stat keyed on end_date,
    # pledge_detail/repurchase/stk_holdertrade on ann_date,
    # stk_surv on surv_date, limit_list_*/hm_detail on trade_date.
    "pledge_stat": ("end_date",),
    "pledge_detail": ("ann_date",),
    "repurchase": ("ann_date",),
    "stk_holdertrade": ("ann_date",),
    "stk_surv": ("surv_date",),
    "limit_list_ths": ("trade_date",),
    "limit_list_d": ("trade_date",),
    "hm_detail": ("trade_date",),
}
# Plan §5 expansion — forecast's identity keyed on (ts_code, ann_date,
# end_date, update_flag). Distinct from FINANCIAL_VERSION_FIELDS
# because forecast lacks f_ann_date / report_type / comp_type.
FORECAST_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "forecast": FORECAST_VERSION_FIELDS,
}
# Plan §5 expansion — date columns that the forecast fetcher validates
# as non-null + ISO-shape. ann_date is the announcement timestamp;
# end_date is the report period the forecast refers to; first_ann_date
# is the earliest announcement (may be null when update_flag='0').
FORECAST_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "forecast": ("ann_date", "end_date"),
}
HOLDINGS_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "top10_holders": ("ts_code", "end_date", "holder_name", "ann_date"),
    "top10_floatholders": ("ts_code", "end_date", "holder_name", "ann_date"),
    "fund_portfolio": ("ts_code", "end_date", "symbol", "ann_date"),
    "hsgt_top10": ("trade_date", "ts_code", "market_type", "rank"),
    "hsgt_hold_top10": ("trade_date", "ts_code", "exchange"),
}
HOLDINGS_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "top10_holders": ("ann_date", "end_date"),
    "top10_floatholders": ("ann_date", "end_date"),
    "fund_portfolio": ("ann_date", "end_date"),
    "hsgt_top10": ("trade_date",),
    "hsgt_hold_top10": ("trade_date",),
}
_METHOD_BY_DATASET = {
    "stock_basic": "stock_basic",
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "adj_factor": "adj_factor",
    "daily_basic": "daily_basic",
    "index_basic": "index_basic",
    "index_daily": "index_daily",
    "index_weight": "index_weight",
    "index_member": "index_member",
    "index_classify": "index_classify",
    "trade_cal": "trade_cal",
    "stock_company": "stock_company",
    "namechange": "namechange",
    "anns": "anns",
    "suspend_d": "suspend_d",
    "dividend": "dividend",
    "share_float": "share_float",
    "stk_holdernumber": "stk_holdernumber",
    "disclosure_date": "disclosure_date",
    "income": "income",
    "balancesheet": "balancesheet",
    "cashflow": "cashflow",
    "fina_indicator": "fina_indicator",
    # Plan §5 expansion — 4 new dataset -> tushare.pro method names.
    "stk_limit": "stk_limit",
    "block_trade": "block_trade",
    "moneyflow": "moneyflow",
    "forecast": "forecast",
    # M1.13 expansion (precondition 9 closure) — 8 new dataset → method names.
    "pledge_stat": "pledge_stat",
    "pledge_detail": "pledge_detail",
    "repurchase": "repurchase",
    "stk_holdertrade": "stk_holdertrade",
    "stk_surv": "stk_surv",
    "limit_list_ths": "limit_list_ths",
    "limit_list_d": "limit_list_d",
    "hm_detail": "hm_detail",
    # M4.5 holdings intake expansion. hsgt_hold_top10 is the data-platform
    # raw dataset name for Tushare's official hk_hold API.
    "top10_holders": "top10_holders",
    "top10_floatholders": "top10_floatholders",
    "fund_portfolio": "fund_portfolio",
    "hsgt_top10": "hsgt_top10",
    "hsgt_hold_top10": "hk_hold",
}
_IDENTITY_FIELDS_BY_DATASET = {
    "stock_basic": STOCK_BASIC_IDENTITY_FIELDS,
    **{dataset: MARKET_DATA_IDENTITY_FIELDS for dataset in MARKET_DATASETS},
    **REFERENCE_DATA_IDENTITY_FIELDS,
    **EVENT_IDENTITY_FIELDS,
    **{dataset: FINANCIAL_REQUIRED_FIELDS for dataset in FINANCIAL_DATASETS},
    **FORECAST_IDENTITY_FIELDS,  # Plan §5
    **HOLDINGS_IDENTITY_FIELDS,
}
_PARTITION_DATE_FIELD_BY_DATASET = {
    **{dataset: "trade_date" for dataset in MARKET_DATASETS},
    "index_daily": "trade_date",
    "index_weight": "trade_date",
    "index_member": "in_date",
    "trade_cal": "cal_date",
    "namechange": "start_date",
    "anns": "ann_date",
    "suspend_d": "trade_date",
    "dividend": "ann_date",
    "share_float": "ann_date",
    "stk_holdernumber": "ann_date",
    "disclosure_date": "ann_date",
    "block_trade": "trade_date",  # Plan §5
    "forecast": "ann_date",  # Plan §5
    # M1.13 expansion (precondition 9 closure).
    "pledge_stat": "end_date",
    "pledge_detail": "ann_date",
    "repurchase": "ann_date",
    "stk_holdertrade": "ann_date",
    "stk_surv": "surv_date",
    "limit_list_ths": "trade_date",
    "limit_list_d": "trade_date",
    "hm_detail": "trade_date",
    # M4.5 holdings intake expansion.
    "top10_holders": "end_date",
    "top10_floatholders": "end_date",
    "fund_portfolio": "end_date",
    "hsgt_top10": "trade_date",
    "hsgt_hold_top10": "trade_date",
    **{dataset: "end_date" for dataset in FINANCIAL_DATASETS},
}
_PARTITION_REQUEST_PARAMS_BY_DATASET = {
    **{dataset: ("trade_date",) for dataset in MARKET_DATASETS},
    "index_daily": ("trade_date",),
    "index_weight": ("trade_date",),
    "index_member": ("start_date", "end_date"),
    "trade_cal": ("start_date", "end_date"),
    "namechange": ("start_date", "end_date"),
    "anns": ("ann_date",),
    "suspend_d": ("trade_date",),
    "dividend": ("ann_date",),
    "share_float": ("ann_date",),
    "stk_holdernumber": ("ann_date",),
    "disclosure_date": ("ann_date",),
    "block_trade": ("trade_date",),  # Plan §5
    "forecast": ("ann_date",),  # Plan §5 — single partition date (like anns)
    # M1.13 expansion (precondition 9 closure) — single partition date per
    # M1.11 sign-off table's event_date column.
    "pledge_stat": ("end_date",),
    "pledge_detail": ("ann_date",),
    "repurchase": ("ann_date",),
    "stk_holdertrade": ("ann_date",),
    "stk_surv": ("surv_date",),
    "limit_list_ths": ("trade_date",),
    "limit_list_d": ("trade_date",),
    "hm_detail": ("trade_date",),
    # M4.5 holdings intake expansion.
    "top10_holders": ("period",),
    "top10_floatholders": ("period",),
    "fund_portfolio": ("period",),
    "hsgt_top10": ("trade_date",),
    "hsgt_hold_top10": ("trade_date",),
    **{dataset: ("period",) for dataset in FINANCIAL_DATASETS},
}
_DATE_PARAM_NAMES_BY_DATASET = {
    **{dataset: ("trade_date", "start_date", "end_date") for dataset in MARKET_DATASETS},
    "index_daily": ("trade_date", "start_date", "end_date"),
    "index_weight": ("trade_date", "start_date", "end_date"),
    "index_member": ("start_date", "end_date"),
    "trade_cal": ("start_date", "end_date"),
    "namechange": ("start_date", "end_date"),
    "anns": ("ann_date", "start_date", "end_date"),
    "suspend_d": ("trade_date", "start_date", "end_date"),
    "dividend": ("ann_date", "record_date", "ex_date", "pay_date", "start_date", "end_date"),
    "share_float": ("ann_date", "float_date", "start_date", "end_date"),
    "stk_holdernumber": ("ann_date", "end_date", "start_date"),
    "disclosure_date": (
        "ann_date",
        "end_date",
        "pre_date",
        "actual_date",
        "modify_date",
        "start_date",
    ),
    # Plan §5 expansion — date param names Tushare's stk_limit /
    # block_trade / moneyflow / forecast APIs expose.
    "block_trade": ("trade_date", "start_date", "end_date"),
    "forecast": ("ann_date", "end_date", "start_date", "period"),
    # M1.13 expansion (precondition 9 closure) — date params each Tushare
    # endpoint accepts. pledge_stat/repurchase/pledge_detail/stk_holdertrade
    # accept the standard ann_date/start_date/end_date trio; stk_surv uses
    # surv_date / start_date / end_date; limit_list_*/hm_detail are
    # trade-date-keyed.
    "pledge_stat": ("ann_date", "end_date", "start_date"),
    "pledge_detail": ("ann_date", "start_date", "end_date"),
    "repurchase": ("ann_date", "start_date", "end_date"),
    "stk_holdertrade": ("ann_date", "start_date", "end_date"),
    "stk_surv": ("surv_date", "start_date", "end_date"),
    "limit_list_ths": ("trade_date", "start_date", "end_date"),
    "limit_list_d": ("trade_date", "start_date", "end_date"),
    "hm_detail": ("trade_date", "start_date", "end_date"),
    # M4.5 holdings intake expansion.
    "top10_holders": ("period", "ann_date", "start_date", "end_date"),
    "top10_floatholders": ("period", "ann_date", "start_date", "end_date"),
    "fund_portfolio": ("period", "ann_date", "start_date", "end_date"),
    "hsgt_top10": ("trade_date", "start_date", "end_date"),
    "hsgt_hold_top10": ("trade_date", "start_date", "end_date"),
    **{
        dataset: ("ann_date", "start_date", "end_date", "period")
        for dataset in FINANCIAL_DATASETS
    },
}
_FETCH_SPECS_BY_ASSET_NAME = {
    _asset.name: _TushareFetchSpec(
        asset=_asset,
        method_name=_METHOD_BY_DATASET[_asset.dataset],
        identity_fields=_IDENTITY_FIELDS_BY_DATASET[_asset.dataset],
        partition_date_field=_PARTITION_DATE_FIELD_BY_DATASET.get(_asset.dataset),
        partition_request_params=_PARTITION_REQUEST_PARAMS_BY_DATASET.get(_asset.dataset, ()),
        date_param_names=_DATE_PARAM_NAMES_BY_DATASET.get(_asset.dataset, ()),
    )
    for _asset in TUSHARE_ASSETS
}
_FETCH_SPECS_BY_DATASET = {
    _fetch_spec.asset.dataset: _fetch_spec for _fetch_spec in _FETCH_SPECS_BY_ASSET_NAME.values()
}


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AdapterConfigError",
    "TOKEN_ENV_VAR",
    "TushareAdapter",
    "UpstreamDataQualityError",
    "_to_event_table",
    "_to_financial_table",
    "_to_forecast_table",
    "_to_reference_table",
    "main",
    "run_stock_basic",
    "run_tushare_asset",
]
