"""Human override submission and application helpers for L7."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from main_core.common.errors import MainCoreError
from main_core.common.schemas import OverrideRecord, RecommendationSnapshot
from main_core.common.types import CycleId, EntityId


class OverrideStore(Protocol):
    """Minimal storage protocol for validated override records."""

    def save(self, override: OverrideRecord) -> OverrideRecord:
        """Persist an override and return the stored immutable record."""

    def list_overrides(self) -> Sequence[OverrideRecord]:
        """Return stored override records in insertion order."""


class InMemoryOverrideStore:
    """Local/test-only override store with insertion-order semantics."""

    def __init__(self, overrides: Sequence[OverrideRecord] | None = None) -> None:
        self._overrides = [override.model_copy() for override in overrides or ()]

    @property
    def records(self) -> tuple[OverrideRecord, ...]:
        """Return immutable stored records for tests and local callers."""

        return tuple(self._overrides)

    def save(self, override: OverrideRecord) -> OverrideRecord:
        """Store a validated override record."""

        stored_override = override.model_copy()
        self._overrides.append(stored_override)
        return stored_override

    def list_overrides(self) -> Sequence[OverrideRecord]:
        """Return stored override records in insertion order."""

        return self.records


_DEFAULT_OVERRIDE_STORE = InMemoryOverrideStore()


def submit_override(
    override_input: OverrideRecord | Mapping[str, Any],
    *,
    store: OverrideStore | None = None,
) -> OverrideRecord:
    """Validate, store, and return a human override record."""

    override = _coerce_override(override_input)
    active_store = store if store is not None else _DEFAULT_OVERRIDE_STORE
    return active_store.save(override)


def find_override(
    overrides: Sequence[OverrideRecord],
    cycle_id: CycleId,
    entity_id: EntityId,
) -> OverrideRecord | None:
    """Return the first override matching a cycle/entity pair."""

    for override in overrides:
        if override.cycle_id == cycle_id and override.entity_id == entity_id:
            return override
    return None


def apply_override(
    candidate: RecommendationSnapshot,
    override: OverrideRecord,
) -> RecommendationSnapshot:
    """Apply a matching human override while preserving constraint audit data."""

    if candidate.cycle_id != override.cycle_id:
        raise MainCoreError("override cycle_id must match recommendation cycle_id")
    if candidate.entity_id != override.entity_id:
        raise MainCoreError("override entity_id must match recommendation entity_id")

    updates: dict[str, Any] = {
        "action_type": override.action_type,
        "triggered_by": "human_decision",
        "override_applied": True,
        "constraints_applied": dict(candidate.constraints_applied),
    }
    if override.action_type == "inconclusive":
        updates["rating"] = None
        updates["confidence"] = None
    else:
        updates["rating"] = _rating_for_action(override.action_type)

    return candidate.model_copy(update=updates)


def _coerce_override(override_input: OverrideRecord | Mapping[str, Any]) -> OverrideRecord:
    if isinstance(override_input, OverrideRecord):
        return override_input.model_copy()
    return OverrideRecord.model_validate(dict(override_input))


def _rating_for_action(action_type: str) -> str:
    ratings = {
        "buy": "A",
        "hold": "B",
        "reduce": "C",
    }
    return ratings[action_type]


__all__ = [
    "InMemoryOverrideStore",
    "OverrideStore",
    "apply_override",
    "find_override",
    "submit_override",
]
