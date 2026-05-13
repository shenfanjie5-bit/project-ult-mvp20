import inspect
from collections.abc import Iterator

import pytest

import entity_registry
from entity_registry.aliases import (
    AliasManager,
    generate_aliases_from_stock_basic,
    lookup_alias,
    normalize_alias_text,
)
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    EntityAlias,
    EntityStatus,
    EntityType,
)
from entity_registry.init import StockBasicRecord
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def make_stock_record(**overrides: object) -> StockBasicRecord:
    payload = {
        "ts_code": "300750.SZ",
        "symbol": "300750",
        "name": "宁德时代",
        "fullname": "宁德时代新能源科技股份有限公司",
        "enname": "Contemporary Amperex Technology Co., Limited",
        "cnspell": "NDSD",
        "market": "创业板",
        "exchange": "SZSE",
        "list_status": "L",
        "list_date": "20180611",
        "is_hs": "H",
    }
    payload.update(overrides)
    return StockBasicRecord.model_validate(payload)


def make_alias(
    *,
    entity_id: str = "ENT_STOCK_300750.SZ",
    alias_text: str = "宁德时代",
    alias_type: AliasType = AliasType.SHORT_NAME,
    is_primary: bool = True,
) -> EntityAlias:
    return EntityAlias(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=alias_type,
        confidence=1.0,
        source="unit-test",
        is_primary=is_primary,
    )


def make_entity(
    entity_id: str = "ENT_STOCK_300750.SZ",
    *,
    display_name: str = "宁德时代",
    cross_listing_group: str | None = None,
) -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name=display_name,
        status=EntityStatus.ACTIVE,
        anchor_code=entity_id.removeprefix("ENT_STOCK_"),
        cross_listing_group=cross_listing_group,
    )


def test_generate_aliases_maps_all_stock_basic_fields() -> None:
    aliases = generate_aliases_from_stock_basic(
        make_stock_record(),
        "ENT_STOCK_300750.SZ",
    )

    alias_by_type = {alias.alias_type: alias for alias in aliases}

    assert alias_by_type[AliasType.SHORT_NAME].alias_text == "宁德时代"
    assert alias_by_type[AliasType.FULL_NAME].alias_text == "宁德时代新能源科技股份有限公司"
    assert alias_by_type[AliasType.ENGLISH].alias_text == (
        "Contemporary Amperex Technology Co., Limited"
    )
    assert alias_by_type[AliasType.CNSPELL].alias_text == "NDSD"
    assert alias_by_type[AliasType.CODE].alias_text == "300750"


def test_generate_aliases_marks_name_as_primary() -> None:
    aliases = generate_aliases_from_stock_basic(
        make_stock_record(),
        "ENT_STOCK_300750.SZ",
    )

    primary_aliases = [alias for alias in aliases if alias.is_primary]

    assert len(primary_aliases) == 1
    assert primary_aliases[0].alias_type is AliasType.SHORT_NAME
    assert primary_aliases[0].alias_text == "宁德时代"


def test_generate_aliases_skips_missing_optional_fields() -> None:
    aliases = generate_aliases_from_stock_basic(
        make_stock_record(fullname=None, enname=None, cnspell=None),
        "ENT_STOCK_300750.SZ",
    )

    assert [(alias.alias_type, alias.alias_text) for alias in aliases] == [
        (AliasType.SHORT_NAME, "宁德时代"),
        (AliasType.CODE, "300750"),
    ]


def test_generate_aliases_strips_optional_field_whitespace() -> None:
    aliases = generate_aliases_from_stock_basic(
        make_stock_record(enname=" CATL "),
        "ENT_STOCK_300750.SZ",
    )

    english_alias = next(alias for alias in aliases if alias.alias_type is AliasType.ENGLISH)

    assert english_alias.alias_text == "CATL"


def test_normalize_alias_text_strips_outer_whitespace() -> None:
    assert normalize_alias_text(" 贵州茅台 ") == "贵州茅台"


def test_generate_aliases_keeps_same_text_with_different_types() -> None:
    aliases = generate_aliases_from_stock_basic(
        make_stock_record(fullname="宁德时代"),
        "ENT_STOCK_300750.SZ",
    )

    same_text_aliases = [alias for alias in aliases if alias.alias_text == "宁德时代"]

    assert {alias.alias_type for alias in same_text_aliases} == {
        AliasType.SHORT_NAME,
        AliasType.FULL_NAME,
    }


def test_alias_manager_add_alias_saves_alias() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    alias = make_alias()

    manager.add_alias(alias)

    assert repository.find_by_text("宁德时代") == [alias]


def test_alias_manager_add_alias_skips_semantic_duplicate() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    first = make_alias()
    second = make_alias()

    manager.add_alias(first)
    manager.add_alias(second)

    assert manager.lookup("宁德时代") == [first]


def test_alias_manager_batch_returns_created_count() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    aliases = [
        make_alias(),
        make_alias(alias_text="300750", alias_type=AliasType.CODE, is_primary=False),
    ]

    assert manager.add_aliases_batch(aliases) == 2
    assert manager.add_aliases_batch(aliases) == 0


def test_alias_manager_lookup_returns_exact_matches() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    alias = make_alias()

    manager.add_alias(alias)

    assert manager.lookup("宁德时代") == [alias]
    assert manager.lookup("宁德") == []


def test_lookup_alias_returns_canonical_entity_for_unique_match() -> None:
    alias_repo = InMemoryAliasRepository()
    entity_repo = InMemoryEntityRepository()
    entity = make_entity()
    alias = make_alias(entity_id=entity.canonical_entity_id)

    entity_repo.save(entity)
    alias_repo.save(alias)
    entity_registry.configure_default_repositories(entity_repo, alias_repo)

    assert lookup_alias(" 宁德时代 ") == entity


def test_lookup_alias_returns_none_for_missing_alias() -> None:
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
    )

    assert lookup_alias("不存在的别名") is None


def test_lookup_alias_returns_none_for_a_h_ambiguous_alias() -> None:
    alias_repo = InMemoryAliasRepository()
    entity_repo = InMemoryEntityRepository()
    a_share = make_entity("ENT_STOCK_300750.SZ", cross_listing_group="XLG_CATL")
    h_share = make_entity(
        "ENT_STOCK_03750.HK",
        display_name="宁德时代 H",
        cross_listing_group="XLG_CATL",
    )

    entity_repo.save(a_share)
    entity_repo.save(h_share)
    alias_repo.save_batch(
        [
            make_alias(entity_id=a_share.canonical_entity_id, alias_text="宁德时代"),
            make_alias(entity_id=h_share.canonical_entity_id, alias_text="宁德时代"),
        ]
    )
    entity_registry.configure_default_repositories(entity_repo, alias_repo)

    assert lookup_alias("宁德时代") is None


def test_lookup_alias_public_signature_matches_contract() -> None:
    signature = inspect.signature(lookup_alias)

    assert list(signature.parameters) == ["alias_text"]


def test_alias_manager_get_entity_aliases_returns_all_aliases() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    short_name = make_alias()
    code = make_alias(alias_text="300750", alias_type=AliasType.CODE, is_primary=False)

    manager.add_aliases_batch([short_name, code])

    assert manager.get_entity_aliases("ENT_STOCK_300750.SZ") == [short_name, code]


def test_alias_manager_allows_same_alias_text_for_different_entities() -> None:
    repository = InMemoryAliasRepository()
    manager = AliasManager(repository)
    a_share = make_alias(entity_id="ENT_STOCK_300750.SZ")
    h_share = make_alias(entity_id="ENT_STOCK_03750.HK")

    assert manager.add_aliases_batch([a_share, h_share]) == 2

    assert {alias.canonical_entity_id for alias in manager.lookup("宁德时代")} == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }


def test_alias_manager_returns_empty_list_for_missing_entity() -> None:
    manager = AliasManager(InMemoryAliasRepository())

    assert manager.get_entity_aliases("ENT_STOCK_MISSING.SZ") == []
