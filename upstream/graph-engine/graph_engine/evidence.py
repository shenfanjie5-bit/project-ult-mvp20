"""Evidence reference normalization shared across graph-engine workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def evidence_refs_from_value(value: Any, *, allow_mapping: bool = False) -> list[str]:
    """Return sorted, unique evidence refs from a scalar or collection value."""

    if value is None:
        return []
    if isinstance(value, str):
        ref = value.strip()
        if not ref:
            raise ValueError("evidence refs must be non-empty strings")
        return [ref]
    if isinstance(value, Mapping):
        if allow_mapping:
            return evidence_refs_from_mapping(value)
        raise ValueError("evidence refs must be non-empty strings")
    if isinstance(value, (list, tuple, set)):
        refs: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("evidence refs must be non-empty strings")
            ref = item.strip()
            if not ref:
                raise ValueError("evidence refs must be non-empty strings")
            refs.add(ref)
        return sorted(refs)
    raise ValueError("evidence refs must be non-empty strings")


def evidence_refs_from_mapping(mapping: Mapping[str, Any]) -> list[str]:
    """Extract normalized refs from standard evidence_ref/evidence_refs keys."""

    refs = set(evidence_refs_from_value(mapping.get("evidence_refs")))
    refs.update(evidence_refs_from_value(mapping.get("evidence_ref")))
    return sorted(refs)


def evidence_refs_from_properties(properties: Mapping[str, Any]) -> list[str]:
    """Extract normalized refs from a graph property mapping."""

    return evidence_refs_from_mapping(properties)
