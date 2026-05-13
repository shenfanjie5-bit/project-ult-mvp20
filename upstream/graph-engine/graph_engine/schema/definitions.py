"""Core Neo4j labels and relationship types."""

from __future__ import annotations

from enum import Enum


class NodeLabel(str, Enum):
    """Node labels used by the live graph schema."""

    ENTITY = "Entity"
    SECTOR = "Sector"
    INDUSTRY = "Industry"
    REGION = "Region"
    EVENT = "Event"
    ASSERTION = "Assertion"


class RelationshipType(str, Enum):
    """Relationship types required by graph propagation channels."""

    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    OWNERSHIP = "OWNERSHIP"
    INDUSTRY_CHAIN = "INDUSTRY_CHAIN"
    SECTOR_MEMBERSHIP = "SECTOR_MEMBERSHIP"
    EVENT_IMPACT = "EVENT_IMPACT"
    ASSERTION_LINK = "ASSERTION_LINK"
    CO_HOLDING = "CO_HOLDING"
    NORTHBOUND_HOLD = "NORTHBOUND_HOLD"
