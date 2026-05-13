from __future__ import annotations

import pytest

from mvp20.aggregator import aggregate_company_graph


def _node(node_id: str, parent: str | None, *, status: str = "Known", **kw):
    return {
        "node_id": node_id,
        "dp_id": kw.get("dp_id", node_id),
        "node_name": node_id,
        "parent_node": parent,
        "child_nodes": kw.get("child_nodes", []),
        "direction": kw.get("direction", "positive"),
        "base_weight": kw.get("base_weight", 1.0),
        "active_weight": kw.get("active_weight", 1.0),
        "materiality": kw.get("materiality", 1.0),
        "confidence": kw.get("confidence", 1.0),
        "data_status": status,
        "status": status,
        "value": kw.get("value", {"score": kw.get("score", 1.0)}),
        "field_role": kw.get("field_role", "score_component"),
        "score_target": kw.get("score_target", "fundamental_score"),
        "participates_in_score": kw.get("participates_in_score", True),
        "fallback_policy": kw.get("fallback_policy", "unknown_zero_score"),
        "proxy_candidates": kw.get("proxy_candidates", []),
        "neutral_value": kw.get("neutral_value", 0.0),
        "confidence_penalty": kw.get("confidence_penalty", 1.0),
        "min_required_coverage": kw.get("min_required_coverage", 0.5),
    }


def _overlay(children: list[dict], **parent_kw) -> dict:
    parent = _node("parent", None, child_nodes=[c["node_id"] for c in children], **parent_kw)
    return {"ts_code": "TEST", "nodes": [parent, *children]}


def test_na_field_is_removed_and_siblings_renormalize() -> None:
    out = aggregate_company_graph(_overlay([
        _node("known", "parent", score=1.0),
        _node("na", "parent", status="N/A", score=1.0),
    ]))

    assert out["parent"]["score"] == pytest.approx(1.0)
    assert out["parent"]["data_coverage"] == pytest.approx(1.0)
    assert out["parent"]["n_children_na"] == 1


def test_unknown_field_keeps_denominator_but_contributes_zero() -> None:
    out = aggregate_company_graph(_overlay([
        _node("known", "parent", score=1.0),
        _node("unknown", "parent", status="Unknown", value=None),
    ]))

    assert out["parent"]["score"] == pytest.approx(0.5)
    assert out["parent"]["data_coverage"] == pytest.approx(0.5)
    assert out["parent"]["n_children_unknown"] == 1


def test_unavailable_field_uses_neutral_value_and_confidence_penalty() -> None:
    out = aggregate_company_graph(_overlay([
        _node("known", "parent", score=1.0),
        _node(
            "unavailable",
            "parent",
            status="Unavailable",
            fallback_policy="proxy_then_neutral",
            neutral_value=0.0,
            confidence_penalty=0.4,
        ),
    ]))

    assert out["parent"]["score"] == pytest.approx(0.5)
    assert out["parent"]["data_coverage"] == pytest.approx(1.0)
    assert out["parent"]["missing_penalty"] == pytest.approx(0.7)
    assert out["parent"]["n_children_unavailable"] == 1
    assert out["unavailable"]["missing_balance"] == "neutral_with_penalty"


def test_unavailable_multiplier_neutral_value_is_factor_one_not_score_one() -> None:
    out = aggregate_company_graph(_overlay([
        _node(
            "theme",
            "parent",
            status="Unavailable",
            field_role="multiplier",
            score_target="theme_multiplier",
            neutral_value=1.0,
            confidence_penalty=0.6,
        ),
    ]))

    assert out["theme"]["score"] == pytest.approx(0.0)
    assert out["theme"]["data_coverage"] == pytest.approx(1.0)
    assert out["parent"]["score"] == pytest.approx(0.0)
    assert out["parent"]["missing_penalty"] == pytest.approx(0.6)


def test_unavailable_field_uses_proxy_candidate_before_neutral_value() -> None:
    out = aggregate_company_graph(_overlay([
        _node("proxy_source", "parent", dp_id="proxy.dp", score=0.8),
        _node(
            "unavailable",
            "parent",
            status="Unavailable",
            fallback_policy="proxy_then_neutral",
            proxy_candidates=["proxy.dp"],
            neutral_value=0.0,
            confidence_penalty=0.5,
            value=None,
        ),
    ]))

    assert out["unavailable"]["missing_balance"] == "proxy"
    assert out["unavailable"]["proxy_used"]["dp_id"] == "proxy.dp"
    assert out["parent"]["n_children_proxy"] == 1
    assert out["parent"]["score"] == pytest.approx(0.6)


def test_proxy_field_participates_but_lowers_confidence() -> None:
    out = aggregate_company_graph(_overlay([
        _node(
            "proxy",
            "parent",
            status="Proxy",
            score=0.8,
            fallback_policy="proxy_only",
            confidence_penalty=0.5,
        ),
    ]))

    assert out["parent"]["score"] == pytest.approx(0.4)
    assert out["parent"]["data_coverage"] == pytest.approx(1.0)
    assert out["parent"]["confidence"] == pytest.approx(0.5)
    assert out["parent"]["n_children_proxy"] == 1
    assert out["proxy"]["missing_balance"] == "proxy"


def test_low_coverage_formula_outputs_low_confidence_warning() -> None:
    out = aggregate_company_graph(_overlay([
        _node("known", "parent", score=1.0),
        _node("unknown_a", "parent", status="Unknown", value=None),
        _node("unknown_b", "parent", status="Unknown", value=None),
    ], min_required_coverage=0.8))

    assert out["parent"]["data_coverage"] == pytest.approx(1.0 / 3.0)
    assert out["parent"]["warning_level"] == "low_confidence"


def test_non_scoring_roles_do_not_affect_formula() -> None:
    out = aggregate_company_graph(_overlay([
        _node("known", "parent", score=1.0),
        _node(
            "audit",
            "parent",
            score=1.0,
            field_role="audit",
            score_target="audit_only",
            participates_in_score=False,
        ),
    ]))

    assert out["parent"]["score"] == pytest.approx(1.0)
    assert out["parent"]["data_coverage"] == pytest.approx(1.0)
    assert out["parent"]["n_children_non_scoring"] == 1
