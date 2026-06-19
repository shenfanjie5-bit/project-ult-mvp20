import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_acquisition as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_overlay(root: Path) -> Path:
    path = root / "TEST" / "000001.SZ.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "ts_code: 000001.SZ",
                "industry_id: TEST",
                "nodes:",
                "- node_id: 000001.SZ:L0.demand.frequency",
                "  dp_id: L0.demand.frequency",
                "  status: Unknown",
                "- node_id: 000001.SZ:L4.volume.frequency",
                "  dp_id: L4.volume.frequency",
                "  status: Known",
                "  confidence: 0.70",
                "  value:",
                "    metric_name: usage cadence",
                "    unit: times",
                "  evidence_sources:",
                "    - kind: fixture",
                "- node_id: 000001.SZ:L0.demand.penetration",
                "  dp_id: L0.demand.penetration",
                "  status: Unknown",
                "- node_id: 000001.SZ:L1.position.market_share",
                "  dp_id: L1.position.market_share",
                "  status: Known",
                "  confidence: 0.80",
                "  value:",
                "    metric_name: market share",
                "    unit: percent",
                "  evidence_sources:",
                "    - kind: fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _task(dp_id: str) -> dict:
    return {
        "task_id": f"task-{dp_id}",
        "dp_id": dp_id,
        "score_target": "fundamental_score",
        "acquisition_track": "external_or_text_business_metric",
        "source_priority": "source",
        "source_dependencies": ["L5.is.revenue"],
    }


def _source_review(dp_id: str, false_positive_count: int) -> dict:
    return {
        "dp_id": dp_id,
        "source_review_packet_status": "external_source_required",
        "candidate_columns": [],
        "missing_formula_inputs": ["missing direct source"],
        "excluded_false_positive_count": false_positive_count,
        "direct_known_ready": False,
        "formula_inputs_ready": False,
    }


def test_external_business_metric_acquisition_packages_blockers(
    tmp_path: Path,
) -> None:
    backlog_path = tmp_path / "backlog.json"
    source_review_path = tmp_path / "source_review.json"
    single_path = tmp_path / "single.json"
    local_options_path = tmp_path / "local_options.json"
    stock_overlay_root = _write_overlay(tmp_path / "stock_overlays")
    _write_json(
        backlog_path,
        {
            "rows": [
                _task("L0.demand.frequency"),
                _task("L0.demand.penetration"),
                _task("L0.demand.replacement"),
            ]
        },
    )
    _write_json(
        source_review_path,
        {
            "rows": [
                _source_review("L0.demand.frequency", 96),
                _source_review("L0.demand.penetration", 142),
            ]
        },
    )
    _write_json(
        local_options_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.frequency",
                    "runtime_dependency_ready": True,
                    "runtime_dependency_summary": [{"dp_id": "L5.is.revenue"}],
                },
                {
                    "dp_id": "L0.demand.penetration",
                    "runtime_dependency_ready": True,
                    "runtime_dependency_summary": [{"dp_id": "L5.is.revenue"}],
                },
            ]
        },
    )
    _write_json(
        single_path,
        {
            "rows": [
                {
                    "dp_id": "L0.demand.replacement",
                    "runtime_dependency_ready": True,
                    "runtime_dependency_summary": [{"dp_id": "L5.is.revenue"}],
                    "direct_replacement_cycle_source_ready": False,
                    "overlay_candidate_dp_ids": [
                        "L3.product.lifecycle",
                        "L4.volume.shipments",
                    ],
                    "required_evidence": ["lifecycle"],
                    "lifecycle_source_required": True,
                    "reviewed_policy_required": True,
                }
            ]
        },
    )

    report = audit.build_report(
        backlog_path=backlog_path,
        local_structured_review_path=source_review_path,
        single_dependency_options_path=single_path,
        local_structured_options_path=local_options_path,
        stock_overlay_root=stock_overlay_root,
    )

    assert report["summary"]["external_business_metric_task_count"] == 3
    assert report["summary"]["runtime_dependency_ready_count"] == 3
    assert report["summary"]["runtime_overlay_hint_count"] == 2
    assert report["summary"]["business_metric_group_count"] == 12
    assert report["summary"]["business_metric_group_ready_count"] == 0
    assert report["summary"]["rows_with_supporting_runtime_context_count"] == 3
    assert report["summary"]["rows_with_overlay_business_context_candidate_count"] == 2
    assert report["summary"]["overlay_business_context_known_node_count"] == 2
    assert report["summary"]["overlay_frequency_context_known_node_count"] == 1
    assert report["summary"]["overlay_penetration_context_known_node_count"] == 1
    assert report["summary"]["overlay_frequency_direct_known_node_count"] == 0
    assert report["summary"]["overlay_penetration_direct_known_node_count"] == 0
    assert report["summary"]["overlay_frequency_direct_unknown_node_count"] == 1
    assert report["summary"]["overlay_penetration_direct_unknown_node_count"] == 1
    assert report["summary"]["rows_with_direct_business_metric_source_count"] == 0
    assert report["summary"]["rows_requiring_external_or_text_source_count"] == 3
    assert report["summary"]["excluded_false_positive_count"] == 238
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["ready_for_known_draft_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    assert report["summary"]["packet_contract_valid_count"] == 3

    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.demand.frequency"]["metric_candidate_status"] == (
        "cadence_source_required"
    )
    assert rows["L0.demand.penetration"]["metric_candidate_status"] == (
        "market_denominator_required"
    )
    assert rows["L0.demand.replacement"]["metric_candidate_status"] == (
        "lifecycle_replacement_cycle_required"
    )
    assert rows["L0.demand.replacement"]["runtime_overlay_hint_count"] == 2
    assert rows["L0.demand.frequency"]["overlay_business_context_candidate_available"]
    assert rows["L0.demand.penetration"]["overlay_business_context_candidate_available"]
    assert not rows["L0.demand.replacement"][
        "overlay_business_context_candidate_available"
    ]
    assert "External business metric tasks: `3`" in audit.render_markdown(report)
    assert "Rows with overlay business context candidates: `2`" in audit.render_markdown(
        report
    )


def test_current_external_business_metric_acquisition_report_matches_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_acquisition_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["external_business_metric_task_count"] == 3
    assert report["summary"]["runtime_dependency_ready_count"] == 3
    assert report["summary"]["rows_with_overlay_business_context_candidate_count"] > 0
    assert report["summary"]["overlay_business_context_known_node_count"] > 0
    assert report["summary"]["rows_with_direct_business_metric_source_count"] == 0
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["ready_for_known_draft_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
