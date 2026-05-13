"""Propagation context construction from read-only regime data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from graph_engine.models import Neo4jGraphStatus, PropagationChannel, PropagationContext

_DEFAULT_ENABLED_CHANNELS: tuple[PropagationChannel, ...] = ("fundamental",)


class RegimeContextReader(Protocol):
    """Read-only boundary for world state regime context."""

    def read_regime_context(self, world_state_ref: str) -> Mapping[str, Any]:
        """Return the regime context referenced by a world state snapshot."""


def build_propagation_context(
    cycle_id: str,
    world_state_ref: str,
    graph_generation_id: int,
    *,
    regime_reader: RegimeContextReader,
    graph_status: Neo4jGraphStatus | None = None,
    enabled_channels: Sequence[PropagationChannel] | None = None,
) -> PropagationContext:
    """Build a propagation context without mutating world state."""

    if graph_status is not None and graph_status.graph_status != "ready":
        raise PermissionError(
            "propagation requires graph_status='ready'; "
            f"received {graph_status.graph_status!r}",
        )

    requested_channels = list(
        _DEFAULT_ENABLED_CHANNELS if enabled_channels is None else enabled_channels
    )
    regime_context = dict(regime_reader.read_regime_context(world_state_ref))
    return PropagationContext(
        cycle_id=cycle_id,
        world_state_ref=world_state_ref,
        graph_generation_id=graph_generation_id,
        enabled_channels=requested_channels,
        channel_multipliers={
            channel: _context_multiplier(
                regime_context,
                "channel_multipliers",
                channel,
            )
            for channel in requested_channels
        },
        regime_multipliers={
            channel: _context_multiplier(
                regime_context,
                "regime_multipliers",
                channel,
            )
            for channel in requested_channels
        },
        decay_policy=_context_mapping(regime_context, "decay_policy"),
        regime_context=regime_context,
    )


def _context_multiplier(
    regime_context: Mapping[str, Any],
    key: str,
    channel: PropagationChannel,
) -> float:
    raw_multipliers = regime_context.get(key)
    if not isinstance(raw_multipliers, Mapping):
        return 1.0
    return _as_non_negative_float(
        raw_multipliers.get(channel, 1.0),
        key,
    )


def _context_mapping(
    regime_context: Mapping[str, Any],
    key: str,
) -> dict[str, Any]:
    value = regime_context.get(key)
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _as_non_negative_float(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric multipliers") from exc

    if result < 0.0:
        raise ValueError(f"{field_name} multipliers must be non-negative")
    return result
