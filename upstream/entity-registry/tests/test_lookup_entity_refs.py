from __future__ import annotations

import pytest

import entity_registry
from entity_registry import RepositoryNotConfiguredError
from entity_registry.core import CanonicalEntity, EntityStatus, EntityType
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


@pytest.fixture(autouse=True)
def _reset_repositories() -> None:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_lookup_entity_refs_reads_configured_live_repository() -> None:
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(
        CanonicalEntity(
            canonical_entity_id="ENT_STOCK_600519.SH",
            entity_type=EntityType.STOCK,
            display_name="Kweichow Moutai",
            status=EntityStatus.ACTIVE,
            anchor_code="600519.SH",
        )
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        InMemoryAliasRepository(),
    )

    result = entity_registry.lookup_entity_refs(
        [
            "ENT_STOCK_600519.SH",
            "ENT_STOCK_000001.SZ",
            "plain-alias-not-canonical",
        ]
    )

    assert result == {
        "ENT_STOCK_600519.SH": True,
        "ENT_STOCK_000001.SZ": False,
        "plain-alias-not-canonical": False,
    }


def test_lookup_entity_refs_fails_when_live_repository_is_not_configured() -> None:
    with pytest.raises(RepositoryNotConfiguredError):
        entity_registry.lookup_entity_refs(["ENT_STOCK_600519.SH"])
