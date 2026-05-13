from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "frontend-api"


def test_frontend_api_audit_artifacts_exist() -> None:
    required_paths = [
        ARTIFACT_ROOT / "audit" / "CYCLE_20260424.json",
        ARTIFACT_ROOT / "replay" / "CYCLE_20260424.json",
        ARTIFACT_ROOT / "backtests.json",
        ARTIFACT_ROOT / "backtests" / "BT_API4A_001.json",
    ]

    missing = [str(path) for path in required_paths if not path.exists()]

    assert missing == []


def test_frontend_api_audit_cycle_artifact_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "audit" / "CYCLE_20260424.json")

    assert payload["cycle_id"] == "CYCLE_20260424"
    assert payload["gate_status"] == "passed"
    assert isinstance(payload["audit_records"], list)
    assert payload["audit_records"][0]["record_id"] == "AUDIT_API4A_001"
    assert isinstance(payload["metadata"], dict)


def test_frontend_api_replay_artifact_shape() -> None:
    payload = _load_json(ARTIFACT_ROOT / "replay" / "CYCLE_20260424.json")

    assert payload["cycle_id"] == "CYCLE_20260424"
    assert payload["replay_mode"] == "read_history"
    assert isinstance(payload["objects"], list)
    assert isinstance(payload["invariants"], list)
    assert isinstance(payload["metadata"], dict)


def test_frontend_api_backtest_artifacts_shape() -> None:
    index = _load_json(ARTIFACT_ROOT / "backtests.json")
    detail = _load_json(ARTIFACT_ROOT / "backtests" / "BT_API4A_001.json")

    assert isinstance(index["items"], list)
    assert index["items"][0]["backtest_id"] == "BT_API4A_001"
    assert index["items"][0]["status"] == "completed"
    assert detail["backtest_id"] == "BT_API4A_001"
    assert detail["metric_summary"]["ic_mean"] == 0.04
    assert isinstance(detail["metadata"], dict)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
