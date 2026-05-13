"""Formal serving payload-schema guard.

Asserts the structural contract that public formal payloads must not surface
raw-zone lineage (`source_run_id`, `raw_loaded_at`) or provider-shaped
identifiers (`ts_code`, `index_code`). The contract is exercised by:

* `formal_table_identifier(...)` — already provider-neutral (namespace check).
* `FormalObject.payload.schema.names` — the schema names returned to a
  consumer must not contain forbidden tokens.

The frontend-api legacy compat route already sanitizes payloads recursively
(see `frontend-api/src/frontend_api/routes/cycle.py` per the M1 review
findings closure F5). This file asserts the canonical/data-platform-side
contract independently of frontend-api so future formal Iceberg tables that
inadvertently carry lineage fields fail the guard.

Per ult_milestone.md M1.4. The 8 legacy `canonical.*` table specs (which DO
carry lineage today) are NOT exercised by these tests because formal serving
reads `formal.<object>` tables, not `canonical.<object>` tables. If a future
formal table mirrors a canonical schema (which would be unusual — formal is
typically populated from L8 commits, not canonical mart writes), this test
flags it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from data_platform.cycle.manifest import CyclePublishManifest, FormalTableSnapshot
from data_platform.serving import formal as formal_module


FORMAL_IDENTIFIER: Final[str] = "formal.recommendation_snapshot"
FORBIDDEN_PUBLIC_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "source",
        "source_name",
        "source_run_id",
        "source_status",
        "source_provider",
        "source_interface_id",
        "raw_loaded_at",
        "submitted_at",
        "ingest_seq",
        "provider",
        "provider_id",
        "provider_name",
        "ts_code",
        "index_code",
    }
)


def test_formal_table_identifier_uses_provider_neutral_namespace() -> None:
    """formal_table_identifier must produce a `formal.*` identifier and reject
    provider-shaped object types. This is already the existing contract; the
    test pins it explicitly so future changes do not weaken it.
    """

    assert formal_module.formal_table_identifier("recommendation_snapshot") == (
        "formal.recommendation_snapshot"
    )
    # Reject obvious provider-shaped names — the formal_registry validates against
    # a strict allow-list, so any unknown name is rejected.
    with pytest.raises(formal_module.FormalObjectTypeInvalid):
        formal_module.formal_table_identifier("tushare_stock_basic")
    with pytest.raises(formal_module.FormalObjectTypeInvalid):
        formal_module.formal_table_identifier("stg_tushare_daily")
    with pytest.raises(formal_module.FormalObjectTypeInvalid):
        formal_module.formal_table_identifier("doc_api")


def test_provider_neutral_payload_passes_runtime_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canonical_v2-shaped payload (security_id PK + business columns + no
    lineage) passes the formal serving runtime guard.
    """

    payload = pa.table(
        {
            "security_id": ["ENT_AAA", "ENT_BBB"],
            "trade_date": [None, None],
            "close": [1.5, 2.5],
            "canonical_loaded_at": [None, None],
        }
    )
    formal_object = _get_latest_with_payload(monkeypatch, payload)

    assert formal_object.payload == payload


@pytest.mark.parametrize("forbidden_field", sorted(FORBIDDEN_PUBLIC_FIELDS))
def test_payload_with_forbidden_field_is_rejected_by_runtime_guard(
    monkeypatch: pytest.MonkeyPatch,
    forbidden_field: str,
) -> None:
    """Formal serving raises fail-closed for every forbidden public field.

    This exercises the real `get_formal_latest(...)` path instead of a local
    test helper, so future formal reads cannot return a leaking `pa.Table`.
    """

    schema_columns = {forbidden_field: ["X"]}
    if forbidden_field != "security_id":
        schema_columns["security_id"] = ["ENT_AAA"]

    payload = pa.table(schema_columns)
    with pytest.raises(
        formal_module.FormalPayloadSourceFieldError,
        match="forbidden public source fields",
    ) as exc_info:
        _get_latest_with_payload(monkeypatch, payload)
    assert exc_info.value.forbidden_fields == (forbidden_field,)
    assert exc_info.value.table_identifier == FORMAL_IDENTIFIER
    assert exc_info.value.snapshot_id == 123


@pytest.mark.parametrize("forbidden_field", ["source_vendor", "provider_ref", "actual_provider"])
def test_payload_with_source_provider_pattern_field_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    forbidden_field: str,
) -> None:
    payload = pa.table({"security_id": ["ENT_AAA"], forbidden_field: ["raw"]})

    with pytest.raises(formal_module.FormalPayloadSourceFieldError) as exc_info:
        _get_latest_with_payload(monkeypatch, payload)

    assert exc_info.value.forbidden_fields == (forbidden_field,)


def test_nested_payload_with_forbidden_field_is_rejected_by_runtime_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested_type = pa.struct(
        [
            pa.field("value", pa.int64()),
            pa.field("source_run_id", pa.string()),
            pa.field("actual_provider", pa.string()),
        ]
    )
    payload = pa.Table.from_arrays(
        [
            pa.array(["ENT_AAA"]),
            pa.array(
                [{"value": 1, "source_run_id": "RUN_RAW", "actual_provider": "tushare"}],
                type=nested_type,
            ),
        ],
        names=["security_id", "payload"],
    )

    with pytest.raises(formal_module.FormalPayloadSourceFieldError) as exc_info:
        _get_latest_with_payload(monkeypatch, payload)

    assert exc_info.value.forbidden_fields == (
        "payload.actual_provider",
        "payload.source_run_id",
    )


def test_legacy_canonical_schema_shape_fails_runtime_guard_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documents the gap: a legacy canonical.dim_security-shaped payload still
    carries `ts_code`, `source_run_id`, and `raw_loaded_at`. If this payload
    were ever forwarded as a formal response, formal serving rejects it.

    This test PASSES today because we EXPECT the rejection; it documents that
    raw canonical shapes are NOT public-formal-safe and must transit through
    canonical_v2 (or an explicit projection) before any formal response.
    """

    legacy_payload = pa.table(
        {
            "ts_code": ["000001.SZ"],
            "name": ["X"],
            "list_date": [None],
            "is_active": [True],
            "source_run_id": ["run-1"],
            "raw_loaded_at": [None],
        }
    )
    with pytest.raises(
        formal_module.FormalPayloadSourceFieldError,
        match="forbidden public source fields",
    ) as exc_info:
        _get_latest_with_payload(monkeypatch, legacy_payload)
    assert exc_info.value.forbidden_fields == (
        "raw_loaded_at",
        "source_run_id",
        "ts_code",
    )


def test_canonical_v2_dim_security_schema_passes_guard() -> None:
    """The canonical_v2.dim_security schema (provider-neutral by construction)
    passes the guard. This pins the M1.3 design — if a future change
    accidentally re-introduces `ts_code` or lineage to canonical_v2, this test
    fails."""

    from data_platform.ddl.iceberg_tables import CANONICAL_V2_DIM_SECURITY_SPEC

    leaks = sorted(
        set(CANONICAL_V2_DIM_SECURITY_SPEC.schema.names) & FORBIDDEN_PUBLIC_FIELDS
    )
    assert not leaks, (
        f"canonical_v2.dim_security spec leaks forbidden public fields {leaks}"
    )


def _get_latest_with_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: pa.Table,
) -> formal_module.FormalObject:
    manifest = CyclePublishManifest(
        published_cycle_id="CYCLE_20260424",
        published_at=datetime(2026, 4, 24, 10, 0, tzinfo=UTC),
        formal_table_snapshots={
            "formal.world_state_snapshot": FormalTableSnapshot(
                table="formal.world_state_snapshot",
                snapshot_id=120,
            ),
            "formal.official_alpha_pool": FormalTableSnapshot(
                table="formal.official_alpha_pool",
                snapshot_id=121,
            ),
            "formal.alpha_result_snapshot": FormalTableSnapshot(
                table="formal.alpha_result_snapshot",
                snapshot_id=122,
            ),
            FORMAL_IDENTIFIER: FormalTableSnapshot(
                table=FORMAL_IDENTIFIER,
                snapshot_id=123,
            )
        },
    )

    def read_iceberg_snapshot(table_identifier: str, snapshot_id: int) -> pa.Table:
        assert table_identifier == FORMAL_IDENTIFIER
        assert snapshot_id == 123
        return payload

    monkeypatch.setattr(
        formal_module,
        "get_latest_publish_manifest",
        lambda: manifest,
    )
    monkeypatch.setattr(
        formal_module.serving_reader,
        "read_iceberg_snapshot",
        read_iceberg_snapshot,
    )
    return formal_module.get_formal_latest("recommendation_snapshot")
