from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from reasoner_runtime.callbacks import LangfuseCallbackBackend
from reasoner_runtime.callbacks import factory as callback_factory
from reasoner_runtime.config import CallbackProfile, ProviderProfile
from reasoner_runtime.core import ReasonerRequest, generate_structured_with_replay
from reasoner_runtime.providers import FallbackExecutionError
from reasoner_runtime.replay import sha256_text


class LangfusePayload(BaseModel):
    answer: str


@pytest.fixture(autouse=True)
def _clear_callback_factory_cache() -> Any:
    callback_factory._build_callback_backends_cached.cache_clear()
    yield
    callback_factory._build_callback_backends_cached.cache_clear()


def test_langfuse_callback_profile_enters_runtime_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    langfuse_client = _FakeLangfuseClient()
    seen_hosts: list[str | None] = []
    _install_langfuse_factory(monkeypatch, langfuse_client, seen_hosts)

    result, bundle = generate_structured_with_replay(
        _request("req-langfuse-profile"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_profile=CallbackProfile(
            backend="langfuse",
            enabled=True,
            endpoint="http://langfuse.local",
        ),
    )

    assert seen_hosts == ["http://langfuse.local"]
    assert result.parsed_result == {"answer": "ok"}
    assert [event["name"] for event in langfuse_client.events] == [
        "reasoner.llm.start",
        "reasoner.llm.success",
    ]
    assert langfuse_client.events[0]["trace_context"] == {
        "trace_id": hashlib.sha256(b"req-langfuse-profile").hexdigest()[:32]
    }
    success_metadata = langfuse_client.events[1]["metadata"]
    assert success_metadata["request_id"] == "req-langfuse-profile"
    assert success_metadata["provider"] == "openai"
    assert success_metadata["model"] == "gpt-4"
    assert success_metadata["token_usage"] == {
        "prompt": 5,
        "completion": 7,
        "total": 12,
    }
    assert success_metadata["cost_estimate"] == 0.03
    assert success_metadata["latency_ms"] == 22
    assert success_metadata["fallback_path"] == ["openai/gpt-4"]
    assert success_metadata["retry_count"] == 0
    assert success_metadata["failure_class"] == "none"
    assert _payload_keys().isdisjoint(success_metadata)
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert bundle.output_hash == sha256_text(bundle.raw_output)
    assert {
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    }.issubset(bundle.model_dump())


def test_langfuse_profile_and_direct_backend_emit_same_success_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_client = _FakeLangfuseClient()
    _install_langfuse_factory(monkeypatch, profile_client)
    profile_result, profile_bundle = generate_structured_with_replay(
        _request("req-langfuse-parity"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_profile=CallbackProfile(
            backend="langfuse",
            enabled=True,
            endpoint="http://langfuse.local",
        ),
    )

    direct_client = _FakeLangfuseClient()
    direct_result, direct_bundle = generate_structured_with_replay(
        _request("req-langfuse-parity"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_backends=[LangfuseCallbackBackend(client=direct_client)],
    )

    assert profile_result.model_dump().keys() == direct_result.model_dump().keys()
    assert profile_bundle.input_hash == direct_bundle.input_hash
    assert profile_bundle.output_hash == direct_bundle.output_hash
    assert profile_client.events == direct_client.events


def test_langfuse_profile_and_direct_backend_emit_same_error_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_client = _FakeLangfuseClient()
    _install_langfuse_factory(monkeypatch, profile_client)
    with pytest.raises(FallbackExecutionError):
        generate_structured_with_replay(
            _request("req-langfuse-error"),
            provider_profiles=[_profile()],
            schema_registry={"LangfusePayload": LangfusePayload},
            client_factory=lambda _profile, _max_retries: _FailingClient(),
            callback_profile=CallbackProfile(
                backend="langfuse",
                enabled=True,
                endpoint="http://langfuse.local",
            ),
        )

    direct_client = _FakeLangfuseClient()
    with pytest.raises(FallbackExecutionError):
        generate_structured_with_replay(
            _request("req-langfuse-error"),
            provider_profiles=[_profile()],
            schema_registry={"LangfusePayload": LangfusePayload},
            client_factory=lambda _profile, _max_retries: _FailingClient(),
            callback_backends=[LangfuseCallbackBackend(client=direct_client)],
        )

    assert _events_without_error_latency(profile_client.events) == (
        _events_without_error_latency(direct_client.events)
    )
    error_metadata = profile_client.events[1]["metadata"]
    assert error_metadata["error_type"] == "FallbackExecutionError"
    assert error_metadata["failure_class"] == "infra_level"
    assert "Alice" not in error_metadata["error_message"]
    assert "13800138000" not in error_metadata["error_message"]
    assert "123456789012" not in error_metadata["error_message"]


def test_result_keys_match_for_langfuse_otel_and_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_langfuse_factory(monkeypatch, _FakeLangfuseClient())

    langfuse_result, langfuse_bundle = generate_structured_with_replay(
        _request("req-langfuse-keys"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_profile=CallbackProfile(backend="langfuse", enabled=True),
    )
    otel_result, otel_bundle = generate_structured_with_replay(
        _request("req-langfuse-keys"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_profile=CallbackProfile(backend="otel", enabled=True),
    )
    none_result, none_bundle = generate_structured_with_replay(
        _request("req-langfuse-keys"),
        provider_profiles=[_profile()],
        schema_registry={"LangfusePayload": LangfusePayload},
        client_factory=lambda _profile, _max_retries: _SuccessClient(),
        callback_profile=CallbackProfile(backend="none", enabled=False),
    )

    assert langfuse_result.model_dump().keys() == otel_result.model_dump().keys()
    assert langfuse_result.model_dump().keys() == none_result.model_dump().keys()
    assert langfuse_bundle.model_dump().keys() == otel_bundle.model_dump().keys()
    assert langfuse_bundle.model_dump().keys() == none_bundle.model_dump().keys()


def _install_langfuse_factory(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: _FakeLangfuseClient,
    seen_hosts: list[str | None] | None = None,
) -> None:
    def build_backend(
        client: Any | None = None,
        *,
        host: str | None = None,
        trace_name: str = "reasoner.llm",
    ) -> LangfuseCallbackBackend:
        if seen_hosts is not None:
            seen_hosts.append(host)
        return LangfuseCallbackBackend(
            client=client or fake_client,
            host=host,
            trace_name=trace_name,
        )

    monkeypatch.setattr(callback_factory, "LangfuseCallbackBackend", build_backend)
    callback_factory._build_callback_backends_cached.cache_clear()


def _request(request_id: str) -> ReasonerRequest:
    return ReasonerRequest(
        request_id=request_id,
        caller_module="integration-test",
        target_schema="LangfusePayload",
        messages=[{"role": "user", "content": "return a structured answer"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )


def _profile() -> ProviderProfile:
    return ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)


def _payload_keys() -> set[str]:
    return {
        "messages",
        "raw_output",
        "parsed_result",
        "sanitized_input",
        "replay_bundle",
    }


def _events_without_error_latency(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_events: list[dict[str, Any]] = []
    for event in events:
        metadata = dict(event["metadata"])
        if "error_type" in metadata:
            metadata.pop("latency_ms", None)
        normalized_events.append({**event, "metadata": metadata})
    return normalized_events


class _SuccessClient:
    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> Any:
        completion = SimpleNamespace(
            raw_output='{"answer":"ok"}',
            usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            response_cost=0.03,
            latency_ms=22,
        )
        return response_model(answer="ok"), completion


class _FailingClient:
    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> Any:
        raise ConnectionError(
            "provider unavailable name Alice phone 13800138000 account 123456789012"
        )


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def create_event(
        self,
        *,
        name: str,
        metadata: dict[str, Any],
        trace_context: dict[str, str] | None = None,
    ) -> None:
        self.events.append(
            {
                "name": name,
                "metadata": metadata,
                "trace_context": trace_context,
            }
        )
