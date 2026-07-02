#!/usr/bin/env python3
"""Draft value-selection and formula policy for L0.demand.penetration.

This report consumes the confirmed P1 source-scope packet and the existing
value-review packet. It proposes the review target and formula policy, but does
not select a final value, emit a Known draft, create an approval packet, or
write runtime data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_review_staging_manifest import _bridge_validation  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_CONFIRMATION_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json"
)
DEFAULT_VALUE_REVIEW_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_policy_draft_2026-06-19.md"
)


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


def _value_packet_by_id(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        packet_id = str(row.get("value_review_packet_id") or "")
        if packet_id:
            out[packet_id] = dict(row)
    return out


def _valid_options(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(option)
        for option in packet.get("candidate_value_options") or []
        if isinstance(option, Mapping)
        and option.get("option_contract_valid")
        and isinstance(option.get("bridge_validation"), Mapping)
        and option["bridge_validation"].get("final_score_target_ready")
    ]


def _draft_row(source_row: Mapping[str, Any], packet: Mapping[str, Any] | None) -> dict[str, Any]:
    packet = packet or {}
    options = _valid_options(packet)
    source_confirmed = bool(source_row.get("source_scope_confirmed"))
    raw_tokens = [str(token) for token in source_row.get("raw_tokens") or []]
    matching_options = [
        option for option in options if str(option.get("raw_token") or "") in raw_tokens
    ]
    option = matching_options[0] if matching_options else (options[0] if options else {})
    raw_percent = option.get("raw_percent")
    score = option.get("formula_probe_score")
    proposed_value_json = None
    proposed_payload = None
    bridge = {}
    if source_confirmed and raw_percent is not None and score is not None:
        proposed_value_json = {
            "score": score,
            "raw_value": raw_percent,
            "unit": "percent",
            "normalization": "score = clamp(raw_percent / 100, 0, 1)",
            "source_scope": source_row.get("confirmed_scope"),
            "source_scope_confirmed": True,
            "review_required": True,
            "bounds": {"score_min": 0.0, "score_max": 1.0},
            "formula_policy": "Treat domestic listed-company market-share percentage as penetration proxy only after reviewer confirms issuer/industry applicability.",
        }
        proposed_payload = {
            "target_dp_id": "L0.demand.penetration",
            "score_target": "fundamental_score",
            "data_status": "Known",
            "bridge_entry_data_status": "Known",
            "confidence": 0.36,
            "value_json": proposed_value_json,
            "evidence_refs": [
                "docs/audit/a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json",
                "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json",
                str(source_row.get("market_relative_path") or ""),
            ],
            "rationale": "Review draft only: P1 source confirms a domestic listed-company electronic-gas market-share percentage, but reviewer must still accept value selection, bounds, formula policy, and applicability.",
            "review_status": "review_required",
            "safe_to_upsert_without_review": False,
        }
        bridge = _bridge_validation(
            "L0.demand.penetration",
            "fundamental_score",
            proposed_payload,
        )
    validation_errors: list[str] = []
    if not source_confirmed:
        validation_errors.append("source scope is not confirmed")
    if not options:
        validation_errors.append("no bridge-ready candidate value option")
    if proposed_value_json is None:
        validation_errors.append("no proposed value json")
    if proposed_payload is not None and not bridge.get("final_score_target_ready"):
        validation_errors.append("proposed payload does not bridge to final score")
    return {
        "dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "value_review_packet_id": source_row.get("value_review_packet_id"),
        "source_scope_confirmed": source_confirmed,
        "raw_tokens": raw_tokens,
        "proposed_raw_value": raw_percent,
        "proposed_value_json": proposed_value_json,
        "proposed_payload": proposed_payload,
        "bridge_validation": bridge,
        "draft_contract_valid": not validation_errors,
        "draft_validation_errors": validation_errors,
        "review_status": "review_required",
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "missing_before_known": [
            "reviewed_numeric_value_selection",
            "reviewed_bounds",
            "reviewed_formula_policy",
            "issuer_or_industry_applicability_review",
            "approval_record",
        ],
    }


def build_report(*, source_confirmation_path: Path, value_review_path: Path) -> dict[str, Any]:
    started = time.time()
    source_confirmation = _load_json(source_confirmation_path)
    value_review = _load_json(value_review_path)
    value_by_id = _value_packet_by_id(value_review)
    rows = [
        _draft_row(row, value_by_id.get(str(row.get("value_review_packet_id") or "")))
        for row in source_confirmation.get("rows") or []
        if isinstance(row, Mapping)
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "source_confirmation_path": _portable_path(source_confirmation_path),
            "value_review_path": _portable_path(value_review_path),
        },
        "summary": {
            "draft_row_count": len(rows),
            "source_scope_confirmed_count": sum(
                1 for row in rows if row["source_scope_confirmed"]
            ),
            "proposed_value_json_count": sum(
                1 for row in rows if row.get("proposed_value_json") is not None
            ),
            "draft_contract_valid_count": sum(
                1 for row in rows if row["draft_contract_valid"]
            ),
            "draft_contract_invalid_count": sum(
                1 for row in rows if not row["draft_contract_valid"]
            ),
            "bridge_final_score_ready_count": sum(
                1
                for row in rows
                if (row.get("bridge_validation") or {}).get("final_score_target_ready")
            ),
            "selected_raw_value_count": 0,
            "selected_value_json_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; value-policy draft only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration value-policy draft",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Draft rows: `{summary['draft_row_count']}`",
        f"- Source scope confirmed: `{summary['source_scope_confirmed_count']}`",
        f"- Proposed value JSONs: `{summary['proposed_value_json_count']}`",
        f"- Draft contracts valid: `{summary['draft_contract_valid_count']}`",
        f"- Bridge final-score ready: `{summary['bridge_final_score_ready_count']}`",
        f"- Selected raw values: `{summary['selected_raw_value_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | proposed raw value | proposed score | bridge-ready | missing before Known |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        value = row.get("proposed_value_json") or {}
        missing = ", ".join(row.get("missing_before_known") or [])
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"{row.get('proposed_raw_value')} | "
            f"{value.get('score')} | "
            f"{'yes' if (row.get('bridge_validation') or {}).get('final_score_target_ready') else 'no'} | "
            f"{missing} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `proposed_value_json` is a review target, not a selected runtime value.",
            "- The draft remains blocked on reviewer value selection, bounds, formula policy, applicability, and approval.",
            "- This report creates no Known draft and writes no runtime data.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-confirmation-path",
        type=Path,
        default=DEFAULT_SOURCE_CONFIRMATION_PATH,
    )
    parser.add_argument("--value-review-path", type=Path, default=DEFAULT_VALUE_REVIEW_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        source_confirmation_path=args.source_confirmation_path,
        value_review_path=args.value_review_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
