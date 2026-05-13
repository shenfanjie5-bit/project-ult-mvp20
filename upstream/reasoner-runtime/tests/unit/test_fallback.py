from __future__ import annotations

from typing import Any

import pytest
from contracts.schemas.reasoner import ReasonerErrorCategory
from pydantic import ValidationError

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers import (
    FailureClass,
    FallbackDecision,
    FallbackExecutionError,
    NoAvailableProviderError,
    ParseValidationError,
    classify_failure,
    execute_with_fallback,
    format_provider_target,
    ordered_fallback_chain,
    to_reasoner_error_classification,
)


def _request(**overrides: Any) -> ReasonerRequest:
    payload = {
        "request_id": "req-1",
        "caller_module": "unit-test",
        "target_schema": "AnswerPayload",
        "messages": [{"role": "user", "content": "hello"}],
        "configured_provider": "openai",
        "configured_model": "gpt-4",
        "max_retries": 2,
    }
    payload.update(overrides)
    return ReasonerRequest(**payload)


def _profile(
    provider: str = "openai",
    model: str = "gpt-4",
    fallback_priority: int = 0,
) -> ProviderProfile:
    return ProviderProfile(
        provider=provider,
        model=model,
        fallback_priority=fallback_priority,
    )


def _result(
    provider: str = "placeholder",
    model: str = "placeholder-model",
) -> StructuredGenerationResult:
    return StructuredGenerationResult(
        parsed_result={"answer": "ok"},
        actual_provider=provider,
        actual_model=model,
        fallback_path=["stale/path"],
        retry_count=99,
        token_usage={"prompt": 1, "completion": 1, "total": 2},
        cost_estimate=0.0,
        latency_ms=1,
    )


def test_format_provider_target_does_not_duplicate_provider_prefix() -> None:
    profile = _profile(provider="openai", model="openai/gpt-4")

    assert format_provider_target(profile) == "openai/gpt-4"


def test_ordered_fallback_chain_puts_configured_target_first_and_dedupes() -> None:
    configured_late = _profile("openai", "gpt-4", 5)
    configured_early = _profile("openai", "openai/gpt-4", 3)
    fallback = _profile("anthropic", "claude-sonnet-4.5", 0)
    duplicate_fallback = _profile("anthropic", "anthropic/claude-sonnet-4.5", 6)

    chain = ordered_fallback_chain(
        _request(configured_provider="openai", configured_model="gpt-4"),
        [fallback, duplicate_fallback, configured_late, configured_early],
    )

    assert chain == [configured_early, fallback]
    assert [format_provider_target(profile) for profile in chain] == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]


def test_ordered_fallback_chain_uses_priority_when_configured_target_missing() -> None:
    first = _profile("anthropic", "claude-sonnet-4.5", 0)
    duplicate = _profile("anthropic", "anthropic/claude-sonnet-4.5", 5)
    second = _profile("openai", "gpt-4", 2)

    chain = ordered_fallback_chain(
        _request(configured_provider="missing", configured_model="missing-model"),
        [second, duplicate, first],
    )

    assert chain == [first, second]


def test_ordered_fallback_chain_rejects_empty_profiles() -> None:
    with pytest.raises(NoAvailableProviderError):
        ordered_fallback_chain(_request(), [])


def test_execute_with_fallback_returns_primary_success_decision() -> None:
    profile = _profile()
    calls: list[tuple[str, int]] = []

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        calls.append((format_provider_target(call_profile), retry_index))
        return _result()

    result, decision = execute_with_fallback(_request(), [profile], call_fn)

    assert calls == [("openai/gpt-4", 0)]
    assert result.actual_provider == "openai"
    assert result.actual_model == "gpt-4"
    assert result.configured_target == "openai/gpt-4"
    assert result.failure_class == "none"
    assert result.fallback_path == ["openai/gpt-4"]
    assert result.retry_count == 0
    assert decision.failure_class is FailureClass.none
    assert decision.attempts == ["openai/gpt-4"]
    assert decision.final_target == "openai/gpt-4"


def test_execute_with_fallback_records_success_with_fallback() -> None:
    primary = _profile("openai", "gpt-4", 0)
    fallback = _profile("anthropic", "claude-sonnet-4.5", 1)
    calls: list[str] = []

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        calls.append(format_provider_target(call_profile))
        if call_profile == primary:
            raise ConnectionError("primary unavailable")
        return _result()

    result, decision = execute_with_fallback(
        _request(),
        [primary, fallback],
        call_fn,
    )

    assert calls == ["openai/gpt-4", "anthropic/claude-sonnet-4.5"]
    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"
    assert result.configured_target == "openai/gpt-4"
    assert result.failure_class == "success_with_fallback"
    assert result.fallback_path == calls
    assert decision.failure_class is FailureClass.success_with_fallback
    assert decision.attempts == calls
    assert decision.final_target == "anthropic/claude-sonnet-4.5"


def test_execute_with_fallback_retries_parse_failure_on_current_provider() -> None:
    profile = _profile()
    retry_indexes: list[int] = []

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        retry_indexes.append(retry_index)
        if retry_index == 0:
            raise ParseValidationError("invalid structured output")
        return _result()

    result, decision = execute_with_fallback(_request(max_retries=2), [profile], call_fn)

    assert retry_indexes == [0, 1]
    assert result.retry_count == 1
    assert result.fallback_path == ["openai/gpt-4"]
    assert decision.failure_class is FailureClass.none
    assert decision.attempts == ["openai/gpt-4"]


def test_execute_with_fallback_does_not_retry_parse_failure_when_max_retries_zero() -> None:
    primary = _profile("openai", "gpt-4", 0)
    fallback = _profile("anthropic", "claude-sonnet-4.5", 1)
    calls: list[str] = []

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        calls.append(format_provider_target(call_profile))
        raise ParseValidationError("invalid structured output")

    with pytest.raises(FallbackExecutionError) as error:
        execute_with_fallback(
            _request(max_retries=0),
            [primary, fallback],
            call_fn,
        )

    assert calls == ["openai/gpt-4"]
    assert error.value.decision.failure_class is FailureClass.task_level
    assert error.value.decision.attempts == ["openai/gpt-4"]


def test_execute_with_fallback_exposes_task_level_after_parse_retries_exhausted() -> None:
    primary = _profile("openai", "gpt-4", 0)
    fallback = _profile("anthropic", "claude-sonnet-4.5", 1)
    retry_indexes: list[int] = []

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        retry_indexes.append(retry_index)
        raise ParseValidationError("still invalid")

    with pytest.raises(FallbackExecutionError) as error:
        execute_with_fallback(
            _request(max_retries=2),
            [primary, fallback],
            call_fn,
        )

    assert retry_indexes == [0, 1, 2]
    assert error.value.decision.failure_class is FailureClass.task_level
    assert error.value.decision.attempts == ["openai/gpt-4"]
    assert isinstance(error.value.last_error, ParseValidationError)


def test_execute_with_fallback_exposes_infra_level_when_all_targets_fail() -> None:
    primary = _profile("openai", "gpt-4", 0)
    fallback = _profile("anthropic", "claude-sonnet-4.5", 1)

    def call_fn(
        request: ReasonerRequest,
        call_profile: ProviderProfile,
        retry_index: int,
    ) -> StructuredGenerationResult:
        raise ConnectionError(f"{format_provider_target(call_profile)} down")

    with pytest.raises(FallbackExecutionError) as error:
        execute_with_fallback(_request(), [primary, fallback], call_fn)

    assert error.value.decision.failure_class is FailureClass.infra_level
    assert error.value.decision.error_classification is not None
    assert (
        error.value.decision.error_classification.category
        is ReasonerErrorCategory.MODEL_PROVIDER
    )
    assert error.value.decision.attempts == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert isinstance(error.value.last_error, ConnectionError)


def test_execute_with_fallback_exposes_infra_level_for_empty_profiles() -> None:
    with pytest.raises(FallbackExecutionError) as error:
        execute_with_fallback(_request(), [], lambda request, profile, retry: _result())

    assert error.value.decision.failure_class is FailureClass.infra_level
    assert error.value.decision.error_classification is not None
    assert (
        error.value.decision.error_classification.category
        is ReasonerErrorCategory.INTERNAL
    )
    assert error.value.decision.attempts == []
    assert isinstance(error.value.last_error, NoAvailableProviderError)


def test_failure_class_adapter_returns_contract_error_classification() -> None:
    classification = to_reasoner_error_classification(
        FailureClass.task_level,
        error=ParseValidationError("invalid structured output"),
        context={"phase": "parse", "target_schema": "AnswerPayload"},
    )

    assert classification is not None
    assert classification.category is ReasonerErrorCategory.INPUT_CONTRACT
    assert classification.code.value == "REASONER_INPUT_CONTRACT_ERROR"
    assert classification.retryable is False
    assert classification.details["failure_class"] == "task_level"
    assert classification.details["target_schema"] == "AnswerPayload"


def test_failure_class_adapter_marks_exhausted_quota_as_non_retryable() -> None:
    classification = to_reasoner_error_classification(
        FailureClass.infra_level,
        context={
            "provider": "openai",
            "model": "gpt-4",
            "quota_status": "exhausted",
        },
    )

    assert classification is not None
    assert classification.category is ReasonerErrorCategory.MODEL_PROVIDER
    assert classification.retryable is False


def test_fallback_decision_rejects_mismatched_error_classification() -> None:
    mismatched = to_reasoner_error_classification(
        FailureClass.task_level,
        context={"phase": "parse"},
    )

    with pytest.raises(ValidationError, match="does not match failure_class"):
        FallbackDecision(
            configured_target="openai/gpt-4",
            failure_class=FailureClass.infra_level,
            error_classification=mismatched,
        )


def test_fallback_decision_accepts_more_specific_non_retryable_classification() -> None:
    authentication_error = type("AuthenticationError", (Exception,), {})
    classification = to_reasoner_error_classification(
        FailureClass.infra_level,
        error=authentication_error("invalid api key"),
        context={"provider": "openai", "model": "gpt-4"},
    )

    decision = FallbackDecision(
        configured_target="openai/gpt-4",
        attempts=["openai/gpt-4"],
        final_target="openai/gpt-4",
        failure_class=FailureClass.infra_level,
        error_classification=classification,
    )

    assert decision.error_classification is not None
    assert decision.error_classification.retryable is False


@pytest.mark.parametrize(
    "error_name",
    [
        "RateLimitError",
        "AuthenticationError",
        "ServiceUnavailableError",
        "APITimeoutError",
        "APIConnectionError",
    ],
)
def test_classify_failure_marks_litellm_named_errors_as_infra_level(
    error_name: str,
) -> None:
    error_type = type(error_name, (ValueError,), {})

    assert (
        classify_failure(error_type("provider failed"), {"failure_source": "parse"})
        is FailureClass.infra_level
    )
