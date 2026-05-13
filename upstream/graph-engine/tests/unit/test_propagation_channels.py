from __future__ import annotations

from graph_engine.propagation import (
    EVENT_RELATIONSHIP_TYPES,
    PROPAGATION_CHANNELS,
    REFLEXIVE_RELATIONSHIP_TYPES,
)
from graph_engine.propagation.channels import (
    effective_channel_selector,
    relationship_types_for_channel,
)
from graph_engine.schema.definitions import RelationshipType


def test_holdings_relationship_channel_declaration_is_scoped_to_two_new_types() -> None:
    assert PROPAGATION_CHANNELS[RelationshipType.CO_HOLDING] == ("reflexive",)
    assert PROPAGATION_CHANNELS[RelationshipType.NORTHBOUND_HOLD] == (
        "event",
        "reflexive",
    )
    assert RelationshipType.NORTHBOUND_HOLD.value in EVENT_RELATIONSHIP_TYPES
    assert RelationshipType.CO_HOLDING.value in REFLEXIVE_RELATIONSHIP_TYPES
    assert RelationshipType.NORTHBOUND_HOLD.value in REFLEXIVE_RELATIONSHIP_TYPES

    assert "TOP_SHAREHOLDER" not in {
        relationship_type.value for relationship_type in PROPAGATION_CHANNELS
    }
    assert "PLEDGE_STATUS" not in {
        relationship_type.value for relationship_type in PROPAGATION_CHANNELS
    }
    assert "MAJOR_CUSTOMER" not in {
        relationship_type.value for relationship_type in PROPAGATION_CHANNELS
    }
    assert "MAJOR_SUPPLIER" not in {
        relationship_type.value for relationship_type in PROPAGATION_CHANNELS
    }


def test_northbound_hold_defaults_into_event_and_reflexive_selectors() -> None:
    event_selector = effective_channel_selector("event")
    reflexive_selector = effective_channel_selector("reflexive")

    assert '"NORTHBOUND_HOLD"' in event_selector
    assert '"NORTHBOUND_HOLD"' in reflexive_selector
    assert '"CO_HOLDING"' in reflexive_selector
    assert RelationshipType.NORTHBOUND_HOLD.value not in relationship_types_for_channel(
        "fundamental",
    )
    assert RelationshipType.CO_HOLDING.value not in relationship_types_for_channel(
        "event",
    )
