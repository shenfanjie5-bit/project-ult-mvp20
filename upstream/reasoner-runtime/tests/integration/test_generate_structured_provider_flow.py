from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import ReasonerRequest, generate_structured


class ProviderFlowPayload(BaseModel):
    answer: str
    confidence: float


def test_generate_structured_uses_selected_profile_and_schema_registry() -> None:
    configured_profile = ProviderProfile(
        provider="openai",
        model="gpt-4",
        fallback_priority=5,
    )
    selected_fallback = ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=0,
    )
    request_messages = [{"role": "user", "content": "return a structured answer"}]
    request = ReasonerRequest(
        request_id="req-integration",
        caller_module="integration-test",
        target_schema="ProviderFlowPayload",
        messages=request_messages,
        configured_provider="missing",
        configured_model="missing-model",
        max_retries=3,
    )
    client_factory_calls: list[tuple[ProviderProfile, int]] = []
    completions = _FakeCompletions(
        (
            ProviderFlowPayload(answer="fallback-ok", confidence=0.75),
            SimpleNamespace(
                choices=[
                    {
                        "message": {
                            "content": '{"answer":"fallback-ok","confidence":0.75}'
                        }
                    }
                ],
                token_usage={"prompt": 9, "completion": 4, "total": 13},
                cost_estimate=0.02,
                latency_ms=41,
            ),
        )
    )

    def client_factory(profile: ProviderProfile, max_retries: int) -> Any:
        client_factory_calls.append((profile, max_retries))
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    result = generate_structured(
        request,
        schema_registry={"ProviderFlowPayload": ProviderFlowPayload},
        provider_profiles=[configured_profile, selected_fallback],
        client_factory=client_factory,
    )

    assert client_factory_calls == [(selected_fallback, 1)]
    assert completions.calls[0]["messages"] == request.messages
    assert completions.calls[0]["response_model"] is ProviderFlowPayload
    assert result.parsed_result == {"answer": "fallback-ok", "confidence": 0.75}
    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"
    assert result.fallback_path == ["anthropic/claude-sonnet-4.5"]
    assert result.token_usage == {"prompt": 9, "completion": 4, "total": 13}
    assert result.cost_estimate == 0.02
    assert result.latency_ms == 41


class _FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create_with_completion(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response
