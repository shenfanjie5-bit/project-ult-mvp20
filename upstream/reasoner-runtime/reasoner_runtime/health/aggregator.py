from __future__ import annotations

from reasoner_runtime.health.models import (
    HealthCheckReport,
    ProviderHealthStatus,
    QuotaStatus,
)


def aggregate_health_statuses(
    statuses: list[ProviderHealthStatus],
) -> HealthCheckReport:
    if not statuses:
        return HealthCheckReport(
            provider_statuses=[],
            all_critical_targets_available=False,
            summary="no provider/model targets were checked",
        )

    unavailable = [
        status
        for status in statuses
        if not status.reachable or status.quota_status != QuotaStatus.ok
    ]
    all_available = not unavailable

    if all_available:
        summary = f"all {len(statuses)} critical provider/model target(s) available"
    else:
        summary = (
            f"{len(statuses) - len(unavailable)}/{len(statuses)} critical "
            "provider/model target(s) available; unavailable: "
            + ", ".join(_status_summary(status) for status in unavailable)
        )

    return HealthCheckReport(
        provider_statuses=statuses,
        all_critical_targets_available=all_available,
        summary=summary,
    )


def _status_summary(status: ProviderHealthStatus) -> str:
    reason = (
        "unreachable"
        if not status.reachable
        else f"quota={status.quota_status.value}"
    )
    return f"{status.provider}/{status.model} ({reason})"
