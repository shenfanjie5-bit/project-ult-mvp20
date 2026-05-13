"""Contract-boundary schemas for entity-registry public payloads."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from contracts.core import ContractBaseModel
from contracts.schemas import (
    CANONICAL_ID_RULE_VERSION,
    CanonicalEntity,
    EntityAlias,
    EntityReference,
    EntityResolutionDecision,
    ResolutionCase,
)

ContractCanonicalEntity = CanonicalEntity
ContractEntityAlias = EntityAlias
ContractEntityReference = EntityReference
ContractResolutionCase = ResolutionCase


def current_canonical_id_rule_version() -> str:
    """Return the stable canonical ID rule version for contract payloads."""

    return CANONICAL_ID_RULE_VERSION


def to_contract_canonical_entity(entity: Any) -> CanonicalEntity:
    """Project an internal canonical entity record to the contracts schema."""

    return CanonicalEntity(
        canonical_entity_id=entity.canonical_entity_id,
        entity_type=_enum_value(entity.entity_type),
        display_name=entity.display_name,
        canonical_id_rule_version=_canonical_rule_version(entity),
        created_at=entity.created_at,
        attributes={
            "status": _enum_value(entity.status),
            "anchor_code": entity.anchor_code,
            "cross_listing_group": entity.cross_listing_group,
            "updated_at": entity.updated_at,
        },
    )


def to_contract_entity_alias(alias: Any) -> EntityAlias:
    """Project an internal alias record to the contracts schema."""

    return EntityAlias(
        alias_id=_stable_contract_id(
            "ALIAS",
            alias.canonical_entity_id,
            alias.alias_text,
            _enum_value(alias.alias_type),
            alias.source,
        ),
        canonical_entity_id=alias.canonical_entity_id,
        alias=alias.alias_text,
        alias_type=_enum_value(alias.alias_type),
        source_reference={
            "source": alias.source,
            "is_primary": alias.is_primary,
        },
        confidence=alias.confidence,
        observed_at=alias.created_at,
        canonical_id_rule_version=_canonical_rule_version(alias),
    )


def to_contract_entity_reference(entity: Any) -> EntityReference:
    """Project an internal canonical entity to a portable entity reference."""

    return EntityReference(
        entity_id=entity.canonical_entity_id,
        entity_type=_enum_value(entity.entity_type),
        canonical_id_rule_version=_canonical_rule_version(entity),
        display_name=entity.display_name,
    )


def to_contract_resolution_case(
    case: Any,
    *,
    input_alias: str,
    candidate_entities: Sequence[Any],
    decision: EntityResolutionDecision | str,
    resolved_entity: Any | None = None,
    evidence_refs: Sequence[str] | None = None,
    confidence: float | None = None,
) -> ResolutionCase:
    """Project an internal resolution case to the contracts audit schema."""

    contract_decision = _contract_decision(decision)
    canonical_id_rule_version = _canonical_rule_version(case)
    candidate_refs = _contract_candidate_references(
        candidate_entities,
        contract_decision,
        canonical_id_rule_version,
    )
    selected_entity_id = case.selected_entity_id
    if contract_decision is EntityResolutionDecision.MATCHED:
        if selected_entity_id is None:
            raise ValueError(
                "matched contracts ResolutionCase requires selected_entity_id"
            )
        selected_entity = resolved_entity or _find_entity(
            selected_entity_id,
            candidate_entities,
        )
        if selected_entity is None:
            raise ValueError(
                "matched contracts ResolutionCase requires the selected entity"
            )
        resolved_contract_entity = to_contract_entity_reference(selected_entity)
    else:
        if selected_entity_id is not None:
            raise ValueError(
                "unmatched contracts ResolutionCase must not carry selected_entity_id"
            )
        resolved_contract_entity = None

    return ResolutionCase(
        resolution_case_id=case.case_id,
        input_alias=input_alias,
        decision=contract_decision,
        confidence=_case_confidence(contract_decision, confidence),
        candidate_entities=candidate_refs,
        evidence_refs=list(evidence_refs or [case.reference_id]),
        resolved_at=case.created_at,
        canonical_id_rule_version=canonical_id_rule_version,
        resolved_entity=resolved_contract_entity,
    )


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _canonical_rule_version(value: Any) -> str:
    return getattr(value, "canonical_id_rule_version", CANONICAL_ID_RULE_VERSION)


def _contract_decision(
    decision: EntityResolutionDecision | str,
) -> EntityResolutionDecision:
    if isinstance(decision, EntityResolutionDecision):
        return decision
    return EntityResolutionDecision(decision)


def _contract_candidate_references(
    candidate_entities: Sequence[Any],
    decision: EntityResolutionDecision,
    canonical_id_rule_version: str,
) -> list[EntityReference]:
    if candidate_entities:
        return [
            to_contract_entity_reference(entity)
            for entity in candidate_entities
        ]

    if decision is EntityResolutionDecision.UNRESOLVED:
        return []

    raise ValueError(
        "contracts ResolutionCase requires candidate entities unless "
        "decision='unresolved'"
    )


def _stable_contract_id(prefix: str, *parts: str) -> str:
    joined = "\x1f".join(parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _find_entity(entity_id: str, entities: Sequence[Any]) -> Any | None:
    for entity in entities:
        if entity.canonical_entity_id == entity_id:
            return entity
    return None


def _case_confidence(
    decision: EntityResolutionDecision,
    confidence: float | None,
) -> float:
    if confidence is not None:
        return confidence
    if decision is EntityResolutionDecision.MATCHED:
        return 1.0
    return 0.0


__all__ = [
    "CANONICAL_ID_RULE_VERSION",
    "CanonicalEntity",
    "ContractBaseModel",
    "ContractCanonicalEntity",
    "ContractEntityAlias",
    "ContractEntityReference",
    "ContractResolutionCase",
    "EntityAlias",
    "EntityReference",
    "EntityResolutionDecision",
    "ResolutionCase",
    "current_canonical_id_rule_version",
    "to_contract_canonical_entity",
    "to_contract_entity_alias",
    "to_contract_entity_reference",
    "to_contract_resolution_case",
]
