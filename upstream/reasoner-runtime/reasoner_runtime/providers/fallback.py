from __future__ import annotations

from collections.abc import Callable

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.providers.models import (
    FailureClass,
    FallbackDecision,
    to_reasoner_error_classification,
)
from reasoner_runtime.providers.routing import (
    NoAvailableProviderError,
    ParseValidationError,
    classify_failure,
)


ProviderCall = Callable[
    [ReasonerRequest, ProviderProfile, int],
    StructuredGenerationResult,
]


class FallbackExecutionError(RuntimeError):
    def __init__(
        self,
        decision: FallbackDecision,
        last_error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.last_error = last_error
        message = decision.terminal_reason or "fallback execution failed"
        super().__init__(message)


def format_provider_target(profile: ProviderProfile) -> str:
    provider_prefix = f"{profile.provider}/"
    if profile.model.startswith(provider_prefix):
        return profile.model

    return f"{profile.provider}/{profile.model}"


def ordered_fallback_chain(
    request: ReasonerRequest,
    profiles: list[ProviderProfile],
) -> list[ProviderProfile]:
    if not profiles:
        raise NoAvailableProviderError("at least one provider profile is required")

    configured_target = _format_request_target(request)
    selected_profiles: list[ProviderProfile] = []
    selected_targets: set[str] = set()

    for profile in sorted(profiles, key=lambda item: item.fallback_priority):
        target = format_provider_target(profile)
        if target == configured_target and target not in selected_targets:
            selected_profiles.append(profile)
            selected_targets.add(target)
            break

    for profile in sorted(profiles, key=lambda item: item.fallback_priority):
        target = format_provider_target(profile)
        if target in selected_targets:
            continue
        selected_profiles.append(profile)
        selected_targets.add(target)

    return selected_profiles


def execute_with_fallback(
    request: ReasonerRequest,
    profiles: list[ProviderProfile],
    call_fn: ProviderCall,
) -> tuple[StructuredGenerationResult, FallbackDecision]:
    configured_target = _format_request_target(request)

    try:
        fallback_chain = ordered_fallback_chain(request, profiles)
    except NoAvailableProviderError as error:
        decision = FallbackDecision(
            configured_target=configured_target,
            failure_class=FailureClass.infra_level,
            terminal_reason=str(error),
            error_classification=to_reasoner_error_classification(
                FailureClass.infra_level,
                error=error,
                context={"configured_target": configured_target},
            ),
        )
        raise FallbackExecutionError(decision, error) from error

    attempts: list[str] = []
    last_error: Exception | None = None
    had_infra_failure = False

    for profile in fallback_chain:
        target = format_provider_target(profile)
        attempts.append(target)

        for retry_index in range(request.max_retries + 1):
            try:
                result = call_fn(request, profile, retry_index)
            except ParseValidationError as error:
                last_error = error
                if retry_index < request.max_retries:
                    continue

                decision = FallbackDecision(
                    configured_target=configured_target,
                    attempts=attempts.copy(),
                    final_target=target,
                    failure_class=FailureClass.task_level,
                    terminal_reason=str(error),
                    error_classification=to_reasoner_error_classification(
                        FailureClass.task_level,
                        error=error,
                        context={
                            "configured_target": configured_target,
                            "attempts": attempts.copy(),
                            "final_target": target,
                            "provider": profile.provider,
                            "model": profile.model,
                            "target": target,
                            "phase": "parse",
                        },
                    ),
                )
                raise FallbackExecutionError(decision, error) from error
            except Exception as error:
                last_error = error
                failure_class = classify_failure(
                    error,
                    {
                        "failure_source": "provider",
                        "provider": profile.provider,
                        "model": profile.model,
                        "target": target,
                    },
                )
                if failure_class is FailureClass.task_level:
                    decision = FallbackDecision(
                        configured_target=configured_target,
                        attempts=attempts.copy(),
                        final_target=target,
                        failure_class=FailureClass.task_level,
                        terminal_reason=str(error),
                        error_classification=to_reasoner_error_classification(
                            FailureClass.task_level,
                            error=error,
                            context={
                                "configured_target": configured_target,
                                "attempts": attempts.copy(),
                                "final_target": target,
                                "provider": profile.provider,
                                "model": profile.model,
                                "target": target,
                                "failure_source": "provider",
                            },
                        ),
                    )
                    raise FallbackExecutionError(decision, error) from error

                had_infra_failure = True
                break
            else:
                failure_class = (
                    FailureClass.success_with_fallback
                    if had_infra_failure
                    else FailureClass.none
                )
                result = result.model_copy(
                    update={
                        "actual_provider": profile.provider,
                        "actual_model": profile.model,
                        "configured_target": configured_target,
                        "failure_class": failure_class.value,
                        "fallback_path": attempts.copy(),
                        "retry_count": retry_index,
                    }
                )
                decision = FallbackDecision(
                    configured_target=configured_target,
                    attempts=attempts.copy(),
                    final_target=target,
                    failure_class=failure_class,
                )
                return result, decision

    terminal_reason = (
        str(last_error) if last_error is not None else "fallback chain exhausted"
    )
    decision = FallbackDecision(
        configured_target=configured_target,
        attempts=attempts.copy(),
        failure_class=FailureClass.infra_level,
        terminal_reason=terminal_reason,
        error_classification=to_reasoner_error_classification(
            FailureClass.infra_level,
            error=last_error,
            context={
                "configured_target": configured_target,
                "attempts": attempts.copy(),
                "failure_source": "provider" if attempts else "routing",
            },
        ),
    )
    raise FallbackExecutionError(decision, last_error)


def _format_request_target(request: ReasonerRequest) -> str:
    provider_prefix = f"{request.configured_provider}/"
    if request.configured_model.startswith(provider_prefix):
        return request.configured_model

    return f"{request.configured_provider}/{request.configured_model}"
