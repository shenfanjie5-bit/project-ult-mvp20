"""Types for the PostgreSQL-backed Lite candidate queue."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias

CandidatePayloadType: TypeAlias = Literal["Ex-0", "Ex-1", "Ex-2", "Ex-3"]
ValidationStatus: TypeAlias = Literal["pending", "accepted", "rejected"]

CANDIDATE_QUEUE_TABLE: Final[str] = "data_platform.candidate_queue"
INGEST_METADATA_VIEW: Final[str] = "data_platform.ingest_metadata"

_CANDIDATE_PAYLOAD_TYPES: Final[frozenset[str]] = frozenset(
    ("Ex-0", "Ex-1", "Ex-2", "Ex-3")
)
_VALIDATION_STATUSES: Final[frozenset[str]] = frozenset(
    ("pending", "accepted", "rejected")
)
_FORBIDDEN_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(("submitted_at", "ingest_seq"))


@dataclass(frozen=True, slots=True)
class CandidateSubmitReceipt:
    """Sanitized receipt for an idempotent candidate_queue submission."""

    candidate_id: int
    payload_type: CandidatePayloadType
    submitted_by: str
    submitted_at: datetime
    ingest_seq: int
    validation_status: ValidationStatus
    rejection_reason: str | None
    replayed: bool

    def __post_init__(self) -> None:
        if self.candidate_id < 1:
            msg = "candidate_id must be positive"
            raise ValueError(msg)
        _validate_payload_type(self.payload_type)
        _validate_validation_status(self.validation_status)
        if self.ingest_seq < 1:
            msg = "ingest_seq must be positive"
            raise ValueError(msg)

    @classmethod
    def from_candidate(
        cls,
        item: CandidateQueueItem,
        *,
        replayed: bool,
    ) -> CandidateSubmitReceipt:
        """Build a public receipt without returning producer payload contents."""

        return cls(
            candidate_id=item.id,
            payload_type=item.payload_type,
            submitted_by=item.submitted_by,
            submitted_at=item.submitted_at,
            ingest_seq=item.ingest_seq,
            validation_status=item.validation_status,
            rejection_reason=item.rejection_reason,
            replayed=replayed,
        )

    def as_public_dict(self) -> dict[str, object]:
        """Return a JSON-shaped receipt safe for runbooks and evidence."""

        return {
            "candidate_id": self.candidate_id,
            "payload_type": self.payload_type,
            "submitted_by": self.submitted_by,
            "submitted_at": self.submitted_at.isoformat(),
            "ingest_seq": self.ingest_seq,
            "validation_status": self.validation_status,
            "rejection_reason": self.rejection_reason,
            "replayed": self.replayed,
        }


@dataclass(frozen=True, slots=True)
class CandidateQueueItem:
    """A row from data_platform.candidate_queue."""

    id: int
    payload_type: CandidatePayloadType
    payload: Mapping[str, Any]
    submitted_by: str
    submitted_at: datetime
    ingest_seq: int
    validation_status: ValidationStatus
    rejection_reason: str | None

    def __post_init__(self) -> None:
        _validate_payload_type(self.payload_type)
        _validate_validation_status(self.validation_status)
        _validate_payload(self.payload)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class IngestMetadataRecord:
    """A row from data_platform.ingest_metadata."""

    candidate_id: int
    payload_type: CandidatePayloadType
    submitted_by: str
    submitted_at: datetime
    ingest_seq: int
    validation_status: ValidationStatus
    rejection_reason: str | None

    def __post_init__(self) -> None:
        _validate_payload_type(self.payload_type)
        _validate_validation_status(self.validation_status)


def _validate_payload_type(value: str) -> None:
    if value not in _CANDIDATE_PAYLOAD_TYPES:
        msg = f"payload_type must be one of {sorted(_CANDIDATE_PAYLOAD_TYPES)}"
        raise ValueError(msg)


def _validate_validation_status(value: str) -> None:
    if value not in _VALIDATION_STATUSES:
        msg = f"validation_status must be one of {sorted(_VALIDATION_STATUSES)}"
        raise ValueError(msg)


def _validate_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        msg = "payload must be a JSON object mapping"
        raise TypeError(msg)

    forbidden_keys = sorted(_FORBIDDEN_PAYLOAD_KEYS.intersection(payload))
    if forbidden_keys:
        msg = (
            "producer payload must not include PostgreSQL ingest metadata fields: "
            f"{forbidden_keys}"
        )
        raise ValueError(msg)
