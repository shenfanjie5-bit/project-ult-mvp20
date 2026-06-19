import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_value_policy_draft as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_penetration_value_policy_draft_proposes_but_does_not_select(
    tmp_path: Path,
) -> None:
    source_confirmation_path = tmp_path / "source.json"
    value_review_path = tmp_path / "value_review.json"
    _write_json(
        source_confirmation_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.penetration",
                    "value_review_packet_id": "p1",
                    "source_scope_confirmed": True,
                    "raw_tokens": ["40%"],
                    "market_relative_path": "news/p1.html",
                    "confirmed_scope": "domestic listed-company share",
                }
            ]
        },
    )
    _write_json(
        value_review_path,
        {
            "rows": [
                {
                    "value_review_packet_id": "p1",
                    "dp_id": "L0.demand.penetration",
                    "candidate_value_options": [
                        {
                            "raw_token": "40%",
                            "raw_percent": 40.0,
                            "formula_probe_score": 0.4,
                            "bridge_validation": {"final_score_target_ready": True},
                            "option_contract_valid": True,
                        }
                    ],
                }
            ]
        },
    )

    report = audit.build_report(
        source_confirmation_path=source_confirmation_path,
        value_review_path=value_review_path,
    )

    assert report["summary"]["draft_row_count"] == 1
    assert report["summary"]["source_scope_confirmed_count"] == 1
    assert report["summary"]["proposed_value_json_count"] == 1
    assert report["summary"]["draft_contract_valid_count"] == 1
    assert report["summary"]["bridge_final_score_ready_count"] == 1
    assert report["summary"]["selected_raw_value_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["proposed_raw_value"] == 40.0
    assert row["proposed_value_json"]["score"] == 0.4
    assert row["proposed_value_json"]["review_required"] is True
    assert row["proposed_payload"]["review_status"] == "review_required"
    assert row["proposed_payload"]["safe_to_upsert_without_review"] is False
    assert row["known_draft_sufficient"] is False
    assert "Proposed value JSONs: `1`" in audit.render_markdown(report)
