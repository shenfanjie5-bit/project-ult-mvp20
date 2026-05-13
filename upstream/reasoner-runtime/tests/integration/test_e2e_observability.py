from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

import reasoner_runtime
from reasoner_runtime.callbacks import CallbackContext, CallbackError, CallbackSuccess


class ObservablePayload(BaseModel):
    answer: str


def test_generate_structured_emits_final_callback_metadata_for_fallback_success() -> None:
    recorder = _RecordingBackend()

    result, _bundle = reasoner_runtime.generate_structured_with_replay(
        _request("req-observable-success"),
        provider_profiles=_profiles(),
        schema_registry={"ObservablePayload": ObservablePayload},
        client_factory=_client_factory(),
        callback_backends=[recorder],
    )

    assert result.actual_provider == "anthropic"
    assert [context.request_id for context in recorder.starts] == [
        "req-observable-success"
    ]
    success_context, success = recorder.successes[0]
    assert success_context.request_id == "req-observable-success"
    assert success_context.caller_module == "subsystem-smoke"
    assert success_context.target_schema == "ObservablePayload"
    assert success_context.provider == "anthropic"
    assert success_context.model == "claude-sonnet-4.5"
    assert success.fallback_path == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert success.retry_count == 0
    assert success.failure_class == "success_with_fallback"
    assert success.token_usage == {"prompt": 8, "completion": 4, "total": 12}
    assert success.cost_estimate == 0.03
    assert success.latency_ms == 19
    assert recorder.errors == []


def test_callback_backend_failure_does_not_break_generation() -> None:
    recorder = _RecordingBackend()

    result, _bundle = reasoner_runtime.generate_structured_with_replay(
        _request("req-observable-isolated"),
        provider_profiles=_profiles(),
        schema_registry={"ObservablePayload": ObservablePayload},
        client_factory=_client_factory(),
        callback_backends=[_RaisingBackend(), recorder],
    )

    assert result.parsed_result == {"answer": "fallback-ok"}
    assert len(recorder.starts) == 1
    assert len(recorder.successes) == 1
    assert recorder.errors == []


def test_generate_structured_emits_terminal_callback_error_for_infra_failure() -> None:
    recorder = _RecordingBackend()

    with pytest.raises(RuntimeError):
        reasoner_runtime.generate_structured_with_replay(
            _request("req-observable-error"),
            provider_profiles=_profiles(),
            schema_registry={"ObservablePayload": ObservablePayload},
            client_factory=_client_factory(all_fail=True),
            callback_backends=[recorder],
        )

    assert len(recorder.starts) == 1
    assert recorder.successes == []
    error_context, error = recorder.errors[0]
    assert error_context.request_id == "req-observable-error"
    assert error.failure_class == "infra_level"
    assert error.error_type == "FallbackExecutionError"
    assert "acct_123456" not in error.error_message
    assert "13900139000" not in error.error_message


def _request(request_id: str) -> reasoner_runtime.ReasonerRequest:
    return reasoner_runtime.ReasonerRequest(
        request_id=request_id,
        caller_module="subsystem-smoke",
        target_schema="ObservablePayload",
        messages=[{"role": "user", "content": "answer with JSON"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )


def _profiles() -> list[reasoner_runtime.ProviderProfile]:
    return [
        reasoner_runtime.ProviderProfile(
            provider="openai",
            model="gpt-4",
            fallback_priority=0,
        ),
        reasoner_runtime.ProviderProfile(
            provider="anthropic",
            model="claude-sonnet-4.5",
            fallback_priority=1,
        ),
    ]


def _client_factory(
    *,
    all_fail: bool = False,
) -> Any:
    def factory(
        profile: reasoner_runtime.ProviderProfile,
        max_retries: int,
    ) -> _ObservableClient:
        return _ObservableClient(profile, all_fail=all_fail)

    return factory


class _ObservableClient:
    def __init__(
        self,
        profile: reasoner_runtime.ProviderProfile,
        *,
        all_fail: bool,
    ) -> None:
        self.profile = profile
        self.all_fail = all_fail

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> Any:
        if self.profile.provider == "openai" or self.all_fail:
            raise ConnectionError(
                f"{self.profile.provider}/{self.profile.model} unavailable "
                "account_id=acct_123456 phone 13900139000"
            )

        completion = SimpleNamespace(
            raw_output='{"answer":"fallback-ok"}',
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            response_cost=0.03,
            latency_ms=19,
        )
        return response_model(answer="fallback-ok"), completion


class _RecordingBackend:
    def __init__(self) -> None:
        self.starts: list[CallbackContext] = []
        self.successes: list[tuple[CallbackContext, CallbackSuccess]] = []
        self.errors: list[tuple[CallbackContext, CallbackError]] = []

    def on_start(self, context: CallbackContext) -> None:
        self.starts.append(context)

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        self.successes.append((context, success))

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        self.errors.append((context, error))


class _RaisingBackend:
    def on_start(self, context: CallbackContext) -> None:
        raise RuntimeError("backend failed")

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        raise RuntimeError("backend failed")

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        raise RuntimeError("backend failed")
