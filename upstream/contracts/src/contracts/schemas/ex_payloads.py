"""Ex payload schemas shared by producer-facing contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from contracts.core import (
    AwareDatetime,
    Confidence,
    ContractBaseModel,
    DeltaId,
    Direction,
    EntityId,
    EvidenceRef,
    FactId,
    HeartbeatStatus,
    Magnitude,
    NodeId,
    SectorId,
    SignalId,
    SubsystemId,
    VersionString,
)
from contracts.errors import ErrorCode, validation_error_message


FORBIDDEN_INGEST_METADATA_FIELDS: frozenset[str] = frozenset(
    {"submitted_at", "ingest_seq"}
)


class BaseExPayload(ContractBaseModel):
    """Shared base for Ex producer payload schemas."""

    subsystem_id: SubsystemId

    @model_validator(mode="before")
    @classmethod
    def reject_ingest_metadata(cls, data: object) -> object:
        """Reject Layer B ingest metadata in producer payloads."""

        if isinstance(data, Mapping):
            forbidden_fields = FORBIDDEN_INGEST_METADATA_FIELDS.intersection(data)
            if forbidden_fields:
                field_list = ", ".join(sorted(forbidden_fields))
                raise ValueError(
                    validation_error_message(
                        ErrorCode.FORBIDDEN_INGEST_METADATA,
                        "ingest metadata fields are not allowed in Ex payloads: "
                        f"{field_list}",
                    )
                )

        return data


class Ex0Metadata(BaseExPayload):
    """Ex-0 metadata and heartbeat payload."""

    version: VersionString
    heartbeat_at: AwareDatetime
    status: HeartbeatStatus
    last_output_at: AwareDatetime | None
    pending_count: int = Field(ge=0, strict=True)


class Ex1CandidateFact(BaseExPayload):
    """Ex-1 candidate fact payload.

    v0.1.3 additions (backward compatible):
    - ``evidence`` (optional canonical evidence-ref list, mirrors Ex2/Ex3)
    - ``producer_context`` (canonical extension slot for subsystem-local
      provenance fields that Layer B treats as opaque passthrough; see
      ``BaseExPayload`` docstring & the v0.1.3 CHANGELOG entry)
    """

    fact_id: FactId
    entity_id: EntityId
    fact_type: str = Field(min_length=1)
    fact_content: dict[str, object]
    confidence: Confidence
    source_reference: dict[str, object]
    extracted_at: AwareDatetime
    evidence: list[EvidenceRef] | None = None
    producer_context: dict[str, Any] | None = None

    @field_validator("fact_content", "source_reference")
    @classmethod
    def validate_non_empty_dict(
        cls, value: dict[str, object], info: ValidationInfo
    ) -> dict[str, object]:
        """Reject empty structured payload fields."""

        if not value:
            raise ValueError(
                validation_error_message(
                    ErrorCode.CONTRACT_VALIDATION_ERROR,
                    f"{info.field_name} must not be empty",
                )
            )

        return value


class Ex2CandidateSignal(BaseExPayload):
    """Ex-2 candidate signal payload.

    v0.1.3 changes (backward compatible):
    - ``affected_sectors`` constraint relaxed: ``Field(min_length=1)`` is
      removed (the list itself no longer requires ≥1 entry); the field
      remains REQUIRED on the wire (so consumers can still rely on its
      presence — they just must accept ``[]``). Sector enrichment is the
      downstream graph-engine's responsibility, not subsystem ingestion.
      Existing producers that emit non-empty sectors keep working; new
      producers (announcement / news) without sector data emit ``[]``.
      Element-level constraint (each SectorId still ``min_length=1``)
      preserved — no truly empty-string sectors allowed.
    - ``producer_context`` added as canonical extension slot (see Ex-1).
    """

    signal_id: SignalId
    signal_type: str = Field(min_length=1)
    direction: Direction
    magnitude: Magnitude
    affected_entities: list[EntityId] = Field(min_length=1)
    affected_sectors: list[SectorId]
    time_horizon: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    confidence: Confidence
    producer_context: dict[str, Any] | None = None


class Ex3CandidateGraphDelta(BaseExPayload):
    """Ex-3 candidate graph delta payload.

    v0.1.3 addition (backward compatible):
    - ``producer_context`` added as canonical extension slot (see Ex-1).
    """

    delta_id: DeltaId
    delta_type: str = Field(min_length=1)
    source_node: NodeId
    target_node: NodeId
    relation_type: str = Field(min_length=1)
    properties: dict[str, object]
    evidence: list[EvidenceRef] = Field(min_length=1)
    producer_context: dict[str, Any] | None = None


__all__ = [
    "FORBIDDEN_INGEST_METADATA_FIELDS",
    "BaseExPayload",
    "Ex0Metadata",
    "Ex1CandidateFact",
    "Ex2CandidateSignal",
    "Ex3CandidateGraphDelta",
]
