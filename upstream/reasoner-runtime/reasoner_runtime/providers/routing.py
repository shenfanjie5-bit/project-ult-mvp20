from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers.models import FailureClass


class ProviderRoutingError(RuntimeError):
    """Base error for provider routing and configuration failures."""


class NoAvailableProviderError(ProviderRoutingError):
    """Raised when no provider profile can be selected."""


class ProviderConfigError(ProviderRoutingError):
    """Raised when provider configuration cannot be used for routing."""


class ParseValidationError(ValueError):
    """Raised when structured output cannot be parsed into the target schema."""


def select_provider(
    configured_provider: str,
    configured_model: str,
    profiles: list[ProviderProfile],
) -> ProviderProfile:
    if not profiles:
        raise NoAvailableProviderError("at least one provider profile is required")

    sorted_profiles = sorted(profiles, key=lambda profile: profile.fallback_priority)
    for profile in sorted_profiles:
        if (
            profile.provider == configured_provider
            and profile.model == configured_model
        ):
            return profile

    return sorted_profiles[0]


def classify_failure(error: Exception, context: dict[str, Any]) -> FailureClass:
    failure_source = context.get("failure_source") or context.get("phase")
    if isinstance(error, (NoAvailableProviderError, ProviderConfigError)):
        return FailureClass.infra_level
    if _is_litellm_infra_error(error):
        return FailureClass.infra_level
    if isinstance(error, (ConnectionError, TimeoutError)):
        return FailureClass.infra_level
    if isinstance(error, ParseValidationError) or (
        failure_source == "parse" and isinstance(error, (ValueError, ValidationError))
    ):
        return FailureClass.task_level
    if isinstance(error, ValidationError):
        return FailureClass.infra_level
    return FailureClass.infra_level


def _is_litellm_infra_error(error: Exception) -> bool:
    infra_error_names = {
        "APIConnectionError",
        "APITimeoutError",
        "AuthenticationError",
        "BudgetExceededError",
        "InternalServerError",
        "RateLimitError",
        "ServiceUnavailableError",
        "Timeout",
    }
    return any(cls.__name__ in infra_error_names for cls in type(error).mro())
