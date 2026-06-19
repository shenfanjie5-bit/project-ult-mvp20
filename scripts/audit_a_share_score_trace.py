#!/usr/bin/env python3
"""A-share spec field score-closure audit.

This is stricter than ``check_a_share_spec_completion.py``: it does not stop at
"the field exists in SQLite/overlay". It follows the production scoring gates:

runtime/hot.sqlite + sentinel merge
-> field governance
-> realtime value validity
-> _realtime_signal numeric conversion
-> synthesize_realtime_nodes / authored overlay candidate
-> aggregate_company_graph
-> score_company final_score role components
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_SAFE_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

from mvp20.aggregator import (  # noqa: E402
    _REALTIME_DEDUP_PRIMARY,
    _realtime_blocking_dp_ids,
    _realtime_signal,
    aggregate_company_graph,
    synthesize_realtime_nodes,
)
from mvp20.coverage import coverage_summary_for_overlay  # noqa: E402
from mvp20.field_governance import (  # noqa: E402
    DataPointGovernance,
    FieldGovernanceRegistry,
    load_default_governance,
)
from mvp20.peer_context import default_artifact_path, load_peer_context  # noqa: E402
from mvp20.scoring import _role_participates, score_company  # noqa: E402
from mvp20.storage import read_hot_snapshot  # noqa: E402


A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")
VALID_RUNTIME_STATUSES = {"Known", "Proxy"}
SCORE_CAPABLE_OVERLAY_STATUSES = {"Known", "Proxy", "Optionality", "LowMateriality"}
NON_FINAL_TARGETS = {
    "none",
    "audit_only",
    "display_only",
    "parent_score",
    "node_score",
}
DIRECT_FINAL_TARGETS = {
    "fundamental_score",
    "expectation_gap",
    "valuation_rerating",
    "capital_sentiment",
    "funding_score",
    "sentiment_score",
    "risk_discount",
    "uncertainty_discount",
    "volatility_risk",
    "overheat_risk",
    "valuation_pressure",
    "priced_in_discount",
    "option_priced_in",
    "time_decay",
}


def is_a_share(ts_code: str | None) -> bool:
    return bool(ts_code and str(ts_code).upper().endswith(A_SHARE_SUFFIXES))


def is_mock_source(source: str | None) -> bool:
    return str(source or "").lower().startswith("mock:")


def source_category(source: str | None) -> str:
    text = str(source or "").strip().lower()
    if not text:
        return "unknown"
    if text.startswith("mock:"):
        return "mock"
    if "tushare" in text:
        return "tushare"
    if "akshare" in text:
        return "akshare"
    if "fmp" in text:
        return "fmp"
    if "llm" in text:
        return "llm"
    if "web" in text or "crawl" in text or "scrape" in text:
        return "web"
    if "derive" in text or "derived" in text:
        return "derived"
    if "overlay" in text:
        return "overlay"
    return "other"


def has_usable_value(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if isinstance(value, (dict, list, tuple, set)) and not value:
        return False
    return True


def json_safe(value: Any) -> Any:
    """Return a strict-JSON-serializable copy of an audit payload."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, set):
        return [json_safe(v) for v in sorted(value, key=str)]
    return value


def normalize_status(node_or_status: Mapping[str, Any] | str | None) -> str:
    if isinstance(node_or_status, Mapping):
        raw = node_or_status.get("data_status") or node_or_status.get("status")
    else:
        raw = node_or_status
    text = str(raw or "").strip().lower()
    if text in {"known"}:
        return "Known"
    if text in {"proxy"}:
        return "Proxy"
    if text in {"optionality"}:
        return "Optionality"
    if text in {"low materiality", "low_materiality", "lowmateriality"}:
        return "LowMateriality"
    if text in {"inactive"}:
        return "Inactive"
    if text in {"n/a", "na", "not_applicable", "not applicable"}:
        return "N/A"
    if text in {"unavailable"}:
        return "Unavailable"
    return "Unknown"


def reaches_final_score_target(rule: DataPointGovernance | None) -> bool:
    if rule is None or not rule.participates_in_score:
        return False
    return rule.score_target not in NON_FINAL_TARGETS


def row_reaches_final_score_target(row: Mapping[str, Any]) -> bool:
    return bool(row.get("participates_in_score")) and row.get("score_target") not in NON_FINAL_TARGETS


def reaches_direct_base_score(rule: DataPointGovernance | None) -> bool:
    return bool(rule and rule.participates_in_score and rule.score_target in DIRECT_FINAL_TARGETS)


def _fetch_rows(db_path: Path, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, tuple(params)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def build_overlay_index(overlays_dir: Path) -> dict[str, Path]:
    if not overlays_dir.exists():
        return {}
    out: dict[str, Path] = {}
    for path in overlays_dir.glob("**/*.yaml"):
        ts_code = path.stem
        if ts_code not in out and is_a_share(ts_code):
            out[ts_code] = path
    return out


def load_a_share_universe(
    db_path: Path,
    overlays_dir: Path,
    *,
    overlay_index: Mapping[str, Path] | None = None,
) -> list[str]:
    rows = _fetch_rows(
        db_path,
        """
        SELECT DISTINCT ts_code
        FROM (
            SELECT ts_code FROM realtime_current
            UNION
            SELECT ts_code FROM overlay_manifest
            UNION
            SELECT ts_code FROM company_node_instance
            UNION
            SELECT ts_code FROM company_graph_snapshot
        )
        WHERE ts_code LIKE '%.SH'
           OR ts_code LIKE '%.SZ'
           OR ts_code LIKE '%.BJ'
        ORDER BY ts_code
        """,
    )
    out = {str(r["ts_code"]) for r in rows if is_a_share(str(r["ts_code"]))}
    if overlay_index is None:
        overlay_index = build_overlay_index(overlays_dir)
    out.update(ts_code for ts_code in overlay_index if is_a_share(ts_code))
    return sorted(out)


def locate_stock_overlay(
    ts_code: str,
    overlays_dir: Path,
    *,
    industry_id: str | None = None,
    overlay_index: Mapping[str, Path] | None = None,
) -> Path | None:
    if overlay_index is not None:
        path = overlay_index.get(ts_code)
        if path is not None:
            return path
    if industry_id:
        candidate = overlays_dir / industry_id / f"{ts_code}.yaml"
        if candidate.exists():
            return candidate
    if overlays_dir.exists():
        for sub in overlays_dir.iterdir():
            if sub.is_dir():
                candidate = sub / f"{ts_code}.yaml"
                if candidate.exists():
                    return candidate
    candidate = overlays_dir / f"{ts_code}.yaml"
    return candidate if candidate.exists() else None


def load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_SAFE_YAML_LOADER)
    return payload if isinstance(payload, dict) else {}


def load_industry_overlay(stock_overlay: Mapping[str, Any], industry_dir: Path) -> dict[str, Any] | None:
    industry_id = stock_overlay.get("industry_id")
    if not industry_id:
        industry_ids = stock_overlay.get("industry_ids")
        if isinstance(industry_ids, list) and industry_ids:
            industry_id = industry_ids[0]
    if not industry_id:
        return None
    path = industry_dir / f"{industry_id}.yaml"
    return load_yaml(path) if path.exists() else None


def overlay_dp_statuses(overlay: Mapping[str, Any]) -> dict[str, Counter[str]]:
    by_dp: dict[str, Counter[str]] = defaultdict(Counter)
    for node in overlay.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        dp_id = node.get("dp_id")
        if dp_id:
            by_dp[str(dp_id)][normalize_status(node)] += 1
    return by_dp


def overlay_score_candidate_dp_ids(
    overlay: Mapping[str, Any],
    registry: FieldGovernanceRegistry,
) -> set[str]:
    out: set[str] = set()
    for raw in overlay.get("nodes") or []:
        if not isinstance(raw, Mapping):
            continue
        dp_id = str(raw.get("dp_id") or "")
        rule = registry.get(dp_id)
        if not reaches_final_score_target(rule):
            continue
        node = registry.apply_to_node(raw)
        if normalize_status(node) not in SCORE_CAPABLE_OVERLAY_STATUSES:
            continue
        if not has_usable_value(node.get("value")):
            continue
        out.add(dp_id)
    return out


def existing_overlay_dp_ids(
    db_path: Path,
    ts_code: str,
    overlay: Mapping[str, Any],
    registry: FieldGovernanceRegistry,
) -> set[str]:
    nodes_by_id: dict[str, dict] = {}
    for idx, raw in enumerate(overlay.get("nodes") or []):
        if not isinstance(raw, Mapping):
            continue
        node = registry.apply_to_node(raw)
        node_id = str(node.get("node_id") or f"node-{idx}")
        nodes_by_id[node_id] = node
    if nodes_by_id:
        return _realtime_blocking_dp_ids(nodes_by_id)
    rows = _fetch_rows(
        db_path,
        """
        SELECT DISTINCT dp_id
        FROM company_node_instance
        WHERE ts_code = ? AND dp_id IS NOT NULL
        """,
        (ts_code,),
    )
    return {str(r["dp_id"]) for r in rows}


def _make_acc(rule: DataPointGovernance) -> dict[str, Any]:
    return {
        "dp_id": rule.dp_id,
        "field_role": rule.field_role,
        "score_target": rule.score_target,
        "derived_target": rule.derived_target,
        "source_status": rule.source_status,
        "participates_in_score": rule.participates_in_score,
        "runtime_snapshot_ts_codes": set(),
        "runtime_valid_real_ts_codes": set(),
        "runtime_valid_real_direct_ts_codes": set(),
        "runtime_valid_real_sentinel_ts_codes": set(),
        "runtime_numeric_signal_ts_codes": set(),
        "runtime_numeric_signal_direct_ts_codes": set(),
        "runtime_numeric_signal_sentinel_ts_codes": set(),
        "runtime_nonzero_signal_ts_codes": set(),
        "runtime_bridge_emitted_ts_codes": set(),
        "runtime_valid_but_not_numeric_ts_codes": set(),
        "runtime_numeric_blocked_by_overlay_ts_codes": set(),
        "runtime_blocked_by_overlay_without_score_ts_codes": set(),
        "runtime_numeric_blocked_by_dedup_ts_codes": set(),
        "runtime_numeric_not_emitted_other_ts_codes": set(),
        "runtime_mock_ts_codes": set(),
        "overlay_present_ts_codes": set(),
        "overlay_score_candidate_ts_codes": set(),
        "statuses": Counter(),
        "runtime_source_categories": Counter(),
        "runtime_sources": Counter(),
        "origins": Counter(),
        "overlay_statuses": Counter(),
        "sample_values": [],
        "sample_signals": [],
    }


def trace_runtime_entries(
    *,
    ts_code: str,
    snapshot: Mapping[str, Mapping[str, Any]],
    emitted_dp_ids: set[str],
    existing_dp_ids: set[str],
    overlay_score_dp_ids: set[str],
    registry: FieldGovernanceRegistry,
    peer_context: Mapping[str, Any] | None,
    acc_by_dp: dict[str, dict[str, Any]],
) -> None:
    for dp_id, entry in snapshot.items():
        if dp_id not in acc_by_dp or not isinstance(entry, Mapping):
            continue
        acc = acc_by_dp[dp_id]
        rule = registry.get(dp_id)
        status = normalize_status(entry.get("data_status"))
        source = str(entry.get("source") or "")
        origin = str(entry.get("_origin_ts_code") or ts_code)
        acc["runtime_snapshot_ts_codes"].add(ts_code)
        acc["statuses"][status] += 1
        acc["runtime_sources"][source] += 1
        acc["runtime_source_categories"][source_category(source)] += 1
        acc["origins"][origin] += 1
        if len(acc["sample_values"]) < 3:
            acc["sample_values"].append({
                "ts_code": ts_code,
                "origin": origin,
                "status": status,
                "source": source,
                "value": entry.get("value"),
            })

        if is_mock_source(source):
            acc["runtime_mock_ts_codes"].add(ts_code)

        valid_real = (
            status in VALID_RUNTIME_STATUSES
            and not is_mock_source(source)
            and has_usable_value(entry.get("value"))
        )
        if not valid_real:
            continue

        acc["runtime_valid_real_ts_codes"].add(ts_code)
        if origin == ts_code:
            acc["runtime_valid_real_direct_ts_codes"].add(ts_code)
        else:
            acc["runtime_valid_real_sentinel_ts_codes"].add(ts_code)
        signal = _realtime_signal(
            dp_id,
            entry.get("value"),
            rule.score_target if rule else None,
            ts_code=ts_code,
            peer_context=peer_context,
        )
        if signal is None:
            acc["runtime_valid_but_not_numeric_ts_codes"].add(ts_code)
            continue

        acc["runtime_numeric_signal_ts_codes"].add(ts_code)
        if origin == ts_code:
            acc["runtime_numeric_signal_direct_ts_codes"].add(ts_code)
        else:
            acc["runtime_numeric_signal_sentinel_ts_codes"].add(ts_code)
        if abs(float(signal)) > 1e-12:
            acc["runtime_nonzero_signal_ts_codes"].add(ts_code)
        if len(acc["sample_signals"]) < 5:
            acc["sample_signals"].append({
                "ts_code": ts_code,
                "origin": origin,
                "signal": round(float(signal), 6),
            })

        if dp_id in emitted_dp_ids:
            acc["runtime_bridge_emitted_ts_codes"].add(ts_code)
            continue
        if dp_id in existing_dp_ids:
            acc["runtime_numeric_blocked_by_overlay_ts_codes"].add(ts_code)
            if dp_id not in overlay_score_dp_ids:
                acc["runtime_blocked_by_overlay_without_score_ts_codes"].add(ts_code)
            continue
        primary_dp = _REALTIME_DEDUP_PRIMARY.get(dp_id)
        if primary_dp and primary_dp in emitted_dp_ids:
            acc["runtime_numeric_blocked_by_dedup_ts_codes"].add(ts_code)
            continue
        acc["runtime_numeric_not_emitted_other_ts_codes"].add(ts_code)


def trace_overlay_entries(
    *,
    ts_code: str,
    overlay: Mapping[str, Any],
    overlay_score_dp_ids: set[str],
    acc_by_dp: dict[str, dict[str, Any]],
) -> None:
    for dp_id, statuses in overlay_dp_statuses(overlay).items():
        if dp_id not in acc_by_dp:
            continue
        acc = acc_by_dp[dp_id]
        acc["overlay_present_ts_codes"].add(ts_code)
        for status, count in statuses.items():
            acc["overlay_statuses"][status] += count
        if dp_id in overlay_score_dp_ids:
            acc["overlay_score_candidate_ts_codes"].add(ts_code)


def serialize_counter(counter: Counter[str], limit: int = 12) -> dict[str, int]:
    return dict(counter.most_common(limit))


def set_count(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    return len(value) if isinstance(value, set) else 0


def field_rows(acc_by_dp: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for dp_id, acc in sorted(acc_by_dp.items()):
        effective_score_ts = set(acc["runtime_bridge_emitted_ts_codes"]) | set(
            acc["overlay_score_candidate_ts_codes"]
        )
        row = {
            "dp_id": dp_id,
            "field_role": acc["field_role"],
            "score_target": acc["score_target"],
            "derived_target": acc["derived_target"],
            "source_status": acc["source_status"],
            "participates_in_score": acc["participates_in_score"],
            "runtime_snapshot_ts_count": set_count(acc, "runtime_snapshot_ts_codes"),
            "runtime_valid_real_ts_count": set_count(acc, "runtime_valid_real_ts_codes"),
            "runtime_valid_real_direct_ts_count": set_count(
                acc, "runtime_valid_real_direct_ts_codes"
            ),
            "runtime_valid_real_sentinel_ts_count": set_count(
                acc, "runtime_valid_real_sentinel_ts_codes"
            ),
            "runtime_numeric_signal_ts_count": set_count(acc, "runtime_numeric_signal_ts_codes"),
            "runtime_numeric_signal_direct_ts_count": set_count(
                acc, "runtime_numeric_signal_direct_ts_codes"
            ),
            "runtime_numeric_signal_sentinel_ts_count": set_count(
                acc, "runtime_numeric_signal_sentinel_ts_codes"
            ),
            "runtime_nonzero_signal_ts_count": set_count(acc, "runtime_nonzero_signal_ts_codes"),
            "runtime_bridge_emitted_ts_count": set_count(acc, "runtime_bridge_emitted_ts_codes"),
            "runtime_valid_but_not_numeric_ts_count": set_count(
                acc, "runtime_valid_but_not_numeric_ts_codes"
            ),
            "runtime_numeric_blocked_by_overlay_ts_count": set_count(
                acc, "runtime_numeric_blocked_by_overlay_ts_codes"
            ),
            "runtime_blocked_by_overlay_without_score_ts_count": set_count(
                acc, "runtime_blocked_by_overlay_without_score_ts_codes"
            ),
            "runtime_numeric_blocked_by_dedup_ts_count": set_count(
                acc, "runtime_numeric_blocked_by_dedup_ts_codes"
            ),
            "runtime_numeric_not_emitted_other_ts_count": set_count(
                acc, "runtime_numeric_not_emitted_other_ts_codes"
            ),
            "runtime_mock_ts_count": set_count(acc, "runtime_mock_ts_codes"),
            "overlay_present_ts_count": set_count(acc, "overlay_present_ts_codes"),
            "overlay_score_candidate_ts_count": set_count(
                acc, "overlay_score_candidate_ts_codes"
            ),
            "effective_score_path_ts_count": len(effective_score_ts),
            "statuses": serialize_counter(acc["statuses"]),
            "overlay_statuses": serialize_counter(acc["overlay_statuses"]),
            "runtime_source_categories": serialize_counter(acc["runtime_source_categories"]),
            "runtime_sources": serialize_counter(acc["runtime_sources"]),
            "origins": serialize_counter(acc["origins"]),
            "sample_values": acc["sample_values"],
            "sample_signals": acc["sample_signals"],
        }
        reaches_final_score = row_reaches_final_score_target(row)
        if not reaches_final_score and row["runtime_valid_but_not_numeric_ts_count"] > 0:
            row["status"] = "non_scoring_valid_runtime_no_numeric"
        elif not acc["participates_in_score"]:
            row["status"] = "non_scoring_spec"
        elif not reaches_final_score:
            row["status"] = "non_final_score_target"
        elif row["effective_score_path_ts_count"] > 0:
            row["status"] = "score_path_candidate"
        elif row["runtime_valid_real_ts_count"] > 0 and row["runtime_numeric_signal_ts_count"] == 0:
            row["status"] = "score_relevant_valid_real_but_no_numeric_formula"
        elif row["runtime_blocked_by_overlay_without_score_ts_count"] > 0:
            row["status"] = "numeric_runtime_blocked_by_non_scoring_overlay"
        elif row["runtime_numeric_signal_ts_count"] > 0:
            row["status"] = "numeric_runtime_not_emitted"
        elif row["runtime_mock_ts_count"] > 0 and row["runtime_valid_real_ts_count"] == 0:
            row["status"] = "mock_only_or_no_real_valid_data"
        else:
            row["status"] = "no_valid_a_share_data"
        out.append(row)
    return out


def _dp_id_sets(rows: list[Mapping[str, Any]]) -> dict[str, set[str]]:
    return {
        "participating": {r["dp_id"] for r in rows if r["participates_in_score"]},
        "score_relevant": {
            r["dp_id"]
            for r in rows
            if row_reaches_final_score_target(r)
        },
        "runtime_valid_real": {r["dp_id"] for r in rows if r["runtime_valid_real_ts_count"] > 0},
        "runtime_valid_real_direct": {
            r["dp_id"] for r in rows if r["runtime_valid_real_direct_ts_count"] > 0
        },
        "runtime_valid_real_sentinel": {
            r["dp_id"] for r in rows if r["runtime_valid_real_sentinel_ts_count"] > 0
        },
        "runtime_numeric_signal": {
            r["dp_id"] for r in rows if r["runtime_numeric_signal_ts_count"] > 0
        },
        "runtime_numeric_signal_direct": {
            r["dp_id"] for r in rows if r["runtime_numeric_signal_direct_ts_count"] > 0
        },
        "runtime_numeric_signal_sentinel": {
            r["dp_id"] for r in rows if r["runtime_numeric_signal_sentinel_ts_count"] > 0
        },
        "runtime_nonzero_signal": {
            r["dp_id"] for r in rows if r["runtime_nonzero_signal_ts_count"] > 0
        },
        "runtime_bridge_emitted": {
            r["dp_id"] for r in rows if r["runtime_bridge_emitted_ts_count"] > 0
        },
        "overlay_score_candidate": {
            r["dp_id"] for r in rows if r["overlay_score_candidate_ts_count"] > 0
        },
        "effective_score_path": {
            r["dp_id"] for r in rows if r["effective_score_path_ts_count"] > 0
        },
        "valid_but_not_numeric": {
            r["dp_id"]
            for r in rows
            if r["runtime_valid_real_ts_count"] > 0
            and r["runtime_numeric_signal_ts_count"] == 0
        },
        "score_relevant_valid_but_not_numeric": {
            r["dp_id"]
            for r in rows
            if row_reaches_final_score_target(r)
            and r["runtime_valid_real_ts_count"] > 0
            and r["runtime_numeric_signal_ts_count"] == 0
        },
        "non_scoring_valid_but_not_numeric": {
            r["dp_id"]
            for r in rows
            if not row_reaches_final_score_target(r)
            and r["runtime_valid_real_ts_count"] > 0
            and r["runtime_numeric_signal_ts_count"] == 0
        },
        "blocked_by_overlay_without_score": {
            r["dp_id"]
            for r in rows
            if r["runtime_blocked_by_overlay_without_score_ts_count"] > 0
        },
        "mock_only": {
            r["dp_id"]
            for r in rows
            if r["runtime_mock_ts_count"] > 0 and r["runtime_valid_real_ts_count"] == 0
        },
    }


def summarize(rows: list[Mapping[str, Any]], registry: FieldGovernanceRegistry) -> dict[str, Any]:
    sets = _dp_id_sets(rows)
    direct_base = {
        dp_id for dp_id in sets["effective_score_path"]
        if reaches_direct_base_score(registry.get(dp_id))
    }
    score_result = {
        dp_id for dp_id in sets["effective_score_path"]
        if reaches_final_score_target(registry.get(dp_id))
    }
    gaps = sets["participating"] - score_result
    return {
        "spec_total": len(registry.rules),
        "participating_spec_dp_ids": len(sets["participating"]),
        "score_relevant_spec_dp_ids": len(sets["score_relevant"]),
        "runtime_valid_real_dp_ids": len(sets["runtime_valid_real"]),
        "runtime_valid_real_direct_dp_ids": len(sets["runtime_valid_real_direct"]),
        "runtime_valid_real_sentinel_dp_ids": len(sets["runtime_valid_real_sentinel"]),
        "runtime_numeric_signal_dp_ids": len(sets["runtime_numeric_signal"]),
        "runtime_numeric_signal_direct_dp_ids": len(sets["runtime_numeric_signal_direct"]),
        "runtime_numeric_signal_sentinel_dp_ids": len(sets["runtime_numeric_signal_sentinel"]),
        "runtime_nonzero_signal_dp_ids": len(sets["runtime_nonzero_signal"]),
        "runtime_bridge_emitted_dp_ids": len(sets["runtime_bridge_emitted"]),
        "overlay_score_candidate_dp_ids": len(sets["overlay_score_candidate"]),
        "effective_score_path_dp_ids": len(score_result),
        "direct_base_score_candidate_dp_ids": len(direct_base),
        "participating_gap_dp_ids": len(gaps),
        "all_valid_real_but_no_numeric_formula_dp_ids": len(sets["valid_but_not_numeric"]),
        "valid_real_but_no_numeric_formula_dp_ids": len(sets["valid_but_not_numeric"]),
        "score_relevant_valid_real_but_no_numeric_formula_dp_ids": len(
            sets["score_relevant_valid_but_not_numeric"]
        ),
        "non_scoring_valid_runtime_no_numeric_dp_ids": len(
            sets["non_scoring_valid_but_not_numeric"]
        ),
        "numeric_runtime_blocked_by_non_scoring_overlay_dp_ids": len(
            sets["blocked_by_overlay_without_score"]
        ),
        "mock_only_dp_ids": len(sets["mock_only"]),
        "dp_id_lists": {
            "runtime_valid_real": sorted(sets["runtime_valid_real"]),
            "runtime_valid_real_direct": sorted(sets["runtime_valid_real_direct"]),
            "runtime_valid_real_sentinel": sorted(sets["runtime_valid_real_sentinel"]),
            "score_relevant": sorted(sets["score_relevant"]),
            "runtime_numeric_signal": sorted(sets["runtime_numeric_signal"]),
            "runtime_numeric_signal_direct": sorted(sets["runtime_numeric_signal_direct"]),
            "runtime_numeric_signal_sentinel": sorted(sets["runtime_numeric_signal_sentinel"]),
            "runtime_bridge_emitted": sorted(sets["runtime_bridge_emitted"]),
            "overlay_score_candidate": sorted(sets["overlay_score_candidate"]),
            "effective_score_path": sorted(score_result),
            "direct_base_score_candidate": sorted(direct_base),
            "participating_gap": sorted(gaps),
            "all_valid_real_but_no_numeric_formula": sorted(sets["valid_but_not_numeric"]),
            "valid_real_but_no_numeric_formula": sorted(sets["valid_but_not_numeric"]),
            "score_relevant_valid_real_but_no_numeric_formula": sorted(
                sets["score_relevant_valid_but_not_numeric"]
            ),
            "non_scoring_valid_runtime_no_numeric": sorted(
                sets["non_scoring_valid_but_not_numeric"]
            ),
            "numeric_runtime_blocked_by_non_scoring_overlay": sorted(
                sets["blocked_by_overlay_without_score"]
            ),
            "mock_only": sorted(sets["mock_only"]),
        },
    }


def layer_of(dp_id: str) -> str:
    return dp_id.split(".", 1)[0] if "." in dp_id else dp_id


def summarize_by_layer(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        layer = layer_of(str(row["dp_id"]))
        bucket = out.setdefault(
            layer,
            {
                "total": 0,
                "participating": 0,
                "runtime_valid_real": 0,
                "runtime_numeric_signal": 0,
                "runtime_bridge_emitted": 0,
                "overlay_score_candidate": 0,
                "effective_score_path": 0,
                "gap": 0,
            },
        )
        bucket["total"] += 1
        if row["participates_in_score"]:
            bucket["participating"] += 1
        if row["runtime_valid_real_ts_count"] > 0:
            bucket["runtime_valid_real"] += 1
        if row["runtime_numeric_signal_ts_count"] > 0:
            bucket["runtime_numeric_signal"] += 1
        if row["runtime_bridge_emitted_ts_count"] > 0:
            bucket["runtime_bridge_emitted"] += 1
        if row["overlay_score_candidate_ts_count"] > 0:
            bucket["overlay_score_candidate"] += 1
        if row["effective_score_path_ts_count"] > 0:
            bucket["effective_score_path"] += 1
        if row["participates_in_score"] and row["effective_score_path_ts_count"] == 0:
            bucket["gap"] += 1
    return dict(sorted(out.items()))


def sample_score_trace(
    *,
    ts_code: str,
    db_path: Path,
    overlays_dir: Path,
    industry_dir: Path,
    registry: FieldGovernanceRegistry,
    peer_context: Mapping[str, Any] | None,
    overlay_index: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    overlay_path = locate_stock_overlay(
        ts_code,
        overlays_dir,
        overlay_index=overlay_index,
    )
    if overlay_path is None:
        return {"ts_code": ts_code, "ok": False, "error": "stock_overlay_not_found"}
    stock_overlay = load_yaml(overlay_path)
    industry_overlay = load_industry_overlay(stock_overlay, industry_dir)
    snapshot = read_hot_snapshot(db_path, ts_code)
    aggregated = aggregate_company_graph(
        stock_overlay,
        industry_overlay,
        role_registry=registry,
        realtime_snapshot=snapshot or None,
        peer_context=peer_context,
    )
    coverage = coverage_summary_for_overlay(stock_overlay)
    result = score_company(
        stock_overlay=stock_overlay,
        aggregated_nodes=aggregated,
        coverage_report=coverage,
        realtime_data=snapshot,
    )
    scored_nodes = []
    dp_targets: dict[str, Counter[str]] = defaultdict(Counter)
    for node_id, node in aggregated.items():
        if not isinstance(node, Mapping):
            continue
        dp_id = node.get("dp_id")
        if not dp_id:
            continue
        if not _role_participates(node):
            continue
        target = str(node.get("score_target") or "none")
        if target in NON_FINAL_TARGETS:
            continue
        score = float(node.get("score") or 0.0)
        confidence = float(node.get("confidence") or 0.0)
        dp_targets[str(dp_id)][target] += 1
        scored_nodes.append({
            "node_id": node_id,
            "dp_id": str(dp_id),
            "score_target": target,
            "score": round(score, 6),
            "confidence": round(confidence, 6),
            "weighted_score": round(score * confidence, 6),
            "synthetic_realtime": bool(node.get("synthetic_realtime")),
        })
    scored_nodes.sort(key=lambda x: abs(float(x["weighted_score"])), reverse=True)
    synthetic_nodes = [n for n in scored_nodes if n["synthetic_realtime"]]
    return {
        "ts_code": ts_code,
        "ok": True,
        "overlay_path": str(overlay_path),
        "industry_id": stock_overlay.get("industry_id"),
        "runtime_snapshot_dp_ids": len(snapshot),
        "aggregated_nodes": len(aggregated),
        "scored_dp_ids": len(dp_targets),
        "synthetic_realtime_scored_nodes": len(synthetic_nodes),
        "role_components": result.get("role_components") or {},
        "core_final_score": result.get("core_final_score") or {},
        "final_score": result.get("final_score") or {},
        "market_adjusted_final_score": result.get("market_adjusted_final_score") or {},
        "trading_signal": result.get("trading_signal"),
        "signal_evidence": result.get("signal_evidence") or {},
        "scored_targets_by_dp": {
            dp: dict(counter) for dp, counter in sorted(dp_targets.items())
        },
        "top_scored_nodes": scored_nodes[:40],
        "top_synthetic_realtime_nodes": synthetic_nodes[:40],
    }


def build_score_trace_report(
    *,
    db_path: Path,
    overlays_dir: Path,
    industry_dir: Path,
    registry: FieldGovernanceRegistry,
    sample_ts_codes: Sequence[str],
    peer_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    overlay_index = build_overlay_index(overlays_dir)
    ts_codes = load_a_share_universe(
        db_path,
        overlays_dir,
        overlay_index=overlay_index,
    )
    acc_by_dp = {dp_id: _make_acc(rule) for dp_id, rule in registry.rules.items()}
    for ts_code in ts_codes:
        overlay_path = locate_stock_overlay(
            ts_code,
            overlays_dir,
            overlay_index=overlay_index,
        )
        overlay = load_yaml(overlay_path)
        existing_dp_ids = existing_overlay_dp_ids(db_path, ts_code, overlay, registry)
        overlay_score_dp_ids = overlay_score_candidate_dp_ids(overlay, registry)
        trace_overlay_entries(
            ts_code=ts_code,
            overlay=overlay,
            overlay_score_dp_ids=overlay_score_dp_ids,
            acc_by_dp=acc_by_dp,
        )
        snapshot = read_hot_snapshot(db_path, ts_code)
        emitted = synthesize_realtime_nodes(
            snapshot,
            registry,
            existing_dp_ids=existing_dp_ids,
            ts_code=ts_code,
            peer_context=peer_context,
        )
        emitted_dp_ids = {str(n.get("dp_id")) for n in emitted if n.get("dp_id")}
        trace_runtime_entries(
            ts_code=ts_code,
            snapshot=snapshot,
            emitted_dp_ids=emitted_dp_ids,
            existing_dp_ids=existing_dp_ids,
            overlay_score_dp_ids=overlay_score_dp_ids,
            registry=registry,
            peer_context=peer_context,
            acc_by_dp=acc_by_dp,
        )

    rows = field_rows(acc_by_dp)
    samples = [
        sample_score_trace(
            ts_code=ts_code,
            db_path=db_path,
            overlays_dir=overlays_dir,
            industry_dir=industry_dir,
            registry=registry,
            peer_context=peer_context,
            overlay_index=overlay_index,
        )
        for ts_code in sample_ts_codes
    ]
    summary = summarize(rows, registry)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "market": "A-share",
        "db_path": str(db_path),
        "overlays_dir": str(overlays_dir),
        "industry_dir": str(industry_dir),
        "peer_context_loaded": bool(peer_context),
        "a_share_ts_codes": len(ts_codes),
        "summary": summary,
        "by_layer": summarize_by_layer(rows),
        "field_rows": rows,
        "sample_score_traces": samples,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share spec score trace audit",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| Spec dp_ids | {summary['spec_total']} |",
        f"| Participating spec dp_ids | {summary['participating_spec_dp_ids']} |",
        f"| Score-relevant spec dp_ids | {summary['score_relevant_spec_dp_ids']} |",
        f"| A-share universe ts_codes | {report['a_share_ts_codes']} |",
        f"| Runtime valid real dp_ids | {summary['runtime_valid_real_dp_ids']} |",
        f"| Runtime valid real direct-stock dp_ids | {summary['runtime_valid_real_direct_dp_ids']} |",
        f"| Runtime valid real sentinel-origin dp_ids | {summary['runtime_valid_real_sentinel_dp_ids']} |",
        f"| Runtime numeric-signal dp_ids | {summary['runtime_numeric_signal_dp_ids']} |",
        f"| Runtime numeric-signal direct-stock dp_ids | {summary['runtime_numeric_signal_direct_dp_ids']} |",
        f"| Runtime numeric-signal sentinel-origin dp_ids | {summary['runtime_numeric_signal_sentinel_dp_ids']} |",
        f"| Runtime bridge-emitted dp_ids | {summary['runtime_bridge_emitted_dp_ids']} |",
        f"| Overlay score-candidate dp_ids | {summary['overlay_score_candidate_dp_ids']} |",
        f"| Effective score-path dp_ids | {summary['effective_score_path_dp_ids']} |",
        f"| Direct base-score candidate dp_ids | {summary['direct_base_score_candidate_dp_ids']} |",
        f"| Participating gaps | {summary['participating_gap_dp_ids']} |",
        f"| All valid runtime but no numeric formula | {summary['all_valid_real_but_no_numeric_formula_dp_ids']} |",
        f"| Score-relevant valid runtime but no numeric formula | {summary['score_relevant_valid_real_but_no_numeric_formula_dp_ids']} |",
        f"| Non-scoring valid runtime without numeric formula | {summary['non_scoring_valid_runtime_no_numeric_dp_ids']} |",
        f"| Numeric runtime blocked by non-scoring overlay | {summary['numeric_runtime_blocked_by_non_scoring_overlay_dp_ids']} |",
        f"| Mock-only dp_ids | {summary['mock_only_dp_ids']} |",
        "",
        "Definitions: runtime valid real = consumer-visible coverage after `read_hot_snapshot` sentinel merge: "
        "`Known/Proxy`, non-`mock:` source, non-empty value. Direct-stock counts have `_origin_ts_code == ts_code`; "
        "sentinel-origin counts come from merged `MARKET:` / `INDUSTRY:` rows. "
        "Runtime numeric-signal means `_realtime_signal(...)` returned a value. "
        "Runtime bridge-emitted means `synthesize_realtime_nodes(...)` actually created a scoring node. "
        "Effective score-path means either a bridge-emitted runtime node or a score-capable authored overlay node. "
        "Score-relevant excludes `none`, `audit_only`, `display_only`, `parent_score`, and `node_score` targets; "
        "the all-valid/no-numeric count is intentionally broader for data-quality triage.",
        "",
        "## By Layer",
        "",
        "| layer | total | participating | runtime valid | numeric | bridge | overlay | effective | gap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for layer, row in report["by_layer"].items():
        lines.append(
            f"| {layer} | {row['total']} | {row['participating']} | "
            f"{row['runtime_valid_real']} | {row['runtime_numeric_signal']} | "
            f"{row['runtime_bridge_emitted']} | {row['overlay_score_candidate']} | "
            f"{row['effective_score_path']} | {row['gap']} |"
        )

    def append_list(title: str, key: str, limit: int = 80) -> None:
        values = summary["dp_id_lists"].get(key) or []
        lines.extend(["", f"## {title}", ""])
        if not values:
            lines.append("- None")
            return
        shown = values[:limit]
        lines.append(", ".join(f"`{v}`" for v in shown))
        if len(values) > limit:
            lines.append(f"+{len(values) - limit} more")

    append_list("Participating Gaps", "participating_gap")
    append_list("All Valid Runtime But No Numeric Formula", "all_valid_real_but_no_numeric_formula")
    append_list(
        "Score-Relevant Valid Runtime But No Numeric Formula",
        "score_relevant_valid_real_but_no_numeric_formula",
    )
    append_list(
        "Non-scoring Valid Runtime Without Numeric Formula",
        "non_scoring_valid_runtime_no_numeric",
    )
    append_list(
        "Numeric Runtime Blocked By Non-scoring Overlay",
        "numeric_runtime_blocked_by_non_scoring_overlay",
    )
    append_list("Mock-only Runtime Fields", "mock_only")

    lines.extend(["", "## Sample Score Traces", ""])
    for sample in report.get("sample_score_traces") or []:
        if not sample.get("ok"):
            lines.append(f"- `{sample.get('ts_code')}`: {sample.get('error')}")
            continue
        final = sample.get("final_score") or {}
        role = sample.get("role_components") or {}
        lines.extend(
            [
                f"### `{sample['ts_code']}`",
                "",
                f"- overlay: `{sample['overlay_path']}`",
                f"- runtime snapshot dp_ids: {sample['runtime_snapshot_dp_ids']}",
                f"- aggregated nodes: {sample['aggregated_nodes']}",
                f"- scored dp_ids: {sample['scored_dp_ids']}",
                f"- synthetic realtime scored nodes: {sample['synthetic_realtime_scored_nodes']}",
                f"- final base_score: {final.get('base_score')}",
                f"- trading_signal: {sample.get('trading_signal')}",
                f"- role_components: `{json.dumps(json_safe(role), ensure_ascii=False, sort_keys=True, allow_nan=False)}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "runtime/hot.sqlite")
    parser.add_argument("--overlays-dir", type=Path, default=ROOT / "config/stock_overlays")
    parser.add_argument("--industry-dir", type=Path, default=ROOT / "config/industry_overlays")
    parser.add_argument(
        "--sample-ts-code",
        action="append",
        default=[],
        help="A-share ts_code to run full aggregate->score trace for. Repeatable.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "docs/audit/a_share_score_trace_2026-06-18.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "docs/audit/a_share_score_trace_2026-06-18.md",
    )
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    registry = load_default_governance(strict=False)
    if registry is None:
        raise SystemExit("config/data_point_roles.yaml not found")
    samples = args.sample_ts_code or ["300750.SZ"]
    peer_context = load_peer_context(default_artifact_path(args.db, "A"))
    raw_report = build_score_trace_report(
        db_path=args.db,
        overlays_dir=args.overlays_dir,
        industry_dir=args.industry_dir,
        registry=registry,
        sample_ts_codes=samples,
        peer_context=peer_context,
    )
    report = json_safe(raw_report)
    md = render_markdown(report)
    if not args.no_write:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "spec_total": report["summary"]["spec_total"],
                "a_share_ts_codes": report["a_share_ts_codes"],
                "runtime_valid_real_dp_ids": report["summary"]["runtime_valid_real_dp_ids"],
                "runtime_valid_real_direct_dp_ids": report["summary"][
                    "runtime_valid_real_direct_dp_ids"
                ],
                "runtime_valid_real_sentinel_dp_ids": report["summary"][
                    "runtime_valid_real_sentinel_dp_ids"
                ],
                "runtime_numeric_signal_dp_ids": report["summary"]["runtime_numeric_signal_dp_ids"],
                "runtime_numeric_signal_direct_dp_ids": report["summary"][
                    "runtime_numeric_signal_direct_dp_ids"
                ],
                "runtime_numeric_signal_sentinel_dp_ids": report["summary"][
                    "runtime_numeric_signal_sentinel_dp_ids"
                ],
                "runtime_bridge_emitted_dp_ids": report["summary"]["runtime_bridge_emitted_dp_ids"],
                "overlay_score_candidate_dp_ids": report["summary"]["overlay_score_candidate_dp_ids"],
                "effective_score_path_dp_ids": report["summary"]["effective_score_path_dp_ids"],
                "participating_gap_dp_ids": report["summary"]["participating_gap_dp_ids"],
                "all_valid_real_but_no_numeric_formula_dp_ids": report["summary"][
                    "all_valid_real_but_no_numeric_formula_dp_ids"
                ],
                "score_relevant_valid_real_but_no_numeric_formula_dp_ids": report["summary"][
                    "score_relevant_valid_real_but_no_numeric_formula_dp_ids"
                ],
                "non_scoring_valid_runtime_no_numeric_dp_ids": report["summary"][
                    "non_scoring_valid_runtime_no_numeric_dp_ids"
                ],
                "numeric_runtime_blocked_by_non_scoring_overlay_dp_ids": report["summary"][
                    "numeric_runtime_blocked_by_non_scoring_overlay_dp_ids"
                ],
                "output_json": str(args.output_json),
                "output_md": str(args.output_md),
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
