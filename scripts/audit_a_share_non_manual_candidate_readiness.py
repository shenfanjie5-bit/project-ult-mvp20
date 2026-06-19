#!/usr/bin/env python3
"""Audit readiness for non-manual A-share generator candidates.

This report is read-only.  It does not call an LLM, generate business values,
or write ``runtime/hot.sqlite``.  It classifies the remaining local/event
generator tasks by evidence shape and verifies that their output contracts can
reach the production realtime bridge once a reviewed generator emits values.
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
DEFAULT_QUEUE_PATH = ROOT / "docs/audit/a_share_candidate_generation_queue_2026-06-19.json"
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.md"
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


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _candidate_rows_by_dp(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _non_manual_tasks(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task in queue.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("generator_kind") in {"local_llm_candidate", "event_llm_candidate"}:
            tasks.append(task)
    return tasks


def _deps(candidate_row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    candidate_input = (
        candidate_row.get("candidate_input")
        if isinstance(candidate_row, Mapping)
        else None
    )
    if not isinstance(candidate_input, Mapping):
        return []
    return [dep for dep in candidate_input.get("dependencies") or [] if isinstance(dep, dict)]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _known_ratio(dep: Mapping[str, Any]) -> float:
    row_count = _safe_float(dep.get("row_count")) or 0.0
    known_count = _safe_float(dep.get("known_count")) or 0.0
    if row_count <= 0.0:
        return 0.0
    return max(0.0, min(1.0, known_count / row_count))


def _sample_value_keys(dep: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for sample in dep.get("sample_rows") or []:
        if not isinstance(sample, Mapping):
            continue
        compact = sample.get("value_json_compact")
        if isinstance(compact, Mapping):
            keys.extend(str(key) for key in compact.keys())
    return sorted(set(keys))


def _has_textual_evidence(dep: Mapping[str, Any]) -> bool:
    dep_id = str(dep.get("dp_id") or "")
    if dep_id.startswith("L9.media") or dep_id.startswith("L9.disclosure"):
        return True
    text_keys = {"top_headlines", "top_qa", "question", "answer", "title"}
    return bool(text_keys.intersection(_sample_value_keys(dep)))


def _has_event_evidence(dep: Mapping[str, Any]) -> bool:
    dep_id = str(dep.get("dp_id") or "")
    if dep_id.startswith("L9.industry") or dep_id.startswith("L9.macro") or dep_id.startswith("L9.media"):
        return True
    event_keys = {"event_active", "top_headlines", "positive_policy_count", "negative_policy_count"}
    return bool(event_keys.intersection(_sample_value_keys(dep)))


def _dependency_profiles(deps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for dep in deps:
        profiles.append(
            {
                "dp_id": dep.get("dp_id"),
                "row_count": _safe_int(dep.get("row_count")),
                "known_count": _safe_int(dep.get("known_count")),
                "known_ratio": round(_known_ratio(dep), 6),
                "namespace_counts": dep.get("namespace_counts") or {},
                "latest_updated_at_iso": dep.get("latest_updated_at_iso"),
                "sample_value_keys": _sample_value_keys(dep),
                "has_textual_evidence": _has_textual_evidence(dep),
                "has_event_evidence": _has_event_evidence(dep),
            }
        )
    return profiles


def _route_bucket(kind: str, deps: list[dict[str, Any]]) -> str:
    if kind == "event_llm_candidate":
        return "event_text_classification_required"
    if any(_has_textual_evidence(dep) for dep in deps):
        return "local_structured_text_llm_required"
    if len(deps) == 1:
        return "local_single_dependency_policy_required"
    return "local_structured_llm_required"


def _dependency_readiness(deps: list[dict[str, Any]]) -> str:
    if not deps:
        return "missing_candidate_evidence"
    if all(_safe_int(dep.get("known_count")) > 0 for dep in deps):
        if all(_known_ratio(dep) >= 0.7 or _safe_int(dep.get("row_count")) <= 2 for dep in deps):
            return "all_dependencies_have_material_known_coverage"
        return "all_dependencies_have_some_known_rows"
    return "some_dependencies_have_no_known_rows"


def _bridge_probe_payload(score_target: str) -> dict[str, Any]:
    if score_target in {"risk_discount", "priced_in_discount", "uncertainty_discount"}:
        return {
            "score": 0.1,
            "magnitude": 0.1,
            "drivers": ["contract_probe"],
        }
    return {"score": 0.1}


def _bridge_validation(dp_id: str, score_target: str, value_json: Mapping[str, Any]) -> dict[str, Any]:
    signal = _realtime_signal(dp_id, value_json, score_target, ts_code="000001.SZ")
    registry = load_default_governance(strict=False)
    entry = {
        "value": value_json,
        "data_status": "Known",
        "confidence": 0.5,
        "source": "candidate:non_manual_contract_probe",
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
    node = nodes[0] if nodes else None
    return {
        "bridge_probe_payload": dict(value_json),
        "bridge_signal": signal,
        "bridge_signal_ready": signal is not None,
        "node_emitted": node is not None,
        "node_score": (node.get("value") or {}).get("score") if node else None,
        "node_synthetic_realtime": bool(node and node.get("synthetic_realtime")),
        "final_score_target_ready": bool(
            node is not None and score_target not in FINAL_SCORE_EXCLUDED_TARGETS
        ),
    }


def _task_contract_valid(task: Mapping[str, Any]) -> bool:
    contract = task.get("output_contract")
    if not isinstance(contract, Mapping):
        return False
    value_contract = contract.get("value_json")
    if not isinstance(value_contract, Mapping):
        return False
    return bool(contract.get("safe_to_upsert_without_review") is False)


def build_report(queue_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    queue = _load_json(queue_path)
    candidate = _load_json(candidate_path)
    candidate_rows = _candidate_rows_by_dp(candidate)
    rows: list[dict[str, Any]] = []

    for task in _non_manual_tasks(queue):
        dp_id = str(task.get("dp_id") or "")
        score_target = str(task.get("score_target") or "")
        kind = str(task.get("generator_kind") or "")
        candidate_row = candidate_rows.get(dp_id)
        deps = _deps(candidate_row)
        profiles = _dependency_profiles(deps)
        route_bucket = _route_bucket(kind, deps)
        dependency_readiness = _dependency_readiness(deps)
        bridge = _bridge_validation(dp_id, score_target, _bridge_probe_payload(score_target))
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "task_id": task.get("task_id"),
                "generator_kind": kind,
                "route_bucket": route_bucket,
                "dependency_readiness": dependency_readiness,
                "candidate_status": candidate_row.get("candidate_status") if candidate_row else None,
                "recommended_source_route": candidate_row.get("recommended_source_route") if candidate_row else task.get("recommended_source_route"),
                "source_dependencies": [dep.get("dp_id") for dep in deps],
                "dependency_profiles": profiles,
                "current_placeholder_contract_valid": bool(task.get("current_contract_valid")),
                "output_contract_shape_valid": _task_contract_valid(task),
                "bridge_validation": bridge,
                "deterministic_known_draft_allowed": False,
                "next_action": (
                    "generate_reviewed_event_llm_candidate"
                    if kind == "event_llm_candidate"
                    else "generate_reviewed_local_closed_loop_candidate"
                ),
                "production_write_allowed": False,
                "note": "readiness only; no business value generated",
            }
        )

    kind_counts = Counter(row["generator_kind"] for row in rows)
    bucket_counts = Counter(row["route_bucket"] for row in rows)
    readiness_counts = Counter(row["dependency_readiness"] for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "queue_path": _portable_path(queue_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "non_manual_task_count": len(rows),
            "generator_kind_counts": dict(sorted(kind_counts.items())),
            "route_bucket_counts": dict(sorted(bucket_counts.items())),
            "dependency_readiness_counts": dict(sorted(readiness_counts.items())),
            "placeholder_contract_valid_count": sum(
                1 for row in rows if row["current_placeholder_contract_valid"]
            ),
            "output_contract_shape_valid_count": sum(
                1 for row in rows if row["output_contract_shape_valid"]
            ),
            "bridge_probe_ready_count": sum(
                1 for row in rows if row["bridge_validation"].get("final_score_target_ready")
            ),
            "bridge_probe_blocked_count": sum(
                1 for row in rows if not row["bridge_validation"].get("final_score_target_ready")
            ),
            "deterministic_known_draft_allowed_count": 0,
            "review_required_count": len(rows),
            "production_write_allowed_count": 0,
            "safe_to_upsert_without_review_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share non-manual candidate readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Non-manual tasks: `{summary['non_manual_task_count']}`",
        f"- Placeholder contracts valid: `{summary['placeholder_contract_valid_count']}`",
        f"- Output contract shapes valid: `{summary['output_contract_shape_valid_count']}`",
        f"- Bridge probes ready: `{summary['bridge_probe_ready_count']}`",
        f"- Deterministic Known drafts allowed: `{summary['deterministic_known_draft_allowed_count']}`",
        f"- Safe to upsert without review: `{summary['safe_to_upsert_without_review_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Route Bucket Counts",
        "",
        "| Bucket | Count |",
        "|---|---:|",
    ]
    for bucket, count in summary["route_bucket_counts"].items():
        lines.append(f"| `{bucket}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | kind | target | route bucket | dependency readiness | bridge probe |",
            "|---|---|---|---|---|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['generator_kind']}` | "
            f"`{row['score_target']}` | "
            f"`{row['route_bucket']}` | "
            f"`{row['dependency_readiness']}` | "
            f"{'yes' if row['bridge_validation'].get('final_score_target_ready') else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This audit proves input readiness and bridge-contract reachability only.",
            "- It deliberately emits 0 deterministic Known drafts because these local/event rows still need governed LLM or policy review to assign business direction and magnitude.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-path", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.queue_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
