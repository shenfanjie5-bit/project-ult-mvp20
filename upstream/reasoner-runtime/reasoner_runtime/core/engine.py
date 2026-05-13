from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError as PydanticValidationError

from reasoner_runtime.callbacks import (
    CallbackBackend,
    CallbackContext,
    CallbackError,
    CallbackSuccess,
    build_callback_backends,
    configure_litellm_callbacks,
)
from reasoner_runtime.config.loader import (
    load_callback_profile,
    load_provider_profiles,
)
from reasoner_runtime.config.models import (
    CallbackProfile,
    ProviderProfile,
    ScrubRuleSet,
)
from reasoner_runtime.core.models import (
    _RUNTIME_CONTRACT_VERSION,
    _prompt_from_messages,
    ReasonerRequest,
    StructuredGenerationResult,
)
from reasoner_runtime.providers import (
    FallbackExecutionError,
    ParseValidationError,
    build_client,
    execute_with_fallback,
    to_reasoner_error_classification,
)
from reasoner_runtime.replay import (
    ReplayBundle,
    build_llm_lineage,
    build_replay_bundle,
)
from reasoner_runtime.scrub import scrub_request, scrub_text
from reasoner_runtime.structured import resolve_response_model, run_structured_call


ClientFactory = Callable[[ProviderProfile, int], Any]
_INSTRUCTOR_ATTEMPTS_PER_FALLBACK_RETRY = 1
_RUNTIME_CALLBACK_LOCK = RLock()
_LOGGER = logging.getLogger(__name__)

# Fan-out failure counter for observability — populated when a callback
# backend (Langfuse / OTEL / etc.) raises during on_start / on_success /
# on_error. Keyed by f"{event}:{backend_class_name}". Read via
# `callback_failure_counts()`. Backed by its own RLock so the hot path
# can update without contending with the runtime configure lock.
_CALLBACK_FAILURE_LOCK = RLock()
_CALLBACK_FAILURES: dict[str, int] = {}


def _record_callback_failure(
    event: str,
    backend: object,
    exc: BaseException,
) -> None:
    """Log a callback fan-out failure and bump its counter.

    Replaces the previous silent `except Exception: continue` swallow so
    misconfigured Langfuse / OTEL backends surface in the logs and a
    snapshot is queryable from tests / runbooks.
    """

    backend_name = type(backend).__name__
    key = f"{event}:{backend_name}"
    with _CALLBACK_FAILURE_LOCK:
        _CALLBACK_FAILURES[key] = _CALLBACK_FAILURES.get(key, 0) + 1
    _LOGGER.warning(
        "reasoner-runtime callback %s failed "
        "(backend=%s, exception_type=%s)",
        event,
        backend_name,
        type(exc).__name__,
    )


def callback_failure_counts() -> Mapping[str, int]:
    """Return a read-only snapshot of callback fan-out failure counts."""

    with _CALLBACK_FAILURE_LOCK:
        return dict(_CALLBACK_FAILURES)


def generate_structured(
    request: ReasonerRequest,
    *,
    schema_registry: Mapping[str, type[BaseModel]],
    provider_profiles: list[ProviderProfile] | None = None,
    provider_config_path: Path | None = None,
    client_factory: ClientFactory = build_client,
    scrub_rule_set: ScrubRuleSet | None = None,
    callback_profile: CallbackProfile | None = None,
    callback_config_path: Path | None = None,
    callback_backends: Sequence[CallbackBackend] | None = None,
) -> StructuredGenerationResult:
    """Generate structured output through the configured provider boundary.

    Callers may inject provider profiles directly or load them from a config
    path. Without either, the configured request target is converted into a
    single profile to preserve the provider boundary.
    """
    result, _bundle = _generate_structured_with_replay_impl(
        request,
        schema_registry=schema_registry,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
        client_factory=client_factory,
        scrub_rule_set=scrub_rule_set,
        callback_profile=callback_profile,
        callback_config_path=callback_config_path,
        callback_backends=callback_backends,
    )
    return result


def generate_structured_with_replay(
    request: ReasonerRequest,
    provider_profiles: list[ProviderProfile] | None = None,
    schema_registry: Mapping[str, type[BaseModel]] | None = None,
    client_factory: ClientFactory = build_client,
    *,
    provider_config_path: Path | None = None,
    scrub_rule_set: ScrubRuleSet | None = None,
    callback_profile: CallbackProfile | None = None,
    callback_config_path: Path | None = None,
    callback_backends: Sequence[CallbackBackend] | None = None,
) -> tuple[StructuredGenerationResult, ReplayBundle]:
    if schema_registry is None:
        raise TypeError("schema_registry is required")

    return _generate_structured_with_replay_impl(
        request,
        schema_registry=schema_registry,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
        client_factory=client_factory,
        scrub_rule_set=scrub_rule_set,
        callback_profile=callback_profile,
        callback_config_path=callback_config_path,
        callback_backends=callback_backends,
    )


def _generate_structured_with_replay_impl(
    request: ReasonerRequest,
    *,
    schema_registry: Mapping[str, type[BaseModel]],
    provider_profiles: list[ProviderProfile] | None,
    provider_config_path: Path | None,
    client_factory: ClientFactory,
    scrub_rule_set: ScrubRuleSet | None,
    callback_profile: CallbackProfile | None,
    callback_config_path: Path | None,
    callback_backends: Sequence[CallbackBackend] | None,
) -> tuple[StructuredGenerationResult, ReplayBundle]:
    normalized_request = _normalize_request(request)
    profiles = _resolve_provider_profiles(
        normalized_request,
        provider_profiles=provider_profiles,
        provider_config_path=provider_config_path,
    )
    with _RUNTIME_CALLBACK_LOCK:
        runtime_callback_backends = _resolve_runtime_callback_backends(
            callback_profile=callback_profile,
            callback_config_path=callback_config_path,
            direct_callback_backends=callback_backends,
        )
        configure_litellm_callbacks(runtime_callback_backends)
        callback_started_at = perf_counter()
        _emit_callback_start(normalized_request, runtime_callback_backends)
        try:
            scrubbed = scrub_request(
                normalized_request.messages,
                normalized_request.metadata,
                scrub_rule_set,
            )
            runtime_request = normalized_request.model_copy(
                update={
                    "messages": scrubbed.messages,
                    "metadata": scrubbed.metadata,
                    "prompt": _prompt_from_messages(scrubbed.messages),
                    "context": scrubbed.metadata,
                }
            )

            response_model = resolve_response_model(
                normalized_request.target_schema,
                schema_registry,
            )
            final_raw_output: str | None = None

            def call_provider(
                call_request: ReasonerRequest,
                profile: ProviderProfile,
                parse_retry_index: int,
            ) -> StructuredGenerationResult:
                nonlocal final_raw_output

                if parse_retry_index < 0:
                    raise ValueError(
                        "parse_retry_index must be greater than or equal to 0"
                    )

                # execute_with_fallback owns request.max_retries; Instructor
                # gets one attempt.
                client = client_factory(
                    profile,
                    _INSTRUCTOR_ATTEMPTS_PER_FALLBACK_RETRY,
                )
                try:
                    call_result = run_structured_call(
                        client,
                        call_request,
                        response_model,
                    )
                except Exception as error:
                    parse_error = _parse_error_from_instructor_retry(error)
                    if parse_error is not None:
                        raise parse_error from error
                    raise
                final_raw_output = call_result.raw_output

                return StructuredGenerationResult(
                    result_id=f"{call_request.request_id}:result"
                    if call_request.request_id
                    else "runtime-result",
                    request_id=call_request.request_id or "runtime-request",
                    reasoner_name=call_request.reasoner_name,
                    reasoner_version=call_request.reasoner_version
                    or _RUNTIME_CONTRACT_VERSION,
                    output=call_result.parsed_result,
                    completed_at=datetime.now(UTC),
                    parsed_result=call_result.parsed_result,
                    actual_provider=profile.provider,
                    actual_model=profile.model,
                    fallback_path=[],
                    token_usage=call_result.token_usage,
                    cost_estimate=call_result.cost_estimate,
                    latency_ms=call_result.latency_ms,
                )

            result, _decision = execute_with_fallback(
                runtime_request,
                profiles,
                call_provider,
            )
            if final_raw_output is None:
                raise RuntimeError("structured call did not produce raw output")

            lineage = build_llm_lineage(result)
            replay_bundle = build_replay_bundle(
                scrubbed.sanitized_input,
                final_raw_output,
                result.parsed_result,
                lineage,
                request=runtime_request,
                result=result,
            )
            _emit_callback_success(
                normalized_request,
                result,
                _decision.failure_class.value,
                runtime_callback_backends,
            )
            return result, replay_bundle
        except Exception as error:
            _emit_callback_error(
                normalized_request,
                error,
                runtime_callback_backends,
                callback_started_at,
            )
            raise
        finally:
            configure_litellm_callbacks(())


def _resolve_provider_profiles(
    request: ReasonerRequest,
    *,
    provider_profiles: list[ProviderProfile] | None,
    provider_config_path: Path | None,
) -> list[ProviderProfile]:
    if provider_profiles is not None and provider_config_path is not None:
        raise ValueError(
            "provider_profiles and provider_config_path cannot both be provided"
        )

    if provider_profiles is not None:
        return provider_profiles

    if provider_config_path is not None:
        return load_provider_profiles(provider_config_path)

    return [
        ProviderProfile(
            provider=request.configured_provider,
            model=request.configured_model,
            fallback_priority=0,
        )
    ]


def _resolve_runtime_callback_backends(
    *,
    callback_profile: CallbackProfile | None,
    callback_config_path: Path | None,
    direct_callback_backends: Sequence[CallbackBackend] | None,
) -> tuple[CallbackBackend, ...]:
    if callback_profile is not None and callback_config_path is not None:
        raise ValueError(
            "callback_profile and callback_config_path cannot both be provided"
        )

    resolved_profile = (
        load_callback_profile(callback_config_path)
        if callback_config_path is not None
        else callback_profile
    )
    configured_backends = build_callback_backends(resolved_profile)
    return (*configured_backends, *tuple(direct_callback_backends or ()))


def _emit_callback_start(
    request: ReasonerRequest,
    backends: Sequence[CallbackBackend],
) -> None:
    if not backends:
        return

    context = _callback_context(
        request,
        provider=request.configured_provider,
        model=request.configured_model,
    )
    for backend in backends:
        try:
            backend.on_start(context)
        except Exception as exc:
            _record_callback_failure("on_start", backend, exc)
            continue


def _emit_callback_success(
    request: ReasonerRequest,
    result: StructuredGenerationResult,
    failure_class: str,
    backends: Sequence[CallbackBackend],
) -> None:
    if not backends:
        return

    context = _callback_context(
        request,
        provider=result.actual_provider,
        model=result.actual_model,
    )
    success = CallbackSuccess(
        token_usage=result.token_usage,
        cost_estimate=result.cost_estimate,
        latency_ms=result.latency_ms,
        fallback_path=result.fallback_path,
        retry_count=result.retry_count,
        failure_class=failure_class,
    )
    for backend in backends:
        try:
            backend.on_success(context, success)
        except Exception as exc:
            _record_callback_failure("on_success", backend, exc)
            continue


def _emit_callback_error(
    request: ReasonerRequest,
    error: Exception,
    backends: Sequence[CallbackBackend],
    started_at: float,
) -> None:
    if not backends:
        return

    provider, model = _callback_error_target(request, error)
    context = _callback_context(request, provider=provider, model=model)
    callback_error = CallbackError(
        error_type=type(error).__name__,
        error_message=scrub_text(str(error)),
        failure_class=_callback_failure_class(error),
        error_classification=_callback_error_classification(request, error),
        latency_ms=max(int((perf_counter() - started_at) * 1000), 0),
    )
    for backend in backends:
        try:
            backend.on_error(context, callback_error)
        except Exception as exc:
            _record_callback_failure("on_error", backend, exc)
            continue


_TRACE_METADATA_KEYS: tuple[str, ...] = (
    "cycle_id",
    "ticker",
    "analyzer_type",
    "regime_label",
)


def _trace_metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key) if metadata else None
    return "" if value is None else str(value)


def _callback_context(
    request: ReasonerRequest,
    *,
    provider: str,
    model: str,
) -> CallbackContext:
    metadata = request.metadata or {}
    return CallbackContext(
        request_id=request.request_id,
        caller_module=request.caller_module,
        target_schema=request.target_schema,
        provider=provider,
        model=model,
        cycle_id=_trace_metadata_value(metadata, "cycle_id"),
        ticker=_trace_metadata_value(metadata, "ticker"),
        analyzer_type=_trace_metadata_value(metadata, "analyzer_type"),
        regime_label=_trace_metadata_value(metadata, "regime_label"),
    )


def _callback_error_target(
    request: ReasonerRequest,
    error: Exception,
) -> tuple[str, str]:
    if isinstance(error, FallbackExecutionError) and error.decision.final_target:
        provider, _, model = error.decision.final_target.partition("/")
        if provider and model:
            return provider, model

    return request.configured_provider, request.configured_model


def _callback_failure_class(error: Exception) -> str:
    if isinstance(error, FallbackExecutionError):
        return error.decision.failure_class.value
    if isinstance(error, ParseValidationError):
        return "task_level"
    return "infra_level"


def _callback_error_classification(
    request: ReasonerRequest,
    error: Exception,
) -> Any:
    if isinstance(error, FallbackExecutionError):
        if error.decision.error_classification is not None:
            return error.decision.error_classification
        return to_reasoner_error_classification(
            error.decision.failure_class,
            error=error.last_error,
            context={
                "configured_target": error.decision.configured_target,
                "attempts": error.decision.attempts,
                "final_target": error.decision.final_target,
                "request_id": request.request_id,
                "caller_module": request.caller_module,
                "target_schema": request.target_schema,
            },
        )
    if isinstance(error, ParseValidationError):
        return to_reasoner_error_classification(
            "task_level",
            error=error,
            context={
                "phase": "parse",
                "request_id": request.request_id,
                "caller_module": request.caller_module,
                "target_schema": request.target_schema,
            },
        )
    return to_reasoner_error_classification(
        "infra_level",
        error=error,
        context={
            "provider": request.configured_provider,
            "model": request.configured_model,
            "request_id": request.request_id,
            "caller_module": request.caller_module,
            "target_schema": request.target_schema,
        },
    )


def _normalize_request(request: ReasonerRequest) -> ReasonerRequest:
    if not isinstance(request, ReasonerRequest):
        raise TypeError("request must be a ReasonerRequest")

    if request.max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    required_text_fields = {
        "caller_module": request.caller_module,
        "target_schema": request.target_schema,
        "configured_provider": request.configured_provider,
        "configured_model": request.configured_model,
    }
    missing_fields = [
        field_name
        for field_name, value in required_text_fields.items()
        if not value.strip()
    ]
    if missing_fields:
        joined_fields = ", ".join(missing_fields)
        raise ValueError(f"required request fields cannot be empty: {joined_fields}")

    if request.request_id.strip():
        return request

    return request.model_copy(update={"request_id": str(uuid4())})


def _parse_error_from_instructor_retry(error: Exception) -> ParseValidationError | None:
    retry_exception_type = _instructor_retry_exception_type()
    if retry_exception_type is None or not isinstance(error, retry_exception_type):
        return None

    failed_attempts = getattr(error, "failed_attempts", None)
    if not failed_attempts:
        return None

    if not all(
        _is_instructor_parse_failure(getattr(attempt, "exception", None))
        for attempt in failed_attempts
    ):
        return None

    return ParseValidationError(str(error))


def _is_instructor_parse_failure(error: Any) -> bool:
    if isinstance(
        error,
        (ParseValidationError, PydanticValidationError, JSONDecodeError),
    ):
        return True

    instructor_validation_error_type = _instructor_validation_error_type()
    return instructor_validation_error_type is not None and isinstance(
        error,
        instructor_validation_error_type,
    )


def _instructor_retry_exception_type() -> type[Exception] | None:
    try:
        from instructor.core import InstructorRetryException
    except ImportError:
        return None

    return InstructorRetryException


def _instructor_validation_error_type() -> type[Exception] | None:
    try:
        from instructor.core import ValidationError
    except ImportError:
        return None

    return ValidationError
