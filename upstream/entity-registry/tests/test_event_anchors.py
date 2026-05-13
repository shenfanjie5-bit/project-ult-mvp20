from __future__ import annotations

import entity_registry
from entity_registry.core import EntityType
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


def test_anchor_event_entity_is_idempotent_and_live_lookup_visible() -> None:
    entity_repo = InMemoryEntityRepository()
    event = entity_registry.anchor_event_entity(
        entity_repo,
        namespace="controlled-news",
        event_key="article-1#fact-1",
        display_name="Controlled news contract event",
    )

    repeated = entity_registry.anchor_event_entity(
        entity_repo,
        namespace="controlled-news",
        event_key="article-1#fact-1",
        display_name="Different later display name",
    )

    assert event == repeated
    assert event.entity_type is EntityType.EVENT
    assert event.anchor_code == "controlled-news:article-1#fact-1"
    assert event.canonical_entity_id.startswith("ENT_EVENT_CONTROLLED_NEWS_")
    assert entity_repo.list_all() == [event]

    entity_registry.configure_default_repositories(
        entity_repo,
        InMemoryAliasRepository(),
    )
    try:
        assert entity_registry.lookup_entity_refs([event.canonical_entity_id]) == {
            event.canonical_entity_id: True
        }
    finally:
        entity_registry.reset_default_repositories()
