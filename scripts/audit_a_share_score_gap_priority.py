#!/usr/bin/env python3
"""Prioritize A-share score-relevant spec gaps from the score-trace audit."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from mvp20.aggregator import _VALR_SUPPRESSED_WHEN_POOLED


ROOT = Path(__file__).resolve().parent.parent
TRACE_JSON = ROOT / "docs/audit/a_share_score_trace_2026-06-18.json"
FIELD_STRATEGY = ROOT / "docs/data_sources/llm_field_master_list.md"
OUT_JSON = ROOT / "docs/audit/a_share_score_gap_priority_2026-06-18.json"
OUT_MD = ROOT / "docs/audit/a_share_score_gap_priority_2026-06-18.md"

PEER_CONTEXT_SUPPRESSED = set(_VALR_SUPPRESSED_WHEN_POOLED)

VALUATION_CONTEXT_REQUIRED = {
    "L6.mult.pe": (
        "trailing PE should be scored through peer/historical valuation context; "
        "a direct scalar formula would double-count or ignore industry regime"
    ),
    "L6.mult.pb": (
        "PB needs peer/historical valuation context; direct absolute PB scoring "
        "would mix balance-sheet intensity across industries"
    ),
    "L6.state.industry_center": (
        "industry-center payload is a reference baseline; score the stock-vs-peer "
        "spread through peer_compare/percentile, not as a standalone direction"
    ),
}

NORMALIZATION_REQUIRED = {
    "L5.is.eps": "absolute EPS needs EPS growth, history, or peer-normalized profitability before scoring",
    "L5.is.operating_profit": "absolute operating profit needs size/revenue/asset normalization before scoring",
}

BASELINE_REQUIRED = {
    "L5.fcst.eps_cf": "forecast EPS/cash-flow needs comparison against current/base consensus before scoring",
    "L5.fcst.revenue_margin": "forecast revenue/margin needs comparison against current/base margin before scoring",
}

BUSINESS_SEMANTICS_REVIEW = {
    "L5.cf.capex": "capex needs a defined intensity/trend policy; high capex can be investment or drag",
    "L2.segment.revenue_share": "segment revenue share needs a concentration/strategy policy before it has a score direction",
    "L7.flow.block_trade": "block-trade amount/count needs buyer/seller direction or discount/premium before funding_score has a sign",
}

INTENTIONAL_ALIAS_DUPLICATE = {
    "L9.company.mgmt_litigation": (
        "legacy duplicate of L8.gov.management_change in the current Tushare adapter; "
        "do not double-count the same stk_managers events into risk_discount"
    ),
}

INTENTIONAL_FALLBACK_DUPLICATE = {
    "L9.media.social_buzz": (
        "same Tushare ths_hot 热股 evidence as L7.mood.media_social in the current adapter; "
        "do not score as a separate expectation_gap field without a distinct source"
    ),
}

INTENTIONAL_DERIVED_BRIDGE_REVIEW = {
    "L7.mood.media_social": (
        "already consumed by L7.mood.fomo -> overheat_risk/risk_discount; "
        "a direct sentiment_score formula would reuse the same hot-list evidence"
    ),
}

INTENTIONAL_DATA_ONLY = {
    "L6.mult.peg": "scored through L6.state.peg_match; direct raw PEG would double-count",
    "L6.mult.mcap_fcf": "negative FCF makes mcap/FCF sign-aware; no safe scalar formula yet",
    "L7.trade.margin_short": "snapshot margin/short payload lacks clean directional signal",
}

A_SHARE_OPTIONS_UNIVERSE_REQUIRED = {
    "L6.priced.iv": (
        "A-share single-stock option coverage is not broad enough to fabricate; "
        "only populate for a legitimate listed-option universe or mark N/A/Unavailable"
    ),
    "L7.trade.iv": (
        "A-share per-stock IV needs a licensed listed-option mapping; otherwise "
        "keep it out of scoring instead of proxying from unrelated instruments"
    ),
    "L7.trade.options_cp": (
        "A-share per-stock call/put ratios require real option-chain volume/OI; "
        "do not infer them from stock turnover or sentiment"
    ),
}

CANONICAL_DP_ID = {
    "L9.company.mgmt_litigation": "L8.gov.management_change",
    "L9.media.social_buzz": "L7.mood.media_social",
}

REPLACEMENT_DP_ID = {
    "L6.mult.peg": "L6.state.peg_match",
    "L7.mood.media_social": "L7.mood.fomo",
    **{dp_id: "L6.state.peer_compare" for dp_id in PEER_CONTEXT_SUPPRESSED},
    "L6.mult.pe": "L6.state.peer_compare",
    "L6.mult.pb": "L6.state.peer_compare",
    "L6.state.industry_center": "L6.state.peer_compare",
}

STRUCTURED_COLLECTOR_WIRED_PENDING_REFRESH = {
    "L5.surprise.preprice": (
        "Tushare Bucket A now derives forecast announcement preprice from "
        "forecast + daily history; runtime still needs a collector refresh "
        "to prove A-share rows in hot.sqlite"
    ),
    "L10.industry.inventory_orders": (
        "Tushare macro batch now emits PMI new-orders / inventory subindices "
        "as industry confidence-validation rows; runtime still needs a "
        "collector refresh to prove INDUSTRY:<id> rows in hot.sqlite"
    ),
    "L10.industry.sales_price": (
        "Tushare macro batch now emits CPI/PPI price-index payloads as "
        "industry confidence-validation rows; runtime still needs a collector "
        "refresh to prove INDUSTRY:<id> rows in hot.sqlite"
    ),
}

CONDITIONAL_FORMULA_READY_PENDING_VALID_DATA = {
    "L5.surprise.beat_miss": (
        "Conditional score formula is already wired: beat/miss/in_range maps "
        "to expectation_gap. Bucket A now accepts express net-profit, total-profit, "
        "operating-profit, or revenue yoy against the forecast range; current "
        "blocker is the next source refresh / valid event, not formula design."
    ),
    "L8.fin.goodwill_impairment": (
        "Conditional risk formula is already wired through alert_severity. "
        "Bucket A now requests goodwill in the balancesheet cache; after the "
        "next collector refresh, the remaining blocker is source permission/"
        "schema availability or no valid impairment event."
    ),
    "L8.fin.revenue_profit_miss": (
        "Conditional risk formula is already wired through alert_severity. "
        "Current blocker is that beat_miss currently emits no valid miss events."
    ),
    "L8.industry.valuation_compression": (
        "Conditional risk formula is already wired through alert_severity. "
        "Bucket A now emits valid 30d/90d industry PE compression as Known "
        "neutral when it does not cross WARN/ERROR thresholds; current blocker "
        "is the next runtime refresh."
    ),
    "L9.media.analyst_action": (
        "Conditional score formula is already wired: recent net upgrades/downgrades "
        "map to expectation_gap. Bucket B now also treats a recent comparable "
        "same-broker unchanged rating as Known neutral; current blocker is the "
        "next report_rc refresh / valid comparable report, not formula design."
    ),
    "L9.macro.liquidity": (
        "Conditional score formula is already wired: cn_m M2 yoy change maps to "
        "expectation_gap, while sub-0.3pct monthly changes become valid Known "
        "neutral observations. Current blocker is the next cn_m refresh, not "
        "formula design."
    ),
    "L9.macro.fx": (
        "Conditional risk formula is already wired: measurable fx_daily RMB windows "
        "enter risk_discount, with only depreciation beyond threshold producing a "
        "non-zero discount and other measured windows becoming Known neutral. "
        "Current blocker is the next fx_daily refresh, not formula design."
    ),
    "L9.capital.etf_block": (
        "Conditional score formula is already wired: a decoded stock_dzjy_mrmx "
        "window with zero per-stock block-trade events becomes Known neutral, "
        "while non-zero event count/notional maps to a bounded expectation_gap. "
        "Current blocker is the next akshare refresh, not formula design."
    ),
    "L9.industry.compete_risk": (
        "Conditional risk formula is already wired: decoded CLS risk-keyword "
        "windows with zero hits become Known neutral, while non-zero risk hit "
        "count maps to a bounded risk_discount. Current blocker is the next "
        "stock_info_global_cls refresh, not formula design."
    ),
    "L9.industry.policy_change": (
        "Conditional multiplier formula is already wired: decoded CLS policy "
        "windows with zero or ambiguous hits become Known neutral, while "
        "high-precision supportive/restrictive policy terms map to a bounded "
        "policy_sensitivity_multiplier. Current blocker is the next "
        "stock_info_global_cls refresh, not formula design."
    ),
    "L9.media.report": (
        "Conditional score formula is already wired: decoded CLS news windows "
        "with zero or ambiguous headline tilt become Known neutral, while "
        "high-precision positive/negative media terms map to a bounded "
        "expectation_gap through net_media_score. Current blocker is the next "
        "stock_info_global_cls refresh, not formula design."
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def parse_field_strategy(path: Path) -> dict[str, dict[str, str]]:
    """Parse bucket/state hints from docs/data_sources/llm_field_master_list.md."""
    if not path.exists():
        return {}
    pattern = re.compile(
        r"^#### `(?P<dp_id>[^`]+)` .*?\*\(bucket (?P<bucket>[A-Z]), spec `(?P<spec>[^`]+)`, state `(?P<state>[^`]+)`\)"
    )
    out: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        out[match.group("dp_id")] = {
            "bucket": match.group("bucket"),
            "spec": match.group("spec"),
            "state": match.group("state"),
        }
    return out


def source_route(row: Mapping[str, Any], strategy: Mapping[str, Mapping[str, str]]) -> str:
    cats = row.get("runtime_source_categories") or {}
    valid = int(row.get("runtime_valid_real_ts_count") or 0)
    if row["dp_id"] in CONDITIONAL_FORMULA_READY_PENDING_VALID_DATA and valid == 0:
        return "conditional_formula_ready_pending_valid_data"
    if row["dp_id"] in STRUCTURED_COLLECTOR_WIRED_PENDING_REFRESH and valid == 0:
        return "structured_collector_wired_pending_refresh"
    if row["dp_id"] in A_SHARE_OPTIONS_UNIVERSE_REQUIRED:
        return "a_share_listed_options_or_na_required"
    if row["dp_id"] in PEER_CONTEXT_SUPPRESSED:
        return "intentional_peer_context_suppressed"
    if row["dp_id"] in VALUATION_CONTEXT_REQUIRED:
        return "valuation_peer_context_review"
    if row["dp_id"] in NORMALIZATION_REQUIRED:
        return "normalization_required_formula"
    if row["dp_id"] in BASELINE_REQUIRED:
        return "baseline_required_formula"
    if row["dp_id"] in BUSINESS_SEMANTICS_REVIEW:
        return "business_semantics_review"
    if row["dp_id"] in INTENTIONAL_ALIAS_DUPLICATE:
        return "intentional_alias_duplicate"
    if row["dp_id"] in INTENTIONAL_FALLBACK_DUPLICATE:
        return "intentional_fallback_duplicate"
    if row["dp_id"] in INTENTIONAL_DERIVED_BRIDGE_REVIEW:
        return "intentional_derived_bridge_review"
    if row["dp_id"] in INTENTIONAL_DATA_ONLY:
        return "intentional_data_only"
    if cats.get("tushare") or cats.get("akshare"):
        if valid <= 0:
            return "structured_runtime_present_no_valid_data"
        return "existing_structured_runtime_formula"
    if cats.get("derived"):
        if valid <= 0:
            return "derived_runtime_present_no_valid_data"
        return "existing_derived_runtime_formula"
    bucket = (strategy.get(str(row["dp_id"])) or {}).get("bucket")
    if bucket == "C":
        return "llm_or_web_required"
    if bucket == "A":
        return "structured_collector_required"
    return "manual_review_required"


def priority(row: Mapping[str, Any], route: str) -> str:
    valid = int(row.get("runtime_valid_real_ts_count") or 0)
    if route in {"normalization_required_formula", "baseline_required_formula"}:
        return "P1_add_normalized_or_baseline_formula"
    if route in {"valuation_peer_context_review", "business_semantics_review"}:
        return "P3_governance_or_design_review"
    if route == "a_share_listed_options_or_na_required":
        return "P3_governance_or_design_review"
    if route.startswith("intentional_"):
        return "P3_governance_or_design_review"
    if route in {"existing_structured_runtime_formula", "existing_derived_runtime_formula"}:
        if valid >= 1000:
            return "P0_add_formula_high_coverage"
        if valid >= 100:
            return "P1_add_event_or_sparse_formula"
        return "P2_low_coverage_formula"
    if route in {
        "structured_runtime_present_no_valid_data",
        "derived_runtime_present_no_valid_data",
        "conditional_formula_ready_pending_valid_data",
    }:
        return "P2_refresh_or_validate_structured_data"
    if route == "structured_collector_required":
        return "P1_add_tushare_or_structured_collector"
    if route == "structured_collector_wired_pending_refresh":
        return "P1_refresh_runtime_data"
    if route == "llm_or_web_required":
        return "P2_llm_or_web_extraction"
    return "P3_manual_review"


def gap_bucket(row: Mapping[str, Any], route: str, row_priority: str) -> str:
    if route in {
        "llm_or_web_required",
        "structured_runtime_present_no_valid_data",
        "derived_runtime_present_no_valid_data",
        "conditional_formula_ready_pending_valid_data",
        "structured_collector_required",
        "structured_collector_wired_pending_refresh",
        "existing_structured_runtime_formula",
        "existing_derived_runtime_formula",
        "normalization_required_formula",
        "baseline_required_formula",
    }:
        return "blocking_actionable"
    if route == "manual_review_required" or row_priority == "P3_manual_review":
        return "manual_triage"
    if route == "a_share_listed_options_or_na_required":
        return "universe_not_applicable"
    if route in {"business_semantics_review", "valuation_peer_context_review"}:
        return "design_review"
    if route.startswith("intentional_"):
        return "intentional_governance"
    return "manual_triage"


def intent_subtype(row: Mapping[str, Any], route: str) -> str:
    if route == "llm_or_web_required":
        return "requires_llm_or_web"
    if route in {
        "structured_runtime_present_no_valid_data",
        "derived_runtime_present_no_valid_data",
        "conditional_formula_ready_pending_valid_data",
    }:
        return "present_no_valid"
    if route == "structured_collector_required":
        return "structured_collector_missing"
    if route == "structured_collector_wired_pending_refresh":
        return "refresh_required"
    if route == "a_share_listed_options_or_na_required":
        return "listed_option_universe_required"
    if route == "business_semantics_review":
        return "sign_or_business_semantics_required"
    if route == "valuation_peer_context_review":
        return "valuation_context_required"
    if route == "intentional_peer_context_suppressed":
        return "peer_context_suppressed"
    if route in {"intentional_alias_duplicate", "intentional_fallback_duplicate"}:
        return "duplicate_evidence"
    if route == "intentional_derived_bridge_review":
        return "derived_replacement"
    if route == "intentional_data_only":
        return "data_only_no_safe_signal"
    if route in {"normalization_required_formula", "baseline_required_formula"}:
        return "formula_requires_baseline"
    if route in {"existing_structured_runtime_formula", "existing_derived_runtime_formula"}:
        return "formula_mapping_required"
    return "manual_triage"


def source_data_state(row: Mapping[str, Any], route: str) -> str:
    valid = int(row.get("runtime_valid_real_ts_count") or 0)
    if valid > 0:
        return "valid_real"
    if route in {
        "structured_runtime_present_no_valid_data",
        "derived_runtime_present_no_valid_data",
        "conditional_formula_ready_pending_valid_data",
        "structured_collector_wired_pending_refresh",
    }:
        return "present_no_valid"
    if route == "a_share_listed_options_or_na_required":
        return "not_applicable_or_unlicensed"
    return "missing"


def repair_hint(row: Mapping[str, Any], route: str) -> str:
    dp_id = str(row["dp_id"])
    target = str(row.get("score_target") or "")
    role = str(row.get("field_role") or "")
    if dp_id in PEER_CONTEXT_SUPPRESSED:
        return "Do not add a direct formula while valuation peer pool is active; verify L6.state.peer_compare coverage instead."
    if dp_id in VALUATION_CONTEXT_REQUIRED:
        return VALUATION_CONTEXT_REQUIRED[dp_id]
    if dp_id in NORMALIZATION_REQUIRED:
        return NORMALIZATION_REQUIRED[dp_id]
    if dp_id in BASELINE_REQUIRED:
        return BASELINE_REQUIRED[dp_id]
    if dp_id in BUSINESS_SEMANTICS_REVIEW:
        return BUSINESS_SEMANTICS_REVIEW[dp_id]
    if dp_id in A_SHARE_OPTIONS_UNIVERSE_REQUIRED:
        return A_SHARE_OPTIONS_UNIVERSE_REQUIRED[dp_id]
    if dp_id in STRUCTURED_COLLECTOR_WIRED_PENDING_REFRESH:
        return STRUCTURED_COLLECTOR_WIRED_PENDING_REFRESH[dp_id]
    if dp_id in CONDITIONAL_FORMULA_READY_PENDING_VALID_DATA:
        return CONDITIONAL_FORMULA_READY_PENDING_VALID_DATA[dp_id]
    if dp_id in INTENTIONAL_ALIAS_DUPLICATE:
        return INTENTIONAL_ALIAS_DUPLICATE[dp_id]
    if dp_id in INTENTIONAL_FALLBACK_DUPLICATE:
        return INTENTIONAL_FALLBACK_DUPLICATE[dp_id]
    if dp_id in INTENTIONAL_DERIVED_BRIDGE_REVIEW:
        return INTENTIONAL_DERIVED_BRIDGE_REVIEW[dp_id]
    if dp_id in INTENTIONAL_DATA_ONLY:
        return INTENTIONAL_DATA_ONLY[dp_id]
    if route == "structured_runtime_present_no_valid_data":
        return "Collector/derive path is present but emits no valid A-share Known/Proxy rows; refresh, inspect inactive reasons, or fix source coverage before adding a formula."
    if route == "derived_runtime_present_no_valid_data":
        return "Derived path is present but currently produces no valid A-share rows; inspect missing_inputs/inactive_reason before scoring."
    if role == "confidence" or target == "confidence_multiplier":
        return "Convert validation signal into confidence multiplier, not base-score direction."
    if route == "existing_derived_runtime_formula":
        return f"Map the derived payload into {target}; if payload already has multiplier, convert it to signed delta around 1.0."
    if role == "multiplier" or target.endswith("_multiplier"):
        return f"Add multiplier formula around neutral 1.0 and route into {target}."
    if role == "discount" or target.endswith("_discount"):
        return f"Convert event magnitude/freshness into bounded discount for {target}."
    if route == "existing_structured_runtime_formula":
        return f"Add explicit _realtime_field_signal mapping into {target}; calibrate sign and unit from payload."
    if route == "llm_or_web_required":
        return "Add LLM/web extraction with source evidence, freshness, and confidence before scoring."
    return "Manual governance and formula review required."


def field_row_by_dp(trace: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(row["dp_id"]): row for row in trace.get("field_rows") or []}


def compact_sources(row: Mapping[str, Any], limit: int = 3) -> str:
    sources = row.get("sources") or row.get("runtime_sources") or {}
    if not isinstance(sources, Mapping):
        return ""
    return ", ".join(f"{k}:{v}" for k, v in list(sources.items())[:limit])


def build_report(trace: Mapping[str, Any], strategy: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    rows_by_dp = field_row_by_dp(trace)
    formula_gap_ids = trace["summary"]["dp_id_lists"][
        "score_relevant_valid_real_but_no_numeric_formula"
    ]
    participating_gap_ids = trace["summary"]["dp_id_lists"]["participating_gap"]

    formula_rows = []
    for dp_id in formula_gap_ids:
        row = rows_by_dp[dp_id]
        route = source_route(row, strategy)
        row_priority = priority(row, route)
        bucket = gap_bucket(row, route, row_priority)
        formula_rows.append({
            "dp_id": dp_id,
            "field_role": row.get("field_role"),
            "score_target": row.get("score_target"),
            "runtime_valid_real_ts_count": row.get("runtime_valid_real_ts_count"),
            "runtime_source_categories": row.get("runtime_source_categories") or {},
            "sources": row.get("runtime_sources") or {},
            "strategy": strategy.get(dp_id) or {},
            "route": route,
            "priority": row_priority,
            "gap_bucket": bucket,
            "intent_subtype": intent_subtype(row, route),
            "blocking_gap": bucket in {"blocking_actionable", "manual_triage"},
            "source_data_state": source_data_state(row, route),
            "replacement_dp_id": REPLACEMENT_DP_ID.get(dp_id),
            "canonical_dp_id": CANONICAL_DP_ID.get(dp_id),
            "repair_hint": repair_hint(row, route),
        })

    participating_rows = []
    for dp_id in participating_gap_ids:
        row = rows_by_dp[dp_id]
        route = source_route(row, strategy)
        row_priority = priority(row, route)
        bucket = gap_bucket(row, route, row_priority)
        participating_rows.append({
            "dp_id": dp_id,
            "field_role": row.get("field_role"),
            "score_target": row.get("score_target"),
            "runtime_valid_real_ts_count": row.get("runtime_valid_real_ts_count"),
            "runtime_numeric_signal_ts_count": row.get("runtime_numeric_signal_ts_count"),
            "overlay_score_candidate_ts_count": row.get("overlay_score_candidate_ts_count"),
            "effective_score_path_ts_count": row.get("effective_score_path_ts_count"),
            "runtime_source_categories": row.get("runtime_source_categories") or {},
            "sources": row.get("runtime_sources") or {},
            "strategy": strategy.get(dp_id) or {},
            "route": route,
            "priority": row_priority,
            "gap_bucket": bucket,
            "intent_subtype": intent_subtype(row, route),
            "blocking_gap": bucket in {"blocking_actionable", "manual_triage"},
            "source_data_state": source_data_state(row, route),
            "replacement_dp_id": REPLACEMENT_DP_ID.get(dp_id),
            "canonical_dp_id": CANONICAL_DP_ID.get(dp_id),
            "repair_hint": repair_hint(row, route),
        })

    formula_by_route = Counter(row["route"] for row in formula_rows)
    formula_by_priority = Counter(row["priority"] for row in formula_rows)
    formula_by_bucket = Counter(row["gap_bucket"] for row in formula_rows)
    participating_by_route = Counter(row["route"] for row in participating_rows)
    participating_by_priority = Counter(row["priority"] for row in participating_rows)
    participating_by_bucket = Counter(row["gap_bucket"] for row in participating_rows)
    governance_formula_rows = [
        row for row in formula_rows
        if row["gap_bucket"] in {"design_review", "intentional_governance", "universe_not_applicable"}
    ]
    actionable_formula_rows = [
        row for row in formula_rows
        if row["blocking_gap"]
    ]
    governance_participating_rows = [
        row for row in participating_rows
        if row["gap_bucket"] in {"design_review", "intentional_governance", "universe_not_applicable"}
    ]
    actionable_participating_rows = [
        row for row in participating_rows
        if row["blocking_gap"]
    ]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "trace_json": str(TRACE_JSON),
        "summary": {
            "score_relevant_formula_gap_dp_ids": len(formula_rows),
            "actionable_formula_gap_dp_ids": len(actionable_formula_rows),
            "governance_or_intentional_formula_gap_dp_ids": len(governance_formula_rows),
            "formula_gap_by_route": dict(sorted(formula_by_route.items())),
            "formula_gap_by_priority": dict(sorted(formula_by_priority.items())),
            "formula_gap_by_bucket": dict(sorted(formula_by_bucket.items())),
            "participating_gap_dp_ids": len(participating_rows),
            "actionable_participating_gap_dp_ids": len(actionable_participating_rows),
            "blocking_participating_gap_dp_ids": len(actionable_participating_rows),
            "governance_or_intentional_participating_gap_dp_ids": len(
                governance_participating_rows
            ),
            "participating_gap_by_route": dict(sorted(participating_by_route.items())),
            "participating_gap_by_priority": dict(sorted(participating_by_priority.items())),
            "participating_gap_by_bucket": dict(sorted(participating_by_bucket.items())),
            "conditional_formula_ready_pending_valid_data_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["route"] == "conditional_formula_ready_pending_valid_data"
            ),
            "peer_context_suppressed_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["intent_subtype"] == "peer_context_suppressed"
            ),
            "derived_replacement_gap_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["intent_subtype"] == "derived_replacement"
            ),
            "duplicate_evidence_gap_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["intent_subtype"] == "duplicate_evidence"
            ),
            "data_only_no_safe_signal_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["intent_subtype"] == "data_only_no_safe_signal"
            ),
            "universe_not_applicable_dp_ids": sorted(
                row["dp_id"] for row in participating_rows
                if row["gap_bucket"] == "universe_not_applicable"
            ),
            "score_completion_blocking_gap_dp_ids": sorted(
                row["dp_id"] for row in actionable_participating_rows
            ),
        },
        "formula_gap_rows": sorted(
            formula_rows,
            key=lambda r: (r["priority"], r["route"], -int(r["runtime_valid_real_ts_count"] or 0), r["dp_id"]),
        ),
        "participating_gap_rows": sorted(
            participating_rows,
            key=lambda r: (r["priority"], r["route"], -int(r["runtime_valid_real_ts_count"] or 0), r["dp_id"]),
        ),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share score gap priority",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "|---|---:|",
        f"| Score-relevant formula gaps | {summary['score_relevant_formula_gap_dp_ids']} |",
        f"| Actionable formula gaps | {summary['actionable_formula_gap_dp_ids']} |",
        f"| Governance/intentional formula gaps | {summary['governance_or_intentional_formula_gap_dp_ids']} |",
        f"| Participating gaps | {summary['participating_gap_dp_ids']} |",
        f"| Actionable participating gaps | {summary['actionable_participating_gap_dp_ids']} |",
        f"| Governance/intentional participating gaps | {summary['governance_or_intentional_participating_gap_dp_ids']} |",
        "",
        "### Formula Gap By Route",
        "",
        "| route | count |",
        "|---|---:|",
    ]
    for key, value in summary["formula_gap_by_route"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "### Formula Gap By Priority", "", "| priority | count |", "|---|---:|"])
    for key, value in summary["formula_gap_by_priority"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "### Formula Gap By Bucket", "", "| bucket | count |", "|---|---:|"])
    for key, value in summary["formula_gap_by_bucket"].items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Score-Relevant Formula Gaps",
            "",
            "| priority | bucket | subtype | route | dp_id | target | valid ts_codes | main sources | repair hint |",
            "|---|---|---|---|---|---|---:|---|---|",
        ]
    )
    for row in report["formula_gap_rows"]:
        lines.append(
            f"| {row['priority']} | {row['gap_bucket']} | {row['intent_subtype']} | "
            f"{row['route']} | `{row['dp_id']}` | "
            f"{row['score_target']} | {row['runtime_valid_real_ts_count']} | "
            f"{compact_sources(row)} | {row['repair_hint']} |"
        )

    lines.extend(
        [
            "",
            "## Participating Gap Route Counts",
            "",
            "| route | count |",
            "|---|---:|",
        ]
    )
    for key, value in summary["participating_gap_by_route"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "| priority | count |", "|---|---:|"])
    for key, value in summary["participating_gap_by_priority"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "| bucket | count |", "|---|---:|"])
    for key, value in summary["participating_gap_by_bucket"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Participating Gap Details",
            "",
            "| priority | bucket | subtype | route | dp_id | target | valid ts_codes | main sources | repair hint |",
            "|---|---|---|---|---|---|---:|---|---|",
        ]
    )
    for row in report["participating_gap_rows"]:
        lines.append(
            f"| {row['priority']} | {row['gap_bucket']} | {row['intent_subtype']} | "
            f"{row['route']} | `{row['dp_id']}` | "
            f"{row.get('score_target') or ''} | {row['runtime_valid_real_ts_count']} | "
            f"{compact_sources(row)} | {row.get('repair_hint') or ''} |"
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-json", type=Path, default=TRACE_JSON)
    parser.add_argument("--field-strategy", type=Path, default=FIELD_STRATEGY)
    parser.add_argument("--output-json", type=Path, default=OUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUT_MD)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    trace = load_json(args.trace_json)
    strategy = parse_field_strategy(args.field_strategy)
    report = json_safe(build_report(trace, strategy))
    if not args.no_write:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {"ok": True, **report["summary"]},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
