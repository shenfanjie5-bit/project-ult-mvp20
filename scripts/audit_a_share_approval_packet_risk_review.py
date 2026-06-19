#!/usr/bin/env python3
"""Classify A-share approval-review packets by review risk.

This report is deliberately read-only. It helps decide review order for
concrete A-share candidate packets, but it never creates approvals and never
writes runtime values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKETS_PATH = ROOT / "docs/audit/a_share_approval_review_packets_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.md"

STRUCTURED_SOURCE_KINDS = {
    "local_single_dependency_policy_pilot",
    "local_structured_policy_pilot",
    "local_structured_text_policy_pilot",
}
STRICT_BULK_REVIEW_DP_IDS = {
    "L0.cost.cac",
    "L0.cost.labor",
    "L0.price.pricing_power",
    "L0.supply.capacity",
    "L0.supply.chain_eff",
    "L0.supply.inventory",
}
BORDERLINE_STRUCTURED_TEXT_DP_IDS = {"L0.supply.channel_service"}
EVENT_SOURCE_KIND = "event_text_policy_pilot"
MANUAL_SOURCE_KIND = "manual_policy_pilot"


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _impact_value(row: Mapping[str, Any]) -> float | None:
    value_json = row.get("value_json")
    value_json = value_json if isinstance(value_json, Mapping) else {}
    for key in ("score", "magnitude"):
        value = _float(value_json.get(key))
        if value is not None:
            return abs(value)
    multiplier = _float(value_json.get("multiplier"))
    if multiplier is not None:
        return abs(multiplier - 1.0)
    return None


def _has_external_text_evidence(row: Mapping[str, Any]) -> bool:
    refs = row.get("evidence_refs") or []
    if not isinstance(refs, list):
        return False
    return any(str(ref).startswith("dockcase:") for ref in refs)


def _risk_class(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    source_kind = str(row.get("source_kind") or "")
    score_target = str(row.get("score_target") or "")
    confidence = _float(row.get("confidence"))
    impact = _impact_value(row)

    if row.get("approval_gate_status") != "approval_missing":
        reasons.append("packet is not in approval_missing state")
    if row.get("data_status") != "Known":
        reasons.append("packet is not a Known concrete value")
    if not row.get("final_score_target_ready"):
        reasons.append("packet is not final-score-target ready")
    if not row.get("approval_payload_hash_matches_manifest"):
        reasons.append("approval payload hash does not match manifest")
    if not row.get("approval_record_template_contract_valid"):
        reasons.append("approval template contract is invalid")

    if reasons:
        return "do_not_approve_until_contract_fixed", reasons

    if score_target != "fundamental_score":
        reasons.append(f"non-fundamental score target: {score_target}")
        if source_kind == MANUAL_SOURCE_KIND:
            reasons.append("manual-policy payload requires explicit policy review")
        if impact is not None and impact >= 0.25:
            reasons.append(f"high score impact {impact:.6g}")
        return "individual_policy_review_required", reasons

    if source_kind == EVENT_SOURCE_KIND:
        reasons.append("event/text evidence requires source and transmission review")
        if _has_external_text_evidence(row):
            reasons.append("packet depends on local market-document snippets")
        return "individual_event_evidence_review_required", reasons

    if source_kind == MANUAL_SOURCE_KIND:
        reasons.append("manual-policy payload requires assumption review")
        return "individual_policy_review_required", reasons

    if str(row.get("dp_id") or "") in BORDERLINE_STRUCTURED_TEXT_DP_IDS:
        reasons.append("structured-text packet should be sample-checked before approval")
        return "borderline_structured_text_review_candidate", reasons

    if source_kind in STRUCTURED_SOURCE_KINDS:
        if str(row.get("dp_id") or "") not in STRICT_BULK_REVIEW_DP_IDS:
            reasons.append("structured proxy semantics require individual review")
            return "individual_structured_review_required", reasons
        if confidence is None or confidence < 0.34:
            reasons.append(f"confidence below bulk-review floor: {confidence}")
        if impact is None:
            reasons.append("impact value is unavailable")
        elif impact > 0.25:
            reasons.append(f"impact exceeds bulk-review cap: {impact:.6g}")
        if reasons:
            return "individual_structured_review_required", reasons
        reasons.append("structured/local dependency packet with bounded impact")
        return "bulk_structured_review_candidate", reasons

    reasons.append(f"unrecognized source kind: {source_kind}")
    return "individual_policy_review_required", reasons


def build_report(*, packets_path: Path) -> dict[str, Any]:
    started = time.time()
    packets = _load_json(packets_path)
    rows: list[dict[str, Any]] = []
    for source in packets.get("rows") or []:
        if not isinstance(source, Mapping):
            continue
        risk_class, reasons = _risk_class(source)
        row = {
            "dp_id": source.get("dp_id"),
            "score_target": source.get("score_target"),
            "source_kind": source.get("source_kind"),
            "data_status": source.get("data_status"),
            "confidence": source.get("confidence"),
            "impact_value": _impact_value(source),
            "approval_gate_status": source.get("approval_gate_status"),
            "payload_sha256": source.get("payload_sha256"),
            "risk_class": risk_class,
            "risk_reasons": reasons,
            "final_score_target_ready": bool(source.get("final_score_target_ready")),
            "approval_payload_hash_matches_manifest": bool(
                source.get("approval_payload_hash_matches_manifest")
            ),
            "approval_record_template_contract_valid": bool(
                source.get("approval_record_template_contract_valid")
            ),
            "evidence_ref_count": len(source.get("evidence_refs") or []),
            "runtime_write_allowed": False,
            "auto_approval_allowed": False,
            "production_write_allowed": False,
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row.get("risk_class") or ""),
            str(row.get("score_target") or ""),
            str(row.get("dp_id") or ""),
        )
    )
    risk_counts = Counter(str(row.get("risk_class") or "") for row in rows)
    source_counts = Counter(str(row.get("source_kind") or "") for row in rows)
    target_counts = Counter(str(row.get("score_target") or "") for row in rows)
    do_not_approve = [
        str(row.get("dp_id") or "")
        for row in rows
        if row.get("risk_class") == "do_not_approve_until_contract_fixed"
    ]
    individual_review_count = sum(
        1
        for row in rows
        if str(row.get("risk_class") or "").startswith("individual_")
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {"packets_path": _portable_path(packets_path)},
        "summary": {
            "packet_count": len(rows),
            "bulk_structured_review_candidate_count": risk_counts.get(
                "bulk_structured_review_candidate", 0
            ),
            "borderline_structured_text_review_candidate_count": risk_counts.get(
                "borderline_structured_text_review_candidate", 0
            ),
            "individual_review_required_count": individual_review_count,
            "individual_event_evidence_review_required_count": risk_counts.get(
                "individual_event_evidence_review_required", 0
            ),
            "individual_structured_review_required_count": risk_counts.get(
                "individual_structured_review_required", 0
            ),
            "individual_policy_review_required_count": risk_counts.get(
                "individual_policy_review_required", 0
            ),
            "do_not_approve_until_contract_fixed_count": len(do_not_approve),
            "do_not_approve_until_contract_fixed_dp_ids": do_not_approve,
            "auto_approval_allowed_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "risk_class_counts": dict(sorted(risk_counts.items())),
            "source_kind_counts": dict(sorted(source_counts.items())),
            "score_target_counts": dict(sorted(target_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share approval packet risk review",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Packets reviewed: `{summary['packet_count']}`",
        f"- Bulk structured-review candidates: `{summary['bulk_structured_review_candidate_count']}`",
        f"- Borderline structured-text candidates: `{summary['borderline_structured_text_review_candidate_count']}`",
        f"- Individual review required: `{summary['individual_review_required_count']}`",
        f"- Event-evidence individual reviews: `{summary['individual_event_evidence_review_required_count']}`",
        f"- Structured individual reviews: `{summary['individual_structured_review_required_count']}`",
        f"- Policy / non-fundamental individual reviews: `{summary['individual_policy_review_required_count']}`",
        f"- Do-not-approve until contract fixed: `{summary['do_not_approve_until_contract_fixed_count']}`",
        f"- Auto approvals allowed: `{summary['auto_approval_allowed_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Risk classes",
        "",
        "| risk class | count |",
        "|---|---:|",
    ]
    for key, count in summary["risk_class_counts"].items():
        lines.append(f"| `{key}` | {count} |")
    lines.extend(
        [
            "",
            "## Packets",
            "",
            "| dp_id | target | source | confidence | impact | risk class | reason |",
            "|---|---|---|---:|---:|---|---|",
        ]
    )
    for row in report["rows"]:
        reasons = "; ".join(str(reason) for reason in row.get("risk_reasons") or [])
        impact = row.get("impact_value")
        impact_text = "" if impact is None else f"{impact:.6g}"
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('score_target')}` | "
            f"`{row.get('source_kind')}` | "
            f"{row.get('confidence')} | "
            f"{impact_text} | "
            f"`{row.get('risk_class')}` | "
            f"{reasons} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This report prioritizes review work; it is not an approval list.",
            "- Bulk structured-review candidates still require reviewer identity, timestamp, matching payload hash, and risk acknowledgement before runtime write.",
            "- Borderline structured-text candidates should receive source-text sample checks before any batch approval.",
            "- Event/text, manual-policy, and non-fundamental score-target packets remain individual-review items.",
            "- The report does not write runtime values or change scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets-path", type=Path, default=DEFAULT_PACKETS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(packets_path=args.packets_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
