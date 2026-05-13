from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import (
    ReasonerRequest,
    StructuredGenerationResult,
    generate_structured,
    generate_structured_with_replay,
)
from reasoner_runtime.replay import ReplayBundle, sha256_text
from reasoner_runtime.structured import StructuredCallResult


class ReplayPayload(BaseModel):
    answer: str
    score: int


def _request(messages: list[dict[str, Any]] | None = None) -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-replay",
        caller_module="integration-test",
        target_schema="ReplayPayload",
        messages=messages or [{"role": "user", "content": "return a replay payload"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
    )


def test_generate_structured_with_replay_returns_result_and_bundle() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    raw_output = ' \n{"score":7,"answer":"ok"}\n '
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 7},
        raw_output=raw_output,
        token_usage={"prompt": 3, "completion": 4, "total": 7},
        cost_estimate=0.02,
        latency_ms=11,
    )
    client = _FakeStructuredClient(call_result)
    client_factory_calls: list[tuple[ProviderProfile, int]] = []

    def client_factory(call_profile: ProviderProfile, max_retries: int) -> Any:
        client_factory_calls.append((call_profile, max_retries))
        return client

    result, bundle = generate_structured_with_replay(
        _request(),
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=client_factory,
    )

    assert isinstance(result, StructuredGenerationResult)
    assert isinstance(bundle, ReplayBundle)
    assert client_factory_calls == [(profile, 1)]
    assert client.calls[0]["response_model"] is ReplayPayload
    assert result.parsed_result == {"answer": "ok", "score": 7}
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.fallback_path == ["openai/gpt-4"]
    assert result.retry_count == 0
    assert bundle.raw_output == raw_output
    assert bundle.parsed_result == result.parsed_result
    assert bundle.output_hash == sha256_text(raw_output)
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert json.loads(bundle.sanitized_input) == {
        "messages": _request().messages,
        "metadata": {},
    }
    assert bundle.llm_lineage == {
        "provider": result.actual_provider,
        "model": result.actual_model,
        "configured_target": "openai/gpt-4",
        "failure_class": "none",
        "fallback_path": result.fallback_path,
        "retry_count": result.retry_count,
    }


def test_generate_structured_with_replay_hashes_provider_sanitized_messages() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    raw_output = '{"score":8,"answer":"ok"}'
    call_result = StructuredCallResult(
        parsed_result={"answer": "ok", "score": 8},
        raw_output=raw_output,
        token_usage={"prompt": 4, "completion": 4, "total": 8},
        cost_estimate=0.01,
        latency_ms=9,
    )
    client = _FakeStructuredClient(call_result)
    request = _request(
        [
            {
                "role": "user",
                "content": (
                    "name is Ada Lovelace, phone 415-555-2671, "
                    "account 123456789012"
                ),
            }
        ]
    )

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=lambda _profile, _max_retries: client,
    )

    sanitized_payload = json.loads(bundle.sanitized_input)
    serialized_client_payload = json.dumps(
        {"messages": client.calls[0]["messages"], "metadata": {}},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    sanitized_messages = sanitized_payload["messages"]
    assert client.calls[0]["messages"] == sanitized_messages
    assert serialized_client_payload == bundle.sanitized_input
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert "Ada Lovelace" not in bundle.sanitized_input
    assert "415-555-2671" not in bundle.sanitized_input
    assert "123456789012" not in bundle.sanitized_input
    assert sanitized_messages != request.messages


def test_generate_structured_with_replay_contract_keeps_request_identity() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok", "score": 9},
            raw_output='{"answer":"ok","score":9}',
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost_estimate=0.0,
            latency_ms=1,
        )
    )
    request = _request()

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[profile],
        schema_registry={"ReplayPayload": ReplayPayload},
        client_factory=lambda _profile, _max_retries: client,
    )

    contract = bundle.to_contract()
    contract_payload = contract.model_dump()
    assert contract.request.request_id == request.request_id
    assert contract.result.request_id == request.request_id
    for replay_field_name in ReplayBundle.replay_field_names:
        assert contract_payload[replay_field_name] == getattr(bundle, replay_field_name)


def test_generate_structured_keeps_structured_result_return_type() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok", "score": 1},
            raw_output='{"answer":"ok","score":1}',
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost_estimate=0.0,
            latency_ms=1,
        )
    )

    result = generate_structured(
        _request(),
        schema_registry={"ReplayPayload": ReplayPayload},
        provider_profiles=[profile],
        client_factory=lambda _profile, _max_retries: client,
    )

    assert isinstance(result, StructuredGenerationResult)


class _FakeStructuredClient:
    def __init__(self, result: StructuredCallResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> StructuredCallResult:
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
            }
        )
        return self.result
