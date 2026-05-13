"""Fail-closed provenance preflight for formal recommendation snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from data_platform.cycle.models import _cycle_date_from_id
from data_platform.cycle.manifest import (
    FORMAL_RECOMMENDATION_SNAPSHOT,
    FormalTableSnapshot,
    InvalidFormalSnapshotManifest,
    validate_snapshot_id,
)

RECOMMENDATION_PROVENANCE_SOURCE_LAYER: Final[str] = "L8"
RECOMMENDATION_PROVENANCE_SOURCE_KIND: Final[str] = "current-cycle"
_FORBIDDEN_PROVENANCE_KINDS: Final[frozenset[str]] = frozenset(
    {"fixture", "historical", "smoke", "synthetic"}
)


@dataclass(frozen=True, slots=True)
class RecommendationSnapshotProvenance:
    """Proof required before exposing a formal recommendation snapshot."""

    cycle_id: str
    current_cycle_id: str
    source_layer: str
    source_kind: str
    recommendation_snapshot_id: int
    audit_record_ids: tuple[str, ...]
    replay_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cycle_id", _validate_cycle_id(self.cycle_id, "cycle_id"))
        object.__setattr__(
            self,
            "current_cycle_id",
            _validate_cycle_id(self.current_cycle_id, "current_cycle_id"),
        )
        object.__setattr__(
            self,
            "recommendation_snapshot_id",
            validate_snapshot_id(self.recommendation_snapshot_id),
        )
        object.__setattr__(
            self,
            "audit_record_ids",
            _validate_non_empty_ids(self.audit_record_ids, field_name="audit_record_ids"),
        )
        object.__setattr__(
            self,
            "replay_record_ids",
            _validate_non_empty_ids(self.replay_record_ids, field_name="replay_record_ids"),
        )

        if self.cycle_id != self.current_cycle_id:
            msg = (
                "recommendation_snapshot provenance must bind to the current cycle: "
                f"{self.cycle_id!r} != {self.current_cycle_id!r}"
            )
            raise InvalidFormalSnapshotManifest(msg)
        if self.source_layer != RECOMMENDATION_PROVENANCE_SOURCE_LAYER:
            msg = "recommendation_snapshot provenance source_layer must be 'L8'"
            raise InvalidFormalSnapshotManifest(msg)
        if self.source_kind in _FORBIDDEN_PROVENANCE_KINDS:
            msg = (
                "recommendation_snapshot provenance source_kind must not be "
                "fixture, historical, smoke, or synthetic"
            )
            raise InvalidFormalSnapshotManifest(msg)
        if self.source_kind != RECOMMENDATION_PROVENANCE_SOURCE_KIND:
            msg = "recommendation_snapshot provenance source_kind must be 'current-cycle'"
            raise InvalidFormalSnapshotManifest(msg)


RecommendationSnapshotProvenanceInput = (
    RecommendationSnapshotProvenance | Mapping[str, object]
)


def preflight_recommendation_snapshot_publish(
    *,
    cycle_id: str,
    recommendation_snapshot: FormalTableSnapshot,
    provenance: RecommendationSnapshotProvenanceInput | None,
) -> RecommendationSnapshotProvenance:
    """Validate recommendation provenance before formal publish becomes visible."""

    if recommendation_snapshot.table != FORMAL_RECOMMENDATION_SNAPSHOT:
        msg = (
            "recommendation provenance preflight requires "
            f"{FORMAL_RECOMMENDATION_SNAPSHOT!r}"
        )
        raise InvalidFormalSnapshotManifest(msg)
    if provenance is None:
        msg = "recommendation_snapshot formal publish requires provenance preflight"
        raise InvalidFormalSnapshotManifest(msg)

    proof = _coerce_provenance(provenance)
    if proof.cycle_id != cycle_id:
        msg = (
            "recommendation_snapshot provenance cycle_id must match published cycle: "
            f"{proof.cycle_id!r} != {cycle_id!r}"
        )
        raise InvalidFormalSnapshotManifest(msg)
    if proof.recommendation_snapshot_id != recommendation_snapshot.snapshot_id:
        msg = (
            "recommendation_snapshot provenance snapshot id must match manifest: "
            f"{proof.recommendation_snapshot_id!r} != "
            f"{recommendation_snapshot.snapshot_id!r}"
        )
        raise InvalidFormalSnapshotManifest(msg)
    return proof


def _coerce_provenance(
    provenance: RecommendationSnapshotProvenanceInput,
) -> RecommendationSnapshotProvenance:
    if isinstance(provenance, RecommendationSnapshotProvenance):
        return provenance
    if not isinstance(provenance, Mapping):
        msg = "recommendation_snapshot provenance must be a mapping"
        raise InvalidFormalSnapshotManifest(msg)
    try:
        return RecommendationSnapshotProvenance(
            cycle_id=str(provenance["cycle_id"]),
            current_cycle_id=str(provenance["current_cycle_id"]),
            source_layer=str(provenance["source_layer"]),
            source_kind=str(provenance["source_kind"]),
            recommendation_snapshot_id=provenance["recommendation_snapshot_id"],  # type: ignore[arg-type]
            audit_record_ids=_coerce_ids(
                provenance["audit_record_ids"],
                field_name="audit_record_ids",
            ),
            replay_record_ids=_coerce_ids(
                provenance["replay_record_ids"],
                field_name="replay_record_ids",
            ),
        )
    except KeyError as exc:
        msg = f"recommendation_snapshot provenance missing field: {exc.args[0]}"
        raise InvalidFormalSnapshotManifest(msg) from exc


def _validate_cycle_id(value: str, field_name: str) -> str:
    try:
        _cycle_date_from_id(value)
    except Exception as exc:
        msg = f"recommendation_snapshot provenance {field_name} is invalid"
        raise InvalidFormalSnapshotManifest(msg) from exc
    return value


def _coerce_ids(value: object, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        msg = f"recommendation_snapshot provenance {field_name} must be a sequence"
        raise InvalidFormalSnapshotManifest(msg)
    return _validate_non_empty_ids(value, field_name=field_name)


def _validate_non_empty_ids(
    values: Sequence[object],
    *,
    field_name: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            msg = (
                f"recommendation_snapshot provenance {field_name} values must be "
                "non-empty strings"
            )
            raise InvalidFormalSnapshotManifest(msg)
        ids.append(value)
    if not ids:
        msg = f"recommendation_snapshot provenance {field_name} must not be empty"
        raise InvalidFormalSnapshotManifest(msg)
    return tuple(ids)


__all__ = [
    "RECOMMENDATION_PROVENANCE_SOURCE_KIND",
    "RECOMMENDATION_PROVENANCE_SOURCE_LAYER",
    "RecommendationSnapshotProvenance",
    "RecommendationSnapshotProvenanceInput",
    "preflight_recommendation_snapshot_publish",
]
