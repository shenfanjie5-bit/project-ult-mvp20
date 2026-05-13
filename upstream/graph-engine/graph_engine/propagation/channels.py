"""Shared propagation channel classification helpers."""

from __future__ import annotations

from graph_engine.schema.definitions import RelationshipType

PROPAGATION_CHANNELS: dict[RelationshipType, tuple[str, ...]] = {
    RelationshipType.SUPPLY_CHAIN: ("fundamental",),
    RelationshipType.OWNERSHIP: ("fundamental",),
    RelationshipType.INDUSTRY_CHAIN: ("fundamental",),
    RelationshipType.SECTOR_MEMBERSHIP: ("fundamental",),
    RelationshipType.EVENT_IMPACT: ("event",),
    RelationshipType.CO_HOLDING: ("reflexive",),
    RelationshipType.NORTHBOUND_HOLD: ("event", "reflexive"),
}
PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE: dict[str, tuple[str, ...]] = {
    relationship_type.value: channels
    for relationship_type, channels in PROPAGATION_CHANNELS.items()
}
DEFAULT_CHANNEL_BY_RELATIONSHIP_TYPE: dict[str, str] = {
    relationship_type: channels[0]
    for relationship_type, channels in PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE.items()
}


def relationship_types_for_channel(channel: str) -> tuple[str, ...]:
    """Return relationship type values that default into a propagation channel."""

    return tuple(
        relationship_type
        for relationship_type, channels in PROPAGATION_CHANNELS_BY_RELATIONSHIP_TYPE.items()
        if channel in channels
    )


def effective_channel_expression(relationship_variable: str = "relationship") -> str:
    """Return the Cypher expression used to classify propagation relationships."""

    return (
        f"coalesce({relationship_variable}.propagation_channel, "
        f"{relationship_variable}.channel, "
        f"{relationship_variable}.impact_channel, "
        f"{_default_channel_case_expression(relationship_variable)})"
    )


def effective_channel_selector(
    channel: str,
    relationship_variable: str = "relationship",
) -> str:
    """Return the Cypher predicate for one propagation channel."""

    default_relationship_types = relationship_types_for_channel(channel)
    if default_relationship_types:
        default_relationship_type_selector = (
            f"type({relationship_variable}) IN "
            f"{_cypher_string_list(default_relationship_types)}"
        )
    else:
        default_relationship_type_selector = "false"
    explicit_channel_absent_selector = " AND ".join(
        f"{relationship_variable}.{property_name} IS NULL"
        for property_name in ("propagation_channel", "channel", "impact_channel")
    )
    return (
        f'({effective_channel_expression(relationship_variable)} = "{channel}" '
        f"OR ({explicit_channel_absent_selector} "
        f"AND {default_relationship_type_selector}))"
    )


def _cypher_string_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _default_channel_case_expression(relationship_variable: str) -> str:
    case_parts = [
        f'WHEN "{relationship_type}" THEN "{channel}"'
        for relationship_type, channel in DEFAULT_CHANNEL_BY_RELATIONSHIP_TYPE.items()
    ]
    return f"CASE type({relationship_variable}) {' '.join(case_parts)} ELSE null END"
