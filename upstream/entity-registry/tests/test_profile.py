from collections.abc import Iterator
from pathlib import Path

import pytest

import entity_registry
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.profile import CanonicalEntityProfile, get_entity_profile_from
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def initialized_repositories() -> tuple[
    InMemoryEntityRepository,
    InMemoryAliasRepository,
]:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert result.errors == []
    return entity_repo, alias_repo


def test_get_entity_profile_from_returns_entity_aliases_and_cross_listing_fields() -> None:
    entity_repo, alias_repo = initialized_repositories()

    profile = get_entity_profile_from("ENT_STOCK_600519.SH", entity_repo, alias_repo)

    assert isinstance(profile, CanonicalEntityProfile)
    assert profile.canonical_entity.canonical_entity_id == "ENT_STOCK_600519.SH"
    assert profile.canonical_entity.display_name == "贵州茅台"
    assert {alias.alias_text for alias in profile.aliases} >= {
        "贵州茅台",
        "贵州茅台酒股份有限公司",
        "600519",
    }
    assert profile.cross_listing_group is None
    assert profile.cross_listing_entity_ids == []


def test_get_entity_profile_keeps_a_h_listings_as_independent_ids() -> None:
    entity_repo, alias_repo = initialized_repositories()

    a_share = get_entity_profile_from("ENT_STOCK_300750.SZ", entity_repo, alias_repo)
    h_share = get_entity_profile_from("ENT_STOCK_03750.HK", entity_repo, alias_repo)

    assert a_share.canonical_entity.canonical_entity_id == "ENT_STOCK_300750.SZ"
    assert h_share.canonical_entity.canonical_entity_id == "ENT_STOCK_03750.HK"
    assert a_share.cross_listing_group == h_share.cross_listing_group
    assert a_share.cross_listing_group is not None
    assert a_share.cross_listing_entity_ids == ["ENT_STOCK_03750.HK"]
    assert h_share.cross_listing_entity_ids == ["ENT_STOCK_300750.SZ"]


def test_get_entity_profile_from_raises_key_error_for_missing_entity() -> None:
    entity_repo, alias_repo = initialized_repositories()

    with pytest.raises(KeyError):
        get_entity_profile_from("ENT_STOCK_MISSING.SZ", entity_repo, alias_repo)


def test_public_get_entity_profile_uses_configured_default_repositories() -> None:
    entity_repo, alias_repo = initialized_repositories()
    entity_registry.configure_default_repositories(entity_repo, alias_repo)

    profile = entity_registry.get_entity_profile("ENT_STOCK_000001.SZ")

    assert profile["canonical_entity"].display_name == "平安银行"
    assert {alias.alias for alias in profile["aliases"]} >= {"平安银行", "000001"}
