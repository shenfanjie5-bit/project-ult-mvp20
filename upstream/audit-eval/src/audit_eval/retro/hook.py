"""Production-safe retrospective hook for published daily cycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal, Protocol

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.audit.manifest_gateway import FormalSnapshotGateway, ManifestGateway
from audit_eval.audit.query import (
    DagsterRunGateway,
    GraphSnapshotGateway,
    ReplayQueryContext,
)
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.contracts.manifest_draft import CyclePublishManifestDraft
from audit_eval.contracts.replay_record import ReplayRecord
from audit_eval.contracts.retrospective import RetrospectiveEvaluation
from audit_eval.retro.compute import compute_retrospective
from audit_eval.retro.horizon import (
    HORIZONS,
    horizon_to_days,
    is_outcome_mature,
    resolve_evaluation_date,
)
from audit_eval.retro.schema import MarketOutcome, RetrospectiveTarget
from audit_eval.retro.storage import (
    RetrospectiveEvaluationStorage,
    RetrospectiveInputError,
    RetrospectiveInputGateway,
)

RetrospectiveHookState = Literal["pending", "completed"]

_FORBIDDEN_PROVENANCE_MARKERS = ("smoke", "fixture", "historical")


class RetrospectiveHookError(RetrospectiveInputError):
    """Raised when the production hook must fail closed."""


class RetrospectiveHookReplayRepository(Protocol):
    """Repository boundary used to prove audit/replay lineage is queryable."""

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        """Return the replay row for cycle_id/object_ref, if present."""

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        """Return persisted audit rows for the requested ids."""


class RetrospectiveHookReplayIdRepository(
    RetrospectiveHookReplayRepository,
    Protocol,
):
    """Repository boundary for durable replay-id lookups."""

    def get_replay_record_by_id(self, replay_id: str) -> ReplayRecord | None:
        """Return a persisted replay row by id, if present."""


class RetrospectiveHookStatusStorage(Protocol):
    """Optional write boundary for hook status records."""

    def append_statuses(
        self,
        statuses: Sequence["RetrospectiveHookStatus"],
    ) -> list[str]:
        """Append hook statuses and return persisted status ids."""


@dataclass(frozen=True)
class RetrospectiveHookRequest:
    """Input contract for the real daily-cycle retrospective hook."""

    cycle_id: str
    date_ref: date
    manifest_ref: str | None = None
    manifest: CyclePublishManifestDraft | None = None
    replay_ids: Sequence[str] = ()
    audit_record_ids: Sequence[str] = ()
    object_refs: Sequence[str] = ()
    horizons: Sequence[RetrospectiveHorizon] = HORIZONS
    provenance: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle_id", _require_non_empty(self.cycle_id, "cycle_id"))
        if self.manifest_ref is not None:
            object.__setattr__(
                self,
                "manifest_ref",
                _require_non_empty(self.manifest_ref, "manifest_ref"),
            )
        if self.manifest_ref is None and self.manifest is None:
            raise RetrospectiveHookError(
                "cycle_publish_manifest ref or row is required"
            )
        object.__setattr__(
            self,
            "replay_ids",
            _normalize_string_sequence(self.replay_ids, "replay_ids"),
        )
        object.__setattr__(
            self,
            "audit_record_ids",
            _normalize_string_sequence(self.audit_record_ids, "audit_record_ids"),
        )
        object.__setattr__(
            self,
            "object_refs",
            _normalize_string_sequence(self.object_refs, "object_refs"),
        )
        object.__setattr__(
            self,
            "horizons",
            _normalize_horizons(self.horizons),
        )


@dataclass(frozen=True)
class RetrospectiveHookStatus:
    """One object/horizon hook status record.

    Pending statuses intentionally contain no retrospective metric fields.
    Completed statuses only point to an evaluation written by
    ``compute_retrospective``.
    """

    status_id: str
    cycle_id: str
    object_ref: str
    horizon: RetrospectiveHorizon
    status: RetrospectiveHookState
    reason: str
    manifest_ref: str
    replay_id: str
    audit_record_ids: tuple[str, ...]
    outcome_maturity_date: date
    recorded_at: datetime
    evaluation_id: str | None = None


@dataclass(frozen=True)
class RetrospectiveHookResult:
    """Result returned to the orchestrator adapter."""

    request: RetrospectiveHookRequest
    manifest_cycle_id: str
    manifest_ref: str
    replay_ids: tuple[str, ...]
    audit_record_ids: tuple[str, ...]
    statuses: tuple[RetrospectiveHookStatus, ...]
    recorded_status_ids: tuple[str, ...]

    @property
    def completed_evaluation_ids(self) -> tuple[str, ...]:
        """Evaluation ids that were truly computed and persisted."""

        return tuple(
            status.evaluation_id
            for status in self.statuses
            if status.status == "completed" and status.evaluation_id is not None
        )

    @property
    def pending_statuses(self) -> tuple[RetrospectiveHookStatus, ...]:
        """Statuses still waiting on real outcome data or dependencies."""

        return tuple(status for status in self.statuses if status.status == "pending")


class InMemoryRetrospectiveHookStatusStorage:
    """In-memory hook status storage for tests and Lite adapters."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append_statuses(
        self,
        statuses: Sequence[RetrospectiveHookStatus],
    ) -> list[str]:
        rows = [asdict(status) for status in statuses]
        for index, row in enumerate(rows):
            assert_no_forbidden_write(row, path=f"$.retrospective_hook[{index}]")
        self.rows.extend(deepcopy(rows))
        return [status.status_id for status in statuses]


def run_real_retrospective_hook(
    request: RetrospectiveHookRequest,
    *,
    repository: RetrospectiveHookReplayRepository,
    manifest_gateway: ManifestGateway | None = None,
    require_manifest_gateway: bool = False,
    formal_gateway: FormalSnapshotGateway | None = None,
    dagster_gateway: DagsterRunGateway | None = None,
    graph_gateway: GraphSnapshotGateway | None = None,
    input_gateway: RetrospectiveInputGateway | None = None,
    evaluation_storage: RetrospectiveEvaluationStorage | None = None,
    status_storage: RetrospectiveHookStatusStorage | None = None,
    as_of_date: date | None = None,
    recorded_at: datetime | None = None,
) -> RetrospectiveHookResult:
    """Validate published lineage and record real retrospective hook status.

    The hook fails closed for missing manifest, missing audit/replay lineage, or
    forbidden non-production provenance. It only writes completed metrics via
    ``compute_retrospective`` when a real outcome gateway and evaluation
    storage are provided and the requested horizon is mature.
    """

    _validate_no_forbidden_provenance(
        request.provenance or {},
        path="$.request.provenance",
    )
    manifest = _load_manifest(
        request,
        manifest_gateway,
        require_manifest_gateway=require_manifest_gateway,
    )
    manifest_ref = request.manifest_ref or manifest.published_cycle_id
    _validate_manifest(request, manifest, manifest_ref=manifest_ref)

    replay_records = _resolve_replay_records(request, repository, manifest)
    audit_records = _load_and_validate_audit_records(
        request,
        repository,
        replay_records,
    )
    _validate_lineage_provenance(
        manifest=manifest,
        manifest_ref=manifest_ref,
        replay_records=replay_records,
        audit_records=audit_records,
    )

    effective_as_of_date = as_of_date or date.today()
    effective_recorded_at = recorded_at or datetime.now(timezone.utc)
    replay_context = _build_replay_context(
        repository=repository,
        manifest=manifest,
        manifest_gateway=manifest_gateway,
        formal_gateway=formal_gateway,
        dagster_gateway=dagster_gateway,
        graph_gateway=graph_gateway,
    )
    statuses: list[RetrospectiveHookStatus] = []
    for replay_record in replay_records:
        for horizon in request.horizons:
            statuses.append(
                _evaluate_or_mark_pending(
                    request=request,
                    manifest_ref=manifest_ref,
                    replay_record=replay_record,
                    horizon=horizon,
                    replay_context=replay_context,
                    input_gateway=input_gateway,
                    evaluation_storage=evaluation_storage,
                    formal_gateway=formal_gateway,
                    dagster_gateway=dagster_gateway,
                    graph_gateway=graph_gateway,
                    as_of_date=effective_as_of_date,
                    recorded_at=effective_recorded_at,
                )
            )

    recorded_status_ids: tuple[str, ...] = ()
    if status_storage is not None and statuses:
        recorded_status_ids = tuple(status_storage.append_statuses(statuses))

    return RetrospectiveHookResult(
        request=request,
        manifest_cycle_id=manifest.published_cycle_id,
        manifest_ref=manifest_ref,
        replay_ids=tuple(record.replay_id for record in replay_records),
        audit_record_ids=tuple(
            dict.fromkeys(
                record_id
                for replay_record in replay_records
                for record_id in replay_record.audit_record_ids
            )
        ),
        statuses=tuple(statuses),
        recorded_status_ids=recorded_status_ids,
    )


def _load_manifest(
    request: RetrospectiveHookRequest,
    manifest_gateway: ManifestGateway | None,
    *,
    require_manifest_gateway: bool = False,
) -> CyclePublishManifestDraft:
    if require_manifest_gateway:
        if manifest_gateway is None:
            raise RetrospectiveHookError(
                "durable cycle_publish_manifest gateway is required",
            )
        manifest = _load_manifest_from_gateway(request, manifest_gateway)
        if request.manifest is not None:
            _validate_request_manifest_matches_durable_manifest(
                request.manifest,
                manifest,
            )
        return manifest

    if request.manifest is not None:
        return request.manifest
    if manifest_gateway is None:
        raise RetrospectiveHookError(
            "cycle_publish_manifest missing: no manifest row or gateway was provided"
        )
    return _load_manifest_from_gateway(request, manifest_gateway)


def _load_manifest_from_gateway(
    request: RetrospectiveHookRequest,
    manifest_gateway: ManifestGateway,
) -> CyclePublishManifestDraft:
    try:
        manifest = manifest_gateway.load(request.cycle_id)
    except RetrospectiveHookError:
        raise
    except Exception as exc:
        raise RetrospectiveHookError(
            "cycle_publish_manifest missing or unreadable for "
            f"cycle_id={request.cycle_id!r}"
        ) from exc
    if manifest is None:
        raise RetrospectiveHookError(
            "cycle_publish_manifest missing for "
            f"cycle_id={request.cycle_id!r}"
        )
    return manifest


def _validate_request_manifest_matches_durable_manifest(
    request_manifest: CyclePublishManifestDraft,
    durable_manifest: CyclePublishManifestDraft,
) -> None:
    if request_manifest.published_cycle_id != durable_manifest.published_cycle_id:
        raise RetrospectiveHookError(
            "cycle_publish_manifest request row does not match durable manifest: "
            "published_cycle_id",
        )
    if dict(request_manifest.snapshot_refs) != dict(durable_manifest.snapshot_refs):
        raise RetrospectiveHookError(
            "cycle_publish_manifest request row does not match durable manifest: "
            "snapshot_refs",
        )


def _validate_manifest(
    request: RetrospectiveHookRequest,
    manifest: CyclePublishManifestDraft,
    *,
    manifest_ref: str,
) -> None:
    if manifest.published_cycle_id != request.cycle_id:
        raise RetrospectiveHookError(
            "cycle_publish_manifest.published_cycle_id does not match cycle_id: "
            f"{manifest.published_cycle_id!r} != {request.cycle_id!r}"
        )
    if not manifest.snapshot_refs:
        raise RetrospectiveHookError(
            "cycle_publish_manifest.snapshot_refs must not be empty"
        )
    _validate_no_forbidden_provenance(
        {
            "manifest_ref": manifest_ref,
            "published_cycle_id": manifest.published_cycle_id,
            "snapshot_refs": manifest.snapshot_refs,
        },
        path="$.cycle_publish_manifest",
    )


def _resolve_replay_records(
    request: RetrospectiveHookRequest,
    repository: RetrospectiveHookReplayRepository,
    manifest: CyclePublishManifestDraft,
) -> tuple[ReplayRecord, ...]:
    replay_records = (
        _resolve_replay_records_by_id(request, repository)
        if request.replay_ids
        else _resolve_replay_records_by_object_ref(request, repository, manifest)
    )
    if not replay_records:
        raise RetrospectiveHookError("No replay records resolved for hook request")

    seen_replay_ids: set[str] = set()
    for replay_record in replay_records:
        if replay_record.replay_id in seen_replay_ids:
            raise RetrospectiveHookError(
                f"Duplicate replay_record id {replay_record.replay_id!r}"
            )
        seen_replay_ids.add(replay_record.replay_id)
        _validate_replay_record(request, manifest, replay_record)

    if request.object_refs:
        requested_object_refs = set(request.object_refs)
        unexpected_object_refs = [
            replay_record.object_ref
            for replay_record in replay_records
            if replay_record.object_ref not in requested_object_refs
        ]
        if unexpected_object_refs:
            raise RetrospectiveHookError(
                "Resolved replay records include object_refs outside request: "
                f"{', '.join(unexpected_object_refs)}"
            )
    return replay_records


def _resolve_replay_records_by_id(
    request: RetrospectiveHookRequest,
    repository: RetrospectiveHookReplayRepository,
) -> tuple[ReplayRecord, ...]:
    get_by_id = getattr(repository, "get_replay_record_by_id", None)
    if not callable(get_by_id):
        raise RetrospectiveHookError(
            "replay_ids require a repository with get_replay_record_by_id"
        )
    records: list[ReplayRecord] = []
    for replay_id in request.replay_ids:
        replay_record = get_by_id(replay_id)
        if replay_record is None:
            raise RetrospectiveHookError(
                f"replay_record {replay_id!r} is missing or not queryable"
            )
        records.append(replay_record)
    return tuple(records)


def _resolve_replay_records_by_object_ref(
    request: RetrospectiveHookRequest,
    repository: RetrospectiveHookReplayRepository,
    manifest: CyclePublishManifestDraft,
) -> tuple[ReplayRecord, ...]:
    object_refs = request.object_refs or tuple(manifest.snapshot_refs)
    records: list[ReplayRecord] = []
    for object_ref in object_refs:
        replay_record = repository.get_replay_record(request.cycle_id, object_ref)
        if replay_record is None:
            raise RetrospectiveHookError(
                "replay_record is missing or not queryable for "
                f"cycle_id={request.cycle_id!r}, object_ref={object_ref!r}"
            )
        records.append(replay_record)
    return tuple(records)


def _validate_replay_record(
    request: RetrospectiveHookRequest,
    manifest: CyclePublishManifestDraft,
    replay_record: ReplayRecord,
) -> None:
    if replay_record.cycle_id != request.cycle_id:
        raise RetrospectiveHookError(
            "ReplayRecord.cycle_id does not match hook cycle_id: "
            f"{replay_record.cycle_id!r} != {request.cycle_id!r}"
        )
    if replay_record.manifest_cycle_id != manifest.published_cycle_id:
        raise RetrospectiveHookError(
            "ReplayRecord.manifest_cycle_id does not match manifest: "
            f"{replay_record.manifest_cycle_id!r} != "
            f"{manifest.published_cycle_id!r}"
        )
    if replay_record.object_ref not in manifest.snapshot_refs:
        raise RetrospectiveHookError(
            "ReplayRecord.object_ref is not published by cycle_publish_manifest: "
            f"{replay_record.object_ref!r}"
        )
    if replay_record.object_ref not in replay_record.formal_snapshot_refs:
        raise RetrospectiveHookError(
            "ReplayRecord.formal_snapshot_refs missing its object_ref: "
            f"{replay_record.object_ref!r}"
        )
    for object_ref, replay_snapshot_ref in replay_record.formal_snapshot_refs.items():
        manifest_snapshot_ref = manifest.snapshot_refs.get(object_ref)
        if manifest_snapshot_ref is None:
            raise RetrospectiveHookError(
                "ReplayRecord.formal_snapshot_refs includes object_ref not present "
                f"in manifest: {object_ref!r}"
            )
        if replay_snapshot_ref != manifest_snapshot_ref:
            raise RetrospectiveHookError(
                "ReplayRecord.formal_snapshot_refs does not match manifest for "
                f"object_ref={object_ref!r}"
            )


def _load_and_validate_audit_records(
    request: RetrospectiveHookRequest,
    repository: RetrospectiveHookReplayRepository,
    replay_records: Sequence[ReplayRecord],
) -> tuple[AuditRecord, ...]:
    lineage_audit_ids = tuple(
        dict.fromkeys(
            audit_record_id
            for replay_record in replay_records
            for audit_record_id in replay_record.audit_record_ids
        )
    )
    provided_audit_ids = set(request.audit_record_ids)
    unlinked_audit_ids = provided_audit_ids.difference(lineage_audit_ids)
    if unlinked_audit_ids:
        raise RetrospectiveHookError(
            "Provided audit_record_ids are not referenced by resolved replay "
            f"records: {', '.join(sorted(unlinked_audit_ids))}"
        )

    audit_ids = tuple(dict.fromkeys((*lineage_audit_ids, *request.audit_record_ids)))
    records = repository.get_audit_records(audit_ids)
    records_by_id = {record.record_id: record for record in records}
    missing_ids = [
        audit_record_id
        for audit_record_id in audit_ids
        if audit_record_id not in records_by_id
    ]
    if missing_ids:
        raise RetrospectiveHookError(
            "audit_record rows are missing or not queryable: "
            f"{', '.join(missing_ids)}"
        )
    for record in records_by_id.values():
        if record.cycle_id != request.cycle_id:
            raise RetrospectiveHookError(
                "AuditRecord.cycle_id does not match hook cycle_id for "
                f"{record.record_id!r}"
            )
    return tuple(records_by_id[audit_record_id] for audit_record_id in audit_ids)


def _validate_lineage_provenance(
    *,
    manifest: CyclePublishManifestDraft,
    manifest_ref: str,
    replay_records: Sequence[ReplayRecord],
    audit_records: Sequence[AuditRecord],
) -> None:
    _validate_no_forbidden_provenance(
        {
            "manifest_ref": manifest_ref,
            "published_cycle_id": manifest.published_cycle_id,
            "snapshot_refs": manifest.snapshot_refs,
        },
        path="$.cycle_publish_manifest",
    )
    for index, replay_record in enumerate(replay_records):
        _validate_no_forbidden_provenance(
            replay_record.model_dump(mode="json"),
            path=f"$.replay_records[{index}]",
        )
    for index, audit_record in enumerate(audit_records):
        _validate_no_forbidden_provenance(
            audit_record.model_dump(mode="json"),
            path=f"$.audit_records[{index}]",
        )


def _evaluate_or_mark_pending(
    *,
    request: RetrospectiveHookRequest,
    manifest_ref: str,
    replay_record: ReplayRecord,
    horizon: RetrospectiveHorizon,
    replay_context: ReplayQueryContext | None,
    input_gateway: RetrospectiveInputGateway | None,
    evaluation_storage: RetrospectiveEvaluationStorage | None,
    formal_gateway: FormalSnapshotGateway | None,
    dagster_gateway: DagsterRunGateway | None,
    graph_gateway: GraphSnapshotGateway | None,
    as_of_date: date,
    recorded_at: datetime,
) -> RetrospectiveHookStatus:
    maturity_date = resolve_evaluation_date(request.date_ref, horizon)
    if not is_outcome_mature(horizon, request.date_ref, as_of_date):
        return _status(
            request=request,
            manifest_ref=manifest_ref,
            replay_record=replay_record,
            horizon=horizon,
            state="pending",
            reason="outcome_not_mature",
            maturity_date=maturity_date,
            recorded_at=recorded_at,
        )

    target = RetrospectiveTarget(replay_record.cycle_id, replay_record.object_ref)
    if input_gateway is None:
        return _status(
            request=request,
            manifest_ref=manifest_ref,
            replay_record=replay_record,
            horizon=horizon,
            state="pending",
            reason="outcome_gateway_unavailable",
            maturity_date=maturity_date,
            recorded_at=recorded_at,
        )
    try:
        outcome = input_gateway.load_market_outcome(target, horizon, request.date_ref)
    except (KeyError, RetrospectiveInputError):
        return _status(
            request=request,
            manifest_ref=manifest_ref,
            replay_record=replay_record,
            horizon=horizon,
            state="pending",
            reason="outcome_unavailable",
            maturity_date=maturity_date,
            recorded_at=recorded_at,
        )
    except Exception as exc:
        raise RetrospectiveHookError(
            "real outcome gateway failed for "
            f"cycle_id={target.cycle_id!r}, object_ref={target.object_ref!r}, "
            f"horizon={horizon!r}"
        ) from exc
    _validate_no_forbidden_provenance(
        asdict(outcome),
        path="$.market_outcome",
    )

    missing_dependencies = _missing_compute_dependencies(
        replay_record,
        replay_context=replay_context,
        evaluation_storage=evaluation_storage,
        formal_gateway=formal_gateway,
        dagster_gateway=dagster_gateway,
        graph_gateway=graph_gateway,
    )
    if missing_dependencies:
        return _status(
            request=request,
            manifest_ref=manifest_ref,
            replay_record=replay_record,
            horizon=horizon,
            state="pending",
            reason="retrospective_dependencies_unavailable",
            maturity_date=maturity_date,
            recorded_at=recorded_at,
        )

    assert replay_context is not None
    assert evaluation_storage is not None
    evaluations = compute_retrospective(
        horizon,
        request.date_ref,
        replay_context=replay_context,
        input_gateway=_SingleOutcomeInputGateway(target=target, outcome=outcome),
        storage=evaluation_storage,
        as_of_date=as_of_date,
    )
    if len(evaluations) != 1:
        raise RetrospectiveHookError(
            "retrospective computation produced an unexpected evaluation count: "
            f"{len(evaluations)}"
        )
    return _status(
        request=request,
        manifest_ref=manifest_ref,
        replay_record=replay_record,
        horizon=horizon,
        state="completed",
        reason="evaluation_computed",
        maturity_date=maturity_date,
        recorded_at=recorded_at,
        evaluation=evaluations[0],
    )


def _missing_compute_dependencies(
    replay_record: ReplayRecord,
    *,
    replay_context: ReplayQueryContext | None,
    evaluation_storage: RetrospectiveEvaluationStorage | None,
    formal_gateway: FormalSnapshotGateway | None,
    dagster_gateway: DagsterRunGateway | None,
    graph_gateway: GraphSnapshotGateway | None,
) -> tuple[str, ...]:
    missing: list[str] = []
    if replay_context is None:
        missing.append("replay_context")
    if evaluation_storage is None:
        missing.append("evaluation_storage")
    if formal_gateway is None:
        missing.append("formal_gateway")
    if dagster_gateway is None:
        missing.append("dagster_gateway")
    if replay_record.graph_snapshot_ref is not None and graph_gateway is None:
        missing.append("graph_gateway")
    return tuple(missing)


def _status(
    *,
    request: RetrospectiveHookRequest,
    manifest_ref: str,
    replay_record: ReplayRecord,
    horizon: RetrospectiveHorizon,
    state: RetrospectiveHookState,
    reason: str,
    maturity_date: date,
    recorded_at: datetime,
    evaluation: RetrospectiveEvaluation | None = None,
) -> RetrospectiveHookStatus:
    status = RetrospectiveHookStatus(
        status_id=f"retro-hook-{request.cycle_id}-{replay_record.object_ref}-{horizon}",
        cycle_id=request.cycle_id,
        object_ref=replay_record.object_ref,
        horizon=horizon,
        status=state,
        reason=reason,
        manifest_ref=manifest_ref,
        replay_id=replay_record.replay_id,
        audit_record_ids=tuple(replay_record.audit_record_ids),
        outcome_maturity_date=maturity_date,
        recorded_at=recorded_at,
        evaluation_id=evaluation.evaluation_id if evaluation is not None else None,
    )
    assert_no_forbidden_write(asdict(status), path="$.retrospective_hook_status")
    return status


def _build_replay_context(
    *,
    repository: RetrospectiveHookReplayRepository,
    manifest: CyclePublishManifestDraft,
    manifest_gateway: ManifestGateway | None,
    formal_gateway: FormalSnapshotGateway | None,
    dagster_gateway: DagsterRunGateway | None,
    graph_gateway: GraphSnapshotGateway | None,
) -> ReplayQueryContext | None:
    if formal_gateway is None:
        return None
    return ReplayQueryContext(
        repository=repository,
        manifest_gateway=manifest_gateway or _StaticManifestGateway(manifest),
        formal_gateway=formal_gateway,
        dagster_gateway=dagster_gateway,
        graph_gateway=graph_gateway,
    )


@dataclass(frozen=True)
class _StaticManifestGateway:
    manifest: CyclePublishManifestDraft

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        if cycle_id != self.manifest.published_cycle_id:
            raise RetrospectiveHookError(
                "cycle_publish_manifest missing for "
                f"cycle_id={cycle_id!r}"
            )
        return self.manifest


@dataclass(frozen=True)
class _SingleOutcomeInputGateway:
    target: RetrospectiveTarget
    outcome: MarketOutcome

    def list_targets(
        self,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> Sequence[RetrospectiveTarget]:
        return (self.target,)

    def load_market_outcome(
        self,
        target: RetrospectiveTarget,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> MarketOutcome:
        if target != self.target or horizon != self.outcome.horizon:
            raise RetrospectiveInputError("preloaded outcome does not match target")
        return self.outcome


def _validate_no_forbidden_provenance(payload: Any, *, path: str) -> None:
    if payload is None:
        return
    if isinstance(payload, str):
        lowered = payload.lower()
        for marker in _FORBIDDEN_PROVENANCE_MARKERS:
            if marker in lowered:
                raise RetrospectiveHookError(
                    f"Forbidden provenance marker {marker!r} at {path}"
                )
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_path = f"{path}.{key}" if isinstance(key, str) else f"{path}.*"
            _validate_no_forbidden_provenance(key, path=f"{path}.__key__")
            _validate_no_forbidden_provenance(value, path=key_path)
        return
    if isinstance(payload, Sequence) and not isinstance(
        payload,
        (bytes, bytearray),
    ):
        for index, value in enumerate(payload):
            _validate_no_forbidden_provenance(value, path=f"{path}[{index}]")


def _normalize_horizons(
    horizons: Sequence[RetrospectiveHorizon],
) -> tuple[RetrospectiveHorizon, ...]:
    normalized = tuple(dict.fromkeys(horizons))
    if not normalized:
        raise RetrospectiveHookError("horizons must not be empty")
    for horizon in normalized:
        horizon_to_days(horizon)
    return normalized


def _normalize_string_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        normalized.append(_require_non_empty(value, field_name))
    return tuple(dict.fromkeys(normalized))


def _require_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise RetrospectiveHookError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise RetrospectiveHookError(f"{field_name} must not be empty")
    return stripped


__all__ = [
    "InMemoryRetrospectiveHookStatusStorage",
    "RetrospectiveHookError",
    "RetrospectiveHookReplayIdRepository",
    "RetrospectiveHookReplayRepository",
    "RetrospectiveHookRequest",
    "RetrospectiveHookResult",
    "RetrospectiveHookState",
    "RetrospectiveHookStatus",
    "RetrospectiveHookStatusStorage",
    "run_real_retrospective_hook",
]
