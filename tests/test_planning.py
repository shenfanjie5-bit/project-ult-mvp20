from pathlib import Path

from mvp20.fixture import run_fixture_e2e
from mvp20.planning import build_backfill_plan


ROOT = Path(__file__).resolve().parents[1]


def test_backfill_plan_uses_120_month_two_hop_window() -> None:
    plan = build_backfill_plan(ROOT / "config" / "mvp20.universe.yaml")

    assert plan.history_window_months == 120
    assert plan.decision_target_count == 20
    assert plan.graph_depth == 2
    assert plan.live_evidence_blocked is True
    assert plan.provider_gap_policy == (
        "provider_available_data_with_explicit_gap_evidence"
    )
    assert "graph_two_hop_context" in plan.planned_datasets


def test_fixture_e2e_keeps_recommendations_to_20_targets() -> None:
    result = run_fixture_e2e()

    assert result.ok
    assert result.decision_target_count == 20
    assert result.recommendation_count == 20
    assert result.context_entity_count > 0
    assert result.max_graph_depth == 2
