"""Unit tests for data-platform's graph-engine Phase 1 adapters."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from contracts.schemas import CandidateGraphDelta

from data_platform.cycle.graph_phase1_adapters import (
    IcebergEntityAnchorReader,
    PostgresCandidateDeltaReader,
    StubCanonicalGraphWriter,
    _FailClosedCanonicalGraphWriter,
)


# ---------------------------------------------------------------------------
# PostgresCandidateDeltaReader — mock SQLAlchemy engine
# ---------------------------------------------------------------------------


class _FakeMappingResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappingResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executed: list[tuple[Any, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any]) -> _FakeMappingResult:
        self.executed.append((statement, params))
        return _FakeMappingResult(self._rows)

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.connection = _FakeConnection(rows)

    @contextmanager
    def connect(self):
        yield self.connection


def _ex3_payload(*, delta_id: str = "delta-1") -> dict[str, Any]:
    return {
        "subsystem_id": "test-subsystem",
        "delta_id": delta_id,
        "delta_type": "create_edge",
        "source_node": "node-source",
        "target_node": "node-target",
        "relation_type": "SUPPLY_CHAIN",
        "properties": {"weight": 1.0},
        "evidence": ["fact-1"],
    }


def test_candidate_delta_reader_returns_typed_deltas() -> None:
    rows = [
        {"payload": _ex3_payload(delta_id="delta-1")},
        {"payload": _ex3_payload(delta_id="delta-2")},
    ]
    engine = _FakeEngine(rows)
    reader = PostgresCandidateDeltaReader(engine=engine)

    deltas = reader.read_candidate_graph_deltas(
        cycle_id="CYCLE_20260429",
        selection_ref="cycle_candidate_selection:CYCLE_20260429",
    )

    assert len(deltas) == 2
    assert all(isinstance(delta, CandidateGraphDelta) for delta in deltas)
    assert deltas[0].delta_id == "delta-1"
    assert deltas[1].delta_id == "delta-2"
    # Confirm the bound parameters reach the SQL layer correctly.
    statement, params = engine.connection.executed[0]
    assert params == {"cycle_id": "CYCLE_20260429", "payload_type": "Ex-3"}


def test_candidate_delta_reader_strips_queue_envelope_fields() -> None:
    """The PG queue stores submit_candidate() envelopes.

    ``payload_type`` / ``submitted_by`` are required by Layer B, but the
    contracts-owned Ex-3 payload forbids them. The reader must strip only
    those envelope fields before validating ``CandidateGraphDelta``.
    """

    payload = {
        **_ex3_payload(delta_id="delta-envelope"),
        "payload_type": "Ex-3",
        "submitted_by": "test-subsystem",
    }
    reader = PostgresCandidateDeltaReader(engine=_FakeEngine([{"payload": payload}]))

    deltas = reader.read_candidate_graph_deltas(
        cycle_id="CYCLE_20260429",
        selection_ref="cycle_candidate_selection:CYCLE_20260429",
    )

    assert len(deltas) == 1
    assert deltas[0].delta_id == "delta-envelope"


def test_candidate_delta_reader_sql_includes_validation_status_and_order_by() -> None:
    """Pin the WHERE / ORDER BY clauses so a regression that drops the
    validation_status filter or the ingest_seq ordering is caught here
    rather than at production runtime."""

    engine = _FakeEngine([])
    reader = PostgresCandidateDeltaReader(engine=engine)
    reader.read_candidate_graph_deltas(cycle_id="C", selection_ref="r")

    statement, _ = engine.connection.executed[0]
    sql = str(statement)

    # Filter must reject pending/rejected candidates.
    assert "validation_status = 'accepted'" in sql
    # Determinism: order by the monotonic ingest sequence.
    assert "ORDER BY cq.ingest_seq ASC" in sql
    # Joins the right tables on candidate id.
    assert "candidate_queue" in sql
    assert "cycle_candidate_selection" in sql
    assert "sel.candidate_id = cq.id" in sql
    # Bound parameters (not interpolated) for the user-supplied values.
    assert ":cycle_id" in sql
    assert ":payload_type" in sql


def test_candidate_delta_reader_propagates_pydantic_validation_error() -> None:
    """Malformed payload from PG fails Pydantic validation. Today the error
    propagates (fail-fast). Pin this contract so any future change to
    swallow / log validation errors is a deliberate decision."""

    rows = [{"payload": {"subsystem_id": "x"}}]  # missing required Ex-3 fields
    reader = PostgresCandidateDeltaReader(engine=_FakeEngine(rows))

    with pytest.raises(Exception) as exc_info:
        reader.read_candidate_graph_deltas(cycle_id="C", selection_ref="r")
    # The Pydantic validation error is the underlying cause; the exact class
    # name is from pydantic, so we only assert on message content.
    assert "delta_id" in str(exc_info.value) or "Field required" in str(
        exc_info.value
    )


def test_candidate_delta_reader_handles_string_payload_for_resilience() -> None:
    """psycopg may return JSONB as already-parsed dict OR raw string depending
    on driver version; the reader must accept both."""
    import json

    rows = [{"payload": json.dumps(_ex3_payload(delta_id="delta-stringified"))}]
    reader = PostgresCandidateDeltaReader(engine=_FakeEngine(rows))

    deltas = reader.read_candidate_graph_deltas(
        cycle_id="CYCLE_X", selection_ref="ref"
    )
    assert deltas[0].delta_id == "delta-stringified"


def test_candidate_delta_reader_returns_empty_for_no_rows() -> None:
    reader = PostgresCandidateDeltaReader(engine=_FakeEngine([]))
    deltas = reader.read_candidate_graph_deltas(
        cycle_id="CYCLE_EMPTY", selection_ref="ref"
    )
    assert deltas == []


def test_candidate_delta_reader_from_env_returns_unbound_instance() -> None:
    reader = PostgresCandidateDeltaReader.from_env()
    assert isinstance(reader, PostgresCandidateDeltaReader)
    # _engine is not constructed until first read; this is intentional so
    # the factory does not require live PG at import time.
    assert reader._engine is None


# ---------------------------------------------------------------------------
# IcebergEntityAnchorReader — fake read_canonical
# ---------------------------------------------------------------------------


class _FakeAnchorReader(IcebergEntityAnchorReader):
    def __init__(self, table_by_name: dict[str, pa.Table]) -> None:
        self._tables = table_by_name
        self.calls: list[tuple[str, list[str] | None, list[Any] | None]] = []

    def read_canonical_table(
        self, table: str, columns=None, filters=None
    ) -> pa.Table:
        self.calls.append((table, columns, filters))
        return self._tables[table]


def _alias_table(rows: list[tuple[str, str]]) -> pa.Table:
    return pa.table(
        {
            "alias": [row[0] for row in rows],
            "canonical_entity_id": [row[1] for row in rows],
        }
    )


def _entity_table(canonical_ids: list[str]) -> pa.Table:
    return pa.table({"canonical_entity_id": canonical_ids})


def test_entity_anchor_reader_maps_node_ids_to_canonical_ids() -> None:
    """The fake mimics the real read_canonical contract: it pre-filters
    the table to the rows the filters argument would have returned, since
    test does not exercise DuckDB's filter implementation."""

    reader = _FakeAnchorReader(
        {
            # Only the matched rows; the real DuckDB IN-filter applies the
            # ``alias IN (sorted node_ids)`` clause for us upstream.
            "entity_alias": _alias_table(
                [
                    ("node-1", "ent-1"),
                    ("node-2", "ent-2"),
                ]
            ),
        }
    )

    result = reader.canonical_entity_ids_for_node_ids({"node-1", "node-2"})
    assert result == {"node-1": "ent-1", "node-2": "ent-2"}


def test_entity_anchor_reader_returns_empty_dict_for_empty_node_set() -> None:
    reader = IcebergEntityAnchorReader()
    # Empty node_ids must short-circuit; no read_canonical call is made.
    assert reader.canonical_entity_ids_for_node_ids(set()) == {}


def test_entity_anchor_reader_constructs_in_filter_correctly() -> None:
    """Pin the filter argument so a regression to the wrong operator
    (e.g. ``IN`` instead of ``in``, or a typo) is caught at unit-test time
    rather than producing UnsupportedFilter at production runtime via the
    DuckDB-backed reader.py.
    """

    reader = _FakeAnchorReader({"entity_alias": _alias_table([])})

    reader.canonical_entity_ids_for_node_ids({"node-z", "node-a", "node-m"})

    assert len(reader.calls) == 1
    table, columns, filters = reader.calls[0]
    assert table == "entity_alias"
    assert columns == ["alias", "canonical_entity_id"]
    # Sorted node_ids into a deterministic IN clause; the operator string
    # MUST be lowercase 'in' to match data_platform.serving.reader._compile_filters.
    assert filters == [("alias", "in", ["node-a", "node-m", "node-z"])]


def test_entity_anchor_reader_existing_entity_ids_constructs_in_filter_correctly() -> None:
    reader = _FakeAnchorReader({"canonical_entity": _entity_table([])})

    reader.existing_entity_ids({"ent-z", "ent-a"})

    assert len(reader.calls) == 1
    table, columns, filters = reader.calls[0]
    assert table == "canonical_entity"
    assert columns == ["canonical_entity_id"]
    assert filters == [("canonical_entity_id", "in", ["ent-a", "ent-z"])]


def test_entity_anchor_reader_returns_empty_when_table_missing() -> None:
    """Phase 0 should not block on absent canonical tables — the Iceberg
    warehouse may not have materialised entity_alias yet on first cycle."""

    from data_platform.serving.reader import CanonicalTableNotFound

    class _MissingTableReader(IcebergEntityAnchorReader):
        def read_canonical_table(self, table, columns=None, filters=None):
            raise CanonicalTableNotFound(table)

    reader = _MissingTableReader()
    assert reader.canonical_entity_ids_for_node_ids({"node-x"}) == {}
    assert reader.existing_entity_ids({"ent-x"}) == set()


def test_entity_anchor_reader_filters_existing_entity_ids() -> None:
    reader = _FakeAnchorReader(
        {"canonical_entity": _entity_table(["ent-1", "ent-2"])}
    )

    present = reader.existing_entity_ids({"ent-1", "ent-2", "ent-3"})
    assert present == {"ent-1", "ent-2"}


def test_entity_anchor_reader_returns_empty_set_for_empty_input() -> None:
    reader = IcebergEntityAnchorReader()
    assert reader.existing_entity_ids(set()) == set()


# ---------------------------------------------------------------------------
# Graph promotion write-back boundary
# ---------------------------------------------------------------------------


def test_legacy_canonical_graph_writer_alias_is_fail_closed() -> None:
    assert StubCanonicalGraphWriter is _FailClosedCanonicalGraphWriter

    writer = StubCanonicalGraphWriter()
    with pytest.raises(RuntimeError, match="graph-engine owns graph promotion"):
        writer.write_canonical_records(object())


def test_fail_closed_canonical_graph_writer_from_env_does_not_load_storage() -> None:
    writer = _FailClosedCanonicalGraphWriter.from_env()

    assert isinstance(writer, _FailClosedCanonicalGraphWriter)
