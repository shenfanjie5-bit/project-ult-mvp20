from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import entity_registry
from entity_registry.core import AliasType
from entity_registry.fuzzy import FuzzyCandidate
from entity_registry.llm_client import (
    CallableReasonerRuntimeClient,
    LLMDisambiguationCandidate,
    LLMDisambiguationRequest,
    LLMDisambiguationResponse,
    ReasonerRuntimeClient,
    build_disambiguation_request,
)
from entity_registry.resolution_types import ResolutionContext


def make_llm_candidate(
    entity_id: str = "ENT_STOCK_600519.SH",
    *,
    score: float | None = 0.92,
    source: str = "unit-test",
) -> LLMDisambiguationCandidate:
    return LLMDisambiguationCandidate(
        canonical_entity_id=entity_id,
        display_name="贵州茅台",
        alias_text="贵州茅台股份",
        alias_type="short_name",
        score=score,
        source=source,
    )


def test_package_exports_reasoner_runtime_types() -> None:
    assert entity_registry.ReasonerRuntimeClient is ReasonerRuntimeClient
    assert entity_registry.CallableReasonerRuntimeClient is CallableReasonerRuntimeClient
    assert entity_registry.LLMDisambiguationRequest is LLMDisambiguationRequest
    assert entity_registry.LLMDisambiguationResponse is LLMDisambiguationResponse


def test_callable_reasoner_client_normalizes_dict_response() -> None:
    calls: list[dict[str, object]] = []

    def invoke(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {
            "selected_entity_id": "ENT_STOCK_600519.SH",
            "confidence": 0.91,
            "rationale": "context names the mainland listing",
        }

    request = build_disambiguation_request(
        "贵州茅台股份",
        {"document_id": "doc-1"},
        [make_llm_candidate()],
    )
    response = CallableReasonerRuntimeClient(invoke).disambiguate(request)

    assert calls[0]["raw_mention_text"] == "贵州茅台股份"
    assert calls[0]["source_context"] == {"document_id": "doc-1"}
    assert response == LLMDisambiguationResponse(
        selected_entity_id="ENT_STOCK_600519.SH",
        confidence=0.91,
        rationale="context names the mainland listing",
        raw_response={
            "selected_entity_id": "ENT_STOCK_600519.SH",
            "confidence": 0.91,
            "rationale": "context names the mainland listing",
        },
    )


def test_callable_reasoner_client_accepts_response_model() -> None:
    response = LLMDisambiguationResponse(
        selected_entity_id="ENT_STOCK_600519.SH",
        confidence=0.95,
        rationale="clear match",
    )
    client = CallableReasonerRuntimeClient(lambda payload: response)

    assert client.disambiguate(
        build_disambiguation_request("贵州茅台股份", None, [make_llm_candidate()])
    ) is response


def test_llm_response_rejects_invalid_candidate_selection() -> None:
    with pytest.raises(ValidationError, match="request candidates"):
        LLMDisambiguationResponse.model_validate(
            {
                "selected_entity_id": "ENT_STOCK_000001.SZ",
                "confidence": 0.9,
                "rationale": "wrong candidate",
            },
            context={"candidate_entity_ids": ["ENT_STOCK_600519.SH"]},
        )


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("inf"), float("nan")])
def test_llm_response_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError, match="confidence"):
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_600519.SH",
            confidence=confidence,
            rationale="bad confidence",
        )


def test_llm_response_rejects_empty_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        LLMDisambiguationResponse(
            selected_entity_id=None,
            confidence=None,
            rationale=" ",
        )


def test_build_disambiguation_request_preserves_fuzzy_candidate_order_and_context() -> None:
    candidates = [
        FuzzyCandidate(
            canonical_entity_id="ENT_STOCK_600519.SH",
            alias_text="贵州茅台股份",
            alias_type=AliasType.SHORT_NAME,
            score=0.91,
            source="splink",
        ),
        FuzzyCandidate(
            canonical_entity_id="ENT_STOCK_300750.SZ",
            alias_text="宁德时代新能源",
            alias_type=AliasType.FULL_NAME,
            score=0.88,
            source="splink",
        ),
    ]
    context = ResolutionContext(
        raw_mention_text="公告提到贵州茅台股份",
        document_context="公告提到贵州茅台股份",
        source_type="announcement",
        timestamp=datetime(2026, 1, 2, tzinfo=UTC),
    )

    request = build_disambiguation_request("贵州茅台股份", context, candidates)

    assert request.raw_mention_text == "贵州茅台股份"
    assert request.source_context["source_type"] == "announcement"
    assert request.source_context["timestamp"] == "2026-01-02T00:00:00Z"
    assert [candidate.canonical_entity_id for candidate in request.candidates] == [
        "ENT_STOCK_600519.SH",
        "ENT_STOCK_300750.SZ",
    ]
    assert request.candidates[0].alias_text == "贵州茅台股份"
    assert request.candidates[0].alias_type == "short_name"
    assert request.candidates[0].score == 0.91
    assert request.candidates[0].source == "splink"


def test_llm_client_module_has_no_provider_or_local_resilience_imports() -> None:
    text = Path("src/entity_registry/llm_client.py").read_text(encoding="utf-8")
    lowered = text.lower()

    for forbidden in ("openai", "anthropic", "google.generativeai"):
        assert forbidden not in lowered
    for forbidden in ("tenacity", "backoff", "retry"):
        assert forbidden not in lowered
