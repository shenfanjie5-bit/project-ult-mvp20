from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from reasoner_runtime.callbacks.base import (
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)

try:  # pragma: no cover - exercised when OTEL is installed.
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ImportError:  # pragma: no cover - default sandbox path.
    trace = None  # type: ignore[assignment]

    class StatusCode:  # type: ignore[no-redef]
        ERROR = "ERROR"

    class Status:  # type: ignore[no-redef]
        def __init__(self, status_code: Any, description: str | None = None) -> None:
            self.status_code = status_code
            self.description = description


class OTELCallbackBackend:
    def __init__(
        self,
        tracer: Any | None = None,
        service_name: str = "reasoner-runtime",
    ) -> None:
        self.service_name = service_name
        self._tracer = tracer or self._default_tracer(service_name)

    def on_start(self, context: CallbackContext) -> None:
        self._with_span(
            "reasoner.llm.start",
            lambda span: self._set_context_attributes(span, context),
        )

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        def annotate(span: Any) -> None:
            self._set_context_attributes(span, context)
            _set_attribute(
                span,
                "llm.tokens.prompt",
                success.token_usage.get("prompt", 0),
            )
            _set_attribute(
                span,
                "llm.tokens.completion",
                success.token_usage.get("completion", 0),
            )
            _set_attribute(
                span,
                "llm.tokens.total",
                success.token_usage.get("total", 0),
            )
            _set_attribute(span, "llm.cost_estimate", success.cost_estimate)
            _set_attribute(span, "llm.latency_ms", success.latency_ms)
            _set_attribute(span, "llm.retry_count", success.retry_count)
            _set_attribute(
                span,
                "llm.fallback_path.length",
                len(success.fallback_path),
            )
            if success.failure_class is not None:
                _set_attribute(span, "llm.failure_class", success.failure_class)

        self._with_span("reasoner.llm.success", annotate)

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        def annotate(span: Any) -> None:
            self._set_context_attributes(span, context)
            _set_attribute(span, "llm.error_type", error.error_type)
            _set_attribute(span, "llm.error_message", error.error_message)
            if error.failure_class is not None:
                _set_attribute(span, "llm.failure_class", error.failure_class)
            if error.error_classification is not None:
                _set_attribute(
                    span,
                    "llm.error_classification.code",
                    error.error_classification.code.value,
                )
                _set_attribute(
                    span,
                    "llm.error_classification.category",
                    error.error_classification.category.value,
                )
                _set_attribute(
                    span,
                    "llm.error_classification.retryable",
                    str(error.error_classification.retryable).lower(),
                )
            if error.latency_ms is not None:
                _set_attribute(span, "llm.latency_ms", error.latency_ms)
            if hasattr(span, "set_status"):
                span.set_status(Status(StatusCode.ERROR, error.error_message))

        self._with_span("reasoner.llm.error", annotate)

    def _default_tracer(self, service_name: str) -> Any:
        if trace is None:
            return _NoopTracer()
        return trace.get_tracer(service_name)

    def _with_span(self, name: str, annotate: Callable[[Any], None]) -> None:
        try:
            with _start_span(self._tracer, name) as span:
                annotate(span)
        except Exception:
            return

    def _set_context_attributes(self, span: Any, context: CallbackContext) -> None:
        context_attributes = {
            "reasoner.request_id": context.request_id,
            "reasoner.caller_module": context.caller_module,
            "reasoner.target_schema": context.target_schema,
            "reasoner.cycle_id": context.cycle_id,
            "reasoner.ticker": context.ticker,
            "reasoner.analyzer_type": context.analyzer_type,
            "reasoner.regime_label": context.regime_label,
            "llm.provider": context.provider,
            "llm.model": context.model,
        }
        if context.cycle_id and context.ticker:
            context_attributes["reasoner.session_id"] = (
                f"{context.cycle_id}_{context.ticker}"
            )
            context_attributes["reasoner.user_id"] = context.ticker
        if context.analyzer_type or context.regime_label:
            tags = [
                tag
                for tag in ("L6", context.analyzer_type, context.regime_label)
                if tag
            ]
            context_attributes["reasoner.tags"] = ",".join(tags)
        for key, value in context_attributes.items():
            if value:
                _set_attribute(span, key, value)


@contextmanager
def _start_span(tracer: Any, name: str) -> Any:
    if hasattr(tracer, "start_as_current_span"):
        with tracer.start_as_current_span(name) as span:
            yield span
        return

    span = tracer.start_span(name)
    try:
        yield span
    finally:
        if hasattr(span, "end"):
            span.end()


def _set_attribute(span: Any, key: str, value: str | int | float) -> None:
    if hasattr(span, "set_attribute"):
        span.set_attribute(key, value)


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return

    def set_status(self, status: Any) -> None:
        return

    def end(self) -> None:
        return


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, name: str) -> Any:
        yield _NoopSpan()
