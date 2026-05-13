"""Retrospective multi-horizon backfill orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import cast

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.audit.query import ReplayQueryContext
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.contracts.retrospective import RetrospectiveEvaluation
from audit_eval.retro.compute import compute_retrospective
from audit_eval.retro.horizon import HORIZONS, horizon_to_days, require_mature_horizon
from audit_eval.retro.schema import MarketOutcome, RetroWindow, RetrospectiveTarget
from audit_eval.retro.storage import (
    RetrospectiveEvaluationReader,
    RetrospectiveEvaluationStorage,
    RetrospectiveEvaluationWriteResult,
    RetrospectiveInputError,
    RetrospectiveInputGateway,
    RetrospectiveStorageError,
    get_default_evaluation_reader,
    get_default_evaluation_storage,
    get_default_input_gateway,
)


@dataclass(frozen=True)
class RetrospectiveJob:
    """Backfill request for one business date and a set of horizons."""

    date_ref: date
    horizons: tuple[RetrospectiveHorizon, ...] = HORIZONS
    object_ref: str | None = None


@dataclass(frozen=True)
class HorizonCoverageReport:
    """Coverage status for object/horizon retrospective evaluations."""

    expected_horizons: tuple[RetrospectiveHorizon, ...]
    object_refs: tuple[str, ...]
    covered_horizons_by_object: dict[str, tuple[RetrospectiveHorizon, ...]]
    missing_horizons_by_object: dict[str, tuple[RetrospectiveHorizon, ...]]
    covered_count: int
    expected_count: int
    coverage_ratio: float
    is_complete: bool


@dataclass(frozen=True)
class RetrospectiveBackfillResult:
    """Result of one idempotent retrospective backfill run."""

    job: RetrospectiveJob
    written_evaluation_ids: tuple[str, ...]
    skipped_existing_ids: tuple[str, ...]
    coverage: HorizonCoverageReport


def run_backfill(
    date_ref: date,
    horizons: Sequence[RetrospectiveHorizon] = HORIZONS,
    *,
    object_ref: str | None = None,
    replay_context: ReplayQueryContext | None = None,
    input_gateway: RetrospectiveInputGateway | None = None,
    storage: RetrospectiveEvaluationStorage | None = None,
    reader: RetrospectiveEvaluationReader | None = None,
    as_of_date: date | None = None,
) -> RetrospectiveBackfillResult:
    """Run an idempotent backfill for all requested mature horizons."""

    requested_horizons = _normalize_horizons(horizons)
    normalized_object_ref = _normalize_optional_object_ref(object_ref)
    effective_as_of_date = as_of_date or date.today()
    for horizon in requested_horizons:
        require_mature_horizon(horizon, date_ref, effective_as_of_date)

    gateway = input_gateway or get_default_input_gateway()
    evaluation_storage = storage or get_default_evaluation_storage()
    evaluation_reader = _resolve_reader(reader, evaluation_storage)

    targets_by_horizon = _load_targets_by_horizon(
        gateway,
        requested_horizons,
        date_ref,
        object_ref=normalized_object_ref,
    )
    _require_requested_object_ref_targets(
        targets_by_horizon,
        requested_horizons,
        object_ref=normalized_object_ref,
    )
    existing_before_by_id = _load_existing_evaluations_by_id(
        evaluation_reader,
        targets_by_horizon,
    )
    targets_to_compute_by_horizon = _missing_targets_by_horizon(
        targets_by_horizon,
        existing_before_by_id,
    )

    collector = _CollectingEvaluationStorage()
    filtered_gateway = _BackfillInputGateway(
        delegate=gateway,
        targets_by_horizon=targets_to_compute_by_horizon,
    )
    for horizon in requested_horizons:
        if not targets_to_compute_by_horizon[horizon]:
            continue
        compute_retrospective(
            horizon,
            date_ref,
            replay_context=replay_context,
            input_gateway=filtered_gateway,
            storage=collector,
            as_of_date=effective_as_of_date,
        )

    write_result = (
        _upsert_evaluations_by_id(evaluation_storage, collector.evaluations)
        if collector.evaluations
        else RetrospectiveEvaluationWriteResult(
            written_evaluation_ids=(),
            skipped_existing_ids=(),
        )
    )
    persisted_evaluations_by_id = _load_existing_evaluations_by_id(
        evaluation_reader,
        targets_by_horizon,
    )
    skipped_existing_ids = _merge_skipped_existing_ids(
        targets_by_horizon,
        existing_before_by_id,
        write_result.skipped_existing_ids,
    )

    object_refs = _object_refs_for_targets(targets_by_horizon, requested_horizons)
    coverage = check_horizon_coverage(
        list(persisted_evaluations_by_id.values()),
        expected_horizons=requested_horizons,
        object_refs=object_refs,
    )
    return RetrospectiveBackfillResult(
        job=RetrospectiveJob(
            date_ref=date_ref,
            horizons=requested_horizons,
            object_ref=normalized_object_ref,
        ),
        written_evaluation_ids=write_result.written_evaluation_ids,
        skipped_existing_ids=skipped_existing_ids,
        coverage=coverage,
    )


def check_horizon_coverage(
    evaluations: Sequence[RetrospectiveEvaluation],
    *,
    expected_horizons: Sequence[RetrospectiveHorizon] = HORIZONS,
    object_refs: Sequence[str] | None = None,
) -> HorizonCoverageReport:
    """Report whether each object_ref has all expected horizon evaluations."""

    requested_horizons = _normalize_horizons(expected_horizons)
    requested_horizon_set = set(requested_horizons)
    if object_refs is None:
        report_object_refs = tuple(
            sorted({evaluation.object_ref for evaluation in evaluations})
        )
    else:
        report_object_refs = tuple(dict.fromkeys(object_refs))

    covered_by_object: dict[str, tuple[RetrospectiveHorizon, ...]] = {}
    missing_by_object: dict[str, tuple[RetrospectiveHorizon, ...]] = {}
    for object_ref in report_object_refs:
        present_horizons = {
            evaluation.horizon
            for evaluation in evaluations
            if evaluation.object_ref == object_ref
            and evaluation.horizon in requested_horizon_set
        }
        covered = tuple(
            horizon for horizon in requested_horizons if horizon in present_horizons
        )
        missing = tuple(
            horizon for horizon in requested_horizons if horizon not in present_horizons
        )
        covered_by_object[object_ref] = covered
        missing_by_object[object_ref] = missing

    expected_count = len(report_object_refs) * len(requested_horizons)
    covered_count = sum(len(horizons) for horizons in covered_by_object.values())
    coverage_ratio = 1.0 if expected_count == 0 else covered_count / expected_count
    return HorizonCoverageReport(
        expected_horizons=requested_horizons,
        object_refs=report_object_refs,
        covered_horizons_by_object=covered_by_object,
        missing_horizons_by_object=missing_by_object,
        covered_count=covered_count,
        expected_count=expected_count,
        coverage_ratio=coverage_ratio,
        is_complete=covered_count == expected_count,
    )


class _CollectingEvaluationStorage:
    def __init__(self) -> None:
        self.evaluations: list[RetrospectiveEvaluation] = []

    def append_evaluations(
        self,
        evaluations: Sequence[RetrospectiveEvaluation],
    ) -> list[str]:
        self.evaluations.extend(evaluations)
        return [evaluation.evaluation_id for evaluation in evaluations]

    def upsert_evaluations_by_id(
        self,
        evaluations: Sequence[RetrospectiveEvaluation],
    ) -> RetrospectiveEvaluationWriteResult:
        self.evaluations.extend(evaluations)
        return RetrospectiveEvaluationWriteResult(
            written_evaluation_ids=tuple(
                evaluation.evaluation_id for evaluation in evaluations
            ),
            skipped_existing_ids=(),
        )


@dataclass(frozen=True)
class _BackfillInputGateway:
    delegate: RetrospectiveInputGateway
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]]

    def list_targets(
        self,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> Sequence[RetrospectiveTarget]:
        return self.targets_by_horizon[horizon]

    def load_market_outcome(
        self,
        target: RetrospectiveTarget,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> MarketOutcome:
        return self.delegate.load_market_outcome(target, horizon, date_ref)


def _normalize_horizons(
    horizons: Sequence[RetrospectiveHorizon],
) -> tuple[RetrospectiveHorizon, ...]:
    normalized = tuple(dict.fromkeys(horizons))
    for horizon in normalized:
        horizon_to_days(horizon)
    return normalized


def _normalize_optional_object_ref(object_ref: str | None) -> str | None:
    if object_ref is None:
        return None
    if not isinstance(object_ref, str):
        raise RetrospectiveInputError("object_ref must be a string")
    stripped = object_ref.strip()
    if not stripped:
        raise RetrospectiveInputError("object_ref must not be empty")
    return stripped


def _resolve_reader(
    reader: RetrospectiveEvaluationReader | None,
    storage: RetrospectiveEvaluationStorage,
) -> RetrospectiveEvaluationReader:
    if reader is not None:
        return reader
    if hasattr(storage, "load_evaluations"):
        return cast(RetrospectiveEvaluationReader, storage)
    return get_default_evaluation_reader()


def _load_targets_by_horizon(
    gateway: RetrospectiveInputGateway,
    horizons: Sequence[RetrospectiveHorizon],
    date_ref: date,
    *,
    object_ref: str | None,
) -> dict[RetrospectiveHorizon, list[RetrospectiveTarget]]:
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]] = {}
    for horizon in horizons:
        targets = [
            target
            for target in gateway.list_targets(horizon, date_ref)
            if object_ref is None or target.object_ref == object_ref
        ]
        for index, target in enumerate(targets):
            assert_no_forbidden_write(
                asdict(target),
                path=f"$.targets[{horizon}][{index}]",
            )
        targets_by_horizon[horizon] = targets
    return targets_by_horizon


def _require_requested_object_ref_targets(
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]],
    horizons: Sequence[RetrospectiveHorizon],
    *,
    object_ref: str | None,
) -> None:
    if object_ref is None:
        return
    if any(targets_by_horizon[horizon] for horizon in horizons):
        return
    raise RetrospectiveInputError(
        f"No retrospective targets found for object_ref={object_ref!r}"
    )


def _missing_targets_by_horizon(
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]],
    existing_by_id: dict[str, RetrospectiveEvaluation],
) -> dict[RetrospectiveHorizon, list[RetrospectiveTarget]]:
    missing: dict[RetrospectiveHorizon, list[RetrospectiveTarget]] = {}
    for horizon, targets in targets_by_horizon.items():
        missing[horizon] = [
            target
            for target in targets
            if _evaluation_id(target, horizon) not in existing_by_id
        ]
    return missing


def _load_existing_evaluations_by_id(
    reader: RetrospectiveEvaluationReader,
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]],
) -> dict[str, RetrospectiveEvaluation]:
    expected_ids: set[str] = set()
    windows: set[tuple[RetrospectiveHorizon, str]] = set()
    for horizon, targets in targets_by_horizon.items():
        for target in targets:
            expected_ids.add(_evaluation_id(target, horizon))
            windows.add((horizon, target.object_ref))

    existing: dict[str, RetrospectiveEvaluation] = {}
    for horizon, object_ref in sorted(windows):
        for evaluation in reader.load_evaluations(
            RetroWindow(
                start=date.min,
                end=date.max,
                horizon=horizon,
                object_ref=object_ref,
            )
        ):
            if evaluation.evaluation_id in expected_ids:
                existing.setdefault(evaluation.evaluation_id, evaluation)
    return existing


def _merge_skipped_existing_ids(
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]],
    existing_before_by_id: dict[str, RetrospectiveEvaluation],
    storage_skipped_ids: Sequence[str],
) -> tuple[str, ...]:
    skipped: list[str] = []
    storage_skipped_set = set(storage_skipped_ids)
    for horizon, targets in targets_by_horizon.items():
        for target in targets:
            evaluation_id = _evaluation_id(target, horizon)
            if (
                evaluation_id in existing_before_by_id
                or evaluation_id in storage_skipped_set
            ) and evaluation_id not in skipped:
                skipped.append(evaluation_id)
    return tuple(skipped)


def _upsert_evaluations_by_id(
    storage: RetrospectiveEvaluationStorage,
    evaluations: Sequence[RetrospectiveEvaluation],
) -> RetrospectiveEvaluationWriteResult:
    if not hasattr(storage, "upsert_evaluations_by_id"):
        raise RetrospectiveStorageError(
            "Retrospective backfill requires storage.upsert_evaluations_by_id "
            "for atomic idempotency"
        )
    try:
        return storage.upsert_evaluations_by_id(evaluations)
    except RetrospectiveStorageError:
        raise
    except Exception as exc:
        raise RetrospectiveStorageError(
            f"upsert_evaluations_by_id failed: {exc}"
        ) from exc


def _object_refs_for_targets(
    targets_by_horizon: dict[RetrospectiveHorizon, list[RetrospectiveTarget]],
    horizons: Sequence[RetrospectiveHorizon],
) -> tuple[str, ...]:
    object_refs: dict[str, None] = {}
    for horizon in horizons:
        for target in targets_by_horizon[horizon]:
            object_refs.setdefault(target.object_ref, None)
    return tuple(object_refs)


def _evaluation_id(
    target: RetrospectiveTarget,
    horizon: RetrospectiveHorizon,
) -> str:
    return f"retro-{target.cycle_id}-{target.object_ref}-{horizon}"


__all__ = [
    "HorizonCoverageReport",
    "RetrospectiveBackfillResult",
    "RetrospectiveJob",
    "check_horizon_coverage",
    "run_backfill",
]
