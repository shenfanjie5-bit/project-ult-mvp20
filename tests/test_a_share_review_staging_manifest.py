import json
from pathlib import Path

from scripts import audit_a_share_review_staging_manifest as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload(
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict,
) -> dict:
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
        "production_write_allowed": False,
    }


def _staging_row(dp_id: str, score_target: str, status: str, payload: dict | None = None) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "payload_status": status,
        "production_write_allowed": False,
        "staging_payload": payload
        or _payload(dp_id, score_target, "Unknown", {"review_required": True}),
        "staging_bridge_validation": (
            {"final_score_target_ready": True}
            if status.startswith("deterministic_")
            else {}
        ),
    }


def _contract_row(dp_id: str, status: str) -> dict:
    return {
        "dp_id": dp_id,
        "payload_status": status,
        "contract_valid": True,
        "bridge_validation": {"final_score_target_ready": True},
    }


def _draft_row(
    dp_id: str,
    score_target: str,
    data_status: str,
    value_json: dict,
    source_dependencies: list[str] | None = None,
) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_dependencies": source_dependencies or [],
        "draft_status": (
            "draft_known_review_required"
            if data_status in {"Known", "NotApplicable"}
            else "unknown_policy_required"
        ),
        "draft_payload": _payload(dp_id, score_target, data_status, value_json),
        "contract_validation": {"contract_valid": True, "validation_errors": []},
        "bridge_validation": (
            {"final_score_target_ready": True}
            if data_status in {"Known", "NotApplicable"}
            else {}
        ),
        "production_write_allowed": False,
    }


def _empty_report() -> dict:
    return {"rows": [], "summary": {}}


def test_review_staging_manifest_merges_concrete_and_unknown_packets(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    value_contracts_path = tmp_path / "contracts.json"
    event_text_path = tmp_path / "event.json"
    local_structured_path = tmp_path / "local.json"
    local_structured_text_path = tmp_path / "text.json"
    single_dependency_path = tmp_path / "single.json"
    manual_policy_path = tmp_path / "manual.json"

    _write_json(
        staging_path,
        {
            "rows": [
                _staging_row(
                    "L9.media.short_report",
                    "expectation_gap",
                    "deterministic_neutral_review_payload",
                    _payload(
                        "L9.media.short_report",
                        "expectation_gap",
                        "Known",
                        {"score": 0.0, "event_state": "none_observed"},
                    ),
                ),
                _staging_row(
                    "L7.trade.gamma",
                    "gamma_multiplier",
                    "deterministic_not_applicable_review_payload",
                    _payload(
                        "L7.trade.gamma",
                        "gamma_multiplier",
                        "NotApplicable",
                        {
                            "multiplier": 1.0,
                            "applicability": "a_share_single_stock_no_listed_option",
                        },
                    ),
                ),
                _staging_row("L0.cost.cac", "fundamental_score", "requires_generator_output"),
                _staging_row("L0.compete.price_war", "fundamental_score", "requires_generator_output"),
                _staging_row("L0.demand.user_count", "fundamental_score", "requires_generator_output"),
                _staging_row("L0.price.pricing_power", "fundamental_score", "requires_generator_output"),
                _staging_row("L6.mult.dcf", "valuation_rerating", "requires_generator_output"),
            ]
        },
    )
    _write_json(
        value_contracts_path,
        {
            "rows": [
                _contract_row("L9.media.short_report", "deterministic_neutral_review_payload"),
                _contract_row("L7.trade.gamma", "deterministic_not_applicable_review_payload"),
            ]
        },
    )
    _write_json(
        event_text_path,
        {
            "rows": [
                _draft_row(
                    "L0.compete.price_war",
                    "fundamental_score",
                    "Unknown",
                    {
                        "review_required": True,
                        "blocked_reason": "event_text_requires_price_war_classification",
                        "required_policy": "price-war classification",
                    },
                )
            ]
        },
    )
    _write_json(
        local_structured_path,
        {
            "rows": [
                _draft_row(
                    "L0.cost.cac",
                    "fundamental_score",
                    "Known",
                    {"score": 0.1, "drivers": ["L5.is.sga_rd"]},
                )
            ]
        },
    )
    _write_json(
        local_structured_text_path,
        {
            "rows": [
                _draft_row(
                    "L0.demand.user_count",
                    "fundamental_score",
                    "Unknown",
                    {
                        "review_required": True,
                        "blocked_reason": "qa_recent_requires_customer_user_extraction",
                        "required_policy": "customer extraction",
                    },
                )
            ]
        },
    )
    _write_json(
        single_dependency_path,
        {
            "rows": [
                _draft_row(
                    "L0.price.pricing_power",
                    "fundamental_score",
                    "Known",
                    {"score": 0.2, "drivers": ["L5.is.gross_margin"]},
                )
            ]
        },
    )
    _write_json(
        manual_policy_path,
        {
            "rows": [
                _draft_row(
                    "L6.mult.dcf",
                    "valuation_rerating",
                    "Unknown",
                    {
                        "review_required": True,
                        "blocked_reason": "dcf_assumptions_require_review",
                        "required_assumptions": ["discount_rate"],
                    },
                )
            ]
        },
    )

    report = audit.build_report(
        staging_path=staging_path,
        value_contracts_path=value_contracts_path,
        event_text_path=event_text_path,
        local_structured_path=local_structured_path,
        local_structured_text_path=local_structured_text_path,
        single_dependency_path=single_dependency_path,
        manual_policy_path=manual_policy_path,
    )

    assert report["summary"]["candidate_blocking_rows"] == 7
    assert report["summary"]["review_manifest_entries"] == 7
    assert report["summary"]["missing_review_entry_count"] == 0
    assert report["summary"]["review_ready_concrete_count"] == 4
    assert report["summary"]["review_gated_unknown_count"] == 3
    assert report["summary"]["known_payload_count"] == 3
    assert report["summary"]["not_applicable_payload_count"] == 1
    assert report["summary"]["unknown_payload_count"] == 3
    assert report["summary"]["contract_valid_count"] == 7
    assert report["summary"]["contract_invalid_count"] == 0
    assert report["summary"]["bridge_ready_concrete_count"] == 4
    assert report["summary"]["safe_to_upsert_without_review_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["approved_runtime_write_count"] == 0
    assert report["summary"]["source_kind_counts"] == {
        "deterministic_candidate_staging": 2,
        "event_text_policy_pilot": 1,
        "local_single_dependency_policy_pilot": 1,
        "local_structured_policy_pilot": 1,
        "local_structured_text_policy_pilot": 1,
        "manual_policy_pilot": 1,
    }
    assert "Review-ready concrete entries: `4`" in audit.render_markdown(report)


def test_review_staging_manifest_flags_missing_review_entry(tmp_path: Path) -> None:
    staging_path = tmp_path / "staging.json"
    value_contracts_path = tmp_path / "contracts.json"
    event_text_path = tmp_path / "event.json"
    local_structured_path = tmp_path / "local.json"
    local_structured_text_path = tmp_path / "text.json"
    single_dependency_path = tmp_path / "single.json"
    manual_policy_path = tmp_path / "manual.json"

    _write_json(
        staging_path,
        {
            "rows": [
                _staging_row("L0.cost.cac", "fundamental_score", "requires_generator_output")
            ]
        },
    )
    for path in (
        value_contracts_path,
        event_text_path,
        local_structured_path,
        local_structured_text_path,
        single_dependency_path,
        manual_policy_path,
    ):
        _write_json(path, _empty_report())

    report = audit.build_report(
        staging_path=staging_path,
        value_contracts_path=value_contracts_path,
        event_text_path=event_text_path,
        local_structured_path=local_structured_path,
        local_structured_text_path=local_structured_text_path,
        single_dependency_path=single_dependency_path,
        manual_policy_path=manual_policy_path,
    )

    assert report["summary"]["missing_review_entry_count"] == 1
    assert report["summary"]["contract_invalid_count"] == 1
    assert report["rows"][0]["review_entry_status"] == "missing_review_entry"
