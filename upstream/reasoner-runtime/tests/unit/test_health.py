from __future__ import annotations

from typing import Any

import pytest
from contracts.core import HeartbeatStatus
from contracts.schemas.reasoner import ReasonerErrorCategory
from pydantic import ValidationError

from reasoner_runtime.config import ProviderProfile
from reasoner_runtime.health import (
    HealthCheckReport,
    ProviderHealthStatus,
    QuotaStatus,
    aggregate_health_statuses,
    health_check,
)
from reasoner_runtime.health.checker import (
    _quota_status_from_error,
    _safe_error_summary,
    probe_provider,
)


class RateLimitError(Exception):
    pass


class BudgetExceededError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class StatusError(Exception):
    def __init__(self, status_code: int, message: str = "provider error") -> None:
        super().__init__(message)
        self.status_code = status_code


def _status(**overrides: Any) -> ProviderHealthStatus:
    payload = {
        "provider": "openai",
        "model": "gpt-4",
        "reachable": True,
        "latency_ms": 1,
        "quota_status": QuotaStatus.ok,
    }
    payload.update(overrides)
    return ProviderHealthStatus(**payload)


def _profile(
    provider: str = "openai",
    model: str = "gpt-4",
    timeout_ms: int = 30000,
) -> ProviderProfile:
    return ProviderProfile(provider=provider, model=model, timeout_ms=timeout_ms)


def test_provider_health_status_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        _status(latency_ms=-1)

    assert _status(latency_ms=0).latency_ms == 0


def test_health_check_report_json_preserves_public_fields() -> None:
    report = HealthCheckReport(
        provider_statuses=[_status()],
        all_critical_targets_available=True,
        summary="ok",
    )

    dump = report.model_dump(mode="json")

    assert dump["provider_statuses"] == [
        {
            "provider": "openai",
            "model": "gpt-4",
            "reachable": True,
            "latency_ms": 1,
            "quota_status": "ok",
            "error": None,
        }
    ]
    assert dump["all_critical_targets_available"] is True
    assert dump["summary"] == "ok"
    assert dump["subsystem_id"] == "reasoner-runtime"
    assert dump["status"] == "ok"
    assert dump["pending_count"] == 0


def test_aggregate_health_statuses_passes_only_when_all_targets_are_available() -> None:
    report = aggregate_health_statuses(
        [
            _status(provider="openai", model="gpt-4"),
            _status(provider="anthropic", model="claude-sonnet-4.5"),
        ]
    )

    assert report.all_critical_targets_available is True
    assert len(report.provider_statuses) == 2


@pytest.mark.parametrize(
    "status",
    [
        _status(reachable=False, error="connection failed"),
        _status(quota_status=QuotaStatus.limited),
        _status(quota_status=QuotaStatus.exhausted),
    ],
)
def test_aggregate_health_statuses_fails_on_unreachable_or_quota_issue(
    status: ProviderHealthStatus,
) -> None:
    report = aggregate_health_statuses([_status(), status])

    assert report.all_critical_targets_available is False
    assert "unavailable" in report.summary
    assert report.error_classification is not None
    assert report.error_classification.category in {
        ReasonerErrorCategory.MODEL_PROVIDER,
        ReasonerErrorCategory.TIMEOUT,
    }


def test_aggregate_health_statuses_empty_list_does_not_pass_gate() -> None:
    report = aggregate_health_statuses([])

    assert report.provider_statuses == []
    assert report.all_critical_targets_available is False
    assert report.status is HeartbeatStatus.FAILED
    assert report.error_classification is not None
    assert report.error_classification.category is ReasonerErrorCategory.INTERNAL


def test_aggregate_health_statuses_marks_exhausted_quota_non_retryable() -> None:
    report = aggregate_health_statuses(
        [_status(reachable=False, quota_status=QuotaStatus.exhausted)]
    )

    assert report.error_classification is not None
    assert report.error_classification.category is ReasonerErrorCategory.MODEL_PROVIDER
    assert report.error_classification.retryable is False


@pytest.mark.parametrize(
    ("error", "reachable", "expected"),
    [
        (None, True, QuotaStatus.ok),
        (RateLimitError("rate limit exceeded"), False, QuotaStatus.limited),
        (RuntimeError("provider response is limited"), False, QuotaStatus.limited),
        (RuntimeError("provider has unlimited capacity"), False, QuotaStatus.ok),
        (AuthenticationError("invalid api key"), False, QuotaStatus.exhausted),
        (BudgetExceededError("budget exceeded"), False, QuotaStatus.exhausted),
        (RuntimeError("quota exhausted"), False, QuotaStatus.exhausted),
        (RuntimeError("auth failed"), False, QuotaStatus.exhausted),
        (RuntimeError("authored response failed"), False, QuotaStatus.ok),
        (StatusError(401), False, QuotaStatus.exhausted),
        (StatusError(429), False, QuotaStatus.limited),
        (TimeoutError("timed out"), False, QuotaStatus.ok),
        (ConnectionError("connection refused"), False, QuotaStatus.ok),
    ],
)
def test_quota_status_from_error(
    error: Exception | None,
    reachable: bool,
    expected: QuotaStatus,
) -> None:
    assert _quota_status_from_error(error, reachable) is expected


def test_safe_error_summary_scrubs_pii_and_truncates() -> None:
    error = RuntimeError(
        "姓名 张三 name Alice 手机 13800138000 "
        "账户 6222021234567890123 account_id=acct_123456 "
        + ("x" * 300)
    )

    summary = _safe_error_summary(error)

    assert "张三" not in summary
    assert "Alice" not in summary
    assert "13800138000" not in summary
    assert "6222021234567890123" not in summary
    assert "acct_123456" not in summary
    assert "[REDACTED_NAME]" in summary
    assert "[REDACTED_PHONE]" in summary
    assert "[REDACTED_ACCOUNT]" in summary
    assert len(summary) <= 240


def test_health_check_uses_fake_probe_for_each_profile_and_normalizes_identity() -> None:
    profiles = [
        _profile("openai", "gpt-4"),
        _profile("anthropic", "claude-sonnet-4.5"),
    ]
    calls: list[tuple[str, str, float]] = []

    def probe(profile: ProviderProfile, timeout_s: float) -> ProviderHealthStatus:
        calls.append((profile.provider, profile.model, timeout_s))
        return _status(provider="wrong", model="wrong")

    report = health_check(profiles, probe=probe, timeout_s=1.5)

    assert calls == [
        ("openai", "gpt-4", 1.5),
        ("anthropic", "claude-sonnet-4.5", 1.5),
    ]
    assert [
        (status.provider, status.model) for status in report.provider_statuses
    ] == [
        ("openai", "gpt-4"),
        ("anthropic", "claude-sonnet-4.5"),
    ]


def test_health_check_default_probe_timeout_contract_is_sequential() -> None:
    profiles = [_profile("openai", "gpt-4"), _profile("anthropic", "claude")]
    calls: list[tuple[str, float, int]] = []

    def probe(profile: ProviderProfile, timeout_s: float) -> ProviderHealthStatus:
        calls.append((profile.provider, timeout_s, len(calls)))
        return _status(provider=profile.provider, model=profile.model)

    health_check(profiles, probe=probe)

    assert calls == [("openai", 3.0, 0), ("anthropic", 3.0, 1)]


def test_health_check_converts_probe_error_and_continues() -> None:
    profiles = [_profile("openai", "gpt-4"), _profile("anthropic", "claude")]
    calls: list[str] = []

    def probe(profile: ProviderProfile, timeout_s: float) -> ProviderHealthStatus:
        calls.append(profile.provider)
        if profile.provider == "openai":
            raise TimeoutError("name Alice phone 13800138000 timed out")
        return _status(provider=profile.provider, model=profile.model)

    report = health_check(profiles, probe=probe)

    assert calls == ["openai", "anthropic"]
    assert report.all_critical_targets_available is False
    assert report.provider_statuses[0].reachable is False
    assert report.provider_statuses[0].quota_status is QuotaStatus.ok
    assert "Alice" not in (report.provider_statuses[0].error or "")
    assert "13800138000" not in (report.provider_statuses[0].error or "")
    assert report.provider_statuses[1].reachable is True


def test_probe_provider_uses_strictest_timeout_and_normalized_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def completion(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setitem(
        __import__("sys").modules,
        "litellm",
        type("FakeLiteLLM", (), {"completion": staticmethod(completion)}),
    )

    status = probe_provider(_profile("openai", "gpt-4", timeout_ms=2500), timeout_s=3.0)

    assert status.reachable is True
    assert status.quota_status is QuotaStatus.ok
    assert calls[0]["model"] == "openai/gpt-4"
    assert calls[0]["timeout"] == 2.5

    probe_provider(_profile("openai", "gpt-4", timeout_ms=30000), timeout_s=3.0)
    assert calls[1]["timeout"] == 3.0


def test_probe_provider_uses_structured_client_for_codex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import reasoner_runtime.health.checker as checker

    calls: list[tuple[ProviderProfile, int]] = []

    class FakeStructuredClient:
        def __init__(self) -> None:
            self.http = type("FakeHttp", (), {"close": lambda self: None})()

        def create_structured(
            self,
            *,
            messages: list[dict[str, Any]],
            response_model: type[Any],
            metadata: dict[str, Any],
        ) -> object:
            assert messages
            assert metadata["reasoner_runtime_health_check"] is True
            return type("Result", (), {"parsed_result": {"ok": True}})()

    def build_client(profile: ProviderProfile, max_retries: int) -> object:
        calls.append((profile, max_retries))
        return FakeStructuredClient()

    monkeypatch.setattr(checker, "build_client", build_client)

    status = probe_provider(
        _profile("openai-codex", "gpt-5.5", timeout_ms=60000),
        timeout_s=5.0,
    )

    assert status.reachable is True
    assert status.quota_status is QuotaStatus.ok
    assert calls == [
        (
            ProviderProfile(
                provider="openai-codex",
                model="gpt-5.5",
                timeout_ms=5000,
            ),
            0,
        )
    ]
