#!/usr/bin/env python3
"""Audit A-share current-MVP final-score applicability.

This report does not change the full 256-field spec. It defines the narrower
"current local MVP" final-score denominator from reproducible audit evidence:
fields count only when they can be scored today without fabricating Known data
or bypassing an approval/formula/provider gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_FIELD_CLOSURE_PATH = AUDIT_DIR / "a_share_score_field_closure_2026-06-20.json"
DEFAULT_CONVERSION_PATH = AUDIT_DIR / "a_share_spec_score_conversion_path_2026-06-20.json"
DEFAULT_EXECUTION_PATH = (
    AUDIT_DIR / "a_share_approval_materialization_batch_execution_2026-06-20.json"
)
DEFAULT_CONFIG_PATH = ROOT / "config/a_share_current_mvp_score_applicability.yaml"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_current_mvp_score_applicability_2026-06-20.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_current_mvp_score_applicability_2026-06-20.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rows_by_dp(payload: Mapping[str, Any], key: str = "rows") -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in payload.get(key) or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _summary_int(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int((payload.get("summary") or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100.0, 2) if denominator else 0.0


def _policy(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    policies = config.get("exclusion_policies") or {}
    value = policies.get(name) if isinstance(policies, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _peer_superseded_ids(config: Mapping[str, Any]) -> set[str]:
    policy = _policy(config, "valuation_peer_context_superseded")
    applies = policy.get("applies_when") if isinstance(policy, Mapping) else {}
    values = (applies or {}).get("dp_id_in") if isinstance(applies, Mapping) else []
    return {str(item) for item in values or [] if str(item)}


def _evidence_paths(reason: str, *, closure_path: Path, conversion_path: Path, execution_path: Path) -> list[str]:
    if reason == "no_valid_target_data_requires_unapproved_generation":
        return [_portable_path(closure_path)]
    if reason in {
        "formula_policy_review_required",
        "governance_suppression_verified",
        "option_universe_na_verified",
        "valuation_peer_context_superseded",
    }:
        return [_portable_path(conversion_path)]
    if reason == "current_numeric_final_score":
        return [_portable_path(closure_path), _portable_path(execution_path)]
    return [_portable_path(closure_path), _portable_path(conversion_path)]


def _row_decision(
    *,
    dp_id: str,
    closure_row: Mapping[str, Any],
    conversion_row: Mapping[str, Any],
    config: Mapping[str, Any],
    closure_path: Path,
    conversion_path: Path,
    execution_path: Path,
) -> dict[str, Any]:
    current_closed = bool(conversion_row.get("current_final_score_numeric")) or (
        closure_row.get("closure_status") == "closed_reaches_final_score"
    )
    review_status = str(conversion_row.get("review_decision_status") or "")
    conversion_status = str(conversion_row.get("conversion_path_status") or "")
    blocking_gap = closure_row.get("blocking_gap") is True
    closure_status = str(closure_row.get("closure_status") or "")
    peer_superseded = dp_id in _peer_superseded_ids(config)

    reason = "included_open_gap"
    included = True
    if current_closed:
        reason = "current_numeric_final_score"
    elif blocking_gap and closure_row.get("safe_to_upsert_without_review") is not True:
        included = False
        reason = "no_valid_target_data_requires_unapproved_generation"
    elif review_status in {
        "formula_policy_review_required",
        "governance_suppression_verified",
        "option_universe_na_verified",
    }:
        included = False
        reason = review_status
    elif peer_superseded and conversion_status == "sample_numeric_score_path_ready":
        included = False
        reason = "valuation_peer_context_superseded"

    policy = _policy(config, reason)
    return {
        "dp_id": dp_id,
        "score_target": closure_row.get("score_target") or conversion_row.get("score_target"),
        "raw_score_relevant": True,
        "current_final_score_numeric": current_closed,
        "current_mvp_denominator_included": included,
        "current_mvp_closed": included and current_closed,
        "current_mvp_actionable_gap": included and not current_closed,
        "applicability_reason": reason,
        "mvp_applicability": policy.get("mvp_applicability")
        or ("included_in_current_mvp_denominator" if included else "excluded_from_current_mvp_denominator"),
        "retained_as": policy.get("retained_as"),
        "replacement_signal": policy.get("replacement_signal"),
        "rationale": policy.get("rationale"),
        "closure_status": closure_status,
        "conversion_path_status": conversion_status,
        "review_decision_status": review_status or None,
        "repair_route": closure_row.get("repair_route"),
        "recommended_source_route": closure_row.get("recommended_source_route"),
        "runtime_valid_real_ts_count": closure_row.get("runtime_valid_real_ts_count", 0),
        "runtime_numeric_signal_ts_count": closure_row.get("runtime_numeric_signal_ts_count", 0),
        "effective_score_path_ts_count": closure_row.get("effective_score_path_ts_count", 0),
        "evidence_paths": _evidence_paths(
            reason,
            closure_path=closure_path,
            conversion_path=conversion_path,
            execution_path=execution_path,
        ),
    }


def build_report(
    *,
    field_closure_path: Path,
    conversion_path: Path,
    execution_path: Path,
    config_path: Path,
) -> dict[str, Any]:
    field_closure = _load_json(field_closure_path)
    conversion = _load_json(conversion_path)
    execution = _load_json(execution_path)
    config = _load_yaml(config_path)
    closure_by_dp = _rows_by_dp(field_closure)
    conversion_rows = [
        row
        for row in conversion.get("rows") or []
        if isinstance(row, Mapping) and row.get("score_relevant_final_target") is True
    ]

    rows = [
        _row_decision(
            dp_id=str(row.get("dp_id") or ""),
            closure_row=closure_by_dp.get(str(row.get("dp_id") or ""), {}),
            conversion_row=row,
            config=config,
            closure_path=field_closure_path,
            conversion_path=conversion_path,
            execution_path=execution_path,
        )
        for row in conversion_rows
        if str(row.get("dp_id") or "")
    ]
    reason_counts = Counter(
        str(row["applicability_reason"])
        for row in rows
        if not row["current_mvp_denominator_included"]
    )
    score_target_counts = Counter(str(row.get("score_target") or "none") for row in rows)
    included_rows = [row for row in rows if row["current_mvp_denominator_included"]]
    excluded_rows = [row for row in rows if not row["current_mvp_denominator_included"]]
    closed_rows = [row for row in included_rows if row["current_mvp_closed"]]
    actionable_rows = [row for row in included_rows if row["current_mvp_actionable_gap"]]
    raw_closed = sum(1 for row in rows if row["current_final_score_numeric"])
    raw_total = len(rows)
    execution_summary = execution.get("summary") or {}
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "field_closure_path": _portable_path(field_closure_path),
            "conversion_path": _portable_path(conversion_path),
            "execution_path": _portable_path(execution_path),
            "config_path": _portable_path(config_path),
        },
        "summary": {
            "raw_score_relevant_final_target_count": raw_total,
            "raw_current_numeric_final_score_count": raw_closed,
            "raw_current_numeric_final_score_pct": _pct(raw_closed, raw_total),
            "current_mvp_denominator_count": len(included_rows),
            "current_mvp_closed_count": len(closed_rows),
            "current_mvp_final_score_closure_pct": _pct(len(closed_rows), len(included_rows)),
            "current_mvp_excluded_count": len(excluded_rows),
            "current_mvp_actionable_gap_count": len(actionable_rows),
            "current_mvp_deviation_pct": round(100.0 - _pct(len(closed_rows), len(included_rows)), 2)
            if included_rows
            else 100.0,
            "excluded_reason_counts": dict(sorted(reason_counts.items())),
            "score_target_counts": dict(sorted(score_target_counts.items())),
            "runtime_materialization_execution_status": execution_summary.get("execution_status"),
            "runtime_materialization_post_write_verified_row_count": execution_summary.get(
                "post_write_verified_row_count", 0
            ),
            "score_mutation": "none; this audit is read-only and only defines current-MVP applicability",
        },
        "actionable_gap_rows": actionable_rows,
        "excluded_rows": excluded_rows,
        "rows": rows,
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share current-MVP score applicability audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Raw final-score closure: `{summary['raw_current_numeric_final_score_count']}` / `{summary['raw_score_relevant_final_target_count']}` ({summary['raw_current_numeric_final_score_pct']}%)",
        f"- Current-MVP final-score closure: `{summary['current_mvp_closed_count']}` / `{summary['current_mvp_denominator_count']}` ({summary['current_mvp_final_score_closure_pct']}%)",
        f"- Current-MVP actionable gap: `{summary['current_mvp_actionable_gap_count']}`",
        f"- Current-MVP deviation: `{summary['current_mvp_deviation_pct']}%`",
        f"- Excluded from current-MVP denominator: `{summary['current_mvp_excluded_count']}`",
        f"- Runtime execution status: `{summary['runtime_materialization_execution_status']}`",
        f"- Post-write verified rows: `{summary['runtime_materialization_post_write_verified_row_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Exclusion Reasons",
        "",
        "| Reason | Count |",
        "|---|---:|",
    ]
    for reason, count in summary["excluded_reason_counts"].items():
        lines.append(_md_table_row([f"`{reason}`", count]))
    lines.extend(
        [
            "",
            "## Actionable Gaps",
            "",
            "| dp_id | target | reason |",
            "|---|---|---|",
        ]
    )
    for row in report.get("actionable_gap_rows") or []:
        lines.append(
            _md_table_row(
                [
                    f"`{row['dp_id']}`",
                    f"`{row.get('score_target')}`",
                    f"`{row['applicability_reason']}`",
                ]
            )
        )
    if not report.get("actionable_gap_rows"):
        lines.append("| none | none | none |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The raw spec denominator is preserved for transparency.",
            "- The current-MVP denominator excludes only fields backed by audit evidence showing an unresolved approval, formula-policy, provider-universe, or peer-context-supersession gate.",
            "- Excluded fields stay in backlog/design scope; they are not counted as completed and are not written as fabricated Known values.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-closure-path", type=Path, default=DEFAULT_FIELD_CLOSURE_PATH)
    parser.add_argument("--conversion-path", type=Path, default=DEFAULT_CONVERSION_PATH)
    parser.add_argument("--execution-path", type=Path, default=DEFAULT_EXECUTION_PATH)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        field_closure_path=args.field_closure_path,
        conversion_path=args.conversion_path,
        execution_path=args.execution_path,
        config_path=args.config_path,
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
