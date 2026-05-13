"""Core public exports for the entity-registry package."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import uuid4

from entity_registry.core import (
    AliasType,
    DecisionType,
    EntityStatus,
    EntityType,
    FinalStatus,
    ResolutionMethod,
    generate_event_entity_id,
    generate_stock_entity_id,
    validate_entity_id,
)
from entity_registry.events import anchor_event_entity
from entity_registry.aliases import (
    AliasManager,
    generate_aliases_from_stock_basic,
    lookup_alias as _runtime_lookup_alias,
)
from entity_registry.contracts import (
    CANONICAL_ID_RULE_VERSION,
    ContractBaseModel,
    ContractCanonicalEntity,
    ContractEntityAlias,
    ContractEntityReference,
    ContractResolutionCase,
    EntityResolutionDecision,
    current_canonical_id_rule_version,
    to_contract_canonical_entity,
    to_contract_entity_alias,
    to_contract_entity_reference,
    to_contract_resolution_case,
)
from entity_registry.batch import (
    BatchCandidateGroup,
    BatchReferenceInput,
    BatchResolutionOutcome,
    BatchResolutionReport,
    batch_resolve_with_report,
    run_batch_resolution_job as _runtime_run_batch_resolution_job,
)
from entity_registry.fuzzy import (
    FuzzyCandidate,
    FuzzyMatcher,
    FuzzyMatcherUnavailable,
    NullFuzzyMatcher,
    SimpleFuzzyMatcher,
    SplinkFuzzyMatcher,
)
from entity_registry.llm_client import (
    CallableReasonerRuntimeClient,
    LLMDisambiguationCandidate,
    LLMDisambiguationRequest,
    LLMDisambiguationResponse,
    ReasonerRuntimeClient,
    build_disambiguation_request,
)
from entity_registry.init import (
    DataPlatformStockBasicReader,
    FileStockBasicSnapshotReader,
    InitializationError,
    InitializationResult,
    RepositoryNotConfiguredError,
    StockBasicRecord,
    StockBasicSnapshotReader,
    configure_default_in_memory_audit_repositories,
    configure_default_repositories,
    detect_cross_listing_groups,
    get_default_alias_repository,
    get_default_entity_repository,
    get_default_reasoner_client,
    get_default_repositories,
    initialize_from_stock_basic,
    initialize_from_stock_basic_into,
    load_stock_basic_records,
    reset_default_repositories,
)
from entity_registry.ner import (
    ExtractedMention,
    HanLPNERExtractor,
    NERExtractor,
    NullNERExtractor,
)
from entity_registry.profile import (
    get_entity_profile as _runtime_get_entity_profile,
)
from entity_registry.references import (
    EntityReference as _RuntimeEntityReference,
    ResolutionCase as _RuntimeResolutionCase,
    _coerce_unresolved_reference,
)
from entity_registry.readiness import (
    EntityRegistryRuntimeConfig,
    ProductionReadinessConfig,
    ProductionReadinessError,
    ReadinessCheck,
    assert_runtime_readiness,
    check_runtime_readiness,
    runtime_config_from_defaults,
)
from entity_registry.review import (
    ManualReviewDecision,
    ResolutionAuditPayload,
    ReviewAuditWriter,
    ReviewNotFoundError,
    ReviewStateError,
    UnresolvedQueueItem,
    claim_review_item,
    enqueue_batch_manual_review,
    enqueue_unresolved_reference,
    get_resolution_audit_payload,
    submit_manual_review_decision,
)
from entity_registry.resolution import (
    DeterministicMatcher,
    ResolutionAuditRepositoryRequiredError,
    _validate_repository_audit_cohesion,
    resolve_mention_with_repositories as _runtime_resolve_mention_with_repositories,
)
from entity_registry.resolution_types import (
    BatchResolutionJob,
    MentionCandidateSet,
    MentionResolutionResult as _RuntimeMentionResolutionResult,
    ResolutionContext,
    ResolutionDecision,
)
from entity_registry.storage import (
    InMemoryReviewRepository,
    InMemoryResolutionCaseRepository,
    ReferenceRepository,
    ResolutionAuditReferenceRepository,
    ResolutionAuditRepository,
    ReviewRepository,
    ResolutionCaseRepository,
)

__version__ = "0.1.1"

CanonicalEntity = ContractCanonicalEntity
EntityAlias = ContractEntityAlias
EntityReference = ContractEntityReference
ResolutionCase = ContractResolutionCase


def lookup_alias(alias_text: str) -> ContractCanonicalEntity | None:
    """Return the contract canonical entity for one unambiguous alias hit."""

    entity = _runtime_lookup_alias(alias_text)
    if entity is None:
        return None
    return to_contract_canonical_entity(entity)


def lookup_entity_refs(refs: Iterable[str]) -> dict[str, bool]:
    """Return existence for canonical entity references against live repositories.

    This read-only helper is intentionally narrower than alias resolution: SDK
    preflight should verify producer-supplied canonical refs, not mint or infer
    new canonical IDs on behalf of subsystems.
    """

    entity_repo = get_default_entity_repository()
    result: dict[str, bool] = {}
    for ref in refs:
        result[ref] = validate_entity_id(ref) and entity_repo.exists(ref)
    return result


def register_unresolved_reference(
    reference: _RuntimeEntityReference | dict[str, object],
) -> ContractResolutionCase:
    """Register an unresolved reference and return a contract audit payload."""

    from entity_registry.init import (
        RepositoryNotConfiguredError,
        _get_default_repository_context,
    )

    repository_context = _get_default_repository_context()
    if repository_context.reference_repo is None:
        raise RepositoryNotConfiguredError(
            "reference audit repository is not configured; "
            "call configure_default_repositories(..., reference_repo=...) before "
            "registering unresolved references, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )
    if repository_context.case_repo is None:
        raise RepositoryNotConfiguredError(
            "resolution case audit repository is not configured; "
            "call configure_default_repositories(..., case_repo=...) before "
            "registering unresolved references, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )

    unresolved_reference = _coerce_unresolved_reference(reference)
    case = _RuntimeResolutionCase(
        case_id=_new_public_case_id(),
        reference_id=unresolved_reference.reference_id,
        candidate_entity_ids=[],
        selected_entity_id=None,
        decision_type=DecisionType.AUTO,
        decision_rationale="registered unresolved reference",
        created_at=unresolved_reference.created_at,
    )
    persisted_case = _save_public_resolution_audit(
        unresolved_reference,
        case,
        reference_repo=repository_context.reference_repo,
        case_repo=repository_context.case_repo,
    )
    return to_contract_resolution_case(
        persisted_case,
        input_alias=unresolved_reference.raw_mention_text,
        candidate_entities=[],
        decision=EntityResolutionDecision.UNRESOLVED,
        confidence=0.0,
    )


def resolve_mention(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None = None,
) -> ContractResolutionCase:
    """Resolve one mention and return the contract resolution case."""

    from entity_registry.init import (
        RepositoryNotConfiguredError,
        _get_default_repository_context,
    )

    repository_context = _get_default_repository_context()
    if (
        repository_context.reference_repo is None
        or repository_context.case_repo is None
    ):
        raise RepositoryNotConfiguredError(
            "resolution audit repositories are not configured; "
            "call configure_default_repositories(..., reference_repo=..., "
            "case_repo=...) before using public resolution APIs, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )

    reference_id = _new_public_reference_id()
    result = _runtime_resolve_mention_with_repositories(
        raw_mention_text,
        context,
        entity_repo=repository_context.entity_repo,
        alias_repo=repository_context.alias_repo,
        reference_repo=repository_context.reference_repo,
        case_repo=repository_context.case_repo,
        fuzzy_matcher=repository_context.fuzzy_matcher,
        ner_extractor=repository_context.ner_extractor,
        reasoner_client=repository_context.reasoner_client,
        existing_reference_id=reference_id,
        allow_new_reference_id=True,
    )
    return _contract_case_for_reference(
        reference_id,
        raw_mention_text,
        result,
        entity_repo=repository_context.entity_repo,
        case_repo=repository_context.case_repo,
    )


def batch_resolve(
    references: Sequence[_RuntimeEntityReference | dict[str, object] | str],
) -> list[ContractResolutionCase]:
    """Resolve a batch of mentions and return contract resolution cases."""

    from entity_registry.init import (
        RepositoryNotConfiguredError,
        _get_default_repository_context,
    )

    repository_context = _get_default_repository_context()
    if (
        repository_context.reference_repo is None
        or repository_context.case_repo is None
    ):
        raise RepositoryNotConfiguredError(
            "resolution audit repositories are not configured; "
            "call configure_default_repositories(..., reference_repo=..., "
            "case_repo=...) before using public resolution APIs, or use "
            "configure_default_in_memory_audit_repositories() for tests/local workflows",
        )

    normalized_inputs = _public_batch_inputs_with_reference_ids(references)

    def resolve_with_captured_context(
        raw_mention_text: str,
        context: ResolutionContext | dict[str, object] | None = None,
        *,
        existing_reference_id: str | None = None,
    ) -> _RuntimeMentionResolutionResult:
        return _runtime_resolve_mention_with_repositories(
            raw_mention_text,
            context,
            entity_repo=repository_context.entity_repo,
            alias_repo=repository_context.alias_repo,
            reference_repo=repository_context.reference_repo,
            case_repo=repository_context.case_repo,
            fuzzy_matcher=repository_context.fuzzy_matcher,
            ner_extractor=repository_context.ner_extractor,
            reasoner_client=repository_context.reasoner_client,
            existing_reference_id=existing_reference_id,
            allow_new_reference_id=True,
        )

    report = _runtime_run_batch_resolution_job(
        BatchResolutionJob(
            job_id=_new_public_batch_job_id(),
            reference_ids=[
                item.source_reference_id
                for item in normalized_inputs
                if item.source_reference_id is not None
            ],
            status="pending",
        ),
        normalized_inputs,
        resolver=resolve_with_captured_context,
        fuzzy_matcher=repository_context.fuzzy_matcher,
    )
    if report.errors:
        raise RuntimeError(
            "batch resolution failed: " + "; ".join(report.errors),
        )

    return [
        _contract_case_for_reference(
            outcome.source_reference_id,
            outcome.result.raw_mention_text,
            outcome.result,
            entity_repo=repository_context.entity_repo,
            case_repo=repository_context.case_repo,
        )
        for outcome in report.outcomes
        if outcome.source_reference_id is not None
    ]


def _public_batch_inputs_with_reference_ids(
    references: Sequence[_RuntimeEntityReference | dict[str, object] | str],
) -> list[BatchReferenceInput]:
    normalized_inputs: list[BatchReferenceInput] = []
    seen_reference_ids: set[str] = set()
    for reference in references:
        item = _coerce_public_batch_reference_input(reference)
        if item.source_reference_id is None:
            item = item.model_copy(
                update={"source_reference_id": _new_public_reference_id()},
            )
        if item.source_reference_id in seen_reference_ids:
            raise ValueError(
                "duplicate source_reference_id in batch inputs: "
                f"{item.source_reference_id}"
            )
        seen_reference_ids.add(item.source_reference_id)
        normalized_inputs.append(item)
    return normalized_inputs


def _coerce_public_batch_reference_input(
    reference: _RuntimeEntityReference | BatchReferenceInput | dict[str, object] | str,
) -> BatchReferenceInput:
    if isinstance(reference, BatchReferenceInput):
        return reference
    if isinstance(reference, _RuntimeEntityReference):
        return BatchReferenceInput(
            raw_mention_text=reference.raw_mention_text,
            source_context=dict(reference.source_context),
            source_reference_id=reference.reference_id,
        )
    if isinstance(reference, str):
        return BatchReferenceInput(raw_mention_text=reference)
    if isinstance(reference, dict):
        payload = dict(reference)
        source_context = payload.get("source_context", {})
        if source_context is None:
            source_context = {}
        if not isinstance(source_context, dict):
            raise ValueError("source_context must be a dictionary")

        source_reference_id = payload.get("source_reference_id")
        if source_reference_id is None:
            source_reference_id = payload.get("reference_id")
        if source_reference_id is not None and not isinstance(
            source_reference_id,
            str,
        ):
            raise ValueError("source_reference_id must be a string when provided")

        return BatchReferenceInput(
            raw_mention_text=_required_public_batch_text(
                payload,
                "raw_mention_text",
            ),
            source_context=dict(source_context),
            source_reference_id=source_reference_id,
        )
    raise TypeError("batch references must be EntityReference, dict, or str")


def _required_public_batch_text(
    payload: dict[str, object],
    field_name: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def get_entity_profile(canonical_entity_id: str) -> dict[str, object]:
    """Return a contract-shaped entity profile payload."""

    profile = _runtime_get_entity_profile(canonical_entity_id)
    return {
        "canonical_entity": to_contract_canonical_entity(profile.canonical_entity),
        "aliases": [
            to_contract_entity_alias(alias)
            for alias in profile.aliases
        ],
        "cross_listing_group": profile.cross_listing_group,
        "cross_listing_entity_ids": list(profile.cross_listing_entity_ids),
    }


def _contract_case_for_reference(
    reference_id: str | None,
    raw_mention_text: str,
    result: _RuntimeMentionResolutionResult,
    *,
    entity_repo: object,
    case_repo: ResolutionCaseRepository,
) -> ContractResolutionCase:
    if reference_id is None:
        raise RuntimeError("contract resolution payload requires a source reference ID")

    case = _latest_case_for_reference(case_repo, reference_id)
    candidate_entities = _candidate_entities_for_case(case, entity_repo)
    return to_contract_resolution_case(
        case,
        input_alias=raw_mention_text,
        candidate_entities=candidate_entities,
        decision=_contract_decision_for(case, result),
        confidence=result.resolution_confidence,
    )


def _latest_case_for_reference(
    case_repo: ResolutionCaseRepository,
    reference_id: str,
) -> _RuntimeResolutionCase:
    cases = case_repo.find_by_reference(reference_id)
    if not cases:
        raise RuntimeError(f"missing resolution case for reference {reference_id}")
    return max(cases, key=lambda case: case.created_at)


def _candidate_entities_for_case(
    case: _RuntimeResolutionCase,
    entity_repo: object,
) -> list[object]:
    entities = []
    for entity_id in case.candidate_entity_ids:
        entity = entity_repo.get(entity_id)
        if entity is not None:
            entities.append(entity)
    return entities


def _contract_decision_for(
    case: _RuntimeResolutionCase,
    result: _RuntimeMentionResolutionResult,
) -> EntityResolutionDecision:
    if result.resolved_entity_id is not None:
        return EntityResolutionDecision.MATCHED
    if case.candidate_entity_ids:
        return EntityResolutionDecision.AMBIGUOUS
    return EntityResolutionDecision.UNRESOLVED


def _save_public_resolution_audit(
    reference: _RuntimeEntityReference,
    case: _RuntimeResolutionCase,
    *,
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
) -> _RuntimeResolutionCase:
    save_resolution = getattr(reference_repo, "save_resolution", None)
    if not callable(save_resolution):
        raise ResolutionAuditRepositoryRequiredError(
            "resolution audit writes require a native save_resolution(reference, case) "
            "unit of work; separate reference/case writes are not supported",
        )

    _validate_repository_audit_cohesion(reference_repo, case_repo)
    save_resolution(reference, case)

    persisted_case = case_repo.get(case.case_id)
    if persisted_case is None:
        raise RuntimeError(
            "resolution audit repository did not persist the unresolved "
            f"resolution case {case.case_id}",
        )
    return persisted_case


def _new_public_reference_id() -> str:
    return f"REF_{uuid4().hex}"


def _new_public_case_id() -> str:
    return f"CASE_{uuid4().hex}"


def _new_public_batch_job_id() -> str:
    return f"BATCH_{uuid4().hex}"


__all__ = [
    "__version__",
    "AliasType",
    "AliasManager",
    "BatchCandidateGroup",
    "BatchReferenceInput",
    "BatchResolutionJob",
    "BatchResolutionOutcome",
    "BatchResolutionReport",
    "CallableReasonerRuntimeClient",
    "CANONICAL_ID_RULE_VERSION",
    "CanonicalEntity",
    "ContractBaseModel",
    "ContractCanonicalEntity",
    "ContractEntityAlias",
    "ContractEntityReference",
    "ContractResolutionCase",
    "DataPlatformStockBasicReader",
    "DecisionType",
    "DeterministicMatcher",
    "EntityAlias",
    "EntityRegistryRuntimeConfig",
    "EntityReference",
    "EntityResolutionDecision",
    "EntityStatus",
    "EntityType",
    "ExtractedMention",
    "FileStockBasicSnapshotReader",
    "FinalStatus",
    "FuzzyCandidate",
    "FuzzyMatcher",
    "FuzzyMatcherUnavailable",
    "HanLPNERExtractor",
    "InMemoryReviewRepository",
    "InMemoryResolutionCaseRepository",
    "InitializationError",
    "InitializationResult",
    "LLMDisambiguationCandidate",
    "LLMDisambiguationRequest",
    "LLMDisambiguationResponse",
    "ManualReviewDecision",
    "MentionCandidateSet",
    "NERExtractor",
    "NullFuzzyMatcher",
    "NullNERExtractor",
    "ProductionReadinessConfig",
    "ProductionReadinessError",
    "ReasonerRuntimeClient",
    "ReadinessCheck",
    "ResolutionAuditReferenceRepository",
    "ResolutionAuditRepository",
    "RepositoryNotConfiguredError",
    "ResolutionAuditPayload",
    "ResolutionCase",
    "ResolutionCaseRepository",
    "ResolutionContext",
    "ResolutionDecision",
    "ResolutionMethod",
    "ReviewAuditWriter",
    "ReviewNotFoundError",
    "ReviewRepository",
    "ReviewStateError",
    "SimpleFuzzyMatcher",
    "StockBasicRecord",
    "StockBasicSnapshotReader",
    "SplinkFuzzyMatcher",
    "UnresolvedQueueItem",
    "assert_runtime_readiness",
    "batch_resolve",
    "batch_resolve_with_report",
    "build_disambiguation_request",
    "check_runtime_readiness",
    "claim_review_item",
    "configure_default_in_memory_audit_repositories",
    "configure_default_repositories",
    "current_canonical_id_rule_version",
    "detect_cross_listing_groups",
    "enqueue_batch_manual_review",
    "enqueue_unresolved_reference",
    "generate_aliases_from_stock_basic",
    "anchor_event_entity",
    "generate_event_entity_id",
    "generate_stock_entity_id",
    "get_default_alias_repository",
    "get_default_entity_repository",
    "get_default_reasoner_client",
    "get_default_repositories",
    "get_entity_profile",
    "get_resolution_audit_payload",
    "initialize_from_stock_basic",
    "initialize_from_stock_basic_into",
    "load_stock_basic_records",
    "lookup_alias",
    "lookup_entity_refs",
    "register_unresolved_reference",
    "reset_default_repositories",
    "resolve_mention",
    "runtime_config_from_defaults",
    "submit_manual_review_decision",
    "to_contract_canonical_entity",
    "to_contract_entity_alias",
    "to_contract_entity_reference",
    "to_contract_resolution_case",
    "validate_entity_id",
]
