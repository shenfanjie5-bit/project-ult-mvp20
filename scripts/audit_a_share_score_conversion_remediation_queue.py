#!/usr/bin/env python3
"""Classify unresolved A-share spec score-conversion fields into next actions.

This audit is intentionally read-only. It starts from the conversion-path audit
and the score-gap-priority audit, then explains whether each unresolved
score-relevant field can be fixed by a safe formula change, needs scoring-policy
review, should remain suppressed/deduplicated, or needs a real source universe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_CONVERSION_PATH = AUDIT_DIR / "a_share_spec_score_conversion_path_2026-06-19.json"
DEFAULT_PRIORITY_PATH = AUDIT_DIR / "a_share_score_gap_priority_2026-06-18.json"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_score_conversion_remediation_queue_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_score_conversion_remediation_queue_2026-06-19.md"


REMEDIATION_CLASS_BY_BUCKET = {
    "design_review": "formula_policy_required",
    "intentional_governance": "intentional_governance_or_duplicate",
    "universe_not_applicable": "missing_or_not_applicable_source",
}

NEXT_ACTION_BY_CLASS = {
    "formula_policy_required": "define_reviewed_policy_or_peer_context_before_formula",
    "intentional_governance_or_duplicate": "verify_replacement_or_keep_suppressed",
    "missing_or_not_applicable_source": "obtain_real_source_universe_or_keep_na",
    "manual_review_required": "manual_triage_required",
}


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


def _rows_by_dp(rows: Any) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _priority_rows_by_dp(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for key in ("participating_gap_rows", "formula_gap_rows"):
        for dp_id, row in _rows_by_dp(payload.get(key)).items():
            out.setdefault(dp_id, row)
    return out


def _remediation_class(
    conversion_row: Mapping[str, Any],
    priority_row: Mapping[str, Any] | None,
) -> str:
    if priority_row is not None:
        bucket = str(priority_row.get("gap_bucket") or "")
        if bucket in REMEDIATION_CLASS_BY_BUCKET:
            return REMEDIATION_CLASS_BY_BUCKET[bucket]
    if conversion_row.get("conversion_path_status") == "no_current_numeric_input":
        return "missing_or_not_applicable_source"
    return "manual_review_required"


def _safe_formula_now(
    remediation_class: str,
    priority_row: Mapping[str, Any] | None,
) -> bool:
    if remediation_class != "manual_review_required":
        return False
    return bool(priority_row and priority_row.get("blocking_gap"))


def _source_categories(priority_row: Mapping[str, Any] | None) -> dict[str, int]:
    cats = priority_row.get("runtime_source_categories") if priority_row else {}
    if not isinstance(cats, Mapping):
        return {}
    out: dict[str, int] = {}
    for key, value in cats.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _join_sources(priority_row: Mapping[str, Any] | None) -> str:
    sources = priority_row.get("sources") if priority_row else {}
    if not isinstance(sources, Mapping) or not sources:
        return ""
    return ", ".join(f"{key}:{value}" for key, value in list(sources.items())[:4])


def build_report(
    *,
    conversion_path: Path,
    priority_path: Path,
) -> dict[str, Any]:
    conversion = _load_json(conversion_path)
    priority = _load_json(priority_path)
    priority_by_dp = _priority_rows_by_dp(priority)

    unresolved_rows = [
        row
        for row in conversion.get("blocked_score_relevant_rows") or []
        if isinstance(row, Mapping)
    ]

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    next_action_counts: Counter[str] = Counter()
    source_category_counts: Counter[str] = Counter()
    source_state_counts: Counter[str] = Counter()
    missing_priority_dp_ids: list[str] = []

    for row in unresolved_rows:
        dp_id = str(row.get("dp_id") or "")
        priority_row = priority_by_dp.get(dp_id)
        if priority_row is None:
            missing_priority_dp_ids.append(dp_id)
        remediation_class = _remediation_class(row, priority_row)
        next_action = NEXT_ACTION_BY_CLASS[remediation_class]
        safe_formula_now = _safe_formula_now(remediation_class, priority_row)
        categories = _source_categories(priority_row)
        for category, count in categories.items():
            if count:
                source_category_counts[category] += 1
        source_state = str(priority_row.get("source_data_state") if priority_row else "")
        if not source_state:
            source_state = "valid_real" if int(row.get("runtime_valid_real_ts_count") or 0) else "missing"
        source_state_counts[source_state] += 1
        class_counts[remediation_class] += 1
        next_action_counts[next_action] += 1

        rows.append(
            {
                "dp_id": dp_id,
                "score_target": row.get("score_target"),
                "conversion_path_status": row.get("conversion_path_status"),
                "closure_status": row.get("closure_status"),
                "runtime_valid_real_ts_count": int(row.get("runtime_valid_real_ts_count") or 0),
                "runtime_numeric_signal_ts_count": int(
                    row.get("runtime_numeric_signal_ts_count") or 0
                ),
                "score_company_route_ready": bool(row.get("score_company_route_ready")),
                "remediation_class": remediation_class,
                "next_action": next_action,
                "safe_formula_now": safe_formula_now,
                "source_data_state": source_state,
                "runtime_source_categories": categories,
                "route": priority_row.get("route") if priority_row else None,
                "gap_bucket": priority_row.get("gap_bucket") if priority_row else None,
                "intent_subtype": priority_row.get("intent_subtype") if priority_row else None,
                "priority": priority_row.get("priority") if priority_row else None,
                "replacement_dp_id": priority_row.get("replacement_dp_id") if priority_row else None,
                "canonical_dp_id": priority_row.get("canonical_dp_id") if priority_row else None,
                "main_sources": _join_sources(priority_row),
                "repair_hint": priority_row.get("repair_hint") if priority_row else (
                    "Missing priority-row evidence; rerun score-gap priority audit."
                ),
                "production_write_allowed": False,
            }
        )

    safe_formula_count = sum(1 for row in rows if row["safe_formula_now"])
    existing_input_count = sum(1 for row in rows if row["runtime_valid_real_ts_count"] > 0)
    no_current_input_count = sum(
        1 for row in rows if row["conversion_path_status"] == "no_current_numeric_input"
    )
    score_route_ready_count = sum(1 for row in rows if row["score_company_route_ready"])
    direct_tushare_or_derived_count = sum(
        1
        for row in rows
        if row["runtime_source_categories"].get("tushare")
        or row["runtime_source_categories"].get("derived")
    )

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "conversion_path": _portable_path(conversion_path),
            "priority_path": _portable_path(priority_path),
            "dockcase_scan": "not_performed",
            "score_mutation": "none; this audit is read-only",
        },
        "summary": {
            "unresolved_score_relevant_count": len(rows),
            "existing_current_input_count": existing_input_count,
            "no_current_input_count": no_current_input_count,
            "score_company_route_ready_count": score_route_ready_count,
            "direct_tushare_or_derived_input_count": direct_tushare_or_derived_count,
            "safe_formula_now_count": safe_formula_count,
            "formula_policy_required_count": class_counts["formula_policy_required"],
            "intentional_governance_or_duplicate_count": class_counts[
                "intentional_governance_or_duplicate"
            ],
            "missing_or_not_applicable_source_count": class_counts[
                "missing_or_not_applicable_source"
            ],
            "manual_review_required_count": class_counts["manual_review_required"],
            "production_write_allowed_count": 0,
            "remediation_class_counts": dict(sorted(class_counts.items())),
            "next_action_counts": dict(sorted(next_action_counts.items())),
            "source_category_counts": dict(sorted(source_category_counts.items())),
            "source_data_state_counts": dict(sorted(source_state_counts.items())),
            "missing_priority_dp_ids": sorted(missing_priority_dp_ids),
        },
        "rows": sorted(
            rows,
            key=lambda r: (
                r["remediation_class"],
                r["score_target"] or "",
                -int(r["runtime_valid_real_ts_count"] or 0),
                r["dp_id"],
            ),
        ),
    }


def _md_table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share score-conversion remediation queue",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Score mutation: `{report['inputs']['score_mutation']}`",
        f"- DOCKCASE scan: `{report['inputs']['dockcase_scan']}`",
        f"- Unresolved score-relevant fields: `{summary['unresolved_score_relevant_count']}`",
        f"- Existing current inputs: `{summary['existing_current_input_count']}`",
        f"- No current input: `{summary['no_current_input_count']}`",
        f"- Score route ready: `{summary['score_company_route_ready_count']}`",
        f"- Direct Tushare/derived input available: `{summary['direct_tushare_or_derived_input_count']}`",
        f"- Safe formula-now fields: `{summary['safe_formula_now_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        "",
        "## Remediation Classes",
        "",
        "| class | count |",
        "|---|---:|",
    ]
    for key, value in summary["remediation_class_counts"].items():
        lines.append(_md_table_row([f"`{key}`", value]))

    lines.extend(["", "## Next Actions", "", "| action | count |", "|---|---:|"])
    for key, value in summary["next_action_counts"].items():
        lines.append(_md_table_row([f"`{key}`", value]))

    lines.extend(
        [
            "",
            "## Queue",
            "",
            "| class | dp_id | target | status | valid ts_codes | source state | replacement/canonical | next action | repair hint |",
            "|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    for row in report["rows"]:
        replacement = row.get("replacement_dp_id") or row.get("canonical_dp_id") or ""
        lines.append(
            _md_table_row(
                [
                    f"`{row['remediation_class']}`",
                    f"`{row['dp_id']}`",
                    f"`{row.get('score_target') or ''}`",
                    f"`{row['conversion_path_status']}`",
                    row["runtime_valid_real_ts_count"],
                    f"`{row['source_data_state']}`",
                    f"`{replacement}`" if replacement else "",
                    f"`{row['next_action']}`",
                    row.get("repair_hint") or "",
                ]
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `safe_formula_now_count = 0` means none of the unresolved score-relevant rows should be auto-wired into scoring without policy, source-universe, or duplicate-evidence review.",
            "- `formula_policy_required` rows have current inputs, but need a reviewed scoring direction, peer context, or baseline before a formula is defensible.",
            "- `intentional_governance_or_duplicate` rows should be verified through their replacement/canonical dp_id or kept suppressed to avoid double-counting.",
            "- `missing_or_not_applicable_source` rows require a real listed-option source universe or explicit N/A handling for A-share coverage.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-path", type=Path, default=DEFAULT_CONVERSION_PATH)
    parser.add_argument("--priority-path", type=Path, default=DEFAULT_PRIORITY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        conversion_path=args.conversion_path,
        priority_path=args.priority_path,
    )
    if not args.no_write:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.md_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {"ok": True, **report["summary"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
