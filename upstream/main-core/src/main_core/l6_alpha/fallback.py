"""Task-level fallback helpers for L6 alpha analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.errors import InconclusiveError
from main_core.common.schemas import AlphaResultSnapshot, single_prompt_result
from main_core.common.types import EntityId
from main_core.l6_alpha.reasoner_port import AlphaReasonerResponse


def build_inconclusive_result(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
    reason: str,
    *,
    similar_cases: Sequence[Mapping[str, Any]] | None = None,
) -> AlphaResultSnapshot:
    """Build a formal inconclusive L6 result for a task-level failure."""

    active_similar_cases = similar_cases if similar_cases is not None else context.similar_cases
    return single_prompt_result(
        cycle_id=context.cycle_id,
        entity_id=entity_id,
        score=None,
        confidence=0.0,
        rationale=f"inconclusive: {reason}",
        similar_cases=[dict(case) for case in active_similar_cases],
        status="inconclusive",
    )


def is_task_level_failure(error: BaseException) -> bool:
    """Return whether an exception should be downgraded to inconclusive."""

    return isinstance(error, InconclusiveError) or (
        isinstance(error, AlphaReasonerResponse) and error.task_failed
    )


__all__ = ["build_inconclusive_result", "is_task_level_failure"]
