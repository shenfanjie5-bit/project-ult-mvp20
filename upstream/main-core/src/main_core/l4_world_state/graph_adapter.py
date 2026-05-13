"""Read-only graph-engine adapter for L4 world-state inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from main_core.common.contexts import WorldStateInputs
from main_core.common.protocols import GraphEnginePort, GraphSnapshotError
from main_core.common.types import CycleId


def load_graph_regime_context(
    cycle_id: CycleId,
    port: GraphEnginePort | None,
) -> dict[str, Any]:
    """Load graph regime context in the shape expected by WorldStateInputs."""

    if port is None:
        return {}

    context = port.read_graph_regime_context(cycle_id)
    if context is None:
        return {}
    if str(context.cycle_id) != str(cycle_id):
        raise GraphSnapshotError(
            "graph regime context contains records from a different cycle"
        )

    return {
        "snapshot_id": context.snapshot_id,
        "regime_context": _to_plain_json_like(context.regime_context),
    }


def with_graph_impact(
    inputs: WorldStateInputs,
    graph_impact: Mapping[str, Any],
) -> WorldStateInputs:
    """Return a validated copy of world-state inputs with graph impact attached."""

    return WorldStateInputs.model_validate(
        {
            "cycle_id": inputs.cycle_id,
            "feature_bundle": inputs.feature_bundle,
            "macro_context": dict(inputs.macro_context),
            "graph_impact": _to_plain_json_like(graph_impact) if graph_impact else {},
        }
    )


def _to_plain_json_like(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_plain_json_like(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_plain_json_like(item) for item in value]
    return value


__all__ = ["load_graph_regime_context", "with_graph_impact"]
