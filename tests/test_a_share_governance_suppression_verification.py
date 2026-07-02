import json
from pathlib import Path

from scripts.audit_a_share_governance_suppression_verification import (
    build_report,
    render_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_governance_suppression_verification_covers_replacements_and_data_only(
    tmp_path: Path,
) -> None:
    remediation_path = tmp_path / "remediation.json"
    closure_path = tmp_path / "closure.json"

    _write_json(
        remediation_path,
        {
            "rows": [
                {
                    "dp_id": "L6.mult.ev_ebitda",
                    "score_target": "valuation_rerating",
                    "remediation_class": "intentional_governance_or_duplicate",
                    "intent_subtype": "peer_context_suppressed",
                    "route": "intentional_peer_context_suppressed",
                    "runtime_valid_real_ts_count": 100,
                    "replacement_dp_id": "L6.state.peer_compare",
                    "repair_hint": "verify peer compare",
                },
                {
                    "dp_id": "L6.mult.peg",
                    "score_target": "valuation_rerating",
                    "remediation_class": "intentional_governance_or_duplicate",
                    "intent_subtype": "data_only_no_safe_signal",
                    "route": "intentional_data_only",
                    "runtime_valid_real_ts_count": 90,
                    "replacement_dp_id": "L6.state.peg_match",
                    "repair_hint": "raw PEG would double-count",
                },
                {
                    "dp_id": "L9.company.mgmt_litigation",
                    "score_target": "risk_discount",
                    "remediation_class": "intentional_governance_or_duplicate",
                    "intent_subtype": "duplicate_evidence",
                    "route": "intentional_alias_duplicate",
                    "runtime_valid_real_ts_count": 50,
                    "canonical_dp_id": "L8.gov.management_change",
                    "repair_hint": "legacy duplicate",
                },
                {
                    "dp_id": "L9.media.social_buzz",
                    "score_target": "expectation_gap",
                    "remediation_class": "intentional_governance_or_duplicate",
                    "intent_subtype": "duplicate_evidence",
                    "route": "intentional_fallback_duplicate",
                    "runtime_valid_real_ts_count": 10,
                    "canonical_dp_id": "L7.mood.media_social",
                    "repair_hint": "fallback duplicate",
                },
                {
                    "dp_id": "L7.mood.media_social",
                    "score_target": "sentiment_score",
                    "remediation_class": "intentional_governance_or_duplicate",
                    "intent_subtype": "derived_replacement",
                    "route": "intentional_derived_bridge_review",
                    "runtime_valid_real_ts_count": 10,
                    "replacement_dp_id": "L7.mood.fomo",
                    "repair_hint": "derived replacement",
                },
            ]
        },
    )
    _write_json(
        closure_path,
        {
            "rows": [
                {
                    "dp_id": "L6.mult.ev_ebitda",
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "value": {"scalar": 20.0},
                        }
                    ],
                },
                {
                    "dp_id": "L6.state.peer_compare",
                    "closure_status": "closed_reaches_final_score",
                    "score_target": "valuation_rerating",
                    "runtime_valid_real_ts_count": 100,
                    "effective_score_path_ts_count": 100,
                },
                {
                    "dp_id": "L6.mult.peg",
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "value": {"scalar": 1.2},
                        }
                    ],
                },
                {
                    "dp_id": "L6.state.peg_match",
                    "closure_status": "closed_reaches_final_score",
                    "score_target": "valuation_rerating",
                    "runtime_valid_real_ts_count": 90,
                    "effective_score_path_ts_count": 90,
                },
                {
                    "dp_id": "L9.company.mgmt_litigation",
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "value": {"events": [{"person": "A", "type": "高管变动"}]},
                        }
                    ],
                },
                {
                    "dp_id": "L8.gov.management_change",
                    "closure_status": "closed_reaches_final_score",
                    "score_target": "risk_discount",
                    "runtime_valid_real_ts_count": 50,
                    "effective_score_path_ts_count": 50,
                },
                {
                    "dp_id": "L9.media.social_buzz",
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "value": {"rank_overall": 5},
                        }
                    ],
                },
                {
                    "dp_id": "L7.mood.media_social",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 10,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "value": {"rank_overall": 5},
                        }
                    ],
                },
                {
                    "dp_id": "L7.mood.fomo",
                    "closure_status": "closed_reaches_final_score",
                    "score_target": "overheat_risk",
                    "runtime_valid_real_ts_count": 10,
                    "effective_score_path_ts_count": 10,
                },
            ]
        },
    )

    report = build_report(
        remediation_path=remediation_path,
        field_closure_path=closure_path,
    )
    summary = report["summary"]

    assert summary["governance_suppression_packet_count"] == 5
    assert summary["suppression_verified_count"] == 5
    assert summary["replacement_or_canonical_ready_count"] == 5
    assert summary["peer_context_suppressed_count"] == 1
    assert summary["requires_governance_review_count"] == 0
    assert summary["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L6.mult.ev_ebitda"]["verification_status"] == (
        "suppressed_with_replacement_ready"
    )
    assert by_dp["L6.mult.peg"]["verification_status"] == "data_only_suppression_verified"
    assert by_dp["L9.company.mgmt_litigation"]["verification_status"] == (
        "duplicate_with_canonical_ready"
    )
    assert by_dp["L9.media.social_buzz"]["verification_status"] == (
        "duplicate_with_transitive_replacement_ready"
    )
    assert "Suppression verified: `5`" in render_markdown(report)
