#!/usr/bin/env python3
"""Plan A-share approval-packet runtime materialization.

This audit is intentionally read-only. It refines the approval target-scope
readiness result by separating packets that can be converted into per-stock
formula materialization plans from packets that still need market/event scope
policy or full text-match target extraction.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import yaml

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from mvp20.aggregator import _realtime_signal  # noqa: E402
from scripts.audit_a_share_unknown_acquisition_backlog import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_TARGET_SCOPE_READINESS_PATH = (
    AUDIT_DIR / "a_share_approval_target_scope_readiness_2026-06-20.json"
)
DEFAULT_REVIEW_MANIFEST_PATH = (
    AUDIT_DIR / "a_share_review_staging_manifest_2026-06-19.json"
)
DEFAULT_RUNTIME_DB_PATH = ROOT / "runtime/hot.sqlite"
DEFAULT_UNIVERSE_PATH = ROOT / "config/mvp20.universe.yaml"
DEFAULT_JSON_OUTPUT = (
    AUDIT_DIR / "a_share_approval_materialization_plan_2026-06-20.json"
)
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_approval_materialization_plan_2026-06-20.md"

A_SHARE_SUFFIXES = (".SH", ".SZ", ".BJ")


FormulaFn = Callable[[Mapping[str, Any]], tuple[float | None, dict[str, Any]]]


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _is_a_share(ts_code: str) -> bool:
    return ts_code.endswith(A_SHARE_SUFFIXES)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("rows") or []
    if not isinstance(raw_rows, list):
        return []
    return [dict(row) for row in raw_rows if isinstance(row, Mapping)]


def _by_dp_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            out[dp_id] = row
    return out


def _config_a_share_codes(universe_path: Path) -> list[str]:
    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    constituents = payload.get("constituents") or []
    codes = [
        str(row.get("ts_code"))
        for row in constituents
        if isinstance(row, Mapping) and _is_a_share(str(row.get("ts_code") or ""))
    ]
    return sorted(set(codes))


def _config_a_share_industry_map(universe_path: Path) -> dict[str, str]:
    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    constituents = payload.get("constituents") or []
    out: dict[str, str] = {}
    for row in constituents:
        if not isinstance(row, Mapping):
            continue
        ts_code = str(row.get("ts_code") or "")
        industry_ids = row.get("industry_ids")
        if isinstance(industry_ids, list):
            industry_id = str(next((item for item in industry_ids if item), "") or "")
        else:
            industry_id = str(row.get("industry_id") or "")
        if _is_a_share(ts_code) and industry_id:
            out[ts_code] = industry_id
    return out


def _runtime_values_by_dp(
    runtime_db_path: Path, dp_ids: Iterable[str]
) -> dict[str, dict[str, Mapping[str, Any]]]:
    wanted = sorted({str(dp_id) for dp_id in dp_ids if str(dp_id)})
    if not wanted:
        return {}
    placeholders = ",".join("?" for _ in wanted)
    conn = sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"""
            select ts_code, dp_id, value_json
            from realtime_current
            where dp_id in ({placeholders}) and ts_code is not null
            """,
            wanted,
        ).fetchall()
    finally:
        conn.close()
    values: dict[str, dict[str, Mapping[str, Any]]] = {dp_id: {} for dp_id in wanted}
    for ts_code, dp_id, value_json in rows:
        try:
            parsed = json.loads(value_json) if isinstance(value_json, str) else value_json
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, Mapping):
            values.setdefault(str(dp_id), {})[str(ts_code)] = parsed
    return values


def _value(values: Mapping[str, Mapping[str, Any]], dep: str, key: str) -> float | None:
    return _safe_float((values.get(dep) or {}).get(key))


def _formula_cost_cac(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    ratio = _value(values, "L5.is.sga_rd", "sga_rd_ratio_revenue")
    if ratio is None:
        return None, {"missing": ["L5.is.sga_rd.sga_rd_ratio_revenue"]}
    return _clip((0.18 - ratio) / 0.30), {"sga_rd_ratio_revenue": _round(ratio)}


def _formula_cost_labor(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    pct = _value(values, "L4.cost.labor", "labor_cost_pct")
    yoy = _value(values, "L4.cost.labor", "labor_cost_yoy_pct")
    missing = []
    if pct is None:
        missing.append("L4.cost.labor.labor_cost_pct")
    if yoy is None:
        missing.append("L4.cost.labor.labor_cost_yoy_pct")
    if missing:
        return None, {"missing": missing}
    return _clip(((20.0 - pct) / 40.0) - (yoy / 30.0)), {
        "labor_cost_pct": _round(pct),
        "labor_cost_yoy_pct": _round(yoy),
    }


def _formula_demand_terminal(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    yoy = _value(values, "L5.is.revenue_growth", "yoy_pct")
    if yoy is None:
        return None, {"missing": ["L5.is.revenue_growth.yoy_pct"]}
    return _clip(math.tanh(yoy / 35.0)), {"revenue_yoy_pct": _round(yoy)}


def _formula_supply_capacity(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    capex = _value(values, "L5.cf.capex", "scalar")
    ppe = _value(values, "L5.bs.goodwill_ppe", "fix_assets_ppe")
    missing = []
    if capex is None:
        missing.append("L5.cf.capex.scalar")
    if ppe is None or ppe <= 0:
        missing.append("L5.bs.goodwill_ppe.fix_assets_ppe")
    if missing:
        return None, {"missing": missing}
    ratio = capex / ppe
    return _clip((ratio - 0.02) / 0.08), {"capex_to_ppe": _round(ratio)}


def _formula_chain_eff(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    ccc = _value(values, "L4.eff.cycle", "ccc_days")
    if ccc is None:
        return None, {"missing": ["L4.eff.cycle.ccc_days"]}
    return _clip((90.0 - ccc) / 180.0), {"ccc_days": _round(ccc)}


def _formula_pricing_power(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    gross_margin = _value(values, "L5.is.gross_margin", "scalar")
    if gross_margin is None:
        return None, {"missing": ["L5.is.gross_margin.scalar"]}
    return _clip((gross_margin - 0.20) / 0.30), {"gross_margin": _round(gross_margin)}


def _formula_inventory(values: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    inv = _value(values, "L5.bs.inventory", "inventory_to_assets")
    if inv is None:
        return None, {"missing": ["L5.bs.inventory.inventory_to_assets"]}
    return _clip((0.20 - inv) / 0.40), {"inventory_to_assets": _round(inv)}


DIRECT_STRUCTURED_FORMULAS: dict[str, tuple[list[str], FormulaFn, str]] = {
    "L0.cost.cac": (
        ["L5.is.sga_rd"],
        _formula_cost_cac,
        "score = clamp((0.18 - sga_rd_ratio_revenue) / 0.30, -1, 1)",
    ),
    "L0.cost.labor": (
        ["L4.cost.labor"],
        _formula_cost_labor,
        "score = clamp(((20 - labor_cost_pct) / 40) - (labor_cost_yoy_pct / 30), -1, 1)",
    ),
    "L0.demand.terminal": (
        ["L5.is.revenue_growth"],
        _formula_demand_terminal,
        "score = clamp(tanh(revenue_yoy_pct / 35), -1, 1)",
    ),
    "L0.supply.capacity": (
        ["L5.cf.capex", "L5.bs.goodwill_ppe"],
        _formula_supply_capacity,
        "score = clamp((capex / fix_assets_ppe - 0.02) / 0.08, -1, 1)",
    ),
    "L0.supply.chain_eff": (
        ["L4.eff.cycle"],
        _formula_chain_eff,
        "score = clamp((90 - ccc_days) / 180, -1, 1)",
    ),
    "L0.price.pricing_power": (
        ["L5.is.gross_margin"],
        _formula_pricing_power,
        "score = clamp((gross_margin - 0.20) / 0.30, -1, 1)",
    ),
    "L0.supply.inventory": (
        ["L5.bs.inventory"],
        _formula_inventory,
        "score = clamp((0.20 - inventory_to_assets) / 0.40, -1, 1)",
    ),
}

GRAIN_JOIN_FORMULAS = {"L0.price.contract_spot"}
TEXT_EVIDENCE_SUBSET = {
    "L0.demand.user_count",
    "L0.price.discount",
    "L0.supply.channel_service",
}
MARKET_EVENT_SOURCE_KINDS = {"event_text_policy_pilot", "manual_policy_pilot"}


def _score_stats(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
        }
    return {
        "count": len(scores),
        "min": _round(min(scores)),
        "max": _round(max(scores)),
        "avg": _round(sum(scores) / len(scores)),
    }


def _direct_formula_row(
    *,
    packet: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    a_share_codes: list[str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    dp_id = str(packet.get("dp_id") or "")
    deps, formula, formula_text = DIRECT_STRUCTURED_FORMULAS[dp_id]
    target_codes: list[str] = []
    scores: list[float] = []
    bridge_ready_count = 0
    samples: list[dict[str, Any]] = []
    missing_reason_counts: Counter[str] = Counter()
    for ts_code in a_share_codes:
        values = {dep: runtime_values.get(dep, {}).get(ts_code, {}) for dep in deps}
        score, components = formula(values)
        if score is None:
            for reason in components.get("missing", ["formula_input_missing"]):
                missing_reason_counts[str(reason)] += 1
            continue
        value_json = {
            "score": _round(score),
            "drivers": deps,
            "components": components,
            "materialization_formula": formula_text,
        }
        signal = _realtime_signal(dp_id, value_json, "fundamental_score", ts_code=ts_code)
        bridge_ready = signal is not None
        if bridge_ready:
            bridge_ready_count += 1
        target_codes.append(ts_code)
        scores.append(score)
        if len(samples) < 5:
            samples.append(
                {
                    "ts_code": ts_code,
                    "score": _round(score),
                    "bridge_signal": _round(signal) if signal is not None else None,
                    "components": components,
                }
            )
    payload = manifest_row.get("review_payload") or {}
    return {
        "dp_id": dp_id,
        "score_target": packet.get("score_target"),
        "source_kind": packet.get("source_kind"),
        "materialization_class": "direct_structured_per_stock_formula",
        "required_next_step": "approve_formula_materialization_plan",
        "source_dependencies": deps,
        "formula": formula_text,
        "review_payload_score": ((payload.get("value_json") or {}).get("score")),
        "a_share_universe_count": len(a_share_codes),
        "target_ts_code_count": len(target_codes),
        "bridge_ready_count": bridge_ready_count,
        "score_stats": _score_stats(scores),
        "sample_materialized_rows": samples,
        "missing_input_count": len(a_share_codes) - len(target_codes),
        "missing_input_reason_counts": dict(sorted(missing_reason_counts.items())),
        "runtime_materialization_plan_ready": bool(target_codes)
        and bridge_ready_count == len(target_codes),
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _grain_join_target_rows(
    *,
    a_share_codes: list[str],
    industry_by_ts_code: Mapping[str, str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[list[str], dict[str, int], list[dict[str, Any]]]:
    target_codes: list[str] = []
    samples: list[dict[str, Any]] = []
    missing_counts: Counter[str] = Counter()
    raw_material_by_industry = runtime_values.get("L0.cost.raw_material", {})
    gross_margin_by_ts = runtime_values.get("L5.is.gross_margin", {})
    for ts_code in a_share_codes:
        industry_id = industry_by_ts_code.get(ts_code)
        if not industry_id:
            missing_counts["missing_industry_id"] += 1
            continue
        raw_material = raw_material_by_industry.get(f"INDUSTRY:{industry_id}")
        if not raw_material:
            missing_counts["missing_raw_material"] += 1
            continue
        gross_margin = gross_margin_by_ts.get(ts_code)
        if not gross_margin:
            missing_counts["missing_gross_margin"] += 1
            continue
        target_codes.append(ts_code)
        if len(samples) < 5:
            samples.append(
                {
                    "ts_code": ts_code,
                    "industry_id": industry_id,
                    "raw_material_avg_pct_change": _round(
                        _safe_float(raw_material.get("avg_pct_change"))
                    ),
                    "gross_margin": _round(_safe_float(gross_margin.get("scalar"))),
                }
            )
    return target_codes, dict(sorted(missing_counts.items())), samples


def _grain_join_row(
    packet: Mapping[str, Any],
    manifest_row: Mapping[str, Any],
    *,
    a_share_codes: list[str],
    industry_by_ts_code: Mapping[str, str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    payload = manifest_row.get("review_payload") or {}
    components = ((payload.get("value_json") or {}).get("components") or {})
    grain = components.get("grain_join_policy") if isinstance(components, Mapping) else {}
    grain = grain if isinstance(grain, Mapping) else {}
    target_codes, missing_counts, samples = _grain_join_target_rows(
        a_share_codes=a_share_codes,
        industry_by_ts_code=industry_by_ts_code,
        runtime_values=runtime_values,
    )
    return {
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "source_kind": packet.get("source_kind"),
        "materialization_class": "structured_formula_grain_join_per_stock",
        "required_next_step": "approve_grain_join_materialization_plan",
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "formula": (
            "score = clamp(((gross_margin - 0.20) / 0.50) - "
            "(raw_material_avg_pct_change / 3.0), -1, 1)"
        ),
        "review_payload_score": ((payload.get("value_json") or {}).get("score")),
        "grain_join_policy": grain,
        "target_ts_code_count": len(target_codes),
        "target_ts_codes_sample": target_codes[:10],
        "sample_materialized_rows": samples,
        "missing_input_reason_counts": missing_counts,
        "missing_raw_material_a_share_count": missing_counts.get("missing_raw_material", 0),
        "missing_gross_margin_a_share_count": missing_counts.get("missing_gross_margin", 0),
        "runtime_materialization_plan_ready": bool(target_codes),
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _text_subset_row(packet: Mapping[str, Any], manifest_row: Mapping[str, Any]) -> dict[str, Any]:
    payload = manifest_row.get("review_payload") or {}
    value_json = payload.get("value_json") or {}
    components = value_json.get("components") if isinstance(value_json, Mapping) else {}
    components = components if isinstance(components, Mapping) else {}
    examples = components.get("evidence_examples") or []
    example_codes = sorted(
        {
            str(example.get("ts_code"))
            for example in examples
            if isinstance(example, Mapping) and str(example.get("ts_code") or "").strip()
        }
    )
    match_count_keys = [
        "qa_user_count_demand_match_count",
        "qa_discount_pressure_match_count",
        "qa_channel_service_match_count",
    ]
    full_match_count = next(
        (
            int(components.get(key))
            for key in match_count_keys
            if isinstance(components.get(key), int)
        ),
        len(example_codes),
    )
    target_count = len(example_codes)
    return {
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "source_kind": packet.get("source_kind"),
        "materialization_class": "text_evidence_subset_per_stock",
        "required_next_step": "approve_text_evidence_subset_materialization_plan",
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "review_payload_score": value_json.get("score"),
        "text_match_count": full_match_count,
        "target_ts_code_count": target_count,
        "evidence_example_ts_code_count": len(example_codes),
        "evidence_example_ts_codes": example_codes,
        "runtime_materialization_plan_ready": bool(example_codes),
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _market_event_row(packet: Mapping[str, Any], manifest_row: Mapping[str, Any]) -> dict[str, Any]:
    payload = manifest_row.get("review_payload") or {}
    return {
        "dp_id": packet.get("dp_id"),
        "score_target": packet.get("score_target"),
        "source_kind": packet.get("source_kind"),
        "materialization_class": "market_or_event_scope_policy_required",
        "required_next_step": "approve_market_or_event_target_scope_policy",
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "review_payload_score": ((payload.get("value_json") or {}).get("score")),
        "runtime_materialization_plan_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def _classify_packet(
    packet: Mapping[str, Any],
    *,
    manifest_row: Mapping[str, Any],
    a_share_codes: list[str],
    industry_by_ts_code: Mapping[str, str],
    runtime_values: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    dp_id = str(packet.get("dp_id") or "")
    score_target = str(packet.get("score_target") or "")
    source_kind = str(packet.get("source_kind") or "")
    if dp_id in DIRECT_STRUCTURED_FORMULAS:
        return _direct_formula_row(
            packet=packet,
            manifest_row=manifest_row,
            a_share_codes=a_share_codes,
            runtime_values=runtime_values,
        )
    if dp_id in GRAIN_JOIN_FORMULAS:
        return _grain_join_row(
            packet,
            manifest_row,
            a_share_codes=a_share_codes,
            industry_by_ts_code=industry_by_ts_code,
            runtime_values=runtime_values,
        )
    if dp_id in TEXT_EVIDENCE_SUBSET:
        return _text_subset_row(packet, manifest_row)
    if source_kind in MARKET_EVENT_SOURCE_KINDS or score_target != "fundamental_score":
        return _market_event_row(packet, manifest_row)
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_kind": source_kind,
        "materialization_class": "unsupported_materialization_policy",
        "required_next_step": "define_materialization_policy",
        "source_dependencies": manifest_row.get("source_dependencies") or [],
        "runtime_materialization_plan_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *,
    target_scope_readiness_path: Path,
    review_manifest_path: Path,
    runtime_db_path: Path,
    universe_path: Path,
) -> dict[str, Any]:
    target_scope_readiness = _load_json(target_scope_readiness_path)
    review_manifest = _load_json(review_manifest_path)
    packets = _rows(target_scope_readiness)
    manifest_by_dp_id = _by_dp_id(_rows(review_manifest))
    a_share_codes = _config_a_share_codes(universe_path)
    industry_by_ts_code = _config_a_share_industry_map(universe_path)
    formula_dp_ids = {
        dep
        for deps, _formula, _text in DIRECT_STRUCTURED_FORMULAS.values()
        for dep in deps
    }
    formula_dp_ids.update({"L0.cost.raw_material", "L5.is.gross_margin"})
    runtime_values = _runtime_values_by_dp(runtime_db_path, formula_dp_ids)

    rows = [
        _classify_packet(
            packet,
            manifest_row=manifest_by_dp_id.get(str(packet.get("dp_id") or ""), {}),
            a_share_codes=a_share_codes,
            industry_by_ts_code=industry_by_ts_code,
            runtime_values=runtime_values,
        )
        for packet in packets
    ]
    materialization_class_counts = Counter(
        str(row.get("materialization_class") or "") for row in rows
    )
    required_next_step_counts = Counter(
        str(row.get("required_next_step") or "") for row in rows
    )
    ready_rows = [
        row for row in rows if row.get("runtime_materialization_plan_ready") is True
    ]
    direct_rows = [
        row
        for row in rows
        if row.get("materialization_class") == "direct_structured_per_stock_formula"
    ]
    direct_ready_rows = [
        row for row in direct_rows if row.get("runtime_materialization_plan_ready") is True
    ]
    target_counts = [
        int(row.get("target_ts_code_count") or 0)
        for row in direct_rows
        if int(row.get("target_ts_code_count") or 0) > 0
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "target_scope_readiness_path": _portable_path(target_scope_readiness_path),
            "review_manifest_path": _portable_path(review_manifest_path),
            "runtime_db_path": _portable_path(runtime_db_path),
            "universe_path": _portable_path(universe_path),
        },
        "summary": {
            "approval_packet_count": len(rows),
            "a_share_universe_count": len(a_share_codes),
            "fundamental_packet_count": sum(
                1 for row in rows if row.get("score_target") == "fundamental_score"
            ),
            "direct_structured_formula_packet_count": materialization_class_counts.get(
                "direct_structured_per_stock_formula", 0
            ),
            "direct_structured_formula_plan_ready_count": len(direct_ready_rows),
            "direct_structured_formula_min_target_count": min(target_counts)
            if target_counts
            else 0,
            "direct_structured_formula_max_target_count": max(target_counts)
            if target_counts
            else 0,
            "grain_join_policy_required_count": materialization_class_counts.get(
                "structured_formula_grain_join_review_required", 0
            ),
            "text_evidence_full_match_export_required_count": materialization_class_counts.get(
                "text_evidence_subset_requires_full_match_export", 0
            ),
            "grain_join_plan_ready_count": materialization_class_counts.get(
                "structured_formula_grain_join_per_stock", 0
            ),
            "text_evidence_subset_plan_ready_count": materialization_class_counts.get(
                "text_evidence_subset_per_stock", 0
            ),
            "market_or_event_scope_policy_required_count": materialization_class_counts.get(
                "market_or_event_scope_policy_required", 0
            ),
            "unsupported_materialization_policy_count": materialization_class_counts.get(
                "unsupported_materialization_policy", 0
            ),
            "runtime_materialization_plan_ready_count": len(ready_rows),
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "materialization_class_counts": dict(
                sorted(materialization_class_counts.items())
            ),
            "required_next_step_counts": dict(sorted(required_next_step_counts.items())),
            "score_mutation": "none; materialization planning audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share approval materialization plan",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Approval packets checked: `{summary['approval_packet_count']}`",
        f"- A-share universe count: `{summary['a_share_universe_count']}`",
        f"- Fundamental packets: `{summary['fundamental_packet_count']}`",
        f"- Direct structured formula packets: `{summary['direct_structured_formula_packet_count']}`",
        f"- Direct structured formula plans ready for review: `{summary['direct_structured_formula_plan_ready_count']}`",
        f"- Direct structured formula target range: `{summary['direct_structured_formula_min_target_count']}` to `{summary['direct_structured_formula_max_target_count']}`",
        f"- Grain-join policy required: `{summary['grain_join_policy_required_count']}`",
        f"- Text full-match export required: `{summary['text_evidence_full_match_export_required_count']}`",
        f"- Market/event scope policy required: `{summary['market_or_event_scope_policy_required_count']}`",
        f"- Unsupported materialization policy: `{summary['unsupported_materialization_policy_count']}`",
        f"- Runtime materialization plans ready: `{summary['runtime_materialization_plan_ready_count']}`",
        f"- Runtime writes allowed: `{summary['runtime_write_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Class Counts",
        "",
        "| Class | Count |",
        "|---|---:|",
    ]
    for key, value in summary["materialization_class_counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | class | next step | target count | score range / sample scope |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in report.get("rows") or []:
        stats = row.get("score_stats") or {}
        detail = (
            f"{stats.get('min')}..{stats.get('max')}"
            if stats
            else f"text examples={row.get('evidence_example_ts_code_count', '-')}"
            if row.get("materialization_class")
            == "text_evidence_subset_requires_full_match_export"
            else "-"
        )
        lines.append(
            "| "
            f"`{row.get('dp_id')}` | "
            f"`{row.get('materialization_class')}` | "
            f"`{row.get('required_next_step')}` | "
            f"{int(row.get('target_ts_code_count') or 0)} | "
            f"{detail} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Direct structured formula rows have enough runtime inputs to package a reviewable per-stock materialization plan.",
            "- Grain-join and text rows still need explicit target extraction policy before a write plan.",
            "- Market/event rows should not be expanded to every A-share ticker without a reviewed target-scope policy.",
            "- This report does not approve or execute runtime writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-scope-readiness-path",
        type=Path,
        default=DEFAULT_TARGET_SCOPE_READINESS_PATH,
    )
    parser.add_argument(
        "--review-manifest-path", type=Path, default=DEFAULT_REVIEW_MANIFEST_PATH
    )
    parser.add_argument("--runtime-db-path", type=Path, default=DEFAULT_RUNTIME_DB_PATH)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        target_scope_readiness_path=args.target_scope_readiness_path,
        review_manifest_path=args.review_manifest_path,
        runtime_db_path=args.runtime_db_path,
        universe_path=args.universe_path,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
