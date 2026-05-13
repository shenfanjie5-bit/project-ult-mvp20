from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime
from typing import Any

from reasoner_runtime.callbacks.base import (
    CallbackBackend,
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)
from reasoner_runtime.providers.models import (
    FailureClass,
    to_reasoner_error_classification,
)
from reasoner_runtime.scrub import scrub_payload, scrub_text


_LOGGER = logging.getLogger(__name__)
_MAX_ERROR_MESSAGE_CHARS = 500
_UNKNOWN_PROVIDER_ERROR_TYPE = "UnknownProviderError"
_UNKNOWN_PROVIDER_ERROR_MESSAGE = "unknown provider error"
_ERROR_CODE_KEYS = ("error_code", "code", "status_code", "status")


class LiteLLMCallbackBridge:
    def __init__(self, backends: Sequence[CallbackBackend]) -> None:
        self.backends = tuple(backends)

    def input_handler(
        self,
        kwargs: dict[str, Any],
        *_args: Any,
        **_extra: Any,
    ) -> None:
        """LiteLLM input_callback: defense-in-depth PII scrub before any
        provider call.

        spec v5.0.1 §14A.3 (TIGHTEN-02): the engine wrapper already runs
        `scrub_request` pre-call (audit_record.sanitized_input is its
        product). Registering an input_callback ensures the same scrub
        pass runs even if a caller bypasses `generate_structured` and
        invokes `litellm.completion` directly. When content needs
        scrubbing, mutate the message payload before the provider call and
        WARN with the request_id so the bypass surfaces in observability
        rather than being silent.
        """

        try:
            messages = kwargs.get("messages")
            if not isinstance(messages, list):
                return

            for index, message in enumerate(messages):
                if not isinstance(message, Mapping):
                    continue
                content = message.get("content")
                if content in (None, ""):
                    continue
                scrubbed = scrub_payload(content, scrub_keys=False)
                if scrubbed != content:
                    if isinstance(message, MutableMapping):
                        message["content"] = scrubbed
                    else:
                        scrubbed_message = dict(message)
                        scrubbed_message["content"] = scrubbed
                        messages[index] = scrubbed_message
                    metadata = _extract_reasoner_metadata(kwargs)
                    _LOGGER.warning(
                        "litellm input_callback scrubbed direct-call PII "
                        "(request_id=%s, message_index=%s). Route LLM calls "
                        "through reasoner_runtime.generate_structured.",
                        metadata.get("request_id") or "<unknown>",
                        index,
                    )
        except Exception as exc:  # defense-in-depth must not raise
            _LOGGER.warning(
                "litellm input_callback PII scrub guard failed "
                "(exception_type=%s)",
                type(exc).__name__,
            )

    def success_handler(
        self,
        kwargs: dict[str, Any],
        completion_response: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        try:
            context = _build_context(kwargs)
            success = CallbackSuccess(
                token_usage=_extract_token_usage(completion_response),
                cost_estimate=_extract_cost_estimate(completion_response, kwargs),
                latency_ms=_extract_latency_ms(
                    completion_response,
                    start_time,
                    end_time,
                ),
                fallback_path=_extract_fallback_path(kwargs),
                retry_count=_extract_retry_count(kwargs),
                failure_class=_extract_failure_class(kwargs),
            )
        except Exception as exc:
            _LOGGER.warning(
                "litellm success callback payload extraction failed "
                "(exception_type=%s)",
                type(exc).__name__,
            )
            return

        for backend in self.backends:
            try:
                backend.on_success(context, success)
            except Exception as exc:
                _LOGGER.warning(
                    "litellm success callback backend %s failed "
                    "(exception_type=%s)",
                    type(backend).__name__,
                    type(exc).__name__,
                )
                continue

    def failure_handler(
        self,
        kwargs: dict[str, Any],
        completion_response: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        try:
            context = _build_context(kwargs)
            error_type, error_message = _extract_error_details(kwargs)
            error = CallbackError(
                error_type=error_type,
                error_message=error_message,
                failure_class=_extract_failure_class(kwargs),
                error_classification=_extract_error_classification(kwargs, context),
                latency_ms=_extract_latency_ms(None, start_time, end_time),
            )
        except Exception as exc:
            _LOGGER.warning(
                "litellm failure callback payload extraction failed "
                "(exception_type=%s)",
                type(exc).__name__,
            )
            return

        for backend in self.backends:
            try:
                backend.on_error(context, error)
            except Exception as exc:
                _LOGGER.warning(
                    "litellm failure callback backend %s failed "
                    "(exception_type=%s)",
                    type(backend).__name__,
                    type(exc).__name__,
                )
                continue


_installed_bridges: dict[int, LiteLLMCallbackBridge] = {}


def configure_litellm_callbacks(
    backends: Sequence[CallbackBackend],
) -> LiteLLMCallbackBridge | None:
    try:
        import litellm
    except ImportError:
        return None

    _remove_installed_handlers(litellm)
    # Stage-4 PII scrub guard: register the input_callback even when no
    # observability backend is configured, so direct `litellm.completion`
    # calls that bypass the engine wrapper still hit a scrub trip-wire.
    bridge = LiteLLMCallbackBridge(backends)
    _installed_bridges[id(litellm)] = bridge
    _register_handler(litellm, "input_callback", bridge.input_handler)
    if not backends:
        return None

    _register_handler(litellm, "success_callback", bridge.success_handler)
    _register_handler(litellm, "failure_callback", bridge.failure_handler)
    return bridge


def _remove_installed_handlers(module: Any) -> None:
    _installed_bridges.pop(id(module), None)
    _unregister_bridge_handlers(
        module,
        "input_callback",
        LiteLLMCallbackBridge.input_handler,
    )
    _unregister_bridge_handlers(
        module,
        "success_callback",
        LiteLLMCallbackBridge.success_handler,
    )
    _unregister_bridge_handlers(
        module,
        "failure_callback",
        LiteLLMCallbackBridge.failure_handler,
    )


def _register_handler(module: Any, attribute: str, handler: Any) -> None:
    callbacks = _normalize_callback_list(getattr(module, attribute, None))
    if not any(_same_handler(existing, handler) for existing in callbacks):
        callbacks.append(handler)
    setattr(module, attribute, callbacks)


def _unregister_bridge_handlers(
    module: Any,
    attribute: str,
    method: Any,
) -> None:
    callbacks = _normalize_callback_list(getattr(module, attribute, None))
    callbacks = [
        existing
        for existing in callbacks
        if not _same_bridge_handler(existing, method)
    ]
    setattr(module, attribute, callbacks)


def _normalize_callback_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _same_handler(left: Any, right: Any) -> bool:
    return (
        getattr(left, "__self__", None) is getattr(right, "__self__", None)
        and getattr(left, "__func__", None) is getattr(right, "__func__", None)
    ) or left is right


def _same_bridge_handler(handler: Any, method: Any) -> bool:
    return (
        isinstance(getattr(handler, "__self__", None), LiteLLMCallbackBridge)
        and getattr(handler, "__func__", None) is method
    )


def _build_context(kwargs: Mapping[str, Any]) -> CallbackContext:
    metadata = _extract_reasoner_metadata(kwargs)
    provider = _string_value(metadata.get("provider"))
    model = _string_value(metadata.get("model"))
    if not provider or not model:
        parsed_provider, parsed_model = _provider_model_from_litellm_kwargs(kwargs)
        provider = provider or parsed_provider
        model = model or parsed_model

    return CallbackContext(
        request_id=_string_value(metadata.get("request_id")),
        caller_module=_string_value(metadata.get("caller_module")),
        target_schema=_string_value(metadata.get("target_schema")),
        provider=provider,
        model=model,
        # spec v5.0.1 §14A.3 four trace fields. Surface them on the
        # context so observability backends (Langfuse / OTEL) can compose
        # session_id / tags / user_id without re-parsing kwargs.
        cycle_id=_string_value(metadata.get("cycle_id")),
        ticker=_string_value(metadata.get("ticker")),
        analyzer_type=_string_value(metadata.get("analyzer_type")),
        regime_label=_string_value(metadata.get("regime_label")),
    )


def _extract_reasoner_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    for candidate in (
        source.get("metadata"),
        _read_value(source.get("litellm_params"), "metadata"),
        _read_value(source.get("optional_params"), "metadata"),
    ):
        if isinstance(candidate, Mapping):
            nested = candidate.get("reasoner")
            if isinstance(nested, Mapping):
                return dict(nested)
            return dict(candidate)
    return {}


def _provider_model_from_litellm_kwargs(
    kwargs: Mapping[str, Any],
) -> tuple[str, str]:
    model_name = _string_value(kwargs.get("model"))
    if "/" not in model_name:
        return "", model_name

    provider, _, model = model_name.partition("/")
    return provider, model


def _extract_token_usage(completion_response: Any) -> dict[str, int]:
    usage = _read_value(completion_response, "token_usage")
    if usage is None:
        usage = _read_value(completion_response, "usage")

    prompt = _read_nonnegative_int(usage, "prompt")
    if prompt == 0:
        prompt = _read_nonnegative_int(usage, "prompt_tokens")

    completion = _read_nonnegative_int(usage, "completion")
    if completion == 0:
        completion = _read_nonnegative_int(usage, "completion_tokens")

    total = _read_nonnegative_int(usage, "total")
    if total == 0:
        total = _read_nonnegative_int(usage, "total_tokens")
    if total == 0:
        total = prompt + completion

    return {
        "prompt": prompt,
        "completion": completion,
        "total": total,
    }


def _extract_cost_estimate(
    completion_response: Any,
    kwargs: Mapping[str, Any],
) -> float:
    for source in (completion_response, kwargs):
        cost = _read_value(source, "cost_estimate")
        if cost is None:
            cost = _read_value(source, "response_cost")
        if cost is None:
            hidden_params = _read_value(source, "_hidden_params")
            cost = _read_value(hidden_params, "response_cost")
        if cost is not None:
            return _coerce_nonnegative_float(cost)
    return 0.0


def _extract_latency_ms(
    completion_response: Any | None,
    start_time: Any,
    end_time: Any,
) -> int:
    latency_ms = _read_value(completion_response, "latency_ms")
    if latency_ms is None:
        latency_ms = _read_value(completion_response, "latency")
    if latency_ms is not None:
        return _coerce_nonnegative_int(latency_ms)

    start_seconds = _to_seconds(start_time)
    end_seconds = _to_seconds(end_time)
    if start_seconds is None or end_seconds is None:
        return 0

    return max(int((end_seconds - start_seconds) * 1000), 0)


def _extract_fallback_path(kwargs: Mapping[str, Any]) -> list[str]:
    metadata = _extract_reasoner_metadata(kwargs)
    fallback_path = metadata.get("fallback_path")
    if not isinstance(fallback_path, Sequence) or isinstance(fallback_path, str):
        return []
    return [str(item) for item in fallback_path]


def _extract_retry_count(kwargs: Mapping[str, Any]) -> int:
    metadata = _extract_reasoner_metadata(kwargs)
    return _coerce_nonnegative_int(metadata.get("retry_count"))


def _extract_failure_class(kwargs: Mapping[str, Any]) -> str | None:
    metadata = _extract_reasoner_metadata(kwargs)
    value = metadata.get("failure_class")
    if value is None:
        return None
    return _string_value(getattr(value, "value", value))


def _extract_error_classification(
    kwargs: Mapping[str, Any],
    context: CallbackContext,
) -> Any:
    metadata = _extract_reasoner_metadata(kwargs)
    failure_class = _extract_failure_class(kwargs) or FailureClass.infra_level
    target = (
        f"{context.provider}/{context.model}"
        if context.provider and context.model
        else ""
    )
    return to_reasoner_error_classification(
        failure_class,
        error=_extract_exception(kwargs),
        context={
            **metadata,
            "failure_source": "provider",
            "provider": context.provider,
            "model": context.model,
            "target": target,
        },
    )


def _extract_exception(kwargs: Mapping[str, Any]) -> BaseException | None:
    for key in ("exception", "error", "original_exception"):
        value = kwargs.get(key)
        if isinstance(value, BaseException):
            return value
    return None


def _extract_error_details(kwargs: Mapping[str, Any]) -> tuple[str, str]:
    for key in ("exception", "error", "original_exception"):
        value = kwargs.get(key)
        if value is not None:
            return _safe_error_type(value), _safe_error_message(value)
    return _UNKNOWN_PROVIDER_ERROR_TYPE, _UNKNOWN_PROVIDER_ERROR_MESSAGE


def _safe_error_type(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("error_type", "type"):
            error_type = value.get(key)
            if isinstance(error_type, str) and error_type.strip():
                return _truncate(scrub_text(error_type.strip()))
        return _UNKNOWN_PROVIDER_ERROR_TYPE

    return type(value).__name__


def _safe_error_message(value: Any) -> str:
    if isinstance(value, BaseException):
        return _scrubbed_truncated_message(str(value))

    if isinstance(value, str):
        return _scrubbed_truncated_message(value)

    if isinstance(value, Mapping):
        for key in _ERROR_CODE_KEYS:
            error_code = value.get(key)
            if _is_scalar(error_code):
                return _scrubbed_truncated_message(f"{key}={error_code}")

    for key in _ERROR_CODE_KEYS:
        error_code = _read_value(value, key)
        if _is_scalar(error_code):
            return _scrubbed_truncated_message(f"{key}={error_code}")

    return _UNKNOWN_PROVIDER_ERROR_MESSAGE


def _scrubbed_truncated_message(value: str) -> str:
    scrubbed = scrub_text(value).strip()
    if not scrubbed:
        return _UNKNOWN_PROVIDER_ERROR_MESSAGE
    return _truncate(scrubbed)


def _truncate(value: str) -> str:
    if len(value) <= _MAX_ERROR_MESSAGE_CHARS:
        return value
    return value[: _MAX_ERROR_MESSAGE_CHARS - 3].rstrip() + "..."


def _is_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def _read_nonnegative_int(source: Any | None, key: str) -> int:
    return _coerce_nonnegative_int(_read_value(source, key))


def _coerce_nonnegative_int(value: Any | None) -> int:
    if value is None:
        return 0
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return max(coerced, 0)


def _coerce_nonnegative_float(value: Any | None) -> float:
    if value is None:
        return 0.0
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(coerced, 0.0)


def _to_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _read_value(source: Any | None, key: str) -> Any | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
