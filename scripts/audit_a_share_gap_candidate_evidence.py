#!/usr/bin/env python3
"""Build candidate evidence packs for A-share score-blocking spec gaps.

This is intentionally read-only.  It packages existing runtime dependency rows
into reviewable candidate inputs for later LLM/event/manual fills, but it does
not write candidate values into ``runtime/hot.sqlite`` and therefore does not
change any stock scores.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_READINESS_PATH = ROOT / "docs/audit/a_share_l0_source_readiness_2026-06-19.json"
DEFAULT_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_UNIVERSE_PATH = ROOT / "config/mvp20.universe.yaml"
DEFAULT_SHORT_REPORT_EVIDENCE_PATH = (
    ROOT / "docs/audit/a_share_short_report_evidence_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.md"

MAX_SAMPLES_PER_DEP = 3
MAX_PAYLOAD_KEYS = 12
MAX_STRING_CHARS = 500

MANUAL_DESIGN_POLICIES: dict[str, dict[str, Any]] = {
    "L6.mult.dcf": {
        "policy_name": "bounded_dcf_assumption_candidate",
        "source_dependencies": [
            "L5.cf.fcf",
            "L5.is.revenue_growth",
            "L6.sens.rates",
            "L6.sens.growth_margin",
            "L6.sens.cashflow",
            "L6.mult.mcap_fcf",
        ],
        "target_behavior": (
            "Generate a reviewable DCF valuation-rerating candidate only when "
            "cash-flow, growth, rates, and sensitivity evidence are present. "
            "The candidate must expose discount-rate, terminal-growth, horizon, "
            "and FCF-normalization assumptions explicitly; without reviewed "
            "assumptions it stays Unknown and must not be upserted."
        ),
        "required_output_override": {
            "value_json": {
                "scalar": "bounded valuation contribution in [-1, 1]",
                "assumptions": "discount_rate, terminal_growth, forecast_horizon, normalized_fcf",
                "sensitivity": "low/base/high case values",
            }
        },
    },
    "L6.priced.realization_risk": {
        "policy_name": "priced_catalyst_realization_risk_candidate",
        "source_dependencies": [
            "L6.priced.run_up",
            "L6.priced.news_age",
            "L5.surprise.preprice",
            "L8.val.priced_in",
        ],
        "target_behavior": (
            "Convert run-up, fresh catalyst age, pre-announcement pricing, and "
            "priced-in state into a bounded priced_in_discount risk factor. "
            "Higher recent run-up plus fresher positive catalyst implies higher "
            "realization risk; stale or absent catalyst evidence stays neutral."
        ),
        "required_output_override": {
            "value_json": {
                "magnitude": "risk discount in [0, 1]",
                "drivers": "run_up/news_age/preprice/priced_in evidence refs",
            }
        },
    },
    "L7.reflex.tag": {
        "policy_name": "flow_sentiment_reflexivity_candidate",
        "source_dependencies": [
            "L7.flow.active_inflow",
            "L7.mood.fomo",
            "L7.mood.media_social",
            "L6.priced.run_up",
        ],
        "target_behavior": (
            "Classify reflexivity from active inflow, FOMO, media/social heat, "
            "and recent run-up. Emit a multiplier around neutral 1.0; positive "
            "feedback loops can lift the multiplier, exhausted crowded loops can "
            "dampen it. Keep the candidate bounded and evidence-referenced."
        ),
        "required_output_override": {
            "value_json": {
                "multiplier": "bounded reflexivity multiplier, neutral 1.0",
                "tag": "positive_feedback | exhausted_feedback | neutral",
            }
        },
    },
    "L7.trade.gamma": {
        "policy_name": "a_share_single_stock_options_applicability_candidate",
        "requires_known_dependencies": False,
        "source_dependencies": [
            "L7.trade.iv",
            "L7.trade.options_cp",
        ],
        "target_behavior": (
            "A-share single-stock gamma must be NotApplicable/neutral unless a "
            "legitimate stock-specific listed option, licensed Greeks/OI feed, "
            "or explicit ETF/index proxy mapping exists for the target. Do not "
            "reuse non-A-share option rows for A-share single-stock scoring."
        ),
        "required_output_override": {
            "data_status": "NotApplicable | Known | Unknown",
            "value_json": {
                "multiplier": "1.0 when NotApplicable; bounded gamma multiplier when legitimate direct/proxy option evidence exists",
                "applicability": "a_share_single_stock_no_listed_option | direct_option | mapped_proxy",
            },
        },
    },
    "L8.val.slope_risk_off": {
        "policy_name": "valuation_slope_risk_off_candidate",
        "source_dependencies": [
            "L6.path.second_derivative",
            "L8.val.overvalued",
            "L7.env.risk_appetite",
            "L9.macro.rates",
            "L6.state.expansion_compression",
        ],
        "target_behavior": (
            "Convert decelerating valuation/price momentum, overvaluation, "
            "falling risk appetite, rates pressure, and valuation-compression "
            "state into a bounded risk_discount factor. Risk-off slope should "
            "increase only when multiple evidence legs agree."
        ),
        "required_output_override": {
            "value_json": {
                "magnitude": "risk discount in [0, 1]",
                "drivers": "slope/risk_appetite/overvaluation/rates evidence refs",
            }
        },
    },
}


def _safe_json_loads(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:MAX_STRING_CHARS]}


def _compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (key, child) in enumerate(value.items()):
            if idx >= MAX_PAYLOAD_KEYS:
                out["_truncated_keys"] = len(value) - MAX_PAYLOAD_KEYS
                break
            out[str(key)] = _compact_value(child)
        return out
    if isinstance(value, list):
        compacted = [_compact_value(item) for item in value[:5]]
        if len(value) > 5:
            compacted.append({"_truncated_items": len(value) - 5})
        return compacted
    if isinstance(value, str) and len(value) > MAX_STRING_CHARS:
        return value[:MAX_STRING_CHARS] + "..."
    return value


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _updated_at_iso(updated_at: int | None) -> str | None:
    if updated_at is None:
        return None
    try:
        return dt.datetime.fromtimestamp(int(updated_at), tz=dt.timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _ts_namespace(ts_code: str | None) -> str:
    if not ts_code:
        return "other"
    if ts_code.startswith("MARKET:"):
        return "market"
    if ts_code.startswith("INDUSTRY:"):
        return "industry"
    if "." in ts_code:
        return "stock"
    return "other"


def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_a_share_universe_industries(universe_path: Path) -> dict[str, list[str]]:
    if not universe_path.exists():
        return {}
    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for row in payload.get("constituents") or []:
        if not isinstance(row, dict):
            continue
        ts_code = str(row.get("ts_code") or "")
        if not ts_code.endswith((".SH", ".SZ", ".BJ")):
            continue
        industries = [str(industry) for industry in row.get("industry_ids") or []]
        if industries:
            out[ts_code] = industries
    return out


def _known_ts_codes(conn: sqlite3.Connection | None, dp_id: str) -> set[str]:
    if conn is None:
        return set()
    return {
        str(row["ts_code"])
        for row in conn.execute(
            """
            SELECT ts_code
            FROM realtime_current
            WHERE dp_id = ?
              AND data_status = 'Known'
              AND COALESCE(source, '') NOT LIKE 'mock:%'
            """,
            (dp_id,),
        )
    }


def _contract_spot_grain_join_policy(
    conn: sqlite3.Connection | None,
    universe_path: Path,
) -> dict[str, Any] | None:
    universe = _load_a_share_universe_industries(universe_path)
    raw_ts_codes = _known_ts_codes(conn, "L0.cost.raw_material")
    gross_margin_ts_codes = _known_ts_codes(conn, "L5.is.gross_margin")
    raw_industries = {
        ts_code.removeprefix("INDUSTRY:")
        for ts_code in raw_ts_codes
        if ts_code.startswith("INDUSTRY:")
    }
    if not universe or not raw_industries or not gross_margin_ts_codes:
        return None

    join_ready: list[dict[str, Any]] = []
    missing_raw_material: list[dict[str, Any]] = []
    missing_gross_margin: list[dict[str, Any]] = []
    for ts_code, industry_ids in sorted(universe.items()):
        matching_industries = sorted(raw_industries.intersection(industry_ids))
        if ts_code not in gross_margin_ts_codes:
            missing_gross_margin.append(
                {"ts_code": ts_code, "industry_ids": industry_ids}
            )
        elif not matching_industries:
            missing_raw_material.append(
                {"ts_code": ts_code, "industry_ids": industry_ids}
            )
        else:
            join_ready.append(
                {
                    "ts_code": ts_code,
                    "industry_ids": industry_ids,
                    "matched_raw_material_industry_ids": matching_industries,
                }
            )

    return {
        "policy": (
            "Join stock-level L5.is.gross_margin rows to INDUSTRY:<industry_id> "
            "L0.cost.raw_material rows through config/mvp20.universe.yaml "
            "industry_ids. Generate reviewable candidates only for stocks with "
            "both sides present; leave unmapped stocks Unknown or NotApplicable."
        ),
        "universe_path": _portable_path(universe_path),
        "a_share_universe_count": len(universe),
        "raw_material_industry_count": len(raw_industries),
        "raw_material_industry_ids": sorted(raw_industries),
        "known_gross_margin_a_share_count": sum(
            1 for ts_code in universe if ts_code in gross_margin_ts_codes
        ),
        "join_ready_a_share_count": len(join_ready),
        "missing_raw_material_a_share_count": len(missing_raw_material),
        "missing_gross_margin_a_share_count": len(missing_gross_margin),
        "join_ready_sample": join_ready[:10],
        "missing_raw_material_sample": missing_raw_material[:10],
        "missing_gross_margin_sample": missing_gross_margin[:10],
    }


def _grain_join_policy(
    row: dict[str, Any],
    conn: sqlite3.Connection | None,
    universe_path: Path,
) -> dict[str, Any] | None:
    deps = set(str(dep) for dep in row.get("source_dependencies") or [])
    if (
        row.get("dp_id") == "L0.price.contract_spot"
        and row.get("recommended_source_route") == "local_llm_closed_loop"
        and {"L0.cost.raw_material", "L5.is.gross_margin"}.issubset(deps)
    ):
        return _contract_spot_grain_join_policy(conn, universe_path)
    return None


def _short_report_evidence(
    row: dict[str, Any],
    report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if row.get("dp_id") != "L9.media.short_report" or not report:
        return None
    summary = report.get("summary") or {}
    samples = (report.get("direct_a_share_samples") or []) + (
        report.get("foreign_or_market_samples") or []
    )
    return {
        "audit_report": "docs/audit/a_share_short_report_evidence_2026-06-19.json",
        "candidate_evidence_ready": bool(summary.get("candidate_evidence_ready")),
        "news_html_files_scanned": int(summary.get("news_html_files_scanned") or 0),
        "parse_error_count": int(summary.get("parse_error_count") or 0),
        "strict_short_report_documents": int(
            summary.get("strict_short_report_documents") or 0
        ),
        "direct_a_share_short_report_documents": int(
            summary.get("direct_a_share_short_report_documents") or 0
        ),
        "foreign_or_market_short_report_documents": int(
            summary.get("foreign_or_market_short_report_documents") or 0
        ),
        "direct_a_share_top_ts_codes": summary.get("direct_a_share_top_ts_codes") or {},
        "source_counts": summary.get("source_counts") or {},
        "strict_source_counts": summary.get("strict_source_counts") or {},
        "candidate_policy": (
            "Use direct A-share samples only for active short-report events. "
            "If direct samples are absent, candidate generation must emit "
            "reviewed neutral/Unknown outputs instead of inferring events from "
            "foreign or market-only context."
        ),
        "samples": [
            {
                "path": item.get("path"),
                "source": item.get("source"),
                "title": item.get("title"),
                "a_share_ts_codes": item.get("a_share_ts_codes") or [],
                "excerpt": item.get("excerpt"),
            }
            for item in samples[:5]
            if isinstance(item, dict)
        ],
    }


def _manual_design_policy(row: dict[str, Any]) -> dict[str, Any] | None:
    policy = MANUAL_DESIGN_POLICIES.get(str(row.get("dp_id") or ""))
    if not policy:
        return None
    return {
        "policy_name": policy["policy_name"],
        "requires_known_dependencies": bool(policy.get("requires_known_dependencies", True)),
        "source_dependencies": list(policy.get("source_dependencies") or []),
        "target_behavior": policy["target_behavior"],
        "required_output_override": policy.get("required_output_override") or {},
        "score_mutation": "none; policy only makes the candidate input reviewable",
    }


def _dependency_evidence(
    conn: sqlite3.Connection | None,
    dp_ids: list[str],
    *,
    sample_limit: int = MAX_SAMPLES_PER_DEP,
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for dp_id in dp_ids:
        evidence[dp_id] = {
            "row_count": 0,
            "known_count": 0,
            "status_counts": {},
            "source_counts": {},
            "ts_code_count": 0,
            "namespace_counts": {},
            "latest_updated_at": None,
            "latest_updated_at_iso": None,
            "sample_rows": [],
        }
    if conn is None or not dp_ids:
        return evidence

    for dp_id in dp_ids:
        rows = list(
            conn.execute(
                """
                SELECT ts_code, dp_id, value_json, data_status, confidence, source, updated_at
                FROM realtime_current
                WHERE dp_id = ?
                  AND COALESCE(source, '') NOT LIKE 'mock:%'
                ORDER BY updated_at DESC, ts_code ASC
                """,
                (dp_id,),
            )
        )
        status_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        namespaces: Counter[str] = Counter()
        ts_codes: set[str] = set()
        latest_updated_at: int | None = None
        sample_rows: list[dict[str, Any]] = []
        for row in rows:
            status = str(row["data_status"])
            source = str(row["source"])
            ts_code = str(row["ts_code"])
            updated_at = int(row["updated_at"]) if row["updated_at"] is not None else None
            status_counts[status] += 1
            source_counts[source] += 1
            ts_codes.add(ts_code)
            namespaces[_ts_namespace(ts_code)] += 1
            if updated_at is not None and (latest_updated_at is None or updated_at > latest_updated_at):
                latest_updated_at = updated_at
            if len(sample_rows) < sample_limit:
                payload = _compact_value(_safe_json_loads(row["value_json"]))
                sample_rows.append(
                    {
                        "ts_code": row["ts_code"],
                        "data_status": row["data_status"],
                        "confidence": row["confidence"],
                        "source": row["source"],
                        "updated_at": updated_at,
                        "updated_at_iso": _updated_at_iso(updated_at),
                        "value_json_compact": payload,
                    }
                )

        evidence[dp_id] = {
            "row_count": len(rows),
            "known_count": status_counts.get("Known", 0),
            "status_counts": dict(sorted(status_counts.items())),
            "source_counts": dict(source_counts.most_common(8)),
            "ts_code_count": len(ts_codes),
            "namespace_counts": dict(sorted(namespaces.items())),
            "latest_updated_at": latest_updated_at,
            "latest_updated_at_iso": _updated_at_iso(latest_updated_at),
            "sample_rows": sample_rows,
        }
    return evidence


def _primary_namespaces(evidence: dict[str, Any]) -> set[str]:
    counts = evidence.get("namespace_counts") or {}
    return {str(namespace) for namespace, count in counts.items() if int(count or 0) > 0}


def _mixed_local_dependency_grain(
    deps: list[str],
    dep_evidence: dict[str, dict[str, Any]],
) -> list[str]:
    grain_by_dep = {dep: _primary_namespaces(dep_evidence.get(dep, {})) for dep in deps}
    has_stock = any("stock" in grains for grains in grain_by_dep.values())
    non_stock_deps = [
        dep
        for dep, grains in grain_by_dep.items()
        if grains and "stock" not in grains and ({"industry", "market"} & grains)
    ]
    if has_stock and non_stock_deps:
        return non_stock_deps
    return []


def _classify_candidate(
    row: dict[str, Any],
    dep_evidence: dict[str, dict[str, Any]],
    grain_join_policy: dict[str, Any] | None = None,
    short_report_evidence: dict[str, Any] | None = None,
    manual_design_policy: dict[str, Any] | None = None,
) -> tuple[str, bool, str]:
    route = str(row.get("recommended_source_route") or "")
    deps = [str(dep) for dep in row.get("source_dependencies") or []]
    missing = [dep for dep in deps if dep_evidence.get(dep, {}).get("row_count", 0) == 0]
    known_missing = [dep for dep in deps if dep_evidence.get(dep, {}).get("known_count", 0) == 0]

    if route == "manual_design_review":
        if manual_design_policy:
            requires_known_dependencies = bool(
                manual_design_policy.get("requires_known_dependencies", True)
            )
            if requires_known_dependencies and missing:
                return (
                    "partial_missing_manual_design_dependency",
                    False,
                    f"Manual-design policy exists but dependency rows are missing: {', '.join(missing)}.",
                )
            if requires_known_dependencies and known_missing:
                return (
                    "partial_no_known_manual_design_dependency",
                    False,
                    f"Manual-design policy exists but dependencies lack Known status: {', '.join(known_missing)}.",
                )
            return (
                "ready_for_manual_design_candidate",
                True,
                (
                    "Formula/applicability policy is now explicit and runtime "
                    "evidence can be packaged for governed candidate review; "
                    "no runtime score write is allowed without separate validation."
                ),
            )
        return (
            "needs_manual_design",
            False,
            "Formula/applicability must be designed before any candidate value should affect score.",
        )
    if route == "web_event_extraction":
        if (
            row.get("dp_id") == "L9.media.short_report"
            and short_report_evidence
            and short_report_evidence.get("candidate_evidence_ready")
        ):
            return (
                "ready_for_web_event_candidate",
                True,
                (
                    "Dedicated short-report corpus evidence is present "
                    f"({short_report_evidence['news_html_files_scanned']} news HTML files, "
                    f"{short_report_evidence['direct_a_share_short_report_documents']} direct A-share hits, "
                    f"{short_report_evidence['foreign_or_market_short_report_documents']} foreign/market-only hits). "
                    "Generate active events only from direct A-share evidence; otherwise keep candidates neutral/Unknown."
                ),
            )
        return (
            "needs_dedicated_web_extraction",
            False,
            "Runtime context exists only as generic media/social evidence; short-report semantics need a dedicated web extraction pass.",
        )
    if missing:
        return (
            "partial_missing_dependency",
            False,
            f"Missing runtime dependency rows: {', '.join(missing)}.",
        )
    if known_missing:
        return (
            "partial_no_known_dependency",
            False,
            f"Dependency rows exist but lack Known status: {', '.join(known_missing)}.",
        )
    mixed_grain_deps = (
        _mixed_local_dependency_grain(deps, dep_evidence)
        if route == "local_llm_closed_loop"
        else []
    )
    if mixed_grain_deps:
        if grain_join_policy and int(grain_join_policy.get("join_ready_a_share_count") or 0) > 0:
            return (
                "ready_for_local_llm_candidate_with_grain_join",
                True,
                (
                    "Runtime dependencies are present with an explicit stock-to-industry "
                    "grain join policy; generate candidates only for mapped stocks "
                    f"({grain_join_policy['join_ready_a_share_count']} A-share universe rows)."
                ),
            )
        return (
            "partial_mixed_dependency_grain",
            False,
            (
                "Dependency rows are present but require an explicit grain join "
                f"before candidate generation: {', '.join(mixed_grain_deps)}."
            ),
        )
    if route == "event_llm_from_runtime_news":
        return (
            "ready_for_event_llm_candidate",
            True,
            "Runtime news/event dependencies are present and can be packaged for event classification.",
        )
    if route == "local_llm_closed_loop":
        return (
            "ready_for_local_llm_candidate",
            True,
            "Runtime filing/financial dependencies are present and can be packaged for local closed-loop inference.",
        )
    return (
        "needs_route_review",
        False,
        "Unknown source route; review before candidate generation.",
    )


def _candidate_input(
    row: dict[str, Any],
    dep_evidence: dict[str, dict[str, Any]],
    grain_join_policy: dict[str, Any] | None = None,
    short_report_evidence: dict[str, Any] | None = None,
    manual_design_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    required_output_schema: dict[str, Any] = {
        "target_dp_id": "string",
        "data_status": "Known | NotApplicable | Unknown",
        "value_json": "object with explicit scalar/category/event fields required by scoring formula",
        "confidence": "0.0-1.0",
        "evidence_refs": "array of dependency row/source references",
        "rationale": "short explanation of how evidence supports the value",
    }
    if manual_design_policy and manual_design_policy.get("required_output_override"):
        required_output_schema.update(manual_design_policy["required_output_override"])
    payload = {
        "target_dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "source_route": row.get("recommended_source_route"),
        "model_tier": row.get("model_tier"),
        "refresh_trigger": row.get("refresh_trigger"),
        "candidate_task": "derive a reviewable candidate data-point value from the dependency evidence; do not write to realtime_current",
        "required_output_schema": required_output_schema,
        "dependencies": [
            {
                "dp_id": dep,
                "row_count": dep_evidence.get(dep, {}).get("row_count", 0),
                "known_count": dep_evidence.get(dep, {}).get("known_count", 0),
                "ts_code_count": dep_evidence.get(dep, {}).get("ts_code_count", 0),
                "namespace_counts": dep_evidence.get(dep, {}).get("namespace_counts", {}),
                "latest_updated_at_iso": dep_evidence.get(dep, {}).get("latest_updated_at_iso"),
                "sample_rows": dep_evidence.get(dep, {}).get("sample_rows", []),
            }
            for dep in row.get("source_dependencies") or []
        ],
    }
    if grain_join_policy:
        payload["grain_join_policy"] = grain_join_policy
    if short_report_evidence:
        payload["short_report_evidence"] = short_report_evidence
    if manual_design_policy:
        payload["manual_design_policy"] = manual_design_policy
    return payload


def build_report(
    *,
    readiness_path: Path,
    db_path: Path,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
    short_report_evidence_path: Path | None = None,
    sample_limit: int = MAX_SAMPLES_PER_DEP,
) -> dict[str, Any]:
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    short_report_report = _load_optional_json(short_report_evidence_path)
    conn = _connect_ro(db_path)
    rows: list[dict[str, Any]] = []
    try:
        for row in readiness.get("rows") or []:
            manual_policy = _manual_design_policy(row)
            deps = [str(dep) for dep in row.get("source_dependencies") or []]
            if not deps and manual_policy:
                deps = [str(dep) for dep in manual_policy.get("source_dependencies") or []]
            evidence_row = dict(row)
            evidence_row["source_dependencies"] = deps
            dep_evidence = _dependency_evidence(conn, deps, sample_limit=sample_limit)
            join_policy = _grain_join_policy(evidence_row, conn, universe_path)
            short_evidence = _short_report_evidence(evidence_row, short_report_report)
            status, ready, note = _classify_candidate(
                evidence_row,
                dep_evidence,
                join_policy,
                short_evidence,
                manual_policy,
            )
            rows.append(
                {
                    "dp_id": row.get("dp_id"),
                    "priority": row.get("priority"),
                    "score_target": row.get("score_target"),
                    "recommended_source_route": row.get("recommended_source_route"),
                    "source_dependencies": deps,
                    "candidate_status": status,
                    "candidate_input_ready": ready,
                    "upsert_recommended": False,
                    "safety_note": "read-only evidence pack; score-affecting runtime writes require separate validation",
                    "status_note": note,
                    "dependency_evidence": dep_evidence,
                    "candidate_input": _candidate_input(
                        evidence_row,
                        dep_evidence,
                        join_policy,
                        short_evidence,
                        manual_policy,
                    ),
                }
            )
    finally:
        if conn is not None:
            conn.close()

    status_counts = Counter(str(row["candidate_status"]) for row in rows)
    route_counts = Counter(str(row["recommended_source_route"]) for row in rows)
    ready_by_route = Counter(
        str(row["recommended_source_route"]) for row in rows if row["candidate_input_ready"]
    )
    missing_deps = sorted(
        {
            dep
            for row in rows
            if not row["candidate_input_ready"]
            for dep, evidence in row["dependency_evidence"].items()
            if evidence.get("row_count", 0) == 0
        }
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "readiness_path": _portable_path(readiness_path),
        "db_path": _portable_path(db_path),
        "universe_path": _portable_path(universe_path),
        "short_report_evidence_path": (
            _portable_path(short_report_evidence_path)
            if short_report_evidence_path is not None
            else None
        ),
        "summary": {
            "blocking_gap_count": len(rows),
            "candidate_input_ready_count": sum(1 for row in rows if row["candidate_input_ready"]),
            "candidate_input_not_ready_count": sum(1 for row in rows if not row["candidate_input_ready"]),
            "safe_to_upsert_without_review_count": 0,
            "candidate_status_counts": dict(sorted(status_counts.items())),
            "recommended_source_route_counts": dict(sorted(route_counts.items())),
            "candidate_ready_by_route": dict(sorted(ready_by_route.items())),
            "dependency_dp_ids_missing_runtime_rows": missing_deps,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    status_counts = summary["candidate_status_counts"]
    not_ready_reasons: list[str] = []
    if status_counts.get("needs_dedicated_web_extraction"):
        not_ready_reasons.append("web extraction")
    if status_counts.get("needs_manual_design"):
        not_ready_reasons.append("manual design")
    if status_counts.get("partial_mixed_dependency_grain"):
        not_ready_reasons.append("grain-join policy")
    if status_counts.get("partial_missing_dependency"):
        not_ready_reasons.append("missing dependency data")
    if status_counts.get("partial_no_known_dependency"):
        not_ready_reasons.append("dependency rows without Known status")
    not_ready_reason_text = ", ".join(not_ready_reasons) or "route review"
    lines = [
        "# A-share gap candidate evidence",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Blocking gaps packaged: `{summary['blocking_gap_count']}`",
        f"- Candidate inputs ready: `{summary['candidate_input_ready_count']}`",
        f"- Candidate inputs not ready: `{summary['candidate_input_not_ready_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Candidate Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["candidate_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | route | status | ready | deps missing runtime rows | note |",
            "|---|---|---|---:|---|---|",
        ]
    )
    for row in report["rows"]:
        missing = [
            dep
            for dep, evidence in row["dependency_evidence"].items()
            if evidence.get("row_count", 0) == 0
        ]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['recommended_source_route']}` | "
            f"`{row['candidate_status']}` | "
            f"{'yes' if row['candidate_input_ready'] else 'no'} | "
            f"{', '.join(f'`{dep}`' for dep in missing) or '-'} | "
            f"{row['status_note']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Ready rows mean dependency evidence exists and can be sent through a local candidate-generation/review step.",
        ]
    )
    if int(summary["candidate_input_not_ready_count"] or 0):
        lines.append(
            f"- Not-ready rows are deliberately excluded from runtime upserts because they need {not_ready_reason_text}."
        )
    else:
        lines.append(
            "- No not-ready rows remain in this candidate-input audit; runtime upserts still require separate value validation and review."
        )
    lines.extend(
        [
            "- This report does not change scores; it only narrows the next fill workload from generic gaps to evidence-backed candidate inputs.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument(
        "--short-report-evidence-path",
        type=Path,
        default=DEFAULT_SHORT_REPORT_EVIDENCE_PATH,
    )
    parser.add_argument("--sample-limit", type=int, default=MAX_SAMPLES_PER_DEP)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        readiness_path=args.readiness_path,
        db_path=args.db_path,
        universe_path=args.universe_path,
        short_report_evidence_path=args.short_report_evidence_path,
        sample_limit=args.sample_limit,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
