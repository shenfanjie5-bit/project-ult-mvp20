"""Public Python API for Lite candidate queue writes."""

from __future__ import annotations

from data_platform.queue.models import CandidateQueueItem, CandidateSubmitReceipt
from data_platform.queue.repository import CandidateRepository
from data_platform.queue.validation import ExPayload, validate_candidate_envelope


def submit_candidate(payload: ExPayload) -> CandidateQueueItem:
    """Validate and insert one producer Ex payload into candidate_queue."""

    envelope = validate_candidate_envelope(payload)
    repository = CandidateRepository()
    try:
        return repository.insert_candidate(envelope)
    finally:
        repository.close()


def submit_candidate_idempotent(payload: ExPayload) -> CandidateSubmitReceipt:
    """Validate and idempotently insert one producer Ex payload into candidate_queue."""

    envelope = validate_candidate_envelope(payload)
    repository = CandidateRepository()
    try:
        return repository.insert_candidate_idempotent(envelope)
    finally:
        repository.close()


__all__ = ["ExPayload", "submit_candidate", "submit_candidate_idempotent"]
