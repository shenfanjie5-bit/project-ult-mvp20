import json
from pathlib import Path

from scripts import audit_a_share_candidate_value_contracts as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload(dp_id: str, score_target: str, data_status: str, value_json: dict) -> dict:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "data_status": data_status,
        "bridge_entry_data_status": "Known" if data_status == "NotApplicable" else data_status,
        "value_json": value_json,
        "confidence": 0.6,
        "evidence_refs": ["docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"],
        "rationale": "review packet rationale",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }


def test_candidate_value_contracts_accept_valid_concrete_and_placeholder_rows(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    _write_json(
        staging_path,
        {
            "rows": [
                {
                    "dp_id": "L9.media.short_report",
                    "score_target": "expectation_gap",
                    "payload_status": "deterministic_neutral_review_payload",
                    "production_write_allowed": False,
                    "staging_payload": _payload(
                        "L9.media.short_report",
                        "expectation_gap",
                        "Known",
                        {"score": 0.0, "event_state": "none_observed"},
                    ),
                },
                {
                    "dp_id": "L7.trade.gamma",
                    "score_target": "gamma_multiplier",
                    "payload_status": "deterministic_not_applicable_review_payload",
                    "production_write_allowed": False,
                    "staging_payload": _payload(
                        "L7.trade.gamma",
                        "gamma_multiplier",
                        "NotApplicable",
                        {
                            "multiplier": 1.0,
                            "applicability": "a_share_single_stock_no_listed_option",
                        },
                    ),
                },
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "payload_status": "requires_generator_output",
                    "production_write_allowed": False,
                    "staging_payload": _payload(
                        "L0.cost.cac",
                        "fundamental_score",
                        "Unknown",
                        {"review_required": True},
                    ),
                },
            ]
        },
    )

    report = audit.build_report(staging_path)

    assert report["summary"]["candidate_rows_checked"] == 3
    assert report["summary"]["contract_valid_count"] == 3
    assert report["summary"]["contract_invalid_count"] == 0
    assert report["summary"]["concrete_payload_valid_count"] == 2
    assert report["summary"]["placeholder_payload_valid_count"] == 1
    assert report["summary"]["bridge_validated_concrete_count"] == 2
    assert report["summary"]["production_write_allowed_count"] == 0
    assert "Contract valid: `3`" in audit.render_markdown(report)


def test_candidate_value_contracts_reject_bad_bounds_and_missing_evidence(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    bad = _payload(
        "L0.cost.cac",
        "fundamental_score",
        "Known",
        {"score": 2.0},
    )
    bad["evidence_refs"] = []
    _write_json(
        staging_path,
        {
            "rows": [
                {
                    "dp_id": "L0.cost.cac",
                    "score_target": "fundamental_score",
                    "payload_status": "deterministic_neutral_review_payload",
                    "production_write_allowed": False,
                    "staging_payload": bad,
                },
                {
                    "dp_id": "L8.val.slope_risk_off",
                    "score_target": "risk_discount",
                    "payload_status": "deterministic_neutral_review_payload",
                    "production_write_allowed": False,
                    "staging_payload": _payload(
                        "L8.val.slope_risk_off",
                        "risk_discount",
                        "Known",
                        {"magnitude": True, "drivers": ["bad_bool"]},
                    ),
                },
            ]
        },
    )

    report = audit.build_report(staging_path)

    assert report["summary"]["contract_invalid_count"] == 2
    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert "evidence_refs must be a non-empty list of strings" in by_dp[
        "L0.cost.cac"
    ]["validation_errors"]
    assert "score=2.0 outside [-1.0, 1.0]" in by_dp["L0.cost.cac"][
        "validation_errors"
    ]
    assert "magnitude must be a finite number" in by_dp["L8.val.slope_risk_off"][
        "validation_errors"
    ]


def test_candidate_value_contracts_reject_incomplete_manual_known_payload(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    _write_json(
        staging_path,
        {
            "rows": [
                {
                    "dp_id": "L6.mult.dcf",
                    "score_target": "valuation_rerating",
                    "payload_status": "deterministic_neutral_review_payload",
                    "production_write_allowed": False,
                    "staging_payload": _payload(
                        "L6.mult.dcf",
                        "valuation_rerating",
                        "Known",
                        {"scalar": 0.2},
                    ),
                }
            ]
        },
    )

    report = audit.build_report(staging_path)

    assert report["summary"]["contract_invalid_count"] == 1
    errors = report["rows"][0]["validation_errors"]
    assert "assumptions must be an object" in errors
    assert "sensitivity must be an object" in errors
