"""Scoring glue for the PIT backtest — reuses the production engine unchanged.

Replicates the ~20 lines of orchestration in ``mvp20/cli.py::score_company_command``
(read overlay → aggregate_company_graph → score_company) by IMPORTING the public
functions; ``mvp20/cli.py`` is not modified.

Industry-L0 is FROZEN two ways (per the approved plan): (1) ``industry_overlay``
is passed as ``None`` so inherited L0 demand/supply/price values stay empty, and
(2) any ``L0.*`` node is stripped from the in-memory overlay before aggregation
so authored L0 values cannot contribute either. The LLM qualitative layer is
already ≈0 via ``_to_scalar`` and is left as static overlay context (excluded
from any PIT data).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from mvp20.aggregator import aggregate_company_graph
from mvp20.peer_context import default_artifact_path, load_peer_context
from mvp20.scoring import score_company
from mvp20.storage import read_hot_snapshot

_DEFAULT_OVERLAYS = Path("config/stock_overlays")


def locate_overlay(ts_code: str, overlays_dir: Path = _DEFAULT_OVERLAYS,
                   industry_id: str | None = None) -> Path | None:
    """Same resolution order as cli.score_company_command."""

    if industry_id:
        c = overlays_dir / industry_id / f"{ts_code}.yaml"
        if c.exists():
            return c
    if overlays_dir.exists():
        for sub in overlays_dir.iterdir():
            if sub.is_dir():
                c = sub / f"{ts_code}.yaml"
                if c.exists():
                    return c
    c = overlays_dir / f"{ts_code}.yaml"
    return c if c.exists() else None


# Layers frozen/excluded per the approved plan:
#   L0   — industry景气 (current-period YoY embedded → look-ahead leak)
#   L1-L3 — per-stock LLM qualitative (moat / competitive position / business
#           structure; "current info", and the model's latent memory knows the
#           future). These authored nodes target fundamental_score and SUM into
#           industry_contrib, so dropping them removes both the leak and the
#           qualitative inflation. L5 hard-financial realtime still flows via the
#           realtime dead-sink → realtime_fundamental.
#   L8/L9 event nodes (Track B, 2026-06) — script-fillable L8.gov.insider_sell /
#           management_change + L9.company.buyback_dividend / earnings_guidance are
#           filled with AS-OF-TODAY data (latest 分红/指引/减持/高管离任) → point-in-time,
#           NOT reconstructable as-of a past base date → would LEAK future info. Freeze
#           these SPECIFIC nodes only (NOT the whole L8./L9. layer — L8.fin.* etc are
#           PIT-safe quant). Pre-Track-B L8/L9 event nodes are Inactive=0 → no leak.
_FROZEN_LAYER_PREFIXES = ("L0.", "L1.", "L2.", "L3.")
_FROZEN_EVENT_DPIDS = frozenset({
    "L8.gov.insider_sell", "L8.gov.management_change",
    "L9.company.buyback_dividend", "L9.company.earnings_guidance",
})


def _freeze_qualitative_layers(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Drop authored L0–L3 nodes (industry景气 + per-stock qualitative) from the
    overlay nodes list. Returns a shallow-copied overlay."""

    out = dict(overlay)
    nodes = out.get("nodes") or []
    kept = []
    for n in nodes:
        dp = str(n.get("dp_id") or "")
        nid = str(n.get("node_id") or "")
        layer_hit = dp.startswith(_FROZEN_LAYER_PREFIXES) or any(
            f":{p}" in nid for p in _FROZEN_LAYER_PREFIXES
        )
        event_hit = dp in _FROZEN_EVENT_DPIDS or any(
            nid.endswith(f":{d}") for d in _FROZEN_EVENT_DPIDS
        )
        if layer_hit or event_hit:
            continue
        kept.append(n)
    out["nodes"] = kept
    return out


def score_one(ts_code: str, db_path: Path, *, overlays_dir: Path = _DEFAULT_OVERLAYS,
              industry_id: str | None = None, freeze_l0: bool = True) -> dict[str, Any] | None:
    """Score one stock against the PIT DB. Returns the score_company result, or
    None if no overlay exists. Industry-L0 frozen by default."""

    overlay_path = locate_overlay(ts_code, overlays_dir, industry_id)
    if overlay_path is None:
        return None
    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    if freeze_l0:
        overlay = _freeze_qualitative_layers(overlay)

    realtime = read_hot_snapshot(Path(db_path), ts_code)
    peer = load_peer_context(default_artifact_path(Path(db_path), "A"))

    # industry_overlay=None — freeze inherited L0 (belt-and-suspenders with the
    # node strip above).
    aggregated = aggregate_company_graph(
        overlay, None, realtime_snapshot=realtime or None, peer_context=peer
    ) or {}

    coverage: dict[str, Any] = {}
    try:
        from mvp20.coverage import coverage_summary_for_overlay  # type: ignore

        coverage = coverage_summary_for_overlay(overlay) or {}
    except Exception:  # noqa: BLE001
        coverage = overlay.get("coverage") or {}

    result = score_company(
        stock_overlay=overlay,
        aggregated_nodes=aggregated,
        coverage_report=coverage,
        realtime_data=realtime,
    )
    return result


def extract_row(result: Mapping[str, Any], ts_code: str, base_date: str) -> dict[str, Any]:
    """Flatten a score_company result into a persistence row."""

    def g(d, *path, default=None):
        cur = d
        for p in path:
            if not isinstance(cur, Mapping) or p not in cur:
                return default
            cur = cur[p]
        return cur

    return {
        "ts_code": ts_code,
        "base_date": base_date,
        "base_score": g(result, "final_score", "base_score"),
        "core_base_score": g(result, "core_final_score", "base_score"),
        "short_total": result.get("short_total"),
        "medium_total": result.get("medium_total"),
        "long_total": result.get("long_total"),
        "trading_signal": result.get("trading_signal"),
        "mode": result.get("mode"),
        "industry_contrib": g(result, "company_score", "components", "industry_contrib"),
    }
