#!/usr/bin/env python3
"""Prepare A-share bulk-review approval candidates.

The output is a reviewer convenience bundle. Approval records are deliberately
drafts with blank reviewer/status/timestamp fields and cannot pass the runtime
approval gate until a reviewer fills them after review.
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
DEFAULT_RISK_REVIEW_PATH = ROOT / "docs/audit/a_share_approval_packet_risk_review_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_bulk_review_approval_candidates_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_bulk_review_approval_candidates_2026-06-19.md"


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


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _approval_draft(dp_id: str, payload_sha256: str) -> dict[str, Any]:
    return {
        "approval_id": "",
        "dp_id": dp_id,
        "approval_status": "",
        "approval_scope": "runtime_write",
        "reviewer": "",
        "approved_at": "",
        "payload_sha256": payload_sha256,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }


def _draft_errors(draft: Mapping[str, Any], *, dp_id: str, payload_sha256: str) -> list[str]:
    errors: list[str] = []
    expected = {
        "approval_id": "",
        "dp_id": dp_id,
        "approval_status": "",
        "approval_scope": "runtime_write",
        "reviewer": "",
        "approved_at": "",
        "payload_sha256": payload_sha256,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }
    for key, expected_value in expected.items():
        if draft.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    return errors


def _candidate_row(packet: Mapping[str, Any], risk: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(packet.get("dp_id") or "")
    payload_sha256 = str(packet.get("payload_sha256") or "")
    draft = _approval_draft(dp_id, payload_sha256)
    return {
        "dp_id": dp_id,
        "score_target": packet.get("score_target"),
        "source_kind": packet.get("source_kind"),
        "source_report": packet.get("source_report"),
        "source_dependencies": packet.get("source_dependencies") or [],
        "data_status": packet.get("data_status"),
        "payload_sha256": payload_sha256,
        "confidence": packet.get("confidence"),
        "impact_value": risk.get("impact_value"),
        "value_json": packet.get("value_json") or {},
        "evidence_refs": packet.get("evidence_refs") or [],
        "rationale": packet.get("rationale"),
        "risk_class": risk.get("risk_class"),
        "risk_reasons": risk.get("risk_reasons") or [],
        "approval_record_draft": draft,
        "approval_record_draft_contract_valid": not _draft_errors(
            draft, dp_id=dp_id, payload_sha256=payload_sha256
        ),
        "approval_record_draft_validation_errors": _draft_errors(
            draft, dp_id=dp_id, payload_sha256=payload_sha256
        ),
        "ready_for_bulk_review": risk.get("risk_class") == "bulk_structured_review_candidate",
        "requires_sample_check": (
            risk.get("risk_class") == "borderline_structured_text_review_candidate"
        ),
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, packets_path: Path, risk_review_path: Path) -> dict[str, Any]:
    started = time.time()
    packets = _load_json(packets_path)
    risk_review = _load_json(risk_review_path)
    packet_by_dp = _rows_by_dp(packets)
    candidate_risk_classes = {
        "bulk_structured_review_candidate",
        "borderline_structured_text_review_candidate",
    }
    rows = [
        _candidate_row(packet_by_dp[str(risk.get("dp_id") or "")], risk)
        for risk in risk_review.get("rows") or []
        if isinstance(risk, Mapping)
        and risk.get("risk_class") in candidate_risk_classes
        and str(risk.get("dp_id") or "") in packet_by_dp
    ]
    rows.sort(
        key=lambda row: (
            1 if row.get("requires_sample_check") else 0,
            str(row.get("score_target") or ""),
            str(row.get("dp_id") or ""),
        )
    )
    risk_counts = Counter(str(row.get("risk_class") or "") for row in rows)
    source_counts = Counter(str(row.get("source_kind") or "") for row in rows)
    invalid_drafts = [
        row
        for row in rows
        if not row.get("approval_record_draft_contract_valid")
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "packets_path": _portable_path(packets_path),
            "risk_review_path": _portable_path(risk_review_path),
        },
        "summary": {
            "candidate_count": len(rows),
            "strict_bulk_candidate_count": risk_counts.get(
                "bulk_structured_review_candidate", 0
            ),
            "borderline_sample_check_candidate_count": risk_counts.get(
                "borderline_structured_text_review_candidate", 0
            ),
            "approval_record_draft_count": len(rows),
            "approval_record_draft_contract_valid_count": len(rows)
            - len(invalid_drafts),
            "approval_record_draft_contract_invalid_count": len(invalid_drafts),
            "approval_record_draft_contract_invalid_dp_ids": [
                str(row.get("dp_id") or "") for row in invalid_drafts
            ],
            "auto_approval_allowed_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "risk_class_counts": dict(sorted(risk_counts.items())),
            "source_kind_counts": dict(sorted(source_counts.items())),
            "candidate_dp_ids": [str(row.get("dp_id") or "") for row in rows],
            "score_mutation": "none; draft approvals only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share bulk-review approval candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidates: `{summary['candidate_count']}`",
        f"- Strict bulk candidates: `{summary['strict_bulk_candidate_count']}`",
        f"- Borderline sample-check candidates: `{summary['borderline_sample_check_candidate_count']}`",
        f"- Approval drafts: `{summary['approval_record_draft_count']}`",
        f"- Approval draft contracts valid: `{summary['approval_record_draft_contract_valid_count']}`",
        f"- Approval draft contracts invalid: `{summary['approval_record_draft_contract_invalid_count']}`",
        f"- Auto approvals allowed: `{summary['auto_approval_allowed_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Candidates",
        "",
        "| dp_id | source | confidence | impact | risk class | draft valid |",
        "|---|---|---:|---:|---|---:|",
    ]
    for row in report["rows"]:
        impact = row.get("impact_value")
        impact_text = "" if impact is None else f"{impact:.6g}"
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('source_kind')}` | "
            f"{row.get('confidence')} | "
            f"{impact_text} | "
            f"`{row.get('risk_class')}` | "
            f"{'yes' if row.get('approval_record_draft_contract_valid') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Draft records are intentionally incomplete and cannot pass the approval gate.",
            "- Strict bulk candidates may be reviewed together, but the reviewer must still fill approval identity, timestamp, status, and risk acknowledgement.",
            "- Borderline sample-check candidates need source-text sampling before approval.",
            "- The report does not write runtime values or change scores.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets-path", type=Path, default=DEFAULT_PACKETS_PATH)
    parser.add_argument("--risk-review-path", type=Path, default=DEFAULT_RISK_REVIEW_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        packets_path=args.packets_path,
        risk_review_path=args.risk_review_path,
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
