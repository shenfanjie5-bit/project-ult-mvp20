"""Cycle control metadata schema."""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import ConfigDict, model_validator

from contracts.core import (
    AwareDatetime,
    ContractBaseModel,
    CycleId,
    VersionString,
    __version__,
)
from contracts.errors import ErrorCode, validation_error_message


class CyclePhase(str, Enum):
    """Cycle execution phase."""

    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class CycleMetadata(ContractBaseModel):
    """Minimal cycle control metadata shared by orchestrator consumers."""

    model_config = ConfigDict(frozen=True)

    cycle_id: CycleId
    phase: CyclePhase
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    previous_cycle_id: CycleId | None = None
    version: VersionString = __version__

    @model_validator(mode="after")
    def ended_at_must_not_precede_started_at(self) -> Self:
        """Ensure completed cycle windows are chronologically valid."""

        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError(
                validation_error_message(
                    ErrorCode.CONTRACT_VALIDATION_ERROR,
                    "ended_at must be greater than or equal to started_at",
                )
            )

        return self


__all__ = ["CyclePhase", "CycleMetadata"]
