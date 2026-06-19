#!/usr/bin/env python3
"""Draft review-only values for local single-dependency A-share candidates.

This pilot is deliberately narrow and read-only.  It only handles the three
non-manual tasks that the readiness audit classifies as
``local_single_dependency_policy_required``.  It emits bounded review drafts
when a single structured dependency has a defensible monotonic policy, and
keeps revenue-only replacement demand Unknown.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_READINESS_PATH = ROOT / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_local_single_dependency_policy_drafts_2026-06-19.md"
FINAL_SCORE_EXCLUDED_TARGETS = {
    "none",
    "audit_only",
    "display_only",
    "parent_score",
    "node_score",
}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _candidate_rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _single_dependency_rows(readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("route_bucket") == "local_single_dependency_policy_required":
            rows.append(row)
    return rows


def _deps(candidate_row: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    candidate_input = (
        candidate_row.get("candidate_input")
        if isinstance(candidate_row, Mapping)
        else None
    )
    deps: dict[str, dict[str, Any]] = {}
    if not isinstance(candidate_input, Mapping):
        return deps
    for dep in candidate_input.get("dependencies") or []:
        if not isinstance(dep, dict):
            continue
        dp_id = str(dep.get("dp_id") or "")
        if dp_id:
            deps[dp_id] = dep
    return deps


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _sample_values(dep: Mapping[str, Any] | None, *keys: str) -> list[float]:
    if not isinstance(dep, Mapping):
        return []
    values: list[float] = []
    for sample in dep.get("sample_rows") or []:
        if not isinstance(sample, Mapping):
            continue
        compact = sample.get("value_json_compact")
        if not isinstance(compact, Mapping):
            continue
        for key in keys:
            value = _safe_float(compact.get(key))
            if value is not None:
                values.append(value)
                break
    return values


def _avg(values: Iterable[float], default: float = 0.0) -> float:
    nums = list(values)
    if not nums:
        return default
    return sum(nums) / len(nums)


def _evidence_refs(candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> list[str]:
    refs = ["docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"]
    for dep_id in deps:
        refs.append(f"runtime:realtime_current:{dep_id}")
    if isinstance(candidate_row, Mapping):
        refs.append("docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json")
    return list(dict.fromkeys(refs))


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
        "draft_kind": "local_single_dependency_policy_pilot",
        "draft_status": draft_status,
        "pilot_only": True,
        "production_write_allowed": False,
    }


def _bridge_validation(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:local_single_dependency_policy_pilot",
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


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_payload(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("target_dp_id") != dp_id:
        errors.append("target_dp_id does not match row dp_id")
    if payload.get("score_target") != score_target:
        errors.append("score_target does not match row score_target")
    if payload.get("data_status") not in {"Known", "Unknown"}:
        errors.append("data_status must be Known or Unknown")
    confidence = _safe_float(payload.get("confidence"))
    if confidence is None or not 0.0 <= confidence <= 1.0:
        errors.append("confidence must be finite and in [0, 1]")
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(_nonempty_string(ref) for ref in evidence_refs):
        errors.append("evidence_refs must be a non-empty list of strings")
    if not _nonempty_string(payload.get("rationale")):
        errors.append("rationale must be non-empty")
    if payload.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if payload.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if payload.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    value_json = payload.get("value_json")
    if not isinstance(value_json, Mapping):
        errors.append("value_json must be an object")
        value_json = {}
    if payload.get("data_status") == "Known":
        score = _safe_float(value_json.get("score"))
        if score is None or not -1.0 <= score <= 1.0:
            errors.append("Known draft score must be finite and in [-1, 1]")
        if not isinstance(value_json.get("drivers"), list) or not value_json.get("drivers"):
            errors.append("Known draft drivers must be non-empty")
    else:
        if value_json.get("review_required") is not True:
            errors.append("Unknown draft value_json.review_required must be true")
        if not _nonempty_string(value_json.get("blocked_reason")):
            errors.append("Unknown draft must include blocked_reason")
    return {"contract_valid": not errors, "validation_errors": errors}


def _pricing_power(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    gross_margin_values = _sample_values(deps.get("L5.is.gross_margin"), "scalar")
    avg_gm = _avg(gross_margin_values)
    score = _clip((avg_gm - 0.20) / 0.30)
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "score": _round(score),
            "drivers": ["L5.is.gross_margin"],
            "components": {
                "sample_avg_gross_margin": _round(avg_gm),
                "neutral_gross_margin": 0.20,
                "scale": 0.30,
            },
        },
        confidence=0.42,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps gross-margin evidence to pricing-power direction using a conservative "
            "neutral 20% margin and bounded review-only score."
        ),
        draft_status="draft_known_review_required",
    )


def _inventory_policy(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    inventory_values = _sample_values(deps.get("L5.bs.inventory"), "inventory_to_assets")
    avg_inventory = _avg(inventory_values)
    score = _clip((0.20 - avg_inventory) / 0.40)
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Known",
        value_json={
            "score": _round(score),
            "drivers": ["L5.bs.inventory"],
            "components": {
                "sample_avg_inventory_to_assets": _round(avg_inventory),
                "neutral_inventory_to_assets": 0.20,
                "scale": 0.40,
            },
        },
        confidence=0.42,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Pilot maps lower inventory-to-assets to stronger supply inventory quality; "
            "high inventory remains a bounded negative signal pending review."
        ),
        draft_status="draft_known_review_required",
    )


def _replacement_unknown(dp_id: str, score_target: str, candidate_row: Mapping[str, Any] | None, deps: Mapping[str, Any]) -> dict[str, Any]:
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Unknown",
        value_json={
            "review_required": True,
            "blocked_reason": "revenue_only_cannot_identify_replacement_cycle",
            "required_policy": "replacement demand needs product lifecycle, installed base, or cycle evidence beyond revenue scalar",
        },
        confidence=0.0,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale=(
            "Revenue is materially known, but a single revenue scalar does not identify replacement cycle demand; keep Unknown."
        ),
        draft_status="unknown_policy_required",
    )


def _draft_payload(readiness_row: Mapping[str, Any], candidate_row: Mapping[str, Any] | None) -> dict[str, Any]:
    dp_id = str(readiness_row.get("dp_id") or "")
    score_target = str(readiness_row.get("score_target") or "")
    deps = _deps(candidate_row)
    if candidate_row is None:
        return _payload_envelope(
            dp_id=dp_id,
            score_target=score_target,
            data_status="Unknown",
            value_json={"review_required": True, "blocked_reason": "missing_candidate_evidence"},
            confidence=0.0,
            evidence_refs=["docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"],
            rationale="No matching candidate-evidence row exists; keep Unknown.",
            draft_status="unknown_missing_candidate_evidence",
        )
    if dp_id == "L0.price.pricing_power":
        return _pricing_power(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.supply.inventory":
        return _inventory_policy(dp_id, score_target, candidate_row, deps)
    if dp_id == "L0.demand.replacement":
        return _replacement_unknown(dp_id, score_target, candidate_row, deps)
    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Unknown",
        value_json={"review_required": True, "blocked_reason": "unsupported_single_dependency_policy"},
        confidence=0.0,
        evidence_refs=_evidence_refs(candidate_row, deps),
        rationale="This single-dependency task is not supported by the pilot policy.",
        draft_status="unknown_unsupported_policy",
    )


def build_report(readiness_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    readiness = _load_json(readiness_path)
    candidate = _load_json(candidate_path)
    candidate_rows = _candidate_rows_by_dp(candidate)
    rows: list[dict[str, Any]] = []
    for readiness_row in _single_dependency_rows(readiness):
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
            "single_dependency_task_count": len(rows),
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
        "# A-share local single-dependency policy drafts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Single-dependency tasks: `{summary['single_dependency_task_count']}`",
        f"- Draft Known review packets: `{summary['draft_known_count']}`",
        f"- Draft Unknown packets: `{summary['draft_unknown_count']}`",
        f"- Draft contracts valid: `{summary['draft_contract_valid_count']}`",
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
            "- This pilot produces review-only policy drafts for single-dependency local candidates when monotonic direction is defensible.",
            "- `L0.demand.replacement` remains Unknown because revenue alone cannot identify replacement-cycle demand.",
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
