import json
import sqlite3
from pathlib import Path

from scripts import audit_a_share_unknown_local_formula_review_packets as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _group(name: str, status: str) -> dict:
    return {
        "name": name,
        "status": status,
        "evidence": f"{name} evidence",
        "blockers": [] if status == "ready" else [f"{name} missing"],
        "ready_for_formula": status == "ready",
    }


def _formula_row(dp_id: str, groups: list[dict], ready: bool = False) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "data_status": "Unknown",
        "source_review_packet_status": "review_candidate_ready",
        "candidate_columns": ["candidate"],
        "empty_candidate_columns": [],
        "formula_input_groups": groups,
        "formula_input_group_count": len(groups),
        "formula_input_group_ready_count": sum(
            1 for group in groups if group["ready_for_formula"]
        ),
        "formula_inputs_ready": ready,
        "formula_candidate_status": "test",
    }


def test_local_formula_review_packets_block_incomplete_formula_inputs(
    tmp_path: Path,
) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    runtime_db_path = tmp_path / "missing.sqlite"
    _write_json(
        acquisition_path,
        {
            "rows": [
                _formula_row(
                    "L0.cost.rent",
                    [
                        _group("lease_proxy_numerator", "review_candidate"),
                        _group("direct_lease_payment", "missing"),
                        _group("denominator", "missing"),
                        _group("formula_policy", "missing"),
                    ],
                ),
                _formula_row(
                    "L0.price.product_asp",
                    [
                        _group("product_revenue_numerator", "supporting_candidate"),
                        _group("product_mapping", "review_required"),
                        _group("quantity_or_price_index", "missing"),
                        _group("formula_policy", "missing"),
                    ],
                ),
            ]
        },
    )

    report = audit.build_report(
        acquisition_path=acquisition_path,
        runtime_db_path=runtime_db_path,
        price_index_context_paths=(),
    )

    assert report["summary"]["local_formula_review_packet_count"] == 2
    assert report["summary"]["rows_with_candidate_numerator_count"] == 2
    assert report["summary"]["rows_with_direct_denominator_count"] == 0
    assert report["summary"]["rows_with_denominator_candidate_count"] == 0
    assert report["summary"]["rows_with_candidate_formula_shape_count"] == 0
    assert report["summary"]["rows_with_formula_policy_draft_candidate_count"] == 0
    assert report["summary"]["formula_policy_review_template_count"] == 0
    assert report["summary"]["rows_with_price_index_context_candidate_count"] == 0
    assert report["summary"]["rows_with_candidate_price_context_shape_count"] == 0
    assert report["summary"]["price_context_review_template_count"] == 0
    assert report["summary"]["rows_with_quantity_or_price_index_count"] == 0
    assert report["summary"]["rows_with_formula_policy_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["formula_probe_available_count"] == 0
    assert report["summary"]["bridge_probe_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["local_formula_review_contract_valid_count"] == 2

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.cost.rent"]["missing_before_known"] == [
        "denominator",
        "formula_policy",
    ]
    assert rows["L0.price.product_asp"]["missing_before_known"] == [
        "quantity_or_price_index",
        "formula_policy",
    ]
    assert "Formula probes available: `0`" in audit.render_markdown(report)


def test_local_formula_review_packets_adds_runtime_denominator_candidate(
    tmp_path: Path,
) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    runtime_db_path = tmp_path / "hot.sqlite"
    _write_json(
        acquisition_path,
        {
            "rows": [
                _formula_row(
                    "L0.cost.rent",
                    [
                        _group("lease_proxy_numerator", "review_candidate"),
                        _group("direct_lease_payment", "missing"),
                        _group("denominator", "missing"),
                        _group("formula_policy", "missing"),
                    ],
                )
            ]
        },
    )
    with sqlite3.connect(runtime_db_path) as conn:
        conn.execute(
            """
            create table realtime_current (
              ts_code text,
              dp_id text,
              data_status text,
              value_json text,
              source text,
              updated_at integer
            )
            """
        )
        conn.execute(
            """
            insert into realtime_current
            values ('000001.SZ', 'L5.is.revenue', 'Known',
                    '{"scalar": 1000000, "unit": "元"}',
                    'tushare:income', 1)
            """
        )

    report = audit.build_report(
        acquisition_path=acquisition_path,
        runtime_db_path=runtime_db_path,
        price_index_context_paths=(),
    )

    assert report["summary"]["rows_with_direct_denominator_count"] == 0
    assert report["summary"]["rows_with_denominator_candidate_count"] == 1
    assert report["summary"]["rows_with_candidate_formula_shape_count"] == 1
    assert report["summary"]["rows_with_formula_policy_draft_candidate_count"] == 1
    assert report["summary"]["formula_policy_review_template_count"] == 1
    assert report["summary"]["formula_policy_review_template_contract_valid_count"] == 1
    assert report["summary"]["formula_policy_review_template_contract_invalid_count"] == 0
    assert report["summary"]["formula_policy_review_template_blank_pending_count"] == 1
    assert report["summary"]["rows_with_price_index_context_candidate_count"] == 0
    assert report["summary"]["rows_with_candidate_price_context_shape_count"] == 0
    assert report["summary"]["price_context_review_template_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["formula_probe_available_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    packet = report["rows"][0]
    assert packet["denominator_candidate_available"] is True
    assert packet["runtime_denominator_candidate"]["candidate_dp_id"] == "L5.is.revenue"
    assert packet["candidate_formula_shape"]["candidate_formula"] == (
        "use_right_asset_dep / L5.is.revenue"
    )
    assert packet["formula_policy_draft_candidate_available"] is True
    assert packet["formula_policy_draft_candidate"]["candidate_formula_ready"] is False
    assert packet["formula_policy_draft_candidate"]["review_required"] is True
    assert packet["formula_policy_review_template_contract_valid"] is True
    assert packet["formula_policy_review_template_validation_errors"] == []
    assert packet["formula_policy_review_template"]["reviewer"] == ""
    assert packet["formula_policy_review_template"]["proxy_semantics_accepted"] is False
    assert packet["formula_policy_review_template"]["formula_probe_allowed"] is False
    assert packet["missing_before_known"] == [
        "denominator_review",
        "formula_policy_review",
    ]


def test_local_formula_review_packets_adds_price_index_context_candidate(
    tmp_path: Path,
) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    runtime_db_path = tmp_path / "missing.sqlite"
    price_index_path = tmp_path / "ppi.csv"
    _write_json(
        acquisition_path,
        {
            "rows": [
                _formula_row(
                    "L0.price.product_asp",
                    [
                        _group("product_revenue_numerator", "supporting_candidate"),
                        _group("product_mapping", "review_required"),
                        _group("quantity_or_price_index", "missing"),
                        _group("formula_policy", "missing"),
                    ],
                )
            ]
        },
    )
    price_index_path.write_text(
        "month,ppi_yoy,ppi_mom,ppi_accu\n"
        "202512,-1.9,0.2,-2.6\n"
        "202511,-2.2,0.1,-2.7\n",
        encoding="utf-8",
    )

    report = audit.build_report(
        acquisition_path=acquisition_path,
        runtime_db_path=runtime_db_path,
        price_index_context_paths=(price_index_path,),
    )

    assert report["summary"]["rows_with_price_index_context_candidate_count"] == 1
    assert report["summary"]["rows_with_candidate_price_context_shape_count"] == 1
    assert report["summary"]["price_context_review_template_count"] == 1
    assert report["summary"]["price_context_review_template_contract_valid_count"] == 1
    assert report["summary"]["price_context_review_template_contract_invalid_count"] == 0
    assert report["summary"]["price_context_review_template_blank_pending_count"] == 1
    assert report["summary"]["rows_with_quantity_or_price_index_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["formula_probe_available_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    packet = report["rows"][0]
    assert packet["price_index_context_candidate_available"] is True
    assert packet["price_index_context_candidate"]["direct_formula_input"] is False
    assert packet["candidate_price_context_shape"]["direct_formula_ready"] is False
    assert packet["price_context_review_template_contract_valid"] is True
    assert packet["price_context_review_template_validation_errors"] == []
    assert packet["price_context_review_template"]["reviewer"] == ""
    assert packet["price_context_review_template"]["price_index_mapping_accepted"] is False
    assert packet["price_context_review_template"]["formula_probe_allowed"] is False
    assert packet["missing_before_known"] == [
        "quantity_or_price_index",
        "formula_policy",
    ]


def test_local_formula_review_packets_can_probe_ready_payload(
    tmp_path: Path,
) -> None:
    acquisition_path = tmp_path / "acquisition.json"
    runtime_db_path = tmp_path / "missing.sqlite"
    row = _formula_row(
        "L0.cost.rent",
        [
            _group("lease_proxy_numerator", "ready"),
            _group("direct_lease_payment", "ready"),
            _group("denominator", "ready"),
            _group("formula_policy", "ready"),
        ],
        ready=True,
    )
    row["candidate_formula_probe_payload"] = {
        "target_dp_id": "L0.cost.rent",
        "score_target": "fundamental_score",
        "data_status": "Known",
        "bridge_entry_data_status": "Known",
        "confidence": 0.4,
        "value_json": {
            "score": 0.25,
            "raw_value": 0.25,
            "unit": "ratio",
            "normalization": "test probe",
        },
        "evidence_refs": ["tmp/acquisition.json"],
        "rationale": "test probe",
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
    }
    _write_json(acquisition_path, {"rows": [row]})

    report = audit.build_report(
        acquisition_path=acquisition_path,
        runtime_db_path=runtime_db_path,
        price_index_context_paths=(),
    )

    assert report["summary"]["formula_inputs_ready_count"] == 1
    assert report["summary"]["formula_probe_available_count"] == 1
    assert report["summary"]["bridge_probe_ready_count"] == 1
    assert report["summary"]["selected_value_json_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    packet = report["rows"][0]
    assert packet["bridge_validation"]["final_score_target_ready"]
    assert packet["missing_before_known"] == []


def test_current_unknown_local_formula_review_packets_match_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["local_formula_review_packet_count"] == 2
    assert report["summary"]["rows_with_candidate_numerator_count"] == 2
    assert report["summary"]["rows_with_direct_denominator_count"] == 0
    assert report["summary"]["rows_with_denominator_candidate_count"] == 1
    assert report["summary"]["rows_with_candidate_formula_shape_count"] == 1
    assert report["summary"]["rows_with_formula_policy_draft_candidate_count"] == 1
    assert report["summary"]["formula_policy_review_template_count"] == 1
    assert report["summary"]["rows_with_price_index_context_candidate_count"] == 1
    assert report["summary"]["rows_with_candidate_price_context_shape_count"] == 1
    assert report["summary"]["price_context_review_template_count"] == 1
    assert report["summary"]["rows_with_quantity_or_price_index_count"] == 0
    assert report["summary"]["rows_with_formula_policy_count"] == 0
    assert report["summary"]["formula_inputs_ready_count"] == 0
    assert report["summary"]["formula_probe_available_count"] == 0
    assert report["summary"]["bridge_probe_ready_count"] == 0
    assert report["summary"]["selected_value_json_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["approval_ready_count"] == 0
    assert report["summary"]["local_formula_review_contract_valid_count"] == 2
    assert report["summary"]["production_write_allowed_count"] == 0
