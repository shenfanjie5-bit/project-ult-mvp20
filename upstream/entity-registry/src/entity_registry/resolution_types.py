"""Runtime models used during mention resolution."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

from entity_registry.core import FinalStatus, ResolutionMethod
from entity_registry.fuzzy import FuzzyCandidate


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MentionCandidateSet(BaseModel):
    """Candidates collected while resolving one raw mention."""

    raw_mention_text: str
    deterministic_hits: list[str]
    fuzzy_hits: list[str]
    fuzzy_scores: dict[str, float] = Field(default_factory=dict, exclude=True)
    fuzzy_candidates: list[FuzzyCandidate] = Field(default_factory=list, exclude=True)
    llm_required: bool
    final_status: FinalStatus
    failure_rationale: str | None = Field(default=None, exclude=True)


class ResolutionContext(BaseModel):
    """Context supplied to a single mention resolution attempt."""

    raw_mention_text: str
    document_context: str
    source_type: str
    timestamp: datetime = Field(default_factory=_utcnow)


class MentionResolutionResult(BaseModel):
    """Stable public result shape for mention resolution."""

    raw_mention_text: str
    resolved_entity_id: str | None
    resolution_method: ResolutionMethod
    resolution_confidence: float | None

    @model_validator(mode="after")
    def validate_unresolved_result(self) -> MentionResolutionResult:
        if (
            self.resolved_entity_id is None
            and self.resolution_method is not ResolutionMethod.UNRESOLVED
        ):
            raise ValueError(
                "resolved_entity_id=None requires resolution_method='unresolved'"
            )
        if (
            self.resolution_method is ResolutionMethod.UNRESOLVED
            and self.resolved_entity_id is not None
        ):
            raise ValueError("unresolved results must not carry a resolved entity")
        if (
            self.resolution_method is ResolutionMethod.UNRESOLVED
            and self.resolution_confidence is not None
        ):
            raise ValueError("unresolved results must not carry confidence")
        return self


class ResolutionDecision(BaseModel):
    """Decision output from a single resolution attempt."""

    selected_entity_id: str | None
    method: ResolutionMethod
    confidence: float | None
    rationale: str


class BatchResolutionJob(BaseModel):
    """Runtime metadata for a batch resolution job."""

    job_id: str
    reference_ids: list[str]
    status: str
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: str | None = None
