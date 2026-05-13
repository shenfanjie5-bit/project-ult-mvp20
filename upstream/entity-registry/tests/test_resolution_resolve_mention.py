import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

import entity_registry
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityAlias,
    EntityStatus,
    EntityType,
    ResolutionMethod,
)
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution import (
    ResolutionAuditRepositoryRequiredError,
    resolve_mention,
    resolve_mention_with_repositories,
)
from entity_registry.resolution_types import MentionResolutionResult, ResolutionContext
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionCaseRepository,
)


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def initialized_resolution_repositories() -> tuple[
    InMemoryEntityRepository,
    InMemoryAliasRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionCaseRepository,
]:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo)
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert result.errors == []
    return entity_repo, alias_repo, reference_repo, case_repo


def saved_references(
    reference_repo: InMemoryReferenceRepository,
) -> list[EntityReference]:
    return list(reference_repo._references.values())


def make_reference(
    reference_id: str,
    raw_mention_text: str,
    *,
    source_context: dict | None = None,
    resolved_entity_id: str | None = None,
    resolution_method: ResolutionMethod = ResolutionMethod.UNRESOLVED,
    resolution_confidence: float | None = None,
) -> EntityReference:
    return EntityReference(
        reference_id=reference_id,
        raw_mention_text=raw_mention_text,
        source_context=source_context or {},
        resolved_entity_id=resolved_entity_id,
        resolution_method=resolution_method,
        resolution_confidence=resolution_confidence,
    )


def test_resolve_mention_public_signature_matches_contract() -> None:
    signature = inspect.signature(resolve_mention)

    assert list(signature.parameters) == ["raw_mention_text", "context"]
    assert signature.parameters["context"].default is None


def test_package_exports_resolution_public_api() -> None:
    assert entity_registry.resolve_mention is not resolve_mention
    assert not hasattr(entity_registry, "MentionResolutionResult")


def test_mention_resolution_result_json_shape_is_stable() -> None:
    result = MentionResolutionResult(
        raw_mention_text="贵州茅台",
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )

    assert result.model_dump(mode="json") == {
        "raw_mention_text": "贵州茅台",
        "resolved_entity_id": "ENT_STOCK_600519.SH",
        "resolution_method": "deterministic",
        "resolution_confidence": 1.0,
    }


def test_mention_resolution_result_rejects_null_entity_with_resolved_method() -> None:
    with pytest.raises(ValidationError):
        MentionResolutionResult(
            raw_mention_text="Unknown Corp",
            resolved_entity_id=None,
            resolution_method=ResolutionMethod.DETERMINISTIC,
            resolution_confidence=None,
        )


def test_unique_deterministic_hit_returns_result_and_audit_records() -> None:
    entity_repo, alias_repo, reference_repo, case_repo = (
        initialized_resolution_repositories()
    )

    result = resolve_mention_with_repositories(
        "贵州茅台",
        {"document_id": "doc-1"},
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    references = saved_references(reference_repo)
    cases = case_repo.find_by_reference(references[0].reference_id)
    assert result == MentionResolutionResult(
        raw_mention_text="贵州茅台",
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )
    assert len(references) == 1
    assert references[0].resolved_entity_id == "ENT_STOCK_600519.SH"
    assert references[0].source_context == {"document_id": "doc-1"}
    assert len(cases) == 1
    assert cases[0].decision_type is DecisionType.AUTO
    assert cases[0].selected_entity_id == "ENT_STOCK_600519.SH"


def test_resolve_mention_audits_same_candidate_snapshot_used_for_decision() -> None:
    entity_repo = InMemoryEntityRepository()
    first_entity = make_entity("ENT_STOCK_FIRST.SZ")
    second_entity = make_entity("ENT_STOCK_SECOND.SZ")
    entity_repo.save(first_entity)
    entity_repo.save(second_entity)
    alias_repo = FlappingAliasRepository(
        [
            make_alias(first_entity.canonical_entity_id, "flip"),
            make_alias(second_entity.canonical_entity_id, "flip"),
        ]
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo)

    result = resolve_mention_with_repositories(
        "flip",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,  # type: ignore[arg-type]
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    references = saved_references(reference_repo)
    cases = case_repo.find_by_reference(references[0].reference_id)
    assert alias_repo.find_by_text_calls == 1
    assert result.resolved_entity_id == "ENT_STOCK_FIRST.SZ"
    assert cases[0].selected_entity_id == "ENT_STOCK_FIRST.SZ"
    assert cases[0].candidate_entity_ids == ["ENT_STOCK_FIRST.SZ"]


def test_unique_code_hit_returns_deterministic_result() -> None:
    entity_repo, alias_repo, reference_repo, case_repo = (
        initialized_resolution_repositories()
    )

    result = resolve_mention_with_repositories(
        "600519",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert result.resolution_method is ResolutionMethod.DETERMINISTIC
    assert result.resolution_confidence == 1.0


def test_missing_mention_returns_unresolved_and_writes_audit_records() -> None:
    entity_repo, alias_repo, reference_repo, case_repo = (
        initialized_resolution_repositories()
    )

    result = resolve_mention_with_repositories(
        "不存在的公司",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    unresolved = reference_repo.find_unresolved()
    cases = case_repo.find_by_reference(unresolved[0].reference_id)
    assert result.model_dump(mode="json") == {
        "raw_mention_text": "不存在的公司",
        "resolved_entity_id": None,
        "resolution_method": "unresolved",
        "resolution_confidence": None,
    }
    assert len(unresolved) == 1
    assert unresolved[0].resolution_method is ResolutionMethod.UNRESOLVED
    assert len(cases) == 1
    assert cases[0].candidate_entity_ids == []
    assert cases[0].decision_type is DecisionType.AUTO
    assert cases[0].selected_entity_id is None


def test_a_h_shared_short_name_returns_unresolved_with_candidate_case() -> None:
    entity_repo, alias_repo, reference_repo, case_repo = (
        initialized_resolution_repositories()
    )

    result = resolve_mention_with_repositories(
        "宁德时代",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    unresolved = reference_repo.find_unresolved()
    cases = case_repo.find_by_reference(unresolved[0].reference_id)
    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert result.resolution_confidence is None
    assert len(cases) == 1
    assert set(cases[0].candidate_entity_ids) == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }
    assert cases[0].selected_entity_id is None
    assert cases[0].decision_type is DecisionType.MANUAL_REVIEW


def test_public_resolve_mention_uses_configured_default_repositories() -> None:
    entity_repo, alias_repo, reference_repo, case_repo = (
        initialized_resolution_repositories()
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    result = entity_registry.resolve_mention(
        "贵州茅台",
        ResolutionContext(
            raw_mention_text="贵州茅台",
            document_context="贵州茅台发布公告",
            source_type="announcement",
        ),
    )

    references = saved_references(reference_repo)
    assert result.resolved_entity is not None
    assert result.resolved_entity.entity_id == "ENT_STOCK_600519.SH"
    assert len(references) == 1
    assert references[0].source_context["source_type"] == "announcement"


def test_resolved_resolution_requires_native_audit_unit_of_work() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    reference_repo = AppendTrackingReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(
        ResolutionAuditRepositoryRequiredError,
        match="save_resolution",
    ):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
        )

    assert reference_repo.saved_records == []
    assert case_repo.find_by_reference("any") == []


def test_unresolved_resolution_requires_native_audit_unit_of_work() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    reference_repo = AppendTrackingReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(
        ResolutionAuditRepositoryRequiredError,
        match="save_resolution",
    ):
        resolve_mention_with_repositories(
            "不存在的公司",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
        )

    assert reference_repo.saved_records == []
    assert case_repo.find_by_reference("any") == []


def test_resolution_audit_uses_native_save_resolution_boundary() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo=case_repo)

    result = resolve_mention_with_repositories(
        "贵州茅台",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    references = saved_references(reference_repo)
    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert len(references) == 1
    assert len(reference_repo.saved_cases) == 1
    assert reference_repo.saved_cases[0].reference_id == references[0].reference_id


def test_resolution_audit_accepts_public_uow_without_case_repo_attrs() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = PublicContractAuditReferenceRepository(CaseAuditBackend(case_repo))

    result = resolve_mention_with_repositories(
        "贵州茅台",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )

    references = saved_references(reference_repo)
    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert len(references) == 1
    assert len(case_repo.find_by_reference(references[0].reference_id)) == 1


def test_existing_reference_id_must_exist_before_resolution_write() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo=case_repo)

    with pytest.raises(ValueError, match="was not found"):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id="ref-missing",
        )

    assert saved_references(reference_repo) == []
    assert case_repo.find_by_reference("ref-missing") == []


def test_existing_reference_id_must_be_unresolved_before_resolution_write() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo=case_repo)
    existing = make_reference(
        "ref-resolved",
        "贵州茅台",
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )
    reference_repo.save(existing)

    with pytest.raises(ValueError, match="unresolved reference"):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id="ref-resolved",
        )

    assert reference_repo.get("ref-resolved") == existing
    assert case_repo.find_by_reference("ref-resolved") == []


def test_existing_reference_id_must_match_raw_mention_before_resolution_write() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo=case_repo)
    existing = make_reference("ref-mismatch", "宁德时代")
    reference_repo.save(existing)

    with pytest.raises(ValueError, match="raw_mention_text"):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id="ref-mismatch",
        )

    assert reference_repo.get("ref-mismatch") == existing
    assert case_repo.find_by_reference("ref-mismatch") == []


def test_existing_reference_id_with_audit_repo_only_requires_reader() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    audit_repo = WriteOnlyAuditRepository()

    with pytest.raises(
        ResolutionAuditRepositoryRequiredError,
        match="existing_reference_id requires",
    ):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_repo=audit_repo,
            existing_reference_id="ref-unreadable",
        )

    assert audit_repo.references == []
    assert audit_repo.cases == []


def test_existing_reference_id_with_audit_repo_only_uses_reader() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    audit_repo = ReadableAuditRepository()
    existing = make_reference("ref-readable", "贵州茅台")
    audit_repo.references_by_id[existing.reference_id] = existing

    result = resolve_mention_with_repositories(
        "贵州茅台",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        existing_reference_id=existing.reference_id,
    )

    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert audit_repo.references_by_id["ref-readable"].resolved_entity_id == (
        "ENT_STOCK_600519.SH"
    )
    assert audit_repo.cases[0].reference_id == "ref-readable"


def test_existing_reference_id_reads_from_audit_write_boundary() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = NativeResolutionAuditReferenceRepository(case_repo=case_repo)
    reference_repo_reference = make_reference("ref-shared-reader", "贵州茅台")
    reference_repo.save(reference_repo_reference)
    audit_repo = ReadableAuditRepository()

    with pytest.raises(ValueError, match="was not found"):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_repo=audit_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id="ref-shared-reader",
        )

    assert reference_repo.get("ref-shared-reader") == reference_repo_reference
    assert audit_repo.references_by_id == {}
    assert audit_repo.cases == []


def test_resolution_module_has_no_provider_or_later_stage_imports() -> None:
    text = Path("src/entity_registry/resolution.py").read_text(encoding="utf-8")

    for forbidden in ("openai", "anthropic", "google.generativeai", "splink", "hanlp"):
        assert forbidden not in text


def test_runtime_resolve_rejects_audit_repo_that_hides_case_write() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    reference_repo = ReferenceOnlyAuditReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()
    original = make_reference("ref-orphan-risk", "贵州茅台")
    reference_repo.save(original)

    with pytest.raises(
        ResolutionAuditRepositoryRequiredError,
        match="does not own the configured case_repo",
    ):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id=original.reference_id,
        )

    assert reference_repo.get(original.reference_id) == original
    assert case_repo.find_by_reference(original.reference_id) == []


def test_audit_cohesion_preflight_runs_before_save_resolution() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    reference_repo = MutatingCohesionRejectingAuditReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(
        ResolutionAuditRepositoryRequiredError,
        match="does not own the configured case_repo",
    ):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
        )

    assert reference_repo.save_resolution_calls == 0
    assert saved_references(reference_repo) == []
    assert case_repo.find_by_reference("any") == []


def test_audit_failure_does_not_restore_over_interleaved_successful_resolution() -> None:
    entity_repo, alias_repo, _reference_repo, _case_repo = (
        initialized_resolution_repositories()
    )
    case_repo = InMemoryResolutionCaseRepository()
    reference_id = "ref-shared"
    original = make_reference(reference_id, "贵州茅台")
    interleaved_reference = make_reference(
        reference_id,
        "贵州茅台",
        source_context={"worker": "successful"},
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )
    interleaved_case = ResolutionCase(
        case_id="case-interleaved-success",
        reference_id=reference_id,
        candidate_entity_ids=["ENT_STOCK_600519.SH"],
        selected_entity_id="ENT_STOCK_600519.SH",
        decision_type=DecisionType.AUTO,
        decision_rationale="interleaved successful resolution",
    )
    reference_repo = InterleavingFailingAuditReferenceRepository(
        case_repo,
        interleaved_reference=interleaved_reference,
        interleaved_case=interleaved_case,
    )
    reference_repo.save(original)

    with pytest.raises(RuntimeError, match="audit failure after interleaved write"):
        resolve_mention_with_repositories(
            "贵州茅台",
            {"worker": "failing"},
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            reference_repo=reference_repo,
            case_repo=case_repo,
            existing_reference_id=reference_id,
        )

    assert reference_repo.get(reference_id) == interleaved_reference
    assert case_repo.get(interleaved_case.case_id) == interleaved_case


def make_entity(entity_id: str) -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name=entity_id,
        status=EntityStatus.ACTIVE,
        anchor_code=entity_id.removeprefix("ENT_STOCK_"),
        cross_listing_group=None,
    )


def make_alias(entity_id: str, alias_text: str) -> EntityAlias:
    return EntityAlias(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=AliasType.SHORT_NAME,
        confidence=1.0,
        source="unit-test",
        is_primary=True,
    )


class FlappingAliasRepository:
    def __init__(self, aliases_by_call: list[EntityAlias]) -> None:
        self.aliases_by_call = aliases_by_call
        self.find_by_text_calls = 0

    def find_by_text(self, alias_text: str) -> list[EntityAlias]:
        index = min(self.find_by_text_calls, len(self.aliases_by_call) - 1)
        self.find_by_text_calls += 1
        return [self.aliases_by_call[index]]

    def find_by_entity(self, entity_id: str) -> list[EntityAlias]:
        return [
            alias
            for alias in self.aliases_by_call
            if alias.canonical_entity_id == entity_id
        ]

    def save(self, alias: EntityAlias) -> None:
        raise NotImplementedError

    def save_if_absent(self, alias: EntityAlias) -> bool:
        raise NotImplementedError

    def save_batch(self, aliases: list[EntityAlias]) -> None:
        raise NotImplementedError

    def save_batch_if_absent(self, aliases: list[EntityAlias]) -> int:
        raise NotImplementedError


class UnexpectedResolutionCaseRepository(InMemoryResolutionCaseRepository):
    def save(self, case: entity_registry.ResolutionCase) -> None:
        raise AssertionError("native audit unit of work should save cases")


class AppendTrackingReferenceRepository(InMemoryReferenceRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saved_records: list[EntityReference] = []

    def save(self, ref: EntityReference) -> None:
        self.saved_records.append(ref)
        super().save(ref)


class NativeResolutionAuditReferenceRepository(InMemoryReferenceRepository):
    def __init__(
        self,
        case_repo: InMemoryResolutionCaseRepository | None = None,
    ) -> None:
        super().__init__()
        self.saved_cases: list[entity_registry.ResolutionCase] = []
        self.case_repo = case_repo

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.save(reference)
        if self.case_repo is not None:
            self.case_repo.save(case)
        self.saved_cases.append(case)

    def owns_resolution_case_repository(
        self,
        case_repo: InMemoryResolutionCaseRepository,
    ) -> bool:
        return case_repo is self.case_repo


class PublicContractAuditReferenceRepository(InMemoryReferenceRepository):
    def __init__(self, audit_backend: "CaseAuditBackend") -> None:
        super().__init__()
        self.audit_backend = audit_backend

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.save(reference)
        self.audit_backend.save_case(case)

    def owns_resolution_case_repository(
        self,
        case_repo: InMemoryResolutionCaseRepository,
    ) -> bool:
        return self.audit_backend.owns_resolution_case_repository(case_repo)


class CaseAuditBackend:
    def __init__(self, case_repo: InMemoryResolutionCaseRepository) -> None:
        self._target = case_repo

    def save_case(self, case: entity_registry.ResolutionCase) -> None:
        self._target.save(case)

    def owns_resolution_case_repository(
        self,
        case_repo: InMemoryResolutionCaseRepository,
    ) -> bool:
        return case_repo is self._target


class WriteOnlyAuditRepository:
    def __init__(self) -> None:
        self.references: list[EntityReference] = []
        self.cases: list[entity_registry.ResolutionCase] = []

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.references.append(reference)
        self.cases.append(case)


class ReadableAuditRepository:
    def __init__(self) -> None:
        self.references_by_id: dict[str, EntityReference] = {}
        self.cases: list[entity_registry.ResolutionCase] = []

    def get(self, reference_id: str) -> EntityReference | None:
        return self.references_by_id.get(reference_id)

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.references_by_id[reference.reference_id] = reference
        self.cases.append(case)


class ReferenceOnlyAuditReferenceRepository(InMemoryReferenceRepository):
    """Native save_resolution that writes the reference but skips the case_repo.

    This adapter passes the ``save_resolution`` method check, but the case
    readback guard rejects it because it never persists the resolution case.
    """

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.save(reference)
        # Intentionally do not write ``case`` anywhere.

    def owns_resolution_case_repository(
        self,
        case_repo: InMemoryResolutionCaseRepository,
    ) -> bool:
        return False


class MutatingCohesionRejectingAuditReferenceRepository(InMemoryReferenceRepository):
    def __init__(self) -> None:
        super().__init__()
        self.save_resolution_calls = 0

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.save_resolution_calls += 1
        self.save(reference)

    def owns_resolution_case_repository(
        self,
        case_repo: InMemoryResolutionCaseRepository,
    ) -> bool:
        return False


class InterleavingFailingAuditReferenceRepository(
    NativeResolutionAuditReferenceRepository
):
    def __init__(
        self,
        case_repo: InMemoryResolutionCaseRepository,
        *,
        interleaved_reference: EntityReference,
        interleaved_case: ResolutionCase,
    ) -> None:
        super().__init__(case_repo=case_repo)
        self.interleaved_reference = interleaved_reference
        self.interleaved_case = interleaved_case

    def save_resolution(
        self,
        reference: EntityReference,
        case: entity_registry.ResolutionCase,
    ) -> None:
        self.save(reference)
        super().save_resolution(self.interleaved_reference, self.interleaved_case)
        raise RuntimeError("audit failure after interleaved write")
