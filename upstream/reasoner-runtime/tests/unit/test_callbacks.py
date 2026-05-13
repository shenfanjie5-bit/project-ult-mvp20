from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from contracts.schemas.reasoner import ReasonerErrorCategory
from pydantic import BaseModel

from reasoner_runtime.callbacks import (
    CallbackContext,
    CallbackError,
    CallbackSuccess,
    LiteLLMCallbackBridge,
    OTELCallbackBackend,
    configure_litellm_callbacks,
)
from reasoner_runtime.core import ReasonerRequest
from reasoner_runtime.providers import to_reasoner_error_classification
from reasoner_runtime.structured import run_structured_call


class CallbackPayload(BaseModel):
    answer: str


def _context() -> CallbackContext:
    return CallbackContext(
        request_id="req-1",
        caller_module="unit-test",
        target_schema="CallbackPayload",
        provider="openai",
        model="gpt-4",
    )


def _trace_context() -> CallbackContext:
    return CallbackContext(
        request_id="req-1",
        caller_module="unit-test",
        target_schema="CallbackPayload",
        provider="openai",
        model="gpt-4",
        cycle_id="CYCLE_20260501",
        ticker="ENT_STOCK_300750.SZ",
        analyzer_type="single_prompt_v1",
        regime_label="neutral",
    )


def _request() -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-1",
        caller_module="unit-test",
        target_schema="CallbackPayload",
        messages=[{"role": "user", "content": "hello"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
    )


def test_otel_success_records_stable_non_pii_attributes() -> None:
    tracer = _FakeTracer()
    backend = OTELCallbackBackend(tracer=tracer)

    backend.on_success(
        _context(),
        CallbackSuccess(
            token_usage={"prompt": 3, "completion": 4, "total": 7},
            cost_estimate=0.05,
            latency_ms=25,
            fallback_path=["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
            retry_count=1,
            failure_class="success_with_fallback",
        ),
    )

    span = tracer.spans[0]
    assert span.name == "reasoner.llm.success"
    assert span.attributes["reasoner.request_id"] == "req-1"
    assert span.attributes["reasoner.caller_module"] == "unit-test"
    assert span.attributes["reasoner.target_schema"] == "CallbackPayload"
    assert span.attributes["llm.provider"] == "openai"
    assert span.attributes["llm.model"] == "gpt-4"
    assert span.attributes["llm.tokens.prompt"] == 3
    assert span.attributes["llm.tokens.completion"] == 4
    assert span.attributes["llm.tokens.total"] == 7
    assert span.attributes["llm.cost_estimate"] == 0.05
    assert span.attributes["llm.latency_ms"] == 25
    assert span.attributes["llm.retry_count"] == 1
    assert span.attributes["llm.fallback_path.length"] == 2
    assert span.attributes["llm.failure_class"] == "success_with_fallback"
    assert not {"messages", "raw_output", "parsed_result"} & span.attributes.keys()


def test_otel_success_records_trace_metadata() -> None:
    tracer = _FakeTracer()
    backend = OTELCallbackBackend(tracer=tracer)

    backend.on_success(_trace_context(), CallbackSuccess())

    span = tracer.spans[0]
    assert span.attributes["reasoner.cycle_id"] == "CYCLE_20260501"
    assert span.attributes["reasoner.ticker"] == "ENT_STOCK_300750.SZ"
    assert span.attributes["reasoner.analyzer_type"] == "single_prompt_v1"
    assert span.attributes["reasoner.regime_label"] == "neutral"
    assert span.attributes["reasoner.session_id"] == (
        "CYCLE_20260501_ENT_STOCK_300750.SZ"
    )
    assert span.attributes["reasoner.user_id"] == "ENT_STOCK_300750.SZ"
    assert span.attributes["reasoner.tags"] == "L6,single_prompt_v1,neutral"


def test_otel_error_records_failure_and_marks_status_error() -> None:
    tracer = _FakeTracer()
    backend = OTELCallbackBackend(tracer=tracer)

    backend.on_error(
        _context(),
        CallbackError(
            error_type="ConnectionError",
            error_message="provider unavailable",
            failure_class="infra_level",
            error_classification=to_reasoner_error_classification(
                "infra_level",
                error=ConnectionError("provider unavailable"),
                context={"provider": "openai", "model": "gpt-4"},
            ),
            latency_ms=9,
        ),
    )

    span = tracer.spans[0]
    assert span.name == "reasoner.llm.error"
    assert span.attributes["llm.error_type"] == "ConnectionError"
    assert span.attributes["llm.error_message"] == "provider unavailable"
    assert span.attributes["llm.failure_class"] == "infra_level"
    assert (
        span.attributes["llm.error_classification.code"]
        == "REASONER_MODEL_PROVIDER_ERROR"
    )
    assert span.attributes["llm.error_classification.category"] == "model_provider"
    assert span.attributes["llm.error_classification.retryable"] == "true"
    assert span.attributes["llm.latency_ms"] == 9
    assert _status_code_name(span.status) == "ERROR"


def test_otel_backend_swallows_exporter_errors() -> None:
    backend = OTELCallbackBackend(tracer=_RaisingTracer())

    backend.on_start(_context())
    backend.on_success(_context(), CallbackSuccess())
    backend.on_error(
        _context(),
        CallbackError(error_type="RuntimeError", error_message="boom"),
    )


def test_litellm_bridge_success_extracts_dict_response_shape() -> None:
    recorder = _RecordingBackend()
    bridge = LiteLLMCallbackBridge([_RaisingBackend(), recorder])

    bridge.success_handler(
        {
            "model": "ignored-provider/ignored-model",
            "messages": [{"role": "user", "content": "do not record"}],
            "metadata": {
                "reasoner": {
                    "request_id": "req-bridge",
                    "caller_module": "bridge-test",
                    "target_schema": "CallbackPayload",
                    "provider": "anthropic",
                    "model": "claude-sonnet-4.5",
                    "fallback_path": [
                        "openai/gpt-4",
                        "anthropic/claude-sonnet-4.5",
                    ],
                    "retry_count": 2,
                    "failure_class": "success_with_fallback",
                }
            },
        },
        {
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 5,
                "total_tokens": 16,
            },
            "_hidden_params": {"response_cost": 0.004},
            "choices": [{"message": {"content": "raw response"}}],
        },
        100.0,
        100.125,
    )

    context, success = recorder.successes[0]
    assert context.request_id == "req-bridge"
    assert context.provider == "anthropic"
    assert context.model == "claude-sonnet-4.5"
    assert success.token_usage == {"prompt": 11, "completion": 5, "total": 16}
    assert success.cost_estimate == 0.004
    assert success.latency_ms == 125
    assert success.fallback_path == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert success.retry_count == 2
    assert success.failure_class == "success_with_fallback"
    assert not hasattr(success, "raw_output")


def test_litellm_bridge_failure_extracts_object_shape_and_isolates_backends() -> None:
    recorder = _RecordingBackend()
    bridge = LiteLLMCallbackBridge([_RaisingBackend(), recorder])

    bridge.failure_handler(
        {
            "model": "openai/gpt-4",
            "metadata": {"reasoner": {"request_id": "req-fail"}},
            "exception": TimeoutError("request timed out"),
        },
        SimpleNamespace(response_cost=0.01),
        10.0,
        10.005,
    )

    context, error = recorder.errors[0]
    assert context.request_id == "req-fail"
    assert context.provider == "openai"
    assert context.model == "gpt-4"
    assert error.error_type == "TimeoutError"
    assert error.error_message == "request timed out"
    assert error.error_classification is not None
    assert error.error_classification.category is ReasonerErrorCategory.TIMEOUT
    assert error.error_classification.retryable is True
    assert error.latency_ms == 5


def test_litellm_bridge_failure_never_uses_completion_response_as_error_message() -> None:
    recorder = _RecordingBackend()
    bridge = LiteLLMCallbackBridge([recorder])

    bridge.failure_handler(
        {
            "model": "openai/gpt-4",
            "metadata": {"reasoner": {"request_id": "req-safe-fail"}},
        },
        {
            "messages": [
                {"role": "user", "content": "name Alice phone 13800138000"}
            ],
            "choices": [
                {
                    "message": {
                        "content": (
                            "raw_output account 123456789012 should not leak"
                        )
                    }
                }
            ],
        },
        20.0,
        20.003,
    )

    _, error = recorder.errors[0]
    assert error.error_type == "UnknownProviderError"
    assert error.error_message == "unknown provider error"
    assert "Alice" not in error.error_message
    assert "13800138000" not in error.error_message
    assert "123456789012" not in error.error_message
    assert "raw_output" not in error.error_message


def test_litellm_bridge_failure_scrubs_and_truncates_explicit_error_messages() -> None:
    recorder = _RecordingBackend()
    bridge = LiteLLMCallbackBridge([recorder])
    raw_message = (
        "name Alice phone 13800138000 account 123456789012 " + ("x" * 700)
    )

    bridge.failure_handler(
        {
            "model": "openai/gpt-4",
            "metadata": {"reasoner": {"request_id": "req-scrubbed-fail"}},
            "exception": RuntimeError(raw_message),
        },
        None,
        30.0,
        30.002,
    )

    _, error = recorder.errors[0]
    assert error.error_type == "RuntimeError"
    assert len(error.error_message) <= 500
    assert error.error_message.endswith("...")
    assert "[REDACTED_NAME]" in error.error_message
    assert "[REDACTED_PHONE]" in error.error_message
    assert "[REDACTED_ACCOUNT]" in error.error_message
    assert "Alice" not in error.error_message
    assert "13800138000" not in error.error_message
    assert "123456789012" not in error.error_message


def test_litellm_bridge_backend_failure_log_omits_raw_exception(
    caplog: Any,
) -> None:
    class _SensitiveRaisingBackend:
        def on_error(self, context: CallbackContext, error: CallbackError) -> None:
            raise RuntimeError(
                "sensitive provider data phone 13800138000 "
                "SENSITIVE_DATABASE_SECRET"
            )

    bridge = LiteLLMCallbackBridge([_SensitiveRaisingBackend()])

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.callbacks.litellm"):
        bridge.failure_handler(
            {
                "model": "openai/gpt-4",
                "metadata": {"reasoner": {"request_id": "req-safe-log"}},
                "exception": TimeoutError("provider timeout"),
            },
            None,
            30.0,
            30.002,
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "litellm failure callback backend" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "13800138000" not in rendered
    assert "SENSITIVE_DATABASE_SECRET" not in rendered
    assert "[REDACTED_PHONE]" not in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_litellm_bridge_extraction_failure_log_omits_raw_exception(
    caplog: Any,
    monkeypatch: Any,
) -> None:
    def _raise_sensitive_context(_kwargs: Any) -> CallbackContext:
        raise RuntimeError(
            "prompt phone 13800138000 credential SENSITIVE_CREDENTIAL_VALUE"
        )

    monkeypatch.setattr(
        "reasoner_runtime.callbacks.litellm._build_context",
        _raise_sensitive_context,
    )
    bridge = LiteLLMCallbackBridge([_RecordingBackend()])

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.callbacks.litellm"):
        bridge.success_handler(
            {"model": "openai/gpt-4"},
            None,
            1.0,
            1.001,
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "payload extraction failed" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "13800138000" not in rendered
    assert "SENSITIVE_CREDENTIAL_VALUE" not in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_configure_litellm_callbacks_registers_once(monkeypatch: Any) -> None:
    fake_litellm = SimpleNamespace(success_callback=[], failure_callback=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    backend = _RecordingBackend()

    first = configure_litellm_callbacks([backend])
    second = configure_litellm_callbacks([backend])

    assert first is not None
    assert second is not None
    assert len(fake_litellm.success_callback) == 1
    assert len(fake_litellm.failure_callback) == 1
    assert fake_litellm.success_callback[0].__self__ is second
    assert fake_litellm.failure_callback[0].__self__ is second


def test_configure_litellm_callbacks_can_disable_package_handlers(
    monkeypatch: Any,
) -> None:
    foreign_success = object()
    foreign_failure = object()
    fake_litellm = SimpleNamespace(
        success_callback=[foreign_success],
        failure_callback=(foreign_failure,),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    backend = _RecordingBackend()

    bridge = configure_litellm_callbacks([backend])
    assert bridge is not None

    configure_litellm_callbacks(())

    assert fake_litellm.success_callback == [foreign_success]
    assert fake_litellm.failure_callback == [foreign_failure]


def test_run_structured_call_passes_callback_metadata_without_extra_call() -> None:
    client = _CreateStructuredClient()

    result = run_structured_call(client, _request(), CallbackPayload)

    assert result.parsed_result == {"answer": "ok"}
    assert len(client.calls) == 1
    assert client.calls[0]["callback_metadata"] == {
        "request_id": "req-1",
        "caller_module": "unit-test",
        "target_schema": "CallbackPayload",
        "provider": "openai",
        "model": "gpt-4",
    }


class _FakeSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict[str, Any] = {}
        self.status: Any = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: Any) -> None:
        self.status = status


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    @contextmanager
    def start_as_current_span(self, name: str) -> Any:
        span = _FakeSpan(name)
        self.spans.append(span)
        yield span


class _RaisingTracer:
    @contextmanager
    def start_as_current_span(self, name: str) -> Any:
        raise RuntimeError("exporter failed")
        yield


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


class _CreateStructuredClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        callback_metadata: dict[str, Any],
    ) -> Any:
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
                "callback_metadata": callback_metadata,
            }
        )
        return CallbackPayload(answer="ok")


def _status_code_name(status: Any) -> str:
    status_code = getattr(status, "status_code", status)
    return getattr(status_code, "name", str(status_code))
