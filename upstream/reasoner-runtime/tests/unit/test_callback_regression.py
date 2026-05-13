from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator, Sequence
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from reasoner_runtime.callbacks import (
    CallbackBackend,
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)
from reasoner_runtime.callbacks import factory as callback_factory
from reasoner_runtime.config import CallbackProfile, ProviderProfile
from reasoner_runtime.core import (
    ReasonerRequest,
    StructuredGenerationResult,
    callback_failure_counts,
    generate_structured,
    generate_structured_with_replay,
)
import reasoner_runtime.core.engine as core_engine
from reasoner_runtime.providers import FallbackExecutionError
from reasoner_runtime.replay import ReplayBundle


RAW_OUTPUT = '{"answer":"fallback-ok","score":7}'
EXPECTED_FALLBACK_PATH = ["openai/gpt-4", "anthropic/claude-sonnet-4.5"]


class CallbackRegressionPayload(BaseModel):
    answer: str
    score: int


def _run_generation(
    callback_profile: CallbackProfile | None = None,
    callback_backends: Sequence[CallbackBackend] | None = None,
) -> tuple[StructuredGenerationResult, ReplayBundle]:
    return generate_structured_with_replay(
        _request(),
        provider_profiles=_provider_profiles(),
        schema_registry=_schema_registry(),
        client_factory=_client_factory(),
        callback_profile=callback_profile,
        callback_backends=callback_backends,
    )


@pytest.fixture(autouse=True)
def _record_configured_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    callback_factory._build_callback_backends_cached.cache_clear()
    monkeypatch.setattr(callback_factory, "OTELCallbackBackend", _RecordingBackend)
    monkeypatch.setattr(
        callback_factory,
        "LangfuseCallbackBackend",
        lambda host=None: _RecordingBackend(),
    )
    yield
    callback_factory._build_callback_backends_cached.cache_clear()


def test_callback_backend_switch_does_not_change_structured_result_contract() -> None:
    dumps = [
        _run_generation(callback_profile=profile)[0].model_dump()
        for profile in _callback_profiles()
    ]

    baseline = dumps[0]
    for result_dump in dumps:
        assert result_dump.keys() == baseline.keys()
        assert _without_dynamic_contract_times(result_dump) == (
            _without_dynamic_contract_times(baseline)
        )

    assert baseline["parsed_result"] == {"answer": "fallback-ok", "score": 7}
    assert baseline["actual_provider"] == "anthropic"
    assert baseline["actual_model"] == "claude-sonnet-4.5"
    assert baseline["fallback_path"] == EXPECTED_FALLBACK_PATH
    assert baseline["retry_count"] == 0
    assert baseline["token_usage"] == {"prompt": 8, "completion": 4, "total": 12}
    assert baseline["cost_estimate"] == 0.03
    assert baseline["latency_ms"] == 19


def test_callback_backend_switch_does_not_change_replay_bundle_contract() -> None:
    bundles = [
        _run_generation(callback_profile=profile)[1]
        for profile in _callback_profiles()
    ]
    dumps = [bundle.model_dump() for bundle in bundles]

    baseline = dumps[0]
    for bundle, bundle_dump in zip(bundles, dumps, strict=True):
        assert _without_dynamic_contract_times(bundle_dump) == (
            _without_dynamic_contract_times(baseline)
        )
        assert _core_replay_fields(bundle_dump) == {
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        }
        assert bundle.input_hash == _sha256(bundle.sanitized_input)
        assert bundle.output_hash == _sha256(bundle.raw_output)
        assert bundle.raw_output == RAW_OUTPUT


def test_generate_structured_return_shape_is_stable_across_callback_backends() -> None:
    for profile in _callback_profiles():
        result = generate_structured(
            _request(),
            provider_profiles=_provider_profiles(),
            schema_registry=_schema_registry(),
            client_factory=_client_factory(),
            callback_profile=profile,
        )

        assert isinstance(result, StructuredGenerationResult)
        assert not isinstance(result, tuple)
        assert result.actual_provider == "anthropic"
        assert result.fallback_path == EXPECTED_FALLBACK_PATH


def test_callback_failure_counts_increment_without_altering_generation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _SensitiveRaisingBackend:
        def on_start(self, context: CallbackContext) -> None:
            raise RuntimeError(
                "callback start prompt phone 13800138000 "
                "SENSITIVE_DATABASE_SECRET"
            )

        def on_success(
            self,
            context: CallbackContext,
            success: CallbackSuccess,
        ) -> None:
            raise RuntimeError(
                "callback success prompt phone 13800138000 "
                "SENSITIVE_DATABASE_SECRET"
            )

        def on_error(self, context: CallbackContext, error: CallbackError) -> None:
            raise RuntimeError("callback error should not run")

    _clear_callback_failure_counts()

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.core.engine"):
        result, _bundle = generate_structured_with_replay(
            _request(),
            provider_profiles=_provider_profiles(),
            schema_registry=_schema_registry(),
            client_factory=_client_factory(),
            callback_backends=(_SensitiveRaisingBackend(),),
        )

    assert result.parsed_result == {"answer": "fallback-ok", "score": 7}
    assert callback_failure_counts() == {
        "on_start:_SensitiveRaisingBackend": 1,
        "on_success:_SensitiveRaisingBackend": 1,
    }
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "exception_type=RuntimeError" in rendered
    assert "13800138000" not in rendered
    assert "SENSITIVE_DATABASE_SECRET" not in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_on_error_callback_failure_preserves_generation_error_and_safe_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_callback_message = (
        "callback exporter failed postgresql://callback:password@localhost:5432/prod "
        "token=CALLBACK_SECRET_TOKEN_123"
    )

    class _OnErrorRaisingBackend:
        def on_start(self, context: CallbackContext) -> None:
            pass

        def on_success(
            self,
            context: CallbackContext,
            success: CallbackSuccess,
        ) -> None:
            raise AssertionError("on_success should not run")

        def on_error(self, context: CallbackContext, error: CallbackError) -> None:
            raise RuntimeError(sensitive_callback_message)

    _clear_callback_failure_counts()

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.core.engine"):
        with pytest.raises(FallbackExecutionError) as raised:
            generate_structured_with_replay(
                _request(),
                provider_profiles=_provider_profiles(),
                schema_registry=_schema_registry(),
                client_factory=_client_factory(all_fail=True),
                callback_backends=(_OnErrorRaisingBackend(),),
            )

    assert isinstance(raised.value.last_error, ConnectionError)
    assert "anthropic/claude-sonnet-4.5 unavailable" in str(
        raised.value.last_error
    )
    assert "callback exporter failed" not in str(raised.value)
    assert callback_failure_counts() == {"on_error:_OnErrorRaisingBackend": 1}

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "reasoner-runtime callback on_error failed" in rendered
    assert "backend=_OnErrorRaisingBackend" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "postgresql://callback:password@localhost:5432/prod" not in rendered
    assert "CALLBACK_SECRET_TOKEN_123" not in rendered
    assert sensitive_callback_message not in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_callbacks_example_yaml_validates_all_callback_profiles() -> None:
    config_path = Path("config/callbacks.example.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    examples = config["examples"]
    assert set(examples) == {"none", "otel", "langfuse"}
    for name in ("none", "otel", "langfuse"):
        CallbackProfile.model_validate(examples[name]["callback"])

    rendered = config_path.read_text(encoding="utf-8").lower()
    assert "api_key" not in rendered
    assert "secret" not in rendered
    assert "token" not in rendered
    assert "sk-" not in rendered


def _callback_profiles() -> tuple[CallbackProfile, CallbackProfile, CallbackProfile]:
    return (
        CallbackProfile(backend="none", enabled=False),
        CallbackProfile(backend="otel", enabled=True, endpoint="memory://otel"),
        CallbackProfile(
            backend="langfuse",
            enabled=True,
            endpoint="http://localhost:3000",
        ),
    )


def _request() -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-callback-regression",
        caller_module="unit-test",
        target_schema="CallbackRegressionPayload",
        messages=[
            {
                "role": "user",
                "content": (
                    "name Alice phone 13900139000 account 123456789012 "
                    "acct id acct_ABC123"
                ),
            }
        ],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
        metadata={"account": "acct_ZYX987"},
    )


def _provider_profiles() -> list[ProviderProfile]:
    return [
        ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0),
        ProviderProfile(
            provider="anthropic",
            model="claude-sonnet-4.5",
            fallback_priority=1,
        ),
    ]


def _schema_registry() -> dict[str, type[BaseModel]]:
    return {"CallbackRegressionPayload": CallbackRegressionPayload}


def _client_factory(*, all_fail: bool = False) -> Any:
    def factory(profile: ProviderProfile, max_retries: int) -> _FakeClient:
        assert max_retries == 1
        return _FakeClient(profile, all_fail=all_fail)

    return factory


def _core_replay_fields(bundle_dump: dict[str, Any]) -> set[str]:
    return {
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    } & bundle_dump.keys()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _without_dynamic_contract_times(payload: dict[str, Any]) -> dict[str, Any]:
    stable_payload = deepcopy(payload)
    stable_payload.pop("completed_at", None)
    stable_payload.pop("recorded_at", None)
    request = stable_payload.get("request")
    if isinstance(request, dict):
        request.pop("requested_at", None)
    result = stable_payload.get("result")
    if isinstance(result, dict):
        result.pop("completed_at", None)
    return stable_payload


def _clear_callback_failure_counts() -> None:
    with core_engine._CALLBACK_FAILURE_LOCK:
        core_engine._CALLBACK_FAILURES.clear()


class _FakeClient:
    def __init__(self, profile: ProviderProfile, *, all_fail: bool) -> None:
        self.profile = profile
        self.all_fail = all_fail

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        callback_metadata: dict[str, Any],
    ) -> Any:
        if self.profile.provider == "openai" or self.all_fail:
            raise ConnectionError(
                f"{self.profile.provider}/{self.profile.model} unavailable "
                "name Alice phone 13900139000 account 123456789012 "
                "acct id acct_ABC123"
            )

        completion = SimpleNamespace(
            raw_output=RAW_OUTPUT,
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            response_cost=0.03,
            latency_ms=19,
        )
        return response_model(answer="fallback-ok", score=7), completion


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
        raise RuntimeError("callback backend failed")

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        raise RuntimeError("callback backend failed")

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        raise RuntimeError("callback backend failed")
