from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "frontend-api"


def test_frontend_api_entity_artifact_exists() -> None:
    path = ARTIFACT_ROOT / "entities.json"

    assert path.exists()


def test_frontend_api_entity_artifact_exposes_search_and_profiles() -> None:
    payload = _load_json(ARTIFACT_ROOT / "entities.json")
    items = payload["items"]

    assert isinstance(items, list)
    assert len(items) >= 2
    first = items[0]
    assert first["entity_id"] == "ENT_STOCK_600519.SH"
    assert first["display_name"] == "Kweichow Moutai"
    assert "600519.SH" in first["aliases"]
    assert first["profile"]["canonical_entity"]["canonical_entity_id"] == (
        "ENT_STOCK_600519.SH"
    )
    assert isinstance(first["profile"]["aliases"], list)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
