"""Tests for the L6 alpha reasoner boundary port."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.l6_alpha import AlphaReasonerResponse, StaticAlphaReasonerPort


def test_alpha_reasoner_response_is_frozen_dataclass() -> None:
    response = AlphaReasonerResponse(
        score=0.8,
        confidence=0.7,
        rationale="fixture",
        similar_cases=[],
    )

    with pytest.raises(FrozenInstanceError):
        response.score = 0.1  # type: ignore[misc]


def test_static_alpha_reasoner_port_returns_configured_response(
    analysis_context: AlphaAnalysisContext,
) -> None:
    response = AlphaReasonerResponse(
        score=0.61,
        confidence=0.77,
        rationale="configured fake response",
        similar_cases=[{"entity_id": "ENT_X"}],
    )
    port = StaticAlphaReasonerPort(response)

    assert port.analyze_alpha("ENT_A", analysis_context) == response


def test_static_alpha_reasoner_port_default_uses_context_similar_cases(
    analysis_context: AlphaAnalysisContext,
) -> None:
    response = StaticAlphaReasonerPort().analyze_alpha("ENT_A", analysis_context)

    assert response.score == 0.0
    assert response.confidence == 0.0
    assert response.rationale == "static alpha analysis"
    assert response.similar_cases == [{"entity_id": "ENT_B", "score": 0.4}]
