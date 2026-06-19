#!/usr/bin/env python3
"""Prioritize L0.demand.penetration value-review candidates.

This report narrows the existing value-review packets for the A-share
penetration field. It ranks candidate value sources for reviewer attention, but
it does not select a value, create a Known draft, or write runtime data.
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
DEFAULT_VALUE_REVIEW_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_priority_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_penetration_value_priority_2026-06-19.md"
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


def _source_quality(path: str) -> str:
    if "eastmoney_guba" in path:
        return "low_confidence_community"
    if "cls_flash" in path:
        return "secondary_market_doc"
    if "ths_news" in path:
        return "broker_or_research_doc"
    return "unknown_source_quality"


def _priority(row: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    verdict = str(row.get("source_scope_verdict") or "")
    path = str(row.get("market_relative_path") or "")
    quality = _source_quality(path)
    reasons: list[str] = []
    if verdict == "review_a_share_or_domestic_scope" and quality == "secondary_market_doc":
        reasons.append("A-share/domestic scope with non-community market document")
        return "P1_preferred_source_scope_review", quality, reasons
    if quality == "low_confidence_community":
        reasons.append("community/forum source cannot support selection without confirmation")
        return "P3_low_confidence_community_review", quality, reasons
    if verdict == "review_domestic_or_industry_scope":
        reasons.append("domestic/industry scope needs issuer and denominator review")
        return "P2_industry_scope_review", quality, reasons
    if verdict == "review_forecast_or_assumption_scope":
        reasons.append("forecast/assumption scope needs policy and bounds review")
        return "P3_forecast_or_assumption_review", quality, reasons
    reasons.append(f"unhandled source scope verdict: {verdict}")
    return "P3_manual_scope_review", quality, reasons


def _candidate_values(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for option in row.get("candidate_value_options") or []:
        if not isinstance(option, Mapping):
            continue
        values.append(
            {
                "option_id": option.get("option_id"),
                "raw_token": option.get("raw_token"),
                "raw_percent": option.get("raw_percent"),
                "formula_probe_score": option.get("formula_probe_score"),
                "bridge_probe_ready": bool(
                    (option.get("bridge_validation") or {}).get(
                        "final_score_target_ready"
                    )
                ),
                "option_contract_valid": bool(option.get("option_contract_valid")),
            }
        )
    return values


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    priority, quality, reasons = _priority(row)
    values = _candidate_values(row)
    return {
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target"),
        "value_review_packet_id": row.get("value_review_packet_id"),
        "source_scope_verdict": row.get("source_scope_verdict"),
        "source_quality": quality,
        "priority_bucket": priority,
        "priority_reasons": reasons,
        "title": row.get("title"),
        "market_relative_path": row.get("market_relative_path"),
        "excerpt": row.get("excerpt"),
        "candidate_values": values,
        "candidate_value_option_count": len(values),
        "bridge_probe_ready_option_count": sum(
            1 for value in values if value["bridge_probe_ready"]
        ),
        "selected_raw_value": None,
        "selected_value_json": None,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(*, value_review_path: Path) -> dict[str, Any]:
    started = time.time()
    source = _load_json(value_review_path)
    rows = [
        _row(row)
        for row in source.get("rows") or []
        if isinstance(row, Mapping) and row.get("dp_id") == "L0.demand.penetration"
    ]
    priority_order = {
        "P1_preferred_source_scope_review": 1,
        "P2_industry_scope_review": 2,
        "P3_forecast_or_assumption_review": 3,
        "P3_low_confidence_community_review": 4,
        "P3_manual_scope_review": 5,
    }
    rows.sort(
        key=lambda row: (
            priority_order.get(str(row.get("priority_bucket") or ""), 99),
            str(row.get("market_relative_path") or ""),
        )
    )
    priority_counts = Counter(str(row.get("priority_bucket") or "") for row in rows)
    source_quality_counts = Counter(str(row.get("source_quality") or "") for row in rows)
    option_count = sum(int(row["candidate_value_option_count"]) for row in rows)
    bridge_count = sum(int(row["bridge_probe_ready_option_count"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {"value_review_path": _portable_path(value_review_path)},
        "summary": {
            "penetration_value_review_packet_count": len(rows),
            "candidate_value_option_count": option_count,
            "bridge_probe_ready_option_count": bridge_count,
            "preferred_source_scope_review_count": priority_counts.get(
                "P1_preferred_source_scope_review", 0
            ),
            "industry_scope_review_count": priority_counts.get(
                "P2_industry_scope_review", 0
            ),
            "forecast_or_assumption_review_count": priority_counts.get(
                "P3_forecast_or_assumption_review", 0
            ),
            "low_confidence_community_review_count": priority_counts.get(
                "P3_low_confidence_community_review", 0
            ),
            "selected_raw_value_count": 0,
            "selected_value_json_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "priority_bucket_counts": dict(sorted(priority_counts.items())),
            "source_quality_counts": dict(sorted(source_quality_counts.items())),
            "score_mutation": "none; priority review only and no realtime_current mutation",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown penetration value priority",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Value-review packets: `{summary['penetration_value_review_packet_count']}`",
        f"- Candidate value options: `{summary['candidate_value_option_count']}`",
        f"- Bridge-probe-ready options: `{summary['bridge_probe_ready_option_count']}`",
        f"- Preferred source-scope reviews: `{summary['preferred_source_scope_review_count']}`",
        f"- Industry-scope reviews: `{summary['industry_scope_review_count']}`",
        f"- Forecast/assumption reviews: `{summary['forecast_or_assumption_review_count']}`",
        f"- Low-confidence community reviews: `{summary['low_confidence_community_review_count']}`",
        f"- Selected raw values: `{summary['selected_raw_value_count']}`",
        f"- Known-draft sufficient: `{summary['known_draft_sufficient_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| priority | source quality | title | options | bridge-ready |",
        "|---|---|---|---:|---:|",
    ]
    for row in report["rows"]:
        title = str(row.get("title") or "").replace("|", "\\|")
        if len(title) > 80:
            title = title[:77] + "..."
        lines.append(
            "| "
            f"`{row.get('priority_bucket')}` | "
            f"`{row.get('source_quality')}` | "
            f"{title} | "
            f"{row.get('candidate_value_option_count')} | "
            f"{row.get('bridge_probe_ready_option_count')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Priority means review order, not approval.",
            "- No candidate value is selected and no Known draft is emitted.",
            "- Every option still requires source-scope, value, bounds, formula-policy, and approval review.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value-review-path", type=Path, default=DEFAULT_VALUE_REVIEW_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(value_review_path=args.value_review_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
