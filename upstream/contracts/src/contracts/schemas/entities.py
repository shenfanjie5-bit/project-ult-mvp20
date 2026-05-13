"""Entity registry shared schemas."""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import Field, model_validator

from contracts.core import (
    AwareDatetime,
    Confidence,
    ContractBaseModel,
    EntityId,
    EvidenceRef,
    VersionString,
)
from contracts.core.types import NonEmptyString


CANONICAL_ID_RULE_VERSION: VersionString = "ent-id-rule-v1"


class EntityResolutionDecision(str, Enum):
    """Stable resolution outcomes for entity-registry contracts."""

    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class CanonicalEntity(ContractBaseModel):
    """Canonical entity published by entity-registry."""

    canonical_entity_id: EntityId
    entity_type: NonEmptyString
    display_name: NonEmptyString
    canonical_id_rule_version: VersionString
    created_at: AwareDatetime
    attributes: dict[str, object] = Field(default_factory=dict)


class EntityAlias(ContractBaseModel):
    """Observed alias mapped to a canonical entity."""

    alias_id: NonEmptyString
    canonical_entity_id: EntityId
    alias: NonEmptyString
    alias_type: NonEmptyString
    source_reference: dict[str, object] = Field(min_length=1)
    confidence: Confidence
    observed_at: AwareDatetime
    canonical_id_rule_version: VersionString


class EntityReference(ContractBaseModel):
    """Portable reference to a canonical entity across downstream schemas."""

    entity_id: EntityId
    entity_type: NonEmptyString
    canonical_id_rule_version: VersionString
    display_name: NonEmptyString | None = None


class ResolutionCase(ContractBaseModel):
    """Entity resolution decision record shared at the module boundary."""

    resolution_case_id: NonEmptyString
    input_alias: NonEmptyString
    decision: EntityResolutionDecision
    confidence: Confidence
    candidate_entities: list[EntityReference]
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    resolved_at: AwareDatetime
    canonical_id_rule_version: VersionString
    resolved_entity: EntityReference | None = None

    @model_validator(mode="after")
    def resolved_entity_must_match_decision(self) -> Self:
        """Keep resolution outcomes aligned with the resolved entity field."""

        if self.decision is EntityResolutionDecision.MATCHED:
            if self.resolved_entity is None:
                raise ValueError("matched resolution requires resolved_entity")
        if (
            self.decision
            in {
                EntityResolutionDecision.MATCHED,
                EntityResolutionDecision.AMBIGUOUS,
            }
            and not self.candidate_entities
        ):
            raise ValueError(
                "candidate_entities may be empty only for unresolved decisions"
            )

        if (
            self.decision is not EntityResolutionDecision.MATCHED
            and self.resolved_entity is not None
        ):
            raise ValueError(
                "resolved_entity is only allowed for matched resolution decisions"
            )

        return self


__all__ = [
    "CANONICAL_ID_RULE_VERSION",
    "EntityResolutionDecision",
    "CanonicalEntity",
    "EntityAlias",
    "EntityReference",
    "ResolutionCase",
]
