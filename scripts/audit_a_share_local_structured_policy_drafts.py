#!/usr/bin/env python3
"""Draft review-only values for local structured A-share candidates.

This pilot is read-only and deliberately conservative. It handles only the
``local_structured_llm_required`` rows from the non-manual readiness audit.
Rows with a defensible monotonic policy get bounded Known review drafts; rows
that require business decomposition, unit volume, TAM/share, or lease detail
stay Unknown. The contract/spot draft is intentionally review-only because it
depends on a governed stock-to-industry raw-material grain join.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance
from scripts.audit_a_share_local_single_dependency_policy_drafts import (
    DEFAULT_CANDIDATE_PATH,
    DEFAULT_READINESS_PATH,
    FINAL_SCORE_EXCLUDED_TARGETS,
    ROOT,
    _avg,
    _candidate_rows_by_dp,
    _clip,
    _deps,
    _evidence_refs,
    _load_json,
    _portable_path,
    _round,
    _safe_float,
    _sample_values,
    _validate_payload,
)


DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_local_structured_policy_drafts_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_local_structured_policy_drafts_2026-06-19.md"


def _structured_rows(readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness.get("rows") or []:
        if isinstance(row, dict) and row.get("route_bucket") == "local_structured_llm_required":
            rows.append(row)
    return rows


def _payload_envelope(
    *,
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict[str, Any],
    confidence: float,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str,
) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": data_status,
        "value_json": value_json,
        "confidence": _round(max(0.0, min(1.0, confidence))),
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "draft_kind": "local_structured_policy_pilot",
        "draft_status": draft_status,
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _known(
    *,
    dp_id: str,
    score_target: str,
    score: float,
    drivers: list[str],
    components: dict[str, Any],
    confidence: float,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str = "draft_known_review_required",
) -> dict[str, Any]:
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "score": _round(score),
            "drivers": drivers,
            "components": components,
        },
        confidence=confidence,
        evidence_refs=evidence_refs,
        rationale=rationale,
        draft_status=draft_status,
    )


def _unknown(
    *,
    dp_id: str,
    score_target: str,
    blocked_reason: str,
    required_policy: str,
    evidence_refs: list[str],
    rationale: str,
    draft_status: str = "unknown_policy_required",
) -> dict[str, Any]:
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Unknown",
        value_json={
            "review_required": True,
            "blocked_reason": blocked_reason,
            "required_policy": required_policy,
        },
        confidence=0.0,
        evidence_refs=evidence_refs,
        rationale=rationale,
        draft_status=draft_status,
    )


def _bridge_validation(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:local_structured_policy_pilot",
        "updated_at": 1_800_000_000,
    }
    nodes = (
        synthesize_realtime_nodes(
            {dp_id: entry},
            registry,
            existing_dp_ids=set(),
            ts_code="000001.SZ",
        )
        if registry is not None
        else []
    )
    node = nodes[0] if nodes else None
    return {
        "bridge_signal": signal,
        "bridge_signal_ready": signal is not None,
        "node_emitted": node is not None,
        "node_score": (node.get("value") or {}).get("score") if node else None,
        "node_synthetic_realtime": bool(node and node.get("synthetic_realtime")),
        "final_score_target_ready": bool(
            node is not None and score_target not in FINAL_SCORE_EXCLUDED_TARGETS
        ),
    }


def _paired_ratios(
    numerator_dep: Mapping[str, Any] | None,
    denominator_dep: Mapping[str, Any] | None,
    numerator_key: str,
    denominator_key: str,
) -> list[float]:
    if not isinstance(numerator_dep, Mapping) or not isinstance(denominator_dep, Mapping):
        return []
    ratios: list[float] = []
    numerator_samples = numerator_dep.get("sample_rows") or []
    denominator_samples = denominator_dep.get("sample_rows") or []
    for numerator_sample, denominator_sample in zip(numerator_samples, denominator_samples):
        if not isinstance(numerator_sample, Mapping) or not isinstance(denominator_sample, Mapping):
            continue
        numerator_value = _safe_float(
            (numerator_sample.get("value_json_compact") or {}).get(numerator_key)
        )
        denominator_value = _safe_float(
            (denominator_sample.get("value_json_compact") or {}).get(denominator_key)
        )
        if numerator_value is not None and denominator_value and denominator_value > 0:
            ratios.append(numerator_value / denominator_value)
    return ratios


def _cost_cac(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    ratios = _sample_values(deps.get("L5.is.sga_rd"), "sga_rd_ratio_revenue")
    avg_ratio = _avg(ratios)
    score = _clip((0.18 - avg_ratio) / 0.30)
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L5.is.sga_rd", "L5.is.revenue"],
        components={
            "sample_avg_sga_rd_ratio_revenue": _round(avg_ratio),
            "neutral_ratio": 0.18,
            "scale": 0.30,
        },
        confidence=0.36,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps lower SGA/R&D burden versus revenue to a better CAC/cost-position draft; "
            "this remains review-only because SGA/R&D is an imperfect CAC proxy."
        ),
    )


def _cost_labor(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    pct_values = _sample_values(deps.get("L4.cost.labor"), "labor_cost_pct")
    yoy_values = _sample_values(deps.get("L4.cost.labor"), "labor_cost_yoy_pct")
    avg_pct = _avg(pct_values, default=20.0)
    avg_yoy = _avg(yoy_values, default=0.0)
    score = _clip(((20.0 - avg_pct) / 40.0) - (avg_yoy / 30.0))
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L4.cost.labor", "L5.is.sga_rd"],
        components={
            "sample_avg_labor_cost_pct": _round(avg_pct),
            "sample_avg_labor_cost_yoy_pct": _round(avg_yoy),
            "neutral_labor_cost_pct": 20.0,
            "pct_scale": 40.0,
            "yoy_scale": 30.0,
        },
        confidence=0.38,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot treats lower labor-cost share and falling labor cost as a bounded positive draft; "
            "the output remains review-gated."
        ),
    )


def _demand_terminal(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    yoy_values = _sample_values(deps.get("L5.is.revenue_growth"), "yoy_pct")
    avg_yoy = _avg(yoy_values)
    score = _clip(math.tanh(avg_yoy / 35.0))
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L5.is.revenue", "L5.is.revenue_growth"],
        components={
            "sample_avg_revenue_yoy_pct": _round(avg_yoy),
            "tanh_scale": 35.0,
        },
        confidence=0.34,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot uses revenue growth as a broad terminal-demand proxy; it is not a substitute "
            "for reviewed volume, ASP, or end-market decomposition."
        ),
    )


def _supply_capacity(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    ratios = _paired_ratios(
        deps.get("L5.cf.capex"),
        deps.get("L5.bs.goodwill_ppe"),
        "scalar",
        "fix_assets_ppe",
    )
    avg_ratio = _avg(ratios)
    score = _clip((avg_ratio - 0.02) / 0.08)
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L5.cf.capex", "L5.bs.goodwill_ppe"],
        components={
            "sample_avg_capex_to_ppe": _round(avg_ratio),
            "neutral_capex_to_ppe": 0.02,
            "scale": 0.08,
        },
        confidence=0.34,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps capex relative to PPE to a bounded capacity-investment draft; "
            "capacity utilization and project details still need review."
        ),
    )


def _chain_eff(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    ccc_values = _sample_values(deps.get("L4.eff.cycle"), "ccc_days")
    avg_ccc = _avg(ccc_values, default=90.0)
    score = _clip((90.0 - avg_ccc) / 180.0)
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L4.eff.turnover", "L4.eff.cycle"],
        components={
            "sample_avg_ccc_days": _round(avg_ccc),
            "neutral_ccc_days": 90.0,
            "scale": 180.0,
        },
        confidence=0.38,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps shorter cash-conversion cycle to better supply-chain efficiency; "
            "outlier and industry-context review is still required."
        ),
    )


def _grain_join_components(candidate_row: Mapping[str, Any]) -> dict[str, Any]:
    candidate_input = candidate_row.get("candidate_input")
    if not isinstance(candidate_input, Mapping):
        return {}
    grain = candidate_input.get("grain_join_policy")
    if not isinstance(grain, Mapping):
        return {}
    keys = [
        "a_share_universe_count",
        "raw_material_industry_count",
        "known_gross_margin_a_share_count",
        "join_ready_a_share_count",
        "missing_raw_material_a_share_count",
        "missing_gross_margin_a_share_count",
    ]
    return {key: grain.get(key) for key in keys if grain.get(key) is not None}


def _contract_spot(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    raw_material_changes = _sample_values(deps.get("L0.cost.raw_material"), "avg_pct_change")
    gross_margins = _sample_values(deps.get("L5.is.gross_margin"), "scalar")
    avg_raw_material_pct_change = _avg(raw_material_changes, default=0.0)
    avg_gross_margin = _avg(gross_margins, default=0.20)
    raw_material_relief = -avg_raw_material_pct_change / 3.0
    margin_buffer = (avg_gross_margin - 0.20) / 0.50
    score = _clip(raw_material_relief + margin_buffer)
    grain_components = _grain_join_components(candidate_row)
    return _known(
        dp_id=dp_id,
        score_target=score_target,
        score=score,
        drivers=["L0.cost.raw_material", "L5.is.gross_margin"],
        components={
            "sample_avg_raw_material_pct_change": _round(avg_raw_material_pct_change),
            "sample_avg_gross_margin": _round(avg_gross_margin),
            "raw_material_relief_component": _round(raw_material_relief),
            "gross_margin_buffer_component": _round(margin_buffer),
            "grain_join_policy": grain_components,
        },
        confidence=0.32,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps lower raw-material pressure plus gross-margin buffer to a bounded "
            "contract/spot pricing draft for join-ready A-share rows; this remains review-only "
            "because futures changes and gross margin do not prove individual contract terms."
        ),
        draft_status="draft_known_pass_through_review_required",
    )


def _policy_unknown(dp_id: str, score_target: str, candidate_row: Mapping[str, Any], deps: Mapping[str, Any]) -> dict[str, Any]:
    policies = {
        "L0.cost.rent": (
            "ppe_capex_cannot_identify_rent_or_lease_burden",
            "rent-cost drafts require lease/rent expense or reviewed asset-light policy, not only PPE/capex/goodwill proxies",
        ),
        "L0.demand.frequency": (
            "revenue_growth_cannot_separate_purchase_frequency",
            "frequency needs transaction/order/usage cadence or reviewed decomposition beyond revenue growth",
        ),
        "L0.demand.penetration": (
            "revenue_growth_cannot_identify_penetration_without_tam",
            "penetration needs TAM, market share, user-base, or installed-base evidence",
        ),
        "L0.price.product_asp": (
            "revenue_and_margin_cannot_identify_unit_asp_without_volume_mix",
            "ASP needs unit volume, product mix, or reviewed price-index evidence beyond revenue/gross margin",
        ),
    }
    blocked_reason, required_policy = policies.get(
        dp_id,
        (
            "unsupported_local_structured_policy",
            "no conservative local structured policy is defined for this dp_id",
        ),
    )
    return _unknown(
        dp_id=dp_id,
        score_target=score_target,
        blocked_reason=blocked_reason,
        required_policy=required_policy,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale="Structured dependencies are present, but this field needs business-specific review before Known output.",
    )


def _draft_payload(readiness_row: Mapping[str, Any], candidate_row: Mapping[str, Any] | None) -> dict[str, Any]:
    dp_id = str(readiness_row.get("dp_id") or "")
    score_target = str(readiness_row.get("score_target") or "")
    if candidate_row is None:
        return _unknown(
            dp_id=dp_id,
            score_target=score_target,
            blocked_reason="missing_candidate_evidence",
            required_policy="matching candidate-evidence row is required before local structured draft output",
            evidence_refs=["docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"],
            rationale="No matching candidate-evidence row exists; keep Unknown.",
            draft_status="unknown_missing_candidate_evidence",
        )
    deps = _deps(candidate_row)
    if dp_id == "L0.cost.cac":
        return _cost_cac(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.cost.labor":
        return _cost_labor(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.demand.terminal":
        return _demand_terminal(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.supply.capacity":
        return _supply_capacity(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.supply.chain_eff":
        return _chain_eff(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.price.contract_spot":
        return _contract_spot(dp_id, score_target, candidate_row, deps)
    return _policy_unknown(dp_id, score_target, candidate_row, deps)


def build_report(readiness_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    readiness = _load_json(readiness_path)
    candidate = _load_json(candidate_path)
    candidate_rows = _candidate_rows_by_dp(candidate)
    rows: list[dict[str, Any]] = []
    for readiness_row in _structured_rows(readiness):
        dp_id = str(readiness_row.get("dp_id") or "")
        score_target = str(readiness_row.get("score_target") or "")
        candidate_row = candidate_rows.get(dp_id)
        payload = _draft_payload(readiness_row, candidate_row)
        contract = _validate_payload(dp_id, score_target, payload)
        bridge = (
            _bridge_validation(dp_id, score_target, payload)
            if payload.get("data_status") == "Known"
            else {}
        )
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "route_bucket": readiness_row.get("route_bucket"),
                "dependency_readiness": readiness_row.get("dependency_readiness"),
                "draft_status": payload.get("draft_status"),
                "draft_payload": payload,
                "contract_validation": contract,
                "bridge_validation": bridge,
                "production_write_allowed": False,
            }
        )

    draft_status_counts = Counter(row["draft_status"] for row in rows)
    known_rows = [row for row in rows if row["draft_payload"].get("data_status") == "Known"]
    unknown_rows = [row for row in rows if row["draft_payload"].get("data_status") == "Unknown"]
    invalid_rows = [row for row in rows if not row["contract_validation"]["contract_valid"]]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "readiness_path": _portable_path(readiness_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "local_structured_task_count": len(rows),
            "draft_known_count": len(known_rows),
            "draft_unknown_count": len(unknown_rows),
            "draft_contract_valid_count": sum(1 for row in rows if row["contract_validation"]["contract_valid"]),
            "draft_contract_invalid_count": len(invalid_rows),
            "draft_contract_invalid_dp_ids": [row["dp_id"] for row in invalid_rows],
            "bridge_validated_known_count": sum(
                1 for row in known_rows if row["bridge_validation"].get("final_score_target_ready")
            ),
            "bridge_blocked_known_count": sum(
                1 for row in known_rows if not row["bridge_validation"].get("final_score_target_ready")
            ),
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "draft_status_counts": dict(sorted(draft_status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share local structured policy drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Local structured tasks: `{summary['local_structured_task_count']}`",
        f"- Draft Known review packets: `{summary['draft_known_count']}`",
        f"- Draft Unknown packets: `{summary['draft_unknown_count']}`",
        f"- Draft contracts valid: `{summary['draft_contract_valid_count']}`",
        f"- Draft contracts invalid: `{summary['draft_contract_invalid_count']}`",
        f"- Known drafts bridge-validated: `{summary['bridge_validated_known_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Draft Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["draft_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | draft status | data status | contract | bridge | confidence | value |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        payload = row["draft_payload"]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['score_target']}` | "
            f"`{row['draft_status']}` | "
            f"`{payload['data_status']}` | "
            f"{'yes' if row['contract_validation'].get('contract_valid') else 'no'} | "
            f"{'yes' if row['bridge_validation'].get('final_score_target_ready') else '-'} | "
            f"{payload['confidence']} | "
            f"`{json.dumps(payload['value_json'], ensure_ascii=False, sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This pilot emits review-only local structured drafts where a monotonic financial policy is defensible.",
            "- Fields that require volume/mix/TAM/lease detail/text review remain Unknown.",
            "- Contract/spot pricing is a review-only pass-through draft from raw-material futures, gross margin, and the explicit grain-join policy.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.readiness_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
