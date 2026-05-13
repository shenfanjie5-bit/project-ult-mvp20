"""Reasoner-runtime boundary for L6 single-stock alpha analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.types import EntityId


@dataclass(frozen=True)
class AlphaReasonerResponse:
    """Raw L6 reasoner response before formal alpha result assembly."""

    score: float | None
    confidence: float
    rationale: str
    similar_cases: list[dict[str, Any]]
    task_failed: bool = False
    failure_reason: str | None = None


class AlphaReasonerPort(Protocol):
    """Boundary protocol for reasoner-runtime alpha analysis."""

    def analyze_alpha(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
    ) -> AlphaReasonerResponse:
        """Analyze one entity and return the raw reasoner response."""


@dataclass(frozen=True)
class StaticAlphaReasonerPort:
    """Deterministic reasoner fake for tests and local single-stock runs."""

    response: AlphaReasonerResponse | None = None

    def analyze_alpha(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
    ) -> AlphaReasonerResponse:
        """Return the configured response, or a static response from context."""

        if self.response is not None:
            return self.response

        return AlphaReasonerResponse(
            score=0.0,
            confidence=0.0,
            rationale="static alpha analysis",
            similar_cases=[dict(case) for case in context.similar_cases],
        )


__all__ = [
    "AlphaReasonerPort",
    "AlphaReasonerResponse",
    "StaticAlphaReasonerPort",
]
