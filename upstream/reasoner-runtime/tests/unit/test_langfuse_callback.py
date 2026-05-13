from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from reasoner_runtime.callbacks import (
    CallbackBackend,
    CallbackContext,
    CallbackError,
    CallbackSuccess,
    LangfuseCallbackBackend,
    build_callback_backends,
)
from reasoner_runtime.callbacks import factory as callback_factory
from reasoner_runtime.callbacks.langfuse import _build_default_client
from reasoner_runtime.config import CallbackProfile, load_callback_profile
from reasoner_runtime.providers import to_reasoner_error_classification


_FORBIDDEN_PAYLOAD_KEYS = {
    "messages",
    "raw_output",
    "parsed_result",
    "sanitized_input",
    "replay_bundle",
}


def test_langfuse_backend_imports_without_sdk_and_satisfies_protocol() -> None:
    backend = LangfuseCallbackBackend(client=_FakeEventClient())

    assert isinstance(backend, CallbackBackend)


def test_langfuse_start_records_context_metadata_only() -> None:
    client = _FakeEventClient()
    backend = LangfuseCallbackBackend(client=client)

    backend.on_start(_context())

    event = client.events[0]
    assert event["name"] == "reasoner.llm.start"
    assert event["metadata"] == {
        "request_id": "req-langfuse",
        "caller_module": "unit-test",
        "target_schema": "LangfusePayload",
        "provider": "openai",
        "model": "gpt-4",
    }
    _assert_no_payload_keys(event["metadata"])


def test_langfuse_start_records_trace_metadata() -> None:
    client = _FakeEventClient()
    backend = LangfuseCallbackBackend(client=client)

    backend.on_start(_trace_context())

    metadata = client.events[0]["metadata"]
    assert metadata["cycle_id"] == "CYCLE_20260501"
    assert metadata["ticker"] == "ENT_STOCK_300750.SZ"
    assert metadata["analyzer_type"] == "single_prompt_v1"
    assert metadata["regime_label"] == "neutral"
    assert metadata["session_id"] == "CYCLE_20260501_ENT_STOCK_300750.SZ"
    assert metadata["user_id"] == "ENT_STOCK_300750.SZ"
    assert metadata["tags"] == ["L6", "single_prompt_v1", "neutral"]
    _assert_no_payload_keys(metadata)


def test_langfuse_backend_supports_create_event_client_shape() -> None:
    client = _FakeCreateEventClient()
    backend = LangfuseCallbackBackend(client=client)

    backend.on_start(_context())

    event = client.events[0]
    assert event["name"] == "reasoner.llm.start"
    assert event["metadata"]["request_id"] == "req-langfuse"
    assert event["trace_context"] == {
        "trace_id": hashlib.sha256(b"req-langfuse").hexdigest()[:32]
    }


def test_langfuse_success_records_whitelisted_metadata() -> None:
    client = _FakeEventClient()
    backend = LangfuseCallbackBackend(client=client)

    backend.on_success(
        _context(),
        CallbackSuccess(
            token_usage={"prompt": 3, "completion": 4, "total": 7},
            cost_estimate=0.02,
            latency_ms=25,
            fallback_path=["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
            retry_count=1,
            failure_class="success_with_fallback",
        ),
    )

    event = client.events[0]
    metadata = event["metadata"]
    assert event["name"] == "reasoner.llm.success"
    assert metadata["request_id"] == "req-langfuse"
    assert metadata["provider"] == "openai"
    assert metadata["model"] == "gpt-4"
    assert metadata["token_usage"] == {"prompt": 3, "completion": 4, "total": 7}
    assert metadata["cost_estimate"] == 0.02
    assert metadata["latency_ms"] == 25
    assert metadata["fallback_path"] == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert metadata["retry_count"] == 1
    assert metadata["failure_class"] == "success_with_fallback"
    _assert_no_payload_keys(metadata)


def test_langfuse_error_scrubs_and_truncates_metadata() -> None:
    client = _FakeEventClient()
    backend = LangfuseCallbackBackend(client=client)
    raw_message = (
        "name Alice phone 13800138000 account 123456789012 "
        "acct id acct_ABC123 " + ("x" * 700)
    )

    backend.on_error(
        _context(),
        CallbackError(
            error_type="RuntimeError",
            error_message=raw_message,
            failure_class="infra_level",
            error_classification=to_reasoner_error_classification(
                "infra_level",
                error=ConnectionError("provider unavailable"),
                context={"provider": "openai", "model": "gpt-4"},
            ),
            latency_ms=19,
        ),
    )

    event = client.events[0]
    metadata = event["metadata"]
    error_message = metadata["error_message"]
    assert event["name"] == "reasoner.llm.error"
    assert metadata["error_type"] == "RuntimeError"
    assert metadata["failure_class"] == "infra_level"
    assert metadata["error_classification"]["category"] == "model_provider"
    assert metadata["error_classification"]["code"] == "REASONER_MODEL_PROVIDER_ERROR"
    assert metadata["latency_ms"] == 19
    assert len(error_message) <= 500
    assert error_message.endswith("...")
    assert "[REDACTED_NAME]" in error_message
    assert "[REDACTED_PHONE]" in error_message
    assert "[REDACTED_ACCOUNT]" in error_message
    assert "Alice" not in error_message
    assert "13800138000" not in error_message
    assert "123456789012" not in error_message
    assert "acct_ABC123" not in error_message
    _assert_no_payload_keys(metadata)


def test_langfuse_backend_swallows_client_errors() -> None:
    backend = LangfuseCallbackBackend(client=_RaisingClient())

    backend.on_start(_context())
    backend.on_success(_context(), CallbackSuccess())
    backend.on_error(
        _context(),
        CallbackError(error_type="RuntimeError", error_message="boom"),
    )


def test_langfuse_backend_supports_trace_event_client_shape() -> None:
    client = _FakeTraceClient()
    backend = LangfuseCallbackBackend(client=client, trace_name="reasoner.custom")

    backend.on_start(_context())

    assert client.trace_names == ["reasoner.custom"]
    assert client.trace_events[0]["name"] == "reasoner.llm.start"
    assert client.trace_events[0]["metadata"]["request_id"] == "req-langfuse"


def test_langfuse_backend_warns_for_unsupported_client_shape(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = LangfuseCallbackBackend(client=object())

    with caplog.at_level(
        logging.WARNING,
        logger="reasoner_runtime.callbacks.langfuse",
    ):
        backend.on_start(_context())

    assert backend.unsupported_client_events == 1
    assert "unsupported client shape object" in caplog.text


def test_default_client_maps_host_to_langfuse_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "langfuse",
        SimpleNamespace(Langfuse=_FakeLangfuseSdkClient),
    )

    client = _build_default_client("http://langfuse.local")

    assert client.host == "http://langfuse.local"


def test_default_client_missing_sdk_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "langfuse", None)

    with pytest.raises(RuntimeError, match="optional 'langfuse' package"):
        _build_default_client(None)


def test_langfuse_missing_sdk_is_visible_during_callback_emit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setitem(sys.modules, "langfuse", None)
    backend = LangfuseCallbackBackend()

    with caplog.at_level(
        logging.WARNING,
        logger="reasoner_runtime.callbacks.langfuse",
    ):
        backend.on_start(_context())

    assert backend.export_failures == 1
    assert "optional 'langfuse' package" in caplog.text


def test_factory_builds_langfuse_backend_and_disabled_profile_skips_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "langfuse", None)
    callback_factory._build_callback_backends_cached.cache_clear()

    assert build_callback_backends(
        CallbackProfile(backend="langfuse", enabled=False)
    ) == ()

    backends = build_callback_backends(
        CallbackProfile(
            backend="langfuse",
            enabled=True,
            endpoint="http://langfuse.local",
        )
    )

    assert len(backends) == 1
    assert isinstance(backends[0], LangfuseCallbackBackend)
    assert backends[0].host == "http://langfuse.local"


def test_load_callback_profile_parses_wrapped_langfuse_config(tmp_path: Path) -> None:
    config_path = tmp_path / "callback.yaml"
    config_path.write_text(
        """
callback:
  backend: langfuse
  enabled: true
  endpoint: http://langfuse.local
""",
        encoding="utf-8",
    )

    profile = load_callback_profile(config_path)

    assert profile == CallbackProfile(
        backend="langfuse",
        enabled=True,
        endpoint="http://langfuse.local",
    )


def _context() -> CallbackContext:
    return CallbackContext(
        request_id="req-langfuse",
        caller_module="unit-test",
        target_schema="LangfusePayload",
        provider="openai",
        model="gpt-4",
    )


def _trace_context() -> CallbackContext:
    return CallbackContext(
        request_id="req-langfuse",
        caller_module="unit-test",
        target_schema="LangfusePayload",
        provider="openai",
        model="gpt-4",
        cycle_id="CYCLE_20260501",
        ticker="ENT_STOCK_300750.SZ",
        analyzer_type="single_prompt_v1",
        regime_label="neutral",
    )


def _assert_no_payload_keys(metadata: dict[str, Any]) -> None:
    assert _FORBIDDEN_PAYLOAD_KEYS.isdisjoint(metadata)


class _FakeEventClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def event(self, *, name: str, metadata: dict[str, Any]) -> None:
        self.events.append({"name": name, "metadata": metadata})


class _FakeCreateEventClient:
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


class _FakeTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def event(self, *, name: str, metadata: dict[str, Any]) -> None:
        self.events.append({"name": name, "metadata": metadata})


class _FakeTraceClient:
    def __init__(self) -> None:
        self._trace = _FakeTrace()
        self.trace_names: list[str] = []

    @property
    def trace_events(self) -> list[dict[str, Any]]:
        return self._trace.events

    def trace(self, *, name: str) -> _FakeTrace:
        self.trace_names.append(name)
        return self._trace


class _RaisingClient:
    def event(self, *, name: str, metadata: dict[str, Any]) -> None:
        raise RuntimeError("langfuse exporter failed")


class _FakeLangfuseSdkClient:
    def __init__(self, host: str | None = None) -> None:
        self.host = host
