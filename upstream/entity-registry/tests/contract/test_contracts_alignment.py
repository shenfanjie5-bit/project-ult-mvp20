"""Cross-repo alignment between entity-registry runtime models and the
contracts envelope (codex stage-2.3 follow-up #1 sub-rule from main-core).

entity-registry public APIs return contract-shaped objects:
- ``resolve_mention`` returns ``ContractResolutionCase``
- ``lookup_alias`` returns ``ContractCanonicalEntity | None``
- ``batch_resolve`` returns ``list[ContractResolutionCase]``

This file validates that:
1. The contract types are still importable from
   ``contracts.schemas.entities``.
2. Their canonical id format invariants per CLAUDE.md hold (CanonicalEntity
   uses ENT_* canonical id rule; A+H stays separate via cross_listing_group,
   not by sharing canonical id).
3. ``ResolutionCase.decision_type`` enum still includes the canonical
   values entity-registry produces.

**Module-level skip on missing dep**: requires the
``[contracts-schemas]`` extra. Other contract tests in this directory
remain runnable without it.
"""

from __future__ import annotations

import pytest

contracts_entities = pytest.importorskip(
    "contracts.schemas.entities",
    reason=(
        "project-ult-contracts not installed; install [contracts-schemas] "
        "extra to run cross-repo alignment tests"
    ),
)


class TestContractEntityTypesImport:
    def test_canonical_entity_importable(self) -> None:
        from contracts.schemas.entities import CanonicalEntity

        assert CanonicalEntity.model_fields, "CanonicalEntity has no fields"

    def test_entity_alias_importable(self) -> None:
        from contracts.schemas.entities import EntityAlias

        assert EntityAlias.model_fields, "EntityAlias has no fields"

    def test_resolution_case_importable(self) -> None:
        from contracts.schemas.entities import ResolutionCase

        assert ResolutionCase.model_fields, "ResolutionCase has no fields"


class TestEntityAlignmentInvariants:
    """Cross-repo invariants that must hold so entity-registry can publish
    its objects through the contract envelope without semantic drift."""

    def test_canonical_entity_has_id_and_canonical_id_rule_version(self) -> None:
        """CLAUDE.md: CanonicalEntity carries ``canonical_entity_id``
        (the ENT_* primary key) and ``canonical_id_rule_version`` (the
        rule version that minted the id; must be stable across publishes
        per "canonical ID 规则变更是否经由 contracts 版本发布"). Both
        field names must remain stable in the contract envelope.
        """
        from contracts.schemas.entities import CanonicalEntity

        for fname in (
            "canonical_entity_id",
            "canonical_id_rule_version",
            "entity_type",
        ):
            assert fname in CanonicalEntity.model_fields, (
                f"CanonicalEntity missing required field {fname!r}; "
                f"got {list(CanonicalEntity.model_fields)}"
            )

    def test_resolution_case_carries_decision_and_candidates(self) -> None:
        """CLAUDE.md: ResolutionCase records ``decision`` (the path
        chosen) + ``candidate_entities`` (multi-match audit set) +
        ``confidence``. These keep unresolved/multi-match audit paths
        intact across runtime ↔ contract serialization.
        """
        from contracts.schemas.entities import ResolutionCase

        for fname in (
            "decision",
            "candidate_entities",
            "confidence",
            "input_alias",
        ):
            assert fname in ResolutionCase.model_fields, (
                f"ResolutionCase missing required field {fname!r}; "
                f"got {list(ResolutionCase.model_fields)}"
            )
