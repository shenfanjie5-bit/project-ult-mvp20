"""Immutable JSON storage helpers for single-stock LLM contexts/decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from mvp20.json_utils import json_safe

CONTEXT_ROOT_NAME = "llm_contexts"
DECISION_ROOT_NAME = "llm_decisions"


def _snapshot_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _snapshot_safe(value.model_dump(mode="json", by_alias=True))
    if isinstance(value, Mapping):
        return {str(k): _snapshot_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_safe(v) for v in value]
    return json_safe(value)


def canonical_json(value: Any) -> str:
    """Stable JSON representation used for replay hashes."""

    return json.dumps(
        _snapshot_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_payload(value: Any) -> str:
    return sha256_text(canonical_json(value))


def short_hash(value: Any, n: int = 12) -> str:
    return sha256_payload(value).split(":", 1)[1][:n]


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            _snapshot_safe(dict(payload)),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=str,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def context_dir(runtime_dir: Path, market: str, ts_code: str, horizon: str) -> Path:
    return runtime_dir / CONTEXT_ROOT_NAME / market / ts_code / horizon


def decision_dir(runtime_dir: Path, market: str, ts_code: str, horizon: str) -> Path:
    return runtime_dir / DECISION_ROOT_NAME / market / ts_code / horizon


def write_context_snapshot(runtime_dir: Path, context: Mapping[str, Any]) -> Path:
    folder = context_dir(
        runtime_dir,
        str(context["market"]),
        str(context["ts_code"]),
        str(context["horizon"]),
    )
    path = folder / f"{context['context_id']}.json"
    atomic_write_json(path, context)
    atomic_write_json(folder / "latest.json", context)
    return path


def write_decision_snapshot(runtime_dir: Path, decision: Mapping[str, Any]) -> Path:
    folder = decision_dir(
        runtime_dir,
        str(decision["market"]),
        str(decision["ts_code"]),
        str(decision["horizon"]),
    )
    path = folder / f"{decision['decision_id']}.json"
    atomic_write_json(path, decision)
    atomic_write_json(folder / "latest.json", decision)
    return path


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_context_snapshot(
    runtime_dir: Path,
    *,
    market: str,
    ts_code: str,
    horizon: str,
    context_id: str | None = None,
) -> dict[str, Any] | None:
    folder = context_dir(runtime_dir, market, ts_code, horizon)
    path = folder / (f"{context_id}.json" if context_id else "latest.json")
    return read_json(path)


def read_decision_snapshot(
    runtime_dir: Path,
    *,
    market: str,
    ts_code: str,
    horizon: str,
    decision_id: str | None = None,
) -> dict[str, Any] | None:
    folder = decision_dir(runtime_dir, market, ts_code, horizon)
    path = folder / (f"{decision_id}.json" if decision_id else "latest.json")
    return read_json(path)


def latest_decision_summary(
    runtime_dir: Path,
    *,
    market: str,
    ts_code: str,
    horizon: str = "5d",
) -> dict[str, Any]:
    decision = read_decision_snapshot(
        runtime_dir,
        market=market,
        ts_code=ts_code,
        horizon=horizon,
    )
    if not decision:
        return {
            "available": False,
            "reason": "no llm decision snapshot",
            "market": market,
            "ts_code": ts_code,
            "horizon": horizon,
        }
    validation = decision.get("validation_result") or {}
    context = decision.get("context_ref") or {}
    return {
        "available": True,
        "status": decision.get("status"),
        "action_type": decision.get("action_type"),
        "horizon": decision.get("horizon"),
        "context_id": context.get("context_id") or decision.get("context_id"),
        "context_hash": context.get("context_hash"),
        "decision_id": decision.get("decision_id"),
        "decision_hash": decision.get("decision_hash"),
        "as_of": decision.get("as_of"),
        "evidence_counts": decision.get("data_quality_summary", {}).get(
            "evidence_counts",
            {},
        ),
        "validation_passed": bool(validation.get("passed")),
        "evidence_gate_passed": bool(validation.get("evidence_gate_passed")),
        "degradation_flags": decision.get("degradation_flags") or [],
    }


def list_snapshots(folder: Path) -> list[dict[str, Any]]:
    if not folder.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        if path.name == "latest.json":
            continue
        payload = read_json(path)
        if payload:
            rows.append(payload)
    return rows
