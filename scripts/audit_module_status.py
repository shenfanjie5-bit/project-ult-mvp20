#!/usr/bin/env python3
"""Classify locked Project ULT modules from current repo evidence.

The output is intentionally conservative. An artifact-backed adapter returning
HTTP 200 counts as a local contract surface, not as a production-normal service;
an importable dependency does not count as a running service.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import yaml


ADAPTER_MODULES = {
    "audit-eval": {
        "adapter": "mvp20/adapters/audit_eval.py",
        "endpoint": "/api/project-ult/audit/smoke",
        "artifact": "upstream/audit-eval/artifacts/frontend-api/audit/CYCLE_20260424.json",
    },
    "data-platform": {
        "adapter": "mvp20/adapters/data_platform.py",
        "endpoint": "/api/project-ult/data/canonical/smoke",
        "artifact": "upstream/data-platform/artifacts/frontend-api/data/canonical/stock_basic.json",
    },
    "entity-registry": {
        "adapter": "mvp20/adapters/entity_registry.py",
        "endpoint": "/api/project-ult/entities",
        "artifact": "upstream/entity-registry/artifacts/frontend-api/entities.json",
    },
    "graph-engine": {
        "adapter": "mvp20/adapters/graph_engine.py",
        "endpoint": "/api/project-ult/graph/query",
        "artifact": "upstream/graph-engine/artifacts/frontend-api/subgraph.json",
    },
    "main-core": {
        "adapter": "mvp20/adapters/main_core.py",
        "endpoint": "/api/stocks/smoke",
        "artifact": "upstream/data-platform/artifacts/frontend-api/cycles.json",
    },
    "reasoner-runtime": {
        "adapter": "mvp20/adapters/reasoner_runtime.py",
        "endpoint": "/api/project-ult/reasoner/smoke",
        "artifact": "upstream/reasoner-runtime/artifacts/frontend-api/results.json",
    },
}

DEPENDENCY_MODULES = {"contracts"}

REPLACEMENT_MODULES: dict[str, dict[str, Any]] = {
    "assembly": {
        "replacement_path": "repo-level manifest/docs/audit assembly",
        "required_paths": (
            "README.md",
            "docs/README.md",
            "locks/modules.lock.yaml",
            "docs/audit/completion_deviation_2026-06-20.json",
        ),
        "rationale": "current MVP assembly is the repo-level manifest, lock, docs, and generated completion audit bundle",
    },
    "frontend-api": {
        "replacement_path": "mvp20 BFF /api/project-ult/* HTTP contract",
        "required_paths": (
            "mvp20/server.py",
            "tests/test_server.py",
            "docs/audit/bff_latency_2026-06-20.json",
        ),
        "rationale": "current MVP frontend API is served by the local mvp20 BFF contract and smoke-tested latency audit",
    },
    "orchestrator": {
        "replacement_path": "mvp20 CLI plus operator runbook/audit orchestration",
        "required_paths": (
            "mvp20/cli.py",
            "docs/RUNBOOK.md",
            "scripts/audit_completion_deviation.py",
            "scripts/audit_module_status.py",
        ),
        "rationale": "current MVP orchestration is operator-mediated through the local CLI, runbook, and reproducible audit scripts",
    },
    "subsystem-announcement": {
        "replacement_path": "Tushare disclosure/report routes plus event-source audits",
        "required_paths": (
            "mvp20/sources/tushare_source.py",
            "tests/test_tushare_disclosure.py",
            "tests/test_tushare_report_rc.py",
            "docs/audit/a_share_unknown_event_primary_source_confirmation_2026-06-19.json",
        ),
        "rationale": "current MVP announcement evidence is sourced through local Tushare disclosure/report adapters and event-source audits",
    },
    "subsystem-holdings": {
        "replacement_path": "Tushare/A-share source readiness and materialization evidence",
        "required_paths": (
            "mvp20/sources/tushare_source.py",
            "tests/test_tushare_core_batch.py",
            "docs/audit/a_share_l0_source_readiness_2026-06-19.json",
            "docs/audit/a_share_approval_materialization_plan_2026-06-20.json",
        ),
        "rationale": "current MVP holdings/capital-flow coverage is represented by local structured A-share source readiness and runtime materialization audits",
    },
    "subsystem-news": {
        "replacement_path": "AKShare/CLS and local market-document event pipeline",
        "required_paths": (
            "mvp20/sources/akshare_source.py",
            "scripts/collect_trackb_news.py",
            "tests/test_akshare_cls.py",
            "docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json",
        ),
        "rationale": "current MVP news/event text path uses local AKShare/CLS collection and market-document event evidence audits",
    },
    "subsystem-sdk": {
        "replacement_path": "local HTTP contract tests and BFF latency smoke",
        "required_paths": (
            "tests/test_server.py",
            "tests/test_audit_bff_latency.py",
            "docs/audit/bff_latency_2026-06-20.json",
        ),
        "rationale": "current MVP SDK contract is the tested local HTTP envelope and latency-smoke interface",
    },
}

BUCKET_RUNTIME_STATE = {
    "normal_running": "proven_runnable_or_serviceable",
    "normal_but_not_enabled": "configured_runnable_not_currently_enabled",
    "not_usable": "not_usable",
    "not_usable_full_service": "not_usable_as_full_service",
    "not_a_service": "normal_dependency_not_service",
}


LOCAL_SURFACE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "module": "mvp20_cli",
        "surface_type": "cli",
        "service_bucket": "normal_running",
        "classification": "local_cli_entrypoint_ready",
        "required_paths": ("pyproject.toml", "mvp20/cli.py", "mvp20/__main__.py"),
        "evidence": ("pyproject console script maps mvp20 to mvp20.cli:main",),
    },
    {
        "module": "mvp20_bff",
        "surface_type": "http_bff",
        "service_bucket": "normal_running",
        "classification": "local_http_bff_under_1s",
        "required_paths": ("mvp20/server.py", "docs/audit/bff_latency_2026-06-20.json"),
        "audit_kind": "bff_latency",
        "evidence": ("BFF latency audit all_ok/all_under_threshold",),
    },
    {
        "module": "frontend_spa",
        "surface_type": "frontend",
        "service_bucket": "normal_running",
        "classification": "local_frontend_shell_under_1s",
        "required_paths": ("FrontEnd/package.json", "FrontEnd/src/App.tsx"),
        "audit_kind": "frontend_shell",
        "evidence": ("frontend shell latency and route coverage audits are green",),
    },
    {
        "module": "tauri_shell",
        "surface_type": "desktop_shell",
        "service_bucket": "normal_but_not_enabled",
        "classification": "desktop_shell_configured_not_running",
        "required_paths": (
            "FrontEnd/src-tauri/Cargo.toml",
            "FrontEnd/src-tauri/tauri.conf.json",
            "FrontEnd/src-tauri/src/main.rs",
        ),
        "evidence": ("Tauri v2 config and Rust shell source exist",),
    },
    {
        "module": "collector_daemon",
        "surface_type": "daemon",
        "service_bucket": "normal_but_not_enabled",
        "classification": "daemon_runnable_not_enabled",
        "required_paths": (
            "scripts/collector.py",
            "scripts/collector_supervisor.sh",
            "scripts/com.mvp20.collector.plist",
            "scripts/mvp20-collector.service",
        ),
        "evidence": ("collector CLI, supervisor, launchd, and systemd manifests exist",),
    },
    {
        "module": "tushare_source",
        "surface_type": "data_source",
        "service_bucket": "normal_but_not_enabled",
        "classification": "structured_source_runnable_needs_token_or_manual_cycle",
        "required_paths": ("mvp20/sources/tushare_source.py", "tests/test_tushare_core_batch.py"),
        "evidence": ("focused Tushare routes are implemented and tested; runtime use needs token/manual refresh",),
    },
    {
        "module": "akshare_source",
        "surface_type": "data_source",
        "service_bucket": "normal_running",
        "classification": "free_source_ready",
        "required_paths": (
            "mvp20/sources/akshare_source.py",
            "tests/test_akshare_source.py",
            "docs/audit/akshare_cls_refresh_2026-06-18.json",
        ),
        "evidence": ("AKShare source and focused CLS refresh evidence exist",),
    },
    {
        "module": "fmp_source",
        "surface_type": "data_source",
        "service_bucket": "normal_but_not_enabled",
        "classification": "source_runnable_needs_api_key",
        "required_paths": ("mvp20/sources/fmp_source.py", "tests/test_fmp_macro.py"),
        "evidence": ("FMP source is implemented; live use needs FMP_API_KEY",),
    },
    {
        "module": "futu_source",
        "surface_type": "data_source",
        "service_bucket": "normal_but_not_enabled",
        "classification": "source_runnable_needs_external_opend",
        "required_paths": ("mvp20/sources/futu_source.py", "docs/data_sources/futu_endpoints.csv"),
        "evidence": ("Futu source mapping exists; live use needs Futu OpenD/account session",),
    },
    {
        "module": "yfinance_provider",
        "surface_type": "data_source",
        "service_bucket": "not_usable",
        "classification": "configured_provider_without_local_collector",
        "required_paths": ("mvp20/providers.py",),
        "missing_impl_paths": ("mvp20/sources/yfinance_source.py",),
        "evidence": ("provider matrix mentions yfinance, but no local yfinance collector implementation exists",),
    },
    {
        "module": "dockcase_cache",
        "surface_type": "external_data_cache",
        "service_bucket": "normal_running",
        "classification": "external_cache_mounted_and_adapter_ready",
        "required_paths": ("mvp20/sources/dockcase_cache.py", "tests/test_dockcase_cache.py"),
        "audit_kind": "dockcase_mount",
        "evidence": ("DockCase cache adapter exists and external roots are mounted",),
    },
    {
        "module": "hot_store_history",
        "surface_type": "runtime_store",
        "service_bucket": "normal_running",
        "classification": "runtime_store_ready",
        "required_paths": ("mvp20/storage.py", "mvp20/history.py", "runtime/hot.sqlite"),
        "evidence": ("SQLite hot store and history code paths exist",),
    },
    {
        "module": "pit_backtest",
        "surface_type": "backtest",
        "service_bucket": "normal_running",
        "classification": "pit_backtest_package_ready",
        "required_paths": ("pit_backtest/runner.py", "scripts/run_pit_backtest.py", "tests/test_pit_leakage.py"),
        "evidence": ("PIT backtest package, runner, and leakage tests exist",),
    },
    {
        "module": "pnl_feedback_loop",
        "surface_type": "feedback_loop",
        "service_bucket": "normal_running",
        "classification": "pnl_loop_ready",
        "required_paths": ("mvp20/pnl_loop.py", "scripts/run_pnl_loop.py", "docs/audit/pnl_quant_implementation_2026-06-10.md"),
        "evidence": ("P&L feedback implementation and run script exist",),
    },
    {
        "module": "quant_score_shadow",
        "surface_type": "scoring_shadow",
        "service_bucket": "normal_but_not_enabled",
        "classification": "shadow_score_runnable_not_primary",
        "required_paths": ("mvp20/quant_score.py", "scripts/build_quant_scores.py", "tests/test_quant_score.py"),
        "evidence": ("quant score artifacts can be built, but primary score path remains mvp20.scoring",),
    },
    {
        "module": "factor_research",
        "surface_type": "research",
        "service_bucket": "normal_but_not_enabled",
        "classification": "research_pipeline_artifacts_not_product_enabled",
        "required_paths": ("factor_research/README.md", "factor_research/model/final_model.json", "factor_research/pit_extra/realbase.sqlite"),
        "evidence": ("factor research artifacts exist but are not enabled as a product runtime module",),
    },
    {
        "module": "docs_audit_toolchain",
        "surface_type": "audit_tooling",
        "service_bucket": "normal_running",
        "classification": "audit_toolchain_ready",
        "required_paths": ("scripts/audit_goal_coverage.py", "scripts/audit_module_status.py", "tests/test_audit_module_status.py", "docs/audit"),
        "evidence": ("audit scripts, tests, and generated docs/audit artifacts exist",),
    },
)


def _local_evidence_level(definition: dict[str, Any], service_bucket: str) -> str:
    audit_kind = definition.get("audit_kind")
    if service_bucket == "not_usable":
        return "missing_or_failed_current_evidence"
    if audit_kind == "bff_latency":
        return "current_bff_latency_audit_json"
    if audit_kind == "frontend_shell":
        return "current_frontend_shell_and_navigation_audit_json"
    if audit_kind == "dockcase_mount":
        return "current_external_mount_check"
    if definition.get("missing_impl_paths"):
        return "missing_implementation_path"
    if service_bucket == "normal_but_not_enabled":
        return "static_configuration_preflight"
    return "static_entrypoint_or_test_evidence"


def _locked_evidence_level(
    *, classification: str, has_source: bool, route_ok: bool = False
) -> str:
    if classification == "normal_dependency_not_service":
        return "vendored_dependency_source"
    if classification == "artifact_callable_contract_surface":
        if route_ok:
            return "artifact_adapter_and_route_latency_audit"
        if has_source:
            return "artifact_adapter_without_route_proof"
        return "artifact_adapter_without_vendored_source"
    if classification == "skeleton_callable_not_full_service":
        if route_ok:
            return "vendored_skeleton_adapter_and_route_latency_audit"
        if has_source:
            return "vendored_skeleton_adapter_without_route_proof"
        return "skeleton_adapter_without_vendored_source"
    if has_source:
        return "vendored_source_without_service_proof"
    return "missing_vendored_source"


def _replacement_evidence(
    repo: Path,
    module_name: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    definition = REPLACEMENT_MODULES.get(module_name)
    if not definition:
        return None, []
    required_paths = tuple(definition.get("required_paths", ()))
    missing = _missing_paths(repo, required_paths)
    evidence = [
        f"current MVP replacement path: {definition['replacement_path']}",
        f"replacement rationale: {definition['rationale']}",
    ]
    if missing:
        evidence.append(f"missing replacement required paths: {', '.join(missing)}")
    else:
        evidence.append("replacement required paths present")
    return {
        "current_mvp_replacement_path": definition["replacement_path"],
        "replacement_required_paths": list(required_paths),
        "replacement_missing_paths": missing,
        "replacement_path_verified": not missing,
        "replacement_rationale": definition["rationale"],
    }, evidence


def load_lock(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_latency(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _path_exists(repo: Path, rel_path: str) -> bool:
    return (repo / rel_path).exists()


def _latency_endpoint_ok(latency: dict[str, Any], endpoint: str | None) -> bool:
    if not endpoint:
        return False
    row = latency.get("endpoints", {}).get(endpoint)
    return bool(row and row.get("ok") and row.get("under_threshold"))


def _adapter_is_skeleton(repo: Path, adapter: str | None) -> bool:
    if not adapter:
        return False
    path = repo / adapter
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return '"wire_depth": "skeleton"' in text or "'wire_depth': 'skeleton'" in text


def _adapter_is_artifact_backed(repo: Path, adapter: str | None) -> bool:
    if not adapter:
        return False
    path = repo / adapter
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return "artifact_envelope" in text or '"wire_depth": "artifact"' in text


def _frontend_audit_ok(frontend_latency: dict[str, Any], frontend_navigation: dict[str, Any]) -> bool:
    return bool(
        frontend_latency.get("all_ok")
        and frontend_latency.get("all_under_threshold")
        and frontend_navigation.get("all_ok")
    )


def _dockcase_ok(dockcase_roots: tuple[Path, ...]) -> bool:
    return all(root.exists() for root in dockcase_roots)


def _missing_paths(repo: Path, rel_paths: tuple[str, ...]) -> list[str]:
    return [rel_path for rel_path in rel_paths if not _path_exists(repo, rel_path)]


def classify_local_surfaces(
    repo: Path,
    latency: dict[str, Any],
    frontend_latency: dict[str, Any],
    frontend_navigation: dict[str, Any],
    dockcase_roots: tuple[Path, ...],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []

    for definition in LOCAL_SURFACE_DEFINITIONS:
        required_paths = tuple(definition.get("required_paths", ()))
        missing_required_paths = _missing_paths(repo, required_paths)
        missing_impl_paths = [
            rel_path
            for rel_path in definition.get("missing_impl_paths", ())
            if not _path_exists(repo, rel_path)
        ]
        evidence = list(definition.get("evidence", ()))

        audit_kind = definition.get("audit_kind")
        audit_ok = True
        if audit_kind == "bff_latency":
            audit_ok = bool(latency.get("all_ok") and latency.get("all_under_threshold"))
            if audit_ok:
                evidence.append(
                    f"BFF max observed {latency.get('max_observed_ms')} ms under "
                    f"{latency.get('threshold_ms')} ms"
                )
        elif audit_kind == "frontend_shell":
            audit_ok = _frontend_audit_ok(frontend_latency, frontend_navigation)
            if audit_ok:
                evidence.append(
                    f"frontend shell max observed {frontend_latency.get('max_observed_ms')} ms"
                )
        elif audit_kind == "dockcase_mount":
            audit_ok = _dockcase_ok(dockcase_roots)
            if audit_ok:
                evidence.extend(f"mounted: {root}" for root in dockcase_roots)

        service_bucket = definition["service_bucket"]
        classification = definition["classification"]
        if missing_required_paths or not audit_ok:
            service_bucket = "not_usable"
            classification = "missing_current_evidence"
            if missing_required_paths:
                evidence.append(f"missing required paths: {', '.join(missing_required_paths)}")
            if not audit_ok:
                evidence.append(f"audit proof failed or missing for {audit_kind}")

        rows.append({
            "module": definition["module"],
            "surface_type": definition["surface_type"],
            "classification": classification,
            "service_bucket": service_bucket,
            "runtime_state": BUCKET_RUNTIME_STATE[service_bucket],
            "evidence_level": _local_evidence_level(definition, service_bucket),
            "live_process_ok": None,
            "live_process_note": (
                "not asserted by module status; latency audits may start temporary "
                "servers and then stop them"
            ),
            "required_paths": list(required_paths),
            "missing_required_paths": missing_required_paths,
            "expected_missing_impl_paths": missing_impl_paths,
            "evidence": evidence,
        })

    counts = {
        "local_total": len(rows),
        "normal_running": sum(1 for row in rows if row["service_bucket"] == "normal_running"),
        "normal_but_not_enabled": sum(
            1 for row in rows if row["service_bucket"] == "normal_but_not_enabled"
        ),
        "not_usable": sum(1 for row in rows if row["service_bucket"] == "not_usable"),
    }
    return rows, counts


def classify_modules(
    repo: Path,
    lock_path: Path,
    latency_path: Path | None,
    frontend_latency_path: Path | None = None,
    frontend_navigation_path: Path | None = None,
    dockcase_roots: tuple[Path, ...] = (
        Path("/Volumes/dockcase2tb/database_all"),
        Path("/Volumes/dockcase2tb/market_data"),
    ),
) -> dict[str, Any]:
    lock = load_lock(lock_path)
    latency = load_latency(latency_path)
    frontend_latency = load_latency(frontend_latency_path)
    frontend_navigation = load_latency(frontend_navigation_path)
    modules = lock.get("modules", {})
    rows = []

    for name in sorted(modules):
        upstream_dir = repo / "upstream" / name
        has_source = upstream_dir.exists()
        evidence: list[str] = []
        route_ok = False
        replacement, replacement_evidence = _replacement_evidence(repo, name)

        if name in DEPENDENCY_MODULES:
            classification = "normal_dependency_not_service"
            service_bucket = "not_a_service"
            evidence.append("vendored source under upstream")
            if has_source:
                evidence.append("dependency source present")
        elif name in ADAPTER_MODULES:
            cfg = ADAPTER_MODULES[name]
            skeleton = _adapter_is_skeleton(repo, cfg.get("adapter"))
            artifact_backed = _adapter_is_artifact_backed(repo, cfg.get("adapter"))
            artifact_path = str(cfg.get("artifact") or "")
            artifact_present = bool(artifact_path and (repo / artifact_path).exists())
            route_ok = _latency_endpoint_ok(latency, cfg.get("endpoint"))
            classification = (
                "artifact_callable_contract_surface"
                if artifact_backed and artifact_present
                else "skeleton_callable_not_full_service"
            )
            service_bucket = "not_usable_full_service"
            if has_source:
                evidence.append("vendored source under upstream")
            if artifact_present:
                evidence.append(f"frontend-api artifact present: {artifact_path}")
            if artifact_backed:
                evidence.append("adapter serves local frontend-api artifact")
            if skeleton:
                evidence.append("adapter declares wire_depth=skeleton")
            if route_ok:
                evidence.append("latency scan route ok under threshold")
            else:
                evidence.append("no repeatable production-normal route proof")
        else:
            classification = "unavailable_as_full_module_here"
            service_bucket = "not_usable_full_service"
            if has_source:
                evidence.append("source present but no enabled service proof")
            else:
                evidence.append("no full vendored source in this checkout")
        evidence.extend(replacement_evidence)

        row = {
            "module": name,
            "commit": modules[name].get("commit"),
            "repo": modules[name].get("repo"),
            "has_vendored_source": has_source,
            "classification": classification,
            "service_bucket": service_bucket,
            "runtime_state": BUCKET_RUNTIME_STATE[service_bucket],
            "evidence_level": _locked_evidence_level(
                classification=classification,
                has_source=has_source,
                route_ok=route_ok,
            ),
            "live_process_ok": None,
            "live_process_note": (
                "locked upstream module status is based on vendored source and "
                "adapter evidence, not a live process probe"
            ),
            "evidence": evidence,
        }
        if replacement is not None:
            row.update(replacement)
        rows.append(row)

    counts = {
        "locked_total": len(rows),
        "normal_running": sum(1 for r in rows if r["service_bucket"] == "normal_running"),
        "normal_but_not_enabled": sum(
            1 for r in rows if r["service_bucket"] == "normal_but_not_enabled"
        ),
        "not_usable_full_service": sum(
            1 for r in rows if r["service_bucket"] == "not_usable_full_service"
        ),
        "normal_dependency_not_service": sum(
            1 for r in rows if r["service_bucket"] == "not_a_service"
        ),
        "skeleton_callable": sum(
            1 for r in rows if r["classification"] == "skeleton_callable_not_full_service"
        ),
        "artifact_callable": sum(
            1 for r in rows if r["classification"] == "artifact_callable_contract_surface"
        ),
        "missing_or_stub_only": sum(
            1 for r in rows if r["classification"] == "unavailable_as_full_module_here"
        ),
        "replacement_path_verified": sum(
            1 for r in rows if r.get("replacement_path_verified") is True
        ),
        "replacement_path_unverified": sum(
            1 for r in rows if r.get("current_mvp_replacement_path") and not r.get("replacement_path_verified")
        ),
    }

    local_rows, local_counts = classify_local_surfaces(
        repo, latency, frontend_latency, frontend_navigation, dockcase_roots
    )
    combined_counts = {
        "inventory_total": counts["locked_total"] + local_counts["local_total"],
        "normal_running": counts["normal_running"] + local_counts["normal_running"],
        "normal_but_not_enabled": (
            counts["normal_but_not_enabled"] + local_counts["normal_but_not_enabled"]
        ),
        "not_usable": counts["not_usable_full_service"] + local_counts["not_usable"],
        "normal_dependency_not_service": counts["normal_dependency_not_service"],
    }
    return {
        "lock_path": str(lock_path),
        "latency_path": str(latency_path) if latency_path else None,
        "frontend_latency_path": str(frontend_latency_path) if frontend_latency_path else None,
        "frontend_navigation_path": str(frontend_navigation_path) if frontend_navigation_path else None,
        "dockcase_roots": [str(root) for root in dockcase_roots],
        "counts": counts,
        "modules": rows,
        "local_runtime_data_tooling_surfaces": {
            "counts": local_counts,
            "modules": local_rows,
        },
        "combined_inventory_counts": combined_counts,
        "counting_policy": {
            "locked_upstream_modules_are_counted_separately": True,
            "local_runtime_data_tooling_surfaces_are_not_in_modules_lock": True,
            "combined_inventory_total_is_locked_plus_local_surfaces": True,
        },
        "classification_policy": {
            "artifact_200_is_normal_service": False,
            "artifact_200_is_local_contract_surface": True,
            "skeleton_200_is_normal": False,
            "dependency_is_service": False,
            "missing_source_counts_as_accounted": False,
            "replacement_path_must_be_verified_to_count": True,
            "normal_but_not_enabled_requires_proof": True,
            "normal_running_bucket_means": (
                "audit evidence proves the local surface is runnable or serviceable; "
                "it does not assert that a persistent process is currently listening"
            ),
            "live_process_ok_null_means": "not checked by this inventory audit",
        },
        "runtime_evidence_policy": {
            "service_bucket_is_backward_compatible": True,
            "runtime_state_is_the_preferred_semantic_status": True,
            "evidence_level_describes_current_proof_strength": True,
            "latency_audits_start_temporary_servers_when_requested": True,
        },
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--lock", default="locks/modules.lock.yaml")
    ap.add_argument("--latency-json", default="docs/audit/bff_latency_2026-06-20.json")
    ap.add_argument(
        "--frontend-shell-latency-json",
        default="docs/audit/frontend_shell_latency_2026-06-19.json",
    )
    ap.add_argument(
        "--frontend-navigation-json",
        default="docs/audit/frontend_project_ult_navigation_2026-06-19.json",
    )
    ap.add_argument("--output", default=None)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    started = time.time()
    result = classify_modules(
        repo,
        repo / args.lock,
        repo / args.latency_json,
        repo / args.frontend_shell_latency_json,
        repo / args.frontend_navigation_json,
    )
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    result["elapsed_s"] = round(time.time() - started, 3)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
