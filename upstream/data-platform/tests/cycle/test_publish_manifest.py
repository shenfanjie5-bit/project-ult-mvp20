from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest

from data_platform.cycle import (
    CYCLE_PUBLISH_MANIFEST_TABLE,
    CyclePublishManifest,
    FormalTableSnapshot,
    InvalidCycleId,
    InvalidCycleTransition,
    InvalidFormalSnapshotManifest,
    ManifestAlreadyPublished,
    PublishManifestNotFound,
    RecommendationSnapshotProvenance,
    create_cycle,
    get_cycle,
    get_latest_publish_manifest,
    get_publish_manifest,
    publish_manifest,
    transition_cycle_status,
)


EXPECTED_MIGRATIONS = ["0001", "0002", "0003", "0004", "0005", "0006"]
EXPECTED_SNAPSHOT_COLUMNS = ["table", "snapshot_id"]
EXPECTED_MANIFEST_COLUMNS = [
    "published_cycle_id",
    "published_at",
    "formal_table_snapshots",
]
FORMAL_WORLD_STATE = "formal.world_state_snapshot"
FORMAL_ALPHA_POOL = "formal.official_alpha_pool"
FORMAL_ALPHA_RESULT = "formal.alpha_result_snapshot"
FORMAL_RECOMMENDATION = "formal.recommendation_snapshot"


def _snapshot_manifest(**overrides: object) -> dict[str, object]:
    snapshots: dict[str, object] = {
        FORMAL_WORLD_STATE: 11,
        FORMAL_ALPHA_POOL: 12,
        FORMAL_ALPHA_RESULT: 13,
        FORMAL_RECOMMENDATION: 14,
    }
    for object_name, snapshot in overrides.items():
        snapshots[f"formal.{object_name}"] = snapshot
    return snapshots


def _recommendation_provenance(
    *,
    cycle_id: str = "CYCLE_20260416",
    snapshot_id: int = 14,
    **overrides: object,
) -> dict[str, object]:
    proof: dict[str, object] = {
        "cycle_id": cycle_id,
        "current_cycle_id": cycle_id,
        "source_layer": "L8",
        "source_kind": "current-cycle",
        "recommendation_snapshot_id": snapshot_id,
        "audit_record_ids": ["audit-recommendation-1"],
        "replay_record_ids": ["replay-recommendation-1"],
    }
    proof.update(overrides)
    return proof


def test_publish_manifest_models_expose_contract() -> None:
    assert CYCLE_PUBLISH_MANIFEST_TABLE == "data_platform.cycle_publish_manifest"

    assert is_dataclass(FormalTableSnapshot)
    assert [field.name for field in fields(FormalTableSnapshot)] == EXPECTED_SNAPSHOT_COLUMNS
    assert FormalTableSnapshot.__slots__ == tuple(EXPECTED_SNAPSHOT_COLUMNS)

    assert is_dataclass(CyclePublishManifest)
    assert [field.name for field in fields(CyclePublishManifest)] == (EXPECTED_MANIFEST_COLUMNS)
    assert CyclePublishManifest.__slots__ == tuple(EXPECTED_MANIFEST_COLUMNS)

    snapshot = FormalTableSnapshot(table=FORMAL_RECOMMENDATION, snapshot_id=123)
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_id = 456

    manifest = CyclePublishManifest(
        published_cycle_id="CYCLE_20260416",
        published_at=datetime.now(UTC),
        formal_table_snapshots=_snapshot_manifest(recommendation_snapshot=snapshot),
    )
    with pytest.raises(FrozenInstanceError):
        manifest.published_cycle_id = "CYCLE_20260417"
    assert manifest.formal_table_snapshots[FORMAL_RECOMMENDATION] == snapshot


@pytest.mark.parametrize(
    "snapshots",
    [
        {},
        {"canonical.recommendation_snapshot": 123},
        {"formal.": 123},
        {" formal.recommendation_snapshot": 123},
        _snapshot_manifest(recommendation_snapshot=0),
        _snapshot_manifest(recommendation_snapshot=-1),
        _snapshot_manifest(recommendation_snapshot=True),
        _snapshot_manifest(recommendation_snapshot=12.3),
        _snapshot_manifest(recommendation_snapshot={}),
        _snapshot_manifest(recommendation_snapshot={"snapshot_id": 0}),
        _snapshot_manifest(recommendation_snapshot={"snapshot_id": "123"}),
        {
            **_snapshot_manifest(),
            FORMAL_RECOMMENDATION: FormalTableSnapshot(
                table=FORMAL_WORLD_STATE,
                snapshot_id=123,
            ),
        },
        {**_snapshot_manifest(), "formal.unknown_object": 123},
        {FORMAL_WORLD_STATE: 1, FORMAL_ALPHA_POOL: 2, FORMAL_ALPHA_RESULT: 3},
    ],
)
def test_publish_manifest_rejects_invalid_snapshot_manifest_before_database(
    snapshots: object,
) -> None:
    with pytest.raises(InvalidFormalSnapshotManifest):
        publish_manifest("CYCLE_20260416", snapshots)  # type: ignore[arg-type]


def test_publish_manifest_rejects_invalid_cycle_id_before_database() -> None:
    with pytest.raises(InvalidCycleId):
        publish_manifest("bad", _snapshot_manifest())


def test_publish_manifest_rejects_recommendation_without_provenance_preflight() -> None:
    with pytest.raises(InvalidFormalSnapshotManifest, match="requires provenance preflight"):
        publish_manifest("CYCLE_20260416", _snapshot_manifest())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"cycle_id": "CYCLE_20260415"}, "published cycle"),
        ({"current_cycle_id": "CYCLE_20260415"}, "current cycle"),
        ({"source_layer": "L7"}, "source_layer"),
        ({"source_kind": "fixture"}, "source_kind"),
        ({"source_kind": "historical"}, "source_kind"),
        ({"source_kind": "smoke"}, "source_kind"),
        ({"source_kind": "synthetic"}, "source_kind"),
        ({"recommendation_snapshot_id": 15}, "snapshot id must match"),
        ({"audit_record_ids": []}, "audit_record_ids must not be empty"),
        ({"replay_record_ids": []}, "replay_record_ids must not be empty"),
    ],
)
def test_publish_manifest_rejects_invalid_recommendation_provenance_before_database(
    override: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(InvalidFormalSnapshotManifest, match=message):
        publish_manifest(
            "CYCLE_20260416",
            _snapshot_manifest(),
            recommendation_provenance=_recommendation_provenance(**override),
        )


def test_recommendation_provenance_model_accepts_current_cycle_l8_binding() -> None:
    proof = RecommendationSnapshotProvenance(
        cycle_id="CYCLE_20260416",
        current_cycle_id="CYCLE_20260416",
        source_layer="L8",
        source_kind="current-cycle",
        recommendation_snapshot_id=14,
        audit_record_ids=("audit-recommendation-1",),
        replay_record_ids=("replay-recommendation-1",),
    )

    assert proof.cycle_id == "CYCLE_20260416"
    assert proof.audit_record_ids == ("audit-recommendation-1",)
    assert proof.replay_record_ids == ("replay-recommendation-1",)


def test_migration_creates_cycle_publish_manifest_schema(
    migrated_postgres_dsn: str,
) -> None:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    _text("SELECT to_regclass('data_platform.cycle_publish_manifest')")
                ).scalar_one()
                == "data_platform.cycle_publish_manifest"
            )

            table_columns = connection.execute(
                _text(
                    """
                    SELECT column_name, data_type, udt_name, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'data_platform'
                      AND table_name = 'cycle_publish_manifest'
                    ORDER BY ordinal_position
                    """
                )
            ).mappings()
            columns = {str(row["column_name"]): row for row in table_columns}
            assert list(columns) == EXPECTED_MANIFEST_COLUMNS
            assert columns["published_cycle_id"]["data_type"] == "text"
            assert columns["published_at"]["data_type"] == "timestamp with time zone"
            assert columns["published_at"]["column_default"] == "now()"
            assert columns["formal_table_snapshots"]["udt_name"] == "jsonb"
            for column_name in EXPECTED_MANIFEST_COLUMNS:
                assert columns[column_name]["is_nullable"] == "NO"

            assert {
                str(row[0])
                for row in connection.execute(
                    _text(
                        """
                        SELECT constraint_name
                        FROM information_schema.table_constraints
                        WHERE table_schema = 'data_platform'
                          AND table_name = 'cycle_publish_manifest'
                        """
                    )
                )
            } >= {
                "cycle_publish_manifest_pkey",
                "cycle_publish_manifest_published_cycle_id_fkey",
                "cycle_publish_manifest_snapshots_is_object",
            }
    finally:
        engine.dispose()


def test_publish_manifest_inserts_row_and_updates_cycle_status(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    _advance_cycle_to_phase3("CYCLE_20260416")

    manifest = publish_manifest(
        "CYCLE_20260416",
        _snapshot_manifest(recommendation_snapshot={"snapshot_id": 123}),
        recommendation_provenance=_recommendation_provenance(snapshot_id=123),
    )

    assert manifest.published_cycle_id == "CYCLE_20260416"
    assert isinstance(manifest.published_at, datetime)
    assert manifest.formal_table_snapshots == {
        FORMAL_WORLD_STATE: FormalTableSnapshot(
            table=FORMAL_WORLD_STATE,
            snapshot_id=11,
        ),
        FORMAL_ALPHA_POOL: FormalTableSnapshot(
            table=FORMAL_ALPHA_POOL,
            snapshot_id=12,
        ),
        FORMAL_ALPHA_RESULT: FormalTableSnapshot(
            table=FORMAL_ALPHA_RESULT,
            snapshot_id=13,
        ),
        FORMAL_RECOMMENDATION: FormalTableSnapshot(
            table=FORMAL_RECOMMENDATION,
            snapshot_id=123,
        ),
    }
    assert get_publish_manifest("CYCLE_20260416") == manifest
    assert get_cycle("CYCLE_20260416").status == "published"
    assert _stored_manifest_payload(cycle_engine, "CYCLE_20260416") == {
        FORMAL_WORLD_STATE: {"snapshot_id": 11},
        FORMAL_ALPHA_POOL: {"snapshot_id": 12},
        FORMAL_ALPHA_RESULT: {"snapshot_id": 13},
        FORMAL_RECOMMENDATION: {"snapshot_id": 123},
    }


def test_repeated_publish_raises_and_preserves_original_manifest(
    cycle_repository_env: str,
) -> None:
    create_cycle(date(2026, 4, 16))
    _advance_cycle_to_phase3("CYCLE_20260416")
    original = publish_manifest(
        "CYCLE_20260416",
        _snapshot_manifest(recommendation_snapshot=123),
        recommendation_provenance=_recommendation_provenance(snapshot_id=123),
    )

    with pytest.raises(ManifestAlreadyPublished):
        publish_manifest(
            "CYCLE_20260416",
            _snapshot_manifest(recommendation_snapshot=999),
            recommendation_provenance=_recommendation_provenance(snapshot_id=999),
        )

    assert get_publish_manifest("CYCLE_20260416") == original
    assert (
        get_publish_manifest("CYCLE_20260416")
        .formal_table_snapshots[FORMAL_RECOMMENDATION]
        .snapshot_id
        == 123
    )


def test_transition_cycle_status_cannot_publish_without_manifest(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    _advance_cycle_to_phase3("CYCLE_20260416")

    with pytest.raises(InvalidCycleTransition):
        transition_cycle_status("CYCLE_20260416", "published")

    assert get_cycle("CYCLE_20260416").status == "phase3"
    with pytest.raises(PublishManifestNotFound):
        get_publish_manifest("CYCLE_20260416")
    assert _manifest_count(cycle_engine) == 0


@pytest.mark.parametrize(
    "status",
    ["pending", "phase0", "phase1", "phase2", "failed"],
)
def test_publish_manifest_rejects_cycles_before_phase3(
    cycle_repository_env: str,
    cycle_engine: Any,
    status: str,
) -> None:
    create_cycle(date(2026, 4, 16))
    _move_cycle_to_status("CYCLE_20260416", status)

    with pytest.raises(InvalidCycleTransition):
        publish_manifest(
            "CYCLE_20260416",
            _snapshot_manifest(),
            recommendation_provenance=_recommendation_provenance(),
        )

    assert get_cycle("CYCLE_20260416").status == status
    assert _manifest_count(cycle_engine) == 0


def test_publish_manifest_missing_cycle_raises_not_found(
    cycle_repository_env: str,
) -> None:
    with pytest.raises(PublishManifestNotFound):
        publish_manifest(
            "CYCLE_20260416",
            _snapshot_manifest(),
            recommendation_provenance=_recommendation_provenance(),
        )


def test_get_publish_manifest_missing_row_raises_not_found(
    cycle_repository_env: str,
) -> None:
    create_cycle(date(2026, 4, 16))

    with pytest.raises(PublishManifestNotFound):
        get_publish_manifest("CYCLE_20260416")


def test_get_latest_publish_manifest_missing_row_raises_not_found(
    cycle_repository_env: str,
) -> None:
    with pytest.raises(PublishManifestNotFound):
        get_latest_publish_manifest()


def test_get_publish_manifest_rejects_stored_invalid_json_contract(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    _advance_cycle_to_phase3("CYCLE_20260416")
    with cycle_engine.begin() as connection:
        connection.execute(
            _text(
                """
                INSERT INTO data_platform.cycle_publish_manifest (
                    published_cycle_id,
                    formal_table_snapshots
                )
                VALUES (
                    'CYCLE_20260416',
                    '{"formal.world_state_snapshot": {"snapshot_id": 1},
                      "formal.official_alpha_pool": {"snapshot_id": 2},
                      "formal.alpha_result_snapshot": {"snapshot_id": 3},
                      "formal.recommendation_snapshot": {"snapshot_id": "bad"}}'::jsonb
                )
                """
            )
        )

    with pytest.raises(InvalidFormalSnapshotManifest):
        get_publish_manifest("CYCLE_20260416")


def test_publish_manifest_insert_failure_rolls_back_status_update(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    _advance_cycle_to_phase3("CYCLE_20260416")
    with cycle_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION data_platform.raise_publish_manifest_insert_failure()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'forced publish manifest insert failure';
            END;
            $$;

            CREATE TRIGGER force_publish_manifest_insert_failure
            BEFORE INSERT ON data_platform.cycle_publish_manifest
            FOR EACH ROW
            EXECUTE FUNCTION data_platform.raise_publish_manifest_insert_failure();
            """
        )

    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    ).SQLAlchemyError
    with pytest.raises(sqlalchemy_error):
        publish_manifest(
            "CYCLE_20260416",
            _snapshot_manifest(),
            recommendation_provenance=_recommendation_provenance(),
        )

    assert get_cycle("CYCLE_20260416").status == "phase3"
    assert _manifest_count(cycle_engine) == 0


def test_get_latest_publish_manifest_orders_by_postgres_manifest_metadata(
    cycle_repository_env: str,
    cycle_engine: Any,
) -> None:
    create_cycle(date(2026, 4, 16))
    create_cycle(date(2026, 4, 17))
    _advance_cycle_to_phase3("CYCLE_20260416")
    _advance_cycle_to_phase3("CYCLE_20260417")
    publish_manifest(
        "CYCLE_20260416",
        _snapshot_manifest(recommendation_snapshot=123),
        recommendation_provenance=_recommendation_provenance(snapshot_id=123),
    )
    publish_manifest(
        "CYCLE_20260417",
        _snapshot_manifest(recommendation_snapshot=456),
        recommendation_provenance=_recommendation_provenance(
            cycle_id="CYCLE_20260417",
            snapshot_id=456,
        ),
    )

    with cycle_engine.begin() as connection:
        connection.execute(
            _text(
                """
                UPDATE data_platform.cycle_publish_manifest
                SET published_at = TIMESTAMPTZ '2026-04-16 00:00:00+00'
                WHERE published_cycle_id IN ('CYCLE_20260416', 'CYCLE_20260417')
                """
            )
        )

    latest = get_latest_publish_manifest()

    assert latest.published_cycle_id == "CYCLE_20260417"
    assert latest.formal_table_snapshots[FORMAL_RECOMMENDATION].snapshot_id == 456


@pytest.fixture()
def postgres_dsn() -> Generator[str]:
    admin_dsn = os.environ.get("DATABASE_URL") or os.environ.get("DP_PG_DSN")
    if not admin_dsn:
        pytest.skip("PostgreSQL publish manifest tests require DATABASE_URL or DP_PG_DSN")

    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL publish manifest tests require the migration runner",
    )
    make_url = pytest.importorskip(
        "sqlalchemy.engine",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    ).make_url
    sqlalchemy_error = pytest.importorskip(
        "sqlalchemy.exc",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    ).SQLAlchemyError

    admin_engine = _create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    database_name = f"dp_publish_manifest_test_{uuid4().hex}"
    try:
        with admin_engine.connect() as connection:
            connection.execute(sqlalchemy.text(f'CREATE DATABASE "{database_name}"'))
    except sqlalchemy_error as exc:
        admin_engine.dispose()
        pytest.skip(
            f"PostgreSQL publish manifest tests require permission to create test databases: {exc}"
        )

    test_dsn = (
        make_url(runner_module._sqlalchemy_postgres_uri(admin_dsn))
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )
    try:
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


@pytest.fixture()
def migrated_postgres_dsn(postgres_dsn: str) -> str:
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL publish manifest tests require the migration runner",
    )
    applied_versions = runner_module.MigrationRunner().apply_pending(postgres_dsn)
    assert applied_versions == EXPECTED_MIGRATIONS
    assert runner_module.MigrationRunner().apply_pending(postgres_dsn) == []
    return postgres_dsn


@pytest.fixture()
def cycle_repository_env(
    migrated_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str]:
    monkeypatch.setenv("DP_PG_DSN", migrated_postgres_dsn)
    yield migrated_postgres_dsn


@pytest.fixture()
def cycle_engine(migrated_postgres_dsn: str) -> Generator[Any]:
    engine = _create_engine(migrated_postgres_dsn)
    try:
        yield engine
    finally:
        engine.dispose()


def _stored_manifest_payload(engine: Any, cycle_id: str) -> Mapping[str, object]:
    with engine.connect() as connection:
        return connection.execute(
            _text(
                """
                SELECT formal_table_snapshots
                FROM data_platform.cycle_publish_manifest
                WHERE published_cycle_id = :cycle_id
                """
            ),
            {"cycle_id": cycle_id},
        ).scalar_one()


def _manifest_count(engine: Any) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                _text("SELECT count(*) FROM data_platform.cycle_publish_manifest")
            ).scalar_one()
        )


def _advance_cycle_to_phase3(cycle_id: str) -> None:
    _move_cycle_to_status(cycle_id, "phase3")


def _move_cycle_to_status(cycle_id: str, status: str) -> None:
    if status == "pending":
        return
    if status == "failed":
        transition_cycle_status(cycle_id, "failed")
        return
    for next_status in ("phase0", "phase1", "phase2", "phase3"):
        transition_cycle_status(cycle_id, next_status)
        if next_status == status:
            return
    msg = f"unsupported test cycle status: {status!r}"
    raise AssertionError(msg)


def _create_engine(dsn: str, **kwargs: object) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    )
    runner_module = pytest.importorskip(
        "data_platform.ddl.runner",
        reason="PostgreSQL publish manifest tests require the migration runner",
    )
    return sqlalchemy.create_engine(runner_module._sqlalchemy_postgres_uri(dsn), **kwargs)


def _text(sql: str) -> Any:
    sqlalchemy = pytest.importorskip(
        "sqlalchemy",
        reason="PostgreSQL publish manifest tests require SQLAlchemy",
    )
    return sqlalchemy.text(sql)
