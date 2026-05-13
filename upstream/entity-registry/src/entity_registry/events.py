"""Deterministic anchoring helpers for event entities."""

from __future__ import annotations

from entity_registry.core import (
    CanonicalEntity,
    EntityStatus,
    EntityType,
    generate_event_entity_id,
)
from entity_registry.storage import EntityRepository


def anchor_event_entity(
    entity_repo: EntityRepository,
    *,
    namespace: str,
    event_key: str,
    display_name: str,
) -> CanonicalEntity:
    """Persist or return the canonical event entity for a deterministic event key."""

    entity_id = generate_event_entity_id(namespace, event_key)
    anchor_code = _event_anchor_code(namespace, event_key)
    entity = CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.EVENT,
        display_name=_require_text(display_name, field_name="display_name"),
        status=EntityStatus.ACTIVE,
        anchor_code=anchor_code,
    )
    entity_repo.save_if_absent(entity)
    anchored = entity_repo.get(entity_id)
    if anchored is None:
        raise RuntimeError(f"event entity anchor was not persisted: {entity_id}")
    return anchored


def _event_anchor_code(namespace: str, event_key: str) -> str:
    return (
        f"{_require_text(namespace, field_name='namespace')}:"
        f"{_require_text(event_key, field_name='event_key')}"
    )


def _require_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = " ".join(value.strip().split())
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


__all__ = ["anchor_event_entity"]
