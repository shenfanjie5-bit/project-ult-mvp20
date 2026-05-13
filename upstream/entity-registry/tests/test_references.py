import inspect
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import entity_registry
from entity_registry.core import DecisionType, FinalStatus, ResolutionMethod
from entity_registry.references import (
    EntityReference,
    ResolutionCase,
    record_resolution_case,
    register_unresolved_reference_into,
)
from entity_registry.resolution_types import (
    BatchResolutionJob,
    MentionCandidateSet,
    ResolutionContext,
    ResolutionDecision,
)
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_entity_reference_builds_resolved_state() -> None:
    reference = EntityReference(
        reference_id="ref-1",
        raw_mention_text="CATL",
        source_context={"source": "fixture"},
        resolved_entity_id="ENT_STOCK_300750.SZ",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
    )

    assert reference.resolved_entity_id == "ENT_STOCK_300750.SZ"
    assert reference.resolution_method is ResolutionMethod.DETERMINISTIC


def test_register_unresolved_reference_public_signature_matches_contract() -> None:
    signature = inspect.signature(entity_registry.register_unresolved_reference)

    assert list(signature.parameters) == ["reference"]


def test_entity_reference_builds_unresolved_state() -> None:
    reference = EntityReference(
        reference_id="ref-2",
        raw_mention_text="Unknown Corp",
        source_context={"source": "fixture"},
        resolved_entity_id=None,
        resolution_method=ResolutionMethod.UNRESOLVED,
        resolution_confidence=None,
    )

    assert reference.resolved_entity_id is None
    assert reference.resolution_method is ResolutionMethod.UNRESOLVED


def test_entity_reference_rejects_unresolved_id_with_resolved_method() -> None:
    with pytest.raises(ValidationError):
        EntityReference(
            reference_id="ref-invalid",
            raw_mention_text="Unknown Corp",
            source_context={"source": "fixture"},
            resolved_entity_id=None,
            resolution_method=ResolutionMethod.DETERMINISTIC,
            resolution_confidence=None,
        )


def test_entity_reference_rejects_resolved_method_without_confidence() -> None:
    with pytest.raises(ValidationError):
        EntityReference(
            reference_id="ref-invalid",
            raw_mention_text="CATL",
            source_context={"source": "fixture"},
            resolved_entity_id="ENT_STOCK_300750.SZ",
            resolution_method=ResolutionMethod.DETERMINISTIC,
            resolution_confidence=None,
        )


def test_entity_reference_rejects_unresolved_method_with_resolution_payload() -> None:
    with pytest.raises(ValidationError):
        EntityReference(
            reference_id="ref-invalid",
            raw_mention_text="CATL",
            source_context={"source": "fixture"},
            resolved_entity_id="ENT_STOCK_300750.SZ",
            resolution_method=ResolutionMethod.UNRESOLVED,
            resolution_confidence=None,
        )


def test_entity_reference_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        EntityReference(
            reference_id="ref-invalid",
            raw_mention_text="CATL",
            source_context={"source": "fixture"},
            resolved_entity_id="ENT_STOCK_300750.SZ",
            resolution_method=ResolutionMethod.DETERMINISTIC,
            resolution_confidence=1.1,
        )


def test_register_unresolved_reference_into_saves_normalized_reference() -> None:
    repository = InMemoryReferenceRepository()

    reference = register_unresolved_reference_into(
        {
            "reference_id": "ref-unresolved",
            "raw_mention_text": "Unknown Corp",
            "source_context": {"source": "fixture"},
        },
        repository,
    )

    assert repository.get("ref-unresolved") == reference
    assert reference.resolved_entity_id is None
    assert reference.resolution_method is ResolutionMethod.UNRESOLVED
    assert reference.resolution_confidence is None


@pytest.mark.parametrize(
    "payload",
    [
        {"resolved_entity_id": "ENT_STOCK_300750.SZ"},
        {"resolution_method": ResolutionMethod.DETERMINISTIC},
        {"resolution_confidence": 1.0},
    ],
)
def test_register_unresolved_reference_into_rejects_conflicting_payload(
    payload: dict[str, object],
) -> None:
    repository = InMemoryReferenceRepository()
    base_payload = {
        "reference_id": "ref-conflict",
        "raw_mention_text": "Unknown Corp",
        "source_context": {"source": "fixture"},
    }
    base_payload.update(payload)

    with pytest.raises(ValueError):
        register_unresolved_reference_into(base_payload, repository)

    assert repository.get("ref-conflict") is None


def test_public_register_unresolved_reference_uses_configured_repository() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    contract_case = entity_registry.register_unresolved_reference(
        {
            "reference_id": "ref-public",
            "raw_mention_text": "Unknown Corp",
            "source_context": {"source": "fixture"},
        }
    )

    reference = reference_repo.get("ref-public")
    cases = case_repo.find_by_reference("ref-public")
    assert reference is not None
    assert len(cases) == 1
    assert reference.resolution_method is ResolutionMethod.UNRESOLVED
    assert contract_case.resolution_case_id == cases[0].case_id
    assert contract_case.decision is entity_registry.EntityResolutionDecision.UNRESOLVED
    assert contract_case.evidence_refs == ["ref-public"]


def test_public_register_unresolved_reference_rejects_non_atomic_audit_repository() -> None:
    reference_repo = InMemoryReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    with pytest.raises(RuntimeError, match="save_resolution"):
        entity_registry.register_unresolved_reference(
            {
                "reference_id": "ref-non-atomic",
                "raw_mention_text": "Unknown Corp",
                "source_context": {"source": "fixture"},
            }
        )

    assert reference_repo.get("ref-non-atomic") is None
    assert case_repo.find_by_reference("ref-non-atomic") == []


def test_public_register_unresolved_reference_rolls_back_case_write_failure() -> None:
    case_repo = FailingCaseWriteRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    entity_registry.configure_default_repositories(
        InMemoryEntityRepository(),
        InMemoryAliasRepository(),
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    with pytest.raises(RuntimeError, match="case write failed"):
        entity_registry.register_unresolved_reference(
            {
                "reference_id": "ref-case-failure",
                "raw_mention_text": "Unknown Corp",
                "source_context": {"source": "fixture"},
            }
        )

    assert reference_repo.get("ref-case-failure") is None
    assert case_repo.find_by_reference("ref-case-failure") == []


def test_register_unresolved_reference_into_rejects_resolved_model() -> None:
    repository = InMemoryReferenceRepository()
    reference = EntityReference(
        reference_id="ref-resolved",
        raw_mention_text="CATL",
        source_context={"source": "fixture"},
        resolved_entity_id="ENT_STOCK_300750.SZ",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )

    with pytest.raises(ValueError):
        register_unresolved_reference_into(reference, repository)


def test_entity_reference_round_trips_without_data_loss() -> None:
    reference = EntityReference(
        reference_id="ref-3",
        raw_mention_text="CATL",
        source_context={"document_id": "doc-1", "offset": 3},
        resolved_entity_id="ENT_STOCK_300750.SZ",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=0.98,
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
    )

    restored = EntityReference.model_validate(reference.model_dump(mode="json"))

    assert restored == reference


def test_resolution_case_builds() -> None:
    case = ResolutionCase(
        case_id="case-1",
        reference_id="ref-1",
        candidate_entity_ids=["ENT_STOCK_300750.SZ"],
        selected_entity_id="ENT_STOCK_300750.SZ",
        decision_type=DecisionType.AUTO,
        decision_rationale="single deterministic hit",
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
    )

    assert case.selected_entity_id == "ENT_STOCK_300750.SZ"
    assert case.decision_type is DecisionType.AUTO


def test_resolution_case_supports_unresolved_selection() -> None:
    case = ResolutionCase(
        case_id="case-2",
        reference_id="ref-2",
        candidate_entity_ids=[],
        selected_entity_id=None,
        decision_type=DecisionType.MANUAL_REVIEW,
        decision_rationale="no candidates",
    )

    assert case.selected_entity_id is None
    assert case.candidate_entity_ids == []


def test_record_resolution_case_saves_and_returns_case() -> None:
    repository = InMemoryResolutionCaseRepository()
    case = ResolutionCase(
        case_id="case-3",
        reference_id="ref-3",
        candidate_entity_ids=[],
        selected_entity_id=None,
        decision_type=DecisionType.AUTO,
        decision_rationale="no deterministic candidates",
    )

    saved_case = record_resolution_case(case, repository)

    assert saved_case == case
    assert repository.get("case-3") == case


def test_mention_candidate_set_builds_and_serializes() -> None:
    candidate_set = MentionCandidateSet(
        raw_mention_text="CATL",
        deterministic_hits=["ENT_STOCK_300750.SZ"],
        fuzzy_hits=[],
        llm_required=False,
        final_status=FinalStatus.RESOLVED,
    )

    payload = candidate_set.model_dump(mode="json")

    assert payload["final_status"] == "resolved"
    assert payload["deterministic_hits"] == ["ENT_STOCK_300750.SZ"]


def test_resolution_context_builds() -> None:
    context = ResolutionContext(
        raw_mention_text="CATL",
        document_context="CATL published its annual report",
        source_type="announcement",
        timestamp=datetime(2026, 4, 15, tzinfo=UTC),
    )

    assert context.source_type == "announcement"
    assert context.timestamp == datetime(2026, 4, 15, tzinfo=UTC)


def test_resolution_decision_builds_unresolved_decision() -> None:
    decision = ResolutionDecision(
        selected_entity_id=None,
        method=ResolutionMethod.UNRESOLVED,
        confidence=None,
        rationale="no deterministic or fuzzy candidates",
    )

    assert decision.selected_entity_id is None
    assert decision.method is ResolutionMethod.UNRESOLVED


def test_batch_resolution_job_builds_pending_state() -> None:
    job = BatchResolutionJob(
        job_id="job-1",
        reference_ids=["ref-1", "ref-2"],
        status="pending",
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
        completed_at=None,
    )

    assert job.reference_ids == ["ref-1", "ref-2"]
    assert job.completed_at is None


def test_batch_resolution_job_round_trips() -> None:
    job = BatchResolutionJob(
        job_id="job-2",
        reference_ids=[],
        status="completed",
        created_at=datetime(2026, 4, 15, tzinfo=UTC),
        completed_at=datetime(2026, 4, 16, tzinfo=UTC),
    )

    restored = BatchResolutionJob.model_validate(job.model_dump(mode="json"))

    assert restored == job


class FailingCaseWriteRepository(InMemoryResolutionCaseRepository):
    def _save_unchecked(self, case: ResolutionCase) -> None:
        raise RuntimeError("case write failed")
