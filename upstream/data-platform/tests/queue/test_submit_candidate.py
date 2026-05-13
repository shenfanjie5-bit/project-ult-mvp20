from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from data_platform.queue import (
    CandidateEnvelope,
    CandidateQueueItem,
    CandidateSubmitReceipt,
    CandidateValidationError,
    ForbiddenIngestMetadataError,
    submit_candidate,
    submit_candidate_idempotent,
    validate_candidate_envelope,
)
from data_platform.queue import api as queue_api
from data_platform.queue.repository import (
    CandidateRepository,
    _sqlalchemy_postgres_uri,
)


def test_submit_candidate_validates_and_writes_with_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_envelopes: list[CandidateEnvelope] = []
    closed = False

    class FakeRepository:
        def insert_candidate(self, envelope: CandidateEnvelope) -> CandidateQueueItem:
            seen_envelopes.append(envelope)
            return CandidateQueueItem(
                id=10,
                payload_type=envelope.payload_type,
                payload=envelope.payload,
                submitted_by=envelope.submitted_by,
                submitted_at=datetime.now(UTC),
                ingest_seq=99,
                validation_status="pending",
                rejection_reason=None,
            )

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(queue_api, "CandidateRepository", FakeRepository)

    payload = {
        "payload_type": "Ex-1",
        "submitted_by": "test-subsystem",
        "candidate": {"id": "alpha"},
    }
    item = submit_candidate(payload)

    assert item.id == 10
    assert item.ingest_seq == 99
    assert item.submitted_at is not None
    assert item.validation_status == "pending"
    assert item.rejection_reason is None
    assert dict(item.payload) == payload
    assert seen_envelopes == [
        CandidateEnvelope(
            payload_type="Ex-1",
            submitted_by="test-subsystem",
            payload=payload,
        )
    ]
    assert closed is True


def test_submit_candidate_accepts_sdk_bridge_shaped_ex3_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_envelopes: list[CandidateEnvelope] = []

    class FakeRepository:
        def insert_candidate(self, envelope: CandidateEnvelope) -> CandidateQueueItem:
            seen_envelopes.append(envelope)
            return CandidateQueueItem(
                id=11,
                payload_type=envelope.payload_type,
                payload=envelope.payload,
                submitted_by=envelope.submitted_by,
                submitted_at=datetime.now(UTC),
                ingest_seq=100,
                validation_status="pending",
                rejection_reason=None,
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(queue_api, "CandidateRepository", FakeRepository)

    payload = {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-bridge",
        "subsystem_id": "subsystem-bridge",
        "delta_id": "sdk-bridge-delta-1",
        "delta_type": "add",
        "source_node": "node-source",
        "target_node": "node-target",
        "relation_type": "SUPPLY_CHAIN",
        "properties": {"weight": 0.7},
        "evidence_refs": ["announcement:1"],
    }

    item = submit_candidate(payload)

    assert item.id == 11
    assert item.payload_type == "Ex-3"
    assert item.submitted_by == "subsystem-bridge"
    assert dict(item.payload) == payload
    assert seen_envelopes == [
        CandidateEnvelope(
            payload_type="Ex-3",
            submitted_by="subsystem-bridge",
            payload=payload,
        )
    ]


def test_submit_candidate_idempotent_returns_sanitized_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_envelopes: list[CandidateEnvelope] = []

    class FakeRepository:
        def insert_candidate_idempotent(
            self,
            envelope: CandidateEnvelope,
        ) -> CandidateSubmitReceipt:
            seen_envelopes.append(envelope)
            return CandidateSubmitReceipt(
                candidate_id=12,
                payload_type=envelope.payload_type,
                submitted_by=envelope.submitted_by,
                submitted_at=datetime.now(UTC),
                ingest_seq=101,
                validation_status="pending",
                rejection_reason=None,
                replayed=False,
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(queue_api, "CandidateRepository", FakeRepository)

    payload = {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-holdings",
        "delta_id": "delta-safe-receipt",
        "provider_payload": "must not be accepted",
    }

    with pytest.raises(ForbiddenIngestMetadataError, match="provider_payload"):
        submit_candidate_idempotent(payload)

    safe_payload = {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-holdings",
        "delta_id": "delta-safe-receipt",
        "candidate": {"id": "alpha"},
    }
    receipt = submit_candidate_idempotent(safe_payload)

    public_receipt = receipt.as_public_dict()
    assert receipt.candidate_id == 12
    assert receipt.replayed is False
    assert "payload" not in public_receipt
    assert "provider_payload" not in public_receipt
    assert "raw_payload_path" not in public_receipt
    assert "dsn" not in public_receipt
    assert seen_envelopes == [
        CandidateEnvelope(
            payload_type="Ex-3",
            submitted_by="subsystem-holdings",
            payload=safe_payload,
        )
    ]


def test_validate_candidate_envelope_returns_immutable_payload_copy() -> None:
    payload = {
        "payload_type": "Ex-2",
        "submitted_by": "test-subsystem",
        "candidate": "alpha",
    }

    envelope = validate_candidate_envelope(payload)
    payload["candidate"] = "mutated"

    assert envelope.payload_type == "Ex-2"
    assert envelope.submitted_by == "test-subsystem"
    assert dict(envelope.payload) == {
        "payload_type": "Ex-2",
        "submitted_by": "test-subsystem",
        "candidate": "alpha",
    }
    with pytest.raises(TypeError):
        envelope.payload["ingest_seq"] = 1  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        envelope.submitted_by = "other-subsystem"


def test_submit_candidate_rejects_invalid_payload_type() -> None:
    with pytest.raises(CandidateValidationError, match="payload_type must be one of"):
        submit_candidate(
            {
                "payload_type": "Ex-4",
                "submitted_by": "test-subsystem",
                "candidate": "alpha",
            }
        )


@pytest.mark.parametrize("payload_type", [None, ["Ex-1"]])
def test_submit_candidate_rejects_non_string_payload_type(payload_type: object) -> None:
    with pytest.raises(CandidateValidationError, match="payload_type must be one of"):
        submit_candidate(
            {
                "payload_type": payload_type,
                "submitted_by": "test-subsystem",
                "candidate": "alpha",
            }
        )


def test_submit_candidate_rejects_missing_submitted_by() -> None:
    with pytest.raises(CandidateValidationError, match="submitted_by is required"):
        submit_candidate({"payload_type": "Ex-1", "candidate": "alpha"})


def test_submit_candidate_rejects_ingest_metadata_before_other_fields() -> None:
    with pytest.raises(ForbiddenIngestMetadataError, match="must not include"):
        submit_candidate({"payload_type": "Ex-1", "ingest_seq": 123})


@pytest.mark.parametrize("forbidden_key", ["submitted_at", "ingest_seq"])
def test_submit_candidate_rejects_top_level_ingest_metadata(
    monkeypatch: pytest.MonkeyPatch,
    forbidden_key: str,
) -> None:
    class UnexpectedRepository:
        def __init__(self) -> None:
            raise AssertionError("repository must not be created for invalid payloads")

    monkeypatch.setattr(queue_api, "CandidateRepository", UnexpectedRepository)

    with pytest.raises(ForbiddenIngestMetadataError, match="must not include"):
        submit_candidate(
            {
                "payload_type": "Ex-1",
                "submitted_by": "test-subsystem",
                forbidden_key: "not producer-owned",
            }
        )


@pytest.mark.parametrize(
    "forbidden_key",
    ["layer_b_receipt_id", "ex_type", "produced_at", "raw_payload_path"],
)
def test_submit_candidate_rejects_private_receipt_fields_before_insert(
    monkeypatch: pytest.MonkeyPatch,
    forbidden_key: str,
) -> None:
    class UnexpectedRepository:
        def __init__(self) -> None:
            raise AssertionError("repository must not be created for invalid payloads")

    monkeypatch.setattr(queue_api, "CandidateRepository", UnexpectedRepository)

    with pytest.raises(ForbiddenIngestMetadataError, match=forbidden_key):
        submit_candidate(
            {
                "payload_type": "Ex-3",
                "submitted_by": "subsystem-holdings",
                "delta_id": "delta-private-receipt",
                forbidden_key: "private-receipt-value",
            }
        )


def test_submit_candidate_rejects_non_json_payload() -> None:
    with pytest.raises(CandidateValidationError, match="JSON serializable"):
        submit_candidate(
            {
                "payload_type": "Ex-1",
                "submitted_by": "test-subsystem",
                "as_of": datetime.now(UTC),
            }
        )


def test_submit_candidate_rejects_nested_non_string_payload_keys() -> None:
    with pytest.raises(CandidateValidationError, match="JSON object keys must be strings"):
        submit_candidate(
            {
                "payload_type": "Ex-1",
                "submitted_by": "test-subsystem",
                "candidate": {"id": "alpha", "nested": {1: "not-json-object-key"}},
            }
        )


def test_submit_candidate_rejects_nested_non_string_payload_keys_in_lists() -> None:
    with pytest.raises(CandidateValidationError, match="JSON object keys must be strings"):
        submit_candidate(
            {
                "payload_type": "Ex-1",
                "submitted_by": "test-subsystem",
                "candidate": [{"id": "alpha"}, {1: "not-json-object-key"}],
            }
        )


def test_repository_rewrites_plain_postgres_dsn_to_psycopg() -> None:
    assert _sqlalchemy_postgres_uri("postgresql://dp:dp@localhost/db") == (
        "postgresql+psycopg://dp:dp@localhost/db"
    )
    assert _sqlalchemy_postgres_uri("postgres://dp:dp@localhost/db") == (
        "postgresql+psycopg://dp:dp@localhost/db"
    )
    assert _sqlalchemy_postgres_uri("postgresql+psycopg://dp:dp@localhost/db") == (
        "postgresql+psycopg://dp:dp@localhost/db"
    )


def test_submit_candidate_inserts_and_returns_pg_generated_fields(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_settings_env(monkeypatch, migrated_postgres_dsn)

    payload = {
        "payload_type": "Ex-1",
        "submitted_by": "test-subsystem",
        "candidate": {"id": "alpha"},
    }

    item = submit_candidate(payload)

    assert item.id is not None
    assert item.submitted_at is not None
    assert item.ingest_seq is not None
    assert item.payload_type == "Ex-1"
    assert item.submitted_by == "test-subsystem"
    assert dict(item.payload) == payload
    assert item.validation_status == "pending"
    assert item.rejection_reason is None


def test_forbidden_ingest_metadata_does_not_insert_row(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_settings_env(monkeypatch, migrated_postgres_dsn)
    engine = _create_engine(migrated_postgres_dsn)
    try:
        before_count = _candidate_count(engine)
        with pytest.raises(ForbiddenIngestMetadataError):
            submit_candidate(
                {
                    "payload_type": "Ex-1",
                    "submitted_by": "test-subsystem",
                    "ingest_seq": 123,
                }
            )
        assert _candidate_count(engine) == before_count
    finally:
        engine.dispose()


def test_repository_maps_pg_returning_fields(migrated_postgres_dsn: str) -> None:
    envelope = validate_candidate_envelope(
        {
            "payload_type": "Ex-3",
            "submitted_by": "test-subsystem",
            "candidate": "beta",
        }
    )
    repository = CandidateRepository(dsn=migrated_postgres_dsn)
    try:
        item = repository.insert_candidate(envelope)
    finally:
        repository.close()

    assert item.id > 0
    assert item.payload_type == "Ex-3"
    assert item.submitted_by == "test-subsystem"
    assert item.submitted_at is not None
    assert item.ingest_seq > 0
    assert item.validation_status == "pending"
    assert item.rejection_reason is None


def test_idempotent_ex3_delta_id_replays_existing_row(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_settings_env(monkeypatch, migrated_postgres_dsn)

    payload = {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-holdings",
        "subsystem_id": "subsystem-holdings",
        "delta_id": "holdings-delta-replay",
        "delta_type": "edge_upsert",
        "source_node": "source",
        "target_node": "target",
        "relation_type": "CO_HOLDING",
        "properties": {"source_mart": "mart_deriv_fund_co_holding"},
        "evidence": ["proof-row"],
    }
    engine = _create_engine(migrated_postgres_dsn)
    try:
        before_count = _candidate_count(engine)
        first = submit_candidate_idempotent(payload)
        second = submit_candidate_idempotent({**payload, "properties": {"ignored": True}})

        assert _candidate_count(engine) == before_count + 1
        assert first.replayed is False
        assert second.replayed is True
        assert second.candidate_id == first.candidate_id
        assert second.ingest_seq == first.ingest_seq
        assert "payload" not in first.as_public_dict()
    finally:
        engine.dispose()


@pytest.mark.parametrize("delta_id", ["", 42])
def test_idempotent_ex3_invalid_delta_id_uses_non_idempotent_insert(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    delta_id: object,
) -> None:
    _set_required_settings_env(monkeypatch, migrated_postgres_dsn)

    payload = {
        "payload_type": "Ex-3",
        "submitted_by": "subsystem-holdings",
        "subsystem_id": "subsystem-holdings",
        "delta_id": delta_id,
        "delta_type": "edge_upsert",
        "source_node": "source",
        "target_node": "target",
        "relation_type": "CO_HOLDING",
        "properties": {"source_mart": "mart_deriv_fund_co_holding"},
        "evidence": ["proof-row"],
    }
    engine = _create_engine(migrated_postgres_dsn)
    try:
        before_count = _candidate_count(engine)
        first = submit_candidate_idempotent(payload)
        second = submit_candidate_idempotent({**payload, "properties": {"repeat": True}})

        assert _candidate_count(engine) == before_count + 2
        assert first.replayed is False
        assert second.replayed is False
        assert second.candidate_id != first.candidate_id
        assert second.ingest_seq > first.ingest_seq
        assert "payload" not in first.as_public_dict()
        assert "payload" not in second.as_public_dict()
    finally:
        engine.dispose()


@pytest.fixture()
def migrated_postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL submit_candidate tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL submit_candidate tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL submit_candidate tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL submit_candidate tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL submit_candidate tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = sqlalchemy.create_engine(
        runner_module._sqlalchemy_postgres_uri(admin_dsn),
        isolation_level="AUTOCOMMIT",
    )
    database_name = f"dp_submit_candidate_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            "PostgreSQL submit_candidate tests require permission to create "
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
            connection.execute(sqlalchemy.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def _set_required_settings_env(monkeypatch: pytest.MonkeyPatch, dsn: str) -> None:
    monkeypatch.setenv("DP_PG_DSN", dsn)
    monkeypatch.setenv("DP_RAW_ZONE_PATH", "data_platform/raw")
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", "data_platform/iceberg/warehouse")
    monkeypatch.setenv("DP_DUCKDB_PATH", "data_platform/duckdb/data_platform.duckdb")


def _create_engine(dsn: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL submit_candidate tests require SQLAlchemy",
    )
    return sqlalchemy.create_engine(_sqlalchemy_postgres_uri(dsn))


def _candidate_count(engine: Any) -> int:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL submit_candidate tests require SQLAlchemy",
    )
    with engine.connect() as connection:
        return int(
            connection.execute(
                sqlalchemy.text("SELECT count(*) FROM data_platform.candidate_queue")
            ).scalar_one()
        )
