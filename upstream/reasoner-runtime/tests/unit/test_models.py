from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

import reasoner_runtime
from reasoner_runtime.config import (
    CallbackProfile,
    DependencyLockEntry,
    ProviderProfile,
    ScrubRule,
    ScrubRuleSet,
)
from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.health import ProviderHealthStatus, QuotaStatus
from reasoner_runtime.providers import FailureClass, FallbackDecision
from reasoner_runtime.replay import ReplayBundle


def _contract_request() -> object:
    return ReasonerRequest(
        request_id="req-replay",
        caller_module="unit-test",
        target_schema="EntityResult",
        messages=[{"role": "user", "content": "hello"}],
        configured_provider="openai",
        configured_model="gpt-5.4",
        max_retries=2,
        metadata={"cycle_id": "cycle-replay"},
    ).to_contract()


def _contract_result() -> object:
    return StructuredGenerationResult(
        result_id="req-replay:result",
        request_id="req-replay",
        parsed_result={"answer": "ok"},
        actual_provider="openai",
        actual_model="gpt-5.4",
        token_usage={"prompt": 0, "completion": 0, "total": 0},
        cost_estimate=0,
        latency_ms=0,
    ).to_contract()


def test_reasoner_request_constructs_with_required_fields() -> None:
    request = ReasonerRequest(
        request_id="req-1",
        caller_module="main-core",
        target_schema="EntityResult",
        messages=[{"role": "user", "content": "hello"}],
        configured_provider="openai",
        configured_model="gpt-5.4",
        max_retries=2,
        metadata={"ticker": "AAPL"},
    )

    assert request.max_retries == 2
    assert request.metadata == {"ticker": "AAPL"}


def test_reasoner_request_requires_explicit_max_retries() -> None:
    with pytest.raises(ValidationError):
        ReasonerRequest(
            request_id="req-1",
            caller_module="main-core",
            target_schema="EntityResult",
            messages=[{"role": "user", "content": "hello"}],
            configured_provider="openai",
            configured_model="gpt-5.4",
        )


def test_reasoner_request_rejects_negative_max_retries() -> None:
    with pytest.raises(ValidationError):
        ReasonerRequest(
            request_id="req-1",
            caller_module="main-core",
            target_schema="EntityResult",
            messages=[{"role": "user", "content": "hello"}],
            configured_provider="openai",
            configured_model="gpt-5.4",
            max_retries=-1,
        )


def test_reasoner_request_metadata_default_is_isolated() -> None:
    first = ReasonerRequest(
        request_id="req-1",
        caller_module="main-core",
        target_schema="EntityResult",
        messages=[],
        configured_provider="openai",
        configured_model="gpt-5.4",
        max_retries=0,
    )
    second = ReasonerRequest(
        request_id="req-2",
        caller_module="main-core",
        target_schema="EntityResult",
        messages=[],
        configured_provider="openai",
        configured_model="gpt-5.4",
        max_retries=0,
    )

    first.metadata["cycle_id"] = "cycle-1"

    assert second.metadata == {}


def test_structured_generation_result_json_round_trip() -> None:
    result = StructuredGenerationResult(
        parsed_result={"answer": "ok"},
        actual_provider="openai",
        actual_model="gpt-5.4",
        fallback_path=["openai/gpt-5.4"],
        retry_count=1,
        token_usage={"prompt": 10, "completion": 5, "total": 15},
        cost_estimate=0.01,
        latency_ms=120,
    )

    restored = StructuredGenerationResult.model_validate_json(result.model_dump_json())

    assert restored == result


def test_structured_generation_result_defaults() -> None:
    result = StructuredGenerationResult(
        parsed_result={"answer": "ok"},
        actual_provider="openai",
        actual_model="gpt-5.4",
        token_usage={"prompt": 10, "completion": 5, "total": 15},
        cost_estimate=0.01,
        latency_ms=120,
    )

    assert result.fallback_path == []
    assert result.retry_count == 0
    assert result.configured_target is None
    assert result.failure_class == "none"


def test_replay_bundle_constructs_with_core_five_fields() -> None:
    bundle = ReplayBundle(
        sanitized_input="hello",
        input_hash="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        raw_output='{"answer": "ok"}',
        parsed_result={"answer": "ok"},
        output_hash="hash",
        llm_lineage={"provider": "openai", "model": "gpt-5.4"},
        request=_contract_request(),
        result=_contract_result(),
    )

    assert bundle.sanitized_input == "hello"
    assert bundle.parsed_result == {"answer": "ok"}


@pytest.mark.parametrize(
    "missing_field",
    ["sanitized_input", "input_hash", "raw_output", "parsed_result", "output_hash"],
)
def test_replay_bundle_requires_each_core_field(missing_field: str) -> None:
    payload = {
        "sanitized_input": "hello",
        "input_hash": "input-hash",
        "raw_output": "{}",
        "parsed_result": {},
        "output_hash": "output-hash",
        "llm_lineage": {},
        "request": _contract_request(),
        "result": _contract_result(),
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ReplayBundle(**payload)


@pytest.mark.parametrize("missing_field", ["request", "result"])
def test_replay_bundle_requires_contract_identity(missing_field: str) -> None:
    payload = {
        "sanitized_input": "hello",
        "input_hash": "input-hash",
        "raw_output": "{}",
        "parsed_result": {},
        "output_hash": "output-hash",
        "llm_lineage": {},
        "request": _contract_request(),
        "result": _contract_result(),
    }
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        ReplayBundle(**payload)


def test_provider_health_status_accepts_quota_enum() -> None:
    status = ProviderHealthStatus(
        provider="openai",
        model="gpt-5.4",
        reachable=True,
        latency_ms=50,
        quota_status="ok",
    )

    assert status.quota_status is QuotaStatus.ok
    assert status.error is None


def test_provider_health_status_rejects_unknown_quota_status() -> None:
    with pytest.raises(ValidationError):
        ProviderHealthStatus(
            provider="openai",
            model="gpt-5.4",
            reachable=True,
            latency_ms=50,
            quota_status="degraded",
        )


def test_fallback_decision_defaults() -> None:
    decision = FallbackDecision(configured_target="openai/gpt-5.4")

    assert decision.attempts == []
    assert decision.final_target is None
    assert decision.failure_class is FailureClass.none
    assert decision.terminal_reason is None


def test_fallback_decision_represents_success_with_fallback() -> None:
    decision = FallbackDecision(
        configured_target="openai/gpt-5.4",
        attempts=["openai/gpt-5.4", "anthropic/claude-sonnet-4.5"],
        final_target="anthropic/claude-sonnet-4.5",
        failure_class=FailureClass.success_with_fallback,
    )

    assert decision.failure_class is FailureClass.success_with_fallback
    assert decision.model_dump(mode="json")["failure_class"] == "success_with_fallback"


def test_fallback_decision_rejects_unknown_failure_class() -> None:
    with pytest.raises(ValidationError):
        FallbackDecision(
            configured_target="openai/gpt-5.4",
            failure_class="partial_failure",
        )


def test_provider_profile_constructs_with_defaults() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-5.4")

    assert profile.timeout_ms == 30000
    assert profile.fallback_priority == 0
    assert profile.rate_limit_rpm is None


def test_provider_profile_json_round_trip() -> None:
    profile = ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        timeout_ms=15000,
        fallback_priority=1,
        rate_limit_rpm=60,
    )

    assert ProviderProfile.model_validate_json(profile.model_dump_json()) == profile


def test_scrub_rule_set_constructs_rules() -> None:
    rules = ScrubRuleSet(
        rules=[
            ScrubRule(pattern_type="name"),
            ScrubRule(pattern_type="phone", enabled=False),
            ScrubRule(pattern_type="account"),
        ]
    )

    assert rules.enabled is True
    assert [rule.pattern_type for rule in rules.rules] == ["name", "phone", "account"]


def test_scrub_rule_rejects_unknown_pattern_type() -> None:
    with pytest.raises(ValidationError):
        ScrubRule(pattern_type="email")


def test_callback_profile_defaults() -> None:
    profile = CallbackProfile()

    assert profile.backend == "none"
    assert profile.endpoint is None
    assert profile.enabled is False


def test_callback_profile_rejects_unknown_backend() -> None:
    with pytest.raises(ValidationError):
        CallbackProfile(backend="stdout")


def test_dependency_lock_entry_constructs() -> None:
    lock = DependencyLockEntry(
        package="litellm",
        version="1.83.0",
        sha256="9b74c9897bac770ffc029102a200c5de3b4bb65a7dfc7cb0d131d9b27f67f6e4",
    )

    assert lock.package == "litellm"
    assert len(lock.sha256) == 64


def test_top_level_exports_key_models() -> None:
    assert reasoner_runtime.__version__ == "0.1.1"
    assert reasoner_runtime.ReasonerRequest is ReasonerRequest
    assert reasoner_runtime.ReplayBundle is ReplayBundle
    assert reasoner_runtime.ProviderProfile is ProviderProfile


@pytest.mark.parametrize(
    "module_name",
    [
        "reasoner_runtime.core",
        "reasoner_runtime.providers",
        "reasoner_runtime.structured",
        "reasoner_runtime.scrub",
        "reasoner_runtime.callbacks",
        "reasoner_runtime.health",
        "reasoner_runtime.replay",
        "reasoner_runtime.config",
    ],
)
def test_all_submodules_are_importable(module_name: str) -> None:
    assert importlib.import_module(module_name)
