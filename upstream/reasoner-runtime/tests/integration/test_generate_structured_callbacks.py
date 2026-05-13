from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from reasoner_runtime.callbacks import (
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)
from reasoner_runtime.callbacks import factory as callback_factory
from reasoner_runtime.callbacks import litellm as litellm_callbacks
from reasoner_runtime.config import CallbackProfile, ProviderProfile
from reasoner_runtime.core import ReasonerRequest, generate_structured_with_replay
from reasoner_runtime.providers import FallbackExecutionError


class CallbackPayload(BaseModel):
    answer: str


def _request(request_id: str) -> ReasonerRequest:
    return ReasonerRequest(
        request_id=request_id,
        caller_module="integration-test",
        target_schema="CallbackPayload",
        messages=[{"role": "user", "content": "return a structured answer"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )


def _callback_config_path(tmp_path: Path) -> Path:
    config_path = tmp_path / "callback.yaml"
    config_path.write_text(
        """
callback:
  backend: otel
  enabled: true
  endpoint: memory://callback-integration
""",
        encoding="utf-8",
    )
    return config_path


def test_generate_structured_with_replay_installs_configured_callbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_litellm = SimpleNamespace(success_callback=[], failure_callback=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    recorder = _RecordingBackend()
    callback_factory._build_callback_backends_cached.cache_clear()
    litellm_callbacks._installed_bridges.clear()
    monkeypatch.setattr(
        callback_factory,
        "OTELCallbackBackend",
        lambda: recorder,
    )

    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    callback_config_path = _callback_config_path(tmp_path)

    result, _bundle = generate_structured_with_replay(
        _request("req-callback-success"),
        provider_profiles=[profile],
        schema_registry={"CallbackPayload": CallbackPayload},
        client_factory=lambda _profile, _max_retries: _CallbackClient(
            fake_litellm,
            mode="success",
        ),
        callback_config_path=callback_config_path,
    )

    assert result.parsed_result == {"answer": "ok"}
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []
    success_context, success = recorder.successes[0]
    assert success_context.request_id == "req-callback-success"
    assert success_context.provider == "openai"
    assert success_context.model == "gpt-4"
    assert success.token_usage == {"prompt": 5, "completion": 7, "total": 12}
    assert success.cost_estimate == 0.03
    assert success.latency_ms == 22

    with pytest.raises(FallbackExecutionError):
        generate_structured_with_replay(
            _request("req-callback-error"),
            provider_profiles=[profile],
            schema_registry={"CallbackPayload": CallbackPayload},
            client_factory=lambda _profile, _max_retries: _CallbackClient(
                fake_litellm,
                mode="error",
            ),
            callback_config_path=callback_config_path,
        )

    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []
    assert any(
        error.error_type == "ConnectionError" for _context, error in recorder.errors
    )
    error_context, error = next(
        (context, error)
        for context, error in recorder.errors
        if error.error_type == "FallbackExecutionError"
    )
    assert error_context.request_id == "req-callback-error"
    assert error_context.provider == "openai"
    assert error_context.model == "gpt-4"
    assert error.error_type == "FallbackExecutionError"
    assert error.error_message == "provider unavailable"
    assert error.latency_ms is not None
    assert error.latency_ms >= 0


def test_generate_structured_with_replay_does_not_reuse_callback_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_litellm = SimpleNamespace(success_callback=[], failure_callback=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    recorder = _RecordingBackend()
    callback_factory._build_callback_backends_cached.cache_clear()
    litellm_callbacks._installed_bridges.clear()
    monkeypatch.setattr(
        callback_factory,
        "OTELCallbackBackend",
        lambda: recorder,
    )

    profile = ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
    callback_config_path = _callback_config_path(tmp_path)

    generate_structured_with_replay(
        _request("req-callback-enabled"),
        provider_profiles=[profile],
        schema_registry={"CallbackPayload": CallbackPayload},
        client_factory=lambda _profile, _max_retries: _CallbackClient(
            fake_litellm,
            mode="success",
        ),
        callback_config_path=callback_config_path,
    )

    assert _terminal_success_request_ids(recorder) == [
        "req-callback-enabled"
    ]
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []

    generate_structured_with_replay(
        _request("req-callback-no-profile"),
        provider_profiles=[profile],
        schema_registry={"CallbackPayload": CallbackPayload},
        client_factory=lambda _profile, _max_retries: _CallbackClient(
            fake_litellm,
            mode="success",
        ),
    )

    assert _terminal_success_request_ids(recorder) == [
        "req-callback-enabled"
    ]
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []

    generate_structured_with_replay(
        _request("req-callback-enabled-again"),
        provider_profiles=[profile],
        schema_registry={"CallbackPayload": CallbackPayload},
        client_factory=lambda _profile, _max_retries: _CallbackClient(
            fake_litellm,
            mode="success",
        ),
        callback_config_path=callback_config_path,
    )

    assert _terminal_success_request_ids(recorder) == [
        "req-callback-enabled",
        "req-callback-enabled-again",
    ]
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []

    generate_structured_with_replay(
        _request("req-callback-disabled"),
        provider_profiles=[profile],
        schema_registry={"CallbackPayload": CallbackPayload},
        client_factory=lambda _profile, _max_retries: _CallbackClient(
            fake_litellm,
            mode="success",
        ),
        callback_profile=CallbackProfile(backend="none", enabled=False),
    )

    assert _terminal_success_request_ids(recorder) == [
        "req-callback-enabled",
        "req-callback-enabled-again",
    ]
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []


class _CallbackClient:
    def __init__(self, litellm_module: Any, mode: str) -> None:
        self.litellm_module = litellm_module
        self.mode = mode

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        callback_metadata: dict[str, Any],
    ) -> Any:
        callback_kwargs = {
            "model": "openai/gpt-4",
            "messages": messages,
            "metadata": {"reasoner": callback_metadata},
        }

        if self.mode == "error":
            error = ConnectionError("provider unavailable")
            for handler in list(self.litellm_module.failure_callback):
                handler(
                    {**callback_kwargs, "exception": error},
                    None,
                    100.0,
                    100.013,
                )
            raise error

        completion = SimpleNamespace(
            choices=[{"message": {"content": '{"answer":"ok"}'}}],
            usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            response_cost=0.03,
            latency_ms=22,
        )
        for handler in list(self.litellm_module.success_callback):
            handler(callback_kwargs, completion, 100.0, 100.022)
        return response_model(answer="ok"), completion


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


def _terminal_success_request_ids(backend: _RecordingBackend) -> list[str]:
    return [
        context.request_id
        for context, success in backend.successes
        if success.failure_class == "none"
    ]
