"""MVP universe manifest validation (13-industry edition).

The MVP universe is organised by industry, not by a fixed stock count. The
manifest declares a set of constituents, each of which must reference one or
two industry slugs declared in the sibling ``mvp20.industries.yaml`` file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# A-share: 6 digits + .SH/.SZ/.BJ
# HK: 4-5 digits + .HK
# US: 1-5 uppercase letters (optionally with a single dot for class shares)
#     followed by .US
TS_CODE_RE = re.compile(
    r"^(?:\d{6}\.(?:SH|SZ|BJ)|\d{4,5}\.HK|[A-Z]{1,5}(?:\.[A-Z])?\.US)$"
)
HISTORY_WINDOW_MONTHS = 120
GRAPH_DEPTH = 2
RELATED_POLICY = "graph_and_risk_summary_only"
INDUSTRY_COUNT = 13
MAX_INDUSTRY_IDS_PER_CONSTITUENT = 3
VALID_ROLES: frozenset[str] = frozenset({"target", "customer", "both"})
DEFAULT_ROLE = "target"
# Pool tier — regular pool covers the full ~300 leader pool; core pool is the
# subset that goes through deep-dive LLM analysis. Membership is curated by
# hand (no auto-promotion).
VALID_POOLS: frozenset[str] = frozenset({"regular", "core"})
DEFAULT_POOL = "regular"

INDUSTRIES_FILENAME = "mvp20.industries.yaml"


@dataclass(frozen=True)
class ManifestValidationResult:
    ok: bool
    universe_id: str
    industry_count: int
    constituent_count: int
    live_evidence_blocked: bool
    industries_with_constituents: tuple[str, ...]
    industries_missing_constituents: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    pool_counts: dict[str, int] = field(default_factory=dict)


VALID_GRAPH_STATUSES: frozenset[str] = frozenset({"present", "pending"})


@dataclass(frozen=True)
class IndustrySetValidationResult:
    ok: bool
    industry_set_id: str
    industry_ids: tuple[str, ...]
    industry_graph_status: dict[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = field(default_factory=tuple)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a YAML object")
    return payload


def load_industry_set(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("industry set must be a YAML object")
    return payload


def validate_industry_set(path: Path) -> IndustrySetValidationResult:
    payload = load_industry_set(path)
    errors: list[str] = []

    industry_set_id = _string(payload.get("industry_set_id"))
    if not industry_set_id:
        errors.append("industry_set_id is required")

    industries = payload.get("industries")
    if not isinstance(industries, list):
        errors.append("industries must be a list")
        industries = []

    seen: list[str] = []
    graph_status_map: dict[str, str] = {}
    for index, entry in enumerate(industries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"industries[{index}] must be an object")
            continue
        slug = _string(entry.get("id"))
        if not slug:
            errors.append(f"industries[{index}].id is required")
            continue
        if not slug.isascii() or not re.fullmatch(r"[A-Z][A-Z0-9_]*", slug):
            errors.append(
                f"industries[{index}].id must be an UPPER_SNAKE_CASE ASCII slug"
            )
        if slug in seen:
            errors.append(f"duplicate industry id: {slug}")
        else:
            seen.append(slug)
        display_name = _string(entry.get("display_name"))
        if not display_name:
            errors.append(f"industries[{index}].display_name is required")
        graph_status = _string(entry.get("graph_status")) or "present"
        if graph_status not in VALID_GRAPH_STATUSES:
            errors.append(
                f"industries[{index}].graph_status must be one of "
                f"{sorted(VALID_GRAPH_STATUSES)}; got {graph_status!r}"
            )
        else:
            graph_status_map[slug] = graph_status

    if industries and len(seen) != INDUSTRY_COUNT:
        errors.append(
            f"industries must contain exactly {INDUSTRY_COUNT} entries; "
            f"got {len(seen)}"
        )

    return IndustrySetValidationResult(
        ok=not errors,
        industry_set_id=industry_set_id,
        industry_ids=tuple(seen),
        industry_graph_status=graph_status_map,
        errors=tuple(errors),
    )


def validate_manifest(
    path: Path, industries_path: Path | None = None
) -> ManifestValidationResult:
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

    # Resolve industry set: prefer caller-provided path, otherwise look for
    # the sibling industries.yaml referenced by industry_set_ref.
    if industries_path is None:
        industries_path = path.parent / INDUSTRIES_FILENAME
    industry_set_ref = _string(manifest.get("industry_set_ref"))
    if not industry_set_ref:
        errors.append("industry_set_ref is required")

    industry_validation: IndustrySetValidationResult | None = None
    if industries_path.exists():
        industry_validation = validate_industry_set(industries_path)
        if not industry_validation.ok:
            for sub_error in industry_validation.errors:
                errors.append(f"industries.yaml: {sub_error}")
        if (
            industry_set_ref
            and industry_validation.industry_set_id
            and industry_set_ref != industry_validation.industry_set_id
        ):
            errors.append(
                "industry_set_ref does not match industries.yaml "
                f"industry_set_id ({industry_set_ref!r} != "
                f"{industry_validation.industry_set_id!r})"
            )
    else:
        errors.append(
            f"industries file not found at {industries_path}"
        )

    valid_industry_ids: set[str] = (
        set(industry_validation.industry_ids)
        if industry_validation is not None
        else set()
    )

    constituents = manifest.get("constituents")
    if not isinstance(constituents, list):
        errors.append("constituents must be a list")
        constituents = []
    if isinstance(constituents, list) and len(constituents) == 0:
        errors.append("constituents must contain at least one entry")

    seen_ts_codes: set[str] = set()
    slot_count = 0
    industries_with_constituents: set[str] = set()
    pool_counts: dict[str, int] = {p: 0 for p in VALID_POOLS}
    for index, target in enumerate(constituents, start=1):
        if not isinstance(target, dict):
            errors.append(f"constituents[{index}] must be an object")
            continue
        ts_code = _string(target.get("ts_code"))
        if not TS_CODE_RE.fullmatch(ts_code):
            errors.append(
                f"constituents[{index}].ts_code is invalid (expected "
                f"<NNNNNN>.SH|SZ|BJ, <NNNN[N]>.HK, or <SYMBOL>.US): {ts_code!r}"
            )
        if ts_code in seen_ts_codes:
            errors.append(f"duplicate constituent ts_code: {ts_code}")
        seen_ts_codes.add(ts_code)
        if target.get("slot") is True:
            slot_count += 1

        role_raw = target.get("role")
        role = _string(role_raw) or DEFAULT_ROLE
        if role not in VALID_ROLES:
            errors.append(
                f"constituents[{index}].role must be one of "
                f"{sorted(VALID_ROLES)}; got {role!r}"
            )

        pool_raw = target.get("pool")
        pool = _string(pool_raw) or DEFAULT_POOL
        if pool not in VALID_POOLS:
            errors.append(
                f"constituents[{index}].pool must be one of "
                f"{sorted(VALID_POOLS)}; got {pool!r}"
            )
        else:
            pool_counts[pool] = pool_counts.get(pool, 0) + 1

        industry_ids = target.get("industry_ids")
        if not isinstance(industry_ids, list) or not industry_ids:
            errors.append(
                f"constituents[{index}].industry_ids must be a non-empty list"
            )
            continue
        if len(industry_ids) > MAX_INDUSTRY_IDS_PER_CONSTITUENT:
            errors.append(
                f"constituents[{index}].industry_ids exceeds max "
                f"{MAX_INDUSTRY_IDS_PER_CONSTITUENT} entries"
            )
        unique_industries: list[str] = []
        for slug in industry_ids:
            slug_str = _string(slug)
            if not slug_str:
                errors.append(
                    f"constituents[{index}].industry_ids contains empty entry"
                )
                continue
            if slug_str in unique_industries:
                errors.append(
                    f"constituents[{index}].industry_ids has duplicate "
                    f"entry: {slug_str}"
                )
                continue
            unique_industries.append(slug_str)
            if valid_industry_ids and slug_str not in valid_industry_ids:
                errors.append(
                    f"constituents[{index}].industry_ids references unknown "
                    f"industry slug: {slug_str}"
                )
            else:
                industries_with_constituents.add(slug_str)

    industries_missing: tuple[str, ...] = ()
    if valid_industry_ids:
        missing = sorted(valid_industry_ids - industries_with_constituents)
        industries_missing = tuple(missing)
        if missing:
            # Pending industries (declared in industries.yaml with
            # graph_status: pending) are allowed to have no constituent yet —
            # they are reserved slots whose universe entries are filled in
            # along with the matching causal-graph YAML. Only constituent gaps
            # for present-graph industries fail the manifest.
            graph_status_map = (
                industry_validation.industry_graph_status
                if industry_validation is not None
                else {}
            )
            hard_missing = [
                slug
                for slug in missing
                if graph_status_map.get(slug, "present") != "pending"
            ]
            soft_missing = [
                slug
                for slug in missing
                if graph_status_map.get(slug, "present") == "pending"
            ]
            if hard_missing:
                errors.append(
                    "industries without any constituent: "
                    + ", ".join(hard_missing)
                )
            for slug in soft_missing:
                warnings.append(
                    f"pending industry {slug} has no constituent yet"
                )

    live_evidence_blocked = bool(manifest.get("live_evidence_blocked"))
    if slot_count and not live_evidence_blocked:
        errors.append("slot manifest must keep live_evidence_blocked=true")
    if live_evidence_blocked:
        warnings.append(
            "live MVP evidence is blocked until real constituents are filled"
        )

    return ManifestValidationResult(
        ok=not errors,
        universe_id=universe_id,
        industry_count=len(valid_industry_ids),
        constituent_count=len(constituents) if isinstance(constituents, list) else 0,
        live_evidence_blocked=live_evidence_blocked,
        industries_with_constituents=tuple(sorted(industries_with_constituents)),
        industries_missing_constituents=industries_missing,
        errors=tuple(errors),
        warnings=tuple(warnings),
        pool_counts=dict(pool_counts),
    )


def _string(value: object) -> str:
    return "" if value is None else str(value).strip()
