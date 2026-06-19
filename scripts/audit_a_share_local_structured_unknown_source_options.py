#!/usr/bin/env python3
"""Classify source options for local-structured A-share Unknown drafts.

The local structured pilot keeps five fields Unknown because their current
runtime dependencies are known but semantically insufficient. This audit is
read-only: it records what the current runtime evidence can support, what
source routes could close each field, and which review gate is still required.
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


DEFAULT_LOCAL_STRUCTURED_PATH = (
    ROOT / "docs/audit/a_share_local_structured_policy_drafts_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.md"
)


SOURCE_OPTION_POLICIES: dict[str, dict[str, Any]] = {
    "L0.cost.rent": {
        "resolution_status": "requires_new_field_mapping_or_text_extraction",
        "new_mapping_required": True,
        "reviewed_policy_required": False,
        "dependency_limit": (
            "PPE, goodwill, and capex show asset intensity but do not identify rent, lease, "
            "store, logistics, or energy burden."
        ),
        "required_evidence": [
            "lease or rent expense",
            "store/logistics/energy cost split",
            "reviewed asset-light policy when direct rent expense is unavailable",
        ],
        "overlay_candidate_dp_ids": ["L4.cost.rent_energy_logistics"],
        "candidate_source_routes": [
            "extend structured filing extraction for lease/rent expense",
            "map existing overlay node L4.cost.rent_energy_logistics where reviewed evidence exists",
            "extract management discussion / annual report / exchange Q&A cost disclosures",
        ],
    },
    "L0.demand.frequency": {
        "resolution_status": "requires_volume_or_usage_source",
        "new_mapping_required": True,
        "reviewed_policy_required": False,
        "dependency_limit": (
            "Revenue and revenue growth do not separate price, volume, order count, repeat "
            "rate, or usage cadence."
        ),
        "required_evidence": [
            "order, transaction, shipment, or usage frequency",
            "active user / customer base with repeat cadence",
            "reviewed decomposition separating volume cadence from ASP",
        ],
        "overlay_candidate_dp_ids": [
            "L4.volume.frequency",
            "L4.volume.orders",
            "L4.volume.sales",
            "L4.volume.shipments",
            "L4.volume.users",
        ],
        "candidate_source_routes": [
            "map volume/order/user overlay nodes when present",
            "extract order and usage cadence from exchange Q&A or filing text",
            "join product-segment volume disclosures when available",
        ],
    },
    "L0.demand.penetration": {
        "resolution_status": "requires_market_share_or_tam_source",
        "new_mapping_required": True,
        "reviewed_policy_required": False,
        "dependency_limit": (
            "Revenue and revenue growth do not identify TAM, installed base, customer "
            "penetration, or market share."
        ),
        "required_evidence": [
            "market share",
            "TAM or addressable customer base",
            "installed base or penetration denominator",
        ],
        "overlay_candidate_dp_ids": [
            "L1.position.market_share",
            "L4.share.market",
            "L4.share.substitution",
        ],
        "candidate_source_routes": [
            "map market-share overlay nodes where reviewed evidence exists",
            "extract TAM/share statements from filings, research notes, or exchange Q&A",
            "join industry dataset denominators when a governed source is added",
        ],
    },
    "L0.price.contract_spot": {
        "resolution_status": "requires_reviewed_pass_through_policy",
        "new_mapping_required": False,
        "reviewed_policy_required": True,
        "dependency_limit": (
            "Raw-material futures and gross margin are available, but a governed "
            "pass-through policy is required before converting the industry join into Known."
        ),
        "required_evidence": [
            "reviewed industry-to-stock grain join",
            "raw-material pass-through direction and bounds",
            "contract-vs-spot pricing policy",
        ],
        "overlay_candidate_dp_ids": ["L0.price.contract_spot", "L0.cost.raw_material"],
        "candidate_source_routes": [
            "review and approve current grain_join_policy for stocks with both sides present",
            "extend raw-material industry coverage for currently unmapped A-share stocks",
            "extract contract/spot pricing disclosures from filings or exchange Q&A",
        ],
    },
    "L0.price.product_asp": {
        "resolution_status": "requires_volume_mix_or_price_index",
        "new_mapping_required": True,
        "reviewed_policy_required": False,
        "dependency_limit": (
            "Revenue and gross margin cannot identify unit ASP without product volume, mix, "
            "or a governed external price index."
        ),
        "required_evidence": [
            "unit volume or shipment volume",
            "product mix split",
            "reviewed price index or segment ASP disclosure",
        ],
        "overlay_candidate_dp_ids": [
            "L0.price.product_asp",
            "L4.volume.sales",
            "L4.volume.orders",
            "L4.volume.shipments",
            "L4.volume.users",
        ],
        "candidate_source_routes": [
            "map product volume/mix overlay nodes when reviewed evidence exists",
            "extract Tushare fina_mainbz product revenue with volume/mix text where available",
            "join governed product price index or exchange Q&A ASP disclosures",
        ],
    },
}


def _unknown_local_structured_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
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
    records: list[dict[str, Any]] = []
    dependency_evidence = candidate_row.get("dependency_evidence")
    if not isinstance(dependency_evidence, Mapping):
        dependency_evidence = {}
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
                if key not in sample_keys:
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


def _grain_join_summary(candidate_row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate_row, Mapping):
        return {}
    candidate_input = candidate_row.get("candidate_input")
    if not isinstance(candidate_input, Mapping):
        return {}
    grain = candidate_input.get("grain_join_policy")
    if not isinstance(grain, Mapping):
        return {}
    return {
        "universe_path": grain.get("universe_path"),
        "a_share_universe_count": int(grain.get("a_share_universe_count") or 0),
        "raw_material_industry_count": int(grain.get("raw_material_industry_count") or 0),
        "known_gross_margin_a_share_count": int(grain.get("known_gross_margin_a_share_count") or 0),
        "join_ready_a_share_count": int(grain.get("join_ready_a_share_count") or 0),
        "missing_raw_material_a_share_count": int(grain.get("missing_raw_material_a_share_count") or 0),
        "missing_gross_margin_a_share_count": int(grain.get("missing_gross_margin_a_share_count") or 0),
    }


def _payload_value(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("draft_payload")
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get("value_json")
    return value if isinstance(value, Mapping) else {}


def build_report(local_structured_path: Path, candidate_path: Path) -> dict[str, Any]:
    started = time.time()
    local_structured = _load_json(local_structured_path)
    candidates = _candidate_rows_by_dp(_load_json(candidate_path))
    rows: list[dict[str, Any]] = []

    for source_row in _unknown_local_structured_rows(local_structured):
        dp_id = str(source_row.get("dp_id") or "")
        score_target = str(source_row.get("score_target") or "")
        policy = SOURCE_OPTION_POLICIES.get(dp_id, {})
        candidate_row = candidates.get(dp_id)
        dependencies = _dependency_records(candidate_row)
        runtime_dependency_ready = bool(dependencies) and all(
            dep["row_count"] > 0 and dep["known_count"] > 0 for dep in dependencies
        )
        grain_join_policy = _grain_join_summary(candidate_row)
        partial_known_unlock_candidate = bool(
            policy.get("reviewed_policy_required")
            and grain_join_policy.get("join_ready_a_share_count", 0) > 0
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
                "runtime_dependency_summary": dependencies,
                "direct_existing_structured_source_ready": False,
                "direct_existing_structured_source_reason": (
                    "Current structured runtime dependencies are material, but they do not contain "
                    "the target business field directly."
                ),
                "dependency_limit": policy.get("dependency_limit", "No reviewed source-option policy is defined."),
                "required_evidence": list(policy.get("required_evidence") or []),
                "overlay_candidate_dp_ids": list(policy.get("overlay_candidate_dp_ids") or []),
                "candidate_source_routes": list(policy.get("candidate_source_routes") or []),
                "resolution_status": policy.get("resolution_status", "requires_reviewed_source_policy"),
                "new_mapping_required": bool(policy.get("new_mapping_required")),
                "reviewed_policy_required": bool(policy.get("reviewed_policy_required")),
                "grain_join_policy": grain_join_policy,
                "partial_known_unlock_candidate": partial_known_unlock_candidate,
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
        "local_structured_path": _portable_path(local_structured_path),
        "candidate_path": _portable_path(candidate_path),
        "summary": {
            "unknown_local_structured_count": len(rows),
            "existing_runtime_dependency_ready_count": sum(
                1 for row in rows if row["runtime_dependency_ready"]
            ),
            "direct_existing_structured_source_ready_count": sum(
                1 for row in rows if row["direct_existing_structured_source_ready"]
            ),
            "overlay_candidate_hint_count": sum(
                1 for row in rows if row["overlay_candidate_dp_ids"]
            ),
            "candidate_requires_new_mapping_count": sum(
                1 for row in rows if row["new_mapping_required"]
            ),
            "candidate_requires_review_policy_count": sum(
                1 for row in rows if row["reviewed_policy_required"]
            ),
            "partial_known_unlock_candidate_count": sum(
                1 for row in rows if row["partial_known_unlock_candidate"]
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
        "# A-share local structured Unknown source options",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown local structured rows: `{summary['unknown_local_structured_count']}`",
        f"- Runtime dependencies ready: `{summary['existing_runtime_dependency_ready_count']}`",
        f"- Direct structured source-ready rows: `{summary['direct_existing_structured_source_ready_count']}`",
        f"- Overlay/source hints: `{summary['overlay_candidate_hint_count']}`",
        f"- New mapping or text extraction required: `{summary['candidate_requires_new_mapping_count']}`",
        f"- Reviewed policy required: `{summary['candidate_requires_review_policy_count']}`",
        f"- Partial Known unlock candidates: `{summary['partial_known_unlock_candidate_count']}`",
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
            "| dp_id | runtime deps | direct source ready | overlay hints | status | partial unlock | production write |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['runtime_dependency_ready'] else 'no'} | "
            f"{'yes' if row['direct_existing_structured_source_ready'] else 'no'} | "
            f"{len(row['overlay_candidate_dp_ids'])} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['partial_known_unlock_candidate'] else 'no'} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Current runtime dependencies are useful evidence packs, but none directly contains the target business field.",
            "- Four rows need new mapped fields or text extraction before Known output is defensible.",
            "- `L0.price.contract_spot` can move first after a reviewed grain-join/pass-through policy because the current candidate evidence already has a partial join-ready set.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local-structured-path",
        type=Path,
        default=DEFAULT_LOCAL_STRUCTURED_PATH,
    )
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.local_structured_path, args.candidate_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
