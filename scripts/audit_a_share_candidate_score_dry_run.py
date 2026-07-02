#!/usr/bin/env python3
"""Dry-run A-share candidate values through the production score bridge.

This audit is intentionally read-only.  It does not generate final candidate
values, call an LLM, or write ``runtime/hot.sqlite``.  It validates the bridge
contract for the 34 candidate-ready score blockers by constructing a minimal
review-placeholder payload for each candidate, then running the same
``_realtime_signal`` and ``synthesize_realtime_nodes`` gates used by production
scoring.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from mvp20.aggregator import _realtime_signal, synthesize_realtime_nodes
from mvp20.field_governance import load_default_governance


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_candidate_score_dry_run_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_candidate_score_dry_run_2026-06-19.md"

DISCOUNT_TARGETS = {
    "priced_in_discount",
    "risk_discount",
    "uncertainty_discount",
    "volatility_risk",
    "overheat_risk",
}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _bridge_payload(dp_id: str, score_target: str, candidate_status: str) -> tuple[str, dict[str, Any]]:
    """Return ``(data_status, value_json)`` for a minimal bridge-compatible row."""

    if dp_id == "L6.mult.dcf":
        return "Known", {
            "scalar": 0.15,
            "assumptions": {
                "discount_rate": "review_required",
                "terminal_growth": "review_required",
                "forecast_horizon_years": 5,
            },
            "sensitivity": {"low": -0.05, "base": 0.15, "high": 0.30},
        }
    if dp_id == "L6.priced.realization_risk":
        return "Known", {
            "magnitude": 0.20,
            "drivers": ["run_up", "news_age", "priced_in"],
        }
    if dp_id == "L8.val.slope_risk_off":
        return "Known", {
            "magnitude": 0.18,
            "drivers": ["second_derivative", "risk_appetite", "overvalued"],
        }
    if dp_id == "L7.reflex.tag":
        return "Known", {
            "multiplier": 1.05,
            "tag": "positive_feedback",
        }
    if dp_id == "L7.trade.gamma":
        return "Known", {
            "multiplier": 1.0,
            "applicability": "a_share_single_stock_no_listed_option",
        }
    if score_target.endswith("_multiplier"):
        return "Known", {"multiplier": 1.03}
    if score_target in DISCOUNT_TARGETS:
        return "Known", {"score": 0.20, "magnitude": 0.20}
    if candidate_status == "ready_for_web_event_candidate":
        return "Known", {"score": 0.0, "event_state": "none_observed"}
    return "Known", {"score": 0.10}


def build_report(candidate_path: Path, sample_ts_code: str) -> dict[str, Any]:
    started = time.time()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    registry = load_default_governance(strict=False)
    rows: list[dict[str, Any]] = []

    for row in candidate.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if row.get("candidate_input_ready") is not True:
            continue
        rule = registry.get(dp_id) if registry is not None else None
        score_target = str(row.get("score_target") or (rule.score_target if rule else "none"))
        data_status, value_json = _bridge_payload(
            dp_id,
            score_target,
            str(row.get("candidate_status") or ""),
        )
        signal = _realtime_signal(dp_id, value_json, score_target, ts_code=sample_ts_code)
        entry = {
            "value": value_json,
            "data_status": data_status,
            "confidence": 0.7,
            "source": "candidate:dry_run",
            "updated_at": 1_800_000_000,
        }
        nodes = (
            synthesize_realtime_nodes(
                {dp_id: entry},
                registry,
                existing_dp_ids=set(),
                ts_code=sample_ts_code,
            )
            if registry is not None
            else []
        )
        node = nodes[0] if nodes else None
        rows.append(
            {
                "dp_id": dp_id,
                "candidate_status": row.get("candidate_status"),
                "recommended_source_route": row.get("recommended_source_route"),
                "score_target": score_target,
                "bridge_payload_status": data_status,
                "bridge_payload": value_json,
                "bridge_signal": signal,
                "bridge_signal_ready": signal is not None,
                "node_emitted": node is not None,
                "node_direction": node.get("direction") if node else None,
                "node_score": (node.get("value") or {}).get("score") if node else None,
                "final_score_target_ready": bool(node is not None and score_target not in {"none", "audit_only", "display_only", "parent_score", "node_score"}),
                "score_mutation": "none; dry-run only",
            }
        )

    status_counts = Counter(str(row["candidate_status"]) for row in rows)
    route_counts = Counter(str(row["recommended_source_route"]) for row in rows)
    blocked = [
        row["dp_id"]
        for row in rows
        if not row["bridge_signal_ready"] or not row["node_emitted"]
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "candidate_path": _portable_path(candidate_path),
        "sample_ts_code": sample_ts_code,
        "summary": {
            "candidate_ready_rows_checked": len(rows),
            "bridge_signal_ready_count": sum(1 for row in rows if row["bridge_signal_ready"]),
            "node_emitted_count": sum(1 for row in rows if row["node_emitted"]),
            "final_score_target_ready_count": sum(1 for row in rows if row["final_score_target_ready"]),
            "bridge_blocked_count": len(blocked),
            "bridge_blocked_dp_ids": blocked,
            "candidate_status_counts": dict(sorted(status_counts.items())),
            "recommended_source_route_counts": dict(sorted(route_counts.items())),
            "score_mutation": "none; dry-run only",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share candidate score dry-run",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        f"- Candidate-ready rows checked: `{summary['candidate_ready_rows_checked']}`",
        f"- Bridge signal ready: `{summary['bridge_signal_ready_count']}`",
        f"- Realtime nodes emitted: `{summary['node_emitted_count']}`",
        f"- Final score target ready: `{summary['final_score_target_ready_count']}`",
        f"- Bridge blocked: `{summary['bridge_blocked_count']}`",
        "",
        "## Candidate Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["candidate_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | route | target | signal | node | payload |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['recommended_source_route']}` | "
            f"`{row['score_target']}` | "
            f"{row['bridge_signal'] if row['bridge_signal'] is not None else '-'} | "
            f"{'yes' if row['node_emitted'] else 'no'} | "
            f"`{json.dumps(row['bridge_payload'], ensure_ascii=False, sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This validates the bridge contract only. It does not prove the candidate value is correct.",
            "- A row passing this dry-run can be numerically converted by the current production bridge if a reviewed candidate writes the same payload shape as Known/Proxy.",
            "- `safe_to_upsert_without_review` remains governed by the candidate-evidence audit and is still 0.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--sample-ts-code", default="000001.SZ")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.candidate_path, args.sample_ts_code)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
