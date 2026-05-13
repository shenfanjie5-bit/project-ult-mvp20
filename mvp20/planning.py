"""Dry-run planning helpers for MVP data coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mvp20.manifest import load_manifest, validate_manifest
from mvp20.providers import validate_provider_catalog


@dataclass(frozen=True)
class BackfillPlan:
    universe_id: str
    history_window_months: int
    industry_count: int
    constituent_count: int
    graph_depth: int
    live_evidence_blocked: bool
    planned_datasets: tuple[str, ...]
    provider_gap_policy: str
    data_sources: tuple[str, ...] = field(default_factory=tuple)
    market_coverage: dict[str, tuple[str, ...]] = field(default_factory=dict)


def build_backfill_plan(
    manifest_path: Path,
    *,
    providers_path: Path | None = None,
) -> BackfillPlan:
    """Plan a backfill run for the leader pool.

    If ``providers_path`` is supplied (and the catalog validates), the
    plan reports the active provider list and per-market coverage so
    operators can see e.g. that ``US`` is served by ``fmp + yfinance``.
    Otherwise these fields are left empty — the upstream caller can
    still proceed with provider routing logic.
    """

    validation = validate_manifest(manifest_path)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    manifest = load_manifest(manifest_path)

    data_sources: tuple[str, ...] = ()
    market_coverage: dict[str, tuple[str, ...]] = {}
    if providers_path is None:
        default_providers = manifest_path.parent / "data_providers.yaml"
        if default_providers.exists():
            providers_path = default_providers
    if providers_path is not None and providers_path.exists():
        # Derive required markets from constituents.
        required_markets: set[str] = set()
        for c in manifest.get("constituents") or []:
            ts = str(c.get("ts_code", ""))
            if ts.endswith(".HK"):
                required_markets.add("HK")
            elif ts.endswith(".US"):
                required_markets.add("US")
            elif ts.endswith((".SH", ".SZ", ".BJ")):
                required_markets.add("A")
        provider_validation = validate_provider_catalog(
            providers_path, required_markets=required_markets
        )
        if provider_validation.ok:
            data_sources = provider_validation.active_providers
            market_coverage = {
                m: tuple(provs)
                for m, provs in provider_validation.market_coverage.items()
                if provs
            }
        else:
            raise ValueError(
                "data provider catalog failed validation: "
                + "; ".join(provider_validation.errors)
            )

    return BackfillPlan(
        universe_id=validation.universe_id,
        history_window_months=int(manifest["history_window_months"]),
        industry_count=validation.industry_count,
        constituent_count=validation.constituent_count,
        graph_depth=int(manifest["graph_depth"]),
        live_evidence_blocked=validation.live_evidence_blocked,
        planned_datasets=(
            "market_daily",
            "event_timeline",
            "holding_position",
            "top_holder_qoq",
            "fund_co_holding",
            "northbound_holding",
            "graph_two_hop_context",
        ),
        provider_gap_policy="provider_available_data_with_explicit_gap_evidence",
        data_sources=data_sources,
        market_coverage=market_coverage,
    )
