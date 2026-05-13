"""Tests for the industry causal graph schema and validators."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from mvp20.graph import (
    VALID_DEDUP_GROUPS,
    VALID_STATE_NAMES,
    VALID_VIEW_IDS,
    validate_industry_graph,
    validate_industry_graph_set,
    validate_walkthrough,
)
from mvp20.manifest import validate_industry_set


ROOT = Path(__file__).resolve().parents[1]
INDUSTRIES_PATH = ROOT / "config" / "mvp20.industries.yaml"
REAL_GRAPHS_DIR = ROOT / "config" / "industry_graphs"


# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------


def _minimal_priors() -> dict:
    return {
        "boundary": {
            "scope_segments": ["A", "B"],
            "core_judgment": "synthetic",
        },
        "prediction_target": {
            "equation": "r_i_h = market_beta_i × r_market_h + sector_beta_i × r_sector_h + alpha_i_h",
            "notes": "synthetic",
        },
        "state_probabilities": [
            {"name": "强多头", "probability": 0.20},
            {"name": "温和多头", "probability": 0.30},
            {"name": "结构分化", "probability": 0.25},
            {"name": "杀估值", "probability": 0.15},
            {"name": "等待验证", "probability": 0.10},
        ],
        "shock_model": {
            "formula": "Shock_eff = ...",
            "fields": [{"name": "consensus_expectation", "description": "x"}],
        },
        "path_dedup_groups": ["需求组", "价格组", "风险组"],
        "exposure": {
            "factors": ["AI 收入占比"],
            "formula": "Exposure = ...",
            "scoring": {"5": "直接受益", "1": "间接"},
        },
        "financial_vector": {
            "fields": ["Revenue", "GrossMargin", "EPS"],
            "notes": {"Revenue": "synthetic"},
        },
        "valuation_mix": {
            "weights": {
                "PE": 0.35,
                "PS": 0.20,
                "EV_EBITDA": 0.20,
                "DCF": 0.10,
                "SOTP": 0.15,
            },
            "note": "v3.1.1",
        },
        "tail_risk": {
            "risk_factors": ["客户集中"],
            "formula_note": "synthetic",
        },
        "validation_signals": ["Capex 指引"],
        "falsification": {
            "bullish_triggers": ["订单超预期"],
            "bearish_triggers": ["毛利率下滑"],
        },
        "tradability_panel": [
            {"name": "mu", "formula": "...", "interpretation": "..."},
        ],
        "workflow_steps": [
            "1. 识别事件",
            "2. 计算 Surprise",
        ],
        "one_line_summary": "synthetic",
    }


def _minimal_views() -> dict:
    return {
        "causal_propagation": {"description": "事件 → 股价"},
        "core_factor": {"description": "重要变量"},
        "supply_chain": {"description": "上下游"},
        "risk": {"description": "下跌路径"},
    }


def _minimal_graph(industry_id: str = "AI_COMPUTE") -> dict:
    return {
        "schema_version": 1,
        "template_version": "v3.1.1",
        "industry_id": industry_id,
        "industry_name_cn": "测试行业",
        "graph_status": "present",
        "priors": _minimal_priors(),
        "nodes": [
            {
                "id": "EVENT.synthetic_demand",
                "layer": "event",
                "type": "demand_event",
                "label_cn": "测试事件",
                "industry_tags": [industry_id],
            },
            {
                "id": "FIN.synthetic_revenue",
                "layer": "financial",
                "type": "financial_vector",
                "label_cn": "测试收入",
                "industry_tags": [industry_id],
            },
        ],
        "edges": [
            {
                "id": "EDGE.SYN.001",
                "source": "EVENT.synthetic_demand",
                "target": "FIN.synthetic_revenue",
                "relation": "drives_revenue",
                "polarity": "positive",
                "beta_positive": 0.85,
                "beta_negative": 0.70,
                "threshold": "synthetic",
                "lag": "1-2 quarters",
                "dedup_group": "需求组",
                "views": ["causal_propagation", "core_factor"],
            }
        ],
        "views": _minimal_views(),
    }


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Vocabulary sanity
# ---------------------------------------------------------------------------


def test_vocabularies_have_expected_sizes() -> None:
    # 8 core groups + 8 extension groups industries actually use.
    assert len(VALID_DEDUP_GROUPS) == 16
    assert {"需求组", "风险组", "叙事组", "供给组"} <= VALID_DEDUP_GROUPS
    assert len(VALID_STATE_NAMES) == 5
    assert VALID_VIEW_IDS == {
        "causal_propagation",
        "core_factor",
        "supply_chain",
        "risk",
    }


# ---------------------------------------------------------------------------
# Single-graph validation: positive synthetic baseline
# ---------------------------------------------------------------------------


def test_synthetic_minimal_graph_validates(tmp_path: Path) -> None:
    payload = _minimal_graph()
    path = _write_yaml(tmp_path / "AI_COMPUTE.yaml", payload)

    result = validate_industry_graph(path)

    assert result.ok, result.errors
    assert result.industry_id == "AI_COMPUTE"
    assert result.graph_status == "present"
    assert result.node_count == 2
    assert result.edge_count == 1
    assert set(result.view_keys) == VALID_VIEW_IDS


# ---------------------------------------------------------------------------
# Negative cases — priors
# ---------------------------------------------------------------------------


def test_state_probabilities_must_sum_to_one(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["priors"]["state_probabilities"][0]["probability"] = 0.10
    # Now total = 0.90
    path = _write_yaml(tmp_path / "bad_states.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("state_probabilities probabilities must sum to 1.0" in e for e in result.errors)


def test_unknown_state_name_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["priors"]["state_probabilities"][0]["name"] = "未知状态"
    path = _write_yaml(tmp_path / "bad_state_name.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("name unknown" in e for e in result.errors)


def test_valuation_weights_must_sum_to_one(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["priors"]["valuation_mix"]["weights"]["EV_EBITDA"] = 0.50  # over
    path = _write_yaml(tmp_path / "bad_weights.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("valuation_mix.weights must sum to 1.0" in e for e in result.errors)


def test_unknown_dedup_group_in_priors_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["priors"]["path_dedup_groups"].append("未定义组")
    path = _write_yaml(tmp_path / "bad_group.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("path_dedup_groups" in e and "unknown" in e for e in result.errors)


def test_priors_missing_required_section_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    del payload["priors"]["one_line_summary"]
    path = _write_yaml(tmp_path / "missing_summary.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("priors.one_line_summary is required" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Negative cases — nodes
# ---------------------------------------------------------------------------


def test_node_id_prefix_required(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["nodes"][0]["id"] = "BAD.synthetic"  # BAD is not in NODE_ID_PREFIXES
    payload["edges"][0]["source"] = "BAD.synthetic"
    path = _write_yaml(tmp_path / "bad_prefix.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("prefix" in e for e in result.errors)


def test_node_layer_must_be_known(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["nodes"][0]["layer"] = "unknown_layer"
    path = _write_yaml(tmp_path / "bad_layer.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("layer must be one of" in e for e in result.errors)


def test_node_industry_tags_must_be_non_empty(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["nodes"][0]["industry_tags"] = []
    path = _write_yaml(tmp_path / "bad_tags.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("industry_tags" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Negative cases — edges
# ---------------------------------------------------------------------------


def test_edge_views_must_be_non_empty(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["edges"][0]["views"] = []
    path = _write_yaml(tmp_path / "bad_views.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("views must be a non-empty list" in e for e in result.errors)


def test_edge_unknown_view_id_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["edges"][0]["views"] = ["unknown_view"]
    path = _write_yaml(tmp_path / "bad_view_id.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("unknown id 'unknown_view'" in e for e in result.errors)


def test_edge_unknown_dedup_group_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["edges"][0]["dedup_group"] = "未知组"
    path = _write_yaml(tmp_path / "bad_dedup.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("dedup_group" in e for e in result.errors)


def test_edge_polarity_must_be_known(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["edges"][0]["polarity"] = "weird"
    path = _write_yaml(tmp_path / "bad_polarity.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("polarity" in e for e in result.errors)


def test_edge_beta_out_of_range_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["edges"][0]["beta_positive"] = 2.5
    path = _write_yaml(tmp_path / "bad_beta.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("beta_positive" in e and "[0, 2]" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Negative cases — views
# ---------------------------------------------------------------------------


def test_missing_required_view_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    del payload["views"]["risk"]
    path = _write_yaml(tmp_path / "missing_view.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("missing required keys" in e and "risk" in e for e in result.errors)


def test_extra_view_rejected(tmp_path: Path) -> None:
    payload = _minimal_graph()
    payload["views"]["fancy_view"] = {"description": "extra"}
    path = _write_yaml(tmp_path / "extra_view.yaml", payload)

    result = validate_industry_graph(path)

    assert not result.ok
    assert any("unknown keys" in e and "fancy_view" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Set-level validation: cross-graph consistency
# ---------------------------------------------------------------------------


def _industry_graph_status_present(*ids: str) -> dict[str, str]:
    return {industry_id: "present" for industry_id in ids}


def test_cross_graph_node_label_mismatch_rejected(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    payload_a = _minimal_graph("AI_COMPUTE")
    shared_node_a = {
        "id": "COMPANY.NVDA",
        "layer": "stock",
        "type": "company",
        "label_cn": "英伟达",
        "industry_tags": ["AI_COMPUTE"],
    }
    payload_a["nodes"].append(shared_node_a)
    payload_a["edges"][0]["target"] = "COMPANY.NVDA"

    payload_b = _minimal_graph("SEMI_EQUIPMENT")
    shared_node_b = deepcopy(shared_node_a)
    shared_node_b["label_cn"] = "NVIDIA Corp"  # mismatch on purpose
    shared_node_b["industry_tags"] = ["SEMI_EQUIPMENT"]
    payload_b["nodes"].append(shared_node_b)

    _write_yaml(graphs_dir / "AI_COMPUTE.yaml", payload_a)
    _write_yaml(graphs_dir / "SEMI_EQUIPMENT.yaml", payload_b)

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"AI_COMPUTE", "SEMI_EQUIPMENT"},
        industry_graph_status=_industry_graph_status_present(
            "AI_COMPUTE", "SEMI_EQUIPMENT"
        ),
    )

    assert not result.ok
    assert any("label_cn differs" in e for e in result.errors)


def test_cross_graph_edge_target_resolves(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    payload_a = _minimal_graph("AI_COMPUTE")
    payload_a["edges"][0]["target"] = "COMPANY.NVDA"  # not declared anywhere
    _write_yaml(graphs_dir / "AI_COMPUTE.yaml", payload_a)

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"AI_COMPUTE"},
        industry_graph_status=_industry_graph_status_present("AI_COMPUTE"),
    )

    assert not result.ok
    assert any(
        "references undeclared node 'COMPANY.NVDA'" in e for e in result.errors
    )


def test_pending_industry_rejects_non_pending_graph_file(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    payload = _minimal_graph("SPACE_ECONOMY")
    _write_yaml(graphs_dir / "SPACE_ECONOMY.yaml", payload)

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"SPACE_ECONOMY"},
        industry_graph_status={"SPACE_ECONOMY": "pending"},
    )

    assert not result.ok
    assert any("marked pending but has a non-pending graph file" in e for e in result.errors)


def test_pending_industry_stub_allowed(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    _write_yaml(
        graphs_dir / "SPACE_ECONOMY.yaml",
        {
            "schema_version": 1,
            "template_version": "industry-graph-v3.1.1-pending",
            "industry_id": "SPACE_ECONOMY",
            "industry_name_cn": "太空经济、卫星互联网",
            "graph_status": "pending",
            "priors": {"boundary": {"scope_segments": [], "core_judgment": "pending"}},
            "nodes": [],
            "edges": [],
            "views": {},
        },
    )

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"SPACE_ECONOMY"},
        industry_graph_status={"SPACE_ECONOMY": "pending"},
    )

    assert result.ok, result.errors
    assert result.industry_graph_count == 0
    assert "SPACE_ECONOMY" in result.graph_status_pending
    assert any("pending stub" in w for w in result.warnings)


def test_present_industry_without_graph_file_rejected(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"AI_COMPUTE"},
        industry_graph_status={"AI_COMPUTE": "present"},
    )

    assert not result.ok
    assert any(
        "marked present but has no graph file" in e for e in result.errors
    )


def test_pending_industry_emits_warning_only(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "industry_graphs"
    graphs_dir.mkdir()

    payload = _minimal_graph("AI_COMPUTE")
    _write_yaml(graphs_dir / "AI_COMPUTE.yaml", payload)

    result = validate_industry_graph_set(
        graphs_dir,
        valid_industry_ids={"AI_COMPUTE", "SPACE_ECONOMY"},
        industry_graph_status={
            "AI_COMPUTE": "present",
            "SPACE_ECONOMY": "pending",
        },
    )

    assert result.ok, result.errors
    assert "SPACE_ECONOMY" in result.graph_status_pending
    assert any("SPACE_ECONOMY" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Walkthrough validator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Real industry graph corpus (12 present + 1 pending) integration tests
# ---------------------------------------------------------------------------


def test_real_industry_graphs_all_validate() -> None:
    industry_validation = validate_industry_set(INDUSTRIES_PATH)
    assert industry_validation.ok, industry_validation.errors

    result = validate_industry_graph_set(
        REAL_GRAPHS_DIR,
        valid_industry_ids=set(industry_validation.industry_ids),
        industry_graph_status=industry_validation.industry_graph_status,
    )

    assert result.ok, result.errors
    assert result.industry_graph_count == 12
    assert "SPACE_ECONOMY" in result.graph_status_pending
    assert result.total_nodes > 100
    assert result.total_edges > 100
    assert result.walkthroughs_validated >= 1
    assert any("SPACE_ECONOMY" in w for w in result.warnings)


def test_real_industry_graphs_have_all_four_views_each() -> None:
    industry_validation = validate_industry_set(INDUSTRIES_PATH)
    for slug in industry_validation.industry_ids:
        if industry_validation.industry_graph_status[slug] == "pending":
            continue
        path = REAL_GRAPHS_DIR / f"{slug}.yaml"
        per_graph = validate_industry_graph(path)
        assert per_graph.ok, (slug, per_graph.errors)
        assert set(per_graph.view_keys) == VALID_VIEW_IDS, slug


def test_walkthrough_rejects_undeclared_node_id(tmp_path: Path) -> None:
    fixture = {
        "fixture_id": "TEST_FIXTURE",
        "given_event": {
            "node_id": "EVENT.unknown",
            "industry_id": "AI_COMPUTE",
            "surprise": 0.5,
            "data_quality": "high",
        },
        "target": {"node_id": "COMPANY.NVDA"},
        "horizon": "1-2 quarters",
        "propagation_paths": {
            "positive": [
                {
                    "id": "PATH.POS.001",
                    "sequence": ["EVENT.unknown", "COMPANY.NVDA"],
                    "edges_used": [],
                    "aggregate_strength": 0.5,
                }
            ],
            "negative": [
                {
                    "id": "PATH.NEG.001",
                    "sequence": ["EVENT.unknown", "COMPANY.NVDA"],
                    "edges_used": [],
                    "aggregate_strength": 0.2,
                }
            ],
        },
        "verdict": {
            "positive_strength": 0.5,
            "negative_strength": 0.2,
            "net": 0.3,
            "net_direction": "positive",
            "rationale": "synthetic",
        },
    }
    path = _write_yaml(tmp_path / "fix.yaml", fixture)

    result = validate_walkthrough(
        path,
        declared_node_ids={"COMPANY.NVDA"},
        declared_edge_ids=set(),
    )

    assert not result.ok
    assert any("EVENT.unknown" in e for e in result.errors)
