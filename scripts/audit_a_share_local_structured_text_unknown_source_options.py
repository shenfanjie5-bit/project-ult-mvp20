#!/usr/bin/env python3
"""Classify source options for local structured-text A-share Unknown drafts.

The structured-text pilot keeps three fields Unknown because the runtime
dependencies combine financial rows with QA/IR text that has not been
classified into the target business concept. This audit records the available
evidence and the text-classification routes required before reviewable Known
packets can be produced.
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

from scripts.audit_a_share_local_single_dependency_policy_drafts import (
    DEFAULT_CANDIDATE_PATH,
    ROOT,
    _candidate_rows_by_dp,
    _load_json,
    _portable_path,
)


DEFAULT_LOCAL_STRUCTURED_TEXT_PATH = (
    ROOT / "docs/audit/a_share_local_structured_text_policy_drafts_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_text_unknown_source_options_2026-06-19.md"
)


SOURCE_OPTION_POLICIES: dict[str, dict[str, Any]] = {
    "L0.demand.user_count": {
        "resolution_status": "requires_customer_user_text_classification",
        "dependency_limit": (
            "Revenue is not a customer/user count, and recent QA samples often describe "
            "shareholder counts or investor relations topics that must not be treated as demand."
        ),
        "required_evidence": [
            "customer or active-user count",
            "order/user volume disclosure",
            "installed base or reviewed customer-count extraction",
        ],
        "overlay_candidate_dp_ids": ["L4.volume.users", "L4.volume.orders"],
        "candidate_source_routes": [
            "classify L9.disclosure.qa_recent for customer/user/order-count evidence",
            "extract annual-report customer/revenue sections when they disclose user base",
            "map overlay volume/user nodes only when reviewed evidence exists",
        ],
    },
    "L0.price.discount": {
        "resolution_status": "requires_discount_pricing_text_classification",
        "dependency_limit": (
            "Gross margin is an outcome metric, not direct discount pressure; QA text must "
            "be classified for pricing, rebate, promotion, or customer negotiation evidence."
        ),
        "required_evidence": [
            "direct discount or rebate commentary",
            "pricing pressure / promotion language",
            "reviewed gross-margin decomposition by price versus cost",
        ],
        "overlay_candidate_dp_ids": [
            "L0.price.discount",
            "L0.compete.price_war",
            "L0.price.pricing_power",
        ],
        "candidate_source_routes": [
            "classify L9.disclosure.qa_recent for discount/pricing-pressure evidence",
            "extract filing MD&A pricing/margin commentary",
            "join reviewed gross-margin decomposition only after price/cost attribution",
        ],
    },
    "L0.supply.channel_service": {
        "resolution_status": "requires_channel_service_text_classification",
        "dependency_limit": (
            "SGA/R&D burden can proxy go-to-market or support spend, but it does not prove "
            "channel/service capacity, delivery capability, or support quality."
        ),
        "required_evidence": [
            "channel capacity or partner/service network evidence",
            "delivery, maintenance, or support-quality disclosure",
            "reviewed service/channel KPI extraction",
        ],
        "overlay_candidate_dp_ids": ["L0.supply.channel_service", "L4.share.customer_channel"],
        "candidate_source_routes": [
            "classify L9.disclosure.qa_recent for channel/service evidence",
            "extract annual-report channel/service network descriptions",
            "map customer-channel overlays only with reviewed source evidence",
        ],
    },
}


def _unknown_text_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        payload = row.get("draft_payload")
        if isinstance(payload, Mapping) and payload.get("data_status") == "Unknown":
            rows.append(row)
    return rows


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
        qa_sample_count = 0
        qa_item_count = 0
        for sample in dep.get("sample_rows") or []:
            if not isinstance(sample, Mapping):
                continue
            compact = sample.get("value_json_compact")
            if not isinstance(compact, Mapping):
                continue
            for key in compact:
                if key not in sample_keys:
                    sample_keys.append(str(key))
            top_qa = compact.get("top_qa")
            if isinstance(top_qa, list):
                qa_sample_count += 1
                qa_item_count += sum(1 for item in top_qa if isinstance(item, Mapping))
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
                "qa_sample_count": qa_sample_count,
                "qa_item_count": qa_item_count,
            }
        )
    return records


def _payload_value(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("draft_payload")
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get("value_json")
    return value if isinstance(value, Mapping) else {}


def _has_qa_dependency(dependencies: list[dict[str, Any]]) -> bool:
    return any(dep.get("dp_id") == "L9.disclosure.qa_recent" for dep in dependencies)


def build_report(local_structured_text_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    local_structured_text = _load_json(local_structured_text_path)
    candidates = _candidate_rows_by_dp(_load_json(candidate_path))
    rows: list[dict[str, Any]] = []

    for source_row in _unknown_text_rows(local_structured_text):
        dp_id = str(source_row.get("dp_id") or "")
        score_target = str(source_row.get("score_target") or "")
        policy = SOURCE_OPTION_POLICIES.get(dp_id, {})
        candidate_row = candidates.get(dp_id)
        dependencies = _dependency_records(candidate_row)
        runtime_dependency_ready = bool(dependencies) and all(
            dep["row_count"] > 0 and dep["known_count"] > 0 for dep in dependencies
        )
        qa_dependency_ready = _has_qa_dependency(dependencies) and any(
            dep["dp_id"] == "L9.disclosure.qa_recent"
            and dep["row_count"] > 0
            and dep["known_count"] > 0
            for dep in dependencies
        )
        value_json = _payload_value(source_row)
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "draft_status": source_row.get("draft_status"),
                "blocked_reason": value_json.get("blocked_reason"),
                "required_policy": value_json.get("required_policy"),
                "candidate_status": candidate_row.get("candidate_status") if candidate_row else None,
                "source_dependencies": candidate_row.get("source_dependencies") if candidate_row else [],
                "runtime_dependency_ready": runtime_dependency_ready,
                "qa_recent_dependency_ready": qa_dependency_ready,
                "runtime_dependency_summary": dependencies,
                "direct_text_classification_ready": False,
                "direct_text_classification_reason": (
                    "QA/IR text is available, but it is not classified into the target "
                    "business field and includes non-target investor-relations topics."
                ),
                "dependency_limit": policy.get("dependency_limit", "No reviewed source-option policy is defined."),
                "required_evidence": list(policy.get("required_evidence") or []),
                "overlay_candidate_dp_ids": list(policy.get("overlay_candidate_dp_ids") or []),
                "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
                "resolution_status": policy.get("resolution_status", "requires_text_classification_policy"),
                "text_classification_required": True,
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
        "local_structured_text_path": _portable_path(local_structured_text_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "unknown_local_structured_text_count": len(rows),
            "existing_runtime_dependency_ready_count": sum(
                1 for row in rows if row["runtime_dependency_ready"]
            ),
            "qa_recent_dependency_ready_count": sum(
                1 for row in rows if row["qa_recent_dependency_ready"]
            ),
            "direct_text_classification_ready_count": sum(
                1 for row in rows if row["direct_text_classification_ready"]
            ),
            "overlay_candidate_hint_count": sum(
                1 for row in rows if row["overlay_candidate_dp_ids"]
            ),
            "candidate_requires_text_classification_count": sum(
                1 for row in rows if row["text_classification_required"]
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
        "# A-share local structured-text Unknown source options",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown local structured-text rows: `{summary['unknown_local_structured_text_count']}`",
        f"- Runtime dependencies ready: `{summary['existing_runtime_dependency_ready_count']}`",
        f"- QA recent dependencies ready: `{summary['qa_recent_dependency_ready_count']}`",
        f"- Direct text classification-ready rows: `{summary['direct_text_classification_ready_count']}`",
        f"- Overlay/source hints: `{summary['overlay_candidate_hint_count']}`",
        f"- Text classification required: `{summary['candidate_requires_text_classification_count']}`",
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
            "| dp_id | runtime deps | QA ready | classification ready | overlay hints | status | production write |",
            "|---|---:|---:|---:|---:|---|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['runtime_dependency_ready'] else 'no'} | "
            f"{'yes' if row['qa_recent_dependency_ready'] else 'no'} | "
            f"{'yes' if row['direct_text_classification_ready'] else 'no'} | "
            f"{len(row['overlay_candidate_dp_ids'])} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- QA/IR text is present, but it has not been classified into customer/user, discount/pricing-pressure, or channel/service evidence.",
            "- Shareholder-count and generic investor-relations answers must be filtered out before any Known packet is drafted.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-structured-text-path",
        type=Path,
        default=DEFAULT_LOCAL_STRUCTURED_TEXT_PATH,
    )
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.local_structured_text_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
