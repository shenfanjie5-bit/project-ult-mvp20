"""P1c end-to-end smoke runner for queue, cycle, manifest, and formal serving."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import json
import sys
from time import perf_counter_ns
from types import MappingProxyType
from typing import Any, Final, TypeVar
from uuid import uuid4

from data_platform.cycle import (
    CycleAlreadyExists,
    CycleMetadata,
    create_cycle,
    freeze_cycle_candidates,
    publish_manifest,
    transition_cycle_status,
)
from data_platform.queue import CandidateQueueItem, submit_candidate
from data_platform.queue.worker import validate_pending_candidates


P1C_FORMAL_OBJECT_TYPE: Final[str] = "recommendation_snapshot"
P1C_FORMAL_TABLE_IDENTIFIER: Final[str] = f"formal.{P1C_FORMAL_OBJECT_TYPE}"
P1C_SUBMITTED_BY: Final[str] = "p1c-smoke"
P1C_CANDIDATE_COUNT: Final[int] = 3
_REQUIRED_DURATION_STEPS: Final[tuple[str, ...]] = (
    "submit",
    "validate",
    "freeze",
    "publish_manifest",
    "formal_latest",
)
_MAX_CYCLE_DATE_ATTEMPTS: Final[int] = 3660
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class P1cSmokeResult:
    """Result summary for one P1c smoke run."""

    cycle_id: str
    candidate_count: int
    manifest_snapshot_id: int
    duration_ms: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.candidate_count < P1C_CANDIDATE_COUNT:
            msg = f"candidate_count must be at least {P1C_CANDIDATE_COUNT}"
            raise ValueError(msg)
        if self.manifest_snapshot_id < 1:
            msg = "manifest_snapshot_id must be a positive integer"
            raise ValueError(msg)

        durations = {str(step): int(duration) for step, duration in self.duration_ms.items()}
        missing_steps = sorted(set(_REQUIRED_DURATION_STEPS).difference(durations))
        if missing_steps:
            msg = "duration_ms missing required smoke steps: " + ", ".join(missing_steps)
            raise ValueError(msg)
        object.__setattr__(self, "duration_ms", MappingProxyType(durations))

    def to_json_payload(self) -> dict[str, object]:
        """Return a JSON-serializable result payload."""

        return {
            "cycle_id": self.cycle_id,
            "candidate_count": self.candidate_count,
            "manifest_snapshot_id": self.manifest_snapshot_id,
            "duration_ms": dict(self.duration_ms),
        }


def run_p1c_smoke(partition_date: date | None = None) -> P1cSmokeResult:
    """Run the P1c submit, freeze, manifest, and formal-serving smoke."""

    from data_platform.config import reset_settings_cache

    if partition_date is not None and not isinstance(partition_date, date):
        msg = "partition_date must be a datetime.date or None"
        raise TypeError(msg)

    reset_settings_cache()
    started_ns = perf_counter_ns()
    durations: dict[str, int] = {}
    smoke_run_id = str(uuid4())
    start_date = partition_date or date.today()

    submitted = _measure_step(
        durations,
        "submit",
        lambda: _submit_smoke_candidates(smoke_run_id),
    )
    _measure_step(
        durations,
        "validate",
        lambda: validate_pending_candidates(limit=max(P1C_CANDIDATE_COUNT, 100)),
    )
    _assert_candidates_accepted(submitted)

    cycle = _measure_step(
        durations,
        "create_cycle",
        lambda: _create_next_available_cycle(start_date),
    )
    metadata = _measure_step(
        durations,
        "freeze",
        lambda: freeze_cycle_candidates(cycle.cycle_id),
    )
    _assert_selection_matches_metadata(metadata, submitted)

    _measure_step(
        durations,
        "transition",
        lambda: _transition_to_phase3(cycle.cycle_id),
    )
    manifest = _measure_step(
        durations,
        "publish_manifest",
        lambda: _write_formal_snapshot_and_publish(
            cycle.cycle_id,
            metadata.candidate_count,
            smoke_run_id,
        ),
    )
    manifest_snapshot_id = (
        manifest.formal_table_snapshots[P1C_FORMAL_TABLE_IDENTIFIER].snapshot_id
    )

    latest = _measure_step(
        durations,
        "formal_latest",
        lambda: _get_formal_latest(P1C_FORMAL_OBJECT_TYPE),
    )
    by_id = _measure_step(
        durations,
        "formal_by_id",
        lambda: _get_formal_by_id(cycle.cycle_id, P1C_FORMAL_OBJECT_TYPE),
    )
    _assert_formal_serving_result(
        cycle_id=cycle.cycle_id,
        smoke_run_id=smoke_run_id,
        snapshot_id=manifest_snapshot_id,
        latest=latest,
        by_id=by_id,
    )

    durations["total"] = int((perf_counter_ns() - started_ns) / 1_000_000)
    return P1cSmokeResult(
        cycle_id=cycle.cycle_id,
        candidate_count=metadata.candidate_count,
        manifest_snapshot_id=manifest_snapshot_id,
        duration_ms=durations,
    )


def _submit_smoke_candidates(smoke_run_id: str) -> list[CandidateQueueItem]:
    return [
        submit_candidate(
            {
                "payload_type": "Ex-1",
                "submitted_by": P1C_SUBMITTED_BY,
                "smoke_run_id": smoke_run_id,
                "candidate_index": index,
                "object_type": P1C_FORMAL_OBJECT_TYPE,
            }
        )
        for index in range(P1C_CANDIDATE_COUNT)
    ]


def _create_next_available_cycle(start_date: date) -> CycleMetadata:
    cycle_date = start_date
    for _attempt in range(_MAX_CYCLE_DATE_ATTEMPTS):
        try:
            return create_cycle(cycle_date)
        except CycleAlreadyExists:
            cycle_date += timedelta(days=1)

    msg = (
        "could not create an available smoke cycle within "
        f"{_MAX_CYCLE_DATE_ATTEMPTS} days from {start_date.isoformat()}"
    )
    raise RuntimeError(msg)


def _transition_to_phase3(cycle_id: str) -> CycleMetadata:
    transition_cycle_status(cycle_id, "phase1")
    transition_cycle_status(cycle_id, "phase2")
    return transition_cycle_status(cycle_id, "phase3")


def _write_formal_snapshot_and_publish(
    cycle_id: str,
    candidate_count: int,
    smoke_run_id: str,
) -> Any:
    snapshot_id = _write_formal_fixture_snapshot(
        cycle_id=cycle_id,
        candidate_count=candidate_count,
        smoke_run_id=smoke_run_id,
    )
    return publish_manifest(
        cycle_id,
        {
            "formal.world_state_snapshot": snapshot_id,
            "formal.official_alpha_pool": snapshot_id,
            "formal.alpha_result_snapshot": snapshot_id,
            P1C_FORMAL_TABLE_IDENTIFIER: snapshot_id,
        },
        recommendation_provenance={
            "cycle_id": cycle_id,
            "current_cycle_id": cycle_id,
            "source_layer": "L8",
            "source_kind": "current-cycle",
            "recommendation_snapshot_id": snapshot_id,
            "audit_record_ids": [f"audit-p1c-smoke-{cycle_id}-{smoke_run_id}"],
            "replay_record_ids": [f"replay-p1c-smoke-{cycle_id}-{smoke_run_id}"],
        },
    )


def _write_formal_fixture_snapshot(
    *,
    cycle_id: str,
    candidate_count: int,
    smoke_run_id: str,
) -> int:
    import pyarrow as pa  # type: ignore[import-untyped]

    from data_platform.serving.catalog import ensure_namespaces, load_catalog

    schema = _formal_fixture_schema(pa)
    catalog = load_catalog()
    ensure_namespaces(catalog, [("formal",)])
    table = catalog.create_table_if_not_exists(
        P1C_FORMAL_TABLE_IDENTIFIER,
        schema=schema,
    )
    table.overwrite(
        pa.table(
            {
                "cycle_id": [cycle_id],
                "smoke_run_id": [smoke_run_id],
                "candidate_count": [candidate_count],
                "object_type": [P1C_FORMAL_OBJECT_TYPE],
            },
            schema=schema,
        )
    )
    snapshot = table.refresh().current_snapshot()
    if snapshot is None:
        msg = "formal fixture overwrite did not create an Iceberg snapshot"
        raise RuntimeError(msg)
    return int(snapshot.snapshot_id)


def _formal_fixture_schema(pa_module: Any) -> Any:
    return pa_module.schema(
        [
            pa_module.field("cycle_id", pa_module.string()),
            pa_module.field("smoke_run_id", pa_module.string()),
            pa_module.field("candidate_count", pa_module.int64()),
            pa_module.field("object_type", pa_module.string()),
        ]
    )


def _get_formal_latest(object_type: str) -> Any:
    from data_platform.serving.formal import get_formal_latest

    return get_formal_latest(object_type)


def _get_formal_by_id(cycle_id: str, object_type: str) -> Any:
    from data_platform.serving.formal import get_formal_by_id

    return get_formal_by_id(cycle_id, object_type)


def _assert_candidates_accepted(submitted: Sequence[CandidateQueueItem]) -> None:
    submitted_ids = [candidate.id for candidate in submitted]
    statuses = _candidate_validation_statuses(submitted_ids)
    missing_candidate_ids = sorted(set(submitted_ids).difference(statuses))
    if missing_candidate_ids:
        msg = "P1c smoke candidates were not found after validation: " + json.dumps(
            missing_candidate_ids
        )
        raise RuntimeError(msg)

    not_accepted = {
        candidate_id: status
        for candidate_id, status in statuses.items()
        if status != "accepted"
    }
    if not_accepted:
        msg = "P1c smoke candidates were not all accepted: " + json.dumps(
            not_accepted,
            sort_keys=True,
        )
        raise RuntimeError(msg)


def _assert_selection_matches_metadata(
    metadata: CycleMetadata,
    submitted: Sequence[CandidateQueueItem],
) -> None:
    selection_ids = _selection_candidate_ids(metadata.cycle_id)
    if len(selection_ids) != metadata.candidate_count:
        msg = (
            "cycle candidate_count does not match selection rows: "
            f"{metadata.candidate_count} != {len(selection_ids)}"
        )
        raise RuntimeError(msg)

    submitted_ids = {candidate.id for candidate in submitted}
    missing_submitted_ids = sorted(submitted_ids.difference(selection_ids))
    if missing_submitted_ids:
        msg = "smoke candidates missing from frozen selection: " + json.dumps(
            missing_submitted_ids
        )
        raise RuntimeError(msg)


def _assert_formal_serving_result(
    *,
    cycle_id: str,
    smoke_run_id: str,
    snapshot_id: int,
    latest: Any,
    by_id: Any,
) -> None:
    if latest.snapshot_id != snapshot_id or by_id.snapshot_id != snapshot_id:
        msg = (
            "formal serving snapshot mismatch: "
            f"manifest={snapshot_id} latest={latest.snapshot_id} by_id={by_id.snapshot_id}"
        )
        raise RuntimeError(msg)
    if latest.cycle_id != cycle_id or by_id.cycle_id != cycle_id:
        msg = (
            "formal serving cycle mismatch: "
            f"cycle={cycle_id} latest={latest.cycle_id} by_id={by_id.cycle_id}"
        )
        raise RuntimeError(msg)

    for name, formal_object in (("latest", latest), ("by_id", by_id)):
        payload = formal_object.payload
        if payload.num_rows != 1:
            msg = f"formal {name} payload should contain one row, got {payload.num_rows}"
            raise RuntimeError(msg)
        if payload.column("cycle_id").to_pylist() != [cycle_id]:
            msg = f"formal {name} payload cycle_id does not match {cycle_id}"
            raise RuntimeError(msg)
        if payload.column("smoke_run_id").to_pylist() != [smoke_run_id]:
            msg = f"formal {name} payload smoke_run_id does not match current run"
            raise RuntimeError(msg)


def _candidate_validation_statuses(candidate_ids: Sequence[int]) -> dict[int, str]:
    if not candidate_ids:
        return {}

    engine = _create_engine()
    try:
        with engine.connect() as connection:
            rows = list(
                connection.execute(
                    _text(
                        """
                        SELECT id, validation_status
                        FROM data_platform.candidate_queue
                        WHERE id = ANY(:candidate_ids)
                        """
                    ),
                    {"candidate_ids": list(candidate_ids)},
                )
            )
    finally:
        engine.dispose()

    return {int(row[0]): str(row[1]) for row in rows}


def _selection_candidate_ids(cycle_id: str) -> list[int]:
    engine = _create_engine()
    try:
        with engine.connect() as connection:
            rows = list(
                connection.execute(
                    _text(
                        """
                        SELECT candidate_id
                        FROM data_platform.cycle_candidate_selection
                        WHERE cycle_id = :cycle_id
                        ORDER BY candidate_id ASC
                        """
                    ),
                    {"cycle_id": cycle_id},
                )
            )
    finally:
        engine.dispose()

    return [int(row[0]) for row in rows]


def _create_engine() -> Any:
    from sqlalchemy import create_engine

    from data_platform.config import get_settings

    return create_engine(_sqlalchemy_postgres_uri(str(get_settings().pg_dsn)))


def _text(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


def _sqlalchemy_postgres_uri(dsn: str) -> str:
    if dsn.startswith("jdbc:postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("jdbc:postgresql://")
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgres://")
    return dsn


def _measure_step(
    durations: dict[str, int],
    name: str,
    action: Callable[[], _T],
) -> _T:
    started_ns = perf_counter_ns()
    try:
        return action()
    finally:
        durations[name] = int((perf_counter_ns() - started_ns) / 1_000_000)


def _parse_partition_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        msg = f"invalid ISO partition date: {raw_value!r}"
        raise argparse.ArgumentTypeError(msg) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Run the P1c smoke and print JSON duration telemetry."""

    parser = argparse.ArgumentParser(description="Run the P1c data-platform smoke.")
    parser.add_argument(
        "--partition-date",
        type=_parse_partition_date,
        default=None,
        help="first cycle date to try, in YYYY-MM-DD form",
    )
    args = parser.parse_args(argv)

    try:
        result = run_p1c_smoke(partition_date=args.partition_date)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result.to_json_payload(), sort_keys=True))
    print("P1c smoke OK")
    return 0


__all__ = [
    "P1C_FORMAL_OBJECT_TYPE",
    "P1cSmokeResult",
    "main",
    "run_p1c_smoke",
]


if __name__ == "__main__":
    raise SystemExit(main())
