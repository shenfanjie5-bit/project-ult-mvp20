#!/usr/bin/env python3
"""Build a read-only generation queue for A-share candidate values.

This report does not call an LLM, generate final business values, or write
``runtime/hot.sqlite``.  It turns generator-required staging envelopes into
actionable local/event/manual generation tasks with explicit output contracts
and acceptance gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STAGING_PATH = ROOT / "docs/audit/a_share_candidate_staging_payloads_2026-06-19.json"
DEFAULT_CONTRACT_PATH = ROOT / "docs/audit/a_share_candidate_value_contracts_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_candidate_generation_queue_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_candidate_generation_queue_2026-06-19.md"


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _contract_rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _generator_kind(row: Mapping[str, Any]) -> str:
    action = str(row.get("next_action") or "")
    if action == "generate_event_llm_candidate":
        return "event_llm_candidate"
    if action == "generate_manual_policy_candidate":
        return "manual_policy_candidate"
    if action == "generate_local_llm_candidate":
        return "local_llm_candidate"
    return "route_review_candidate"


def _value_contract(dp_id: str, score_target: str) -> dict[str, Any]:
    if dp_id == "L6.mult.dcf":
        return {
            "value_json": {
                "scalar": "finite number in [-1, 1]",
                "assumptions": {
                    "discount_rate": "finite reviewed assumption",
                    "terminal_growth": "finite reviewed assumption",
                    "forecast_horizon": "reviewed horizon",
                    "normalized_fcf": "reviewed normalized FCF basis",
                },
                "sensitivity": "object with bounded low/base/high cases",
            }
        }
    if dp_id in {"L6.priced.realization_risk", "L8.val.slope_risk_off"}:
        return {
            "value_json": {
                "magnitude": "finite number in [0, 1]",
                "drivers": "non-empty list of evidence-backed driver refs",
            }
        }
    if dp_id == "L7.reflex.tag":
        return {
            "value_json": {
                "multiplier": "finite number in (0, 2], neutral 1.0",
                "tag": "positive_feedback | exhausted_feedback | neutral",
            }
        }
    if score_target in {"risk_discount", "priced_in_discount"}:
        return {"value_json": {"magnitude": "finite number in [0, 1]"}}
    if str(score_target).endswith("_multiplier"):
        return {"value_json": {"multiplier": "finite number > 0"}}
    return {"value_json": {"score": "finite signed number in [-1, 1]"}}


def _task_priority(kind: str, score_target: str) -> str:
    if kind == "manual_policy_candidate":
        return "P1_manual_policy_before_known_value"
    if score_target in {"risk_discount", "priced_in_discount"}:
        return "P1_risk_discount_candidate"
    if kind == "event_llm_candidate":
        return "P2_event_classification_candidate"
    return "P2_local_closed_loop_candidate"


def _build_task(row: Mapping[str, Any], contract_row: Mapping[str, Any] | None) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    score_target = str(row.get("score_target") or "")
    kind = _generator_kind(row)
    staging_payload = row.get("staging_payload") if isinstance(row.get("staging_payload"), Mapping) else {}
    evidence_refs = staging_payload.get("evidence_refs") if isinstance(staging_payload, Mapping) else []
    contract_valid = bool(contract_row and contract_row.get("contract_valid"))
    return {
        "task_id": f"a_share_candidate::{kind}::{dp_id}",
        "dp_id": dp_id,
        "score_target": score_target,
        "generator_kind": kind,
        "priority": _task_priority(kind, score_target),
        "recommended_source_route": row.get("recommended_source_route"),
        "next_action": row.get("next_action"),
        "current_payload_status": row.get("payload_status"),
        "current_contract_valid": contract_valid,
        "input_evidence_refs": evidence_refs,
        "output_contract": {
            "target_dp_id": dp_id,
            "score_target": score_target,
            "data_status": "Known | Unknown | NotApplicable",
            **_value_contract(dp_id, score_target),
            "confidence": "finite number in [0, 1]",
            "evidence_refs": "non-empty list; must cite runtime/candidate evidence used",
            "rationale": "non-empty explanation of evidence and value direction",
            "review_status": "review_required",
            "safe_to_upsert_without_review": False,
        },
        "acceptance_gates": [
            "passes scripts/audit_a_share_candidate_value_contracts.py",
            "concrete Known/Proxy values must produce _realtime_signal != None",
            "concrete Known/Proxy values must emit a synthetic realtime node",
            "production_write_allowed remains false until separate review approval",
        ],
        "forbidden_inputs": [
            "do not copy placeholder dry-run values from audit_a_share_candidate_score_dry_run.py",
            "do not emit Known without evidence_refs and rationale",
            "do not rely on aggregator clipping to accept out-of-bounds values",
            "do not write runtime/hot.sqlite or overlay YAML from this queue",
        ],
    }


def build_report(staging_path: Path, contract_path: Path) -> dict[str, Any]:
    started = time.time()
    staging = _load_json(staging_path)
    contracts = _load_json(contract_path)
    contract_rows = _contract_rows_by_dp(contracts)
    tasks: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in staging.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("payload_status") != "requires_generator_output":
            skipped.append(
                {
                    "dp_id": row.get("dp_id"),
                    "reason": "not generator-required",
                    "payload_status": row.get("payload_status"),
                }
            )
            continue
        tasks.append(_build_task(row, contract_rows.get(str(row.get("dp_id") or ""))))

    kind_counts = Counter(task["generator_kind"] for task in tasks)
    priority_counts = Counter(task["priority"] for task in tasks)
    batches: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        batches[task["generator_kind"]].append(task["dp_id"])

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "staging_path": _portable_path(staging_path),
        "contract_path": _portable_path(contract_path),
        "summary": {
            "generator_required_task_count": len(tasks),
            "skipped_non_generator_count": len(skipped),
            "generator_kind_counts": dict(sorted(kind_counts.items())),
            "priority_counts": dict(sorted(priority_counts.items())),
            "all_tasks_have_valid_placeholder_contract": all(
                task["current_contract_valid"] for task in tasks
            ),
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "batches": {kind: sorted(dp_ids) for kind, dp_ids in sorted(batches.items())},
        "tasks": tasks,
        "skipped_rows": skipped,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share candidate generation queue",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Generator-required tasks: `{summary['generator_required_task_count']}`",
        f"- Skipped non-generator rows: `{summary['skipped_non_generator_count']}`",
        f"- Placeholder contracts valid: `{summary['all_tasks_have_valid_placeholder_contract']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Generator Kind Counts",
        "",
        "| Kind | Count |",
        "|---|---:|",
    ]
    for kind, count in summary["generator_kind_counts"].items():
        lines.append(f"| `{kind}` | {count} |")

    lines.extend(["", "## Batches", ""])
    for kind, dp_ids in report["batches"].items():
        lines.append(f"- `{kind}` ({len(dp_ids)}): " + ", ".join(f"`{dp_id}`" for dp_id in dp_ids))

    lines.extend(
        [
            "",
            "## Tasks",
            "",
            "| dp_id | kind | priority | target | evidence refs |",
            "|---|---|---|---|---:|",
        ]
    )
    for task in report["tasks"]:
        lines.append(
            "| "
            f"`{task['dp_id']}` | "
            f"`{task['generator_kind']}` | "
            f"`{task['priority']}` | "
            f"`{task['score_target']}` | "
            f"{len(task['input_evidence_refs'])} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This queue packages generator work only; it does not generate candidate business values.",
            "- Every task must produce a reviewed output that passes the value-contract audit before it can become a Known staging payload.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-path", type=Path, default=DEFAULT_STAGING_PATH)
    parser.add_argument("--contract-path", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.staging_path, args.contract_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
