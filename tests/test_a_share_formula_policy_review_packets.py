import json
from pathlib import Path

from scripts.audit_a_share_formula_policy_review_packets import (
    build_report,
    render_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_formula_policy_review_packets_keep_direct_formulas_gated(tmp_path: Path) -> None:
    remediation_path = tmp_path / "remediation.json"
    closure_path = tmp_path / "closure.json"

    _write_json(
        remediation_path,
        {
            "rows": [
                {
                    "dp_id": "L5.cf.capex",
                    "score_target": "fundamental_score",
                    "remediation_class": "formula_policy_required",
                    "conversion_path_status": "not_numeric_no_formula_or_normalizer",
                    "source_data_state": "valid_real",
                    "runtime_valid_real_ts_count": 1640,
                    "runtime_numeric_signal_ts_count": 0,
                    "score_company_route_ready": True,
                    "runtime_source_categories": {"tushare": 1640},
                    "main_sources": "tushare:cashflow:1640",
                    "repair_hint": "capex needs a defined intensity/trend policy",
                },
                {
                    "dp_id": "L6.mult.pe",
                    "score_target": "valuation_rerating",
                    "remediation_class": "formula_policy_required",
                    "conversion_path_status": "not_numeric_no_formula_or_normalizer",
                    "source_data_state": "valid_real",
                    "runtime_valid_real_ts_count": 1405,
                    "runtime_numeric_signal_ts_count": 0,
                    "score_company_route_ready": True,
                    "runtime_source_categories": {"tushare": 1405},
                    "main_sources": "tushare:daily_basic:1405",
                    "replacement_dp_id": "L6.state.peer_compare",
                    "repair_hint": "trailing PE should be scored through peer context",
                },
            ]
        },
    )
    _write_json(
        closure_path,
        {
            "rows": [
                {
                    "dp_id": "L5.cf.capex",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 1640,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:cashflow",
                            "value": {"scalar": 172000000.0, "unit": "元"},
                        }
                    ],
                },
                {
                    "dp_id": "L6.mult.pe",
                    "closure_status": "valid_real_but_formula_unmapped",
                    "runtime_valid_real_ts_count": 1405,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:daily_basic",
                            "value": {"scalar": 5.1, "unit": "ratio"},
                        }
                    ],
                },
                {
                    "dp_id": "L6.state.peer_compare",
                    "closure_status": "closed_reaches_final_score",
                    "score_target": "valuation_rerating",
                    "runtime_valid_real_ts_count": 1403,
                    "effective_score_path_ts_count": 1403,
                    "sample_values": [
                        {
                            "ts_code": "000001.SZ",
                            "status": "Known",
                            "source": "tushare:daily_basic.peer_compare",
                            "value": {"premium_vs_industry_pct": -68.4},
                        }
                    ],
                },
            ]
        },
    )

    report = build_report(
        remediation_path=remediation_path,
        field_closure_path=closure_path,
    )
    summary = report["summary"]

    assert summary["formula_policy_packet_count"] == 2
    assert summary["current_input_available_count"] == 2
    assert summary["valuation_peer_context_packet_count"] == 1
    assert summary["business_semantics_packet_count"] == 1
    assert summary["replacement_path_ready_count"] == 1
    assert summary["direct_formula_ready_count"] == 0
    assert summary["known_draft_sufficient_count"] == 0
    assert summary["policy_contract_valid_count"] == 2
    assert summary["production_write_allowed_count"] == 0

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L5.cf.capex"]["policy_family"] == "capex_intensity_and_trend"
    assert by_dp["L5.cf.capex"]["direct_formula_ready"] is False
    assert by_dp["L6.mult.pe"]["policy_family"] == "valuation_peer_context"
    assert by_dp["L6.mult.pe"]["replacement_path"]["replacement_path_ready"] is True
    assert "Direct formula ready: `0`" in render_markdown(report)
