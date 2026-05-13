"""Canonical entity profile aggregation."""

from __future__ import annotations

from pydantic import BaseModel

from entity_registry.core import CanonicalEntity, EntityAlias
from entity_registry.storage import AliasRepository, EntityRepository


class CanonicalEntityProfile(BaseModel):
    """Canonical entity with aliases and cross-listing links."""

    canonical_entity: CanonicalEntity
    aliases: list[EntityAlias]
    cross_listing_group: str | None
    cross_listing_entity_ids: list[str]


def get_entity_profile(canonical_entity_id: str) -> CanonicalEntityProfile:
    """Return an entity profile from the configured default repositories."""

    from entity_registry.init import get_default_repositories

    entity_repo, alias_repo = get_default_repositories()
    return get_entity_profile_from(canonical_entity_id, entity_repo, alias_repo)


def get_entity_profile_from(
    canonical_entity_id: str,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
) -> CanonicalEntityProfile:
    """Return a profile for one canonical entity ID."""

    entity = entity_repo.get(canonical_entity_id)
    if entity is None:
        raise KeyError(canonical_entity_id)

    cross_listing_entity_ids: list[str] = []
    if entity.cross_listing_group is not None:
        cross_listing_entity_ids = sorted(
            other.canonical_entity_id
            for other in entity_repo.list_all()
            if (
                other.canonical_entity_id != entity.canonical_entity_id
                and other.cross_listing_group == entity.cross_listing_group
            )
        )

    return CanonicalEntityProfile(
        canonical_entity=entity,
        aliases=alias_repo.find_by_entity(canonical_entity_id),
        cross_listing_group=entity.cross_listing_group,
        cross_listing_entity_ids=cross_listing_entity_ids,
    )
