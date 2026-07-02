"""Immutable LLM extraction snapshots for candidate deep analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mvp20.json_utils import json_safe
from mvp20.llm_storage import atomic_write_json, read_json, sha256_payload, short_hash

EXTRACTION_SCHEMA_VERSION = "single_stock_llm_extraction.v1"
EXTRACTION_ROOT_NAME = "llm_extractions"
VALUE_SCHEMA_STATUSES = {"Known", "Proxy", "LowMateriality", "Optionality"}

#: A value-asserting field may only lean on evidence that is llm-usable, fresh
#: and verified. This is the pre-materialization quality gate: the upstream
#: context builder retains some signal-protected-but-unusable evidence in the
#: pack (llm_context keeps ``llm_usable or protected``), so existence alone is
#: not enough — the cited item's quality must be checked here.
ACCEPTABLE_FRESHNESS = {"fresh"}
ACCEPTABLE_VERIFICATION = {"verified"}


def normalize_context_payload(context: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(context, "model_dump"):
        return context.model_dump(mode="json", by_alias=True)
    return dict(context)


def _context_hash(context_payload: Mapping[str, Any]) -> str | None:
    if not context_payload.get("context_id"):
        return None
    return context_payload.get("input_hash") or sha256_payload({
        k: v
        for k, v in context_payload.items()
        if k not in {"storage"}
    })


def extraction_dir(runtime_dir: Path, market: str, ts_code: str, horizon: str) -> Path:
    return Path(runtime_dir) / EXTRACTION_ROOT_NAME / str(market) / str(ts_code) / str(horizon)


def write_extraction_snapshot(runtime_dir: Path, extraction: Mapping[str, Any]) -> Path:
    folder = extraction_dir(
        runtime_dir,
        str(extraction["market"]),
        str(extraction["ts_code"]),
        str(extraction["horizon"]),
    )
    path = folder / f"{extraction['extraction_id']}.json"
    atomic_write_json(path, extraction)
    atomic_write_json(folder / "latest.json", extraction)
    return path


def read_extraction_snapshot(
    runtime_dir: Path,
    *,
    market: str,
    ts_code: str,
    horizon: str,
    extraction_id: str | None = None,
) -> dict[str, Any] | None:
    folder = extraction_dir(runtime_dir, market, ts_code, horizon)
    path = folder / (f"{extraction_id}.json" if extraction_id else "latest.json")
    # Defense-in-depth path-traversal guard: any path segment (market /
    # extraction_id) that escapes the extraction root resolves outside it and is
    # refused, regardless of caller-side validation.
    root = (Path(runtime_dir) / EXTRACTION_ROOT_NAME).resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return None
    return read_json(path)


def _evidence_index(context_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index evidence_pack by evidence_ref, retaining the full item so quality
    (usability / freshness / verification) can be checked, not just existence."""

    index: dict[str, Mapping[str, Any]] = {}
    for item in context_payload.get("evidence_pack") or []:
        if isinstance(item, Mapping) and item.get("evidence_ref"):
            index[str(item.get("evidence_ref"))] = item
    return index


def _evidence_quality_errors(dp_id: str, ref: str, item: Mapping[str, Any]) -> list[str]:
    """Reject cited evidence that is not llm-usable / fresh / verified. Each
    status is only enforced when present, so a partial dict is not over-flagged,
    but a populated bad value (the realistic stale-signal leak) is caught."""

    errors: list[str] = []
    if item.get("llm_usable") is False:
        errors.append(f"{dp_id}: evidence_ref {ref} is not llm_usable")
    fresh = item.get("freshness_status")
    if fresh is not None and fresh not in ACCEPTABLE_FRESHNESS:
        errors.append(f"{dp_id}: evidence_ref {ref} freshness_status={fresh} (require fresh)")
    verification = item.get("verification_status")
    if verification is not None and verification not in ACCEPTABLE_VERIFICATION:
        errors.append(
            f"{dp_id}: evidence_ref {ref} verification_status={verification} (require verified)")
    return errors


def _field_errors(
    field: Mapping[str, Any],
    evidence_index: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    dp_id = str(field.get("dp_id") or "")
    if not dp_id:
        errors.append("field missing dp_id")
    status = str(field.get("data_status") or "")
    if not status:
        errors.append(f"{dp_id or '<missing>'}: field missing data_status")
    conf = field.get("confidence")
    if conf is not None:
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0 <= float(conf) <= 1):
            errors.append(f"{dp_id}: confidence must be 0..1")
    refs = field.get("evidence_refs") or field.get("evidence_ref") or []
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list):
        errors.append(f"{dp_id}: evidence_refs must be a list")
        refs = []
    asserts_value = status in VALUE_SCHEMA_STATUSES
    for ref in refs:
        item = evidence_index.get(str(ref))
        if item is None:
            errors.append(f"{dp_id}: unknown evidence_ref {ref}")
            continue
        # A value-asserting field may only cite usable/fresh/verified evidence.
        if asserts_value:
            errors.extend(_evidence_quality_errors(dp_id, str(ref), item))
    if asserts_value:
        if "value" not in field:
            errors.append(f"{dp_id}: {status} field requires value")
        else:
            try:
                from mvp20.schema_validator import validate_value
                schema_errors = validate_value(dp_id, field.get("value"))
            except Exception as exc:  # noqa: BLE001
                schema_errors = [f"schema validator failed: {exc}"]
            errors.extend(f"{dp_id}: {err}" for err in schema_errors)
    return errors


def validate_extraction_output(
    context: Mapping[str, Any] | Any,
    output: Mapping[str, Any],
) -> dict[str, Any]:
    context_payload = normalize_context_payload(context)
    errors: list[str] = []
    if not isinstance(output, Mapping):
        return {"passed": False, "errors": ["output must be an object"], "field_count": 0}
    fields = output.get("fields") or []
    if not isinstance(fields, list):
        return {"passed": False, "errors": ["fields must be a list"], "field_count": 0}
    # An extraction must be bound to a reproducible frozen context; otherwise the
    # immutable snapshot cannot be audited or materialized later.
    if not context_payload.get("context_id"):
        errors.append("context missing context_id; unbound extraction cannot be persisted")
    # A zero-field extraction is inconclusive, not a passing validation.
    if not fields:
        errors.append("extraction has no fields (status inconclusive cannot pass validation)")
    evidence_index = _evidence_index(context_payload)
    for idx, field in enumerate(fields):
        if not isinstance(field, Mapping):
            errors.append(f"fields[{idx}] must be an object")
            continue
        errors.extend(_field_errors(field, evidence_index))
    return {
        "passed": not errors,
        "errors": errors,
        "field_count": len(fields),
        "evidence_ref_count": len(evidence_index),
    }


def _base_extraction(context_payload: Mapping[str, Any]) -> dict[str, Any]:
    as_of = str(context_payload.get("as_of") or datetime.now(tz=timezone.utc).isoformat())
    return {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "extraction_id": "pending",
        "context_ref": {
            "schema_version": context_payload.get("schema_version"),
            "context_id": context_payload.get("context_id"),
            "context_hash": _context_hash(context_payload),
        },
        "cycle_id": str(context_payload.get("cycle_id") or "unknown"),
        "ts_code": str(context_payload.get("ts_code") or ""),
        "market": str(context_payload.get("market") or "UNKNOWN"),
        "horizon": str(context_payload.get("horizon") or "5d"),
        "horizon_days": context_payload.get("horizon_days"),
        "as_of": as_of,
        "status": "inconclusive",
        "fields": [],
        "validation_result": {},
        "extraction_hash": "pending",
        "audit_record": {
            "llm_lineage": {
                "called": False,
                "provider": None,
                "model": None,
            },
            "materialization": {
                "allowed": False,
                "requires_approval": True,
                "target": "runtime_or_overlay_explicit_command_only",
            },
        },
    }


def _finalize_extraction(
    extraction: Mapping[str, Any],
    context_payload: Mapping[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    out = dict(extraction)
    base = _base_extraction(context_payload)
    for key, value in base.items():
        out.setdefault(key, value)
    out.setdefault("fields", [])
    out["context_ref"] = base["context_ref"]
    out["ts_code"] = base["ts_code"]
    out["market"] = base["market"]
    out["horizon"] = base["horizon"]
    out["horizon_days"] = base["horizon_days"]
    if not out.get("status") or out.get("status") == "pending":
        out["status"] = "extracted" if out.get("fields") else "inconclusive"
    validation = validate_extraction_output(context_payload, out)
    out["validation_result"] = validation
    out.setdefault("audit_record", base["audit_record"])
    out["audit_record"] = {
        **base["audit_record"],
        **(out.get("audit_record") if isinstance(out.get("audit_record"), Mapping) else {}),
    }
    out["audit_record"]["llm_lineage"] = {
        **base["audit_record"]["llm_lineage"],
        **((out.get("audit_record") or {}).get("llm_lineage") or {}),
        "called": not dry_run,
    }
    # Content-address the id over semantic content only. Exclude ``as_of`` (a
    # now()-fallback when the context omits it) and ``audit_record`` (carries the
    # volatile ``llm_lineage.called = not dry_run`` flag) so identical extracted
    # content yields a stable id across the dry-run/real boundary and across
    # calls that lack a caller-supplied as_of.
    hash_input = {
        k: v
        for k, v in out.items()
        if k not in {
            "extraction_id",
            "extraction_hash",
            "validation_result",
            "as_of",
            "audit_record",
        }
    }
    out["extraction_hash"] = sha256_payload(hash_input)
    out["extraction_id"] = str(out.get("extraction_id") or "pending")
    if out["extraction_id"] == "pending":
        out["extraction_id"] = "xtr_" + short_hash(hash_input)
    return json_safe(out)


def prepare_extraction_snapshot(
    context: Mapping[str, Any] | Any,
    output: Mapping[str, Any] | None = None,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    context_payload = normalize_context_payload(context)
    if output is None:
        output = _base_extraction(context_payload)
    else:
        output = dict(output)
    return _finalize_extraction(output, context_payload, dry_run=dry_run)
