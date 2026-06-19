import json
from pathlib import Path

from scripts import audit_a_share_unknown_event_external_source_confirmation as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_external_source_confirmation_packages_review_inputs_only(
    tmp_path: Path,
) -> None:
    primary_confirmation_path = tmp_path / "primary_confirmation.json"
    _write_json(
        primary_confirmation_path,
        {
            "rows": [
                {
                    "packet_id": "L0.compete.new_entrant#strict_review_candidate#1",
                    "dp_id": "L0.compete.new_entrant",
                    "score_target": "fundamental_score",
                    "data_status": "Unknown",
                    "local_confirmation_status": "local_supporting_context_only",
                },
                {
                    "packet_id": "L0.tech.substitute_tech#strict_review_candidate#1",
                    "dp_id": "L0.tech.substitute_tech",
                    "score_target": "fundamental_score",
                    "data_status": "Unknown",
                    "local_confirmation_status": "local_supporting_context_only",
                },
            ]
        },
    )

    report = audit.build_report(primary_confirmation_path=primary_confirmation_path)

    assert report["summary"]["external_confirmation_packet_count"] == 2
    assert report["summary"]["external_source_card_count"] == 6
    assert report["summary"]["external_confirmation_candidate_count"] == 2
    assert report["summary"]["external_supporting_context_count"] == 4
    assert report["summary"]["rows_with_external_confirmation_candidate_count"] == 2
    assert report["summary"]["rows_with_external_supporting_context_only_count"] == 0
    assert report["summary"]["classifier_input_candidate_count"] == 2
    assert report["summary"]["classifier_input_candidate_contract_valid_count"] == 2
    assert report["summary"]["classifier_input_candidate_contract_invalid_count"] == 0
    assert report["summary"]["classifier_input_candidate_ready_count"] == 0
    assert report["summary"]["classifier_input_review_required_count"] == 2
    assert report["summary"]["classifier_input_primary_source_covered_count"] == 2
    assert report["summary"]["classifier_input_required_label_count"] == 12
    assert report["summary"]["classifier_input_guardrail_count"] == 6
    assert report["summary"]["classifier_review_template_count"] == 2
    assert report["summary"]["classifier_review_template_contract_valid_count"] == 2
    assert report["summary"]["classifier_review_template_contract_invalid_count"] == 0
    assert report["summary"]["classifier_review_template_blank_pending_count"] == 2
    assert report["summary"]["classifier_review_template_input_ready_count"] == 0
    assert report["summary"]["classifier_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["external_confirmation_contract_valid_count"] == 2
    assert report["summary"]["external_confirmation_contract_invalid_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["external_source_status_counts"] == {
        "external_confirmation_candidates_found": 2
    }

    for row in report["rows"]:
        assert row["data_status"] == "Unknown"
        assert row["external_confirmation_candidate_count"] == 1
        assert row["classifier_input_candidate_available"] is True
        assert row["classifier_input_candidate_contract_valid"] is True
        assert row["classifier_input_candidate_validation_errors"] == []
        assert row["classifier_input_candidate"]["classifier_input_ready"] is False
        assert row["classifier_input_candidate"]["required_labels"]
        assert row["classifier_input_candidate"]["guardrails"]
        assert row["classifier_review_template_contract_valid"] is True
        assert row["classifier_review_template_validation_errors"] == []
        assert row["classifier_review_template"]["reviewer"] == ""
        assert row["classifier_review_template"]["reviewed_at"] == ""
        assert row["classifier_review_template"]["known_draft_allowed"] is False
        assert row["classifier_review_template"]["classifier_ready_allowed"] is False
        assert row["external_supporting_context_count"] == 2
        assert row["external_confirmation_contract_valid"] is True
        assert row["known_draft_sufficient"] is False
        assert row["approval_ready"] is False
        assert row["production_write_allowed"] is False

    assert "External confirmation candidates are review inputs only." in (
        audit.render_markdown(report)
    )
    assert "Classifier input candidates: `2`" in audit.render_markdown(report)
    assert "Classifier input candidate contracts valid: `2`" in audit.render_markdown(
        report
    )
    assert "Classifier review templates: `2`" in audit.render_markdown(report)
