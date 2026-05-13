from __future__ import annotations

import pytest

import reasoner_runtime


def test_health_check_report_can_drive_phase_zero_gate() -> None:
    profiles = [
        reasoner_runtime.ProviderProfile(provider="openai", model="gpt-4"),
        reasoner_runtime.ProviderProfile(
            provider="anthropic",
            model="claude-sonnet-4.5",
        ),
    ]
    calls: list[tuple[str, str, float]] = []

    def ok_probe(
        profile: reasoner_runtime.ProviderProfile,
        timeout_s: float,
    ) -> reasoner_runtime.ProviderHealthStatus:
        calls.append((profile.provider, profile.model, timeout_s))
        return _status(
            profile,
            reachable=True,
            quota_status=reasoner_runtime.QuotaStatus.ok,
        )

    report = reasoner_runtime.health_check(profiles, probe=ok_probe, timeout_s=1.25)

    assert calls == [
        ("openai", "gpt-4", 1.25),
        ("anthropic", "claude-sonnet-4.5", 1.25),
    ]
    assert report.provider_statuses[0].provider == "openai"
    assert report.provider_statuses[1].provider == "anthropic"
    assert report.all_critical_targets_available is True
    assert report.summary == "all 2 critical provider/model target(s) available"


@pytest.mark.parametrize(
    ("reachable", "quota_status"),
    [
        (False, reasoner_runtime.QuotaStatus.ok),
        (True, reasoner_runtime.QuotaStatus.limited),
        (True, reasoner_runtime.QuotaStatus.exhausted),
    ],
)
def test_health_gate_fails_when_any_target_is_unavailable_or_quota_blocked(
    reachable: bool,
    quota_status: reasoner_runtime.QuotaStatus,
) -> None:
    profiles = [
        reasoner_runtime.ProviderProfile(provider="openai", model="gpt-4"),
        reasoner_runtime.ProviderProfile(provider="anthropic", model="claude"),
    ]

    def probe(
        profile: reasoner_runtime.ProviderProfile,
        timeout_s: float,
    ) -> reasoner_runtime.ProviderHealthStatus:
        if profile.provider == "anthropic":
            return _status(profile, reachable=reachable, quota_status=quota_status)
        return _status(
            profile,
            reachable=True,
            quota_status=reasoner_runtime.QuotaStatus.ok,
        )

    report = reasoner_runtime.health_check(profiles, probe=probe, timeout_s=1.0)

    assert report.all_critical_targets_available is False
    assert "unavailable" in report.summary
    assert len(report.provider_statuses) == 2


def _status(
    profile: reasoner_runtime.ProviderProfile,
    *,
    reachable: bool,
    quota_status: reasoner_runtime.QuotaStatus,
) -> reasoner_runtime.ProviderHealthStatus:
    return reasoner_runtime.ProviderHealthStatus(
        provider=profile.provider,
        model=profile.model,
        reachable=reachable,
        latency_ms=12,
        quota_status=quota_status,
        error=None if reachable else "unreachable",
    )
