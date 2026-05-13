"""Tests for mvp20.aggregator: parent aggregation + three-horizon scoring.

Covers spec §27 (父节点公式) and §29 (短/中/长线权重) plus §23 missing-state
handling (Inactive / N/A / Unknown / Optionality).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from mvp20.aggregator import (
    _classify_horizon,
    _recency,
    _to_scalar,
    aggregate_company_graph,
)


ROOT = Path(__file__).resolve().parents[1]
STORAGE_GRID_STOCK = (
    ROOT / "config" / "stock_overlays" / "STORAGE_GRID" / "300750.SZ.yaml"
)
STORAGE_GRID_INDUSTRY = (
    ROOT / "config" / "industry_overlays" / "STORAGE_GRID.yaml"
)


# ---------------------------------------------------------------------------
# Synthetic fixture: 3-level tree, 5 nodes
# ---------------------------------------------------------------------------


def _build_synthetic_overlay() -> dict:
    """Tree:

        root
        ├── parentA  (own parent_node = root)
        │   ├── leaf1  Known positive yoy=50
        │   └── leaf2  Known negative magnitude=moderate
        └── parentB  (own parent_node = root)
            └── leaf3  Known positive magnitude=strong
    """

    def node(node_id, parent, children=None, **kw):
        defaults = {
            "node_id": node_id,
            "dp_id": kw.get("dp_id", node_id),
            "node_name": kw.get("node_name", node_id),
            "parent_node": parent,
            "child_nodes": children or [],
            "direction": kw.get("direction", "positive"),
            "base_weight": kw.get("base_weight", 1.0),
            "active_weight": kw.get("active_weight", 1.0),
            "materiality": kw.get("materiality", 1.0),
            "confidence": kw.get("confidence", 0.8),
            "data_status": kw.get("data_status", "Known"),
            "status": kw.get("status", "Known"),
            "value": kw.get("value"),
            "last_updated": kw.get("last_updated"),
        }
        return defaults

    return {
        "ts_code": "TEST.SZ",
        "nodes": [
            node("root", None, ["parentA", "parentB"], direction="neutral"),
            node("parentA", "root", ["leaf1", "leaf2"]),
            node("parentB", "root", ["leaf3"]),
            # leaf1: strong positive
            node("leaf1", "parentA", value={"yoy_pct": 50.0}),
            # leaf2: moderate negative
            node("leaf2", "parentA",
                 direction="negative",
                 value={"magnitude": "moderate"}),
            # leaf3: strong positive
            node("leaf3", "parentB", value={"magnitude": "strong"}),
        ],
    }


# ---------------------------------------------------------------------------
# 1. Basic parent-aggregation arithmetic
# ---------------------------------------------------------------------------


def test_parent_score_equals_weighted_child_sum() -> None:
    """spec §27: Parent = Σ Child Direction × Strength × Weight × Confidence."""

    overlay = _build_synthetic_overlay()
    result = aggregate_company_graph(overlay)

    # leaf1 magnitude = tanh(50/50) ≈ 0.7616
    leaf1_mag = math.tanh(1.0)
    # leaf2 magnitude = 0.5 (moderate), direction negative
    leaf2_mag = 0.5
    # Each carries confidence=0.8, recency=1 (no last_updated), weight=1.

    # parentA aggregates leaf1 + leaf2 with weights renormalized to 0.5 each
    expected_parentA = (
        (+1.0 * leaf1_mag * 1.0) * 0.5 * 0.8 +  # leaf1
        (-1.0 * leaf2_mag * 1.0) * 0.5 * 0.8     # leaf2
    )
    assert result["parentA"]["score"] == pytest.approx(expected_parentA, rel=1e-6)
    assert result["parentA"]["n_children_active"] == 2
    assert result["parentA"]["n_children_inactive"] == 0
    assert result["parentA"]["n_children_unknown"] == 0
    assert result["parentA"]["data_coverage"] == pytest.approx(1.0)


def test_leaf_score_carries_direction_sign() -> None:
    overlay = _build_synthetic_overlay()
    result = aggregate_company_graph(overlay)
    assert result["leaf1"]["score"] > 0
    assert result["leaf2"]["score"] < 0
    assert result["leaf3"]["score"] > 0


# ---------------------------------------------------------------------------
# 2. N/A renormalization
# ---------------------------------------------------------------------------


def test_na_child_drops_out_and_siblings_renormalize() -> None:
    """spec §23.1: N/A children are removed; surviving siblings re-share weight."""

    overlay = _build_synthetic_overlay()
    # Make leaf2 N/A — parentA's score should then be exactly leaf1 alone.
    for n in overlay["nodes"]:
        if n["node_id"] == "leaf2":
            n["data_status"] = "N/A"

    result = aggregate_company_graph(overlay)

    leaf1_mag = math.tanh(1.0)
    # parentA now has only leaf1, weight=1.0/1.0=1.0, confidence=0.8
    expected = (+1.0 * leaf1_mag * 1.0) * 1.0 * 0.8
    assert result["parentA"]["score"] == pytest.approx(expected, rel=1e-6)
    assert result["parentA"]["n_children_na"] == 1
    assert result["parentA"]["n_children_active"] == 1


# ---------------------------------------------------------------------------
# 3. Inactive contributes 0 and isn't in denominator
# ---------------------------------------------------------------------------


def test_inactive_child_does_not_contribute() -> None:
    """spec §23.3: Inactive children carry active_weight=0 → no contribution."""

    overlay = _build_synthetic_overlay()
    for n in overlay["nodes"]:
        if n["node_id"] == "leaf2":
            n["data_status"] = "Inactive"
            n["active_weight"] = 0.0

    result = aggregate_company_graph(overlay)

    leaf1_mag = math.tanh(1.0)
    # parentA aggregates only leaf1
    expected = (+1.0 * leaf1_mag * 1.0) * 1.0 * 0.8
    assert result["parentA"]["score"] == pytest.approx(expected, rel=1e-6)
    assert result["parentA"]["n_children_inactive"] == 1
    assert result["parentA"]["n_children_active"] == 1


# ---------------------------------------------------------------------------
# 4. Unknown lowers data_coverage
# ---------------------------------------------------------------------------


def test_unknown_child_reduces_data_coverage() -> None:
    """spec §23.2: Unknown is applicable but missing data — counts in
    denominator of data_coverage but not the numerator."""

    overlay = _build_synthetic_overlay()
    for n in overlay["nodes"]:
        if n["node_id"] == "leaf2":
            n["data_status"] = "Unknown"
            n["value"] = None

    result = aggregate_company_graph(overlay)

    # data_coverage = known_weight / total_weight = 1.0 / 2.0 = 0.5
    assert result["parentA"]["data_coverage"] == pytest.approx(0.5)
    assert result["parentA"]["n_children_unknown"] == 1


# ---------------------------------------------------------------------------
# 5. Three-horizon mix weights
# ---------------------------------------------------------------------------


def test_classify_horizon_short_keywords() -> None:
    s, m, l = _classify_horizon("L7.flow.active_inflow", "主力净流入")
    assert (s, m, l) == (0.5, 0.3, 0.2)


def test_classify_horizon_medium_keywords() -> None:
    s, m, l = _classify_horizon("L3.delivery.lead_time", "交付周期")
    assert m > s and m > l
    assert pytest.approx(s + m + l, abs=1e-6) == 1.0


def test_classify_horizon_long_keywords() -> None:
    s, m, l = _classify_horizon("L2.newbiz.tam", "新业务潜在空间")
    assert (s, m, l) == (0.1, 0.3, 0.6)


def test_classify_horizon_default() -> None:
    s, m, l = _classify_horizon("X.unknown.something", "completely off-topic")
    assert pytest.approx(s + m + l, abs=1e-2) == 1.0
    assert max(s, m, l) - min(s, m, l) < 0.05  # roughly even


def test_three_horizon_mix_on_synthetic_tree() -> None:
    """short/medium/long aggregates should respect dp_id classification.

    leaf1 = L1.newbiz.tam → long-heavy (0.1/0.3/0.6).
    leaf2 = same dp_id family, negative.
    """

    overlay = _build_synthetic_overlay()
    # Re-tag leaf1 / leaf2 as long-horizon ids
    for n in overlay["nodes"]:
        if n["node_id"] == "leaf1":
            n["dp_id"] = "L2.newbiz.tam"
            n["node_name"] = "新业务潜在空间"
        if n["node_id"] == "leaf2":
            n["dp_id"] = "L1.position.stickiness"
            n["node_name"] = "客户粘性"

    result = aggregate_company_graph(overlay)
    pa = result["parentA"]
    # All children are long-classified → long_score | > medium | > short
    assert abs(pa["long_score"]) >= abs(pa["medium_score"])
    assert abs(pa["medium_score"]) >= abs(pa["short_score"])


# ---------------------------------------------------------------------------
# 6. Optionality split: future_option_value goes into long only
# ---------------------------------------------------------------------------


def test_optionality_future_value_long_horizon_only() -> None:
    overlay = _build_synthetic_overlay()
    for n in overlay["nodes"]:
        if n["node_id"] == "leaf3":
            n["data_status"] = "Optionality"
            n["dp_id"] = "L2.newbiz.tam"
            n["node_name"] = "新业务潜在空间"
            n["value"] = {
                "current_contribution": 0.1,
                "future_option_value": 0.7,
            }

    result = aggregate_company_graph(overlay)
    leaf3 = result["leaf3"]
    # Long-horizon should pick up future_option_value (≈0.7 * recency=1)
    # in addition to the standard direction × magnitude × long_weight piece.
    assert leaf3["long_score"] > leaf3["medium_score"]
    assert leaf3["long_score"] > leaf3["short_score"]


# ---------------------------------------------------------------------------
# 7. _to_scalar helper behaviour
# ---------------------------------------------------------------------------


def test_to_scalar_yoy() -> None:
    assert _to_scalar({"yoy_pct": 50.0}) == pytest.approx(math.tanh(1.0), rel=1e-6)


def test_to_scalar_magnitude() -> None:
    assert _to_scalar({"magnitude": "strong"}) == 0.8
    assert _to_scalar({"magnitude": "moderate"}) == 0.5
    assert _to_scalar({"magnitude": "weak"}) == 0.3


def test_to_scalar_score() -> None:
    assert _to_scalar({"score": 0.42}) == pytest.approx(0.42)
    # clipped to [0,1]
    assert _to_scalar({"score": 2.5}) == 1.0


def test_to_scalar_returns_zero_on_none() -> None:
    assert _to_scalar(None) == 0.0
    assert _to_scalar({}) == 0.0
    assert _to_scalar({"unrelated": "blob"}) == 0.0


# ---------------------------------------------------------------------------
# 8. Recency
# ---------------------------------------------------------------------------


def test_recency_no_timestamp_returns_one() -> None:
    assert _recency(None) == 1.0
    assert _recency("") == 1.0


def test_recency_decays_over_time() -> None:
    from datetime import datetime, timezone

    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    # 90d old → 0.5
    assert _recency(
        "2026-02-11T00:00:00+00:00", ref_now=now, halflife_days=90.0
    ) == pytest.approx(0.5, rel=1e-2)


# ---------------------------------------------------------------------------
# 9. End-to-end on real CATL overlay
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not STORAGE_GRID_STOCK.exists(), reason="CATL fixture missing"
)
def test_aggregate_real_catl_overlay() -> None:
    stock = yaml.safe_load(STORAGE_GRID_STOCK.read_text(encoding="utf-8"))
    industry = None
    if STORAGE_GRID_INDUSTRY.exists():
        industry = yaml.safe_load(
            STORAGE_GRID_INDUSTRY.read_text(encoding="utf-8")
        )
    out = aggregate_company_graph(stock, industry)

    # Sanity:
    assert len(out) > 0
    # The root company node must be present and have a numeric score.
    root_id = "300750.SZ:company"
    assert root_id in out
    assert isinstance(out[root_id]["score"], (int, float))
    # Three-horizon scores all populated.
    assert "short_score" in out[root_id]
    assert "medium_score" in out[root_id]
    assert "long_score" in out[root_id]
    # data_coverage in [0, 1].
    assert 0.0 <= out[root_id]["data_coverage"] <= 1.0


# ---------------------------------------------------------------------------
# 10. Disconnected nodes still get scored individually
# ---------------------------------------------------------------------------


def test_disconnected_node_still_in_output() -> None:
    overlay = {
        "ts_code": "TEST.SZ",
        "nodes": [
            {
                "node_id": "lonely",
                "dp_id": "L3.product.lifecycle",
                "node_name": "产品",
                "parent_node": None,
                "child_nodes": [],
                "direction": "positive",
                "base_weight": 1.0,
                "active_weight": 1.0,
                "materiality": 1.0,
                "confidence": 0.7,
                "data_status": "Known",
                "value": {"magnitude": "strong"},
            }
        ],
    }
    out = aggregate_company_graph(overlay)
    assert "lonely" in out
    assert out["lonely"]["score"] > 0
