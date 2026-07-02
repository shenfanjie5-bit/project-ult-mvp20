#!/usr/bin/env python3
"""Validate A-share candidate staging payload contracts.

The staging report prepares review envelopes.  This audit validates those
envelopes: required fields, evidence/rationale, numeric bounds, placeholder
semantics, and bridge reachability for concrete review payloads.  It is
read-only and never writes ``runtime/hot.sqlite``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STAGING_PATH = ROOT / "docs/audit/a_share_candidate_staging_payloads_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_candidate_value_contracts_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_candidate_value_contracts_2026-06-19.md"
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


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    x = float(value)
    if not math.isfinite(x):
        return None
    return x


def _range_error(name: str, value: Any, lo: float, hi: float) -> str | None:
    x = _finite_number(value)
    if x is None:
        return f"{name} must be a finite number"
    if not lo <= x <= hi:
        return f"{name}={x} outside [{lo}, {hi}]"
    return None


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_common(row: Mapping[str, Any], payload: Mapping[str, Any] | None) -> list[str]:
    errors: list[str] = []
    dp_id = str(row.get("dp_id") or "")
    score_target = str(row.get("score_target") or "")
    if payload is None:
        return ["missing staging_payload"]
    if payload.get("target_dp_id") != dp_id:
        errors.append("target_dp_id does not match row dp_id")
    if payload.get("score_target") != score_target:
        errors.append("score_target does not match row score_target")
    if payload.get("data_status") not in {"Known", "Proxy", "Unknown", "NotApplicable"}:
        errors.append("data_status must be Known, Proxy, Unknown, or NotApplicable")
    if payload.get("bridge_entry_data_status") not in {
        "Known",
        "Proxy",
        "Unknown",
        "NotApplicable",
    }:
        errors.append("bridge_entry_data_status must be Known, Proxy, Unknown, or NotApplicable")
    confidence = _finite_number(payload.get("confidence"))
    if confidence is None or not 0.0 <= confidence <= 1.0:
        errors.append("confidence must be a finite number in [0, 1]")
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(
        _nonempty_string(ref) for ref in evidence_refs
    ):
        errors.append("evidence_refs must be a non-empty list of strings")
    if not _nonempty_string(payload.get("rationale")):
        errors.append("rationale must be a non-empty string")
    if payload.get("review_status") != "review_required":
        errors.append("review_status must be review_required")
    if payload.get("safe_to_upsert_without_review") is not False:
        errors.append("safe_to_upsert_without_review must be false")
    if not isinstance(payload.get("value_json"), dict):
        errors.append("value_json must be an object")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    return errors


def _bridge_validation(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:contract_validation",
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
        "node_value_score": (node.get("value") or {}).get("score") if node else None,
        "node_synthetic_realtime": bool(node and node.get("synthetic_realtime")),
        "node_score_numeric": _finite_number((node.get("value") or {}).get("score")) is not None
        if node
        else False,
        "final_score_target_ready": bool(
            node is not None and score_target not in FINAL_SCORE_EXCLUDED_TARGETS
        ),
    }


def _validate_known_value(dp_id: str, score_target: str, value: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if dp_id == "L6.mult.dcf":
        scalar = value.get("scalar", value.get("score"))
        err = _range_error("scalar", scalar, -1.0, 1.0)
        if err:
            errors.append(err)
        assumptions = value.get("assumptions")
        if not isinstance(assumptions, Mapping):
            errors.append("assumptions must be an object")
        else:
            for key in ("discount_rate", "terminal_growth", "forecast_horizon", "normalized_fcf"):
                if key not in assumptions:
                    errors.append(f"assumptions.{key} is required")
        if not isinstance(value.get("sensitivity"), Mapping):
            errors.append("sensitivity must be an object")
        return errors
    if dp_id in {"L6.priced.realization_risk", "L8.val.slope_risk_off"}:
        err = _range_error("magnitude", value.get("magnitude"), 0.0, 1.0)
        if err:
            errors.append(err)
        if not isinstance(value.get("drivers"), list) or not value.get("drivers"):
            errors.append("drivers must be a non-empty list")
        return errors
    if dp_id == "L7.reflex.tag":
        x = _finite_number(value.get("multiplier"))
        if x is None or not 0.0 < x <= 2.0:
            errors.append("multiplier must be finite and in (0, 2]")
        if value.get("tag") not in {"positive_feedback", "exhausted_feedback", "neutral"}:
            errors.append("tag must be positive_feedback, exhausted_feedback, or neutral")
        return errors
    if dp_id == "L7.trade.gamma":
        x = _finite_number(value.get("multiplier"))
        if x is None or not 0.0 < x <= 2.0:
            errors.append("multiplier must be finite and in (0, 2]")
        if value.get("applicability") not in {
            "a_share_single_stock_no_listed_option",
            "direct_option",
            "mapped_proxy",
        }:
            errors.append("applicability is invalid")
        return errors

    if score_target in {"fundamental_score", "expectation_gap", "valuation_rerating"}:
        err = _range_error("score", value.get("score"), -1.0, 1.0)
        if err:
            errors.append(err)
    elif score_target in {"risk_discount", "priced_in_discount"}:
        risk_value = value.get("magnitude", value.get("score", value.get("scalar")))
        err = _range_error("magnitude", risk_value, 0.0, 1.0)
        if err:
            errors.append(err)
    elif str(score_target).endswith("_multiplier"):
        x = _finite_number(value.get("multiplier"))
        if x is None or x <= 0:
            errors.append("multiplier must be finite and > 0")
    return errors


def _validate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("staging_payload")
    payload = payload if isinstance(payload, Mapping) else None
    errors = _validate_common(row, payload)
    bridge: dict[str, Any] = {}
    dp_id = str(row.get("dp_id") or "")
    score_target = str(row.get("score_target") or "")
    payload_status = str(row.get("payload_status") or "")
    validation_mode = "blocked"

    if payload is not None:
        raw_value_json = payload.get("value_json")
        value_json = raw_value_json if isinstance(raw_value_json, Mapping) else {}
        if payload_status == "requires_generator_output":
            validation_mode = "placeholder"
            if payload.get("data_status") != "Unknown":
                errors.append("placeholder data_status must be Unknown")
            if value_json != {"review_required": True}:
                errors.append("placeholder value_json must be {'review_required': True}")
        else:
            validation_mode = "concrete"
            errors.extend(_validate_known_value(dp_id, score_target, value_json))
            bridge = _bridge_validation(dp_id, score_target, payload)
            if not bridge.get("bridge_signal_ready"):
                errors.append("bridge signal is not ready")
            if not bridge.get("node_emitted"):
                errors.append("bridge did not emit a realtime node")
            if not bridge.get("node_synthetic_realtime"):
                errors.append("bridge node is not synthetic_realtime")
            if not bridge.get("node_score_numeric"):
                errors.append("bridge node value.score is not numeric")
            if not bridge.get("final_score_target_ready"):
                errors.append("bridge node does not reach a final score target")

    return {
        "dp_id": dp_id,
        "payload_status": payload_status,
        "validation_mode": validation_mode,
        "contract_valid": not errors,
        "validation_errors": errors,
        "bridge_validation": bridge,
    }


def build_report(staging_path: Path) -> dict[str, Any]:
    started = time.time()
    staging = _load_json(staging_path)
    rows = [_validate_row(row) for row in staging.get("rows") or [] if isinstance(row, Mapping)]
    mode_counts = Counter(str(row["validation_mode"]) for row in rows)
    status_counts = Counter(str(row["payload_status"]) for row in rows)
    invalid_rows = [row for row in rows if not row["contract_valid"]]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "staging_path": _portable_path(staging_path),
        "summary": {
            "candidate_rows_checked": len(rows),
            "contract_valid_count": sum(1 for row in rows if row["contract_valid"]),
            "contract_invalid_count": len(invalid_rows),
            "invalid_dp_ids": [row["dp_id"] for row in invalid_rows],
            "concrete_payload_valid_count": sum(
                1
                for row in rows
                if row["validation_mode"] == "concrete" and row["contract_valid"]
            ),
            "placeholder_payload_valid_count": sum(
                1
                for row in rows
                if row["validation_mode"] == "placeholder" and row["contract_valid"]
            ),
            "bridge_validated_concrete_count": sum(
                1
                for row in rows
                if row["bridge_validation"].get("final_score_target_ready")
            ),
            "payload_status_counts": dict(sorted(status_counts.items())),
            "validation_mode_counts": dict(sorted(mode_counts.items())),
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share candidate value contracts",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidate rows checked: `{summary['candidate_rows_checked']}`",
        f"- Contract valid: `{summary['contract_valid_count']}`",
        f"- Contract invalid: `{summary['contract_invalid_count']}`",
        f"- Concrete payloads valid: `{summary['concrete_payload_valid_count']}`",
        f"- Placeholder payloads valid: `{summary['placeholder_payload_valid_count']}`",
        f"- Concrete payloads bridge-validated: `{summary['bridge_validated_concrete_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Validation Mode Counts",
        "",
        "| Mode | Count |",
        "|---|---:|",
    ]
    for mode, count in summary["validation_mode_counts"].items():
        lines.append(f"| `{mode}` | {count} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | payload status | mode | valid | errors |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in report["rows"]:
        errors = "; ".join(row["validation_errors"]) or "-"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['payload_status']}` | "
            f"`{row['validation_mode']}` | "
            f"{'yes' if row['contract_valid'] else 'no'} | "
            f"{errors} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Valid placeholders prove the review contract is complete; they do not produce a scoring signal.",
            "- Valid concrete payloads must pass schema, bounds, evidence/rationale checks, and the production scoring bridge.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-path", type=Path, default=DEFAULT_STAGING_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.staging_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
