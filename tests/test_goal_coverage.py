import json
from pathlib import Path

from scripts import audit_goal_coverage


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_goal_coverage_builds_conservative_matrix(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    _write_json(
        audit_dir / "file_inventory_2026-06-19.json",
        {
            "roots": {
                "repo_operational": {
                    "files": 10,
                    "dirs": 2,
                    "bytes": 100,
                    "error_count": 0,
                },
                "dockcase_database_all_pruned": {
                    "files": 20,
                    "bytes": 200,
                    "error_count": 0,
                },
                "dockcase_market_data": {
                    "files": 5,
                    "bytes": 50,
                    "error_count": 0,
                },
            }
        },
    )
    _write_json(
        audit_dir / "repo_content_2026-06-19.json",
        {
            "text_files_read": 7,
            "text_bytes_read": 700,
            "text_lines_read": 70,
            "skipped_binary": 2,
            "skipped_too_large": 1,
            "skipped_file_samples": [
                {
                    "path": "runtime/hot.sqlite",
                    "reason": "binary_extension:.sqlite",
                    "head_tail_sha256": "abc",
                }
            ],
            "skipped_file_fingerprints_count": 3,
            "error_count": 0,
        },
    )
    _write_json(
        audit_dir / "code_inventory_2026-06-19.json",
        {
            "totals": {"files": 3, "lines": 30, "definitions": 4, "imports": 5},
            "parse_error_count": 0,
        },
    )
    _write_json(
        audit_dir / "data_catalog_2026-06-19.json",
        {
            "roots": {
                "/Volumes/dockcase2tb/database_all": {
                    "csv_headers_read": 20,
                    "csv_data_rows_sampled": 19,
                    "csv_files_without_sampled_data_row": 1,
                    "csv_row_width_mismatch_count": 0,
                    "csv_header_error_count": 0,
                },
                "/Volumes/dockcase2tb/market_data": {"data_files": 5},
            }
        },
    )
    _write_json(
        audit_dir / "dockcase_csv_file_evidence_2026-06-19.json",
        {
            "summary": {
                "csv_files_seen": 20,
                "file_evidence_count": 20,
                "signature_count": 3,
                "header_read_error_count": 0,
                "fingerprint_error_count": 0,
                "files_with_data_row_evidence": 19,
                "header_only_or_no_tail_data_files": 1,
                "first_tail_width_mismatch_count": 0,
                "all_seen_files_have_evidence_rows": True,
                "all_seen_files_have_head_tail_fingerprint": True,
                "coverage_boundary": {
                    "all_business_csv_files_have_file_evidence": True,
                    "full_row_semantic_scan": False,
                    "tail_row_is_derived_from_tail_byte_sample": True,
                },
            }
        },
    )
    _write_json(
        audit_dir / "dockcase_csv_full_scan_2026-06-19.json",
        {
            "summary": {
                "csv_files_seen": 200,
                "rows_scanned": 1522830,
                "row_read_error_count": 0,
                "full_row_semantic_scan": False,
                "coverage_boundary": {
                    "all_business_csv_files_selected": False,
                    "all_selected_files_read_to_eof": True,
                    "full_row_semantic_scan": False,
                    "max_files_limit": 200,
                    "skip_files": 0,
                },
            }
        },
    )
    _write_json(
        audit_dir / "dockcase_csv_full_scan_progress_2026-06-19.json",
        {
            "summary": {
                "shard_count": 2,
                "total_business_csv_files": 20,
                "csv_files_scanned": 400,
                "rows_scanned": 2721034,
                "row_read_error_count": 0,
                "full_row_semantic_scan_complete": False,
            }
        },
    )
    _write_json(
        audit_dir / "dockcase_csv_semantics_2026-06-18.json",
        {
            "summary": {
                "csv_files_seen": 20,
                "signature_count": 3,
                "sampled_signature_count": 3,
                "selected_files": 4,
                "sampled_files": 4,
                "sampled_rows": 120,
                "coverage_gaps": {
                    "header_read_error_files": 0,
                    "unsampled_signatures": 0,
                    "signatures_selected_but_no_sampled_rows": 0,
                    "csv_files_not_selected_for_row_sampling": 16,
                    "csv_files_selected_but_no_sampled_rows": 0,
                    "bounded_row_sampling": True,
                },
                "issue_counts": {"sparse_columns_lt_5pct_non_empty": 1},
            }
        },
    )
    _write_json(
        audit_dir / "dockcase_backlog_batch_2026-06-18.json",
        {
            "target_ranks": [46],
            "summary": {
                "matched_files": 28,
                "sampled_files": 28,
                "sampled_rows": 5600,
                "row_width_mismatch_count": 0,
                "header_read_error_count": 0,
                "issue_counts": {"index_by_symbol_bundle_mismatch": 5600},
            },
        },
    )
    _write_json(
        audit_dir / "dockcase_backlog_batch_r27_r31_2026-06-18.json",
        {
            "target_ranks": [27, 31],
            "summary": {
                "matched_files": 324,
                "sampled_files": 100,
                "sampled_rows": 20000,
                "row_width_mismatch_count": 0,
                "header_read_error_count": 0,
                "issue_counts": {"index_by_symbol_bundle_mismatch": 20000},
            },
        },
    )
    _write_json(
        audit_dir / "a_share_data_semantics_2026-06-18.json",
        {"summary": {"total_rows_read": 100, "total_files_loaded": 4}},
    )
    _write_json(
        audit_dir / "market_documents_2026-06-18.json",
        {
            "summary": {
                "news_html_files": 5,
                "news_html_selected": 3,
                "announcement_pdf_files": 1,
                "announcement_pdf_selected": 1,
                "document_files_total": 6,
                "documents_selected_for_extractability_sampling": 4,
                "documents_successfully_parsed": 3,
                "coverage_gaps": {
                    "document_files_not_selected_for_extractability_sampling": 2,
                    "selected_documents_without_successful_parse": 1,
                    "news_html_files_not_selected": 2,
                    "announcement_pdf_files_not_selected": 0,
                    "bounded_document_sampling": True,
                    "entity_event_signals_are_sample_based": True,
                },
                "signal_counts": {
                    "sampled_documents": 3,
                    "entity_signal_samples": 2,
                    "event_keyword_samples": 2,
                },
            }
        },
    )
    _write_json(
        audit_dir / "bff_latency_2026-06-19.json",
        {"all_ok": True, "all_under_threshold": True, "max_observed_ms": 100},
    )
    _write_json(
        audit_dir / "bff_concurrent_probe_2026-06-19.json",
        {
            "summary": {
                "all_ok": True,
                "all_under_threshold": True,
                "endpoint_count": 8,
                "max_ms": 250,
            }
        },
    )
    _write_json(
        audit_dir / "frontend_browser_qa_2026-06-18.json",
        {
            "all_warm_under_threshold": False,
            "latest_project_ult_route_recheck": {
                "measurement": "navigation commit to first h1 identity render",
                "summary": {"warm_commit_to_h1_under_1000ms": True},
                "routes": [
                    {"route": "/project-ult/system", "sample_ms": 75, "result": "pass"},
                    {"route": "/project-ult/evidence", "sample_ms": 75, "result": "pass"},
                ],
            },
            "routes": {
                "market_overview": {
                    "warm_median_ms": 101,
                    "any_error_overlay": False,
                },
            },
        },
    )
    _write_json(
        audit_dir / "frontend_shell_latency_2026-06-19.json",
        {
            "all_ok": True,
            "all_under_threshold": True,
            "route_count": 20,
            "max_observed_ms": 25,
        },
    )
    _write_json(
        audit_dir / "frontend_stock_detail_perf_probe_2026-06-19.json",
        {
            "summary": {
                "path_graph_ready_under_1000ms": True,
                "path_graph_ready_ms": 900,
                "console_error_warn_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "frontend_project_ult_navigation_2026-06-19.json",
        {
            "all_ok": True,
            "summary": {
                "app_route_count": 20,
                "app_routes_shell_covered": 20,
                "read_only_link_count": 8,
                "read_only_links_declared": 8,
                "read_only_links_shell_covered": 8,
                "missing_route_shell_count": 0,
                "missing_link_shell_count": 0,
                "undeclared_read_only_link_count": 0,
                "shell_route_count": 20,
                "shell_all_ok": True,
                "shell_all_under_threshold": True,
                "shell_max_observed_ms": 25,
            },
        },
    )
    _write_json(
        audit_dir / "module_status_2026-06-19.json",
        {
            "counts": {"locked_total": 14, "normal_running": 0},
            "local_runtime_data_tooling_surfaces": {
                "counts": {
                    "local_total": 17,
                    "normal_running": 9,
                    "normal_but_not_enabled": 7,
                    "not_usable": 1,
                },
            },
            "combined_inventory_counts": {
                "inventory_total": 31,
                "normal_running": 9,
                "normal_but_not_enabled": 7,
                "not_usable": 14,
                "normal_dependency_not_service": 1,
            },
            "classification_policy": {
                "normal_running_bucket_means": (
                    "audit evidence proves the local surface is runnable or serviceable; "
                    "it does not assert that a persistent process is currently listening"
                ),
                "live_process_ok_null_means": "not checked by this inventory audit",
            },
            "runtime_evidence_policy": {
                "runtime_state_is_the_preferred_semantic_status": True,
                "evidence_level_describes_current_proof_strength": True,
            },
        },
    )
    _write_json(
        audit_dir / "a_share_score_trace_2026-06-18.json",
        {"summary": {"spec_total": 256, "participating_gap_dp_ids": 69}},
    )
    _write_json(
        audit_dir / "a_share_score_gap_priority_2026-06-18.json",
        {
            "summary": {
                "participating_gap_dp_ids": 69,
                "actionable_formula_gap_dp_ids": 0,
                "actionable_participating_gap_dp_ids": 34,
                "governance_or_intentional_participating_gap_dp_ids": 21,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_gap_candidate_evidence_2026-06-19.json",
        {
            "summary": {
                "blocking_gap_count": 34,
                "candidate_input_ready_count": 34,
                "candidate_input_not_ready_count": 0,
                "safe_to_upsert_without_review_count": 0,
                "candidate_status_counts": {
                    "ready_for_event_llm_candidate": 12,
                    "ready_for_local_llm_candidate": 15,
                    "ready_for_local_llm_candidate_with_grain_join": 1,
                    "ready_for_manual_design_candidate": 5,
                    "ready_for_web_event_candidate": 1,
                },
                "score_mutation": "none; this audit is read-only and does not alter realtime_current",
            }
        },
    )
    _write_json(
        audit_dir / "a_share_candidate_score_dry_run_2026-06-19.json",
        {
            "summary": {
                "candidate_ready_rows_checked": 34,
                "bridge_signal_ready_count": 34,
                "node_emitted_count": 34,
                "final_score_target_ready_count": 34,
                "bridge_blocked_count": 0,
                "bridge_blocked_dp_ids": [],
            }
        },
    )
    _write_json(
        audit_dir / "a_share_candidate_upsert_safety_2026-06-19.json",
        {
            "summary": {
                "candidate_rows_checked": 34,
                "candidate_input_ready_count": 34,
                "bridge_ready_count": 34,
                "review_gated_count": 34,
                "blocked_count": 0,
                "blocked_dp_ids": [],
                "safe_to_upsert_without_review_count": 0,
                "upsert_safety_class_counts": {
                    "neutral_candidate_review_required": 1,
                    "not_applicable_candidate_review_required": 1,
                    "review_required": 32,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_candidate_staging_payloads_2026-06-19.json",
        {
            "summary": {
                "candidate_rows_checked": 34,
                "deterministic_staging_payload_count": 2,
                "generator_required_count": 32,
                "blocked_count": 0,
                "staging_payload_bridge_ready_count": 2,
                "dry_run_bridge_ready_count": 34,
                "review_required_count": 34,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_candidate_value_contracts_2026-06-19.json",
        {
            "summary": {
                "candidate_rows_checked": 34,
                "contract_valid_count": 34,
                "contract_invalid_count": 0,
                "invalid_dp_ids": [],
                "concrete_payload_valid_count": 2,
                "placeholder_payload_valid_count": 32,
                "bridge_validated_concrete_count": 2,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_spec_numeric_validity_2026-06-19.json",
        {
            "summary": {
                "configured_spec_total_dp_ids": 256,
                "runtime_trace_spec_total_dp_ids": 256,
                "spec_total_matches_runtime": True,
                "score_relevant_spec_dp_ids": 174,
                "current_final_score_numeric_dp_ids": 119,
                "current_score_relevant_not_final_score_dp_ids": 55,
                "candidate_dry_run_bridge_ready_dp_ids": 34,
                "review_ready_concrete_final_score_dp_ids": 27,
                "review_gated_unknown_dp_ids": 7,
                "approval_missing_count": 25,
                "approved_runtime_write_count": 2,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_spec_score_conversion_path_2026-06-19.json",
        {
            "summary": {
                "total_checked_count": 256,
                "score_relevant_final_target_count": 174,
                "current_numeric_final_score_count": 119,
                "candidate_numeric_score_path_ready_count": 34,
                "sample_numeric_score_path_ready_count": 4,
                "numeric_and_score_path_ready_count": 157,
                "unresolved_score_relevant_count": 17,
                "not_numeric_or_no_formula_count": 14,
                "no_current_numeric_input_count": 3,
                "formula_policy_review_required_count": 6,
                "governance_suppression_verified_count": 8,
                "option_universe_na_verified_count": 3,
                "verified_non_numeric_exception_count": 11,
                "review_decision_backed_not_ready_count": 17,
                "remaining_unclassified_conversion_gap_count": 0,
                "formula_policy_packet_artifact_count": 6,
                "governance_suppression_artifact_verified_count": 8,
                "option_universe_na_artifact_valid_count": 3,
                "no_weight_or_non_scoring_count": 82,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_score_conversion_remediation_queue_2026-06-19.json",
        {
            "summary": {
                "unresolved_score_relevant_count": 17,
                "existing_current_input_count": 14,
                "no_current_input_count": 3,
                "formula_policy_required_count": 6,
                "intentional_governance_or_duplicate_count": 8,
                "missing_or_not_applicable_source_count": 3,
                "safe_formula_now_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_formula_policy_review_packets_2026-06-19.json",
        {
            "summary": {
                "formula_policy_packet_count": 6,
                "current_input_available_count": 6,
                "valuation_peer_context_packet_count": 3,
                "business_semantics_packet_count": 3,
                "replacement_path_ready_count": 3,
                "direct_formula_ready_count": 0,
                "policy_contract_valid_count": 6,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_governance_suppression_verification_2026-06-19.json",
        {
            "summary": {
                "governance_suppression_packet_count": 8,
                "suppression_verified_count": 8,
                "replacement_or_canonical_ready_count": 6,
                "direct_signal_suppressed_count": 8,
                "peer_context_suppressed_count": 2,
                "requires_governance_review_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_option_universe_na_verification_2026-06-19.json",
        {
            "summary": {
                "option_universe_packet_count": 3,
                "no_current_a_share_input_count": 3,
                "listed_option_universe_required_count": 3,
                "na_or_unavailable_allowed_after_review_count": 3,
                "known_value_allowed_now_count": 0,
                "verification_contract_valid_count": 3,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_candidate_generation_queue_2026-06-19.json",
        {
            "summary": {
                "generator_required_task_count": 32,
                "skipped_non_generator_count": 2,
                "generator_kind_counts": {
                    "event_llm_candidate": 12,
                    "local_llm_candidate": 16,
                    "manual_policy_candidate": 4,
                },
                "all_tasks_have_valid_placeholder_contract": True,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_l0_source_readiness_2026-06-19.json",
        {
            "summary": {
                "blocking_gap_count": 32,
                "priority_counts": {
                    "P2_llm_or_web_extraction": 28,
                    "P3_manual_review": 4,
                },
                "recommended_source_route_counts": {
                    "event_llm_from_runtime_news": 12,
                    "local_llm_closed_loop": 16,
                    "manual_design_review": 4,
                },
                "direct_structured_tushare_remaining": 0,
                "dependency_dp_ids_with_runtime_rows": [
                    "L0.cost.raw_material",
                    "L4.cost.labor",
                    "L4.eff.cycle",
                    "L4.eff.turnover",
                    "L5.bs.goodwill_ppe",
                    "L5.bs.inventory",
                    "L5.cf.capex",
                    "L5.is.gross_margin",
                    "L5.is.revenue",
                    "L5.is.revenue_growth",
                    "L5.is.sga_rd",
                    "L9.disclosure.qa_recent",
                    "L9.industry.compete_risk",
                    "L9.industry.policy_change",
                    "L9.macro.fx",
                    "L9.macro.geo",
                    "L9.media.report",
                ],
                "dependency_dp_ids_without_runtime_rows": [],
            }
        },
    )
    _write_json(
        audit_dir / "a_share_short_report_evidence_2026-06-19.json",
        {
            "summary": {
                "news_html_files_scanned": 14956,
                "parse_error_count": 0,
                "strict_short_report_documents": 4,
                "direct_a_share_short_report_documents": 0,
                "foreign_or_market_short_report_documents": 4,
                "direct_a_share_ts_code_count": 0,
                "candidate_evidence_ready": True,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_non_manual_candidate_readiness_2026-06-19.json",
        {
            "summary": {
                "non_manual_task_count": 28,
                "generator_kind_counts": {
                    "event_llm_candidate": 12,
                    "local_llm_candidate": 16,
                },
                "route_bucket_counts": {
                    "event_text_classification_required": 12,
                    "local_single_dependency_policy_required": 3,
                    "local_structured_llm_required": 10,
                    "local_structured_text_llm_required": 3,
                },
                "dependency_readiness_counts": {
                    "all_dependencies_have_material_known_coverage": 28
                },
                "placeholder_contract_valid_count": 28,
                "output_contract_shape_valid_count": 28,
                "bridge_probe_ready_count": 28,
                "bridge_probe_blocked_count": 0,
                "deterministic_known_draft_allowed_count": 0,
                "review_required_count": 28,
                "production_write_allowed_count": 0,
                "safe_to_upsert_without_review_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_single_dependency_policy_drafts_2026-06-19.json",
        {
            "summary": {
                "single_dependency_task_count": 3,
                "draft_known_count": 2,
                "draft_unknown_count": 1,
                "draft_contract_valid_count": 3,
                "draft_contract_invalid_count": 0,
                "draft_contract_invalid_dp_ids": [],
                "bridge_validated_known_count": 2,
                "bridge_blocked_known_count": 0,
                "review_required_count": 3,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "draft_status_counts": {
                    "draft_known_review_required": 2,
                    "unknown_policy_required": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_single_dependency_unknown_source_options_2026-06-19.json",
        {
            "summary": {
                "unknown_local_single_dependency_count": 1,
                "existing_runtime_dependency_ready_count": 1,
                "direct_replacement_cycle_source_ready_count": 0,
                "overlay_candidate_hint_count": 1,
                "rows_with_overlay_lifecycle_context_candidate_count": 1,
                "overlay_lifecycle_known_node_count": 205,
                "overlay_replacement_known_node_count": 0,
                "overlay_replacement_unknown_node_count": 1646,
                "candidate_requires_lifecycle_source_count": 1,
                "candidate_requires_review_policy_count": 1,
                "lifecycle_policy_review_template_count": 1,
                "lifecycle_policy_review_template_contract_valid_count": 1,
                "lifecycle_policy_review_template_contract_invalid_count": 0,
                "lifecycle_policy_review_template_blank_pending_count": 1,
                "lifecycle_policy_review_template_input_ready_count": 0,
                "auto_known_candidate_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "review_required_count": 1,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "resolution_status_counts": {
                    "requires_lifecycle_or_replacement_cycle_source": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_policy_drafts_2026-06-19.json",
        {
            "summary": {
                "local_structured_task_count": 10,
                "draft_known_count": 6,
                "draft_unknown_count": 4,
                "draft_contract_valid_count": 10,
                "draft_contract_invalid_count": 0,
                "draft_contract_invalid_dp_ids": [],
                "bridge_validated_known_count": 6,
                "bridge_blocked_known_count": 0,
                "review_required_count": 10,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "draft_status_counts": {
                    "draft_known_pass_through_review_required": 1,
                    "draft_known_review_required": 5,
                    "unknown_policy_required": 4,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_unknown_source_options_2026-06-19.json",
        {
            "summary": {
                "unknown_local_structured_count": 4,
                "existing_runtime_dependency_ready_count": 4,
                "direct_existing_structured_source_ready_count": 0,
                "overlay_candidate_hint_count": 4,
                "candidate_requires_new_mapping_count": 4,
                "candidate_requires_review_policy_count": 0,
                "partial_known_unlock_candidate_count": 0,
                "auto_known_candidate_count": 0,
                "review_required_count": 4,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "resolution_status_counts": {
                    "requires_market_share_or_tam_source": 1,
                    "requires_new_field_mapping_or_text_extraction": 1,
                    "requires_volume_mix_or_price_index": 1,
                    "requires_volume_or_usage_source": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_source_candidates_2026-06-19.json",
        {
            "summary": {
                "unknown_dp_count": 4,
                "runtime_dependency_ready_count": 4,
                "direct_known_ready_count": 0,
                "review_candidate_dp_count": 2,
                "review_candidate_match_count": 1,
                "supporting_candidate_match_count": 4,
                "empty_candidate_match_count": 1,
                "no_direct_catalog_source_count": 2,
                "excluded_false_positive_count": 407,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_source_review_packets_2026-06-19.json",
        {
            "summary": {
                "local_structured_source_review_packet_count": 4,
                "review_candidate_ready_count": 1,
                "supporting_candidate_needs_quantity_source_count": 1,
                "external_source_required_count": 2,
                "direct_known_ready_count": 0,
                "formula_inputs_ready_count": 0,
                "candidate_packet_count": 2,
                "candidate_column_count": 5,
                "empty_candidate_column_count": 1,
                "packet_contract_valid_count": 4,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_policy_drafts_2026-06-19.json",
        {
            "summary": {
                "event_text_task_count": 12,
                "draft_known_count": 10,
                "draft_unknown_count": 2,
                "draft_contract_valid_count": 12,
                "draft_contract_invalid_count": 0,
                "draft_contract_invalid_dp_ids": [],
                "bridge_validated_known_count": 10,
                "bridge_blocked_known_count": 0,
                "market_doc_known_review_draft_count": 10,
                "market_doc_unknown_policy_required_count": 1,
                "market_doc_unknown_evidence_required_count": 1,
                "review_required_count": 12,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "draft_status_counts": {
                    "draft_known_market_doc_review_required": 10,
                    "unknown_market_doc_evidence_required": 1,
                    "unknown_market_doc_policy_required": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_classification_inputs_2026-06-19.json",
        {
            "summary": {
                "classification_input_packet_count": 12,
                "classification_input_ready_count": 12,
                "missing_headline_input_count": 0,
                "headline_input_count": 78,
                "unique_headline_count": 8,
                "full_article_text_available_count": 0,
                "title_level_only_count": 12,
                "classified_known_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_preclassification_screen_2026-06-19.json",
        {
            "summary": {
                "preclassification_packet_count": 12,
                "packets_screened_count": 12,
                "title_level_only_count": 12,
                "target_keyword_hit_packet_count": 3,
                "a_share_transmission_hit_packet_count": 11,
                "target_and_transmission_hit_packet_count": 2,
                "direct_known_candidate_count": 0,
                "classified_known_count": 0,
                "review_required_count": 12,
                "safe_to_upsert_without_review_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_sufficiency_gate_2026-06-19.json",
        {
            "summary": {
                "sufficiency_packet_count": 12,
                "title_level_only_count": 12,
                "target_headline_packet_count": 3,
                "broad_market_only_transmission_packet_count": 11,
                "same_headline_target_and_any_transmission_packet_count": 0,
                "same_headline_target_and_direct_transmission_packet_count": 0,
                "title_signal_sufficient_for_classifier_count": 0,
                "known_candidate_allowed_count": 0,
                "review_required_count": 12,
                "safe_to_upsert_without_review_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_url_fetchability_2026-06-19.json",
        {
            "summary": {
                "unique_url_count": 8,
                "fetch_success_count": 8,
                "fetch_failure_count": 0,
                "primary_text_available_url_count": 8,
                "body_packet_count": 12,
                "body_text_available_packet_count": 12,
                "body_target_hit_packet_count": 3,
                "body_direct_transmission_hit_packet_count": 0,
                "body_broad_market_transmission_hit_packet_count": 11,
                "body_signal_sufficient_for_classifier_count": 0,
                "known_candidate_allowed_count": 0,
                "safe_to_upsert_without_review_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_unknown_source_options_2026-06-19.json",
        {
            "summary": {
                "unknown_event_text_count": 2,
                "classification_input_ready_count": 2,
                "body_text_available_count": 2,
                "target_event_evidence_present_count": 0,
                "direct_a_share_transmission_present_count": 0,
                "broad_market_transmission_only_count": 2,
                "classifier_ready_for_review_count": 0,
                "candidate_requires_target_event_evidence_count": 2,
                "candidate_requires_direct_a_share_transmission_count": 0,
                "auto_known_candidate_count": 0,
                "review_required_count": 2,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "resolution_status_counts": {
                    "requires_target_event_evidence": 2,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_market_doc_evidence_2026-06-19.json",
        {
            "summary": {
                "unknown_event_text_rows_checked": 12,
                "market_html_files_scanned": 14956,
                "market_html_read_error_count": 0,
                "rows_with_market_doc_target_evidence_count": 12,
                "rows_with_market_doc_direct_transmission_count": 12,
                "rows_with_market_doc_target_and_direct_count": 12,
                "rows_with_same_sentence_candidate_count": 11,
                "rows_still_requiring_target_evidence_count": 0,
                "rows_still_requiring_direct_transmission_link_count": 1,
                "market_doc_review_candidate_count": 11,
                "auto_known_candidate_count": 0,
                "review_required_count": 12,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_text_market_doc_review_packets_2026-06-19.json",
        {
            "summary": {
                "event_text_packet_count": 12,
                "market_doc_review_ready_count": 11,
                "requires_target_event_evidence_count": 0,
                "requires_direct_transmission_link_count": 1,
                "candidate_example_count": 53,
                "packet_contract_valid_count": 12,
                "packet_contract_invalid_count": 0,
                "auto_known_candidate_count": 0,
                "review_required_count": 12,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_text_policy_drafts_2026-06-19.json",
        {
            "summary": {
                "local_structured_text_task_count": 3,
                "draft_known_count": 3,
                "draft_unknown_count": 0,
                "draft_contract_valid_count": 3,
                "draft_contract_invalid_count": 0,
                "draft_contract_invalid_dp_ids": [],
                "bridge_validated_known_count": 3,
                "bridge_blocked_known_count": 0,
                "qa_discount_pressure_known_draft_count": 1,
                "qa_channel_service_known_draft_count": 1,
                "review_required_count": 3,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "draft_status_counts": {
                    "draft_known_qa_channel_service_review_required": 1,
                    "draft_known_qa_discount_pressure_review_required": 1,
                    "unknown_text_classification_required": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_structured_text_unknown_source_options_2026-06-19.json",
        {
            "summary": {
                "unknown_local_structured_text_count": 0,
                "existing_runtime_dependency_ready_count": 0,
                "qa_recent_dependency_ready_count": 0,
                "direct_text_classification_ready_count": 0,
                "overlay_candidate_hint_count": 0,
                "candidate_requires_text_classification_count": 0,
                "auto_known_candidate_count": 0,
                "review_required_count": 0,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "resolution_status_counts": {},
            }
        },
    )
    _write_json(
        audit_dir / "a_share_manual_policy_draft_candidates_2026-06-19.json",
        {
            "summary": {
                "manual_policy_task_count": 4,
                "draft_payload_count": 4,
                "draft_known_count": 4,
                "draft_unknown_count": 0,
                "draft_contract_valid_count": 4,
                "draft_contract_invalid_count": 0,
                "draft_contract_invalid_dp_ids": [],
                "bridge_validated_known_count": 4,
                "bridge_blocked_known_count": 0,
                "review_required_count": 4,
                "pilot_only_count": 4,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "draft_status_counts": {
                    "draft_known_review_required": 3,
                    "draft_known_standard_dcf_assumption_review_required": 1,
                },
            }
        },
    )
    _write_json(
        audit_dir / "a_share_manual_policy_unknown_source_options_2026-06-19.json",
        {
            "summary": {
                "unknown_manual_policy_count": 0,
                "dependency_pack_ready_count": 0,
                "direct_reviewed_assumption_ready_count": 0,
                "required_assumption_count": 0,
                "candidate_requires_assumption_review_count": 0,
                "candidate_requires_review_policy_count": 0,
                "auto_known_candidate_count": 0,
                "review_required_count": 0,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "resolution_status_counts": {},
            }
        },
    )
    _write_json(
        audit_dir / "a_share_review_staging_manifest_2026-06-19.json",
        {
            "summary": {
                "candidate_blocking_rows": 34,
                "review_manifest_entries": 34,
                "candidate_rows_with_review_entry": 34,
                "missing_review_entry_count": 0,
                "missing_review_entry_dp_ids": [],
                "review_ready_concrete_count": 27,
                "review_gated_unknown_count": 7,
                "known_payload_count": 26,
                "not_applicable_payload_count": 1,
                "unknown_payload_count": 7,
                "contract_valid_count": 34,
                "contract_invalid_count": 0,
                "contract_invalid_dp_ids": [],
                "bridge_ready_concrete_count": 27,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
                "approved_runtime_write_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_review_approvals_2026-06-19.json",
        {
            "summary": {
                "manifest_row_count": 34,
                "deterministic_policy_count": 2,
                "approval_record_count": 2,
                "approved_deterministic_runtime_write_count": 2,
                "deterministic_policy_rejected_count": 0,
                "not_in_deterministic_policy_count": 32,
                "approval_contract_valid_count": 2,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_review_approval_gate_2026-06-19.json",
        {
            "summary": {
                "review_manifest_entries": 34,
                "review_ready_concrete_count": 27,
                "review_gated_unknown_count": 7,
                "approval_records_seen": 2,
                "orphan_approval_record_count": 0,
                "orphan_approval_records": [],
                "approval_required_count": 27,
                "approval_missing_count": 25,
                "rejected_approval_count": 0,
                "approved_runtime_write_count": 2,
                "write_plan_count": 2,
                "not_approvable_unknown_count": 7,
                "safe_to_upsert_without_review_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_completion_next_actions_2026-06-19.json",
        {
            "summary": {
                "actionable_gap_count": 34,
                "approval_ready_packet_count": 25,
                "runtime_write_plan_ready_count": 2,
                "approval_record_template_count": 25,
                "unknown_resolution_required_count": 7,
                "event_text_classification_required_count": 2,
                "local_structured_mapping_required_count": 4,
                "structured_text_extraction_required_count": 0,
                "single_dependency_policy_required_count": 1,
                "manual_assumption_review_required_count": 0,
                "approved_runtime_write_count": 2,
                "write_plan_count": 2,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_closure_matrix_2026-06-19.json",
        {
            "summary": {
                "closure_matrix_row_count": 7,
                "unknown_closure_row_count": 7,
                "closure_route_assigned_count": 7,
                "missing_closure_route_count": 0,
                "review_ready_concrete_count": 27,
                "review_gated_unknown_count": 7,
                "approval_ready_packet_count": 27,
                "auto_known_ready_count": 0,
                "approval_ready_count": 0,
                "event_text_classification_required_count": 2,
                "local_structured_mapping_required_count": 4,
                "structured_text_extraction_required_count": 0,
                "single_dependency_policy_required_count": 1,
                "manual_assumption_review_required_count": 0,
                "rows_with_source_candidates_count": 3,
                "formula_inputs_ready_count": 0,
                "closure_contract_valid_count": 7,
                "closure_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_acquisition_backlog_2026-06-19.json",
        {
            "summary": {
                "acquisition_task_count": 7,
                "unknown_acquisition_task_count": 7,
                "event_doc_search_task_count": 2,
                "local_formula_source_task_count": 2,
                "external_business_source_task_count": 3,
                "tasks_with_existing_candidate_evidence_count": 3,
                "tasks_with_runtime_overlay_hints_count": 1,
                "web_or_external_acquisition_required_count": 6,
                "llm_allowed_count": 7,
                "formula_inputs_ready_count": 0,
                "ready_for_auto_known_count": 0,
                "ready_for_approval_count": 0,
                "task_contract_valid_count": 7,
                "task_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_market_doc_acquisition_candidates_2026-06-19.json",
        {
            "summary": {
                "market_doc_acquisition_task_count": 2,
                "market_html_files_scanned": 14956,
                "market_html_read_error_count": 0,
                "rows_with_review_candidates_count": 2,
                "new_entrant_window_candidate_count": 5,
                "new_entrant_review_candidate_count": 6,
                "substitute_same_sentence_candidate_count": 34,
                "substitute_clean_risk_review_candidate_count": 3,
                "weak_candidate_count": 9,
                "rejected_candidate_count": 34,
                "known_draft_sufficient_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_event_evidence_adjudication_2026-06-19.json",
        {
            "summary": {
                "event_unknown_adjudication_row_count": 2,
                "candidate_examples_reviewed_count": 14,
                "accepted_candidate_count": 0,
                "rejected_or_ambiguous_candidate_count": 14,
                "remaining_unknown_count": 2,
                "known_draft_sufficient_count": 0,
                "auto_known_ready_count": 0,
                "approval_ready_count": 0,
                "adjudication_contract_valid_count": 2,
                "adjudication_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_event_strict_source_gate_2026-06-19.json",
        {
            "summary": {
                "event_strict_gate_row_count": 2,
                "market_html_files_scanned": 14956,
                "market_html_read_error_count": 0,
                "strict_candidate_count": 11,
                "strict_review_candidate_count": 8,
                "strict_rejected_count": 3,
                "rows_with_strict_review_candidates_count": 2,
                "rows_without_strict_source_candidate_count": 0,
                "classifier_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "strict_gate_contract_valid_count": 2,
                "strict_gate_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_event_strict_review_packets_2026-06-19.json",
        {
            "summary": {
                "strict_review_packet_count": 8,
                "strict_review_rows_count": 2,
                "source_quality_low_confidence_count": 2,
                "source_quality_secondary_newswire_count": 6,
                "requires_primary_source_confirmation_count": 2,
                "requires_manual_review_count": 0,
                "deterministic_rejected_count": 6,
                "classifier_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "packet_contract_valid_count": 8,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_event_primary_source_confirmation_2026-06-19.json",
        {
            "summary": {
                "primary_confirmation_packet_count": 2,
                "market_html_files_scanned": 14956,
                "market_html_read_error_count": 0,
                "local_candidate_count": 12,
                "local_high_quality_confirmation_candidate_count": 0,
                "local_supporting_context_only_count": 12,
                "rows_with_local_confirmation_candidate_count": 0,
                "rows_with_supporting_context_only_count": 2,
                "rows_without_local_confirmation_candidate_count": 0,
                "classifier_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "confirmation_contract_valid_count": 2,
                "confirmation_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_event_external_source_confirmation_2026-06-19.json",
        {
            "summary": {
                "external_confirmation_packet_count": 2,
                "external_source_card_count": 6,
                "external_confirmation_candidate_count": 2,
                "external_supporting_context_count": 4,
                "rows_with_external_confirmation_candidate_count": 2,
                "rows_with_external_supporting_context_only_count": 0,
                "classifier_input_candidate_count": 2,
                "classifier_input_candidate_contract_valid_count": 2,
                "classifier_input_candidate_contract_invalid_count": 0,
                "classifier_input_candidate_ready_count": 0,
                "classifier_input_review_required_count": 2,
                "classifier_input_primary_source_covered_count": 2,
                "classifier_input_required_label_count": 12,
                "classifier_input_guardrail_count": 6,
                "classifier_review_template_count": 2,
                "classifier_review_template_contract_valid_count": 2,
                "classifier_review_template_contract_invalid_count": 0,
                "classifier_review_template_blank_pending_count": 2,
                "classifier_review_template_input_ready_count": 0,
                "classifier_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "external_confirmation_contract_valid_count": 2,
                "external_confirmation_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_local_formula_acquisition_candidates_2026-06-19.json",
        {
            "summary": {
                "local_formula_acquisition_task_count": 2,
                "runtime_dependency_ready_count": 2,
                "sample_csv_files_checked": 6,
                "sample_csv_files_existing": 6,
                "sample_csv_read_error_count": 0,
                "formula_input_group_count": 8,
                "formula_input_group_ready_count": 0,
                "rows_with_candidate_numerator_count": 2,
                "rows_with_direct_denominator_count": 0,
                "rows_with_quantity_or_price_index_count": 0,
                "rows_with_formula_policy_count": 0,
                "formula_inputs_ready_count": 0,
                "ready_for_known_draft_count": 0,
                "packet_contract_valid_count": 2,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_local_formula_review_packets_2026-06-19.json",
        {
            "summary": {
                "local_formula_review_packet_count": 2,
                "rows_with_candidate_numerator_count": 2,
                "rows_with_direct_denominator_count": 0,
                "rows_with_denominator_candidate_count": 1,
                "rows_with_candidate_formula_shape_count": 1,
                "rows_with_formula_policy_draft_candidate_count": 1,
                "formula_policy_review_template_count": 1,
                "formula_policy_review_template_contract_valid_count": 1,
                "formula_policy_review_template_blank_pending_count": 1,
                "rows_with_price_index_context_candidate_count": 1,
                "rows_with_candidate_price_context_shape_count": 1,
                "price_context_review_template_count": 1,
                "price_context_review_template_contract_valid_count": 1,
                "price_context_review_template_blank_pending_count": 1,
                "rows_with_quantity_or_price_index_count": 0,
                "rows_with_formula_policy_count": 0,
                "formula_inputs_ready_count": 0,
                "formula_probe_available_count": 0,
                "bridge_probe_ready_count": 0,
                "selected_value_json_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "local_formula_review_contract_valid_count": 2,
                "local_formula_review_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_local_formula_source_capability_2026-06-19.json",
        {
            "summary": {
                "local_formula_source_capability_row_count": 2,
                "source_capability_check_count": 8,
                "source_candidate_present_count": 6,
                "header_available_but_sample_empty_count": 1,
                "candidate_context_or_proxy_count": 3,
                "review_policy_required_count": 3,
                "external_or_text_required_count": 1,
                "formula_blocker_resolved_by_current_source_count": 0,
                "formula_inputs_ready_after_source_scan_count": 0,
                "formula_probe_available_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_external_business_metric_acquisition_2026-06-19.json",
        {
            "summary": {
                "external_business_metric_task_count": 3,
                "runtime_dependency_ready_count": 3,
                "runtime_overlay_hint_count": 7,
                "business_metric_group_count": 12,
                "business_metric_group_ready_count": 0,
                "rows_with_supporting_runtime_context_count": 3,
                "rows_with_overlay_business_context_candidate_count": 2,
                "overlay_business_context_known_node_count": 527,
                "overlay_frequency_context_known_node_count": 166,
                "overlay_penetration_context_known_node_count": 361,
                "overlay_frequency_direct_known_node_count": 0,
                "overlay_penetration_direct_known_node_count": 0,
                "overlay_frequency_direct_unknown_node_count": 1646,
                "overlay_penetration_direct_unknown_node_count": 1646,
                "rows_with_direct_business_metric_source_count": 0,
                "rows_requiring_external_or_text_source_count": 3,
                "excluded_false_positive_count": 238,
                "metric_inputs_ready_count": 0,
                "ready_for_known_draft_count": 0,
                "packet_contract_valid_count": 3,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_external_business_metric_market_doc_candidates_2026-06-19.json",
        {
            "summary": {
                "business_metric_market_doc_task_count": 3,
                "market_html_files_scanned": 14956,
                "market_html_read_error_count": 0,
                "rows_with_review_candidates_count": 3,
                "candidate_document_count": 178,
                "review_candidate_count": 99,
                "numeric_review_candidate_count": 49,
                "textual_review_candidate_count": 50,
                "weak_candidate_count": 82,
                "rejected_candidate_count": 72,
                "known_draft_sufficient_count": 0,
                "metric_inputs_ready_count": 0,
                "packet_contract_valid_count": 3,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_external_business_metric_review_packets_2026-06-19.json",
        {
            "summary": {
                "business_metric_review_packet_count": 99,
                "expected_review_candidate_count": 99,
                "review_candidate_retention_complete": True,
                "rows_with_review_packets_count": 3,
                "numeric_review_packet_count": 49,
                "textual_review_packet_count": 50,
                "metric_inputs_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "packets_with_scope_candidate_count": 99,
                "packets_with_denominator_candidate_count": 70,
                "packets_with_period_candidate_count": 36,
                "packets_with_unit_candidate_count": 49,
                "packet_contract_valid_count": 99,
                "packet_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json",
        {
            "summary": {
                "business_metric_review_packet_count": 99,
                "formula_policy_only_candidate_count": 18,
                "period_or_unit_required_count": 52,
                "denominator_required_count": 29,
                "missing_denominator_count": 29,
                "missing_period_count": 63,
                "missing_unit_count": 50,
                "missing_bounds_count": 99,
                "missing_formula_policy_count": 99,
                "metric_inputs_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_external_business_metric_policy_drafts_2026-06-19.json",
        {
            "summary": {
                "p0_source_packet_count": 18,
                "policy_draft_packet_count": 18,
                "formula_policy_review_required_count": 18,
                "value_json_template_count": 18,
                "policy_review_template_count": 18,
                "policy_review_template_contract_valid_count": 18,
                "policy_review_template_contract_invalid_count": 0,
                "policy_review_template_blank_pending_count": 18,
                "policy_review_template_input_ready_count": 0,
                "metric_inputs_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "policy_contract_valid_count": 18,
                "policy_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
                "policy_draft_counts_by_dp_id": {
                    "L0.demand.frequency": 1,
                    "L0.demand.penetration": 17,
                },
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_external_business_metric_value_candidates_2026-06-19.json",
        {
            "summary": {
                "policy_draft_packet_count": 18,
                "value_candidate_adjudication_row_count": 18,
                "rows_with_value_candidate_tokens_count": 9,
                "value_candidate_token_count": 13,
                "rejected_numeric_token_count": 31,
                "shortlist_review_required_count": 6,
                "scope_rejected_count": 3,
                "scope_ambiguous_count": 0,
                "no_scoreable_numeric_candidate_count": 9,
                "metric_inputs_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "value_candidate_contract_valid_count": 18,
                "value_candidate_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_external_business_metric_value_review_packets_2026-06-19.json",
        {
            "summary": {
                "shortlist_source_row_count": 6,
                "value_review_packet_count": 6,
                "candidate_value_option_count": 8,
                "bridge_probe_ready_option_count": 8,
                "selected_raw_value_count": 0,
                "selected_value_json_count": 0,
                "metric_inputs_ready_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "value_review_contract_valid_count": 6,
                "value_review_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_business_metric_value_selection_gate_2026-06-19.json",
        {
            "summary": {
                "business_metric_selection_row_count": 3,
                "value_review_packet_count": 6,
                "candidate_value_option_count": 8,
                "bridge_probe_ready_option_count": 8,
                "review_value_selection_required_count": 0,
                "review_value_policy_draft_ready_count": 1,
                "value_policy_draft_ready_count": 1,
                "proposed_value_json_count": 1,
                "source_metric_missing_count": 2,
                "auto_selectable_count": 0,
                "selected_value_json_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "selection_contract_valid_count": 3,
                "selection_contract_invalid_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_penetration_value_priority_2026-06-19.json",
        {
            "summary": {
                "penetration_value_review_packet_count": 6,
                "candidate_value_option_count": 8,
                "bridge_probe_ready_option_count": 8,
                "preferred_source_scope_review_count": 1,
                "industry_scope_review_count": 1,
                "forecast_or_assumption_review_count": 2,
                "low_confidence_community_review_count": 2,
                "selected_raw_value_count": 0,
                "selected_value_json_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_penetration_p1_source_confirmation_2026-06-19.json",
        {
            "summary": {
                "p1_candidate_count": 1,
                "source_file_found_count": 1,
                "raw_value_token_confirmed_count": 1,
                "source_scope_confirmed_count": 1,
                "selected_raw_value_count": 0,
                "selected_value_json_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_unknown_penetration_value_policy_draft_2026-06-19.json",
        {
            "summary": {
                "draft_row_count": 1,
                "source_scope_confirmed_count": 1,
                "proposed_value_json_count": 1,
                "draft_contract_valid_count": 1,
                "draft_contract_invalid_count": 0,
                "bridge_final_score_ready_count": 1,
                "selected_raw_value_count": 0,
                "selected_value_json_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_packets_2026-06-19.json",
        {
            "summary": {
                "value_confirmation_packet_count": 1,
                "review_required_packet_count": 1,
                "source_scope_confirmed_count": 1,
                "proposed_value_json_count": 1,
                "final_score_target_ready_count": 1,
                "value_policy_draft_ready_count": 1,
                "confirmation_record_template_count": 1,
                "confirmation_record_template_contract_valid_count": 1,
                "confirmation_packet_contract_valid_count": 1,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_templates_2026-06-19.json",
        {
            "summary": {
                "source_confirmation_packet_count": 1,
                "confirmation_template_bundle_count": 1,
                "confirmation_template_count": 1,
                "blank_pending_template_count": 1,
                "blank_pending_template_contract_valid_count": 1,
                "blank_pending_template_contract_invalid_count": 0,
                "confirmation_record_input_ready_count": 0,
                "confirmed_template_count": 0,
                "known_draft_sufficient_count": 0,
                "approval_ready_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_penetration_value_confirmation_gate_2026-06-19.json",
        {
            "summary": {
                "confirmation_packet_count": 1,
                "confirmation_required_count": 1,
                "confirmation_records_seen": 0,
                "confirmation_missing_count": 1,
                "rejected_confirmation_count": 0,
                "confirmed_value_policy_count": 0,
                "packet_contract_invalid_count": 0,
                "known_draft_candidate_count": 0,
                "known_draft_emission_allowed_count": 0,
                "approval_ready_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_unknown_penetration_confirmed_known_drafts_2026-06-19.json",
        {
            "summary": {
                "confirmation_gate_row_count": 1,
                "confirmed_value_policy_candidate_count": 0,
                "known_draft_row_count": 1,
                "known_draft_emitted_count": 0,
                "known_draft_blocked_count": 1,
                "known_draft_contract_valid_count": 0,
                "ready_for_review_staging_count": 0,
                "approval_ready_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_review_packets_2026-06-19.json",
        {
            "summary": {
                "approval_review_packet_count": 27,
                "known_packet_count": 26,
                "not_applicable_packet_count": 1,
                "final_score_target_ready_count": 27,
                "approval_missing_count": 25,
                "approval_record_template_count": 25,
                "approval_record_template_contract_valid_count": 25,
                "approval_record_template_contract_invalid_count": 0,
                "approved_runtime_write_count": 2,
                "write_plan_count": 2,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_packet_risk_review_2026-06-19.json",
        {
            "summary": {
                "packet_count": 25,
                "bulk_structured_review_candidate_count": 6,
                "borderline_structured_text_review_candidate_count": 1,
                "individual_review_required_count": 18,
                "individual_event_evidence_review_required_count": 8,
                "individual_structured_review_required_count": 4,
                "individual_policy_review_required_count": 6,
                "do_not_approve_until_contract_fixed_count": 0,
                "auto_approval_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_bulk_review_approval_candidates_2026-06-19.json",
        {
            "summary": {
                "candidate_count": 7,
                "strict_bulk_candidate_count": 6,
                "borderline_sample_check_candidate_count": 1,
                "approval_record_draft_count": 7,
                "approval_record_draft_contract_valid_count": 7,
                "approval_record_draft_contract_invalid_count": 0,
                "auto_approval_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_event_approval_source_samples_2026-06-19.json",
        {
            "summary": {
                "event_approval_source_sample_count": 10,
                "event_text_approval_packet_count": 10,
                "individual_event_evidence_review_required_count": 8,
                "source_report_exists_count": 10,
                "source_report_row_found_count": 10,
                "source_payload_matches_candidate_count": 10,
                "source_contract_valid_count": 10,
                "source_bridge_final_score_ready_count": 10,
                "repo_doc_evidence_refs_complete_count": 10,
                "runtime_dependency_ref_complete_count": 10,
                "market_doc_review_packet_found_count": 10,
                "market_doc_review_packet_contract_valid_count": 10,
                "market_doc_review_refs_complete_count": 10,
                "dockcase_ref_count": 48,
                "dockcase_file_exists_count": 48,
                "dockcase_file_readable_count": 48,
                "dockcase_file_missing_count": 0,
                "dockcase_file_read_error_count": 0,
                "dockcase_keyword_evidence_ready_count": 10,
                "approval_record_template_blank_contract_valid_count": 10,
                "event_evidence_review_template_count": 10,
                "event_evidence_review_template_contract_valid_count": 10,
                "event_evidence_review_template_contract_invalid_count": 0,
                "event_evidence_review_template_blank_pending_count": 10,
                "reviewer_packet_complete_count": 10,
                "auto_approval_allowed_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_individual_review_source_samples_2026-06-19.json",
        {
            "summary": {
                "individual_review_source_sample_count": 10,
                "individual_structured_review_required_count": 4,
                "individual_policy_review_required_count": 6,
                "manual_policy_review_count": 4,
                "event_policy_review_count": 2,
                "structured_proxy_review_count": 4,
                "source_kind_counts": {
                    "event_text_policy_pilot": 2,
                    "local_structured_policy_pilot": 2,
                    "local_structured_text_policy_pilot": 2,
                    "manual_policy_pilot": 4,
                },
                "score_target_counts": {
                    "fundamental_score": 4,
                    "priced_in_discount": 1,
                    "reflexivity_multiplier": 1,
                    "risk_discount": 3,
                    "valuation_rerating": 1,
                },
                "source_report_exists_count": 10,
                "source_report_row_found_count": 10,
                "source_payload_matches_candidate_count": 10,
                "source_contract_valid_count": 10,
                "source_bridge_final_score_ready_count": 10,
                "evidence_refs_complete_count": 10,
                "approval_record_template_blank_contract_valid_count": 10,
                "text_sample_evidence_ready_count": 2,
                "event_source_sample_row_found_count": 2,
                "event_source_sample_reviewer_packet_complete_count": 2,
                "individual_review_template_count": 10,
                "individual_review_template_contract_valid_count": 10,
                "individual_review_template_contract_invalid_count": 0,
                "individual_review_template_blank_pending_count": 10,
                "reviewer_packet_complete_count": 10,
                "auto_approval_allowed_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_source_sample_coverage_2026-06-19.json",
        {
            "summary": {
                "approval_packet_count": 25,
                "source_sample_supported_packet_count": 25,
                "source_sample_found_count": 25,
                "source_sample_reviewer_packet_complete_count": 25,
                "source_sample_payload_matches_candidate_count": 25,
                "source_sample_review_template_contract_valid_count": 25,
                "approval_record_template_blank_contract_valid_count": 25,
                "approval_input_ready_count": 25,
                "approval_input_not_ready_count": 0,
                "supplemental_event_source_sample_complete_count": 2,
                "unsupported_risk_class_count": 0,
                "source_sample_route_counts": {
                    "bulk_review_source_sample": 7,
                    "event_approval_source_sample": 8,
                    "individual_review_source_sample": 10,
                },
                "risk_class_counts": {
                    "borderline_structured_text_review_candidate": 1,
                    "bulk_structured_review_candidate": 6,
                    "individual_event_evidence_review_required": 8,
                    "individual_policy_review_required": 6,
                    "individual_structured_review_required": 4,
                },
                "approved_runtime_write_count": 0,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_target_scope_readiness_2026-06-20.json",
        {
            "summary": {
                "approval_packet_count": 25,
                "final_score_target_ready_count": 25,
                "approval_missing_count": 25,
                "source_sample_reviewer_packet_complete_count": 25,
                "source_sample_payload_match_count": 25,
                "existing_target_scope_policy_count": 2,
                "existing_target_scope_policy_dp_ids": [
                    "L7.trade.gamma",
                    "L9.media.short_report",
                ],
                "supported_by_existing_target_scope_policy_count": 0,
                "explicit_target_scope_count": 0,
                "target_scope_ready_after_approval_count": 0,
                "target_scope_policy_required_count": 25,
                "per_stock_value_materialization_required_count": 19,
                "market_or_event_scope_policy_required_count": 6,
                "explicit_target_scope_policy_required_count": 0,
                "runtime_materialization_ready_count": 0,
                "approval_only_not_sufficient_count": 25,
                "safe_runtime_write_after_approval_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_materialization_plan_2026-06-20.json",
        {
            "summary": {
                "approval_packet_count": 25,
                "a_share_universe_count": 1641,
                "fundamental_packet_count": 19,
                "direct_structured_formula_packet_count": 7,
                "direct_structured_formula_plan_ready_count": 7,
                "direct_structured_formula_min_target_count": 868,
                "direct_structured_formula_max_target_count": 1639,
                "grain_join_policy_required_count": 1,
                "text_evidence_full_match_export_required_count": 3,
                "market_or_event_scope_policy_required_count": 14,
                "unsupported_materialization_policy_count": 0,
                "runtime_materialization_plan_ready_count": 7,
                "runtime_write_allowed_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_approval_materialization_batch_plan_2026-06-20.json",
        {
            "summary": {
                "direct_formula_plan_count": 7,
                "batch_plan_entry_count": 7,
                "batch_plan_contract_valid_count": 7,
                "batch_plan_contract_invalid_count": 0,
                "batch_plan_review_required_count": 7,
                "batch_plan_approved_count": 0,
                "planned_upsert_row_count": 9995,
                "rows_to_insert_count": 9995,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "upsert_ready_entry_count": 0,
                "blocked_entry_count": 7,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_approval_materialization_batch_codex_review_2026-06-20.json",
        {
            "summary": {
                "batch_plan_row_count": 7,
                "codex_review_approved_count": 7,
                "codex_review_rejected_count": 0,
                "approval_record_count": 7,
                "planned_upsert_row_count": 9995,
                "approved_planned_upsert_row_count": 9995,
                "rows_to_insert_count": 9995,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_approval_materialization_batch_approval_gate_2026-06-20.json",
        {
            "summary": {
                "batch_plan_row_count": 7,
                "batch_plan_contract_valid_count": 7,
                "approval_records_seen": 7,
                "orphan_approval_record_count": 0,
                "approval_required_count": 7,
                "approval_missing_count": 0,
                "approval_rejected_count": 0,
                "approved_controlled_formula_batch_plan_count": 7,
                "blank_approval_template_count": 7,
                "blank_approval_template_contract_valid_count": 7,
                "planned_upsert_row_count": 9995,
                "approved_planned_upsert_row_count": 9995,
                "runtime_write_allowed_count": 7,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir
        / "a_share_approval_materialization_batch_execution_preflight_2026-06-20.json",
        {
            "summary": {
                "execution_status": "dry_run_ready",
                "batch_plan_entry_count": 7,
                "approved_batch_plan_count": 7,
                "preflight_checked_count": 7,
                "preflight_ready_count": 7,
                "preflight_blocked_count": 0,
                "planned_upsert_row_count": 9995,
                "runtime_rows_would_write_count": 9995,
                "rows_to_insert_count": 9995,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "runtime_backup_required_count": 7,
                "runtime_backup_created_count": 0,
                "runtime_write_attempted_count": 0,
                "runtime_write_completed_count": 0,
                "post_write_verified_row_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_scope_approvals_2026-06-19.json",
        {
            "summary": {
                "target_scope_row_count": 2,
                "scope_approval_record_count": 2,
                "approved_runtime_target_scope_count": 2,
                "scope_policy_rejected_count": 0,
                "candidate_runtime_rows_would_write_count": 3282,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_write_preflight_2026-06-19.json",
        {
            "summary": {
                "approved_write_plan_entry_count": 2,
                "upsert_ready_entry_count": 0,
                "executed_entry_count": 2,
                "blocked_entry_count": 0,
                "missing_target_scope_count": 0,
                "runtime_rows_would_write_count": 0,
                "target_scope_candidate_count": 2,
                "target_scope_review_required_count": 0,
                "controlled_batch_plan_required_count": 0,
                "batch_plan_candidate_count": 2,
                "batch_plan_review_required_count": 0,
                "batch_plan_approved_count": 2,
                "runtime_backup_execution_required_count": 0,
                "runtime_execution_completed_count": 2,
                "runtime_execution_rows_written_count": 3282,
                "runtime_execution_post_write_verified_row_count": 3282,
                "batch_plan_planned_upsert_rows_count": 3282,
                "batch_plan_rows_to_insert_count": 3282,
                "batch_plan_rows_to_update_count": 0,
                "batch_plan_existing_rows_to_backup_count": 0,
                "candidate_runtime_rows_would_write_count": 3282,
                "runtime_write_attempted_count": 2,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_write_target_scope_2026-06-19.json",
        {
            "summary": {
                "approved_write_plan_entry_count": 2,
                "runtime_a_share_ts_code_count": 1641,
                "config_a_share_ts_code_count": 1641,
                "config_runtime_a_share_exact_match": True,
                "target_scope_candidate_count": 2,
                "target_scope_contract_valid_count": 2,
                "target_scope_contract_invalid_count": 0,
                "target_scope_review_required_count": 0,
                "target_scope_approved_count": 2,
                "controlled_batch_plan_required_count": 2,
                "candidate_runtime_rows_would_write_count": 3282,
                "upsert_ready_entry_count": 0,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_write_batch_plan_2026-06-19.json",
        {
            "summary": {
                "scope_approved_entry_count": 2,
                "batch_plan_entry_count": 2,
                "batch_plan_contract_valid_count": 2,
                "batch_plan_contract_invalid_count": 0,
                "batch_plan_review_required_count": 0,
                "batch_plan_approved_count": 2,
                "planned_upsert_row_count": 3282,
                "rows_to_insert_count": 3282,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_write_batch_approvals_2026-06-19.json",
        {
            "summary": {
                "batch_plan_row_count": 2,
                "batch_approval_record_count": 2,
                "approved_controlled_batch_plan_count": 2,
                "batch_policy_rejected_count": 0,
                "planned_upsert_row_count": 3282,
                "rows_to_insert_count": 3282,
                "rows_to_update_count": 0,
                "existing_rows_to_backup_count": 0,
                "runtime_write_attempted_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_runtime_write_execution_2026-06-19.json",
        {
            "summary": {
                "execution_status": "executed",
                "batch_plan_entry_count": 2,
                "approved_batch_plan_count": 2,
                "approved_controlled_batch_plan_count": 2,
                "execution_ready_count": 2,
                "execution_blocked_count": 0,
                "planned_upsert_row_count": 3282,
                "backup_required_count": 2,
                "runtime_backup_created_count": 1,
                "backup_completed_count": 2,
                "backup_failed_count": 0,
                "runtime_write_attempted_count": 2,
                "runtime_write_completed_count": 2,
                "runtime_write_failed_count": 0,
                "runtime_rows_written_count": 3282,
                "upserted_row_count": 3282,
                "rows_inserted_count": 3282,
                "rows_updated_count": 0,
                "existing_rows_backed_up_count": 0,
                "post_write_verified_count": 2,
                "post_write_verified_row_count": 3282,
                "post_write_verification_error_count": 0,
                "production_write_allowed_count": 0,
            }
        },
    )
    _write_json(
        audit_dir / "a_share_score_field_closure_2026-06-19.json",
        {
            "summary": {
                "configured_spec_total_dp_ids": 256,
                "runtime_trace_spec_total_dp_ids": 256,
                "spec_total_matches_runtime": True,
                "score_relevant_spec_dp_ids": 174,
                "closed_score_relevant_dp_ids": 119,
                "blocking_gap_dp_ids": 34,
                "candidate_ready_blocking_gap_dp_ids": 34,
                "candidate_not_ready_blocking_gap_dp_ids": 0,
                "safe_to_upsert_without_review_count": 0,
                "direct_structured_tushare_remaining": 0,
            }
        },
    )

    report = audit_goal_coverage.build_report(audit_dir)

    assert report["completion_status"] == "not_complete"
    assert report["summary"]["requirement_count"] == 10
    assert report["summary"]["covered_count"] == 10
    assert report["summary"]["missing_evidence_count"] == 0
    assert (
        "DOCKCASE CSV semantic review is signature-stratified and evidence-backed, "
        "with a ranked backlog, accumulated deep-sampled backlog batches, and partial full-row scan progress, but not exhaustive across every CSV row/file"
        in report["summary"]["completion_blockers"]
    )
    assert "repo binary/large files are fully head/tail fingerprinted, but type-aware semantic classification remains incomplete" in report["summary"]["completion_blockers"]
    a_share_blocker = next(
        blocker
        for blocker in report["summary"]["completion_blockers"]
        if blocker.startswith("A-share score field trace still reports")
    )
    assert "34 actionable participating gaps" in a_share_blocker
    assert "34 candidate-ready" in a_share_blocker
    assert "157 spec score-conversion path-ready" in a_share_blocker
    assert "17 spec score-conversion unresolved" in a_share_blocker
    assert "14 spec score-conversion formula/normalizer gaps" in a_share_blocker
    assert "3 spec score-conversion missing-current-input gaps" in a_share_blocker
    assert "17 spec score-conversion review-decision-backed not-ready fields" in a_share_blocker
    assert "6 spec score-conversion formula-policy review-required fields" in a_share_blocker
    assert "8 spec score-conversion governance-suppression verified fields" in a_share_blocker
    assert "3 spec score-conversion option-universe/N/A verified fields" in a_share_blocker
    assert "0 spec score-conversion unclassified gaps" in a_share_blocker
    assert "32 l0 source-readiness blocking gaps" in a_share_blocker
    assert "28 l0 source-readiness P2 rows" in a_share_blocker
    assert "4 l0 source-readiness P3 rows" in a_share_blocker
    assert "12 l0 source-readiness event/news routes" in a_share_blocker
    assert "16 l0 source-readiness local closed-loop routes" in a_share_blocker
    assert "4 l0 source-readiness manual-design routes" in a_share_blocker
    assert "0 l0 source-readiness direct structured Tushare remaining" in a_share_blocker
    assert "17 l0 source-readiness dependency runtime rows" in a_share_blocker
    assert "0 l0 source-readiness missing runtime rows" in a_share_blocker
    assert "14956 short-report evidence HTML files scanned" in a_share_blocker
    assert "0 short-report evidence parse errors" in a_share_blocker
    assert "4 short-report evidence strict documents" in a_share_blocker
    assert "0 short-report evidence direct A-share documents" in a_share_blocker
    assert "4 short-report evidence foreign/market-only documents" in a_share_blocker
    assert "0 short-report evidence direct A-share ts_codes" in a_share_blocker
    assert "True short-report candidate evidence ready" in a_share_blocker
    assert "10/12 event-text Known drafts" in a_share_blocker
    assert "10 event-text drafts bridge-ready" in a_share_blocker
    assert "2 event-text unknown source-option rows" in a_share_blocker
    assert "2 event-text unknown classification inputs ready" in a_share_blocker
    assert "2 event-text unknown body texts available" in a_share_blocker
    assert "0 event-text unknown target-event evidence present" in a_share_blocker
    assert "0 event-text unknown direct A-share transmission present" in a_share_blocker
    assert "2 event-text unknown broad-market-only transmission rows" in a_share_blocker
    assert "0 event-text unknown classifier-ready review candidates" in a_share_blocker
    assert "2 event-text target-event evidence required" in a_share_blocker
    assert "0 event-text direct A-share transmission required" in a_share_blocker
    assert "0 event-text unknown auto Known candidates" in a_share_blocker
    assert "0 event-text unknown source-option production writes" in a_share_blocker
    assert "6/10 local-structured Known drafts" in a_share_blocker
    assert "6 local-structured drafts bridge-ready" in a_share_blocker
    assert "4 local-structured unknown source-option rows" in a_share_blocker
    assert "4 local-structured unknown runtime dependencies ready" in a_share_blocker
    assert "0 local-structured direct source-ready rows" in a_share_blocker
    assert "4 local-structured overlay/source hints" in a_share_blocker
    assert "4 local-structured new mappings required" in a_share_blocker
    assert "0 local-structured reviewed policies required" in a_share_blocker
    assert "0 local-structured partial Known unlock candidates" in a_share_blocker
    assert "0 local-structured auto Known candidates" in a_share_blocker
    assert "0 local-structured unknown source-option production writes" in a_share_blocker
    assert "4 local-structured source-candidate rows" in a_share_blocker
    assert "4 local-structured source-candidate runtime dependencies ready" in a_share_blocker
    assert "0 local-structured source-candidate direct Known-ready rows" in a_share_blocker
    assert "2 local-structured source-candidate review/source rows" in a_share_blocker
    assert "1 local-structured source-candidate review matches" in a_share_blocker
    assert "4 local-structured source-candidate supporting matches" in a_share_blocker
    assert "1 local-structured source-candidate empty matches" in a_share_blocker
    assert "2 local-structured source-candidate no-direct-source rows" in a_share_blocker
    assert "407 local-structured source-candidate false positives excluded" in a_share_blocker
    assert "0 local-structured source-candidate production writes" in a_share_blocker
    assert "4 local-structured source-review packets" in a_share_blocker
    assert "1 local-structured source-review lease/rent review-ready packets" in a_share_blocker
    assert "1 local-structured source-review quantity-needed ASP packets" in a_share_blocker
    assert "2 local-structured source-review external-source-required packets" in a_share_blocker
    assert "0 local-structured source-review direct Known-ready packets" in a_share_blocker
    assert "0 local-structured source-review formula-ready packets" in a_share_blocker
    assert "2 local-structured source-review candidate-column packets" in a_share_blocker
    assert "4 local-structured source-review packet contracts valid" in a_share_blocker
    assert "0 local-structured source-review packet contracts invalid" in a_share_blocker
    assert "0 local-structured source-review production writes" in a_share_blocker
    assert "3/3 local-structured-text Known drafts" in a_share_blocker
    assert "3 local-structured-text drafts bridge-ready" in a_share_blocker
    assert "0 local-structured-text unknown source-option rows" in a_share_blocker
    assert "0 local-structured-text unknown runtime dependencies ready" in a_share_blocker
    assert "0 local-structured-text QA recent dependencies ready" in a_share_blocker
    assert "0 local-structured-text direct text-classification-ready rows" in a_share_blocker
    assert "0 local-structured-text overlay/source hints" in a_share_blocker
    assert "0 local-structured-text text classifications required" in a_share_blocker
    assert "0 local-structured-text auto Known candidates" in a_share_blocker
    assert "0 local-structured-text unknown source-option production writes" in a_share_blocker
    assert "1 single-dependency unknown source-option rows" in a_share_blocker
    assert "1 single-dependency unknown runtime dependencies ready" in a_share_blocker
    assert "0 single-dependency direct replacement-cycle source-ready rows" in a_share_blocker
    assert "1 single-dependency overlay/source hints" in a_share_blocker
    assert "1 single-dependency lifecycle sources required" in a_share_blocker
    assert "1 single-dependency reviewed policies required" in a_share_blocker
    assert "0 single-dependency auto Known candidates" in a_share_blocker
    assert "0 single-dependency unknown source-option production writes" in a_share_blocker
    assert "0 manual-policy unknown source-option rows" in a_share_blocker
    assert "0 manual-policy unknown dependency packs ready" in a_share_blocker
    assert "0 manual-policy direct reviewed-assumption-ready rows" in a_share_blocker
    assert "0 manual-policy required assumptions" in a_share_blocker
    assert "0 manual-policy assumption reviews required" in a_share_blocker
    assert "0 manual-policy reviewed policies required" in a_share_blocker
    assert "0 manual-policy auto Known candidates" in a_share_blocker
    assert "0 manual-policy unknown source-option production writes" in a_share_blocker
    assert "12 event-text market-doc rows checked" in a_share_blocker
    assert "14956 event-text market-doc HTML files scanned" in a_share_blocker
    assert "0 event-text market-doc read errors" in a_share_blocker
    assert "12 event-text market-doc target-evidence rows" in a_share_blocker
    assert "12 event-text market-doc direct-transmission rows" in a_share_blocker
    assert "12 event-text market-doc target+direct rows" in a_share_blocker
    assert "11 event-text market-doc same-sentence candidates" in a_share_blocker
    assert "0 event-text market-doc target evidence still required" in a_share_blocker
    assert "1 event-text market-doc direct links still required" in a_share_blocker
    assert "11 event-text market-doc review candidates" in a_share_blocker
    assert "0 event-text market-doc auto Known candidates" in a_share_blocker
    assert "0 event-text market-doc production writes" in a_share_blocker
    assert "12 event-text market-doc review packets" in a_share_blocker
    assert "11 event-text market-doc review-ready packets" in a_share_blocker
    assert "0 event-text market-doc packet target evidence required" in a_share_blocker
    assert "1 event-text market-doc packet direct links required" in a_share_blocker
    assert "53 event-text market-doc packet candidate examples" in a_share_blocker
    assert "12 event-text market-doc packet contracts valid" in a_share_blocker
    assert "0 event-text market-doc packet contracts invalid" in a_share_blocker
    assert "0 event-text market-doc packet auto Known candidates" in a_share_blocker
    assert "0 event-text market-doc packet production writes" in a_share_blocker
    assert "2 unknown event strict-source rows" in a_share_blocker
    assert "14956 unknown event strict-source HTML files scanned" in a_share_blocker
    assert "0 unknown event strict-source read errors" in a_share_blocker
    assert "11 unknown event strict-source candidates" in a_share_blocker
    assert "8 unknown event strict-source review candidates" in a_share_blocker
    assert "3 unknown event strict-source rejected candidates" in a_share_blocker
    assert "2 unknown event strict-source rows with review candidates" in a_share_blocker
    assert "0 unknown event strict-source rows without source candidates" in a_share_blocker
    assert "0 unknown event strict-source classifier-ready rows" in a_share_blocker
    assert "0 unknown event strict-source Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown event strict-source approval-ready rows" in a_share_blocker
    assert "2 unknown event strict-source contracts valid" in a_share_blocker
    assert "0 unknown event strict-source contracts invalid" in a_share_blocker
    assert "0 unknown event strict-source production writes" in a_share_blocker
    assert "8 unknown event strict-review packets" in a_share_blocker
    assert "2 unknown event strict-review rows" in a_share_blocker
    assert "2 unknown event strict-review low-confidence source packets" in a_share_blocker
    assert "6 unknown event strict-review secondary-newswire packets" in a_share_blocker
    assert "2 unknown event strict-review primary-source confirmations required" in a_share_blocker
    assert "0 unknown event strict-review manual reviews required" in a_share_blocker
    assert "6 unknown event strict-review deterministic rejections" in a_share_blocker
    assert "0 unknown event strict-review classifier-ready packets" in a_share_blocker
    assert "0 unknown event strict-review Known-draft-sufficient packets" in a_share_blocker
    assert "0 unknown event strict-review approval-ready packets" in a_share_blocker
    assert "8 unknown event strict-review contracts valid" in a_share_blocker
    assert "0 unknown event strict-review contracts invalid" in a_share_blocker
    assert "0 unknown event strict-review production writes" in a_share_blocker
    assert "2 unknown event primary-confirmation packets" in a_share_blocker
    assert "14956 unknown event primary-confirmation HTML files scanned" in a_share_blocker
    assert "0 unknown event primary-confirmation read errors" in a_share_blocker
    assert "12 unknown event primary-confirmation local candidates" in a_share_blocker
    assert "0 unknown event primary-confirmation high-quality candidates" in a_share_blocker
    assert "12 unknown event primary-confirmation supporting-only candidates" in a_share_blocker
    assert "0 unknown event primary-confirmation rows with local confirmation" in a_share_blocker
    assert "2 unknown event primary-confirmation rows with supporting context only" in a_share_blocker
    assert "0 unknown event primary-confirmation rows without local confirmation" in a_share_blocker
    assert "0 unknown event primary-confirmation classifier-ready rows" in a_share_blocker
    assert "0 unknown event primary-confirmation Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown event primary-confirmation approval-ready rows" in a_share_blocker
    assert "2 unknown event primary-confirmation contracts valid" in a_share_blocker
    assert "0 unknown event primary-confirmation contracts invalid" in a_share_blocker
    assert "0 unknown event primary-confirmation production writes" in a_share_blocker
    assert "2 unknown event external-confirmation packets" in a_share_blocker
    assert "6 unknown event external-confirmation source cards" in a_share_blocker
    assert "2 unknown event external-confirmation candidates" in a_share_blocker
    assert "4 unknown event external-confirmation supporting-context cards" in a_share_blocker
    assert (
        "2 unknown event external-confirmation rows with confirmation candidates"
        in a_share_blocker
    )
    assert "0 unknown event external-confirmation rows supporting-only" in a_share_blocker
    assert "0 unknown event external-confirmation classifier-ready rows" in a_share_blocker
    assert (
        "0 unknown event external-confirmation Known-draft-sufficient rows"
        in a_share_blocker
    )
    assert "0 unknown event external-confirmation approval-ready rows" in a_share_blocker
    assert "2 unknown event external-confirmation contracts valid" in a_share_blocker
    assert "0 unknown event external-confirmation contracts invalid" in a_share_blocker
    assert "0 unknown event external-confirmation production writes" in a_share_blocker
    assert "27 review-manifest concrete-ready" in a_share_blocker
    assert "7 review-manifest Unknown-gated" in a_share_blocker
    assert "2 deterministic approval records" in a_share_blocker
    assert "2 deterministic approved runtime writes" in a_share_blocker
    assert "25 approval-gate missing approvals" in a_share_blocker
    assert "25 completion human approvals" in a_share_blocker
    assert "2 completion runtime write-plan-ready packets" in a_share_blocker
    assert "7 completion Unknown resolutions" in a_share_blocker
    assert "0 approval cross-report consistency errors" in a_share_blocker
    assert "0 completion structured-text extractions" in a_share_blocker
    assert "7 unknown closure rows" in a_share_blocker
    assert "7 unknown closure routes assigned" in a_share_blocker
    assert "0 unknown closure routes missing" in a_share_blocker
    assert "2 unknown closure event-text classifications" in a_share_blocker
    assert "4 unknown closure local structured mappings" in a_share_blocker
    assert "0 unknown closure structured-text extractions" in a_share_blocker
    assert "1 unknown closure single-dependency policies" in a_share_blocker
    assert "0 unknown closure manual assumption reviews" in a_share_blocker
    assert "0 unknown closure auto Known-ready rows" in a_share_blocker
    assert "0 unknown closure approval-ready rows" in a_share_blocker
    assert "7 unknown closure contracts valid" in a_share_blocker
    assert "0 unknown closure contracts invalid" in a_share_blocker
    assert "0 unknown closure production writes" in a_share_blocker
    assert "3 unknown external business metric acquisition tasks" in a_share_blocker
    assert "3 unknown external business metric runtime dependency-ready tasks" in a_share_blocker
    assert "7 unknown external business metric overlay hints" in a_share_blocker
    assert "12 unknown external business metric groups" in a_share_blocker
    assert "0 unknown external business metric groups ready" in a_share_blocker
    assert "3 unknown external business metric rows with supporting runtime context" in a_share_blocker
    assert "0 unknown external business metric rows with direct sources" in a_share_blocker
    assert "3 unknown external business metric rows requiring external/text source" in a_share_blocker
    assert "238 unknown external business metric false positives" in a_share_blocker
    assert "0 unknown external business metric-ready rows" in a_share_blocker
    assert "0 unknown external business metric Known-draft-ready rows" in a_share_blocker
    assert "3 unknown external business metric contracts valid" in a_share_blocker
    assert "0 unknown external business metric contracts invalid" in a_share_blocker
    assert "0 unknown external business metric production writes" in a_share_blocker
    assert "3 unknown external business metric market-doc tasks" in a_share_blocker
    assert "14956 unknown external business metric market-doc HTML files scanned" in a_share_blocker
    assert "0 unknown external business metric market-doc read errors" in a_share_blocker
    assert "3 unknown external business metric market-doc rows with review candidates" in a_share_blocker
    assert "178 unknown external business metric market-doc candidate documents" in a_share_blocker
    assert "99 unknown external business metric market-doc review candidates" in a_share_blocker
    assert "49 unknown external business metric market-doc numeric review candidates" in a_share_blocker
    assert "50 unknown external business metric market-doc textual review candidates" in a_share_blocker
    assert "82 unknown external business metric market-doc weak candidates" in a_share_blocker
    assert "72 unknown external business metric market-doc rejected candidates" in a_share_blocker
    assert "0 unknown external business metric market-doc Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown external business metric market-doc metric-ready rows" in a_share_blocker
    assert "3 unknown external business metric market-doc contracts valid" in a_share_blocker
    assert "0 unknown external business metric market-doc contracts invalid" in a_share_blocker
    assert "0 unknown external business metric market-doc production writes" in a_share_blocker
    assert "99 unknown external business metric review packets" in a_share_blocker
    assert "99 unknown external business metric expected review candidates" in a_share_blocker
    assert "3 unknown external business metric rows with review packets" in a_share_blocker
    assert "49 unknown external business metric numeric review packets" in a_share_blocker
    assert "50 unknown external business metric textual review packets" in a_share_blocker
    assert "99 unknown external business metric packets with scope candidates" in a_share_blocker
    assert "70 unknown external business metric packets with denominator candidates" in a_share_blocker
    assert "36 unknown external business metric packets with period candidates" in a_share_blocker
    assert "49 unknown external business metric packets with unit candidates" in a_share_blocker
    assert "0 unknown external business metric review-packet metric-ready rows" in a_share_blocker
    assert "0 unknown external business metric review-packet Known-draft-sufficient rows" in a_share_blocker
    assert "99 unknown external business metric review-packet contracts valid" in a_share_blocker
    assert "0 unknown external business metric review-packet contracts invalid" in a_share_blocker
    assert "0 unknown external business metric review-packet production writes" in a_share_blocker
    assert "99 unknown external business metric readiness packets" in a_share_blocker
    assert "18 unknown external business metric P0 formula-policy-only candidates" in a_share_blocker
    assert "52 unknown external business metric P1 period/unit-required candidates" in a_share_blocker
    assert "29 unknown external business metric P2 denominator-required candidates" in a_share_blocker
    assert "29 unknown external business metric packets missing denominator" in a_share_blocker
    assert "63 unknown external business metric packets missing period" in a_share_blocker
    assert "50 unknown external business metric packets missing unit" in a_share_blocker
    assert "99 unknown external business metric packets missing bounds" in a_share_blocker
    assert "99 unknown external business metric packets missing formula policy" in a_share_blocker
    assert "0 unknown external business metric readiness metric-ready packets" in a_share_blocker
    assert "0 unknown external business metric readiness Known-draft-sufficient packets" in a_share_blocker
    assert "0 unknown external business metric readiness production writes" in a_share_blocker
    assert "18 unknown external business metric P0 source packets for policy draft" in a_share_blocker
    assert "18 unknown external business metric policy draft packets" in a_share_blocker
    assert "18 unknown external business metric formula-policy reviews required" in a_share_blocker
    assert "18 unknown external business metric value JSON templates" in a_share_blocker
    assert "18 unknown external business metric policy review templates" in a_share_blocker
    assert "18 unknown external business metric policy review template contracts valid" in a_share_blocker
    assert "0 unknown external business metric policy review template contracts invalid" in a_share_blocker
    assert "18 unknown external business metric policy review templates blank-pending" in a_share_blocker
    assert "0 unknown external business metric policy review template inputs ready" in a_share_blocker
    assert "0 unknown external business metric policy-draft metric-ready rows" in a_share_blocker
    assert "0 unknown external business metric policy-draft Known-draft-sufficient rows" in a_share_blocker
    assert "18 unknown external business metric policy-draft contracts valid" in a_share_blocker
    assert "0 unknown external business metric policy-draft contracts invalid" in a_share_blocker
    assert "0 unknown external business metric policy-draft production writes" in a_share_blocker
    assert "6 unknown penetration value-priority packets" in a_share_blocker
    assert "8 unknown penetration value-priority candidate options" in a_share_blocker
    assert "8 unknown penetration value-priority bridge-ready options" in a_share_blocker
    assert "1 unknown penetration value-priority P1 reviews" in a_share_blocker
    assert "1 unknown penetration value-priority P2 reviews" in a_share_blocker
    assert "2 unknown penetration value-priority P3 forecast reviews" in a_share_blocker
    assert "2 unknown penetration value-priority P3 low-confidence reviews" in a_share_blocker
    assert "0 unknown penetration value-priority selected value JSONs" in a_share_blocker
    assert "0 unknown penetration value-priority Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown penetration value-priority approval-ready rows" in a_share_blocker
    assert "0 unknown penetration value-priority production writes" in a_share_blocker
    assert "1 unknown penetration P1 source-confirmation candidates" in a_share_blocker
    assert "1 unknown penetration P1 source files found" in a_share_blocker
    assert "1 unknown penetration P1 raw-value tokens confirmed" in a_share_blocker
    assert "1 unknown penetration P1 source scopes confirmed" in a_share_blocker
    assert "0 unknown penetration P1 selected value JSONs" in a_share_blocker
    assert "0 unknown penetration P1 Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown penetration P1 approval-ready rows" in a_share_blocker
    assert "0 unknown penetration P1 production writes" in a_share_blocker
    assert "1 unknown penetration value-policy draft rows" in a_share_blocker
    assert "1 unknown penetration value-policy source scopes confirmed" in a_share_blocker
    assert "1 unknown penetration value-policy proposed value JSONs" in a_share_blocker
    assert "1 unknown penetration value-policy draft contracts valid" in a_share_blocker
    assert "0 unknown penetration value-policy draft contracts invalid" in a_share_blocker
    assert "1 unknown penetration value-policy final-score bridges ready" in a_share_blocker
    assert "0 unknown penetration value-policy selected value JSONs" in a_share_blocker
    assert "0 unknown penetration value-policy Known-draft-sufficient rows" in a_share_blocker
    assert "0 unknown penetration value-policy approval-ready rows" in a_share_blocker
    assert "0 unknown penetration value-policy production writes" in a_share_blocker
    assert "27 approval review packets" in a_share_blocker
    assert "25 approval packet missing approvals" in a_share_blocker
    assert "2 approval packet approved runtime writes" in a_share_blocker
    assert "2 approval packet write-plan entries" in a_share_blocker
    assert "25 approval-packet risk-review packets" in a_share_blocker
    assert "6 approval-packet risk-review bulk structured candidates" in a_share_blocker
    assert "1 approval-packet risk-review borderline structured-text candidates" in a_share_blocker
    assert "18 approval-packet risk-review individual-review packets" in a_share_blocker
    assert "8 approval-packet risk-review event evidence packets" in a_share_blocker
    assert "4 approval-packet risk-review structured proxy packets" in a_share_blocker
    assert "6 approval-packet risk-review policy packets" in a_share_blocker
    assert "0 approval-packet risk-review contract-fix blockers" in a_share_blocker
    assert "0 approval-packet risk-review auto approvals" in a_share_blocker
    assert "0 approval-packet risk-review production writes" in a_share_blocker
    assert "7 bulk-review approval candidates" in a_share_blocker
    assert "6 bulk-review approval strict candidates" in a_share_blocker
    assert "1 bulk-review approval borderline candidates" in a_share_blocker
    assert "7 bulk-review approval drafts" in a_share_blocker
    assert "7 bulk-review approval draft contracts valid" in a_share_blocker
    assert "0 bulk-review approval draft contracts invalid" in a_share_blocker
    assert "0 bulk-review approval auto approvals" in a_share_blocker
    assert "0 bulk-review approval production writes" in a_share_blocker
    assert "10 event-approval source-sample event-text packets" in a_share_blocker
    assert "8 event-approval individual event-evidence reviews required" in a_share_blocker
    assert "10 event-approval source payload matches" in a_share_blocker
    assert "10 event-approval market-doc review packets" in a_share_blocker
    assert "10 event-approval market-doc review refs complete" in a_share_blocker
    assert "48/48 event-approval DOCKCASE docs readable" in a_share_blocker
    assert "10 event-approval keyword-evidence-ready rows" in a_share_blocker
    assert "10/10 event-approval event-evidence review templates valid" in a_share_blocker
    assert "10 event-approval templates blank/pending" in a_share_blocker
    assert "10 event-approval complete reviewer packets" in a_share_blocker
    assert "0 event-approval source-sample production writes" in a_share_blocker
    assert "10 individual-review source-sample packets" in a_share_blocker
    assert "4 individual-review structured proxy reviews" in a_share_blocker
    assert "6 individual-review policy reviews" in a_share_blocker
    assert "4 individual-review manual-policy packets" in a_share_blocker
    assert "2 individual-review event policy packets" in a_share_blocker
    assert "4 individual-review structured proxy packets" in a_share_blocker
    assert "10 individual-review source payload matches" in a_share_blocker
    assert "10 individual-review complete evidence refs" in a_share_blocker
    assert "2 individual-review text sample-evidence ready rows" in a_share_blocker
    assert "2 individual-review event source-sample packets complete" in a_share_blocker
    assert "10/10 individual-review templates valid" in a_share_blocker
    assert "10 individual-review templates blank/pending" in a_share_blocker
    assert "10 individual-review complete reviewer packets" in a_share_blocker
    assert "0 individual-review source-sample production writes" in a_share_blocker
    assert "25 approval source-sample coverage packets" in a_share_blocker
    assert "25 approval source-sample supported routes" in a_share_blocker
    assert "25 approval source-sample source samples found" in a_share_blocker
    assert "25 approval source-sample reviewer packets complete" in a_share_blocker
    assert "25 approval source-sample payload matches" in a_share_blocker
    assert "25 approval source-sample review templates valid" in a_share_blocker
    assert "25 approval source-sample blank approval templates valid" in a_share_blocker
    assert "25 approval source-sample approval inputs ready" in a_share_blocker
    assert "0 approval source-sample approval inputs not ready" in a_share_blocker
    assert "0 approval source-sample unsupported risk classes" in a_share_blocker
    assert "0 approval source-sample production writes" in a_share_blocker
    assert "25 approval target-scope readiness packets" in a_share_blocker
    assert "25 approval target-scope final-score-ready packets" in a_share_blocker
    assert "25 approval target-scope source-sample packets complete" in a_share_blocker
    assert "2 approval target-scope existing runtime policies" in a_share_blocker
    assert "0 approval target-scope packets supported by existing policies" in a_share_blocker
    assert "0 approval target-scope explicit target scopes" in a_share_blocker
    assert "0 approval target-scope packets ready after approval" in a_share_blocker
    assert "25 approval target-scope policies required" in a_share_blocker
    assert "19 approval target-scope per-stock materializations required" in a_share_blocker
    assert "6 approval target-scope market/event policies required" in a_share_blocker
    assert "0 approval target-scope runtime materializations ready" in a_share_blocker
    assert "25 approval-only not sufficient packets" in a_share_blocker
    assert "0 approval target-scope safe runtime writes after approval" in a_share_blocker
    assert "0 approval target-scope production writes" in a_share_blocker
    assert "25 approval materialization packets" in a_share_blocker
    assert "1641 approval materialization A-share universe tickers" in a_share_blocker
    assert "19 approval materialization fundamental packets" in a_share_blocker
    assert "7 approval materialization direct structured formula packets" in a_share_blocker
    assert "7 approval materialization direct formula plans ready" in a_share_blocker
    assert "868 approval materialization minimum direct-formula target tickers" in a_share_blocker
    assert "1639 approval materialization maximum direct-formula target tickers" in a_share_blocker
    assert "1 approval materialization grain-join policies required" in a_share_blocker
    assert "3 approval materialization text full-match exports required" in a_share_blocker
    assert "14 approval materialization market/event policies required" in a_share_blocker
    assert "0 approval materialization unsupported policies" in a_share_blocker
    assert "7 approval materialization runtime plans ready" in a_share_blocker
    assert "0 approval materialization runtime writes" in a_share_blocker
    assert "0 approval materialization production writes" in a_share_blocker
    assert "7 approval materialization batch direct formula plans" in a_share_blocker
    assert "7 approval materialization batch-plan entries" in a_share_blocker
    assert "7 approval materialization batch-plan contracts valid" in a_share_blocker
    assert "0 approval materialization batch-plan contracts invalid" in a_share_blocker
    assert "7 approval materialization batch plans review required" in a_share_blocker
    assert "0 approval materialization batch plans approved" in a_share_blocker
    assert "9995 approval materialization planned formula UPSERT rows" in a_share_blocker
    assert "9995 approval materialization formula rows to insert" in a_share_blocker
    assert "0 approval materialization formula rows to update" in a_share_blocker
    assert "0 approval materialization formula rows requiring backup" in a_share_blocker
    assert "0 approval materialization upsert-ready entries" in a_share_blocker
    assert "7 approval materialization blocked entries" in a_share_blocker
    assert "0 approval materialization runtime write attempts" in a_share_blocker
    assert "0 approval materialization batch production writes" in a_share_blocker
    assert (
        "7 approval materialization Codex review batch-plan rows"
        in a_share_blocker
    )
    assert "7 approval materialization Codex review approvals" in a_share_blocker
    assert "0 approval materialization Codex review rejections" in a_share_blocker
    assert "7 approval materialization Codex approval records" in a_share_blocker
    assert "9995 approval materialization Codex planned UPSERT rows" in a_share_blocker
    assert (
        "9995 approval materialization Codex approved planned UPSERT rows"
        in a_share_blocker
    )
    assert "9995 approval materialization Codex rows to insert" in a_share_blocker
    assert "0 approval materialization Codex rows to update" in a_share_blocker
    assert (
        "0 approval materialization Codex rows requiring backup"
        in a_share_blocker
    )
    assert "0 approval materialization Codex runtime write attempts" in a_share_blocker
    assert "0 approval materialization Codex production writes" in a_share_blocker
    assert "7 approval materialization gate batch-plan rows" in a_share_blocker
    assert (
        "7 approval materialization gate contract-valid batch plans"
        in a_share_blocker
    )
    assert "7 approval materialization gate approval records seen" in a_share_blocker
    assert "7 approval materialization gate approvals required" in a_share_blocker
    assert "0 approval materialization gate approvals missing" in a_share_blocker
    assert "0 approval materialization gate approvals rejected" in a_share_blocker
    assert (
        "7 approval materialization gate formula batch plans approved"
        in a_share_blocker
    )
    assert "7 approval materialization gate blank approval templates" in a_share_blocker
    assert (
        "7 approval materialization gate blank templates contract valid"
        in a_share_blocker
    )
    assert "9995 approval materialization gate planned UPSERT rows" in a_share_blocker
    assert (
        "9995 approval materialization gate approved planned UPSERT rows"
        in a_share_blocker
    )
    assert "7 approval materialization gate runtime writes allowed" in a_share_blocker
    assert "0 approval materialization gate production writes" in a_share_blocker
    assert (
        "7 approval materialization execution-preflight batch-plan entries"
        in a_share_blocker
    )
    assert (
        "7 approval materialization execution-preflight approved batch plans"
        in a_share_blocker
    )
    assert (
        "7 approval materialization execution-preflight entries checked"
        in a_share_blocker
    )
    assert (
        "7 approval materialization execution-preflight entries ready"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight entries blocked"
        in a_share_blocker
    )
    assert (
        "9995 approval materialization execution-preflight planned UPSERT rows"
        in a_share_blocker
    )
    assert (
        "9995 approval materialization execution-preflight rows would write"
        in a_share_blocker
    )
    assert (
        "9995 approval materialization execution-preflight rows to insert"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight rows to update"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight rows requiring backup"
        in a_share_blocker
    )
    assert (
        "7 approval materialization execution-preflight backups required"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight backups created"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight runtime write attempts"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight runtime write completions"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight post-write verified rows"
        in a_share_blocker
    )
    assert (
        "0 approval materialization execution-preflight production writes"
        in a_share_blocker
    )
    assert "2 runtime scope approval rows checked" in a_share_blocker
    assert "2 runtime scope approval records" in a_share_blocker
    assert "2 runtime scopes approved" in a_share_blocker
    assert "0 runtime scope approvals rejected" in a_share_blocker
    assert (
        "3282 runtime scope approval candidate rows would write if batch-approved"
        in a_share_blocker
    )
    assert "0 runtime scope approval write attempts" in a_share_blocker
    assert "0 runtime scope approval production writes" in a_share_blocker
    assert "2 runtime target-scope approved write-plan entries" in a_share_blocker
    assert "1641 runtime target-scope A-share ts_codes" in a_share_blocker
    assert "1641 runtime target-scope configured A-share ts_codes" in a_share_blocker
    assert "True runtime target-scope exact config/runtime match" in a_share_blocker
    assert "2 runtime target-scope candidates" in a_share_blocker
    assert "2 runtime target-scope contracts valid" in a_share_blocker
    assert "0 runtime target-scope contracts invalid" in a_share_blocker
    assert "0 runtime target-scope reviews required" in a_share_blocker
    assert "2 runtime target scopes approved" in a_share_blocker
    assert "2 runtime target-scope controlled batch plans required" in a_share_blocker
    assert (
        "3282 runtime target-scope candidate rows would write if approved"
        in a_share_blocker
    )
    assert "0 runtime target-scope upsert-ready entries" in a_share_blocker
    assert "0 runtime target-scope write attempts" in a_share_blocker
    assert "0 runtime target-scope production writes" in a_share_blocker
    assert "2 runtime batch-plan entries" in a_share_blocker
    assert "2 runtime batch-plan contracts valid" in a_share_blocker
    assert "0 runtime batch-plan contracts invalid" in a_share_blocker
    assert "0 runtime batch-plan reviews required" in a_share_blocker
    assert "2 runtime batch plans approved" in a_share_blocker
    assert "3282 runtime batch-plan UPSERT rows planned" in a_share_blocker
    assert "3282 runtime batch-plan rows to insert" in a_share_blocker
    assert "0 runtime batch-plan rows to update" in a_share_blocker
    assert "0 runtime batch-plan existing rows needing backup" in a_share_blocker
    assert "0 runtime batch-plan write attempts" in a_share_blocker
    assert "0 runtime batch-plan production writes" in a_share_blocker
    assert "2 runtime batch-approval rows checked" in a_share_blocker
    assert "2 runtime batch approval records" in a_share_blocker
    assert "2 runtime controlled batch plans approved" in a_share_blocker
    assert "0 runtime batch policies rejected" in a_share_blocker
    assert "3282 runtime batch-approval UPSERT rows covered" in a_share_blocker
    assert "3282 runtime batch-approval rows to insert" in a_share_blocker
    assert "0 runtime batch-approval rows to update" in a_share_blocker
    assert "0 runtime batch-approval existing rows needing backup" in a_share_blocker
    assert "0 runtime batch-approval write attempts" in a_share_blocker
    assert "0 runtime batch-approval production writes" in a_share_blocker
    assert "2 runtime execution approved batch plans" in a_share_blocker
    assert "2 runtime execution-ready plans" in a_share_blocker
    assert "0 runtime execution blocked plans" in a_share_blocker
    assert "2 runtime execution backups completed" in a_share_blocker
    assert "0 runtime execution backup failures" in a_share_blocker
    assert "2 runtime execution write attempts" in a_share_blocker
    assert "2 runtime execution write completions" in a_share_blocker
    assert "0 runtime execution write failures" in a_share_blocker
    assert "3282 runtime execution rows written" in a_share_blocker
    assert "3282 runtime execution rows inserted" in a_share_blocker
    assert "0 runtime execution rows updated" in a_share_blocker
    assert "3282 runtime execution rows post-write verified" in a_share_blocker
    assert "0 runtime execution verification errors" in a_share_blocker
    assert "0 runtime execution production writes" in a_share_blocker
    assert "2 runtime preflight approved write-plan entries" in a_share_blocker
    assert "0 runtime preflight upsert-ready entries" in a_share_blocker
    assert "2 runtime preflight executed entries" in a_share_blocker
    assert "0 runtime preflight blocked entries" in a_share_blocker
    assert "0 runtime preflight missing target scopes" in a_share_blocker
    assert "3282 runtime preflight candidate rows would write if approved" in a_share_blocker
    assert "0 runtime preflight controlled batch plans required" in a_share_blocker
    assert "2 runtime preflight batch-plan candidates" in a_share_blocker
    assert "0 runtime preflight batch-plan reviews required" in a_share_blocker
    assert "2 runtime preflight batch plans approved" in a_share_blocker
    assert "0 runtime preflight backup/execution gates required" in a_share_blocker
    assert "2 runtime preflight executions completed" in a_share_blocker
    assert "3282 runtime preflight execution rows written" in a_share_blocker
    assert "3282 runtime preflight execution rows verified" in a_share_blocker
    assert "3282 runtime preflight batch-plan UPSERT rows planned" in a_share_blocker
    assert "0 runtime preflight batch-plan existing rows needing backup" in a_share_blocker
    assert "0 runtime preflight rows would write" in a_share_blocker
    assert "2 runtime preflight write attempts" in a_share_blocker
    assert "0 runtime preflight production writes" in a_share_blocker
    matrix = {row["requirement_id"]: row for row in report["requirements"]}
    assert matrix["module_status_classification"]["evidence"]["locked_total"] == 14
    assert matrix["module_status_classification"]["evidence"]["local_surface_counts"][
        "local_total"
    ] == 17
    assert matrix["module_status_classification"]["evidence"][
        "combined_inventory_counts"
    ]["inventory_total"] == 31
    assert (
        matrix["module_status_classification"]["evidence"]["classification_policy"][
            "normal_running_bucket_means"
        ]
        .startswith("audit evidence proves")
    )
    assert (
        matrix["module_status_classification"]["evidence"]["runtime_evidence_policy"][
            "runtime_state_is_the_preferred_semantic_status"
        ]
        is True
    )
    batch_summary = matrix["dockcase_csv_stratified_semantics"]["evidence"]["semantic_backlog_batch_summary"]
    assert batch_summary["batch_count"] == 2
    assert batch_summary["target_ranks"] == [27, 31, 46]
    assert batch_summary["sampled_rows"] == 25600
    assert matrix["frontend_bff_hot_path_latency"]["status"] == "covered"
    assert matrix["frontend_bff_hot_path_latency"]["evidence"]["frontend_latest_recheck_ok"] is True
    assert matrix["frontend_bff_hot_path_latency"]["evidence"]["bff_concurrent_ok"] is True
    assert (
        matrix["frontend_bff_hot_path_latency"]["evidence"][
            "bff_concurrent_probe_summary"
        ]["endpoint_count"]
        == 8
    )
    assert (
        matrix["frontend_bff_hot_path_latency"]["evidence"][
            "frontend_stock_detail_probe_ok"
        ]
        is True
    )
    assert (
        matrix["a_share_score_field_path"]["evidence_strength"]
        == "runtime_trace_gap_priority_candidate_evidence_field_closure_bridge_dry_run_upsert_safety_staging_payloads_value_contracts_generation_queue_l0_source_readiness_short_report_evidence_spec_numeric_validity_spec_score_conversion_path_formula_policy_review_packets_governance_suppression_verification_option_universe_na_verification_non_manual_readiness_event_text_drafts_event_text_classification_inputs_event_text_preclassification_screen_event_text_sufficiency_gate_event_text_url_fetchability_event_text_unknown_source_options_event_text_market_doc_evidence_event_text_market_doc_review_packets_local_structured_drafts_local_structured_unknown_source_options_local_structured_source_candidates_local_structured_source_review_packets_local_structured_text_drafts_local_structured_text_unknown_source_options_single_dependency_drafts_single_dependency_unknown_source_options_manual_policy_draft_pilot_manual_policy_unknown_source_options_review_staging_manifest_deterministic_runtime_approvals_review_approval_gate_completion_next_actions_unknown_closure_matrix_unknown_acquisition_backlog_unknown_market_doc_acquisition_candidates_unknown_event_evidence_adjudication_unknown_event_strict_source_gate_unknown_event_strict_review_packets_unknown_event_primary_source_confirmation_unknown_event_external_source_confirmation_unknown_local_formula_acquisition_candidates_unknown_local_formula_review_packets_local_formula_source_capability_unknown_external_business_metric_acquisition_unknown_external_business_metric_market_doc_candidates_unknown_external_business_metric_review_packets_unknown_external_business_metric_readiness_queue_unknown_external_business_metric_policy_drafts_unknown_external_business_metric_value_candidates_unknown_external_business_metric_value_review_packets_unknown_business_metric_value_selection_gate_unknown_penetration_value_priority_unknown_penetration_p1_source_confirmation_unknown_penetration_value_policy_draft_unknown_penetration_value_confirmation_packets_unknown_penetration_value_confirmation_templates_unknown_penetration_value_confirmation_gate_unknown_penetration_confirmed_known_drafts_approval_review_packets_approval_packet_risk_review_bulk_review_approval_candidates_event_approval_source_samples_individual_review_source_samples_approval_source_sample_coverage_approval_target_scope_readiness_approval_materialization_plan_approval_materialization_batch_plan_approval_materialization_batch_codex_review_approval_materialization_batch_approval_gate_approval_materialization_batch_execution_preflight_runtime_scope_approvals_runtime_write_target_scope_runtime_write_batch_plan_runtime_write_batch_approvals_runtime_write_execution_and_runtime_write_preflight"
    )
    assert matrix["a_share_score_field_path"]["evidence"]["candidate_summary"][
        "candidate_input_ready_count"
    ] == 34
    assert matrix["a_share_score_field_path"]["evidence"]["field_closure_summary"][
        "closed_score_relevant_dp_ids"
    ] == 119
    assert matrix["a_share_score_field_path"]["evidence"]["candidate_dry_run_summary"][
        "final_score_target_ready_count"
    ] == 34
    assert matrix["a_share_score_field_path"]["evidence"][
        "candidate_upsert_safety_summary"
    ]["review_gated_count"] == 34
    assert matrix["a_share_score_field_path"]["evidence"][
        "candidate_staging_summary"
    ]["deterministic_staging_payload_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "candidate_value_contracts_summary"
    ]["contract_valid_count"] == 34
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_numeric_validity_summary"
    ]["current_final_score_numeric_dp_ids"] == 119
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_numeric_validity_summary"
    ]["review_gated_unknown_dp_ids"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["numeric_and_score_path_ready_count"] == 157
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["unresolved_score_relevant_count"] == 17
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["not_numeric_or_no_formula_count"] == 14
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["no_current_numeric_input_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["formula_policy_review_required_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["governance_suppression_verified_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["option_universe_na_verified_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["review_decision_backed_not_ready_count"] == 17
    assert matrix["a_share_score_field_path"]["evidence"][
        "spec_score_conversion_summary"
    ]["remaining_unclassified_conversion_gap_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "score_conversion_remediation_summary"
    ]["missing_or_not_applicable_source_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "score_formula_policy_review_packets_summary"
    ]["direct_formula_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "score_governance_suppression_summary"
    ]["suppression_verified_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "score_option_universe_na_summary"
    ]["option_universe_packet_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "score_option_universe_na_summary"
    ]["known_value_allowed_now_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_review_packets_summary"
    ]["approval_record_template_contract_valid_count"] == 25
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_packet_risk_review_summary"
    ]["individual_review_required_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "bulk_review_approval_candidates_summary"
    ]["approval_record_draft_contract_valid_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_approval_source_samples_summary"
    ]["reviewer_packet_complete_count"] == 10
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_approval_source_samples_summary"
    ]["dockcase_file_readable_count"] == 48
    assert matrix["a_share_score_field_path"]["evidence"][
        "individual_review_source_samples_summary"
    ]["reviewer_packet_complete_count"] == 10
    assert matrix["a_share_score_field_path"]["evidence"][
        "individual_review_source_samples_summary"
    ]["individual_policy_review_required_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_source_sample_coverage_summary"
    ]["approval_input_ready_count"] == 25
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_source_sample_coverage_summary"
    ]["source_sample_route_counts"]["bulk_review_source_sample"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_source_sample_coverage_summary"
    ]["source_sample_route_counts"]["event_approval_source_sample"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_source_sample_coverage_summary"
    ]["source_sample_route_counts"]["individual_review_source_sample"] == 10
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_target_scope_readiness_summary"
    ]["target_scope_policy_required_count"] == 25
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_target_scope_readiness_summary"
    ]["per_stock_value_materialization_required_count"] == 19
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_target_scope_readiness_summary"
    ]["market_or_event_scope_policy_required_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_target_scope_readiness_summary"
    ]["target_scope_ready_after_approval_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["direct_structured_formula_plan_ready_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["direct_structured_formula_min_target_count"] == 868
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["grain_join_policy_required_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["text_evidence_full_match_export_required_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["market_or_event_scope_policy_required_count"] == 14
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_plan_summary"
    ]["runtime_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_plan_summary"
    ]["batch_plan_entry_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_plan_summary"
    ]["batch_plan_contract_valid_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_plan_summary"
    ]["planned_upsert_row_count"] == 9995
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_plan_summary"
    ]["batch_plan_review_required_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_plan_summary"
    ]["runtime_write_attempted_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_codex_review_summary"
    ]["codex_review_approved_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_codex_review_summary"
    ]["codex_review_rejected_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_codex_review_summary"
    ]["approval_record_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_codex_review_summary"
    ]["approved_planned_upsert_row_count"] == 9995
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["batch_plan_row_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["approval_records_seen"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["approval_missing_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["approved_controlled_formula_batch_plan_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["approved_planned_upsert_row_count"] == 9995
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["blank_approval_template_contract_valid_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_approval_gate_summary"
    ]["runtime_write_allowed_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_execution_preflight_summary"
    ]["execution_status"] == "dry_run_ready"
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_execution_preflight_summary"
    ]["preflight_ready_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_execution_preflight_summary"
    ]["runtime_rows_would_write_count"] == 9995
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_materialization_batch_execution_preflight_summary"
    ]["runtime_write_attempted_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "candidate_generation_queue_summary"
    ]["generator_required_task_count"] == 32
    assert matrix["a_share_score_field_path"]["evidence"][
        "l0_source_readiness_summary"
    ]["direct_structured_tushare_remaining"] == 0
    assert (
        len(
            matrix["a_share_score_field_path"]["evidence"][
                "l0_source_readiness_summary"
            ]["dependency_dp_ids_with_runtime_rows"]
        )
        == 17
    )
    assert matrix["a_share_score_field_path"]["evidence"][
        "short_report_evidence_summary"
    ]["news_html_files_scanned"] == 14956
    assert matrix["a_share_score_field_path"]["evidence"][
        "short_report_evidence_summary"
    ]["direct_a_share_short_report_documents"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "non_manual_readiness_summary"
    ]["bridge_probe_ready_count"] == 28
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_draft_summary"
    ]["draft_unknown_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_draft_summary"
    ]["draft_known_count"] == 10
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_draft_summary"
    ]["bridge_validated_known_count"] == 10
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_classification_inputs_summary"
    ]["classification_input_ready_count"] == 12
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_preclassification_screen_summary"
    ]["direct_known_candidate_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_sufficiency_gate_summary"
    ]["title_signal_sufficient_for_classifier_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_url_fetchability_summary"
    ]["body_signal_sufficient_for_classifier_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_unknown_source_options_summary"
    ]["candidate_requires_target_event_evidence_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_unknown_source_options_summary"
    ]["candidate_requires_direct_a_share_transmission_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_market_doc_evidence_summary"
    ]["market_doc_review_candidate_count"] == 11
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_market_doc_evidence_summary"
    ]["rows_still_requiring_direct_transmission_link_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_market_doc_review_packets_summary"
    ]["market_doc_review_ready_count"] == 11
    assert matrix["a_share_score_field_path"]["evidence"][
        "event_text_market_doc_review_packets_summary"
    ]["requires_direct_transmission_link_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_draft_summary"
    ]["draft_known_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_draft_summary"
    ]["bridge_validated_known_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_unknown_source_options_summary"
    ]["direct_existing_structured_source_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_unknown_source_options_summary"
    ]["partial_known_unlock_candidate_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_source_candidates_summary"
    ]["unknown_dp_count"] == 4
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_source_candidates_summary"
    ]["direct_known_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_source_review_packets_summary"
    ]["local_structured_source_review_packet_count"] == 4
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_source_review_packets_summary"
    ]["formula_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_text_draft_summary"
    ]["draft_unknown_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_text_draft_summary"
    ]["draft_known_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_text_draft_summary"
    ]["bridge_validated_known_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_text_unknown_source_options_summary"
    ]["direct_text_classification_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_structured_text_unknown_source_options_summary"
    ]["candidate_requires_text_classification_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_draft_summary"
    ]["draft_known_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_draft_summary"
    ]["draft_contract_invalid_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["direct_replacement_cycle_source_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["rows_with_overlay_lifecycle_context_candidate_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["overlay_lifecycle_known_node_count"] == 205
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["candidate_requires_lifecycle_source_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["lifecycle_policy_review_template_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["lifecycle_policy_review_template_contract_valid_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["lifecycle_policy_review_template_blank_pending_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "single_dependency_unknown_source_options_summary"
    ]["approval_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "manual_policy_draft_summary"
    ]["draft_known_count"] == 4
    assert matrix["a_share_score_field_path"]["evidence"][
        "manual_policy_unknown_source_options_summary"
    ]["direct_reviewed_assumption_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "manual_policy_unknown_source_options_summary"
    ]["required_assumption_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "review_staging_manifest_summary"
    ]["review_ready_concrete_count"] == 27
    assert matrix["a_share_score_field_path"]["evidence"][
        "deterministic_runtime_approvals_summary"
    ]["approval_record_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "review_approval_gate_summary"
    ]["approval_missing_count"] == 25
    assert matrix["a_share_score_field_path"]["evidence"][
        "completion_next_actions_summary"
    ]["approval_ready_packet_count"] == 25
    assert matrix["a_share_score_field_path"]["evidence"][
        "completion_next_actions_summary"
    ]["runtime_write_plan_ready_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_closure_matrix_summary"
    ]["unknown_closure_row_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_closure_matrix_summary"
    ]["closure_route_assigned_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_closure_matrix_summary"
    ]["missing_closure_route_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_closure_matrix_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_acquisition_backlog_summary"
    ]["unknown_acquisition_task_count"] == 7
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_acquisition_backlog_summary"
    ]["event_doc_search_task_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_acquisition_backlog_summary"
    ]["web_or_external_acquisition_required_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_acquisition_backlog_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_market_doc_acquisition_summary"
    ]["market_doc_acquisition_task_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_market_doc_acquisition_summary"
    ]["new_entrant_review_candidate_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_market_doc_acquisition_summary"
    ]["substitute_clean_risk_review_candidate_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_market_doc_acquisition_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_market_doc_acquisition_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_evidence_adjudication_summary"
    ]["candidate_examples_reviewed_count"] == 14
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_evidence_adjudication_summary"
    ]["accepted_candidate_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_evidence_adjudication_summary"
    ]["remaining_unknown_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["event_strict_gate_row_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["market_html_files_scanned"] == 14956
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["strict_candidate_count"] == 11
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["strict_review_candidate_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["classifier_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_source_gate_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["strict_review_packet_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["requires_primary_source_confirmation_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["deterministic_rejected_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["classifier_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_strict_review_packets_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["primary_confirmation_packet_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["local_candidate_count"] == 12
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["local_high_quality_confirmation_candidate_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["local_supporting_context_only_count"] == 12
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["classifier_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_primary_source_confirmation_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["external_confirmation_packet_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["external_source_card_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["external_confirmation_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["external_supporting_context_count"] == 4
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["rows_with_external_confirmation_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_candidate_contract_valid_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_candidate_contract_invalid_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_candidate_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_review_required_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_primary_source_covered_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_required_label_count"] == 12
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_input_guardrail_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_review_template_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_review_template_contract_valid_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_review_template_contract_invalid_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_review_template_blank_pending_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_review_template_input_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["classifier_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_event_external_source_confirmation_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["local_formula_acquisition_task_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["sample_csv_files_existing"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["rows_with_candidate_numerator_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["rows_with_quantity_or_price_index_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["formula_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_acquisition_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["local_formula_review_packet_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["rows_with_denominator_candidate_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["rows_with_candidate_formula_shape_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["rows_with_formula_policy_draft_candidate_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["formula_policy_review_template_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["formula_policy_review_template_contract_valid_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["formula_policy_review_template_blank_pending_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["rows_with_price_index_context_candidate_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["rows_with_candidate_price_context_shape_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["price_context_review_template_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["price_context_review_template_contract_valid_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["price_context_review_template_blank_pending_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["formula_probe_available_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["bridge_probe_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_local_formula_review_packets_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_formula_source_capability_summary"
    ]["source_capability_check_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_formula_source_capability_summary"
    ]["header_available_but_sample_empty_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_formula_source_capability_summary"
    ]["formula_blocker_resolved_by_current_source_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "local_formula_source_capability_summary"
    ]["formula_inputs_ready_after_source_scan_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["external_business_metric_task_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["runtime_dependency_ready_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["business_metric_group_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["rows_with_overlay_business_context_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["overlay_business_context_known_node_count"] == 527
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["overlay_frequency_direct_known_node_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["overlay_penetration_direct_unknown_node_count"] == 1646
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["rows_with_direct_business_metric_source_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["metric_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_acquisition_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["business_metric_market_doc_task_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["market_html_files_scanned"] == 14956
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["rows_with_review_candidates_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["review_candidate_count"] == 99
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["numeric_review_candidate_count"] == 49
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["metric_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_market_doc_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["business_metric_review_packet_count"] == 99
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["expected_review_candidate_count"] == 99
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["rows_with_review_packets_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["numeric_review_packet_count"] == 49
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["metric_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_review_packets_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["formula_policy_only_candidate_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["period_or_unit_required_count"] == 52
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["denominator_required_count"] == 29
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["missing_formula_policy_count"] == 99
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["metric_inputs_ready_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_readiness_queue_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["policy_draft_packet_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["formula_policy_review_required_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["value_json_template_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["policy_review_template_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["policy_review_template_contract_valid_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["policy_review_template_blank_pending_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_policy_drafts_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_candidates_summary"
    ]["value_candidate_adjudication_row_count"] == 18
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_candidates_summary"
    ]["shortlist_review_required_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_candidates_summary"
    ]["scope_rejected_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_candidates_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_candidates_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["value_review_packet_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["candidate_value_option_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["bridge_probe_ready_option_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["selected_raw_value_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_external_business_metric_value_review_packets_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["business_metric_selection_row_count"] == 3
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["bridge_probe_ready_option_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["review_value_selection_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["value_policy_draft_ready_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["proposed_value_json_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["source_metric_missing_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["auto_selectable_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_business_metric_value_selection_gate_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_priority_summary"
    ]["penetration_value_review_packet_count"] == 6
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_priority_summary"
    ]["preferred_source_scope_review_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_priority_summary"
    ]["bridge_probe_ready_option_count"] == 8
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_p1_source_confirmation_summary"
    ]["source_file_found_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_p1_source_confirmation_summary"
    ]["raw_value_token_confirmed_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_p1_source_confirmation_summary"
    ]["source_scope_confirmed_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_policy_draft_summary"
    ]["draft_row_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_policy_draft_summary"
    ]["proposed_value_json_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_policy_draft_summary"
    ]["bridge_final_score_ready_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_packets_summary"
    ]["value_confirmation_packet_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_packets_summary"
    ]["confirmation_record_template_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_packets_summary"
    ]["confirmation_packet_contract_valid_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_packets_summary"
    ]["known_draft_sufficient_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_templates_summary"
    ]["confirmation_template_bundle_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_templates_summary"
    ]["blank_pending_template_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_templates_summary"
    ]["blank_pending_template_contract_valid_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_templates_summary"
    ]["confirmed_template_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_templates_summary"
    ]["runtime_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_gate_summary"
    ]["confirmation_packet_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_gate_summary"
    ]["confirmation_records_seen"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_gate_summary"
    ]["confirmation_missing_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_value_confirmation_gate_summary"
    ]["known_draft_candidate_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_confirmed_known_drafts_summary"
    ]["confirmation_gate_row_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_confirmed_known_drafts_summary"
    ]["known_draft_emitted_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_confirmed_known_drafts_summary"
    ]["known_draft_blocked_count"] == 1
    assert matrix["a_share_score_field_path"]["evidence"][
        "unknown_penetration_confirmed_known_drafts_summary"
    ]["ready_for_review_staging_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_review_packets_summary"
    ]["approval_review_packet_count"] == 27
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_scope_approvals_summary"
    ]["approved_runtime_target_scope_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_scope_approvals_summary"
    ]["candidate_runtime_rows_would_write_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_scope_approvals_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["approved_write_plan_entry_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["runtime_a_share_ts_code_count"] == 1641
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["config_runtime_a_share_exact_match"] is True
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["target_scope_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["target_scope_review_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["target_scope_approved_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["controlled_batch_plan_required_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_target_scope_summary"
    ]["candidate_runtime_rows_would_write_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["batch_plan_entry_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["batch_plan_contract_valid_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["batch_plan_review_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["batch_plan_approved_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["planned_upsert_row_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_plan_summary"
    ]["runtime_write_attempted_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_approvals_summary"
    ]["batch_approval_record_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_approvals_summary"
    ]["approved_controlled_batch_plan_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_approvals_summary"
    ]["planned_upsert_row_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_batch_approvals_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["approved_controlled_batch_plan_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["execution_ready_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["backup_completed_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["runtime_write_completed_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["runtime_rows_written_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["post_write_verified_row_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_execution_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["upsert_ready_entry_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["missing_target_scope_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["target_scope_review_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["controlled_batch_plan_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["batch_plan_candidate_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["batch_plan_review_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["batch_plan_approved_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["executed_entry_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["runtime_backup_execution_required_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["runtime_execution_completed_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["runtime_execution_rows_written_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["runtime_execution_post_write_verified_row_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["batch_plan_planned_upsert_rows_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["candidate_runtime_rows_would_write_count"] == 3282
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["runtime_write_attempted_count"] == 2
    assert matrix["a_share_score_field_path"]["evidence"][
        "runtime_write_preflight_summary"
    ]["production_write_allowed_count"] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_cross_report_consistency_error_count"
    ] == 0
    assert matrix["a_share_score_field_path"]["evidence"][
        "approval_cross_report_consistency_errors"
    ] == []
    assert matrix["frontend_bff_hot_path_latency"]["evidence"]["frontend_shell_ok"] is True
    assert matrix["frontend_bff_hot_path_latency"]["evidence"]["frontend_navigation_ok"] is True
    assert (
        matrix["frontend_bff_hot_path_latency"]["evidence_strength"]
        == "machine_bff_latency_plus_machine_browser_qa_plus_spa_shell_latency_plus_navigation_contract_plus_stock_detail_probe_plus_bff_concurrent_probe"
    )
    assert matrix["repo_operational_file_inventory"]["evidence"]["text_files_read"] == 7
    assert matrix["repo_operational_file_inventory"]["evidence"]["skipped_file_samples"] == 1
    assert (
        matrix["repo_operational_file_inventory"]["evidence"][
            "skipped_file_fingerprints_count"
        ]
        == 3
    )
    assert (
        matrix["repo_operational_file_inventory"]["evidence_strength"]
        == "metadata_full_walk_plus_bounded_text_body_read"
    )
    assert matrix["dockcase_csv_stratified_semantics"]["evidence"]["sampled_rows"] == 120
    assert matrix["dockcase_csv_stratified_semantics"]["evidence"][
        "csv_file_evidence_summary"
    ]["file_evidence_count"] == 20
    assert (
        matrix["dockcase_csv_stratified_semantics"]["evidence_strength"]
        == "all_csv_file_head_tail_evidence_plus_signature_stratified_bounded_semantic_rows_plus_partial_full_row_scan"
    )
    assert matrix["dockcase_csv_stratified_semantics"]["evidence"]["csv_full_scan_summary"][
        "rows_scanned"
    ] == 2721034
    assert matrix["dockcase_csv_stratified_semantics"]["evidence"][
        "csv_full_scan_progress_exists"
    ] is True
    assert matrix["dockcase_csv_stratified_semantics"]["evidence"]["coverage_gaps"][
        "csv_files_not_selected_for_row_sampling"
    ] == 16
    remaining_gap = matrix["a_share_score_field_path"]["remaining_gap"]
    assert "Current score-field closure is 119/174 score-relevant dp_ids" in remaining_gap
    assert "34 actionable gaps for source-backed candidate review" in remaining_gap
    assert "Event-text policy pilot checks 12 tasks" in remaining_gap
    assert "drafts 10 Known review packets" in remaining_gap
    assert "leaves 2 Unknown" in remaining_gap
    assert "marks 27 concrete review-ready" in remaining_gap
    assert "splits 34 actions into 25 human approvals" in remaining_gap
    assert "2 runtime-write-plan-ready packets" in remaining_gap
    assert "and 7 Unknown resolutions" in remaining_gap
    assert "Score-conversion remediation queue classifies 17 unresolved fields" in remaining_gap
    assert "6 formula-policy/peer-context rows" in remaining_gap
    assert "8 governed-or-duplicate rows" in remaining_gap
    assert "3 listed-option-source/N/A rows" in remaining_gap
    assert "Formula-policy review packets package 6 rows" in remaining_gap
    assert "leave 0 direct formulas ready" in remaining_gap
    assert "Governance-suppression verification packages 8 rows" in remaining_gap
    assert "verifies 8 suppressions" in remaining_gap
    assert "Option-universe/N/A verification packages 3 rows" in remaining_gap
    assert "allows 0 Known values now" in remaining_gap
    assert "Local structured policy pilot checks 10 tasks" in remaining_gap
    assert "drafts 6 Known review packets" in remaining_gap
    assert "leaves 4 Unknown" in remaining_gap
    assert "bridge-validates 6 Known drafts" in remaining_gap
    assert "Local structured Unknown source-options audit reviews 4 Unknown rows" in remaining_gap
    assert "confirms 4 have runtime dependencies ready" in remaining_gap
    assert "finds 0 direct structured source-ready rows" in remaining_gap
    assert "records 4 overlay/source hints" in remaining_gap
    assert "marks 4 needing new mapping or text extraction" in remaining_gap
    assert "0 needing reviewed policy" in remaining_gap
    assert "0 partial Known unlock candidate" in remaining_gap
    assert "allows 0 auto Known candidates" in remaining_gap
    assert "allows 0 production writes" in remaining_gap
    assert "Local structured source-candidates audit checks 4 Unknown dp_ids" in remaining_gap
    assert "finds 0 direct Known-ready rows" in remaining_gap
    assert "records 1 review candidate matches" in remaining_gap
    assert "4 supporting candidate matches" in remaining_gap
    assert "excludes 407 false-positive field/path matches" in remaining_gap
    assert "Local structured source-review packets package 4 Unknown rows" in remaining_gap
    assert "mark 1 lease/rent candidate ready for review" in remaining_gap
    assert "1 ASP packet needing quantity or price-index source" in remaining_gap
    assert "2 packets requiring external business sources" in remaining_gap
    assert "0 formula-ready packets" in remaining_gap
    assert "Local structured-text policy pilot checks 3 tasks" in remaining_gap
    assert "drafts 3 Known review packets" in remaining_gap
    assert "leaves 0 Unknown" in remaining_gap
    assert "bridge-validates 3 Known drafts" in remaining_gap
    assert "Local structured-text Unknown source-options audit reviews 0 Unknown rows" in remaining_gap
    assert "confirms 0 have runtime dependencies ready" in remaining_gap
    assert "0 have QA recent dependencies ready" in remaining_gap
    assert "finds 0 direct text-classification-ready rows" in remaining_gap
    assert "records 0 overlay/source hints" in remaining_gap
    assert "marks 0 needing text classification" in remaining_gap
    assert "Local single-dependency Unknown source-options audit reviews 1 Unknown rows" in remaining_gap
    assert "finds 0 direct replacement-cycle source-ready rows" in remaining_gap
    assert "marks 1 needing lifecycle/replacement-cycle evidence" in remaining_gap
    assert "Manual-policy draft pilot checks 4 queued manual tasks" in remaining_gap
    assert "drafts 4 Known review packets" in remaining_gap
    assert "leaves 0 Unknown" in remaining_gap
    assert "Manual-policy Unknown source-options audit reviews 0 Unknown rows" in remaining_gap
    assert "finds 0 direct reviewed-assumption-ready rows" in remaining_gap
    assert "requires 0 reviewed assumptions" in remaining_gap
    assert "marks 0 needing assumption review" in remaining_gap
    assert "Event-text Unknown source-options audit reviews 2 Unknown rows" in remaining_gap
    assert "confirms 2 have classification inputs ready" in remaining_gap
    assert "2 have body text available" in remaining_gap
    assert "finds 0 with target-event evidence" in remaining_gap
    assert "0 with direct A-share transmission" in remaining_gap
    assert "2 broad-market-only transmission rows" in remaining_gap
    assert "0 classifier-ready review candidates" in remaining_gap
    assert "marks 2 needing target-event evidence" in remaining_gap
    assert "0 needing direct A-share transmission" in remaining_gap
    assert "Event-text market-doc evidence scan checks 12 Unknown rows" in remaining_gap
    assert "scans 14956 DOCKCASE market HTML files" in remaining_gap
    assert "0 read errors" in remaining_gap
    assert "finds market-doc target evidence for 12" in remaining_gap
    assert "direct transmission evidence for 12" in remaining_gap
    assert "same-sentence review candidates for 11" in remaining_gap
    assert "0 still needing target evidence" in remaining_gap
    assert "1 still needing direct-transmission links" in remaining_gap
    assert "marks 11 market-doc review candidates" in remaining_gap
    assert "Event-text market-doc review packets package 12 packets" in remaining_gap
    assert "mark 11 market-doc review-ready" in remaining_gap
    assert "leave 0 needing target-event evidence" in remaining_gap
    assert "1 needing direct-transmission links" in remaining_gap
    assert "retain 53 candidate examples" in remaining_gap
    assert "validate 12 packet contracts" in remaining_gap
    assert "flag 0 invalid packet contracts" in remaining_gap
    assert "Unknown event strict-source gate rescans 2 event Unknown rows" in remaining_gap
    assert "across 14956 market HTML files with 0 read errors" in remaining_gap
    assert "finds 11 strict candidates" in remaining_gap
    assert "8 strict review candidates" in remaining_gap
    assert "3 strict rejected candidates" in remaining_gap
    assert "0 classifier-ready rows" in remaining_gap
    assert "0 Known-draft-sufficient rows" in remaining_gap
    assert "0 approval-ready rows" in remaining_gap
    assert "2 strict gate contracts valid" in remaining_gap
    assert "and 0 production writes" in remaining_gap
    assert "Unknown event strict-review packets triage 8 strict candidates" in remaining_gap
    assert "with 2 low-confidence community/forum source packets" in remaining_gap
    assert "6 secondary-newswire packets" in remaining_gap
    assert "2 requiring primary-source confirmation" in remaining_gap
    assert "0 requiring manual review" in remaining_gap
    assert "6 deterministically rejected" in remaining_gap
    assert "0 classifier-ready packets" in remaining_gap
    assert "0 Known-draft-sufficient packets" in remaining_gap
    assert "0 approval-ready packets" in remaining_gap
    assert "8 packet contracts valid" in remaining_gap
    assert "Unknown event primary-source confirmation scan checks 2 low-confidence packets" in remaining_gap
    assert "across 14956 local market HTML files with 0 read errors" in remaining_gap
    assert "finds 12 local candidates" in remaining_gap
    assert "0 local high-quality confirmation candidates" in remaining_gap
    assert "12 supporting-context-only candidates" in remaining_gap
    assert "0 rows with local confirmation candidates" in remaining_gap
    assert "2 rows with supporting context only" in remaining_gap
    assert "0 rows without local confirmation candidates" in remaining_gap
    assert "0 classifier-ready rows" in remaining_gap
    assert "0 Known-draft-sufficient rows" in remaining_gap
    assert "0 approval-ready rows" in remaining_gap
    assert "2 confirmation contracts valid" in remaining_gap
    assert "Unknown event external-source confirmation packages 2 packets" in remaining_gap
    assert "6 source cards" in remaining_gap
    assert "2 external confirmation candidates" in remaining_gap
    assert "4 supporting-context cards" in remaining_gap
    assert "2 rows with external confirmation candidates" in remaining_gap
    assert "0 rows with supporting context only" in remaining_gap
    assert "0 classifier-ready rows" in remaining_gap
    assert "0 Known-draft-sufficient rows" in remaining_gap
    assert "0 approval-ready rows" in remaining_gap
    assert "2 contracts valid" in remaining_gap
    assert "and 0 production writes" in remaining_gap
    assert "Unknown closure matrix checks 7 review-gated Unknown rows" in remaining_gap
    assert "assigns 7 closure routes" in remaining_gap
    assert "leaves 0 missing closure routes" in remaining_gap
    assert "splits routes into 2 event-text classifications" in remaining_gap
    assert "4 local structured mappings" in remaining_gap
    assert "0 structured-text extractions" in remaining_gap
    assert "1 single-dependency policies" in remaining_gap
    assert "0 manual assumption reviews" in remaining_gap
    assert "3 rows with source candidates" in remaining_gap
    assert "0 formula-ready rows" in remaining_gap
    assert "0 auto Known-ready rows" in remaining_gap
    assert "0 approval-ready Unknown rows" in remaining_gap
    assert "7 closure contracts valid" in remaining_gap
    assert "Unknown business-metric value-selection gate checks 3 rows" in remaining_gap
    assert "8 bridge-probe-ready options" in remaining_gap
    assert "marks 0 value-selection-review rows" in remaining_gap
    assert "1 value-policy-draft-ready rows" in remaining_gap
    assert "1 proposed value JSONs" in remaining_gap
    assert "2 rows still source-metric-missing" in remaining_gap
    assert "0 auto-selectable values" in remaining_gap
    assert "Unknown penetration value-confirmation packets package 1 review-required packets" in remaining_gap
    assert "include 1 blank confirmation templates" in remaining_gap
    assert "validate 1 template contracts and 1 packet contracts" in remaining_gap
    assert "Unknown penetration value-confirmation template bundle extracts 1 templates from packets" in remaining_gap
    assert "keeps 1 blank/pending templates" in remaining_gap
    assert "validates 1 blank template contracts" in remaining_gap
    assert "sees 0 confirmed templates" in remaining_gap
    assert "0 runtime writes" in remaining_gap
    assert "Unknown penetration value-confirmation gate checks 1 packets" in remaining_gap
    assert "sees 0 confirmation records" in remaining_gap
    assert "marks 1 confirmations missing" in remaining_gap
    assert "0 Known-draft candidates" in remaining_gap
    assert "Unknown penetration confirmed Known-draft emitter checks 1 confirmation-gate rows" in remaining_gap
    assert "emits 0 Known drafts" in remaining_gap
    assert "blocks 1 rows" in remaining_gap
    assert "marks 0 ready for review staging" in remaining_gap
    assert "Runtime-scope approval audit checks 2 target-scope rows" in remaining_gap
    assert "creates 2 scope approval records" in remaining_gap
    assert "approves 2 runtime target scopes" in remaining_gap
    assert "rejects 0" in remaining_gap
    assert (
        "tracks 3282 candidate runtime rows that would write if later batch-approved"
        in remaining_gap
    )
    assert "Runtime-write target-scope audit checks 2 approved write-plan entries" in remaining_gap
    assert "matches 1641 runtime A-share ts_codes to 1641 configured A-share ts_codes" in remaining_gap
    assert "packages 2 target-scope candidates" in remaining_gap
    assert "validates 2 target-scope contracts" in remaining_gap
    assert "keeps 0 target-scope reviews required" in remaining_gap
    assert "marks 2 target scopes approved" in remaining_gap
    assert "requires 2 controlled batch plans" in remaining_gap
    assert "would write 3282 candidate runtime rows if later approved" in remaining_gap
    assert "finds 0 upsert-ready entries" in remaining_gap
    assert "Runtime-write execution audit covers 2 approved batch plans" in remaining_gap
    assert "has 2 execution-ready plans" in remaining_gap
    assert "blocks 0" in remaining_gap
    assert "completes backup for 2 plans" in remaining_gap
    assert "attempts 2 runtime writes" in remaining_gap
    assert "completes 2" in remaining_gap
    assert "writes 3282 runtime rows" in remaining_gap
    assert "post-write verifies 3282 rows" in remaining_gap
    assert "Runtime-write preflight checks 2 approved write-plan entries" in remaining_gap
    assert "finds 0 upsert-ready entries" in remaining_gap
    assert "finds 2 executed entries" in remaining_gap
    assert "blocks 0" in remaining_gap
    assert "finds 0 missing target scopes" in remaining_gap
    assert "tracks 3282 candidate runtime rows that would write if later approved" in remaining_gap
    assert "requires 2 controlled batch plans" in remaining_gap
    assert "recognizes 2 runtime executions complete" in remaining_gap
    assert "tracks 3282 execution-written rows" in remaining_gap
    assert "verifies 3282 execution-written rows" in remaining_gap
    assert "would write 0 runtime rows" in remaining_gap
    assert "attempts 2 runtime writes" in remaining_gap
    assert "safe-to-upsert-without-review remains 0" in remaining_gap
    assert (
        matrix["market_document_extractability_sample"]["evidence"]["signal_counts"][
            "entity_signal_samples"
        ]
        == 2
    )
    assert matrix["market_document_extractability_sample"]["evidence"]["coverage_gaps"][
        "document_files_not_selected_for_extractability_sampling"
    ] == 2

    _write_json(
        audit_dir / "dockcase_csv_full_scan_progress_2026-06-19.json",
        {
            "summary": {
                "shard_count": 3,
                "total_business_csv_files": 20,
                "csv_files_scanned": 20,
                "rows_scanned": 3000,
                "row_read_error_count": 0,
                "row_width_mismatch_count": 0,
                "range_gap_count": 0,
                "range_overlap_count": 0,
                "full_row_semantic_scan_complete": True,
            }
        },
    )
    _write_json(
        audit_dir / "repo_binary_semantics_2026-06-19.json",
        {
            "summary": {
                "skipped_files_from_repo_content": 3,
                "semantic_records": 3,
                "semantic_error_count": 0,
                "missing_file_count": 0,
                "all_skipped_files_classified": True,
                "all_existing_files_have_semantic_kind": True,
            }
        },
    )
    complete_report = audit_goal_coverage.build_report(audit_dir)
    complete_matrix = {
        row["requirement_id"]: row for row in complete_report["requirements"]
    }
    assert not any(
        blocker.startswith("repo binary/large files")
        for blocker in complete_report["summary"]["completion_blockers"]
    )
    assert not any(
        blocker.startswith("DOCKCASE CSV semantic review")
        for blocker in complete_report["summary"]["completion_blockers"]
    )
    assert (
        complete_matrix["repo_operational_file_inventory"]["evidence_strength"]
        == "metadata_full_walk_plus_text_body_read_plus_binary_large_semantic_audit"
    )
    assert (
        complete_matrix["dockcase_csv_stratified_semantics"]["evidence_strength"]
        == "all_csv_file_head_tail_evidence_plus_full_row_semantic_scan"
    )
    assert (
        complete_matrix["dockcase_csv_stratified_semantics"]["remaining_gap"]
        == "Every business CSV now has file-level head/tail fingerprint evidence and full-row semantic scan coverage; the full-row scanner has read 3000 rows from 20 files with 0 row-read errors, 0 row-width mismatches, 0 shard gaps, and 0 shard overlaps. The remaining work is issue interpretation/remediation, not row/file coverage."
    )


def test_score_approval_consistency_errors_detect_count_drift() -> None:
    errors = audit_goal_coverage._score_approval_consistency_errors(
        review_manifest_summary={
            "review_ready_concrete_count": 27,
            "review_gated_unknown_count": 7,
        },
        deterministic_approvals_summary={
            "approved_deterministic_runtime_write_count": 2,
            "production_write_allowed_count": 0,
        },
        approval_gate_summary={
            "approval_required_count": 27,
            "approval_missing_count": 25,
            "not_approvable_unknown_count": 7,
            "approved_runtime_write_count": 2,
            "write_plan_count": 2,
            "production_write_allowed_count": 0,
        },
        completion_next_actions_summary={
            "approval_ready_packet_count": 26,
            "runtime_write_plan_ready_count": 2,
            "unknown_resolution_required_count": 7,
            "approval_record_template_count": 25,
            "approved_runtime_write_count": 2,
            "write_plan_count": 2,
            "production_write_allowed_count": 0,
        },
        approval_review_packets_summary={
            "approval_review_packet_count": 27,
            "final_score_target_ready_count": 26,
            "approval_missing_count": 25,
            "approval_record_template_count": 25,
            "approval_record_template_contract_valid_count": 25,
            "approved_runtime_write_count": 2,
            "write_plan_count": 2,
            "production_write_allowed_count": 0,
        },
        spec_numeric_validity_summary={
            "approval_missing_count": 25,
            "approved_runtime_write_count": 1,
            "production_write_allowed_count": 0,
        },
    )

    assert (
        "approval_gate.approval_missing_count=25 does not match "
        "completion_next_actions.approval_ready_packet_count=26"
    ) in errors
    assert (
        "approval_review_packets.approval_review_packet_count=27 does not match "
        "approval_review_packets.final_score_target_ready_count=26"
    ) in errors
    assert (
        "approval_gate.approved_runtime_write_count=2 does not match "
        "spec_numeric_validity.approved_runtime_write_count=1"
    ) in errors


def test_score_approval_consistency_accepts_executed_deterministic_writes() -> None:
    errors = audit_goal_coverage._score_approval_consistency_errors(
        review_manifest_summary={
            "review_ready_concrete_count": 25,
            "review_gated_unknown_count": 7,
        },
        deterministic_approvals_summary={
            "approved_deterministic_runtime_write_count": 2,
            "production_write_allowed_count": 0,
        },
        approval_gate_summary={
            "approval_required_count": 25,
            "approval_missing_count": 25,
            "not_approvable_unknown_count": 7,
            "approved_runtime_write_count": 0,
            "write_plan_count": 0,
            "production_write_allowed_count": 0,
        },
        completion_next_actions_summary={
            "approval_ready_packet_count": 25,
            "runtime_write_plan_ready_count": 0,
            "unknown_resolution_required_count": 7,
            "approval_record_template_count": 25,
            "approved_runtime_write_count": 0,
            "write_plan_count": 0,
            "production_write_allowed_count": 0,
        },
        approval_review_packets_summary={
            "approval_review_packet_count": 25,
            "final_score_target_ready_count": 25,
            "approval_missing_count": 25,
            "approval_record_template_count": 25,
            "approval_record_template_contract_valid_count": 25,
            "approved_runtime_write_count": 0,
            "write_plan_count": 0,
            "production_write_allowed_count": 0,
        },
        spec_numeric_validity_summary={
            "approval_missing_count": 25,
            "approved_runtime_write_count": 0,
            "production_write_allowed_count": 0,
        },
        runtime_write_execution_summary={
            "runtime_write_completed_count": 2,
            "runtime_write_failed_count": 0,
            "runtime_rows_written_count": 3282,
            "post_write_verified_row_count": 3282,
            "post_write_verification_error_count": 0,
            "production_write_allowed_count": 0,
        },
    )

    assert errors == []


def test_goal_coverage_marks_missing_evidence(tmp_path: Path) -> None:
    report = audit_goal_coverage.build_report(tmp_path / "missing")

    assert report["completion_status"] == "not_complete"
    assert report["summary"]["missing_evidence_count"] == report["summary"]["requirement_count"]
