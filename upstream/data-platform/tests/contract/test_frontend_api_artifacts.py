from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "frontend-api"


def test_frontend_api_cycle_artifacts_exist() -> None:
    required_paths = [
        ARTIFACT_ROOT / "cycles.json",
        ARTIFACT_ROOT / "manifests" / "latest.json",
        ARTIFACT_ROOT / "formal" / "world_state_snapshot" / "latest.json",
        ARTIFACT_ROOT / "formal" / "official_alpha_pool" / "latest.json",
        ARTIFACT_ROOT / "formal" / "recommendation_snapshot" / "latest.json",
    ]

    missing = [str(path) for path in required_paths if not path.exists()]

    assert missing == []


def test_frontend_api_manifest_artifact_is_keyed_snapshot_object() -> None:
    manifest = _load_json(ARTIFACT_ROOT / "manifests" / "latest.json")

    snapshots = manifest["formal_table_snapshots"]

    assert manifest["published_cycle_id"] == "CYCLE_20260424"
    assert isinstance(snapshots, dict)
    assert snapshots.keys() >= {
        "world_state_snapshot",
        "official_alpha_pool",
        "recommendation_snapshot",
    }
    for object_type, snapshot in snapshots.items():
        assert isinstance(object_type, str)
        assert isinstance(snapshot, dict)
        assert snapshot["snapshot_id"]
        assert snapshot["manifest_ref"]


def test_frontend_api_formal_artifacts_expose_domain_payloads() -> None:
    world_state = _load_formal_payload("world_state_snapshot")
    pool = _load_formal_payload("official_alpha_pool")
    recommendations = _load_formal_payload("recommendation_snapshot")

    assert world_state["regime"] == "range_bound"
    assert isinstance(pool["core_pool"], list)
    assert pool["core_pool"][0]["stock_id"] == "600519.SH"
    assert isinstance(recommendations["recommendations"], list)
    assert recommendations["recommendations"][0]["rank"] == 1


def test_frontend_api_cycle_index_points_to_published_artifact_cycle() -> None:
    cycles = _load_json(ARTIFACT_ROOT / "cycles.json")

    assert cycles["items"][0]["cycle_id"] == "CYCLE_20260424"
    assert cycles["items"][0]["status"] == "published"
    assert isinstance(
        cycles["items"][0]["manifest"]["formal_table_snapshots"],
        dict,
    )


def test_frontend_api_canonical_data_artifact_exposes_rows() -> None:
    payload = _load_json(ARTIFACT_ROOT / "data" / "canonical" / "stock_basic.json")

    assert payload["columns"] == [
        "ts_code",
        "symbol",
        "name",
        "area",
        "industry",
        "list_status",
    ]
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["ts_code"] == "600519.SH"


def test_frontend_api_raw_data_artifact_exposes_rows() -> None:
    payload = _load_json(ARTIFACT_ROOT / "data" / "raw" / "tushare_stock_basic.json")

    assert payload["columns"] == [
        "source",
        "ts_code",
        "name",
        "trade_date",
        "raw_loaded_at",
    ]
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["source"] == "tushare"


def _load_formal_payload(object_type: str) -> dict[str, Any]:
    formal_object = _load_json(ARTIFACT_ROOT / "formal" / object_type / "latest.json")
    assert formal_object["object_type"] == object_type
    assert formal_object["cycle_id"] == "CYCLE_20260424"
    assert formal_object["snapshot_id"]
    payload = formal_object["payload"]
    assert isinstance(payload, dict)
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
