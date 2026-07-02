import json
from pathlib import Path

from scripts import audit_module_status


def _touch_path(root: Path, rel_path: str) -> None:
    path = root / rel_path
    if rel_path.endswith("/") or "." not in path.name:
        path.mkdir(parents=True, exist_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_classify_modules_keeps_dependency_and_artifact_adapter_out_of_running(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (tmp_path / "upstream" / "contracts").mkdir(parents=True)
    (tmp_path / "upstream" / "graph-engine").mkdir(parents=True)
    adapter = tmp_path / "mvp20" / "adapters"
    adapter.mkdir(parents=True)
    (adapter / "graph_engine.py").write_text(
        'from mvp20.adapters._artifacts import artifact_envelope\n',
        encoding="utf-8",
    )
    artifact = tmp_path / "upstream" / "graph-engine" / "artifacts" / "frontend-api"
    artifact.mkdir(parents=True)
    (artifact / "subgraph.json").write_text("{}", encoding="utf-8")
    lock = lock_dir / "modules.lock.yaml"
    lock.write_text(
        """
modules:
  contracts:
    repo: x
    commit: c1
  graph-engine:
    repo: x
    commit: c2
  orchestrator:
    repo: x
    commit: c3
""",
        encoding="utf-8",
    )
    latency = tmp_path / "latency.json"
    latency.write_text(
        json.dumps({
            "all_ok": True,
            "all_under_threshold": True,
            "endpoints": {
                "/api/project-ult/graph/query": {
                    "ok": True,
                    "under_threshold": True,
                }
            },
        }),
        encoding="utf-8",
    )

    result = audit_module_status.classify_modules(tmp_path, lock, latency)

    assert result["counts"]["locked_total"] == 3
    assert result["counts"]["normal_running"] == 0
    assert result["counts"]["normal_but_not_enabled"] == 0
    assert result["counts"]["normal_dependency_not_service"] == 1
    assert result["counts"]["not_usable_full_service"] == 2
    by_name = {row["module"]: row for row in result["modules"]}
    assert by_name["contracts"]["service_bucket"] == "not_a_service"
    assert by_name["contracts"]["runtime_state"] == "normal_dependency_not_service"
    assert by_name["contracts"]["evidence_level"] == "vendored_dependency_source"
    assert by_name["contracts"]["live_process_ok"] is None
    assert by_name["graph-engine"]["classification"] == "artifact_callable_contract_surface"
    assert (
        by_name["graph-engine"]["evidence_level"]
        == "artifact_adapter_and_route_latency_audit"
    )
    assert result["counts"]["artifact_callable"] == 1
    assert result["counts"]["replacement_path_verified"] == 0
    assert result["counts"]["replacement_path_unverified"] == 1
    assert by_name["orchestrator"]["classification"] == "unavailable_as_full_module_here"
    assert by_name["orchestrator"]["evidence_level"] == "missing_vendored_source"
    assert by_name["orchestrator"]["replacement_path_verified"] is False
    assert (
        result["classification_policy"]["normal_running_bucket_means"]
        .startswith("audit evidence proves")
    )
    assert result["runtime_evidence_policy"]["runtime_state_is_the_preferred_semantic_status"]


def test_classify_local_surfaces_counts_runtime_data_and_tooling(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock = lock_dir / "modules.lock.yaml"
    lock.write_text("modules: {}\n", encoding="utf-8")

    for definition in audit_module_status.LOCAL_SURFACE_DEFINITIONS:
        for rel_path in definition.get("required_paths", ()):
            _touch_path(tmp_path, rel_path)

    latency = tmp_path / "docs" / "audit" / "bff_latency_2026-06-19.json"
    latency.write_text(
        json.dumps({
            "all_ok": True,
            "all_under_threshold": True,
            "max_observed_ms": 424.999,
            "threshold_ms": 1000.0,
            "endpoints": {},
        }),
        encoding="utf-8",
    )
    frontend_latency = (
        tmp_path / "docs" / "audit" / "frontend_shell_latency_2026-06-19.json"
    )
    frontend_latency.write_text(
        json.dumps({
            "all_ok": True,
            "all_under_threshold": True,
            "max_observed_ms": 24.094,
        }),
        encoding="utf-8",
    )
    frontend_navigation = (
        tmp_path / "docs" / "audit" / "frontend_project_ult_navigation_2026-06-19.json"
    )
    frontend_navigation.write_text(json.dumps({"all_ok": True}), encoding="utf-8")
    dockcase_roots = (
        tmp_path / "dockcase" / "database_all",
        tmp_path / "dockcase" / "market_data",
    )
    for root in dockcase_roots:
        root.mkdir(parents=True)

    result = audit_module_status.classify_modules(
        tmp_path,
        lock,
        latency,
        frontend_latency,
        frontend_navigation,
        dockcase_roots,
    )

    local = result["local_runtime_data_tooling_surfaces"]
    assert local["counts"] == {
        "local_total": 17,
        "normal_running": 9,
        "normal_but_not_enabled": 7,
        "not_usable": 1,
    }
    by_name = {row["module"]: row for row in local["modules"]}
    assert by_name["yfinance_provider"]["service_bucket"] == "not_usable"
    assert by_name["yfinance_provider"]["runtime_state"] == "not_usable"
    assert by_name["yfinance_provider"]["evidence_level"] == "missing_or_failed_current_evidence"
    assert by_name["dockcase_cache"]["service_bucket"] == "normal_running"
    assert by_name["dockcase_cache"]["runtime_state"] == "proven_runnable_or_serviceable"
    assert by_name["dockcase_cache"]["evidence_level"] == "current_external_mount_check"
    assert by_name["mvp20_bff"]["evidence_level"] == "current_bff_latency_audit_json"
    assert (
        by_name["frontend_spa"]["evidence_level"]
        == "current_frontend_shell_and_navigation_audit_json"
    )
    assert by_name["frontend_spa"]["live_process_ok"] is None
    assert result["combined_inventory_counts"] == {
        "inventory_total": 17,
        "normal_running": 9,
        "normal_but_not_enabled": 7,
        "not_usable": 1,
        "normal_dependency_not_service": 0,
    }
