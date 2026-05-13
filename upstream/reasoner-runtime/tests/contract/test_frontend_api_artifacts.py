from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "frontend-api"


def test_frontend_api_reasoner_artifacts_exist() -> None:
    required_paths = [
        ARTIFACT_ROOT / "providers.json",
        ARTIFACT_ROOT / "results.json",
    ]

    missing = [str(path) for path in required_paths if not path.exists()]

    assert missing == []


def test_frontend_api_reasoner_providers_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "providers.json")
    items = payload["items"]

    assert isinstance(items, list)
    assert items[0]["provider_id"] == "reasoner_primary_structured"
    assert items[0]["provider"] == "openai"
    assert items[0]["status"] == "available"
    assert isinstance(items[0]["capabilities"], list)
    assert isinstance(payload["metadata"], dict)


def test_frontend_api_reasoner_results_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "results.json")
    items = payload["items"]

    assert isinstance(items, list)
    assert items[0]["result_id"] == "reasoner_result_cycle_20260424_001"
    assert items[0]["cycle_id"] == "CYCLE_20260424"
    assert items[0]["status"] == "success"
    assert isinstance(items[0]["payload"], dict)
    assert isinstance(payload["metadata"], dict)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
