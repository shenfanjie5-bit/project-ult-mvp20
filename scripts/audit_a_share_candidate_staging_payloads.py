#!/usr/bin/env python3
"""Prepare review-stage A-share candidate payload packets.

This audit is read-only and does not write ``runtime/hot.sqlite``.  It turns
the candidate-evidence and upsert-safety reports into a staging queue:

* deterministic neutral / not-applicable rows get a concrete review payload,
* the remaining rows get an explicit generator task and output contract,
* every row remains blocked from production writes until review.
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
DEFAULT_DRY_RUN_PATH = ROOT / "docs/audit/a_share_candidate_score_dry_run_2026-06-19.json"
DEFAULT_UPSERT_SAFETY_PATH = ROOT / "docs/audit/a_share_candidate_upsert_safety_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_candidate_staging_payloads_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_candidate_staging_payloads_2026-06-19.md"


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
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


def _short_report_counts(row: Mapping[str, Any]) -> dict[str, int]:
    evidence = (
        row.get("candidate_input", {}).get("short_report_evidence", {})
        if isinstance(row.get("candidate_input"), Mapping)
        else {}
    )
    out: dict[str, int] = {}
    for key in (
        "news_html_files_scanned",
        "strict_short_report_documents",
        "direct_a_share_short_report_documents",
        "foreign_or_market_short_report_documents",
    ):
        try:
            out[key] = int(evidence.get(key) or 0)
        except (AttributeError, TypeError, ValueError):
            out[key] = 0
    return out


def _required_output_contract(candidate_row: Mapping[str, Any]) -> dict[str, Any]:
    candidate_input = candidate_row.get("candidate_input")
    if isinstance(candidate_input, Mapping):
        schema = candidate_input.get("required_output_schema")
        if isinstance(schema, Mapping):
            return dict(schema)
    return {
        "target_dp_id": "string",
        "data_status": "Known | Proxy | Unknown | NotApplicable",
        "value_json": "object accepted by the scoring bridge",
        "confidence": "0.0-1.0",
        "evidence_refs": "array",
        "rationale": "string",
    }


def _next_action(route: str, dp_id: str) -> str:
    if dp_id == "L9.media.short_report":
        return "review_neutral_or_unknown_payload"
    if dp_id == "L7.trade.gamma":
        return "review_not_applicable_payload"
    if route == "event_llm_from_runtime_news":
        return "generate_event_llm_candidate"
    if route == "local_llm_closed_loop":
        return "generate_local_llm_candidate"
    if route == "manual_design_review":
        return "generate_manual_policy_candidate"
    return "review_route_before_generation"


def _candidate_evidence_refs(candidate_row: Mapping[str, Any]) -> list[str]:
    refs = ["docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"]
    candidate_input = candidate_row.get("candidate_input")
    if isinstance(candidate_input, Mapping):
        if candidate_input.get("short_report_evidence"):
            refs.append("docs/audit/a_share_short_report_evidence_2026-06-19.json")
        if candidate_input.get("grain_join_policy"):
            refs.append("config/mvp20.universe.yaml")
        for dep in candidate_row.get("source_dependencies") or []:
            refs.append(f"runtime:realtime_current:{dep}")
    return list(dict.fromkeys(str(ref) for ref in refs))


def _payload_envelope(
    *,
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict[str, Any],
    confidence: float,
    evidence_refs: list[str],
    rationale: str,
    bridge_entry_data_status: str | None = None,
) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": bridge_entry_data_status or data_status,
        "value_json": value_json,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
        "rationale": rationale,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }


def _staging_payload(candidate_row: Mapping[str, Any], safety_row: Mapping[str, Any]) -> dict[str, Any] | None:
    dp_id = str(candidate_row.get("dp_id") or "")
    score_target = str(candidate_row.get("score_target") or "")
    if safety_row.get("upsert_safety_class") == "blocked":
        return None

    if dp_id == "L9.media.short_report":
        counts = _short_report_counts(candidate_row)
        if counts["direct_a_share_short_report_documents"] != 0:
            return None
        return _payload_envelope(
            dp_id=dp_id,
            score_target=score_target,
            data_status="Known",
            confidence=0.6,
            value_json={
                "score": 0.0,
                "event_state": "none_observed",
                **counts,
            },
            evidence_refs=_candidate_evidence_refs(candidate_row),
            rationale=(
                "Dedicated short-report scan found no direct A-share short-report hits; "
                "stage a neutral payload for review only."
            ),
        )

    if dp_id == "L7.trade.gamma":
        return _payload_envelope(
            dp_id=dp_id,
            score_target=score_target,
            data_status="NotApplicable",
            bridge_entry_data_status="Known",
            confidence=0.7,
            value_json={
                "multiplier": 1.0,
                "applicability": "a_share_single_stock_no_listed_option",
            },
            evidence_refs=_candidate_evidence_refs(candidate_row),
            rationale=(
                "A-share single-stock gamma is neutral unless direct listed-option "
                "or reviewed proxy option evidence exists."
            ),
        )

    return _payload_envelope(
        dp_id=dp_id,
        score_target=score_target,
        data_status="Unknown",
        confidence=0.0,
        value_json={"review_required": True},
        evidence_refs=_candidate_evidence_refs(candidate_row),
        rationale="A governed candidate generator must produce and review a bounded value before staging a Known payload.",
    )


def _validate_bridge(dp_id: str, score_target: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    value_json = payload.get("value_json")
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": payload.get("bridge_entry_data_status", payload.get("data_status")),
        "confidence": payload.get("confidence", 0.5),
        "source": "candidate:staging_review",
        "updated_at": 1_800_000_000,
    }
    nodes = (
        synthesize_realtime_nodes(
            {dp_id: entry},
            registry,
            existing_dp_ids=set(),
            ts_code="000001.SZ",
        )
        if registry is not None
        else []
    )
    return {
        "bridge_signal": signal,
        "bridge_signal_ready": signal is not None,
        "node_emitted": bool(nodes),
        "final_score_target_ready": bool(nodes and score_target not in {"none", "audit_only", "display_only", "parent_score", "node_score"}),
    }


def build_report(
    candidate_path: Path,
    dry_run_path: Path,
    upsert_safety_path: Path,
) -> dict[str, Any]:
    started = time.time()
    candidate = _load_json(candidate_path)
    dry_run = _load_json(dry_run_path)
    upsert_safety = _load_json(upsert_safety_path)
    dry_rows = _rows_by_dp(dry_run)
    safety_rows = _rows_by_dp(upsert_safety)
    rows: list[dict[str, Any]] = []

    for candidate_row in candidate.get("rows") or []:
        if not isinstance(candidate_row, Mapping):
            continue
        dp_id = str(candidate_row.get("dp_id") or "")
        route = str(candidate_row.get("recommended_source_route") or "")
        score_target = str(candidate_row.get("score_target") or "")
        safety_row = safety_rows.get(dp_id, {})
        dry_row = dry_rows.get(dp_id, {})
        payload = _staging_payload(candidate_row, safety_row)
        bridge_validation = (
            _validate_bridge(dp_id, score_target, payload)
            if payload is not None
            and payload.get("data_status") in {"Known", "NotApplicable"}
            and not payload.get("value_json", {}).get("review_required")
            else {}
        )
        if payload is not None:
            if dp_id == "L9.media.short_report":
                payload_status = "deterministic_neutral_review_payload"
            elif dp_id == "L7.trade.gamma":
                payload_status = "deterministic_not_applicable_review_payload"
            else:
                payload_status = "requires_generator_output"
        elif safety_row.get("upsert_safety_class") == "blocked":
            payload_status = "blocked"
        else:
            payload_status = "requires_generator_output"
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "recommended_source_route": route,
                "candidate_status": candidate_row.get("candidate_status"),
                "upsert_safety_class": safety_row.get("upsert_safety_class"),
                "next_action": _next_action(route, dp_id),
                "payload_status": payload_status,
                "production_write_allowed": False,
                "review_required": payload_status != "blocked",
                "required_output_contract": _required_output_contract(candidate_row),
                "staging_payload": payload,
                "staging_bridge_validation": bridge_validation,
                "dry_run_bridge_ready": bool(
                    dry_row.get("bridge_signal_ready")
                    and dry_row.get("node_emitted")
                    and dry_row.get("final_score_target_ready")
                ),
                "note": (
                    "Concrete deterministic staging payload is for review only and must not be production-upserted."
                    if payload_status.startswith("deterministic_")
                    else "Placeholder staging payload records the review contract; generate a bounded value before staging as Known."
                    if payload_status == "requires_generator_output"
                    else "Generate a reviewed candidate value before staging a payload."
                ),
            }
        )

    payload_status_counts = Counter(str(row["payload_status"]) for row in rows)
    next_action_counts = Counter(str(row["next_action"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "candidate_path": _portable_path(candidate_path),
        "dry_run_path": _portable_path(dry_run_path),
        "upsert_safety_path": _portable_path(upsert_safety_path),
        "summary": {
            "candidate_rows_checked": len(rows),
            "staging_payload_count": sum(1 for row in rows if row["staging_payload"] is not None),
            "deterministic_staging_payload_count": sum(
                1 for row in rows if str(row["payload_status"]).startswith("deterministic_")
            ),
            "placeholder_payload_count": sum(
                1 for row in rows if row["payload_status"] == "requires_generator_output"
            ),
            "generator_required_count": sum(
                1 for row in rows if row["payload_status"] == "requires_generator_output"
            ),
            "blocked_count": sum(1 for row in rows if row["payload_status"] == "blocked"),
            "staging_payload_bridge_ready_count": sum(
                1
                for row in rows
                if row["staging_bridge_validation"].get("final_score_target_ready")
            ),
            "dry_run_bridge_ready_count": sum(1 for row in rows if row["dry_run_bridge_ready"]),
            "review_required_count": sum(1 for row in rows if row["review_required"]),
            "production_write_allowed_count": sum(
                1 for row in rows if row["production_write_allowed"]
            ),
            "payload_status_counts": dict(sorted(payload_status_counts.items())),
            "next_action_counts": dict(sorted(next_action_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share candidate staging payloads",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidate rows checked: `{summary['candidate_rows_checked']}`",
        f"- Deterministic staging payloads: `{summary['deterministic_staging_payload_count']}`",
        f"- Generator-required rows: `{summary['generator_required_count']}`",
        f"- Blocked: `{summary['blocked_count']}`",
        f"- Staging payloads bridge-ready: `{summary['staging_payload_bridge_ready_count']}`",
        f"- Dry-run bridge-ready rows: `{summary['dry_run_bridge_ready_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Payload Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["payload_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | route | payload status | next action | staging bridge | production write |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['recommended_source_route']}` | "
            f"`{row['payload_status']}` | "
            f"`{row['next_action']}` | "
            f"{'yes' if row['staging_bridge_validation'].get('final_score_target_ready') else '-'} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This report prepares review packets only; it does not claim candidate values are correct.",
            "- Only deterministic neutral / not-applicable rows receive concrete staging payloads here.",
            "- The remaining rows require governed local/event/manual candidate generation before staging.",
            "- Production score-affecting writes remain disabled for all rows.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--dry-run-path", type=Path, default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--upsert-safety-path", type=Path, default=DEFAULT_UPSERT_SAFETY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.candidate_path, args.dry_run_path, args.upsert_safety_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
