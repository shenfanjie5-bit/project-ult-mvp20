"""Public API for Lite candidate selection freeze."""

from __future__ import annotations

from data_platform.cycle.models import CycleMetadata, _cycle_date_from_id
from data_platform.cycle.repository import CycleRepository


def freeze_cycle_candidates(
    cycle_id: str,
    *,
    submitted_by: str | None = None,
    payload_type: str | None = None,
) -> CycleMetadata:
    """Freeze accepted candidate_queue rows for one cycle."""

    _cycle_date_from_id(cycle_id)
    repository = CycleRepository()
    try:
        with repository.begin() as connection:
            return repository.freeze_selection(
                cycle_id,
                connection,
                submitted_by=submitted_by,
                payload_type=payload_type,
            )
    finally:
        repository.close()


__all__ = ["freeze_cycle_candidates"]
