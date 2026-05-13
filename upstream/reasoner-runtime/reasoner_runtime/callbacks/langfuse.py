from __future__ import annotations

import hashlib
import logging
from typing import Any

from reasoner_runtime.callbacks.base import (
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)
from reasoner_runtime.scrub.rules import scrub_text


_MAX_ERROR_MESSAGE_CHARS = 500
_TRACE_ID_HEX_CHARS = 32
_LOGGER = logging.getLogger(__name__)


class LangfuseCallbackBackend:
    def __init__(
        self,
        client: Any | None = None,
        *,
        host: str | None = None,
        trace_name: str = "reasoner.llm",
    ) -> None:
        self._client = client
        self.host = host
        self.trace_name = trace_name
        self._unsupported_client_events = 0
        self._export_failures = 0

    @property
    def unsupported_client_events(self) -> int:
        return self._unsupported_client_events

    @property
    def export_failures(self) -> int:
        return self._export_failures

    def on_start(self, context: CallbackContext) -> None:
        self._emit_event(
            "reasoner.llm.start",
            _context_metadata(context),
        )

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        self._emit_event(
            "reasoner.llm.success",
            {
                **_context_metadata(context),
                **_success_metadata(success),
            },
        )

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        self._emit_event(
            "reasoner.llm.error",
            {
                **_context_metadata(context),
                **_error_metadata(error),
            },
        )

    def _emit_event(self, name: str, metadata: dict[str, Any]) -> None:
        try:
            client = self._get_client()
            if _emit_on_target(client, name, metadata):
                _flush_target(client)
                return

            trace_method = getattr(client, "trace", None)
            if not callable(trace_method):
                self._unsupported_client_events += 1
                _LOGGER.warning(
                    "Langfuse callback backend could not emit %s: unsupported "
                    "client shape %s",
                    name,
                    type(client).__name__,
                )
                return

            trace = _build_trace(trace_method, self.trace_name)
            if _emit_on_target(trace, name, metadata):
                _flush_target(client)
                return

            self._unsupported_client_events += 1
            _LOGGER.warning(
                "Langfuse callback backend could not emit %s: unsupported trace "
                "shape %s",
                name,
                type(trace).__name__,
            )
        except Exception as error:
            self._export_failures += 1
            _LOGGER.warning(
                "Langfuse callback backend failed to emit %s: %s",
                name,
                _diagnostic_error(error),
            )
            return

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _build_default_client(self.host)
        return self._client


def _build_default_client(host: str | None) -> Any:
    try:
        from langfuse import Langfuse
    except ImportError as error:
        raise RuntimeError(
            "Langfuse callback backend requires the optional 'langfuse' package "
            "when no client is injected"
        ) from error

    if host:
        return Langfuse(host=host)
    return Langfuse()


def _context_metadata(context: CallbackContext) -> dict[str, Any]:
    metadata = {
        "request_id": context.request_id,
        "caller_module": context.caller_module,
        "target_schema": context.target_schema,
        "provider": context.provider,
        "model": context.model,
    }
    metadata.update(_trace_metadata(context))
    return metadata


def _trace_metadata(context: CallbackContext) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if context.cycle_id:
        metadata["cycle_id"] = context.cycle_id
    if context.ticker:
        metadata["ticker"] = context.ticker
        metadata["user_id"] = context.ticker
    if context.analyzer_type:
        metadata["analyzer_type"] = context.analyzer_type
    if context.regime_label:
        metadata["regime_label"] = context.regime_label
    if context.cycle_id and context.ticker:
        metadata["session_id"] = f"{context.cycle_id}_{context.ticker}"

    if context.analyzer_type or context.regime_label:
        tags = [
            tag
            for tag in ("L6", context.analyzer_type, context.regime_label)
            if tag
        ]
        metadata["tags"] = tags
    return metadata


def _success_metadata(success: CallbackSuccess) -> dict[str, Any]:
    return {
        "token_usage": dict(success.token_usage),
        "cost_estimate": success.cost_estimate,
        "latency_ms": success.latency_ms,
        "fallback_path": list(success.fallback_path),
        "retry_count": success.retry_count,
        "failure_class": success.failure_class,
    }


def _error_metadata(error: CallbackError) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "error_type": error.error_type,
        "error_message": _truncate(scrub_text(error.error_message).strip()),
        "failure_class": error.failure_class,
    }
    if error.error_classification is not None:
        metadata["error_classification"] = error.error_classification.model_dump(
            mode="json"
        )
    if error.latency_ms is not None:
        metadata["latency_ms"] = error.latency_ms
    return metadata


def _emit_on_target(target: Any, name: str, metadata: dict[str, Any]) -> bool:
    create_event_method = getattr(target, "create_event", None)
    if callable(create_event_method):
        _emit_create_event(target, create_event_method, name, metadata)
        return True

    event_method = getattr(target, "event", None)
    if not callable(event_method):
        return False

    try:
        event_method(name=name, metadata=metadata)
    except TypeError:
        event_method(name, metadata=metadata)
    return True


def _emit_create_event(
    target: Any,
    create_event_method: Any,
    name: str,
    metadata: dict[str, Any],
) -> None:
    kwargs: dict[str, Any] = {
        "name": name,
        "metadata": metadata,
    }
    trace_context = _trace_context(target, metadata)
    if trace_context is not None:
        kwargs["trace_context"] = trace_context

    try:
        create_event_method(**kwargs)
    except TypeError:
        kwargs.pop("trace_context", None)
        create_event_method(**kwargs)


def _trace_context(target: Any, metadata: dict[str, Any]) -> dict[str, str] | None:
    request_id = metadata.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return None

    return {"trace_id": _trace_id(target, request_id)}


def _trace_id(target: Any, request_id: str) -> str:
    create_trace_id_method = getattr(target, "create_trace_id", None)
    if callable(create_trace_id_method):
        try:
            return str(create_trace_id_method(seed=request_id))
        except TypeError:
            try:
                return str(create_trace_id_method(request_id))
            except Exception:
                return _deterministic_trace_id(request_id)
        except Exception:
            return _deterministic_trace_id(request_id)

    return _deterministic_trace_id(request_id)


def _deterministic_trace_id(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()[
        :_TRACE_ID_HEX_CHARS
    ]


def _flush_target(target: Any) -> None:
    flush_method = getattr(target, "flush", None)
    if callable(flush_method):
        flush_method()


def _build_trace(trace_method: Any, trace_name: str) -> Any:
    try:
        return trace_method(name=trace_name)
    except TypeError:
        return trace_method(trace_name)


def _diagnostic_error(error: Exception) -> str:
    message = scrub_text(str(error)).strip()
    if message:
        return f"{type(error).__name__}: {_truncate(message)}"
    return type(error).__name__


def _truncate(value: str) -> str:
    if len(value) <= _MAX_ERROR_MESSAGE_CHARS:
        return value
    return value[: _MAX_ERROR_MESSAGE_CHARS - 3].rstrip() + "..."


__all__ = ["LangfuseCallbackBackend"]
