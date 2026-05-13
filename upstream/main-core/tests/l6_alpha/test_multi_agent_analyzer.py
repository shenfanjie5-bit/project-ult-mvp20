"""Tests for the explicit opt-in multi-agent L6 analyzer."""

from __future__ import annotations

from collections.abc import Mapping
from math import inf, nan

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.errors import InconclusiveError, MainCoreError
from main_core.common.schemas import AlphaResultSnapshot
from main_core.l6_alpha import (
    AgentRoleConfig,
    MultiAgentAnalyzer,
    MultiAgentReasonerPort,
    MultiAgentRoleResult,
    StaticMultiAgentReasonerPort,
    analyze_stock,
)
from main_core.l6_alpha.multi_agent_analyzer import aggregate_role_results
from main_core.l6_alpha.single_prompt_analyzer import AlphaAnalyzerError

EXPECTED_WEIGHTED_CONFIDENCE = 0.75
EXPECTED_WEIGHTED_SCORE = 0.6
HEALTHY_ONLY_SCORE = 0.8


class RecordingMultiAgentPort:
    def __init__(
        self,
        results: Mapping[str, MultiAgentRoleResult] | None = None,
        errors: Mapping[str, BaseException] | None = None,
    ) -> None:
        self.results = dict(results or {})
        self.errors = dict(errors or {})
        self.calls: list[tuple[object, AlphaAnalysisContext, AgentRoleConfig, Mapping]] = []

    def analyze_role(
        self,
        entity_id: object,
        context: AlphaAnalysisContext,
        role: AgentRoleConfig,
        payload: Mapping,
    ) -> MultiAgentRoleResult:
        self.calls.append((entity_id, context, role, payload))
        if role.name in self.errors:
            raise self.errors[role.name]
        if role.name in self.results:
            return self.results[role.name]
        return MultiAgentRoleResult(
            role=role.name,
            score=0.5,
            confidence=0.6,
            rationale=f"{role.name} default",
        )


def test_agent_role_config_validates_name_and_weight() -> None:
    with pytest.raises(ValueError, match="name"):
        AgentRoleConfig(" ")
    with pytest.raises(ValueError, match="weight"):
        AgentRoleConfig("risk", 0.0)
    with pytest.raises(ValueError, match="weight"):
        AgentRoleConfig("risk", inf)


def test_multi_agent_role_result_validates_success_fields() -> None:
    with pytest.raises(ValueError, match="confidence"):
        MultiAgentRoleResult("risk", 0.5, 1.1, "too confident")
    with pytest.raises(ValueError, match="score"):
        MultiAgentRoleResult("risk", None, 0.5, "missing score")
    with pytest.raises(ValueError, match="score"):
        MultiAgentRoleResult("risk", nan, 0.5, "nan score")


def test_static_multi_agent_port_matches_runtime_protocol() -> None:
    assert isinstance(StaticMultiAgentReasonerPort(), MultiAgentReasonerPort)


def test_multi_agent_analyzer_happy_path_returns_formal_result(
    analysis_context: AlphaAnalysisContext,
) -> None:
    roles = (AgentRoleConfig("fundamental", 2.0), AgentRoleConfig("technical", 1.0))
    port = RecordingMultiAgentPort(
        {
            "fundamental": MultiAgentRoleResult(
                "fundamental",
                0.7,
                0.8,
                "fundamental case is strong",
                evidence={"metric": "quality"},
            ),
            "technical": MultiAgentRoleResult(
                "technical",
                0.4,
                0.65,
                "technical case is mixed",
            ),
        }
    )
    analyzer = MultiAgentAnalyzer(port, roles=roles)

    result = analyzer.analyze("ENT_A", analysis_context)

    assert isinstance(result, AlphaResultSnapshot)
    assert result.analyzer_type == "multi_agent_v1"
    assert result.status == "ok"
    assert result.score == pytest.approx(EXPECTED_WEIGHTED_SCORE)
    assert result.confidence == pytest.approx(EXPECTED_WEIGHTED_CONFIDENCE)
    assert "fundamental case is strong" in result.rationale
    assert "technical case is mixed" in result.rationale
    assert [call[2].name for call in port.calls] == ["fundamental", "technical"]


def test_multi_agent_analyzer_rejects_entity_mismatch_without_calling_port(
    analysis_context: AlphaAnalysisContext,
) -> None:
    port = RecordingMultiAgentPort()
    analyzer = MultiAgentAnalyzer(port)

    with pytest.raises(AlphaAnalyzerError, match="context.entity_id"):
        analyzer.analyze("ENT_OTHER", analysis_context)

    assert port.calls == []


def test_aggregate_role_results_is_stable_when_role_order_changes(
    analysis_context: AlphaAnalysisContext,
) -> None:
    roles = (AgentRoleConfig("technical", 1.0), AgentRoleConfig("fundamental", 2.0))
    reversed_roles = tuple(reversed(roles))
    role_results = (
        MultiAgentRoleResult("fundamental", 0.7, 0.8, "fundamental"),
        MultiAgentRoleResult("technical", 0.4, 0.65, "technical"),
    )
    reversed_results = tuple(reversed(role_results))

    result = aggregate_role_results("ENT_A", analysis_context, role_results, roles=roles)
    reversed_result = aggregate_role_results(
        "ENT_A",
        analysis_context,
        reversed_results,
        roles=reversed_roles,
    )

    assert reversed_result.score == result.score
    assert reversed_result.confidence == result.confidence
    assert reversed_result.rationale == result.rationale


def test_single_role_task_failure_keeps_ok_result_and_records_reason(
    analysis_context: AlphaAnalysisContext,
) -> None:
    roles = (AgentRoleConfig("fundamental"), AgentRoleConfig("risk"))
    analyzer = MultiAgentAnalyzer(
        RecordingMultiAgentPort(
            {
                "fundamental": MultiAgentRoleResult(
                    "fundamental",
                    0.8,
                    0.7,
                    "healthy role",
                ),
                "risk": MultiAgentRoleResult(
                    "risk",
                    None,
                    0.0,
                    "risk task failed",
                    task_failed=True,
                    failure_reason="risk provider timeout",
                ),
            }
        ),
        roles=roles,
    )

    result = analyzer.analyze("ENT_A", analysis_context)

    assert result.status == "ok"
    assert result.score == HEALTHY_ONLY_SCORE
    assert "risk failed: risk provider timeout" in result.rationale


def test_inconclusive_role_error_is_downgraded_to_role_failure(
    analysis_context: AlphaAnalysisContext,
) -> None:
    roles = (AgentRoleConfig("fundamental"), AgentRoleConfig("risk"))
    analyzer = MultiAgentAnalyzer(
        RecordingMultiAgentPort(errors={"risk": InconclusiveError("risk had no answer")}),
        roles=roles,
    )

    result = analyzer.analyze("ENT_A", analysis_context)

    assert result.status == "ok"
    assert "risk failed: risk had no answer" in result.rationale


def test_all_role_task_failures_return_multi_agent_inconclusive(
    analysis_context: AlphaAnalysisContext,
) -> None:
    roles = (AgentRoleConfig("fundamental"), AgentRoleConfig("risk"))
    analyzer = MultiAgentAnalyzer(
        RecordingMultiAgentPort(
            {
                "fundamental": MultiAgentRoleResult(
                    "fundamental",
                    None,
                    0.0,
                    "fundamental failed",
                    task_failed=True,
                    failure_reason="no data",
                ),
                "risk": MultiAgentRoleResult(
                    "risk",
                    None,
                    0.0,
                    "risk failed",
                    task_failed=True,
                    failure_reason="timeout",
                ),
            }
        ),
        roles=roles,
    )

    result = analyzer.analyze("ENT_A", analysis_context)

    assert result.analyzer_type == "multi_agent_v1"
    assert result.status == "inconclusive"
    assert result.score is None
    assert result.confidence == 0.0
    assert "fundamental: no data" in result.rationale
    assert "risk: timeout" in result.rationale


def test_main_core_error_from_role_hard_stops_without_fallback(
    analysis_context: AlphaAnalysisContext,
) -> None:
    analyzer = MultiAgentAnalyzer(
        RecordingMultiAgentPort(errors={"fundamental": MainCoreError("reasoner down")}),
        roles=(AgentRoleConfig("fundamental"),),
    )

    with pytest.raises(MainCoreError, match="reasoner down"):
        analyzer.analyze("ENT_A", analysis_context)


def test_default_analyze_stock_stays_single_prompt_without_explicit_analyzer(
    analysis_context: AlphaAnalysisContext,
) -> None:
    default_result = analyze_stock("ENT_A", analysis_context)
    explicit_result = analyze_stock(
        "ENT_A",
        analysis_context,
        analyzer=MultiAgentAnalyzer(roles=(AgentRoleConfig("fundamental"),)),
    )

    assert default_result.analyzer_type == "single_prompt_v1"
    assert explicit_result.analyzer_type == "multi_agent_v1"
