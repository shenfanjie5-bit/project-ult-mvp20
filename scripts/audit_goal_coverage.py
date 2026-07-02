#!/usr/bin/env python3
"""Summarize evidence coverage for the long-running project audit objective."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
    }


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _load_dockcase_backlog_batches(audit_dir: Path) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for path in sorted(audit_dir.glob("dockcase_backlog_batch*.json")):
        payload = _load_json(path)
        if not payload:
            continue
        payload["_path"] = str(path)
        batches.append(payload)
    return batches


def _dockcase_backlog_batch_summary(batches: list[dict[str, Any]]) -> dict[str, Any]:
    issue_counts: dict[str, int] = {}
    target_ranks: list[int] = []
    for batch in batches:
        for rank in batch.get("target_ranks", []):
            try:
                target_ranks.append(int(rank))
            except (TypeError, ValueError):
                continue
        for issue, count in (batch.get("summary", {}).get("issue_counts") or {}).items():
            issue_counts[str(issue)] = issue_counts.get(str(issue), 0) + int(count)
    return {
        "batch_count": len(batches),
        "target_ranks": sorted(set(target_ranks)),
        "matched_files": sum(int(batch.get("summary", {}).get("matched_files") or 0) for batch in batches),
        "sampled_files": sum(int(batch.get("summary", {}).get("sampled_files") or 0) for batch in batches),
        "sampled_rows": sum(int(batch.get("summary", {}).get("sampled_rows") or 0) for batch in batches),
        "row_width_mismatch_count": sum(
            int(batch.get("summary", {}).get("row_width_mismatch_count") or 0)
            for batch in batches
        ),
        "header_read_error_count": sum(
            int(batch.get("summary", {}).get("header_read_error_count") or 0)
            for batch in batches
        ),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _root(data: dict[str, Any], name: str) -> dict[str, Any]:
    return data.get("roots", {}).get(name, {}) if data else {}


def _status(ok: bool, fallback: str = "missing_evidence") -> str:
    return "covered" if ok else fallback


def _line(
    requirement_id: str,
    label: str,
    status: str,
    strength: str,
    evidence: dict[str, Any],
    remaining_gap: str,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "label": label,
        "status": status,
        "evidence_strength": strength,
        "evidence": evidence,
        "remaining_gap": remaining_gap,
    }


def _strength_with_suffixes(base: str, suffixes: list[str]) -> str:
    if not suffixes:
        return base
    if len(suffixes) == 1:
        return f"{base}_and_{suffixes[0]}"
    return f"{base}_{'_'.join(suffixes[:-1])}_and_{suffixes[-1]}"


def _summary_int(summary: dict[str, Any], key: str) -> int:
    return int(summary.get(key) or 0)


def _append_count_mismatch(
    errors: list[str],
    *,
    left_name: str,
    left_value: int,
    right_name: str,
    right_value: int,
) -> None:
    if left_value != right_value:
        errors.append(
            f"{left_name}={left_value} does not match {right_name}={right_value}"
        )


def _score_approval_consistency_errors(
    *,
    review_manifest_summary: dict[str, Any],
    deterministic_approvals_summary: dict[str, Any],
    approval_gate_summary: dict[str, Any],
    completion_next_actions_summary: dict[str, Any],
    approval_review_packets_summary: dict[str, Any],
    spec_numeric_validity_summary: dict[str, Any],
    runtime_write_execution_summary: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []

    review_concrete = _summary_int(review_manifest_summary, "review_ready_concrete_count")
    review_unknown = _summary_int(review_manifest_summary, "review_gated_unknown_count")
    gate_required = _summary_int(approval_gate_summary, "approval_required_count")
    gate_missing = _summary_int(approval_gate_summary, "approval_missing_count")
    gate_unknown = _summary_int(approval_gate_summary, "not_approvable_unknown_count")
    gate_approved = _summary_int(approval_gate_summary, "approved_runtime_write_count")
    gate_write_plan = _summary_int(approval_gate_summary, "write_plan_count")
    next_human = _summary_int(completion_next_actions_summary, "approval_ready_packet_count")
    next_runtime_ready = _summary_int(
        completion_next_actions_summary, "runtime_write_plan_ready_count"
    )
    next_unknown = _summary_int(
        completion_next_actions_summary, "unknown_resolution_required_count"
    )
    next_templates = _summary_int(
        completion_next_actions_summary, "approval_record_template_count"
    )
    next_approved = _summary_int(
        completion_next_actions_summary, "approved_runtime_write_count"
    )
    next_write_plan = _summary_int(completion_next_actions_summary, "write_plan_count")
    packet_count = _summary_int(
        approval_review_packets_summary, "approval_review_packet_count"
    )
    packet_bridge_ready = _summary_int(
        approval_review_packets_summary, "final_score_target_ready_count"
    )
    packet_missing = _summary_int(
        approval_review_packets_summary, "approval_missing_count"
    )
    packet_templates = _summary_int(
        approval_review_packets_summary, "approval_record_template_count"
    )
    packet_template_valid = _summary_int(
        approval_review_packets_summary,
        "approval_record_template_contract_valid_count",
    )
    packet_approved = _summary_int(
        approval_review_packets_summary, "approved_runtime_write_count"
    )
    packet_write_plan = _summary_int(approval_review_packets_summary, "write_plan_count")
    deterministic_approved = _summary_int(
        deterministic_approvals_summary,
        "approved_deterministic_runtime_write_count",
    )
    runtime_execution_summary = runtime_write_execution_summary or {}
    runtime_execution_completed = _summary_int(
        runtime_execution_summary, "runtime_write_completed_count"
    )
    runtime_execution_failed = _summary_int(
        runtime_execution_summary, "runtime_write_failed_count"
    )
    runtime_execution_verified_rows = _summary_int(
        runtime_execution_summary, "post_write_verified_row_count"
    )
    runtime_execution_written_rows = _summary_int(
        runtime_execution_summary, "runtime_rows_written_count"
    ) or _summary_int(runtime_execution_summary, "upserted_row_count")
    runtime_execution_verification_errors = _summary_int(
        runtime_execution_summary, "post_write_verification_error_count"
    )
    runtime_execution_prod_writes = _summary_int(
        runtime_execution_summary, "production_write_allowed_count"
    )
    runtime_execution_clean = (
        runtime_execution_completed > 0
        and runtime_execution_failed == 0
        and runtime_execution_verification_errors == 0
        and runtime_execution_verified_rows == runtime_execution_written_rows
        and runtime_execution_prod_writes == 0
    )
    runtime_executed_deterministic = (
        min(deterministic_approved, runtime_execution_completed)
        if runtime_execution_clean
        else 0
    )
    deterministic_remaining_after_execution = max(
        0, deterministic_approved - runtime_executed_deterministic
    )
    numeric_missing = _summary_int(spec_numeric_validity_summary, "approval_missing_count")
    numeric_approved = _summary_int(
        spec_numeric_validity_summary, "approved_runtime_write_count"
    )

    _append_count_mismatch(
        errors,
        left_name="review_manifest.review_ready_concrete_count",
        left_value=review_concrete,
        right_name="approval_gate.approval_required_count",
        right_value=gate_required,
    )
    _append_count_mismatch(
        errors,
        left_name="review_manifest.review_ready_concrete_count",
        left_value=review_concrete,
        right_name="approval_review_packets.approval_review_packet_count",
        right_value=packet_count,
    )
    _append_count_mismatch(
        errors,
        left_name="approval_review_packets.approval_review_packet_count",
        left_value=packet_count,
        right_name="approval_review_packets.final_score_target_ready_count",
        right_value=packet_bridge_ready,
    )
    _append_count_mismatch(
        errors,
        left_name="review_manifest.review_gated_unknown_count",
        left_value=review_unknown,
        right_name="approval_gate.not_approvable_unknown_count",
        right_value=gate_unknown,
    )
    _append_count_mismatch(
        errors,
        left_name="review_manifest.review_gated_unknown_count",
        left_value=review_unknown,
        right_name="completion_next_actions.unknown_resolution_required_count",
        right_value=next_unknown,
    )
    for right_name, right_value in (
        ("completion_next_actions.approval_ready_packet_count", next_human),
        ("completion_next_actions.approval_record_template_count", next_templates),
        ("approval_review_packets.approval_missing_count", packet_missing),
        ("approval_review_packets.approval_record_template_count", packet_templates),
        (
            "approval_review_packets.approval_record_template_contract_valid_count",
            packet_template_valid,
        ),
        ("spec_numeric_validity.approval_missing_count", numeric_missing),
    ):
        _append_count_mismatch(
            errors,
            left_name="approval_gate.approval_missing_count",
            left_value=gate_missing,
            right_name=right_name,
            right_value=right_value,
        )
    for right_name, right_value in (
        ("approval_gate.write_plan_count", gate_write_plan),
        ("completion_next_actions.runtime_write_plan_ready_count", next_runtime_ready),
        ("completion_next_actions.approved_runtime_write_count", next_approved),
        ("completion_next_actions.write_plan_count", next_write_plan),
        ("approval_review_packets.approved_runtime_write_count", packet_approved),
        ("approval_review_packets.write_plan_count", packet_write_plan),
        ("spec_numeric_validity.approved_runtime_write_count", numeric_approved),
    ):
        _append_count_mismatch(
            errors,
            left_name="approval_gate.approved_runtime_write_count",
            left_value=gate_approved,
            right_name=right_name,
            right_value=right_value,
        )
    if deterministic_remaining_after_execution > gate_approved:
        errors.append(
            "deterministic_approvals.approved_deterministic_runtime_write_count="
            f"{deterministic_approved} leaves "
            f"{deterministic_remaining_after_execution} unexecuted approvals, "
            "which exceeds approval_gate.approved_runtime_write_count="
            f"{gate_approved}"
        )
    for report_name, summary in (
        ("deterministic_approvals", deterministic_approvals_summary),
        ("approval_gate", approval_gate_summary),
        ("completion_next_actions", completion_next_actions_summary),
        ("approval_review_packets", approval_review_packets_summary),
        ("spec_numeric_validity", spec_numeric_validity_summary),
    ):
        production_writes = _summary_int(summary, "production_write_allowed_count")
        if production_writes:
            errors.append(
                f"{report_name}.production_write_allowed_count={production_writes} "
                "must remain 0 for read-only approval audits"
            )
    return errors


def build_report(audit_dir: Path) -> dict[str, Any]:
    file_inventory_path = _first_existing(
        audit_dir / "file_inventory_2026-06-19.json",
        audit_dir / "file_inventory_2026-06-18.json",
    )
    repo_content_path = _first_existing(
        audit_dir / "repo_content_2026-06-19.json",
        audit_dir / "repo_content_2026-06-18.json",
    )
    repo_binary_semantics_path = audit_dir / "repo_binary_semantics_2026-06-19.json"
    code_inventory_path = _first_existing(
        audit_dir / "code_inventory_2026-06-19.json",
        audit_dir / "code_inventory_2026-06-18.json",
    )
    data_catalog_path = _first_existing(
        audit_dir / "data_catalog_2026-06-19.json",
        audit_dir / "data_catalog_2026-06-18.json",
    )
    dockcase_csv_file_evidence_path = (
        audit_dir / "dockcase_csv_file_evidence_2026-06-19.json"
    )
    dockcase_csv_full_scan_path = audit_dir / "dockcase_csv_full_scan_2026-06-19.json"
    dockcase_csv_full_scan_progress_path = (
        audit_dir / "dockcase_csv_full_scan_progress_2026-06-19.json"
    )
    dockcase_csv_semantics_path = audit_dir / "dockcase_csv_semantics_2026-06-18.json"
    dockcase_backlog_path = audit_dir / "dockcase_semantic_backlog_2026-06-18.json"
    a_share_data_path = audit_dir / "a_share_data_semantics_2026-06-18.json"
    market_doc_path = audit_dir / "market_documents_2026-06-18.json"
    frontend_browser_path = audit_dir / "frontend_browser_qa_2026-06-19.json"
    if not frontend_browser_path.exists():
        frontend_browser_path = audit_dir / "frontend_browser_qa_2026-06-18.json"
    frontend_shell_path = audit_dir / "frontend_shell_latency_2026-06-19.json"
    frontend_navigation_path = audit_dir / "frontend_project_ult_navigation_2026-06-19.json"
    frontend_stock_detail_probe_path = (
        audit_dir / "frontend_stock_detail_perf_probe_2026-06-19.json"
    )
    bff_latency_path = audit_dir / "bff_latency_2026-06-19.json"
    bff_concurrent_probe_path = audit_dir / "bff_concurrent_probe_2026-06-19.json"
    module_status_path = audit_dir / "module_status_2026-06-19.json"
    score_trace_path = audit_dir / "a_share_score_trace_2026-06-18.json"
    score_gap_path = audit_dir / "a_share_score_gap_priority_2026-06-18.json"
    score_candidate_path = audit_dir / "a_share_gap_candidate_evidence_2026-06-19.json"
    score_candidate_dry_run_path = (
        audit_dir / "a_share_candidate_score_dry_run_2026-06-19.json"
    )
    score_candidate_upsert_safety_path = (
        audit_dir / "a_share_candidate_upsert_safety_2026-06-19.json"
    )
    score_candidate_staging_path = (
        audit_dir / "a_share_candidate_staging_payloads_2026-06-19.json"
    )
    score_candidate_value_contracts_path = (
        audit_dir / "a_share_candidate_value_contracts_2026-06-19.json"
    )
    score_spec_numeric_validity_path = (
        audit_dir / "a_share_spec_numeric_validity_2026-06-19.json"
    )
    score_spec_score_conversion_path = (
        audit_dir / "a_share_spec_score_conversion_path_2026-06-19.json"
    )
    score_conversion_remediation_path = (
        audit_dir / "a_share_score_conversion_remediation_queue_2026-06-19.json"
    )
    score_formula_policy_review_packets_path = (
        audit_dir / "a_share_formula_policy_review_packets_2026-06-19.json"
    )
    score_governance_suppression_path = (
        audit_dir / "a_share_governance_suppression_verification_2026-06-19.json"
    )
    score_option_universe_na_path = (
        audit_dir / "a_share_option_universe_na_verification_2026-06-19.json"
    )
    score_candidate_generation_queue_path = (
        audit_dir / "a_share_candidate_generation_queue_2026-06-19.json"
    )
    score_l0_source_readiness_path = (
        audit_dir / "a_share_l0_source_readiness_2026-06-19.json"
    )
    score_short_report_evidence_path = (
        audit_dir / "a_share_short_report_evidence_2026-06-19.json"
    )
    score_non_manual_readiness_path = (
        audit_dir / "a_share_non_manual_candidate_readiness_2026-06-19.json"
    )
    score_event_text_draft_path = (
        audit_dir / "a_share_event_text_policy_drafts_2026-06-19.json"
    )
    score_event_text_classification_inputs_path = (
        audit_dir / "a_share_event_text_classification_inputs_2026-06-19.json"
    )
    score_event_text_preclassification_screen_path = (
        audit_dir / "a_share_event_text_preclassification_screen_2026-06-19.json"
    )
    score_event_text_sufficiency_gate_path = (
        audit_dir / "a_share_event_text_sufficiency_gate_2026-06-19.json"
    )
    score_event_text_url_fetchability_path = (
        audit_dir / "a_share_event_text_url_fetchability_2026-06-19.json"
    )
    score_event_text_unknown_source_options_path = (
        audit_dir / "a_share_event_text_unknown_source_options_2026-06-19.json"
    )
    score_event_text_market_doc_evidence_path = (
        audit_dir / "a_share_event_text_market_doc_evidence_2026-06-19.json"
    )
    score_event_text_market_doc_review_packets_path = (
        audit_dir / "a_share_event_text_market_doc_review_packets_2026-06-19.json"
    )
    score_local_structured_draft_path = (
        audit_dir / "a_share_local_structured_policy_drafts_2026-06-19.json"
    )
    score_local_structured_unknown_source_options_path = (
        audit_dir / "a_share_local_structured_unknown_source_options_2026-06-19.json"
    )
    score_local_structured_source_candidates_path = (
        audit_dir / "a_share_local_structured_source_candidates_2026-06-19.json"
    )
    score_local_structured_source_review_packets_path = (
        audit_dir / "a_share_local_structured_source_review_packets_2026-06-19.json"
    )
    score_local_structured_text_draft_path = (
        audit_dir / "a_share_local_structured_text_policy_drafts_2026-06-19.json"
    )
    score_local_structured_text_unknown_source_options_path = (
        audit_dir / "a_share_local_structured_text_unknown_source_options_2026-06-19.json"
    )
    score_single_dependency_draft_path = (
        audit_dir / "a_share_local_single_dependency_policy_drafts_2026-06-19.json"
    )
    score_single_dependency_unknown_source_options_path = (
        audit_dir / "a_share_local_single_dependency_unknown_source_options_2026-06-19.json"
    )
    score_manual_policy_draft_path = (
        audit_dir / "a_share_manual_policy_draft_candidates_2026-06-19.json"
    )
    score_manual_policy_unknown_source_options_path = (
        audit_dir / "a_share_manual_policy_unknown_source_options_2026-06-19.json"
    )
    score_review_staging_manifest_path = (
        audit_dir / "a_share_review_staging_manifest_2026-06-19.json"
    )
    score_review_approval_gate_path = (
        audit_dir / "a_share_review_approval_gate_2026-06-19.json"
    )
    score_deterministic_runtime_approvals_path = (
        audit_dir / "a_share_review_approvals_2026-06-19.json"
    )
    score_completion_next_actions_path = (
        audit_dir / "a_share_completion_next_actions_2026-06-19.json"
    )
    score_unknown_closure_matrix_path = (
        audit_dir / "a_share_unknown_closure_matrix_2026-06-19.json"
    )
    score_unknown_acquisition_backlog_path = (
        audit_dir / "a_share_unknown_acquisition_backlog_2026-06-19.json"
    )
    score_unknown_market_doc_acquisition_path = (
        audit_dir / "a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json"
    )
    score_unknown_event_evidence_adjudication_path = (
        audit_dir / "a_share_unknown_event_evidence_adjudication_2026-06-19.json"
    )
    score_unknown_event_strict_source_gate_path = (
        audit_dir / "a_share_unknown_event_strict_source_gate_2026-06-19.json"
    )
    score_unknown_event_strict_review_packets_path = (
        audit_dir / "a_share_unknown_event_strict_review_packets_2026-06-19.json"
    )
    score_unknown_event_primary_source_confirmation_path = (
        audit_dir
        / "a_share_unknown_event_primary_source_confirmation_2026-06-19.json"
    )
    score_unknown_event_external_source_confirmation_path = (
        audit_dir
        / "a_share_unknown_event_external_source_confirmation_2026-06-19.json"
    )
    score_unknown_local_formula_acquisition_path = (
        audit_dir / "a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json"
    )
    score_unknown_local_formula_review_packets_path = (
        audit_dir / "a_share_unknown_local_formula_review_packets_2026-06-19.json"
    )
    score_local_formula_source_capability_path = (
        audit_dir / "a_share_local_formula_source_capability_2026-06-19.json"
    )
    score_unknown_external_business_metric_acquisition_path = (
        audit_dir / "a_share_unknown_external_business_metric_acquisition_2026-06-19.json"
    )
    score_unknown_external_business_metric_market_doc_path = (
        audit_dir
        / "a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json"
    )
    score_unknown_external_business_metric_review_packets_path = (
        audit_dir / "a_share_unknown_external_business_metric_review_packets_2026-06-19.json"
    )
    score_unknown_external_business_metric_readiness_queue_path = (
        audit_dir / "a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json"
    )
    score_unknown_external_business_metric_policy_drafts_path = (
        audit_dir / "a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json"
    )
    score_unknown_external_business_metric_value_candidates_path = (
        audit_dir
        / "a_share_unknown_external_business_metric_value_candidates_2026-06-19.json"
    )
    score_unknown_external_business_metric_value_review_packets_path = (
        audit_dir
        / "a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json"
    )
    score_unknown_business_metric_value_selection_gate_path = (
        audit_dir
        / "a_share_unknown_business_metric_value_selection_gate_2026-06-19.json"
    )
    score_unknown_penetration_value_priority_path = (
        audit_dir / "a_share_unknown_penetration_value_priority_2026-06-19.json"
    )
    score_unknown_penetration_p1_source_confirmation_path = (
        audit_dir / "a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json"
    )
    score_unknown_penetration_value_policy_draft_path = (
        audit_dir / "a_share_unknown_penetration_value_policy_draft_2026-06-19.json"
    )
    score_unknown_penetration_value_confirmation_packets_path = (
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json"
    )
    score_unknown_penetration_value_confirmation_templates_path = (
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_templates_2026-06-19.json"
    )
    score_unknown_penetration_value_confirmation_gate_path = (
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json"
    )
    score_unknown_penetration_confirmed_known_drafts_path = (
        audit_dir
        / "a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.json"
    )
    score_approval_review_packets_path = (
        audit_dir / "a_share_approval_review_packets_2026-06-19.json"
    )
    score_approval_packet_risk_review_path = (
        audit_dir / "a_share_approval_packet_risk_review_2026-06-19.json"
    )
    score_bulk_review_approval_candidates_path = (
        audit_dir / "a_share_bulk_review_approval_candidates_2026-06-19.json"
    )
    score_bulk_review_source_samples_path = (
        audit_dir / "a_share_bulk_review_source_samples_2026-06-19.json"
    )
    score_event_approval_source_samples_path = (
        audit_dir / "a_share_event_approval_source_samples_2026-06-19.json"
    )
    score_individual_review_source_samples_path = (
        audit_dir / "a_share_individual_review_source_samples_2026-06-19.json"
    )
    score_approval_source_sample_coverage_path = (
        audit_dir / "a_share_approval_source_sample_coverage_2026-06-19.json"
    )
    score_approval_target_scope_readiness_path = (
        audit_dir / "a_share_approval_target_scope_readiness_2026-06-20.json"
    )
    score_approval_materialization_plan_path = (
        audit_dir / "a_share_approval_materialization_plan_2026-06-20.json"
    )
    score_approval_materialization_batch_plan_path = (
        audit_dir / "a_share_approval_materialization_batch_plan_2026-06-20.json"
    )
    score_approval_materialization_batch_codex_review_path = (
        audit_dir
        / "a_share_approval_materialization_batch_codex_review_2026-06-20.json"
    )
    score_approval_materialization_batch_approval_gate_path = (
        audit_dir
        / "a_share_approval_materialization_batch_approval_gate_2026-06-20.json"
    )
    score_approval_materialization_batch_execution_preflight_path = (
        audit_dir
        / "a_share_approval_materialization_batch_execution_preflight_2026-06-20.json"
    )
    score_runtime_scope_approvals_path = (
        audit_dir / "a_share_runtime_scope_approvals_2026-06-19.json"
    )
    score_runtime_write_target_scope_path = (
        audit_dir / "a_share_runtime_write_target_scope_2026-06-19.json"
    )
    score_runtime_write_batch_plan_path = (
        audit_dir / "a_share_runtime_write_batch_plan_2026-06-19.json"
    )
    score_runtime_write_batch_approvals_path = (
        audit_dir / "a_share_runtime_write_batch_approvals_2026-06-19.json"
    )
    score_runtime_write_execution_path = (
        audit_dir / "a_share_runtime_write_execution_2026-06-19.json"
    )
    score_runtime_write_preflight_path = (
        audit_dir / "a_share_runtime_write_preflight_2026-06-19.json"
    )
    score_field_closure_path = audit_dir / "a_share_score_field_closure_2026-06-19.json"

    file_inventory = _load_json(file_inventory_path)
    repo_content = _load_json(repo_content_path)
    repo_binary_semantics = _load_json(repo_binary_semantics_path)
    code_inventory = _load_json(code_inventory_path)
    data_catalog = _load_json(data_catalog_path)
    dockcase_csv_file_evidence = _load_json(dockcase_csv_file_evidence_path)
    dockcase_csv_full_scan = _load_json(dockcase_csv_full_scan_path)
    dockcase_csv_full_scan_progress = _load_json(dockcase_csv_full_scan_progress_path)
    dockcase_csv_semantics = _load_json(dockcase_csv_semantics_path)
    dockcase_backlog = _load_json(dockcase_backlog_path)
    dockcase_backlog_batches = _load_dockcase_backlog_batches(audit_dir)
    dockcase_backlog_batch_summary = _dockcase_backlog_batch_summary(dockcase_backlog_batches)
    a_share_data = _load_json(a_share_data_path)
    market_doc = _load_json(market_doc_path)
    frontend_browser = _load_json(frontend_browser_path)
    frontend_shell = _load_json(frontend_shell_path)
    frontend_navigation = _load_json(frontend_navigation_path)
    frontend_stock_detail_probe = _load_json(frontend_stock_detail_probe_path)
    bff_latency = _load_json(bff_latency_path)
    bff_concurrent_probe = _load_json(bff_concurrent_probe_path)
    module_status = _load_json(module_status_path)
    score_trace = _load_json(score_trace_path)
    score_gap = _load_json(score_gap_path)
    score_candidate = _load_json(score_candidate_path)
    score_candidate_dry_run = _load_json(score_candidate_dry_run_path)
    score_candidate_upsert_safety = _load_json(score_candidate_upsert_safety_path)
    score_candidate_staging = _load_json(score_candidate_staging_path)
    score_candidate_value_contracts = _load_json(score_candidate_value_contracts_path)
    score_spec_numeric_validity = _load_json(score_spec_numeric_validity_path)
    score_spec_score_conversion = _load_json(score_spec_score_conversion_path)
    score_conversion_remediation = _load_json(score_conversion_remediation_path)
    score_formula_policy_review_packets = _load_json(score_formula_policy_review_packets_path)
    score_governance_suppression = _load_json(score_governance_suppression_path)
    score_option_universe_na = _load_json(score_option_universe_na_path)
    score_candidate_generation_queue = _load_json(score_candidate_generation_queue_path)
    score_l0_source_readiness = _load_json(score_l0_source_readiness_path)
    score_short_report_evidence = _load_json(score_short_report_evidence_path)
    score_non_manual_readiness = _load_json(score_non_manual_readiness_path)
    score_event_text_draft = _load_json(score_event_text_draft_path)
    score_event_text_classification_inputs = _load_json(
        score_event_text_classification_inputs_path
    )
    score_event_text_preclassification_screen = _load_json(
        score_event_text_preclassification_screen_path
    )
    score_event_text_sufficiency_gate = _load_json(
        score_event_text_sufficiency_gate_path
    )
    score_event_text_url_fetchability = _load_json(
        score_event_text_url_fetchability_path
    )
    score_event_text_unknown_source_options = _load_json(
        score_event_text_unknown_source_options_path
    )
    score_event_text_market_doc_evidence = _load_json(
        score_event_text_market_doc_evidence_path
    )
    score_event_text_market_doc_review_packets = _load_json(
        score_event_text_market_doc_review_packets_path
    )
    score_local_structured_draft = _load_json(score_local_structured_draft_path)
    score_local_structured_unknown_source_options = _load_json(
        score_local_structured_unknown_source_options_path
    )
    score_local_structured_source_candidates = _load_json(
        score_local_structured_source_candidates_path
    )
    score_local_structured_source_review_packets = _load_json(
        score_local_structured_source_review_packets_path
    )
    score_local_structured_text_draft = _load_json(score_local_structured_text_draft_path)
    score_local_structured_text_unknown_source_options = _load_json(
        score_local_structured_text_unknown_source_options_path
    )
    score_single_dependency_draft = _load_json(score_single_dependency_draft_path)
    score_single_dependency_unknown_source_options = _load_json(
        score_single_dependency_unknown_source_options_path
    )
    score_manual_policy_draft = _load_json(score_manual_policy_draft_path)
    score_manual_policy_unknown_source_options = _load_json(
        score_manual_policy_unknown_source_options_path
    )
    score_review_staging_manifest = _load_json(score_review_staging_manifest_path)
    score_review_approval_gate = _load_json(score_review_approval_gate_path)
    score_deterministic_runtime_approvals = _load_json(
        score_deterministic_runtime_approvals_path
    )
    score_completion_next_actions = _load_json(score_completion_next_actions_path)
    score_unknown_closure_matrix = _load_json(score_unknown_closure_matrix_path)
    score_unknown_acquisition_backlog = _load_json(
        score_unknown_acquisition_backlog_path
    )
    score_unknown_market_doc_acquisition = _load_json(
        score_unknown_market_doc_acquisition_path
    )
    score_unknown_event_evidence_adjudication = _load_json(
        score_unknown_event_evidence_adjudication_path
    )
    score_unknown_event_strict_source_gate = _load_json(
        score_unknown_event_strict_source_gate_path
    )
    score_unknown_event_strict_review_packets = _load_json(
        score_unknown_event_strict_review_packets_path
    )
    score_unknown_event_primary_source_confirmation = _load_json(
        score_unknown_event_primary_source_confirmation_path
    )
    score_unknown_event_external_source_confirmation = _load_json(
        score_unknown_event_external_source_confirmation_path
    )
    score_unknown_local_formula_acquisition = _load_json(
        score_unknown_local_formula_acquisition_path
    )
    score_unknown_local_formula_review_packets = _load_json(
        score_unknown_local_formula_review_packets_path
    )
    score_local_formula_source_capability = _load_json(
        score_local_formula_source_capability_path
    )
    score_unknown_external_business_metric_acquisition = _load_json(
        score_unknown_external_business_metric_acquisition_path
    )
    score_unknown_external_business_metric_market_doc = _load_json(
        score_unknown_external_business_metric_market_doc_path
    )
    score_unknown_external_business_metric_review_packets = _load_json(
        score_unknown_external_business_metric_review_packets_path
    )
    score_unknown_external_business_metric_readiness_queue = _load_json(
        score_unknown_external_business_metric_readiness_queue_path
    )
    score_unknown_external_business_metric_policy_drafts = _load_json(
        score_unknown_external_business_metric_policy_drafts_path
    )
    score_unknown_external_business_metric_value_candidates = _load_json(
        score_unknown_external_business_metric_value_candidates_path
    )
    score_unknown_external_business_metric_value_review_packets = _load_json(
        score_unknown_external_business_metric_value_review_packets_path
    )
    score_unknown_business_metric_value_selection_gate = _load_json(
        score_unknown_business_metric_value_selection_gate_path
    )
    score_unknown_penetration_value_priority = _load_json(
        score_unknown_penetration_value_priority_path
    )
    score_unknown_penetration_p1_source_confirmation = _load_json(
        score_unknown_penetration_p1_source_confirmation_path
    )
    score_unknown_penetration_value_policy_draft = _load_json(
        score_unknown_penetration_value_policy_draft_path
    )
    score_unknown_penetration_value_confirmation_packets = _load_json(
        score_unknown_penetration_value_confirmation_packets_path
    )
    score_unknown_penetration_value_confirmation_template_bundle = _load_json(
        score_unknown_penetration_value_confirmation_templates_path
    )
    score_unknown_penetration_value_confirmation_gate = _load_json(
        score_unknown_penetration_value_confirmation_gate_path
    )
    score_unknown_penetration_confirmed_known_drafts = _load_json(
        score_unknown_penetration_confirmed_known_drafts_path
    )
    score_approval_review_packets = _load_json(score_approval_review_packets_path)
    score_approval_packet_risk_review = _load_json(
        score_approval_packet_risk_review_path
    )
    score_bulk_review_approval_candidates = _load_json(
        score_bulk_review_approval_candidates_path
    )
    score_bulk_review_source_samples = _load_json(score_bulk_review_source_samples_path)
    score_event_approval_source_samples = _load_json(
        score_event_approval_source_samples_path
    )
    score_individual_review_source_samples = _load_json(
        score_individual_review_source_samples_path
    )
    score_approval_source_sample_coverage = _load_json(
        score_approval_source_sample_coverage_path
    )
    score_approval_target_scope_readiness = _load_json(
        score_approval_target_scope_readiness_path
    )
    score_approval_materialization_plan = _load_json(
        score_approval_materialization_plan_path
    )
    score_approval_materialization_batch_plan = _load_json(
        score_approval_materialization_batch_plan_path
    )
    score_approval_materialization_batch_codex_review = _load_json(
        score_approval_materialization_batch_codex_review_path
    )
    score_approval_materialization_batch_approval_gate = _load_json(
        score_approval_materialization_batch_approval_gate_path
    )
    score_approval_materialization_batch_execution_preflight = _load_json(
        score_approval_materialization_batch_execution_preflight_path
    )
    score_runtime_scope_approvals = _load_json(score_runtime_scope_approvals_path)
    score_runtime_write_target_scope = _load_json(score_runtime_write_target_scope_path)
    score_runtime_write_batch_plan = _load_json(score_runtime_write_batch_plan_path)
    score_runtime_write_batch_approvals = _load_json(
        score_runtime_write_batch_approvals_path
    )
    score_runtime_write_execution = _load_json(score_runtime_write_execution_path)
    score_runtime_write_preflight = _load_json(score_runtime_write_preflight_path)
    score_field_closure = _load_json(score_field_closure_path)
    market_summary = market_doc.get("summary", {})
    market_gaps = market_summary.get("coverage_gaps", {})
    market_full_parse = bool(
        market_summary.get("document_files_total")
        and market_summary.get("documents_successfully_parsed")
        == market_summary.get("document_files_total")
        and market_gaps.get("document_files_not_selected_for_extractability_sampling")
        == 0
        and market_gaps.get("selected_documents_without_successful_parse") == 0
    )

    repo_files = _root(file_inventory, "repo_operational")
    dock_db = _root(file_inventory, "dockcase_database_all_pruned")
    dock_market = _root(file_inventory, "dockcase_market_data")
    data_db = _root(data_catalog, "/Volumes/dockcase2tb/database_all")
    data_market = _root(data_catalog, "/Volumes/dockcase2tb/market_data")
    code_totals = code_inventory.get("totals", {})
    module_counts = module_status.get("counts", {})
    module_local_counts = (
        module_status.get("local_runtime_data_tooling_surfaces", {}).get("counts", {})
    )
    module_combined_counts = module_status.get("combined_inventory_counts", {})
    module_classification_policy = module_status.get("classification_policy", {})
    module_runtime_evidence_policy = module_status.get("runtime_evidence_policy", {})
    dockcase_file_evidence_summary = dockcase_csv_file_evidence.get("summary", {})
    dockcase_full_scan_summary = (
        dockcase_csv_full_scan_progress.get("summary")
        or dockcase_csv_full_scan.get("summary", {})
    )
    dockcase_full_scan_complete = bool(
        dockcase_full_scan_summary.get("full_row_semantic_scan_complete")
    )
    frontend_stock_detail_probe_summary = frontend_stock_detail_probe.get(
        "summary", {}
    )
    bff_concurrent_probe_summary = bff_concurrent_probe.get("summary", {})
    bff_ok = bool(bff_latency.get("all_ok") and bff_latency.get("all_under_threshold"))
    bff_concurrent_ok = bool(
        bff_concurrent_probe_summary.get("all_ok")
        and bff_concurrent_probe_summary.get("all_under_threshold")
    )
    frontend_stock_detail_probe_ok = bool(
        frontend_stock_detail_probe_summary.get("path_graph_ready_under_1000ms")
        and frontend_stock_detail_probe_summary.get("console_error_warn_count") == 0
    )
    frontend_browser_legacy_ok = bool(
        frontend_browser.get("all_warm_under_threshold")
        and not any(
            route.get("any_error_overlay")
            for route in frontend_browser.get("routes", {}).values()
        )
    )
    frontend_latest_recheck = frontend_browser.get("latest_project_ult_route_recheck", {})
    frontend_latest_routes = frontend_latest_recheck.get("routes", [])
    frontend_browser_summary = frontend_browser.get("summary", {})
    frontend_latest_ok = bool(
        frontend_latest_recheck.get("summary", {}).get("warm_commit_to_h1_under_1000ms")
        and frontend_latest_routes
        and all(route.get("result") == "pass" for route in frontend_latest_routes)
    )
    frontend_browser_ok = frontend_browser_legacy_ok or frontend_latest_ok
    frontend_shell_ok = bool(
        frontend_shell.get("all_ok")
        and frontend_shell.get("all_under_threshold")
        and frontend_shell.get("route_count", 0) >= 20
    )
    frontend_navigation_ok = bool(
        frontend_navigation.get("all_ok")
        and frontend_navigation.get("summary", {}).get("missing_route_shell_count") == 0
        and frontend_navigation.get("summary", {}).get("missing_link_shell_count") == 0
    )
    score_gap_summary = score_gap.get("summary", {})
    score_actionable_gaps = int(
        score_gap_summary.get(
            "actionable_participating_gap_dp_ids",
            score_gap_summary.get("participating_gap_dp_ids") or 0,
        )
        or 0
    )
    score_governance_gaps = int(
        score_gap_summary.get("governance_or_intentional_participating_gap_dp_ids")
        or 0
    )
    skipped_file_fingerprints_count = int(
        repo_content.get("skipped_file_fingerprints_count")
        or len(repo_content.get("skipped_file_fingerprints", []))
        or len(repo_content.get("skipped_file_samples", []))
    )
    repo_binary_summary = repo_binary_semantics.get("summary", {})
    repo_binary_semantics_complete = bool(
        skipped_file_fingerprints_count
        and repo_binary_summary.get("all_skipped_files_classified")
        and repo_binary_summary.get("semantic_records") == skipped_file_fingerprints_count
        and repo_binary_summary.get("semantic_error_count") == 0
        and repo_binary_summary.get("missing_file_count") == 0
    )
    score_formula_actionable_gaps = int(
        score_gap_summary.get("actionable_formula_gap_dp_ids") or 0
    )
    score_candidate_summary = score_candidate.get("summary", {})
    score_candidate_dry_run_summary = score_candidate_dry_run.get("summary", {})
    score_candidate_upsert_safety_summary = score_candidate_upsert_safety.get("summary", {})
    score_candidate_staging_summary = score_candidate_staging.get("summary", {})
    score_candidate_value_contracts_summary = score_candidate_value_contracts.get("summary", {})
    score_spec_numeric_validity_summary = score_spec_numeric_validity.get("summary", {})
    score_spec_score_conversion_summary = score_spec_score_conversion.get("summary", {})
    score_conversion_remediation_summary = score_conversion_remediation.get("summary", {})
    score_formula_policy_review_packets_summary = (
        score_formula_policy_review_packets.get("summary", {})
    )
    score_governance_suppression_summary = score_governance_suppression.get(
        "summary", {}
    )
    score_option_universe_na_summary = score_option_universe_na.get("summary", {})
    score_candidate_generation_queue_summary = score_candidate_generation_queue.get("summary", {})
    score_l0_source_readiness_summary = score_l0_source_readiness.get("summary", {})
    score_short_report_evidence_summary = score_short_report_evidence.get("summary", {})
    score_non_manual_readiness_summary = score_non_manual_readiness.get("summary", {})
    score_event_text_draft_summary = score_event_text_draft.get("summary", {})
    score_event_text_classification_inputs_summary = (
        score_event_text_classification_inputs.get("summary", {})
    )
    score_event_text_preclassification_screen_summary = (
        score_event_text_preclassification_screen.get("summary", {})
    )
    score_event_text_sufficiency_gate_summary = (
        score_event_text_sufficiency_gate.get("summary", {})
    )
    score_event_text_url_fetchability_summary = (
        score_event_text_url_fetchability.get("summary", {})
    )
    score_event_text_unknown_source_options_summary = (
        score_event_text_unknown_source_options.get("summary", {})
    )
    score_event_text_market_doc_evidence_summary = (
        score_event_text_market_doc_evidence.get("summary", {})
    )
    score_event_text_market_doc_review_packets_summary = (
        score_event_text_market_doc_review_packets.get("summary", {})
    )
    score_local_structured_draft_summary = score_local_structured_draft.get("summary", {})
    score_local_structured_unknown_source_options_summary = (
        score_local_structured_unknown_source_options.get("summary", {})
    )
    score_local_structured_source_candidates_summary = (
        score_local_structured_source_candidates.get("summary", {})
    )
    score_local_structured_source_review_packets_summary = (
        score_local_structured_source_review_packets.get("summary", {})
    )
    score_local_structured_text_draft_summary = score_local_structured_text_draft.get(
        "summary", {}
    )
    score_local_structured_text_unknown_source_options_summary = (
        score_local_structured_text_unknown_source_options.get("summary", {})
    )
    score_single_dependency_draft_summary = score_single_dependency_draft.get("summary", {})
    score_single_dependency_unknown_source_options_summary = (
        score_single_dependency_unknown_source_options.get("summary", {})
    )
    score_single_dependency_unknown_source_options_rows = []
    for row in score_single_dependency_unknown_source_options.get("rows") or []:
        if not isinstance(row, dict):
            continue
        score_single_dependency_unknown_source_options_rows.append(
            {
                "dp_id": row.get("dp_id"),
                "score_target": row.get("score_target"),
                "resolution_status": row.get("resolution_status"),
                "source_dependencies": list(row.get("source_dependencies") or []),
                "required_evidence": list(row.get("required_evidence") or []),
                "candidate_source_routes": list(row.get("candidate_source_routes") or []),
                "lifecycle_policy_review_template_contract_valid": row.get(
                    "lifecycle_policy_review_template_contract_valid"
                ),
                "known_draft_sufficient": row.get("known_draft_sufficient"),
                "approval_ready": row.get("approval_ready"),
                "production_write_allowed": row.get("production_write_allowed"),
            }
        )
    score_manual_policy_draft_summary = score_manual_policy_draft.get("summary", {})
    score_manual_policy_unknown_source_options_summary = (
        score_manual_policy_unknown_source_options.get("summary", {})
    )
    score_review_staging_manifest_summary = score_review_staging_manifest.get("summary", {})
    score_review_approval_gate_summary = score_review_approval_gate.get("summary", {})
    score_deterministic_runtime_approvals_summary = (
        score_deterministic_runtime_approvals.get("summary", {})
    )
    score_completion_next_actions_summary = score_completion_next_actions.get("summary", {})
    score_unknown_closure_matrix_summary = score_unknown_closure_matrix.get("summary", {})
    score_unknown_acquisition_backlog_summary = score_unknown_acquisition_backlog.get(
        "summary", {}
    )
    score_unknown_market_doc_acquisition_summary = (
        score_unknown_market_doc_acquisition.get("summary", {})
    )
    score_unknown_event_evidence_adjudication_summary = (
        score_unknown_event_evidence_adjudication.get("summary", {})
    )
    score_unknown_event_strict_source_gate_summary = (
        score_unknown_event_strict_source_gate.get("summary", {})
    )
    score_unknown_event_strict_review_packets_summary = (
        score_unknown_event_strict_review_packets.get("summary", {})
    )
    score_unknown_event_primary_source_confirmation_summary = (
        score_unknown_event_primary_source_confirmation.get("summary", {})
    )
    score_unknown_event_external_source_confirmation_summary = (
        score_unknown_event_external_source_confirmation.get("summary", {})
    )
    score_unknown_local_formula_acquisition_summary = (
        score_unknown_local_formula_acquisition.get("summary", {})
    )
    score_unknown_local_formula_review_packets_summary = (
        score_unknown_local_formula_review_packets.get("summary", {})
    )
    score_local_formula_source_capability_summary = (
        score_local_formula_source_capability.get("summary", {})
    )
    score_unknown_external_business_metric_acquisition_summary = (
        score_unknown_external_business_metric_acquisition.get("summary", {})
    )
    score_unknown_external_business_metric_market_doc_summary = (
        score_unknown_external_business_metric_market_doc.get("summary", {})
    )
    score_unknown_external_business_metric_review_packets_summary = (
        score_unknown_external_business_metric_review_packets.get("summary", {})
    )
    score_unknown_external_business_metric_readiness_queue_summary = (
        score_unknown_external_business_metric_readiness_queue.get("summary", {})
    )
    score_unknown_external_business_metric_policy_drafts_summary = (
        score_unknown_external_business_metric_policy_drafts.get("summary", {})
    )
    score_unknown_external_business_metric_value_candidates_summary = (
        score_unknown_external_business_metric_value_candidates.get("summary", {})
    )
    score_unknown_external_business_metric_value_review_packets_summary = (
        score_unknown_external_business_metric_value_review_packets.get("summary", {})
    )
    score_unknown_business_metric_value_selection_gate_summary = (
        score_unknown_business_metric_value_selection_gate.get("summary", {})
    )
    score_unknown_penetration_value_priority_summary = (
        score_unknown_penetration_value_priority.get("summary", {})
    )
    score_unknown_penetration_p1_source_confirmation_summary = (
        score_unknown_penetration_p1_source_confirmation.get("summary", {})
    )
    score_unknown_penetration_value_policy_draft_summary = (
        score_unknown_penetration_value_policy_draft.get("summary", {})
    )
    score_unknown_penetration_value_confirmation_packets_summary = (
        score_unknown_penetration_value_confirmation_packets.get("summary", {})
    )
    score_unknown_penetration_value_confirmation_templates_summary = (
        score_unknown_penetration_value_confirmation_template_bundle.get("summary", {})
    )
    score_unknown_penetration_value_confirmation_gate_summary = (
        score_unknown_penetration_value_confirmation_gate.get("summary", {})
    )
    score_unknown_penetration_confirmed_known_drafts_summary = (
        score_unknown_penetration_confirmed_known_drafts.get("summary", {})
    )
    score_approval_review_packets_summary = score_approval_review_packets.get("summary", {})
    score_approval_packet_risk_review_summary = (
        score_approval_packet_risk_review.get("summary", {})
    )
    score_bulk_review_approval_candidates_summary = (
        score_bulk_review_approval_candidates.get("summary", {})
    )
    score_bulk_review_source_samples_summary = (
        score_bulk_review_source_samples.get("summary", {})
    )
    score_event_approval_source_samples_summary = (
        score_event_approval_source_samples.get("summary", {})
    )
    score_individual_review_source_samples_summary = (
        score_individual_review_source_samples.get("summary", {})
    )
    score_approval_source_sample_coverage_summary = (
        score_approval_source_sample_coverage.get("summary", {})
    )
    score_approval_target_scope_readiness_summary = (
        score_approval_target_scope_readiness.get("summary", {})
    )
    score_approval_materialization_plan_summary = (
        score_approval_materialization_plan.get("summary", {})
    )
    score_approval_materialization_batch_plan_summary = (
        score_approval_materialization_batch_plan.get("summary", {})
    )
    score_approval_materialization_batch_codex_review_summary = (
        score_approval_materialization_batch_codex_review.get("summary", {})
    )
    score_approval_materialization_batch_approval_gate_summary = (
        score_approval_materialization_batch_approval_gate.get("summary", {})
    )
    score_approval_materialization_batch_execution_preflight_summary = (
        score_approval_materialization_batch_execution_preflight.get("summary", {})
    )
    score_runtime_scope_approvals_summary = score_runtime_scope_approvals.get(
        "summary", {}
    )
    score_runtime_write_target_scope_summary = score_runtime_write_target_scope.get(
        "summary", {}
    )
    score_runtime_write_batch_plan_summary = score_runtime_write_batch_plan.get(
        "summary", {}
    )
    score_runtime_write_batch_approvals_summary = (
        score_runtime_write_batch_approvals.get("summary", {})
    )
    score_runtime_write_execution_summary = score_runtime_write_execution.get(
        "summary", {}
    )
    score_runtime_write_preflight_summary = score_runtime_write_preflight.get(
        "summary", {}
    )
    score_field_closure_summary = score_field_closure.get("summary", {})
    score_candidate_ready = int(score_candidate_summary.get("candidate_input_ready_count") or 0)
    score_candidate_not_ready = int(
        score_candidate_summary.get("candidate_input_not_ready_count") or 0
    )
    score_closed_fields = int(score_field_closure_summary.get("closed_score_relevant_dp_ids") or 0)
    score_relevant_fields = int(score_field_closure_summary.get("score_relevant_spec_dp_ids") or 0)
    score_safe_upsert_fallback = int(
        score_field_closure_summary.get(
            "safe_to_upsert_without_review_count",
            score_candidate_summary.get("safe_to_upsert_without_review_count") or 0,
        )
        or 0
    )
    score_safe_upsert = int(
        score_candidate_upsert_safety_summary.get(
            "safe_to_upsert_without_review_count",
            score_safe_upsert_fallback,
        )
        or 0
    )
    score_dry_run_ready = int(
        score_candidate_dry_run_summary.get("final_score_target_ready_count") or 0
    )
    score_dry_run_checked = int(
        score_candidate_dry_run_summary.get("candidate_ready_rows_checked") or 0
    )
    score_dry_run_blocked = int(
        score_candidate_dry_run_summary.get("bridge_blocked_count") or 0
    )
    score_upsert_checked = int(
        score_candidate_upsert_safety_summary.get("candidate_rows_checked")
        or score_dry_run_checked
    )
    score_upsert_review_gated = int(
        score_candidate_upsert_safety_summary.get("review_gated_count") or 0
    )
    score_upsert_blocked = int(
        score_candidate_upsert_safety_summary.get("blocked_count") or 0
    )
    score_staging_payloads = int(
        score_candidate_staging_summary.get("deterministic_staging_payload_count") or 0
    )
    score_staging_generator_required = int(
        score_candidate_staging_summary.get("generator_required_count") or 0
    )
    score_staging_prod_writes = int(
        score_candidate_staging_summary.get("production_write_allowed_count") or 0
    )
    score_contract_valid = int(
        score_candidate_value_contracts_summary.get("contract_valid_count") or 0
    )
    score_contract_invalid = int(
        score_candidate_value_contracts_summary.get("contract_invalid_count") or 0
    )
    score_contract_bridge_concrete = int(
        score_candidate_value_contracts_summary.get("bridge_validated_concrete_count") or 0
    )
    score_generation_tasks = int(
        score_candidate_generation_queue_summary.get("generator_required_task_count") or 0
    )
    score_generation_queue_valid = bool(
        score_candidate_generation_queue_summary.get(
            "all_tasks_have_valid_placeholder_contract"
        )
    )
    score_l0_source_blocking_gaps = int(
        score_l0_source_readiness_summary.get("blocking_gap_count") or 0
    )
    score_l0_source_p2 = int(
        (score_l0_source_readiness_summary.get("priority_counts") or {}).get(
            "P2_llm_or_web_extraction"
        )
        or 0
    )
    score_l0_source_p3 = int(
        (score_l0_source_readiness_summary.get("priority_counts") or {}).get(
            "P3_manual_review"
        )
        or 0
    )
    score_l0_source_event_route = int(
        (
            score_l0_source_readiness_summary.get("recommended_source_route_counts")
            or {}
        ).get("event_llm_from_runtime_news")
        or 0
    )
    score_l0_source_local_route = int(
        (
            score_l0_source_readiness_summary.get("recommended_source_route_counts")
            or {}
        ).get("local_llm_closed_loop")
        or 0
    )
    score_l0_source_manual_route = int(
        (
            score_l0_source_readiness_summary.get("recommended_source_route_counts")
            or {}
        ).get("manual_design_review")
        or 0
    )
    score_l0_source_direct_tushare_remaining = int(
        score_l0_source_readiness_summary.get("direct_structured_tushare_remaining")
        or 0
    )
    score_l0_source_runtime_rows = len(
        score_l0_source_readiness_summary.get("dependency_dp_ids_with_runtime_rows")
        or []
    )
    score_l0_source_missing_runtime_rows = len(
        score_l0_source_readiness_summary.get(
            "dependency_dp_ids_without_runtime_rows"
        )
        or []
    )
    score_short_report_files_scanned = int(
        score_short_report_evidence_summary.get("news_html_files_scanned") or 0
    )
    score_short_report_parse_errors = int(
        score_short_report_evidence_summary.get("parse_error_count") or 0
    )
    score_short_report_strict_docs = int(
        score_short_report_evidence_summary.get("strict_short_report_documents") or 0
    )
    score_short_report_direct_docs = int(
        score_short_report_evidence_summary.get("direct_a_share_short_report_documents")
        or 0
    )
    score_short_report_foreign_docs = int(
        score_short_report_evidence_summary.get(
            "foreign_or_market_short_report_documents"
        )
        or 0
    )
    score_short_report_direct_ts_codes = int(
        score_short_report_evidence_summary.get("direct_a_share_ts_code_count") or 0
    )
    score_short_report_candidate_ready = bool(
        score_short_report_evidence_summary.get("candidate_evidence_ready")
    )
    score_non_manual_tasks = int(
        score_non_manual_readiness_summary.get("non_manual_task_count") or 0
    )
    score_non_manual_placeholder_valid = int(
        score_non_manual_readiness_summary.get("placeholder_contract_valid_count") or 0
    )
    score_non_manual_output_contract_valid = int(
        score_non_manual_readiness_summary.get("output_contract_shape_valid_count") or 0
    )
    score_non_manual_bridge_ready = int(
        score_non_manual_readiness_summary.get("bridge_probe_ready_count") or 0
    )
    score_non_manual_deterministic = int(
        score_non_manual_readiness_summary.get("deterministic_known_draft_allowed_count") or 0
    )
    score_non_manual_prod_writes = int(
        score_non_manual_readiness_summary.get("production_write_allowed_count") or 0
    )
    score_event_text_tasks = int(
        score_event_text_draft_summary.get("event_text_task_count") or 0
    )
    score_event_text_known = int(
        score_event_text_draft_summary.get("draft_known_count") or 0
    )
    score_event_text_unknown = int(
        score_event_text_draft_summary.get("draft_unknown_count") or 0
    )
    score_event_text_contract_valid = int(
        score_event_text_draft_summary.get("draft_contract_valid_count") or 0
    )
    score_event_text_contract_invalid = int(
        score_event_text_draft_summary.get("draft_contract_invalid_count") or 0
    )
    score_event_text_bridge = int(
        score_event_text_draft_summary.get("bridge_validated_known_count") or 0
    )
    score_event_text_review_required = int(
        score_event_text_draft_summary.get("review_required_count") or 0
    )
    score_event_text_safe_upsert = int(
        score_event_text_draft_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_event_text_prod_writes = int(
        score_event_text_draft_summary.get("production_write_allowed_count") or 0
    )
    score_event_text_input_packets = int(
        score_event_text_classification_inputs_summary.get("classification_input_packet_count")
        or 0
    )
    score_event_text_input_ready = int(
        score_event_text_classification_inputs_summary.get("classification_input_ready_count")
        or 0
    )
    score_event_text_input_missing = int(
        score_event_text_classification_inputs_summary.get("missing_headline_input_count")
        or 0
    )
    score_event_text_headlines = int(
        score_event_text_classification_inputs_summary.get("headline_input_count") or 0
    )
    score_event_text_unique_headlines = int(
        score_event_text_classification_inputs_summary.get("unique_headline_count") or 0
    )
    score_event_text_full_text = int(
        score_event_text_classification_inputs_summary.get("full_article_text_available_count")
        or 0
    )
    score_event_text_title_only = int(
        score_event_text_classification_inputs_summary.get("title_level_only_count") or 0
    )
    score_event_text_classified_known = int(
        score_event_text_classification_inputs_summary.get("classified_known_count") or 0
    )
    score_event_text_input_prod_writes = int(
        score_event_text_classification_inputs_summary.get("production_write_allowed_count")
        or 0
    )
    score_event_text_pre_packets = int(
        score_event_text_preclassification_screen_summary.get("preclassification_packet_count")
        or 0
    )
    score_event_text_pre_screened = int(
        score_event_text_preclassification_screen_summary.get("packets_screened_count")
        or 0
    )
    score_event_text_pre_target_hits = int(
        score_event_text_preclassification_screen_summary.get("target_keyword_hit_packet_count")
        or 0
    )
    score_event_text_pre_transmission_hits = int(
        score_event_text_preclassification_screen_summary.get(
            "a_share_transmission_hit_packet_count"
        )
        or 0
    )
    score_event_text_pre_target_and_transmission = int(
        score_event_text_preclassification_screen_summary.get(
            "target_and_transmission_hit_packet_count"
        )
        or 0
    )
    score_event_text_pre_direct_known = int(
        score_event_text_preclassification_screen_summary.get("direct_known_candidate_count")
        or 0
    )
    score_event_text_pre_review_required = int(
        score_event_text_preclassification_screen_summary.get("review_required_count")
        or 0
    )
    score_event_text_pre_prod_writes = int(
        score_event_text_preclassification_screen_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_event_text_suff_packets = int(
        score_event_text_sufficiency_gate_summary.get("sufficiency_packet_count") or 0
    )
    score_event_text_suff_target_headlines = int(
        score_event_text_sufficiency_gate_summary.get("target_headline_packet_count") or 0
    )
    score_event_text_suff_broad_only = int(
        score_event_text_sufficiency_gate_summary.get(
            "broad_market_only_transmission_packet_count"
        )
        or 0
    )
    score_event_text_suff_same_any = int(
        score_event_text_sufficiency_gate_summary.get(
            "same_headline_target_and_any_transmission_packet_count"
        )
        or 0
    )
    score_event_text_suff_same_direct = int(
        score_event_text_sufficiency_gate_summary.get(
            "same_headline_target_and_direct_transmission_packet_count"
        )
        or 0
    )
    score_event_text_suff_classifier_ready = int(
        score_event_text_sufficiency_gate_summary.get(
            "title_signal_sufficient_for_classifier_count"
        )
        or 0
    )
    score_event_text_suff_known_allowed = int(
        score_event_text_sufficiency_gate_summary.get("known_candidate_allowed_count")
        or 0
    )
    score_event_text_suff_prod_writes = int(
        score_event_text_sufficiency_gate_summary.get("production_write_allowed_count")
        or 0
    )
    score_event_text_url_unique = int(
        score_event_text_url_fetchability_summary.get("unique_url_count") or 0
    )
    score_event_text_url_fetch_success = int(
        score_event_text_url_fetchability_summary.get("fetch_success_count") or 0
    )
    score_event_text_url_primary_text = int(
        score_event_text_url_fetchability_summary.get("primary_text_available_url_count")
        or 0
    )
    score_event_text_body_packets = int(
        score_event_text_url_fetchability_summary.get("body_packet_count") or 0
    )
    score_event_text_body_target_hits = int(
        score_event_text_url_fetchability_summary.get("body_target_hit_packet_count")
        or 0
    )
    score_event_text_body_direct_hits = int(
        score_event_text_url_fetchability_summary.get(
            "body_direct_transmission_hit_packet_count"
        )
        or 0
    )
    score_event_text_body_classifier_ready = int(
        score_event_text_url_fetchability_summary.get(
            "body_signal_sufficient_for_classifier_count"
        )
        or 0
    )
    score_event_text_body_known_allowed = int(
        score_event_text_url_fetchability_summary.get("known_candidate_allowed_count")
        or 0
    )
    score_event_text_body_prod_writes = int(
        score_event_text_url_fetchability_summary.get("production_write_allowed_count")
        or 0
    )
    score_event_text_unknown_options = int(
        score_event_text_unknown_source_options_summary.get("unknown_event_text_count")
        or 0
    )
    score_event_text_unknown_input_ready = int(
        score_event_text_unknown_source_options_summary.get(
            "classification_input_ready_count"
        )
        or 0
    )
    score_event_text_unknown_body_ready = int(
        score_event_text_unknown_source_options_summary.get("body_text_available_count")
        or 0
    )
    score_event_text_unknown_target_present = int(
        score_event_text_unknown_source_options_summary.get(
            "target_event_evidence_present_count"
        )
        or 0
    )
    score_event_text_unknown_direct_present = int(
        score_event_text_unknown_source_options_summary.get(
            "direct_a_share_transmission_present_count"
        )
        or 0
    )
    score_event_text_unknown_broad_only = int(
        score_event_text_unknown_source_options_summary.get(
            "broad_market_transmission_only_count"
        )
        or 0
    )
    score_event_text_unknown_classifier_ready = int(
        score_event_text_unknown_source_options_summary.get(
            "classifier_ready_for_review_count"
        )
        or 0
    )
    score_event_text_unknown_target_required = int(
        score_event_text_unknown_source_options_summary.get(
            "candidate_requires_target_event_evidence_count"
        )
        or 0
    )
    score_event_text_unknown_direct_required = int(
        score_event_text_unknown_source_options_summary.get(
            "candidate_requires_direct_a_share_transmission_count"
        )
        or 0
    )
    score_event_text_unknown_auto_known = int(
        score_event_text_unknown_source_options_summary.get("auto_known_candidate_count")
        or 0
    )
    score_event_text_unknown_prod_writes = int(
        score_event_text_unknown_source_options_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_event_text_market_doc_checked = int(
        score_event_text_market_doc_evidence_summary.get(
            "unknown_event_text_rows_checked"
        )
        or 0
    )
    score_event_text_market_doc_files = int(
        score_event_text_market_doc_evidence_summary.get("market_html_files_scanned")
        or 0
    )
    score_event_text_market_doc_read_errors = int(
        score_event_text_market_doc_evidence_summary.get(
            "market_html_read_error_count"
        )
        or 0
    )
    score_event_text_market_doc_target = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_with_market_doc_target_evidence_count"
        )
        or 0
    )
    score_event_text_market_doc_direct = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_with_market_doc_direct_transmission_count"
        )
        or 0
    )
    score_event_text_market_doc_target_direct = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_with_market_doc_target_and_direct_count"
        )
        or 0
    )
    score_event_text_market_doc_same_sentence = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_with_same_sentence_candidate_count"
        )
        or 0
    )
    score_event_text_market_doc_target_required = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_still_requiring_target_evidence_count"
        )
        or 0
    )
    score_event_text_market_doc_direct_required = int(
        score_event_text_market_doc_evidence_summary.get(
            "rows_still_requiring_direct_transmission_link_count"
        )
        or 0
    )
    score_event_text_market_doc_review_candidates = int(
        score_event_text_market_doc_evidence_summary.get(
            "market_doc_review_candidate_count"
        )
        or 0
    )
    score_event_text_market_doc_auto_known = int(
        score_event_text_market_doc_evidence_summary.get("auto_known_candidate_count")
        or 0
    )
    score_event_text_market_doc_prod_writes = int(
        score_event_text_market_doc_evidence_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_count = int(
        score_event_text_market_doc_review_packets_summary.get("event_text_packet_count")
        or 0
    )
    score_event_text_market_doc_packet_ready = int(
        score_event_text_market_doc_review_packets_summary.get(
            "market_doc_review_ready_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_target_required = int(
        score_event_text_market_doc_review_packets_summary.get(
            "requires_target_event_evidence_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_direct_required = int(
        score_event_text_market_doc_review_packets_summary.get(
            "requires_direct_transmission_link_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_examples = int(
        score_event_text_market_doc_review_packets_summary.get(
            "candidate_example_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_contract_valid = int(
        score_event_text_market_doc_review_packets_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_contract_invalid = int(
        score_event_text_market_doc_review_packets_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_auto_known = int(
        score_event_text_market_doc_review_packets_summary.get(
            "auto_known_candidate_count"
        )
        or 0
    )
    score_event_text_market_doc_packet_prod_writes = int(
        score_event_text_market_doc_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_local_structured_tasks = int(
        score_local_structured_draft_summary.get("local_structured_task_count") or 0
    )
    score_local_structured_known = int(
        score_local_structured_draft_summary.get("draft_known_count") or 0
    )
    score_local_structured_unknown = int(
        score_local_structured_draft_summary.get("draft_unknown_count") or 0
    )
    score_local_structured_contract_valid = int(
        score_local_structured_draft_summary.get("draft_contract_valid_count") or 0
    )
    score_local_structured_contract_invalid = int(
        score_local_structured_draft_summary.get("draft_contract_invalid_count") or 0
    )
    score_local_structured_bridge = int(
        score_local_structured_draft_summary.get("bridge_validated_known_count") or 0
    )
    score_local_structured_review_required = int(
        score_local_structured_draft_summary.get("review_required_count") or 0
    )
    score_local_structured_safe_upsert = int(
        score_local_structured_draft_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_local_structured_prod_writes = int(
        score_local_structured_draft_summary.get("production_write_allowed_count") or 0
    )
    score_local_structured_unknown_options = int(
        score_local_structured_unknown_source_options_summary.get(
            "unknown_local_structured_count"
        )
        or 0
    )
    score_local_structured_unknown_runtime_ready = int(
        score_local_structured_unknown_source_options_summary.get(
            "existing_runtime_dependency_ready_count"
        )
        or 0
    )
    score_local_structured_unknown_direct_ready = int(
        score_local_structured_unknown_source_options_summary.get(
            "direct_existing_structured_source_ready_count"
        )
        or 0
    )
    score_local_structured_unknown_overlay_hints = int(
        score_local_structured_unknown_source_options_summary.get(
            "overlay_candidate_hint_count"
        )
        or 0
    )
    score_local_structured_unknown_new_mapping = int(
        score_local_structured_unknown_source_options_summary.get(
            "candidate_requires_new_mapping_count"
        )
        or 0
    )
    score_local_structured_unknown_review_policy = int(
        score_local_structured_unknown_source_options_summary.get(
            "candidate_requires_review_policy_count"
        )
        or 0
    )
    score_local_structured_unknown_partial_unlock = int(
        score_local_structured_unknown_source_options_summary.get(
            "partial_known_unlock_candidate_count"
        )
        or 0
    )
    score_local_structured_unknown_auto_known = int(
        score_local_structured_unknown_source_options_summary.get(
            "auto_known_candidate_count"
        )
        or 0
    )
    score_local_structured_unknown_prod_writes = int(
        score_local_structured_unknown_source_options_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_local_structured_source_candidates_unknown = int(
        score_local_structured_source_candidates_summary.get("unknown_dp_count") or 0
    )
    score_local_structured_source_candidates_runtime_ready = int(
        score_local_structured_source_candidates_summary.get("runtime_dependency_ready_count") or 0
    )
    score_local_structured_source_candidates_direct_known = int(
        score_local_structured_source_candidates_summary.get("direct_known_ready_count") or 0
    )
    score_local_structured_source_candidates_review_dp = int(
        score_local_structured_source_candidates_summary.get("review_candidate_dp_count") or 0
    )
    score_local_structured_source_candidates_review_matches = int(
        score_local_structured_source_candidates_summary.get("review_candidate_match_count") or 0
    )
    score_local_structured_source_candidates_supporting_matches = int(
        score_local_structured_source_candidates_summary.get("supporting_candidate_match_count") or 0
    )
    score_local_structured_source_candidates_empty_matches = int(
        score_local_structured_source_candidates_summary.get("empty_candidate_match_count") or 0
    )
    score_local_structured_source_candidates_no_source = int(
        score_local_structured_source_candidates_summary.get("no_direct_catalog_source_count") or 0
    )
    score_local_structured_source_candidates_false_positive = int(
        score_local_structured_source_candidates_summary.get("excluded_false_positive_count") or 0
    )
    score_local_structured_source_candidates_prod_writes = int(
        score_local_structured_source_candidates_summary.get("production_write_allowed_count") or 0
    )
    score_local_structured_source_review_packets_total = int(
        score_local_structured_source_review_packets_summary.get(
            "local_structured_source_review_packet_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_ready = int(
        score_local_structured_source_review_packets_summary.get(
            "review_candidate_ready_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_quantity = int(
        score_local_structured_source_review_packets_summary.get(
            "supporting_candidate_needs_quantity_source_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_external = int(
        score_local_structured_source_review_packets_summary.get(
            "external_source_required_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_direct_known = int(
        score_local_structured_source_review_packets_summary.get("direct_known_ready_count")
        or 0
    )
    score_local_structured_source_review_packets_formula_ready = int(
        score_local_structured_source_review_packets_summary.get(
            "formula_inputs_ready_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_candidate = int(
        score_local_structured_source_review_packets_summary.get("candidate_packet_count")
        or 0
    )
    score_local_structured_source_review_packets_contract_valid = int(
        score_local_structured_source_review_packets_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_contract_invalid = int(
        score_local_structured_source_review_packets_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_local_structured_source_review_packets_prod_writes = int(
        score_local_structured_source_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_local_structured_text_tasks = int(
        score_local_structured_text_draft_summary.get("local_structured_text_task_count") or 0
    )
    score_local_structured_text_known = int(
        score_local_structured_text_draft_summary.get("draft_known_count") or 0
    )
    score_local_structured_text_unknown = int(
        score_local_structured_text_draft_summary.get("draft_unknown_count") or 0
    )
    score_local_structured_text_contract_valid = int(
        score_local_structured_text_draft_summary.get("draft_contract_valid_count") or 0
    )
    score_local_structured_text_contract_invalid = int(
        score_local_structured_text_draft_summary.get("draft_contract_invalid_count") or 0
    )
    score_local_structured_text_bridge = int(
        score_local_structured_text_draft_summary.get("bridge_validated_known_count") or 0
    )
    score_local_structured_text_review_required = int(
        score_local_structured_text_draft_summary.get("review_required_count") or 0
    )
    score_local_structured_text_safe_upsert = int(
        score_local_structured_text_draft_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_local_structured_text_prod_writes = int(
        score_local_structured_text_draft_summary.get("production_write_allowed_count") or 0
    )
    score_local_structured_text_unknown_options = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "unknown_local_structured_text_count"
        )
        or 0
    )
    score_local_structured_text_unknown_runtime_ready = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "existing_runtime_dependency_ready_count"
        )
        or 0
    )
    score_local_structured_text_unknown_qa_ready = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "qa_recent_dependency_ready_count"
        )
        or 0
    )
    score_local_structured_text_unknown_classified = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "direct_text_classification_ready_count"
        )
        or 0
    )
    score_local_structured_text_unknown_overlay_hints = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "overlay_candidate_hint_count"
        )
        or 0
    )
    score_local_structured_text_unknown_text_required = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "candidate_requires_text_classification_count"
        )
        or 0
    )
    score_local_structured_text_unknown_auto_known = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "auto_known_candidate_count"
        )
        or 0
    )
    score_local_structured_text_unknown_prod_writes = int(
        score_local_structured_text_unknown_source_options_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_single_dependency_tasks = int(
        score_single_dependency_draft_summary.get("single_dependency_task_count") or 0
    )
    score_single_dependency_known = int(
        score_single_dependency_draft_summary.get("draft_known_count") or 0
    )
    score_single_dependency_unknown = int(
        score_single_dependency_draft_summary.get("draft_unknown_count") or 0
    )
    score_single_dependency_contract_valid = int(
        score_single_dependency_draft_summary.get("draft_contract_valid_count") or 0
    )
    score_single_dependency_contract_invalid = int(
        score_single_dependency_draft_summary.get("draft_contract_invalid_count") or 0
    )
    score_single_dependency_bridge = int(
        score_single_dependency_draft_summary.get("bridge_validated_known_count") or 0
    )
    score_single_dependency_review_required = int(
        score_single_dependency_draft_summary.get("review_required_count") or 0
    )
    score_single_dependency_safe_upsert = int(
        score_single_dependency_draft_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_single_dependency_prod_writes = int(
        score_single_dependency_draft_summary.get("production_write_allowed_count") or 0
    )
    score_single_dependency_unknown_options = int(
        score_single_dependency_unknown_source_options_summary.get(
            "unknown_local_single_dependency_count"
        )
        or 0
    )
    score_single_dependency_unknown_runtime_ready = int(
        score_single_dependency_unknown_source_options_summary.get(
            "existing_runtime_dependency_ready_count"
        )
        or 0
    )
    score_single_dependency_unknown_direct_ready = int(
        score_single_dependency_unknown_source_options_summary.get(
            "direct_replacement_cycle_source_ready_count"
        )
        or 0
    )
    score_single_dependency_unknown_overlay_hints = int(
        score_single_dependency_unknown_source_options_summary.get(
            "overlay_candidate_hint_count"
        )
        or 0
    )
    score_single_dependency_unknown_overlay_lifecycle_context = int(
        score_single_dependency_unknown_source_options_summary.get(
            "rows_with_overlay_lifecycle_context_candidate_count"
        )
        or 0
    )
    score_single_dependency_unknown_overlay_lifecycle_known = int(
        score_single_dependency_unknown_source_options_summary.get(
            "overlay_lifecycle_known_node_count"
        )
        or 0
    )
    score_single_dependency_unknown_overlay_replacement_known = int(
        score_single_dependency_unknown_source_options_summary.get(
            "overlay_replacement_known_node_count"
        )
        or 0
    )
    score_single_dependency_unknown_overlay_replacement_unknown = int(
        score_single_dependency_unknown_source_options_summary.get(
            "overlay_replacement_unknown_node_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_required = int(
        score_single_dependency_unknown_source_options_summary.get(
            "candidate_requires_lifecycle_source_count"
        )
        or 0
    )
    score_single_dependency_unknown_review_policy = int(
        score_single_dependency_unknown_source_options_summary.get(
            "candidate_requires_review_policy_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_templates = int(
        score_single_dependency_unknown_source_options_summary.get(
            "lifecycle_policy_review_template_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_templates_valid = int(
        score_single_dependency_unknown_source_options_summary.get(
            "lifecycle_policy_review_template_contract_valid_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_templates_invalid = int(
        score_single_dependency_unknown_source_options_summary.get(
            "lifecycle_policy_review_template_contract_invalid_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_templates_blank = int(
        score_single_dependency_unknown_source_options_summary.get(
            "lifecycle_policy_review_template_blank_pending_count"
        )
        or 0
    )
    score_single_dependency_unknown_lifecycle_templates_input_ready = int(
        score_single_dependency_unknown_source_options_summary.get(
            "lifecycle_policy_review_template_input_ready_count"
        )
        or 0
    )
    score_single_dependency_unknown_auto_known = int(
        score_single_dependency_unknown_source_options_summary.get(
            "auto_known_candidate_count"
        )
        or 0
    )
    score_single_dependency_unknown_known_sufficient = int(
        score_single_dependency_unknown_source_options_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_single_dependency_unknown_approval_ready = int(
        score_single_dependency_unknown_source_options_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_single_dependency_unknown_prod_writes = int(
        score_single_dependency_unknown_source_options_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_manual_policy_tasks = int(
        score_manual_policy_draft_summary.get("manual_policy_task_count") or 0
    )
    score_manual_policy_known = int(
        score_manual_policy_draft_summary.get("draft_known_count") or 0
    )
    score_manual_policy_unknown = int(
        score_manual_policy_draft_summary.get("draft_unknown_count") or 0
    )
    score_manual_policy_bridge = int(
        score_manual_policy_draft_summary.get("bridge_validated_known_count") or 0
    )
    score_manual_policy_contract_valid = int(
        score_manual_policy_draft_summary.get("draft_contract_valid_count") or 0
    )
    score_manual_policy_contract_invalid = int(
        score_manual_policy_draft_summary.get("draft_contract_invalid_count") or 0
    )
    score_manual_policy_prod_writes = int(
        score_manual_policy_draft_summary.get("production_write_allowed_count") or 0
    )
    score_manual_policy_safe_upsert = int(
        score_manual_policy_draft_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_manual_policy_unknown_options = int(
        score_manual_policy_unknown_source_options_summary.get("unknown_manual_policy_count")
        or 0
    )
    score_manual_policy_unknown_dependency_ready = int(
        score_manual_policy_unknown_source_options_summary.get("dependency_pack_ready_count")
        or 0
    )
    score_manual_policy_unknown_assumption_ready = int(
        score_manual_policy_unknown_source_options_summary.get(
            "direct_reviewed_assumption_ready_count"
        )
        or 0
    )
    score_manual_policy_unknown_required_assumptions = int(
        score_manual_policy_unknown_source_options_summary.get(
            "required_assumption_count"
        )
        or 0
    )
    score_manual_policy_unknown_assumption_review = int(
        score_manual_policy_unknown_source_options_summary.get(
            "candidate_requires_assumption_review_count"
        )
        or 0
    )
    score_manual_policy_unknown_review_policy = int(
        score_manual_policy_unknown_source_options_summary.get(
            "candidate_requires_review_policy_count"
        )
        or 0
    )
    score_manual_policy_unknown_auto_known = int(
        score_manual_policy_unknown_source_options_summary.get(
            "auto_known_candidate_count"
        )
        or 0
    )
    score_manual_policy_unknown_prod_writes = int(
        score_manual_policy_unknown_source_options_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_review_manifest_entries = int(
        score_review_staging_manifest_summary.get("review_manifest_entries") or 0
    )
    score_review_manifest_concrete = int(
        score_review_staging_manifest_summary.get("review_ready_concrete_count") or 0
    )
    score_review_manifest_unknown = int(
        score_review_staging_manifest_summary.get("review_gated_unknown_count") or 0
    )
    score_review_manifest_contract_valid = int(
        score_review_staging_manifest_summary.get("contract_valid_count") or 0
    )
    score_review_manifest_contract_invalid = int(
        score_review_staging_manifest_summary.get("contract_invalid_count") or 0
    )
    score_review_manifest_bridge_ready = int(
        score_review_staging_manifest_summary.get("bridge_ready_concrete_count") or 0
    )
    score_review_manifest_safe_upsert = int(
        score_review_staging_manifest_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_review_manifest_prod_writes = int(
        score_review_staging_manifest_summary.get("production_write_allowed_count") or 0
    )
    score_review_manifest_approved_writes = int(
        score_review_staging_manifest_summary.get("approved_runtime_write_count") or 0
    )
    score_deterministic_approval_records = int(
        score_deterministic_runtime_approvals_summary.get("approval_record_count") or 0
    )
    score_deterministic_approved_writes = int(
        score_deterministic_runtime_approvals_summary.get(
            "approved_deterministic_runtime_write_count"
        )
        or 0
    )
    score_deterministic_rejected = int(
        score_deterministic_runtime_approvals_summary.get(
            "deterministic_policy_rejected_count"
        )
        or 0
    )
    score_deterministic_not_reviewed = int(
        score_deterministic_runtime_approvals_summary.get(
            "not_in_deterministic_policy_count"
        )
        or 0
    )
    score_deterministic_prod_writes = int(
        score_deterministic_runtime_approvals_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_review_approval_required = int(
        score_review_approval_gate_summary.get("approval_required_count") or 0
    )
    score_review_approval_records = int(
        score_review_approval_gate_summary.get("approval_records_seen") or 0
    )
    score_review_approval_missing = int(
        score_review_approval_gate_summary.get("approval_missing_count") or 0
    )
    score_review_approval_rejected = int(
        score_review_approval_gate_summary.get("rejected_approval_count") or 0
    )
    score_review_approval_approved_writes = int(
        score_review_approval_gate_summary.get("approved_runtime_write_count") or 0
    )
    score_review_approval_write_plan = int(
        score_review_approval_gate_summary.get("write_plan_count") or 0
    )
    score_review_approval_unknown = int(
        score_review_approval_gate_summary.get("not_approvable_unknown_count") or 0
    )
    score_review_approval_safe_upsert = int(
        score_review_approval_gate_summary.get("safe_to_upsert_without_review_count") or 0
    )
    score_review_approval_prod_writes = int(
        score_review_approval_gate_summary.get("production_write_allowed_count") or 0
    )
    score_next_action_total = int(
        score_completion_next_actions_summary.get("actionable_gap_count") or 0
    )
    score_next_action_approval_ready = int(
        score_completion_next_actions_summary.get("approval_ready_packet_count") or 0
    )
    score_next_action_runtime_ready = int(
        score_completion_next_actions_summary.get("runtime_write_plan_ready_count") or 0
    )
    score_next_action_templates = int(
        score_completion_next_actions_summary.get("approval_record_template_count") or 0
    )
    score_next_action_unknown = int(
        score_completion_next_actions_summary.get("unknown_resolution_required_count") or 0
    )
    score_next_action_event_text = int(
        score_completion_next_actions_summary.get(
            "event_text_classification_required_count"
        )
        or 0
    )
    score_next_action_local_structured = int(
        score_completion_next_actions_summary.get(
            "local_structured_mapping_required_count"
        )
        or 0
    )
    score_next_action_structured_text = int(
        score_completion_next_actions_summary.get(
            "structured_text_extraction_required_count"
        )
        or 0
    )
    score_next_action_single_dependency = int(
        score_completion_next_actions_summary.get(
            "single_dependency_policy_required_count"
        )
        or 0
    )
    score_next_action_manual = int(
        score_completion_next_actions_summary.get(
            "manual_assumption_review_required_count"
        )
        or 0
    )
    score_next_action_approved_writes = int(
        score_completion_next_actions_summary.get("approved_runtime_write_count") or 0
    )
    score_next_action_write_plan = int(
        score_completion_next_actions_summary.get("write_plan_count") or 0
    )
    score_next_action_prod_writes = int(
        score_completion_next_actions_summary.get("production_write_allowed_count") or 0
    )
    score_unknown_closure_rows = int(
        score_unknown_closure_matrix_summary.get("unknown_closure_row_count") or 0
    )
    score_unknown_closure_assigned = int(
        score_unknown_closure_matrix_summary.get("closure_route_assigned_count") or 0
    )
    score_unknown_closure_missing = int(
        score_unknown_closure_matrix_summary.get("missing_closure_route_count") or 0
    )
    score_unknown_closure_event_text = int(
        score_unknown_closure_matrix_summary.get(
            "event_text_classification_required_count"
        )
        or 0
    )
    score_unknown_closure_local_structured = int(
        score_unknown_closure_matrix_summary.get(
            "local_structured_mapping_required_count"
        )
        or 0
    )
    score_unknown_closure_structured_text = int(
        score_unknown_closure_matrix_summary.get(
            "structured_text_extraction_required_count"
        )
        or 0
    )
    score_unknown_closure_single_dependency = int(
        score_unknown_closure_matrix_summary.get(
            "single_dependency_policy_required_count"
        )
        or 0
    )
    score_unknown_closure_manual = int(
        score_unknown_closure_matrix_summary.get(
            "manual_assumption_review_required_count"
        )
        or 0
    )
    score_unknown_closure_auto_known = int(
        score_unknown_closure_matrix_summary.get("auto_known_ready_count") or 0
    )
    score_unknown_closure_approval_ready = int(
        score_unknown_closure_matrix_summary.get("approval_ready_count") or 0
    )
    score_unknown_closure_source_candidates = int(
        score_unknown_closure_matrix_summary.get("rows_with_source_candidates_count")
        or 0
    )
    score_unknown_closure_formula_ready = int(
        score_unknown_closure_matrix_summary.get("formula_inputs_ready_count") or 0
    )
    score_unknown_closure_contract_valid = int(
        score_unknown_closure_matrix_summary.get("closure_contract_valid_count") or 0
    )
    score_unknown_closure_contract_invalid = int(
        score_unknown_closure_matrix_summary.get("closure_contract_invalid_count") or 0
    )
    score_unknown_closure_prod_writes = int(
        score_unknown_closure_matrix_summary.get("production_write_allowed_count") or 0
    )
    score_unknown_acquisition_tasks = int(
        score_unknown_acquisition_backlog_summary.get("unknown_acquisition_task_count")
        or score_unknown_acquisition_backlog_summary.get("acquisition_task_count")
        or 0
    )
    score_unknown_acquisition_event_doc = int(
        score_unknown_acquisition_backlog_summary.get("event_doc_search_task_count")
        or 0
    )
    score_unknown_acquisition_local_formula = int(
        score_unknown_acquisition_backlog_summary.get("local_formula_source_task_count")
        or 0
    )
    score_unknown_acquisition_external_business = int(
        score_unknown_acquisition_backlog_summary.get(
            "external_business_source_task_count"
        )
        or 0
    )
    score_unknown_acquisition_existing_evidence = int(
        score_unknown_acquisition_backlog_summary.get(
            "tasks_with_existing_candidate_evidence_count"
        )
        or 0
    )
    score_unknown_acquisition_overlay_hints = int(
        score_unknown_acquisition_backlog_summary.get(
            "tasks_with_runtime_overlay_hints_count"
        )
        or 0
    )
    score_unknown_acquisition_web_external = int(
        score_unknown_acquisition_backlog_summary.get(
            "web_or_external_acquisition_required_count"
        )
        or 0
    )
    score_unknown_acquisition_llm_allowed = int(
        score_unknown_acquisition_backlog_summary.get("llm_allowed_count") or 0
    )
    score_unknown_acquisition_formula_ready = int(
        score_unknown_acquisition_backlog_summary.get("formula_inputs_ready_count") or 0
    )
    score_unknown_acquisition_auto_known = int(
        score_unknown_acquisition_backlog_summary.get("ready_for_auto_known_count") or 0
    )
    score_unknown_acquisition_approval_ready = int(
        score_unknown_acquisition_backlog_summary.get("ready_for_approval_count") or 0
    )
    score_unknown_acquisition_contract_valid = int(
        score_unknown_acquisition_backlog_summary.get("task_contract_valid_count") or 0
    )
    score_unknown_acquisition_contract_invalid = int(
        score_unknown_acquisition_backlog_summary.get("task_contract_invalid_count") or 0
    )
    score_unknown_acquisition_prod_writes = int(
        score_unknown_acquisition_backlog_summary.get("production_write_allowed_count")
        or 0
    )
    score_unknown_market_doc_tasks = int(
        score_unknown_market_doc_acquisition_summary.get(
            "market_doc_acquisition_task_count"
        )
        or 0
    )
    score_unknown_market_doc_files = int(
        score_unknown_market_doc_acquisition_summary.get("market_html_files_scanned")
        or 0
    )
    score_unknown_market_doc_read_errors = int(
        score_unknown_market_doc_acquisition_summary.get("market_html_read_error_count")
        or 0
    )
    score_unknown_market_doc_review_rows = int(
        score_unknown_market_doc_acquisition_summary.get(
            "rows_with_review_candidates_count"
        )
        or 0
    )
    score_unknown_market_doc_new_entrant_windows = int(
        score_unknown_market_doc_acquisition_summary.get(
            "new_entrant_window_candidate_count"
        )
        or 0
    )
    score_unknown_market_doc_new_entrant_review = int(
        score_unknown_market_doc_acquisition_summary.get(
            "new_entrant_review_candidate_count"
        )
        or 0
    )
    score_unknown_market_doc_substitute_same_sentence = int(
        score_unknown_market_doc_acquisition_summary.get(
            "substitute_same_sentence_candidate_count"
        )
        or 0
    )
    score_unknown_market_doc_substitute_clean = int(
        score_unknown_market_doc_acquisition_summary.get(
            "substitute_clean_risk_review_candidate_count"
        )
        or 0
    )
    score_unknown_market_doc_weak = int(
        score_unknown_market_doc_acquisition_summary.get("weak_candidate_count") or 0
    )
    score_unknown_market_doc_rejected = int(
        score_unknown_market_doc_acquisition_summary.get("rejected_candidate_count")
        or 0
    )
    score_unknown_market_doc_known_sufficient = int(
        score_unknown_market_doc_acquisition_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_market_doc_prod_writes = int(
        score_unknown_market_doc_acquisition_summary.get("production_write_allowed_count")
        or 0
    )
    score_unknown_event_adjudication_rows = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "event_unknown_adjudication_row_count"
        )
        or 0
    )
    score_unknown_event_adjudication_examples = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "candidate_examples_reviewed_count"
        )
        or 0
    )
    score_unknown_event_adjudication_accepted = int(
        score_unknown_event_evidence_adjudication_summary.get("accepted_candidate_count")
        or 0
    )
    score_unknown_event_adjudication_rejected = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "rejected_or_ambiguous_candidate_count"
        )
        or 0
    )
    score_unknown_event_adjudication_remaining = int(
        score_unknown_event_evidence_adjudication_summary.get("remaining_unknown_count")
        or 0
    )
    score_unknown_event_adjudication_known = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_event_adjudication_contract_valid = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "adjudication_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_adjudication_contract_invalid = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "adjudication_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_adjudication_prod_writes = int(
        score_unknown_event_evidence_adjudication_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_event_strict_rows = int(
        score_unknown_event_strict_source_gate_summary.get("event_strict_gate_row_count")
        or 0
    )
    score_unknown_event_strict_files = int(
        score_unknown_event_strict_source_gate_summary.get("market_html_files_scanned")
        or 0
    )
    score_unknown_event_strict_read_errors = int(
        score_unknown_event_strict_source_gate_summary.get(
            "market_html_read_error_count"
        )
        or 0
    )
    score_unknown_event_strict_candidates = int(
        score_unknown_event_strict_source_gate_summary.get("strict_candidate_count") or 0
    )
    score_unknown_event_strict_review_candidates = int(
        score_unknown_event_strict_source_gate_summary.get(
            "strict_review_candidate_count"
        )
        or 0
    )
    score_unknown_event_strict_rejected = int(
        score_unknown_event_strict_source_gate_summary.get("strict_rejected_count") or 0
    )
    score_unknown_event_strict_rows_with_review = int(
        score_unknown_event_strict_source_gate_summary.get(
            "rows_with_strict_review_candidates_count"
        )
        or 0
    )
    score_unknown_event_strict_rows_without_source = int(
        score_unknown_event_strict_source_gate_summary.get(
            "rows_without_strict_source_candidate_count"
        )
        or 0
    )
    score_unknown_event_strict_classifier_ready = int(
        score_unknown_event_strict_source_gate_summary.get("classifier_ready_count") or 0
    )
    score_unknown_event_strict_known = int(
        score_unknown_event_strict_source_gate_summary.get("known_draft_sufficient_count")
        or 0
    )
    score_unknown_event_strict_approval_ready = int(
        score_unknown_event_strict_source_gate_summary.get("approval_ready_count") or 0
    )
    score_unknown_event_strict_contract_valid = int(
        score_unknown_event_strict_source_gate_summary.get(
            "strict_gate_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_strict_contract_invalid = int(
        score_unknown_event_strict_source_gate_summary.get(
            "strict_gate_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_strict_prod_writes = int(
        score_unknown_event_strict_source_gate_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_event_strict_review_packet_count = int(
        score_unknown_event_strict_review_packets_summary.get(
            "strict_review_packet_count"
        )
        or 0
    )
    score_unknown_event_strict_review_rows = int(
        score_unknown_event_strict_review_packets_summary.get("strict_review_rows_count")
        or 0
    )
    score_unknown_event_strict_low_confidence_sources = int(
        score_unknown_event_strict_review_packets_summary.get(
            "source_quality_low_confidence_count"
        )
        or 0
    )
    score_unknown_event_strict_secondary_newswire = int(
        score_unknown_event_strict_review_packets_summary.get(
            "source_quality_secondary_newswire_count"
        )
        or 0
    )
    score_unknown_event_strict_primary_required = int(
        score_unknown_event_strict_review_packets_summary.get(
            "requires_primary_source_confirmation_count"
        )
        or 0
    )
    score_unknown_event_strict_manual_review = int(
        score_unknown_event_strict_review_packets_summary.get(
            "requires_manual_review_count"
        )
        or 0
    )
    score_unknown_event_strict_deterministic_rejected = int(
        score_unknown_event_strict_review_packets_summary.get(
            "deterministic_rejected_count"
        )
        or 0
    )
    score_unknown_event_strict_packet_classifier_ready = int(
        score_unknown_event_strict_review_packets_summary.get("classifier_ready_count")
        or 0
    )
    score_unknown_event_strict_packet_known = int(
        score_unknown_event_strict_review_packets_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_event_strict_packet_approval_ready = int(
        score_unknown_event_strict_review_packets_summary.get("approval_ready_count")
        or 0
    )
    score_unknown_event_strict_packet_contract_valid = int(
        score_unknown_event_strict_review_packets_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_strict_packet_contract_invalid = int(
        score_unknown_event_strict_review_packets_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_strict_packet_prod_writes = int(
        score_unknown_event_strict_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_event_primary_confirmation_packets = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "primary_confirmation_packet_count"
        )
        or 0
    )
    score_unknown_event_primary_confirmation_files = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "market_html_files_scanned"
        )
        or 0
    )
    score_unknown_event_primary_confirmation_read_errors = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "market_html_read_error_count"
        )
        or 0
    )
    score_unknown_event_primary_local_candidates = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "local_candidate_count"
        )
        or 0
    )
    score_unknown_event_primary_local_confirmations = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "local_high_quality_confirmation_candidate_count"
        )
        or 0
    )
    score_unknown_event_primary_supporting_only = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "local_supporting_context_only_count"
        )
        or 0
    )
    score_unknown_event_primary_rows_with_confirmation = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "rows_with_local_confirmation_candidate_count"
        )
        or 0
    )
    score_unknown_event_primary_rows_supporting_only = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "rows_with_supporting_context_only_count"
        )
        or 0
    )
    score_unknown_event_primary_rows_without_confirmation = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "rows_without_local_confirmation_candidate_count"
        )
        or 0
    )
    score_unknown_event_primary_classifier_ready = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "classifier_ready_count"
        )
        or 0
    )
    score_unknown_event_primary_known = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_event_primary_approval_ready = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_event_primary_contract_valid = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "confirmation_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_primary_contract_invalid = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "confirmation_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_primary_prod_writes = int(
        score_unknown_event_primary_source_confirmation_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_event_external_confirmation_packets = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_confirmation_packet_count"
        )
        or 0
    )
    score_unknown_event_external_source_cards = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_source_card_count"
        )
        or 0
    )
    score_unknown_event_external_confirmation_candidates = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_confirmation_candidate_count"
        )
        or 0
    )
    score_unknown_event_external_supporting_context = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_supporting_context_count"
        )
        or 0
    )
    score_unknown_event_external_rows_with_confirmation = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "rows_with_external_confirmation_candidate_count"
        )
        or 0
    )
    score_unknown_event_external_rows_supporting_only = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "rows_with_external_supporting_context_only_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_candidates = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_candidate_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_contract_valid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_candidate_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_contract_invalid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_candidate_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_ready = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_candidate_ready_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_review_required = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_review_required_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_primary_source = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_primary_source_covered_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_labels = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_required_label_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_input_guardrails = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_input_guardrail_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_review_templates = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_review_template_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_review_template_contract_valid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_review_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_review_template_contract_invalid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_review_template_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_review_template_blank_pending = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_review_template_blank_pending_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_review_template_input_ready = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_review_template_input_ready_count"
        )
        or 0
    )
    score_unknown_event_external_classifier_ready = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "classifier_ready_count"
        )
        or 0
    )
    score_unknown_event_external_known = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_event_external_approval_ready = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_event_external_contract_valid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_confirmation_contract_valid_count"
        )
        or 0
    )
    score_unknown_event_external_contract_invalid = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "external_confirmation_contract_invalid_count"
        )
        or 0
    )
    score_unknown_event_external_prod_writes = int(
        score_unknown_event_external_source_confirmation_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_local_formula_tasks = int(
        score_unknown_local_formula_acquisition_summary.get(
            "local_formula_acquisition_task_count"
        )
        or 0
    )
    score_unknown_local_formula_runtime_ready = int(
        score_unknown_local_formula_acquisition_summary.get(
            "runtime_dependency_ready_count"
        )
        or 0
    )
    score_unknown_local_formula_csv_checked = int(
        score_unknown_local_formula_acquisition_summary.get("sample_csv_files_checked")
        or 0
    )
    score_unknown_local_formula_csv_existing = int(
        score_unknown_local_formula_acquisition_summary.get("sample_csv_files_existing")
        or 0
    )
    score_unknown_local_formula_csv_errors = int(
        score_unknown_local_formula_acquisition_summary.get("sample_csv_read_error_count")
        or 0
    )
    score_unknown_local_formula_group_count = int(
        score_unknown_local_formula_acquisition_summary.get("formula_input_group_count")
        or 0
    )
    score_unknown_local_formula_group_ready = int(
        score_unknown_local_formula_acquisition_summary.get(
            "formula_input_group_ready_count"
        )
        or 0
    )
    score_unknown_local_formula_candidate_numerator = int(
        score_unknown_local_formula_acquisition_summary.get(
            "rows_with_candidate_numerator_count"
        )
        or 0
    )
    score_unknown_local_formula_direct_denominator = int(
        score_unknown_local_formula_acquisition_summary.get(
            "rows_with_direct_denominator_count"
        )
        or 0
    )
    score_unknown_local_formula_quantity_or_price = int(
        score_unknown_local_formula_acquisition_summary.get(
            "rows_with_quantity_or_price_index_count"
        )
        or 0
    )
    score_unknown_local_formula_policy = int(
        score_unknown_local_formula_acquisition_summary.get(
            "rows_with_formula_policy_count"
        )
        or 0
    )
    score_unknown_local_formula_ready = int(
        score_unknown_local_formula_acquisition_summary.get("formula_inputs_ready_count")
        or 0
    )
    score_unknown_local_formula_known_draft = int(
        score_unknown_local_formula_acquisition_summary.get("ready_for_known_draft_count")
        or 0
    )
    score_unknown_local_formula_contract_valid = int(
        score_unknown_local_formula_acquisition_summary.get("packet_contract_valid_count")
        or 0
    )
    score_unknown_local_formula_contract_invalid = int(
        score_unknown_local_formula_acquisition_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_unknown_local_formula_prod_writes = int(
        score_unknown_local_formula_acquisition_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_local_formula_review_packets = int(
        score_unknown_local_formula_review_packets_summary.get(
            "local_formula_review_packet_count"
        )
        or 0
    )
    score_unknown_local_formula_review_candidate_numerator = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_candidate_numerator_count"
        )
        or 0
    )
    score_unknown_local_formula_review_direct_denominator = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_direct_denominator_count"
        )
        or 0
    )
    score_unknown_local_formula_review_denominator_candidate = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_denominator_candidate_count"
        )
        or 0
    )
    score_unknown_local_formula_review_formula_shape = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_candidate_formula_shape_count"
        )
        or 0
    )
    score_unknown_local_formula_review_policy_draft = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_formula_policy_draft_candidate_count"
        )
        or 0
    )
    score_unknown_local_formula_review_policy_template = int(
        score_unknown_local_formula_review_packets_summary.get(
            "formula_policy_review_template_count"
        )
        or 0
    )
    score_unknown_local_formula_review_policy_template_valid = int(
        score_unknown_local_formula_review_packets_summary.get(
            "formula_policy_review_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_local_formula_review_policy_template_blank = int(
        score_unknown_local_formula_review_packets_summary.get(
            "formula_policy_review_template_blank_pending_count"
        )
        or 0
    )
    score_unknown_local_formula_review_price_context = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_price_index_context_candidate_count"
        )
        or 0
    )
    score_unknown_local_formula_review_price_context_shape = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_candidate_price_context_shape_count"
        )
        or 0
    )
    score_unknown_local_formula_review_price_template = int(
        score_unknown_local_formula_review_packets_summary.get(
            "price_context_review_template_count"
        )
        or 0
    )
    score_unknown_local_formula_review_price_template_valid = int(
        score_unknown_local_formula_review_packets_summary.get(
            "price_context_review_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_local_formula_review_price_template_blank = int(
        score_unknown_local_formula_review_packets_summary.get(
            "price_context_review_template_blank_pending_count"
        )
        or 0
    )
    score_unknown_local_formula_review_quantity_or_price = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_quantity_or_price_index_count"
        )
        or 0
    )
    score_unknown_local_formula_review_policy = int(
        score_unknown_local_formula_review_packets_summary.get(
            "rows_with_formula_policy_count"
        )
        or 0
    )
    score_unknown_local_formula_review_inputs_ready = int(
        score_unknown_local_formula_review_packets_summary.get(
            "formula_inputs_ready_count"
        )
        or 0
    )
    score_unknown_local_formula_review_probe_available = int(
        score_unknown_local_formula_review_packets_summary.get(
            "formula_probe_available_count"
        )
        or 0
    )
    score_unknown_local_formula_review_bridge_ready = int(
        score_unknown_local_formula_review_packets_summary.get(
            "bridge_probe_ready_count"
        )
        or 0
    )
    score_unknown_local_formula_review_selected_json = int(
        score_unknown_local_formula_review_packets_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_local_formula_review_known = int(
        score_unknown_local_formula_review_packets_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_local_formula_review_approval_ready = int(
        score_unknown_local_formula_review_packets_summary.get("approval_ready_count")
        or 0
    )
    score_unknown_local_formula_review_contract_valid = int(
        score_unknown_local_formula_review_packets_summary.get(
            "local_formula_review_contract_valid_count"
        )
        or 0
    )
    score_unknown_local_formula_review_contract_invalid = int(
        score_unknown_local_formula_review_packets_summary.get(
            "local_formula_review_contract_invalid_count"
        )
        or 0
    )
    score_unknown_local_formula_review_prod_writes = int(
        score_unknown_local_formula_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_local_formula_source_capability_rows = int(
        score_local_formula_source_capability_summary.get(
            "local_formula_source_capability_row_count"
        )
        or 0
    )
    score_local_formula_source_capability_checks = int(
        score_local_formula_source_capability_summary.get("source_capability_check_count")
        or 0
    )
    score_local_formula_source_capability_candidates = int(
        score_local_formula_source_capability_summary.get("source_candidate_present_count")
        or 0
    )
    score_local_formula_source_header_empty = int(
        score_local_formula_source_capability_summary.get(
            "header_available_but_sample_empty_count"
        )
        or 0
    )
    score_local_formula_source_context = int(
        score_local_formula_source_capability_summary.get(
            "candidate_context_or_proxy_count"
        )
        or 0
    )
    score_local_formula_source_policy_required = int(
        score_local_formula_source_capability_summary.get("review_policy_required_count")
        or 0
    )
    score_local_formula_source_external_required = int(
        score_local_formula_source_capability_summary.get("external_or_text_required_count")
        or 0
    )
    score_local_formula_source_resolved = int(
        score_local_formula_source_capability_summary.get(
            "formula_blocker_resolved_by_current_source_count"
        )
        or 0
    )
    score_local_formula_source_ready = int(
        score_local_formula_source_capability_summary.get(
            "formula_inputs_ready_after_source_scan_count"
        )
        or 0
    )
    score_local_formula_source_probe = int(
        score_local_formula_source_capability_summary.get("formula_probe_available_count")
        or 0
    )
    score_local_formula_source_known = int(
        score_local_formula_source_capability_summary.get("known_draft_sufficient_count")
        or 0
    )
    score_local_formula_source_approval_ready = int(
        score_local_formula_source_capability_summary.get("approval_ready_count")
        or 0
    )
    score_local_formula_source_prod_writes = int(
        score_local_formula_source_capability_summary.get("production_write_allowed_count")
        or 0
    )
    score_unknown_external_business_tasks = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "external_business_metric_task_count"
        )
        or 0
    )
    score_unknown_external_business_runtime_ready = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "runtime_dependency_ready_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_hints = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "runtime_overlay_hint_count"
        )
        or 0
    )
    score_unknown_external_business_group_count = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "business_metric_group_count"
        )
        or 0
    )
    score_unknown_external_business_group_ready = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "business_metric_group_ready_count"
        )
        or 0
    )
    score_unknown_external_business_runtime_context = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "rows_with_supporting_runtime_context_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_context_rows = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "rows_with_overlay_business_context_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_context_known = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_business_context_known_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_frequency_known = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_frequency_context_known_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_penetration_known = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_penetration_context_known_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_frequency_direct_known = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_frequency_direct_known_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_penetration_direct_known = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_penetration_direct_known_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_frequency_direct_unknown = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_frequency_direct_unknown_node_count"
        )
        or 0
    )
    score_unknown_external_business_overlay_penetration_direct_unknown = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "overlay_penetration_direct_unknown_node_count"
        )
        or 0
    )
    score_unknown_external_business_direct_source = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "rows_with_direct_business_metric_source_count"
        )
        or 0
    )
    score_unknown_external_business_required_external = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "rows_requiring_external_or_text_source_count"
        )
        or 0
    )
    score_unknown_external_business_false_positives = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "excluded_false_positive_count"
        )
        or 0
    )
    score_unknown_external_business_metric_ready = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_known_draft = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "ready_for_known_draft_count"
        )
        or 0
    )
    score_unknown_external_business_contract_valid = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_contract_invalid = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_prod_writes = int(
        score_unknown_external_business_metric_acquisition_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_tasks = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "business_metric_market_doc_task_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_files = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "market_html_files_scanned"
        )
        or 0
    )
    score_unknown_external_business_market_doc_read_errors = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "market_html_read_error_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_rows = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "rows_with_review_candidates_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_documents = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "candidate_document_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_review = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "review_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_numeric = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "numeric_review_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_textual = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "textual_review_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_weak = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "weak_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_rejected = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "rejected_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_known = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_metric_ready = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_contract_valid = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_contract_invalid = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_market_doc_prod_writes = int(
        score_unknown_external_business_metric_market_doc_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_review_packets = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "business_metric_review_packet_count"
        )
        or 0
    )
    score_unknown_external_business_review_expected = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "expected_review_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_review_rows = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "rows_with_review_packets_count"
        )
        or 0
    )
    score_unknown_external_business_review_numeric = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "numeric_review_packet_count"
        )
        or 0
    )
    score_unknown_external_business_review_textual = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "textual_review_packet_count"
        )
        or 0
    )
    score_unknown_external_business_review_metric_ready = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_review_known = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_review_scope = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packets_with_scope_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_review_denominator = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packets_with_denominator_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_review_period = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packets_with_period_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_review_unit = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packets_with_unit_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_review_contract_valid = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packet_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_review_contract_invalid = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "packet_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_review_prod_writes = int(
        score_unknown_external_business_metric_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_packets = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "business_metric_review_packet_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_p0 = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "formula_policy_only_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_p1 = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "period_or_unit_required_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_p2 = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "denominator_required_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_missing_denominator = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "missing_denominator_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_missing_period = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "missing_period_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_missing_unit = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "missing_unit_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_missing_bounds = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "missing_bounds_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_missing_formula = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "missing_formula_policy_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_metric_ready = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_known = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_readiness_prod_writes = int(
        score_unknown_external_business_metric_readiness_queue_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_policy_p0 = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "p0_source_packet_count"
        )
        or 0
    )
    score_unknown_external_business_policy_drafts = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_draft_packet_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_required = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "formula_policy_review_required_count"
        )
        or 0
    )
    score_unknown_external_business_policy_value_templates = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "value_json_template_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_templates = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_review_template_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_templates_valid = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_review_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_templates_invalid = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_review_template_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_templates_blank = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_review_template_blank_pending_count"
        )
        or 0
    )
    score_unknown_external_business_policy_review_templates_input_ready = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_review_template_input_ready_count"
        )
        or 0
    )
    score_unknown_external_business_policy_metric_ready = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_policy_known = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_policy_contract_valid = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_policy_contract_invalid = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "policy_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_policy_prod_writes = int(
        score_unknown_external_business_metric_policy_drafts_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_value_rows = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "value_candidate_adjudication_row_count"
        )
        or 0
    )
    score_unknown_external_business_value_rows_with_tokens = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "rows_with_value_candidate_tokens_count"
        )
        or 0
    )
    score_unknown_external_business_value_tokens = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "value_candidate_token_count"
        )
        or 0
    )
    score_unknown_external_business_value_rejected_tokens = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "rejected_numeric_token_count"
        )
        or 0
    )
    score_unknown_external_business_value_shortlist = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "shortlist_review_required_count"
        )
        or 0
    )
    score_unknown_external_business_value_scope_rejected = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "scope_rejected_count"
        )
        or 0
    )
    score_unknown_external_business_value_no_numeric = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "no_scoreable_numeric_candidate_count"
        )
        or 0
    )
    score_unknown_external_business_value_metric_ready = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_value_known = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_value_contract_valid = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "value_candidate_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_value_contract_invalid = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "value_candidate_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_value_prod_writes = int(
        score_unknown_external_business_metric_value_candidates_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_packets = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "value_review_packet_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_options = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "candidate_value_option_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_bridge_ready = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "bridge_probe_ready_option_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_selected_raw = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "selected_raw_value_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_selected_json = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_metric_ready = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "metric_inputs_ready_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_known = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_approval_ready = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_contract_valid = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "value_review_contract_valid_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_contract_invalid = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "value_review_contract_invalid_count"
        )
        or 0
    )
    score_unknown_external_business_value_review_prod_writes = int(
        score_unknown_external_business_metric_value_review_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_business_value_selection_rows = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "business_metric_selection_row_count"
        )
        or 0
    )
    score_unknown_business_value_selection_packets = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "value_review_packet_count"
        )
        or 0
    )
    score_unknown_business_value_selection_options = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "candidate_value_option_count"
        )
        or 0
    )
    score_unknown_business_value_selection_bridge_ready = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "bridge_probe_ready_option_count"
        )
        or 0
    )
    score_unknown_business_value_selection_review_required = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "review_value_selection_required_count"
        )
        or 0
    )
    score_unknown_business_value_selection_policy_draft_ready = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "value_policy_draft_ready_count"
        )
        or 0
    )
    score_unknown_business_value_selection_policy_draft_status_ready = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "review_value_policy_draft_ready_count"
        )
        or score_unknown_business_value_selection_policy_draft_ready
    )
    score_unknown_business_value_selection_proposed_json = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "proposed_value_json_count"
        )
        or 0
    )
    score_unknown_business_value_selection_source_missing = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "source_metric_missing_count"
        )
        or 0
    )
    score_unknown_business_value_selection_auto = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "auto_selectable_count"
        )
        or 0
    )
    score_unknown_business_value_selection_selected_json = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_business_value_selection_known = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_business_value_selection_approval_ready = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_business_value_selection_contract_valid = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "selection_contract_valid_count"
        )
        or 0
    )
    score_unknown_business_value_selection_contract_invalid = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "selection_contract_invalid_count"
        )
        or 0
    )
    score_unknown_business_value_selection_prod_writes = int(
        score_unknown_business_metric_value_selection_gate_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_packets = int(
        score_unknown_penetration_value_priority_summary.get(
            "penetration_value_review_packet_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_options = int(
        score_unknown_penetration_value_priority_summary.get(
            "candidate_value_option_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_bridge_ready = int(
        score_unknown_penetration_value_priority_summary.get(
            "bridge_probe_ready_option_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_p1 = int(
        score_unknown_penetration_value_priority_summary.get(
            "preferred_source_scope_review_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_p2 = int(
        score_unknown_penetration_value_priority_summary.get(
            "industry_scope_review_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_p3_forecast = int(
        score_unknown_penetration_value_priority_summary.get(
            "forecast_or_assumption_review_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_p3_low_confidence = int(
        score_unknown_penetration_value_priority_summary.get(
            "low_confidence_community_review_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_selected_json = int(
        score_unknown_penetration_value_priority_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_known = int(
        score_unknown_penetration_value_priority_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_penetration_value_priority_approval_ready = int(
        score_unknown_penetration_value_priority_summary.get("approval_ready_count")
        or 0
    )
    score_unknown_penetration_value_priority_prod_writes = int(
        score_unknown_penetration_value_priority_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_p1_source_candidates = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "p1_candidate_count"
        )
        or 0
    )
    score_unknown_penetration_p1_source_found = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "source_file_found_count"
        )
        or 0
    )
    score_unknown_penetration_p1_raw_value_confirmed = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "raw_value_token_confirmed_count"
        )
        or 0
    )
    score_unknown_penetration_p1_scope_confirmed = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "source_scope_confirmed_count"
        )
        or 0
    )
    score_unknown_penetration_p1_selected_json = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_penetration_p1_known = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_penetration_p1_approval_ready = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_penetration_p1_prod_writes = int(
        score_unknown_penetration_p1_source_confirmation_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_rows = int(
        score_unknown_penetration_value_policy_draft_summary.get("draft_row_count")
        or 0
    )
    score_unknown_penetration_value_policy_draft_scope_confirmed = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "source_scope_confirmed_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_proposed_json = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "proposed_value_json_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_valid = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "draft_contract_valid_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_invalid = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "draft_contract_invalid_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_bridge_ready = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "bridge_final_score_ready_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_selected_json = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "selected_value_json_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_known = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_approval_ready = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_penetration_value_policy_draft_prod_writes = int(
        score_unknown_penetration_value_policy_draft_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_packets_count = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "value_confirmation_packet_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_templates = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "confirmation_record_template_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_valid = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "confirmation_record_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_packet_valid = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "confirmation_packet_contract_valid_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_known = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_approval_ready = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_prod_writes = int(
        score_unknown_penetration_value_confirmation_packets_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_count = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "confirmation_template_bundle_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_blank = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "blank_pending_template_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_valid = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "blank_pending_template_contract_valid_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_confirmed = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "confirmed_template_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_known = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "known_draft_sufficient_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_approval_ready = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "approval_ready_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_runtime_writes = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "runtime_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_template_bundle_prod_writes = int(
        score_unknown_penetration_value_confirmation_templates_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_packets = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "confirmation_packet_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_records = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "confirmation_records_seen"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_missing = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "confirmation_missing_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_confirmed = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "confirmed_value_policy_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_known_candidates = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "known_draft_candidate_count"
        )
        or 0
    )
    score_unknown_penetration_value_confirmation_gate_prod_writes = int(
        score_unknown_penetration_value_confirmation_gate_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_gate_rows = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "confirmation_gate_row_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_candidates = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "confirmed_value_policy_candidate_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_emitted = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "known_draft_emitted_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_blocked = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "known_draft_blocked_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_staging_ready = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "ready_for_review_staging_count"
        )
        or 0
    )
    score_unknown_penetration_confirmed_known_draft_prod_writes = int(
        score_unknown_penetration_confirmed_known_drafts_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_packet_count = int(
        score_approval_review_packets_summary.get("approval_review_packet_count") or 0
    )
    score_approval_packet_known = int(
        score_approval_review_packets_summary.get("known_packet_count") or 0
    )
    score_approval_packet_not_applicable = int(
        score_approval_review_packets_summary.get("not_applicable_packet_count") or 0
    )
    score_approval_packet_bridge_ready = int(
        score_approval_review_packets_summary.get("final_score_target_ready_count") or 0
    )
    score_approval_packet_missing = int(
        score_approval_review_packets_summary.get("approval_missing_count") or 0
    )
    score_approval_packet_templates = int(
        score_approval_review_packets_summary.get("approval_record_template_count") or 0
    )
    score_approval_packet_template_valid = int(
        score_approval_review_packets_summary.get(
            "approval_record_template_contract_valid_count"
        )
        or 0
    )
    score_approval_packet_template_invalid = int(
        score_approval_review_packets_summary.get(
            "approval_record_template_contract_invalid_count"
        )
        or 0
    )
    score_approval_packet_approved_writes = int(
        score_approval_review_packets_summary.get("approved_runtime_write_count") or 0
    )
    score_approval_packet_write_plan = int(
        score_approval_review_packets_summary.get("write_plan_count") or 0
    )
    score_approval_packet_prod_writes = int(
        score_approval_review_packets_summary.get("production_write_allowed_count") or 0
    )
    score_approval_risk_packets = int(
        score_approval_packet_risk_review_summary.get("packet_count") or 0
    )
    score_approval_risk_bulk_structured = int(
        score_approval_packet_risk_review_summary.get(
            "bulk_structured_review_candidate_count"
        )
        or 0
    )
    score_approval_risk_borderline = int(
        score_approval_packet_risk_review_summary.get(
            "borderline_structured_text_review_candidate_count"
        )
        or 0
    )
    score_approval_risk_individual = int(
        score_approval_packet_risk_review_summary.get("individual_review_required_count")
        or 0
    )
    score_approval_risk_event = int(
        score_approval_packet_risk_review_summary.get(
            "individual_event_evidence_review_required_count"
        )
        or 0
    )
    score_approval_risk_structured = int(
        score_approval_packet_risk_review_summary.get(
            "individual_structured_review_required_count"
        )
        or 0
    )
    score_approval_risk_policy = int(
        score_approval_packet_risk_review_summary.get(
            "individual_policy_review_required_count"
        )
        or 0
    )
    score_approval_risk_contract_fix = int(
        score_approval_packet_risk_review_summary.get(
            "do_not_approve_until_contract_fixed_count"
        )
        or 0
    )
    score_approval_risk_auto = int(
        score_approval_packet_risk_review_summary.get("auto_approval_allowed_count")
        or 0
    )
    score_approval_risk_prod_writes = int(
        score_approval_packet_risk_review_summary.get("production_write_allowed_count")
        or 0
    )
    score_bulk_review_candidate_count = int(
        score_bulk_review_approval_candidates_summary.get("candidate_count") or 0
    )
    score_bulk_review_strict = int(
        score_bulk_review_approval_candidates_summary.get("strict_bulk_candidate_count")
        or 0
    )
    score_bulk_review_borderline = int(
        score_bulk_review_approval_candidates_summary.get(
            "borderline_sample_check_candidate_count"
        )
        or 0
    )
    score_bulk_review_drafts = int(
        score_bulk_review_approval_candidates_summary.get(
            "approval_record_draft_count"
        )
        or 0
    )
    score_bulk_review_draft_valid = int(
        score_bulk_review_approval_candidates_summary.get(
            "approval_record_draft_contract_valid_count"
        )
        or 0
    )
    score_bulk_review_draft_invalid = int(
        score_bulk_review_approval_candidates_summary.get(
            "approval_record_draft_contract_invalid_count"
        )
        or 0
    )
    score_bulk_review_auto = int(
        score_bulk_review_approval_candidates_summary.get("auto_approval_allowed_count")
        or 0
    )
    score_bulk_review_prod_writes = int(
        score_bulk_review_approval_candidates_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_bulk_source_sample_candidates = int(
        score_bulk_review_source_samples_summary.get("candidate_count") or 0
    )
    score_bulk_source_sample_complete = int(
        score_bulk_review_source_samples_summary.get("reviewer_packet_complete_count") or 0
    )
    score_bulk_source_sample_payload_match = int(
        score_bulk_review_source_samples_summary.get("source_payload_matches_candidate_count")
        or 0
    )
    score_bulk_source_sample_evidence_complete = int(
        score_bulk_review_source_samples_summary.get("evidence_refs_complete_count") or 0
    )
    score_bulk_source_sample_borderline_ready = int(
        score_bulk_review_source_samples_summary.get(
            "borderline_sample_evidence_ready_count"
        )
        or 0
    )
    score_bulk_source_sample_prod_writes = int(
        score_bulk_review_source_samples_summary.get("production_write_allowed_count") or 0
    )
    score_event_approval_source_sample_packets = int(
        score_event_approval_source_samples_summary.get("event_text_approval_packet_count")
        or 0
    )
    score_event_approval_individual_reviews = int(
        score_event_approval_source_samples_summary.get(
            "individual_event_evidence_review_required_count"
        )
        or 0
    )
    score_event_approval_payload_match = int(
        score_event_approval_source_samples_summary.get(
            "source_payload_matches_candidate_count"
        )
        or 0
    )
    score_event_approval_market_packet_found = int(
        score_event_approval_source_samples_summary.get(
            "market_doc_review_packet_found_count"
        )
        or 0
    )
    score_event_approval_market_refs_complete = int(
        score_event_approval_source_samples_summary.get(
            "market_doc_review_refs_complete_count"
        )
        or 0
    )
    score_event_approval_dockcase_refs = int(
        score_event_approval_source_samples_summary.get("dockcase_ref_count") or 0
    )
    score_event_approval_dockcase_readable = int(
        score_event_approval_source_samples_summary.get("dockcase_file_readable_count")
        or 0
    )
    score_event_approval_keyword_ready = int(
        score_event_approval_source_samples_summary.get(
            "dockcase_keyword_evidence_ready_count"
        )
        or 0
    )
    score_event_approval_template_count = int(
        score_event_approval_source_samples_summary.get(
            "event_evidence_review_template_count"
        )
        or 0
    )
    score_event_approval_template_valid = int(
        score_event_approval_source_samples_summary.get(
            "event_evidence_review_template_contract_valid_count"
        )
        or 0
    )
    score_event_approval_template_blank = int(
        score_event_approval_source_samples_summary.get(
            "event_evidence_review_template_blank_pending_count"
        )
        or 0
    )
    score_event_approval_complete = int(
        score_event_approval_source_samples_summary.get("reviewer_packet_complete_count")
        or 0
    )
    score_event_approval_prod_writes = int(
        score_event_approval_source_samples_summary.get("production_write_allowed_count")
        or 0
    )
    score_individual_source_sample_packets = int(
        score_individual_review_source_samples_summary.get(
            "individual_review_source_sample_count"
        )
        or 0
    )
    score_individual_structured_reviews = int(
        score_individual_review_source_samples_summary.get(
            "individual_structured_review_required_count"
        )
        or 0
    )
    score_individual_policy_reviews = int(
        score_individual_review_source_samples_summary.get(
            "individual_policy_review_required_count"
        )
        or 0
    )
    score_individual_manual_policy_reviews = int(
        score_individual_review_source_samples_summary.get("manual_policy_review_count")
        or 0
    )
    score_individual_event_policy_reviews = int(
        score_individual_review_source_samples_summary.get("event_policy_review_count")
        or 0
    )
    score_individual_structured_proxy_reviews = int(
        score_individual_review_source_samples_summary.get("structured_proxy_review_count")
        or 0
    )
    score_individual_payload_match = int(
        score_individual_review_source_samples_summary.get(
            "source_payload_matches_candidate_count"
        )
        or 0
    )
    score_individual_evidence_refs_complete = int(
        score_individual_review_source_samples_summary.get("evidence_refs_complete_count")
        or 0
    )
    score_individual_text_sample_ready = int(
        score_individual_review_source_samples_summary.get(
            "text_sample_evidence_ready_count"
        )
        or 0
    )
    score_individual_event_source_complete = int(
        score_individual_review_source_samples_summary.get(
            "event_source_sample_reviewer_packet_complete_count"
        )
        or 0
    )
    score_individual_template_count = int(
        score_individual_review_source_samples_summary.get(
            "individual_review_template_count"
        )
        or 0
    )
    score_individual_template_valid = int(
        score_individual_review_source_samples_summary.get(
            "individual_review_template_contract_valid_count"
        )
        or 0
    )
    score_individual_template_blank = int(
        score_individual_review_source_samples_summary.get(
            "individual_review_template_blank_pending_count"
        )
        or 0
    )
    score_individual_complete = int(
        score_individual_review_source_samples_summary.get("reviewer_packet_complete_count")
        or 0
    )
    score_individual_prod_writes = int(
        score_individual_review_source_samples_summary.get("production_write_allowed_count")
        or 0
    )
    score_approval_source_coverage_packets = int(
        score_approval_source_sample_coverage_summary.get("approval_packet_count") or 0
    )
    score_approval_source_coverage_supported = int(
        score_approval_source_sample_coverage_summary.get(
            "source_sample_supported_packet_count"
        )
        or 0
    )
    score_approval_source_coverage_found = int(
        score_approval_source_sample_coverage_summary.get("source_sample_found_count")
        or 0
    )
    score_approval_source_coverage_complete = int(
        score_approval_source_sample_coverage_summary.get(
            "source_sample_reviewer_packet_complete_count"
        )
        or 0
    )
    score_approval_source_coverage_payload_match = int(
        score_approval_source_sample_coverage_summary.get(
            "source_sample_payload_matches_candidate_count"
        )
        or 0
    )
    score_approval_source_coverage_template_valid = int(
        score_approval_source_sample_coverage_summary.get(
            "source_sample_review_template_contract_valid_count"
        )
        or 0
    )
    score_approval_source_coverage_approval_template_valid = int(
        score_approval_source_sample_coverage_summary.get(
            "approval_record_template_blank_contract_valid_count"
        )
        or 0
    )
    score_approval_source_coverage_input_ready = int(
        score_approval_source_sample_coverage_summary.get("approval_input_ready_count")
        or 0
    )
    score_approval_source_coverage_input_not_ready = int(
        score_approval_source_sample_coverage_summary.get(
            "approval_input_not_ready_count"
        )
        or 0
    )
    score_approval_source_coverage_unsupported = int(
        score_approval_source_sample_coverage_summary.get("unsupported_risk_class_count")
        or 0
    )
    score_approval_source_coverage_prod_writes = int(
        score_approval_source_sample_coverage_summary.get("production_write_allowed_count")
        or 0
    )
    score_approval_target_scope_packets = int(
        score_approval_target_scope_readiness_summary.get("approval_packet_count") or 0
    )
    score_approval_target_scope_final_ready = int(
        score_approval_target_scope_readiness_summary.get(
            "final_score_target_ready_count"
        )
        or 0
    )
    score_approval_target_scope_samples_complete = int(
        score_approval_target_scope_readiness_summary.get(
            "source_sample_reviewer_packet_complete_count"
        )
        or 0
    )
    score_approval_target_scope_existing_policies = int(
        score_approval_target_scope_readiness_summary.get(
            "existing_target_scope_policy_count"
        )
        or 0
    )
    score_approval_target_scope_supported = int(
        score_approval_target_scope_readiness_summary.get(
            "supported_by_existing_target_scope_policy_count"
        )
        or 0
    )
    score_approval_target_scope_explicit = int(
        score_approval_target_scope_readiness_summary.get("explicit_target_scope_count")
        or 0
    )
    score_approval_target_scope_ready = int(
        score_approval_target_scope_readiness_summary.get(
            "target_scope_ready_after_approval_count"
        )
        or 0
    )
    score_approval_target_scope_policy_required = int(
        score_approval_target_scope_readiness_summary.get(
            "target_scope_policy_required_count"
        )
        or 0
    )
    score_approval_target_scope_per_stock = int(
        score_approval_target_scope_readiness_summary.get(
            "per_stock_value_materialization_required_count"
        )
        or 0
    )
    score_approval_target_scope_market_event = int(
        score_approval_target_scope_readiness_summary.get(
            "market_or_event_scope_policy_required_count"
        )
        or 0
    )
    score_approval_target_scope_materialization_ready = int(
        score_approval_target_scope_readiness_summary.get(
            "runtime_materialization_ready_count"
        )
        or 0
    )
    score_approval_target_scope_approval_only_not_sufficient = int(
        score_approval_target_scope_readiness_summary.get(
            "approval_only_not_sufficient_count"
        )
        or 0
    )
    score_approval_target_scope_safe_after_approval = int(
        score_approval_target_scope_readiness_summary.get(
            "safe_runtime_write_after_approval_count"
        )
        or 0
    )
    score_approval_target_scope_prod_writes = int(
        score_approval_target_scope_readiness_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_packets = int(
        score_approval_materialization_plan_summary.get("approval_packet_count") or 0
    )
    score_approval_materialization_a_share_universe = int(
        score_approval_materialization_plan_summary.get("a_share_universe_count") or 0
    )
    score_approval_materialization_fundamental_packets = int(
        score_approval_materialization_plan_summary.get("fundamental_packet_count") or 0
    )
    score_approval_materialization_direct_formula = int(
        score_approval_materialization_plan_summary.get(
            "direct_structured_formula_packet_count"
        )
        or 0
    )
    score_approval_materialization_direct_formula_ready = int(
        score_approval_materialization_plan_summary.get(
            "direct_structured_formula_plan_ready_count"
        )
        or 0
    )
    score_approval_materialization_min_target = int(
        score_approval_materialization_plan_summary.get(
            "direct_structured_formula_min_target_count"
        )
        or 0
    )
    score_approval_materialization_max_target = int(
        score_approval_materialization_plan_summary.get(
            "direct_structured_formula_max_target_count"
        )
        or 0
    )
    score_approval_materialization_grain_join = int(
        score_approval_materialization_plan_summary.get(
            "grain_join_policy_required_count"
        )
        or 0
    )
    score_approval_materialization_text_export = int(
        score_approval_materialization_plan_summary.get(
            "text_evidence_full_match_export_required_count"
        )
        or 0
    )
    score_approval_materialization_market_event = int(
        score_approval_materialization_plan_summary.get(
            "market_or_event_scope_policy_required_count"
        )
        or 0
    )
    score_approval_materialization_unsupported = int(
        score_approval_materialization_plan_summary.get(
            "unsupported_materialization_policy_count"
        )
        or 0
    )
    score_approval_materialization_ready = int(
        score_approval_materialization_plan_summary.get(
            "runtime_materialization_plan_ready_count"
        )
        or 0
    )
    score_approval_materialization_runtime_writes = int(
        score_approval_materialization_plan_summary.get("runtime_write_allowed_count")
        or 0
    )
    score_approval_materialization_prod_writes = int(
        score_approval_materialization_plan_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_batch_formula_plans = int(
        score_approval_materialization_batch_plan_summary.get(
            "direct_formula_plan_count"
        )
        or 0
    )
    score_approval_materialization_batch_entries = int(
        score_approval_materialization_batch_plan_summary.get("batch_plan_entry_count")
        or 0
    )
    score_approval_materialization_batch_contract_valid = int(
        score_approval_materialization_batch_plan_summary.get(
            "batch_plan_contract_valid_count"
        )
        or 0
    )
    score_approval_materialization_batch_contract_invalid = int(
        score_approval_materialization_batch_plan_summary.get(
            "batch_plan_contract_invalid_count"
        )
        or 0
    )
    score_approval_materialization_batch_review_required = int(
        score_approval_materialization_batch_plan_summary.get(
            "batch_plan_review_required_count"
        )
        or 0
    )
    score_approval_materialization_batch_approved = int(
        score_approval_materialization_batch_plan_summary.get(
            "batch_plan_approved_count"
        )
        or 0
    )
    score_approval_materialization_batch_rows = int(
        score_approval_materialization_batch_plan_summary.get(
            "planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_batch_inserts = int(
        score_approval_materialization_batch_plan_summary.get("rows_to_insert_count")
        or 0
    )
    score_approval_materialization_batch_updates = int(
        score_approval_materialization_batch_plan_summary.get("rows_to_update_count")
        or 0
    )
    score_approval_materialization_batch_backup_rows = int(
        score_approval_materialization_batch_plan_summary.get(
            "existing_rows_to_backup_count"
        )
        or 0
    )
    score_approval_materialization_batch_upsert_ready = int(
        score_approval_materialization_batch_plan_summary.get(
            "upsert_ready_entry_count"
        )
        or 0
    )
    score_approval_materialization_batch_blocked = int(
        score_approval_materialization_batch_plan_summary.get("blocked_entry_count")
        or 0
    )
    score_approval_materialization_batch_attempted = int(
        score_approval_materialization_batch_plan_summary.get(
            "runtime_write_attempted_count"
        )
        or 0
    )
    score_approval_materialization_batch_prod_writes = int(
        score_approval_materialization_batch_plan_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_codex_rows = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "batch_plan_row_count"
        )
        or 0
    )
    score_approval_materialization_codex_approved = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "codex_review_approved_count"
        )
        or 0
    )
    score_approval_materialization_codex_rejected = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "codex_review_rejected_count"
        )
        or 0
    )
    score_approval_materialization_codex_records = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "approval_record_count"
        )
        or 0
    )
    score_approval_materialization_codex_planned_rows = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_codex_approved_rows = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "approved_planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_codex_inserts = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "rows_to_insert_count"
        )
        or 0
    )
    score_approval_materialization_codex_updates = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "rows_to_update_count"
        )
        or 0
    )
    score_approval_materialization_codex_backup_rows = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "existing_rows_to_backup_count"
        )
        or 0
    )
    score_approval_materialization_codex_runtime_writes = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "runtime_write_attempted_count"
        )
        or 0
    )
    score_approval_materialization_codex_prod_writes = int(
        score_approval_materialization_batch_codex_review_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_gate_rows = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "batch_plan_row_count"
        )
        or 0
    )
    score_approval_materialization_gate_contract_valid = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "batch_plan_contract_valid_count"
        )
        or 0
    )
    score_approval_materialization_gate_records_seen = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approval_records_seen"
        )
        or 0
    )
    score_approval_materialization_gate_required = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approval_required_count"
        )
        or 0
    )
    score_approval_materialization_gate_missing = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approval_missing_count"
        )
        or 0
    )
    score_approval_materialization_gate_rejected = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approval_rejected_count"
        )
        or 0
    )
    score_approval_materialization_gate_approved = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approved_controlled_formula_batch_plan_count"
        )
        or 0
    )
    score_approval_materialization_gate_templates = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "blank_approval_template_count"
        )
        or 0
    )
    score_approval_materialization_gate_templates_valid = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "blank_approval_template_contract_valid_count"
        )
        or 0
    )
    score_approval_materialization_gate_planned_rows = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_gate_approved_rows = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "approved_planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_gate_runtime_writes = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "runtime_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_gate_prod_writes = int(
        score_approval_materialization_batch_approval_gate_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_approval_materialization_preflight_entries = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "batch_plan_entry_count"
        )
        or 0
    )
    score_approval_materialization_preflight_approved = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "approved_batch_plan_count"
        )
        or 0
    )
    score_approval_materialization_preflight_checked = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "preflight_checked_count"
        )
        or 0
    )
    score_approval_materialization_preflight_ready = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "preflight_ready_count"
        )
        or 0
    )
    score_approval_materialization_preflight_blocked = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "preflight_blocked_count"
        )
        or 0
    )
    score_approval_materialization_preflight_planned_rows = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "planned_upsert_row_count"
        )
        or 0
    )
    score_approval_materialization_preflight_would_write = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "runtime_rows_would_write_count"
        )
        or 0
    )
    score_approval_materialization_preflight_inserts = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "rows_to_insert_count"
        )
        or 0
    )
    score_approval_materialization_preflight_updates = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "rows_to_update_count"
        )
        or 0
    )
    score_approval_materialization_preflight_backup_rows = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "existing_rows_to_backup_count"
        )
        or 0
    )
    score_approval_materialization_preflight_backups_required = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "runtime_backup_required_count"
        )
        or 0
    )
    score_approval_materialization_preflight_backups_created = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "runtime_backup_created_count"
        )
        or 0
    )
    score_approval_materialization_preflight_write_attempts = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "runtime_write_attempted_count"
        )
        or 0
    )
    score_approval_materialization_preflight_write_completed = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "runtime_write_completed_count"
        )
        or 0
    )
    score_approval_materialization_preflight_verified_rows = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "post_write_verified_row_count"
        )
        or 0
    )
    score_approval_materialization_preflight_prod_writes = int(
        score_approval_materialization_batch_execution_preflight_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_runtime_scope_approval_rows = int(
        score_runtime_scope_approvals_summary.get("target_scope_row_count") or 0
    )
    score_runtime_scope_approval_records = int(
        score_runtime_scope_approvals_summary.get("scope_approval_record_count") or 0
    )
    score_runtime_scope_approved_scopes = int(
        score_runtime_scope_approvals_summary.get("approved_runtime_target_scope_count")
        or 0
    )
    score_runtime_scope_rejected = int(
        score_runtime_scope_approvals_summary.get("scope_policy_rejected_count") or 0
    )
    score_runtime_scope_approval_candidate_rows = int(
        score_runtime_scope_approvals_summary.get(
            "candidate_runtime_rows_would_write_count"
        )
        or 0
    )
    score_runtime_scope_approval_attempted = int(
        score_runtime_scope_approvals_summary.get("runtime_write_attempted_count") or 0
    )
    score_runtime_scope_approval_prod_writes = int(
        score_runtime_scope_approvals_summary.get("production_write_allowed_count") or 0
    )
    score_runtime_scope_approved_entries = int(
        score_runtime_write_target_scope_summary.get("approved_write_plan_entry_count")
        or 0
    )
    score_runtime_scope_runtime_a_share = int(
        score_runtime_write_target_scope_summary.get("runtime_a_share_ts_code_count")
        or 0
    )
    score_runtime_scope_config_a_share = int(
        score_runtime_write_target_scope_summary.get("config_a_share_ts_code_count")
        or 0
    )
    score_runtime_scope_exact_match = bool(
        score_runtime_write_target_scope_summary.get(
            "config_runtime_a_share_exact_match"
        )
    )
    score_runtime_scope_candidates = int(
        score_runtime_write_target_scope_summary.get("target_scope_candidate_count") or 0
    )
    score_runtime_scope_contract_valid = int(
        score_runtime_write_target_scope_summary.get(
            "target_scope_contract_valid_count"
        )
        or 0
    )
    score_runtime_scope_contract_invalid = int(
        score_runtime_write_target_scope_summary.get(
            "target_scope_contract_invalid_count"
        )
        or 0
    )
    score_runtime_scope_review_required = int(
        score_runtime_write_target_scope_summary.get(
            "target_scope_review_required_count"
        )
        or 0
    )
    score_runtime_scope_approved_count = int(
        score_runtime_write_target_scope_summary.get("target_scope_approved_count") or 0
    )
    score_runtime_scope_batch_plan_required = int(
        score_runtime_write_target_scope_summary.get(
            "controlled_batch_plan_required_count"
        )
        or 0
    )
    score_runtime_scope_candidate_rows = int(
        score_runtime_write_target_scope_summary.get(
            "candidate_runtime_rows_would_write_count"
        )
        or 0
    )
    score_runtime_scope_upsert_ready = int(
        score_runtime_write_target_scope_summary.get("upsert_ready_entry_count") or 0
    )
    score_runtime_scope_attempted = int(
        score_runtime_write_target_scope_summary.get("runtime_write_attempted_count") or 0
    )
    score_runtime_scope_prod_writes = int(
        score_runtime_write_target_scope_summary.get("production_write_allowed_count")
        or 0
    )
    score_runtime_batch_plan_entries = int(
        score_runtime_write_batch_plan_summary.get("batch_plan_entry_count") or 0
    )
    score_runtime_batch_plan_valid = int(
        score_runtime_write_batch_plan_summary.get("batch_plan_contract_valid_count")
        or 0
    )
    score_runtime_batch_plan_invalid = int(
        score_runtime_write_batch_plan_summary.get(
            "batch_plan_contract_invalid_count"
        )
        or 0
    )
    score_runtime_batch_plan_review_required = int(
        score_runtime_write_batch_plan_summary.get("batch_plan_review_required_count")
        or 0
    )
    score_runtime_batch_plan_approved = int(
        score_runtime_write_batch_plan_summary.get("batch_plan_approved_count") or 0
    )
    score_runtime_batch_plan_rows = int(
        score_runtime_write_batch_plan_summary.get("planned_upsert_row_count") or 0
    )
    score_runtime_batch_plan_insert_rows = int(
        score_runtime_write_batch_plan_summary.get("rows_to_insert_count") or 0
    )
    score_runtime_batch_plan_update_rows = int(
        score_runtime_write_batch_plan_summary.get("rows_to_update_count") or 0
    )
    score_runtime_batch_plan_backup_rows = int(
        score_runtime_write_batch_plan_summary.get("existing_rows_to_backup_count")
        or 0
    )
    score_runtime_batch_plan_attempted = int(
        score_runtime_write_batch_plan_summary.get("runtime_write_attempted_count") or 0
    )
    score_runtime_batch_plan_prod_writes = int(
        score_runtime_write_batch_plan_summary.get("production_write_allowed_count") or 0
    )
    score_runtime_batch_approval_rows = int(
        score_runtime_write_batch_approvals_summary.get("batch_plan_row_count") or 0
    )
    score_runtime_batch_approval_records = int(
        score_runtime_write_batch_approvals_summary.get("batch_approval_record_count")
        or 0
    )
    score_runtime_batch_approved_count = int(
        score_runtime_write_batch_approvals_summary.get(
            "approved_controlled_batch_plan_count"
        )
        or 0
    )
    score_runtime_batch_policy_rejected = int(
        score_runtime_write_batch_approvals_summary.get("batch_policy_rejected_count")
        or 0
    )
    score_runtime_batch_approval_rows_planned = int(
        score_runtime_write_batch_approvals_summary.get("planned_upsert_row_count")
        or 0
    )
    score_runtime_batch_approval_insert_rows = int(
        score_runtime_write_batch_approvals_summary.get("rows_to_insert_count") or 0
    )
    score_runtime_batch_approval_update_rows = int(
        score_runtime_write_batch_approvals_summary.get("rows_to_update_count") or 0
    )
    score_runtime_batch_approval_backup_rows = int(
        score_runtime_write_batch_approvals_summary.get(
            "existing_rows_to_backup_count"
        )
        or 0
    )
    score_runtime_batch_approval_attempted = int(
        score_runtime_write_batch_approvals_summary.get("runtime_write_attempted_count")
        or 0
    )
    score_runtime_batch_approval_prod_writes = int(
        score_runtime_write_batch_approvals_summary.get(
            "production_write_allowed_count"
        )
        or 0
    )
    score_runtime_execution_approved = int(
        score_runtime_write_execution_summary.get("approved_controlled_batch_plan_count")
        or score_runtime_write_execution_summary.get("approved_batch_plan_count")
        or 0
    )
    score_runtime_execution_ready = int(
        score_runtime_write_execution_summary.get("execution_ready_count") or 0
    )
    score_runtime_execution_blocked = int(
        score_runtime_write_execution_summary.get("execution_blocked_count") or 0
    )
    score_runtime_execution_backup_completed = int(
        score_runtime_write_execution_summary.get("backup_completed_count") or 0
    )
    score_runtime_execution_backup_failed = int(
        score_runtime_write_execution_summary.get("backup_failed_count") or 0
    )
    score_runtime_execution_attempted = int(
        score_runtime_write_execution_summary.get("runtime_write_attempted_count") or 0
    )
    score_runtime_execution_completed = int(
        score_runtime_write_execution_summary.get("runtime_write_completed_count") or 0
    )
    score_runtime_execution_failed = int(
        score_runtime_write_execution_summary.get("runtime_write_failed_count") or 0
    )
    score_runtime_execution_rows = int(
        score_runtime_write_execution_summary.get("runtime_rows_written_count")
        or score_runtime_write_execution_summary.get("upserted_row_count")
        or 0
    )
    score_runtime_execution_insert_rows = int(
        score_runtime_write_execution_summary.get("rows_inserted_count") or 0
    )
    score_runtime_execution_update_rows = int(
        score_runtime_write_execution_summary.get("rows_updated_count") or 0
    )
    score_runtime_execution_verified_rows = int(
        score_runtime_write_execution_summary.get("post_write_verified_row_count") or 0
    )
    score_runtime_execution_verification_errors = int(
        score_runtime_write_execution_summary.get(
            "post_write_verification_error_count"
        )
        or 0
    )
    score_runtime_execution_prod_writes = int(
        score_runtime_write_execution_summary.get("production_write_allowed_count") or 0
    )
    score_runtime_preflight_approved_entries = int(
        score_runtime_write_preflight_summary.get("approved_write_plan_entry_count") or 0
    )
    score_runtime_preflight_upsert_ready = int(
        score_runtime_write_preflight_summary.get("upsert_ready_entry_count") or 0
    )
    score_runtime_preflight_blocked = int(
        score_runtime_write_preflight_summary.get("blocked_entry_count") or 0
    )
    score_runtime_preflight_missing_scope = int(
        score_runtime_write_preflight_summary.get("missing_target_scope_count") or 0
    )
    score_runtime_preflight_rows_would_write = int(
        score_runtime_write_preflight_summary.get("runtime_rows_would_write_count") or 0
    )
    score_runtime_preflight_candidate_rows = int(
        score_runtime_write_preflight_summary.get(
            "candidate_runtime_rows_would_write_count"
        )
        or 0
    )
    score_runtime_preflight_batch_plan_required = int(
        score_runtime_write_preflight_summary.get(
            "controlled_batch_plan_required_count"
        )
        or 0
    )
    score_runtime_preflight_batch_plan_candidates = int(
        score_runtime_write_preflight_summary.get("batch_plan_candidate_count") or 0
    )
    score_runtime_preflight_batch_plan_review_required = int(
        score_runtime_write_preflight_summary.get("batch_plan_review_required_count")
        or 0
    )
    score_runtime_preflight_batch_plan_approved = int(
        score_runtime_write_preflight_summary.get("batch_plan_approved_count") or 0
    )
    score_runtime_preflight_backup_execution_required = int(
        score_runtime_write_preflight_summary.get(
            "runtime_backup_execution_required_count"
        )
        or 0
    )
    score_runtime_preflight_executed_entries = int(
        score_runtime_write_preflight_summary.get("executed_entry_count") or 0
    )
    score_runtime_preflight_execution_completed = int(
        score_runtime_write_preflight_summary.get(
            "runtime_execution_completed_count"
        )
        or 0
    )
    score_runtime_preflight_execution_rows = int(
        score_runtime_write_preflight_summary.get(
            "runtime_execution_rows_written_count"
        )
        or 0
    )
    score_runtime_preflight_execution_verified_rows = int(
        score_runtime_write_preflight_summary.get(
            "runtime_execution_post_write_verified_row_count"
        )
        or 0
    )
    score_runtime_preflight_batch_plan_rows = int(
        score_runtime_write_preflight_summary.get(
            "batch_plan_planned_upsert_rows_count"
        )
        or 0
    )
    score_runtime_preflight_batch_plan_backup_rows = int(
        score_runtime_write_preflight_summary.get(
            "batch_plan_existing_rows_to_backup_count"
        )
        or 0
    )
    score_runtime_preflight_attempted = int(
        score_runtime_write_preflight_summary.get("runtime_write_attempted_count") or 0
    )
    score_runtime_preflight_prod_writes = int(
        score_runtime_write_preflight_summary.get("production_write_allowed_count") or 0
    )
    score_numeric_current_final = int(
        score_spec_numeric_validity_summary.get(
            "current_final_score_numeric_dp_ids",
            score_closed_fields,
        )
        or 0
    )
    score_numeric_relevant = int(
        score_spec_numeric_validity_summary.get(
            "score_relevant_spec_dp_ids",
            score_relevant_fields,
        )
        or 0
    )
    score_numeric_not_final = int(
        score_spec_numeric_validity_summary.get(
            "current_score_relevant_not_final_score_dp_ids"
        )
        or 0
    )
    score_numeric_review_ready = int(
        score_spec_numeric_validity_summary.get(
            "review_ready_concrete_final_score_dp_ids"
        )
        or 0
    )
    score_numeric_unknown = int(
        score_spec_numeric_validity_summary.get("review_gated_unknown_dp_ids") or 0
    )
    score_numeric_approved_writes = int(
        score_spec_numeric_validity_summary.get("approved_runtime_write_count") or 0
    )
    score_approval_consistency_errors = _score_approval_consistency_errors(
        review_manifest_summary=score_review_staging_manifest_summary,
        deterministic_approvals_summary=score_deterministic_runtime_approvals_summary,
        approval_gate_summary=score_review_approval_gate_summary,
        completion_next_actions_summary=score_completion_next_actions_summary,
        approval_review_packets_summary=score_approval_review_packets_summary,
        spec_numeric_validity_summary=score_spec_numeric_validity_summary,
        runtime_write_execution_summary=score_runtime_write_execution_summary,
    )
    score_conversion_total = int(
        score_spec_score_conversion_summary.get("total_checked_count") or 0
    )
    score_conversion_relevant = int(
        score_spec_score_conversion_summary.get("score_relevant_final_target_count") or 0
    )
    score_conversion_current_numeric = int(
        score_spec_score_conversion_summary.get("current_numeric_final_score_count") or 0
    )
    score_conversion_candidate_ready = int(
        score_spec_score_conversion_summary.get("candidate_numeric_score_path_ready_count")
        or 0
    )
    score_conversion_sample_ready = int(
        score_spec_score_conversion_summary.get("sample_numeric_score_path_ready_count")
        or 0
    )
    score_conversion_ready = int(
        score_spec_score_conversion_summary.get("numeric_and_score_path_ready_count") or 0
    )
    score_conversion_unresolved = int(
        score_spec_score_conversion_summary.get("unresolved_score_relevant_count") or 0
    )
    score_conversion_no_formula = int(
        score_spec_score_conversion_summary.get("not_numeric_or_no_formula_count") or 0
    )
    score_conversion_no_input = int(
        score_spec_score_conversion_summary.get("no_current_numeric_input_count") or 0
    )
    score_conversion_formula_review = int(
        score_spec_score_conversion_summary.get("formula_policy_review_required_count")
        or 0
    )
    score_conversion_governance_verified = int(
        score_spec_score_conversion_summary.get(
            "governance_suppression_verified_count"
        )
        or 0
    )
    score_conversion_option_verified = int(
        score_spec_score_conversion_summary.get("option_universe_na_verified_count")
        or 0
    )
    score_conversion_verified_exceptions = int(
        score_spec_score_conversion_summary.get(
            "verified_non_numeric_exception_count"
        )
        or 0
    )
    score_conversion_review_backed = int(
        score_spec_score_conversion_summary.get(
            "review_decision_backed_not_ready_count"
        )
        or 0
    )
    score_conversion_unclassified = int(
        score_spec_score_conversion_summary.get(
            "remaining_unclassified_conversion_gap_count"
        )
        or 0
    )
    score_conversion_formula_artifact = int(
        score_spec_score_conversion_summary.get(
            "formula_policy_packet_artifact_count"
        )
        or 0
    )
    score_conversion_governance_artifact = int(
        score_spec_score_conversion_summary.get(
            "governance_suppression_artifact_verified_count"
        )
        or 0
    )
    score_conversion_option_artifact = int(
        score_spec_score_conversion_summary.get(
            "option_universe_na_artifact_valid_count"
        )
        or 0
    )
    score_conversion_no_weight = int(
        score_spec_score_conversion_summary.get("no_weight_or_non_scoring_count") or 0
    )
    score_conversion_prod_writes = int(
        score_spec_score_conversion_summary.get("production_write_allowed_count") or 0
    )
    score_remediation_unresolved = int(
        score_conversion_remediation_summary.get("unresolved_score_relevant_count") or 0
    )
    score_remediation_existing_inputs = int(
        score_conversion_remediation_summary.get("existing_current_input_count") or 0
    )
    score_remediation_no_inputs = int(
        score_conversion_remediation_summary.get("no_current_input_count") or 0
    )
    score_remediation_formula_policy = int(
        score_conversion_remediation_summary.get("formula_policy_required_count") or 0
    )
    score_remediation_governance = int(
        score_conversion_remediation_summary.get(
            "intentional_governance_or_duplicate_count"
        )
        or 0
    )
    score_remediation_missing_source = int(
        score_conversion_remediation_summary.get(
            "missing_or_not_applicable_source_count"
        )
        or 0
    )
    score_remediation_safe_formula = int(
        score_conversion_remediation_summary.get("safe_formula_now_count") or 0
    )
    score_remediation_prod_writes = int(
        score_conversion_remediation_summary.get("production_write_allowed_count") or 0
    )
    score_formula_policy_packets = int(
        score_formula_policy_review_packets_summary.get("formula_policy_packet_count") or 0
    )
    score_formula_policy_current_inputs = int(
        score_formula_policy_review_packets_summary.get("current_input_available_count")
        or 0
    )
    score_formula_policy_valuation = int(
        score_formula_policy_review_packets_summary.get(
            "valuation_peer_context_packet_count"
        )
        or 0
    )
    score_formula_policy_business = int(
        score_formula_policy_review_packets_summary.get("business_semantics_packet_count")
        or 0
    )
    score_formula_policy_replacement_ready = int(
        score_formula_policy_review_packets_summary.get("replacement_path_ready_count")
        or 0
    )
    score_formula_policy_direct_ready = int(
        score_formula_policy_review_packets_summary.get("direct_formula_ready_count")
        or 0
    )
    score_formula_policy_contract_valid = int(
        score_formula_policy_review_packets_summary.get("policy_contract_valid_count")
        or 0
    )
    score_formula_policy_prod_writes = int(
        score_formula_policy_review_packets_summary.get("production_write_allowed_count")
        or 0
    )
    score_governance_suppression_packets = int(
        score_governance_suppression_summary.get(
            "governance_suppression_packet_count"
        )
        or 0
    )
    score_governance_suppression_verified = int(
        score_governance_suppression_summary.get("suppression_verified_count") or 0
    )
    score_governance_replacement_ready = int(
        score_governance_suppression_summary.get(
            "replacement_or_canonical_ready_count"
        )
        or 0
    )
    score_governance_direct_suppressed = int(
        score_governance_suppression_summary.get("direct_signal_suppressed_count") or 0
    )
    score_governance_peer_suppressed = int(
        score_governance_suppression_summary.get("peer_context_suppressed_count") or 0
    )
    score_governance_review_required = int(
        score_governance_suppression_summary.get("requires_governance_review_count")
        or 0
    )
    score_governance_prod_writes = int(
        score_governance_suppression_summary.get("production_write_allowed_count") or 0
    )
    score_option_packets = int(
        score_option_universe_na_summary.get("option_universe_packet_count") or 0
    )
    score_option_no_current_inputs = int(
        score_option_universe_na_summary.get("no_current_a_share_input_count") or 0
    )
    score_option_universe_required = int(
        score_option_universe_na_summary.get("listed_option_universe_required_count")
        or 0
    )
    score_option_na_allowed = int(
        score_option_universe_na_summary.get(
            "na_or_unavailable_allowed_after_review_count"
        )
        or 0
    )
    score_option_known_allowed = int(
        score_option_universe_na_summary.get("known_value_allowed_now_count") or 0
    )
    score_option_contract_valid = int(
        score_option_universe_na_summary.get("verification_contract_valid_count") or 0
    )
    score_option_prod_writes = int(
        score_option_universe_na_summary.get("production_write_allowed_count") or 0
    )
    dry_run_clause = (
        f"Bridge dry-run validates {score_dry_run_ready}/{score_dry_run_checked} candidate-ready rows "
        f"into final-score-target realtime nodes with {score_dry_run_blocked} bridge blockers;"
        if score_candidate_dry_run_summary
        else ""
    )
    upsert_safety_clause = (
        f" Upsert-safety audit checks {score_upsert_checked}/{score_dry_run_checked} candidate-ready rows, "
        f"keeps {score_upsert_review_gated} review-gated/staging-only, "
        f"reports {score_upsert_blocked} blocked, and leaves {score_safe_upsert} safe for unreviewed runtime upsert;"
        if score_candidate_upsert_safety_summary
        else ""
    )
    staging_clause = (
        f" Staging-payload audit prepares {score_staging_payloads} deterministic review payloads, "
        f"leaves {score_staging_generator_required} rows requiring governed generator output, "
        f"and allows {score_staging_prod_writes} production writes;"
        if score_candidate_staging_summary
        else ""
    )
    value_contract_clause = (
        f" Value-contract audit validates {score_contract_valid} staging envelopes, "
        f"flags {score_contract_invalid} invalid, and bridge-validates {score_contract_bridge_concrete} concrete review payloads;"
        if score_candidate_value_contracts_summary
        else ""
    )
    spec_numeric_clause = (
        f" Spec numeric-validity confirms {score_numeric_current_final}/{score_numeric_relevant} "
        f"score-relevant fields currently reach numeric final-score nodes, "
        f"{score_numeric_not_final} score-relevant fields do not, "
        f"{score_numeric_review_ready} concrete packets are review-ready, "
        f"{score_numeric_unknown} packets remain Unknown, and "
        f"{score_numeric_approved_writes} runtime writes are approved;"
        if score_spec_numeric_validity_summary
        else ""
    )
    spec_score_conversion_clause = (
        f" Spec score-conversion-path audit checks {score_conversion_total} spec fields, "
        f"marks {score_conversion_relevant} score-relevant final targets, "
        f"finds {score_conversion_current_numeric} current numeric final-score fields, "
        f"{score_conversion_candidate_ready} candidate numeric score-path-ready fields, "
        f"{score_conversion_sample_ready} current-sample score-path-ready fields, "
        f"{score_conversion_ready} total numeric-and-score-path-ready fields, "
        f"{score_conversion_unresolved} unresolved score-relevant fields, "
        f"{score_conversion_no_formula} lacking a formula/normalizer, "
        f"{score_conversion_no_input} lacking current numeric input, "
        f"{score_conversion_formula_review} formula-policy review-required fields, "
        f"{score_conversion_governance_verified} governance-suppression verified fields, "
        f"{score_conversion_option_verified} option-universe/N/A verified fields, "
        f"{score_conversion_verified_exceptions} verified non-numeric exceptions, "
        f"{score_conversion_review_backed} review-decision-backed not-ready fields, "
        f"{score_conversion_unclassified} remaining unclassified conversion gaps, "
        f"cross-checks {score_conversion_formula_artifact} formula-policy packets, "
        f"{score_conversion_governance_artifact} verified governance suppressions, "
        f"and {score_conversion_option_artifact} valid option/N/A packets, "
        f"{score_conversion_no_weight} non-scoring/no-weight fields, "
        f"and {score_conversion_prod_writes} production writes;"
        if score_spec_score_conversion_summary
        else ""
    )
    score_conversion_remediation_clause = (
        f" Score-conversion remediation queue classifies {score_remediation_unresolved} unresolved fields, "
        f"finds {score_remediation_existing_inputs} with current Tushare/derived inputs and "
        f"{score_remediation_no_inputs} with no current input, splits them into "
        f"{score_remediation_formula_policy} formula-policy/peer-context rows, "
        f"{score_remediation_governance} governed-or-duplicate rows, and "
        f"{score_remediation_missing_source} listed-option-source/N/A rows, "
        f"with {score_remediation_safe_formula} safe formula-now rows and "
        f"{score_remediation_prod_writes} production writes;"
        if score_conversion_remediation_summary
        else ""
    )
    formula_policy_review_packet_clause = (
        f" Formula-policy review packets package {score_formula_policy_packets} rows, "
        f"confirm {score_formula_policy_current_inputs} have current inputs, "
        f"split into {score_formula_policy_valuation} valuation peer-context packets and "
        f"{score_formula_policy_business} business-semantics packets, "
        f"find {score_formula_policy_replacement_ready} replacement paths ready, "
        f"leave {score_formula_policy_direct_ready} direct formulas ready, "
        f"validate {score_formula_policy_contract_valid} policy contracts, "
        f"and allow {score_formula_policy_prod_writes} production writes;"
        if score_formula_policy_review_packets_summary
        else ""
    )
    governance_suppression_clause = (
        f" Governance-suppression verification packages {score_governance_suppression_packets} rows, "
        f"verifies {score_governance_suppression_verified} suppressions, "
        f"finds {score_governance_replacement_ready} replacement/canonical paths ready, "
        f"confirms {score_governance_direct_suppressed} direct signals suppressed, "
        f"{score_governance_peer_suppressed} peer-context suppressions, "
        f"{score_governance_review_required} suppression decisions still needing review, "
        f"and {score_governance_prod_writes} production writes;"
        if score_governance_suppression_summary
        else ""
    )
    option_universe_na_clause = (
        f" Option-universe/N/A verification packages {score_option_packets} rows, "
        f"confirms {score_option_no_current_inputs} have no current A-share option input, "
        f"requires listed-option universe evidence for {score_option_universe_required}, "
        f"allows reviewed N/A/Unavailable resolution for {score_option_na_allowed}, "
        f"allows {score_option_known_allowed} Known values now, "
        f"validates {score_option_contract_valid} verification contracts, "
        f"and allows {score_option_prod_writes} production writes;"
        if score_option_universe_na_summary
        else ""
    )
    generation_queue_clause = (
        f" Generation-queue audit packages {score_generation_tasks} generator tasks "
        f"with valid placeholder contracts={score_generation_queue_valid};"
        if score_candidate_generation_queue_summary
        else ""
    )
    l0_source_readiness_clause = (
        f" L0 source-readiness audit checks {score_l0_source_blocking_gaps} blocking gaps, "
        f"routes {score_l0_source_p2} P2 LLM/web extraction rows and {score_l0_source_p3} P3 manual review rows, "
        f"recommends {score_l0_source_event_route} event/news routes, {score_l0_source_local_route} local closed-loop routes, "
        f"and {score_l0_source_manual_route} manual-design routes, keeps {score_l0_source_direct_tushare_remaining} "
        f"direct structured Tushare gaps remaining, and finds {score_l0_source_runtime_rows} dependency dp_ids with runtime rows "
        f"and {score_l0_source_missing_runtime_rows} without runtime rows;"
        if score_l0_source_readiness_summary
        else ""
    )
    short_report_evidence_clause = (
        f" Short-report evidence scan checks {score_short_report_files_scanned} market HTML files with "
        f"{score_short_report_parse_errors} parse errors, finds {score_short_report_strict_docs} strict short-report documents, "
        f"{score_short_report_direct_docs} direct A-share short-report documents, {score_short_report_foreign_docs} "
        f"foreign/market-only short-report documents, {score_short_report_direct_ts_codes} direct A-share ts_codes, "
        f"and candidate evidence ready={score_short_report_candidate_ready};"
        if score_short_report_evidence_summary
        else ""
    )
    non_manual_readiness_clause = (
        f" Non-manual readiness audit checks {score_non_manual_tasks} local/event tasks, "
        f"validates {score_non_manual_placeholder_valid} placeholder contracts, "
        f"validates {score_non_manual_output_contract_valid} output contract shapes, "
        f"bridge-probes {score_non_manual_bridge_ready} final-score-ready payload shapes, "
        f"allows {score_non_manual_deterministic} deterministic Known drafts, "
        f"and allows {score_non_manual_prod_writes} production writes;"
        if score_non_manual_readiness_summary
        else ""
    )
    event_text_draft_clause = (
        f" Event-text policy pilot checks {score_event_text_tasks} tasks, "
        f"drafts {score_event_text_known} Known review packets, "
        f"leaves {score_event_text_unknown} Unknown, "
        f"validates {score_event_text_contract_valid} draft contracts, "
        f"flags {score_event_text_contract_invalid} invalid draft contracts, "
        f"bridge-validates {score_event_text_bridge} Known drafts, "
        f"leaves {score_event_text_safe_upsert} safe for unreviewed upsert, "
        f"and allows {score_event_text_prod_writes} production writes;"
        if score_event_text_draft_summary
        else ""
    )
    event_text_classification_input_clause = (
        f" Event-text classification input audit packages {score_event_text_input_packets} packets, "
        f"marks {score_event_text_input_ready} input-ready, "
        f"leaves {score_event_text_input_missing} missing headline input, "
        f"extracts {score_event_text_headlines} headline inputs across "
        f"{score_event_text_unique_headlines} unique titles, "
        f"finds {score_event_text_full_text} packets with full article text and "
        f"{score_event_text_title_only} title-level-only packets, "
        f"classifies {score_event_text_classified_known} Known packets, "
        f"and allows {score_event_text_input_prod_writes} production writes;"
        if score_event_text_classification_inputs_summary
        else ""
    )
    event_text_preclassification_screen_clause = (
        f" Event-text preclassification screen checks {score_event_text_pre_packets} packets, "
        f"screens {score_event_text_pre_screened}, "
        f"finds {score_event_text_pre_target_hits} target-keyword-hit packets, "
        f"{score_event_text_pre_transmission_hits} A-share transmission keyword-hit packets, "
        f"and {score_event_text_pre_target_and_transmission} packets with both, "
        f"allows {score_event_text_pre_direct_known} direct Known candidates, "
        f"keeps {score_event_text_pre_review_required} review-required, "
        f"and allows {score_event_text_pre_prod_writes} production writes;"
        if score_event_text_preclassification_screen_summary
        else ""
    )
    event_text_sufficiency_gate_clause = (
        f" Event-text sufficiency gate checks {score_event_text_suff_packets} packets, "
        f"finds {score_event_text_suff_target_headlines} target-headline packets, "
        f"{score_event_text_suff_broad_only} broad-market-only transmission packets, "
        f"{score_event_text_suff_same_any} same-headline target+any-transmission packets, "
        f"{score_event_text_suff_same_direct} same-headline target+direct-transmission packets, "
        f"{score_event_text_suff_classifier_ready} title-signal-sufficient classifier candidates, "
        f"allows {score_event_text_suff_known_allowed} Known candidates, "
        f"and allows {score_event_text_suff_prod_writes} production writes;"
        if score_event_text_sufficiency_gate_summary
        else ""
    )
    event_text_url_fetchability_clause = (
        f" Event-text URL/body audit fetches {score_event_text_url_fetch_success}/{score_event_text_url_unique} unique URLs, "
        f"extracts primary text from {score_event_text_url_primary_text}, "
        f"checks {score_event_text_body_packets} body packets, "
        f"finds {score_event_text_body_target_hits} body target-hit packets, "
        f"{score_event_text_body_direct_hits} body direct-transmission-hit packets, "
        f"{score_event_text_body_classifier_ready} body-signal-sufficient classifier candidates, "
        f"allows {score_event_text_body_known_allowed} Known candidates, "
        f"and allows {score_event_text_body_prod_writes} production writes;"
        if score_event_text_url_fetchability_summary
        else ""
    )
    event_text_unknown_options_clause = (
        f" Event-text Unknown source-options audit reviews {score_event_text_unknown_options} Unknown rows, "
        f"confirms {score_event_text_unknown_input_ready} have classification inputs ready, "
        f"{score_event_text_unknown_body_ready} have body text available, "
        f"finds {score_event_text_unknown_target_present} with target-event evidence, "
        f"{score_event_text_unknown_direct_present} with direct A-share transmission, "
        f"{score_event_text_unknown_broad_only} broad-market-only transmission rows, "
        f"{score_event_text_unknown_classifier_ready} classifier-ready review candidates, "
        f"marks {score_event_text_unknown_target_required} needing target-event evidence, "
        f"{score_event_text_unknown_direct_required} needing direct A-share transmission, "
        f"allows {score_event_text_unknown_auto_known} auto Known candidates, "
        f"and allows {score_event_text_unknown_prod_writes} production writes;"
        if score_event_text_unknown_source_options_summary
        else ""
    )
    event_text_market_doc_evidence_clause = (
        f" Event-text market-doc evidence scan checks {score_event_text_market_doc_checked} Unknown rows, "
        f"scans {score_event_text_market_doc_files} DOCKCASE market HTML files with "
        f"{score_event_text_market_doc_read_errors} read errors, "
        f"finds market-doc target evidence for {score_event_text_market_doc_target}, "
        f"direct transmission evidence for {score_event_text_market_doc_direct}, "
        f"target+direct same-document evidence for {score_event_text_market_doc_target_direct}, "
        f"same-sentence review candidates for {score_event_text_market_doc_same_sentence}, "
        f"leaves {score_event_text_market_doc_target_required} still needing target evidence, "
        f"{score_event_text_market_doc_direct_required} still needing direct-transmission links, "
        f"marks {score_event_text_market_doc_review_candidates} market-doc review candidates, "
        f"allows {score_event_text_market_doc_auto_known} auto Known candidates, "
        f"and allows {score_event_text_market_doc_prod_writes} production writes;"
        if score_event_text_market_doc_evidence_summary
        else ""
    )
    event_text_market_doc_review_packets_clause = (
        f" Event-text market-doc review packets package {score_event_text_market_doc_packet_count} packets, "
        f"mark {score_event_text_market_doc_packet_ready} market-doc review-ready, "
        f"leave {score_event_text_market_doc_packet_target_required} needing target-event evidence, "
        f"{score_event_text_market_doc_packet_direct_required} needing direct-transmission links, "
        f"retain {score_event_text_market_doc_packet_examples} candidate examples, "
        f"validate {score_event_text_market_doc_packet_contract_valid} packet contracts, "
        f"flag {score_event_text_market_doc_packet_contract_invalid} invalid packet contracts, "
        f"allow {score_event_text_market_doc_packet_auto_known} auto Known candidates, "
        f"and allow {score_event_text_market_doc_packet_prod_writes} production writes;"
        if score_event_text_market_doc_review_packets_summary
        else ""
    )
    local_structured_draft_clause = (
        f" Local structured policy pilot checks {score_local_structured_tasks} tasks, "
        f"drafts {score_local_structured_known} Known review packets, "
        f"leaves {score_local_structured_unknown} Unknown, "
        f"validates {score_local_structured_contract_valid} draft contracts, "
        f"flags {score_local_structured_contract_invalid} invalid draft contracts, "
        f"bridge-validates {score_local_structured_bridge} Known drafts, "
        f"leaves {score_local_structured_safe_upsert} safe for unreviewed upsert, "
        f"and allows {score_local_structured_prod_writes} production writes;"
        if score_local_structured_draft_summary
        else ""
    )
    local_structured_unknown_options_clause = (
        f" Local structured Unknown source-options audit reviews {score_local_structured_unknown_options} Unknown rows, "
        f"confirms {score_local_structured_unknown_runtime_ready} have runtime dependencies ready, "
        f"finds {score_local_structured_unknown_direct_ready} direct structured source-ready rows, "
        f"records {score_local_structured_unknown_overlay_hints} overlay/source hints, "
        f"marks {score_local_structured_unknown_new_mapping} needing new mapping or text extraction, "
        f"{score_local_structured_unknown_review_policy} needing reviewed policy, "
        f"{score_local_structured_unknown_partial_unlock} partial Known unlock candidate, "
        f"allows {score_local_structured_unknown_auto_known} auto Known candidates, "
        f"and allows {score_local_structured_unknown_prod_writes} production writes;"
        if score_local_structured_unknown_source_options_summary
        else ""
    )
    local_structured_source_candidates_clause = (
        f" Local structured source-candidates audit checks {score_local_structured_source_candidates_unknown} Unknown dp_ids against DOCKCASE/Tushare semantics, "
        f"confirms {score_local_structured_source_candidates_runtime_ready} have runtime dependencies ready, "
        f"finds {score_local_structured_source_candidates_direct_known} direct Known-ready rows, "
        f"marks {score_local_structured_source_candidates_review_dp} rows with review/source candidates, "
        f"records {score_local_structured_source_candidates_review_matches} review candidate matches, "
        f"{score_local_structured_source_candidates_supporting_matches} supporting candidate matches, "
        f"{score_local_structured_source_candidates_empty_matches} empty candidate matches, "
        f"{score_local_structured_source_candidates_no_source} rows with no direct catalog source, "
        f"excludes {score_local_structured_source_candidates_false_positive} false-positive field/path matches, "
        f"and allows {score_local_structured_source_candidates_prod_writes} production writes;"
        if score_local_structured_source_candidates_summary
        else ""
    )
    local_structured_source_review_packets_clause = (
        f" Local structured source-review packets package {score_local_structured_source_review_packets_total} Unknown rows, "
        f"mark {score_local_structured_source_review_packets_ready} lease/rent candidate ready for review, "
        f"{score_local_structured_source_review_packets_quantity} ASP packet needing quantity or price-index source, "
        f"{score_local_structured_source_review_packets_external} packets requiring external business sources, "
        f"{score_local_structured_source_review_packets_direct_known} direct Known-ready packets, "
        f"{score_local_structured_source_review_packets_formula_ready} formula-ready packets, "
        f"{score_local_structured_source_review_packets_candidate} packets with candidate columns, "
        f"{score_local_structured_source_review_packets_contract_valid} packet contracts valid, "
        f"{score_local_structured_source_review_packets_contract_invalid} packet contracts invalid, "
        f"and allow {score_local_structured_source_review_packets_prod_writes} production writes;"
        if score_local_structured_source_review_packets_summary
        else ""
    )
    local_structured_text_draft_clause = (
        f" Local structured-text policy pilot checks {score_local_structured_text_tasks} tasks, "
        f"drafts {score_local_structured_text_known} Known review packets, "
        f"leaves {score_local_structured_text_unknown} Unknown, "
        f"validates {score_local_structured_text_contract_valid} draft contracts, "
        f"flags {score_local_structured_text_contract_invalid} invalid draft contracts, "
        f"bridge-validates {score_local_structured_text_bridge} Known drafts, "
        f"leaves {score_local_structured_text_safe_upsert} safe for unreviewed upsert, "
        f"and allows {score_local_structured_text_prod_writes} production writes;"
        if score_local_structured_text_draft_summary
        else ""
    )
    local_structured_text_unknown_options_clause = (
        f" Local structured-text Unknown source-options audit reviews {score_local_structured_text_unknown_options} Unknown rows, "
        f"confirms {score_local_structured_text_unknown_runtime_ready} have runtime dependencies ready, "
        f"{score_local_structured_text_unknown_qa_ready} have QA recent dependencies ready, "
        f"finds {score_local_structured_text_unknown_classified} direct text-classification-ready rows, "
        f"records {score_local_structured_text_unknown_overlay_hints} overlay/source hints, "
        f"marks {score_local_structured_text_unknown_text_required} needing text classification, "
        f"allows {score_local_structured_text_unknown_auto_known} auto Known candidates, "
        f"and allows {score_local_structured_text_unknown_prod_writes} production writes;"
        if score_local_structured_text_unknown_source_options_summary
        else ""
    )
    single_dependency_draft_clause = (
        f" Local single-dependency policy pilot checks {score_single_dependency_tasks} tasks, "
        f"drafts {score_single_dependency_known} Known review packets, "
        f"leaves {score_single_dependency_unknown} Unknown, "
        f"validates {score_single_dependency_contract_valid} draft contracts, "
        f"flags {score_single_dependency_contract_invalid} invalid draft contracts, "
        f"bridge-validates {score_single_dependency_bridge} Known drafts, "
        f"leaves {score_single_dependency_safe_upsert} safe for unreviewed upsert, "
        f"and allows {score_single_dependency_prod_writes} production writes;"
        if score_single_dependency_draft_summary
        else ""
    )
    single_dependency_unknown_options_clause = (
        f" Local single-dependency Unknown source-options audit reviews {score_single_dependency_unknown_options} Unknown rows, "
        f"confirms {score_single_dependency_unknown_runtime_ready} have runtime dependencies ready, "
        f"finds {score_single_dependency_unknown_direct_ready} direct replacement-cycle source-ready rows, "
        f"records {score_single_dependency_unknown_overlay_hints} overlay/source hints, "
        f"finds {score_single_dependency_unknown_overlay_lifecycle_context} rows with overlay lifecycle context candidates, "
        f"counts {score_single_dependency_unknown_overlay_lifecycle_known} overlay lifecycle Known nodes, "
        f"{score_single_dependency_unknown_overlay_replacement_known} overlay replacement Known nodes, "
        f"and {score_single_dependency_unknown_overlay_replacement_unknown} overlay replacement Unknown nodes, "
        f"marks {score_single_dependency_unknown_lifecycle_required} needing lifecycle/replacement-cycle evidence, "
        f"{score_single_dependency_unknown_review_policy} needing reviewed policy, "
        f"creates {score_single_dependency_unknown_lifecycle_templates} lifecycle-policy review templates, "
        f"{score_single_dependency_unknown_lifecycle_templates_valid} lifecycle-policy review template contracts valid, "
        f"{score_single_dependency_unknown_lifecycle_templates_invalid} invalid, "
        f"{score_single_dependency_unknown_lifecycle_templates_blank} blank-pending, "
        f"{score_single_dependency_unknown_lifecycle_templates_input_ready} input-ready, "
        f"allows {score_single_dependency_unknown_auto_known} auto Known candidates, "
        f"finds {score_single_dependency_unknown_known_sufficient} Known-draft-sufficient rows, "
        f"{score_single_dependency_unknown_approval_ready} approval-ready rows, "
        f"and allows {score_single_dependency_unknown_prod_writes} production writes;"
        if score_single_dependency_unknown_source_options_summary
        else ""
    )
    manual_policy_draft_clause = (
        f" Manual-policy draft pilot checks {score_manual_policy_tasks} queued manual tasks, "
        f"drafts {score_manual_policy_known} Known review packets, "
        f"leaves {score_manual_policy_unknown} Unknown, "
        f"validates {score_manual_policy_contract_valid} draft contracts, "
        f"flags {score_manual_policy_contract_invalid} invalid draft contracts, "
        f"bridge-validates {score_manual_policy_bridge} Known drafts, "
        f"and allows {score_manual_policy_prod_writes} production writes;"
        if score_manual_policy_draft_summary
        else ""
    )
    manual_policy_unknown_options_clause = (
        f" Manual-policy Unknown source-options audit reviews {score_manual_policy_unknown_options} Unknown rows, "
        f"confirms {score_manual_policy_unknown_dependency_ready} have dependency packs ready, "
        f"finds {score_manual_policy_unknown_assumption_ready} direct reviewed-assumption-ready rows, "
        f"requires {score_manual_policy_unknown_required_assumptions} reviewed assumptions, "
        f"marks {score_manual_policy_unknown_assumption_review} needing assumption review, "
        f"{score_manual_policy_unknown_review_policy} needing reviewed policy, "
        f"allows {score_manual_policy_unknown_auto_known} auto Known candidates, "
        f"and allows {score_manual_policy_unknown_prod_writes} production writes;"
        if score_manual_policy_unknown_source_options_summary
        else ""
    )
    review_staging_manifest_clause = (
        f" Review-staging manifest merges {score_review_manifest_entries} review entries, "
        f"marks {score_review_manifest_concrete} concrete review-ready, "
        f"keeps {score_review_manifest_unknown} Unknown review-gated, "
        f"validates {score_review_manifest_contract_valid} contracts, "
        f"flags {score_review_manifest_contract_invalid} invalid contracts, "
        f"bridge-validates {score_review_manifest_bridge_ready} concrete entries, "
        f"leaves {score_review_manifest_safe_upsert} safe for unreviewed upsert, "
        f"allows {score_review_manifest_prod_writes} production writes, "
        f"and approves {score_review_manifest_approved_writes} runtime writes;"
        if score_review_staging_manifest_summary
        else ""
    )
    deterministic_runtime_approvals_clause = (
        f" Deterministic runtime approvals create {score_deterministic_approval_records} approval records, "
        f"approve {score_deterministic_approved_writes} deterministic runtime writes, "
        f"reject {score_deterministic_rejected} deterministic candidates, "
        f"leave {score_deterministic_not_reviewed} non-deterministic rows unapproved, "
        f"and allow {score_deterministic_prod_writes} production writes;"
        if score_deterministic_runtime_approvals_summary
        else ""
    )
    review_approval_gate_clause = (
        f" Review-approval gate requires approval for {score_review_approval_required} concrete packets, "
        f"finds {score_review_approval_records} approval records, "
        f"leaves {score_review_approval_missing} missing approvals, "
        f"rejects {score_review_approval_rejected} approvals, "
        f"approves {score_review_approval_approved_writes} runtime writes, "
        f"produces {score_review_approval_write_plan} write-plan entries, "
        f"keeps {score_review_approval_unknown} Unknown packets not approvable, "
        f"leaves {score_review_approval_safe_upsert} safe auto-upsert, "
        f"and allows {score_review_approval_prod_writes} production writes;"
        if score_review_approval_gate_summary
        else ""
    )
    completion_next_action_clause = (
        f" Completion next-action queue splits {score_next_action_total} actions into "
        f"{score_next_action_approval_ready} human approvals, "
        f"{score_next_action_runtime_ready} runtime-write-plan-ready packets, and "
        f"{score_next_action_unknown} Unknown resolutions "
        f"({score_next_action_event_text} event-text classifications, "
        f"{score_next_action_local_structured} local structured mappings, "
        f"{score_next_action_structured_text} structured-text extractions, "
        f"{score_next_action_single_dependency} single-dependency policies, "
        f"{score_next_action_manual} manual assumption reviews), "
        f"emits {score_next_action_templates} incomplete approval templates, "
        f"approves {score_next_action_approved_writes} runtime writes, "
        f"produces {score_next_action_write_plan} write-plan entries, "
        f"and allows {score_next_action_prod_writes} production writes;"
        if score_completion_next_actions_summary
        else ""
    )
    unknown_closure_matrix_clause = (
        f" Unknown closure matrix checks {score_unknown_closure_rows} review-gated Unknown rows, "
        f"assigns {score_unknown_closure_assigned} closure routes, "
        f"leaves {score_unknown_closure_missing} missing closure routes, "
        f"splits routes into {score_unknown_closure_event_text} event-text classifications, "
        f"{score_unknown_closure_local_structured} local structured mappings, "
        f"{score_unknown_closure_structured_text} structured-text extractions, "
        f"{score_unknown_closure_single_dependency} single-dependency policies, "
        f"and {score_unknown_closure_manual} manual assumption reviews, "
        f"finds {score_unknown_closure_source_candidates} rows with source candidates, "
        f"{score_unknown_closure_formula_ready} formula-ready rows, "
        f"{score_unknown_closure_auto_known} auto Known-ready rows, "
        f"{score_unknown_closure_approval_ready} approval-ready Unknown rows, "
        f"{score_unknown_closure_contract_valid} closure contracts valid, "
        f"{score_unknown_closure_contract_invalid} closure contracts invalid, "
        f"and allows {score_unknown_closure_prod_writes} production writes;"
        if score_unknown_closure_matrix_summary
        else ""
    )
    unknown_acquisition_backlog_clause = (
        f" Unknown acquisition backlog packages {score_unknown_acquisition_tasks} source-acquisition tasks, "
        f"split into {score_unknown_acquisition_event_doc} DOCKCASE market-doc searches, "
        f"{score_unknown_acquisition_local_formula} local formula-source tasks, "
        f"and {score_unknown_acquisition_external_business} external/text business-metric tasks, "
        f"with {score_unknown_acquisition_existing_evidence} tasks having existing candidate evidence, "
        f"{score_unknown_acquisition_overlay_hints} tasks having runtime overlay hints, "
        f"{score_unknown_acquisition_web_external} tasks requiring web/external or deeper source acquisition, "
        f"{score_unknown_acquisition_llm_allowed} tasks allowing LLM extraction/classification only, "
        f"{score_unknown_acquisition_formula_ready} formula-ready tasks, "
        f"{score_unknown_acquisition_auto_known} auto Known-ready tasks, "
        f"{score_unknown_acquisition_approval_ready} approval-ready tasks, "
        f"{score_unknown_acquisition_contract_valid} task contracts valid, "
        f"{score_unknown_acquisition_contract_invalid} task contracts invalid, "
        f"and {score_unknown_acquisition_prod_writes} production writes;"
        if score_unknown_acquisition_backlog_summary
        else ""
    )
    unknown_market_doc_acquisition_clause = (
        f" Unknown market-doc acquisition scan executes {score_unknown_market_doc_tasks} event-document tasks "
        f"across {score_unknown_market_doc_files} market HTML files with "
        f"{score_unknown_market_doc_read_errors} read errors, "
        f"finds {score_unknown_market_doc_review_rows} rows with review candidates, "
        f"{score_unknown_market_doc_new_entrant_windows} new-entrant window candidate documents, "
        f"{score_unknown_market_doc_new_entrant_review} new-entrant review candidate snippets, "
        f"{score_unknown_market_doc_substitute_same_sentence} substitute-tech same-sentence candidate documents, "
        f"{score_unknown_market_doc_substitute_clean} substitute-tech clean-risk review candidate snippets, "
        f"{score_unknown_market_doc_weak} weak candidates, "
        f"{score_unknown_market_doc_rejected} rejected candidates, "
        f"{score_unknown_market_doc_known_sufficient} Known-draft-sufficient rows, "
        f"and {score_unknown_market_doc_prod_writes} production writes;"
        if score_unknown_market_doc_acquisition_summary
        else ""
    )
    unknown_event_adjudication_clause = (
        f" Unknown event-evidence adjudication reviews {score_unknown_event_adjudication_rows} event Unknown rows, "
        f"adjudicates {score_unknown_event_adjudication_examples} retained candidates, "
        f"accepts {score_unknown_event_adjudication_accepted}, "
        f"rejects or marks ambiguous {score_unknown_event_adjudication_rejected}, "
        f"keeps {score_unknown_event_adjudication_remaining} rows Unknown, "
        f"finds {score_unknown_event_adjudication_known} Known-draft-sufficient rows, "
        f"validates {score_unknown_event_adjudication_contract_valid} adjudication contracts, "
        f"flags {score_unknown_event_adjudication_contract_invalid} invalid, "
        f"and allows {score_unknown_event_adjudication_prod_writes} production writes;"
        if score_unknown_event_evidence_adjudication_summary
        else ""
    )
    unknown_event_strict_source_gate_clause = (
        f" Unknown event strict-source gate rescans {score_unknown_event_strict_rows} event Unknown rows "
        f"across {score_unknown_event_strict_files} market HTML files with "
        f"{score_unknown_event_strict_read_errors} read errors, "
        f"finds {score_unknown_event_strict_candidates} strict candidates, "
        f"{score_unknown_event_strict_review_candidates} strict review candidates, "
        f"{score_unknown_event_strict_rejected} strict rejected candidates, "
        f"{score_unknown_event_strict_rows_with_review} rows with strict review candidates, "
        f"{score_unknown_event_strict_rows_without_source} rows without strict source candidates, "
        f"{score_unknown_event_strict_classifier_ready} classifier-ready rows, "
        f"{score_unknown_event_strict_known} Known-draft-sufficient rows, "
        f"{score_unknown_event_strict_approval_ready} approval-ready rows, "
        f"{score_unknown_event_strict_contract_valid} strict gate contracts valid, "
        f"{score_unknown_event_strict_contract_invalid} invalid, "
        f"and {score_unknown_event_strict_prod_writes} production writes;"
        if score_unknown_event_strict_source_gate_summary
        else ""
    )
    unknown_event_strict_review_packets_clause = (
        f" Unknown event strict-review packets triage {score_unknown_event_strict_review_packet_count} strict candidates "
        f"across {score_unknown_event_strict_review_rows} rows, "
        f"with {score_unknown_event_strict_low_confidence_sources} low-confidence community/forum source packets, "
        f"{score_unknown_event_strict_secondary_newswire} secondary-newswire packets, "
        f"{score_unknown_event_strict_primary_required} requiring primary-source confirmation, "
        f"{score_unknown_event_strict_manual_review} requiring manual review, "
        f"{score_unknown_event_strict_deterministic_rejected} deterministically rejected, "
        f"{score_unknown_event_strict_packet_classifier_ready} classifier-ready packets, "
        f"{score_unknown_event_strict_packet_known} Known-draft-sufficient packets, "
        f"{score_unknown_event_strict_packet_approval_ready} approval-ready packets, "
        f"{score_unknown_event_strict_packet_contract_valid} packet contracts valid, "
        f"{score_unknown_event_strict_packet_contract_invalid} invalid, "
        f"and {score_unknown_event_strict_packet_prod_writes} production writes;"
        if score_unknown_event_strict_review_packets_summary
        else ""
    )
    unknown_event_primary_source_confirmation_clause = (
        f" Unknown event primary-source confirmation scan checks {score_unknown_event_primary_confirmation_packets} low-confidence packets "
        f"across {score_unknown_event_primary_confirmation_files} local market HTML files with "
        f"{score_unknown_event_primary_confirmation_read_errors} read errors, "
        f"finds {score_unknown_event_primary_local_candidates} local candidates, "
        f"{score_unknown_event_primary_local_confirmations} local high-quality confirmation candidates, "
        f"{score_unknown_event_primary_supporting_only} supporting-context-only candidates, "
        f"{score_unknown_event_primary_rows_with_confirmation} rows with local confirmation candidates, "
        f"{score_unknown_event_primary_rows_supporting_only} rows with supporting context only, "
        f"{score_unknown_event_primary_rows_without_confirmation} rows without local confirmation candidates, "
        f"{score_unknown_event_primary_classifier_ready} classifier-ready rows, "
        f"{score_unknown_event_primary_known} Known-draft-sufficient rows, "
        f"{score_unknown_event_primary_approval_ready} approval-ready rows, "
        f"{score_unknown_event_primary_contract_valid} confirmation contracts valid, "
        f"{score_unknown_event_primary_contract_invalid} invalid, "
        f"and {score_unknown_event_primary_prod_writes} production writes;"
        if score_unknown_event_primary_source_confirmation_summary
        else ""
    )
    unknown_event_external_source_confirmation_clause = (
        f" Unknown event external-source confirmation packages {score_unknown_event_external_confirmation_packets} packets, "
        f"{score_unknown_event_external_source_cards} source cards, "
        f"{score_unknown_event_external_confirmation_candidates} external confirmation candidates, "
        f"{score_unknown_event_external_supporting_context} supporting-context cards, "
        f"{score_unknown_event_external_rows_with_confirmation} rows with external confirmation candidates, "
        f"{score_unknown_event_external_rows_supporting_only} rows with supporting context only, "
        f"{score_unknown_event_external_classifier_input_candidates} classifier input candidates, "
        f"{score_unknown_event_external_classifier_input_contract_valid} classifier input candidate contracts valid, "
        f"{score_unknown_event_external_classifier_input_contract_invalid} invalid, "
        f"{score_unknown_event_external_classifier_input_ready} classifier input candidates ready, "
        f"{score_unknown_event_external_classifier_input_review_required} classifier input candidates requiring review, "
        f"{score_unknown_event_external_classifier_input_primary_source} classifier input candidates with primary sources covered, "
        f"{score_unknown_event_external_classifier_input_labels} classifier input required labels, "
        f"{score_unknown_event_external_classifier_input_guardrails} classifier input guardrails, "
        f"{score_unknown_event_external_classifier_review_templates} classifier review templates, "
        f"{score_unknown_event_external_classifier_review_template_contract_valid} classifier review template contracts valid, "
        f"{score_unknown_event_external_classifier_review_template_contract_invalid} invalid, "
        f"{score_unknown_event_external_classifier_review_template_blank_pending} classifier review templates blank-pending, "
        f"{score_unknown_event_external_classifier_review_template_input_ready} classifier review template inputs ready, "
        f"{score_unknown_event_external_classifier_ready} classifier-ready rows, "
        f"{score_unknown_event_external_known} Known-draft-sufficient rows, "
        f"{score_unknown_event_external_approval_ready} approval-ready rows, "
        f"{score_unknown_event_external_contract_valid} contracts valid, "
        f"{score_unknown_event_external_contract_invalid} invalid, "
        f"and {score_unknown_event_external_prod_writes} production writes;"
        if score_unknown_event_external_source_confirmation_summary
        else ""
    )
    unknown_local_formula_acquisition_clause = (
        f" Unknown local formula acquisition scan executes {score_unknown_local_formula_tasks} formula-source tasks, "
        f"finds {score_unknown_local_formula_runtime_ready} runtime dependency-ready tasks, "
        f"checks {score_unknown_local_formula_csv_checked} sample CSV files with "
        f"{score_unknown_local_formula_csv_existing} existing and "
        f"{score_unknown_local_formula_csv_errors} read errors, "
        f"splits formula needs into {score_unknown_local_formula_group_count} input groups with "
        f"{score_unknown_local_formula_group_ready} ready groups, "
        f"finds {score_unknown_local_formula_candidate_numerator} rows with candidate numerators, "
        f"{score_unknown_local_formula_direct_denominator} rows with direct denominators, "
        f"{score_unknown_local_formula_quantity_or_price} rows with quantity or price-index inputs, "
        f"{score_unknown_local_formula_policy} rows with formula policy, "
        f"{score_unknown_local_formula_ready} formula-ready rows, "
        f"{score_unknown_local_formula_known_draft} Known-draft-ready rows, "
        f"{score_unknown_local_formula_contract_valid} local formula packet contracts valid, "
        f"{score_unknown_local_formula_contract_invalid} invalid, "
        f"and {score_unknown_local_formula_prod_writes} production writes;"
        if score_unknown_local_formula_acquisition_summary
        else ""
    )
    unknown_local_formula_review_packets_clause = (
        f" Unknown local formula review packets package {score_unknown_local_formula_review_packets} formula rows, "
        f"find {score_unknown_local_formula_review_candidate_numerator} rows with candidate numerators, "
        f"{score_unknown_local_formula_review_direct_denominator} rows with direct denominators, "
        f"{score_unknown_local_formula_review_denominator_candidate} rows with denominator candidates, "
        f"{score_unknown_local_formula_review_formula_shape} rows with candidate formula shapes, "
        f"{score_unknown_local_formula_review_policy_draft} rows with formula-policy draft candidates, "
        f"{score_unknown_local_formula_review_policy_template} formula-policy review templates, "
        f"{score_unknown_local_formula_review_policy_template_valid} formula-policy review template contracts valid, "
        f"{score_unknown_local_formula_review_policy_template_blank} formula-policy review templates blank-pending, "
        f"{score_unknown_local_formula_review_price_context} rows with price-index context candidates, "
        f"{score_unknown_local_formula_review_price_context_shape} rows with candidate price-context shapes, "
        f"{score_unknown_local_formula_review_price_template} price-context review templates, "
        f"{score_unknown_local_formula_review_price_template_valid} price-context review template contracts valid, "
        f"{score_unknown_local_formula_review_price_template_blank} price-context review templates blank-pending, "
        f"{score_unknown_local_formula_review_quantity_or_price} rows with quantity or price-index inputs, "
        f"{score_unknown_local_formula_review_policy} rows with formula policy, "
        f"{score_unknown_local_formula_review_inputs_ready} formula-input-ready rows, "
        f"{score_unknown_local_formula_review_probe_available} formula probes available, "
        f"{score_unknown_local_formula_review_bridge_ready} bridge-probe-ready packets, "
        f"{score_unknown_local_formula_review_selected_json} selected value JSONs, "
        f"{score_unknown_local_formula_review_known} Known-draft-sufficient packets, "
        f"{score_unknown_local_formula_review_approval_ready} approval-ready packets, "
        f"{score_unknown_local_formula_review_contract_valid} review contracts valid, "
        f"{score_unknown_local_formula_review_contract_invalid} invalid, "
        f"and {score_unknown_local_formula_review_prod_writes} production writes;"
        if score_unknown_local_formula_review_packets_summary
        else ""
    )
    local_formula_source_capability_clause = (
        f" Local formula source-capability audit scans {score_local_formula_source_capability_rows} formula rows with "
        f"{score_local_formula_source_capability_checks} source checks, "
        f"finds {score_local_formula_source_capability_candidates} checks with source candidates, "
        f"{score_local_formula_source_header_empty} header-available-but-sample-empty checks, "
        f"{score_local_formula_source_context} context/proxy checks, "
        f"{score_local_formula_source_policy_required} review-policy-required checks, "
        f"{score_local_formula_source_external_required} external/text-required checks, "
        f"{score_local_formula_source_resolved} formula blockers resolved by current sources, "
        f"{score_local_formula_source_ready} rows formula-ready after source scan, "
        f"{score_local_formula_source_probe} formula probes available, "
        f"{score_local_formula_source_known} Known-draft-sufficient rows, "
        f"{score_local_formula_source_approval_ready} approval-ready rows, "
        f"and {score_local_formula_source_prod_writes} production writes;"
        if score_local_formula_source_capability_summary
        else ""
    )
    unknown_external_business_metric_acquisition_clause = (
        f" Unknown external business metric acquisition scan executes {score_unknown_external_business_tasks} tasks, "
        f"finds {score_unknown_external_business_runtime_ready} runtime dependency-ready tasks, "
        f"{score_unknown_external_business_overlay_hints} overlay hints, "
        f"{score_unknown_external_business_group_count} business metric groups with "
        f"{score_unknown_external_business_group_ready} ready groups, "
        f"{score_unknown_external_business_runtime_context} rows with supporting runtime context, "
        f"{score_unknown_external_business_overlay_context_rows} rows with overlay business context candidates, "
        f"{score_unknown_external_business_overlay_context_known} overlay business context Known nodes "
        f"({score_unknown_external_business_overlay_frequency_known} frequency-context, "
        f"{score_unknown_external_business_overlay_penetration_known} penetration-context), "
        f"{score_unknown_external_business_overlay_frequency_direct_known}/"
        f"{score_unknown_external_business_overlay_frequency_direct_unknown} frequency direct Known/Unknown nodes, "
        f"{score_unknown_external_business_overlay_penetration_direct_known}/"
        f"{score_unknown_external_business_overlay_penetration_direct_unknown} penetration direct Known/Unknown nodes, "
        f"{score_unknown_external_business_direct_source} rows with direct business metric source, "
        f"{score_unknown_external_business_required_external} rows requiring external/text source, "
        f"{score_unknown_external_business_false_positives} false positives, "
        f"{score_unknown_external_business_metric_ready} metric-ready rows, "
        f"{score_unknown_external_business_known_draft} Known-draft-ready rows, "
        f"{score_unknown_external_business_contract_valid} contracts valid, "
        f"{score_unknown_external_business_contract_invalid} invalid, "
        f"and {score_unknown_external_business_prod_writes} production writes;"
        if score_unknown_external_business_metric_acquisition_summary
        else ""
    )
    unknown_external_business_metric_market_doc_clause = (
        f" Unknown external business metric market-doc scan executes {score_unknown_external_business_market_doc_tasks} tasks "
        f"across {score_unknown_external_business_market_doc_files} local market HTML files with "
        f"{score_unknown_external_business_market_doc_read_errors} read errors, "
        f"finds {score_unknown_external_business_market_doc_rows} rows with review candidates, "
        f"{score_unknown_external_business_market_doc_documents} candidate documents, "
        f"{score_unknown_external_business_market_doc_review} review candidates, "
        f"{score_unknown_external_business_market_doc_numeric} numeric review candidates, "
        f"{score_unknown_external_business_market_doc_textual} textual review candidates, "
        f"{score_unknown_external_business_market_doc_weak} weak candidates, "
        f"{score_unknown_external_business_market_doc_rejected} rejected candidates, "
        f"{score_unknown_external_business_market_doc_known} Known-draft-sufficient rows, "
        f"{score_unknown_external_business_market_doc_metric_ready} metric-ready rows, "
        f"{score_unknown_external_business_market_doc_contract_valid} contracts valid, "
        f"{score_unknown_external_business_market_doc_contract_invalid} invalid, "
        f"and {score_unknown_external_business_market_doc_prod_writes} production writes;"
        if score_unknown_external_business_metric_market_doc_summary
        else ""
    )
    unknown_external_business_metric_review_packets_clause = (
        f" Unknown external business metric review-packet bundle converts {score_unknown_external_business_review_packets} "
        f"of {score_unknown_external_business_review_expected} retained review candidates into packets across "
        f"{score_unknown_external_business_review_rows} rows, with "
        f"{score_unknown_external_business_review_numeric} numeric packets, "
        f"{score_unknown_external_business_review_textual} textual packets, "
        f"{score_unknown_external_business_review_scope} scope candidates, "
        f"{score_unknown_external_business_review_denominator} denominator candidates, "
        f"{score_unknown_external_business_review_period} period candidates, "
        f"{score_unknown_external_business_review_unit} unit candidates, "
        f"{score_unknown_external_business_review_metric_ready} metric-ready packets, "
        f"{score_unknown_external_business_review_known} Known-draft-sufficient packets, "
        f"{score_unknown_external_business_review_contract_valid} packet contracts valid, "
        f"{score_unknown_external_business_review_contract_invalid} invalid, "
        f"and {score_unknown_external_business_review_prod_writes} production writes;"
        if score_unknown_external_business_metric_review_packets_summary
        else ""
    )
    unknown_external_business_metric_readiness_queue_clause = (
        f" Unknown external business metric readiness queue prioritizes {score_unknown_external_business_readiness_packets} packets, "
        f"with {score_unknown_external_business_readiness_p0} P0 formula-policy-only candidates, "
        f"{score_unknown_external_business_readiness_p1} P1 period/unit-required candidates, "
        f"{score_unknown_external_business_readiness_p2} P2 denominator-required candidates, "
        f"{score_unknown_external_business_readiness_missing_denominator} missing denominator/normalizer, "
        f"{score_unknown_external_business_readiness_missing_period} missing period, "
        f"{score_unknown_external_business_readiness_missing_unit} missing unit, "
        f"{score_unknown_external_business_readiness_missing_bounds} missing bounds, "
        f"{score_unknown_external_business_readiness_missing_formula} missing formula policy, "
        f"{score_unknown_external_business_readiness_metric_ready} metric-ready packets, "
        f"{score_unknown_external_business_readiness_known} Known-draft-sufficient packets, "
        f"and {score_unknown_external_business_readiness_prod_writes} production writes;"
        if score_unknown_external_business_metric_readiness_queue_summary
        else ""
    )
    unknown_external_business_metric_policy_drafts_clause = (
        f" Unknown external business metric policy-draft bundle converts {score_unknown_external_business_policy_p0} P0 packets into "
        f"{score_unknown_external_business_policy_drafts} review-only policy drafts, "
        f"keeps {score_unknown_external_business_policy_review_required} formula-policy reviews required, "
        f"emits {score_unknown_external_business_policy_value_templates} value JSON templates, "
        f"creates {score_unknown_external_business_policy_review_templates} policy review templates, "
        f"{score_unknown_external_business_policy_review_templates_valid} policy review template contracts valid, "
        f"{score_unknown_external_business_policy_review_templates_invalid} invalid, "
        f"{score_unknown_external_business_policy_review_templates_blank} blank-pending, "
        f"{score_unknown_external_business_policy_review_templates_input_ready} input-ready, "
        f"{score_unknown_external_business_policy_metric_ready} metric-ready drafts, "
        f"{score_unknown_external_business_policy_known} Known-draft-sufficient rows, "
        f"{score_unknown_external_business_policy_contract_valid} policy contracts valid, "
        f"{score_unknown_external_business_policy_contract_invalid} invalid, "
        f"and {score_unknown_external_business_policy_prod_writes} production writes;"
        if score_unknown_external_business_metric_policy_drafts_summary
        else ""
    )
    unknown_external_business_metric_value_candidates_clause = (
        f" Unknown external business metric value-candidate adjudication checks {score_unknown_external_business_value_rows} P0 policy drafts, "
        f"finds {score_unknown_external_business_value_rows_with_tokens} rows with candidate numeric tokens, "
        f"{score_unknown_external_business_value_tokens} value-candidate tokens, "
        f"{score_unknown_external_business_value_rejected_tokens} rejected numeric tokens, "
        f"{score_unknown_external_business_value_shortlist} shortlist rows requiring review, "
        f"{score_unknown_external_business_value_scope_rejected} scope-rejected rows, "
        f"{score_unknown_external_business_value_no_numeric} rows with no scoreable numeric candidate, "
        f"{score_unknown_external_business_value_metric_ready} metric-ready rows, "
        f"{score_unknown_external_business_value_known} Known-draft-sufficient rows, "
        f"{score_unknown_external_business_value_contract_valid} value-candidate contracts valid, "
        f"{score_unknown_external_business_value_contract_invalid} invalid, "
        f"and {score_unknown_external_business_value_prod_writes} production writes;"
        if score_unknown_external_business_metric_value_candidates_summary
        else ""
    )
    unknown_external_business_metric_value_review_packets_clause = (
        f" Unknown external business metric value-review packets convert {score_unknown_external_business_value_shortlist} shortlist rows into "
        f"{score_unknown_external_business_value_review_packets} review packets with "
        f"{score_unknown_external_business_value_review_options} candidate value options, "
        f"{score_unknown_external_business_value_review_bridge_ready} bridge-probe-ready options, "
        f"{score_unknown_external_business_value_review_selected_raw} selected raw values, "
        f"{score_unknown_external_business_value_review_selected_json} selected value JSONs, "
        f"{score_unknown_external_business_value_review_metric_ready} metric-ready packets, "
        f"{score_unknown_external_business_value_review_known} Known-draft-sufficient packets, "
        f"{score_unknown_external_business_value_review_approval_ready} approval-ready packets, "
        f"{score_unknown_external_business_value_review_contract_valid} value-review contracts valid, "
        f"{score_unknown_external_business_value_review_contract_invalid} invalid, "
        f"and {score_unknown_external_business_value_review_prod_writes} production writes;"
        if score_unknown_external_business_metric_value_review_packets_summary
        else ""
    )
    unknown_business_metric_value_selection_gate_clause = (
        f" Unknown business-metric value-selection gate checks {score_unknown_business_value_selection_rows} rows, "
        f"{score_unknown_business_value_selection_packets} value-review packets, "
        f"{score_unknown_business_value_selection_options} candidate value options, "
        f"{score_unknown_business_value_selection_bridge_ready} bridge-probe-ready options, "
        f"marks {score_unknown_business_value_selection_review_required} value-selection-review rows, "
        f"{score_unknown_business_value_selection_policy_draft_status_ready} value-policy-draft-ready rows, "
        f"{score_unknown_business_value_selection_proposed_json} proposed value JSONs, "
        f"{score_unknown_business_value_selection_source_missing} rows still source-metric-missing, "
        f"{score_unknown_business_value_selection_auto} auto-selectable values, "
        f"{score_unknown_business_value_selection_selected_json} selected value JSONs, "
        f"{score_unknown_business_value_selection_known} Known-draft-sufficient rows, "
        f"{score_unknown_business_value_selection_approval_ready} approval-ready rows, "
        f"{score_unknown_business_value_selection_contract_valid} selection contracts valid, "
        f"{score_unknown_business_value_selection_contract_invalid} invalid, "
        f"and {score_unknown_business_value_selection_prod_writes} production writes;"
        if score_unknown_business_metric_value_selection_gate_summary
        else ""
    )
    unknown_penetration_value_priority_clause = (
        f" Unknown penetration value-priority audit ranks {score_unknown_penetration_value_priority_packets} review packets, "
        f"{score_unknown_penetration_value_priority_options} candidate value options, "
        f"{score_unknown_penetration_value_priority_bridge_ready} bridge-ready options, "
        f"{score_unknown_penetration_value_priority_p1} P1 preferred-source review, "
        f"{score_unknown_penetration_value_priority_p2} P2 industry-scope review, "
        f"{score_unknown_penetration_value_priority_p3_forecast} P3 forecast/assumption reviews, "
        f"{score_unknown_penetration_value_priority_p3_low_confidence} P3 low-confidence community reviews, "
        f"{score_unknown_penetration_value_priority_selected_json} selected value JSONs, "
        f"{score_unknown_penetration_value_priority_known} Known-draft-sufficient rows, "
        f"{score_unknown_penetration_value_priority_approval_ready} approval-ready rows, "
        f"and {score_unknown_penetration_value_priority_prod_writes} production writes;"
        if score_unknown_penetration_value_priority_summary
        else ""
    )
    unknown_penetration_p1_source_confirmation_clause = (
        f" Unknown penetration P1 source-confirmation audit checks {score_unknown_penetration_p1_source_candidates} P1 candidates, "
        f"finds {score_unknown_penetration_p1_source_found} source files, "
        f"confirms {score_unknown_penetration_p1_raw_value_confirmed} raw-value tokens, "
        f"confirms {score_unknown_penetration_p1_scope_confirmed} source scopes, "
        f"selects {score_unknown_penetration_p1_selected_json} value JSONs, "
        f"keeps {score_unknown_penetration_p1_known} Known-draft-sufficient rows, "
        f"{score_unknown_penetration_p1_approval_ready} approval-ready rows, "
        f"and {score_unknown_penetration_p1_prod_writes} production writes;"
        if score_unknown_penetration_p1_source_confirmation_summary
        else ""
    )
    unknown_penetration_value_policy_draft_clause = (
        f" Unknown penetration value-policy draft audit packages {score_unknown_penetration_value_policy_draft_rows} draft rows, "
        f"confirms {score_unknown_penetration_value_policy_draft_scope_confirmed} source scopes, "
        f"proposes {score_unknown_penetration_value_policy_draft_proposed_json} value JSONs, "
        f"validates {score_unknown_penetration_value_policy_draft_valid} draft contracts, "
        f"flags {score_unknown_penetration_value_policy_draft_invalid} invalid draft contracts, "
        f"bridge-validates {score_unknown_penetration_value_policy_draft_bridge_ready} final-score targets, "
        f"selects {score_unknown_penetration_value_policy_draft_selected_json} value JSONs, "
        f"keeps {score_unknown_penetration_value_policy_draft_known} Known-draft-sufficient rows, "
        f"{score_unknown_penetration_value_policy_draft_approval_ready} approval-ready rows, "
        f"and {score_unknown_penetration_value_policy_draft_prod_writes} production writes;"
        if score_unknown_penetration_value_policy_draft_summary
        else ""
    )
    unknown_penetration_value_confirmation_packets_clause = (
        f" Unknown penetration value-confirmation packets package {score_unknown_penetration_value_confirmation_packets_count} review-required packets, "
        f"include {score_unknown_penetration_value_confirmation_templates} blank confirmation templates, "
        f"validate {score_unknown_penetration_value_confirmation_template_valid} template contracts and "
        f"{score_unknown_penetration_value_confirmation_packet_valid} packet contracts, "
        f"keep {score_unknown_penetration_value_confirmation_known} Known-draft-sufficient rows, "
        f"{score_unknown_penetration_value_confirmation_approval_ready} approval-ready rows, "
        f"and {score_unknown_penetration_value_confirmation_prod_writes} production writes;"
        if score_unknown_penetration_value_confirmation_packets_summary
        else ""
    )
    unknown_penetration_value_confirmation_templates_clause = (
        f" Unknown penetration value-confirmation template bundle extracts {score_unknown_penetration_value_confirmation_template_bundle_count} templates from packets, "
        f"keeps {score_unknown_penetration_value_confirmation_template_bundle_blank} blank/pending templates, "
        f"validates {score_unknown_penetration_value_confirmation_template_bundle_valid} blank template contracts, "
        f"sees {score_unknown_penetration_value_confirmation_template_bundle_confirmed} confirmed templates, "
        f"keeps {score_unknown_penetration_value_confirmation_template_bundle_known} Known-draft-sufficient rows, "
        f"{score_unknown_penetration_value_confirmation_template_bundle_approval_ready} approval-ready rows, "
        f"{score_unknown_penetration_value_confirmation_template_bundle_runtime_writes} runtime writes, "
        f"and {score_unknown_penetration_value_confirmation_template_bundle_prod_writes} production writes;"
        if score_unknown_penetration_value_confirmation_templates_summary
        else ""
    )
    unknown_penetration_value_confirmation_gate_clause = (
        f" Unknown penetration value-confirmation gate checks {score_unknown_penetration_value_confirmation_gate_packets} packets, "
        f"sees {score_unknown_penetration_value_confirmation_gate_records} confirmation records, "
        f"marks {score_unknown_penetration_value_confirmation_gate_missing} confirmations missing, "
        f"{score_unknown_penetration_value_confirmation_gate_confirmed} value policies confirmed, "
        f"{score_unknown_penetration_value_confirmation_gate_known_candidates} Known-draft candidates, "
        f"and {score_unknown_penetration_value_confirmation_gate_prod_writes} production writes;"
        if score_unknown_penetration_value_confirmation_gate_summary
        else ""
    )
    unknown_penetration_confirmed_known_drafts_clause = (
        f" Unknown penetration confirmed Known-draft emitter checks {score_unknown_penetration_confirmed_known_draft_gate_rows} confirmation-gate rows, "
        f"sees {score_unknown_penetration_confirmed_known_draft_candidates} confirmed value-policy candidates, "
        f"emits {score_unknown_penetration_confirmed_known_draft_emitted} Known drafts, "
        f"blocks {score_unknown_penetration_confirmed_known_draft_blocked} rows, "
        f"marks {score_unknown_penetration_confirmed_known_draft_staging_ready} ready for review staging, "
        f"and allows {score_unknown_penetration_confirmed_known_draft_prod_writes} production writes;"
        if score_unknown_penetration_confirmed_known_drafts_summary
        else ""
    )
    approval_review_packets_clause = (
        f" Approval-review packet bundle extracts {score_approval_packet_count} concrete packets "
        f"({score_approval_packet_known} Known and "
        f"{score_approval_packet_not_applicable} NotApplicable), "
        f"confirms {score_approval_packet_bridge_ready} final-score-target-ready packets, "
        f"keeps {score_approval_packet_missing} missing approvals, "
        f"includes {score_approval_packet_templates} incomplete approval templates, "
        f"validates {score_approval_packet_template_valid} approval template contracts, "
        f"flags {score_approval_packet_template_invalid} invalid approval templates, "
        f"approves {score_approval_packet_approved_writes} runtime writes, "
        f"produces {score_approval_packet_write_plan} write-plan entries, "
        f"and allows {score_approval_packet_prod_writes} production writes;"
        if score_approval_review_packets_summary
        else ""
    )
    approval_packet_risk_review_clause = (
        f" Approval-packet risk review checks {score_approval_risk_packets} packets, "
        f"routes {score_approval_risk_bulk_structured} bulk structured candidates, "
        f"{score_approval_risk_borderline} borderline structured-text candidate, "
        f"{score_approval_risk_individual} individual-review packets "
        f"({score_approval_risk_event} event evidence, {score_approval_risk_structured} structured proxy, "
        f"and {score_approval_risk_policy} policy reviews), finds {score_approval_risk_contract_fix} contract-fix blockers, "
        f"allows {score_approval_risk_auto} auto approvals, and allows {score_approval_risk_prod_writes} production writes;"
        if score_approval_packet_risk_review_summary
        else ""
    )
    bulk_review_approval_candidates_clause = (
        f" Bulk-review approval-candidate audit checks {score_bulk_review_candidate_count} candidates, "
        f"keeps {score_bulk_review_strict} strict bulk candidates and {score_bulk_review_borderline} borderline sample-check candidates, "
        f"emits {score_bulk_review_drafts} approval drafts, validates {score_bulk_review_draft_valid} draft contracts, "
        f"flags {score_bulk_review_draft_invalid} invalid draft contracts, allows {score_bulk_review_auto} auto approvals, "
        f"and allows {score_bulk_review_prod_writes} production writes;"
        if score_bulk_review_approval_candidates_summary
        else ""
    )
    bulk_review_source_samples_clause = (
        f" Bulk-review source-sample audit checks {score_bulk_source_sample_candidates} reviewer candidates, "
        f"matches {score_bulk_source_sample_payload_match} source payloads to candidates, "
        f"has {score_bulk_source_sample_evidence_complete} candidates with complete evidence refs, "
        f"marks {score_bulk_source_sample_borderline_ready} borderline sample-evidence rows ready, "
        f"completes {score_bulk_source_sample_complete} reviewer packets, "
        f"and allows {score_bulk_source_sample_prod_writes} production writes;"
        if score_bulk_review_source_samples_summary
        else ""
    )
    event_approval_source_samples_clause = (
        f" Event-approval source-sample audit checks {score_event_approval_source_sample_packets} event-text packets "
        f"({score_event_approval_individual_reviews} individual event-evidence reviews required), "
        f"matches {score_event_approval_payload_match} source payloads to candidates, "
        f"finds {score_event_approval_market_packet_found} market-doc review packets, "
        f"confirms {score_event_approval_market_refs_complete} market-doc review refs, "
        f"verifies {score_event_approval_dockcase_readable}/{score_event_approval_dockcase_refs} DOCKCASE docs readable, "
        f"marks {score_event_approval_keyword_ready} rows keyword-evidence-ready, "
        f"validates {score_event_approval_template_valid}/{score_event_approval_template_count} event-evidence review templates, "
        f"keeps {score_event_approval_template_blank} templates blank/pending, "
        f"completes {score_event_approval_complete} reviewer packets, "
        f"and allows {score_event_approval_prod_writes} production writes;"
        if score_event_approval_source_samples_summary
        else ""
    )
    individual_review_source_samples_clause = (
        f" Individual-review source-sample audit checks {score_individual_source_sample_packets} packets "
        f"({score_individual_structured_reviews} structured proxy reviews and "
        f"{score_individual_policy_reviews} policy reviews), "
        f"covers {score_individual_manual_policy_reviews} manual-policy packets, "
        f"{score_individual_event_policy_reviews} event policy packets, and "
        f"{score_individual_structured_proxy_reviews} structured proxy packets, "
        f"matches {score_individual_payload_match} source payloads to candidates, "
        f"has {score_individual_evidence_refs_complete} complete evidence-ref sets, "
        f"marks {score_individual_text_sample_ready} text sample-evidence rows ready, "
        f"confirms {score_individual_event_source_complete} event source-sample packets complete, "
        f"validates {score_individual_template_valid}/{score_individual_template_count} individual review templates, "
        f"keeps {score_individual_template_blank} templates blank/pending, "
        f"completes {score_individual_complete} reviewer packets, "
        f"and allows {score_individual_prod_writes} production writes;"
        if score_individual_review_source_samples_summary
        else ""
    )
    approval_source_sample_coverage_clause = (
        f" Approval source-sample coverage gate checks {score_approval_source_coverage_packets} approval source-sample coverage packets, "
        f"supports {score_approval_source_coverage_supported} approval source-sample supported routes, "
        f"finds {score_approval_source_coverage_found} approval source-sample source samples found, "
        f"completes {score_approval_source_coverage_complete} approval source-sample reviewer packets complete, "
        f"matches {score_approval_source_coverage_payload_match} approval source-sample payload matches, "
        f"validates {score_approval_source_coverage_template_valid} approval source-sample review templates valid, "
        f"validates {score_approval_source_coverage_approval_template_valid} approval source-sample blank approval templates valid, "
        f"marks {score_approval_source_coverage_input_ready} approval source-sample approval inputs ready, "
        f"keeps {score_approval_source_coverage_input_not_ready} approval source-sample approval inputs not ready, "
        f"finds {score_approval_source_coverage_unsupported} approval source-sample unsupported risk classes, "
        f"and allows {score_approval_source_coverage_prod_writes} approval source-sample production writes;"
        if score_approval_source_sample_coverage_summary
        else ""
    )
    approval_target_scope_readiness_clause = (
        f" Approval target-scope readiness audit checks {score_approval_target_scope_packets} approval packets, "
        f"confirms {score_approval_target_scope_final_ready} final-score-target-ready packets and "
        f"{score_approval_target_scope_samples_complete} complete source-sample reviewer packets, "
        f"sees {score_approval_target_scope_existing_policies} existing runtime target-scope policies with "
        f"{score_approval_target_scope_supported} packets supported by them and "
        f"{score_approval_target_scope_explicit} packets carrying explicit target scopes, "
        f"marks {score_approval_target_scope_ready} packets target-scope-ready after approval, "
        f"requires target-scope policy for {score_approval_target_scope_policy_required}, "
        f"requires per-stock materialization for {score_approval_target_scope_per_stock}, "
        f"requires market/event scope policy for {score_approval_target_scope_market_event}, "
        f"marks {score_approval_target_scope_materialization_ready} runtime-materialization-ready, "
        f"keeps {score_approval_target_scope_approval_only_not_sufficient} approval-only-not-sufficient packets, "
        f"allows {score_approval_target_scope_safe_after_approval} safe runtime writes after approval, "
        f"and allows {score_approval_target_scope_prod_writes} production writes;"
        if score_approval_target_scope_readiness_summary
        else ""
    )
    approval_materialization_plan_clause = (
        f" Approval materialization plan audit checks {score_approval_materialization_packets} approval packets "
        f"against {score_approval_materialization_a_share_universe} configured A-share tickers, "
        f"separates {score_approval_materialization_fundamental_packets} fundamental packets into "
        f"{score_approval_materialization_direct_formula} direct structured formula packets with "
        f"{score_approval_materialization_direct_formula_ready} review-ready materialization plans, "
        f"covering {score_approval_materialization_min_target} to "
        f"{score_approval_materialization_max_target} tickers per direct formula, "
        f"{score_approval_materialization_grain_join} grain-join policy packet, "
        f"{score_approval_materialization_text_export} text full-match export packets, and "
        f"{score_approval_materialization_market_event} market/event scope policy packets; "
        f"it leaves {score_approval_materialization_unsupported} unsupported materialization policies, "
        f"marks {score_approval_materialization_ready} runtime materialization plans ready for review, "
        f"allows {score_approval_materialization_runtime_writes} runtime writes, "
        f"and allows {score_approval_materialization_prod_writes} production writes;"
        if score_approval_materialization_plan_summary
        else ""
    )
    approval_materialization_batch_plan_clause = (
        f" Approval materialization batch-plan audit packages {score_approval_materialization_batch_formula_plans} "
        f"direct formula plans into {score_approval_materialization_batch_entries} controlled batch-plan entries, "
        f"validates {score_approval_materialization_batch_contract_valid} batch-plan contracts, "
        f"flags {score_approval_materialization_batch_contract_invalid} invalid batch-plan contracts, "
        f"keeps {score_approval_materialization_batch_review_required} batch plans review-required, "
        f"marks {score_approval_materialization_batch_approved} batch plans approved, "
        f"plans {score_approval_materialization_batch_rows} formula UPSERT rows "
        f"({score_approval_materialization_batch_inserts} inserts, "
        f"{score_approval_materialization_batch_updates} updates), "
        f"requires backup for {score_approval_materialization_batch_backup_rows} existing rows, "
        f"keeps {score_approval_materialization_batch_upsert_ready} upsert-ready entries, "
        f"blocks {score_approval_materialization_batch_blocked} entries pending review approval, "
        f"attempts {score_approval_materialization_batch_attempted} runtime writes, "
        f"and allows {score_approval_materialization_batch_prod_writes} production writes;"
        if score_approval_materialization_batch_plan_summary
        else ""
    )
    approval_materialization_batch_codex_review_clause = (
        f" Approval materialization Codex batch-review audit checks {score_approval_materialization_codex_rows} "
        f"batch-plan rows, approves {score_approval_materialization_codex_approved} formula batch plans, "
        f"rejects {score_approval_materialization_codex_rejected}, "
        f"emits {score_approval_materialization_codex_records} approval records, "
        f"covers {score_approval_materialization_codex_planned_rows} planned formula UPSERT rows, "
        f"approves {score_approval_materialization_codex_approved_rows} planned formula UPSERT rows, "
        f"classifies {score_approval_materialization_codex_inserts} inserts and "
        f"{score_approval_materialization_codex_updates} updates, "
        f"requires backup for {score_approval_materialization_codex_backup_rows} existing rows, "
        f"attempts {score_approval_materialization_codex_runtime_writes} runtime writes, "
        f"and allows {score_approval_materialization_codex_prod_writes} production writes;"
        if score_approval_materialization_batch_codex_review_summary
        else ""
    )
    approval_materialization_batch_approval_gate_clause = (
        f" Approval materialization batch approval-gate audit checks {score_approval_materialization_gate_rows} "
        f"batch-plan rows, validates {score_approval_materialization_gate_contract_valid} contract-valid batch plans, "
        f"sees {score_approval_materialization_gate_records_seen} approval records, "
        f"requires {score_approval_materialization_gate_required} approvals, "
        f"keeps {score_approval_materialization_gate_missing} approvals missing, "
        f"rejects {score_approval_materialization_gate_rejected} approvals, "
        f"approves {score_approval_materialization_gate_approved} formula batch plans, "
        f"emits {score_approval_materialization_gate_templates} blank approval templates with "
        f"{score_approval_materialization_gate_templates_valid} template contracts valid, "
        f"covers {score_approval_materialization_gate_planned_rows} planned formula UPSERT rows, "
        f"approves {score_approval_materialization_gate_approved_rows} planned formula UPSERT rows, "
        f"allows {score_approval_materialization_gate_runtime_writes} runtime writes, "
        f"and allows {score_approval_materialization_gate_prod_writes} production writes;"
        if score_approval_materialization_batch_approval_gate_summary
        else ""
    )
    approval_materialization_batch_execution_preflight_clause = (
        f" Approval materialization execution-preflight audit checks {score_approval_materialization_preflight_entries} "
        f"batch-plan entries and {score_approval_materialization_preflight_approved} approved formula batch plans, "
        f"preflights {score_approval_materialization_preflight_checked} entries, "
        f"marks {score_approval_materialization_preflight_ready} dry-run ready and "
        f"{score_approval_materialization_preflight_blocked} blocked, "
        f"covers {score_approval_materialization_preflight_planned_rows} planned formula UPSERT rows, "
        f"would write {score_approval_materialization_preflight_would_write} runtime rows, "
        f"classifies {score_approval_materialization_preflight_inserts} inserts and "
        f"{score_approval_materialization_preflight_updates} updates, "
        f"requires backup for {score_approval_materialization_preflight_backup_rows} existing rows across "
        f"{score_approval_materialization_preflight_backups_required} backup-required entries, "
        f"creates {score_approval_materialization_preflight_backups_created} backups, "
        f"attempts {score_approval_materialization_preflight_write_attempts} runtime writes, "
        f"completes {score_approval_materialization_preflight_write_completed} runtime writes, "
        f"post-write verifies {score_approval_materialization_preflight_verified_rows} rows, "
        f"and allows {score_approval_materialization_preflight_prod_writes} production writes;"
        if score_approval_materialization_batch_execution_preflight_summary
        else ""
    )
    runtime_scope_approvals_clause = (
        f" Runtime-scope approval audit checks {score_runtime_scope_approval_rows} target-scope rows, "
        f"creates {score_runtime_scope_approval_records} scope approval records, "
        f"approves {score_runtime_scope_approved_scopes} runtime target scopes, "
        f"rejects {score_runtime_scope_rejected}, "
        f"tracks {score_runtime_scope_approval_candidate_rows} candidate runtime rows that would write if later batch-approved, "
        f"attempts {score_runtime_scope_approval_attempted} runtime writes, "
        f"and allows {score_runtime_scope_approval_prod_writes} production writes;"
        if score_runtime_scope_approvals_summary
        else ""
    )
    runtime_write_target_scope_clause = (
        f" Runtime-write target-scope audit checks {score_runtime_scope_approved_entries} approved write-plan entries, "
        f"matches {score_runtime_scope_runtime_a_share} runtime A-share ts_codes "
        f"to {score_runtime_scope_config_a_share} configured A-share ts_codes "
        f"(exact match={score_runtime_scope_exact_match}), "
        f"packages {score_runtime_scope_candidates} target-scope candidates, "
        f"validates {score_runtime_scope_contract_valid} target-scope contracts, "
        f"flags {score_runtime_scope_contract_invalid} invalid target-scope contracts, "
        f"keeps {score_runtime_scope_review_required} target-scope reviews required, "
        f"marks {score_runtime_scope_approved_count} target scopes approved, "
        f"requires {score_runtime_scope_batch_plan_required} controlled batch plans, "
        f"would write {score_runtime_scope_candidate_rows} candidate runtime rows if later approved, "
        f"finds {score_runtime_scope_upsert_ready} upsert-ready entries, "
        f"attempts {score_runtime_scope_attempted} runtime writes, "
        f"and allows {score_runtime_scope_prod_writes} production writes;"
        if score_runtime_write_target_scope_summary
        else ""
    )
    runtime_write_batch_plan_clause = (
        f" Runtime-write batch-plan audit builds {score_runtime_batch_plan_entries} controlled batch-plan entries, "
        f"validates {score_runtime_batch_plan_valid} batch-plan contracts, "
        f"flags {score_runtime_batch_plan_invalid} invalid batch-plan contracts, "
        f"keeps {score_runtime_batch_plan_review_required} batch-plan reviews required, "
        f"has {score_runtime_batch_plan_approved} approved batch plans, "
        f"plans {score_runtime_batch_plan_rows} UPSERT rows "
        f"({score_runtime_batch_plan_insert_rows} inserts and "
        f"{score_runtime_batch_plan_update_rows} updates), "
        f"requires backup for {score_runtime_batch_plan_backup_rows} existing rows, "
        f"attempts {score_runtime_batch_plan_attempted} runtime writes, "
        f"and allows {score_runtime_batch_plan_prod_writes} production writes;"
        if score_runtime_write_batch_plan_summary
        else ""
    )
    runtime_write_batch_approval_clause = (
        f" Runtime-write batch-approval audit checks {score_runtime_batch_approval_rows} batch-plan rows, "
        f"creates {score_runtime_batch_approval_records} batch approval records, "
        f"approves {score_runtime_batch_approved_count} controlled batch plans, "
        f"rejects {score_runtime_batch_policy_rejected}, "
        f"covers {score_runtime_batch_approval_rows_planned} planned UPSERT rows "
        f"({score_runtime_batch_approval_insert_rows} inserts and "
        f"{score_runtime_batch_approval_update_rows} updates), "
        f"requires backup for {score_runtime_batch_approval_backup_rows} existing rows, "
        f"attempts {score_runtime_batch_approval_attempted} runtime writes, "
        f"and allows {score_runtime_batch_approval_prod_writes} production writes;"
        if score_runtime_write_batch_approvals_summary
        else ""
    )
    runtime_write_execution_clause = (
        f" Runtime-write execution audit covers {score_runtime_execution_approved} approved batch plans, "
        f"has {score_runtime_execution_ready} execution-ready plans, "
        f"blocks {score_runtime_execution_blocked}, "
        f"completes backup for {score_runtime_execution_backup_completed} plans, "
        f"reports {score_runtime_execution_backup_failed} backup failures, "
        f"attempts {score_runtime_execution_attempted} runtime writes, "
        f"completes {score_runtime_execution_completed}, "
        f"reports {score_runtime_execution_failed} runtime write failures, "
        f"writes {score_runtime_execution_rows} runtime rows "
        f"({score_runtime_execution_insert_rows} inserts and "
        f"{score_runtime_execution_update_rows} updates), "
        f"post-write verifies {score_runtime_execution_verified_rows} rows, "
        f"reports {score_runtime_execution_verification_errors} verification errors, "
        f"and allows {score_runtime_execution_prod_writes} production writes;"
        if score_runtime_write_execution_summary
        else ""
    )
    runtime_write_preflight_clause = (
        f" Runtime-write preflight checks {score_runtime_preflight_approved_entries} approved write-plan entries, "
        f"finds {score_runtime_preflight_upsert_ready} upsert-ready entries, "
        f"finds {score_runtime_preflight_executed_entries} executed entries, "
        f"blocks {score_runtime_preflight_blocked}, "
        f"finds {score_runtime_preflight_missing_scope} missing target scopes, "
        f"tracks {score_runtime_preflight_candidate_rows} candidate runtime rows that would write if later approved, "
        f"requires {score_runtime_preflight_batch_plan_required} controlled batch plans, "
        f"finds {score_runtime_preflight_batch_plan_candidates} batch-plan candidates, "
        f"keeps {score_runtime_preflight_batch_plan_review_required} batch-plan reviews required, "
        f"marks {score_runtime_preflight_batch_plan_approved} batch plans approved, "
        f"keeps {score_runtime_preflight_backup_execution_required} runtime backup/execution gates required, "
        f"recognizes {score_runtime_preflight_execution_completed} runtime executions complete, "
        f"tracks {score_runtime_preflight_execution_rows} execution-written rows, "
        f"verifies {score_runtime_preflight_execution_verified_rows} execution-written rows, "
        f"tracks {score_runtime_preflight_batch_plan_rows} planned batch UPSERT rows, "
        f"requires backup for {score_runtime_preflight_batch_plan_backup_rows} existing rows, "
        f"would write {score_runtime_preflight_rows_would_write} runtime rows, "
        f"attempts {score_runtime_preflight_attempted} runtime writes, "
        f"and allows {score_runtime_preflight_prod_writes} production writes;"
        if score_runtime_write_preflight_summary
        else ""
    )
    score_gap_remaining = (
        f"Current score-field closure is {score_closed_fields}/{score_relevant_fields} score-relevant dp_ids. "
        "All score-relevant valid-real formula gaps are currently governance/intentional; "
        f"remaining score incompleteness is {score_actionable_gaps} actionable participating gaps "
        f"plus {score_governance_gaps} governance/intentional gaps. "
        f"Candidate evidence now packages {score_candidate_ready} actionable gaps for source-backed candidate review "
        f"and leaves {score_candidate_not_ready} not ready for candidate input; "
        f"{dry_run_clause}{upsert_safety_clause}{staging_clause}{value_contract_clause}{spec_numeric_clause}{spec_score_conversion_clause}{score_conversion_remediation_clause}{formula_policy_review_packet_clause}{governance_suppression_clause}{option_universe_na_clause}{generation_queue_clause}{l0_source_readiness_clause}{short_report_evidence_clause}{non_manual_readiness_clause}{event_text_draft_clause}{event_text_classification_input_clause}{event_text_preclassification_screen_clause}{event_text_sufficiency_gate_clause}{event_text_url_fetchability_clause}{event_text_unknown_options_clause}{event_text_market_doc_evidence_clause}{event_text_market_doc_review_packets_clause}{local_structured_draft_clause}{local_structured_unknown_options_clause}{local_structured_source_candidates_clause}{local_structured_source_review_packets_clause}{local_structured_text_draft_clause}{local_structured_text_unknown_options_clause}{single_dependency_draft_clause}{single_dependency_unknown_options_clause}{manual_policy_draft_clause}{manual_policy_unknown_options_clause}{review_staging_manifest_clause}{deterministic_runtime_approvals_clause}{review_approval_gate_clause}{completion_next_action_clause}{unknown_closure_matrix_clause}{unknown_acquisition_backlog_clause}{unknown_market_doc_acquisition_clause}{unknown_event_adjudication_clause}{unknown_event_strict_source_gate_clause}{unknown_event_strict_review_packets_clause}{unknown_event_primary_source_confirmation_clause}{unknown_event_external_source_confirmation_clause}{unknown_local_formula_acquisition_clause}{unknown_local_formula_review_packets_clause}{local_formula_source_capability_clause}{unknown_external_business_metric_acquisition_clause}{unknown_external_business_metric_market_doc_clause}{unknown_external_business_metric_review_packets_clause}{unknown_external_business_metric_readiness_queue_clause}{unknown_external_business_metric_policy_drafts_clause}{unknown_external_business_metric_value_candidates_clause}{unknown_external_business_metric_value_review_packets_clause}{unknown_business_metric_value_selection_gate_clause}{unknown_penetration_value_priority_clause}{unknown_penetration_p1_source_confirmation_clause}{unknown_penetration_value_policy_draft_clause}{unknown_penetration_value_confirmation_packets_clause}{unknown_penetration_value_confirmation_templates_clause}{unknown_penetration_value_confirmation_gate_clause}{unknown_penetration_confirmed_known_drafts_clause}{approval_review_packets_clause}{approval_packet_risk_review_clause}{bulk_review_approval_candidates_clause}{bulk_review_source_samples_clause}{event_approval_source_samples_clause}{individual_review_source_samples_clause}{approval_source_sample_coverage_clause}{approval_target_scope_readiness_clause}{approval_materialization_plan_clause}{approval_materialization_batch_plan_clause}{approval_materialization_batch_codex_review_clause}{approval_materialization_batch_approval_gate_clause}{approval_materialization_batch_execution_preflight_clause}{runtime_scope_approvals_clause}{runtime_write_target_scope_clause}{runtime_write_preflight_clause} safe-to-upsert-without-review remains {score_safe_upsert}."
        if score_gap_summary and score_formula_actionable_gaps == 0
        else "Still has participating gaps and governance/design review items; not all spec fields are complete in the score path."
    )
    if runtime_write_batch_plan_clause:
        score_gap_remaining = score_gap_remaining.replace(
            f"{runtime_write_target_scope_clause}{runtime_write_preflight_clause}",
            f"{runtime_write_target_scope_clause}"
            f"{runtime_write_batch_plan_clause}"
            f"{runtime_write_batch_approval_clause}"
            f"{runtime_write_execution_clause}"
            f"{runtime_write_preflight_clause}",
        )
    score_field_strength = "runtime_trace_and_gap_priority"
    if score_candidate_summary:
        score_field_strength = "runtime_trace_gap_priority_and_candidate_evidence"
    if score_field_closure_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_and_field_closure"
    if score_candidate_dry_run_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_field_closure_and_bridge_dry_run"
    if score_candidate_upsert_safety_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_and_upsert_safety"
    if score_candidate_staging_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_and_staging_payloads"
    if score_candidate_value_contracts_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_and_value_contracts"
    if score_spec_numeric_validity_summary:
        score_field_strength = "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_and_spec_numeric_validity"
    if score_candidate_generation_queue_summary:
        suffixes: list[str] = []
        if score_l0_source_readiness_summary:
            suffixes.append("l0_source_readiness")
        if score_short_report_evidence_summary:
            suffixes.append("short_report_evidence")
        if score_spec_numeric_validity_summary:
            suffixes.append("spec_numeric_validity")
        if score_spec_score_conversion_summary:
            suffixes.append("spec_score_conversion_path")
        if score_formula_policy_review_packets_summary:
            suffixes.append("formula_policy_review_packets")
        if score_governance_suppression_summary:
            suffixes.append("governance_suppression_verification")
        if score_option_universe_na_summary:
            suffixes.append("option_universe_na_verification")
        if score_non_manual_readiness_summary:
            suffixes.append("non_manual_readiness")
        if score_event_text_draft_summary:
            suffixes.append("event_text_drafts")
        if score_event_text_classification_inputs_summary:
            suffixes.append("event_text_classification_inputs")
        if score_event_text_preclassification_screen_summary:
            suffixes.append("event_text_preclassification_screen")
        if score_event_text_sufficiency_gate_summary:
            suffixes.append("event_text_sufficiency_gate")
        if score_event_text_url_fetchability_summary:
            suffixes.append("event_text_url_fetchability")
        if score_event_text_unknown_source_options_summary:
            suffixes.append("event_text_unknown_source_options")
        if score_event_text_market_doc_evidence_summary:
            suffixes.append("event_text_market_doc_evidence")
        if score_event_text_market_doc_review_packets_summary:
            suffixes.append("event_text_market_doc_review_packets")
        if score_local_structured_draft_summary:
            suffixes.append("local_structured_drafts")
        if score_local_structured_unknown_source_options_summary:
            suffixes.append("local_structured_unknown_source_options")
        if score_local_structured_source_candidates_summary:
            suffixes.append("local_structured_source_candidates")
        if score_local_structured_source_review_packets_summary:
            suffixes.append("local_structured_source_review_packets")
        if score_local_structured_text_draft_summary:
            suffixes.append("local_structured_text_drafts")
        if score_local_structured_text_unknown_source_options_summary:
            suffixes.append("local_structured_text_unknown_source_options")
        if score_single_dependency_draft_summary:
            suffixes.append("single_dependency_drafts")
        if score_single_dependency_unknown_source_options_summary:
            suffixes.append("single_dependency_unknown_source_options")
        if score_manual_policy_draft_summary:
            suffixes.append("manual_policy_draft_pilot")
        if score_manual_policy_unknown_source_options_summary:
            suffixes.append("manual_policy_unknown_source_options")
        if score_review_staging_manifest_summary:
            suffixes.append("review_staging_manifest")
        if score_deterministic_runtime_approvals_summary:
            suffixes.append("deterministic_runtime_approvals")
        if score_review_approval_gate_summary:
            suffixes.append("review_approval_gate")
        if score_completion_next_actions_summary:
            suffixes.append("completion_next_actions")
        if score_unknown_closure_matrix_summary:
            suffixes.append("unknown_closure_matrix")
        if score_unknown_acquisition_backlog_summary:
            suffixes.append("unknown_acquisition_backlog")
        if score_unknown_market_doc_acquisition_summary:
            suffixes.append("unknown_market_doc_acquisition_candidates")
        if score_unknown_event_evidence_adjudication_summary:
            suffixes.append("unknown_event_evidence_adjudication")
        if score_unknown_event_strict_source_gate_summary:
            suffixes.append("unknown_event_strict_source_gate")
        if score_unknown_event_strict_review_packets_summary:
            suffixes.append("unknown_event_strict_review_packets")
        if score_unknown_event_primary_source_confirmation_summary:
            suffixes.append("unknown_event_primary_source_confirmation")
        if score_unknown_event_external_source_confirmation_summary:
            suffixes.append("unknown_event_external_source_confirmation")
        if score_unknown_local_formula_acquisition_summary:
            suffixes.append("unknown_local_formula_acquisition_candidates")
        if score_unknown_local_formula_review_packets_summary:
            suffixes.append("unknown_local_formula_review_packets")
        if score_local_formula_source_capability_summary:
            suffixes.append("local_formula_source_capability")
        if score_unknown_external_business_metric_acquisition_summary:
            suffixes.append("unknown_external_business_metric_acquisition")
        if score_unknown_external_business_metric_market_doc_summary:
            suffixes.append("unknown_external_business_metric_market_doc_candidates")
        if score_unknown_external_business_metric_review_packets_summary:
            suffixes.append("unknown_external_business_metric_review_packets")
        if score_unknown_external_business_metric_readiness_queue_summary:
            suffixes.append("unknown_external_business_metric_readiness_queue")
        if score_unknown_external_business_metric_policy_drafts_summary:
            suffixes.append("unknown_external_business_metric_policy_drafts")
        if score_unknown_external_business_metric_value_candidates_summary:
            suffixes.append("unknown_external_business_metric_value_candidates")
        if score_unknown_external_business_metric_value_review_packets_summary:
            suffixes.append("unknown_external_business_metric_value_review_packets")
        if score_unknown_business_metric_value_selection_gate_summary:
            suffixes.append("unknown_business_metric_value_selection_gate")
        if score_unknown_penetration_value_priority_summary:
            suffixes.append("unknown_penetration_value_priority")
        if score_unknown_penetration_p1_source_confirmation_summary:
            suffixes.append("unknown_penetration_p1_source_confirmation")
        if score_unknown_penetration_value_policy_draft_summary:
            suffixes.append("unknown_penetration_value_policy_draft")
        if score_unknown_penetration_value_confirmation_packets_summary:
            suffixes.append("unknown_penetration_value_confirmation_packets")
        if score_unknown_penetration_value_confirmation_templates_summary:
            suffixes.append("unknown_penetration_value_confirmation_templates")
        if score_unknown_penetration_value_confirmation_gate_summary:
            suffixes.append("unknown_penetration_value_confirmation_gate")
        if score_unknown_penetration_confirmed_known_drafts_summary:
            suffixes.append("unknown_penetration_confirmed_known_drafts")
        if score_approval_review_packets_summary:
            suffixes.append("approval_review_packets")
        if score_approval_packet_risk_review_summary:
            suffixes.append("approval_packet_risk_review")
        if score_bulk_review_approval_candidates_summary:
            suffixes.append("bulk_review_approval_candidates")
        if score_bulk_review_source_samples_summary:
            suffixes.append("bulk_review_source_samples")
        if score_event_approval_source_samples_summary:
            suffixes.append("event_approval_source_samples")
        if score_individual_review_source_samples_summary:
            suffixes.append("individual_review_source_samples")
        if score_approval_source_sample_coverage_summary:
            suffixes.append("approval_source_sample_coverage")
        if score_approval_target_scope_readiness_summary:
            suffixes.append("approval_target_scope_readiness")
        if score_approval_materialization_plan_summary:
            suffixes.append("approval_materialization_plan")
        if score_approval_materialization_batch_plan_summary:
            suffixes.append("approval_materialization_batch_plan")
        if score_approval_materialization_batch_codex_review_summary:
            suffixes.append("approval_materialization_batch_codex_review")
        if score_approval_materialization_batch_approval_gate_summary:
            suffixes.append("approval_materialization_batch_approval_gate")
        if score_approval_materialization_batch_execution_preflight_summary:
            suffixes.append("approval_materialization_batch_execution_preflight")
        if score_runtime_scope_approvals_summary:
            suffixes.append("runtime_scope_approvals")
        if score_runtime_write_target_scope_summary:
            suffixes.append("runtime_write_target_scope")
        if score_runtime_write_batch_plan_summary:
            suffixes.append("runtime_write_batch_plan")
        if score_runtime_write_batch_approvals_summary:
            suffixes.append("runtime_write_batch_approvals")
        if score_runtime_write_execution_summary:
            suffixes.append("runtime_write_execution")
        if score_runtime_write_preflight_summary:
            suffixes.append("runtime_write_preflight")
        score_field_strength = _strength_with_suffixes(
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue",
            suffixes,
        )

    rows = [
        _line(
            "repo_operational_file_inventory",
            "Inventory current project files and read bounded text bodies",
            _status(
                bool(
                    repo_files
                    and repo_files.get("error_count") == 0
                    and repo_content.get("text_files_read")
                    and repo_content.get("error_count") == 0
                )
            ),
            (
                "metadata_full_walk_plus_text_body_read_plus_binary_large_semantic_audit"
                if repo_binary_semantics_complete
                else "metadata_full_walk_plus_bounded_text_body_read"
            ),
            {
                **_artifact(file_inventory_path),
                "repo_content_path": str(repo_content_path),
                "repo_content_exists": repo_content_path.exists(),
                "repo_binary_semantics_path": str(repo_binary_semantics_path),
                "repo_binary_semantics_exists": repo_binary_semantics_path.exists(),
                "files": repo_files.get("files"),
                "dirs": repo_files.get("dirs"),
                "bytes": repo_files.get("bytes"),
                "error_count": repo_files.get("error_count"),
                "text_files_read": repo_content.get("text_files_read"),
                "text_bytes_read": repo_content.get("text_bytes_read"),
                "text_lines_read": repo_content.get("text_lines_read"),
                "skipped_binary": repo_content.get("skipped_binary"),
                "skipped_too_large": repo_content.get("skipped_too_large"),
                "repo_content_error_count": repo_content.get("error_count"),
                "skipped_file_samples": len(repo_content.get("skipped_file_samples", [])),
                "skipped_file_fingerprints_count": skipped_file_fingerprints_count,
                "repo_binary_semantics_summary": repo_binary_summary,
                "largest_skipped_files": repo_content.get("largest_skipped_files", [])[:10],
            },
            (
                "Bounded text bodies are read and fingerprinted; every skipped binary/large file has head/tail fingerprint evidence plus type-aware semantic classification and safe structural metadata."
                if repo_binary_semantics_complete
                else "Bounded text bodies are read and fingerprinted; every skipped binary/large file now has a head/tail fingerprint entry, but type-aware semantic classification remains incomplete."
            ),
        ),
        _line(
            "dockcase_inventory",
            "Inventory DOCKCASE database_all and market_data files",
            _status(bool(dock_db and dock_market and dock_db.get("error_count") == 0 and dock_market.get("error_count") == 0)),
            "metadata_full_walk",
            {
                **_artifact(file_inventory_path),
                "database_all_files": dock_db.get("files"),
                "market_data_files": dock_market.get("files"),
                "database_all_bytes": dock_db.get("bytes"),
                "market_data_bytes": dock_market.get("bytes"),
            },
            "Metadata inventory is full, but full semantic content review remains bounded by later samples.",
        ),
        _line(
            "source_code_static_inventory",
            "Read/index source-bearing code roots",
            _status(bool(code_totals and code_inventory.get("parse_error_count") == 0)),
            "static_full_index_selected_roots",
            {
                **_artifact(code_inventory_path),
                "files": code_totals.get("files"),
                "lines": code_totals.get("lines"),
                "definitions": code_totals.get("definitions"),
                "imports": code_totals.get("imports"),
                "parse_error_count": code_inventory.get("parse_error_count"),
            },
            "Static indexing is broad but not equivalent to manual semantic review of every implementation path.",
        ),
        _line(
            "dockcase_schema_and_first_row_catalog",
            "Open data files enough to verify schema and first-row samples",
            _status(bool(data_db and data_db.get("csv_header_error_count") == 0)),
            "schema_full_csv_headers_bounded_first_rows",
            {
                **_artifact(data_catalog_path),
                "database_all_csv_headers_read": data_db.get("csv_headers_read"),
                "database_all_first_rows_sampled": data_db.get("csv_data_rows_sampled"),
                "database_all_header_only_csvs": data_db.get("csv_files_without_sampled_data_row"),
                "database_all_row_width_mismatches": data_db.get("csv_row_width_mismatch_count"),
                "market_data_files": data_market.get("data_files"),
            },
            "Does not read every CSV row; JSON/HTML/PDF content remains sampled.",
        ),
        _line(
            "dockcase_csv_stratified_semantics",
            "Record all-file DOCKCASE CSV evidence, sampled semantics, and full-row scan progress",
            _status(
                bool(
                    dockcase_file_evidence_summary.get("all_seen_files_have_evidence_rows")
                    and dockcase_file_evidence_summary.get(
                        "all_seen_files_have_head_tail_fingerprint"
                    )
                    and dockcase_csv_semantics.get("summary", {}).get("sampled_rows")
                )
            ),
            (
                "all_csv_file_head_tail_evidence_plus_full_row_semantic_scan"
                if dockcase_full_scan_complete
                else (
                    "all_csv_file_head_tail_evidence_plus_signature_stratified_bounded_semantic_rows_plus_partial_full_row_scan"
                    if dockcase_full_scan_summary
                    else "all_csv_file_head_tail_evidence_plus_signature_stratified_bounded_semantic_rows"
                )
            ),
            {
                "csv_file_evidence_path": str(dockcase_csv_file_evidence_path),
                "csv_file_evidence_exists": dockcase_csv_file_evidence_path.exists(),
                "csv_file_evidence_summary": dockcase_file_evidence_summary,
                "csv_full_scan_path": str(dockcase_csv_full_scan_path),
                "csv_full_scan_exists": dockcase_csv_full_scan_path.exists(),
                "csv_full_scan_progress_path": str(dockcase_csv_full_scan_progress_path),
                "csv_full_scan_progress_exists": dockcase_csv_full_scan_progress_path.exists(),
                "csv_full_scan_summary": dockcase_full_scan_summary,
                **_artifact(dockcase_csv_semantics_path),
                "semantic_backlog_path": str(dockcase_backlog_path),
                "semantic_backlog_exists": dockcase_backlog_path.exists(),
                "semantic_backlog_summary": dockcase_backlog.get("summary", {}),
                "semantic_backlog_batch_paths": [
                    batch.get("_path") for batch in dockcase_backlog_batches
                ],
                "semantic_backlog_batch_summary": dockcase_backlog_batch_summary,
                **dockcase_csv_semantics.get("summary", {}),
            },
            (
                (
                    "Every business CSV now has file-level head/tail fingerprint evidence and full-row semantic scan coverage; "
                    f"the full-row scanner has read {dockcase_full_scan_summary.get('rows_scanned', 0)} rows "
                    f"from {dockcase_full_scan_summary.get('csv_files_scanned', dockcase_full_scan_summary.get('csv_files_seen', 0))} files with "
                    f"{dockcase_full_scan_summary.get('row_read_error_count', 0)} row-read errors, "
                    f"{dockcase_full_scan_summary.get('row_width_mismatch_count', 0)} row-width mismatches, "
                    f"{dockcase_full_scan_summary.get('range_gap_count', 0)} shard gaps, and "
                    f"{dockcase_full_scan_summary.get('range_overlap_count', 0)} shard overlaps. "
                    "The remaining work is issue interpretation/remediation, not row/file coverage."
                )
                if dockcase_full_scan_complete
                else (
                    "Every business CSV now has file-level head/tail fingerprint evidence; "
                    "semantic validation still covers bounded real rows across header-signature strata and reports signature/file sampling boundaries; "
                    f"the full-row scanner has read {dockcase_full_scan_summary.get('rows_scanned', 0)} rows "
                    f"from {dockcase_full_scan_summary.get('csv_files_seen', dockcase_full_scan_summary.get('csv_files_scanned', 0))} selected files with "
                    f"{dockcase_full_scan_summary.get('row_read_error_count', 0)} row-read errors, but "
                    f"the semantic backlog ranks remaining high-volume/no-sample/issue-heavy signatures and "
                    f"{dockcase_backlog_batch_summary.get('batch_count', 0)} backlog batches deep-sampled ranks "
                    f"{dockcase_backlog_batch_summary.get('target_ranks', [])}, but it still does not exhaustively read every CSV row."
                )
            ),
        ),
        _line(
            "a_share_structured_semantic_sample",
            "Check selected A-share structured data rows for semantic validity",
            _status(bool(a_share_data.get("summary", {}).get("total_rows_read"))),
            "bounded_real_row_semantic_sample",
            {
                **_artifact(a_share_data_path),
                **a_share_data.get("summary", {}),
            },
            "Covers representative high-value A-share sources, not every symbol/file/row.",
        ),
        _line(
            "market_document_extractability_sample",
            "Check news HTML, announcement PDF text extractability, and entity/event signals",
            _status(bool(market_doc.get("summary", {}).get("news_html_files"))),
            (
                "count_all_parse_full_entity_event_signal_pass"
                if market_full_parse
                else "count_all_parse_bounded_entity_event_signal_samples"
            ),
            {
                **_artifact(market_doc_path),
                **market_doc.get("summary", {}),
            },
            (
                "Counts and parses every audited HTML/PDF file; retained examples are bounded for report size, while entity/event classification remains heuristic."
                if market_full_parse
                else "Counts all audited HTML/PDF files and reports selected/parsed sample boundaries; entity/date/event signals remain sample-based, not full linking/classification for every document."
            ),
        ),
        _line(
            "a_share_score_field_path",
            "Trace A-share spec fields into numeric scoring paths",
            _status(bool(score_trace.get("summary", {}).get("spec_total"))),
            score_field_strength,
            {
                **_artifact(score_trace_path),
                "score_gap_path": str(score_gap_path),
                "score_gap_exists": score_gap_path.exists(),
                "score_candidate_path": str(score_candidate_path),
                "score_candidate_exists": score_candidate_path.exists(),
                "score_candidate_dry_run_path": str(score_candidate_dry_run_path),
                "score_candidate_dry_run_exists": score_candidate_dry_run_path.exists(),
                "score_candidate_upsert_safety_path": str(score_candidate_upsert_safety_path),
                "score_candidate_upsert_safety_exists": score_candidate_upsert_safety_path.exists(),
                "score_candidate_staging_path": str(score_candidate_staging_path),
                "score_candidate_staging_exists": score_candidate_staging_path.exists(),
                "score_candidate_value_contracts_path": str(score_candidate_value_contracts_path),
                "score_candidate_value_contracts_exists": score_candidate_value_contracts_path.exists(),
                "score_spec_numeric_validity_path": str(score_spec_numeric_validity_path),
                "score_spec_numeric_validity_exists": score_spec_numeric_validity_path.exists(),
                "score_spec_score_conversion_path": str(score_spec_score_conversion_path),
                "score_spec_score_conversion_exists": (
                    score_spec_score_conversion_path.exists()
                ),
                "score_conversion_remediation_path": str(score_conversion_remediation_path),
                "score_conversion_remediation_exists": (
                    score_conversion_remediation_path.exists()
                ),
                "score_formula_policy_review_packets_path": str(
                    score_formula_policy_review_packets_path
                ),
                "score_formula_policy_review_packets_exists": (
                    score_formula_policy_review_packets_path.exists()
                ),
                "score_governance_suppression_path": str(
                    score_governance_suppression_path
                ),
                "score_governance_suppression_exists": (
                    score_governance_suppression_path.exists()
                ),
                "score_option_universe_na_path": str(score_option_universe_na_path),
                "score_option_universe_na_exists": (
                    score_option_universe_na_path.exists()
                ),
                "score_candidate_generation_queue_path": str(score_candidate_generation_queue_path),
                "score_candidate_generation_queue_exists": score_candidate_generation_queue_path.exists(),
                "score_l0_source_readiness_path": str(score_l0_source_readiness_path),
                "score_l0_source_readiness_exists": score_l0_source_readiness_path.exists(),
                "score_short_report_evidence_path": str(score_short_report_evidence_path),
                "score_short_report_evidence_exists": score_short_report_evidence_path.exists(),
                "score_non_manual_readiness_path": str(score_non_manual_readiness_path),
                "score_non_manual_readiness_exists": score_non_manual_readiness_path.exists(),
                "score_event_text_draft_path": str(score_event_text_draft_path),
                "score_event_text_draft_exists": score_event_text_draft_path.exists(),
                "score_event_text_classification_inputs_path": str(
                    score_event_text_classification_inputs_path
                ),
                "score_event_text_classification_inputs_exists": (
                    score_event_text_classification_inputs_path.exists()
                ),
                "score_event_text_preclassification_screen_path": str(
                    score_event_text_preclassification_screen_path
                ),
                "score_event_text_preclassification_screen_exists": (
                    score_event_text_preclassification_screen_path.exists()
                ),
                "score_event_text_sufficiency_gate_path": str(
                    score_event_text_sufficiency_gate_path
                ),
                "score_event_text_sufficiency_gate_exists": (
                    score_event_text_sufficiency_gate_path.exists()
                ),
                "score_event_text_url_fetchability_path": str(
                    score_event_text_url_fetchability_path
                ),
                "score_event_text_url_fetchability_exists": (
                    score_event_text_url_fetchability_path.exists()
                ),
                "score_event_text_unknown_source_options_path": str(
                    score_event_text_unknown_source_options_path
                ),
                "score_event_text_unknown_source_options_exists": (
                    score_event_text_unknown_source_options_path.exists()
                ),
                "score_event_text_market_doc_evidence_path": str(
                    score_event_text_market_doc_evidence_path
                ),
                "score_event_text_market_doc_evidence_exists": (
                    score_event_text_market_doc_evidence_path.exists()
                ),
                "score_event_text_market_doc_review_packets_path": str(
                    score_event_text_market_doc_review_packets_path
                ),
                "score_event_text_market_doc_review_packets_exists": (
                    score_event_text_market_doc_review_packets_path.exists()
                ),
                "score_local_structured_draft_path": str(score_local_structured_draft_path),
                "score_local_structured_draft_exists": score_local_structured_draft_path.exists(),
                "score_local_structured_unknown_source_options_path": str(
                    score_local_structured_unknown_source_options_path
                ),
                "score_local_structured_unknown_source_options_exists": (
                    score_local_structured_unknown_source_options_path.exists()
                ),
                "score_local_structured_source_candidates_path": str(
                    score_local_structured_source_candidates_path
                ),
                "score_local_structured_source_candidates_exists": (
                    score_local_structured_source_candidates_path.exists()
                ),
                "score_local_structured_source_review_packets_path": str(
                    score_local_structured_source_review_packets_path
                ),
                "score_local_structured_source_review_packets_exists": (
                    score_local_structured_source_review_packets_path.exists()
                ),
                "score_local_structured_text_draft_path": str(score_local_structured_text_draft_path),
                "score_local_structured_text_draft_exists": score_local_structured_text_draft_path.exists(),
                "score_local_structured_text_unknown_source_options_path": str(
                    score_local_structured_text_unknown_source_options_path
                ),
                "score_local_structured_text_unknown_source_options_exists": (
                    score_local_structured_text_unknown_source_options_path.exists()
                ),
                "score_single_dependency_draft_path": str(score_single_dependency_draft_path),
                "score_single_dependency_draft_exists": score_single_dependency_draft_path.exists(),
                "score_single_dependency_unknown_source_options_path": str(
                    score_single_dependency_unknown_source_options_path
                ),
                "score_single_dependency_unknown_source_options_exists": (
                    score_single_dependency_unknown_source_options_path.exists()
                ),
                "score_manual_policy_draft_path": str(score_manual_policy_draft_path),
                "score_manual_policy_draft_exists": score_manual_policy_draft_path.exists(),
                "score_manual_policy_unknown_source_options_path": str(
                    score_manual_policy_unknown_source_options_path
                ),
                "score_manual_policy_unknown_source_options_exists": (
                    score_manual_policy_unknown_source_options_path.exists()
                ),
                "score_review_staging_manifest_path": str(score_review_staging_manifest_path),
                "score_review_staging_manifest_exists": score_review_staging_manifest_path.exists(),
                "score_deterministic_runtime_approvals_path": str(
                    score_deterministic_runtime_approvals_path
                ),
                "score_deterministic_runtime_approvals_exists": (
                    score_deterministic_runtime_approvals_path.exists()
                ),
                "score_review_approval_gate_path": str(score_review_approval_gate_path),
                "score_review_approval_gate_exists": score_review_approval_gate_path.exists(),
                "score_completion_next_actions_path": str(score_completion_next_actions_path),
                "score_completion_next_actions_exists": score_completion_next_actions_path.exists(),
                "score_unknown_closure_matrix_path": str(score_unknown_closure_matrix_path),
                "score_unknown_closure_matrix_exists": score_unknown_closure_matrix_path.exists(),
                "score_unknown_acquisition_backlog_path": str(
                    score_unknown_acquisition_backlog_path
                ),
                "score_unknown_acquisition_backlog_exists": (
                    score_unknown_acquisition_backlog_path.exists()
                ),
                "score_unknown_market_doc_acquisition_path": str(
                    score_unknown_market_doc_acquisition_path
                ),
                "score_unknown_market_doc_acquisition_exists": (
                    score_unknown_market_doc_acquisition_path.exists()
                ),
                "score_unknown_event_evidence_adjudication_path": str(
                    score_unknown_event_evidence_adjudication_path
                ),
                "score_unknown_event_evidence_adjudication_exists": (
                    score_unknown_event_evidence_adjudication_path.exists()
                ),
                "score_unknown_event_strict_source_gate_path": str(
                    score_unknown_event_strict_source_gate_path
                ),
                "score_unknown_event_strict_source_gate_exists": (
                    score_unknown_event_strict_source_gate_path.exists()
                ),
                "score_unknown_event_strict_review_packets_path": str(
                    score_unknown_event_strict_review_packets_path
                ),
                "score_unknown_event_strict_review_packets_exists": (
                    score_unknown_event_strict_review_packets_path.exists()
                ),
                "score_unknown_event_primary_source_confirmation_path": str(
                    score_unknown_event_primary_source_confirmation_path
                ),
                "score_unknown_event_primary_source_confirmation_exists": (
                    score_unknown_event_primary_source_confirmation_path.exists()
                ),
                "score_unknown_event_external_source_confirmation_path": str(
                    score_unknown_event_external_source_confirmation_path
                ),
                "score_unknown_event_external_source_confirmation_exists": (
                    score_unknown_event_external_source_confirmation_path.exists()
                ),
                "score_unknown_local_formula_acquisition_path": str(
                    score_unknown_local_formula_acquisition_path
                ),
                "score_unknown_local_formula_acquisition_exists": (
                    score_unknown_local_formula_acquisition_path.exists()
                ),
                "score_unknown_local_formula_review_packets_path": str(
                    score_unknown_local_formula_review_packets_path
                ),
                "score_unknown_local_formula_review_packets_exists": (
                    score_unknown_local_formula_review_packets_path.exists()
                ),
                "score_local_formula_source_capability_path": str(
                    score_local_formula_source_capability_path
                ),
                "score_local_formula_source_capability_exists": (
                    score_local_formula_source_capability_path.exists()
                ),
                "score_unknown_external_business_metric_acquisition_path": str(
                    score_unknown_external_business_metric_acquisition_path
                ),
                "score_unknown_external_business_metric_acquisition_exists": (
                    score_unknown_external_business_metric_acquisition_path.exists()
                ),
                "score_unknown_external_business_metric_market_doc_path": str(
                    score_unknown_external_business_metric_market_doc_path
                ),
                "score_unknown_external_business_metric_market_doc_exists": (
                    score_unknown_external_business_metric_market_doc_path.exists()
                ),
                "score_unknown_external_business_metric_review_packets_path": str(
                    score_unknown_external_business_metric_review_packets_path
                ),
                "score_unknown_external_business_metric_review_packets_exists": (
                    score_unknown_external_business_metric_review_packets_path.exists()
                ),
                "score_unknown_external_business_metric_readiness_queue_path": str(
                    score_unknown_external_business_metric_readiness_queue_path
                ),
                "score_unknown_external_business_metric_readiness_queue_exists": (
                    score_unknown_external_business_metric_readiness_queue_path.exists()
                ),
                "score_unknown_external_business_metric_policy_drafts_path": str(
                    score_unknown_external_business_metric_policy_drafts_path
                ),
                "score_unknown_external_business_metric_policy_drafts_exists": (
                    score_unknown_external_business_metric_policy_drafts_path.exists()
                ),
                "score_unknown_external_business_metric_value_candidates_path": str(
                    score_unknown_external_business_metric_value_candidates_path
                ),
                "score_unknown_external_business_metric_value_candidates_exists": (
                    score_unknown_external_business_metric_value_candidates_path.exists()
                ),
                "score_unknown_external_business_metric_value_review_packets_path": str(
                    score_unknown_external_business_metric_value_review_packets_path
                ),
                "score_unknown_external_business_metric_value_review_packets_exists": (
                    score_unknown_external_business_metric_value_review_packets_path.exists()
                ),
                "score_unknown_business_metric_value_selection_gate_path": str(
                    score_unknown_business_metric_value_selection_gate_path
                ),
                "score_unknown_business_metric_value_selection_gate_exists": (
                    score_unknown_business_metric_value_selection_gate_path.exists()
                ),
                "score_unknown_penetration_value_priority_path": str(
                    score_unknown_penetration_value_priority_path
                ),
                "score_unknown_penetration_value_priority_exists": (
                    score_unknown_penetration_value_priority_path.exists()
                ),
                "score_unknown_penetration_p1_source_confirmation_path": str(
                    score_unknown_penetration_p1_source_confirmation_path
                ),
                "score_unknown_penetration_p1_source_confirmation_exists": (
                    score_unknown_penetration_p1_source_confirmation_path.exists()
                ),
                "score_unknown_penetration_value_policy_draft_path": str(
                    score_unknown_penetration_value_policy_draft_path
                ),
                "score_unknown_penetration_value_policy_draft_exists": (
                    score_unknown_penetration_value_policy_draft_path.exists()
                ),
                "score_unknown_penetration_value_confirmation_packets_path": str(
                    score_unknown_penetration_value_confirmation_packets_path
                ),
                "score_unknown_penetration_value_confirmation_packets_exists": (
                    score_unknown_penetration_value_confirmation_packets_path.exists()
                ),
                "score_unknown_penetration_value_confirmation_templates_path": str(
                    score_unknown_penetration_value_confirmation_templates_path
                ),
                "score_unknown_penetration_value_confirmation_templates_exists": (
                    score_unknown_penetration_value_confirmation_templates_path.exists()
                ),
                "score_unknown_penetration_value_confirmation_gate_path": str(
                    score_unknown_penetration_value_confirmation_gate_path
                ),
                "score_unknown_penetration_value_confirmation_gate_exists": (
                    score_unknown_penetration_value_confirmation_gate_path.exists()
                ),
                "score_unknown_penetration_confirmed_known_drafts_path": str(
                    score_unknown_penetration_confirmed_known_drafts_path
                ),
                "score_unknown_penetration_confirmed_known_drafts_exists": (
                    score_unknown_penetration_confirmed_known_drafts_path.exists()
                ),
                "score_approval_review_packets_path": str(score_approval_review_packets_path),
                "score_approval_review_packets_exists": score_approval_review_packets_path.exists(),
                "score_approval_packet_risk_review_path": str(
                    score_approval_packet_risk_review_path
                ),
                "score_approval_packet_risk_review_exists": (
                    score_approval_packet_risk_review_path.exists()
                ),
                "score_bulk_review_approval_candidates_path": str(
                    score_bulk_review_approval_candidates_path
                ),
                "score_bulk_review_approval_candidates_exists": (
                    score_bulk_review_approval_candidates_path.exists()
                ),
                "score_bulk_review_source_samples_path": str(
                    score_bulk_review_source_samples_path
                ),
                "score_bulk_review_source_samples_exists": (
                    score_bulk_review_source_samples_path.exists()
                ),
                "score_event_approval_source_samples_path": str(
                    score_event_approval_source_samples_path
                ),
                "score_event_approval_source_samples_exists": (
                    score_event_approval_source_samples_path.exists()
                ),
                "score_individual_review_source_samples_path": str(
                    score_individual_review_source_samples_path
                ),
                "score_individual_review_source_samples_exists": (
                    score_individual_review_source_samples_path.exists()
                ),
                "score_approval_source_sample_coverage_path": str(
                    score_approval_source_sample_coverage_path
                ),
                "score_approval_source_sample_coverage_exists": (
                    score_approval_source_sample_coverage_path.exists()
                ),
                "score_approval_target_scope_readiness_path": str(
                    score_approval_target_scope_readiness_path
                ),
                "score_approval_target_scope_readiness_exists": (
                    score_approval_target_scope_readiness_path.exists()
                ),
                "score_approval_materialization_plan_path": str(
                    score_approval_materialization_plan_path
                ),
                "score_approval_materialization_plan_exists": (
                    score_approval_materialization_plan_path.exists()
                ),
                "score_approval_materialization_batch_plan_path": str(
                    score_approval_materialization_batch_plan_path
                ),
                "score_approval_materialization_batch_plan_exists": (
                    score_approval_materialization_batch_plan_path.exists()
                ),
                "score_approval_materialization_batch_codex_review_path": str(
                    score_approval_materialization_batch_codex_review_path
                ),
                "score_approval_materialization_batch_codex_review_exists": (
                    score_approval_materialization_batch_codex_review_path.exists()
                ),
                "score_approval_materialization_batch_approval_gate_path": str(
                    score_approval_materialization_batch_approval_gate_path
                ),
                "score_approval_materialization_batch_approval_gate_exists": (
                    score_approval_materialization_batch_approval_gate_path.exists()
                ),
                "score_approval_materialization_batch_execution_preflight_path": str(
                    score_approval_materialization_batch_execution_preflight_path
                ),
                "score_approval_materialization_batch_execution_preflight_exists": (
                    score_approval_materialization_batch_execution_preflight_path.exists()
                ),
                "score_runtime_scope_approvals_path": str(
                    score_runtime_scope_approvals_path
                ),
                "score_runtime_scope_approvals_exists": (
                    score_runtime_scope_approvals_path.exists()
                ),
                "score_runtime_write_target_scope_path": str(
                    score_runtime_write_target_scope_path
                ),
                "score_runtime_write_target_scope_exists": (
                    score_runtime_write_target_scope_path.exists()
                ),
                "score_runtime_write_batch_plan_path": str(
                    score_runtime_write_batch_plan_path
                ),
                "score_runtime_write_batch_plan_exists": (
                    score_runtime_write_batch_plan_path.exists()
                ),
                "score_runtime_write_batch_approvals_path": str(
                    score_runtime_write_batch_approvals_path
                ),
                "score_runtime_write_batch_approvals_exists": (
                    score_runtime_write_batch_approvals_path.exists()
                ),
                "score_runtime_write_execution_path": str(
                    score_runtime_write_execution_path
                ),
                "score_runtime_write_execution_exists": (
                    score_runtime_write_execution_path.exists()
                ),
                "score_runtime_write_preflight_path": str(
                    score_runtime_write_preflight_path
                ),
                "score_runtime_write_preflight_exists": (
                    score_runtime_write_preflight_path.exists()
                ),
                "score_field_closure_path": str(score_field_closure_path),
                "score_field_closure_exists": score_field_closure_path.exists(),
                "trace_summary": score_trace.get("summary", {}),
                "gap_summary": score_gap_summary,
                "candidate_summary": score_candidate_summary,
                "candidate_dry_run_summary": score_candidate_dry_run_summary,
                "candidate_upsert_safety_summary": score_candidate_upsert_safety_summary,
                "candidate_staging_summary": score_candidate_staging_summary,
                "candidate_value_contracts_summary": score_candidate_value_contracts_summary,
                "spec_numeric_validity_summary": score_spec_numeric_validity_summary,
                "spec_score_conversion_summary": score_spec_score_conversion_summary,
                "score_conversion_remediation_summary": score_conversion_remediation_summary,
                "score_formula_policy_review_packets_summary": (
                    score_formula_policy_review_packets_summary
                ),
                "score_governance_suppression_summary": (
                    score_governance_suppression_summary
                ),
                "score_option_universe_na_summary": score_option_universe_na_summary,
                "candidate_generation_queue_summary": score_candidate_generation_queue_summary,
                "l0_source_readiness_summary": score_l0_source_readiness_summary,
                "short_report_evidence_summary": score_short_report_evidence_summary,
                "non_manual_readiness_summary": score_non_manual_readiness_summary,
                "event_text_draft_summary": score_event_text_draft_summary,
                "event_text_classification_inputs_summary": (
                    score_event_text_classification_inputs_summary
                ),
                "event_text_preclassification_screen_summary": (
                    score_event_text_preclassification_screen_summary
                ),
                "event_text_sufficiency_gate_summary": (
                    score_event_text_sufficiency_gate_summary
                ),
                "event_text_url_fetchability_summary": (
                    score_event_text_url_fetchability_summary
                ),
                "event_text_unknown_source_options_summary": (
                    score_event_text_unknown_source_options_summary
                ),
                "event_text_market_doc_evidence_summary": (
                    score_event_text_market_doc_evidence_summary
                ),
                "event_text_market_doc_review_packets_summary": (
                    score_event_text_market_doc_review_packets_summary
                ),
                "local_structured_draft_summary": score_local_structured_draft_summary,
                "local_structured_unknown_source_options_summary": (
                    score_local_structured_unknown_source_options_summary
                ),
                "local_structured_source_candidates_summary": (
                    score_local_structured_source_candidates_summary
                ),
                "local_structured_source_review_packets_summary": (
                    score_local_structured_source_review_packets_summary
                ),
                "local_structured_text_draft_summary": score_local_structured_text_draft_summary,
                "local_structured_text_unknown_source_options_summary": (
                    score_local_structured_text_unknown_source_options_summary
                ),
                "single_dependency_draft_summary": score_single_dependency_draft_summary,
                "single_dependency_unknown_source_options_summary": (
                    score_single_dependency_unknown_source_options_summary
                ),
                "single_dependency_unknown_source_options_rows": (
                    score_single_dependency_unknown_source_options_rows
                ),
                "manual_policy_draft_summary": score_manual_policy_draft_summary,
                "manual_policy_unknown_source_options_summary": (
                    score_manual_policy_unknown_source_options_summary
                ),
                "review_staging_manifest_summary": score_review_staging_manifest_summary,
                "deterministic_runtime_approvals_summary": (
                    score_deterministic_runtime_approvals_summary
                ),
                "review_approval_gate_summary": score_review_approval_gate_summary,
                "completion_next_actions_summary": score_completion_next_actions_summary,
                "approval_cross_report_consistency_error_count": len(
                    score_approval_consistency_errors
                ),
                "approval_cross_report_consistency_errors": (
                    score_approval_consistency_errors
                ),
                "unknown_closure_matrix_summary": score_unknown_closure_matrix_summary,
                "unknown_acquisition_backlog_summary": (
                    score_unknown_acquisition_backlog_summary
                ),
                "unknown_market_doc_acquisition_summary": (
                    score_unknown_market_doc_acquisition_summary
                ),
                "unknown_event_evidence_adjudication_summary": (
                    score_unknown_event_evidence_adjudication_summary
                ),
                "unknown_event_strict_source_gate_summary": (
                    score_unknown_event_strict_source_gate_summary
                ),
                "unknown_event_strict_review_packets_summary": (
                    score_unknown_event_strict_review_packets_summary
                ),
                "unknown_event_primary_source_confirmation_summary": (
                    score_unknown_event_primary_source_confirmation_summary
                ),
                "unknown_event_external_source_confirmation_summary": (
                    score_unknown_event_external_source_confirmation_summary
                ),
                "unknown_local_formula_acquisition_summary": (
                    score_unknown_local_formula_acquisition_summary
                ),
                "unknown_local_formula_review_packets_summary": (
                    score_unknown_local_formula_review_packets_summary
                ),
                "local_formula_source_capability_summary": (
                    score_local_formula_source_capability_summary
                ),
                "unknown_external_business_metric_acquisition_summary": (
                    score_unknown_external_business_metric_acquisition_summary
                ),
                "unknown_external_business_metric_market_doc_summary": (
                    score_unknown_external_business_metric_market_doc_summary
                ),
                "unknown_external_business_metric_review_packets_summary": (
                    score_unknown_external_business_metric_review_packets_summary
                ),
                "unknown_external_business_metric_readiness_queue_summary": (
                    score_unknown_external_business_metric_readiness_queue_summary
                ),
                "unknown_external_business_metric_policy_drafts_summary": (
                    score_unknown_external_business_metric_policy_drafts_summary
                ),
                "unknown_external_business_metric_value_candidates_summary": (
                    score_unknown_external_business_metric_value_candidates_summary
                ),
                "unknown_external_business_metric_value_review_packets_summary": (
                    score_unknown_external_business_metric_value_review_packets_summary
                ),
                "unknown_business_metric_value_selection_gate_summary": (
                    score_unknown_business_metric_value_selection_gate_summary
                ),
                "unknown_penetration_value_priority_summary": (
                    score_unknown_penetration_value_priority_summary
                ),
                "unknown_penetration_p1_source_confirmation_summary": (
                    score_unknown_penetration_p1_source_confirmation_summary
                ),
                "unknown_penetration_value_policy_draft_summary": (
                    score_unknown_penetration_value_policy_draft_summary
                ),
                "unknown_penetration_value_confirmation_packets_summary": (
                    score_unknown_penetration_value_confirmation_packets_summary
                ),
                "unknown_penetration_value_confirmation_templates_summary": (
                    score_unknown_penetration_value_confirmation_templates_summary
                ),
                "unknown_penetration_value_confirmation_gate_summary": (
                    score_unknown_penetration_value_confirmation_gate_summary
                ),
                "unknown_penetration_confirmed_known_drafts_summary": (
                    score_unknown_penetration_confirmed_known_drafts_summary
                ),
                "approval_review_packets_summary": score_approval_review_packets_summary,
                "approval_packet_risk_review_summary": (
                    score_approval_packet_risk_review_summary
                ),
                "bulk_review_approval_candidates_summary": (
                    score_bulk_review_approval_candidates_summary
                ),
                "bulk_review_source_samples_summary": (
                    score_bulk_review_source_samples_summary
                ),
                "event_approval_source_samples_summary": (
                    score_event_approval_source_samples_summary
                ),
                "individual_review_source_samples_summary": (
                    score_individual_review_source_samples_summary
                ),
                "approval_source_sample_coverage_summary": (
                    score_approval_source_sample_coverage_summary
                ),
                "approval_target_scope_readiness_summary": (
                    score_approval_target_scope_readiness_summary
                ),
                "approval_materialization_plan_summary": (
                    score_approval_materialization_plan_summary
                ),
                "approval_materialization_batch_plan_summary": (
                    score_approval_materialization_batch_plan_summary
                ),
                "approval_materialization_batch_codex_review_summary": (
                    score_approval_materialization_batch_codex_review_summary
                ),
                "approval_materialization_batch_approval_gate_summary": (
                    score_approval_materialization_batch_approval_gate_summary
                ),
                "approval_materialization_batch_execution_preflight_summary": (
                    score_approval_materialization_batch_execution_preflight_summary
                ),
                "runtime_scope_approvals_summary": (
                    score_runtime_scope_approvals_summary
                ),
                "runtime_write_target_scope_summary": (
                    score_runtime_write_target_scope_summary
                ),
                "runtime_write_batch_plan_summary": (
                    score_runtime_write_batch_plan_summary
                ),
                "runtime_write_batch_approvals_summary": (
                    score_runtime_write_batch_approvals_summary
                ),
                "runtime_write_execution_summary": (
                    score_runtime_write_execution_summary
                ),
                "runtime_write_preflight_summary": (
                    score_runtime_write_preflight_summary
                ),
                "field_closure_summary": score_field_closure_summary,
            },
            score_gap_remaining,
        ),
        _line(
            "frontend_bff_hot_path_latency",
            "Verify audited user-facing hot paths stay under 1 second",
            _status(
                bff_ok
                and bff_concurrent_ok
                and frontend_browser_ok
                and frontend_shell_ok
                and frontend_navigation_ok
                and frontend_stock_detail_probe_ok
            ),
            (
                "machine_bff_latency_plus_machine_browser_qa_plus_spa_shell_latency_plus_navigation_contract_plus_stock_detail_probe_plus_bff_concurrent_probe"
                if frontend_navigation_ok
                else "machine_bff_latency_plus_machine_browser_qa_plus_spa_shell_latency"
            ),
            {
                **_artifact(bff_latency_path),
                "frontend_browser_path": str(frontend_browser_path),
                "frontend_browser_exists": frontend_browser_path.exists(),
                "frontend_shell_path": str(frontend_shell_path),
                "frontend_shell_exists": frontend_shell_path.exists(),
                "frontend_navigation_path": str(frontend_navigation_path),
                "frontend_navigation_exists": frontend_navigation_path.exists(),
                "frontend_stock_detail_probe_path": str(
                    frontend_stock_detail_probe_path
                ),
                "frontend_stock_detail_probe_exists": (
                    frontend_stock_detail_probe_path.exists()
                ),
                "bff_concurrent_probe_path": str(bff_concurrent_probe_path),
                "bff_concurrent_probe_exists": bff_concurrent_probe_path.exists(),
                "bff_all_ok": bff_latency.get("all_ok"),
                "bff_all_under_threshold": bff_latency.get("all_under_threshold"),
                "max_observed_ms": bff_latency.get("max_observed_ms"),
                "bff_concurrent_ok": bff_concurrent_ok,
                "bff_concurrent_probe_summary": bff_concurrent_probe_summary,
                "frontend_shell_ok": frontend_shell_ok,
                "frontend_shell_all_ok": frontend_shell.get("all_ok"),
                "frontend_shell_all_under_threshold": frontend_shell.get(
                    "all_under_threshold"
                ),
                "frontend_shell_route_count": frontend_shell.get("route_count"),
                "frontend_shell_max_observed_ms": frontend_shell.get(
                    "max_observed_ms"
                ),
                "frontend_navigation_ok": frontend_navigation_ok,
                "frontend_navigation_summary": frontend_navigation.get("summary", {}),
                "frontend_all_warm_under_threshold": frontend_browser.get(
                    "all_warm_under_threshold"
                ),
                "frontend_legacy_ok": frontend_browser_legacy_ok,
                "frontend_latest_recheck_ok": frontend_latest_ok,
                "frontend_latest_recheck_measurement": frontend_latest_recheck.get("measurement"),
                "frontend_stock_detail_probe_ok": frontend_stock_detail_probe_ok,
                "frontend_stock_detail_probe_summary": (
                    frontend_stock_detail_probe_summary
                ),
                "frontend_browser_summary": frontend_browser_summary,
                "frontend_latest_recheck_routes": frontend_latest_routes,
                "frontend_routes": frontend_browser.get("routes", {}),
            },
            (
                "BFF latency, BFF concurrent hot-path probe, browser first-H1 checks, StockDetail path-graph probe, SPA shell latency, and source navigation contract cover the audited Project ULT route/navigation surface; residual risk is browser/device-specific edge cases."
                if frontend_navigation_ok
                else "Browser QA and SPA shell latency now cover audited Project ULT direct routes; they still do not prove every possible frontend interaction."
            ),
        ),
        _line(
            "module_status_classification",
            "Classify locked modules and local runtime/data/tooling surfaces",
            _status(
                bool(
                    module_counts.get("locked_total")
                    and module_local_counts.get("local_total")
                    and module_combined_counts.get("inventory_total")
                )
            ),
            "lockfile_latency_local_runtime_and_data_evidence",
            {
                **_artifact(module_status_path),
                **module_counts,
                "local_surface_counts": module_local_counts,
                "combined_inventory_counts": module_combined_counts,
                "classification_policy": module_classification_policy,
                "runtime_evidence_policy": module_runtime_evidence_policy,
            },
            "Classifies locked upstream modules and local surfaces; does not turn skeleton adapters into full services.",
        ),
    ]

    incomplete_rows = [
        row for row in rows
        if row["status"] != "covered"
        or (
            row["requirement_id"] == "a_share_score_field_path"
            and str(row["evidence_strength"]).startswith("runtime_trace")
        )
        or row["evidence_strength"] in {
            "metadata_full_walk_plus_bounded_text_body_read",
            "all_csv_file_head_tail_evidence_plus_signature_stratified_bounded_semantic_rows",
            "all_csv_file_head_tail_evidence_plus_signature_stratified_bounded_semantic_rows_plus_partial_full_row_scan",
            "bounded_real_row_semantic_sample",
            "count_all_parse_bounded_entity_event_signal_samples",
            "runtime_trace_and_gap_priority",
            "runtime_trace_gap_priority_and_candidate_evidence",
            "runtime_trace_gap_priority_candidate_evidence_and_field_closure",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_and_bridge_dry_run",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_and_upsert_safety",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_and_staging_payloads",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_and_value_contracts",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_and_generation_queue",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_and_non_manual_readiness",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_and_single_dependency_drafts",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_and_manual_policy_draft_pilot",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_non_manual_readiness_and_manual_policy_draft_pilot",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_non_manual_readiness_and_single_dependency_drafts",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_single_dependency_drafts_and_manual_policy_draft_pilot",
            "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_non_manual_readiness_single_dependency_drafts_and_manual_policy_draft_pilot",
            "machine_bff_latency_plus_machine_browser_qa",
            "machine_bff_latency_plus_machine_browser_qa_plus_spa_shell_latency",
        }
    ]
    completion_blockers = []
    if not repo_binary_semantics_complete:
        completion_blockers.append(
            "repo binary/large files are fully head/tail fingerprinted, but type-aware semantic classification remains incomplete"
        )
    if not dockcase_full_scan_complete:
        completion_blockers.append(
            (
                "DOCKCASE CSV semantic review is signature-stratified and evidence-backed, "
                "with a ranked backlog, accumulated deep-sampled backlog batches, and partial full-row scan progress, "
                "but not exhaustive across every CSV row/file"
            )
        )
    if score_actionable_gaps:
        completion_blockers.append(
            (
                f"A-share score field trace still reports {score_actionable_gaps} actionable participating gaps "
                f"({score_candidate_ready} candidate-ready, {score_dry_run_ready} bridge-dry-run ready, "
                f"{score_upsert_review_gated} review-gated, {score_staging_payloads} deterministic staging payloads, "
                f"{score_conversion_ready} spec score-conversion path-ready, "
                f"{score_conversion_unresolved} spec score-conversion unresolved, "
                f"{score_conversion_no_formula} spec score-conversion formula/normalizer gaps, "
                f"{score_conversion_no_input} spec score-conversion missing-current-input gaps, "
                f"{score_conversion_review_backed} spec score-conversion review-decision-backed not-ready fields, "
                f"{score_conversion_formula_review} spec score-conversion formula-policy review-required fields, "
                f"{score_conversion_governance_verified} spec score-conversion governance-suppression verified fields, "
                f"{score_conversion_option_verified} spec score-conversion option-universe/N/A verified fields, "
                f"{score_conversion_unclassified} spec score-conversion unclassified gaps, "
                f"{score_remediation_formula_policy} remediation formula-policy/peer-context rows, "
                f"{score_remediation_governance} remediation governed-or-duplicate rows, "
                f"{score_remediation_missing_source} remediation listed-option-source/N/A rows, "
                f"{score_remediation_safe_formula} remediation safe formula-now rows, "
                f"{score_formula_policy_packets} formula-policy review packets, "
                f"{score_formula_policy_replacement_ready} formula-policy replacement-ready paths, "
                f"{score_formula_policy_direct_ready} formula-policy direct-ready formulas, "
                f"{score_governance_suppression_packets} governance-suppression packets, "
                f"{score_governance_suppression_verified} governance suppressions verified, "
                f"{score_governance_replacement_ready} governance replacement/canonical-ready paths, "
                f"{score_option_packets} option-universe/N/A packets, "
                f"{score_option_no_current_inputs} option rows with no current A-share input, "
                f"{score_option_known_allowed} option Known values allowed now, "
                f"{score_option_contract_valid} option verification contracts valid, "
                f"{score_option_prod_writes} option production writes, "
                f"{score_staging_generator_required} generator-required, {score_contract_valid} valid value contracts, "
                f"{score_contract_invalid} invalid value contracts, {score_generation_tasks} queued generator tasks, "
                f"{score_l0_source_blocking_gaps} l0 source-readiness blocking gaps, "
                f"{score_l0_source_p2} l0 source-readiness P2 rows, "
                f"{score_l0_source_p3} l0 source-readiness P3 rows, "
                f"{score_l0_source_event_route} l0 source-readiness event/news routes, "
                f"{score_l0_source_local_route} l0 source-readiness local closed-loop routes, "
                f"{score_l0_source_manual_route} l0 source-readiness manual-design routes, "
                f"{score_l0_source_direct_tushare_remaining} l0 source-readiness direct structured Tushare remaining, "
                f"{score_l0_source_runtime_rows} l0 source-readiness dependency runtime rows, "
                f"{score_l0_source_missing_runtime_rows} l0 source-readiness missing runtime rows, "
                f"{score_short_report_files_scanned} short-report evidence HTML files scanned, "
                f"{score_short_report_parse_errors} short-report evidence parse errors, "
                f"{score_short_report_strict_docs} short-report evidence strict documents, "
                f"{score_short_report_direct_docs} short-report evidence direct A-share documents, "
                f"{score_short_report_foreign_docs} short-report evidence foreign/market-only documents, "
                f"{score_short_report_direct_ts_codes} short-report evidence direct A-share ts_codes, "
                f"{score_short_report_candidate_ready} short-report candidate evidence ready, "
                f"{score_non_manual_tasks} non-manual tasks readiness-checked, "
                f"{score_non_manual_bridge_ready} non-manual bridge probes ready, "
                f"{score_non_manual_deterministic} non-manual deterministic Known drafts, "
                f"{score_event_text_known}/{score_event_text_tasks} event-text Known drafts, "
                f"{score_event_text_review_required} event-text review-required drafts, "
                f"{score_event_text_contract_valid} event-text draft contracts valid, "
                f"{score_event_text_contract_invalid} event-text draft contracts invalid, "
                f"{score_event_text_bridge} event-text drafts bridge-ready, "
                f"{score_event_text_safe_upsert} event-text safe auto-upsert, "
                f"{score_event_text_prod_writes} event-text production writes, "
                f"{score_event_text_input_packets} event-text classification input packets, "
                f"{score_event_text_input_ready} event-text classification inputs ready, "
                f"{score_event_text_input_missing} event-text missing headline inputs, "
                f"{score_event_text_headlines} event-text headline inputs, "
                f"{score_event_text_unique_headlines} event-text unique headlines, "
                f"{score_event_text_full_text} event-text full-text packets, "
                f"{score_event_text_title_only} event-text title-level-only packets, "
                f"{score_event_text_classified_known} event-text classified Known packets, "
                f"{score_event_text_input_prod_writes} event-text classification production writes, "
                f"{score_event_text_pre_packets} event-text preclassification packets, "
                f"{score_event_text_pre_screened} event-text preclassification packets screened, "
                f"{score_event_text_pre_target_hits} event-text target-keyword-hit packets, "
                f"{score_event_text_pre_transmission_hits} event-text A-share transmission keyword-hit packets, "
                f"{score_event_text_pre_target_and_transmission} event-text target-and-transmission keyword-hit packets, "
                f"{score_event_text_pre_direct_known} event-text direct Known candidates allowed, "
                f"{score_event_text_pre_review_required} event-text preclassification review-required packets, "
                f"{score_event_text_pre_prod_writes} event-text preclassification production writes, "
                f"{score_event_text_suff_packets} event-text sufficiency-gate packets, "
                f"{score_event_text_suff_target_headlines} event-text sufficiency target-headline packets, "
                f"{score_event_text_suff_broad_only} event-text broad-market-only transmission packets, "
                f"{score_event_text_suff_same_any} event-text same-headline target+any-transmission packets, "
                f"{score_event_text_suff_same_direct} event-text same-headline target+direct-transmission packets, "
                f"{score_event_text_suff_classifier_ready} event-text title-signal-sufficient classifier candidates, "
                f"{score_event_text_suff_known_allowed} event-text sufficiency Known candidates allowed, "
                f"{score_event_text_suff_prod_writes} event-text sufficiency production writes, "
                f"{score_event_text_url_fetch_success}/{score_event_text_url_unique} event-text URLs fetchable, "
                f"{score_event_text_url_primary_text} event-text URLs with primary text, "
                f"{score_event_text_body_packets} event-text body packets checked, "
                f"{score_event_text_body_target_hits} event-text body target-hit packets, "
                f"{score_event_text_body_direct_hits} event-text body direct-transmission-hit packets, "
                f"{score_event_text_body_classifier_ready} event-text body-signal-sufficient classifier candidates, "
                f"{score_event_text_body_known_allowed} event-text body Known candidates allowed, "
                f"{score_event_text_body_prod_writes} event-text body production writes, "
                f"{score_event_text_unknown_options} event-text unknown source-option rows, "
                f"{score_event_text_unknown_input_ready} event-text unknown classification inputs ready, "
                f"{score_event_text_unknown_body_ready} event-text unknown body texts available, "
                f"{score_event_text_unknown_target_present} event-text unknown target-event evidence present, "
                f"{score_event_text_unknown_direct_present} event-text unknown direct A-share transmission present, "
                f"{score_event_text_unknown_broad_only} event-text unknown broad-market-only transmission rows, "
                f"{score_event_text_unknown_classifier_ready} event-text unknown classifier-ready review candidates, "
                f"{score_event_text_unknown_target_required} event-text target-event evidence required, "
                f"{score_event_text_unknown_direct_required} event-text direct A-share transmission required, "
                f"{score_event_text_unknown_auto_known} event-text unknown auto Known candidates, "
                f"{score_event_text_unknown_prod_writes} event-text unknown source-option production writes, "
                f"{score_event_text_market_doc_checked} event-text market-doc rows checked, "
                f"{score_event_text_market_doc_files} event-text market-doc HTML files scanned, "
                f"{score_event_text_market_doc_read_errors} event-text market-doc read errors, "
                f"{score_event_text_market_doc_target} event-text market-doc target-evidence rows, "
                f"{score_event_text_market_doc_direct} event-text market-doc direct-transmission rows, "
                f"{score_event_text_market_doc_target_direct} event-text market-doc target+direct rows, "
                f"{score_event_text_market_doc_same_sentence} event-text market-doc same-sentence candidates, "
                f"{score_event_text_market_doc_target_required} event-text market-doc target evidence still required, "
                f"{score_event_text_market_doc_direct_required} event-text market-doc direct links still required, "
                f"{score_event_text_market_doc_review_candidates} event-text market-doc review candidates, "
                f"{score_event_text_market_doc_auto_known} event-text market-doc auto Known candidates, "
                f"{score_event_text_market_doc_prod_writes} event-text market-doc production writes, "
                f"{score_event_text_market_doc_packet_count} event-text market-doc review packets, "
                f"{score_event_text_market_doc_packet_ready} event-text market-doc review-ready packets, "
                f"{score_event_text_market_doc_packet_target_required} event-text market-doc packet target evidence required, "
                f"{score_event_text_market_doc_packet_direct_required} event-text market-doc packet direct links required, "
                f"{score_event_text_market_doc_packet_examples} event-text market-doc packet candidate examples, "
                f"{score_event_text_market_doc_packet_contract_valid} event-text market-doc packet contracts valid, "
                f"{score_event_text_market_doc_packet_contract_invalid} event-text market-doc packet contracts invalid, "
                f"{score_event_text_market_doc_packet_auto_known} event-text market-doc packet auto Known candidates, "
                f"{score_event_text_market_doc_packet_prod_writes} event-text market-doc packet production writes, "
                f"{score_local_structured_known}/{score_local_structured_tasks} local-structured Known drafts, "
                f"{score_local_structured_review_required} local-structured review-required drafts, "
                f"{score_local_structured_contract_valid} local-structured draft contracts valid, "
                f"{score_local_structured_contract_invalid} local-structured draft contracts invalid, "
                f"{score_local_structured_bridge} local-structured drafts bridge-ready, "
                f"{score_local_structured_safe_upsert} local-structured safe auto-upsert, "
                f"{score_local_structured_prod_writes} local-structured production writes, "
                f"{score_local_structured_unknown_options} local-structured unknown source-option rows, "
                f"{score_local_structured_unknown_runtime_ready} local-structured unknown runtime dependencies ready, "
                f"{score_local_structured_unknown_direct_ready} local-structured direct source-ready rows, "
                f"{score_local_structured_unknown_overlay_hints} local-structured overlay/source hints, "
                f"{score_local_structured_unknown_new_mapping} local-structured new mappings required, "
                f"{score_local_structured_unknown_review_policy} local-structured reviewed policies required, "
                f"{score_local_structured_unknown_partial_unlock} local-structured partial Known unlock candidates, "
                f"{score_local_structured_unknown_auto_known} local-structured auto Known candidates, "
                f"{score_local_structured_unknown_prod_writes} local-structured unknown source-option production writes, "
                f"{score_local_structured_source_candidates_unknown} local-structured source-candidate rows, "
                f"{score_local_structured_source_candidates_runtime_ready} local-structured source-candidate runtime dependencies ready, "
                f"{score_local_structured_source_candidates_direct_known} local-structured source-candidate direct Known-ready rows, "
                f"{score_local_structured_source_candidates_review_dp} local-structured source-candidate review/source rows, "
                f"{score_local_structured_source_candidates_review_matches} local-structured source-candidate review matches, "
                f"{score_local_structured_source_candidates_supporting_matches} local-structured source-candidate supporting matches, "
                f"{score_local_structured_source_candidates_empty_matches} local-structured source-candidate empty matches, "
                f"{score_local_structured_source_candidates_no_source} local-structured source-candidate no-direct-source rows, "
                f"{score_local_structured_source_candidates_false_positive} local-structured source-candidate false positives excluded, "
                f"{score_local_structured_source_candidates_prod_writes} local-structured source-candidate production writes, "
                f"{score_local_structured_source_review_packets_total} local-structured source-review packets, "
                f"{score_local_structured_source_review_packets_ready} local-structured source-review lease/rent review-ready packets, "
                f"{score_local_structured_source_review_packets_quantity} local-structured source-review quantity-needed ASP packets, "
                f"{score_local_structured_source_review_packets_external} local-structured source-review external-source-required packets, "
                f"{score_local_structured_source_review_packets_direct_known} local-structured source-review direct Known-ready packets, "
                f"{score_local_structured_source_review_packets_formula_ready} local-structured source-review formula-ready packets, "
                f"{score_local_structured_source_review_packets_candidate} local-structured source-review candidate-column packets, "
                f"{score_local_structured_source_review_packets_contract_valid} local-structured source-review packet contracts valid, "
                f"{score_local_structured_source_review_packets_contract_invalid} local-structured source-review packet contracts invalid, "
                f"{score_local_structured_source_review_packets_prod_writes} local-structured source-review production writes, "
                f"{score_local_structured_text_known}/{score_local_structured_text_tasks} local-structured-text Known drafts, "
                f"{score_local_structured_text_review_required} local-structured-text review-required drafts, "
                f"{score_local_structured_text_contract_valid} local-structured-text draft contracts valid, "
                f"{score_local_structured_text_contract_invalid} local-structured-text draft contracts invalid, "
                f"{score_local_structured_text_bridge} local-structured-text drafts bridge-ready, "
                f"{score_local_structured_text_safe_upsert} local-structured-text safe auto-upsert, "
                f"{score_local_structured_text_prod_writes} local-structured-text production writes, "
                f"{score_local_structured_text_unknown_options} local-structured-text unknown source-option rows, "
                f"{score_local_structured_text_unknown_runtime_ready} local-structured-text unknown runtime dependencies ready, "
                f"{score_local_structured_text_unknown_qa_ready} local-structured-text QA recent dependencies ready, "
                f"{score_local_structured_text_unknown_classified} local-structured-text direct text-classification-ready rows, "
                f"{score_local_structured_text_unknown_overlay_hints} local-structured-text overlay/source hints, "
                f"{score_local_structured_text_unknown_text_required} local-structured-text text classifications required, "
                f"{score_local_structured_text_unknown_auto_known} local-structured-text auto Known candidates, "
                f"{score_local_structured_text_unknown_prod_writes} local-structured-text unknown source-option production writes, "
                f"{score_single_dependency_known}/{score_single_dependency_tasks} single-dependency Known drafts, "
                f"{score_single_dependency_review_required} single-dependency review-required drafts, "
                f"{score_single_dependency_contract_valid} single-dependency draft contracts valid, "
                f"{score_single_dependency_contract_invalid} single-dependency draft contracts invalid, "
                f"{score_single_dependency_bridge} single-dependency drafts bridge-ready, "
                f"{score_single_dependency_safe_upsert} single-dependency safe auto-upsert, "
                f"{score_single_dependency_prod_writes} single-dependency production writes, "
                f"{score_single_dependency_unknown_options} single-dependency unknown source-option rows, "
                f"{score_single_dependency_unknown_runtime_ready} single-dependency unknown runtime dependencies ready, "
                f"{score_single_dependency_unknown_direct_ready} single-dependency direct replacement-cycle source-ready rows, "
                f"{score_single_dependency_unknown_overlay_hints} single-dependency overlay/source hints, "
                f"{score_single_dependency_unknown_overlay_lifecycle_context} single-dependency rows with overlay lifecycle context candidates, "
                f"{score_single_dependency_unknown_overlay_lifecycle_known} single-dependency overlay lifecycle Known nodes, "
                f"{score_single_dependency_unknown_overlay_replacement_known} single-dependency overlay replacement Known nodes, "
                f"{score_single_dependency_unknown_overlay_replacement_unknown} single-dependency overlay replacement Unknown nodes, "
                f"{score_single_dependency_unknown_lifecycle_required} single-dependency lifecycle sources required, "
                f"{score_single_dependency_unknown_review_policy} single-dependency reviewed policies required, "
                f"{score_single_dependency_unknown_lifecycle_templates} single-dependency lifecycle-policy review templates, "
                f"{score_single_dependency_unknown_lifecycle_templates_valid} single-dependency lifecycle-policy review template contracts valid, "
                f"{score_single_dependency_unknown_lifecycle_templates_invalid} single-dependency lifecycle-policy review template contracts invalid, "
                f"{score_single_dependency_unknown_lifecycle_templates_blank} single-dependency lifecycle-policy review templates blank-pending, "
                f"{score_single_dependency_unknown_lifecycle_templates_input_ready} single-dependency lifecycle-policy review template inputs ready, "
                f"{score_single_dependency_unknown_auto_known} single-dependency auto Known candidates, "
                f"{score_single_dependency_unknown_known_sufficient} single-dependency Known-draft-sufficient rows, "
                f"{score_single_dependency_unknown_approval_ready} single-dependency approval-ready rows, "
                f"{score_single_dependency_unknown_prod_writes} single-dependency unknown source-option production writes, "
                f"{score_manual_policy_known}/{score_manual_policy_tasks} manual-policy Known drafts, "
                f"{score_manual_policy_contract_valid} manual-policy draft contracts valid, "
                f"{score_manual_policy_contract_invalid} manual-policy draft contracts invalid, "
                f"{score_manual_policy_bridge} manual-policy drafts bridge-ready, "
                f"{score_manual_policy_safe_upsert} manual-policy safe auto-upsert, "
                f"{score_manual_policy_unknown_options} manual-policy unknown source-option rows, "
                f"{score_manual_policy_unknown_dependency_ready} manual-policy unknown dependency packs ready, "
                f"{score_manual_policy_unknown_assumption_ready} manual-policy direct reviewed-assumption-ready rows, "
                f"{score_manual_policy_unknown_required_assumptions} manual-policy required assumptions, "
                f"{score_manual_policy_unknown_assumption_review} manual-policy assumption reviews required, "
                f"{score_manual_policy_unknown_review_policy} manual-policy reviewed policies required, "
                f"{score_manual_policy_unknown_auto_known} manual-policy auto Known candidates, "
                f"{score_manual_policy_unknown_prod_writes} manual-policy unknown source-option production writes, "
                f"{score_review_manifest_entries} review-manifest entries, "
                f"{score_review_manifest_concrete} review-manifest concrete-ready, "
                f"{score_review_manifest_unknown} review-manifest Unknown-gated, "
                f"{score_review_manifest_contract_valid} review-manifest contracts valid, "
                f"{score_review_manifest_contract_invalid} review-manifest contracts invalid, "
                f"{score_review_manifest_bridge_ready} review-manifest concrete bridge-ready, "
                f"{score_review_manifest_safe_upsert} review-manifest safe auto-upsert, "
                f"{score_review_manifest_prod_writes} review-manifest production writes, "
                f"{score_review_manifest_approved_writes} review-manifest approved runtime writes, "
                f"{score_review_approval_required} approval-gate required approvals, "
                f"{score_deterministic_approval_records} deterministic approval records, "
                f"{score_deterministic_approved_writes} deterministic approved runtime writes, "
                f"{score_deterministic_prod_writes} deterministic approval production writes, "
                f"{score_review_approval_records} approval-gate records seen, "
                f"{score_review_approval_missing} approval-gate missing approvals, "
                f"{score_review_approval_rejected} approval-gate rejected approvals, "
                f"{score_review_approval_approved_writes} approval-gate approved runtime writes, "
                f"{score_review_approval_write_plan} approval-gate write-plan entries, "
                f"{score_review_approval_unknown} approval-gate Unknown not approvable, "
                f"{score_review_approval_safe_upsert} approval-gate safe auto-upsert, "
                f"{score_review_approval_prod_writes} approval-gate production writes, "
                f"{score_next_action_total} completion next-actions, "
                f"{score_next_action_approval_ready} completion human approvals, "
                f"{score_next_action_runtime_ready} completion runtime write-plan-ready packets, "
                f"{score_next_action_unknown} completion Unknown resolutions, "
                f"{score_next_action_event_text} completion event-text classifications, "
                f"{score_next_action_local_structured} completion local structured mappings, "
                f"{score_next_action_structured_text} completion structured-text extractions, "
                f"{score_next_action_single_dependency} completion single-dependency policies, "
                f"{score_next_action_manual} completion manual assumption reviews, "
                f"{score_next_action_templates} completion approval templates, "
                f"{score_next_action_approved_writes} completion approved runtime writes, "
                f"{score_next_action_write_plan} completion write-plan entries, "
                f"{score_next_action_prod_writes} completion production writes, "
                f"{score_unknown_closure_rows} unknown closure rows, "
                f"{score_unknown_closure_assigned} unknown closure routes assigned, "
                f"{score_unknown_closure_missing} unknown closure routes missing, "
                f"{score_unknown_closure_event_text} unknown closure event-text classifications, "
                f"{score_unknown_closure_local_structured} unknown closure local structured mappings, "
                f"{score_unknown_closure_structured_text} unknown closure structured-text extractions, "
                f"{score_unknown_closure_single_dependency} unknown closure single-dependency policies, "
                f"{score_unknown_closure_manual} unknown closure manual assumption reviews, "
                f"{score_unknown_closure_auto_known} unknown closure auto Known-ready rows, "
                f"{score_unknown_closure_approval_ready} unknown closure approval-ready rows, "
                f"{score_unknown_closure_contract_valid} unknown closure contracts valid, "
                f"{score_unknown_closure_contract_invalid} unknown closure contracts invalid, "
                f"{score_unknown_closure_prod_writes} unknown closure production writes, "
                f"{score_unknown_acquisition_tasks} unknown acquisition tasks, "
                f"{score_unknown_acquisition_event_doc} unknown acquisition market-doc searches, "
                f"{score_unknown_acquisition_local_formula} unknown acquisition local formula-source tasks, "
                f"{score_unknown_acquisition_external_business} unknown acquisition external/text business-metric tasks, "
                f"{score_unknown_acquisition_existing_evidence} unknown acquisition tasks with existing candidate evidence, "
                f"{score_unknown_acquisition_overlay_hints} unknown acquisition tasks with runtime overlay hints, "
                f"{score_unknown_acquisition_web_external} unknown acquisition tasks requiring web/external or deeper source acquisition, "
                f"{score_unknown_acquisition_llm_allowed} unknown acquisition LLM extraction/classification-only tasks, "
                f"{score_unknown_acquisition_formula_ready} unknown acquisition formula-ready tasks, "
                f"{score_unknown_acquisition_auto_known} unknown acquisition auto Known-ready tasks, "
                f"{score_unknown_acquisition_approval_ready} unknown acquisition approval-ready tasks, "
                f"{score_unknown_acquisition_contract_valid} unknown acquisition task contracts valid, "
                f"{score_unknown_acquisition_contract_invalid} unknown acquisition task contracts invalid, "
                f"{score_unknown_acquisition_prod_writes} unknown acquisition production writes, "
                f"{score_unknown_market_doc_tasks} unknown market-doc acquisition tasks, "
                f"{score_unknown_market_doc_files} unknown market-doc acquisition HTML files scanned, "
                f"{score_unknown_market_doc_read_errors} unknown market-doc acquisition read errors, "
                f"{score_unknown_market_doc_review_rows} unknown market-doc acquisition rows with review candidates, "
                f"{score_unknown_market_doc_new_entrant_windows} unknown market-doc new-entrant window candidate documents, "
                f"{score_unknown_market_doc_new_entrant_review} unknown market-doc new-entrant review candidate snippets, "
                f"{score_unknown_market_doc_substitute_same_sentence} unknown market-doc substitute-tech same-sentence candidate documents, "
                f"{score_unknown_market_doc_substitute_clean} unknown market-doc substitute-tech clean-risk review candidate snippets, "
                f"{score_unknown_market_doc_weak} unknown market-doc weak candidates, "
                f"{score_unknown_market_doc_rejected} unknown market-doc rejected candidates, "
                f"{score_unknown_market_doc_known_sufficient} unknown market-doc Known-draft-sufficient rows, "
                f"{score_unknown_market_doc_prod_writes} unknown market-doc production writes, "
                f"{score_unknown_event_adjudication_rows} unknown event adjudication rows, "
                f"{score_unknown_event_adjudication_examples} unknown event retained candidates adjudicated, "
                f"{score_unknown_event_adjudication_accepted} unknown event accepted candidates, "
                f"{score_unknown_event_adjudication_rejected} unknown event rejected/ambiguous candidates, "
                f"{score_unknown_event_adjudication_remaining} unknown event rows still Unknown, "
                f"{score_unknown_event_adjudication_known} unknown event Known-draft-sufficient rows, "
                f"{score_unknown_event_adjudication_contract_valid} unknown event adjudication contracts valid, "
                f"{score_unknown_event_adjudication_contract_invalid} unknown event adjudication contracts invalid, "
                f"{score_unknown_event_adjudication_prod_writes} unknown event adjudication production writes, "
                f"{score_unknown_event_strict_rows} unknown event strict-source rows, "
                f"{score_unknown_event_strict_files} unknown event strict-source HTML files scanned, "
                f"{score_unknown_event_strict_read_errors} unknown event strict-source read errors, "
                f"{score_unknown_event_strict_candidates} unknown event strict-source candidates, "
                f"{score_unknown_event_strict_review_candidates} unknown event strict-source review candidates, "
                f"{score_unknown_event_strict_rejected} unknown event strict-source rejected candidates, "
                f"{score_unknown_event_strict_rows_with_review} unknown event strict-source rows with review candidates, "
                f"{score_unknown_event_strict_rows_without_source} unknown event strict-source rows without source candidates, "
                f"{score_unknown_event_strict_classifier_ready} unknown event strict-source classifier-ready rows, "
                f"{score_unknown_event_strict_known} unknown event strict-source Known-draft-sufficient rows, "
                f"{score_unknown_event_strict_approval_ready} unknown event strict-source approval-ready rows, "
                f"{score_unknown_event_strict_contract_valid} unknown event strict-source contracts valid, "
                f"{score_unknown_event_strict_contract_invalid} unknown event strict-source contracts invalid, "
                f"{score_unknown_event_strict_prod_writes} unknown event strict-source production writes, "
                f"{score_unknown_event_strict_review_packet_count} unknown event strict-review packets, "
                f"{score_unknown_event_strict_review_rows} unknown event strict-review rows, "
                f"{score_unknown_event_strict_low_confidence_sources} unknown event strict-review low-confidence source packets, "
                f"{score_unknown_event_strict_secondary_newswire} unknown event strict-review secondary-newswire packets, "
                f"{score_unknown_event_strict_primary_required} unknown event strict-review primary-source confirmations required, "
                f"{score_unknown_event_strict_manual_review} unknown event strict-review manual reviews required, "
                f"{score_unknown_event_strict_deterministic_rejected} unknown event strict-review deterministic rejections, "
                f"{score_unknown_event_strict_packet_classifier_ready} unknown event strict-review classifier-ready packets, "
                f"{score_unknown_event_strict_packet_known} unknown event strict-review Known-draft-sufficient packets, "
                f"{score_unknown_event_strict_packet_approval_ready} unknown event strict-review approval-ready packets, "
                f"{score_unknown_event_strict_packet_contract_valid} unknown event strict-review contracts valid, "
                f"{score_unknown_event_strict_packet_contract_invalid} unknown event strict-review contracts invalid, "
                f"{score_unknown_event_strict_packet_prod_writes} unknown event strict-review production writes, "
                f"{score_unknown_event_primary_confirmation_packets} unknown event primary-confirmation packets, "
                f"{score_unknown_event_primary_confirmation_files} unknown event primary-confirmation HTML files scanned, "
                f"{score_unknown_event_primary_confirmation_read_errors} unknown event primary-confirmation read errors, "
                f"{score_unknown_event_primary_local_candidates} unknown event primary-confirmation local candidates, "
                f"{score_unknown_event_primary_local_confirmations} unknown event primary-confirmation high-quality candidates, "
                f"{score_unknown_event_primary_supporting_only} unknown event primary-confirmation supporting-only candidates, "
                f"{score_unknown_event_primary_rows_with_confirmation} unknown event primary-confirmation rows with local confirmation, "
                f"{score_unknown_event_primary_rows_supporting_only} unknown event primary-confirmation rows with supporting context only, "
                f"{score_unknown_event_primary_rows_without_confirmation} unknown event primary-confirmation rows without local confirmation, "
                f"{score_unknown_event_primary_classifier_ready} unknown event primary-confirmation classifier-ready rows, "
                f"{score_unknown_event_primary_known} unknown event primary-confirmation Known-draft-sufficient rows, "
                f"{score_unknown_event_primary_approval_ready} unknown event primary-confirmation approval-ready rows, "
                f"{score_unknown_event_primary_contract_valid} unknown event primary-confirmation contracts valid, "
                f"{score_unknown_event_primary_contract_invalid} unknown event primary-confirmation contracts invalid, "
                f"{score_unknown_event_primary_prod_writes} unknown event primary-confirmation production writes, "
                f"{score_unknown_event_external_confirmation_packets} unknown event external-confirmation packets, "
                f"{score_unknown_event_external_source_cards} unknown event external-confirmation source cards, "
                f"{score_unknown_event_external_confirmation_candidates} unknown event external-confirmation candidates, "
                f"{score_unknown_event_external_supporting_context} unknown event external-confirmation supporting-context cards, "
                f"{score_unknown_event_external_rows_with_confirmation} unknown event external-confirmation rows with confirmation candidates, "
                f"{score_unknown_event_external_rows_supporting_only} unknown event external-confirmation rows supporting-only, "
                f"{score_unknown_event_external_classifier_input_candidates} unknown event external-confirmation classifier input candidates, "
                f"{score_unknown_event_external_classifier_input_contract_valid} unknown event external-confirmation classifier input candidate contracts valid, "
                f"{score_unknown_event_external_classifier_input_contract_invalid} unknown event external-confirmation classifier input candidate contracts invalid, "
                f"{score_unknown_event_external_classifier_input_ready} unknown event external-confirmation classifier input candidates ready, "
                f"{score_unknown_event_external_classifier_input_review_required} unknown event external-confirmation classifier input candidates requiring review, "
                f"{score_unknown_event_external_classifier_input_primary_source} unknown event external-confirmation classifier input candidates with primary sources covered, "
                f"{score_unknown_event_external_classifier_input_labels} unknown event external-confirmation classifier input required labels, "
                f"{score_unknown_event_external_classifier_input_guardrails} unknown event external-confirmation classifier input guardrails, "
                f"{score_unknown_event_external_classifier_review_templates} unknown event external-confirmation classifier review templates, "
                f"{score_unknown_event_external_classifier_review_template_contract_valid} unknown event external-confirmation classifier review template contracts valid, "
                f"{score_unknown_event_external_classifier_review_template_contract_invalid} unknown event external-confirmation classifier review template contracts invalid, "
                f"{score_unknown_event_external_classifier_review_template_blank_pending} unknown event external-confirmation classifier review templates blank-pending, "
                f"{score_unknown_event_external_classifier_review_template_input_ready} unknown event external-confirmation classifier review template inputs ready, "
                f"{score_unknown_event_external_classifier_ready} unknown event external-confirmation classifier-ready rows, "
                f"{score_unknown_event_external_known} unknown event external-confirmation Known-draft-sufficient rows, "
                f"{score_unknown_event_external_approval_ready} unknown event external-confirmation approval-ready rows, "
                f"{score_unknown_event_external_contract_valid} unknown event external-confirmation contracts valid, "
                f"{score_unknown_event_external_contract_invalid} unknown event external-confirmation contracts invalid, "
                f"{score_unknown_event_external_prod_writes} unknown event external-confirmation production writes, "
                f"{score_unknown_local_formula_tasks} unknown local formula acquisition tasks, "
                f"{score_unknown_local_formula_runtime_ready} unknown local formula runtime dependency-ready tasks, "
                f"{score_unknown_local_formula_csv_checked} unknown local formula sample CSV files checked, "
                f"{score_unknown_local_formula_csv_existing} unknown local formula sample CSV files existing, "
                f"{score_unknown_local_formula_csv_errors} unknown local formula sample CSV read errors, "
                f"{score_unknown_local_formula_group_count} unknown local formula input groups, "
                f"{score_unknown_local_formula_group_ready} unknown local formula input groups ready, "
                f"{score_unknown_local_formula_candidate_numerator} unknown local formula rows with candidate numerators, "
                f"{score_unknown_local_formula_direct_denominator} unknown local formula rows with direct denominators, "
                f"{score_unknown_local_formula_quantity_or_price} unknown local formula rows with quantity or price-index inputs, "
                f"{score_unknown_local_formula_policy} unknown local formula rows with formula policy, "
                f"{score_unknown_local_formula_ready} unknown local formula-ready rows, "
                f"{score_unknown_local_formula_known_draft} unknown local formula Known-draft-ready rows, "
                f"{score_unknown_local_formula_contract_valid} unknown local formula contracts valid, "
                f"{score_unknown_local_formula_contract_invalid} unknown local formula contracts invalid, "
                f"{score_unknown_local_formula_prod_writes} unknown local formula production writes, "
                f"{score_unknown_local_formula_review_packets} unknown local formula review packets, "
                f"{score_unknown_local_formula_review_candidate_numerator} unknown local formula review rows with candidate numerators, "
                f"{score_unknown_local_formula_review_direct_denominator} unknown local formula review rows with direct denominators, "
                f"{score_unknown_local_formula_review_denominator_candidate} unknown local formula review rows with denominator candidates, "
                f"{score_unknown_local_formula_review_formula_shape} unknown local formula review rows with candidate formula shapes, "
                f"{score_unknown_local_formula_review_policy_draft} unknown local formula review rows with formula-policy draft candidates, "
                f"{score_unknown_local_formula_review_policy_template} unknown local formula review formula-policy review templates, "
                f"{score_unknown_local_formula_review_policy_template_valid} unknown local formula review formula-policy review template contracts valid, "
                f"{score_unknown_local_formula_review_policy_template_blank} unknown local formula review formula-policy review templates blank-pending, "
                f"{score_unknown_local_formula_review_price_context} unknown local formula review rows with price-index context candidates, "
                f"{score_unknown_local_formula_review_price_context_shape} unknown local formula review rows with candidate price-context shapes, "
                f"{score_unknown_local_formula_review_price_template} unknown local formula review price-context review templates, "
                f"{score_unknown_local_formula_review_price_template_valid} unknown local formula review price-context review template contracts valid, "
                f"{score_unknown_local_formula_review_price_template_blank} unknown local formula review price-context review templates blank-pending, "
                f"{score_unknown_local_formula_review_quantity_or_price} unknown local formula review rows with quantity or price-index inputs, "
                f"{score_unknown_local_formula_review_policy} unknown local formula review rows with formula policy, "
                f"{score_unknown_local_formula_review_inputs_ready} unknown local formula review input-ready rows, "
                f"{score_unknown_local_formula_review_probe_available} unknown local formula probes available, "
                f"{score_unknown_local_formula_review_bridge_ready} unknown local formula bridge-probe-ready packets, "
                f"{score_unknown_local_formula_review_selected_json} unknown local formula selected value JSONs, "
                f"{score_unknown_local_formula_review_known} unknown local formula Known-draft-sufficient packets, "
                f"{score_unknown_local_formula_review_approval_ready} unknown local formula approval-ready packets, "
                f"{score_unknown_local_formula_review_contract_valid} unknown local formula review contracts valid, "
                f"{score_unknown_local_formula_review_contract_invalid} unknown local formula review contracts invalid, "
                f"{score_unknown_local_formula_review_prod_writes} unknown local formula review production writes, "
                f"{score_local_formula_source_capability_rows} local formula source-capability rows, "
                f"{score_local_formula_source_capability_checks} local formula source-capability checks, "
                f"{score_local_formula_source_capability_candidates} local formula source candidates present, "
                f"{score_local_formula_source_header_empty} local formula header-available-but-sample-empty checks, "
                f"{score_local_formula_source_context} local formula context/proxy checks, "
                f"{score_local_formula_source_policy_required} local formula policy-required checks, "
                f"{score_local_formula_source_external_required} local formula external/text-required checks, "
                f"{score_local_formula_source_resolved} local formula blockers resolved by current sources, "
                f"{score_local_formula_source_ready} local formula rows ready after source scan, "
                f"{score_local_formula_source_probe} local formula probes available after source scan, "
                f"{score_local_formula_source_known} local formula Known-draft-sufficient rows after source scan, "
                f"{score_local_formula_source_approval_ready} local formula approval-ready rows after source scan, "
                f"{score_local_formula_source_prod_writes} local formula source-capability production writes, "
                f"{score_unknown_external_business_tasks} unknown external business metric acquisition tasks, "
                f"{score_unknown_external_business_runtime_ready} unknown external business metric runtime dependency-ready tasks, "
                f"{score_unknown_external_business_overlay_hints} unknown external business metric overlay hints, "
                f"{score_unknown_external_business_group_count} unknown external business metric groups, "
                f"{score_unknown_external_business_group_ready} unknown external business metric groups ready, "
                f"{score_unknown_external_business_runtime_context} unknown external business metric rows with supporting runtime context, "
                f"{score_unknown_external_business_overlay_context_rows} unknown external business metric rows with overlay business context candidates, "
                f"{score_unknown_external_business_overlay_context_known} unknown external business metric overlay business context Known nodes, "
                f"{score_unknown_external_business_overlay_frequency_known} unknown external business metric overlay frequency-context Known nodes, "
                f"{score_unknown_external_business_overlay_penetration_known} unknown external business metric overlay penetration-context Known nodes, "
                f"{score_unknown_external_business_overlay_frequency_direct_known} unknown external business metric overlay frequency direct Known nodes, "
                f"{score_unknown_external_business_overlay_frequency_direct_unknown} unknown external business metric overlay frequency direct Unknown nodes, "
                f"{score_unknown_external_business_overlay_penetration_direct_known} unknown external business metric overlay penetration direct Known nodes, "
                f"{score_unknown_external_business_overlay_penetration_direct_unknown} unknown external business metric overlay penetration direct Unknown nodes, "
                f"{score_unknown_external_business_direct_source} unknown external business metric rows with direct sources, "
                f"{score_unknown_external_business_required_external} unknown external business metric rows requiring external/text source, "
                f"{score_unknown_external_business_false_positives} unknown external business metric false positives, "
                f"{score_unknown_external_business_metric_ready} unknown external business metric-ready rows, "
                f"{score_unknown_external_business_known_draft} unknown external business metric Known-draft-ready rows, "
                f"{score_unknown_external_business_contract_valid} unknown external business metric contracts valid, "
                f"{score_unknown_external_business_contract_invalid} unknown external business metric contracts invalid, "
                f"{score_unknown_external_business_prod_writes} unknown external business metric production writes, "
                f"{score_unknown_external_business_market_doc_tasks} unknown external business metric market-doc tasks, "
                f"{score_unknown_external_business_market_doc_files} unknown external business metric market-doc HTML files scanned, "
                f"{score_unknown_external_business_market_doc_read_errors} unknown external business metric market-doc read errors, "
                f"{score_unknown_external_business_market_doc_rows} unknown external business metric market-doc rows with review candidates, "
                f"{score_unknown_external_business_market_doc_documents} unknown external business metric market-doc candidate documents, "
                f"{score_unknown_external_business_market_doc_review} unknown external business metric market-doc review candidates, "
                f"{score_unknown_external_business_market_doc_numeric} unknown external business metric market-doc numeric review candidates, "
                f"{score_unknown_external_business_market_doc_textual} unknown external business metric market-doc textual review candidates, "
                f"{score_unknown_external_business_market_doc_weak} unknown external business metric market-doc weak candidates, "
                f"{score_unknown_external_business_market_doc_rejected} unknown external business metric market-doc rejected candidates, "
                f"{score_unknown_external_business_market_doc_known} unknown external business metric market-doc Known-draft-sufficient rows, "
                f"{score_unknown_external_business_market_doc_metric_ready} unknown external business metric market-doc metric-ready rows, "
                f"{score_unknown_external_business_market_doc_contract_valid} unknown external business metric market-doc contracts valid, "
                f"{score_unknown_external_business_market_doc_contract_invalid} unknown external business metric market-doc contracts invalid, "
                f"{score_unknown_external_business_market_doc_prod_writes} unknown external business metric market-doc production writes, "
                f"{score_unknown_external_business_review_packets} unknown external business metric review packets, "
                f"{score_unknown_external_business_review_expected} unknown external business metric expected review candidates, "
                f"{score_unknown_external_business_review_rows} unknown external business metric rows with review packets, "
                f"{score_unknown_external_business_review_numeric} unknown external business metric numeric review packets, "
                f"{score_unknown_external_business_review_textual} unknown external business metric textual review packets, "
                f"{score_unknown_external_business_review_scope} unknown external business metric packets with scope candidates, "
                f"{score_unknown_external_business_review_denominator} unknown external business metric packets with denominator candidates, "
                f"{score_unknown_external_business_review_period} unknown external business metric packets with period candidates, "
                f"{score_unknown_external_business_review_unit} unknown external business metric packets with unit candidates, "
                f"{score_unknown_external_business_review_metric_ready} unknown external business metric review-packet metric-ready rows, "
                f"{score_unknown_external_business_review_known} unknown external business metric review-packet Known-draft-sufficient rows, "
                f"{score_unknown_external_business_review_contract_valid} unknown external business metric review-packet contracts valid, "
                f"{score_unknown_external_business_review_contract_invalid} unknown external business metric review-packet contracts invalid, "
                f"{score_unknown_external_business_review_prod_writes} unknown external business metric review-packet production writes, "
                f"{score_unknown_external_business_readiness_packets} unknown external business metric readiness packets, "
                f"{score_unknown_external_business_readiness_p0} unknown external business metric P0 formula-policy-only candidates, "
                f"{score_unknown_external_business_readiness_p1} unknown external business metric P1 period/unit-required candidates, "
                f"{score_unknown_external_business_readiness_p2} unknown external business metric P2 denominator-required candidates, "
                f"{score_unknown_external_business_readiness_missing_denominator} unknown external business metric packets missing denominator, "
                f"{score_unknown_external_business_readiness_missing_period} unknown external business metric packets missing period, "
                f"{score_unknown_external_business_readiness_missing_unit} unknown external business metric packets missing unit, "
                f"{score_unknown_external_business_readiness_missing_bounds} unknown external business metric packets missing bounds, "
                f"{score_unknown_external_business_readiness_missing_formula} unknown external business metric packets missing formula policy, "
                f"{score_unknown_external_business_readiness_metric_ready} unknown external business metric readiness metric-ready packets, "
                f"{score_unknown_external_business_readiness_known} unknown external business metric readiness Known-draft-sufficient packets, "
                f"{score_unknown_external_business_readiness_prod_writes} unknown external business metric readiness production writes, "
                f"{score_unknown_external_business_policy_p0} unknown external business metric P0 source packets for policy draft, "
                f"{score_unknown_external_business_policy_drafts} unknown external business metric policy draft packets, "
                f"{score_unknown_external_business_policy_review_required} unknown external business metric formula-policy reviews required, "
                f"{score_unknown_external_business_policy_value_templates} unknown external business metric value JSON templates, "
                f"{score_unknown_external_business_policy_review_templates} unknown external business metric policy review templates, "
                f"{score_unknown_external_business_policy_review_templates_valid} unknown external business metric policy review template contracts valid, "
                f"{score_unknown_external_business_policy_review_templates_invalid} unknown external business metric policy review template contracts invalid, "
                f"{score_unknown_external_business_policy_review_templates_blank} unknown external business metric policy review templates blank-pending, "
                f"{score_unknown_external_business_policy_review_templates_input_ready} unknown external business metric policy review template inputs ready, "
                f"{score_unknown_external_business_policy_metric_ready} unknown external business metric policy-draft metric-ready rows, "
                f"{score_unknown_external_business_policy_known} unknown external business metric policy-draft Known-draft-sufficient rows, "
                f"{score_unknown_external_business_policy_contract_valid} unknown external business metric policy-draft contracts valid, "
                f"{score_unknown_external_business_policy_contract_invalid} unknown external business metric policy-draft contracts invalid, "
                f"{score_unknown_external_business_policy_prod_writes} unknown external business metric policy-draft production writes, "
                f"{score_unknown_external_business_value_rows} unknown external business metric value-candidate rows adjudicated, "
                f"{score_unknown_external_business_value_rows_with_tokens} unknown external business metric rows with value-candidate tokens, "
                f"{score_unknown_external_business_value_tokens} unknown external business metric value-candidate tokens, "
                f"{score_unknown_external_business_value_rejected_tokens} unknown external business metric rejected numeric tokens, "
                f"{score_unknown_external_business_value_shortlist} unknown external business metric value-candidate shortlist rows, "
                f"{score_unknown_external_business_value_scope_rejected} unknown external business metric value-candidate scope-rejected rows, "
                f"{score_unknown_external_business_value_no_numeric} unknown external business metric rows with no scoreable numeric candidate, "
                f"{score_unknown_external_business_value_metric_ready} unknown external business metric value-candidate metric-ready rows, "
                f"{score_unknown_external_business_value_known} unknown external business metric value-candidate Known-draft-sufficient rows, "
                f"{score_unknown_external_business_value_contract_valid} unknown external business metric value-candidate contracts valid, "
                f"{score_unknown_external_business_value_contract_invalid} unknown external business metric value-candidate contracts invalid, "
                f"{score_unknown_external_business_value_prod_writes} unknown external business metric value-candidate production writes, "
                f"{score_unknown_external_business_value_review_packets} unknown external business metric value-review packets, "
                f"{score_unknown_external_business_value_review_options} unknown external business metric value-review candidate options, "
                f"{score_unknown_external_business_value_review_bridge_ready} unknown external business metric value-review bridge-probe-ready options, "
                f"{score_unknown_external_business_value_review_selected_raw} unknown external business metric value-review selected raw values, "
                f"{score_unknown_external_business_value_review_selected_json} unknown external business metric value-review selected value JSONs, "
                f"{score_unknown_external_business_value_review_metric_ready} unknown external business metric value-review metric-ready packets, "
                f"{score_unknown_external_business_value_review_known} unknown external business metric value-review Known-draft-sufficient packets, "
                f"{score_unknown_external_business_value_review_approval_ready} unknown external business metric value-review approval-ready packets, "
                f"{score_unknown_external_business_value_review_contract_valid} unknown external business metric value-review contracts valid, "
                f"{score_unknown_external_business_value_review_contract_invalid} unknown external business metric value-review contracts invalid, "
                f"{score_unknown_external_business_value_review_prod_writes} unknown external business metric value-review production writes, "
                f"{score_unknown_business_value_selection_rows} unknown business-metric value-selection rows, "
                f"{score_unknown_business_value_selection_packets} unknown business-metric value-selection review packets, "
                f"{score_unknown_business_value_selection_options} unknown business-metric candidate value options, "
                f"{score_unknown_business_value_selection_bridge_ready} unknown business-metric bridge-ready value options, "
                f"{score_unknown_business_value_selection_review_required} unknown business-metric rows needing value-selection review, "
                f"{score_unknown_business_value_selection_policy_draft_ready} unknown business-metric value-policy-draft-ready rows, "
                f"{score_unknown_business_value_selection_proposed_json} unknown business-metric proposed value JSONs, "
                f"{score_unknown_business_value_selection_source_missing} unknown business-metric source-missing rows, "
                f"{score_unknown_business_value_selection_auto} unknown business-metric auto-selectable values, "
                f"{score_unknown_business_value_selection_selected_json} unknown business-metric selected value JSONs, "
                f"{score_unknown_business_value_selection_known} unknown business-metric Known-draft-sufficient rows, "
                f"{score_unknown_business_value_selection_approval_ready} unknown business-metric approval-ready rows, "
                f"{score_unknown_business_value_selection_contract_valid} unknown business-metric value-selection contracts valid, "
                f"{score_unknown_business_value_selection_contract_invalid} unknown business-metric value-selection contracts invalid, "
                f"{score_unknown_business_value_selection_prod_writes} unknown business-metric value-selection production writes, "
                f"{score_unknown_penetration_value_priority_packets} unknown penetration value-priority packets, "
                f"{score_unknown_penetration_value_priority_options} unknown penetration value-priority candidate options, "
                f"{score_unknown_penetration_value_priority_bridge_ready} unknown penetration value-priority bridge-ready options, "
                f"{score_unknown_penetration_value_priority_p1} unknown penetration value-priority P1 reviews, "
                f"{score_unknown_penetration_value_priority_p2} unknown penetration value-priority P2 reviews, "
                f"{score_unknown_penetration_value_priority_p3_forecast} unknown penetration value-priority P3 forecast reviews, "
                f"{score_unknown_penetration_value_priority_p3_low_confidence} unknown penetration value-priority P3 low-confidence reviews, "
                f"{score_unknown_penetration_value_priority_selected_json} unknown penetration value-priority selected value JSONs, "
                f"{score_unknown_penetration_value_priority_known} unknown penetration value-priority Known-draft-sufficient rows, "
                f"{score_unknown_penetration_value_priority_approval_ready} unknown penetration value-priority approval-ready rows, "
                f"{score_unknown_penetration_value_priority_prod_writes} unknown penetration value-priority production writes, "
                f"{score_unknown_penetration_p1_source_candidates} unknown penetration P1 source-confirmation candidates, "
                f"{score_unknown_penetration_p1_source_found} unknown penetration P1 source files found, "
                f"{score_unknown_penetration_p1_raw_value_confirmed} unknown penetration P1 raw-value tokens confirmed, "
                f"{score_unknown_penetration_p1_scope_confirmed} unknown penetration P1 source scopes confirmed, "
                f"{score_unknown_penetration_p1_selected_json} unknown penetration P1 selected value JSONs, "
                f"{score_unknown_penetration_p1_known} unknown penetration P1 Known-draft-sufficient rows, "
                f"{score_unknown_penetration_p1_approval_ready} unknown penetration P1 approval-ready rows, "
                f"{score_unknown_penetration_p1_prod_writes} unknown penetration P1 production writes, "
                f"{score_unknown_penetration_value_policy_draft_rows} unknown penetration value-policy draft rows, "
                f"{score_unknown_penetration_value_policy_draft_scope_confirmed} unknown penetration value-policy source scopes confirmed, "
                f"{score_unknown_penetration_value_policy_draft_proposed_json} unknown penetration value-policy proposed value JSONs, "
                f"{score_unknown_penetration_value_policy_draft_valid} unknown penetration value-policy draft contracts valid, "
                f"{score_unknown_penetration_value_policy_draft_invalid} unknown penetration value-policy draft contracts invalid, "
                f"{score_unknown_penetration_value_policy_draft_bridge_ready} unknown penetration value-policy final-score bridges ready, "
                f"{score_unknown_penetration_value_policy_draft_selected_json} unknown penetration value-policy selected value JSONs, "
                f"{score_unknown_penetration_value_policy_draft_known} unknown penetration value-policy Known-draft-sufficient rows, "
                f"{score_unknown_penetration_value_policy_draft_approval_ready} unknown penetration value-policy approval-ready rows, "
                f"{score_unknown_penetration_value_policy_draft_prod_writes} unknown penetration value-policy production writes, "
                f"{score_unknown_penetration_value_confirmation_packets_count} unknown penetration value-confirmation packets, "
                f"{score_unknown_penetration_value_confirmation_templates} unknown penetration value-confirmation templates, "
                f"{score_unknown_penetration_value_confirmation_template_valid} unknown penetration value-confirmation template contracts valid, "
                f"{score_unknown_penetration_value_confirmation_packet_valid} unknown penetration value-confirmation packet contracts valid, "
                f"{score_unknown_penetration_value_confirmation_known} unknown penetration value-confirmation Known-draft-sufficient rows, "
                f"{score_unknown_penetration_value_confirmation_approval_ready} unknown penetration value-confirmation approval-ready rows, "
                f"{score_unknown_penetration_value_confirmation_prod_writes} unknown penetration value-confirmation production writes, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_count} unknown penetration value-confirmation template-bundle rows, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_blank} unknown penetration value-confirmation blank/pending templates, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_valid} unknown penetration value-confirmation template-bundle contracts valid, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_confirmed} unknown penetration value-confirmation confirmed templates, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_known} unknown penetration value-confirmation template-bundle Known-draft-sufficient rows, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_approval_ready} unknown penetration value-confirmation template-bundle approval-ready rows, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_runtime_writes} unknown penetration value-confirmation template-bundle runtime writes, "
                f"{score_unknown_penetration_value_confirmation_template_bundle_prod_writes} unknown penetration value-confirmation template-bundle production writes, "
                f"{score_unknown_penetration_value_confirmation_gate_packets} unknown penetration value-confirmation gate packets, "
                f"{score_unknown_penetration_value_confirmation_gate_records} unknown penetration value-confirmation records seen, "
                f"{score_unknown_penetration_value_confirmation_gate_missing} unknown penetration value-confirmation records missing, "
                f"{score_unknown_penetration_value_confirmation_gate_confirmed} unknown penetration value policies confirmed, "
                f"{score_unknown_penetration_value_confirmation_gate_known_candidates} unknown penetration Known-draft candidates, "
                f"{score_unknown_penetration_value_confirmation_gate_prod_writes} unknown penetration value-confirmation gate production writes, "
                f"{score_unknown_penetration_confirmed_known_draft_gate_rows} unknown penetration confirmed Known-draft emitter gate rows, "
                f"{score_unknown_penetration_confirmed_known_draft_candidates} unknown penetration confirmed value-policy candidates, "
                f"{score_unknown_penetration_confirmed_known_draft_emitted} unknown penetration Known drafts emitted, "
                f"{score_unknown_penetration_confirmed_known_draft_blocked} unknown penetration Known drafts blocked, "
                f"{score_unknown_penetration_confirmed_known_draft_staging_ready} unknown penetration Known drafts ready for review staging, "
                f"{score_unknown_penetration_confirmed_known_draft_prod_writes} unknown penetration confirmed Known-draft production writes, "
                f"{score_approval_packet_count} approval review packets, "
                f"{score_approval_packet_known} approval Known packets, "
                f"{score_approval_packet_not_applicable} approval NotApplicable packets, "
                f"{score_approval_packet_bridge_ready} approval packets bridge-ready, "
                f"{score_approval_packet_missing} approval packet missing approvals, "
                f"{score_approval_packet_templates} approval packet templates, "
                f"{score_approval_packet_template_valid} approval packet template contracts valid, "
                f"{score_approval_packet_template_invalid} approval packet template contracts invalid, "
                f"{score_approval_packet_approved_writes} approval packet approved runtime writes, "
                f"{score_approval_packet_write_plan} approval packet write-plan entries, "
                f"{score_approval_packet_prod_writes} approval packet production writes, "
                f"{score_approval_risk_packets} approval-packet risk-review packets, "
                f"{score_approval_risk_bulk_structured} approval-packet risk-review bulk structured candidates, "
                f"{score_approval_risk_borderline} approval-packet risk-review borderline structured-text candidates, "
                f"{score_approval_risk_individual} approval-packet risk-review individual-review packets, "
                f"{score_approval_risk_event} approval-packet risk-review event evidence packets, "
                f"{score_approval_risk_structured} approval-packet risk-review structured proxy packets, "
                f"{score_approval_risk_policy} approval-packet risk-review policy packets, "
                f"{score_approval_risk_contract_fix} approval-packet risk-review contract-fix blockers, "
                f"{score_approval_risk_auto} approval-packet risk-review auto approvals, "
                f"{score_approval_risk_prod_writes} approval-packet risk-review production writes, "
                f"{score_bulk_review_candidate_count} bulk-review approval candidates, "
                f"{score_bulk_review_strict} bulk-review approval strict candidates, "
                f"{score_bulk_review_borderline} bulk-review approval borderline candidates, "
                f"{score_bulk_review_drafts} bulk-review approval drafts, "
                f"{score_bulk_review_draft_valid} bulk-review approval draft contracts valid, "
                f"{score_bulk_review_draft_invalid} bulk-review approval draft contracts invalid, "
                f"{score_bulk_review_auto} bulk-review approval auto approvals, "
                f"{score_bulk_review_prod_writes} bulk-review approval production writes, "
                f"{score_bulk_source_sample_candidates} bulk-review source-sample candidates, "
                f"{score_bulk_source_sample_payload_match} bulk-review source payload matches, "
                f"{score_bulk_source_sample_evidence_complete} bulk-review complete evidence refs, "
                f"{score_bulk_source_sample_borderline_ready} bulk-review borderline sample-evidence ready rows, "
                f"{score_bulk_source_sample_complete} bulk-review complete reviewer packets, "
                f"{score_bulk_source_sample_prod_writes} bulk-review source-sample production writes, "
                f"{score_event_approval_source_sample_packets} event-approval source-sample event-text packets, "
                f"{score_event_approval_individual_reviews} event-approval individual event-evidence reviews required, "
                f"{score_event_approval_payload_match} event-approval source payload matches, "
                f"{score_event_approval_market_packet_found} event-approval market-doc review packets, "
                f"{score_event_approval_market_refs_complete} event-approval market-doc review refs complete, "
                f"{score_event_approval_dockcase_readable}/{score_event_approval_dockcase_refs} event-approval DOCKCASE docs readable, "
                f"{score_event_approval_keyword_ready} event-approval keyword-evidence-ready rows, "
                f"{score_event_approval_template_valid}/{score_event_approval_template_count} event-approval event-evidence review templates valid, "
                f"{score_event_approval_template_blank} event-approval templates blank/pending, "
                f"{score_event_approval_complete} event-approval complete reviewer packets, "
                f"{score_event_approval_prod_writes} event-approval source-sample production writes, "
                f"{score_individual_source_sample_packets} individual-review source-sample packets, "
                f"{score_individual_structured_reviews} individual-review structured proxy reviews, "
                f"{score_individual_policy_reviews} individual-review policy reviews, "
                f"{score_individual_manual_policy_reviews} individual-review manual-policy packets, "
                f"{score_individual_event_policy_reviews} individual-review event policy packets, "
                f"{score_individual_structured_proxy_reviews} individual-review structured proxy packets, "
                f"{score_individual_payload_match} individual-review source payload matches, "
                f"{score_individual_evidence_refs_complete} individual-review complete evidence refs, "
                f"{score_individual_text_sample_ready} individual-review text sample-evidence ready rows, "
                f"{score_individual_event_source_complete} individual-review event source-sample packets complete, "
                f"{score_individual_template_valid}/{score_individual_template_count} individual-review templates valid, "
                f"{score_individual_template_blank} individual-review templates blank/pending, "
                f"{score_individual_complete} individual-review complete reviewer packets, "
                f"{score_individual_prod_writes} individual-review source-sample production writes, "
                f"{score_approval_source_coverage_packets} approval source-sample coverage packets, "
                f"{score_approval_source_coverage_supported} approval source-sample supported routes, "
                f"{score_approval_source_coverage_found} approval source-sample source samples found, "
                f"{score_approval_source_coverage_complete} approval source-sample reviewer packets complete, "
                f"{score_approval_source_coverage_payload_match} approval source-sample payload matches, "
                f"{score_approval_source_coverage_template_valid} approval source-sample review templates valid, "
                f"{score_approval_source_coverage_approval_template_valid} approval source-sample blank approval templates valid, "
                f"{score_approval_source_coverage_input_ready} approval source-sample approval inputs ready, "
                f"{score_approval_source_coverage_input_not_ready} approval source-sample approval inputs not ready, "
                f"{score_approval_source_coverage_unsupported} approval source-sample unsupported risk classes, "
                f"{score_approval_source_coverage_prod_writes} approval source-sample production writes, "
                f"{score_approval_target_scope_packets} approval target-scope readiness packets, "
                f"{score_approval_target_scope_final_ready} approval target-scope final-score-ready packets, "
                f"{score_approval_target_scope_samples_complete} approval target-scope source-sample packets complete, "
                f"{score_approval_target_scope_existing_policies} approval target-scope existing runtime policies, "
                f"{score_approval_target_scope_supported} approval target-scope packets supported by existing policies, "
                f"{score_approval_target_scope_explicit} approval target-scope explicit target scopes, "
                f"{score_approval_target_scope_ready} approval target-scope packets ready after approval, "
                f"{score_approval_target_scope_policy_required} approval target-scope policies required, "
                f"{score_approval_target_scope_per_stock} approval target-scope per-stock materializations required, "
                f"{score_approval_target_scope_market_event} approval target-scope market/event policies required, "
                f"{score_approval_target_scope_materialization_ready} approval target-scope runtime materializations ready, "
                f"{score_approval_target_scope_approval_only_not_sufficient} approval-only not sufficient packets, "
                f"{score_approval_target_scope_safe_after_approval} approval target-scope safe runtime writes after approval, "
                f"{score_approval_target_scope_prod_writes} approval target-scope production writes, "
                f"{score_approval_materialization_packets} approval materialization packets, "
                f"{score_approval_materialization_a_share_universe} approval materialization A-share universe tickers, "
                f"{score_approval_materialization_fundamental_packets} approval materialization fundamental packets, "
                f"{score_approval_materialization_direct_formula} approval materialization direct structured formula packets, "
                f"{score_approval_materialization_direct_formula_ready} approval materialization direct formula plans ready, "
                f"{score_approval_materialization_min_target} approval materialization minimum direct-formula target tickers, "
                f"{score_approval_materialization_max_target} approval materialization maximum direct-formula target tickers, "
                f"{score_approval_materialization_grain_join} approval materialization grain-join policies required, "
                f"{score_approval_materialization_text_export} approval materialization text full-match exports required, "
                f"{score_approval_materialization_market_event} approval materialization market/event policies required, "
                f"{score_approval_materialization_unsupported} approval materialization unsupported policies, "
                f"{score_approval_materialization_ready} approval materialization runtime plans ready, "
                f"{score_approval_materialization_runtime_writes} approval materialization runtime writes, "
                f"{score_approval_materialization_prod_writes} approval materialization production writes, "
                f"{score_approval_materialization_batch_formula_plans} approval materialization batch direct formula plans, "
                f"{score_approval_materialization_batch_entries} approval materialization batch-plan entries, "
                f"{score_approval_materialization_batch_contract_valid} approval materialization batch-plan contracts valid, "
                f"{score_approval_materialization_batch_contract_invalid} approval materialization batch-plan contracts invalid, "
                f"{score_approval_materialization_batch_review_required} approval materialization batch plans review required, "
                f"{score_approval_materialization_batch_approved} approval materialization batch plans approved, "
                f"{score_approval_materialization_batch_rows} approval materialization planned formula UPSERT rows, "
                f"{score_approval_materialization_batch_inserts} approval materialization formula rows to insert, "
                f"{score_approval_materialization_batch_updates} approval materialization formula rows to update, "
                f"{score_approval_materialization_batch_backup_rows} approval materialization formula rows requiring backup, "
                f"{score_approval_materialization_batch_upsert_ready} approval materialization upsert-ready entries, "
                f"{score_approval_materialization_batch_blocked} approval materialization blocked entries, "
                f"{score_approval_materialization_batch_attempted} approval materialization runtime write attempts, "
                f"{score_approval_materialization_batch_prod_writes} approval materialization batch production writes, "
                f"{score_approval_materialization_codex_rows} approval materialization Codex review batch-plan rows, "
                f"{score_approval_materialization_codex_approved} approval materialization Codex review approvals, "
                f"{score_approval_materialization_codex_rejected} approval materialization Codex review rejections, "
                f"{score_approval_materialization_codex_records} approval materialization Codex approval records, "
                f"{score_approval_materialization_codex_planned_rows} approval materialization Codex planned UPSERT rows, "
                f"{score_approval_materialization_codex_approved_rows} approval materialization Codex approved planned UPSERT rows, "
                f"{score_approval_materialization_codex_inserts} approval materialization Codex rows to insert, "
                f"{score_approval_materialization_codex_updates} approval materialization Codex rows to update, "
                f"{score_approval_materialization_codex_backup_rows} approval materialization Codex rows requiring backup, "
                f"{score_approval_materialization_codex_runtime_writes} approval materialization Codex runtime write attempts, "
                f"{score_approval_materialization_codex_prod_writes} approval materialization Codex production writes, "
                f"{score_approval_materialization_gate_rows} approval materialization gate batch-plan rows, "
                f"{score_approval_materialization_gate_contract_valid} approval materialization gate contract-valid batch plans, "
                f"{score_approval_materialization_gate_records_seen} approval materialization gate approval records seen, "
                f"{score_approval_materialization_gate_required} approval materialization gate approvals required, "
                f"{score_approval_materialization_gate_missing} approval materialization gate approvals missing, "
                f"{score_approval_materialization_gate_rejected} approval materialization gate approvals rejected, "
                f"{score_approval_materialization_gate_approved} approval materialization gate formula batch plans approved, "
                f"{score_approval_materialization_gate_templates} approval materialization gate blank approval templates, "
                f"{score_approval_materialization_gate_templates_valid} approval materialization gate blank templates contract valid, "
                f"{score_approval_materialization_gate_planned_rows} approval materialization gate planned UPSERT rows, "
                f"{score_approval_materialization_gate_approved_rows} approval materialization gate approved planned UPSERT rows, "
                f"{score_approval_materialization_gate_runtime_writes} approval materialization gate runtime writes allowed, "
                f"{score_approval_materialization_gate_prod_writes} approval materialization gate production writes, "
                f"{score_approval_materialization_preflight_entries} approval materialization execution-preflight batch-plan entries, "
                f"{score_approval_materialization_preflight_approved} approval materialization execution-preflight approved batch plans, "
                f"{score_approval_materialization_preflight_checked} approval materialization execution-preflight entries checked, "
                f"{score_approval_materialization_preflight_ready} approval materialization execution-preflight entries ready, "
                f"{score_approval_materialization_preflight_blocked} approval materialization execution-preflight entries blocked, "
                f"{score_approval_materialization_preflight_planned_rows} approval materialization execution-preflight planned UPSERT rows, "
                f"{score_approval_materialization_preflight_would_write} approval materialization execution-preflight rows would write, "
                f"{score_approval_materialization_preflight_inserts} approval materialization execution-preflight rows to insert, "
                f"{score_approval_materialization_preflight_updates} approval materialization execution-preflight rows to update, "
                f"{score_approval_materialization_preflight_backup_rows} approval materialization execution-preflight rows requiring backup, "
                f"{score_approval_materialization_preflight_backups_required} approval materialization execution-preflight backups required, "
                f"{score_approval_materialization_preflight_backups_created} approval materialization execution-preflight backups created, "
                f"{score_approval_materialization_preflight_write_attempts} approval materialization execution-preflight runtime write attempts, "
                f"{score_approval_materialization_preflight_write_completed} approval materialization execution-preflight runtime write completions, "
                f"{score_approval_materialization_preflight_verified_rows} approval materialization execution-preflight post-write verified rows, "
                f"{score_approval_materialization_preflight_prod_writes} approval materialization execution-preflight production writes, "
                f"{score_runtime_scope_approval_rows} runtime scope approval rows checked, "
                f"{score_runtime_scope_approval_records} runtime scope approval records, "
                f"{score_runtime_scope_approved_scopes} runtime scopes approved, "
                f"{score_runtime_scope_rejected} runtime scope approvals rejected, "
                f"{score_runtime_scope_approval_candidate_rows} runtime scope approval candidate rows would write if batch-approved, "
                f"{score_runtime_scope_approval_attempted} runtime scope approval write attempts, "
                f"{score_runtime_scope_approval_prod_writes} runtime scope approval production writes, "
                f"{score_runtime_scope_approved_entries} runtime target-scope approved write-plan entries, "
                f"{score_runtime_scope_runtime_a_share} runtime target-scope A-share ts_codes, "
                f"{score_runtime_scope_config_a_share} runtime target-scope configured A-share ts_codes, "
                f"{score_runtime_scope_exact_match} runtime target-scope exact config/runtime match, "
                f"{score_runtime_scope_candidates} runtime target-scope candidates, "
                f"{score_runtime_scope_contract_valid} runtime target-scope contracts valid, "
                f"{score_runtime_scope_contract_invalid} runtime target-scope contracts invalid, "
                f"{score_runtime_scope_review_required} runtime target-scope reviews required, "
                f"{score_runtime_scope_approved_count} runtime target scopes approved, "
                f"{score_runtime_scope_batch_plan_required} runtime target-scope controlled batch plans required, "
                f"{score_runtime_scope_candidate_rows} runtime target-scope candidate rows would write if approved, "
                f"{score_runtime_scope_upsert_ready} runtime target-scope upsert-ready entries, "
                f"{score_runtime_scope_attempted} runtime target-scope write attempts, "
                f"{score_runtime_scope_prod_writes} runtime target-scope production writes, "
                f"{score_runtime_batch_plan_entries} runtime batch-plan entries, "
                f"{score_runtime_batch_plan_valid} runtime batch-plan contracts valid, "
                f"{score_runtime_batch_plan_invalid} runtime batch-plan contracts invalid, "
                f"{score_runtime_batch_plan_review_required} runtime batch-plan reviews required, "
                f"{score_runtime_batch_plan_approved} runtime batch plans approved, "
                f"{score_runtime_batch_plan_rows} runtime batch-plan UPSERT rows planned, "
                f"{score_runtime_batch_plan_insert_rows} runtime batch-plan rows to insert, "
                f"{score_runtime_batch_plan_update_rows} runtime batch-plan rows to update, "
                f"{score_runtime_batch_plan_backup_rows} runtime batch-plan existing rows needing backup, "
                f"{score_runtime_batch_plan_attempted} runtime batch-plan write attempts, "
                f"{score_runtime_batch_plan_prod_writes} runtime batch-plan production writes, "
                f"{score_runtime_batch_approval_rows} runtime batch-approval rows checked, "
                f"{score_runtime_batch_approval_records} runtime batch approval records, "
                f"{score_runtime_batch_approved_count} runtime controlled batch plans approved, "
                f"{score_runtime_batch_policy_rejected} runtime batch policies rejected, "
                f"{score_runtime_batch_approval_rows_planned} runtime batch-approval UPSERT rows covered, "
                f"{score_runtime_batch_approval_insert_rows} runtime batch-approval rows to insert, "
                f"{score_runtime_batch_approval_update_rows} runtime batch-approval rows to update, "
                f"{score_runtime_batch_approval_backup_rows} runtime batch-approval existing rows needing backup, "
                f"{score_runtime_batch_approval_attempted} runtime batch-approval write attempts, "
                f"{score_runtime_batch_approval_prod_writes} runtime batch-approval production writes, "
                f"{score_runtime_execution_approved} runtime execution approved batch plans, "
                f"{score_runtime_execution_ready} runtime execution-ready plans, "
                f"{score_runtime_execution_blocked} runtime execution blocked plans, "
                f"{score_runtime_execution_backup_completed} runtime execution backups completed, "
                f"{score_runtime_execution_backup_failed} runtime execution backup failures, "
                f"{score_runtime_execution_attempted} runtime execution write attempts, "
                f"{score_runtime_execution_completed} runtime execution write completions, "
                f"{score_runtime_execution_failed} runtime execution write failures, "
                f"{score_runtime_execution_rows} runtime execution rows written, "
                f"{score_runtime_execution_insert_rows} runtime execution rows inserted, "
                f"{score_runtime_execution_update_rows} runtime execution rows updated, "
                f"{score_runtime_execution_verified_rows} runtime execution rows post-write verified, "
                f"{score_runtime_execution_verification_errors} runtime execution verification errors, "
                f"{score_runtime_execution_prod_writes} runtime execution production writes, "
                f"{score_runtime_preflight_approved_entries} runtime preflight approved write-plan entries, "
                f"{score_runtime_preflight_upsert_ready} runtime preflight upsert-ready entries, "
                f"{score_runtime_preflight_executed_entries} runtime preflight executed entries, "
                f"{score_runtime_preflight_blocked} runtime preflight blocked entries, "
                f"{score_runtime_preflight_missing_scope} runtime preflight missing target scopes, "
                f"{score_runtime_preflight_candidate_rows} runtime preflight candidate rows would write if approved, "
                f"{score_runtime_preflight_batch_plan_required} runtime preflight controlled batch plans required, "
                f"{score_runtime_preflight_batch_plan_candidates} runtime preflight batch-plan candidates, "
                f"{score_runtime_preflight_batch_plan_review_required} runtime preflight batch-plan reviews required, "
                f"{score_runtime_preflight_batch_plan_approved} runtime preflight batch plans approved, "
                f"{score_runtime_preflight_backup_execution_required} runtime preflight backup/execution gates required, "
                f"{score_runtime_preflight_execution_completed} runtime preflight executions completed, "
                f"{score_runtime_preflight_execution_rows} runtime preflight execution rows written, "
                f"{score_runtime_preflight_execution_verified_rows} runtime preflight execution rows verified, "
                f"{score_runtime_preflight_batch_plan_rows} runtime preflight batch-plan UPSERT rows planned, "
                f"{score_runtime_preflight_batch_plan_backup_rows} runtime preflight batch-plan existing rows needing backup, "
                f"{score_runtime_preflight_rows_would_write} runtime preflight rows would write, "
                f"{score_runtime_preflight_attempted} runtime preflight write attempts, "
                f"{score_runtime_preflight_prod_writes} runtime preflight production writes, "
                f"{len(score_approval_consistency_errors)} approval cross-report consistency errors, "
                f"{score_safe_upsert} total safe auto-upsert, "
                f"{score_candidate_not_ready} not ready for candidate input)"
            )
        )
    elif score_governance_gaps:
        completion_blockers.append(
            f"A-share score field trace still reports {score_governance_gaps} governance/intentional participating gaps"
        )
    if not frontend_navigation_ok:
        completion_blockers.append(
            "frontend browser timing covers audited direct routes and selected interactions, not every interaction",
        )
    if score_approval_consistency_errors:
        completion_blockers.append(
            "A-share approval evidence has cross-report consistency errors: "
            + "; ".join(score_approval_consistency_errors)
        )
    if not market_full_parse:
        completion_blockers.insert(
            2,
            "market document entity/event signal evidence is bounded to samples, not full linking/classification for every document",
        )
    completion_status = "not_complete"
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "audit_dir": str(audit_dir),
        "completion_status": completion_status,
        "summary": {
            "requirement_count": len(rows),
            "covered_count": sum(1 for row in rows if row["status"] == "covered"),
            "missing_evidence_count": sum(1 for row in rows if row["status"] != "covered"),
            "bounded_or_documented_not_full_count": len(incomplete_rows),
            "completion_blockers": completion_blockers,
        },
        "requirements": rows,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Goal coverage audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Completion status: `{report['completion_status']}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in report["summary"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend([
        "",
        "## Requirement Matrix",
        "",
        "| Requirement | Status | Evidence strength | Remaining gap |",
        "|---|---|---|---|",
    ])
    for row in report["requirements"]:
        lines.append(
            f"| {row['label']} | `{row['status']}` | `{row['evidence_strength']}` | {row['remaining_gap']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-dir", default="docs/audit")
    ap.add_argument("--output-json", default="docs/audit/goal_coverage_2026-06-19.json")
    ap.add_argument("--output-md", default="docs/audit/goal_coverage_2026-06-19.md")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(Path(args.audit_dir))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
