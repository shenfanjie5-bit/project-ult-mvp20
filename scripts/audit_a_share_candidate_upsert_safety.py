#!/usr/bin/env python3
"""Classify A-share candidate rows by score-affecting upsert safety.

This audit is intentionally read-only.  It separates three states that are easy
to conflate:

1. candidate evidence is available,
2. a bridge-compatible payload can reach the final scoring graph, and
3. the candidate value is safe to write without review.

Current A-share candidate rows satisfy the first two states only.  This report
keeps production upserts gated until generated values are reviewed and staged.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_DRY_RUN_PATH = ROOT / "docs/audit/a_share_candidate_score_dry_run_2026-06-19.json"
DEFAULT_SHORT_REPORT_PATH = ROOT / "docs/audit/a_share_short_report_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_candidate_upsert_safety_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_candidate_upsert_safety_2026-06-19.md"

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


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _short_report_direct_hits(short_report: Mapping[str, Any]) -> int | None:
    if not short_report:
        return None
    summary = short_report.get("summary") or {}
    try:
        return int(summary.get("direct_a_share_short_report_documents") or 0)
    except (TypeError, ValueError):
        return None


def _classify_safety(
    candidate_row: Mapping[str, Any],
    dry_run_row: Mapping[str, Any] | None,
    *,
    short_report: Mapping[str, Any],
) -> dict[str, Any]:
    dp_id = str(candidate_row.get("dp_id") or "")
    score_target = str(candidate_row.get("score_target") or "")
    reasons: list[str] = []
    bridge_ready = False

    if candidate_row.get("candidate_input_ready") is not True:
        reasons.append("candidate input is not ready")
    if dry_run_row is None:
        reasons.append("candidate score dry-run row is missing")
    else:
        bridge_ready = bool(
            dry_run_row.get("bridge_signal_ready")
            and dry_run_row.get("node_emitted")
            and dry_run_row.get("final_score_target_ready")
        )
        if not dry_run_row.get("bridge_signal_ready"):
            reasons.append("dry-run did not produce a realtime signal")
        if not dry_run_row.get("node_emitted"):
            reasons.append("dry-run did not emit a realtime scoring node")
        if not dry_run_row.get("final_score_target_ready"):
            reasons.append("dry-run did not reach a final score target")
    if score_target in FINAL_SCORE_EXCLUDED_TARGETS:
        reasons.append(f"score target `{score_target}` is not a final scoring target")

    if reasons:
        return {
            "upsert_safety_class": "blocked",
            "review_gated": False,
            "bridge_ready": bridge_ready,
            "safe_to_upsert_without_review": False,
            "upsert_action": "blocked_no_upsert",
            "value_validity_status": "blocked_before_candidate_value_review",
            "reason": "; ".join(reasons),
        }

    if dp_id == "L9.media.short_report":
        direct_hits = _short_report_direct_hits(short_report)
        if direct_hits == 0:
            return {
                "upsert_safety_class": "neutral_candidate_review_required",
                "review_gated": True,
                "bridge_ready": True,
                "safe_to_upsert_without_review": False,
                "upsert_action": "review_neutral_or_unknown_then_stage",
                "value_validity_status": "absence_evidence_neutral_only",
                "reason": (
                    "dedicated short-report scan found 0 direct A-share hits; "
                    "active events must stay neutral/Unknown unless direct evidence appears"
                ),
            }
        return {
            "upsert_safety_class": "review_required",
            "review_gated": True,
            "bridge_ready": True,
            "safe_to_upsert_without_review": False,
            "upsert_action": "review_then_stage",
            "value_validity_status": "direct_event_evidence_requires_review",
            "reason": "direct A-share short-report evidence must be reviewed before it can affect score",
        }

    if dp_id == "L7.trade.gamma":
        return {
            "upsert_safety_class": "not_applicable_candidate_review_required",
            "review_gated": True,
            "bridge_ready": True,
            "safe_to_upsert_without_review": False,
            "upsert_action": "review_not_applicable_then_stage",
            "value_validity_status": "applicability_neutral_only",
            "reason": (
                "A-share single-stock gamma is NotApplicable/neutral unless direct "
                "listed-option or explicit proxy evidence is reviewed"
            ),
        }

    route = str(candidate_row.get("recommended_source_route") or "")
    candidate_status = str(candidate_row.get("candidate_status") or "")
    if route == "manual_design_review" or candidate_status == "ready_for_manual_design_candidate":
        reason = "manual-design candidate policy exists, but the generated value and assumptions remain unreviewed"
    elif route == "event_llm_from_runtime_news":
        reason = "runtime event evidence exists, but event classification and value polarity remain unreviewed"
    elif route == "local_llm_closed_loop":
        reason = "runtime dependencies exist, but local candidate inference output remains unreviewed"
    else:
        reason = "candidate evidence and bridge contract are ready, but the candidate value remains unreviewed"

    return {
        "upsert_safety_class": "review_required",
        "review_gated": True,
        "bridge_ready": True,
        "safe_to_upsert_without_review": False,
        "upsert_action": "review_then_stage",
        "value_validity_status": "unreviewed_candidate_contract_only",
        "reason": reason,
    }


def build_report(
    candidate_path: Path,
    dry_run_path: Path,
    short_report_path: Path | None = DEFAULT_SHORT_REPORT_PATH,
) -> dict[str, Any]:
    started = time.time()
    candidate = _load_json(candidate_path)
    dry_run = _load_json(dry_run_path)
    short_report = _load_json(short_report_path)
    dry_rows = _rows_by_dp(dry_run)
    rows: list[dict[str, Any]] = []

    for candidate_row in candidate.get("rows") or []:
        if not isinstance(candidate_row, dict):
            continue
        dp_id = str(candidate_row.get("dp_id") or "")
        dry_row = dry_rows.get(dp_id)
        safety = _classify_safety(
            candidate_row,
            dry_row,
            short_report=short_report,
        )
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": candidate_row.get("score_target"),
                "candidate_status": candidate_row.get("candidate_status"),
                "recommended_source_route": candidate_row.get("recommended_source_route"),
                "candidate_input_ready": candidate_row.get("candidate_input_ready") is True,
                "dry_run_present": dry_row is not None,
                "bridge_signal_ready": bool(dry_row and dry_row.get("bridge_signal_ready")),
                "node_emitted": bool(dry_row and dry_row.get("node_emitted")),
                "final_score_target_ready": bool(
                    dry_row and dry_row.get("final_score_target_ready")
                ),
                **safety,
            }
        )

    class_counts = Counter(str(row["upsert_safety_class"]) for row in rows)
    action_counts = Counter(str(row["upsert_action"]) for row in rows)
    blocked_dp_ids = [
        str(row["dp_id"]) for row in rows if row["upsert_safety_class"] == "blocked"
    ]
    review_gated_count = sum(1 for row in rows if row["review_gated"])
    bridge_ready_count = sum(1 for row in rows if row["bridge_ready"])
    safe_to_upsert_count = sum(1 for row in rows if row["safe_to_upsert_without_review"])

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "candidate_path": _portable_path(candidate_path),
        "dry_run_path": _portable_path(dry_run_path),
        "short_report_path": (
            _portable_path(short_report_path) if short_report_path is not None else None
        ),
        "summary": {
            "candidate_rows_checked": len(rows),
            "candidate_input_ready_count": sum(1 for row in rows if row["candidate_input_ready"]),
            "bridge_ready_count": bridge_ready_count,
            "review_gated_count": review_gated_count,
            "blocked_count": len(blocked_dp_ids),
            "blocked_dp_ids": blocked_dp_ids,
            "safe_to_upsert_without_review_count": safe_to_upsert_count,
            "upsert_safety_class_counts": dict(sorted(class_counts.items())),
            "upsert_action_counts": dict(sorted(action_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
            "policy": (
                "Candidate rows may only be written to a staging/review path after "
                "candidate generation and review. Production score-affecting upserts "
                "remain disabled for unreviewed candidates."
            ),
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share candidate upsert safety",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidate rows checked: `{summary['candidate_rows_checked']}`",
        f"- Candidate inputs ready: `{summary['candidate_input_ready_count']}`",
        f"- Bridge ready: `{summary['bridge_ready_count']}`",
        f"- Review-gated: `{summary['review_gated_count']}`",
        f"- Blocked: `{summary['blocked_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Safety Class Counts",
        "",
        "| Safety class | Count |",
        "|---|---:|",
    ]
    for name, count in summary["upsert_safety_class_counts"].items():
        lines.append(f"| `{name}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | route | candidate status | bridge | safety class | action | reason |",
            "|---|---|---|---:|---|---|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['recommended_source_route']}` | "
            f"`{row['candidate_status']}` | "
            f"{'yes' if row['bridge_ready'] else 'no'} | "
            f"`{row['upsert_safety_class']}` | "
            f"`{row['upsert_action']}` | "
            f"{row['reason']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Bridge-ready rows prove the payload shape can reach scoring; they do not prove candidate values are correct.",
            "- All non-blocked rows remain review-gated and staging-only until generated values, assumptions, and evidence refs are reviewed.",
            "- `safe_to_upsert_without_review` must stay 0 for the current A-share candidate set.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--dry-run-path", type=Path, default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--short-report-path", type=Path, default=DEFAULT_SHORT_REPORT_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.candidate_path, args.dry_run_path, args.short_report_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
