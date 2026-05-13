import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import entity_registry
from entity_registry.batch import BatchResolutionReport
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityStatus,
    EntityType,
    FinalStatus,
    ResolutionMethod,
)
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution_types import (
    BatchResolutionJob,
    MentionResolutionResult,
)
from entity_registry.review import (
    REVIEW_STATUS_CLAIMED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_PROMOTED,
    REVIEW_STATUS_REJECTED,
    ManualReviewDecision,
    ResolutionAuditPayload,
    ReviewNotFoundError,
    ReviewStateError,
    UnresolvedQueueItem,
    claim_review_item,
    enqueue_batch_manual_review,
    enqueue_unresolved_reference,
    get_resolution_audit_payload,
    submit_manual_review_decision,
)
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
    InMemoryReviewRepository,
)

REFERENCE_CREATED_AT = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)


def test_review_public_exports_and_signatures() -> None:
    assert entity_registry.UnresolvedQueueItem is UnresolvedQueueItem
    assert entity_registry.ResolutionAuditPayload is ResolutionAuditPayload
    assert entity_registry.InMemoryReviewRepository is InMemoryReviewRepository

    signature = inspect.signature(enqueue_unresolved_reference)
    assert list(signature.parameters) == ["reference", "review_repo", "case_repo"]


def test_queue_item_round_trips_and_validates_required_fields() -> None:
    item = UnresolvedQueueItem(
        queue_item_id="queue-1",
        reference_id="ref-1",
        raw_mention_text="宁德时代",
        source_context={"document_id": "doc-1"},
        candidate_entity_ids=["ENT_STOCK_300750.SZ"],
        status=REVIEW_STATUS_PENDING,
    )

    restored = UnresolvedQueueItem.model_validate(item.model_dump(mode="json"))

    assert restored == item
    with pytest.raises(ValidationError):
        UnresolvedQueueItem(
            queue_item_id="queue-2",
            reference_id="",
            raw_mention_text="宁德时代",
            source_context={},
            candidate_entity_ids=[],
            status=REVIEW_STATUS_PENDING,
        )
    with pytest.raises(ValidationError):
        UnresolvedQueueItem(
            queue_item_id="queue-2",
            reference_id="ref-2",
            raw_mention_text=" ",
            source_context={},
            candidate_entity_ids=[],
            status=REVIEW_STATUS_PENDING,
        )


def test_enqueue_unresolved_reference_uses_latest_case_candidates_idempotently() -> None:
    review_repo = InMemoryReviewRepository()
    case_repo = InMemoryResolutionCaseRepository()
    reference = make_reference("ref-ah", "宁德时代")
    old_case = make_case(
        "case-old",
        "ref-ah",
        ["ENT_STOCK_300750.SZ"],
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
    )
    new_case = make_case(
        "case-new",
        "ref-ah",
        ["ENT_STOCK_300750.SZ", "ENT_STOCK_03750.HK"],
        created_at=datetime(2026, 4, 16, tzinfo=UTC),
    )
    case_repo.save(old_case)
    case_repo.save(new_case)

    first = enqueue_unresolved_reference(
        reference,
        review_repo=review_repo,
        case_repo=case_repo,
    )
    second = enqueue_unresolved_reference(
        reference,
        review_repo=review_repo,
        case_repo=case_repo,
    )

    assert second == first
    assert review_repo.list_by_status(REVIEW_STATUS_PENDING) == [first]
    assert first.candidate_entity_ids == [
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    ]
    assert first.raw_mention_text == "宁德时代"


def test_enqueue_rejects_resolved_references_and_missing_cases() -> None:
    review_repo = InMemoryReviewRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(ValueError):
        enqueue_unresolved_reference(
            make_reference(
                "ref-resolved",
                "贵州茅台",
                resolved_entity_id="ENT_STOCK_600519.SH",
            ),
            review_repo=review_repo,
            case_repo=case_repo,
        )

    with pytest.raises(ReviewNotFoundError, match="ref-missing-case"):
        enqueue_unresolved_reference(
            make_reference("ref-missing-case", "未知公司"),
            review_repo=review_repo,
            case_repo=case_repo,
        )


def test_batch_manual_review_intake_reads_references_and_cases() -> None:
    reference_repo = InMemoryReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()
    review_repo = InMemoryReviewRepository()
    reference = make_reference("ref-manual", "Ambiguous Co")
    reference_repo.save(reference)
    case_repo.save(
        make_case(
            "case-manual",
            "ref-manual",
            ["ENT_STOCK_000001.SZ", "ENT_STOCK_000002.SZ"],
        )
    )
    report = make_report(["ref-manual"])

    items = enqueue_batch_manual_review(
        report,
        reference_repo=reference_repo,
        case_repo=case_repo,
        review_repo=review_repo,
    )

    assert [item.reference_id for item in items] == ["ref-manual"]
    assert items[0].candidate_entity_ids == [
        "ENT_STOCK_000001.SZ",
        "ENT_STOCK_000002.SZ",
    ]


def test_batch_manual_review_intake_reports_missing_reference_or_case() -> None:
    reference_repo = InMemoryReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()
    review_repo = InMemoryReviewRepository()

    with pytest.raises(ReviewNotFoundError, match="ref-missing"):
        enqueue_batch_manual_review(
            make_report(["ref-missing"]),
            reference_repo=reference_repo,
            case_repo=case_repo,
            review_repo=review_repo,
        )

    reference_repo.save(make_reference("ref-no-case", "Unknown"))
    with pytest.raises(ReviewNotFoundError, match="ref-no-case"):
        enqueue_batch_manual_review(
            make_report(["ref-no-case"]),
            reference_repo=reference_repo,
            case_repo=case_repo,
            review_repo=review_repo,
        )


def test_claim_review_item_is_idempotent_for_same_reviewer_and_blocks_others() -> None:
    review_repo, item = queued_item()

    claimed = claim_review_item(
        item.queue_item_id,
        "reviewer-a",
        review_repo=review_repo,
    )
    repeated = claim_review_item(
        item.queue_item_id,
        "reviewer-a",
        review_repo=review_repo,
    )

    assert claimed.status == REVIEW_STATUS_CLAIMED
    assert claimed.claimed_by == "reviewer-a"
    assert repeated == claimed
    with pytest.raises(ReviewStateError):
        claim_review_item(item.queue_item_id, "reviewer-b", review_repo=review_repo)


def test_concurrent_claim_allows_only_one_reviewer() -> None:
    review_repo, item = queued_item()
    barrier = threading.Barrier(2)

    def attempt_claim(reviewer_id: str) -> tuple[str, str]:
        barrier.wait()
        try:
            claimed = claim_review_item(
                item.queue_item_id,
                reviewer_id,
                review_repo=review_repo,
            )
        except ReviewStateError as exc:
            return ("error", str(exc))
        return ("ok", claimed.claimed_by or "")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(attempt_claim, ["reviewer-a", "reviewer-b"])
        )

    assert [status for status, _ in results].count("ok") == 1
    assert [status for status, _ in results].count("error") == 1
    assert review_repo.get(item.queue_item_id).claimed_by in {
        "reviewer-a",
        "reviewer-b",
    }


def test_reject_decision_writes_unresolved_audit_and_marks_rejected() -> None:
    review_repo, item = queued_item()
    claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    decision = ManualReviewDecision(
        selected_entity_id=None,
        confidence=None,
        rationale="no listed entity match",
    )

    payload = submit_manual_review_decision(
        item.queue_item_id,
        decision,
        review_repo=review_repo,
        entity_repo=InMemoryEntityRepository(),
        alias_repo=InMemoryAliasRepository(),
        audit_writer=audit_writer,
    )

    updated_item = review_repo.get(item.queue_item_id)
    saved_reference = audit_writer.get("ref-review")
    saved_case = case_repo.find_by_reference("ref-review")[0]
    assert payload.unresolved is True
    assert payload.entity_reference == saved_reference
    assert saved_reference.resolved_entity_id is None
    assert saved_reference.resolution_method is ResolutionMethod.UNRESOLVED
    assert saved_case.decision_type is DecisionType.MANUAL_REVIEW
    assert saved_case.selected_entity_id is None
    assert updated_item.status == REVIEW_STATUS_REJECTED
    assert updated_item.decided_at is not None


def test_manual_review_decision_rejects_missing_reference_created_at() -> None:
    review_repo, item = queued_item()
    missing_timestamp_item = item.model_copy(
        update={"reference_created_at": None}
    )
    review_repo.save(missing_timestamp_item)
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(ReviewStateError, match="reference_created_at"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id=None,
                confidence=None,
                rationale="cannot audit without original capture timestamp",
            ),
            review_repo=review_repo,
            entity_repo=InMemoryEntityRepository(),
            alias_repo=InMemoryAliasRepository(),
            audit_writer=audit_writer,
        )

    unchanged = review_repo.get(item.queue_item_id)
    assert unchanged.status == REVIEW_STATUS_PENDING
    assert unchanged.reference_created_at is None
    assert audit_writer.get(item.reference_id) is None
    assert case_repo.find_by_reference(item.reference_id) == []


def test_promote_decision_writes_manual_resolution_for_existing_entity() -> None:
    review_repo, item = queued_item(
        candidate_entity_ids=["ENT_STOCK_300750.SZ", "ENT_STOCK_03750.HK"]
    )
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    entity_repo.save(make_entity("ENT_STOCK_03750.HK"))
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    decision = ManualReviewDecision(
        selected_entity_id="ENT_STOCK_03750.HK",
        confidence=0.92,
        rationale="HK market context",
    )

    payload = submit_manual_review_decision(
        item.queue_item_id,
        decision,
        review_repo=review_repo,
        entity_repo=entity_repo,
        alias_repo=InMemoryAliasRepository(),
        audit_writer=audit_writer,
    )

    saved_reference = audit_writer.get("ref-review")
    saved_case = case_repo.find_by_reference("ref-review")[0]
    assert payload.unresolved is False
    assert saved_reference.resolved_entity_id == "ENT_STOCK_03750.HK"
    assert saved_reference.resolution_method is ResolutionMethod.MANUAL
    assert saved_reference.resolution_confidence == 0.92
    assert saved_case.selected_entity_id == "ENT_STOCK_03750.HK"
    assert saved_case.decision_type is DecisionType.MANUAL_REVIEW
    assert set(saved_case.candidate_entity_ids) == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }
    assert review_repo.get(item.queue_item_id).status == REVIEW_STATUS_PROMOTED


def test_promote_decision_requires_existing_entity_and_does_not_complete_item() -> None:
    review_repo, item = queued_item()

    with pytest.raises(ReviewNotFoundError, match="ENT_STOCK_MISSING.SZ"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id="ENT_STOCK_MISSING.SZ",
                confidence=1.0,
                rationale="reviewer selected entity",
            ),
            review_repo=review_repo,
            entity_repo=InMemoryEntityRepository(),
            alias_repo=InMemoryAliasRepository(),
            audit_writer=InMemoryResolutionAuditReferenceRepository(
                InMemoryResolutionCaseRepository()
            ),
        )

    assert review_repo.get(item.queue_item_id).status == REVIEW_STATUS_PENDING


def test_promote_alias_uses_alias_repository_without_semantic_duplicates() -> None:
    review_repo, item = queued_item(raw_mention_text="宁德时代新能源")
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    alias_repo = InMemoryAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    decision = ManualReviewDecision(
        selected_entity_id="ENT_STOCK_300750.SZ",
        confidence=0.88,
        rationale="reviewer selected A-share listing",
        promote_alias=True,
        alias_type=AliasType.SHORT_NAME,
    )

    submit_manual_review_decision(
        item.queue_item_id,
        decision,
        review_repo=review_repo,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_writer=audit_writer,
    )
    duplicate_item = item.model_copy(
        update={
            "queue_item_id": "queue-duplicate",
            "reference_id": "ref-duplicate",
            "status": REVIEW_STATUS_PENDING,
            "decided_at": None,
        }
    )
    review_repo.save(duplicate_item)
    submit_manual_review_decision(
        duplicate_item.queue_item_id,
        decision,
        review_repo=review_repo,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_writer=audit_writer,
    )

    aliases = alias_repo.find_by_entity("ENT_STOCK_300750.SZ")
    assert len(aliases) == 1
    assert aliases[0].alias_text == "宁德时代新能源"
    assert aliases[0].alias_type is AliasType.SHORT_NAME
    assert aliases[0].source == "manual_review"


def test_audit_writer_failure_leaves_queue_and_alias_unchanged() -> None:
    review_repo, item = queued_item(raw_mention_text="宁德时代新能源")
    claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    alias_repo = InMemoryAliasRepository()

    with pytest.raises(RuntimeError, match="audit failed"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id="ENT_STOCK_300750.SZ",
                confidence=0.9,
                rationale="reviewer selected A-share listing",
                promote_alias=True,
                alias_type=AliasType.SHORT_NAME,
            ),
            review_repo=review_repo,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_writer=FailingAuditWriter(),
        )

    unchanged = review_repo.get(item.queue_item_id)
    assert unchanged.status == REVIEW_STATUS_CLAIMED
    assert unchanged.claimed_by == "reviewer-a"
    assert alias_repo.list_all() == []


def test_alias_failure_rolls_back_audit_and_leaves_queue_decidable() -> None:
    review_repo, item = queued_item(raw_mention_text="宁德时代新能源")
    claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    alias_repo = FailingAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(RuntimeError, match="alias failed"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id="ENT_STOCK_300750.SZ",
                confidence=0.9,
                rationale="reviewer selected A-share listing",
                promote_alias=True,
                alias_type=AliasType.SHORT_NAME,
            ),
            review_repo=review_repo,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_writer=audit_writer,
        )

    unchanged = review_repo.get(item.queue_item_id)
    assert unchanged.status == REVIEW_STATUS_CLAIMED
    assert unchanged.claimed_by == "reviewer-a"
    assert audit_writer.get("ref-review") is None
    assert case_repo.find_by_reference("ref-review") == []
    assert alias_repo.list_all() == []


def test_review_completion_failure_rolls_back_audit_and_alias() -> None:
    review_repo, item = queued_item_with_repository(
        FailingTerminalReviewRepository(),
        raw_mention_text="宁德时代新能源",
    )
    claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    alias_repo = InMemoryAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(RuntimeError, match="review completion failed"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id="ENT_STOCK_300750.SZ",
                confidence=0.9,
                rationale="reviewer selected A-share listing",
                promote_alias=True,
                alias_type=AliasType.SHORT_NAME,
            ),
            review_repo=review_repo,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_writer=audit_writer,
        )

    unchanged = review_repo.get(item.queue_item_id)
    assert unchanged.status == REVIEW_STATUS_CLAIMED
    assert unchanged.claimed_by == "reviewer-a"
    assert audit_writer.get("ref-review") is None
    assert case_repo.find_by_reference("ref-review") == []
    assert alias_repo.list_all() == []


def test_non_in_memory_transactional_repositories_roll_back_alias_failure() -> None:
    review_repo, item = queued_item(raw_mention_text="宁德时代新能源")
    claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    alias_repo = PartiallyFailingTransactionalAliasRepository()
    audit_writer = TransactionalAuditWriter()

    with pytest.raises(RuntimeError, match="alias failed after write"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id="ENT_STOCK_300750.SZ",
                confidence=0.9,
                rationale="reviewer selected A-share listing",
                promote_alias=True,
                alias_type=AliasType.SHORT_NAME,
            ),
            review_repo=review_repo,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_writer=audit_writer,
        )

    unchanged = review_repo.get(item.queue_item_id)
    assert unchanged.status == REVIEW_STATUS_CLAIMED
    assert audit_writer.references == {}
    assert audit_writer.cases == {}
    assert alias_repo.aliases == []


def test_non_transactional_audit_writer_is_rejected_before_side_effects() -> None:
    review_repo, item = queued_item()
    audit_writer = NonTransactionalAuditWriter()

    with pytest.raises(TypeError, match="transactional audit and alias"):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id=None,
                confidence=None,
                rationale="not resolvable",
            ),
            review_repo=review_repo,
            entity_repo=InMemoryEntityRepository(),
            alias_repo=InMemoryAliasRepository(),
            audit_writer=audit_writer,
        )

    assert review_repo.get(item.queue_item_id).status == REVIEW_STATUS_PENDING
    assert audit_writer.references == {}
    assert audit_writer.cases == {}


def test_concurrent_manual_decision_writes_only_one_audit_record() -> None:
    review_repo, item = queued_item(
        candidate_entity_ids=["ENT_STOCK_300750.SZ", "ENT_STOCK_03750.HK"]
    )
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    entity_repo.save(make_entity("ENT_STOCK_03750.HK"))
    alias_repo = InMemoryAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = BlockingAuditWriter(case_repo)

    first = ManualReviewDecision(
        selected_entity_id="ENT_STOCK_300750.SZ",
        confidence=0.91,
        rationale="first reviewer decision",
    )
    second = ManualReviewDecision(
        selected_entity_id="ENT_STOCK_03750.HK",
        confidence=0.88,
        rationale="second reviewer decision",
    )

    def attempt(decision: ManualReviewDecision) -> tuple[str, str | None]:
        try:
            payload = submit_manual_review_decision(
                item.queue_item_id,
                decision,
                review_repo=review_repo,
                entity_repo=entity_repo,
                alias_repo=alias_repo,
                audit_writer=audit_writer,
            )
        except ReviewStateError as exc:
            return ("error", str(exc))
        return ("ok", payload.resolution_case.selected_entity_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_result = executor.submit(attempt, first)
        assert audit_writer.started.wait(timeout=2)
        second_result = executor.submit(attempt, second)
        audit_writer.release.set()
        results = [first_result.result(timeout=2), second_result.result(timeout=2)]

    assert [status for status, _ in results].count("ok") == 1
    assert [status for status, _ in results].count("error") == 1
    assert case_repo.find_by_reference("ref-review")[0].selected_entity_id == (
        "ENT_STOCK_300750.SZ"
    )
    assert len(case_repo.find_by_reference("ref-review")) == 1
    assert audit_writer.save_calls == 1
    assert review_repo.get(item.queue_item_id).status == REVIEW_STATUS_PROMOTED


def test_completed_item_cannot_be_claimed_or_decided_again() -> None:
    review_repo, item = queued_item()
    case_repo = InMemoryResolutionCaseRepository()
    audit_writer = InMemoryResolutionAuditReferenceRepository(case_repo)
    submit_manual_review_decision(
        item.queue_item_id,
        ManualReviewDecision(
            selected_entity_id=None,
            confidence=None,
            rationale="not resolvable",
        ),
        review_repo=review_repo,
        entity_repo=InMemoryEntityRepository(),
        alias_repo=InMemoryAliasRepository(),
        audit_writer=audit_writer,
    )

    with pytest.raises(ReviewStateError):
        claim_review_item(item.queue_item_id, "reviewer-a", review_repo=review_repo)
    with pytest.raises(ReviewStateError):
        submit_manual_review_decision(
            item.queue_item_id,
            ManualReviewDecision(
                selected_entity_id=None,
                confidence=None,
                rationale="second decision",
            ),
            review_repo=review_repo,
            entity_repo=InMemoryEntityRepository(),
            alias_repo=InMemoryAliasRepository(),
            audit_writer=audit_writer,
        )


def test_get_resolution_audit_payload_uses_latest_case_and_includes_queue_item() -> None:
    reference_repo = InMemoryReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()
    review_repo = InMemoryReviewRepository()
    reference = make_reference("ref-audit", "Unknown")
    old_case = make_case(
        "case-old",
        "ref-audit",
        [],
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
    )
    new_case = make_case(
        "case-new",
        "ref-audit",
        ["ENT_STOCK_600519.SH"],
        created_at=datetime(2026, 4, 16, tzinfo=UTC),
    )
    reference_repo.save(reference)
    case_repo.save(old_case)
    case_repo.save(new_case)
    item = enqueue_unresolved_reference(
        reference,
        review_repo=review_repo,
        case_repo=case_repo,
    )

    payload = get_resolution_audit_payload(
        "ref-audit",
        reference_repo=reference_repo,
        case_repo=case_repo,
        review_repo=review_repo,
    )

    assert payload.entity_reference == reference
    assert payload.resolution_case == new_case
    assert payload.unresolved is True
    assert payload.queue_item == item


def test_manual_review_decision_preserves_original_reference_created_at() -> None:
    original_created_at = datetime(2026, 4, 1, 8, 30, tzinfo=UTC)
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    review_repo = InMemoryReviewRepository()
    entity_repo = InMemoryEntityRepository()
    entity_repo.save(make_entity("ENT_STOCK_300750.SZ"))
    reference = make_reference(
        "ref-original-created-at",
        "宁德时代新能源",
        created_at=original_created_at,
    )
    reference_repo.save(reference)
    case_repo.save(
        make_case(
            "case-original-created-at",
            "ref-original-created-at",
            ["ENT_STOCK_300750.SZ"],
        )
    )

    (item,) = enqueue_batch_manual_review(
        make_report(["ref-original-created-at"]),
        reference_repo=reference_repo,
        case_repo=case_repo,
        review_repo=review_repo,
    )
    claimed = claim_review_item(
        item.queue_item_id,
        "reviewer-a",
        review_repo=review_repo,
    )
    decision_payload = submit_manual_review_decision(
        item.queue_item_id,
        ManualReviewDecision(
            selected_entity_id="ENT_STOCK_300750.SZ",
            confidence=0.93,
            rationale="reviewer selected captured mention",
        ),
        review_repo=review_repo,
        entity_repo=entity_repo,
        alias_repo=InMemoryAliasRepository(),
        audit_writer=reference_repo,
    )
    audit_payload = get_resolution_audit_payload(
        "ref-original-created-at",
        reference_repo=reference_repo,
        case_repo=case_repo,
        review_repo=review_repo,
    )

    assert item.reference_created_at == original_created_at
    assert claimed.reference_created_at == original_created_at
    assert decision_payload.entity_reference.created_at == original_created_at
    assert reference_repo.get("ref-original-created-at").created_at == (
        original_created_at
    )
    assert audit_payload.entity_reference.created_at == original_created_at
    assert audit_payload.queue_item.reference_created_at == original_created_at
    assert audit_payload.queue_item.decided_at is not None


def test_review_module_has_no_provider_sdk_or_reasoner_runtime_imports() -> None:
    text = Path("src/entity_registry/review.py").read_text(encoding="utf-8")

    for forbidden in (
        "openai",
        "anthropic",
        "google.generativeai",
        "ReasonerRuntimeClient",
    ):
        assert forbidden not in text


def queued_item(
    *,
    raw_mention_text: str = "宁德时代",
    candidate_entity_ids: list[str] | None = None,
) -> tuple[InMemoryReviewRepository, UnresolvedQueueItem]:
    review_repo = InMemoryReviewRepository()
    item = UnresolvedQueueItem(
        queue_item_id="queue-review",
        reference_id="ref-review",
        raw_mention_text=raw_mention_text,
        source_context={"document_id": "doc-review"},
        reference_created_at=REFERENCE_CREATED_AT,
        candidate_entity_ids=(
            ["ENT_STOCK_300750.SZ"]
            if candidate_entity_ids is None
            else candidate_entity_ids
        ),
        status=REVIEW_STATUS_PENDING,
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
        updated_at=datetime(2026, 4, 15, tzinfo=UTC),
    )
    review_repo.save(item)
    return review_repo, item


def queued_item_with_repository(
    review_repo: InMemoryReviewRepository,
    *,
    raw_mention_text: str = "宁德时代",
    candidate_entity_ids: list[str] | None = None,
) -> tuple[InMemoryReviewRepository, UnresolvedQueueItem]:
    item = UnresolvedQueueItem(
        queue_item_id="queue-review",
        reference_id="ref-review",
        raw_mention_text=raw_mention_text,
        source_context={"document_id": "doc-review"},
        reference_created_at=REFERENCE_CREATED_AT,
        candidate_entity_ids=(
            ["ENT_STOCK_300750.SZ"]
            if candidate_entity_ids is None
            else candidate_entity_ids
        ),
        status=REVIEW_STATUS_PENDING,
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
        updated_at=datetime(2026, 4, 15, tzinfo=UTC),
    )
    review_repo.save(item)
    return review_repo, item


def make_reference(
    reference_id: str,
    raw_mention_text: str,
    *,
    resolved_entity_id: str | None = None,
    created_at: datetime | None = None,
) -> EntityReference:
    return EntityReference(
        reference_id=reference_id,
        raw_mention_text=raw_mention_text,
        source_context={"source": "unit-test"},
        resolved_entity_id=resolved_entity_id,
        resolution_method=(
            ResolutionMethod.UNRESOLVED
            if resolved_entity_id is None
            else ResolutionMethod.DETERMINISTIC
        ),
        resolution_confidence=None if resolved_entity_id is None else 1.0,
        created_at=created_at or datetime(2026, 4, 15, tzinfo=UTC),
    )


def make_case(
    case_id: str,
    reference_id: str,
    candidate_entity_ids: list[str],
    *,
    created_at: datetime | None = None,
) -> ResolutionCase:
    return ResolutionCase(
        case_id=case_id,
        reference_id=reference_id,
        candidate_entity_ids=candidate_entity_ids,
        selected_entity_id=None,
        decision_type=DecisionType.MANUAL_REVIEW,
        decision_rationale="manual review required",
        created_at=created_at or datetime(2026, 4, 15, tzinfo=UTC),
    )


def make_entity(entity_id: str) -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name=entity_id,
        status=EntityStatus.ACTIVE,
        anchor_code=entity_id.removeprefix("ENT_STOCK_"),
    )


def make_report(reference_ids: list[str]) -> BatchResolutionReport:
    return BatchResolutionReport(
        job=BatchResolutionJob(
            job_id="job-review",
            reference_ids=reference_ids,
            status="completed",
        ),
        groups=[],
        outcomes=[
            make_unresolved_outcome(reference_id)
            for reference_id in reference_ids
        ],
        resolved_reference_ids=[],
        unresolved_reference_ids=reference_ids,
        manual_review_reference_ids=reference_ids,
        errors=[],
    )


def make_unresolved_outcome(reference_id: str):
    from entity_registry.batch import BatchResolutionOutcome

    return BatchResolutionOutcome(
        source_reference_id=reference_id,
        result=MentionResolutionResult(
            raw_mention_text=reference_id,
            resolved_entity_id=None,
            resolution_method=ResolutionMethod.UNRESOLVED,
            resolution_confidence=None,
        ),
        final_status=FinalStatus.UNRESOLVED,
        error=None,
    )


class FailingAuditWriter:
    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        raise RuntimeError("audit failed")

    def rollback_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        return None


class FailingAliasRepository(InMemoryAliasRepository):
    def save_if_absent(self, alias) -> bool:
        raise RuntimeError("alias failed")


class FailingTerminalReviewRepository(InMemoryReviewRepository):
    def _save_terminal_unchecked(self, item: UnresolvedQueueItem) -> None:
        raise RuntimeError("review completion failed")


class TransactionalAuditWriter:
    def __init__(self) -> None:
        self.references: dict[str, EntityReference] = {}
        self.cases: dict[str, ResolutionCase] = {}

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        self.references[reference.reference_id] = reference
        self.cases[case.case_id] = case

    def rollback_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        self.references.pop(reference.reference_id, None)
        self.cases.pop(case.case_id, None)


class NonTransactionalAuditWriter:
    def __init__(self) -> None:
        self.references: dict[str, EntityReference] = {}
        self.cases: dict[str, ResolutionCase] = {}

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        self.references[reference.reference_id] = reference
        self.cases[case.case_id] = case


class PartiallyFailingTransactionalAliasRepository:
    def __init__(self) -> None:
        self.aliases: list = []

    def find_by_text(self, alias_text: str) -> list:
        return [alias for alias in self.aliases if alias.alias_text == alias_text]

    def find_by_entity(self, entity_id: str) -> list:
        return [
            alias
            for alias in self.aliases
            if alias.canonical_entity_id == entity_id
        ]

    def list_all(self) -> list:
        return list(self.aliases)

    def save(self, alias) -> None:
        self.save_if_absent(alias)

    def save_if_absent(self, alias) -> bool:
        self.aliases.append(alias)
        raise RuntimeError("alias failed after write")

    def save_batch(self, aliases: list) -> None:
        for alias in aliases:
            self.save(alias)

    def save_batch_if_absent(self, aliases: list) -> int:
        for alias in aliases:
            self.save_if_absent(alias)
        return len(aliases)

    def rollback_alias(self, alias) -> None:
        self.aliases = [
            existing
            for existing in self.aliases
            if existing != alias
        ]


class BlockingAuditWriter(InMemoryResolutionAuditReferenceRepository):
    def __init__(self, case_repo: InMemoryResolutionCaseRepository) -> None:
        super().__init__(case_repo)
        self.started = threading.Event()
        self.release = threading.Event()
        self.save_calls = 0

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        self.save_calls += 1
        self.started.set()
        assert self.release.wait(timeout=2)
        super().save_resolution(reference, case)
