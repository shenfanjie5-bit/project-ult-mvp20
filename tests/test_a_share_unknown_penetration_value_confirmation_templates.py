import json
from pathlib import Path

from scripts import audit_a_share_unknown_penetration_value_confirmation_templates as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _template(payload_sha256: str = "a" * 64, **overrides: object) -> dict:
    template = {
        "confirmation_id": "",
        "dp_id": "L0.demand.penetration",
        "confirmation_status": "",
        "confirmation_scope": "value_policy",
        "reviewer": "",
        "confirmed_at": "",
        "payload_sha256": payload_sha256,
        "value_selection_accepted": False,
        "bounds_accepted": False,
        "formula_policy_accepted": False,
        "applicability_accepted": False,
        "risk_acknowledged": False,
        "template_status": "review_fill_required",
    }
    template.update(overrides)
    return template


def _packet(payload_sha256: str = "a" * 64, **overrides: object) -> dict:
    packet = {
        "dp_id": "L0.demand.penetration",
        "score_target": "fundamental_score",
        "value_review_packet_id": "p1",
        "payload_sha256": payload_sha256,
        "confirmation_record_template": _template(payload_sha256),
        "confirmation_record_template_contract_valid": True,
        "confirmation_packet_contract_valid": True,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }
    packet.update(overrides)
    return packet


def test_confirmation_template_bundle_extracts_blank_templates_only(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "packets.json"
    payload_hash = "b" * 64
    _write_json(packets_path, {"rows": [_packet(payload_hash)]})

    report = audit.build_report(packets_path=packets_path)

    assert report["summary"]["source_confirmation_packet_count"] == 1
    assert report["summary"]["confirmation_template_bundle_count"] == 1
    assert report["summary"]["confirmation_template_count"] == 1
    assert report["summary"]["blank_pending_template_count"] == 1
    assert report["summary"]["blank_pending_template_contract_valid_count"] == 1
    assert report["summary"]["blank_pending_template_contract_invalid_count"] == 0
    assert report["summary"]["confirmation_record_input_ready_count"] == 0
    assert report["summary"]["confirmed_template_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["inputs"]["forbidden_confirmations_file_created"] is False

    row = report["rows"][0]
    assert row["confirmation_record_template"] == _template(payload_hash)
    assert row["blank_pending_template"] is True
    assert row["confirmation_record_input_ready"] is False
    assert row["confirmed_template"] is False
    assert row["known_draft_sufficient"] is False
    assert row["approval_ready"] is False
    assert row["runtime_write_allowed"] is False
    assert row["production_write_allowed"] is False

    markdown = audit.render_markdown(report)
    assert "Blank pending templates: `1`" in markdown
    assert "Runtime writes allowed: `0`" in markdown


def test_confirmation_template_bundle_rejects_filled_template(
    tmp_path: Path,
) -> None:
    packets_path = tmp_path / "packets.json"
    payload_hash = "c" * 64
    _write_json(
        packets_path,
        {
            "rows": [
                _packet(
                    payload_hash,
                    confirmation_record_template=_template(
                        payload_hash,
                        confirmation_id="confirm-1",
                        confirmation_status="confirmed",
                        reviewer="reviewer@example.com",
                        value_selection_accepted=True,
                    ),
                )
            ]
        },
    )

    report = audit.build_report(packets_path=packets_path)

    assert report["summary"]["blank_pending_template_count"] == 0
    assert report["summary"]["blank_pending_template_contract_valid_count"] == 0
    assert report["summary"]["blank_pending_template_contract_invalid_count"] == 1
    assert report["summary"]["confirmed_template_count"] == 0
    assert report["summary"]["runtime_write_allowed_count"] == 0
    row = report["rows"][0]
    assert row["blank_pending_template"] is False
    assert "confirmation_id must be ''" in row[
        "blank_pending_template_validation_errors"
    ]
    assert "confirmation_status must be ''" in row[
        "blank_pending_template_validation_errors"
    ]
    assert "value_selection_accepted must be False" in row[
        "blank_pending_template_validation_errors"
    ]
