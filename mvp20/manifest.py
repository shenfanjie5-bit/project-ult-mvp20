"""MVP20 universe manifest validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TS_CODE_RE = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")
DECISION_TARGET_COUNT = 20
HISTORY_WINDOW_MONTHS = 120
GRAPH_DEPTH = 2
RELATED_POLICY = "graph_and_risk_summary_only"


@dataclass(frozen=True)
class ManifestValidationResult:
    ok: bool
    universe_id: str
    decision_target_count: int
    live_evidence_blocked: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a YAML object")
    return payload


def validate_manifest(path: Path) -> ManifestValidationResult:
    manifest = load_manifest(path)
    errors: list[str] = []
    warnings: list[str] = []

    universe_id = _string(manifest.get("universe_id"))
    if not universe_id:
        errors.append("universe_id is required")

    if manifest.get("history_window_months") != HISTORY_WINDOW_MONTHS:
        errors.append("history_window_months must be 120")
    if manifest.get("graph_depth") != GRAPH_DEPTH:
        errors.append("graph_depth must be 2")
    if manifest.get("related_entity_policy") != RELATED_POLICY:
        errors.append(
            "related_entity_policy must be graph_and_risk_summary_only",
        )

    targets = manifest.get("decision_targets")
    if not isinstance(targets, list):
        errors.append("decision_targets must be a list")
        targets = []
    if len(targets) != DECISION_TARGET_COUNT:
        errors.append("decision_targets must contain exactly 20 stocks")

    seen_ts_codes: set[str] = set()
    slot_count = 0
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            errors.append(f"decision_targets[{index}] must be an object")
            continue
        ts_code = _string(target.get("ts_code"))
        if not TS_CODE_RE.fullmatch(ts_code):
            errors.append(f"decision_targets[{index}].ts_code is invalid")
        if ts_code in seen_ts_codes:
            errors.append(f"duplicate decision target ts_code: {ts_code}")
        seen_ts_codes.add(ts_code)
        if target.get("slot") is True:
            slot_count += 1

    live_evidence_blocked = bool(manifest.get("live_evidence_blocked"))
    if slot_count and not live_evidence_blocked:
        errors.append("slot manifest must keep live_evidence_blocked=true")
    if live_evidence_blocked:
        warnings.append("live MVP evidence is blocked until real ts_codes are filled")

    return ManifestValidationResult(
        ok=not errors,
        universe_id=universe_id,
        decision_target_count=len(targets),
        live_evidence_blocked=live_evidence_blocked,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _string(value: object) -> str:
    return "" if value is None else str(value).strip()
