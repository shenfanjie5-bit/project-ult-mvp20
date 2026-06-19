import json
from pathlib import Path

from scripts import audit_a_share_unknown_external_business_metric_readiness_queue as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(dp_id: str, packet_id: str, missing_fields: list[str]) -> dict:
    return {
        "packet_id": packet_id,
        "dp_id": dp_id,
        "candidate_classification": "numeric_review_candidate",
        "missing_fields": missing_fields,
        "numeric_hits": ["12%"],
        "title": "候选",
        "market_relative_path": f"news/{packet_id}.html",
        "excerpt": "候选片段",
        "metric_inputs_ready": False,
        "known_draft_sufficient": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def test_readiness_queue_prioritizes_missing_fields(tmp_path: Path) -> None:
    review_packets_path = tmp_path / "review_packets.json"
    _write_json(
        review_packets_path,
        {
            "rows": [
                _packet("L0.demand.penetration", "p0", ["bounds", "formula_policy"]),
                _packet(
                    "L0.demand.penetration",
                    "p1",
                    ["period", "unit", "bounds", "formula_policy"],
                ),
                _packet(
                    "L0.demand.replacement",
                    "p2",
                    ["denominator_or_normalizer", "bounds", "formula_policy"],
                ),
            ]
        },
    )

    report = audit.build_report(review_packets_path=review_packets_path)

    assert report["summary"]["business_metric_review_packet_count"] == 3
    assert report["summary"]["formula_policy_only_candidate_count"] == 1
    assert report["summary"]["period_or_unit_required_count"] == 1
    assert report["summary"]["denominator_required_count"] == 1
    assert report["summary"]["missing_denominator_count"] == 1
    assert report["summary"]["missing_period_count"] == 1
    assert report["summary"]["missing_unit_count"] == 1
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0

    rows = {row["packet_id"]: row for row in report["rows"]}
    assert rows["p0"]["priority"] == "P0_formula_policy_only"
    assert rows["p1"]["priority"] == "P1_period_or_unit_required"
    assert rows["p2"]["priority"] == "P2_denominator_required"
    assert "P0 formula-policy-only candidates: `1`" in audit.render_markdown(report)


def test_current_external_business_metric_readiness_queue_matches_gate() -> None:
    path = Path(
        "docs/audit/a_share_unknown_external_business_metric_readiness_queue_2026-06-19.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["summary"]["business_metric_review_packet_count"] == 99
    assert report["summary"]["formula_policy_only_candidate_count"] == 18
    assert report["summary"]["period_or_unit_required_count"] == 52
    assert report["summary"]["denominator_required_count"] == 29
    assert report["summary"]["missing_denominator_count"] == 29
    assert report["summary"]["missing_period_count"] == 63
    assert report["summary"]["missing_unit_count"] == 50
    assert report["summary"]["missing_bounds_count"] == 99
    assert report["summary"]["missing_formula_policy_count"] == 99
    assert report["summary"]["metric_inputs_ready_count"] == 0
    assert report["summary"]["known_draft_sufficient_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
