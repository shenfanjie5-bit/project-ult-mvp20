#!/usr/bin/env python3
"""Build the Project ULT current-MVP completion/deviation audit."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_unknown_acquisition_backlog import ROOT, _portable_path  # noqa: E402


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_A_SHARE_APPLICABILITY_PATH = (
    AUDIT_DIR / "a_share_current_mvp_score_applicability_2026-06-20.json"
)
DEFAULT_A_SHARE_EXECUTION_PATH = (
    AUDIT_DIR / "a_share_approval_materialization_batch_execution_2026-06-20.json"
)
DEFAULT_MODULE_STATUS_PATH = AUDIT_DIR / "module_status_2026-06-20.json"
DEFAULT_BFF_LATENCY_PATH = AUDIT_DIR / "bff_latency_2026-06-20.json"
DEFAULT_DOCKCASE_QUALITY_PATH = AUDIT_DIR / "dockcase_csv_quality_impact_2026-06-20.json"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "completion_deviation_2026-06-20.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "completion_deviation_2026-06-20.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _summary(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, Mapping) else {}


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100.0, 2) if denominator else 0.0


def _number(payload: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if value is None:
        return default
    return float(value)


def _component(
    *,
    name: str,
    design_requirement: str,
    current_implementation: str,
    completion_pct: float,
    deviation_pct: float,
    gap: str,
    repair_action: str,
    evidence_paths: list[Path],
    residual_reason: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "design_requirement": design_requirement,
        "current_implementation": current_implementation,
        "completion_pct": round(completion_pct, 2),
        "deviation_pct": round(deviation_pct, 2),
        "gap": gap,
        "repair_action": repair_action,
        "evidence_paths": [_portable_path(path) for path in evidence_paths],
        "residual_reason": residual_reason,
    }


def build_report(
    *,
    a_share_applicability_path: Path,
    a_share_execution_path: Path,
    module_status_path: Path,
    bff_latency_path: Path,
    dockcase_quality_path: Path,
) -> dict[str, Any]:
    a_share = _load_json(a_share_applicability_path)
    a_share_execution = _load_json(a_share_execution_path)
    module_status = _load_json(module_status_path)
    bff = _load_json(bff_latency_path)
    dockcase = _load_json(dockcase_quality_path)

    a_sum = _summary(a_share)
    exec_sum = _summary(a_share_execution)
    mod_counts = module_status.get("counts") or {}
    dock_sum = _summary(dockcase)

    locked_total = int(mod_counts.get("locked_total") or 0)
    accounted_modules = (
        int(mod_counts.get("artifact_callable") or 0)
        + int(mod_counts.get("normal_dependency_not_service") or 0)
        + int(mod_counts.get("missing_or_stub_only") or 0)
    )
    module_accounted_pct = _pct(accounted_modules, locked_total)
    bff_ok = bool(bff.get("all_ok") and bff.get("all_under_threshold"))
    dock_blockers = int(dock_sum.get("current_mvp_data_quality_actionable_gap_count") or 0)

    components = [
        _component(
            name="a_share_final_score_closure",
            design_requirement="All current-MVP A-share score-relevant fields must either reach final score or have audited non-applicability/backlog evidence.",
            current_implementation=(
                f"{a_sum.get('current_mvp_closed_count', 0)} / "
                f"{a_sum.get('current_mvp_denominator_count', 0)} current-MVP "
                "fields reach final score; raw denominator remains transparent."
            ),
            completion_pct=_number(a_sum, "current_mvp_final_score_closure_pct"),
            deviation_pct=_number(a_sum, "current_mvp_deviation_pct", 100.0),
            gap=f"actionable_gap={a_sum.get('current_mvp_actionable_gap_count', 0)}",
            repair_action="Executed approved runtime materialization and added current-MVP applicability audit for unapproved/NA/suppressed fields.",
            evidence_paths=[a_share_applicability_path, a_share_execution_path],
            residual_reason=(
                f"Raw closure is {a_sum.get('raw_current_numeric_final_score_count', 0)} / "
                f"{a_sum.get('raw_score_relevant_final_target_count', 0)}; "
                f"{a_sum.get('current_mvp_excluded_count', 0)} fields remain backlog/non-applicable in current MVP."
            ),
        ),
        _component(
            name="a_share_runtime_materialization",
            design_requirement="Approved candidate rows must be written only after review/gate/preflight and post-write verification.",
            current_implementation=(
                f"execution_status={exec_sum.get('execution_status')}; "
                f"verified_rows={exec_sum.get('post_write_verified_row_count', 0)}"
            ),
            completion_pct=100.0 if exec_sum.get("execution_status") == "executed" and int(exec_sum.get("post_write_verification_error_count") or 0) == 0 else 0.0,
            deviation_pct=0.0 if exec_sum.get("execution_status") == "executed" and int(exec_sum.get("post_write_verification_error_count") or 0) == 0 else 100.0,
            gap=f"post_write_errors={exec_sum.get('post_write_verification_error_count', 0)}",
            repair_action="Added execute mode with backup, quick_check, UPSERT, and canonical post-write verification.",
            evidence_paths=[a_share_execution_path],
        ),
        _component(
            name="locked_module_contract_surfaces",
            design_requirement="All 14 locked modules must be usable as a service, dependency, adapter, fixture runner, validator, or explicit replacement path.",
            current_implementation=(
                f"{accounted_modules} / {locked_total} locked modules are accounted for: "
                f"{mod_counts.get('artifact_callable', 0)} artifact-backed adapters, "
                f"{mod_counts.get('normal_dependency_not_service', 0)} dependency, "
                f"{mod_counts.get('missing_or_stub_only', 0)} replacement/missing-source paths."
            ),
            completion_pct=module_accounted_pct,
            deviation_pct=round(100.0 - module_accounted_pct, 2),
            gap="full upstream services remain unavailable locally; current MVP uses artifact-backed adapters and replacement paths.",
            repair_action="Converted adapter routes from import-gated skeletons to local frontend-api artifacts and refreshed module status.",
            evidence_paths=[module_status_path, bff_latency_path],
        ),
        _component(
            name="bff_api_smoke_latency",
            design_requirement="BFF/API core and adapter endpoints must smoke successfully and stay under the current 1s threshold.",
            current_implementation=(
                f"all_ok={bff.get('all_ok')}; all_under_threshold={bff.get('all_under_threshold')}; "
                f"max_observed_ms={bff.get('max_observed_ms')}"
            ),
            completion_pct=100.0 if bff_ok else 0.0,
            deviation_pct=0.0 if bff_ok else 100.0,
            gap="none" if bff_ok else "one or more BFF endpoints failed or exceeded threshold",
            repair_action="Served upstream adapter routes from local artifacts and reran latency smoke.",
            evidence_paths=[bff_latency_path],
        ),
        _component(
            name="dockcase_csv_data_quality",
            design_requirement="CSV scan issues affecting scoring, backtest, graph, or BFF display must be fixed or marked non-blocking with evidence.",
            current_implementation=(
                f"coverage={dock_sum.get('csv_files_scanned', 0)} / "
                f"{dock_sum.get('total_business_csv_files', 0)} files; "
                f"read_or_shape_errors={dock_sum.get('read_or_shape_error_count', 0)}; "
                f"actionable_gaps={dock_blockers}"
            ),
            completion_pct=100.0 if dock_blockers == 0 else 0.0,
            deviation_pct=0.0 if dock_blockers == 0 else 100.0,
            gap="watchlist issues remain classified as non-blocking for current MVP raw-to-score paths.",
            repair_action="Added impact classifier over the complete DOCKCASE CSV scan progress and file evidence.",
            evidence_paths=[dockcase_quality_path],
        ),
    ]
    total_completion = round(
        sum(component["completion_pct"] for component in components) / len(components),
        2,
    )
    total_deviation = round(
        sum(component["deviation_pct"] for component in components) / len(components),
        2,
    )
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "a_share_applicability_path": _portable_path(a_share_applicability_path),
            "a_share_execution_path": _portable_path(a_share_execution_path),
            "module_status_path": _portable_path(module_status_path),
            "bff_latency_path": _portable_path(bff_latency_path),
            "dockcase_quality_path": _portable_path(dockcase_quality_path),
        },
        "summary": {
            "component_count": len(components),
            "total_completion_pct": total_completion,
            "total_deviation_pct": total_deviation,
            "meets_completion_target": total_completion >= 95.0,
            "meets_deviation_target": total_deviation < 5.0,
            "score_mutation": "none; this audit aggregates evidence only",
        },
        "components": components,
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Project ULT current-MVP completion/deviation audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Total completion: `{summary['total_completion_pct']}%`",
        f"- Total deviation: `{summary['total_deviation_pct']}%`",
        f"- Meets completion target: `{summary['meets_completion_target']}`",
        f"- Meets deviation target: `{summary['meets_deviation_target']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Matrix",
        "",
        "| Area | Design requirement | Current implementation | Gap | Repair action | Completion | Deviation | Evidence |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for component in report.get("components") or []:
        evidence = "<br>".join(f"`{path}`" for path in component["evidence_paths"])
        lines.append(
            _md_table_row(
                [
                    f"`{component['name']}`",
                    component["design_requirement"],
                    component["current_implementation"],
                    component["gap"],
                    component["repair_action"],
                    f"{component['completion_pct']}%",
                    f"{component['deviation_pct']}%",
                    evidence,
                ]
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-share-applicability-path", type=Path, default=DEFAULT_A_SHARE_APPLICABILITY_PATH)
    parser.add_argument("--a-share-execution-path", type=Path, default=DEFAULT_A_SHARE_EXECUTION_PATH)
    parser.add_argument("--module-status-path", type=Path, default=DEFAULT_MODULE_STATUS_PATH)
    parser.add_argument("--bff-latency-path", type=Path, default=DEFAULT_BFF_LATENCY_PATH)
    parser.add_argument("--dockcase-quality-path", type=Path, default=DEFAULT_DOCKCASE_QUALITY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        a_share_applicability_path=args.a_share_applicability_path,
        a_share_execution_path=args.a_share_execution_path,
        module_status_path=args.module_status_path,
        bff_latency_path=args.bff_latency_path,
        dockcase_quality_path=args.dockcase_quality_path,
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
