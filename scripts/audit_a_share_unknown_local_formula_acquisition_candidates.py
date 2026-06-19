#!/usr/bin/env python3
"""Screen local structured formula inputs for A-share Unknown acquisition tasks.

This read-only audit executes the local-structured formula portion of the
Unknown acquisition backlog. It checks whether candidate DOCKCASE/Tushare
columns cover the formula inputs needed for rent burden and product ASP.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_BACKLOG_PATH = (
    ROOT / "docs/audit/a_share_unknown_acquisition_backlog_2026-06-19.json"
)
DEFAULT_SOURCE_REVIEW_PATH = (
    ROOT / "docs/audit/a_share_local_structured_source_review_packets_2026-06-19.json"
)
DEFAULT_UNKNOWN_OPTIONS_PATH = (
    ROOT / "docs/audit/a_share_local_structured_unknown_source_options_2026-06-19.json"
)
DEFAULT_DATA_ROOT = Path("/Volumes/dockcase2tb/database_all")
DEFAULT_JSON_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT
    / "docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.md"
)

LOCAL_FORMULA_DP_IDS = {"L0.cost.rent", "L0.price.product_asp"}
GEOGRAPHY_TERMS = ("国外", "中国大陆", "境内", "境外", "海外", "地区")
INDUSTRY_TERMS = ("行业", "业务", "服务")


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _tasks(backlog: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in backlog.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("dp_id") not in LOCAL_FORMULA_DP_IDS:
            continue
        if row.get("acquisition_track") != "local_structured_formula_source":
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return rows


def _candidate_examples(source_review_row: Mapping[str, Any]) -> list[str]:
    examples: list[str] = []
    for key in ("source_candidate_refs", "empty_candidate_refs"):
        for ref in source_review_row.get(key) or []:
            if isinstance(ref, Mapping):
                examples.extend(str(item) for item in ref.get("examples") or [])
    examples.extend(str(item) for item in source_review_row.get("source_examples") or [])
    out: list[str] = []
    seen: set[str] = set()
    for item in examples:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out[:8]


def _read_csv_evidence(
    *,
    data_root: Path,
    relative_paths: Iterable[str],
    columns: Iterable[str],
    max_rows_per_file: int = 12,
) -> dict[str, Any]:
    columns = list(columns)
    files_checked = 0
    files_existing = 0
    rows_sampled = 0
    column_non_empty = {column: 0 for column in columns}
    column_present_files = {column: 0 for column in columns}
    bz_item_samples: list[str] = []
    read_errors: list[str] = []
    for relative_path in relative_paths:
        files_checked += 1
        path = data_root / relative_path
        if not path.exists():
            continue
        files_existing += 1
        try:
            with path.open(encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = set(reader.fieldnames or [])
                for column in columns:
                    if column in fieldnames:
                        column_present_files[column] += 1
                for index, row in enumerate(reader):
                    if index >= max_rows_per_file:
                        break
                    rows_sampled += 1
                    for column in columns:
                        value = str(row.get(column) or "").strip()
                        if value:
                            column_non_empty[column] += 1
                    item = str(row.get("bz_item") or "").strip()
                    if item and item not in bz_item_samples and len(bz_item_samples) < 20:
                        bz_item_samples.append(item)
        except Exception as exc:  # noqa: BLE001
            read_errors.append(f"{relative_path}: {exc}")
    geography_like = sum(
        1 for item in bz_item_samples if any(term in item for term in GEOGRAPHY_TERMS)
    )
    industry_like = sum(
        1 for item in bz_item_samples if any(term in item for term in INDUSTRY_TERMS)
    )
    product_like = max(0, len(bz_item_samples) - geography_like - industry_like)
    return {
        "files_checked": files_checked,
        "files_existing": files_existing,
        "rows_sampled": rows_sampled,
        "column_present_files": column_present_files,
        "column_non_empty": column_non_empty,
        "bz_item_samples": bz_item_samples,
        "bz_item_product_like_count": product_like,
        "bz_item_geography_like_count": geography_like,
        "bz_item_industry_like_count": industry_like,
        "read_error_count": len(read_errors),
        "read_errors": read_errors[:5],
    }


def _runtime_dependency_ready(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    return bool(row.get("runtime_dependency_ready"))


def _runtime_dependency_count(row: Mapping[str, Any] | None) -> int:
    if not row:
        return 0
    return len(row.get("runtime_dependency_summary") or [])


def _group(name: str, status: str, evidence: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": evidence,
        "blockers": blockers,
        "ready_for_formula": status == "ready",
    }


def _rent_groups(
    *,
    source_review_row: Mapping[str, Any],
    unknown_option_row: Mapping[str, Any] | None,
    csv_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    use_right_non_empty = int(
        (csv_evidence.get("column_non_empty") or {}).get("use_right_asset_dep") or 0
    )
    lease_payment_non_empty = int(
        (csv_evidence.get("column_non_empty") or {}).get("fa_fnc_leases") or 0
    )
    groups = [
        _group(
            "lease_proxy_numerator",
            "review_candidate",
            f"use_right_asset_dep non-empty sample rows={use_right_non_empty}",
            [
                "proxy semantics require review because use-right asset depreciation is not rent expense"
            ],
        ),
        _group(
            "direct_lease_payment",
            "missing",
            f"fa_fnc_leases non-empty sample rows={lease_payment_non_empty}",
            ["direct lease payment/rent expense is empty or absent in sampled files"],
        ),
        _group(
            "denominator",
            "missing",
            f"runtime dependencies ready={_runtime_dependency_ready(unknown_option_row)}; dependency count={_runtime_dependency_count(unknown_option_row)}",
            [
                "current ready runtime dependencies are context only and do not define a reviewed rent-burden denominator"
            ],
        ),
        _group(
            "formula_policy",
            "missing",
            "no reviewed cap/floor or denominator policy in source-review packet",
            ["reviewed conservative proxy policy is required before Known scoring"],
        ),
    ]
    if not source_review_row.get("candidate_columns"):
        groups[0]["status"] = "missing"
        groups[0]["blockers"].append("source-review packet has no candidate column")
    return groups


def _asp_groups(
    *,
    source_review_row: Mapping[str, Any],
    unknown_option_row: Mapping[str, Any] | None,
    csv_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    non_empty = csv_evidence.get("column_non_empty") or {}
    bz_sales_non_empty = int(non_empty.get("bz_sales") or 0)
    quantity_non_empty = sum(
        int(non_empty.get(column) or 0)
        for column in ("unit_volume", "shipment_volume", "product_quantity")
    )
    product_like = int(csv_evidence.get("bz_item_product_like_count") or 0)
    geography_like = int(csv_evidence.get("bz_item_geography_like_count") or 0)
    industry_like = int(csv_evidence.get("bz_item_industry_like_count") or 0)
    groups = [
        _group(
            "product_revenue_numerator",
            "supporting_candidate",
            f"bz_sales non-empty sample rows={bz_sales_non_empty}",
            ["revenue numerator is available but cannot form ASP without volume or price index"],
        ),
        _group(
            "product_mapping",
            "review_required",
            (
                f"bz_item samples product_like={product_like}, "
                f"geography_like={geography_like}, industry_like={industry_like}"
            ),
            [
                "bz_item rows mix product, geography, industry, and other segment labels"
            ],
        ),
        _group(
            "quantity_or_price_index",
            "missing",
            f"unit/shipment/product quantity non-empty sample rows={quantity_non_empty}",
            ["no unit volume, shipment volume, product quantity, or governed price index column is present"],
        ),
        _group(
            "formula_policy",
            "missing",
            f"runtime dependencies ready={_runtime_dependency_ready(unknown_option_row)}; dependency count={_runtime_dependency_count(unknown_option_row)}",
            ["reviewed ASP formula and bounds are required before Known scoring"],
        ),
    ]
    if not source_review_row.get("candidate_columns"):
        groups[0]["status"] = "missing"
        groups[0]["blockers"].append("source-review packet has no supporting columns")
    return groups


def _row(
    *,
    task: Mapping[str, Any],
    source_review_row: Mapping[str, Any],
    unknown_option_row: Mapping[str, Any] | None,
    data_root: Path,
) -> dict[str, Any]:
    dp_id = str(task.get("dp_id") or "")
    columns = list(source_review_row.get("candidate_columns") or [])
    columns.extend(source_review_row.get("empty_candidate_columns") or [])
    if dp_id == "L0.price.product_asp":
        columns.extend(["unit_volume", "shipment_volume", "product_quantity"])
    examples = _candidate_examples(source_review_row)
    csv_evidence = _read_csv_evidence(
        data_root=data_root,
        relative_paths=examples,
        columns=columns,
    )
    groups = (
        _rent_groups(
            source_review_row=source_review_row,
            unknown_option_row=unknown_option_row,
            csv_evidence=csv_evidence,
        )
        if dp_id == "L0.cost.rent"
        else _asp_groups(
            source_review_row=source_review_row,
            unknown_option_row=unknown_option_row,
            csv_evidence=csv_evidence,
        )
    )
    ready_group_count = sum(1 for group in groups if group["ready_for_formula"])
    formula_inputs_ready = all(group["ready_for_formula"] for group in groups)
    if dp_id == "L0.cost.rent":
        formula_candidate_status = "proxy_available_denominator_policy_missing"
    else:
        formula_candidate_status = "revenue_mix_available_quantity_missing"
    return {
        "task_id": task.get("task_id"),
        "dp_id": dp_id,
        "score_target": task.get("score_target"),
        "data_status": "Unknown",
        "acquisition_track": task.get("acquisition_track"),
        "source_priority": task.get("source_priority"),
        "source_review_packet_status": source_review_row.get(
            "source_review_packet_status"
        ),
        "candidate_columns": source_review_row.get("candidate_columns") or [],
        "empty_candidate_columns": source_review_row.get("empty_candidate_columns") or [],
        "missing_formula_inputs": source_review_row.get("missing_formula_inputs") or [],
        "runtime_dependency_ready": _runtime_dependency_ready(unknown_option_row),
        "runtime_dependency_count": _runtime_dependency_count(unknown_option_row),
        "csv_sample_evidence": csv_evidence,
        "formula_input_groups": groups,
        "formula_input_group_count": len(groups),
        "formula_input_group_ready_count": ready_group_count,
        "formula_inputs_ready": formula_inputs_ready,
        "formula_candidate_status": formula_candidate_status,
        "ready_for_known_draft": False,
        "ready_for_approval": False,
        "review_required": True,
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }


def _validation_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("dp_id"):
        errors.append("dp_id is required")
    if row.get("data_status") != "Unknown":
        errors.append("data_status must stay Unknown")
    if not row.get("formula_input_groups"):
        errors.append("formula_input_groups are required")
    if row.get("formula_inputs_ready") is not False:
        errors.append("formula_inputs_ready must be false until all groups are ready")
    if row.get("ready_for_known_draft") is not False:
        errors.append("ready_for_known_draft must be false")
    if row.get("ready_for_approval") is not False:
        errors.append("ready_for_approval must be false")
    if row.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if row.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    return errors


def build_report(
    *,
    backlog_path: Path,
    source_review_path: Path,
    unknown_options_path: Path,
    data_root: Path,
) -> dict[str, Any]:
    started = time.time()
    backlog = _load_json(backlog_path)
    source_review = _load_json(source_review_path)
    unknown_options = _load_json(unknown_options_path)
    source_review_by_dp = _rows_by_dp(source_review)
    unknown_options_by_dp = _rows_by_dp(unknown_options)
    rows = [
        _row(
            task=task,
            source_review_row=source_review_by_dp.get(str(task.get("dp_id") or ""), {}),
            unknown_option_row=unknown_options_by_dp.get(str(task.get("dp_id") or "")),
            data_root=data_root,
        )
        for task in _tasks(backlog)
    ]
    rows.sort(key=lambda row: str(row["dp_id"]))
    for row in rows:
        errors = _validation_errors(row)
        row["packet_contract_valid"] = not errors
        row["packet_validation_errors"] = errors

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "backlog_path": _portable_path(backlog_path),
            "source_review_path": _portable_path(source_review_path),
            "unknown_options_path": _portable_path(unknown_options_path),
            "data_root": str(data_root),
        },
        "summary": {
            "local_formula_acquisition_task_count": len(rows),
            "runtime_dependency_ready_count": sum(
                1 for row in rows if row["runtime_dependency_ready"]
            ),
            "sample_csv_files_checked": sum(
                int(row["csv_sample_evidence"].get("files_checked") or 0)
                for row in rows
            ),
            "sample_csv_files_existing": sum(
                int(row["csv_sample_evidence"].get("files_existing") or 0)
                for row in rows
            ),
            "sample_csv_read_error_count": sum(
                int(row["csv_sample_evidence"].get("read_error_count") or 0)
                for row in rows
            ),
            "formula_input_group_count": sum(
                int(row["formula_input_group_count"]) for row in rows
            ),
            "formula_input_group_ready_count": sum(
                int(row["formula_input_group_ready_count"]) for row in rows
            ),
            "rows_with_candidate_numerator_count": sum(
                1
                for row in rows
                if row["dp_id"] == "L0.cost.rent"
                and int(
                    row["csv_sample_evidence"]["column_non_empty"].get(
                        "use_right_asset_dep"
                    )
                    or 0
                )
                > 0
                or row["dp_id"] == "L0.price.product_asp"
                and int(row["csv_sample_evidence"]["column_non_empty"].get("bz_sales") or 0)
                > 0
            ),
            "rows_with_direct_denominator_count": 0,
            "rows_with_quantity_or_price_index_count": 0,
            "rows_with_formula_policy_count": 0,
            "formula_inputs_ready_count": sum(
                1 for row in rows if row["formula_inputs_ready"]
            ),
            "ready_for_known_draft_count": sum(
                1 for row in rows if row["ready_for_known_draft"]
            ),
            "ready_for_approval_count": sum(1 for row in rows if row["ready_for_approval"]),
            "packet_contract_valid_count": sum(
                1 for row in rows if row["packet_contract_valid"]
            ),
            "packet_contract_invalid_count": sum(
                1 for row in rows if not row["packet_contract_valid"]
            ),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share Unknown local formula acquisition candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Local formula acquisition tasks: `{summary['local_formula_acquisition_task_count']}`",
        f"- Runtime dependency-ready tasks: `{summary['runtime_dependency_ready_count']}`",
        f"- Sample CSV files checked: `{summary['sample_csv_files_checked']}`",
        f"- Sample CSV files existing: `{summary['sample_csv_files_existing']}`",
        f"- Sample CSV read errors: `{summary['sample_csv_read_error_count']}`",
        f"- Formula input groups: `{summary['formula_input_group_count']}`",
        f"- Formula input groups ready: `{summary['formula_input_group_ready_count']}`",
        f"- Rows with candidate numerator: `{summary['rows_with_candidate_numerator_count']}`",
        f"- Rows with direct denominator: `{summary['rows_with_direct_denominator_count']}`",
        f"- Rows with quantity or price index: `{summary['rows_with_quantity_or_price_index_count']}`",
        f"- Rows with formula policy: `{summary['rows_with_formula_policy_count']}`",
        f"- Formula inputs ready: `{summary['formula_inputs_ready_count']}`",
        f"- Ready for Known draft: `{summary['ready_for_known_draft_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | status | candidate columns | input groups ready | formula ready | production write |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['formula_candidate_status']}` | "
            f"{len(row['candidate_columns'])} | "
            f"{row['formula_input_group_ready_count']}/{row['formula_input_group_count']} | "
            f"{'yes' if row['formula_inputs_ready'] else 'no'} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Rent has a lease-proxy candidate, but lacks direct rent/lease payment, denominator, and reviewed proxy policy.",
            "- Product ASP has product/mix and revenue context, but lacks quantity or governed price-index input.",
            "- These packets are formula acquisition evidence only; no runtime score writes are allowed.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog-path", type=Path, default=DEFAULT_BACKLOG_PATH)
    parser.add_argument("--source-review-path", type=Path, default=DEFAULT_SOURCE_REVIEW_PATH)
    parser.add_argument(
        "--unknown-options-path",
        type=Path,
        default=DEFAULT_UNKNOWN_OPTIONS_PATH,
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        backlog_path=args.backlog_path,
        source_review_path=args.source_review_path,
        unknown_options_path=args.unknown_options_path,
        data_root=args.data_root,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
