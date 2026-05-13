from pathlib import Path

from mvp20.fixture import run_fixture_e2e
from mvp20.manifest import INDUSTRY_COUNT
from mvp20.planning import build_backfill_plan


ROOT = Path(__file__).resolve().parents[1]


def test_backfill_plan_uses_120_month_two_hop_window() -> None:
    plan = build_backfill_plan(ROOT / "config" / "mvp20.universe.yaml")

    assert plan.history_window_months == 120
    assert plan.industry_count == INDUSTRY_COUNT
    assert plan.constituent_count >= INDUSTRY_COUNT
    assert plan.graph_depth == 2
    assert plan.live_evidence_blocked is True
    assert plan.provider_gap_policy == (
        "provider_available_data_with_explicit_gap_evidence"
    )
    assert "graph_two_hop_context" in plan.planned_datasets


def test_backfill_plan_auto_loads_provider_catalog() -> None:
    """When config/data_providers.yaml sits next to the manifest, the plan
    surfaces the active provider list and per-market coverage."""

    plan = build_backfill_plan(ROOT / "config" / "mvp20.universe.yaml")

    assert "fmp" in plan.data_sources, plan.data_sources
    assert "tushare" in plan.data_sources
    # The leader pool spans A / HK / US — every market should be covered.
    for market in ("A", "HK", "US"):
        assert plan.market_coverage.get(market), (market, plan.market_coverage)
    # FMP must own US.
    assert "fmp" in plan.market_coverage["US"]


def test_backfill_plan_explicit_providers_path(tmp_path: Path) -> None:
    """Caller can override the providers path."""

    plan = build_backfill_plan(
        ROOT / "config" / "mvp20.universe.yaml",
        providers_path=ROOT / "config" / "data_providers.yaml",
    )
    assert plan.data_sources, plan.data_sources


def test_fixture_e2e_covers_every_industry() -> None:
    result = run_fixture_e2e()

    assert result.ok
    assert result.industry_count == INDUSTRY_COUNT
    assert result.constituent_count >= INDUSTRY_COUNT
    assert result.recommendation_count == result.constituent_count
    assert result.context_entity_count > 0
    assert result.max_graph_depth == 2
