#!/usr/bin/env python3
"""A-share score-field closure audit.

This read-only audit answers three practical questions for every spec field:

1. Is there real A-share runtime/overlay information for the field?
2. Can the current scoring bridge convert that information into a numeric
   signal?
3. Does the signal reach the final score path, or what exact repair route
   remains?

It intentionally consumes existing evidence files instead of writing
``runtime/hot.sqlite``.  The candidate-evidence report is treated as candidate
input only; it is not counted as score completion.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACE_PATH = ROOT / "docs/audit/a_share_score_trace_2026-06-18.json"
DEFAULT_GAP_PATH = ROOT / "docs/audit/a_share_score_gap_priority_2026-06-18.json"
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_READINESS_PATH = ROOT / "docs/audit/a_share_l0_source_readiness_2026-06-19.json"
DEFAULT_SPEC_PATH = ROOT / "config/data_point_roles.yaml"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_score_field_closure_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_score_field_closure_2026-06-19.md"

NON_FINAL_TARGETS = {
    "none",
    "audit_only",
    "display_only",
    "parent_score",
    "node_score",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _summary_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = (payload.get("summary") or {}).get(key, [])
    return [str(x) for x in value] if isinstance(value, list) else []


def _summary_int(payload: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = (payload.get("summary") or {}).get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _score_relevant(row: Mapping[str, Any]) -> bool:
    return bool(row.get("participates_in_score")) and str(row.get("score_target")) not in NON_FINAL_TARGETS


def _closure_status(row: Mapping[str, Any]) -> str:
    """Classify a trace row by the actual production score gates."""

    if not row.get("participates_in_score"):
        return "non_scoring_spec"
    if not _score_relevant(row):
        return "non_final_score_target"
    if int(row.get("effective_score_path_ts_count") or 0) > 0:
        return "closed_reaches_final_score"
    if int(row.get("runtime_valid_real_ts_count") or 0) > 0:
        if int(row.get("runtime_numeric_signal_ts_count") or 0) == 0:
            return "valid_real_but_formula_unmapped"
        if int(row.get("runtime_blocked_by_overlay_without_score_ts_count") or 0) > 0:
            return "numeric_runtime_blocked_by_non_scoring_overlay"
        if int(row.get("runtime_numeric_blocked_by_dedup_ts_count") or 0) > 0:
            return "numeric_runtime_blocked_by_dedup"
        return "numeric_runtime_not_emitted"
    if int(row.get("overlay_present_ts_count") or 0) > 0:
        return "overlay_only_no_score_candidate"
    return "no_valid_a_share_target_data"


def _repair_route(
    dp_id: str,
    *,
    blocking_ids: set[str],
    candidate_by_dp: Mapping[str, Mapping[str, Any]],
    gap_row_by_dp: Mapping[str, Mapping[str, Any]],
) -> str:
    if dp_id not in blocking_ids:
        return "none"
    candidate = candidate_by_dp.get(dp_id)
    if candidate:
        status = str(candidate.get("candidate_status") or "")
        route = str(candidate.get("recommended_source_route") or "")
        if status.startswith("ready_for_"):
            return f"candidate_generation_required:{route}"
        return f"{status}:{route}"
    gap_row = gap_row_by_dp.get(dp_id) or {}
    return str(gap_row.get("recommended_route") or gap_row.get("route") or "review_required")


def build_report(
    *,
    trace_path: Path,
    gap_path: Path,
    candidate_path: Path,
    readiness_path: Path,
    spec_path: Path,
) -> dict[str, Any]:
    trace = _load_json(trace_path)
    gap = _load_json(gap_path)
    candidate = _load_json(candidate_path)
    readiness = _load_json(readiness_path)
    spec = _load_yaml(spec_path)

    spec_points = spec.get("data_points") or {}
    configured_spec_total = int(spec.get("spec_total_dp_ids") or 0)
    runtime_spec_total = _summary_int(trace, "spec_total")

    blocking_ids = set(_summary_list(gap, "score_completion_blocking_gap_dp_ids"))
    candidate_rows = [r for r in candidate.get("rows") or [] if isinstance(r, Mapping)]
    candidate_by_dp = {str(r.get("dp_id")): r for r in candidate_rows}
    readiness_rows = [r for r in readiness.get("rows") or [] if isinstance(r, Mapping)]
    readiness_by_dp = {str(r.get("dp_id")): r for r in readiness_rows}
    gap_rows = [r for r in gap.get("participating_gap_rows") or [] if isinstance(r, Mapping)]
    gap_row_by_dp = {str(r.get("dp_id")): r for r in gap_rows}

    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    repair_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    score_target_counts: Counter[str] = Counter()

    for raw in trace.get("field_rows") or []:
        if not isinstance(raw, Mapping):
            continue
        dp_id = str(raw.get("dp_id") or "")
        spec_rule = spec_points.get(dp_id) or {}
        ready = readiness_by_dp.get(dp_id) or {}
        closure_status = _closure_status(raw)
        blocking_gap = (
            dp_id in blocking_ids
            and closure_status != "closed_reaches_final_score"
        )
        cand = (candidate_by_dp.get(dp_id) or {}) if blocking_gap else {}
        repair = _repair_route(
            dp_id,
            blocking_ids={dp_id} if blocking_gap else set(),
            candidate_by_dp=candidate_by_dp,
            gap_row_by_dp=gap_row_by_dp,
        )
        status_counts[closure_status] += 1
        repair_counts[repair] += 1
        route = str(cand.get("recommended_source_route") or ready.get("recommended_source_route") or "")
        if route and blocking_gap:
            route_counts[route] += 1
        score_target_counts[str(raw.get("score_target") or "none")] += 1

        rows.append(
            {
                "dp_id": dp_id,
                "field_role": raw.get("field_role"),
                "score_target": raw.get("score_target"),
                "participates_in_score": bool(raw.get("participates_in_score")),
                "score_relevant": _score_relevant(raw),
                "source_status": spec_rule.get("source_status") or raw.get("source_status"),
                "calculation_type": spec_rule.get("calculation_type") or raw.get("calculation_type"),
                "aggregation_policy": spec_rule.get("aggregation_policy") or raw.get("aggregation_policy"),
                "runtime_valid_real_ts_count": raw.get("runtime_valid_real_ts_count", 0),
                "runtime_numeric_signal_ts_count": raw.get("runtime_numeric_signal_ts_count", 0),
                "runtime_bridge_emitted_ts_count": raw.get("runtime_bridge_emitted_ts_count", 0),
                "overlay_score_candidate_ts_count": raw.get("overlay_score_candidate_ts_count", 0),
                "effective_score_path_ts_count": raw.get("effective_score_path_ts_count", 0),
                "runtime_source_categories": raw.get("runtime_source_categories") or {},
                "statuses": raw.get("statuses") or {},
                "closure_status": closure_status,
                "blocking_gap": blocking_gap,
                "repair_route": repair,
                "candidate_status": cand.get("candidate_status"),
                "candidate_input_ready": cand.get("candidate_input_ready"),
                "recommended_source_route": route or None,
                "source_dependencies": cand.get("source_dependencies") or ready.get("source_dependencies") or [],
                "sample_signals": raw.get("sample_signals") or [],
                "sample_values": raw.get("sample_values") or [],
            }
        )

    blocking_rows = [row for row in rows if row["blocking_gap"]]
    score_relevant_rows = [row for row in rows if row["score_relevant"]]
    closed_rows = [row for row in score_relevant_rows if row["closure_status"] == "closed_reaches_final_score"]
    ready_blockers = [row for row in blocking_rows if row.get("candidate_input_ready") is True]
    not_ready_blockers = [row for row in blocking_rows if row.get("candidate_input_ready") is not True]

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "trace_path": _portable_path(trace_path),
            "gap_path": _portable_path(gap_path),
            "candidate_path": _portable_path(candidate_path),
            "readiness_path": _portable_path(readiness_path),
            "spec_path": _portable_path(spec_path),
        },
        "summary": {
            "configured_spec_total_dp_ids": configured_spec_total,
            "runtime_trace_spec_total_dp_ids": runtime_spec_total,
            "spec_total_matches_runtime": configured_spec_total == runtime_spec_total,
            "field_row_count": len(rows),
            "participating_spec_dp_ids": _summary_int(trace, "participating_spec_dp_ids"),
            "score_relevant_spec_dp_ids": _summary_int(trace, "score_relevant_spec_dp_ids"),
            "closed_score_relevant_dp_ids": len(closed_rows),
            "effective_score_path_dp_ids": _summary_int(trace, "effective_score_path_dp_ids"),
            "blocking_gap_dp_ids": len(blocking_rows),
            "candidate_ready_blocking_gap_dp_ids": len(ready_blockers),
            "candidate_not_ready_blocking_gap_dp_ids": len(not_ready_blockers),
            "safe_to_upsert_without_review_count": _summary_int(candidate, "safe_to_upsert_without_review_count"),
            "direct_structured_tushare_remaining": _summary_int(readiness, "direct_structured_tushare_remaining"),
            "status_counts": dict(sorted(status_counts.items())),
            "repair_route_counts": dict(sorted(repair_counts.items())),
            "recommended_source_route_counts": dict(sorted(route_counts.items())),
            "score_target_counts": dict(sorted(score_target_counts.items())),
            "score_mutation": "none; audit is read-only",
        },
        "blocking_rows": blocking_rows,
        "rows": rows,
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(v) for v in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share score-field closure audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        f"- Spec total config/runtime: `{summary['configured_spec_total_dp_ids']}` / `{summary['runtime_trace_spec_total_dp_ids']}`",
        f"- Spec total matches runtime: `{summary['spec_total_matches_runtime']}`",
        f"- Score-relevant closed fields: `{summary['closed_score_relevant_dp_ids']}` / `{summary['score_relevant_spec_dp_ids']}`",
        f"- Blocking gaps: `{summary['blocking_gap_dp_ids']}`",
        f"- Candidate-ready blockers: `{summary['candidate_ready_blocking_gap_dp_ids']}`",
        f"- Candidate-not-ready blockers: `{summary['candidate_not_ready_blocking_gap_dp_ids']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Direct structured Tushare remaining: `{summary['direct_structured_tushare_remaining']}`",
        "",
        "## Closure Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(_md_table_row([f"`{status}`", count]))

    lines.extend(
        [
            "",
            "## Blocking Gaps",
            "",
            "| dp_id | target | closure | candidate | route | dependencies | repair |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in report["blocking_rows"]:
        deps = row.get("source_dependencies") or []
        lines.append(
            _md_table_row(
                [
                    f"`{row['dp_id']}`",
                    f"`{row['score_target']}`",
                    f"`{row['closure_status']}`",
                    f"`{row.get('candidate_status') or '-'}`",
                    f"`{row.get('recommended_source_route') or '-'}`",
                    ", ".join(f"`{dep}`" for dep in deps) or "-",
                    f"`{row['repair_route']}`",
                ]
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A field is counted as closed only when current evidence reaches the production score path: participating spec, Known/Proxy non-mock runtime or score-capable overlay, numeric conversion, and final score sink.",
            "- Candidate-ready means dependency evidence exists; it is not treated as score completion because no reviewed target runtime row has been written.",
            f"- Existing Tushare/AKShare rows currently support candidate generation for {summary['candidate_ready_blocking_gap_dp_ids']} blockers, but direct structured Tushare gaps are already exhausted.",
            "- The remaining work is target-value generation/review, then validating that regenerated rows move from `no_valid_a_share_target_data` to `closed_reaches_final_score` in this audit.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-path", type=Path, default=DEFAULT_TRACE_PATH)
    parser.add_argument("--gap-path", type=Path, default=DEFAULT_GAP_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--spec-path", type=Path, default=DEFAULT_SPEC_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        trace_path=args.trace_path,
        gap_path=args.gap_path,
        candidate_path=args.candidate_path,
        readiness_path=args.readiness_path,
        spec_path=args.spec_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
