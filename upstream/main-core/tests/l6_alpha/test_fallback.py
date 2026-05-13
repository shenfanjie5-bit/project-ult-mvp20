"""Tests for L6 inconclusive fallback helpers."""

from __future__ import annotations

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.errors import InconclusiveError, MainCoreError
from main_core.l6_alpha import AlphaReasonerResponse, build_inconclusive_result
from main_core.l6_alpha.fallback import is_task_level_failure


def test_build_inconclusive_result_creates_valid_formal_object(
    analysis_context: AlphaAnalysisContext,
) -> None:
    result = build_inconclusive_result(
        "ENT_A",
        analysis_context,
        "provider returned no usable answer",
    )

    assert result.cycle_id == "cycle_l6"
    assert result.entity_id == "ENT_A"
    assert result.analyzer_type == "single_prompt_v1"
    assert result.status == "inconclusive"
    assert result.score is None
    assert result.confidence == 0.0
    assert "provider returned no usable answer" in result.rationale
    assert result.similar_cases == ({"entity_id": "ENT_B", "score": 0.4},)


def test_build_inconclusive_result_accepts_explicit_similar_cases(
    analysis_context: AlphaAnalysisContext,
) -> None:
    result = build_inconclusive_result(
        "ENT_A",
        analysis_context,
        "task timeout",
        similar_cases=[{"entity_id": "ENT_C"}],
    )

    assert result.similar_cases == ({"entity_id": "ENT_C"},)


def test_is_task_level_failure_only_accepts_inconclusive_errors() -> None:
    assert is_task_level_failure(InconclusiveError("single stock task failed"))
    assert is_task_level_failure(
        AlphaReasonerResponse(
            score=None,
            confidence=0.0,
            rationale="provider task failed",
            similar_cases=[],
            task_failed=True,
        ),
    )
    assert not is_task_level_failure(MainCoreError("infrastructure failed"))
    assert not is_task_level_failure(RuntimeError("unknown failure"))
