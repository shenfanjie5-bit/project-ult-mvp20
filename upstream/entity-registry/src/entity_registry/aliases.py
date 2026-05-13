"""Alias generation and exact-match alias management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from entity_registry.core import AliasType, CanonicalEntity, EntityAlias
from entity_registry.storage import AliasRepository, EntityRepository

if TYPE_CHECKING:
    from entity_registry.init import StockBasicRecord


_STOCK_BASIC_SOURCE = "stock_basic"


def _clean_alias_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def normalize_alias_text(alias_text: str) -> str:
    """Normalize user-supplied alias text for exact-match lookup."""

    return alias_text.strip()


def generate_aliases_from_stock_basic(
    record: StockBasicRecord,
    canonical_entity_id: str,
) -> list[EntityAlias]:
    """Generate stock aliases from the canonical stock_basic fields."""

    alias_specs = [
        (record.name, AliasType.SHORT_NAME, True),
        (record.fullname, AliasType.FULL_NAME, False),
        (record.enname, AliasType.ENGLISH, False),
        (record.cnspell, AliasType.CNSPELL, False),
        (record.symbol, AliasType.CODE, False),
    ]

    aliases: list[EntityAlias] = []
    seen: set[tuple[str, AliasType]] = set()
    for raw_alias_text, alias_type, is_primary in alias_specs:
        alias_text = _clean_alias_text(raw_alias_text)
        if alias_text is None:
            continue

        dedupe_key = (alias_text, alias_type)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        aliases.append(
            EntityAlias(
                canonical_entity_id=canonical_entity_id,
                alias_text=alias_text,
                alias_type=alias_type,
                confidence=1.0,
                source=_STOCK_BASIC_SOURCE,
                is_primary=is_primary,
            )
        )

    return aliases


def lookup_alias(alias_text: str) -> CanonicalEntity | None:
    """Return a canonical entity only for one exact alias-to-entity match."""

    entity_repo, alias_repo = _get_default_repositories()
    return lookup_alias_in_repositories(alias_text, alias_repo, entity_repo)


def lookup_alias_in_repositories(
    alias_text: str,
    alias_repo: AliasRepository,
    entity_repo: EntityRepository,
) -> CanonicalEntity | None:
    """Return a canonical entity only for one exact alias-to-entity match.

    No alias hit returns ``None``. Alias text that points at multiple canonical
    IDs also returns ``None`` so A+H listings and other ambiguous mentions do
    not silently collapse to one entity.
    """

    aliases = alias_repo.find_by_text(normalize_alias_text(alias_text))
    canonical_entity_ids = {alias.canonical_entity_id for alias in aliases}

    if len(canonical_entity_ids) != 1:
        return None

    canonical_entity_id = next(iter(canonical_entity_ids))
    return entity_repo.get(canonical_entity_id)


class AliasManager:
    """Small exact-match facade over an alias repository."""

    def __init__(self, alias_repo: AliasRepository) -> None:
        self._alias_repo = alias_repo

    def add_alias(self, alias: EntityAlias) -> None:
        """Add one alias unless the same entity/text/type mapping already exists."""

        self._alias_repo.save_if_absent(alias)

    def add_aliases_batch(self, aliases: list[EntityAlias]) -> int:
        """Add aliases and return the number of newly stored mappings."""

        return self._alias_repo.save_batch_if_absent(aliases)

    def lookup(self, alias_text: str) -> list[EntityAlias]:
        """Return exact text matches for an alias."""

        return self._alias_repo.find_by_text(normalize_alias_text(alias_text))

    def get_entity_aliases(self, canonical_entity_id: str) -> list[EntityAlias]:
        """Return all aliases attached to one canonical entity."""

        return self._alias_repo.find_by_entity(canonical_entity_id)


def _get_default_repositories() -> tuple[EntityRepository, AliasRepository]:
    from entity_registry.init import get_default_repositories

    return get_default_repositories()
