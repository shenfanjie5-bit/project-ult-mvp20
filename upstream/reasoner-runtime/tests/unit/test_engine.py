from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import (
    ReasonerRequest,
    StructuredGenerationResult,
    generate_structured,
)
from reasoner_runtime.core.engine import _normalize_request


class _TestSchema(BaseModel):
    answer: str


class _FakeCompletions:
    def __init__(self, answer: str = "ok") -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def create_with_completion(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return (
            _TestSchema(answer=self.answer),
            SimpleNamespace(
                choices=[{"message": {"content": f'{{"answer":"{self.answer}"}}'}}],
                token_usage={"prompt": 1, "completion": 2, "total": 3},
                cost_estimate=0.01,
                latency_ms=4,
            ),
        )


def _client_factory(
    calls: list[tuple[ProviderProfile, int]] | None = None,
) -> Callable[[ProviderProfile, int], Any]:
    def factory(profile: ProviderProfile, max_retries: int) -> Any:
        if calls is not None:
            calls.append((profile, max_retries))
        return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))

    return factory


def _schema_registry() -> dict[str, type[BaseModel]]:
    return {"TestSchema": _TestSchema}


def _request(**overrides: object) -> ReasonerRequest:
    payload = {
        "request_id": "req-1",
        "caller_module": "test",
        "target_schema": "TestSchema",
        "messages": [{"role": "user", "content": "hello"}],
        "configured_provider": "openai",
        "configured_model": "gpt-4",
        "max_retries": 2,
    }
    payload.update(overrides)
    return ReasonerRequest(**payload)


def test_generate_structured_returns_structured_generation_result() -> None:
    result = generate_structured(
        _request(),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
    )

    assert isinstance(result, StructuredGenerationResult)


def test_generate_structured_uses_configured_target_in_result() -> None:
    result = generate_structured(
        _request(configured_provider="anthropic", configured_model="claude-sonnet-4.5"),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
    )

    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"


def test_generate_structured_result_uses_structured_call_payload() -> None:
    result = generate_structured(
        _request(),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
    )

    assert result.parsed_result == {"answer": "ok"}
    assert result.token_usage == {"prompt": 1, "completion": 2, "total": 3}
    assert result.cost_estimate == 0.01
    assert result.latency_ms == 4


def test_generate_structured_routes_selected_provider_to_client_factory() -> None:
    fallback_profile = ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=0,
    )
    configured_profile = ProviderProfile(
        provider="openai",
        model="gpt-5.4",
        fallback_priority=1,
    )
    client_calls: list[tuple[ProviderProfile, int]] = []

    result = generate_structured(
        _request(
            configured_provider="missing",
            configured_model="missing-model",
            max_retries=3,
        ),
        schema_registry=_schema_registry(),
        provider_profiles=[configured_profile, fallback_profile],
        client_factory=_client_factory(client_calls),
    )

    assert client_calls == [(fallback_profile, 1)]
    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"
    assert result.fallback_path == ["anthropic/claude-sonnet-4.5"]


def test_generate_structured_loads_provider_profiles_from_config_path(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(
        """
providers:
  - provider: openai
    model: gpt-5.4
    fallback_priority: 1
  - provider: anthropic
    model: claude-sonnet-4.5
    fallback_priority: 0
""",
        encoding="utf-8",
    )
    client_calls: list[tuple[ProviderProfile, int]] = []

    result = generate_structured(
        _request(
            configured_provider="openai",
            configured_model="gpt-5.4",
            max_retries=1,
        ),
        schema_registry=_schema_registry(),
        provider_config_path=config_path,
        client_factory=_client_factory(client_calls),
    )

    assert client_calls == [
        (ProviderProfile(provider="openai", model="gpt-5.4", fallback_priority=1), 1)
    ]
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-5.4"


def test_normalize_request_preserves_existing_request_id() -> None:
    request = _request(request_id="req-stable")

    normalized = _normalize_request(request)

    assert normalized is request
    assert normalized.request_id == "req-stable"


def test_normalize_request_generates_uuid_for_empty_request_id() -> None:
    request = _request(request_id="")

    normalized = _normalize_request(request)

    assert normalized.request_id
    UUID(normalized.request_id)


def test_normalize_request_rejects_negative_max_retries() -> None:
    request = ReasonerRequest.model_construct(
        request_id="req-1",
        caller_module="test",
        target_schema="TestSchema",
        messages=[],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=-1,
        metadata={},
    )

    with pytest.raises(ValueError, match="max_retries"):
        _normalize_request(request)


@pytest.mark.parametrize(
    "field_name",
    ["caller_module", "target_schema", "configured_provider", "configured_model"],
)
def test_normalize_request_rejects_empty_required_text_fields(field_name: str) -> None:
    request = _request(**{field_name: "  "})

    with pytest.raises(ValueError, match=field_name):
        _normalize_request(request)


def test_normalize_request_rejects_non_reasoner_request() -> None:
    with pytest.raises(TypeError, match="ReasonerRequest"):
        _normalize_request(object())  # type: ignore[arg-type]
