"""Reference and resolution-case audit models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from entity_registry.contracts import current_canonical_id_rule_version
from entity_registry.core import DecisionType, ResolutionMethod

if TYPE_CHECKING:
    from entity_registry.storage import (
        ReferenceRepository,
        ResolutionCaseRepository,
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EntityReference(BaseModel):
    """A recorded raw mention and its resolution state."""

    reference_id: str
    raw_mention_text: str
    source_context: dict
    resolved_entity_id: str | None
    resolution_method: ResolutionMethod
    resolution_confidence: float | None
    created_at: datetime = Field(default_factory=_utcnow)
    canonical_id_rule_version: str = Field(
        default_factory=current_canonical_id_rule_version,
        exclude=True,
    )

    @model_validator(mode="after")
    def validate_resolution_state(self) -> EntityReference:
        if self.resolution_method is ResolutionMethod.UNRESOLVED:
            if self.resolved_entity_id is not None:
                raise ValueError(
                    "unresolved references must not carry a resolved entity"
                )
            if self.resolution_confidence is not None:
                raise ValueError("unresolved references must not carry confidence")
            return self

        if self.resolved_entity_id is None:
            raise ValueError("resolved_entity_id is required for resolved references")
        if self.resolution_confidence is None:
            raise ValueError("resolution_confidence is required for resolved references")
        if self.resolution_confidence < 0.0 or self.resolution_confidence > 1.0:
            raise ValueError("resolution_confidence must be between 0.0 and 1.0")

        return self


class ResolutionCase(BaseModel):
    """Auditable decision record for a mention resolution case."""

    case_id: str
    reference_id: str
    candidate_entity_ids: list[str]
    selected_entity_id: str | None
    decision_type: DecisionType
    decision_rationale: str
    created_at: datetime = Field(default_factory=_utcnow)
    canonical_id_rule_version: str = Field(
        default_factory=current_canonical_id_rule_version,
        exclude=True,
    )


def register_unresolved_reference(
    reference: EntityReference | dict[str, object],
) -> EntityReference:
    """Register an unresolved reference in the configured default repository."""

    from entity_registry.init import get_default_reference_repository

    return register_unresolved_reference_into(
        reference,
        get_default_reference_repository(),
    )


def register_unresolved_reference_into(
    reference: EntityReference | dict[str, object],
    reference_repo: ReferenceRepository,
) -> EntityReference:
    """Normalize, validate, save, and return one unresolved reference."""

    unresolved_reference = _coerce_unresolved_reference(reference)
    reference_repo.save(unresolved_reference)
    return unresolved_reference


def record_resolution_case(
    case: ResolutionCase,
    case_repo: ResolutionCaseRepository,
) -> ResolutionCase:
    """Save and return one resolution audit case."""

    case_repo.save(case)
    return case


def _coerce_unresolved_reference(
    reference: EntityReference | dict[str, object],
) -> EntityReference:
    if isinstance(reference, EntityReference):
        if reference.resolution_method is not ResolutionMethod.UNRESOLVED:
            raise ValueError("register_unresolved_reference requires unresolved state")
        return reference

    payload = dict(reference)
    if payload.get("resolved_entity_id") is not None:
        raise ValueError(
            "unresolved reference payload must not include resolved_entity_id"
        )

    resolution_method = payload.get("resolution_method")
    if (
        resolution_method is not None
        and ResolutionMethod(resolution_method) is not ResolutionMethod.UNRESOLVED
    ):
        raise ValueError(
            "unresolved reference payload must use resolution_method='unresolved'"
        )

    if payload.get("resolution_confidence") is not None:
        raise ValueError("unresolved reference payload must not include confidence")

    payload.setdefault("reference_id", _new_reference_id())
    payload.setdefault("source_context", {})
    payload.setdefault("resolved_entity_id", None)
    payload.setdefault("resolution_method", ResolutionMethod.UNRESOLVED)
    payload.setdefault("resolution_confidence", None)
    return EntityReference.model_validate(payload)


def _new_reference_id() -> str:
    return f"REF_{uuid4().hex}"


def _new_case_id() -> str:
    return f"CASE_{uuid4().hex}"
