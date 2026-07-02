#!/usr/bin/env python3
"""Build an acquisition backlog for remaining A-share Unknown score gaps.

This report is read-only. It converts the Unknown closure matrix into concrete
source-acquisition tasks with acceptance criteria, rejected evidence classes,
and write-safety gates.
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
DEFAULT_CLOSURE_MATRIX_PATH = (
    ROOT / "docs/audit/a_share_unknown_closure_matrix_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.md"
)


TASK_POLICY_BY_DP: dict[str, dict[str, Any]] = {
    "L0.compete.new_entrant": {
        "acquisition_track": "dockcase_market_doc_deep_search",
        "source_priority": "market_doc_direct_transmission",
        "required_source_types": [
            "DOCKCASE market news or announcement body",
            "same-sentence or same-paragraph new-entrant evidence",
            "explicit A-share, listed-company, sector, supply-chain, trade, or policy transmission link",
        ],
        "rejected_evidence": [
            "broad market commentary without a direct transmission path",
            "new product launch text that does not imply a new entrant",
            "headline-only target hit without body evidence",
        ],
        "next_local_action": (
            "Search DOCKCASE market documents with new-entrant target terms plus "
            "direct A-share transmission terms, then retain only same-sentence or "
            "same-paragraph matches."
        ),
        "next_external_action": (
            "If local market documents still lack a direct link, crawl company "
            "announcements, industry association notes, and exchange Q&A for named "
            "entrant-to-A-share transmission evidence."
        ),
    },
    "L0.tech.substitute_tech": {
        "acquisition_track": "dockcase_market_doc_deep_search",
        "source_priority": "market_doc_clean_substitution_risk",
        "required_source_types": [
            "DOCKCASE market news or announcement body",
            "same-sentence substitute-technology risk evidence",
            "explicit A-share company, industry, board, or supply-chain transmission path",
        ],
        "rejected_evidence": [
            "domestic import-substitution opportunity framed as upside",
            "foreign macro substitution or trade-law replacement without A-share impact",
            "broad technology commentary without company or industry transmission",
        ],
        "next_local_action": (
            "Re-screen the 34 same-sentence target/direct matches and keep only "
            "substitution-risk examples that threaten A-share industries or companies."
        ),
        "next_external_action": (
            "Use web or announcement crawl only if the retained local snippets cannot "
            "produce two clean substitution-risk examples."
        ),
    },
    "L0.cost.rent": {
        "acquisition_track": "local_structured_formula_source",
        "source_priority": "lease_burden_formula_inputs",
        "required_source_types": [
            "Tushare/DOCKCASE cash-flow, balance-sheet, lease-note, or annual-report field",
            "rent expense, lease payment, lease liability, revenue, or total-cost denominator",
            "reviewed conservative lease-burden proxy formula and bounds",
        ],
        "rejected_evidence": [
            "asset-heavy proxy without lease-specific semantics",
            "empty lease-payment field",
            "formula that cannot convert into bounded numeric value_json",
        ],
        "next_local_action": (
            "Review use_right_asset_dep against lease-liability, revenue, operating "
            "cash flow, or total-cost denominators before treating it as a proxy."
        ),
        "next_external_action": (
            "Extract rent, lease payment, right-of-use asset, or lease liability "
            "disclosures from annual reports or exchange replies when local tables "
            "lack the denominator."
        ),
    },
    "L0.price.product_asp": {
        "acquisition_track": "local_structured_formula_source",
        "source_priority": "product_quantity_or_price_index",
        "required_source_types": [
            "Tushare fina_mainbz/DOCKCASE business-segment revenue fields",
            "unit volume, shipment volume, product quantity, or governed price index",
            "reviewed mapping from business segment row to ASP-bearing product",
        ],
        "rejected_evidence": [
            "product revenue without quantity or price index",
            "geographic or industry segment row treated as product ASP",
            "gross margin or profit used as standalone ASP",
        ],
        "next_local_action": (
            "Use bz_item and bz_sales only as product/mix and numerator context; "
            "search local disclosures for unit, shipment, volume, or price-index "
            "fields before calculating ASP."
        ),
        "next_external_action": (
            "Extract product sales volume, production/sales/inventory tables, or "
            "governed industry price indexes from annual reports, announcements, "
            "exchange Q&A, and industry sources."
        ),
    },
    "L0.demand.frequency": {
        "acquisition_track": "external_or_text_business_metric",
        "source_priority": "customer_order_usage_cadence",
        "required_source_types": [
            "order count, transaction count, shipment frequency, or usage cadence source",
            "active customer, user, channel, or installed-base denominator when normalized",
            "reviewed decomposition separating cadence from ASP and revenue growth",
        ],
        "rejected_evidence": [
            "revenue growth used as purchase frequency",
            "order backlog without cadence or denominator",
            "market activity indicator unrelated to company customer usage",
        ],
        "next_local_action": (
            "Search local structured and text sources for orders, transactions, "
            "shipments, active users, or channel cadence before using revenue-derived "
            "context."
        ),
        "next_external_action": (
            "Collect order, transaction, shipment, usage, MAU/DAU, active-customer, "
            "or channel-frequency disclosures from reports, Q&A, announcements, or "
            "industry datasets."
        ),
    },
    "L0.demand.penetration": {
        "acquisition_track": "external_or_text_business_metric",
        "source_priority": "market_denominator_and_company_numerator",
        "required_source_types": [
            "market share, TAM, installed base, user base, or governed industry denominator",
            "company numerator mapped to the same market denominator",
            "reviewed source precedence and bounded penetration formula",
        ],
        "rejected_evidence": [
            "company revenue without comparable market denominator",
            "industry total from a different geography, unit, or product scope",
            "shareholder, index, trading, or sentiment fields used as penetration",
        ],
        "next_local_action": (
            "Search local industry reports and structured data for denominator fields "
            "that can be matched to company revenue, installed base, or users."
        ),
        "next_external_action": (
            "Collect market-size, TAM, installed-base, user-base, shipment-share, "
            "or market-share data from annual reports, industry reports, exchange Q&A, "
            "or governed public datasets."
        ),
    },
    "L0.demand.replacement": {
        "acquisition_track": "external_or_text_business_metric",
        "source_priority": "lifecycle_or_replacement_cycle",
        "required_source_types": [
            "product lifecycle, launch/refresh cadence, installed base, or active fleet/source stock",
            "replacement cycle months/years, renewal trend, or maintenance replacement evidence",
            "reviewed policy separating replacement demand from new demand and revenue scalar",
        ],
        "rejected_evidence": [
            "revenue alone",
            "shipment growth without replacement/new-demand split",
            "industry graph prior used as automatic Known value",
        ],
        "next_local_action": (
            "Search overlays and local text for lifecycle, installed-base, renewal, "
            "maintenance, replacement cycle, shipment, order, and user-stock evidence."
        ),
        "next_external_action": (
            "Collect product lifecycle, installed-base, renewal-cycle, fleet/device "
            "stock, or channel replacement disclosures from annual reports, exchange "
            "Q&A, announcements, and industry datasets."
        ),
    },
}


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


def _candidate_signal_count(row: Mapping[str, Any]) -> int:
    evidence = row.get("current_best_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    count = 0
    count += len(evidence.get("candidate_columns") or [])
    count += int(evidence.get("candidate_example_count") or 0)
    return count


def _overlay_hint_count(row: Mapping[str, Any]) -> int:
    evidence = row.get("current_best_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    return len(evidence.get("overlay_candidate_dp_ids") or [])


def _blocking_input_count(row: Mapping[str, Any]) -> int:
    evidence = row.get("current_best_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    missing = evidence.get("missing_formula_inputs") or []
    if missing:
        return len(missing)
    required = evidence.get("required_evidence") or row.get("minimum_unlock_evidence") or []
    if row.get("closure_track") == "market_document_event_evidence":
        return max(1, len(required))
    if row.get("closure_blocker_class") == "lifecycle_source_and_policy_required":
        return len(required)
    return len(required)


def _requires_web_or_external(row: Mapping[str, Any]) -> bool:
    track = row.get("closure_track")
    if track == "external_or_text_business_metric":
        return True
    if track == "local_structured_formula_review":
        return True
    if row.get("closure_blocker_class") == "direct_event_transmission_evidence_required":
        return True
    return False


def _task(row: Mapping[str, Any]) -> dict[str, Any]:
    dp_id = str(row.get("dp_id") or "")
    policy = TASK_POLICY_BY_DP.get(dp_id, {})
    source_dependencies = list(row.get("source_dependencies") or [])
    evidence_refs = list(row.get("evidence_refs") or [])
    candidate_signal_count = _candidate_signal_count(row)
    overlay_hint_count = _overlay_hint_count(row)
    acquisition_track = str(policy.get("acquisition_track") or "unknown_acquisition")
    return {
        "task_id": f"ashare_unknown_acquire_{dp_id.replace('.', '_')}",
        "dp_id": dp_id,
        "score_target": row.get("score_target"),
        "data_status": "Unknown",
        "closure_track": row.get("closure_track"),
        "closure_blocker_class": row.get("closure_blocker_class"),
        "next_action_bucket": row.get("next_action_bucket"),
        "acquisition_track": acquisition_track,
        "source_priority": policy.get("source_priority", "unclassified"),
        "required_source_types": policy.get("required_source_types") or [],
        "acceptable_evidence": list(row.get("minimum_unlock_evidence") or [])
        + list(policy.get("required_source_types") or []),
        "rejected_evidence": policy.get("rejected_evidence") or [],
        "current_candidate_signal_count": candidate_signal_count,
        "runtime_overlay_hint_count": overlay_hint_count,
        "has_existing_candidate_evidence": candidate_signal_count > 0,
        "has_runtime_overlay_hints": overlay_hint_count > 0,
        "blocking_input_count": _blocking_input_count(row),
        "source_dependencies": source_dependencies,
        "evidence_refs": evidence_refs,
        "next_local_action": policy.get("next_local_action"),
        "next_external_action": policy.get("next_external_action"),
        "llm_allowed": True,
        "llm_use": "classification, extraction, and reviewer-draft generation only",
        "web_or_external_acquisition_required": _requires_web_or_external(row),
        "formula_inputs_ready": bool(
            (row.get("current_best_evidence") or {}).get("formula_inputs_ready")
        ),
        "ready_for_auto_known": False,
        "ready_for_approval": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "source_mutation_allowed": False,
    }


def _validation_errors(task: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not task.get("task_id"):
        errors.append("task_id is required")
    if not task.get("dp_id"):
        errors.append("dp_id is required")
    if task.get("data_status") != "Unknown":
        errors.append("acquisition tasks must keep data_status Unknown")
    if not task.get("acquisition_track"):
        errors.append("acquisition_track is required")
    if not task.get("required_source_types"):
        errors.append("required_source_types is required")
    if not task.get("acceptable_evidence"):
        errors.append("acceptable_evidence is required")
    if not task.get("rejected_evidence"):
        errors.append("rejected_evidence is required")
    if not task.get("next_local_action"):
        errors.append("next_local_action is required")
    if not task.get("next_external_action"):
        errors.append("next_external_action is required")
    if task.get("ready_for_auto_known") is not False:
        errors.append("ready_for_auto_known must be false")
    if task.get("ready_for_approval") is not False:
        errors.append("ready_for_approval must be false")
    if task.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if task.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if task.get("source_mutation_allowed") is not False:
        errors.append("source_mutation_allowed must be false")
    return errors


def build_report(*, closure_matrix_path: Path) -> dict[str, Any]:
    started = time.time()
    closure_matrix = _load_json(closure_matrix_path)
    rows = []
    for closure_row in closure_matrix.get("rows") or []:
        if not isinstance(closure_row, Mapping):
            continue
        task = _task(closure_row)
        errors = _validation_errors(task)
        task["task_contract_valid"] = not errors
        task["task_validation_errors"] = errors
        rows.append(task)
    rows.sort(key=lambda row: (str(row["acquisition_track"]), str(row["dp_id"])))

    track_counts = Counter(str(row["acquisition_track"]) for row in rows)
    blocker_counts = Counter(str(row["closure_blocker_class"]) for row in rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "closure_matrix_path": _portable_path(closure_matrix_path),
        },
        "summary": {
            "acquisition_task_count": len(rows),
            "unknown_acquisition_task_count": len(rows),
            "event_doc_search_task_count": track_counts.get(
                "dockcase_market_doc_deep_search", 0
            ),
            "local_formula_source_task_count": track_counts.get(
                "local_structured_formula_source", 0
            ),
            "external_business_source_task_count": track_counts.get(
                "external_or_text_business_metric", 0
            ),
            "tasks_with_existing_candidate_evidence_count": sum(
                1 for row in rows if row["has_existing_candidate_evidence"]
            ),
            "tasks_with_runtime_overlay_hints_count": sum(
                1 for row in rows if row["has_runtime_overlay_hints"]
            ),
            "web_or_external_acquisition_required_count": sum(
                1 for row in rows if row["web_or_external_acquisition_required"]
            ),
            "llm_allowed_count": sum(1 for row in rows if row["llm_allowed"]),
            "formula_inputs_ready_count": sum(
                1 for row in rows if row["formula_inputs_ready"]
            ),
            "ready_for_auto_known_count": sum(
                1 for row in rows if row["ready_for_auto_known"]
            ),
            "ready_for_approval_count": sum(
                1 for row in rows if row["ready_for_approval"]
            ),
            "task_contract_valid_count": sum(
                1 for row in rows if row["task_contract_valid"]
            ),
            "task_contract_invalid_count": sum(
                1 for row in rows if not row["task_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "source_mutation_allowed_count": 0,
            "acquisition_track_counts": dict(sorted(track_counts.items())),
            "closure_blocker_class_counts": dict(sorted(blocker_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown acquisition backlog",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Acquisition tasks: `{summary['acquisition_task_count']}`",
        f"- Event document search tasks: `{summary['event_doc_search_task_count']}`",
        f"- Local formula source tasks: `{summary['local_formula_source_task_count']}`",
        f"- External/text business source tasks: `{summary['external_business_source_task_count']}`",
        f"- Tasks with existing candidate evidence: `{summary['tasks_with_existing_candidate_evidence_count']}`",
        f"- Tasks with runtime overlay hints: `{summary['tasks_with_runtime_overlay_hints_count']}`",
        f"- Web/external acquisition required: `{summary['web_or_external_acquisition_required_count']}`",
        f"- LLM allowed tasks: `{summary['llm_allowed_count']}`",
        f"- Formula inputs ready: `{summary['formula_inputs_ready_count']}`",
        f"- Auto Known-ready tasks: `{summary['ready_for_auto_known_count']}`",
        f"- Approval-ready tasks: `{summary['ready_for_approval_count']}`",
        f"- Valid task contracts: `{summary['task_contract_valid_count']}`",
        f"- Invalid task contracts: `{summary['task_contract_invalid_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Source mutations allowed: `{summary['source_mutation_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Tasks",
        "",
        "| task | acquisition track | current evidence | blocking inputs | write allowed |",
        "|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['acquisition_track']}` | "
            f"{row['current_candidate_signal_count']} | "
            f"{row['blocking_input_count']} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The backlog is source acquisition only; no task can write to runtime scoring.",
            "- Event-document tasks must prove direct A-share transmission before a Known packet can be drafted.",
            "- Local structured formula tasks need complete numeric formula inputs, not just supporting columns.",
            "- External/text business-metric tasks need business denominators or cadence/lifecycle evidence before scoring.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--closure-matrix-path",
        type=Path,
        default=DEFAULT_CLOSURE_MATRIX_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(closure_matrix_path=args.closure_matrix_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
