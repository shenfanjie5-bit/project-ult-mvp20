from datetime import UTC, datetime

import pytest

from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityAlias,
    EntityStatus,
    EntityType,
    ResolutionMethod,
)
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.review import (
    REVIEW_STATUS_CLAIMED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_PROMOTED,
    REVIEW_STATUS_REJECTED,
    ReviewStateError,
    UnresolvedQueueItem,
)
from entity_registry.storage import (
    AliasRepository,
    EntityRepository,
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryReviewRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
    ReferenceRepository,
    ResolutionAuditReferenceRepository,
    ReviewRepository,
    ResolutionCaseRepository,
)

REFERENCE_CREATED_AT = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)


def make_entity(entity_id: str = "ENT_STOCK_300750.SZ") -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name="CATL",
        status=EntityStatus.ACTIVE,
        anchor_code=entity_id.removeprefix("ENT_STOCK_"),
        cross_listing_group=None,
    )


def make_alias(
    entity_id: str = "ENT_STOCK_300750.SZ",
    alias_text: str = "CATL",
) -> EntityAlias:
    return EntityAlias(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=AliasType.SHORT_NAME,
        confidence=1.0,
        source="unit-test",
        is_primary=True,
    )


def make_reference(
    reference_id: str,
    resolved_entity_id: str | None,
) -> EntityReference:
    return EntityReference(
        reference_id=reference_id,
        raw_mention_text="CATL" if resolved_entity_id else "Unknown Corp",
        source_context={"source": "unit-test"},
        resolved_entity_id=resolved_entity_id,
        resolution_method=(
            ResolutionMethod.DETERMINISTIC
            if resolved_entity_id
            else ResolutionMethod.UNRESOLVED
        ),
        resolution_confidence=1.0 if resolved_entity_id else None,
    )


def make_case(
    case_id: str,
    reference_id: str,
    selected_entity_id: str | None,
) -> ResolutionCase:
    return ResolutionCase(
        case_id=case_id,
        reference_id=reference_id,
        candidate_entity_ids=(
            [selected_entity_id]
            if selected_entity_id is not None
            else []
        ),
        selected_entity_id=selected_entity_id,
        decision_type=(
            DecisionType.AUTO
            if selected_entity_id is not None
            else DecisionType.MANUAL_REVIEW
        ),
        decision_rationale="unit-test",
    )


def test_entity_repository_protocol_is_usable_for_in_memory() -> None:
    repository: EntityRepository = InMemoryEntityRepository()

    assert repository.list_all() == []


def test_in_memory_entity_repository_saves_and_gets_entity() -> None:
    repository = InMemoryEntityRepository()
    entity = make_entity()

    repository.save(entity)

    assert repository.get("ENT_STOCK_300750.SZ") == entity
    assert repository.exists("ENT_STOCK_300750.SZ") is True


def test_in_memory_entity_repository_returns_none_for_missing_entity() -> None:
    repository = InMemoryEntityRepository()

    assert repository.get("ENT_STOCK_MISSING.SZ") is None
    assert repository.exists("ENT_STOCK_MISSING.SZ") is False


def test_in_memory_entity_repository_lists_all_entities() -> None:
    repository = InMemoryEntityRepository()
    first = make_entity("ENT_STOCK_300750.SZ")
    second = make_entity("ENT_STOCK_06888.HK")

    repository.save(first)
    repository.save(second)

    assert repository.list_all() == [first, second]


def test_in_memory_entity_repository_upserts_by_id() -> None:
    repository = InMemoryEntityRepository()
    original = make_entity()
    updated = original.model_copy(update={"display_name": "Updated"})

    repository.save(original)
    repository.save(updated)

    assert repository.list_all() == [updated]


def test_in_memory_entity_repository_save_if_absent_is_insert_only() -> None:
    repository = InMemoryEntityRepository()
    original = make_entity()
    updated = original.model_copy(update={"display_name": "Updated"})

    assert repository.save_if_absent(original) is True
    assert repository.save_if_absent(updated) is False

    assert repository.list_all() == [original]


def test_alias_repository_protocol_is_usable_for_in_memory() -> None:
    repository: AliasRepository = InMemoryAliasRepository()

    assert repository.find_by_text("missing") == []
    assert repository.list_all() == []


def test_in_memory_alias_repository_finds_by_text() -> None:
    repository = InMemoryAliasRepository()
    alias = make_alias()

    repository.save(alias)

    assert repository.find_by_text("CATL") == [alias]


def test_in_memory_alias_repository_finds_by_entity() -> None:
    repository = InMemoryAliasRepository()
    alias = make_alias()

    repository.save(alias)

    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [alias]


def test_in_memory_alias_repository_lists_all_aliases_without_exposing_index() -> None:
    repository = InMemoryAliasRepository()
    short_name = make_alias(alias_text="CATL")
    code = make_alias(alias_text="300750")

    repository.save_batch([short_name, code])
    aliases = repository.list_all()
    aliases.clear()

    assert repository.list_all() == [short_name, code]
    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [short_name, code]


def test_in_memory_alias_repository_returns_empty_lists_for_missing_keys() -> None:
    repository = InMemoryAliasRepository()

    assert repository.find_by_text("missing") == []
    assert repository.find_by_entity("ENT_STOCK_MISSING.SZ") == []


def test_in_memory_alias_repository_supports_batch_save() -> None:
    repository = InMemoryAliasRepository()
    short_name = make_alias(alias_text="CATL")
    code = EntityAlias(
        canonical_entity_id="ENT_STOCK_300750.SZ",
        alias_text="300750.SZ",
        alias_type=AliasType.CODE,
        confidence=1.0,
        source="unit-test",
        is_primary=False,
    )

    repository.save_batch([short_name, code])

    assert repository.find_by_text("300750.SZ") == [code]
    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [short_name, code]


def test_in_memory_alias_repository_does_not_duplicate_same_alias() -> None:
    repository = InMemoryAliasRepository()
    alias = make_alias()

    repository.save(alias)
    repository.save(alias)

    assert repository.find_by_text("CATL") == [alias]
    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [alias]


def test_in_memory_alias_repository_rejects_semantic_duplicate_alias() -> None:
    repository = InMemoryAliasRepository()
    first = make_alias()
    second = make_alias()

    assert repository.save_if_absent(first) is True
    assert repository.save_if_absent(second) is False

    assert repository.find_by_text("CATL") == [first]
    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [first]


def test_in_memory_alias_repository_batch_save_if_absent_returns_created_count() -> None:
    repository = InMemoryAliasRepository()
    first = make_alias(alias_text="CATL")
    duplicate = make_alias(alias_text="CATL")
    code = make_alias(alias_text="300750")

    assert repository.save_batch_if_absent([first, duplicate, code]) == 2
    assert repository.save_batch_if_absent([first, code]) == 0

    assert repository.find_by_entity("ENT_STOCK_300750.SZ") == [first, code]


def test_reference_repository_protocol_is_usable_for_in_memory() -> None:
    repository: ReferenceRepository = InMemoryReferenceRepository()

    assert repository.find_unresolved() == []


def test_in_memory_reference_repository_saves_and_gets_reference() -> None:
    repository = InMemoryReferenceRepository()
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")

    repository.save(reference)

    assert repository.get("ref-1") == reference


def test_in_memory_reference_repository_deletes_reference() -> None:
    repository = InMemoryReferenceRepository()
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")

    repository.save(reference)
    repository.delete("ref-1")

    assert repository.get("ref-1") is None


def test_in_memory_reference_repository_returns_none_for_missing_reference() -> None:
    repository = InMemoryReferenceRepository()

    assert repository.get("missing") is None


def test_in_memory_reference_repository_filters_unresolved_references() -> None:
    repository = InMemoryReferenceRepository()
    resolved = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    unresolved = make_reference("ref-2", None)

    repository.save(resolved)
    repository.save(unresolved)

    assert repository.find_unresolved() == [unresolved]


def test_in_memory_reference_repository_upserts_by_reference_id() -> None:
    repository = InMemoryReferenceRepository()
    unresolved = make_reference("ref-1", None)
    resolved = make_reference("ref-1", "ENT_STOCK_300750.SZ")

    repository.save(unresolved)
    repository.save(resolved)

    assert repository.get("ref-1") == resolved
    assert repository.find_unresolved() == []


def test_in_memory_resolution_audit_reference_repository_saves_reference_and_case() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    repository = InMemoryResolutionAuditReferenceRepository(case_repo)
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    case = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    repository.save_resolution(reference, case)

    assert repository.get("ref-1") == reference
    assert case_repo.get("case-1") == case


def test_resolution_audit_reference_repository_protocol_is_usable_for_in_memory() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    repository: ResolutionAuditReferenceRepository = (
        InMemoryResolutionAuditReferenceRepository(case_repo)
    )
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    case = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    repository.save_resolution(reference, case)

    assert repository.get("ref-1") == reference
    assert case_repo.get("case-1") == case
    assert repository.owns_resolution_case_repository(case_repo) is True
    assert (
        repository.owns_resolution_case_repository(InMemoryResolutionCaseRepository())
        is False
    )


def test_in_memory_resolution_audit_repository_stages_case_before_reference() -> None:
    case_repo = FailingResolutionCaseRepository()
    repository = InMemoryResolutionAuditReferenceRepository(case_repo)
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    case = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    try:
        repository.save_resolution(reference, case)
    except RuntimeError as exc:
        assert str(exc) == "case persistence failed"
    else:
        raise AssertionError("case persistence failure should propagate")

    assert repository.get("ref-1") is None
    assert case_repo.get("case-1") is None
    assert case_repo.find_by_reference("ref-1") == []


def test_in_memory_resolution_audit_repository_rolls_back_case_write_failure() -> None:
    case_repo = FailingCaseWriteRepository()
    repository = InMemoryResolutionAuditReferenceRepository(case_repo)
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    case = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    try:
        repository.save_resolution(reference, case)
    except RuntimeError as exc:
        assert str(exc) == "case write failed"
    else:
        raise AssertionError("case write failure should propagate")

    assert repository.get("ref-1") is None
    assert case_repo.get("case-1") is None
    assert case_repo.find_by_reference("ref-1") == []


def test_in_memory_resolution_audit_repository_rejects_mismatched_case() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    repository = InMemoryResolutionAuditReferenceRepository(case_repo)
    reference = make_reference("ref-1", "ENT_STOCK_300750.SZ")
    case = make_case("case-1", "other-ref", "ENT_STOCK_300750.SZ")

    try:
        repository.save_resolution(reference, case)
    except ValueError as exc:
        assert "reference_id" in str(exc)
    else:
        raise AssertionError("mismatched audit records should fail")

    assert repository.get("ref-1") is None
    assert case_repo.get("case-1") is None


def test_resolution_case_repository_protocol_is_usable_for_in_memory() -> None:
    repository: ResolutionCaseRepository = InMemoryResolutionCaseRepository()

    assert repository.find_by_reference("missing") == []


def test_in_memory_resolution_case_repository_saves_and_gets_case() -> None:
    repository = InMemoryResolutionCaseRepository()
    case = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    repository.save(case)

    assert repository.get("case-1") == case


def test_in_memory_resolution_case_repository_returns_none_for_missing_case() -> None:
    repository = InMemoryResolutionCaseRepository()

    assert repository.get("missing") is None


def test_in_memory_resolution_case_repository_finds_by_reference() -> None:
    repository = InMemoryResolutionCaseRepository()
    first = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")
    second = make_case("case-2", "ref-1", None)
    other = make_case("case-3", "ref-2", "ENT_STOCK_600519.SH")

    repository.save(first)
    repository.save(second)
    repository.save(other)

    assert repository.find_by_reference("ref-1") == [first, second]


def test_in_memory_resolution_case_repository_upserts_by_case_id() -> None:
    repository = InMemoryResolutionCaseRepository()
    original = make_case("case-1", "ref-1", None)
    updated = make_case("case-1", "ref-1", "ENT_STOCK_300750.SZ")

    repository.save(original)
    repository.save(updated)

    assert repository.get("case-1") == updated
    assert repository.find_by_reference("ref-1") == [updated]


def test_review_repository_protocol_is_usable_for_in_memory() -> None:
    repository: ReviewRepository = InMemoryReviewRepository()

    assert repository.list_by_status(REVIEW_STATUS_PENDING) == []


def test_in_memory_review_repository_saves_and_finds_queue_items() -> None:
    repository = InMemoryReviewRepository()
    item = make_queue_item("queue-1", "ref-1")

    repository.save(item)

    assert repository.get("queue-1") == item
    assert repository.find_by_reference("ref-1") == item
    assert repository.list_by_status(REVIEW_STATUS_PENDING) == [item]


def test_in_memory_review_repository_keeps_reference_id_idempotent() -> None:
    repository = InMemoryReviewRepository()
    first = make_queue_item("queue-1", "ref-1")
    duplicate = make_queue_item("queue-2", "ref-1")

    repository.save(first)
    repository.save(duplicate)

    assert repository.find_by_reference("ref-1") == first
    assert repository.get("queue-2") is None
    assert repository.list_by_status(REVIEW_STATUS_PENDING) == [first]


def test_in_memory_review_repository_claims_once() -> None:
    repository = InMemoryReviewRepository()
    item = make_queue_item("queue-1", "ref-1")
    repository.save(item)

    claimed = repository.claim("queue-1", "reviewer-a")

    assert claimed.status == REVIEW_STATUS_CLAIMED
    assert claimed.claimed_by == "reviewer-a"
    assert repository.claim("queue-1", "reviewer-a") == claimed
    with pytest.raises(ReviewStateError):
        repository.claim("queue-1", "reviewer-b")


def test_in_memory_review_repository_refuses_terminal_claims() -> None:
    repository = InMemoryReviewRepository()
    item = make_queue_item("queue-1", "ref-1").model_copy(
        update={"status": REVIEW_STATUS_REJECTED}
    )
    repository.save(item)

    with pytest.raises(ReviewStateError):
        repository.claim("queue-1", "reviewer-a")


def test_in_memory_review_repository_complete_decision_is_atomic() -> None:
    repository = InMemoryReviewRepository()
    item = make_queue_item("queue-1", "ref-1")
    repository.save(item)
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    alias_repo = InMemoryAliasRepository()

    def build_records(current: UnresolvedQueueItem):
        return (
            make_reference(current.reference_id, "ENT_STOCK_300750.SZ"),
            make_case("case-review", current.reference_id, "ENT_STOCK_300750.SZ"),
            None,
        )

    completed, reference, case = repository.complete_decision(
        "queue-1",
        REVIEW_STATUS_PROMOTED,
        build_records,
        audit_writer=audit_writer,
        alias_repo=alias_repo,
    )

    assert completed.status == REVIEW_STATUS_PROMOTED
    assert completed.decided_at is not None
    assert audit_writer.get("ref-1") == reference
    assert case_repo.get("case-review") == case
    with pytest.raises(ReviewStateError):
        repository.complete_decision(
            "queue-1",
            REVIEW_STATUS_REJECTED,
            build_records,
            audit_writer=audit_writer,
            alias_repo=alias_repo,
        )
    assert len(case_repo.find_by_reference("ref-1")) == 1


def test_in_memory_review_repository_complete_decision_rolls_back_on_save_failure() -> None:
    repository = FailingTerminalReviewRepository()
    item = make_queue_item("queue-1", "ref-1")
    repository.save(item)
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    alias_repo = InMemoryAliasRepository()

    def build_records(current: UnresolvedQueueItem):
        return (
            make_reference(current.reference_id, "ENT_STOCK_300750.SZ"),
            make_case("case-review", current.reference_id, "ENT_STOCK_300750.SZ"),
            None,
        )

    with pytest.raises(RuntimeError, match="terminal save failed"):
        repository.complete_decision(
            "queue-1",
            REVIEW_STATUS_PROMOTED,
            build_records,
            audit_writer=audit_writer,
            alias_repo=alias_repo,
        )

    assert repository.get("queue-1") == item
    assert audit_writer.get("ref-1") is None
    assert case_repo.find_by_reference("ref-1") == []


class FailingResolutionCaseRepository(InMemoryResolutionCaseRepository):
    def _validate_save(self, case: ResolutionCase) -> None:
        raise RuntimeError("case persistence failed")


class FailingCaseWriteRepository(InMemoryResolutionCaseRepository):
    def _save_unchecked(self, case: ResolutionCase) -> None:
        raise RuntimeError("case write failed")


class FailingTerminalReviewRepository(InMemoryReviewRepository):
    def _save_terminal_unchecked(self, item: UnresolvedQueueItem) -> None:
        raise RuntimeError("terminal save failed")


def make_queue_item(queue_item_id: str, reference_id: str) -> UnresolvedQueueItem:
    return UnresolvedQueueItem(
        queue_item_id=queue_item_id,
        reference_id=reference_id,
        raw_mention_text="Unknown Corp",
        source_context={"source": "unit-test"},
        reference_created_at=REFERENCE_CREATED_AT,
        candidate_entity_ids=[],
        status=REVIEW_STATUS_PENDING,
    )
