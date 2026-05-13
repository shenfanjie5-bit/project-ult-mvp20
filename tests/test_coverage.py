"""Tests for spec §23 Data Coverage + confidence propagation + N/A renorm.

Targets ``mvp20.coverage``. Each test pins one spec line:

- §23.1 N/A renormalisation drops N/A and rescales the rest.
- §23.2 Data Coverage = Σ known&applicable / Σ applicable.
- §23.2 Confidence = Base × Coverage × Evidence Quality.
- §23.2 warning bands: <30% → no_strong_conclusion, <50% → low_confidence.
- §23.3/4/5 classify_missing_state covers all 6 buckets.
- §23.5 Optionality node returns (current, option).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from mvp20.coverage import (
    EVIDENCE_QUALITY_MAP,
    LOW_CONFIDENCE_THRESHOLD,
    LOW_MATERIALITY_THRESHOLD,
    NO_STRONG_CONCLUSION_THRESHOLD,
    adjust_path_score,
    classify_missing_state,
    compute_data_coverage,
    coverage_summary_for_node,
    coverage_summary_for_overlay,
    coverage_warning_level,
    handle_optionality,
    propagate_confidence,
    renormalize_weights,
)


ROOT = Path(__file__).resolve().parents[1]
CATL_OVERLAY = ROOT / "config" / "stock_overlays" / "STORAGE_GRID" / "300750.SZ.yaml"


# ---------------------------------------------------------------------------
# Tiny fixture builders to keep each test self-contained.
# ---------------------------------------------------------------------------


def _child(dp_id: str, status: str, weight: float = 1.0, **kw: object) -> dict:
    return {
        "dp_id": dp_id,
        "node_id": f"X.{dp_id}",
        "data_status": status,
        "active_weight": weight,
        "base_weight": weight,
        **kw,
    }


# ---------------------------------------------------------------------------
# compute_data_coverage — spec §23.2 formula
# ---------------------------------------------------------------------------


def test_data_coverage_known_unknown_na() -> None:
    """1 Known + 1 Unknown + 1 N/A → coverage = 1/(1+1) = 0.5 (N/A dropped)."""

    children = [
        _child("a", "Known", weight=1.0),
        _child("b", "Unknown", weight=1.0),
        _child("c", "N/A", weight=1.0),
    ]
    assert compute_data_coverage(children) == pytest.approx(0.5)


def test_data_coverage_inactive_counts_as_known() -> None:
    """Inactive nodes are explicitly known per spec §23.3 (no event != no data)."""

    children = [
        _child("a", "Known", weight=2.0),
        _child("b", "Inactive", weight=1.0),
        _child("c", "Unknown", weight=1.0),
    ]
    # known = 2 + 1 = 3, applicable = 2 + 1 + 1 = 4
    assert compute_data_coverage(children) == pytest.approx(0.75)


def test_data_coverage_all_unknown_is_zero() -> None:
    children = [_child("a", "Unknown"), _child("b", "Unknown")]
    assert compute_data_coverage(children) == pytest.approx(0.0)


def test_data_coverage_all_na_returns_zero() -> None:
    children = [_child("a", "N/A"), _child("b", "N/A")]
    assert compute_data_coverage(children) == pytest.approx(0.0)


def test_data_coverage_empty_returns_zero() -> None:
    assert compute_data_coverage([]) == pytest.approx(0.0)


def test_data_coverage_uses_active_weight_not_base() -> None:
    """spec §23.3 sets active_weight=0 for Inactive — we should follow that
    so the parent rollup doesn't double-count idle nodes."""

    children = [
        _child("a", "Known", weight=1.0),  # active=1
        # Inactive with active_weight=0 → should contribute 0 to BOTH
        # numerator and denominator.
        {
            "dp_id": "b",
            "node_id": "X.b",
            "data_status": "Inactive",
            "active_weight": 0.0,
            "base_weight": 1.0,
        },
    ]
    assert compute_data_coverage(children) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# renormalize_weights — spec §23.1 (rescale siblings after dropping N/A)
# ---------------------------------------------------------------------------


def test_renormalize_drops_na_and_rescales_rest() -> None:
    """4 children, one N/A → remaining 3 should sum to 1.0."""

    children = [
        _child("a", "Known", weight=1.0),
        _child("b", "Unknown", weight=1.0),
        _child("c", "Inactive", weight=1.0),
        _child("d", "N/A", weight=1.0),
    ]
    out = renormalize_weights(children)
    assert "d" not in out
    assert set(out) == {"a", "b", "c"}
    assert math.isclose(sum(out.values()), 1.0, abs_tol=1e-9)
    for w in out.values():
        assert w == pytest.approx(1 / 3)


def test_renormalize_preserves_relative_weight_ratios() -> None:
    """spec example: 国内 70%, 海外 30%. Remove 海外 → 国内 = 100%."""

    children = [
        _child("domestic", "Known", weight=0.7),
        _child("overseas", "N/A", weight=0.3),
    ]
    out = renormalize_weights(children)
    assert out == {"domestic": pytest.approx(1.0)}


def test_renormalize_all_na_returns_empty() -> None:
    children = [_child("a", "N/A"), _child("b", "N/A")]
    assert renormalize_weights(children) == {}


def test_renormalize_handles_unbalanced_weights() -> None:
    children = [
        _child("big", "Known", weight=3.0),
        _child("small", "Unknown", weight=1.0),
        _child("dropped", "N/A", weight=5.0),
    ]
    out = renormalize_weights(children)
    assert out["big"] == pytest.approx(0.75)
    assert out["small"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# propagate_confidence — spec §23.2 confidence formula
# ---------------------------------------------------------------------------


def test_propagate_confidence_categorical_evidence() -> None:
    """Base × Coverage × Evidence Quality with the three categorical levels."""

    assert propagate_confidence(1.0, 1.0, "low") == pytest.approx(0.5)
    assert propagate_confidence(1.0, 1.0, "medium") == pytest.approx(0.75)
    assert propagate_confidence(1.0, 1.0, "high") == pytest.approx(1.0)


def test_propagate_confidence_full_formula() -> None:
    """0.8 × 0.5 × 0.75 (medium) = 0.30."""

    c = propagate_confidence(0.8, 0.5, "medium")
    assert c == pytest.approx(0.8 * 0.5 * EVIDENCE_QUALITY_MAP["medium"])


def test_propagate_confidence_clamps_inputs() -> None:
    """Coverage > 1 or < 0 should not blow up — clamp to [0, 1]."""

    assert propagate_confidence(2.0, 1.5, "high") == pytest.approx(1.0)
    assert propagate_confidence(-1.0, 0.5, "high") == pytest.approx(0.0)


def test_propagate_confidence_accepts_numeric_evidence() -> None:
    """Allow callers to pre-resolve evidence quality to a float."""

    assert propagate_confidence(1.0, 1.0, 0.9) == pytest.approx(0.9)


def test_propagate_confidence_unknown_evidence_defaults_to_medium() -> None:
    assert propagate_confidence(1.0, 1.0, "bogus-level") == pytest.approx(
        EVIDENCE_QUALITY_MAP["medium"]
    )


# ---------------------------------------------------------------------------
# adjust_path_score
# ---------------------------------------------------------------------------


def test_adjust_path_score_multiplies_by_confidence() -> None:
    assert adjust_path_score(10.0, 0.5) == pytest.approx(5.0)
    assert adjust_path_score(-3.0, 0.8) == pytest.approx(-2.4)
    assert adjust_path_score(10.0, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# coverage_warning_level — spec §23.2 thresholds
# ---------------------------------------------------------------------------


def test_warning_level_thresholds() -> None:
    assert coverage_warning_level(0.0) == "no_strong_conclusion"
    assert coverage_warning_level(0.29) == "no_strong_conclusion"
    assert coverage_warning_level(NO_STRONG_CONCLUSION_THRESHOLD) == "low_confidence"
    assert coverage_warning_level(0.49) == "low_confidence"
    assert coverage_warning_level(LOW_CONFIDENCE_THRESHOLD) == "ok"
    assert coverage_warning_level(1.0) == "ok"


# ---------------------------------------------------------------------------
# classify_missing_state — spec §23.{1..5}
# ---------------------------------------------------------------------------


def test_classify_all_five_states() -> None:
    assert classify_missing_state({"data_status": "Known", "materiality": 0.8}) == "Known"
    assert classify_missing_state({"data_status": "N/A"}) == "NA"
    assert classify_missing_state({"data_status": "Unknown"}) == "Unknown"
    assert classify_missing_state({"data_status": "Inactive"}) == "Inactive"
    assert classify_missing_state({"data_status": "Optionality"}) == "Optionality"


def test_classify_low_materiality_demotes_known() -> None:
    """spec §23.4 — tiny known node should fold into 'Low Materiality'."""

    node = {"data_status": "Known", "materiality": LOW_MATERIALITY_THRESHOLD - 0.01}
    assert classify_missing_state(node) == "LowMateriality"


def test_classify_explicit_low_materiality() -> None:
    assert classify_missing_state({"data_status": "Low Materiality"}) == "LowMateriality"


def test_classify_falls_back_to_missing_policy() -> None:
    node = {"missing_policy": "not_applicable_remove"}
    assert classify_missing_state(node) == "NA"
    node = {"missing_policy": "inactive_zero_weight"}
    assert classify_missing_state(node) == "Inactive"
    node = {"missing_policy": "optionality_track"}
    assert classify_missing_state(node) == "Optionality"


def test_classify_unknown_default() -> None:
    assert classify_missing_state({}) == "Unknown"


# ---------------------------------------------------------------------------
# handle_optionality — spec §23.5
# ---------------------------------------------------------------------------


def test_handle_optionality_returns_current_and_option() -> None:
    """current = current_revenue_share, option = market × prob × time × eq."""

    node = {
        "data_status": "Optionality",
        "value": {
            "current_revenue_share": 0.05,
            "market_space": 100.0,
            "success_prob": 0.3,
            "time_factor": 0.5,
            "evidence_quality": "medium",
        },
    }
    current, option = handle_optionality(node)
    assert current == pytest.approx(0.05)
    assert option == pytest.approx(100.0 * 0.3 * 0.5 * EVIDENCE_QUALITY_MAP["medium"])


def test_handle_optionality_empty_value_returns_zeros() -> None:
    """An author-stubbed Optionality node (no numbers yet) must not crash."""

    node = {"data_status": "Optionality", "value": {}}
    assert handle_optionality(node) == (0.0, 0.0)


def test_handle_optionality_falls_back_to_current_contribution() -> None:
    node = {
        "data_status": "Optionality",
        "value": {"current_contribution": 0.12},
    }
    current, _ = handle_optionality(node)
    assert current == pytest.approx(0.12)


def test_handle_optionality_node_level_evidence_quality() -> None:
    """Evidence quality may be set on the node itself rather than in value."""

    node = {
        "data_status": "Optionality",
        "evidence_quality": "high",
        "value": {"market_space": 10.0, "success_prob": 0.5, "time_factor": 1.0},
    }
    _, option = handle_optionality(node)
    assert option == pytest.approx(10.0 * 0.5 * 1.0 * EVIDENCE_QUALITY_MAP["high"])


# ---------------------------------------------------------------------------
# coverage_summary_for_node — one-shot integration helper
# ---------------------------------------------------------------------------


def test_coverage_summary_for_node_aggregates_counts_and_weights() -> None:
    parent = {"node_id": "P", "dp_id": "p"}
    # 1 Known + 2 Unknown + 1 N/A + 1 Inactive = 1+1 known / 4 applicable = 0.5,
    # but we want < 0.5 so we add an extra unknown to push warning_level off "ok".
    children = [
        _child("a", "Known", weight=1.0),
        _child("b", "Unknown", weight=1.0),
        _child("b2", "Unknown", weight=1.0),
        _child("c", "Inactive", weight=1.0),
        _child("d", "N/A", weight=1.0),
        _child("e", "Optionality", weight=1.0),
    ]
    summary = coverage_summary_for_node(parent, children)

    # Known (a) + Inactive (c) = 2/5 applicable → 0.4 → low_confidence
    assert summary["data_coverage"] == pytest.approx(0.4)
    assert summary["warning_level"] == "low_confidence"
    assert summary["n_known"] == 1
    assert summary["n_unknown"] == 2
    assert summary["n_inactive"] == 1
    assert summary["n_na"] == 1
    assert summary["n_optionality"] == 1
    assert summary["n_children"] == 6
    assert summary["n_applicable"] == 5
    # N/A excluded; the other 5 share 0.20 each
    assert set(summary["normalized_weights"]) == {"a", "b", "b2", "c", "e"}
    for w in summary["normalized_weights"].values():
        assert w == pytest.approx(0.20)


def test_coverage_summary_for_node_below_30pct_blocks_strong_conclusion() -> None:
    """spec §23.2 — Coverage < 30% should surface as no_strong_conclusion."""

    parent = {"node_id": "P"}
    # 1 known + 4 unknown → 1/5 = 0.2
    children = [_child("k", "Known")] + [_child(f"u{i}", "Unknown") for i in range(4)]
    summary = coverage_summary_for_node(parent, children)
    assert summary["data_coverage"] == pytest.approx(0.2)
    assert summary["warning_level"] == "no_strong_conclusion"


# ---------------------------------------------------------------------------
# coverage_summary_for_overlay — CATL smoke test
# ---------------------------------------------------------------------------


def test_coverage_summary_for_overlay_runs_on_catl() -> None:
    """Smoke test on the real CATL overlay shipped with the repo."""

    payload = yaml.safe_load(CATL_OVERLAY.read_text(encoding="utf-8"))
    report = coverage_summary_for_overlay(payload)

    assert report["ts_code"] == "300750.SZ"
    assert report["industry_id"] == "STORAGE_GRID"
    assert report["overall"]["n_parents"] >= 1

    # CATL overlay still has Unknown nodes — overall coverage must be in
    # [0, 1) since not all required data points are Known yet. We avoid
    # pinning to an exact value so the test remains stable as the live
    # overlay is enriched (Unknown -> Known) over time.
    overall_coverage = report["overall"]["data_coverage"]
    assert 0.0 <= overall_coverage < 1.0

    # Round-trip: overall totals must reflect that there is at least one
    # Known datum and at least one Unknown one. If either side were zero,
    # the coverage value above would be degenerate (0.0 or 1.0).
    totals = report["overall"]["totals"]
    assert totals["n_known"] >= 1
    assert totals["n_unknown"] >= 1
    assert report["overall"]["warning_level"] in {
        "ok",
        "low_confidence",
        "no_strong_conclusion",
    }

    # Per-node entries should each have a coverage in [0, 1].
    for n in report["per_node"]:
        assert 0.0 <= n["data_coverage"] <= 1.0
        assert n["warning_level"] in {"ok", "low_confidence", "no_strong_conclusion"}


def test_coverage_summary_for_overlay_synthetic() -> None:
    """Build a tiny overlay payload and verify alert routing."""

    overlay = {
        "ts_code": "MOCK.SZ",
        "industry_id": "MOCK",
        "nodes": [
            {"node_id": "P", "dp_id": "p", "parent_node": None,
             "child_nodes": ["A", "B", "C", "D"]},
            {"node_id": "A", "dp_id": "a", "parent_node": "P",
             "data_status": "Known", "active_weight": 1.0, "base_weight": 1.0,
             "materiality": 0.5},
            {"node_id": "B", "dp_id": "b", "parent_node": "P",
             "data_status": "Unknown", "active_weight": 1.0, "base_weight": 1.0,
             "materiality": 0.5},
            {"node_id": "C", "dp_id": "c", "parent_node": "P",
             "data_status": "Unknown", "active_weight": 1.0, "base_weight": 1.0,
             "materiality": 0.5},
            {"node_id": "D", "dp_id": "d", "parent_node": "P",
             "data_status": "N/A", "active_weight": 1.0, "base_weight": 1.0,
             "materiality": 0.5},
        ],
    }
    report = coverage_summary_for_overlay(overlay)
    assert report["overall"]["n_parents"] == 1
    parent = report["per_node"][0]
    # 1 known / (1 known + 2 unknown) = 1/3 → low_confidence (< 0.5, >= 0.3)
    assert parent["data_coverage"] == pytest.approx(1 / 3)
    assert parent["warning_level"] == "low_confidence"
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["warning_level"] == "low_confidence"


def test_coverage_summary_overall_weighted_by_applicable_count() -> None:
    """Two parents, one with high coverage one with low, weighted by child count."""

    overlay = {
        "ts_code": "MOCK.SZ",
        "industry_id": "MOCK",
        "nodes": [
            {"node_id": "P1", "parent_node": None, "child_nodes": ["A1"]},
            {"node_id": "A1", "parent_node": "P1", "data_status": "Known",
             "active_weight": 1.0, "base_weight": 1.0},
            {"node_id": "P2", "parent_node": None,
             "child_nodes": ["A2", "B2", "C2"]},
            {"node_id": "A2", "parent_node": "P2", "data_status": "Known",
             "active_weight": 1.0, "base_weight": 1.0},
            {"node_id": "B2", "parent_node": "P2", "data_status": "Unknown",
             "active_weight": 1.0, "base_weight": 1.0},
            {"node_id": "C2", "parent_node": "P2", "data_status": "Unknown",
             "active_weight": 1.0, "base_weight": 1.0},
        ],
    }
    report = coverage_summary_for_overlay(overlay)
    # P1 cov = 1.0 (weight 1), P2 cov = 1/3 (weight 3) → (1*1 + 3*(1/3))/4 = 0.5
    assert report["overall"]["data_coverage"] == pytest.approx(0.5)
