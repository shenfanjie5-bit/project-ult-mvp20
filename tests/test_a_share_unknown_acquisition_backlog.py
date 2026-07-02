import json
from pathlib import Path

from scripts import audit_a_share_unknown_acquisition_backlog as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _closure_row(
    dp_id: str,
    closure_track: str,
    closure_blocker_class: str,
    current_best_evidence: dict,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "closure_track": closure_track,
        "closure_blocker_class": closure_blocker_class,
        "next_action_bucket": "bucket",
        "minimum_unlock_evidence": ["unlock"],
        "current_best_evidence": current_best_evidence,
        "source_dependencies": ["dep"],
        "evidence_refs": ["evidence"],
    }


def test_unknown_acquisition_backlog_builds_source_tasks(tmp_path: Path) -> None:
    closure_path = tmp_path / "closure.json"
    _write_json(
        closure_path,
        {
            "rows": [
                _closure_row(
                    "L0.compete.new_entrant",
                    "market_document_event_evidence",
                    "direct_event_transmission_evidence_required",
                    {
                        "candidate_example_count": 0,
                        "required_evidence": ["direct link"],
                    },
                ),
                _closure_row(
                    "L0.tech.substitute_tech",
                    "market_document_event_evidence",
                    "clean_substitution_risk_evidence_required",
                    {
                        "candidate_example_count": 5,
                        "required_evidence": ["clean risk"],
                    },
                ),
                _closure_row(
                    "L0.cost.rent",
                    "local_structured_formula_review",
                    "formula_policy_required",
                    {
                        "candidate_columns": ["use_right_asset_dep"],
                        "missing_formula_inputs": ["denominator"],
                        "formula_inputs_ready": False,
                    },
                ),
                _closure_row(
                    "L0.price.product_asp",
                    "local_structured_formula_review",
                    "quantity_or_price_index_source_required",
                    {
                        "candidate_columns": ["bz_item", "bz_sales"],
                        "missing_formula_inputs": ["quantity"],
                        "formula_inputs_ready": False,
                    },
                ),
                _closure_row(
                    "L0.demand.frequency",
                    "external_or_text_business_metric",
                    "external_business_source_required",
                    {
                        "candidate_columns": [],
                        "missing_formula_inputs": ["orders", "denominator"],
                        "formula_inputs_ready": False,
                    },
                ),
                _closure_row(
                    "L0.demand.penetration",
                    "external_or_text_business_metric",
                    "external_business_source_required",
                    {
                        "candidate_columns": [],
                        "missing_formula_inputs": ["market denominator"],
                        "formula_inputs_ready": False,
                    },
                ),
                _closure_row(
                    "L0.demand.replacement",
                    "external_or_text_business_metric",
                    "lifecycle_source_and_policy_required",
                    {
                        "required_evidence": ["lifecycle", "replacement"],
                        "overlay_candidate_dp_ids": ["L3.product.lifecycle"],
                    },
                ),
            ]
        },
    )

    report = audit.build_report(closure_matrix_path=closure_path)

    assert report["summary"]["acquisition_task_count"] == 7
    assert report["summary"]["unknown_acquisition_task_count"] == 7
    assert report["summary"]["event_doc_search_task_count"] == 2
    assert report["summary"]["local_formula_source_task_count"] == 2
    assert report["summary"]["external_business_source_task_count"] == 3
    assert report["summary"]["tasks_with_existing_candidate_evidence_count"] == 3
    assert report["summary"]["tasks_with_runtime_overlay_hints_count"] == 1
    assert report["summary"]["web_or_external_acquisition_required_count"] == 6
    assert report["summary"]["llm_allowed_count"] == 7
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["ready_for_auto_known_count"] == 0
    assert report["summary"]["ready_for_approval_count"] == 0
    assert report["summary"]["task_contract_valid_count"] == 7
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["source_mutation_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L0.compete.new_entrant"]["acquisition_track"] == (
        "dockcase_market_doc_deep_search"
    )
    assert by_dp["L0.cost.rent"]["acquisition_track"] == (
        "local_structured_formula_source"
    )
    assert by_dp["L0.demand.replacement"]["acquisition_track"] == (
        "external_or_text_business_metric"
    )
    assert by_dp["L0.price.product_asp"]["current_candidate_signal_count"] == 2
    assert by_dp["L0.demand.replacement"]["runtime_overlay_hint_count"] == 1
    assert by_dp["L0.price.product_asp"]["ready_for_auto_known"] is False
    assert by_dp["L0.price.product_asp"]["production_write_allowed"] is False
    assert "Acquisition tasks: `7`" in audit.render_markdown(report)


def test_unknown_acquisition_backlog_rejects_writable_task() -> None:
    task = {
        "task_id": "x",
        "dp_id": "L0.cost.rent",
        "data_status": "Known",
        "acquisition_track": "local_structured_formula_source",
        "required_source_types": ["source"],
        "acceptable_evidence": ["evidence"],
        "rejected_evidence": ["bad"],
        "next_local_action": "local",
        "next_external_action": "external",
        "ready_for_auto_known": True,
        "ready_for_approval": False,
        "runtime_write_allowed": False,
        "production_write_allowed": True,
        "source_mutation_allowed": False,
    }

    errors = audit._validation_errors(task)

    assert "acquisition tasks must keep data_status Unknown" in errors
    assert "ready_for_auto_known must be false" in errors
    assert "production_write_allowed must be false" in errors
