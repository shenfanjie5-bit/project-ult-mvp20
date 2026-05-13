from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from audit_eval.audit.query import replay_cycle_object
from audit_eval.audit.real_cycle import (
    DataPlatformBindingError,
    DataPlatformFormalSnapshotGateway,
    DataPlatformManifestGateway,
    build_data_platform_replay_query_context,
    data_platform_snapshot_ref,
    parse_data_platform_snapshot_ref,
)


@dataclass(frozen=True)
class FakeFormalTableSnapshot:
    table: str
    snapshot_id: int


@dataclass(frozen=True)
class FakeManifest:
    published_cycle_id: str
    published_at: datetime
    formal_table_snapshots: dict[str, FakeFormalTableSnapshot]


@dataclass(frozen=True)
class FakeFormalObject:
    cycle_id: str
    object_type: str
    snapshot_id: int
    payload: Any


class FakeArrowTable:
    num_rows = 1

    def to_pylist(self) -> list[dict[str, Any]]:
        return [
            {
                "cycle_id": "CYCLE_20260415",
                "content_kind": "synthetic_minimal_formal_object",
            }
        ]


def _manifest() -> FakeManifest:
    return FakeManifest(
        published_cycle_id="CYCLE_20260415",
        published_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
        formal_table_snapshots={
            "formal.world_state_snapshot": FakeFormalTableSnapshot(
                table="formal.world_state_snapshot",
                snapshot_id=101,
            ),
            "formal.official_alpha_pool": FakeFormalTableSnapshot(
                table="formal.official_alpha_pool",
                snapshot_id=102,
            ),
            "formal.alpha_result_snapshot": FakeFormalTableSnapshot(
                table="formal.alpha_result_snapshot",
                snapshot_id=103,
            ),
            "formal.recommendation_snapshot": FakeFormalTableSnapshot(
                table="formal.recommendation_snapshot",
                snapshot_id=104,
            ),
        },
    )


def test_data_platform_manifest_gateway_normalizes_runtime_manifest_refs() -> None:
    gateway = DataPlatformManifestGateway(load_manifest=lambda _cycle_id: _manifest())

    manifest = gateway.load("CYCLE_20260415")

    assert manifest.published_cycle_id == "CYCLE_20260415"
    assert manifest.snapshot_refs == {
        "world_state_snapshot": (
            "data-platform://formal/world_state_snapshot/snapshots/101"
        ),
        "official_alpha_pool": (
            "data-platform://formal/official_alpha_pool/snapshots/102"
        ),
        "alpha_result_snapshot": (
            "data-platform://formal/alpha_result_snapshot/snapshots/103"
        ),
        "recommendation_snapshot": (
            "data-platform://formal/recommendation_snapshot/snapshots/104"
        ),
    }


def test_data_platform_formal_gateway_loads_by_published_snapshot_ref() -> None:
    calls: list[tuple[int, str]] = []

    def load_formal(snapshot_id: int, object_type: str) -> FakeFormalObject:
        calls.append((snapshot_id, object_type))
        return FakeFormalObject(
            cycle_id="CYCLE_20260415",
            object_type=object_type,
            snapshot_id=snapshot_id,
            payload=FakeArrowTable(),
        )

    gateway = DataPlatformFormalSnapshotGateway(
        load_formal_by_snapshot=load_formal,
    )

    snapshot = gateway.load_snapshot(
        "data-platform://formal/recommendation_snapshot/snapshots/104"
    )

    assert calls == [(104, "recommendation_snapshot")]
    assert snapshot["snapshot_ref"] == (
        "data-platform://formal/recommendation_snapshot/snapshots/104"
    )
    assert snapshot["cycle_id"] == "CYCLE_20260415"
    assert snapshot["row_count"] == 1
    assert snapshot["payload"][0]["content_kind"] == "synthetic_minimal_formal_object"


def test_real_cycle_context_drives_existing_replay_query_without_fixtures() -> None:
    manifest_gateway = DataPlatformManifestGateway(
        load_manifest=lambda _cycle_id: _manifest(),
    )
    formal_gateway = DataPlatformFormalSnapshotGateway(
        load_formal_by_snapshot=lambda snapshot_id, object_type: FakeFormalObject(
            cycle_id="CYCLE_20260415",
            object_type=object_type,
            snapshot_id=snapshot_id,
            payload=FakeArrowTable(),
        )
    )

    context = build_data_platform_replay_query_context(
        cycle_id="CYCLE_20260415",
        object_ref="recommendation_snapshot",
        manifest_gateway=manifest_gateway,
        formal_gateway=formal_gateway,
    )
    replay_view = replay_cycle_object(
        "CYCLE_20260415",
        "recommendation_snapshot",
        context=context,
    ).to_dict()

    assert replay_view["manifest_snapshot_set"]["recommendation_snapshot"] == (
        "data-platform://formal/recommendation_snapshot/snapshots/104"
    )
    assert set(replay_view["historical_formal_objects"]) == {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
    }
    assert replay_view["audit_records"][0]["llm_lineage"] == {"called": False}
    assert replay_view["audit_records"][0]["degradation_flags"][
        "recommendation_generated"
    ] is False
    assert replay_view["dagster_run_summary"]["source"] == (
        "data-platform-published-cycle"
    )


def test_data_platform_snapshot_ref_parser_rejects_non_data_platform_refs() -> None:
    with pytest.raises(DataPlatformBindingError):
        parse_data_platform_snapshot_ref(
            "snapshot://cycle_20260410/recommendation_snapshot"
        )


def test_data_platform_snapshot_ref_rejects_non_formal_table_key() -> None:
    with pytest.raises(DataPlatformBindingError):
        data_platform_snapshot_ref("canonical.stock_basic", 1)
