"""Example stream-layer style consumer for interim graph impact simulation."""

from __future__ import annotations

import logging
from typing import Any

from graph_engine import (
    GraphStatusManager,
    Neo4jClient,
    ReadonlySimulationRequest,
    simulate_readonly_impact,
)

_LOGGER = logging.getLogger(__name__)


def handle_stream_event(
    event: dict[str, Any],
    *,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
) -> dict[str, Any]:
    """Return an interim impact response for an event-driven seed."""

    seed_entities = [str(seed) for seed in event.get("seed_entities", []) if seed]
    request = ReadonlySimulationRequest(
        cycle_id=str(event["cycle_id"]),
        world_state_ref=str(event["world_state_ref"]),
        graph_generation_id=int(event["graph_generation_id"]),
        depth=int(event.get("depth", 2)),
        enabled_channels=["event", "reflexive"],
        channel_multipliers={"event": 1.0, "reflexive": 1.0},
        regime_multipliers={"event": 1.0, "reflexive": 1.0},
        decay_policy={"default": 1.0},
        regime_context={"source": "stream-layer-readonly"},
        result_limit=int(event.get("result_limit", 50)),
        max_iterations=int(event.get("max_iterations", 10)),
    )
    result = simulate_readonly_impact(
        seed_entities,
        request,
        client=client,
        status_manager=status_manager,
    )
    _LOGGER.debug(
        "stream-layer interim impact computed",
        extra={
            "cycle_id": result.get("cycle_id"),
            "graph_generation_id": result.get("graph_generation_id"),
            "path_count": len(result.get("activated_paths", [])),
            "impacted_entity_count": len(result.get("impacted_entities", [])),
        },
    )
    return result
