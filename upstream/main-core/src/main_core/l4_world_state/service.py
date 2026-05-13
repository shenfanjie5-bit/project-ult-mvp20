"""Service entrypoint for deriving L4 world-state snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from main_core.common.contexts import WorldStateInputs
from main_core.common.errors import MainCoreError
from main_core.common.protocols import GraphEnginePort, WorldStatePolicy
from main_core.common.schemas import FeatureSignalBundle, WorldStateSnapshot
from main_core.l4_world_state.graph_adapter import load_graph_regime_context, with_graph_impact
from main_core.l4_world_state.reasoner_port import (
    StaticWorldStateReasonerPort,
    WorldStateReasonerError,
    WorldStateReasonerPort,
)
from main_core.l4_world_state.rules import DefaultWorldStatePolicy


def derive_world_state(  # noqa: PLR0913
    bundle: FeatureSignalBundle,
    policy: WorldStatePolicy | None = None,
    reasoner_port: WorldStateReasonerPort | None = None,
    *,
    macro_context: Mapping[str, Any] | None = None,
    graph_engine_port: GraphEnginePort | None = None,
    graph_impact: Mapping[str, Any] | None = None,
) -> WorldStateSnapshot:
    """Derive a formal shared world-state snapshot from an L3 feature bundle."""

    active_policy = policy or DefaultWorldStatePolicy()
    active_reasoner_port = reasoner_port or StaticWorldStateReasonerPort()
    graph_impact_payload = dict(graph_impact or {})
    graph_regime_context = load_graph_regime_context(
        bundle.cycle_id,
        graph_engine_port,
    )
    if graph_regime_context:
        graph_impact_payload = {**graph_impact_payload, **graph_regime_context}

    inputs = with_graph_impact(
        WorldStateInputs(
            cycle_id=bundle.cycle_id,
            feature_bundle=bundle,
            macro_context=dict(macro_context or {}),
            graph_impact={},
        ),
        graph_impact_payload,
    )

    baseline_regime = active_policy.baseline(inputs)
    try:
        decision = active_reasoner_port.propose_delta(inputs, baseline_regime)
    except MainCoreError:
        raise
    except Exception as exc:
        raise WorldStateReasonerError("world-state reasoner failed") from exc

    llm_delta = active_policy.bound_delta(decision.raw_delta)
    final_regime = active_policy.compose(baseline_regime, llm_delta)

    return WorldStateSnapshot(
        cycle_id=bundle.cycle_id,
        baseline_regime=baseline_regime,
        llm_delta=llm_delta,
        final_regime=final_regime,
        llm_rationale=decision.rationale,
        actual_model_used=decision.actual_model_used,
        actual_provider=decision.actual_provider,
        fallback_path=decision.fallback_path,
    )


__all__ = ["derive_world_state"]
