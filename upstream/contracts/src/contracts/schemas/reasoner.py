"""Reasoner runtime shared schemas."""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import Field, model_validator

from contracts.core import (
    AwareDatetime,
    Confidence,
    ContractBaseModel,
    CycleId,
    EvidenceRef,
    HeartbeatStatus,
    Severity,
    SubsystemId,
    VersionString,
)
from contracts.core.types import NonEmptyString
from contracts.errors import ErrorCode


class ReasonerStatus(str, Enum):
    """Stable status values for reasoner request execution."""

    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"


class ReasonerErrorCategory(str, Enum):
    """Public reasoner error buckets shared across runtime consumers."""

    INPUT_CONTRACT = "input_contract"
    MODEL_PROVIDER = "model_provider"
    TOOL_EXECUTION = "tool_execution"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


_REASONER_ERROR_CODE_BY_CATEGORY = {
    ReasonerErrorCategory.INPUT_CONTRACT: ErrorCode.REASONER_INPUT_CONTRACT_ERROR,
    ReasonerErrorCategory.MODEL_PROVIDER: ErrorCode.REASONER_MODEL_PROVIDER_ERROR,
    ReasonerErrorCategory.TOOL_EXECUTION: ErrorCode.REASONER_TOOL_EXECUTION_ERROR,
    ReasonerErrorCategory.TIMEOUT: ErrorCode.REASONER_TIMEOUT_ERROR,
    ReasonerErrorCategory.INTERNAL: ErrorCode.REASONER_INTERNAL_ERROR,
}


class ReasonerErrorClassification(ContractBaseModel):
    """Normalized reasoner-runtime error classification."""

    code: ErrorCode
    category: ReasonerErrorCategory
    severity: Severity
    retryable: bool
    message: NonEmptyString
    details: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_code_matches_category(self) -> Self:
        """Keep reasoner error buckets aligned with the central registry."""

        expected_code = _REASONER_ERROR_CODE_BY_CATEGORY[self.category]
        if self.code is not expected_code:
            raise ValueError(
                "reasoner error code "
                f"{self.code.value} does not match category "
                f"{self.category.value}; expected {expected_code.value}"
            )

        return self


class ReasonerRequest(ContractBaseModel):
    """Request envelope accepted by reasoner-runtime."""

    request_id: NonEmptyString
    cycle_id: CycleId
    reasoner_name: NonEmptyString
    reasoner_version: VersionString
    prompt: NonEmptyString
    context: dict[str, object]
    requested_at: AwareDatetime
    input_refs: list[EvidenceRef] = Field(default_factory=list)


class ReasonerResult(ContractBaseModel):
    """Result envelope returned by reasoner-runtime."""

    result_id: NonEmptyString
    request_id: NonEmptyString
    status: ReasonerStatus
    reasoner_name: NonEmptyString
    reasoner_version: VersionString
    output: dict[str, object]
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    completed_at: AwareDatetime
    confidence: Confidence | None = None
    error_classification: ReasonerErrorClassification | None = None

    @model_validator(mode="after")
    def error_classification_must_match_status(self) -> Self:
        """Keep result status aligned with error classification details."""

        if self.status is ReasonerStatus.FAILED:
            if self.error_classification is None:
                raise ValueError(
                    "failed reasoner result requires error_classification"
                )
            return self

        if self.error_classification is not None:
            raise ValueError(
                "error_classification is only allowed for failed reasoner results"
            )

        return self


class ReasonerReplay(ContractBaseModel):
    """Replay bundle for deterministic reasoner-runtime inspection."""

    replay_id: NonEmptyString
    request: ReasonerRequest
    result: ReasonerResult
    recorded_at: AwareDatetime
    replay_version: VersionString


class ReasonerHealth(ContractBaseModel):
    """Reasoner-runtime health contract."""

    subsystem_id: SubsystemId
    version: VersionString
    checked_at: AwareDatetime
    status: HeartbeatStatus
    last_success_at: AwareDatetime | None
    pending_count: int = Field(ge=0, strict=True)
    error_classification: ReasonerErrorClassification | None = None

    @model_validator(mode="after")
    def error_classification_must_match_status(self) -> Self:
        """Keep health status aligned with error classification details."""

        if self.status is HeartbeatStatus.FAILED:
            if self.error_classification is None:
                raise ValueError(
                    "failed reasoner health requires error_classification"
                )
            return self

        if (
            self.status is HeartbeatStatus.OK
            and self.error_classification is not None
        ):
            raise ValueError("ok reasoner health must not carry error_classification")

        return self


__all__ = [
    "ReasonerStatus",
    "ReasonerErrorCategory",
    "ReasonerErrorClassification",
    "ReasonerRequest",
    "ReasonerResult",
    "ReasonerReplay",
    "ReasonerHealth",
]
