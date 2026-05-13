"""Deterministic mention matching."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import cast, overload

from entity_registry.aliases import AliasManager, normalize_alias_text
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityAlias,
    FinalStatus,
    ResolutionMethod,
    generate_stock_entity_id,
    validate_entity_id,
)
from entity_registry.fuzzy import FuzzyCandidate, FuzzyMatcher
from entity_registry.llm_client import (
    LLMDisambiguationCandidate,
    LLMDisambiguationResponse,
    ReasonerRuntimeClient,
    build_disambiguation_request,
)
from entity_registry.ner import NERExtractor
from entity_registry.references import (
    EntityReference,
    ResolutionCase,
    _new_case_id,
    _new_reference_id,
)
from entity_registry.resolution_types import (
    MentionCandidateSet,
    MentionResolutionResult,
    ResolutionContext,
    ResolutionDecision,
)
from entity_registry.storage import (
    AliasRepository,
    EntityRepository,
    ReadableResolutionAuditRepository,
    ReferenceRepository,
    ResolutionAuditReferenceRepository,
    ResolutionAuditRepository,
    ResolutionCaseRepository,
)


_LOGGER = logging.getLogger(__name__)
_LLM_CONFIDENCE_THRESHOLD = 0.80


class ResolutionAuditRepositoryRequiredError(RuntimeError):
    """Raised when resolution is asked to write audit records without a UoW."""


class DeterministicMatcher:
    """Repository-backed Level 1 deterministic matcher."""

    def __init__(
        self,
        entity_repo: EntityRepository,
        alias_repo: AliasRepository,
    ) -> None:
        self._entity_repo = entity_repo
        self._alias_manager = AliasManager(alias_repo)

    def exact_match(self, raw_mention_text: str) -> list[CanonicalEntity]:
        """Return existing entities for exact alias text matches."""

        aliases = self._alias_manager.lookup(raw_mention_text)
        return self._entities_for_aliases(aliases)

    def code_match(self, raw_mention_text: str) -> list[CanonicalEntity]:
        """Return existing entities for stock code aliases only."""

        aliases = [
            alias
            for alias in self._alias_manager.lookup(raw_mention_text)
            if alias.alias_type is AliasType.CODE
        ]
        return self._entities_for_aliases(aliases)

    def rule_match(self, raw_mention_text: str) -> list[CanonicalEntity]:
        """Return entities for verified ENT_* IDs or suffixed stock ts_codes."""

        normalized_text = normalize_alias_text(raw_mention_text)
        if not normalized_text:
            return []

        if validate_entity_id(normalized_text):
            entity = self._entity_repo.get(normalized_text)
            return [] if entity is None else [entity]

        if "." not in normalized_text:
            return []

        try:
            canonical_entity_id = generate_stock_entity_id(normalized_text)
        except ValueError:
            return []

        entity = self._entity_repo.get(canonical_entity_id)
        return [] if entity is None else [entity]

    def collect_candidates(
        self,
        raw_mention_text: str,
        *,
        context: ResolutionContext | dict[str, object] | None = None,
        fuzzy_matcher: FuzzyMatcher | None = None,
        ner_extractor: NERExtractor | None = None,
        limit: int = 10,
    ) -> MentionCandidateSet:
        """Collect deterministic candidates, then fuzzy candidates if needed."""

        return self.collect_candidates_with_fuzzy(
            raw_mention_text,
            context=context,
            fuzzy_matcher=fuzzy_matcher,
            ner_extractor=ner_extractor,
            limit=limit,
        )

    def collect_candidates_with_fuzzy(
        self,
        raw_mention_text: str,
        *,
        context: ResolutionContext | dict[str, object] | None = None,
        fuzzy_matcher: FuzzyMatcher | None = None,
        ner_extractor: NERExtractor | None = None,
        limit: int = 10,
    ) -> MentionCandidateSet:
        """Collect deterministic candidates, then fuzzy candidates if needed."""

        candidates = self._collect_deterministic_candidates(raw_mention_text)

        deterministic_hits = [
            entity.canonical_entity_id
            for entity in candidates
        ]
        if len(deterministic_hits) == 1:
            return MentionCandidateSet(
                raw_mention_text=raw_mention_text,
                deterministic_hits=deterministic_hits,
                fuzzy_hits=[],
                llm_required=False,
                final_status=FinalStatus.RESOLVED,
            )

        try:
            fuzzy_candidates = _generate_fuzzy_candidates(
                raw_mention_text,
                context=context,
                fuzzy_matcher=fuzzy_matcher,
                ner_extractor=ner_extractor,
                limit=limit,
            )
        except Exception as exc:
            _LOGGER.exception("fuzzy candidate generation failed")
            failure_rationale = f"fuzzy candidate generation failed: {exc}"
            final_status, llm_required = _candidate_status(
                deterministic_hits,
                [],
                {},
                auto_resolve_threshold=_auto_resolve_threshold(fuzzy_matcher),
            )
            return MentionCandidateSet(
                raw_mention_text=raw_mention_text,
                deterministic_hits=deterministic_hits,
                fuzzy_hits=[],
                llm_required=llm_required,
                final_status=final_status,
                failure_rationale=failure_rationale,
            )

        fuzzy_hits = [candidate.canonical_entity_id for candidate in fuzzy_candidates]
        fuzzy_scores = {
            candidate.canonical_entity_id: candidate.score
            for candidate in fuzzy_candidates
        }
        final_status, llm_required = _candidate_status(
            deterministic_hits,
            fuzzy_hits,
            fuzzy_scores,
            auto_resolve_threshold=_auto_resolve_threshold(fuzzy_matcher),
        )

        return MentionCandidateSet(
            raw_mention_text=raw_mention_text,
            deterministic_hits=deterministic_hits,
            fuzzy_hits=fuzzy_hits,
            fuzzy_scores=fuzzy_scores,
            fuzzy_candidates=fuzzy_candidates,
            llm_required=llm_required,
            final_status=final_status,
        )

    def resolve(self, raw_mention_text: str) -> ResolutionDecision:
        """Return a deterministic decision without audit writes."""

        candidate_set = self.collect_candidates(raw_mention_text)
        return _decision_from_candidate_set(candidate_set)

    def resolve_candidate_set(
        self,
        candidate_set: MentionCandidateSet,
        *,
        auto_resolve_threshold: float = 0.96,
    ) -> ResolutionDecision:
        """Return a deterministic decision from a pre-collected candidate set."""

        return _decision_from_candidate_set(
            candidate_set,
            auto_resolve_threshold=auto_resolve_threshold,
        )

    def _collect_deterministic_candidates(
        self,
        raw_mention_text: str,
    ) -> list[CanonicalEntity]:
        candidates = self.rule_match(raw_mention_text)
        if candidates:
            return candidates

        aliases = self._alias_manager.lookup(raw_mention_text)
        code_aliases = [
            alias
            for alias in aliases
            if alias.alias_type is AliasType.CODE
        ]
        if code_aliases:
            return self._entities_for_aliases(code_aliases)

        return self._entities_for_aliases(aliases)

    def _entities_for_aliases(
        self,
        aliases: list[EntityAlias],
    ) -> list[CanonicalEntity]:
        entities_by_id: dict[str, CanonicalEntity] = {}
        for alias in aliases:
            if alias.canonical_entity_id in entities_by_id:
                continue

            entity = self._entity_repo.get(alias.canonical_entity_id)
            if entity is None:
                continue

            entities_by_id[entity.canonical_entity_id] = entity

        return [
            entities_by_id[canonical_entity_id]
            for canonical_entity_id in sorted(entities_by_id)
        ]


def _decision_from_candidate_set(
    candidate_set: MentionCandidateSet,
    *,
    auto_resolve_threshold: float = 0.96,
) -> ResolutionDecision:
    """Derive a deterministic decision without re-reading candidate repositories."""

    if candidate_set.failure_rationale is not None:
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=candidate_set.failure_rationale,
        )

    if len(candidate_set.deterministic_hits) == 1:
        return ResolutionDecision(
            selected_entity_id=candidate_set.deterministic_hits[0],
            method=ResolutionMethod.DETERMINISTIC,
            confidence=1.0,
            rationale="single deterministic candidate",
        )

    if (
        not candidate_set.deterministic_hits
        and len(candidate_set.fuzzy_hits) == 1
        and candidate_set.fuzzy_scores.get(candidate_set.fuzzy_hits[0], 0.0)
        >= auto_resolve_threshold
    ):
        entity_id = candidate_set.fuzzy_hits[0]
        return ResolutionDecision(
            selected_entity_id=entity_id,
            method=ResolutionMethod.FUZZY,
            confidence=candidate_set.fuzzy_scores[entity_id],
            rationale="single high-confidence fuzzy candidate",
        )

    if candidate_set.deterministic_hits:
        rationale = "ambiguous deterministic candidates"
    elif candidate_set.fuzzy_hits:
        rationale = "ambiguous or low-confidence fuzzy candidates"
    else:
        rationale = "no deterministic candidates"

    return ResolutionDecision(
        selected_entity_id=None,
        method=ResolutionMethod.UNRESOLVED,
        confidence=None,
        rationale=rationale,
    )


def resolve_mention(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None = None,
) -> MentionResolutionResult:
    """Resolve one mention through the configured deterministic path."""

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

    return resolve_mention_with_repositories(
        raw_mention_text,
        context,
        entity_repo=repository_context.entity_repo,
        alias_repo=repository_context.alias_repo,
        reference_repo=repository_context.reference_repo,
        case_repo=repository_context.case_repo,
        fuzzy_matcher=repository_context.fuzzy_matcher,
        ner_extractor=repository_context.ner_extractor,
        reasoner_client=repository_context.reasoner_client,
    )


@overload
def resolve_mention_with_repositories(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None,
    *,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    audit_repo: ReadableResolutionAuditRepository,
    reference_repo: ReferenceRepository | None = ...,
    case_repo: ResolutionCaseRepository | None = ...,
    fuzzy_matcher: FuzzyMatcher | None = ...,
    ner_extractor: NERExtractor | None = ...,
    reasoner_client: ReasonerRuntimeClient | None = ...,
    existing_reference_id: str,
    allow_new_reference_id: bool = ...,
) -> MentionResolutionResult: ...


@overload
def resolve_mention_with_repositories(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None,
    *,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    audit_repo: None = ...,
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
    fuzzy_matcher: FuzzyMatcher | None = ...,
    ner_extractor: NERExtractor | None = ...,
    reasoner_client: ReasonerRuntimeClient | None = ...,
    existing_reference_id: str,
    allow_new_reference_id: bool = ...,
) -> MentionResolutionResult: ...


@overload
def resolve_mention_with_repositories(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None,
    *,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    audit_repo: ResolutionAuditRepository | None = ...,
    reference_repo: ReferenceRepository | None = ...,
    case_repo: ResolutionCaseRepository | None = ...,
    fuzzy_matcher: FuzzyMatcher | None = ...,
    ner_extractor: NERExtractor | None = ...,
    reasoner_client: ReasonerRuntimeClient | None = ...,
    existing_reference_id: None = ...,
    allow_new_reference_id: bool = ...,
) -> MentionResolutionResult: ...


def resolve_mention_with_repositories(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None,
    *,
    entity_repo: EntityRepository,
    alias_repo: AliasRepository,
    audit_repo: ResolutionAuditRepository | None = None,
    reference_repo: ReferenceRepository | None = None,
    case_repo: ResolutionCaseRepository | None = None,
    fuzzy_matcher: FuzzyMatcher | None = None,
    ner_extractor: NERExtractor | None = None,
    reasoner_client: ReasonerRuntimeClient | None = None,
    existing_reference_id: str | None = None,
    allow_new_reference_id: bool = False,
) -> MentionResolutionResult:
    """Resolve one mention using explicit repositories and write audit records.

    When ``existing_reference_id`` is provided, validation reads from the same
    audit boundary that will receive ``save_resolution``. Supplying
    ``audit_repo`` for that path requires ``ReadableResolutionAuditRepository``;
    otherwise the read comes from ``ReferenceRepository`` before the public
    case-repository ownership preflight and before any mutation.
    """

    if existing_reference_id is not None and not existing_reference_id.strip():
        raise ValueError("existing_reference_id must be a non-empty string")
    existing_reference = _validate_existing_reference_for_update(
        existing_reference_id,
        raw_mention_text,
        reference_repo,
        audit_repo=audit_repo,
        allow_new_reference_id=allow_new_reference_id,
    )

    matcher = DeterministicMatcher(entity_repo, alias_repo)
    candidate_set = matcher.collect_candidates_with_fuzzy(
        raw_mention_text,
        context=context,
        fuzzy_matcher=fuzzy_matcher,
        ner_extractor=ner_extractor,
    )
    decision, decision_type = _resolve_candidate_set_decision(
        matcher,
        candidate_set,
        context=context,
        entity_repo=entity_repo,
        reasoner_client=reasoner_client,
        auto_resolve_threshold=_auto_resolve_threshold(fuzzy_matcher),
    )
    source_context = _source_context_from(context)
    resolved_entity_id = decision.selected_entity_id
    resolution_method = (
        decision.method
        if resolved_entity_id is not None
        else ResolutionMethod.UNRESOLVED
    )
    resolution_confidence = decision.confidence if resolved_entity_id is not None else None
    candidate_entity_ids = _candidate_entity_ids(candidate_set)

    reference_payload = {
        "reference_id": existing_reference_id or _new_reference_id(),
        "raw_mention_text": raw_mention_text,
        "source_context": source_context,
        "resolved_entity_id": resolved_entity_id,
        "resolution_method": resolution_method,
        "resolution_confidence": resolution_confidence,
    }
    if existing_reference is not None:
        reference_payload["created_at"] = existing_reference.created_at

    reference = EntityReference(**reference_payload)
    case = ResolutionCase(
        case_id=_new_case_id(),
        reference_id=reference.reference_id,
        candidate_entity_ids=candidate_entity_ids,
        selected_entity_id=resolved_entity_id,
        decision_type=decision_type,
        decision_rationale=decision.rationale,
    )
    _save_resolution_audit(
        reference,
        case,
        audit_repo=audit_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
    )
    return MentionResolutionResult(
        raw_mention_text=raw_mention_text,
        resolved_entity_id=resolved_entity_id,
        resolution_method=resolution_method,
        resolution_confidence=resolution_confidence,
    )


def _resolve_candidate_set_decision(
    matcher: DeterministicMatcher,
    candidate_set: MentionCandidateSet,
    *,
    context: ResolutionContext | dict[str, object] | None,
    entity_repo: EntityRepository,
    reasoner_client: ReasonerRuntimeClient | None,
    auto_resolve_threshold: float,
) -> tuple[ResolutionDecision, DecisionType]:
    decision = matcher.resolve_candidate_set(
        candidate_set,
        auto_resolve_threshold=auto_resolve_threshold,
    )
    candidate_entity_ids = _candidate_entity_ids(candidate_set)

    if decision.selected_entity_id is not None:
        return decision, DecisionType.AUTO

    if candidate_set.llm_required and candidate_entity_ids:
        if reasoner_client is None:
            return (
                _attach_candidate_failure_rationale(
                    ResolutionDecision(
                        selected_entity_id=None,
                        method=ResolutionMethod.UNRESOLVED,
                        confidence=None,
                        rationale="reasoner client is not configured",
                    ),
                    candidate_set.failure_rationale,
                ),
                DecisionType.MANUAL_REVIEW,
            )
        return (
            _attach_candidate_failure_rationale(
                _resolve_with_reasoner(
                    candidate_set,
                    context=context,
                    entity_repo=entity_repo,
                    reasoner_client=reasoner_client,
                ),
                candidate_set.failure_rationale,
            ),
            DecisionType.LLM_ASSISTED,
        )

    return (
        _attach_candidate_failure_rationale(
            decision,
            candidate_set.failure_rationale,
        ),
        DecisionType.AUTO
        if not candidate_entity_ids
        else DecisionType.MANUAL_REVIEW,
    )


def _attach_candidate_failure_rationale(
    decision: ResolutionDecision,
    failure_rationale: str | None,
) -> ResolutionDecision:
    if failure_rationale is None or failure_rationale in decision.rationale:
        return decision
    return decision.model_copy(
        update={"rationale": f"{decision.rationale}; {failure_rationale}"},
    )


def _resolve_with_reasoner(
    candidate_set: MentionCandidateSet,
    *,
    context: ResolutionContext | dict[str, object] | None,
    entity_repo: EntityRepository,
    reasoner_client: ReasonerRuntimeClient,
) -> ResolutionDecision:
    candidates = _llm_candidates_from_candidate_set(candidate_set, entity_repo)
    request = build_disambiguation_request(
        candidate_set.raw_mention_text,
        context,
        candidates,
    )
    try:
        response = reasoner_client.disambiguate(request)
    except Exception as exc:
        _LOGGER.exception("reasoner disambiguation failed")
        error_text = str(exc)
        if "selected_entity_id" in error_text and "candidate" in error_text:
            rationale = f"invalid reasoner selection: {error_text}"
        else:
            rationale = f"reasoner disambiguation failed: {error_text}"
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=rationale,
        )

    if isinstance(response, dict):
        try:
            response = LLMDisambiguationResponse.model_validate(
                response,
                context={
                    "candidate_entity_ids": [
                        candidate.canonical_entity_id
                        for candidate in request.candidates
                    ],
                },
            )
        except Exception as exc:
            _LOGGER.exception("reasoner disambiguation failed")
            error_text = str(exc)
            if "selected_entity_id" in error_text and "candidate" in error_text:
                rationale = f"invalid reasoner selection: {error_text}"
            else:
                rationale = f"reasoner disambiguation failed: {error_text}"
            return ResolutionDecision(
                selected_entity_id=None,
                method=ResolutionMethod.UNRESOLVED,
                confidence=None,
                rationale=rationale,
            )

    if not isinstance(response, LLMDisambiguationResponse):
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=(
                "reasoner disambiguation failed: unsupported response type "
                f"{type(response).__name__}"
            ),
        )

    return _decision_from_llm_response(response, request.candidates)


def _decision_from_llm_response(
    response: LLMDisambiguationResponse,
    candidates: list[LLMDisambiguationCandidate],
) -> ResolutionDecision:
    candidate_ids = {candidate.canonical_entity_id for candidate in candidates}
    selected_entity_id = response.selected_entity_id

    if selected_entity_id is None:
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=f"reasoner declined: {response.rationale}",
        )
    if selected_entity_id not in candidate_ids:
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=(
                "invalid reasoner selection outside candidate set: "
                f"{selected_entity_id}"
            ),
        )
    if response.confidence is None:
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=f"reasoner confidence missing: {response.rationale}",
        )
    if (
        not math.isfinite(response.confidence)
        or response.confidence < _LLM_CONFIDENCE_THRESHOLD
    ):
        return ResolutionDecision(
            selected_entity_id=None,
            method=ResolutionMethod.UNRESOLVED,
            confidence=None,
            rationale=(
                "reasoner confidence below threshold "
                f"{_LLM_CONFIDENCE_THRESHOLD}: {response.rationale}"
            ),
        )

    return ResolutionDecision(
        selected_entity_id=selected_entity_id,
        method=ResolutionMethod.LLM,
        confidence=response.confidence,
        rationale=response.rationale,
    )


def _llm_candidates_from_candidate_set(
    candidate_set: MentionCandidateSet,
    entity_repo: EntityRepository,
) -> list[LLMDisambiguationCandidate]:
    candidates: list[LLMDisambiguationCandidate] = []
    seen: set[str] = set()

    for entity_id in candidate_set.deterministic_hits:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        candidates.append(
            LLMDisambiguationCandidate(
                canonical_entity_id=entity_id,
                display_name=_display_name_for(entity_id, entity_repo),
                alias_text=None,
                alias_type=None,
                score=None,
                source="deterministic",
            )
        )

    fuzzy_candidates_by_id = {
        candidate.canonical_entity_id: candidate
        for candidate in candidate_set.fuzzy_candidates
    }
    for entity_id in candidate_set.fuzzy_hits:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        fuzzy_candidate = fuzzy_candidates_by_id.get(entity_id)
        if fuzzy_candidate is None:
            candidates.append(
                LLMDisambiguationCandidate(
                    canonical_entity_id=entity_id,
                    display_name=_display_name_for(entity_id, entity_repo),
                    alias_text=None,
                    alias_type=None,
                    score=candidate_set.fuzzy_scores.get(entity_id),
                    source="fuzzy",
                )
            )
            continue

        candidates.append(
            LLMDisambiguationCandidate(
                canonical_entity_id=fuzzy_candidate.canonical_entity_id,
                display_name=_display_name_for(
                    fuzzy_candidate.canonical_entity_id,
                    entity_repo,
                ),
                alias_text=fuzzy_candidate.alias_text,
                alias_type=fuzzy_candidate.alias_type.value,
                score=fuzzy_candidate.score,
                source=fuzzy_candidate.source,
            )
        )

    return candidates


def _display_name_for(
    entity_id: str,
    entity_repo: EntityRepository,
) -> str | None:
    entity = entity_repo.get(entity_id)
    return None if entity is None else entity.display_name


def _save_resolution_audit(
    reference: EntityReference,
    case: ResolutionCase,
    *,
    audit_repo: ResolutionAuditRepository | None,
    reference_repo: ReferenceRepository | None,
    case_repo: ResolutionCaseRepository | None,
) -> None:
    if audit_repo is not None:
        # Caller-supplied audit_repo owns the unit of work; do not interpose
        # cohesion checks against the separately-provided reference/case repos.
        audit_repo.save_resolution(reference, case)
        return

    if reference_repo is None or case_repo is None:
        raise ResolutionAuditRepositoryRequiredError(
            "resolution audit writes require audit_repo or reference_repo/case_repo"
        )

    audit_reference_repo = _validate_repository_audit_cohesion(
        reference_repo,
        case_repo,
    )
    audit_reference_repo.save_resolution(reference, case)


def _validate_repository_audit_cohesion(
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
) -> ResolutionAuditReferenceRepository:
    """Return the public audit UoW, rejecting split write repositories.

    Cohesion is verified before mutation through the public
    ``owns_resolution_case_repository`` preflight. The guard intentionally
    avoids inspecting adapter internals or requiring object identity with a
    private case repository attribute.
    """

    save_resolution = getattr(reference_repo, "save_resolution", None)
    if not callable(save_resolution):
        raise ResolutionAuditRepositoryRequiredError(
            "resolution audit writes require a native save_resolution(reference, case) "
            "unit of work; separate reference/case writes are not supported",
        )

    owns_case_repo = getattr(reference_repo, "owns_resolution_case_repository", None)
    if not callable(owns_case_repo):
        raise ResolutionAuditRepositoryRequiredError(
            "resolution audit writes require a native "
            "owns_resolution_case_repository(case_repo) cohesion preflight",
        )
    if not owns_case_repo(case_repo):
        raise ResolutionAuditRepositoryRequiredError(
            "resolution audit repository does not own the configured case_repo; "
            "save_resolution must write to the same case_repo passed to "
            "resolve_mention_with_repositories",
        )
    return cast(ResolutionAuditReferenceRepository, reference_repo)


def _validate_existing_reference_for_update(
    existing_reference_id: str | None,
    raw_mention_text: str,
    reference_repo: ReferenceRepository | None,
    *,
    audit_repo: ResolutionAuditRepository | None = None,
    allow_new_reference_id: bool = False,
) -> EntityReference | None:
    if existing_reference_id is None:
        return None

    get_reference = _reference_reader_for_update(reference_repo, audit_repo)
    if get_reference is None:
        raise ResolutionAuditRepositoryRequiredError(
            "existing_reference_id requires the audit write boundary to expose "
            "get(reference_id): audit_repo.get(...) when audit_repo is provided, "
            "otherwise reference_repo.get(...)",
        )

    existing_reference = get_reference(existing_reference_id)
    if existing_reference is None:
        if allow_new_reference_id:
            return None
        raise ValueError(
            f"existing_reference_id {existing_reference_id!r} was not found",
        )
    if existing_reference.resolved_entity_id is not None:
        raise ValueError(
            "existing_reference_id must refer to an unresolved reference",
        )
    if existing_reference.raw_mention_text != raw_mention_text:
        raise ValueError(
            "existing_reference_id raw_mention_text does not match the supplied "
            "raw_mention_text",
        )
    if existing_reference.resolution_method is not ResolutionMethod.UNRESOLVED:
        raise ValueError(
            "existing_reference_id must refer to an unresolved reference",
        )
    return existing_reference


def _reference_reader_for_update(
    reference_repo: ReferenceRepository | None,
    audit_repo: ResolutionAuditRepository | None,
) -> Callable[[str], EntityReference | None] | None:
    if audit_repo is not None:
        get_reference = getattr(audit_repo, "get", None)
        if callable(get_reference):
            return cast(ReadableResolutionAuditRepository, audit_repo).get
        return None

    if reference_repo is not None:
        return reference_repo.get

    return None


def _generate_fuzzy_candidates(
    raw_mention_text: str,
    *,
    context: ResolutionContext | dict[str, object] | None,
    fuzzy_matcher: FuzzyMatcher | None,
    ner_extractor: NERExtractor | None,
    limit: int,
) -> list[FuzzyCandidate]:
    if fuzzy_matcher is None:
        return []

    query_text = _fuzzy_query_text(
        raw_mention_text,
        context=context,
        ner_extractor=ner_extractor,
    )
    return fuzzy_matcher.generate_candidates(query_text, context=context, limit=limit)


def _fuzzy_query_text(
    raw_mention_text: str,
    *,
    context: ResolutionContext | dict[str, object] | None,
    ner_extractor: NERExtractor | None,
) -> str:
    if ner_extractor is None:
        return raw_mention_text

    extracted_mentions = ner_extractor.extract_mentions(
        raw_mention_text,
        context=context,
    )
    if len(extracted_mentions) == 1:
        return extracted_mentions[0].mention_text
    return raw_mention_text


def _candidate_status(
    deterministic_hits: list[str],
    fuzzy_hits: list[str],
    fuzzy_scores: dict[str, float],
    *,
    auto_resolve_threshold: float,
) -> tuple[FinalStatus, bool]:
    if len(deterministic_hits) == 1:
        return FinalStatus.RESOLVED, False
    if deterministic_hits:
        return FinalStatus.MANUAL_REVIEW, True
    if (
        len(fuzzy_hits) == 1
        and fuzzy_scores.get(fuzzy_hits[0], 0.0) >= auto_resolve_threshold
    ):
        return FinalStatus.RESOLVED, False
    if fuzzy_hits:
        return FinalStatus.MANUAL_REVIEW, True
    return FinalStatus.UNRESOLVED, False


def _candidate_entity_ids(candidate_set: MentionCandidateSet) -> list[str]:
    candidate_ids: list[str] = []
    for entity_id in candidate_set.deterministic_hits + candidate_set.fuzzy_hits:
        if entity_id not in candidate_ids:
            candidate_ids.append(entity_id)
    return candidate_ids


def _auto_resolve_threshold(fuzzy_matcher: FuzzyMatcher | None) -> float:
    if fuzzy_matcher is None:
        return 0.96
    threshold = getattr(fuzzy_matcher, "auto_resolve_score", 0.96)
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "auto_resolve_score must be finite and between 0.0 and 1.0",
        ) from exc
    if not math.isfinite(threshold_value) or not 0.0 <= threshold_value <= 1.0:
        raise ValueError("auto_resolve_score must be finite and between 0.0 and 1.0")
    return threshold_value


def _source_context_from(
    context: ResolutionContext | dict[str, object] | None,
) -> dict:
    if context is None:
        return {}
    if isinstance(context, ResolutionContext):
        return context.model_dump(mode="json")
    if isinstance(context, dict):
        return dict(context)
    raise TypeError("context must be a ResolutionContext, dict, or None")


__all__ = [
    "DeterministicMatcher",
    "ReadableResolutionAuditRepository",
    "ResolutionAuditRepository",
    "ResolutionAuditRepositoryRequiredError",
    "resolve_mention",
    "resolve_mention_with_repositories",
]
