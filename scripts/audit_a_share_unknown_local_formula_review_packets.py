#!/usr/bin/env python3
"""Build review packets for local formula Unknown acquisition rows.

The acquisition audit can find candidate formula pieces such as a lease proxy
or business-segment revenue. This review-packet layer checks whether those
pieces are sufficient to produce a formula probe that can reach the final score.
It intentionally does not select a value, mark rows Known, or write runtime data.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_review_staging_manifest import ROOT, _bridge_validation


DEFAULT_ACQUISITION_PATH = (
    ROOT
    / "docs/audit/a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.md"
)
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_PRICE_INDEX_CONTEXT_PATHS = (
    Path(
        "/Volumes/dockcase2tb/database_all/宏观经济/国内宏观/价格指数/居民消费价格指数（CPI）/all.csv"
    ),
    Path(
        "/Volumes/dockcase2tb/database_all/宏观经济/国内宏观/价格指数/工业生产者出厂价格指数（PPI）/all.csv"
    ),
)


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


def _runtime_scalar_summary(db_path: Path, dp_id: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "dp_id": dp_id,
        "runtime_db_path": _portable_path(db_path),
        "available": False,
        "known_count": 0,
        "scalar_count": 0,
        "ts_code_count": 0,
        "sample_values": [],
    }
    if not db_path.exists():
        return {**summary, "reason": "runtime_db_missing"}
    uri = f"file:{db_path.resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            aggregate = conn.execute(
                """
                select
                  count(*) as row_count,
                  sum(case when data_status = 'Known' then 1 else 0 end) as known_count,
                  count(distinct ts_code) as ts_code_count,
                  sum(case when json_extract(value_json, '$.scalar') is not null then 1 else 0 end) as scalar_count,
                  min(json_extract(value_json, '$.scalar')) as min_scalar,
                  max(json_extract(value_json, '$.scalar')) as max_scalar
                from realtime_current
                where dp_id = ?
                """,
                (dp_id,),
            ).fetchone()
            samples = conn.execute(
                """
                select ts_code, data_status, json_extract(value_json, '$.scalar') as scalar, source
                from realtime_current
                where dp_id = ? and data_status = 'Known'
                  and json_extract(value_json, '$.scalar') is not null
                order by updated_at desc, ts_code
                limit 3
                """,
                (dp_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        return {**summary, "reason": f"sqlite_error:{type(exc).__name__}"}

    known_count = int(aggregate["known_count"] or 0)
    scalar_count = int(aggregate["scalar_count"] or 0)
    return {
        **summary,
        "available": known_count > 0 and scalar_count > 0,
        "row_count": int(aggregate["row_count"] or 0),
        "known_count": known_count,
        "scalar_count": scalar_count,
        "ts_code_count": int(aggregate["ts_code_count"] or 0),
        "min_scalar": aggregate["min_scalar"],
        "max_scalar": aggregate["max_scalar"],
        "sample_values": [dict(sample) for sample in samples],
    }


def _groups(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(group)
        for group in row.get("formula_input_groups") or []
        if isinstance(group, Mapping)
    ]


def _group_statuses(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(group.get("name") or ""): str(group.get("status") or "")
        for group in _groups(row)
        if group.get("name")
    }


def _is_ready(status: str) -> bool:
    return status == "ready"


def _is_candidate(status: str) -> bool:
    return status in {"ready", "review_candidate", "supporting_candidate"}


def _candidate_numerator_available(row: Mapping[str, Any]) -> bool:
    statuses = _group_statuses(row)
    return bool(
        _is_candidate(statuses.get("lease_proxy_numerator", ""))
        or _is_candidate(statuses.get("product_revenue_numerator", ""))
    )


def _denominator_available(row: Mapping[str, Any]) -> bool:
    return _is_ready(_group_statuses(row).get("denominator", ""))


def _runtime_denominator_candidate(
    row: Mapping[str, Any],
    *,
    runtime_db_path: Path,
) -> dict[str, Any] | None:
    if str(row.get("dp_id") or "") != "L0.cost.rent":
        return None
    revenue = _runtime_scalar_summary(runtime_db_path, "L5.is.revenue")
    return {
        "candidate_dp_id": "L5.is.revenue",
        "candidate_use": "revenue denominator for lease-burden proxy review",
        "candidate_available": bool(revenue.get("available")),
        "review_required": True,
        "runtime_summary": revenue,
    }


def _price_index_file_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _portable_path(path),
        "exists": path.exists(),
        "available": False,
        "columns": [],
        "recognized_price_index_columns": [],
        "sample_rows": [],
    }
    if not path.exists():
        return {**summary, "reason": "missing_file"}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            sample_rows: list[dict[str, Any]] = []
            for row in reader:
                if len(sample_rows) >= 3:
                    break
                sample_rows.append(
                    {
                        key: value
                        for key, value in row.items()
                        if key in {"month", "nt_val", "nt_yoy", "ppi_yoy", "ppi_mom", "ppi_accu"}
                    }
                )
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return {**summary, "reason": f"read_error:{type(exc).__name__}"}

    recognized = [
        column
        for column in columns
        if column in {"nt_val", "nt_yoy", "nt_mom", "ppi_yoy", "ppi_mom", "ppi_accu"}
    ]
    return {
        **summary,
        "available": bool(recognized and sample_rows),
        "columns": columns,
        "recognized_price_index_columns": recognized,
        "sample_rows": sample_rows,
    }


def _price_index_context_candidate(
    row: Mapping[str, Any],
    *,
    price_index_context_paths: Sequence[Path],
) -> dict[str, Any] | None:
    if str(row.get("dp_id") or "") != "L0.price.product_asp":
        return None
    file_summaries = [_price_index_file_summary(path) for path in price_index_context_paths]
    available_files = [item for item in file_summaries if item.get("available")]
    return {
        "candidate_use": "broad macro price-index context for product ASP review",
        "candidate_available": bool(available_files),
        "review_required": True,
        "direct_formula_input": False,
        "reason_not_direct_formula_input": (
            "CPI/PPI files are broad macro price indexes; product ASP still needs "
            "product-level volume/shipment data or a governed product-to-index mapping."
        ),
        "files_checked": len(file_summaries),
        "files_available": len(available_files),
        "file_summaries": file_summaries,
    }


def _denominator_candidate_available(row: Mapping[str, Any], candidate: Any) -> bool:
    if _denominator_available(row):
        return True
    return bool(
        isinstance(candidate, Mapping)
        and candidate.get("candidate_available")
        and candidate.get("review_required") is True
    )


def _price_index_context_candidate_available(candidate: Any) -> bool:
    return bool(
        isinstance(candidate, Mapping)
        and candidate.get("candidate_available")
        and candidate.get("review_required") is True
        and candidate.get("direct_formula_input") is False
    )


def _quantity_or_price_index_available(row: Mapping[str, Any]) -> bool:
    return _is_ready(_group_statuses(row).get("quantity_or_price_index", ""))


def _formula_policy_available(row: Mapping[str, Any]) -> bool:
    return _is_ready(_group_statuses(row).get("formula_policy", ""))


def _probe_payload(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("candidate_formula_probe_payload", "formula_probe_payload"):
        payload = row.get(key)
        if isinstance(payload, Mapping):
            return payload
    return None


def _probe(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _probe_payload(row)
    formula_inputs_ready = bool(row.get("formula_inputs_ready"))
    probe_available = bool(formula_inputs_ready and payload)
    bridge = {}
    if probe_available and payload is not None:
        bridge = _bridge_validation(
            str(row.get("dp_id") or ""),
            str(row.get("score_target") or payload.get("score_target") or ""),
            payload,
        )
    return {
        "formula_probe_available": probe_available,
        "formula_probe_payload": payload if probe_available else None,
        "bridge_validation": bridge,
        "bridge_probe_ready": bool(bridge.get("final_score_target_ready")),
    }


def _missing_requirements(
    row: Mapping[str, Any],
    *,
    denominator_candidate_available: bool = False,
    formula_policy_draft_available: bool = False,
) -> list[str]:
    missing: list[str] = []
    if not _candidate_numerator_available(row):
        missing.append("candidate_numerator")
    dp_id = str(row.get("dp_id") or "")
    if (
        dp_id == "L0.cost.rent"
        and not _denominator_available(row)
        and not denominator_candidate_available
    ):
        missing.append("denominator")
    if (
        dp_id == "L0.cost.rent"
        and not _denominator_available(row)
        and denominator_candidate_available
    ):
        missing.append("denominator_review")
    if dp_id == "L0.price.product_asp" and not _quantity_or_price_index_available(row):
        missing.append("quantity_or_price_index")
    if not _formula_policy_available(row) and formula_policy_draft_available:
        missing.append("formula_policy_review")
    elif not _formula_policy_available(row):
        missing.append("formula_policy")
    if bool(row.get("formula_inputs_ready")) and _probe_payload(row) is None:
        missing.append("formula_probe_payload")
    return missing


def _validation_errors(packet: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not packet.get("local_formula_review_packet_id"):
        errors.append("local_formula_review_packet_id is required")
    if not packet.get("dp_id"):
        errors.append("dp_id is required")
    if packet.get("data_status") != "Unknown":
        errors.append("data_status must remain Unknown")
    if not isinstance(packet.get("formula_input_groups"), list):
        errors.append("formula_input_groups must be a list")
    if packet.get("selected_value_json") is not None:
        errors.append("selected_value_json must remain null")
    if packet.get("known_draft_sufficient") is not False:
        errors.append("known_draft_sufficient must remain false")
    if packet.get("approval_ready") is not False:
        errors.append("approval_ready must remain false")
    if packet.get("runtime_write_allowed") is not False:
        errors.append("runtime_write_allowed must be false")
    if packet.get("production_write_allowed") is not False:
        errors.append("production_write_allowed must be false")
    if packet.get("formula_policy_review_template") is not None:
        if packet.get("formula_policy_review_template_contract_valid") is not True:
            errors.append("formula_policy_review_template contract must be valid")
        errors.extend(
            str(item)
            for item in packet.get("formula_policy_review_template_validation_errors") or []
        )
    if packet.get("price_context_review_template") is not None:
        if packet.get("price_context_review_template_contract_valid") is not True:
            errors.append("price_context_review_template contract must be valid")
        errors.extend(
            str(item)
            for item in packet.get("price_context_review_template_validation_errors") or []
        )
    if packet.get("formula_probe_available"):
        bridge = packet.get("bridge_validation") or {}
        if not bridge.get("final_score_target_ready"):
            errors.append("formula probe must bridge to a final-score target")
        payload = packet.get("formula_probe_payload")
        value_json = payload.get("value_json") if isinstance(payload, Mapping) else None
        if not isinstance(value_json, Mapping) or not isinstance(
            value_json.get("score"), (int, float)
        ):
            errors.append("formula probe payload must include numeric value_json.score")
    return errors


def _candidate_formula_shape(
    row: Mapping[str, Any],
    denominator_candidate: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if str(row.get("dp_id") or "") != "L0.cost.rent":
        return None
    if not _candidate_numerator_available(row):
        return None
    if not _denominator_candidate_available(row, denominator_candidate):
        return None
    return {
        "formula_family": "lease_burden_proxy_review",
        "candidate_formula": "use_right_asset_dep / L5.is.revenue",
        "numerator_column": "use_right_asset_dep",
        "denominator_dp_id": "L5.is.revenue",
        "required_policy": [
            "confirm use_right_asset_dep is an acceptable lease-burden proxy",
            "define cap/floor and sign direction before Known scoring",
            "reject automatic runtime writes until reviewer policy is recorded",
        ],
    }


def _formula_policy_draft_candidate(
    row: Mapping[str, Any],
    formula_shape: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if str(row.get("dp_id") or "") != "L0.cost.rent":
        return None
    if _formula_policy_available(row):
        return None
    if not isinstance(formula_shape, Mapping):
        return None
    return {
        "policy_draft_id": "formula_policy_draft:L0.cost.rent:lease_burden_proxy",
        "policy_family": "lease_burden_proxy_review",
        "candidate_formula": formula_shape.get("candidate_formula"),
        "candidate_formula_ready": False,
        "review_required": True,
        "direct_runtime_write_allowed": False,
        "input_semantics": {
            "numerator": (
                "use_right_asset_dep from cashflow is use-right asset depreciation; "
                "it is a lease-burden proxy, not direct rent expense."
            ),
            "denominator": (
                "L5.is.revenue is a runtime revenue denominator candidate; "
                "it must be accepted as a burden denominator before scoring."
            ),
        },
        "score_direction": "higher lease-burden ratio is worse for cost score",
        "normalization_requirements": [
            "confirm proxy acceptance before any Known draft",
            "define lower bound, upper cap, and clipping rule",
            "define whether neutral score is used when ratio is unavailable",
            "bridge the reviewed value_json.score to fundamental_score before staging",
        ],
        "blockers_before_ready": [
            "proxy_semantics_review",
            "denominator_policy_review",
            "cap_floor_review",
        ],
    }


def _formula_policy_draft_available(candidate: Any) -> bool:
    return bool(
        isinstance(candidate, Mapping)
        and candidate.get("review_required") is True
        and candidate.get("candidate_formula_ready") is False
    )


def _candidate_price_context_shape(
    row: Mapping[str, Any],
    price_index_context_candidate: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if str(row.get("dp_id") or "") != "L0.price.product_asp":
        return None
    if not _candidate_numerator_available(row):
        return None
    if not _price_index_context_candidate_available(price_index_context_candidate):
        return None
    return {
        "context_family": "product_asp_macro_price_index_review",
        "candidate_context": "bz_sales / product mix + macro CPI/PPI context",
        "direct_formula_ready": False,
        "required_policy": [
            "confirm product-level unit volume, shipment volume, or product quantity source",
            "or define a governed mapping from product/segment labels to a price index",
            "keep quantity_or_price_index unavailable until the mapping is reviewed",
            "reject automatic runtime writes until reviewer policy is recorded",
        ],
    }


def _formula_policy_review_template(
    *,
    packet_id: str,
    dp_id: str,
    formula_policy_draft: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if formula_policy_draft is None:
        return None
    return {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "review_scope": "local_formula_policy",
        "policy_draft_id": formula_policy_draft.get("policy_draft_id"),
        "policy_family": formula_policy_draft.get("policy_family"),
        "candidate_formula": formula_policy_draft.get("candidate_formula"),
        "reviewer": "",
        "reviewed_at": "",
        "proxy_semantics_accepted": False,
        "denominator_policy_accepted": False,
        "cap_floor_accepted": False,
        "score_direction_accepted": False,
        "normalization_accepted": False,
        "formula_probe_allowed": False,
        "known_draft_allowed": False,
        "production_write_allowed": False,
    }


def _formula_policy_review_template_errors(
    template: Mapping[str, Any] | None,
    *,
    packet_id: str,
    dp_id: str,
    formula_policy_draft: Mapping[str, Any] | None,
) -> list[str]:
    if formula_policy_draft is None:
        return []
    if template is None:
        return ["formula_policy_review_template missing"]
    errors: list[str] = []
    expected = {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "review_scope": "local_formula_policy",
        "policy_draft_id": formula_policy_draft.get("policy_draft_id"),
        "policy_family": formula_policy_draft.get("policy_family"),
        "candidate_formula": formula_policy_draft.get("candidate_formula"),
        "reviewer": "",
        "reviewed_at": "",
    }
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    for key in (
        "proxy_semantics_accepted",
        "denominator_policy_accepted",
        "cap_floor_accepted",
        "score_direction_accepted",
        "normalization_accepted",
        "formula_probe_allowed",
        "known_draft_allowed",
        "production_write_allowed",
    ):
        if template.get(key) is not False:
            errors.append(f"{key} must be false in blank template")
    return errors


def _price_context_review_template(
    *,
    packet_id: str,
    dp_id: str,
    price_context_shape: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if price_context_shape is None:
        return None
    return {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "review_scope": "product_asp_price_context",
        "context_family": price_context_shape.get("context_family"),
        "candidate_context": price_context_shape.get("candidate_context"),
        "reviewer": "",
        "reviewed_at": "",
        "product_quantity_source_accepted": False,
        "price_index_mapping_accepted": False,
        "scope_alignment_accepted": False,
        "formula_policy_accepted": False,
        "quantity_or_price_index_ready": False,
        "formula_probe_allowed": False,
        "known_draft_allowed": False,
        "production_write_allowed": False,
    }


def _price_context_review_template_errors(
    template: Mapping[str, Any] | None,
    *,
    packet_id: str,
    dp_id: str,
    price_context_shape: Mapping[str, Any] | None,
) -> list[str]:
    if price_context_shape is None:
        return []
    if template is None:
        return ["price_context_review_template missing"]
    errors: list[str] = []
    expected = {
        "template_status": "review_fill_required",
        "packet_id": packet_id,
        "dp_id": dp_id,
        "review_scope": "product_asp_price_context",
        "context_family": price_context_shape.get("context_family"),
        "candidate_context": price_context_shape.get("candidate_context"),
        "reviewer": "",
        "reviewed_at": "",
    }
    for key, expected_value in expected.items():
        if template.get(key) != expected_value:
            errors.append(f"{key} must be {expected_value!r}")
    for key in (
        "product_quantity_source_accepted",
        "price_index_mapping_accepted",
        "scope_alignment_accepted",
        "formula_policy_accepted",
        "quantity_or_price_index_ready",
        "formula_probe_allowed",
        "known_draft_allowed",
        "production_write_allowed",
    ):
        if template.get(key) is not False:
            errors.append(f"{key} must be false in blank template")
    return errors


def _packet(
    row: Mapping[str, Any],
    *,
    runtime_db_path: Path,
    price_index_context_paths: Sequence[Path],
) -> dict[str, Any]:
    probe = _probe(row)
    denominator_candidate = _runtime_denominator_candidate(
        row,
        runtime_db_path=runtime_db_path,
    )
    denominator_candidate_ready = _denominator_candidate_available(
        row,
        denominator_candidate,
    )
    formula_shape = _candidate_formula_shape(row, denominator_candidate)
    formula_policy_draft = _formula_policy_draft_candidate(row, formula_shape)
    formula_policy_draft_ready = _formula_policy_draft_available(
        formula_policy_draft
    )
    price_index_context = _price_index_context_candidate(
        row,
        price_index_context_paths=price_index_context_paths,
    )
    price_index_context_ready = _price_index_context_candidate_available(
        price_index_context
    )
    price_context_shape = _candidate_price_context_shape(row, price_index_context)
    packet_id = f"local_formula:{row.get('dp_id')}"
    formula_policy_review_template = _formula_policy_review_template(
        packet_id=packet_id,
        dp_id=str(row.get("dp_id") or ""),
        formula_policy_draft=formula_policy_draft,
    )
    formula_policy_review_template_errors = _formula_policy_review_template_errors(
        formula_policy_review_template,
        packet_id=packet_id,
        dp_id=str(row.get("dp_id") or ""),
        formula_policy_draft=formula_policy_draft,
    )
    price_context_review_template = _price_context_review_template(
        packet_id=packet_id,
        dp_id=str(row.get("dp_id") or ""),
        price_context_shape=price_context_shape,
    )
    price_context_review_template_errors = _price_context_review_template_errors(
        price_context_review_template,
        packet_id=packet_id,
        dp_id=str(row.get("dp_id") or ""),
        price_context_shape=price_context_shape,
    )
    packet = {
        "local_formula_review_packet_id": packet_id,
        "dp_id": row.get("dp_id"),
        "score_target": row.get("score_target") or "fundamental_score",
        "data_status": "Unknown",
        "formula_candidate_status": row.get("formula_candidate_status"),
        "source_review_packet_status": row.get("source_review_packet_status"),
        "candidate_columns": row.get("candidate_columns") or [],
        "empty_candidate_columns": row.get("empty_candidate_columns") or [],
        "formula_input_groups": _groups(row),
        "formula_input_group_count": int(row.get("formula_input_group_count") or 0),
        "formula_input_group_ready_count": int(
            row.get("formula_input_group_ready_count") or 0
        ),
        "candidate_numerator_available": _candidate_numerator_available(row),
        "denominator_available": _denominator_available(row),
        "denominator_candidate_available": denominator_candidate_ready,
        "runtime_denominator_candidate": denominator_candidate,
        "candidate_formula_shape": formula_shape,
        "formula_policy_draft_candidate_available": formula_policy_draft_ready,
        "formula_policy_draft_candidate": formula_policy_draft,
        "formula_policy_review_template": formula_policy_review_template,
        "formula_policy_review_template_contract_valid": (
            formula_policy_review_template is not None
            and not formula_policy_review_template_errors
        ),
        "formula_policy_review_template_validation_errors": (
            formula_policy_review_template_errors
        ),
        "price_index_context_candidate_available": price_index_context_ready,
        "price_index_context_candidate": price_index_context,
        "candidate_price_context_shape": price_context_shape,
        "price_context_review_template": price_context_review_template,
        "price_context_review_template_contract_valid": (
            price_context_review_template is not None
            and not price_context_review_template_errors
        ),
        "price_context_review_template_validation_errors": (
            price_context_review_template_errors
        ),
        "quantity_or_price_index_available": _quantity_or_price_index_available(row),
        "formula_policy_available": _formula_policy_available(row),
        "formula_inputs_ready": bool(row.get("formula_inputs_ready")),
        "formula_probe_available": probe["formula_probe_available"],
        "formula_probe_payload": probe["formula_probe_payload"],
        "bridge_validation": probe["bridge_validation"],
        "bridge_probe_ready": probe["bridge_probe_ready"],
        "selected_value_json": None,
        "missing_before_known": _missing_requirements(
            row,
            denominator_candidate_available=denominator_candidate_ready,
            formula_policy_draft_available=formula_policy_draft_ready,
        ),
        "known_draft_sufficient": False,
        "approval_ready": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }
    errors = _validation_errors(packet)
    return {
        **packet,
        "local_formula_review_contract_valid": not errors,
        "local_formula_review_validation_errors": errors,
    }


def build_report(
    *,
    acquisition_path: Path,
    runtime_db_path: Path = DEFAULT_RUNTIME_DB_PATH,
    price_index_context_paths: Sequence[Path] = DEFAULT_PRICE_INDEX_CONTEXT_PATHS,
) -> dict[str, Any]:
    started = time.time()
    acquisition = _load_json(acquisition_path)
    rows = [
        _packet(
            row,
            runtime_db_path=runtime_db_path,
            price_index_context_paths=price_index_context_paths,
        )
        for row in acquisition.get("rows") or []
        if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "acquisition_path": _portable_path(acquisition_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "price_index_context_paths": [
                _portable_path(path) for path in price_index_context_paths
            ],
        },
        "summary": {
            "local_formula_review_packet_count": len(rows),
            "rows_with_candidate_numerator_count": sum(
                1 for row in rows if row["candidate_numerator_available"]
            ),
            "rows_with_direct_denominator_count": sum(
                1 for row in rows if row["denominator_available"]
            ),
            "rows_with_denominator_candidate_count": sum(
                1 for row in rows if row["denominator_candidate_available"]
            ),
            "rows_with_candidate_formula_shape_count": sum(
                1 for row in rows if row["candidate_formula_shape"]
            ),
            "rows_with_formula_policy_draft_candidate_count": sum(
                1 for row in rows if row["formula_policy_draft_candidate_available"]
            ),
            "formula_policy_review_template_count": sum(
                1 for row in rows if row["formula_policy_review_template"]
            ),
            "formula_policy_review_template_contract_valid_count": sum(
                1
                for row in rows
                if row["formula_policy_review_template_contract_valid"]
            ),
            "formula_policy_review_template_contract_invalid_count": sum(
                1
                for row in rows
                if row["formula_policy_review_template"]
                and not row["formula_policy_review_template_contract_valid"]
            ),
            "formula_policy_review_template_blank_pending_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("formula_policy_review_template"), Mapping)
                    and row["formula_policy_review_template"].get("template_status")
                    == "review_fill_required"
                    and row["formula_policy_review_template"].get("reviewer") == ""
                    and row["formula_policy_review_template"].get("reviewed_at") == ""
                )
            ),
            "rows_with_price_index_context_candidate_count": sum(
                1 for row in rows if row["price_index_context_candidate_available"]
            ),
            "rows_with_candidate_price_context_shape_count": sum(
                1 for row in rows if row["candidate_price_context_shape"]
            ),
            "price_context_review_template_count": sum(
                1 for row in rows if row["price_context_review_template"]
            ),
            "price_context_review_template_contract_valid_count": sum(
                1
                for row in rows
                if row["price_context_review_template_contract_valid"]
            ),
            "price_context_review_template_contract_invalid_count": sum(
                1
                for row in rows
                if row["price_context_review_template"]
                and not row["price_context_review_template_contract_valid"]
            ),
            "price_context_review_template_blank_pending_count": sum(
                1
                for row in rows
                if (
                    isinstance(row.get("price_context_review_template"), Mapping)
                    and row["price_context_review_template"].get("template_status")
                    == "review_fill_required"
                    and row["price_context_review_template"].get("reviewer") == ""
                    and row["price_context_review_template"].get("reviewed_at") == ""
                )
            ),
            "rows_with_quantity_or_price_index_count": sum(
                1 for row in rows if row["quantity_or_price_index_available"]
            ),
            "rows_with_formula_policy_count": sum(
                1 for row in rows if row["formula_policy_available"]
            ),
            "formula_inputs_ready_count": sum(
                1 for row in rows if row["formula_inputs_ready"]
            ),
            "formula_probe_available_count": sum(
                1 for row in rows if row["formula_probe_available"]
            ),
            "bridge_probe_ready_count": sum(
                1 for row in rows if row["bridge_probe_ready"]
            ),
            "selected_value_json_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "local_formula_review_contract_valid_count": sum(
                1 for row in rows if row["local_formula_review_contract_valid"]
            ),
            "local_formula_review_contract_invalid_count": sum(
                1 for row in rows if not row["local_formula_review_contract_valid"]
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
        "# A-share Unknown local formula review packets",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Local formula review packets: `{summary['local_formula_review_packet_count']}`",
        f"- Rows with candidate numerator: `{summary['rows_with_candidate_numerator_count']}`",
        f"- Rows with direct denominator: `{summary['rows_with_direct_denominator_count']}`",
        f"- Rows with denominator candidates: `{summary['rows_with_denominator_candidate_count']}`",
        f"- Rows with candidate formula shape: `{summary['rows_with_candidate_formula_shape_count']}`",
        f"- Rows with formula-policy draft candidates: `{summary['rows_with_formula_policy_draft_candidate_count']}`",
        f"- Formula-policy review templates: `{summary['formula_policy_review_template_count']}`",
        f"- Formula-policy review template contracts valid: `{summary['formula_policy_review_template_contract_valid_count']}`",
        f"- Formula-policy review templates blank pending: `{summary['formula_policy_review_template_blank_pending_count']}`",
        f"- Rows with price-index context candidates: `{summary['rows_with_price_index_context_candidate_count']}`",
        f"- Rows with candidate price-context shape: `{summary['rows_with_candidate_price_context_shape_count']}`",
        f"- Price-context review templates: `{summary['price_context_review_template_count']}`",
        f"- Price-context review template contracts valid: `{summary['price_context_review_template_contract_valid_count']}`",
        f"- Price-context review templates blank pending: `{summary['price_context_review_template_blank_pending_count']}`",
        f"- Rows with quantity or price index: `{summary['rows_with_quantity_or_price_index_count']}`",
        f"- Rows with formula policy: `{summary['rows_with_formula_policy_count']}`",
        f"- Formula inputs ready: `{summary['formula_inputs_ready_count']}`",
        f"- Formula probes available: `{summary['formula_probe_available_count']}`",
        f"- Bridge-probe-ready packets: `{summary['bridge_probe_ready_count']}`",
        f"- Selected value JSONs: `{summary['selected_value_json_count']}`",
        f"- Known-draft-sufficient packets: `{summary['known_draft_sufficient_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | candidate numerator | denominator candidate | policy draft | policy template | price-index context | price template | missing before Known | formula probe | bridge ready | production write |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        missing = ", ".join(row.get("missing_before_known") or []) or "-"
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{'yes' if row['candidate_numerator_available'] else 'no'} | "
            f"{'yes' if row['denominator_candidate_available'] else 'no'} | "
            f"{'yes' if row['formula_policy_draft_candidate_available'] else 'no'} | "
            f"{'yes' if row['formula_policy_review_template_contract_valid'] else 'no'} | "
            f"{'yes' if row['price_index_context_candidate_available'] else 'no'} | "
            f"{'yes' if row['price_context_review_template_contract_valid'] else 'no'} | "
            f"{missing} | "
            f"{'yes' if row['formula_probe_available'] else 'no'} | "
            f"{'yes' if row['bridge_probe_ready'] else 'no'} | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Candidate numerators are not enough to produce a final-score value.",
            "- A runtime revenue denominator candidate can narrow rent review, but it still needs denominator policy and formula policy before a score probe.",
            "- Rent now has a review-only formula-policy draft candidate, but proxy semantics, denominator policy, and cap/floor are still unapproved.",
            "- Product ASP has broad macro CPI/PPI price-index context, but it still needs quantity, shipment volume, product-level volume, or a governed product-to-index mapping before a score probe.",
            "- All packets remain Unknown, review-required, and non-writable.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--acquisition-path",
        type=Path,
        default=DEFAULT_ACQUISITION_PATH,
    )
    parser.add_argument(
        "--runtime-db-path",
        type=Path,
        default=DEFAULT_RUNTIME_DB_PATH,
    )
    parser.add_argument(
        "--price-index-context-path",
        action="append",
        type=Path,
        dest="price_index_context_paths",
        default=None,
        help="Optional CPI/PPI CSV path to treat as product ASP price-index context evidence.",
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        acquisition_path=args.acquisition_path,
        runtime_db_path=args.runtime_db_path,
        price_index_context_paths=(
            tuple(args.price_index_context_paths)
            if args.price_index_context_paths
            else DEFAULT_PRICE_INDEX_CONTEXT_PATHS
        ),
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
