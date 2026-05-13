"""Formal object name registry aligned with the contracts package."""

from __future__ import annotations

import importlib
from typing import Final

FALLBACK_FORMAL_OBJECT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
        "dashboard_snapshot",
        "report",
        "audit_record",
        "replay_record",
    }
)
REQUIRED_FORMAL_OBJECT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
    }
)


def formal_object_names() -> frozenset[str]:
    """Return canonical formal object names from contracts when installed."""

    contract_names = _contracts_formal_object_names()
    if contract_names:
        return contract_names
    return FALLBACK_FORMAL_OBJECT_NAMES


def validate_formal_object_name(object_name: object) -> str:
    if not isinstance(object_name, str) or not object_name:
        msg = f"formal object name must be a non-empty string: {object_name!r}"
        raise ValueError(msg)
    if object_name not in formal_object_names():
        msg = f"unknown formal object name: {object_name!r}"
        raise ValueError(msg)
    return object_name


def _contracts_formal_object_names() -> frozenset[str]:
    try:
        module = importlib.import_module("contracts.schemas.formal_objects")
    except ImportError:
        return frozenset()

    raw_names = getattr(module, "FORMAL_OBJECT_NAMES", ())
    names: set[str] = set()
    for name in raw_names:
        value = getattr(name, "value", name)
        if isinstance(value, str):
            names.add(value)
    return frozenset(names)


__all__ = [
    "FALLBACK_FORMAL_OBJECT_NAMES",
    "REQUIRED_FORMAL_OBJECT_NAMES",
    "formal_object_names",
    "validate_formal_object_name",
]
