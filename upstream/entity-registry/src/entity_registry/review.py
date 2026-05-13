"""Manual review queue workflows and resolution audit payloads."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from entity_registry.batch import BatchResolutionReport
from entity_registry.core import (
    AliasType,
    DecisionType,
    EntityAlias,
    ResolutionMethod,
)
from entity_registry.references import EntityReference, ResolutionCase, _new_case_id
from entity_registry.storage import (
    AliasRepository,
    EntityRepository,
    ReferenceRepository,
    ResolutionCaseRepository,
    ReviewRepository,
)


class ReviewStatus(str, Enum):
    """Controlled queue item lifecycle states."""

    PENDING = "pending"
    CLAIMED = "claimed"
    REJECTED = "rejected"
    PROMOTED = "promoted"
    DECIDED = "decided"


REVIEW_STATUS_PENDING = ReviewStatus.PENDING.value
REVIEW_STATUS_CLAIMED = ReviewStatus.CLAIMED.value
REVIEW_STATUS_REJECTED = ReviewStatus.REJECTED.value
REVIEW_STATUS_PROMOTED = ReviewStatus.PROMOTED.value
REVIEW_STATUS_DECIDED = ReviewStatus.DECIDED.value
_TERMINAL_STATUSES = {
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_PROMOTED,
    REVIEW_STATUS_DECIDED,
}


class ReviewStateError(RuntimeError):
    """Raised when a review queue transition is invalid."""


class ReviewNotFoundError(LookupError):
    """Raised when a required review, reference, case, or entity is missing."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UnresolvedQueueItem(BaseModel):
    """A queued unresolved mention awaiting manual review."""

    queue_item_id: str
    reference_id: str
    raw_mention_text: str
    source_context: dict[str, object]
    reference_created_at: datetime | None = None
    candidate_entity_ids: list[str]
    status: str
    claimed_by: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    decided_at: datetime | None = None

    @field_validator("queue_item_id", "reference_id", "raw_mention_text")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("field must be a non-empty string")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | ReviewStatus) -> str:
        status = value.value if isinstance(value, ReviewStatus) else value
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        if status not in {item.value for item in ReviewStatus}:
            raise ValueError(f"unsupported review status: {status}")
        return status

    @field_validator("claimed_by")
    @classmethod
    def validate_claimed_by(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("claimed_by must be a non-empty string when provided")
        return value

    @field_validator("candidate_entity_ids")
    @classmethod
    def validate_candidate_entity_ids(cls, value: list[str]) -> list[str]:
        for entity_id in value:
            if not isinstance(entity_id, str) or not entity_id.strip():
                raise ValueError("candidate_entity_ids must contain non-empty strings")
        return value


class ManualReviewDecision(BaseModel):
    """Reviewer decision for one unresolved queue item."""

    selected_entity_id: str | None
    confidence: float | None
    rationale: str
    promote_alias: bool = False
    alias_type: AliasType | None = None

    @field_validator("selected_entity_id")
    @classmethod
    def validate_selected_entity_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("selected_entity_id must be non-empty when provided")
        return value

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("rationale must be a non-empty string")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        if value is not None and (value < 0.0 or value > 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value

    @model_validator(mode="after")
    def validate_alias_promotion(self) -> ManualReviewDecision:
        if self.promote_alias:
            if self.selected_entity_id is None:
                raise ValueError("promote_alias requires selected_entity_id")
            if self.alias_type is None:
                raise ValueError("promote_alias requires alias_type")
        return self


class ResolutionAuditPayload(BaseModel):
    """Aggregated audit payload for one reference resolution."""

    entity_reference: EntityReference
    resolution_case: ResolutionCase
    unresolved: bool
    queue_item: UnresolvedQueueItem | None = None


class ReviewAuditWriter(Protocol):
    """Unit-of-work contract for manual review audit writes."""

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None: ...


class TransactionalReviewAuditWriter(ReviewAuditWriter, Protocol):
    """Audit writer that can roll back a manual-review audit write."""

    def rollback_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None: ...


class TransactionalAliasRepository(AliasRepository, Protocol):
    """Alias repository that can roll back a manual-review alias write."""

    def rollback_alias(self, alias: EntityAlias) -> None: ...


def enqueue_unresolved_reference(
    reference: EntityReference,
    *,
    review_repo: ReviewRepository,
    case_repo: ResolutionCaseRepository,
) -> UnresolvedQueueItem:
    """Queue one explicit unresolved reference for manual review."""

    _require_explicit_unresolved(reference)
    existing = review_repo.find_by_reference(reference.reference_id)
    if existing is not None:
        if existing.reference_created_at is None:
            updated = existing.model_copy(
                update={"reference_created_at": reference.created_at}
            )
            review_repo.save(updated)
            return review_repo.find_by_reference(reference.reference_id) or updated
        return existing

    latest_case = _latest_case_for_reference(reference.reference_id, case_repo)
    now = _utcnow()
    item = UnresolvedQueueItem(
        queue_item_id=_new_queue_item_id(reference.reference_id),
        reference_id=reference.reference_id,
        raw_mention_text=reference.raw_mention_text,
        source_context=dict(reference.source_context),
        reference_created_at=reference.created_at,
        candidate_entity_ids=list(latest_case.candidate_entity_ids),
        status=REVIEW_STATUS_PENDING,
        claimed_by=None,
        created_at=now,
        updated_at=now,
        decided_at=None,
    )
    review_repo.save(item)
    return review_repo.find_by_reference(reference.reference_id) or item


def enqueue_batch_manual_review(
    report: BatchResolutionReport,
    *,
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
    review_repo: ReviewRepository,
) -> list[UnresolvedQueueItem]:
    """Queue all manual-review references from a batch report.

    This helper processes references one at a time. Persistent adapters that need
    all-or-nothing batch enqueue semantics should wrap this call in their own
    storage transaction.
    """

    items: list[UnresolvedQueueItem] = []
    for reference_id in report.manual_review_reference_ids:
        reference = reference_repo.get(reference_id)
        if reference is None:
            raise ReviewNotFoundError(
                f"manual review reference not found: {reference_id}"
            )
        items.append(
            enqueue_unresolved_reference(
                reference,
                review_repo=review_repo,
                case_repo=case_repo,
            )
        )
    return items


def claim_review_item(
    queue_item_id: str,
    reviewer_id: str,
    *,
    review_repo: ReviewRepository,
) -> UnresolvedQueueItem:
    """Claim a pending queue item for one reviewer."""

    return review_repo.claim(queue_item_id, reviewer_id)


def submit_manual_review_decision(
    queue_item_id: str,
    decision: ManualReviewDecision,
    *,
    review_repo: ReviewRepository,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    audit_writer: ReviewAuditWriter,
) -> ResolutionAuditPayload:
    """Persist a reviewer decision and complete the queue item."""

    selected_entity_id = decision.selected_entity_id
    if selected_entity_id is not None and entity_repo.get(selected_entity_id) is None:
        raise ReviewNotFoundError(
            f"selected canonical entity not found: {selected_entity_id}"
        )

    terminal_status = (
        REVIEW_STATUS_REJECTED
        if selected_entity_id is None
        else REVIEW_STATUS_PROMOTED
    )

    def build_records(
        item: UnresolvedQueueItem,
    ) -> tuple[EntityReference, ResolutionCase, EntityAlias | None]:
        reference = _reference_for_decision(item, decision)
        case = ResolutionCase(
            case_id=_new_case_id(),
            reference_id=item.reference_id,
            candidate_entity_ids=_candidate_ids_for_decision(
                item,
                selected_entity_id,
            ),
            selected_entity_id=selected_entity_id,
            decision_type=DecisionType.MANUAL_REVIEW,
            decision_rationale=decision.rationale,
        )
        return reference, case, _alias_for_decision(item, decision)

    updated_item, reference, case = review_repo.complete_decision(
        queue_item_id,
        terminal_status,
        build_records,
        audit_writer=audit_writer,
        alias_repo=alias_repo,
    )

    return ResolutionAuditPayload(
        entity_reference=reference,
        resolution_case=case,
        unresolved=selected_entity_id is None,
        queue_item=updated_item,
    )


def get_resolution_audit_payload(
    reference_id: str,
    *,
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
    review_repo: ReviewRepository | None = None,
) -> ResolutionAuditPayload:
    """Return the latest audit payload for one reference ID."""

    reference = reference_repo.get(reference_id)
    if reference is None:
        raise ReviewNotFoundError(f"entity reference not found: {reference_id}")

    latest_case = _latest_case_for_reference(reference_id, case_repo)
    queue_item = (
        None
        if review_repo is None
        else review_repo.find_by_reference(reference_id)
    )
    return ResolutionAuditPayload(
        entity_reference=reference,
        resolution_case=latest_case,
        unresolved=(
            reference.resolved_entity_id is None
            and reference.resolution_method is ResolutionMethod.UNRESOLVED
        ),
        queue_item=queue_item,
    )


def _require_explicit_unresolved(reference: EntityReference) -> None:
    if (
        reference.resolved_entity_id is not None
        or reference.resolution_method is not ResolutionMethod.UNRESOLVED
    ):
        raise ValueError(
            "only explicit unresolved references can enter manual review"
        )


def _require_queue_item(
    queue_item_id: str,
    review_repo: ReviewRepository,
) -> UnresolvedQueueItem:
    item = review_repo.get(queue_item_id)
    if item is None:
        raise ReviewNotFoundError(f"review queue item not found: {queue_item_id}")
    return item


def _require_decidable(item: UnresolvedQueueItem) -> None:
    if item.status in _TERMINAL_STATUSES:
        raise ReviewStateError(
            f"review queue item already completed: {item.queue_item_id}"
        )
    if item.status not in {REVIEW_STATUS_PENDING, REVIEW_STATUS_CLAIMED}:
        raise ReviewStateError(
            f"review queue item cannot be decided from status={item.status}"
        )


def _reference_for_decision(
    item: UnresolvedQueueItem,
    decision: ManualReviewDecision,
) -> EntityReference:
    selected_entity_id = decision.selected_entity_id
    return EntityReference(
        reference_id=item.reference_id,
        raw_mention_text=item.raw_mention_text,
        source_context=dict(item.source_context),
        resolved_entity_id=selected_entity_id,
        resolution_method=(
            ResolutionMethod.UNRESOLVED
            if selected_entity_id is None
            else ResolutionMethod.MANUAL
        ),
        resolution_confidence=(
            None
            if selected_entity_id is None
            else _manual_confidence(decision)
        ),
        created_at=_reference_created_at_for_item(item),
    )


def _reference_created_at_for_item(item: UnresolvedQueueItem) -> datetime:
    if item.reference_created_at is None:
        raise ReviewStateError(
            "review queue item is missing original reference_created_at: "
            f"{item.queue_item_id}"
        )
    return item.reference_created_at


def _manual_confidence(decision: ManualReviewDecision) -> float:
    return 1.0 if decision.confidence is None else decision.confidence


def _candidate_ids_for_decision(
    item: UnresolvedQueueItem,
    selected_entity_id: str | None,
) -> list[str]:
    candidate_entity_ids = list(item.candidate_entity_ids)
    if (
        selected_entity_id is not None
        and selected_entity_id not in candidate_entity_ids
    ):
        candidate_entity_ids.append(selected_entity_id)
    return candidate_entity_ids


def _alias_for_decision(
    item: UnresolvedQueueItem,
    decision: ManualReviewDecision,
) -> EntityAlias | None:
    if not decision.promote_alias:
        return None
    if decision.selected_entity_id is None or decision.alias_type is None:
        raise ValueError("alias promotion requires an entity and alias_type")

    return EntityAlias(
        canonical_entity_id=decision.selected_entity_id,
        alias_text=item.raw_mention_text,
        alias_type=decision.alias_type,
        confidence=_manual_confidence(decision),
        source="manual_review",
        is_primary=False,
    )


def _latest_case_for_reference(
    reference_id: str,
    case_repo: ResolutionCaseRepository,
) -> ResolutionCase:
    cases = case_repo.find_by_reference(reference_id)
    if not cases:
        raise ReviewNotFoundError(
            f"resolution case not found for reference: {reference_id}"
        )
    return max(cases, key=lambda case: (case.created_at, case.case_id))


def _new_queue_item_id(reference_id: str) -> str:
    digest = hashlib.sha1(reference_id.encode("utf-8")).hexdigest()[:16]
    return f"RQ_{digest}"


__all__ = [
    "ManualReviewDecision",
    "REVIEW_STATUS_CLAIMED",
    "REVIEW_STATUS_DECIDED",
    "REVIEW_STATUS_PENDING",
    "REVIEW_STATUS_PROMOTED",
    "REVIEW_STATUS_REJECTED",
    "ResolutionAuditPayload",
    "ReviewAuditWriter",
    "ReviewNotFoundError",
    "ReviewStateError",
    "ReviewStatus",
    "TransactionalAliasRepository",
    "TransactionalReviewAuditWriter",
    "UnresolvedQueueItem",
    "claim_review_item",
    "enqueue_batch_manual_review",
    "enqueue_unresolved_reference",
    "get_resolution_audit_payload",
    "submit_manual_review_decision",
]
