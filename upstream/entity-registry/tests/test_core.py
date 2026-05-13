from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from entity_registry import __version__
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityAlias,
    EntityStatus,
    EntityType,
    FinalStatus,
    ResolutionMethod,
    generate_event_entity_id,
    generate_stock_entity_id,
    validate_entity_id,
)


def make_stock_entity(entity_id: str = "ENT_STOCK_300750.SZ") -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name="CATL",
        status=EntityStatus.ACTIVE,
        anchor_code=entity_id.removeprefix("ENT_STOCK_"),
        cross_listing_group=None,
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
        updated_at=datetime(2026, 4, 15, tzinfo=UTC),
    )


def test_package_exports_version() -> None:
    assert __version__ == "0.1.1"


def test_entity_type_values() -> None:
    assert {item.value for item in EntityType} == {
        "stock",
        "corp",
        "person",
        "org",
        "index",
        "event",
    }


def test_entity_status_values() -> None:
    assert {item.value for item in EntityStatus} == {
        "active",
        "inactive",
        "merged",
    }


def test_alias_type_values() -> None:
    assert {item.value for item in AliasType} == {
        "full_name",
        "short_name",
        "code",
        "english",
        "former_name",
        "cnspell",
    }


def test_resolution_method_values() -> None:
    assert {item.value for item in ResolutionMethod} == {
        "deterministic",
        "fuzzy",
        "llm",
        "manual",
        "unresolved",
    }


def test_decision_type_values() -> None:
    assert {item.value for item in DecisionType} == {
        "auto",
        "llm_assisted",
        "manual_review",
    }


def test_final_status_values() -> None:
    assert {item.value for item in FinalStatus} == {
        "resolved",
        "unresolved",
        "manual_review",
    }


def test_canonical_entity_builds_and_round_trips() -> None:
    entity = make_stock_entity()
    payload = entity.model_dump(mode="json")
    restored = CanonicalEntity.model_validate(payload)

    assert restored == entity
    assert payload["canonical_entity_id"] == "ENT_STOCK_300750.SZ"
    assert payload["anchor_code"] == "300750.SZ"


def test_stock_entity_requires_anchor_code() -> None:
    with pytest.raises(ValidationError):
        CanonicalEntity(
            canonical_entity_id="ENT_STOCK_300750.SZ",
            entity_type=EntityType.STOCK,
            display_name="CATL",
            status=EntityStatus.ACTIVE,
            anchor_code=None,
            cross_listing_group=None,
        )


def test_canonical_entity_rejects_invalid_id() -> None:
    with pytest.raises(ValidationError):
        CanonicalEntity(
            canonical_entity_id="RANDOM_ID",
            entity_type=EntityType.CORP,
            display_name="Example Corp",
            status=EntityStatus.ACTIVE,
        )


def test_entity_alias_builds() -> None:
    alias = EntityAlias(
        canonical_entity_id="ENT_STOCK_300750.SZ",
        alias_text="CATL",
        alias_type=AliasType.SHORT_NAME,
        confidence=1.0,
        source="unit-test",
        is_primary=True,
    )

    assert alias.alias_type is AliasType.SHORT_NAME
    assert alias.confidence == 1.0


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_entity_alias_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        EntityAlias(
            canonical_entity_id="ENT_STOCK_300750.SZ",
            alias_text="CATL",
            alias_type=AliasType.SHORT_NAME,
            confidence=confidence,
            source="unit-test",
            is_primary=True,
        )


def test_generate_stock_entity_id() -> None:
    assert generate_stock_entity_id("300750.SZ") == "ENT_STOCK_300750.SZ"


def test_generate_stock_entity_id_trims_input() -> None:
    assert generate_stock_entity_id(" 300750.SZ ") == "ENT_STOCK_300750.SZ"


def test_generate_stock_entity_id_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        generate_stock_entity_id("")


def test_generate_stock_entity_id_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        generate_stock_entity_id("300750 SZ")


def test_generate_event_entity_id_is_deterministic_and_namespaced() -> None:
    first = generate_event_entity_id("controlled-news", "article-1#fact-1")
    second = generate_event_entity_id("controlled news", "article-1#fact-1")

    assert first == second
    assert first.startswith("ENT_EVENT_CONTROLLED_NEWS_")
    assert validate_entity_id(first) is True


def test_event_entity_requires_anchor_code() -> None:
    with pytest.raises(ValidationError):
        CanonicalEntity(
            canonical_entity_id=generate_event_entity_id("news", "article-1#fact-1"),
            entity_type=EntityType.EVENT,
            display_name="Controlled event",
            status=EntityStatus.ACTIVE,
        )


def test_validate_entity_id_accepts_stock_id() -> None:
    assert validate_entity_id("ENT_STOCK_300750.SZ") is True


def test_validate_entity_id_accepts_future_extension_shape() -> None:
    assert validate_entity_id("ENT_CORP_EXAMPLE-001") is True


def test_validate_entity_id_rejects_random_id() -> None:
    assert validate_entity_id("RANDOM_ID") is False


def test_validate_entity_id_rejects_whitespace() -> None:
    assert validate_entity_id(" ENT_STOCK_300750.SZ") is False


def test_a_share_and_h_share_generate_independent_ids() -> None:
    a_share_id = generate_stock_entity_id("300750.SZ")
    h_share_id = generate_stock_entity_id("06888.HK")

    assert a_share_id == "ENT_STOCK_300750.SZ"
    assert h_share_id == "ENT_STOCK_06888.HK"
    assert a_share_id != h_share_id
