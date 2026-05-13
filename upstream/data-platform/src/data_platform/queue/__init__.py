"""PostgreSQL-backed Lite candidate queue APIs and types."""

from data_platform.queue.api import ExPayload, submit_candidate, submit_candidate_idempotent
from data_platform.queue.models import (
    CANDIDATE_QUEUE_TABLE,
    INGEST_METADATA_VIEW,
    CandidatePayloadType,
    CandidateQueueItem,
    CandidateSubmitReceipt,
    IngestMetadataRecord,
    ValidationStatus,
)
from data_platform.queue.repository import CandidateQueueWriteError, CandidateRepository
from data_platform.queue.validation import (
    FORBIDDEN_PRODUCER_FIELDS,
    CandidateEnvelope,
    CandidateValidationError,
    CandidateValidator,
    EnvelopeCandidateValidator,
    ForbiddenIngestMetadataError,
    validate_candidate_envelope,
)

__all__ = [
    "CANDIDATE_QUEUE_TABLE",
    "FORBIDDEN_PRODUCER_FIELDS",
    "INGEST_METADATA_VIEW",
    "CandidateEnvelope",
    "CandidatePayloadType",
    "CandidateQueueItem",
    "CandidateQueueWriteError",
    "CandidateRepository",
    "CandidateSubmitReceipt",
    "CandidateValidationError",
    "CandidateValidator",
    "EnvelopeCandidateValidator",
    "ExPayload",
    "ForbiddenIngestMetadataError",
    "IngestMetadataRecord",
    "ValidationStatus",
    "submit_candidate",
    "submit_candidate_idempotent",
    "validate_candidate_envelope",
]
