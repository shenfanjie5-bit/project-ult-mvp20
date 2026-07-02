#!/usr/bin/env python3
"""Build audit artifacts for the single-stock LLM decision pipeline."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
from pathlib import Path
from typing import Any

from mvp20.llm_context import ASIA_SHANGHAI, build_single_stock_context
from mvp20.llm_decision import build_dry_run_decision, validate_decision_output
from mvp20.llm_storage import atomic_write_json, write_context_snapshot, write_decision_snapshot


def _parse_as_of(value: str) -> datetime:
    if len(value) == 10:
        value = value + "T02:45:00+08:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ASIA_SHANGHAI)
    return dt


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _validator_cases(context: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    unknown_ref = copy.deepcopy(decision)
    unknown_ref["positive_driver_claims"] = [
        {
            "claim_id": "audit_unknown_ref",
            "claim_use": "supporting",
            "text": "Audit-only invalid claim with an unknown evidence ref.",
            "evidence_refs": ["ev_missing"],
            "confidence": 0.5,
        }
    ]
    unknown_validation = validate_decision_output(context, unknown_ref)

    unusable_ref = copy.deepcopy(decision)
    unusable = next(
        (
            item
            for item in context.get("evidence_pack", [])
            if item.get("llm_usable") is False
        ),
        None,
    )
    if unusable:
        unusable_ref["positive_driver_claims"] = [
            {
                "claim_id": "audit_unusable_ref",
                "claim_use": "supporting",
                "text": "Audit-only invalid claim using non-usable evidence.",
                "evidence_refs": [unusable["evidence_ref"]],
                "confidence": 0.5,
            }
        ]
        unusable_validation = validate_decision_output(context, unusable_ref)
    else:
        unusable_validation = {
            "passed": None,
            "reason": "context had no non-usable evidence rows",
        }

    probability_misuse = copy.deepcopy(decision)
    for estimate in probability_misuse.get("probability_estimates", []):
        if estimate.get("evidence_ref") == "ev_signal_5d_000977_SZ":
            estimate["target_kind"] = "absolute_up_5d"
            estimate["probability_semantics"] = "P(5d return > 0)"
            estimate["use_scope"] = "primary"
            break
    probability_validation = validate_decision_output(context, probability_misuse)

    return {
        "valid_dry_run": decision.get("validation_result"),
        "unknown_evidence_ref_rejected": unknown_validation,
        "unusable_supporting_evidence_rejected": unusable_validation,
        "relative_signal_as_absolute_probability_rejected": probability_validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ts-code", default="000977.SZ")
    parser.add_argument("--horizon", default="5d")
    parser.add_argument("--as-of", default="2026-06-21")
    parser.add_argument("--max-evidence", type=int, default=80)
    parser.add_argument("--output-dir", default="docs/audit")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of_dt = _parse_as_of(args.as_of)
    stamp = as_of_dt.date().isoformat()

    context_obj = build_single_stock_context(
        repo_root=repo_root,
        ts_code=args.ts_code,
        horizon=args.horizon,
        as_of=as_of_dt.isoformat(),
        now=as_of_dt,
        max_evidence=args.max_evidence,
    )
    context = (
        context_obj.model_dump(mode="json", by_alias=True)
        if hasattr(context_obj, "model_dump")
        else dict(context_obj)
    )
    decision = build_dry_run_decision(context)
    context_path = (
        write_context_snapshot(repo_root / "runtime", context)
        if context.get("context_id")
        else None
    )
    decision_path = write_decision_snapshot(repo_root / "runtime", decision)

    architecture = {
        "audit_name": "llm_stock_decision_architecture_audit",
        "audit_date": stamp,
        "ts_code": args.ts_code,
        "horizon": args.horizon,
        "implemented_endpoints": [
            "GET /api/project-ult/llm/stock-context",
            "POST /api/project-ult/llm/stock-decision",
            "GET /api/project-ult/llm/stock-decision",
            "GET /api/project-ult/llm/audit",
            "GET /api/project-ult/score llm_decision_summary",
        ],
        "schema_versions": {
            "context": context.get("schema_version"),
            "decision": decision.get("schema_version"),
        },
        "runtime_snapshot_paths": {
            "context": _rel(context_path, repo_root) if context_path else None,
            "decision": _rel(decision_path, repo_root),
        },
        "source_files": [
            "mvp20/llm_context.py",
            "mvp20/llm_decision.py",
            "mvp20/llm_storage.py",
            "mvp20/server.py",
        ],
        "storage_contract": {
            "context_pattern": "runtime/llm_contexts/{market}/{ts_code}/{horizon}/{context_id}.json",
            "decision_pattern": "runtime/llm_decisions/{market}/{ts_code}/{horizon}/{decision_id}.json",
            "immutable_snapshot": True,
        },
        "frontend_scope": {
            "frontend_changes_included": False,
            "required_ui_behavior": "status!=ok or evidence_gate_passed=false must render insufficient conclusion, not BUY/REDUCE",
        },
    }
    context_smoke = {
        "audit_name": "llm_stock_context_smoke",
        "audit_date": stamp,
        "context_id": context.get("context_id"),
        "context_hash": context.get("input_hash"),
        "ts_code": context.get("ts_code"),
        "market": context.get("market"),
        "horizon": context.get("horizon"),
        "evidence_counts": context.get("evidence_counts"),
        "probability_semantic_checks": [
            {
                "evidence_ref": p.get("evidence_ref"),
                "target_kind": p.get("target_kind"),
                "probability_semantics": p.get("probability_semantics"),
                "validated": p.get("validated"),
                "stale": p.get("stale"),
                "fallback": p.get("fallback"),
                "shadow": p.get("shadow"),
                "use_scope": p.get("use_scope"),
            }
            for p in context.get("model_probabilities", [])
        ],
        "stale_artifact_handling": {
            "signal_5d": "diagnostic_only unless fresh validated non-fallback",
            "signal_up_5d": "diagnostic_only unless fresh validated non-fallback",
            "final_score": "not treated as probability",
        },
        "unsupported_markets": ["HK", "US"],
        "llm_boundaries": context.get("llm_boundaries"),
    }
    validator_audit = {
        "audit_name": "llm_decision_validator_audit",
        "audit_date": stamp,
        "decision_id": decision.get("decision_id"),
        "decision_hash": decision.get("decision_hash"),
        "status": decision.get("status"),
        "action_type": decision.get("action_type"),
        "validation_result": decision.get("validation_result"),
        "validator_cases": _validator_cases(context, decision),
        "embedded_audit_record": decision.get("audit_record"),
        "tests_run": [
            "tests/test_llm_context.py",
            "tests/test_llm_decision.py",
            "tests/test_server.py::test_llm_stock_context_and_decision_routes",
            "tests/test_server.py::test_score_endpoint_returns_mode_and_signal",
            ".venv/bin/python -m pytest -q",
        ],
    }

    atomic_write_json(
        output_dir / f"{stamp}_llm_stock_decision_architecture_audit.json",
        architecture,
    )
    atomic_write_json(
        output_dir / f"{stamp}_llm_stock_context_smoke.json",
        context_smoke,
    )
    atomic_write_json(
        output_dir / f"{stamp}_llm_decision_validator_audit.json",
        validator_audit,
    )
    print(f"wrote audit artifacts to {_rel(output_dir, repo_root)}")
    print(f"context_id={context.get('context_id')} decision_id={decision.get('decision_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
