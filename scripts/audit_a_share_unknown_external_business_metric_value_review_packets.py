#!/usr/bin/env python3
"""Build review packets for shortlisted external business-metric value candidates.

This audit consumes the value-candidate adjudication output and creates
review-only packets for rows that have plausible numeric tokens.  It parses
percent tokens into bounded formula-probe options and verifies those options
can bridge to the final-score path if a reviewer later approves one of them.

It does not select a final raw value, mark a row Known, or write runtime scores.
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

from scripts.audit_a_share_review_staging_manifest import ROOT, _bridge_validation


DEFAULT_VALUE_CANDIDATES_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.md"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _percent_value(token: str) -> float | None:
    if not token.endswith("%"):
        return None
    try:
        value = float(token[:-1])
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _round(value: float) -> float:
    return round(value, 6)


def _score_from_percent(percent: float) -> float:
    return _round(max(0.0, min(1.0, percent / 100.0)))


def _formula_option(row: Mapping[str, Any], token: str, index: int) -> dict[str, Any]:
    percent = _percent_value(token)
    if percent is None:
        return {
            "option_id": f"{row.get('value_candidate_adjudication_id')}:invalid:{index}",
            "raw_token": token,
            "option_contract_valid": False,
            "option_validation_errors": ["token is not a percent"],
        }
    score = _score_from_percent(percent)
    payload = {
        "target_dp_id": row.get("dp_id"),
        "score_target": row.get("score_target") or "fundamental_score",
        "data_status": "Known",
        "bridge_entry_data_status": "Known",
        "confidence": 0.36,
        "value_json": {
            "score": score,
            "raw_value": percent,
            "unit": "percent",
            "normalization": "score = clamp(raw_percent / 100, 0, 1)",
            "source_scope_verdict": row.get("source_scope_verdict"),
            "review_required": True,
        },
        "evidence_refs": [
            "docs/audit/a_share_unknown_external_business_metric_value_candidates_2026-06-19.json",
            str(row.get("market_relative_path") or ""),
        ],
        "rationale": "Formula probe only; reviewer must confirm source scope, value choice, bounds, and score mapping before Known draft creation.",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }
    bridge = _bridge_validation(
        str(row.get("dp_id") or ""),
        str(row.get("score_target") or "fundamental_score"),
        payload,
    )
    errors: list[str] = []
    if not bridge.get("final_score_target_ready"):
        errors.append("formula probe does not bridge to final-score target")
    if not isinstance(payload["value_json"]["score"], float):
        errors.append("score must be numeric")
    return {
        "option_id": f"{row.get('value_candidate_adjudication_id')}:{index}",
        "raw_token": token,
        "raw_percent": percent,
        "normalized_ratio": _round(percent / 100.0),
        "formula_probe_score": score,
        "formula_probe_payload": payload,
        "bridge_validation": bridge,
        "option_contract_valid": not errors,
        "option_validation_errors": errors,
    }


def _review_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    tokens = [
        str(token.get("token") or "")
        for token in row.get("value_candidate_tokens") or []
        if isinstance(token, Mapping)
    ]
    options = [_formula_option(row, token, index) for index, token in enumerate(tokens, 1)]
    bridge_ready_options = sum(
        1 for option in options if option.get("bridge_validation", {}).get("final_score_target_ready")
    )
    packet = {
        "value_review_packet_id": row.get("value_candidate_adjudication_id"),
        "value_candidate_adjudication_id": row.get("value_candidate_adjudication_id"),
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target") or "fundamental_score",
        "data_status": "Unknown",
        "source_scope_verdict": row.get("source_scope_verdict"),
        "title": row.get("title"),
        "market_relative_path": row.get("market_relative_path"),
        "excerpt": row.get("excerpt"),
        "candidate_value_options": options,
        "candidate_value_option_count": len(options),
        "bridge_probe_ready_option_count": bridge_ready_options,
        "selected_raw_value": None,
        "selected_value_json": None,
        "missing_before_known": [
            "reviewed_source_scope",
            "reviewed_numeric_value",
            "reviewed_bounds",
            "reviewed_formula_policy",
            "approval_record",
        ],
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "value_review_contract_valid": not errors,
        "value_review_validation_errors": errors,
    }


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("value_review_packet_id"):
        errors.append("value_review_packet_id is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must remain Unknown")
    if packet.get("candidate_value_option_count", 0) <= 0:
        errors.append("at least one candidate value option is required")
    if packet.get("selected_raw_value") is not None:
        errors.append("selected_raw_value must remain null")
    if packet.get("selected_value_json") is not None:
        errors.append("selected_value_json must remain null")
    if packet.get("metric_inputs_ready") is not False:
        errors.append("metric_inputs_ready must remain false")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must remain false")
    if packet.get("approval_ready") is not False:
        errors.append("approval_ready must remain false")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    invalid_options = [
        option
        for option in packet.get("candidate_value_options") or []
        if not option.get("option_contract_valid")
    ]
    if invalid_options:
        errors.append("all candidate value options must be valid formula probes")
    return errors


def build_report(*, value_candidates_path: Path) -> dict[str, Any]:
    started = time.time()
    source = _load_json(value_candidates_path)
    shortlist = [
        row
        for row in source.get("rows") or []
        if isinstance(row, Mapping)
        and row.get("adjudication_status") == "value_candidate_shortlist_review_required"
    ]
    rows = [_review_packet(row) for row in shortlist]
    rows.sort(
        key=lambda row: (
            str(row.get("dp_id") or ""),
            str(row.get("source_scope_verdict") or ""),
            str(row.get("market_relative_path") or ""),
        )
    )
    scope_counts = Counter(str(row.get("source_scope_verdict") or "") for row in rows)
    option_count = sum(int(row["candidate_value_option_count"]) for row in rows)
    bridge_count = sum(int(row["bridge_probe_ready_option_count"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {"value_candidates_path": _portable_path(value_candidates_path)},
        "summary": {
            "shortlist_source_row_count": len(shortlist),
            "value_review_packet_count": len(rows),
            "candidate_value_option_count": option_count,
            "bridge_probe_ready_option_count": bridge_count,
            "selected_raw_value_count": 0,
            "selected_value_json_count": 0,
            "metric_inputs_ready_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "value_review_contract_valid_count": sum(
                1 for row in rows if row["value_review_contract_valid"]
            ),
            "value_review_contract_invalid_count": sum(
                1 for row in rows if not row["value_review_contract_valid"]
            ),
            "source_scope_verdict_counts": dict(sorted(scope_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown external business metric value review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Shortlist source rows: `{summary['shortlist_source_row_count']}`",
        f"- Value review packets: `{summary['value_review_packet_count']}`",
        f"- Candidate value options: `{summary['candidate_value_option_count']}`",
        f"- Bridge-probe-ready options: `{summary['bridge_probe_ready_option_count']}`",
        f"- Selected raw values: `{summary['selected_raw_value_count']}`",
        f"- Metric inputs ready: `{summary['metric_inputs_ready_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | scope | value options | bridge-ready options |",
        "|---|---|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['source_scope_verdict']}` | "
            f"{row['candidate_value_option_count']} | "
            f"{row['bridge_probe_ready_option_count']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Bridge-ready options are formula probes only; they are not selected values.",
            "- Every packet still requires source-scope, numeric-value, bounds, formula-policy, and approval review.",
            "- This audit does not create Known values and does not write runtime scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value-candidates-path", type=Path, default=DEFAULT_VALUE_CANDIDATES_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(value_candidates_path=args.value_candidates_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
