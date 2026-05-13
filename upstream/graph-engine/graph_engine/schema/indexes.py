"""Idempotent Neo4j schema DDL statements."""

from __future__ import annotations

from graph_engine.schema.definitions import NodeLabel, RelationshipType


def get_index_statements() -> list[str]:
    """Return the required Neo4j index DDL statements."""

    return [
        "CREATE INDEX graph_entity_canonical_entity_id_index IF NOT EXISTS "
        f"FOR (n:{NodeLabel.ENTITY.value}) ON (n.canonical_entity_id)",
        "CREATE INDEX graph_entity_label_index IF NOT EXISTS "
        f"FOR (n:{NodeLabel.ENTITY.value}) ON (n.label)",
        "CREATE INDEX graph_event_cycle_id_index IF NOT EXISTS "
        f"FOR (n:{NodeLabel.EVENT.value}) ON (n.cycle_id)",
        "CREATE INDEX graph_assertion_type_index IF NOT EXISTS "
        f"FOR (n:{NodeLabel.ASSERTION.value}) ON (n.assertion_type)",
        "CREATE INDEX graph_supply_chain_weight_index IF NOT EXISTS "
        f"FOR ()-[r:{RelationshipType.SUPPLY_CHAIN.value}]-() ON (r.weight)",
        "CREATE INDEX graph_event_impact_confidence_index IF NOT EXISTS "
        f"FOR ()-[r:{RelationshipType.EVENT_IMPACT.value}]-() ON (r.confidence)",
    ]


def get_constraint_statements() -> list[str]:
    """Return the required Neo4j uniqueness constraint DDL statements."""

    return [
        f"CREATE CONSTRAINT graph_{label.value.lower()}_node_id_unique IF NOT EXISTS "
        f"FOR (n:{label.value}) REQUIRE n.node_id IS UNIQUE"
        for label in NodeLabel
    ]
