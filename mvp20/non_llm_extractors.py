"""Deterministic first-pass candidate screening helpers.

This module deliberately sits beside, not inside, the existing scoring path:
``overlay/realtime -> aggregate -> score_company -> llm_context ->
llm_decision`` keeps its current semantics.  The screening layer consumes the
latest score snapshot and writes a runtime candidate-pool artifact that can be
re-sliced by capacity without rebuilding the cross-section.
"""

from __future__ import annotations

import copy
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from mvp20.json_utils import json_safe
from mvp20.llm_storage import atomic_write_json

SCHEMA_VERSION = "candidate_pool.v1"
DEFAULT_CANDIDATE_CAPACITY = 80
MAX_CANDIDATE_CAPACITY = 300
CANDIDATE_POOL_ROOT_NAME = "candidate_pool"
NON_LLM_SOURCE = "non_llm_screen.v1"
A_SHARE_MARKET = "A_share"
A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")

EVENT_REVIEW_GATED_DP_IDS = {
    "L8.gov.insider_sell",
    "L8.gov.management_change",
    "L9.company.buyback_dividend",
    "L9.company.earnings_guidance",
}

RUNTIME_WRITABLE_STATUSES = {
    "Known",
    "Proxy",
    "Inactive",
    "N/A",
    "LowMateriality",
}


def normalize_market(market: str | None) -> str:
    raw = str(market or "A").strip()
    if raw in {"A", "CN", "A_share", "A-share", "a_share"}:
        return A_SHARE_MARKET
    raise ValueError(f"unsupported candidate-pool market: {raw}")


def clamp_capacity(value: Any = None) -> int:
    if value is None or value == "":
        return DEFAULT_CANDIDATE_CAPACITY
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CANDIDATE_CAPACITY
    return max(1, min(MAX_CANDIDATE_CAPACITY, parsed))


def candidate_pool_path(runtime_dir: Path, market: str = A_SHARE_MARKET) -> Path:
    return Path(runtime_dir) / CANDIDATE_POOL_ROOT_NAME / f"{normalize_market(market)}.json"


def load_candidate_pool(runtime_dir: Path, market: str = A_SHARE_MARKET) -> dict[str, Any] | None:
    path = candidate_pool_path(runtime_dir, market)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_candidate_pool(runtime_dir: Path, payload: Mapping[str, Any], market: str = A_SHARE_MARKET) -> Path:
    return atomic_write_json(candidate_pool_path(runtime_dir, market), dict(payload))


def slice_candidate_pool(payload: Mapping[str, Any], capacity: Any = None) -> dict[str, Any]:
    cap = clamp_capacity(capacity if capacity is not None else payload.get("default_capacity"))
    ranked_rows = list(payload.get("ranked_rows") or [])
    response = {
        "schema_version": payload.get("schema_version") or SCHEMA_VERSION,
        "generated_at": payload.get("generated_at"),
        "market": payload.get("market") or A_SHARE_MARKET,
        "policy": payload.get("policy") or {},
        "default_capacity": int(payload.get("default_capacity") or DEFAULT_CANDIDATE_CAPACITY),
        "capacity": cap,
        "source_snapshot": payload.get("source_snapshot") or {},
        "summary": payload.get("summary") or {},
        "rows": ranked_rows[:cap],
        "total_ranked": len(ranked_rows),
        "returned": min(cap, len(ranked_rows)),
    }
    return json_safe(response)


def candidate_gate_summary(
    runtime_dir: Path,
    ts_code: str,
    market: str = A_SHARE_MARKET,
) -> dict[str, Any]:
    payload = load_candidate_pool(runtime_dir, market)
    if not payload:
        return {
            "available": False,
            "reason": "no candidate pool artifact",
            "market": normalize_market(market),
            "ts_code": ts_code,
        }
    for row in payload.get("ranked_rows") or []:
        if row.get("ts_code") == ts_code:
            return {
                "available": True,
                "market": payload.get("market") or normalize_market(market),
                "ts_code": ts_code,
                "rank": row.get("rank"),
                "score": row.get("score"),
                "gate_status": row.get("gate_status"),
                "llm_next_step": row.get("llm_next_step"),
                "generated_at": payload.get("generated_at"),
                "default_capacity": payload.get("default_capacity"),
                "total_ranked": len(payload.get("ranked_rows") or []),
            }
    return {
        "available": False,
        "reason": "ts_code not in candidate pool",
        "market": payload.get("market") or normalize_market(market),
        "ts_code": ts_code,
        "generated_at": payload.get("generated_at"),
        "total_ranked": len(payload.get("ranked_rows") or []),
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _load_universe(repo_root: Path) -> list[dict[str, Any]]:
    path = Path(repo_root) / "config" / "mvp20.universe.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        dict(c)
        for c in data.get("constituents", [])
        if str(c.get("ts_code") or "").endswith(A_SHARE_SUFFIXES)
    ]


def _profile_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {str(p["ts_code"]): p for p in _load_universe(repo_root) if p.get("ts_code")}


def _score_participating_dp_ids(repo_root: Path) -> set[str]:
    path = Path(repo_root) / "config" / "data_point_roles.yaml"
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    roles = data.get("data_points") or data.get("roles") or data
    out: set[str] = set()
    if isinstance(roles, Mapping):
        for dp_id, info in roles.items():
            if isinstance(info, Mapping) and info.get("participates_in_score") is True:
                out.add(str(dp_id))
    return out


def _schema_errors(dp_id: str, value: Any) -> list[str]:
    try:
        from mvp20.schema_validator import validate_value
        return validate_value(dp_id, value)
    except Exception as exc:  # noqa: BLE001 - extractor quality is advisory
        return [f"schema validator failed: {exc}"]


def _confidence_for(candidate: Mapping[str, Any]) -> float | None:
    conf = _finite_number(candidate.get("confidence"))
    if conf is not None:
        return max(0.0, min(1.0, conf))
    status = candidate.get("data_status")
    if status == "Known":
        return 0.82
    if status == "Proxy":
        return 0.65
    return 0.5


def _review_gated_candidate(dp_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dp_id": dp_id,
        "data_status": "ReviewGated",
        "value": None,
        "confidence": _confidence_for(raw),
        "evidence_sources": list(raw.get("evidence_sources") or []),
        "method": "script_fill.event_review_packet",
        "quality": {
            "review_required": True,
            "reason": "event-review-gated field is not written as Known",
            "schema_errors": _schema_errors(dp_id, raw.get("value")),
        },
        "review_packet": {
            "proposed_data_status": raw.get("data_status") or "Known",
            "proposed_value": raw.get("value"),
            "direction": raw.get("direction"),
            "evidence_sources": list(raw.get("evidence_sources") or []),
        },
    }


def extract_for_stock(
    ts_code: str,
    db_path: Path,
    overlay: Mapping[str, Any] | None = None,
    *,
    include_catalysts: bool = True,
    include_management_change: bool = False,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic extraction candidates for one stock.

    ``overlay`` is accepted for the stable pure-function interface; the first
    implementation delegates to the existing deterministic script-fill module
    and normalizes its output into the candidate schema used by screening.
    """

    _ = overlay
    try:
        from scripts import script_fill
        raw = script_fill.extract(
            ts_code,
            Path(db_path),
            include_catalysts=include_catalysts,
            include_management_change=include_management_change,
        )
    except Exception as exc:  # noqa: BLE001
        return [{
            "dp_id": "__extractor__",
            "data_status": "ExtractorFailed",
            "value": None,
            "confidence": 0.0,
            "evidence_sources": [],
            "method": "script_fill.extract",
            "quality": {"error": str(exc), "review_required": True},
        }]

    score_dps = _score_participating_dp_ids(Path(repo_root or Path(__file__).resolve().parent.parent))
    out: list[dict[str, Any]] = []
    for dp_id, node in sorted((raw or {}).items()):
        if not isinstance(node, Mapping):
            continue
        if dp_id in EVENT_REVIEW_GATED_DP_IDS:
            out.append(_review_gated_candidate(dp_id, node))
            continue
        value = node.get("value")
        errors = _schema_errors(dp_id, value)
        out.append({
            "dp_id": dp_id,
            "data_status": node.get("data_status") or "Known",
            "value": value,
            "confidence": _confidence_for(node),
            "evidence_sources": list(node.get("evidence_sources") or []),
            "method": "script_fill.extract",
            "quality": {
                "schema_errors": errors,
                "schema_valid": not errors,
                "participates_in_score": dp_id in score_dps,
                "review_required": False,
            },
        })
    return json_safe(out)


def extraction_summary(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    usable = [
        c for c in candidates
        if c.get("dp_id") != "__extractor__"
    ]
    writable = [
        c for c in usable
        if c.get("data_status") in RUNTIME_WRITABLE_STATUSES
        and not (c.get("quality") or {}).get("schema_errors")
    ]
    review = [c for c in usable if c.get("data_status") == "ReviewGated"]
    score_participating = [
        c for c in usable
        if (c.get("quality") or {}).get("participates_in_score")
    ]
    invalid = [
        c for c in usable
        if (c.get("quality") or {}).get("schema_errors")
    ]
    return {
        "candidate_count": len(usable),
        "available_count": len([c for c in usable if c.get("data_status") != "ExtractorFailed"]),
        "score_participating_count": len(score_participating),
        "review_gated_count": len(review),
        "schema_invalid_count": len(invalid),
        "runtime_writable_count": len(writable),
        "methods": sorted({str(c.get("method")) for c in usable if c.get("method")}),
    }


def upsert_non_llm_candidates(
    db_path: Path,
    ts_code: str,
    candidates: list[Mapping[str, Any]],
    *,
    updated_at: int | None = None,
) -> int:
    from mvp20.storage import upsert_realtime

    ts = int(updated_at or time.time())
    rows = []
    for c in candidates:
        dp_id = str(c.get("dp_id") or "")
        if not dp_id or dp_id == "__extractor__":
            continue
        if c.get("data_status") not in RUNTIME_WRITABLE_STATUSES:
            continue
        quality = c.get("quality") if isinstance(c.get("quality"), Mapping) else {}
        if quality.get("schema_errors"):
            continue
        rows.append((
            ts_code,
            dp_id,
            c.get("value"),
            str(c.get("data_status")),
            _confidence_for(c),
            NON_LLM_SOURCE,
            ts,
        ))
    return upsert_realtime(Path(db_path), rows)


def _base_score_percentiles(snapshot: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    scored = [
        (str(ts), score)
        for ts, row in snapshot.items()
        for score in [_finite_number(row.get("base_score") if isinstance(row, Mapping) else None)]
        if score is not None
    ]
    # Deterministic order independent of snapshot iteration order, plus a
    # tie-aware percentile: equal base_scores map to the SAME percentile (the
    # fraction of strictly-smaller scores). Previously ties got distinct
    # enumerate-index percentiles, so the Top-N gate winner among tied stocks
    # depended on the order rows came back from the score store.
    scored.sort(key=lambda item: (item[1], item[0]))
    n = len(scored)
    if not scored:
        return {}
    first_index: dict[float, int] = {}
    for idx, (_ts, score) in enumerate(scored):
        first_index.setdefault(score, idx)
    return {
        ts: round(100.0 * first_index[score] / max(n - 1, 1), 1)
        for ts, score in scored
    }


def _quant_block(qrow: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not qrow or not qrow.get("validated"):
        return None
    return {
        "mag_score_pct": ((qrow.get("mag") or {}) if isinstance(qrow.get("mag"), Mapping) else {}).get("score_pct"),
        "exp_excess": ((qrow.get("mag") or {}) if isinstance(qrow.get("mag"), Mapping) else {}).get("exp_excess"),
        "p_beat_median": ((qrow.get("prob") or {}) if isinstance(qrow.get("prob"), Mapping) else {}).get("p_beat_median"),
        "tilt_pp": ((qrow.get("prob") or {}) if isinstance(qrow.get("prob"), Mapping) else {}).get("tilt_pp"),
        "theme": qrow.get("theme"),
    }


def build_candidate_pool(
    *,
    repo_root: Path,
    db_path: Path,
    market: str = "A",
    capacity: Any = DEFAULT_CANDIDATE_CAPACITY,
    write_runtime: bool = False,
    output_path: Path | None = None,
    now_ts: int | None = None,
) -> dict[str, Any]:
    market_norm = normalize_market(market)
    cap = clamp_capacity(capacity)
    now = int(now_ts or time.time())
    generated_at = datetime.fromtimestamp(now, tz=timezone.utc).replace(microsecond=0).isoformat()

    try:
        from mvp20 import pnl_loop
        base_date, snapshot = pnl_loop.latest_snapshot()
    except Exception:  # noqa: BLE001
        base_date, snapshot = None, {}
    try:
        from mvp20 import quant_score
        quant_artifact = quant_score.load_artifact(market_norm)
    except Exception:  # noqa: BLE001
        quant_artifact = None
    qrows = (quant_artifact or {}).get("rows") or {}

    profiles = _profile_index(Path(repo_root))
    base_pct = _base_score_percentiles(snapshot)
    excluded_reasons: dict[str, int] = {}
    rows: list[dict[str, Any]] = []

    for ts_code, profile in profiles.items():
        score_row = snapshot.get(ts_code) or {}
        pct = base_pct.get(ts_code)
        base_score = _finite_number(score_row.get("base_score") if isinstance(score_row, Mapping) else None)
        if pct is None or base_score is None:
            reason = "missing_base_score"
            if ts_code not in snapshot:
                reason = "missing_score_snapshot"
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue

        qrow = qrows.get(ts_code) if isinstance(qrows, Mapping) else None
        rows.append({
            "ts_code": ts_code,
            "name": profile.get("name"),
            "industry_ids": list(profile.get("industry_ids") or []),
            "role": profile.get("role"),
            "score": {
                "base_score": base_score,
                "base_score_pct": pct,
                "trading_signal": score_row.get("trading_signal"),
                "trading_signal_v2": score_row.get("signal_v2"),
                "merit": score_row.get("merit"),
                "timing": score_row.get("timing"),
            },
            "quant": _quant_block(qrow if isinstance(qrow, Mapping) else None),
            "quant_validated": bool(isinstance(qrow, Mapping) and qrow.get("validated")),
        })

    def _sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, str]:
        score = row.get("score") if isinstance(row.get("score"), Mapping) else {}
        quant = row.get("quant") if isinstance(row.get("quant"), Mapping) else {}
        # ``is not None`` rather than ``or`` so a legitimate 0.0 (e.g. a real
        # base_score of 0.0, or the lowest percentile) is not collapsed into the
        # -1.0 missing-value sentinel and mis-ordered against negatives.
        pct = score.get("base_score_pct")
        base = score.get("base_score")
        mag = quant.get("mag_score_pct")
        return (
            -float(pct if pct is not None else -1.0),
            -float(base if base is not None else -1.0),
            -float(mag if mag is not None else -1.0),
            str(row.get("ts_code")),
        )

    rows.sort(key=_sort_key)

    runtime_rows_written = 0
    for idx, row in enumerate(rows, start=1):
        passed = idx <= cap
        candidates: list[dict[str, Any]]
        row_runtime_writes = 0
        if passed:
            candidates = extract_for_stock(
                str(row["ts_code"]),
                Path(db_path),
                include_catalysts=True,
                include_management_change=False,
                repo_root=Path(repo_root),
            )
            if write_runtime:
                row_runtime_writes = upsert_non_llm_candidates(
                    Path(db_path),
                    str(row["ts_code"]),
                    candidates,
                    updated_at=now,
                )
                runtime_rows_written += row_runtime_writes
        else:
            candidates = []
        summary = extraction_summary(candidates)
        summary["runtime_write_count"] = row_runtime_writes
        if not passed:
            summary["status"] = "not_run_below_capacity"
        row["rank"] = idx
        row["gate_status"] = {
            "passed": passed,
            "policy": "topn_cross_sectional_base_score_pct",
            "capacity": cap,
            "reason_codes": ["topn_capacity"] if passed else ["below_capacity_cutoff"],
        }
        row["non_llm_fill_summary"] = summary
        row["llm_next_step"] = "llm_extraction_ready" if passed else "screening_only"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "market": market_norm,
        "policy": {
            "gate": "topn_cross_sectional_base_score_pct",
            "default_capacity": DEFAULT_CANDIDATE_CAPACITY,
            "capacity": cap,
            "max_capacity": MAX_CANDIDATE_CAPACITY,
            "score_field": "base_score_pct",
            "event_review_gated_dp_ids": sorted(EVENT_REVIEW_GATED_DP_IDS),
            "runtime_source": NON_LLM_SOURCE,
        },
        "default_capacity": DEFAULT_CANDIDATE_CAPACITY,
        "source_snapshot": {
            "score_snapshot_date": base_date,
            "quant_asof": (quant_artifact or {}).get("asof"),
            "score_source": "runtime/backtest/pnl.sqlite",
            "quant_source": "runtime/quant_score/A_share.json",
            "universe_source": "config/mvp20.universe.yaml",
        },
        "summary": {
            "total_ranked": len(rows),
            "passed_count": min(cap, len(rows)),
            "write_runtime": bool(write_runtime),
            "runtime_rows_written": runtime_rows_written,
            "excluded_reasons": excluded_reasons,
        },
        "ranked_rows": rows,
    }

    path = Path(output_path) if output_path else candidate_pool_path(Path(repo_root) / "runtime", market_norm)
    atomic_write_json(path, json_safe(payload))
    payload = copy.deepcopy(payload)
    payload["artifact_path"] = str(path)
    return json_safe(payload)
