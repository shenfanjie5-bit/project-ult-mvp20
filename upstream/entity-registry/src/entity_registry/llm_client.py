"""reasoner-runtime disambiguation client contracts."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from entity_registry.core import validate_entity_id
from entity_registry.fuzzy import FuzzyCandidate
from entity_registry.resolution_types import ResolutionContext


_DISAMBIGUATION_INSTRUCTIONS = (
    "Select one canonical entity only when the mention context clearly identifies "
    "a candidate. Return selected_entity_id as null when the evidence is ambiguous "
    "or insufficient."
)


class LLMDisambiguationCandidate(BaseModel):
    """One candidate supplied to reasoner-runtime for disambiguation."""

    canonical_entity_id: str
    display_name: str | None = None
    alias_text: str | None = None
    alias_type: str | None = None
    score: float | None = None
    source: str

    @field_validator("canonical_entity_id")
    @classmethod
    def validate_canonical_entity_id(cls, value: str) -> str:
        if not validate_entity_id(value):
            raise ValueError("canonical_entity_id must use the ENT_* namespace")
        return value

    @field_validator("display_name", "alias_text", "alias_type", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        return cleaned or None

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source must not be empty")
        return cleaned

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError("score must be finite and between 0.0 and 1.0")
        return value


class LLMDisambiguationRequest(BaseModel):
    """Structured disambiguation request sent to reasoner-runtime."""

    raw_mention_text: str
    source_context: dict[str, object]
    candidates: list[LLMDisambiguationCandidate]
    instructions: str

    @field_validator("raw_mention_text", "instructions")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text fields must not be empty")
        return cleaned


class LLMDisambiguationResponse(BaseModel):
    """Structured disambiguation response returned by reasoner-runtime."""

    selected_entity_id: str | None
    confidence: float | None
    rationale: str
    raw_response: dict[str, object] | None = None

    @field_validator("selected_entity_id")
    @classmethod
    def validate_selected_entity_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not validate_entity_id(value):
            raise ValueError("selected_entity_id must use the ENT_* namespace")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError("confidence must be finite and between 0.0 and 1.0")
        return value

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("rationale must not be empty")
        return cleaned

    @model_validator(mode="after")
    def validate_selected_candidate(
        self,
        info: ValidationInfo,
    ) -> LLMDisambiguationResponse:
        candidate_ids = _candidate_ids_from_context(info.context)
        if candidate_ids is None:
            return self
        _validate_response_selection(self, candidate_ids)
        return self


class ReasonerRuntimeClient(Protocol):
    """Runtime contract for LLM-assisted entity disambiguation."""

    def disambiguate(
        self,
        request: LLMDisambiguationRequest,
    ) -> LLMDisambiguationResponse: ...


class CallableReasonerRuntimeClient:
    """Adapter around an injected structured reasoner-runtime callable."""

    def __init__(
        self,
        invoke: Callable[
            [dict[str, object]],
            dict[str, object] | LLMDisambiguationResponse,
        ],
    ) -> None:
        self._invoke = invoke

    def disambiguate(
        self,
        request: LLMDisambiguationRequest,
    ) -> LLMDisambiguationResponse:
        payload = request.model_dump(mode="json")
        response = self._invoke(payload)
        candidate_ids = [candidate.canonical_entity_id for candidate in request.candidates]

        if isinstance(response, LLMDisambiguationResponse):
            _validate_response_selection(response, candidate_ids)
            return response
        if not isinstance(response, dict):
            raise TypeError("reasoner-runtime callable must return a dict or response model")

        normalized = dict(response)
        normalized.setdefault("raw_response", dict(response))
        return LLMDisambiguationResponse.model_validate(
            normalized,
            context={"candidate_entity_ids": candidate_ids},
        )


def build_disambiguation_request(
    raw_mention_text: str,
    context: ResolutionContext | dict[str, object] | None,
    candidates: list[FuzzyCandidate] | list[LLMDisambiguationCandidate],
) -> LLMDisambiguationRequest:
    """Build a structured request from collected mention candidates."""

    llm_candidates: list[LLMDisambiguationCandidate] = []
    for candidate in candidates:
        if isinstance(candidate, LLMDisambiguationCandidate):
            llm_candidates.append(candidate)
            continue
        llm_candidates.append(_candidate_from_fuzzy(candidate))

    return LLMDisambiguationRequest(
        raw_mention_text=raw_mention_text,
        source_context=_source_context_from(context),
        candidates=llm_candidates,
        instructions=_DISAMBIGUATION_INSTRUCTIONS,
    )


def _candidate_from_fuzzy(candidate: FuzzyCandidate) -> LLMDisambiguationCandidate:
    return LLMDisambiguationCandidate(
        canonical_entity_id=candidate.canonical_entity_id,
        display_name=None,
        alias_text=candidate.alias_text,
        alias_type=_text_value(candidate.alias_type),
        score=candidate.score,
        source=candidate.source,
    )


def _source_context_from(
    context: ResolutionContext | dict[str, object] | None,
) -> dict[str, object]:
    if context is None:
        return {}
    if isinstance(context, ResolutionContext):
        return context.model_dump(mode="json")
    if isinstance(context, dict):
        return dict(context)
    raise TypeError("context must be a ResolutionContext, dict, or None")


def _text_value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _candidate_ids_from_context(context: object) -> set[str] | None:
    if not isinstance(context, dict):
        return None
    candidate_ids = context.get("candidate_entity_ids")
    if candidate_ids is None:
        return None
    return {str(candidate_id) for candidate_id in candidate_ids}


def _validate_response_selection(
    response: LLMDisambiguationResponse,
    candidate_ids: set[str] | list[str],
) -> None:
    if response.selected_entity_id is None:
        return
    if response.selected_entity_id not in set(candidate_ids):
        raise ValueError("selected_entity_id must be one of the request candidates")


__all__ = [
    "CallableReasonerRuntimeClient",
    "LLMDisambiguationCandidate",
    "LLMDisambiguationRequest",
    "LLMDisambiguationResponse",
    "ReasonerRuntimeClient",
    "build_disambiguation_request",
]
