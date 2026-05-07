"""Dry-run planning helpers for MVP20 data coverage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mvp20.manifest import load_manifest, validate_manifest


@dataclass(frozen=True)
class BackfillPlan:
    universe_id: str
    history_window_months: int
    decision_target_count: int
    graph_depth: int
    live_evidence_blocked: bool
    planned_datasets: tuple[str, ...]
    provider_gap_policy: str


def build_backfill_plan(manifest_path: Path) -> BackfillPlan:
    validation = validate_manifest(manifest_path)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    manifest = load_manifest(manifest_path)
    return BackfillPlan(
        universe_id=validation.universe_id,
        history_window_months=int(manifest["history_window_months"]),
        decision_target_count=validation.decision_target_count,
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
    )
