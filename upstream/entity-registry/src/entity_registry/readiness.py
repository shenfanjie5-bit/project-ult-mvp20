"""Production-readiness checks for entity-registry runtime wiring."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


_LOCAL_PROFILES = {"local", "test", "lite-local", "full-dev"}
_NON_GOALS = {
    "durable_backend": "adapter_contract_only",
    "reasoner_runtime": "injected_or_not_configured",
    "splink_backend": "not_proven",
}


@dataclass(frozen=True, slots=True)
class ProductionReadinessConfig:
    """Policy switches for repository/runtime readiness checks."""

    profile: str = "local"
    allow_in_memory_repositories: bool | None = None
    require_audit_uow: bool = True
    require_reasoner_client: bool = False
    require_fuzzy_backend: bool = False

    def __post_init__(self) -> None:
        profile = self.profile.strip().lower()
        object.__setattr__(self, "profile", profile)
        if self.allow_in_memory_repositories is None:
            object.__setattr__(self, "allow_in_memory_repositories", False)


@dataclass(frozen=True, slots=True)
class EntityRegistryRuntimeConfig:
    """Concrete runtime wiring checked by the readiness gate."""

    profile: str = "local"
    allow_in_memory_repositories: bool | None = None
    require_audit_uow: bool = True
    require_reasoner_client: bool = False
    require_fuzzy_backend: bool = False
    entity_repo: Any | None = None
    alias_repo: Any | None = None
    reference_repo: Any | None = None
    case_repo: Any | None = None
    reasoner_client: Any | None = None
    fuzzy_matcher: Any | None = None

    def readiness_config(self) -> ProductionReadinessConfig:
        return ProductionReadinessConfig(
            profile=self.profile,
            allow_in_memory_repositories=self.allow_in_memory_repositories,
            require_audit_uow=self.require_audit_uow,
            require_reasoner_client=self.require_reasoner_client,
            require_fuzzy_backend=self.require_fuzzy_backend,
        )


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One readiness check result with runner-local timing."""

    name: str
    status: str
    latency_ms: float
    error_type: str | None = None
    message: str | None = None
    non_goals: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "message": self.message,
            "non_goals": dict(self.non_goals),
        }


class ProductionReadinessError(RuntimeError):
    """Raised when runtime wiring cannot satisfy the readiness gate."""

    def __init__(self, checks: list[ReadinessCheck]) -> None:
        self.checks = checks
        failures = [check for check in checks if check.status == "failed"]
        message = "; ".join(
            f"{check.name}: {check.message or check.error_type or 'failed'}"
            for check in failures
        )
        super().__init__(message or "production readiness gate failed")


def check_runtime_readiness(
    runtime: EntityRegistryRuntimeConfig,
) -> list[ReadinessCheck]:
    """Run readiness checks and return structured results."""

    config = runtime.readiness_config()
    return [
        _timed_check(
            "repository_classes_allowed",
            lambda: _check_repository_classes_allowed(runtime, config),
        ),
        _timed_check(
            "public_resolution_repositories_configured",
            lambda: _check_public_resolution_repositories(runtime, config),
        ),
        _timed_check(
            "resolution_audit_uow",
            lambda: _check_resolution_audit_uow(runtime, config),
        ),
        _timed_check(
            "reasoner_client_configured",
            lambda: _check_reasoner_client(runtime, config),
        ),
        _timed_check(
            "fuzzy_backend_configured",
            lambda: _check_fuzzy_backend(runtime, config),
        ),
    ]


def assert_runtime_readiness(runtime: EntityRegistryRuntimeConfig) -> None:
    """Raise if any readiness check fails."""

    checks = check_runtime_readiness(runtime)
    if any(check.status == "failed" for check in checks):
        raise ProductionReadinessError(checks)


def runtime_config_from_defaults(
    config: ProductionReadinessConfig | None = None,
) -> EntityRegistryRuntimeConfig:
    """Build readiness input from the currently configured default repositories."""

    from entity_registry.init import _get_default_repository_context

    readiness_config = config or ProductionReadinessConfig()
    context = _get_default_repository_context()
    return EntityRegistryRuntimeConfig(
        profile=readiness_config.profile,
        allow_in_memory_repositories=readiness_config.allow_in_memory_repositories,
        require_audit_uow=readiness_config.require_audit_uow,
        require_reasoner_client=readiness_config.require_reasoner_client,
        require_fuzzy_backend=readiness_config.require_fuzzy_backend,
        entity_repo=context.entity_repo,
        alias_repo=context.alias_repo,
        reference_repo=context.reference_repo,
        case_repo=context.case_repo,
        reasoner_client=context.reasoner_client,
        fuzzy_matcher=context.fuzzy_matcher,
    )


def _timed_check(name: str, check: Any) -> ReadinessCheck:
    start = time.monotonic()
    try:
        check()
    except Exception as exc:
        return ReadinessCheck(
            name=name,
            status="failed",
            latency_ms=(time.monotonic() - start) * 1000.0,
            error_type=type(exc).__name__,
            message=str(exc),
            non_goals=dict(_NON_GOALS),
        )
    return ReadinessCheck(
        name=name,
        status="passed",
        latency_ms=(time.monotonic() - start) * 1000.0,
        error_type=None,
        message=None,
        non_goals=dict(_NON_GOALS),
    )


def _check_repository_classes_allowed(
    runtime: EntityRegistryRuntimeConfig,
    config: ProductionReadinessConfig,
) -> None:
    if config.profile in _LOCAL_PROFILES and config.allow_in_memory_repositories:
        return

    rejected = [
        name
        for name, repo in (
            ("entity_repo", runtime.entity_repo),
            ("alias_repo", runtime.alias_repo),
            ("reference_repo", runtime.reference_repo),
            ("case_repo", runtime.case_repo),
        )
        if _is_in_memory_repository(repo)
    ]
    if rejected:
        raise ValueError(
            "production profile rejects in-memory repositories: "
            + ", ".join(rejected),
        )


def _check_public_resolution_repositories(
    runtime: EntityRegistryRuntimeConfig,
    config: ProductionReadinessConfig,
) -> None:
    if not config.require_audit_uow:
        return
    if runtime.reference_repo is None or runtime.case_repo is None:
        raise ValueError(
            "public resolution requires reference_repo and case_repo audit sinks",
        )


def _check_resolution_audit_uow(
    runtime: EntityRegistryRuntimeConfig,
    config: ProductionReadinessConfig,
) -> None:
    if not config.require_audit_uow:
        return
    if runtime.reference_repo is None or runtime.case_repo is None:
        raise ValueError("resolution audit repositories are not configured")

    save_resolution = getattr(runtime.reference_repo, "save_resolution", None)
    if not callable(save_resolution):
        raise TypeError(
            "reference_repo must expose save_resolution(reference, case)",
        )

    owns_case_repo = getattr(
        runtime.reference_repo,
        "owns_resolution_case_repository",
        None,
    )
    if not callable(owns_case_repo):
        raise TypeError(
            "reference_repo must expose owns_resolution_case_repository(case_repo)",
        )
    if not owns_case_repo(runtime.case_repo):
        raise ValueError("reference_repo does not own the configured case_repo")


def _check_reasoner_client(
    runtime: EntityRegistryRuntimeConfig,
    config: ProductionReadinessConfig,
) -> None:
    if config.require_reasoner_client and runtime.reasoner_client is None:
        raise ValueError("reasoner_client is required but not configured")


def _check_fuzzy_backend(
    runtime: EntityRegistryRuntimeConfig,
    config: ProductionReadinessConfig,
) -> None:
    if config.require_fuzzy_backend and runtime.fuzzy_matcher is None:
        raise ValueError("fuzzy backend is required but not configured")


def _is_in_memory_repository(repo: Any | None) -> bool:
    if repo is None:
        return False
    return type(repo).__name__.startswith("InMemory")


__all__ = [
    "EntityRegistryRuntimeConfig",
    "ProductionReadinessConfig",
    "ProductionReadinessError",
    "ReadinessCheck",
    "assert_runtime_readiness",
    "check_runtime_readiness",
    "runtime_config_from_defaults",
]
