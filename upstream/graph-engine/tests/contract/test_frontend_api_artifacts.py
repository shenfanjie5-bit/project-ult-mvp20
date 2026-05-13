from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "frontend-api"


def test_frontend_api_graph_artifacts_exist() -> None:
    required_paths = [
        ARTIFACT_ROOT / "subgraph.json",
        ARTIFACT_ROOT / "paths.json",
        ARTIFACT_ROOT / "impact.json",
    ]

    missing = [str(path) for path in required_paths if not path.exists()]

    assert missing == []


def test_frontend_api_subgraph_artifact_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "subgraph.json")

    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
    assert payload["nodes"][0]["node_id"] == "ENT_STOCK_600519.SH"
    assert payload["nodes"][0]["display_name"] == "Kweichow Moutai"
    assert payload["nodes"][0]["entity_role"] == "decision_target"
    assert payload["nodes"][2]["entity_role"] == "context_only"
    assert payload["edges"][0]["source_node_id"] == "ENT_STOCK_600519.SH"
    assert payload["edges"][0]["target_entity_role"] == "context_only"
    assert payload["edges"][0]["relationship_type"]


def test_frontend_api_paths_artifact_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "paths.json")
    paths = payload["paths"]

    assert isinstance(paths, list)
    assert paths[0]["seed"] == "ENT_STOCK_600519.SH"
    assert paths[0]["target"] == "ENT_STOCK_300750.SZ"
    assert paths[0]["target_role"] == "decision_target"
    assert paths[0]["channel"] == "event"
    assert isinstance(paths[0]["nodes"], list)
    assert isinstance(paths[0]["edges"], list)
    assert paths[1]["target"] == "SECTOR_LIQUOR"
    assert paths[1]["target_role"] == "context_only"


def test_frontend_api_impact_artifact_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "impact.json")
    items = payload["items"]

    assert payload["entity_id"] == "ENT_STOCK_600519.SH"
    assert payload["snapshot_id"] == "api3c_impact_001"
    assert isinstance(items, list)
    assert items[1]["entity_id"] == "ENT_STOCK_300750.SZ"
    assert items[1]["display_name"] == "CATL"
    assert items[1]["entity_role"] == "decision_target"
    assert items[2]["entity_id"] == "SECTOR_LIQUOR"
    assert items[2]["entity_role"] == "context_only"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
