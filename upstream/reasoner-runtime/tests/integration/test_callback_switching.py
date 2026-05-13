from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from reasoner_runtime.callbacks import factory as callback_factory
from reasoner_runtime.callbacks import litellm as litellm_callbacks
from reasoner_runtime.config import CallbackProfile, load_callback_profile
from reasoner_runtime.core import generate_structured_with_replay
from reasoner_runtime.providers import FallbackExecutionError
from tests.unit.test_callback_regression import (
    EXPECTED_FALLBACK_PATH,
    _RaisingBackend,
    _RecordingBackend,
    _client_factory,
    _provider_profiles,
    _request,
    _run_generation,
    _schema_registry,
    _without_dynamic_contract_times,
)


@pytest.fixture(autouse=True)
def _clear_callback_cache() -> Iterator[None]:
    callback_factory._build_callback_backends_cached.cache_clear()
    yield
    callback_factory._build_callback_backends_cached.cache_clear()


def test_callback_config_switches_between_none_otel_and_langfuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _patch_configured_backend_factories(monkeypatch)
    config_path = tmp_path / "callback.yaml"

    for backend in ("none", "otel", "langfuse", "none"):
        _write_callback_config(config_path, backend)
        loaded_profile = load_callback_profile(config_path)
        assert loaded_profile.backend == backend

        callback_factory._build_callback_backends_cached.cache_clear()
        result, bundle = generate_structured_with_replay(
            _request(),
            provider_profiles=_provider_profiles(),
            schema_registry=_schema_registry(),
            client_factory=_client_factory(),
            callback_config_path=config_path,
        )

        assert result.actual_provider == "anthropic"
        assert result.fallback_path == EXPECTED_FALLBACK_PATH
        assert bundle.llm_lineage["fallback_path"] == EXPECTED_FALLBACK_PATH

    assert len(created["otel"]) == 1
    assert len(created["langfuse"]) == 1
    assert len(created["otel"][0].starts) == 1
    assert len(created["langfuse"][0].starts) == 1
    assert len(created["otel"][0].successes) == 1
    assert len(created["langfuse"][0].successes) == 1
    assert created["otel"][0].errors == []
    assert created["langfuse"][0].errors == []


def test_configured_and_injected_callback_backends_receive_same_terminal_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _patch_configured_backend_factories(monkeypatch)
    config_path = tmp_path / "callback.yaml"
    _write_callback_config(config_path, "otel")
    injected_success = _RecordingBackend()

    result, _bundle = generate_structured_with_replay(
        _request(),
        provider_profiles=_provider_profiles(),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
        callback_config_path=config_path,
        callback_backends=[injected_success],
    )

    configured_success = created["otel"][0]
    assert result.actual_provider == "anthropic"
    assert configured_success.starts[0] == injected_success.starts[0]
    assert _success_dump(configured_success) == _success_dump(injected_success)
    success_context, success = configured_success.successes[0]
    assert success_context.provider == "anthropic"
    assert success_context.model == "claude-sonnet-4.5"
    assert success.fallback_path == EXPECTED_FALLBACK_PATH
    assert success.retry_count == 0
    assert success.failure_class == "success_with_fallback"

    callback_factory._build_callback_backends_cached.cache_clear()
    created["otel"].clear()
    injected_error = _RecordingBackend()

    with pytest.raises(FallbackExecutionError):
        generate_structured_with_replay(
            _request(),
            provider_profiles=_provider_profiles(),
            schema_registry=_schema_registry(),
            client_factory=_client_factory(all_fail=True),
            callback_config_path=config_path,
            callback_backends=[injected_error],
        )

    configured_error = created["otel"][0]
    assert configured_error.starts[0] == injected_error.starts[0]
    assert _error_dump(configured_error) == _error_dump(injected_error)
    error_context, error = configured_error.errors[0]
    assert error_context.provider == "openai"
    assert error_context.model == "gpt-4"
    assert error.failure_class == "infra_level"
    assert "Alice" not in error.error_message
    assert "13900139000" not in error.error_message
    assert "123456789012" not in error.error_message
    assert "acct_ABC123" not in error.error_message


def test_callback_backend_failure_isolated_during_switching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "callback.yaml"
    _write_callback_config(config_path, "otel")
    monkeypatch.setattr(callback_factory, "OTELCallbackBackend", _RaisingBackend)
    recorder = _RecordingBackend()
    baseline_result, baseline_bundle = _run_generation(
        callback_profile=CallbackProfile(backend="none", enabled=False)
    )

    result, bundle = generate_structured_with_replay(
        _request(),
        provider_profiles=_provider_profiles(),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
        callback_config_path=config_path,
        callback_backends=[recorder],
    )

    assert _without_dynamic_contract_times(result.model_dump()) == (
        _without_dynamic_contract_times(baseline_result.model_dump())
    )
    assert _without_dynamic_contract_times(bundle.model_dump()) == (
        _without_dynamic_contract_times(baseline_bundle.model_dump())
    )
    assert result.fallback_path == EXPECTED_FALLBACK_PATH
    assert result.retry_count == 0
    assert len(recorder.starts) == 1
    assert len(recorder.successes) == 1
    assert recorder.errors == []


def test_switching_to_none_clears_configured_backend_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_litellm = SimpleNamespace(success_callback=[], failure_callback=[])
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    litellm_callbacks._installed_bridges.clear()
    created = _patch_configured_backend_factories(monkeypatch)
    config_path = tmp_path / "callback.yaml"

    for backend in ("otel", "langfuse"):
        _write_callback_config(config_path, backend)
        callback_factory._build_callback_backends_cached.cache_clear()
        generate_structured_with_replay(
            _request(),
            provider_profiles=_provider_profiles(),
            schema_registry=_schema_registry(),
            client_factory=_litellm_switching_client_factory(fake_litellm),
            callback_config_path=config_path,
        )

        recorder = created[backend][0]
        assert any(
            context.provider == "openai" and error.error_type == "ConnectionError"
            for context, error in recorder.errors
        )
        assert any(
            context.provider == "anthropic" and success.failure_class is None
            for context, success in recorder.successes
        )
        assert fake_litellm.success_callback == []
        assert fake_litellm.failure_callback == []

    otel_event_counts = _event_counts(created["otel"][0])
    langfuse_event_counts = _event_counts(created["langfuse"][0])

    litellm_callbacks.configure_litellm_callbacks(
        (created["otel"][0], created["langfuse"][0])
    )
    assert fake_litellm.success_callback != []
    assert fake_litellm.failure_callback != []

    _write_callback_config(config_path, "none")
    callback_factory._build_callback_backends_cached.cache_clear()
    generate_structured_with_replay(
        _request(),
        provider_profiles=_provider_profiles(),
        schema_registry=_schema_registry(),
        client_factory=_litellm_switching_client_factory(fake_litellm),
        callback_config_path=config_path,
    )

    assert len(created["otel"]) == 1
    assert len(created["langfuse"]) == 1
    assert _event_counts(created["otel"][0]) == otel_event_counts
    assert _event_counts(created["langfuse"][0]) == langfuse_event_counts
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []


def _patch_configured_backend_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[_RecordingBackend]]:
    created: dict[str, list[_RecordingBackend]] = {
        "otel": [],
        "langfuse": [],
    }

    def build_otel() -> _RecordingBackend:
        backend = _RecordingBackend()
        created["otel"].append(backend)
        return backend

    def build_langfuse(host: str | None = None) -> _RecordingBackend:
        backend = _RecordingBackend()
        created["langfuse"].append(backend)
        return backend

    monkeypatch.setattr(callback_factory, "OTELCallbackBackend", build_otel)
    monkeypatch.setattr(callback_factory, "LangfuseCallbackBackend", build_langfuse)
    return created


def _write_callback_config(path: Path, backend: str) -> None:
    enabled = "false" if backend == "none" else "true"
    endpoint = {
        "none": "null",
        "otel": "memory://otel-switching",
        "langfuse": "http://localhost:3000",
    }[backend]
    path.write_text(
        f"""
callback:
  backend: {backend}
  enabled: {enabled}
  endpoint: {endpoint}
""",
        encoding="utf-8",
    )


def _success_dump(
    backend: _RecordingBackend,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context, success = backend.successes[0]
    return context.model_dump(), success.model_dump()


def _error_dump(
    backend: _RecordingBackend,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context, error = backend.errors[0]
    return context.model_dump(), error.model_dump()


def _event_counts(backend: _RecordingBackend) -> tuple[int, int, int]:
    return len(backend.starts), len(backend.successes), len(backend.errors)


def _litellm_switching_client_factory(fake_litellm: Any) -> Any:
    def factory(profile: Any, max_retries: int) -> _LiteLLMSwitchingClient:
        assert max_retries == 1
        return _LiteLLMSwitchingClient(fake_litellm, profile)

    return factory


class _LiteLLMSwitchingClient:
    def __init__(self, fake_litellm: Any, profile: Any) -> None:
        self.fake_litellm = fake_litellm
        self.profile = profile

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[Any],
        callback_metadata: dict[str, Any],
    ) -> Any:
        metadata = {
            "reasoner": {
                **callback_metadata,
                "provider": self.profile.provider,
                "model": self.profile.model,
            }
        }
        callback_kwargs = {
            "model": f"{self.profile.provider}/{self.profile.model}",
            "messages": messages,
            "metadata": metadata,
        }

        if self.profile.provider == "openai":
            error = ConnectionError("provider unavailable")
            for handler in list(self.fake_litellm.failure_callback):
                handler(
                    {**callback_kwargs, "exception": error},
                    None,
                    100.0,
                    100.006,
                )
            raise error

        completion = SimpleNamespace(
            choices=[{"message": {"content": '{"answer":"fallback-ok","score":7}'}}],
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            response_cost=0.03,
            latency_ms=19,
        )
        for handler in list(self.fake_litellm.success_callback):
            handler(callback_kwargs, completion, 100.0, 100.019)
        return response_model(answer="fallback-ok", score=7), completion
