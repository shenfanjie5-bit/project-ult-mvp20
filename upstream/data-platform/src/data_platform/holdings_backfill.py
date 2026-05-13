"""Bounded historical backfill planning for holdings Raw Zone intake."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, TypeAlias

import pyarrow as pa  # type: ignore[import-untyped]

from data_platform.adapters.base import AssetSpec, FetchParams, FetchableAdapter
from data_platform.adapters.tushare.assets import TUSHARE_ASSETS
from data_platform.raw import RawArtifact, RawWriter


PlanItemStatus: TypeAlias = Literal["planned", "skipped", "rejected"]
ExecutionItemStatus: TypeAlias = Literal["ok", "skipped"]

SUPPORTED_HOLDINGS_BACKFILL_DATASETS: tuple[str, ...] = (
    "top10_holders",
    "top10_floatholders",
    "fund_portfolio",
    "hsgt_top10",
    "hsgt_hold_top10",
)
STOCK_CODE_DATASETS = frozenset({"top10_holders", "top10_floatholders"})
FUND_CODE_DATASETS = frozenset({"fund_portfolio"})
HSGT_BACKFILL_DATASETS = frozenset({"hsgt_top10", "hsgt_hold_top10"})
PUBLIC_IDENTIFIER_BOUND_CLASSES = {
    "stock_code": "stock_code",
    "fund_code": "fund_code",
}
PUBLIC_SAFE_BOUND_KEYS = frozenset(
    {
        "exchange",
        "market_type",
        "max_plan_items",
        "missing",
        "omitted_month_count",
        "period",
        "planned_count",
        "provider_available_end_date",
        "capped_month_count",
        "related_entity_hops",
        "start_date",
        "end_date",
        "start_month",
        "end_month",
        "stock_count",
        "trade_date",
        "window_months",
    }
)
PUBLIC_IDENTIFIER_VALUE_RE = re.compile(
    r"^(?:\d{5}\.HK|\d{6}\.(?:BJ|OF|SH|SZ)|[A-Z0-9]{1,12}\.(?:BJ|HK|OF|SH|SZ))$"
)
# Keep this aligned with daily_refresh.HK_HOLD_DAILY_PUBLICATION_LAST_DATE
# without importing daily_refresh into the plan-only API surface.
HSGT_HOLD_TOP10_BACKFILL_LAST_DATE = date(2024, 8, 20)
DEFAULT_MAX_PLAN_ITEMS = 5_000
DATE_FORMAT = "%Y%m%d"
LIVE_HOLDINGS_BACKFILL_ENV = "DP_TUSHARE_LIVE_HOLDINGS_BACKFILL"
MVP20_BOUNDED_BACKFILL_WINDOW_MONTHS = 120
MVP20_BOUNDED_BACKFILL_STOCK_COUNT = 20
MVP20_BOUNDED_BACKFILL_MAX_PLAN_ITEMS = 20_000
MVP20_BOUNDED_BACKFILL_END_MONTH = date(2024, 8, 31)
MVP20_HSGT_MARKET_TYPES = ("1", "3")
MVP20_HSGT_EXCHANGES = ("SH", "SZ")
MVP20_A_SHARE_STOCK_CODE_RE = re.compile(r"^\d{6}\.(?:BJ|SH|SZ)$")


class HoldingsBackfillPlanError(ValueError):
    """Raised when a rejected backfill plan is passed to execution."""


@dataclass(frozen=True, slots=True)
class HoldingsBackfillPlanItem:
    """One auditable holdings backfill planning decision."""

    dataset: str
    status: PlanItemStatus
    partition_date: date | None = None
    fetch_params: FetchParams = field(default_factory=dict)
    bounds: Mapping[str, Any] = field(default_factory=dict)
    reason_type: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fetch_params", dict(self.fetch_params))
        object.__setattr__(self, "bounds", dict(self.bounds))


@dataclass(frozen=True, slots=True)
class HoldingsBackfillPlan:
    """A bounded holdings backfill plan with planned, skipped, and rejected items."""

    items: tuple[HoldingsBackfillPlanItem, ...]
    max_plan_items: int = DEFAULT_MAX_PLAN_ITEMS

    @property
    def planned_items(self) -> tuple[HoldingsBackfillPlanItem, ...]:
        return tuple(item for item in self.items if item.status == "planned")

    @property
    def skipped_items(self) -> tuple[HoldingsBackfillPlanItem, ...]:
        return tuple(item for item in self.items if item.status == "skipped")

    @property
    def rejected_items(self) -> tuple[HoldingsBackfillPlanItem, ...]:
        return tuple(item for item in self.items if item.status == "rejected")

    @property
    def has_rejections(self) -> bool:
        return bool(self.rejected_items)

    @property
    def ok(self) -> bool:
        return not self.has_rejections


@dataclass(frozen=True, slots=True)
class HoldingsBackfillExecutionItem:
    """Execution result for a planned or skipped holdings backfill item."""

    dataset: str
    status: ExecutionItemStatus
    partition_date: date | None
    row_count: int = 0
    artifact: RawArtifact | None = None
    reason_type: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class HoldingsBackfillExecutionResult:
    """Result of executing a holdings backfill plan into Raw Zone artifacts."""

    items: tuple[HoldingsBackfillExecutionItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.status in {"ok", "skipped"} for item in self.items)

    @property
    def artifacts(self) -> tuple[RawArtifact, ...]:
        return tuple(item.artifact for item in self.items if item.artifact is not None)


@dataclass(frozen=True, slots=True)
class ProviderGap:
    """One explicit gap in a provider-available planning manifest."""

    scope: str
    reason_type: str
    reason: str
    dataset: str | None = None
    bounds: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bounds", dict(self.bounds))


@dataclass(frozen=True, slots=True)
class MVP20BoundedBackfillManifest:
    """Plan-only MVP20 bounded backfill manifest with explicit provider gaps."""

    seed_stock_codes: tuple[str, ...]
    window_month_ends: tuple[date, ...]
    report_periods: tuple[date, ...]
    trade_dates: tuple[date, ...]
    hsgt_hold_trade_dates: tuple[date, ...]
    holdings_plan: HoldingsBackfillPlan
    provider_gaps: tuple[ProviderGap, ...]
    related_fund_codes: tuple[str, ...] = ()
    related_entity_hops: int = 2
    completeness_status: str = "bounded_provider_available_with_recorded_gaps"

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_stock_codes", tuple(self.seed_stock_codes))
        object.__setattr__(self, "window_month_ends", tuple(self.window_month_ends))
        object.__setattr__(self, "report_periods", tuple(self.report_periods))
        object.__setattr__(self, "trade_dates", tuple(self.trade_dates))
        object.__setattr__(self, "hsgt_hold_trade_dates", tuple(self.hsgt_hold_trade_dates))
        object.__setattr__(self, "provider_gaps", tuple(self.provider_gaps))
        object.__setattr__(self, "related_fund_codes", tuple(self.related_fund_codes))

    @property
    def ok(self) -> bool:
        return self.holdings_plan.ok

    @property
    def complete(self) -> bool:
        return False


def build_holdings_backfill_plan(
    *,
    datasets: Sequence[str],
    stock_codes: Sequence[str] = (),
    fund_codes: Sequence[str] = (),
    periods: Sequence[str] = (),
    trade_dates: Sequence[str] = (),
    start_date: str | None = None,
    end_date: str | None = None,
    market_types: Sequence[str] = (),
    exchanges: Sequence[str] = (),
    max_plan_items: int = DEFAULT_MAX_PLAN_ITEMS,
) -> HoldingsBackfillPlan:
    """Build a fail-closed holdings backfill plan from explicit bounded inputs."""

    if max_plan_items < 1:
        msg = "max_plan_items must be positive"
        raise ValueError(msg)

    dataset_list, dataset_rejections = _normalize_datasets(datasets)
    normalized_stock_codes = _normalize_non_empty_strings(stock_codes)
    normalized_fund_codes = _normalize_non_empty_strings(fund_codes)
    normalized_periods, period_rejections = _parse_date_values(periods, "period")
    normalized_trade_dates, trade_date_rejections = _resolve_trade_dates(
        trade_dates=trade_dates,
        start_date=start_date,
        end_date=end_date,
    )
    normalized_market_types = _normalize_non_empty_strings(market_types)
    normalized_exchanges = _normalize_non_empty_strings(exchanges)

    items: list[HoldingsBackfillPlanItem] = [
        *dataset_rejections,
        *period_rejections,
        *trade_date_rejections,
    ]
    for dataset in dataset_list:
        items.extend(
            _plan_dataset(
                dataset=dataset,
                stock_codes=normalized_stock_codes,
                fund_codes=normalized_fund_codes,
                periods=normalized_periods,
                trade_dates=normalized_trade_dates,
                market_types=normalized_market_types,
                exchanges=normalized_exchanges,
            )
        )

    planned_count = sum(1 for item in items if item.status == "planned")
    if planned_count > max_plan_items:
        items.append(
            _rejected_item(
                "holdings",
                "plan_item_limit_exceeded",
                (
                    f"bounded holdings backfill plan has {planned_count} planned items; "
                    f"limit is {max_plan_items}"
                ),
                bounds={"planned_count": planned_count, "max_plan_items": max_plan_items},
            )
        )

    return HoldingsBackfillPlan(tuple(items), max_plan_items=max_plan_items)


def build_mvp20_bounded_backfill_manifest(
    *,
    stock_codes: Sequence[str],
    end_month: str | date | None = None,
    related_fund_codes: Sequence[str] = (),
    max_plan_items: int = MVP20_BOUNDED_BACKFILL_MAX_PLAN_ITEMS,
) -> MVP20BoundedBackfillManifest:
    """Build the fixed MVP20 plan-only manifest without touching live providers."""

    normalized_stock_codes = _normalize_mvp20_stock_codes(stock_codes)
    normalized_fund_codes = _normalize_non_empty_strings(related_fund_codes)
    month_ends = _month_end_window(
        _parse_end_month(end_month),
        months=MVP20_BOUNDED_BACKFILL_WINDOW_MONTHS,
    )
    report_periods = tuple(value for value in month_ends if value.month in {3, 6, 9, 12})
    hsgt_hold_trade_dates, hsgt_hold_gaps = _hsgt_hold_provider_available_dates(month_ends)

    plans = [
        build_holdings_backfill_plan(
            datasets=("top10_holders", "top10_floatholders"),
            stock_codes=normalized_stock_codes,
            periods=tuple(f"{period:%Y%m%d}" for period in report_periods),
            max_plan_items=max_plan_items,
        ),
        build_holdings_backfill_plan(
            datasets=("hsgt_top10",),
            stock_codes=normalized_stock_codes,
            trade_dates=tuple(f"{trade_date:%Y%m%d}" for trade_date in month_ends),
            market_types=MVP20_HSGT_MARKET_TYPES,
            max_plan_items=max_plan_items,
        ),
    ]
    if hsgt_hold_trade_dates:
        plans.append(
            build_holdings_backfill_plan(
                datasets=("hsgt_hold_top10",),
                stock_codes=normalized_stock_codes,
                trade_dates=tuple(f"{trade_date:%Y%m%d}" for trade_date in hsgt_hold_trade_dates),
                exchanges=MVP20_HSGT_EXCHANGES,
                max_plan_items=max_plan_items,
            )
        )

    provider_gaps: list[ProviderGap] = list(hsgt_hold_gaps)
    if normalized_fund_codes:
        plans.append(
            build_holdings_backfill_plan(
                datasets=("fund_portfolio",),
                fund_codes=normalized_fund_codes,
                periods=tuple(f"{period:%Y%m%d}" for period in report_periods),
                max_plan_items=max_plan_items,
            )
        )
    else:
        provider_gaps.append(
            ProviderGap(
                scope="two_hop_related_entities",
                dataset="fund_portfolio",
                reason_type="related_fund_codes_unresolved_plan_only",
                reason=(
                    "fund_portfolio needs fund codes discovered from observed holdings; "
                    "the plan-only MVP20 manifest records the gap instead of fabricating "
                    "two-hop fund coverage"
                ),
                bounds={
                    "stock_count": len(normalized_stock_codes),
                    "related_entity_hops": 2,
                    "window_months": MVP20_BOUNDED_BACKFILL_WINDOW_MONTHS,
                },
            )
        )

    provider_gaps.append(
        ProviderGap(
            scope="two_hop_related_entities",
            reason_type="holder_identity_resolution_deferred",
            reason=(
                "holder and co-held-security expansion must be derived from fetched "
                "provider rows; this manifest does not enumerate unknown holder entities"
            ),
            bounds={
                "stock_count": len(normalized_stock_codes),
                "related_entity_hops": 2,
            },
        )
    )

    return MVP20BoundedBackfillManifest(
        seed_stock_codes=normalized_stock_codes,
        window_month_ends=month_ends,
        report_periods=report_periods,
        trade_dates=month_ends,
        hsgt_hold_trade_dates=hsgt_hold_trade_dates,
        holdings_plan=_combine_holdings_backfill_plans(plans, max_plan_items=max_plan_items),
        provider_gaps=tuple(provider_gaps),
        related_fund_codes=normalized_fund_codes,
    )


def execute_holdings_backfill_plan(
    plan: HoldingsBackfillPlan,
    *,
    adapter: FetchableAdapter,
    raw_writer: RawWriter,
    execute_live: bool = False,
) -> HoldingsBackfillExecutionResult:
    """Execute planned holdings backfill items through an adapter into Raw Zone."""

    validate_holdings_backfill_live_gate(execute_live=execute_live)

    if plan.has_rejections:
        reasons = ", ".join(
            f"{item.dataset}:{item.reason_type}" for item in plan.rejected_items
        )
        msg = f"holdings backfill plan has rejected item(s): {reasons}"
        raise HoldingsBackfillPlanError(msg)

    for item in plan.planned_items:
        _validate_planned_item_for_execution(item)

    assets_by_dataset = _assets_by_dataset(adapter.get_assets())
    execution_items: list[HoldingsBackfillExecutionItem] = []
    for item in plan.items:
        if item.status == "skipped":
            execution_items.append(
                HoldingsBackfillExecutionItem(
                    dataset=item.dataset,
                    status="skipped",
                    partition_date=item.partition_date,
                    reason_type=item.reason_type,
                    reason=item.reason,
                )
            )
            continue
        if item.status != "planned":
            continue
        if item.partition_date is None:
            msg = f"planned holdings backfill item lacks partition_date: {item.dataset}"
            raise HoldingsBackfillPlanError(msg)

        asset = assets_by_dataset[item.dataset]
        result = adapter.fetch(asset.name, item.fetch_params)
        if not isinstance(result, pa.Table):
            msg = f"holdings backfill adapter returned unsupported result for {item.dataset}"
            raise TypeError(msg)

        artifact = raw_writer.write_arrow(
            adapter.source_id(),
            asset.dataset,
            item.partition_date,
            str(uuid.uuid4()),
            result,
            metadata=asset.metadata,
            request_params=item.fetch_params,
        )
        execution_items.append(
            HoldingsBackfillExecutionItem(
                dataset=item.dataset,
                status="ok",
                partition_date=item.partition_date,
                row_count=artifact.row_count,
                artifact=artifact,
            )
        )

    return HoldingsBackfillExecutionResult(tuple(execution_items))


def validate_holdings_backfill_live_gate(*, execute_live: bool) -> None:
    """Fail closed unless both the code path and environment opt in to live writes."""

    if not execute_live:
        msg = "live holdings backfill requires execute_live=True"
        raise HoldingsBackfillPlanError(msg)
    if os.environ.get(LIVE_HOLDINGS_BACKFILL_ENV) != "1":
        msg = f"live holdings backfill requires {LIVE_HOLDINGS_BACKFILL_ENV}=1"
        raise HoldingsBackfillPlanError(msg)


def public_plan_summary(plan: HoldingsBackfillPlan) -> dict[str, Any]:
    """Return a provider-neutral summary of a holdings backfill plan."""

    return {
        "ok": plan.ok,
        "planned_count": len(plan.planned_items),
        "skipped_count": len(plan.skipped_items),
        "rejected_count": len(plan.rejected_items),
        "max_plan_items": plan.max_plan_items,
        "items": [_public_plan_item(item) for item in plan.items],
    }


def public_execution_summary(result: HoldingsBackfillExecutionResult) -> dict[str, Any]:
    """Return a redacted execution summary suitable for PR notes and operator logs."""

    return {
        "ok": result.ok,
        "artifact_count": len(result.artifacts),
        "row_count": sum(item.row_count for item in result.items),
        "items": [
            {
                "dataset": item.dataset,
                "status": item.status,
                "partition_date": (
                    None if item.partition_date is None else f"{item.partition_date:%Y%m%d}"
                ),
                "row_count": item.row_count,
                **_reason_fields(item.reason_type, item.reason),
            }
            for item in result.items
        ],
    }


def public_mvp20_bounded_backfill_summary(
    manifest: MVP20BoundedBackfillManifest,
) -> dict[str, Any]:
    """Return a redacted MVP20 plan manifest summary with provider gaps."""

    return {
        "ok": manifest.ok,
        "complete": manifest.complete,
        "completeness_status": manifest.completeness_status,
        "seed_stock_count": len(manifest.seed_stock_codes),
        "related_entity_hops": manifest.related_entity_hops,
        "window": {
            "window_months": len(manifest.window_month_ends),
            "start_month": f"{manifest.window_month_ends[0]:%Y%m}",
            "end_month": f"{manifest.window_month_ends[-1]:%Y%m}",
            "report_period_count": len(manifest.report_periods),
            "trade_date_count": len(manifest.trade_dates),
            "hsgt_hold_trade_date_count": len(manifest.hsgt_hold_trade_dates),
        },
        "plan": {
            "planned_count": len(manifest.holdings_plan.planned_items),
            "skipped_count": len(manifest.holdings_plan.skipped_items),
            "rejected_count": len(manifest.holdings_plan.rejected_items),
            "max_plan_items": manifest.holdings_plan.max_plan_items,
            "planned_count_by_dataset": _plan_item_counts_by_dataset(
                manifest.holdings_plan.planned_items
            ),
            "skipped_count_by_dataset": _plan_item_counts_by_dataset(
                manifest.holdings_plan.skipped_items
            ),
            "rejected_count_by_dataset": _plan_item_counts_by_dataset(
                manifest.holdings_plan.rejected_items
            ),
        },
        "provider_gap_count": len(manifest.provider_gaps),
        "provider_gaps": [_public_provider_gap(gap) for gap in manifest.provider_gaps],
    }


def _combine_holdings_backfill_plans(
    plans: Sequence[HoldingsBackfillPlan],
    *,
    max_plan_items: int,
) -> HoldingsBackfillPlan:
    items = tuple(item for plan in plans for item in plan.items)
    planned_count = sum(1 for item in items if item.status == "planned")
    if planned_count <= max_plan_items:
        return HoldingsBackfillPlan(items, max_plan_items=max_plan_items)
    return HoldingsBackfillPlan(
        (
            *items,
            _rejected_item(
                "holdings",
                "plan_item_limit_exceeded",
                (
                    f"bounded holdings backfill plan has {planned_count} planned items; "
                    f"limit is {max_plan_items}"
                ),
                bounds={"planned_count": planned_count, "max_plan_items": max_plan_items},
            ),
        ),
        max_plan_items=max_plan_items,
    )


def _plan_item_counts_by_dataset(
    items: Sequence[HoldingsBackfillPlanItem],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.dataset] = counts.get(item.dataset, 0) + 1
    return dict(sorted(counts.items()))


def _public_provider_gap(gap: ProviderGap) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scope": gap.scope,
        "reason_type": gap.reason_type,
        "reason": gap.reason,
    }
    if gap.dataset is not None:
        payload["dataset"] = gap.dataset
    if gap.bounds:
        payload["bounds"] = _json_safe_public_value(gap.bounds)
    return payload


def _plan_dataset(
    *,
    dataset: str,
    stock_codes: tuple[str, ...],
    fund_codes: tuple[str, ...],
    periods: tuple[date, ...],
    trade_dates: tuple[date, ...],
    market_types: tuple[str, ...],
    exchanges: tuple[str, ...],
) -> tuple[HoldingsBackfillPlanItem, ...]:
    if dataset in STOCK_CODE_DATASETS:
        return _plan_stock_code_dataset(dataset, stock_codes, periods)
    if dataset in FUND_CODE_DATASETS:
        return _plan_fund_code_dataset(dataset, fund_codes, periods)
    if dataset == "hsgt_top10":
        return _plan_hsgt_top10_dataset(trade_dates, market_types, stock_codes)
    if dataset == "hsgt_hold_top10":
        return _plan_hsgt_hold_top10_dataset(trade_dates, exchanges, stock_codes)
    return (
        _rejected_item(
            dataset,
            "unsupported_dataset",
            f"holdings backfill does not support dataset {dataset!r}",
        ),
    )


def _plan_stock_code_dataset(
    dataset: str,
    stock_codes: tuple[str, ...],
    periods: tuple[date, ...],
) -> tuple[HoldingsBackfillPlanItem, ...]:
    missing = []
    if not stock_codes:
        missing.append("stock_codes")
    if not periods:
        missing.append("periods")
    if missing:
        return (
            _rejected_item(
                dataset,
                "missing_bounded_inputs",
                f"{dataset} requires explicit stock_codes and periods",
                bounds={"missing": missing},
            ),
        )

    return tuple(
        _planned_item(
            dataset=dataset,
            partition_date=period,
            fetch_params={"ts_code": stock_code, "period": f"{period:%Y%m%d}"},
            bounds={"stock_code": stock_code, "period": f"{period:%Y%m%d}"},
        )
        for stock_code in stock_codes
        for period in periods
    )


def _plan_fund_code_dataset(
    dataset: str,
    fund_codes: tuple[str, ...],
    periods: tuple[date, ...],
) -> tuple[HoldingsBackfillPlanItem, ...]:
    missing = []
    if not fund_codes:
        missing.append("fund_codes")
    if not periods:
        missing.append("periods")
    if missing:
        return (
            _rejected_item(
                dataset,
                "missing_bounded_inputs",
                f"{dataset} requires explicit fund_codes and periods",
                bounds={"missing": missing},
            ),
        )

    return tuple(
        _planned_item(
            dataset=dataset,
            partition_date=period,
            fetch_params={"ts_code": fund_code, "period": f"{period:%Y%m%d}"},
            bounds={"fund_code": fund_code, "period": f"{period:%Y%m%d}"},
        )
        for fund_code in fund_codes
        for period in periods
    )


def _plan_hsgt_top10_dataset(
    trade_dates: tuple[date, ...],
    market_types: tuple[str, ...],
    stock_codes: tuple[str, ...],
) -> tuple[HoldingsBackfillPlanItem, ...]:
    missing = []
    if not trade_dates:
        missing.append("trade_dates")
    if not market_types:
        missing.append("market_types")
    if not stock_codes:
        missing.append("stock_codes")
    if missing:
        return (
            _rejected_item(
                "hsgt_top10",
                "missing_bounded_inputs",
                "hsgt_top10 requires explicit stock_codes, trade_dates/date range, and market_types",
                bounds={"missing": missing},
            ),
        )

    return tuple(
        _planned_item(
            dataset="hsgt_top10",
            partition_date=trade_date,
            fetch_params={
                "trade_date": f"{trade_date:%Y%m%d}",
                "market_type": market_type,
                "ts_code": stock_code,
            },
            bounds={
                "trade_date": f"{trade_date:%Y%m%d}",
                "market_type": market_type,
                "stock_code": stock_code,
            },
        )
        for trade_date in trade_dates
        for market_type in market_types
        for stock_code in stock_codes
    )


def _plan_hsgt_hold_top10_dataset(
    trade_dates: tuple[date, ...],
    exchanges: tuple[str, ...],
    stock_codes: tuple[str, ...],
) -> tuple[HoldingsBackfillPlanItem, ...]:
    missing = []
    if not trade_dates:
        missing.append("trade_dates")
    if not exchanges:
        missing.append("exchanges")
    if not stock_codes:
        missing.append("stock_codes")
    if missing:
        return (
            _rejected_item(
                "hsgt_hold_top10",
                "missing_bounded_inputs",
                (
                    "hsgt_hold_top10 requires explicit stock_codes, historical "
                    "trade_dates/date range, and exchanges"
                ),
                bounds={"missing": missing},
            ),
        )

    items: list[HoldingsBackfillPlanItem] = []
    for trade_date in trade_dates:
        for exchange in exchanges:
            for stock_code in stock_codes:
                bounds = {
                    "trade_date": f"{trade_date:%Y%m%d}",
                    "exchange": exchange,
                    "stock_code": stock_code,
                }
                if trade_date > HSGT_HOLD_TOP10_BACKFILL_LAST_DATE:
                    items.append(
                        _skipped_item(
                            dataset="hsgt_hold_top10",
                            partition_date=trade_date,
                            reason_type="post_publication_cutoff",
                            reason=(
                                "northbound holding daily publication is only verifiable through "
                                f"{HSGT_HOLD_TOP10_BACKFILL_LAST_DATE:%Y-%m-%d}"
                            ),
                            bounds=bounds,
                        )
                    )
                    continue
                items.append(
                    _planned_item(
                        dataset="hsgt_hold_top10",
                        partition_date=trade_date,
                        fetch_params={
                            "trade_date": f"{trade_date:%Y%m%d}",
                            "exchange": exchange,
                            "ts_code": stock_code,
                        },
                        bounds=bounds,
                    )
                )
    return tuple(items)


def _normalize_datasets(
    datasets: Sequence[str],
) -> tuple[tuple[str, ...], tuple[HoldingsBackfillPlanItem, ...]]:
    normalized = _normalize_non_empty_strings(datasets)
    if not normalized:
        return (), (
            _rejected_item(
                "holdings",
                "missing_datasets",
                "holdings backfill requires at least one explicit dataset",
            ),
        )

    supported = set(SUPPORTED_HOLDINGS_BACKFILL_DATASETS)
    accepted: list[str] = []
    rejected: list[HoldingsBackfillPlanItem] = []
    for dataset in normalized:
        if dataset in supported:
            accepted.append(dataset)
        else:
            rejected.append(
                _rejected_item(
                    dataset,
                    "unsupported_dataset",
                    f"holdings backfill does not support dataset {dataset!r}",
                )
            )
    return tuple(accepted), tuple(rejected)


def _resolve_trade_dates(
    *,
    trade_dates: Sequence[str],
    start_date: str | None,
    end_date: str | None,
) -> tuple[tuple[date, ...], tuple[HoldingsBackfillPlanItem, ...]]:
    parsed_trade_dates, rejections = _parse_date_values(trade_dates, "trade_date")
    range_values: list[date] = []

    if start_date is None and end_date is None:
        return parsed_trade_dates, rejections
    if start_date is None or end_date is None:
        return parsed_trade_dates, (
            *rejections,
            _rejected_item(
                "holdings",
                "incomplete_date_range",
                "date range requires both start_date and end_date",
            ),
        )

    parsed_start = _parse_yyyymmdd(start_date)
    parsed_end = _parse_yyyymmdd(end_date)
    if parsed_start is None or parsed_end is None:
        return parsed_trade_dates, (
            *rejections,
            _rejected_item(
                "holdings",
                "invalid_date_range",
                "date range bounds must use valid YYYYMMDD dates",
                bounds={"start_date": start_date, "end_date": end_date},
            ),
        )
    if parsed_start > parsed_end:
        return parsed_trade_dates, (
            *rejections,
            _rejected_item(
                "holdings",
                "invalid_date_range",
                "start_date must be less than or equal to end_date",
                bounds={"start_date": start_date, "end_date": end_date},
            ),
        )

    current = parsed_start
    while current <= parsed_end:
        range_values.append(current)
        current += timedelta(days=1)
    return _dedupe_dates((*parsed_trade_dates, *range_values)), rejections


def _parse_date_values(
    values: Sequence[str],
    field_name: str,
) -> tuple[tuple[date, ...], tuple[HoldingsBackfillPlanItem, ...]]:
    parsed: list[date] = []
    rejected: list[HoldingsBackfillPlanItem] = []
    for value in _normalize_non_empty_strings(values):
        parsed_value = _parse_yyyymmdd(value)
        if parsed_value is None:
            rejected.append(
                _rejected_item(
                    "holdings",
                    f"invalid_{field_name}",
                    f"{field_name} must use a valid YYYYMMDD date",
                    bounds={field_name: value},
                )
            )
            continue
        parsed.append(parsed_value)
    return _dedupe_dates(parsed), tuple(rejected)


def _parse_yyyymmdd(value: str) -> date | None:
    try:
        parsed = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None
    if f"{parsed:%Y%m%d}" != value:
        return None
    return parsed


def _parse_end_month(value: str | date | None) -> date:
    if value is None:
        return MVP20_BOUNDED_BACKFILL_END_MONTH
    if isinstance(value, date):
        return _month_end(value.year, value.month)

    normalized = value.strip()
    if re.fullmatch(r"\d{6}", normalized):
        year = int(normalized[:4])
        month = int(normalized[4:])
        if not 1 <= month <= 12:
            msg = "end_month must use a valid YYYYMM month"
            raise ValueError(msg)
        return _month_end(year, month)

    parsed = _parse_yyyymmdd(normalized)
    if parsed is None:
        msg = "end_month must use YYYYMM or YYYYMMDD"
        raise ValueError(msg)
    return _month_end(parsed.year, parsed.month)


def _month_end_window(end_month: date, *, months: int) -> tuple[date, ...]:
    if months != MVP20_BOUNDED_BACKFILL_WINDOW_MONTHS:
        msg = "MVP20 bounded backfill uses a fixed 120-month window"
        raise ValueError(msg)

    values = []
    end_year = end_month.year
    end_month_number = end_month.month
    for offset in range(months - 1, -1, -1):
        year, month = _shift_month(end_year, end_month_number, -offset)
        values.append(_month_end(year, month))
    return tuple(values)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + month - 1 + offset
    return month_index // 12, month_index % 12 + 1


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _hsgt_hold_provider_available_dates(
    month_ends: Sequence[date],
) -> tuple[tuple[date, ...], tuple[ProviderGap, ...]]:
    available_dates: list[date] = []
    capped_months: list[date] = []
    omitted_months: list[date] = []
    cutoff = HSGT_HOLD_TOP10_BACKFILL_LAST_DATE
    for month_end in month_ends:
        if month_end <= cutoff:
            available_dates.append(month_end)
            continue
        if month_end.year == cutoff.year and month_end.month == cutoff.month:
            available_dates.append(cutoff)
            capped_months.append(month_end)
            continue
        omitted_months.append(month_end)

    gaps: list[ProviderGap] = []
    if capped_months:
        gaps.append(
            ProviderGap(
                scope="provider_available_window",
                dataset="hsgt_hold_top10",
                reason_type="partial_month_provider_cutoff",
                reason=(
                    "hsgt_hold_top10 daily publication is only provider-verifiable "
                    f"through {cutoff:%Y-%m-%d}; the cutoff month is capped to that date"
                ),
                bounds={
                    "capped_month_count": len(capped_months),
                    "end_month": f"{capped_months[-1]:%Y%m}",
                    "provider_available_end_date": f"{cutoff:%Y%m%d}",
                },
            )
        )
    if omitted_months:
        gaps.append(
            ProviderGap(
                scope="provider_available_window",
                dataset="hsgt_hold_top10",
                reason_type="post_publication_cutoff",
                reason=(
                    "hsgt_hold_top10 daily publication is not provider-verifiable after "
                    f"{cutoff:%Y-%m-%d}; post-cutoff months are omitted from the plan"
                ),
                bounds={
                    "omitted_month_count": len(omitted_months),
                    "start_month": f"{omitted_months[0]:%Y%m}",
                    "end_month": f"{omitted_months[-1]:%Y%m}",
                    "provider_available_end_date": f"{cutoff:%Y%m%d}",
                },
            )
        )
    return _dedupe_dates(available_dates), tuple(gaps)


def _normalize_mvp20_stock_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    normalized = _normalize_non_empty_strings(stock_codes)
    if (
        len(normalized) != MVP20_BOUNDED_BACKFILL_STOCK_COUNT
        or len(frozenset(normalized)) != len(normalized)
    ):
        msg = "mvp20 bounded backfill requires exactly 20 unique stock_codes"
        raise ValueError(msg)
    if any(MVP20_A_SHARE_STOCK_CODE_RE.fullmatch(stock_code) is None for stock_code in normalized):
        msg = "mvp20 bounded backfill stock_codes must be A-share ts_codes"
        raise ValueError(msg)
    return normalized


def _normalize_non_empty_strings(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in str(value).split(","):
            candidate = part.strip()
            if candidate and candidate not in seen:
                normalized.append(candidate)
                seen.add(candidate)
    return tuple(normalized)


def _dedupe_dates(values: Sequence[date]) -> tuple[date, ...]:
    deduped: list[date] = []
    seen: set[date] = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return tuple(deduped)


def _planned_item(
    *,
    dataset: str,
    partition_date: date,
    fetch_params: Mapping[str, Any],
    bounds: Mapping[str, Any],
) -> HoldingsBackfillPlanItem:
    return HoldingsBackfillPlanItem(
        dataset=dataset,
        status="planned",
        partition_date=partition_date,
        fetch_params=fetch_params,
        bounds=bounds,
    )


def _skipped_item(
    *,
    dataset: str,
    partition_date: date,
    reason_type: str,
    reason: str,
    bounds: Mapping[str, Any],
) -> HoldingsBackfillPlanItem:
    return HoldingsBackfillPlanItem(
        dataset=dataset,
        status="skipped",
        partition_date=partition_date,
        bounds=bounds,
        reason_type=reason_type,
        reason=reason,
    )


def _rejected_item(
    dataset: str,
    reason_type: str,
    reason: str,
    *,
    bounds: Mapping[str, Any] | None = None,
) -> HoldingsBackfillPlanItem:
    return HoldingsBackfillPlanItem(
        dataset=dataset,
        status="rejected",
        bounds=bounds or {},
        reason_type=reason_type,
        reason=reason,
    )


def _public_plan_item(item: HoldingsBackfillPlanItem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset": item.dataset,
        "status": item.status,
    }
    if item.partition_date is not None:
        payload["partition_date"] = f"{item.partition_date:%Y%m%d}"
    if item.bounds:
        payload["bounds"] = _public_bounds(item.bounds)
    payload.update(_reason_fields(item.reason_type, item.reason))
    return payload


def _public_bounds(bounds: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, value in bounds.items():
        public_key = str(key)
        if public_key in PUBLIC_IDENTIFIER_BOUND_CLASSES:
            identifier_values = _bound_identifier_values(value)
            public[f"{public_key}_class"] = PUBLIC_IDENTIFIER_BOUND_CLASSES[public_key]
            public[f"{public_key}_count"] = len(identifier_values)
            continue
        if public_key not in PUBLIC_SAFE_BOUND_KEYS:
            continue
        if isinstance(value, Mapping):
            public[public_key] = _public_bounds(value)
            continue
        public[public_key] = _json_safe_public_value(value)
    return public


def _bound_identifier_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return tuple(str(item) for item in value if str(item))
    if value is None:
        return ()
    return (str(value),)


def _reason_fields(reason_type: str | None, reason: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if reason_type is not None:
        fields["reason_type"] = reason_type
    if reason is not None:
        fields["reason"] = reason
    return fields


def _json_safe_public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_public_value(item)
            for key, item in value.items()
            if str(key) in PUBLIC_SAFE_BOUND_KEYS
        }
    if isinstance(value, list | tuple):
        return [_json_safe_public_value(item) for item in value]
    if isinstance(value, date):
        return f"{value:%Y%m%d}"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str) and _looks_like_public_identifier(value):
        return "[redacted]"
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _validate_planned_item_for_execution(item: HoldingsBackfillPlanItem) -> None:
    if item.partition_date is None:
        msg = f"planned holdings backfill item lacks partition_date: {item.dataset}"
        raise HoldingsBackfillPlanError(msg)

    if item.dataset in STOCK_CODE_DATASETS | FUND_CODE_DATASETS:
        _require_non_empty_scalar_param(item, "ts_code")
        period = _parse_fetch_date_param(
            item,
            "period",
            partition_label="report period",
        )
        if period != item.partition_date:
            msg = (
                f"planned {item.dataset} backfill item requires a period matching "
                "partition_date before execution"
            )
            raise HoldingsBackfillPlanError(msg)
        return

    if item.dataset in HSGT_BACKFILL_DATASETS:
        _require_non_empty_scalar_param(item, "ts_code")
        trade_date = _parse_fetch_date_param(
            item,
            "trade_date",
            partition_label="trade_date",
        )
        if trade_date != item.partition_date:
            msg = (
                f"planned {item.dataset} backfill item requires a trade_date matching "
                "partition_date before execution"
            )
            raise HoldingsBackfillPlanError(msg)
        if item.dataset == "hsgt_top10":
            _require_non_empty_scalar_param(item, "market_type")
            return
        if item.dataset == "hsgt_hold_top10":
            _require_non_empty_scalar_param(item, "exchange")
            if trade_date > HSGT_HOLD_TOP10_BACKFILL_LAST_DATE:
                msg = (
                    "planned hsgt_hold_top10 backfill item is after the supported "
                    f"{HSGT_HOLD_TOP10_BACKFILL_LAST_DATE:%Y-%m-%d} cutoff"
                )
                raise HoldingsBackfillPlanError(msg)
            return

    msg = f"planned holdings backfill item has unsupported dataset: {item.dataset}"
    raise HoldingsBackfillPlanError(msg)


def _require_non_empty_scalar_param(
    item: HoldingsBackfillPlanItem,
    param_name: str,
) -> str:
    value = item.fetch_params.get(param_name)
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        msg = (
            f"planned {item.dataset} backfill item requires a non-empty scalar "
            f"{param_name} before execution"
        )
        raise HoldingsBackfillPlanError(msg)
    return value


def _parse_fetch_date_param(
    item: HoldingsBackfillPlanItem,
    param_name: str,
    *,
    partition_label: str,
) -> date:
    value = _require_non_empty_scalar_param(item, param_name)
    parsed = _parse_yyyymmdd(value)
    if parsed is None:
        msg = (
            f"planned {item.dataset} backfill item requires a valid {partition_label} "
            "before execution"
        )
        raise HoldingsBackfillPlanError(msg)
    return parsed


def _looks_like_public_identifier(value: str) -> bool:
    return bool(PUBLIC_IDENTIFIER_VALUE_RE.fullmatch(value.strip().upper()))


def _assets_by_dataset(assets: Sequence[AssetSpec]) -> dict[str, AssetSpec]:
    assets_by_dataset = {asset.dataset: asset for asset in assets}
    missing = [
        dataset
        for dataset in SUPPORTED_HOLDINGS_BACKFILL_DATASETS
        if dataset not in assets_by_dataset
    ]
    if missing:
        msg = "adapter is missing holdings assets: " + ", ".join(missing)
        raise ValueError(msg)
    return assets_by_dataset


def default_holdings_assets_by_dataset() -> dict[str, AssetSpec]:
    """Return the built-in holdings assets keyed by public dataset name."""

    return {
        dataset: asset
        for dataset, asset in _assets_by_dataset(TUSHARE_ASSETS).items()
        if dataset in SUPPORTED_HOLDINGS_BACKFILL_DATASETS
    }


__all__ = [
    "DEFAULT_MAX_PLAN_ITEMS",
    "HSGT_HOLD_TOP10_BACKFILL_LAST_DATE",
    "HoldingsBackfillExecutionItem",
    "HoldingsBackfillExecutionResult",
    "HoldingsBackfillPlan",
    "HoldingsBackfillPlanError",
    "HoldingsBackfillPlanItem",
    "LIVE_HOLDINGS_BACKFILL_ENV",
    "MVP20BoundedBackfillManifest",
    "MVP20_BOUNDED_BACKFILL_STOCK_COUNT",
    "MVP20_BOUNDED_BACKFILL_END_MONTH",
    "MVP20_BOUNDED_BACKFILL_MAX_PLAN_ITEMS",
    "MVP20_BOUNDED_BACKFILL_WINDOW_MONTHS",
    "ProviderGap",
    "SUPPORTED_HOLDINGS_BACKFILL_DATASETS",
    "build_holdings_backfill_plan",
    "build_mvp20_bounded_backfill_manifest",
    "default_holdings_assets_by_dataset",
    "execute_holdings_backfill_plan",
    "public_execution_summary",
    "public_mvp20_bounded_backfill_summary",
    "public_plan_summary",
    "validate_holdings_backfill_live_gate",
]
