"""Batch orchestration for mention resolution and review routing."""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from entity_registry.aliases import normalize_alias_text
from entity_registry.core import FinalStatus, ResolutionMethod
from entity_registry.fuzzy import (
    FuzzyCandidate,
    FuzzyMatcher,
    NullFuzzyMatcher,
    build_alias_blocking_key,
)
from entity_registry.references import EntityReference
from entity_registry.resolution import (
    resolve_mention,
    resolve_mention_with_repositories,
)
from entity_registry.resolution_types import (
    BatchResolutionJob,
    MentionResolutionResult,
    ResolutionContext,
)
from entity_registry.storage import (
    ReferenceRepository,
    ResolutionCaseRepository,
    ReviewRepository,
)


_DEFAULT_RESOLVE_MENTION = resolve_mention
_RESOLUTION_REPOSITORIES_REQUIRED_MESSAGE = (
    "resolution audit repositories are not configured; "
    "call configure_default_repositories(..., reference_repo=..., "
    "case_repo=...) before using public resolution APIs, or use "
    "configure_default_in_memory_audit_repositories() for tests/local workflows"
)

Resolver = Callable[
    ...,
    MentionResolutionResult,
]


class BatchReferenceInput(BaseModel):
    """Normalized input for one batch resolution item."""

    raw_mention_text: str
    source_context: dict[str, object] = Field(default_factory=dict)
    source_reference_id: str | None = None

    @field_validator("raw_mention_text")
    @classmethod
    def validate_raw_mention_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("raw_mention_text must be a non-empty string")
        return value

    @field_validator("source_reference_id")
    @classmethod
    def validate_source_reference_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("source_reference_id must be a non-empty string")
        return value


class BatchCandidateGroup(BaseModel):
    """Candidate group shared by one or more unresolved references."""

    group_id: str
    reference_ids: list[str]
    raw_mentions: list[str]
    candidate_entity_ids: list[str]
    max_score: float | None
    normalized_mention: str
    blocking_key: str | None = None


class BatchResolutionOutcome(BaseModel):
    """Resolution outcome for one source reference input."""

    source_reference_id: str | None
    result: MentionResolutionResult
    final_status: FinalStatus
    error: str | None = None


class BatchResolutionReport(BaseModel):
    """Detailed batch result for schedulers and manual-review handoff."""

    job: BatchResolutionJob
    groups: list[BatchCandidateGroup]
    outcomes: list[BatchResolutionOutcome]
    resolved_reference_ids: list[str]
    unresolved_reference_ids: list[str]
    manual_review_reference_ids: list[str]
    errors: list[str]


def collect_unresolved_references(
    reference_repo: ReferenceRepository,
    *,
    limit: int | None = None,
) -> list[EntityReference]:
    """Return unresolved references from a repository with stable ordering."""

    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    unresolved = [
        reference
        for reference in reference_repo.find_unresolved()
        if (
            reference.resolution_method is ResolutionMethod.UNRESOLVED
            and reference.resolved_entity_id is None
        )
    ]
    unresolved.sort(key=lambda reference: (reference.created_at, reference.reference_id))

    if limit is None:
        return unresolved
    return unresolved[:limit]


def cluster_unresolved_references(
    references: Sequence[EntityReference],
    *,
    fuzzy_matcher: FuzzyMatcher | None = None,
    limit: int = 10,
) -> list[BatchCandidateGroup]:
    """Cluster unresolved references by mention text, blocking key, and candidates."""

    if limit < 0:
        raise ValueError("limit must be non-negative")

    matcher = fuzzy_matcher if fuzzy_matcher is not None else NullFuzzyMatcher()
    groups_by_key: dict[tuple[str, str | None, tuple[str, ...]], BatchCandidateGroup] = {}

    for reference in references:
        candidates = matcher.generate_candidates(
            reference.raw_mention_text,
            context=reference.source_context,
            limit=limit,
        )
        candidate_entity_ids = _candidate_entity_ids(candidates)
        normalized_mention = _normalize_group_mention(reference.raw_mention_text)
        blocking_key = _blocking_key_for(reference.raw_mention_text, candidates)
        group_key = (
            normalized_mention,
            blocking_key,
            tuple(sorted(candidate_entity_ids)),
        )

        group = groups_by_key.get(group_key)
        if group is None:
            group = BatchCandidateGroup(
                group_id=_group_id(group_key),
                reference_ids=[],
                raw_mentions=[],
                candidate_entity_ids=candidate_entity_ids,
                max_score=_max_score(candidates),
                normalized_mention=normalized_mention,
                blocking_key=blocking_key,
            )
            groups_by_key[group_key] = group

        if reference.reference_id not in group.reference_ids:
            group.reference_ids.append(reference.reference_id)
        if reference.raw_mention_text not in group.raw_mentions:
            group.raw_mentions.append(reference.raw_mention_text)
        group.max_score = _max_group_score(group.max_score, _max_score(candidates))

    return sorted(
        groups_by_key.values(),
        key=lambda group: (
            group.normalized_mention,
            group.blocking_key or "",
            group.group_id,
        ),
    )


def run_batch_resolution_job(
    job: BatchResolutionJob,
    references: Sequence[
        EntityReference | BatchReferenceInput | dict[str, object] | str
    ],
    *,
    resolver: Resolver | None = None,
    fuzzy_matcher: FuzzyMatcher | None = None,
) -> BatchResolutionReport:
    """Run one batch job by delegating every unique source reference to a resolver."""

    active_resolver = resolver if resolver is not None else _resolve_mention_for_batch
    inputs = [_coerce_reference_input(reference) for reference in references]
    job.reference_ids = _unique_ids([
        item.source_reference_id
        for item in inputs
        if item.source_reference_id is not None
    ])
    _mark_job_running(job)

    outcomes: list[BatchResolutionOutcome] = []
    errors: list[str] = []
    outcomes_by_reference_id: dict[str, BatchResolutionOutcome] = {}

    for item in inputs:
        cached = (
            outcomes_by_reference_id.get(item.source_reference_id)
            if item.source_reference_id is not None
            else None
        )
        if cached is not None:
            outcomes.append(cached.model_copy(deep=True))
            continue

        outcome = _resolve_one(item, active_resolver)
        if outcome.error is not None:
            errors.append(_outcome_error_message(outcome))
        if item.source_reference_id is not None:
            outcomes_by_reference_id[item.source_reference_id] = outcome
        outcomes.append(outcome)

    groups = cluster_unresolved_references(
        _candidate_group_references(inputs, outcomes),
        fuzzy_matcher=fuzzy_matcher,
    )
    resolved_reference_ids = _resolved_reference_ids(outcomes)
    unresolved_reference_ids = _unresolved_reference_ids(outcomes)
    manual_review_reference_ids = _manual_review_reference_ids(outcomes)

    if errors:
        _mark_job_failed(job, errors[0])
    else:
        _mark_job_completed(job)

    return BatchResolutionReport(
        job=job,
        groups=groups,
        outcomes=outcomes,
        resolved_reference_ids=resolved_reference_ids,
        unresolved_reference_ids=unresolved_reference_ids,
        manual_review_reference_ids=manual_review_reference_ids,
        errors=errors,
    )


def batch_resolve(
    references: Sequence[EntityReference | dict[str, object] | str],
) -> list[MentionResolutionResult]:
    """Resolve a batch of mentions and return the stable public result shape.

    Use batch_resolve_with_report(..., review_repo=...) when callers need the
    report fields required for manual-review handoff.
    """

    normalized_inputs = [_coerce_reference_input(reference) for reference in references]
    job = _new_batch_job(normalized_inputs)
    report = run_batch_resolution_job(job, normalized_inputs)
    _raise_for_report_errors(report)
    return [outcome.result for outcome in report.outcomes]


def batch_resolve_with_report(
    references: Sequence[EntityReference | dict[str, object] | str],
    *,
    review_repo: ReviewRepository | None = None,
    reference_ids: Sequence[str | None] | None = None,
) -> BatchResolutionReport:
    """Resolve a batch and return the manual-review handoff report.

    Anonymous dict/string inputs are assigned durable reference IDs before
    resolution. Callers can pass reference_ids to make those assignments stable
    across retry attempts.

    When review_repo is provided, unresolved outputs are enqueued before this
    function returns. If enqueue fails after audit persistence, the returned
    report records the enqueue error so callers can retry
    enqueue_batch_manual_review(report, ...) with the same configured reference
    and case repositories.
    """

    repository_context = _get_default_resolution_repository_context()
    normalized_inputs = _ensure_source_reference_ids(
        [_coerce_reference_input(reference) for reference in references],
        reference_ids=reference_ids,
    )
    job = _new_batch_job(normalized_inputs)
    report = run_batch_resolution_job(
        job,
        normalized_inputs,
        fuzzy_matcher=repository_context.fuzzy_matcher,
    )
    _raise_for_report_errors(report)

    if review_repo is not None:
        _enqueue_manual_review_items(
            report,
            reference_repo=repository_context.reference_repo,
            case_repo=repository_context.case_repo,
            review_repo=review_repo,
        )

    return report


def _new_batch_job(inputs: Sequence[BatchReferenceInput]) -> BatchResolutionJob:
    return BatchResolutionJob(
        job_id=_new_job_id(),
        reference_ids=_unique_ids([
            item.source_reference_id
            for item in inputs
            if item.source_reference_id is not None
        ]),
        status="pending",
    )


def _ensure_source_reference_ids(
    inputs: Sequence[BatchReferenceInput],
    *,
    reference_ids: Sequence[str | None] | None = None,
) -> list[BatchReferenceInput]:
    if reference_ids is not None and len(reference_ids) != len(inputs):
        raise ValueError("reference_ids length must match references length")

    normalized: list[BatchReferenceInput] = []
    for index, item in enumerate(inputs):
        supplied_reference_id = (
            None if reference_ids is None else reference_ids[index]
        )
        if supplied_reference_id is not None:
            if (
                not isinstance(supplied_reference_id, str)
                or not supplied_reference_id.strip()
            ):
                raise ValueError("reference_ids must contain non-empty strings")

        if item.source_reference_id is not None:
            if (
                supplied_reference_id is not None
                and supplied_reference_id != item.source_reference_id
            ):
                raise ValueError(
                    "reference_ids cannot override an input source_reference_id"
                )
            normalized.append(item)
            continue

        normalized.append(
            item.model_copy(
                update={
                    "source_reference_id": (
                        supplied_reference_id or _new_batch_reference_id()
                    ),
                },
            )
        )
    _validate_effective_reference_ids(normalized)
    return normalized


def _validate_effective_reference_ids(inputs: Sequence[BatchReferenceInput]) -> None:
    seen_by_reference_id: dict[str, BatchReferenceInput] = {}
    for item in inputs:
        if item.source_reference_id is None:
            continue

        existing = seen_by_reference_id.get(item.source_reference_id)
        if existing is None:
            seen_by_reference_id[item.source_reference_id] = item
            continue

        raise ValueError(
            "duplicate source_reference_id in batch inputs: "
            f"{item.source_reference_id}"
        )


def _enqueue_manual_review_items(
    report: BatchResolutionReport,
    *,
    reference_repo: ReferenceRepository,
    case_repo: ResolutionCaseRepository,
    review_repo: ReviewRepository,
) -> None:
    from entity_registry.review import enqueue_batch_manual_review

    try:
        enqueue_batch_manual_review(
            report,
            reference_repo=reference_repo,
            case_repo=case_repo,
            review_repo=review_repo,
        )
    except Exception as exc:
        error = f"manual review enqueue failed: {type(exc).__name__}: {exc}"
        report.errors.append(error)
        _mark_job_failed(report.job, error)


def _get_default_resolution_repository_context():
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
            _RESOLUTION_REPOSITORIES_REQUIRED_MESSAGE,
        )
    return repository_context


def _raise_for_report_errors(report: BatchResolutionReport) -> None:
    if report.errors:
        raise RuntimeError(
            "batch resolution failed: " + "; ".join(report.errors),
        )


def _coerce_reference_input(
    reference: EntityReference | BatchReferenceInput | dict[str, object] | str,
) -> BatchReferenceInput:
    if isinstance(reference, BatchReferenceInput):
        return reference
    if isinstance(reference, EntityReference):
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
        if source_reference_id is not None and not isinstance(source_reference_id, str):
            raise ValueError("source_reference_id must be a string when provided")

        return BatchReferenceInput(
            raw_mention_text=_required_text(payload, "raw_mention_text"),
            source_context=dict(source_context),
            source_reference_id=source_reference_id,
        )
    raise TypeError("batch references must be EntityReference, dict, or str")


def _resolve_one(
    item: BatchReferenceInput,
    resolver: Resolver,
) -> BatchResolutionOutcome:
    try:
        result = _call_resolver(resolver, item)
        if not isinstance(result, MentionResolutionResult):
            result = MentionResolutionResult.model_validate(result)
    except Exception as exc:
        result = MentionResolutionResult(
            raw_mention_text=item.raw_mention_text,
            resolved_entity_id=None,
            resolution_method=ResolutionMethod.UNRESOLVED,
            resolution_confidence=None,
        )
        return BatchResolutionOutcome(
            source_reference_id=item.source_reference_id,
            result=result,
            final_status=FinalStatus.UNRESOLVED,
            error=f"{type(exc).__name__}: {exc}",
        )

    return BatchResolutionOutcome(
        source_reference_id=item.source_reference_id,
        result=result,
        final_status=_final_status_for(result),
        error=None,
    )


def _call_resolver(
    resolver: Resolver,
    item: BatchReferenceInput,
) -> MentionResolutionResult:
    if (
        item.source_reference_id is not None
        and _resolver_accepts_existing_reference_id(resolver)
    ):
        return resolver(
            item.raw_mention_text,
            item.source_context,
            existing_reference_id=item.source_reference_id,
        )
    return resolver(item.raw_mention_text, item.source_context)


def _resolve_mention_for_batch(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None = None,
    *,
    existing_reference_id: str | None = None,
) -> MentionResolutionResult:
    if resolve_mention is not _DEFAULT_RESOLVE_MENTION:
        return resolve_mention(raw_mention_text, context)

    if existing_reference_id is None:
        return resolve_mention(raw_mention_text, context)

    repository_context = _get_default_resolution_repository_context()
    return resolve_mention_with_repositories(
        raw_mention_text,
        context,
        entity_repo=repository_context.entity_repo,
        alias_repo=repository_context.alias_repo,
        reference_repo=repository_context.reference_repo,
        case_repo=repository_context.case_repo,
        fuzzy_matcher=getattr(repository_context, "fuzzy_matcher", None),
        ner_extractor=getattr(repository_context, "ner_extractor", None),
        reasoner_client=repository_context.reasoner_client,
        existing_reference_id=existing_reference_id,
        allow_new_reference_id=True,
    )


def _resolver_accepts_existing_reference_id(resolver: Resolver) -> bool:
    try:
        parameters = inspect.signature(resolver).parameters
    except (TypeError, ValueError):
        return False

    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or name == "existing_reference_id"
        for name, parameter in parameters.items()
    )


def _final_status_for(result: MentionResolutionResult) -> FinalStatus:
    if (
        result.resolved_entity_id is not None
        and result.resolution_method
        in {
            ResolutionMethod.DETERMINISTIC,
            ResolutionMethod.FUZZY,
            ResolutionMethod.LLM,
            ResolutionMethod.MANUAL,
        }
    ):
        return FinalStatus.RESOLVED
    # FinalStatus.MANUAL_REVIEW is reserved for the persistent review queue in #10.
    # This batch layer routes unresolved/error outcomes to manual_review_reference_ids.
    return FinalStatus.UNRESOLVED


def _candidate_group_references(
    inputs: Sequence[BatchReferenceInput],
    outcomes: Sequence[BatchResolutionOutcome],
) -> list[EntityReference]:
    references: list[EntityReference] = []
    for index, (item, outcome) in enumerate(zip(inputs, outcomes, strict=True)):
        if not _routes_to_manual_review(outcome):
            continue

        references.append(
            EntityReference(
                reference_id=item.source_reference_id or f"batch-input:{index}",
                raw_mention_text=item.raw_mention_text,
                source_context=dict(item.source_context),
                resolved_entity_id=outcome.result.resolved_entity_id,
                resolution_method=outcome.result.resolution_method,
                resolution_confidence=outcome.result.resolution_confidence,
            )
        )
    return references


def _routes_to_manual_review(outcome: BatchResolutionOutcome) -> bool:
    return (
        outcome.final_status is FinalStatus.MANUAL_REVIEW
        or outcome.result.resolved_entity_id is None
        or outcome.error is not None
    )


def _resolved_reference_ids(outcomes: Sequence[BatchResolutionOutcome]) -> list[str]:
    return _unique_ids([
        outcome.source_reference_id
        for outcome in outcomes
        if outcome.source_reference_id is not None
        if outcome.final_status is FinalStatus.RESOLVED
    ])


def _unresolved_reference_ids(outcomes: Sequence[BatchResolutionOutcome]) -> list[str]:
    return _unique_ids([
        outcome.source_reference_id
        for outcome in outcomes
        if outcome.source_reference_id is not None
        if outcome.result.resolved_entity_id is None
    ])


def _manual_review_reference_ids(
    outcomes: Sequence[BatchResolutionOutcome],
) -> list[str]:
    return _unique_ids([
        outcome.source_reference_id
        for outcome in outcomes
        if outcome.source_reference_id is not None
        if _routes_to_manual_review(outcome)
    ])


def _unique_ids(reference_ids: Sequence[str]) -> list[str]:
    unique: list[str] = []
    for reference_id in reference_ids:
        if reference_id not in unique:
            unique.append(reference_id)
    return unique


def _required_text(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _candidate_entity_ids(candidates: Sequence[FuzzyCandidate]) -> list[str]:
    best_by_entity: dict[str, FuzzyCandidate] = {}
    for candidate in candidates:
        current = best_by_entity.get(candidate.canonical_entity_id)
        if current is None or _candidate_sort_key(candidate) < _candidate_sort_key(
            current
        ):
            best_by_entity[candidate.canonical_entity_id] = candidate

    return [
        candidate.canonical_entity_id
        for candidate in sorted(best_by_entity.values(), key=_candidate_sort_key)
    ]


def _candidate_sort_key(candidate: FuzzyCandidate) -> tuple[float, str, str]:
    return (-candidate.score, candidate.canonical_entity_id, candidate.alias_text)


def _normalize_group_mention(raw_mention_text: str) -> str:
    return normalize_alias_text(raw_mention_text).casefold()


def _blocking_key_for(
    raw_mention_text: str,
    candidates: Sequence[FuzzyCandidate],
) -> str | None:
    blocking_keys = sorted(
        {
            candidate.blocking_key
            for candidate in candidates
            if candidate.blocking_key
        }
    )
    if blocking_keys:
        return "|".join(blocking_keys)

    fallback = build_alias_blocking_key(raw_mention_text)
    return fallback[:4] or None


def _max_score(candidates: Sequence[FuzzyCandidate]) -> float | None:
    if not candidates:
        return None
    return max(candidate.score for candidate in candidates)


def _max_group_score(
    current: float | None,
    incoming: float | None,
) -> float | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return max(current, incoming)


def _group_id(group_key: tuple[str, str | None, tuple[str, ...]]) -> str:
    payload = "|".join(
        [
            group_key[0],
            group_key[1] or "",
            ",".join(group_key[2]),
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"BCG_{digest}"


def _outcome_error_message(outcome: BatchResolutionOutcome) -> str:
    source = outcome.source_reference_id or outcome.result.raw_mention_text
    return f"{source}: {outcome.error}"


def _mark_job_running(job: BatchResolutionJob) -> None:
    job.status = "running"
    job.started_at = _utcnow()
    job.completed_at = None
    job.error_summary = None


def _mark_job_completed(job: BatchResolutionJob) -> None:
    job.status = "completed"
    job.completed_at = _utcnow()
    job.error_summary = None


def _mark_job_failed(job: BatchResolutionJob, error_summary: str) -> None:
    job.status = "failed"
    job.completed_at = _utcnow()
    job.error_summary = error_summary[:500]


def _new_job_id() -> str:
    return f"BATCH_{uuid4().hex}"


def _new_batch_reference_id() -> str:
    return f"REF_{uuid4().hex}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "BatchCandidateGroup",
    "BatchReferenceInput",
    "BatchResolutionOutcome",
    "BatchResolutionReport",
    "batch_resolve",
    "batch_resolve_with_report",
    "cluster_unresolved_references",
    "collect_unresolved_references",
    "run_batch_resolution_job",
]
