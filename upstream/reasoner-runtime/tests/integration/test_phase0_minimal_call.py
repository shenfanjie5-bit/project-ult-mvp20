from __future__ import annotations

from typing import Any

from pydantic import BaseModel

import reasoner_runtime
from reasoner_runtime.structured import StructuredCallResult


class Phase0Payload(BaseModel):
    answer: str


def test_phase0_public_import_and_minimal_call_flow() -> None:
    request = reasoner_runtime.ReasonerRequest(
        request_id="req-phase0",
        caller_module="integration-test",
        target_schema="Phase0Payload",
        messages=[{"role": "user", "content": "hello"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )

    result = reasoner_runtime.generate_structured(
        request,
        provider_profiles=[
            reasoner_runtime.ProviderProfile(provider="openai", model="gpt-4")
        ],
        schema_registry={"Phase0Payload": Phase0Payload},
        client_factory=lambda _profile, _max_retries: _MinimalClient(),
    )

    assert result.parsed_result == {"answer": "ok"}
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.fallback_path == ["openai/gpt-4"]


class _MinimalClient:
    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        metadata: dict[str, Any],
    ) -> StructuredCallResult:
        assert metadata["reasoner"]["request_id"] == "req-phase0"
        return StructuredCallResult(
            parsed_result={"answer": "ok"},
            raw_output='{"answer":"ok"}',
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost_estimate=0.0,
            latency_ms=1,
        )
