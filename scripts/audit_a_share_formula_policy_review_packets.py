#!/usr/bin/env python3
"""Build review packets for A-share formula-policy score-conversion gaps.

The remediation queue identifies unresolved score-relevant fields where current
runtime inputs exist but a direct formula would be unsafe without scoring
policy, peer context, or sign semantics. This audit turns those rows into
review packets. It does not choose Known values, does not write runtime state,
and does not make production writes safe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_REMEDIATION_PATH = (
    AUDIT_DIR / "a_share_score_conversion_remediation_queue_2026-06-19.json"
)
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-19.json"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_formula_policy_review_packets_2026-06-19.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_formula_policy_review_packets_2026-06-19.md"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _rows_by_dp(rows: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _packet_id(dp_id: str, score_target: str, repair_hint: str) -> str:
    raw = "|".join([dp_id, score_target, repair_hint])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _sample_values(row: Mapping[str, Any] | None, limit: int = 2) -> list[dict[str, Any]]:
    if not row:
        return []
    out: list[dict[str, Any]] = []
    for sample in row.get("sample_values") or []:
        if not isinstance(sample, Mapping):
            continue
        out.append(
            {
                "ts_code": sample.get("ts_code"),
                "status": sample.get("status"),
                "source": sample.get("source"),
                "value": sample.get("value"),
            }
        )
        if len(out) >= limit:
            break
    return out


def _policy_family(dp_id: str) -> str:
    if dp_id in {"L6.mult.pe", "L6.mult.pb", "L6.state.industry_center"}:
        return "valuation_peer_context"
    if dp_id == "L5.cf.capex":
        return "capex_intensity_and_trend"
    if dp_id == "L2.segment.revenue_share":
        return "segment_concentration_and_strategy"
    if dp_id == "L7.flow.block_trade":
        return "block_trade_directional_flow"
    return "manual_formula_policy"


def _policy_template(dp_id: str) -> dict[str, Any]:
    if dp_id in {"L6.mult.pe", "L6.mult.pb", "L6.state.industry_center"}:
        return {
            "policy_family": "valuation_peer_context",
            "direct_formula_rejected": True,
            "preferred_path": "score stock-vs-peer valuation spread through L6.state.peer_compare",
            "candidate_formula_shape": "bounded signed valuation_rerating from peer percentile/z-score or premium_vs_industry_pct, not raw absolute PE/PB",
            "minimum_required_inputs": [
                "stock valuation scalar",
                "industry or peer-pool median/percentile",
                "peer pool size and as-of trade_date",
                "non-positive / loss-making handling policy",
                "reviewed bounds and score direction",
            ],
            "acceptance_criteria": [
                "direct L6.mult.pe/L6.mult.pb raw scalar formula remains suppressed while peer context is available",
                "L6.state.industry_center is used as reference input, not a standalone scored direction",
                "replacement path reaches final score or reviewer explicitly approves a fallback policy",
            ],
        }
    if dp_id == "L5.cf.capex":
        return {
            "policy_family": "capex_intensity_and_trend",
            "direct_formula_rejected": True,
            "preferred_path": "score capex only after intensity/trend policy is reviewed",
            "candidate_formula_shape": "bounded fundamental_score from capex intensity versus revenue/assets/OCF plus multi-period trend and growth-stage context",
            "minimum_required_inputs": [
                "capex scalar",
                "reviewed denominator such as revenue, assets, or operating cash flow",
                "historical capex trend",
                "growth-stage / industry capex intensity baseline",
                "policy for when capex is investment versus cash-flow drag",
            ],
            "acceptance_criteria": [
                "absolute capex is never scored by size alone",
                "negative or unusually high intensity has explicit sign policy",
                "reviewer approves denominator, bounds, and direction",
            ],
        }
    if dp_id == "L2.segment.revenue_share":
        return {
            "policy_family": "segment_concentration_and_strategy",
            "direct_formula_rejected": True,
            "preferred_path": "score concentration only with reviewed strategic/industry context",
            "candidate_formula_shape": "bounded fundamental_score from segment concentration, diversification, or strategic exposure after peer/strategy policy review",
            "minimum_required_inputs": [
                "segment revenue percentages",
                "segment taxonomy or target-strategy labels",
                "industry peer concentration baseline",
                "policy for whether concentration is advantage, risk, or neutral",
            ],
            "acceptance_criteria": [
                "top-segment share alone is not assumed positive or negative",
                "segment labels are mapped to reviewed strategy/industry context",
                "reviewer approves concentration/diversification direction and bounds",
            ],
        }
    if dp_id == "L7.flow.block_trade":
        return {
            "policy_family": "block_trade_directional_flow",
            "direct_formula_rejected": True,
            "preferred_path": "score block trades only with buyer/seller direction or discount/premium evidence",
            "candidate_formula_shape": "bounded funding_score from directional block-trade pressure, using discount/premium, buyer/seller identity, or shareholder-change context",
            "minimum_required_inputs": [
                "block-trade amount and count",
                "block price versus close/VWAP",
                "buyer/seller side or seat/shareholder identity",
                "event freshness and free-float/notional normalizer",
            ],
            "acceptance_criteria": [
                "amount/count alone remains data-only",
                "discount/premium or buyer/seller semantics determine sign",
                "reviewer approves notional normalizer and freshness decay",
            ],
        }
    return {
        "policy_family": "manual_formula_policy",
        "direct_formula_rejected": True,
        "preferred_path": "manual review required",
        "candidate_formula_shape": "review required",
        "minimum_required_inputs": ["review required"],
        "acceptance_criteria": ["reviewer approves formula policy"],
    }


def _replacement_summary(
    remediation_row: Mapping[str, Any],
    closure_by_dp: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    replacement_dp_id = remediation_row.get("replacement_dp_id")
    if not replacement_dp_id:
        return {
            "replacement_dp_id": None,
            "replacement_path_ready": False,
            "replacement_closure_status": None,
            "replacement_effective_score_path_ts_count": 0,
        }
    replacement = closure_by_dp.get(str(replacement_dp_id), {})
    return {
        "replacement_dp_id": replacement_dp_id,
        "replacement_path_ready": replacement.get("closure_status") == "closed_reaches_final_score",
        "replacement_closure_status": replacement.get("closure_status"),
        "replacement_score_target": replacement.get("score_target"),
        "replacement_runtime_valid_real_ts_count": int(
            replacement.get("runtime_valid_real_ts_count") or 0
        ),
        "replacement_effective_score_path_ts_count": int(
            replacement.get("effective_score_path_ts_count") or 0
        ),
        "replacement_sample_values": _sample_values(replacement, limit=1),
    }


def _validate_packet(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("packet_id"):
        errors.append("packet_id is required")
    if packet.get("remediation_class") != "formula_policy_required":
        errors.append("remediation_class must be formula_policy_required")
    if packet.get("policy_review_status") != "formula_policy_review_required":
        errors.append("policy_review_status must require review")
    if packet.get("direct_formula_ready") is not False:
        errors.append("direct_formula_ready must remain false")
    if packet.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    template = packet.get("formula_policy_template")
    if not isinstance(template, Mapping):
        errors.append("formula_policy_template is required")
    else:
        for key in (
            "policy_family",
            "candidate_formula_shape",
            "minimum_required_inputs",
            "acceptance_criteria",
        ):
            if not template.get(key):
                errors.append(f"formula_policy_template.{key} is required")
    if not packet.get("review_blockers"):
        errors.append("review_blockers are required")
    return errors


def _build_packet(
    remediation_row: Mapping[str, Any],
    closure_by_dp: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    dp_id = str(remediation_row.get("dp_id") or "")
    score_target = str(remediation_row.get("score_target") or "")
    closure_row = closure_by_dp.get(dp_id, {})
    repair_hint = str(remediation_row.get("repair_hint") or "")
    template = _policy_template(dp_id)
    replacement = _replacement_summary(remediation_row, closure_by_dp)
    packet = {
        "packet_id": _packet_id(dp_id, score_target, repair_hint),
        "dp_id": dp_id,
        "score_target": score_target,
        "policy_family": _policy_family(dp_id),
        "remediation_class": remediation_row.get("remediation_class"),
        "conversion_path_status": remediation_row.get("conversion_path_status"),
        "source_data_state": remediation_row.get("source_data_state"),
        "runtime_valid_real_ts_count": int(
            remediation_row.get("runtime_valid_real_ts_count") or 0
        ),
        "runtime_numeric_signal_ts_count": int(
            remediation_row.get("runtime_numeric_signal_ts_count") or 0
        ),
        "score_company_route_ready": bool(remediation_row.get("score_company_route_ready")),
        "runtime_source_categories": remediation_row.get("runtime_source_categories") or {},
        "main_sources": remediation_row.get("main_sources"),
        "sample_values": _sample_values(closure_row),
        "replacement_path": replacement,
        "formula_policy_template": template,
        "review_blockers": [
            "review formula direction and bounds",
            "review required input sufficiency",
            "confirm replacement/canonical path is insufficient or intentionally bypassed",
            "create approval record before runtime write",
        ],
        "policy_review_status": "formula_policy_review_required",
        "direct_formula_ready": False,
        "known_draft_sufficient": False,
        "safe_to_upsert_without_review": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validate_packet(packet)
    return {
        **packet,
        "policy_contract_valid": not errors,
        "policy_validation_errors": errors,
    }


def build_report(*, remediation_path: Path, field_closure_path: Path) -> dict[str, Any]:
    remediation = _load_json(remediation_path)
    field_closure = _load_json(field_closure_path)
    closure_by_dp = _rows_by_dp(field_closure.get("rows"))
    rows = [
        _build_packet(row, closure_by_dp)
        for row in remediation.get("rows") or []
        if isinstance(row, Mapping)
        and row.get("remediation_class") == "formula_policy_required"
    ]
    rows.sort(key=lambda row: (row["policy_family"], row["dp_id"]))

    by_policy = Counter(str(row.get("policy_family") or "") for row in rows)
    by_target = Counter(str(row.get("score_target") or "") for row in rows)
    replacement_ready_count = sum(
        1 for row in rows if row["replacement_path"].get("replacement_path_ready")
    )
    business_semantics_count = sum(
        1
        for row in rows
        if row["policy_family"]
        in {
            "capex_intensity_and_trend",
            "segment_concentration_and_strategy",
            "block_trade_directional_flow",
        }
    )
    valuation_peer_count = by_policy["valuation_peer_context"]
    valid_contract_count = sum(1 for row in rows if row["policy_contract_valid"])

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "remediation_path": _portable_path(remediation_path),
            "field_closure_path": _portable_path(field_closure_path),
            "dockcase_scan": "not_performed",
        },
        "summary": {
            "formula_policy_packet_count": len(rows),
            "current_input_available_count": sum(
                1 for row in rows if row["runtime_valid_real_ts_count"] > 0
            ),
            "valuation_peer_context_packet_count": valuation_peer_count,
            "business_semantics_packet_count": business_semantics_count,
            "replacement_path_ready_count": replacement_ready_count,
            "direct_formula_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "policy_contract_valid_count": valid_contract_count,
            "policy_contract_invalid_count": len(rows) - valid_contract_count,
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "policy_family_counts": dict(sorted(by_policy.items())),
            "score_target_counts": dict(sorted(by_target.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def _md_table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share formula-policy review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Formula-policy packets: `{summary['formula_policy_packet_count']}`",
        f"- Current input available: `{summary['current_input_available_count']}`",
        f"- Valuation peer-context packets: `{summary['valuation_peer_context_packet_count']}`",
        f"- Business-semantics packets: `{summary['business_semantics_packet_count']}`",
        f"- Replacement path ready: `{summary['replacement_path_ready_count']}`",
        f"- Direct formula ready: `{summary['direct_formula_ready_count']}`",
        f"- Known draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Policy contracts valid: `{summary['policy_contract_valid_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Policy Families",
        "",
        "| policy_family | count |",
        "|---|---:|",
    ]
    for family, count in summary["policy_family_counts"].items():
        lines.append(_md_table_row([f"`{family}`", count]))
    lines.extend(
        [
            "",
            "## Review Packets",
            "",
            "| policy_family | dp_id | target | valid ts_codes | replacement ready | direct formula ready | required review |",
            "|---|---|---|---:|---|---|---|",
        ]
    )
    for row in report["rows"]:
        template = row["formula_policy_template"]
        lines.append(
            _md_table_row(
                [
                    f"`{row['policy_family']}`",
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    row["runtime_valid_real_ts_count"],
                    row["replacement_path"].get("replacement_path_ready"),
                    row["direct_formula_ready"],
                    "; ".join(template.get("minimum_required_inputs") or []),
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These packets are policy handoff artifacts, not scoring changes.",
            "- `direct_formula_ready_count = 0` keeps raw PE/PB/capex/segment/block-trade payloads out of final score until policy review is complete.",
            "- Valuation packets should prefer the already scoring `L6.state.peer_compare` route unless a reviewer approves a fallback.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remediation-path", type=Path, default=DEFAULT_REMEDIATION_PATH)
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        remediation_path=args.remediation_path,
        field_closure_path=args.field_closure_path,
    )
    if not args.no_write:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.md_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, **report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
