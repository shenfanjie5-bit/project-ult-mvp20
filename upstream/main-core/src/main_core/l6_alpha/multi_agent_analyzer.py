"""Opt-in multi-agent alpha analyzer for L6 A/B evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import fsum, isfinite
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, runtime_checkable

from main_core.common.contexts import (
    AlphaAnalysisContext,
    validate_alpha_analysis_context,
)
from main_core.common.errors import AlphaAnalyzerError, InconclusiveError, MainCoreError
from main_core.common.protocols import AnalyzerBase
from main_core.common.schemas import AlphaResultSnapshot
from main_core.common.types import EntityId

DEFAULT_MULTI_AGENT_ROLES: tuple[str, ...] = ("fundamental", "technical", "risk")


@dataclass(frozen=True)
class AgentRoleConfig:
    """Configuration for one deterministic multi-agent role."""

    name: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("agent role name must be non-empty")
        if not isfinite(self.weight) or self.weight <= 0.0:
            raise ValueError("agent role weight must be finite and > 0")


@dataclass(frozen=True)
class MultiAgentRoleResult:
    """Raw result emitted by one role before multi-agent aggregation."""

    role: str
    score: float | None
    confidence: float
    rationale: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    task_failed: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("role result role must be non-empty")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("role result confidence must be finite and within 0.0..1.0")
        if not self.task_failed and (
            self.score is None or not isfinite(self.score)
        ):
            raise ValueError("successful role result score must be finite")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@runtime_checkable
class MultiAgentReasonerPort(Protocol):
    """Role-scoped L6 reasoner boundary for multi-agent analysis."""

    def analyze_role(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
        role: AgentRoleConfig,
        payload: Mapping[str, Any],
    ) -> MultiAgentRoleResult:
        """Analyze one entity from one role using the prepared context payload."""


@dataclass
class StaticMultiAgentReasonerPort:
    """Deterministic multi-agent reasoner fake for local A/B runs and tests."""

    role_results: Mapping[str, MultiAgentRoleResult] = field(default_factory=dict)
    calls: list[tuple[EntityId, AlphaAnalysisContext, AgentRoleConfig, Mapping[str, Any]]] = (
        field(default_factory=list)
    )

    def analyze_role(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
        role: AgentRoleConfig,
        payload: Mapping[str, Any],
    ) -> MultiAgentRoleResult:
        """Return a configured role result or a stable zero-score default."""

        self.calls.append((entity_id, context, role, payload))
        if role.name in self.role_results:
            return self.role_results[role.name]

        return MultiAgentRoleResult(
            role=role.name,
            score=0.0,
            confidence=0.0,
            rationale=f"static {role.name} alpha analysis",
            evidence={"role": role.name},
        )


def build_multi_agent_input_payload(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
) -> dict[str, Any]:
    """Build the structured role input without provider prompt construction."""

    return {
        "cycle_id": context.cycle_id,
        "entity_id": entity_id,
        "feature_values": _plain_value(context.feature_bundle.feature_values),
        "signal_values": _plain_value(context.feature_bundle.signal_values),
        "graph_features": _plain_value(context.feature_bundle.graph_features),
        "world_state": {
            "final_regime": context.world_state.final_regime,
            "llm_delta": context.world_state.llm_delta,
        },
        "similar_cases": _plain_value(context.similar_cases),
    }


def aggregate_role_results(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
    role_results: Sequence[MultiAgentRoleResult],
    *,
    roles: Sequence[AgentRoleConfig],
) -> AlphaResultSnapshot:
    """Aggregate role-level outputs into one formal multi-agent alpha result."""

    role_weight_map = _role_weight_map(roles)
    result_map = _role_result_map(role_results, role_weight_map)
    failed_results = tuple(result for result in result_map.values() if result.task_failed)
    healthy_results = tuple(
        sorted(
            (result for result in result_map.values() if not result.task_failed),
            key=lambda result: result.role,
        )
    )

    if not healthy_results:
        return _multi_agent_result(
            entity_id,
            context,
            {
                "score": None,
                "confidence": 0.0,
                "rationale": _all_failed_rationale(failed_results, roles),
                "status": "inconclusive",
            },
        )

    total_weight = fsum(role_weight_map[result.role] for result in healthy_results)
    weighted_score = fsum(
        result.score * role_weight_map[result.role]
        for result in healthy_results
        if result.score is not None
    ) / total_weight
    weighted_confidence = fsum(
        result.confidence * role_weight_map[result.role] for result in healthy_results
    ) / total_weight

    return _multi_agent_result(
        entity_id,
        context,
        {
            "score": weighted_score,
            "confidence": weighted_confidence,
            "rationale": _aggregate_rationale(healthy_results, failed_results),
            "status": "ok",
        },
    )


class MultiAgentAnalyzer(AnalyzerBase):
    """Explicit opt-in multi-agent analyzer for phase 4 parity evaluation."""

    analyzer_type: ClassVar[str] = "multi_agent_v1"

    def __init__(
        self,
        reasoner_port: MultiAgentReasonerPort | None = None,
        *,
        roles: Sequence[AgentRoleConfig] | None = None,
    ) -> None:
        self._reasoner_port = reasoner_port or StaticMultiAgentReasonerPort()
        self._roles = tuple(
            roles
            if roles is not None
            else tuple(AgentRoleConfig(name) for name in DEFAULT_MULTI_AGENT_ROLES)
        )
        _role_weight_map(self._roles)

    def analyze(
        self,
        entity_id: EntityId,
        context: AlphaAnalysisContext,
    ) -> AlphaResultSnapshot:
        """Analyze one entity by invoking each configured role exactly once."""

        validate_alpha_analysis_context(entity_id, context)

        payload = build_multi_agent_input_payload(entity_id, context)
        role_results: list[MultiAgentRoleResult] = []
        for role in self._roles:
            try:
                result = self._reasoner_port.analyze_role(
                    entity_id,
                    context,
                    role,
                    payload,
                )
            except InconclusiveError as exc:
                result = MultiAgentRoleResult(
                    role=role.name,
                    score=None,
                    confidence=0.0,
                    rationale="role task failed",
                    task_failed=True,
                    failure_reason=str(exc),
                )
            except MainCoreError:
                raise
            role_results.append(result)

        return aggregate_role_results(
            entity_id,
            context,
            role_results,
            roles=self._roles,
        )


def _multi_agent_result(
    entity_id: EntityId,
    context: AlphaAnalysisContext,
    fields: Mapping[str, Any],
) -> AlphaResultSnapshot:
    return AlphaResultSnapshot(
        cycle_id=context.cycle_id,
        entity_id=entity_id,
        analyzer_type="multi_agent_v1",
        score=fields["score"],
        confidence=fields["confidence"],
        rationale=fields["rationale"],
        similar_cases=[dict(case) for case in context.similar_cases],
        status=fields["status"],
    )


def _role_weight_map(roles: Sequence[AgentRoleConfig]) -> dict[str, float]:
    if not roles:
        raise AlphaAnalyzerError("at least one multi-agent role is required")

    role_weight_map: dict[str, float] = {}
    for role in roles:
        if role.name in role_weight_map:
            raise AlphaAnalyzerError(f"duplicate multi-agent role: {role.name}")
        role_weight_map[role.name] = role.weight
    return role_weight_map


def _role_result_map(
    role_results: Sequence[MultiAgentRoleResult],
    role_weight_map: Mapping[str, float],
) -> dict[str, MultiAgentRoleResult]:
    result_map: dict[str, MultiAgentRoleResult] = {}
    for result in role_results:
        if result.role not in role_weight_map:
            raise AlphaAnalyzerError(f"role result is not configured: {result.role}")
        if result.role in result_map:
            raise AlphaAnalyzerError(f"duplicate role result: {result.role}")
        result_map[result.role] = result
    return result_map


def _aggregate_rationale(
    healthy_results: Sequence[MultiAgentRoleResult],
    failed_results: Sequence[MultiAgentRoleResult],
) -> str:
    role_summaries = [
        (
            f"{result.role}: score={result.score}, confidence={result.confidence}; "
            f"{result.rationale}"
        )
        for result in healthy_results
    ]
    failure_summaries = [
        f"{result.role} failed: {result.failure_reason or result.rationale}"
        for result in sorted(failed_results, key=lambda result: result.role)
    ]
    return "multi-agent aggregation: " + "; ".join(role_summaries + failure_summaries)


def _all_failed_rationale(
    failed_results: Sequence[MultiAgentRoleResult],
    roles: Sequence[AgentRoleConfig],
) -> str:
    if failed_results:
        failures = "; ".join(
            f"{result.role}: {result.failure_reason or result.rationale}"
            for result in sorted(failed_results, key=lambda result: result.role)
        )
    else:
        role_names = ", ".join(sorted(role.name for role in roles))
        failures = f"no successful role results for roles: {role_names}"
    return f"inconclusive: all multi-agent roles failed: {failures}"


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_value(item) for item in value]
    if isinstance(value, frozenset | set):
        return sorted(_plain_value(item) for item in value)
    return value


__all__ = [
    "AgentRoleConfig",
    "MultiAgentAnalyzer",
    "MultiAgentReasonerPort",
    "MultiAgentRoleResult",
    "StaticMultiAgentReasonerPort",
    "aggregate_role_results",
    "build_multi_agent_input_payload",
]
