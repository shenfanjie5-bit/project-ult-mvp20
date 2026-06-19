import json
from pathlib import Path

from scripts.audit_a_share_option_universe_na_verification import (
    build_report,
    render_markdown,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_option_universe_na_verification_keeps_ashare_options_gated(
    tmp_path: Path,
) -> None:
    remediation_path = tmp_path / "remediation.json"
    closure_path = tmp_path / "closure.json"
    collector_path = tmp_path / "collector.py"
    futu_source_path = tmp_path / "futu_source.py"

    option_rows = [
        ("L6.priced.iv", "volatility_risk"),
        ("L7.trade.iv", "volatility_risk"),
        ("L7.trade.options_cp", "options_momentum_multiplier"),
    ]
    _write_json(
        remediation_path,
        {
            "rows": [
                {
                    "dp_id": dp_id,
                    "score_target": score_target,
                    "remediation_class": "missing_or_not_applicable_source",
                    "conversion_path_status": "no_current_numeric_input",
                    "source_data_state": "not_applicable_or_unlicensed",
                    "route": "missing_listed_option_universe",
                    "intent_subtype": "a_share_listed_options_or_na_required",
                }
                for dp_id, score_target in option_rows
            ]
        },
    )
    _write_json(
        closure_path,
        {
            "rows": [
                {
                    "dp_id": dp_id,
                    "closure_status": "no_valid_a_share_target_data",
                    "runtime_valid_real_ts_count": 0,
                    "runtime_numeric_signal_ts_count": 0,
                    "effective_score_path_ts_count": 0,
                    "sample_values": [],
                    "runtime_source_categories": {},
                }
                for dp_id, _score_target in option_rows
            ]
        },
    )

    collector_path.write_text(
        "# Options-related dp_ids are intentionally excluded from this collector.\n",
        encoding="utf-8",
    )
    hk_us_filter = (
        'target = [c for c in constituents if (c.get("ts_code") or "").'
        'endswith((".HK", ".US"))]'
    )
    futu_source_path.write_text(
        "\n".join(
            [
                "L6.priced.iv",
                "L7.trade.iv",
                "L7.trade.options_cp",
                hk_us_filter,
                hk_us_filter,
                hk_us_filter,
            ]
        ),
        encoding="utf-8",
    )

    report = build_report(
        remediation_path=remediation_path,
        field_closure_path=closure_path,
        collector_path=collector_path,
        futu_source_path=futu_source_path,
    )
    summary = report["summary"]

    assert summary["option_universe_packet_count"] == 3
    assert summary["no_current_a_share_input_count"] == 3
    assert summary["listed_option_universe_required_count"] == 3
    assert summary["na_or_unavailable_allowed_after_review_count"] == 3
    assert summary["known_value_allowed_now_count"] == 0
    assert summary["verification_contract_valid_count"] == 3
    assert summary["verification_contract_invalid_count"] == 0
    assert summary["safe_to_upsert_without_review_count"] == 0
    assert summary["production_write_allowed_count"] == 0
    assert summary["code_evidence"]["futu_hk_us_filter_count"] == 3

    by_dp = {row["dp_id"]: row for row in report["rows"]}
    assert by_dp["L7.trade.options_cp"]["policy"]["forbidden_proxies"] == [
        "stock turnover",
        "stock sentiment",
        "index call/put ratio without explicit mapping",
    ]
    assert by_dp["L6.priced.iv"]["known_value_allowed_now"] is False
    assert by_dp["L7.trade.iv"]["production_write_allowed"] is False
    assert "Known value allowed now: `0`" in render_markdown(report)
