"""data-platform readers that satisfy graph-engine's Phase 1 Protocols.

graph-engine Phase 1 promotion needs data-platform-owned read boundaries
for queue and canonical entity lookup:

* ``CandidateDeltaReader`` — reads frozen ``Ex3CandidateGraphDelta`` payloads
  from PostgreSQL ``candidate_queue`` joined to ``cycle_candidate_selection``.
* ``EntityAnchorReader`` — looks up ``canonical_entity`` / ``entity_alias``
  Iceberg tables via DuckDB to resolve graph node ids to canonical entity ids
  and to existence-check declared anchors.

Module ownership rationale (per CLAUDE.md):

* ``EntityAnchorReader`` impl lives here, not in entity-registry, because
  ``data-platform`` OWNs the storage of ``canonical_entity`` / ``entity_alias``
  Iceberg tables (data-platform/CLAUDE.md OWN list). entity-registry OWNs the
  rules for canonical id *generation*; the reader path is data access.
* ``CandidateDeltaReader`` impl is data-platform-owned because the cycle
  control tables (`cycle_candidate_selection`, `candidate_queue`) are
  data-platform's responsibility (CLAUDE.md OWN list).
* Graph promotion write-back and snapshot computation are intentionally absent
  here; CLAUDE.md assigns those responsibilities to graph-engine.

These read adapters are imported by ``graph_engine.providers.phase1`` via the
``build_graph_phase1_runtime_from_env()`` factory. A fail-closed legacy writer
sentinel remains for old imports, but it performs no storage writes.
"""

from __future__ import annotations

import re
from threading import Lock
from typing import TYPE_CHECKING, Any

from data_platform.cycle.models import CYCLE_CANDIDATE_SELECTION_TABLE
from data_platform.cycle.repository import _create_engine, _text
from data_platform.queue.models import CANDIDATE_QUEUE_TABLE

if TYPE_CHECKING:
    # Type-only import keeps contracts an optional runtime dep — installed in
    # production environments via ``project-ult-contracts`` editable / git
    # but not required for data-platform unit tests that don't touch this
    # module.
    from contracts.schemas import CandidateGraphDelta


_EX3_PAYLOAD_TYPE = "Ex-3"
_QUEUE_ENVELOPE_FIELDS = frozenset({"payload_type", "submitted_by"})

# Identifiers we interpolate into SQL via f-strings must be validated as
# safe identifiers (matching ``data_platform.serving.reader._IDENTIFIER_PATTERN``)
# even though they originate as module-level constants today. Defence in depth:
# if a future change exposes either name to env / config, the validation
# raises before the SQL runs.
_QUALIFIED_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


def _validated_identifier(identifier: str, *, kind: str) -> str:
    if not _QUALIFIED_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"unsafe {kind} identifier: {identifier!r}")
    return identifier


# Validate at import time so a malformed module-level constant fails fast.
_QUALIFIED_CANDIDATE_QUEUE_TABLE = _validated_identifier(
    CANDIDATE_QUEUE_TABLE, kind="candidate_queue table"
)
_QUALIFIED_CYCLE_CANDIDATE_SELECTION_TABLE = _validated_identifier(
    CYCLE_CANDIDATE_SELECTION_TABLE, kind="cycle_candidate_selection table"
)


class PostgresCandidateDeltaReader:
    """Read ``Ex3CandidateGraphDelta`` payloads from the lite-mode PG queue.

    Implementation queries ``cycle_candidate_selection`` joined to
    ``candidate_queue``, filters to ``payload_type='Ex-3'`` accepted rows
    selected for the requested cycle, and deserialises each ``payload``
    JSONB column into a ``CandidateGraphDelta`` Pydantic model.

    The ``selection_ref`` parameter (per the graph-engine Protocol) is
    accepted for traceability but not consulted for filtering: the cycle
    candidate set is fully identified by ``cycle_id``.
    """

    def __init__(self, *, engine: Any | None = None) -> None:
        self._engine = engine
        self._engine_lock = Lock()

    def _resolve_engine(self) -> Any:
        # Thread-safe lazy initialisation: Dagster's asset model is
        # single-threaded today, but a future change to multi-threaded
        # asset materialisation would race on the unguarded ``self._engine
        # is None`` check. ``Lock`` is cheap and removes the data race.
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    self._engine = _create_engine()
        return self._engine

    def read_candidate_graph_deltas(
        self,
        cycle_id: str,
        selection_ref: str,
    ) -> list["CandidateGraphDelta"]:
        # Lazy import so this module imports cleanly in environments that do
        # not yet have project-ult-contracts installed (e.g. data-platform
        # unit-test only venvs); tests touching this method are still
        # expected to pip-install or PYTHONPATH-add contracts.
        from contracts.schemas import CandidateGraphDelta

        engine = self._resolve_engine()
        sql = _text(
            f"""
            SELECT cq.payload AS payload
            FROM {_QUALIFIED_CANDIDATE_QUEUE_TABLE} AS cq
            JOIN {_QUALIFIED_CYCLE_CANDIDATE_SELECTION_TABLE} AS sel
              ON sel.candidate_id = cq.id
            WHERE sel.cycle_id = :cycle_id
              AND cq.payload_type = :payload_type
              AND cq.validation_status = 'accepted'
            ORDER BY cq.ingest_seq ASC
            """
        )

        with engine.connect() as connection:
            rows = connection.execute(
                sql,
                {
                    "cycle_id": cycle_id,
                    "payload_type": _EX3_PAYLOAD_TYPE,
                },
            ).mappings().all()

        deltas: list[CandidateGraphDelta] = []
        for row in rows:
            payload = row["payload"]
            # psycopg returns JSONB as already-parsed dict in modern versions;
            # accept either dict or stringified JSON for resilience.
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            payload = _candidate_graph_delta_payload(payload)
            deltas.append(CandidateGraphDelta.model_validate(payload))
        return deltas

    @classmethod
    def from_env(cls) -> PostgresCandidateDeltaReader:
        """Construct from ``DP_PG_DSN`` (validated lazily on first read)."""

        return cls()


def _candidate_graph_delta_payload(payload: Any) -> Any:
    """Strip the queue envelope fields before contract validation.

    ``submit_candidate()`` stores the producer envelope in ``candidate_queue``:
    ``payload_type`` and ``submitted_by`` are required at the queue boundary,
    but ``contracts.schemas.CandidateGraphDelta`` intentionally forbids those
    Layer-B envelope fields. Other extra keys still reach Pydantic and fail
    closed, so this only bridges the queue envelope to the Ex-3 contract.
    """

    if not isinstance(payload, dict):
        return payload
    return {
        key: value
        for key, value in payload.items()
        if key not in _QUEUE_ENVELOPE_FIELDS
    }


class IcebergEntityAnchorReader:
    """Resolve graph node ids and existing canonical entity ids from Iceberg.

    Reads the ``canonical_entity`` and ``entity_alias`` tables under the
    ``canonical`` namespace via the data-platform DuckDB-backed reader. The
    Iceberg specs declare:

    * ``canonical_entity(canonical_entity_id, created_at)``
    * ``entity_alias(alias, canonical_entity_id, source, created_at)``

    For graph-engine the mapping is:

    * ``alias`` ≡ ``node_id`` (subsystem-asserted graph node identifier)
    * ``canonical_entity_id`` ≡ canonical anchor id

    Existence checks fall back to an empty result on
    ``CanonicalTableNotFound`` so the reader fails open as ``no anchors yet``
    when the Iceberg warehouse has not yet materialised these tables (rather
    than blocking Phase 1 with a CanonicalTableNotFound exception).
    """

    def read_canonical_table(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
    ) -> Any:
        """Indirection point — overridable in tests to inject a fake reader.

        Default implementation calls ``data_platform.serving.reader.read_canonical``.
        """

        from data_platform.serving.reader import read_canonical

        return read_canonical(table, columns=columns, filters=filters)

    def canonical_entity_ids_for_node_ids(
        self,
        node_ids: set[str],
    ) -> dict[str, str]:
        if not node_ids:
            return {}

        from data_platform.serving.reader import CanonicalTableNotFound

        try:
            table = self.read_canonical_table(
                "entity_alias",
                columns=["alias", "canonical_entity_id"],
                filters=[("alias", "in", sorted(node_ids))],
            )
        except CanonicalTableNotFound:
            return {}

        result: dict[str, str] = {}
        aliases = table.column("alias").to_pylist()
        canonical_ids = table.column("canonical_entity_id").to_pylist()
        for alias, canonical_id in zip(aliases, canonical_ids, strict=True):
            if alias is None or canonical_id is None:
                continue
            result[str(alias)] = str(canonical_id)
        return result

    def existing_entity_ids(self, entity_ids: set[str]) -> set[str]:
        if not entity_ids:
            return set()

        from data_platform.serving.reader import CanonicalTableNotFound

        try:
            table = self.read_canonical_table(
                "canonical_entity",
                columns=["canonical_entity_id"],
                filters=[("canonical_entity_id", "in", sorted(entity_ids))],
            )
        except CanonicalTableNotFound:
            return set()

        present: set[str] = set()
        for value in table.column("canonical_entity_id").to_pylist():
            if value is None:
                continue
            present.add(str(value))
        return present

    @classmethod
    def from_env(cls) -> IcebergEntityAnchorReader:
        """Construct from data-platform settings (DP_ICEBERG_WAREHOUSE_PATH /
        DP_DUCKDB_PATH consumed lazily by ``read_canonical``)."""

        return cls()


class _FailClosedCanonicalGraphWriter:
    """Legacy writer sentinel that preserves imports without crossing the
    graph ownership boundary.

    data-platform owns queue and canonical entity reads for Phase 1. It does
    not own graph promotion write-back or graph snapshot computation; those
    writes live in graph-engine per the data-platform BAN list.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    @classmethod
    def from_env(cls) -> _FailClosedCanonicalGraphWriter:
        return cls()

    def write_canonical_records(self, plan: Any) -> None:
        del plan
        raise RuntimeError(
            "data-platform does not implement graph promotion write-back; "
            "graph-engine owns graph promotion and snapshot computation",
        )


StubCanonicalGraphWriter = _FailClosedCanonicalGraphWriter


__all__ = [
    "IcebergEntityAnchorReader",
    "PostgresCandidateDeltaReader",
]
