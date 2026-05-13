from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from datetime import date
from typing import Any, NoReturn
from uuid import uuid4

import pytest
from contracts.schemas import CandidateGraphDelta

from data_platform.cycle import create_cycle, freeze_cycle_candidates
from data_platform.cycle.graph_phase1_adapters import PostgresCandidateDeltaReader
from data_platform.queue import ForbiddenIngestMetadataError, submit_candidate
from data_platform.queue.worker import validate_pending_candidates

_SUBMITTED_BY = "subsystem-holdings"
_FORBIDDEN_RECEIPT_FIELDS = frozenset(
    {
        "submitted_at",
        "ingest_seq",
        "layer_b_receipt_id",
        "ex_type",
        "produced_at",
    }
)


def test_holdings_ex3_queue_submit_freeze_phase1_reader_round_trip(
    holdings_bridge_env: str,
    holdings_bridge_engine: Any,
) -> None:
    assert holdings_bridge_env
    cycle_id = "CYCLE_20260507"
    create_cycle(date(2026, 5, 7))

    co_holding = _holdings_ex3_envelope(
        delta_id="holdings-co-proof-1",
        source_node="ENT_SECURITY_ALPHA",
        target_node="ENT_SECURITY_BETA",
        relation_type="CO_HOLDING",
        properties={
            "co_holding_fund_count": 2,
            "jaccard_score": 0.42,
            "source_mart": "mart_deriv_fund_co_holding",
        },
        evidence=["mart_deriv_fund_co_holding:proof-row-1"],
    )
    northbound = _holdings_ex3_envelope(
        delta_id="holdings-nb-proof-1",
        source_node="ENT_NORTHBOUND_CHANNEL",
        target_node="ENT_SECURITY_ALPHA",
        relation_type="NORTHBOUND_HOLD",
        properties={
            "z_score_metric": "holding_amount",
            "lookback_observations": 90,
            "metric_z_score": 1.8,
            "source_mart": "mart_deriv_northbound_holding_z_score",
        },
        evidence=["mart_deriv_northbound_holding_z_score:proof-row-1"],
    )

    receipts = [submit_candidate(co_holding), submit_candidate(northbound)]

    assert [receipt.payload_type for receipt in receipts] == ["Ex-3", "Ex-3"]
    assert [receipt.submitted_by for receipt in receipts] == [_SUBMITTED_BY, _SUBMITTED_BY]
    assert [receipt.validation_status for receipt in receipts] == ["pending", "pending"]
    assert all(receipt.id > 0 for receipt in receipts)
    assert all(receipt.ingest_seq > 0 for receipt in receipts)
    assert all(receipt.submitted_at is not None for receipt in receipts)
    for receipt in receipts:
        assert _FORBIDDEN_RECEIPT_FIELDS.isdisjoint(receipt.payload)

    assert _status_counts(holdings_bridge_engine) == {"pending": 2}

    summary = validate_pending_candidates(limit=10)
    assert summary.scanned == 2
    assert summary.accepted == 2
    assert summary.rejected == 0
    assert _status_counts(holdings_bridge_engine) == {"accepted": 2}

    metadata = freeze_cycle_candidates(cycle_id)
    frozen_ids = _selection_ids(holdings_bridge_engine, cycle_id)

    assert frozen_ids == [receipt.id for receipt in receipts]
    assert metadata.status == "phase0"
    assert metadata.candidate_count == 2
    assert metadata.cutoff_ingest_seq == max(receipt.ingest_seq for receipt in receipts)
    assert metadata.selection_frozen_at is not None
    assert _table_counts(holdings_bridge_engine) == {
        "candidate_queue": 2,
        "cycle_candidate_selection": 2,
    }

    reader = PostgresCandidateDeltaReader(engine=holdings_bridge_engine)
    deltas = reader.read_candidate_graph_deltas(
        cycle_id=cycle_id,
        selection_ref=f"cycle_candidate_selection:{cycle_id}",
    )

    assert all(isinstance(delta, CandidateGraphDelta) for delta in deltas)
    assert [delta.delta_id for delta in deltas] == [
        "holdings-co-proof-1",
        "holdings-nb-proof-1",
    ]
    assert [delta.delta_type for delta in deltas] == ["edge_upsert", "edge_upsert"]
    assert {delta.relation_type for delta in deltas} == {
        "CO_HOLDING",
        "NORTHBOUND_HOLD",
    }
    assert {delta.subsystem_id for delta in deltas} == {_SUBMITTED_BY}
    for delta in deltas:
        wire_payload = delta.model_dump(mode="json")
        assert "payload_type" not in wire_payload
        assert "submitted_by" not in wire_payload
        assert _FORBIDDEN_RECEIPT_FIELDS.isdisjoint(wire_payload)


def test_holdings_ex3_submit_rejects_private_receipt_field_before_insert(
    holdings_bridge_env: str,
    holdings_bridge_engine: Any,
) -> None:
    assert holdings_bridge_env
    before_count = _candidate_count(holdings_bridge_engine)
    payload = _holdings_ex3_envelope(
        delta_id="holdings-private-field-proof",
        source_node="ENT_NORTHBOUND_CHANNEL",
        target_node="ENT_SECURITY_ALPHA",
        relation_type="NORTHBOUND_HOLD",
        properties={"source_mart": "mart_deriv_northbound_holding_z_score"},
        evidence=["mart_deriv_northbound_holding_z_score:proof-row-private"],
    )
    payload["layer_b_receipt_id"] = "must-not-cross-phase1"

    with pytest.raises(ForbiddenIngestMetadataError, match="layer_b_receipt_id"):
        submit_candidate(payload)

    assert _candidate_count(holdings_bridge_engine) == before_count


def test_holdings_ex3_submit_rejects_layer_b_ingest_metadata_before_insert(
    holdings_bridge_env: str,
    holdings_bridge_engine: Any,
) -> None:
    assert holdings_bridge_env
    before_count = _candidate_count(holdings_bridge_engine)
    payload = _holdings_ex3_envelope(
        delta_id="holdings-forbidden-ingest-metadata",
        source_node="ENT_SECURITY_ALPHA",
        target_node="ENT_SECURITY_BETA",
        relation_type="CO_HOLDING",
        properties={"source_mart": "mart_deriv_fund_co_holding"},
        evidence=["mart_deriv_fund_co_holding:proof-row-forbidden"],
    )
    payload["ingest_seq"] = 999

    with pytest.raises(ForbiddenIngestMetadataError, match="ingest_seq"):
        submit_candidate(payload)

    assert _candidate_count(holdings_bridge_engine) == before_count


@pytest.fixture()
def holdings_bridge_env(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    monkeypatch.setenv("DP_PG_DSN", migrated_postgres_dsn)
    yield migrated_postgres_dsn


@pytest.fixture()
def holdings_bridge_engine(migrated_postgres_dsn: str) -> Generator[Any]:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def migrated_postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        _skip_or_fail_pg(
            "PostgreSQL holdings Ex-3 bridge tests require DATABASE_URL or DP_PG_DSN",
        )

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL holdings Ex-3 bridge tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL holdings Ex-3 bridge tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL holdings Ex-3 bridge tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL holdings Ex-3 bridge tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_holdings_ex3_bridge_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        _skip_or_fail_pg(
            "PostgreSQL holdings Ex-3 bridge tests require permission to create "
            f"test databases: {exc}"
        )

    test_dsn = (
        make_url(runner_module._sqlalchemy_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
        runner_module.MigrationRunner().apply_pending(test_dsn)
        yield test_dsn
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                sqlalchemy.text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            connection.execute(
                sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"')
            )
        admin_engine.dispose()


def _holdings_ex3_envelope(
    *,
    delta_id: str,
    source_node: str,
    target_node: str,
    relation_type: str,
    properties: Mapping[str, object],
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "payload_type": "Ex-3",
        "submitted_by": _SUBMITTED_BY,
        "subsystem_id": _SUBMITTED_BY,
        "delta_id": delta_id,
        "delta_type": "edge_upsert",
        "source_node": source_node,
        "target_node": target_node,
        "relation_type": relation_type,
        "properties": {
            **dict(properties),
            "lineage": {
                "source_interface_id_summary": "redacted-bounded-proof",
                "source_window": "bounded-proof-window",
            },
        },
        "evidence": evidence,
        "producer_context": {
            "proof_scope": "holdings_ex3_queue_freeze_bridge",
            "source": "fixture_only_no_live_provider",
        },
    }


def _selection_ids(engine: Any, cycle_id: str) -> list[int]:
    with engine.connect() as connection:
        rows = connection.execute(
            _text(
                """
                SELECT candidate_id
                FROM data_platform.cycle_candidate_selection
                WHERE cycle_id = :cycle_id
                ORDER BY candidate_id ASC
                """
            ),
            {"cycle_id": cycle_id},
        ).scalars()
        return [int(row) for row in rows]


def _status_counts(engine: Any) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            _text(
                """
                SELECT validation_status, count(*) AS row_count
                FROM data_platform.candidate_queue
                GROUP BY validation_status
                ORDER BY validation_status
                """
            )
        )
    return {str(row[0]): int(row[1]) for row in rows}


def _table_counts(engine: Any) -> dict[str, int]:
    with engine.connect() as connection:
        candidate_count = connection.execute(
            _text("SELECT count(*) FROM data_platform.candidate_queue")
        ).scalar_one()
        selection_count = connection.execute(
            _text("SELECT count(*) FROM data_platform.cycle_candidate_selection")
        ).scalar_one()
    return {
        "candidate_queue": int(candidate_count),
        "cycle_candidate_selection": int(selection_count),
    }


def _candidate_count(engine: Any) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                _text("SELECT count(*) FROM data_platform.candidate_queue")
            ).scalar_one()
        )


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL holdings Ex-3 bridge tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL holdings Ex-3 bridge tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL holdings Ex-3 bridge tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)


def _skip_or_fail_pg(message: str) -> NoReturn:
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
        pytest.fail(message)
    pytest.skip(message)
