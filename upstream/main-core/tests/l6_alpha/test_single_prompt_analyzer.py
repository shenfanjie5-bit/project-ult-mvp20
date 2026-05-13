"""Tests for the concrete P2 single-prompt analyzer."""

from __future__ import annotations

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.errors import InconclusiveError, MainCoreError
from main_core.common.schemas import AlphaResultSnapshot
from main_core.l6_alpha import AlphaReasonerResponse, SinglePromptAnalyzer
from main_core.l6_alpha.single_prompt_analyzer import AlphaAnalyzerError

EXPECTED_FEATURE_MOMENTUM = 4.2
EXPECTED_FEATURE_MULTIPLIER = 2.5
HAPPY_PATH_CONFIDENCE = 0.82
HAPPY_PATH_SCORE = 0.73


class RecordingReasonerPort:
    def __init__(
        self,
        response: AlphaReasonerResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or AlphaReasonerResponse(
            score=0.5,
            confidence=0.6,
            rationale="recorded response",
            similar_cases=[],
        )
        self.error = error
        self.calls: list[tuple[object, AlphaAnalysisContext]] = []

    def analyze_alpha(
        self,
        entity_id: object,
        context: AlphaAnalysisContext,
    ) -> AlphaReasonerResponse:
        self.calls.append((entity_id, context))
        if self.error is not None:
            raise self.error
        return self.response


def test_single_prompt_analyzer_happy_path_returns_formal_result(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort(
            AlphaReasonerResponse(
                score=HAPPY_PATH_SCORE,
                confidence=HAPPY_PATH_CONFIDENCE,
                rationale="positive quality and momentum",
                similar_cases=[{"entity_id": "ENT_Z", "score": 0.7}],
            ),
    )
    analyzer = SinglePromptAnalyzer(port)

    result = analyzer.analyze("ENT_A", analysis_context)

    assert isinstance(result, AlphaResultSnapshot)
    assert result.analyzer_type == "single_prompt_v1"
    assert result.status == "ok"
    assert result.score == HAPPY_PATH_SCORE
    assert result.confidence == HAPPY_PATH_CONFIDENCE
    assert result.similar_cases == ({"entity_id": "ENT_Z", "score": 0.7},)
    assert port.calls == [("ENT_A", analysis_context)]


def test_single_prompt_analyzer_rejects_entity_mismatch_without_calling_reasoner(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort()
    analyzer = SinglePromptAnalyzer(port)

    with pytest.raises(AlphaAnalyzerError, match="context.entity_id"):
        analyzer.analyze("ENT_OTHER", analysis_context)

    assert port.calls == []


def test_single_prompt_analyzer_converts_task_failed_response_to_inconclusive(
    analysis_context: AlphaAnalysisContext,
) -> None:
    analyzer = SinglePromptAnalyzer(
        RecordingReasonerPort(
            AlphaReasonerResponse(
                score=0.99,
                confidence=0.9,
                rationale="raw provider failure",
                similar_cases=[{"entity_id": "ENT_FAIL"}],
                task_failed=True,
                failure_reason="provider task timeout",
            ),
        ),
    )

    result = analyzer.analyze("ENT_A", analysis_context)

    assert result.status == "inconclusive"
    assert result.score is None
    assert result.confidence == 0.0
    assert "provider task timeout" in result.rationale
    assert result.similar_cases == ({"entity_id": "ENT_FAIL"},)


def test_single_prompt_analyzer_converts_inconclusive_error_to_formal_result(
    analysis_context: AlphaAnalysisContext,
) -> None:
    analyzer = SinglePromptAnalyzer(
        RecordingReasonerPort(error=InconclusiveError("single prompt had no answer")),
    )

    result = analyzer.analyze("ENT_A", analysis_context)

    assert result.status == "inconclusive"
    assert result.score is None
    assert result.confidence == 0.0
    assert "single prompt had no answer" in result.rationale


def test_single_prompt_analyzer_propagates_main_core_infrastructure_errors(
    analysis_context: AlphaAnalysisContext,
) -> None:
    analyzer = SinglePromptAnalyzer(
        RecordingReasonerPort(error=MainCoreError("reasoner unavailable")),
    )

    with pytest.raises(MainCoreError, match="reasoner unavailable"):
        analyzer.analyze("ENT_A", analysis_context)


def test_single_prompt_analyzer_does_not_reapply_feature_multipliers(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort()
    analyzer = SinglePromptAnalyzer(port)

    analyzer.analyze("ENT_A", analysis_context)

    _, observed_context = port.calls[0]
    assert observed_context.feature_bundle.feature_values["momentum"] == EXPECTED_FEATURE_MOMENTUM
    assert (
        observed_context.feature_bundle.feature_weight_multiplier["momentum"]
        == EXPECTED_FEATURE_MULTIPLIER
    )


def test_single_prompt_analyzer_rejects_feature_bundle_cycle_mismatch(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort()
    analyzer = SinglePromptAnalyzer(port)
    mismatched = analysis_context.model_copy(
        update={
            "feature_bundle": analysis_context.feature_bundle.model_copy(
                update={"cycle_id": "cycle_other"},
            ),
        },
    )

    with pytest.raises(AlphaAnalyzerError, match="feature_bundle.cycle_id"):
        analyzer.analyze("ENT_A", mismatched)

    assert port.calls == []


def test_single_prompt_analyzer_rejects_world_state_cycle_mismatch(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort()
    analyzer = SinglePromptAnalyzer(port)
    mismatched_world = analysis_context.world_state.model_copy(
        update={"cycle_id": "cycle_other"},
    )
    mismatched = analysis_context.model_copy(update={"world_state": mismatched_world})

    with pytest.raises(AlphaAnalyzerError, match="world_state.cycle_id"):
        analyzer.analyze("ENT_A", mismatched)

    assert port.calls == []


def test_single_prompt_analyzer_rejects_feature_bundle_entity_mismatch(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingReasonerPort()
    analyzer = SinglePromptAnalyzer(port)
    mismatched_bundle = analysis_context.feature_bundle.model_copy(
        update={"entity_id": "ENT_OTHER"},
    )
    mismatched = analysis_context.model_copy(update={"feature_bundle": mismatched_bundle})

    with pytest.raises(AlphaAnalyzerError, match="feature_bundle.entity_id"):
        analyzer.analyze("ENT_A", mismatched)

    assert port.calls == []
