"""Integration coverage for L6 multi-agent consumption of enriched contexts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.l6_alpha import AgentRoleConfig, MultiAgentAnalyzer, MultiAgentRoleResult

EXPECTED_LAYER_B_SCORE = 0.75


class PayloadRecordingPort:
    def __init__(self) -> None:
        self.payloads: list[Mapping[str, Any]] = []

    def analyze_role(
        self,
        entity_id: str,
        context: AlphaAnalysisContext,
        role: AgentRoleConfig,
        payload: Mapping[str, Any],
    ) -> MultiAgentRoleResult:
        self.payloads.append(payload)
        candidate_signals = payload["signal_values"]["candidate_signals"]
        score = candidate_signals["layer_b_score"]["adjusted_value"]
        return MultiAgentRoleResult(
            role=role.name,
            score=score,
            confidence=0.9,
            rationale=f"{role.name} consumed enriched context for {entity_id}",
            evidence={"cycle_id": context.cycle_id},
        )


def test_multi_agent_payload_preserves_candidate_signals_and_graph_features() -> None:
    cycle_id = "cycle-l6-enriched"
    candidate_signals = {
        "layer_b_score": {
            "raw_value": 2.0,
            "adjusted_value": EXPECTED_LAYER_B_SCORE,
            "source": "layer_b",
            "confidence": 0.9,
            "metadata": {"source_table": "candidate_facts", "rank": 1},
        },
        "sentiment_label": {
            "raw_value": "positive",
            "adjusted_value": "positive",
            "source": "layer_b",
            "confidence": None,
            "metadata": {"language": "en"},
        },
    }
    graph_features = {
        "snapshot_id": "graph-impact-001",
        "features": {"impact_score": 0.81, "community": "growth"},
    }
    context = AlphaAnalysisContext(
        cycle_id=cycle_id,
        entity_id="ENT_ENRICHED",
        feature_bundle=FeatureSignalBundle(
            cycle_id=cycle_id,
            entity_id="ENT_ENRICHED",
            feature_values={"momentum": 4.2},
            signal_values={"candidate_signals": candidate_signals},
            graph_features=graph_features,
            feature_weight_multiplier={"momentum": 1.0},
        ),
        world_state=WorldStateSnapshot(
            cycle_id=cycle_id,
            baseline_regime="neutral",
            llm_delta=1,
            final_regime="risk_on",
            llm_rationale="fixture",
            actual_model_used="fixture",
            actual_provider="local",
            fallback_path=[],
        ),
        similar_cases=[{"entity_id": "ENT_SIM", "score": 0.44}],
    )
    port = PayloadRecordingPort()
    analyzer = MultiAgentAnalyzer(port, roles=(AgentRoleConfig("fundamental"),))

    result = analyzer.analyze("ENT_ENRICHED", context)

    assert result.analyzer_type == "multi_agent_v1"
    assert result.status == "ok"
    assert result.score == EXPECTED_LAYER_B_SCORE
    assert port.payloads[0]["signal_values"]["candidate_signals"] == candidate_signals
    assert port.payloads[0]["graph_features"] == graph_features
    assert port.payloads[0]["world_state"] == {
        "final_regime": "risk_on",
        "llm_delta": 1,
    }
    assert port.payloads[0]["similar_cases"] == [{"entity_id": "ENT_SIM", "score": 0.44}]


def test_l6_multi_agent_does_not_import_l3_graph_or_graph_engine_ports() -> None:
    l6_root = Path("src/main_core/l6_alpha")
    source = "\n".join(path.read_text(encoding="utf-8") for path in l6_root.glob("*.py"))

    assert "main_core.l3_features.graph_adapter" not in source
    assert "graph_engine" not in source
