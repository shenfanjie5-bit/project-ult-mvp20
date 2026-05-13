"""Example main-core style consumer for read-only graph impact simulation."""

from __future__ import annotations

from typing import Any

from graph_engine import (
    GraphStatusManager,
    Neo4jClient,
    ReadonlySimulationRequest,
    simulate_readonly_impact,
)


def run_main_core_interim_impact(
    seed_entities: list[str],
    *,
    client: Neo4jClient,
    status_manager: GraphStatusManager,
    cycle_id: str,
    world_state_ref: str,
    graph_generation_id: int,
) -> dict[str, Any]:
    """Read interim impact without creating a formal graph impact snapshot."""

    request = ReadonlySimulationRequest(
        cycle_id=cycle_id,
        world_state_ref=world_state_ref,
        graph_generation_id=graph_generation_id,
        depth=2,
        enabled_channels=["fundamental", "event", "reflexive"],
        channel_multipliers={
            "fundamental": 1.0,
            "event": 1.0,
            "reflexive": 1.0,
        },
        regime_multipliers={
            "fundamental": 1.0,
            "event": 1.0,
            "reflexive": 1.0,
        },
        decay_policy={"default": 1.0},
        regime_context={"source": "main-core-readonly"},
        result_limit=100,
        max_iterations=20,
    )
    return simulate_readonly_impact(
        seed_entities,
        request,
        client=client,
        status_manager=status_manager,
    )
