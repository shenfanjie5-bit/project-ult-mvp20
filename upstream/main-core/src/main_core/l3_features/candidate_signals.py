"""Read-only Layer B candidate signal adapter for L3 feature bundles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Protocol, runtime_checkable

from main_core.common.errors import MainCoreError
from main_core.common.schemas.feature_bundle import FeatureSignalBundle
from main_core.common.types import CycleId, EntityId


class CandidateSignalError(MainCoreError):
    """Raised when Layer B candidate signals cannot be consumed safely."""


@dataclass(frozen=True, slots=True)
class CandidateSignalRecord:
    """One read-only Layer B candidate signal row."""

    cycle_id: CycleId
    entity_id: EntityId
    signal_name: str
    value: Any
    source: str = "layer_b"
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class CandidateSignalPort(Protocol):
    """Read-only Layer B candidate signal boundary used by L3."""

    def read_candidate_signals(
        self,
        cycle_id: CycleId,
    ) -> Sequence[CandidateSignalRecord]:
        """Return candidate signals for the requested cycle."""


def candidate_signal_multiplier(
    signal_name: str,
    multipliers: Mapping[str, float],
) -> float:
    """Return the multiplier for a candidate signal, falling back to 1.0."""

    scoped_name = f"candidate_signals.{signal_name}"
    if scoped_name in multipliers:
        return float(multipliers[scoped_name])
    if signal_name in multipliers:
        return float(multipliers[signal_name])
    return 1.0


def normalize_candidate_signals(
    records: Sequence[CandidateSignalRecord],
    *,
    cycle_id: CycleId,
    entity_id: EntityId,
    multipliers: Mapping[str, float],
) -> dict[str, Any]:
    """Normalize Layer B records for one existing market-backed entity."""

    normalized: dict[str, Any] = {}
    seen_record_keys: set[tuple[str, str, str]] = set()
    for record in records:
        if str(record.cycle_id) != str(cycle_id):
            raise CandidateSignalError(
                "candidate signal records must match the requested cycle_id"
            )

        record_key = (str(record.entity_id), record.source, record.signal_name)
        if record_key in seen_record_keys:
            raise CandidateSignalError(
                "candidate signal records contain duplicate entity/source/signal_name"
            )
        seen_record_keys.add(record_key)

        if str(record.entity_id) != str(entity_id):
            continue

        if record.signal_name in normalized:
            raise CandidateSignalError(
                "candidate signal names must be unique per entity"
            )

        raw_value = record.value
        adjusted_value = raw_value
        if _is_number(raw_value):
            multiplier = candidate_signal_multiplier(record.signal_name, multipliers)
            adjusted_value = raw_value * multiplier
            if not isfinite(adjusted_value):
                raise CandidateSignalError(
                    "candidate signal adjusted_value must be finite"
                )

        normalized[record.signal_name] = {
            "raw_value": raw_value,
            "adjusted_value": adjusted_value,
            "source": record.source,
            "confidence": record.confidence,
            "metadata": dict(record.metadata),
        }

    return normalized


def merge_candidate_signals(
    bundle: FeatureSignalBundle,
    candidate_signals: Mapping[str, Any],
) -> FeatureSignalBundle:
    """Return a new feature bundle with candidate signals nested in signal_values."""

    merged_signal_values = dict(bundle.signal_values)
    if not candidate_signals:
        return bundle.model_copy(update={"signal_values": merged_signal_values})

    if "candidate_signals" not in merged_signal_values:
        merged_signal_values["candidate_signals"] = dict(candidate_signals)
        return bundle.model_copy(update={"signal_values": merged_signal_values})

    existing_candidate_payload = merged_signal_values["candidate_signals"]
    if not isinstance(existing_candidate_payload, Mapping):
        raise CandidateSignalError(
            "signal_values.candidate_signals must be a mapping when present"
        )

    merged_candidate_payload = dict(existing_candidate_payload)
    duplicate_signal_names = sorted(
        str(signal_name)
        for signal_name in candidate_signals
        if signal_name in merged_candidate_payload
    )
    if duplicate_signal_names:
        raise CandidateSignalError(
            "candidate signal merge would overwrite existing candidate payload"
        )

    merged_candidate_payload.update(candidate_signals)
    merged_signal_values["candidate_signals"] = merged_candidate_payload
    return bundle.model_copy(update={"signal_values": merged_signal_values})


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


__all__ = [
    "CandidateSignalError",
    "CandidateSignalPort",
    "CandidateSignalRecord",
    "candidate_signal_multiplier",
    "merge_candidate_signals",
    "normalize_candidate_signals",
]
