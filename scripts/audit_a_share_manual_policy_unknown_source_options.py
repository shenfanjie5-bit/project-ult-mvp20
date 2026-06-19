#!/usr/bin/env python3
"""Classify source options for manual-policy A-share Unknown drafts.

The current manual-policy pilot emits ``L6.mult.dcf`` as a review-only Known
standard-assumption draft. This read-only audit is now the fallback report for
manual-policy rows that still arrive as Unknown, recording dependency evidence
and review inputs that would block a Known packet.
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

from scripts.audit_a_share_manual_policy_draft_candidates import (
    DEFAULT_CANDIDATE_PATH,
    ROOT,
    _candidate_rows_by_dp,
    _load_json,
    _portable_path,
)


DEFAULT_MANUAL_POLICY_PATH = (
    ROOT / "docs/audit/a_share_manual_policy_draft_candidates_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_manual_policy_unknown_source_options_2026-06-19.md"
)


SOURCE_OPTION_POLICIES: dict[str, dict[str, Any]] = {
    "L6.mult.dcf": {
        "resolution_status": "requires_reviewed_dcf_assumptions",
        "assumption_review_required": True,
        "reviewed_policy_required": True,
        "dependency_limit": (
            "Cash flow, growth, rates, sensitivity, and market-cap/FCF evidence are present, "
            "but they do not define reviewed discount rate, terminal growth, forecast horizon, "
            "or normalized FCF assumptions."
        ),
        "required_assumptions": [
            "discount_rate",
            "terminal_growth",
            "forecast_horizon",
            "normalized_fcf",
        ],
        "required_evidence": [
            "reviewed cost-of-capital or discount-rate basis",
            "reviewed terminal-growth assumption",
            "reviewed explicit forecast horizon",
            "reviewed normalized FCF basis and one-off adjustment policy",
        ],
        "candidate_source_routes": [
            "use current FCF, revenue-growth, rate, sensitivity, and mcap/FCF dependencies as the evidence pack",
            "derive assumptions from reviewed analyst forecasts or company guidance where available",
            "apply industry valuation-weight context only after explicit reviewer approval",
            "keep FMP DCF evidence as US-capability context unless an A-share governed DCF source is wired",
        ],
    },
}


def _unknown_manual_policy_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        payload = row.get("draft_payload")
        if isinstance(payload, Mapping) and payload.get("data_status") == "Unknown":
            rows.append(row)
    return rows


def _payload_value(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("draft_payload")
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get("value_json")
    return value if isinstance(value, Mapping) else {}


def _dependency_records(candidate_row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(candidate_row, Mapping):
        return []
    candidate_input = candidate_row.get("candidate_input")
    if not isinstance(candidate_input, Mapping):
        return []
    dependency_evidence = candidate_row.get("dependency_evidence")
    if not isinstance(dependency_evidence, Mapping):
        dependency_evidence = {}

    records: list[dict[str, Any]] = []
    for dep in candidate_input.get("dependencies") or []:
        if not isinstance(dep, Mapping):
            continue
        dep_id = str(dep.get("dp_id") or "")
        rich = dependency_evidence.get(dep_id)
        if not isinstance(rich, Mapping):
            rich = {}
        sample_keys: list[str] = []
        for sample in dep.get("sample_rows") or []:
            if not isinstance(sample, Mapping):
                continue
            compact = sample.get("value_json_compact")
            if not isinstance(compact, Mapping):
                continue
            for key in compact:
                if str(key) not in sample_keys:
                    sample_keys.append(str(key))
        records.append(
            {
                "dp_id": dep_id,
                "row_count": int(dep.get("row_count") or rich.get("row_count") or 0),
                "known_count": int(dep.get("known_count") or rich.get("known_count") or 0),
                "ts_code_count": int(dep.get("ts_code_count") or rich.get("ts_code_count") or 0),
                "namespace_counts": dict(dep.get("namespace_counts") or rich.get("namespace_counts") or {}),
                "source_counts": dict(rich.get("source_counts") or {}),
                "latest_updated_at_iso": dep.get("latest_updated_at_iso")
                or rich.get("latest_updated_at_iso"),
                "sample_value_keys": sample_keys,
            }
        )
    return records


def build_report(manual_policy_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    manual_policy = _load_json(manual_policy_path)
    candidates = _candidate_rows_by_dp(_load_json(candidate_path))
    rows: list[dict[str, Any]] = []

    for source_row in _unknown_manual_policy_rows(manual_policy):
        dp_id = str(source_row.get("dp_id") or "")
        score_target = str(source_row.get("score_target") or "")
        policy = SOURCE_OPTION_POLICIES.get(dp_id, {})
        candidate_row = candidates.get(dp_id)
        dependencies = _dependency_records(candidate_row)
        dependency_pack_ready = bool(dependencies) and all(
            dep["row_count"] > 0 and dep["known_count"] > 0 for dep in dependencies
        )
        value_json = _payload_value(source_row)
        required_assumptions = list(
            value_json.get("required_assumptions") or policy.get("required_assumptions") or []
        )
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "draft_status": source_row.get("draft_status"),
                "manual_policy_name": source_row.get("manual_policy_name"),
                "blocked_reason": value_json.get("blocked_reason"),
                "candidate_status": candidate_row.get("candidate_status") if candidate_row else None,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "dependency_pack_ready": dependency_pack_ready,
                "dependency_summary": dependencies,
                "direct_reviewed_assumption_ready": False,
                "direct_reviewed_assumption_reason": (
                    "Current candidate evidence contains inputs for a DCF review, but no reviewed "
                    "discount-rate, terminal-growth, forecast-horizon, or normalized-FCF assumption set."
                ),
                "dependency_limit": policy.get(
                    "dependency_limit",
                    "No reviewed manual-policy source-option policy is defined.",
                ),
                "required_assumptions": required_assumptions,
                "required_evidence": list(policy.get("required_evidence") or []),
                "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
                "resolution_status": policy.get(
                    "resolution_status",
                    "requires_reviewed_manual_policy_assumptions",
                ),
                "assumption_review_required": bool(policy.get("assumption_review_required")),
                "reviewed_policy_required": bool(policy.get("reviewed_policy_required")),
                "auto_known_candidate_allowed": False,
                "review_required": True,
                "safe_to_upsert_without_review": False,
                "production_write_allowed": False,
            }
        )

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["resolution_status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "manual_policy_path": _portable_path(manual_policy_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "unknown_manual_policy_count": len(rows),
            "dependency_pack_ready_count": sum(
                1 for row in rows if row["dependency_pack_ready"]
            ),
            "direct_reviewed_assumption_ready_count": sum(
                1 for row in rows if row["direct_reviewed_assumption_ready"]
            ),
            "required_assumption_count": sum(
                len(row["required_assumptions"]) for row in rows
            ),
            "candidate_requires_assumption_review_count": sum(
                1 for row in rows if row["assumption_review_required"]
            ),
            "candidate_requires_review_policy_count": sum(
                1 for row in rows if row["reviewed_policy_required"]
            ),
            "auto_known_candidate_count": sum(
                1 for row in rows if row["auto_known_candidate_allowed"]
            ),
            "review_required_count": sum(1 for row in rows if row["review_required"]),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "resolution_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share manual-policy Unknown source options",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown manual-policy rows: `{summary['unknown_manual_policy_count']}`",
        f"- Dependency packs ready: `{summary['dependency_pack_ready_count']}`",
        f"- Direct reviewed-assumption-ready rows: `{summary['direct_reviewed_assumption_ready_count']}`",
        f"- Required assumptions: `{summary['required_assumption_count']}`",
        f"- Assumption review required: `{summary['candidate_requires_assumption_review_count']}`",
        f"- Reviewed policy required: `{summary['candidate_requires_review_policy_count']}`",
        f"- Auto Known candidates allowed: `{summary['auto_known_candidate_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Resolution Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["resolution_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | dependency pack | reviewed assumptions ready | required assumptions | status | production write |",
            "|---|---:|---:|---:|---|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['dependency_pack_ready'] else 'no'} | "
            f"{'yes' if row['direct_reviewed_assumption_ready'] else 'no'} | "
            f"{len(row['required_assumptions'])} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(["", "## Interpretation", ""])
    if summary["unknown_manual_policy_count"] == 0:
        lines.extend(
            [
                "- No manual-policy Unknown source-option rows remain in the current A-share review queue.",
                "- `L6.mult.dcf` is handled by the manual-policy draft candidate audit as a review-only Known standard-assumption DCF packet.",
                "- Production score-affecting writes remain disabled until approval records are present.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Current A-share evidence can package manual-policy review inputs, but these rows still lack reviewed assumptions or policy approval.",
                "- Any `L6.mult.dcf` row that appears here must remain Unknown until discount rate, terminal growth, forecast horizon, and normalized FCF are reviewed.",
                "- FMP DCF capability is useful provider context, but it is not a governed A-share runtime value by itself.",
                "- Production score-affecting writes remain disabled.",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manual-policy-path",
        type=Path,
        default=DEFAULT_MANUAL_POLICY_PATH,
    )
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.manual_policy_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
