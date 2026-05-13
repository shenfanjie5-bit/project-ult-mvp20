from __future__ import annotations

import re
from collections.abc import Mapping
from enum import Enum
from typing import Any

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.core import Severity
from contracts.errors import ErrorCode
from contracts.schemas.reasoner import (
    ReasonerErrorCategory,
    ReasonerErrorClassification,
)
from pydantic import BaseModel, Field, model_validator


class FailureClass(str, Enum):
    """Compatibility enum for the runtime's pre-contract failure taxonomy."""

    none = "none"
    success_with_fallback = "success_with_fallback"
    task_level = "task_level"
    infra_level = "infra_level"


_ERROR_CODE_BY_CATEGORY = {
    ReasonerErrorCategory.INPUT_CONTRACT: ErrorCode.REASONER_INPUT_CONTRACT_ERROR,
    ReasonerErrorCategory.MODEL_PROVIDER: ErrorCode.REASONER_MODEL_PROVIDER_ERROR,
    ReasonerErrorCategory.TIMEOUT: ErrorCode.REASONER_TIMEOUT_ERROR,
    ReasonerErrorCategory.INTERNAL: ErrorCode.REASONER_INTERNAL_ERROR,
}

_SAFE_DETAIL_KEYS = {
    "attempts",
    "caller_module",
    "configured_target",
    "failure_source",
    "fallback_path",
    "final_target",
    "model",
    "phase",
    "provider",
    "quota_status",
    "reachable",
    "request_id",
    "retry_count",
    "target",
    "target_schema",
}

_EXHAUSTED_ERROR_NAMES = {
    "AuthenticationError",
    "AuthorizationError",
    "BudgetExceededError",
    "ForbiddenError",
    "InvalidAPIKeyError",
    "PermissionDeniedError",
    "QuotaExceededError",
}
_LIMITED_ERROR_NAMES = {
    "RateLimitError",
}
_EXHAUSTED_HTTP_STATUSES = {401, 402, 403}
_LIMITED_HTTP_STATUSES = {429}
_EXHAUSTED_MESSAGE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bauth\b",
        r"\bauthentication\b",
        r"\bauthorization\b",
        r"\bbilling\b",
        r"\bunauthorized\b",
        r"\bforbidden\b",
        r"\binvalid\s+api\s+key\b",
        r"\bapi\s+key\b",
        r"\bbudget\s+exceeded\b",
        r"\bquota\s+exceeded\b",
        r"\bquota\s+exhausted\b",
        r"\binsufficient_quota\b",
        r"\bcredits\s+exhausted\b",
    )
)
_LIMITED_MESSAGE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brate\s+limit\b",
        r"\brate_limit\b",
        r"\btoo\s+many\s+requests\b",
        r"\blimited\b",
    )
)


def to_reasoner_error_classification(
    failure_class: FailureClass | str | None,
    *,
    error: BaseException | None = None,
    context: Mapping[str, Any] | None = None,
    message: str | None = None,
) -> ReasonerErrorClassification | None:
    """Translate the local failure class into the public contracts taxonomy."""

    normalized = _coerce_failure_class(failure_class)
    if normalized in {FailureClass.none, FailureClass.success_with_fallback}:
        return None

    context_values = dict(context or {})
    category = _classification_category(normalized, error, context_values)
    return ReasonerErrorClassification(
        code=_ERROR_CODE_BY_CATEGORY[category],
        category=category,
        severity=Severity.ERROR,
        retryable=_classification_retryable(
            category,
            normalized,
            error,
            context_values,
        ),
        message=_classification_message(category, normalized, message),
        details=_classification_details(normalized, error, context_values),
    )


class FallbackDecision(BaseModel):
    configured_target: str
    attempts: list[str] = Field(default_factory=list)
    final_target: str | None = None
    failure_class: FailureClass = FailureClass.none
    terminal_reason: str | None = None
    error_classification: ReasonerErrorClassification | None = None

    @model_validator(mode="after")
    def populate_error_classification(self) -> FallbackDecision:
        classification = to_reasoner_error_classification(
            self.failure_class,
            context={
                "configured_target": self.configured_target,
                "attempts": self.attempts,
                "final_target": self.final_target,
            },
        )
        if classification is None:
            if self.error_classification is not None:
                raise ValueError(
                    "fallback error_classification is only valid for failed decisions"
                )
            return self

        if self.error_classification is None:
            self.error_classification = classification
        elif _classification_conflicts(self.error_classification, classification):
            raise ValueError(
                "fallback error_classification does not match failure_class"
            )
        return self


def provider_quota_status_from_error(error: BaseException | None) -> str:
    if error is None:
        return "ok"

    status_code = _error_status_code(error)
    if status_code in _EXHAUSTED_HTTP_STATUSES:
        return "exhausted"
    if status_code in _LIMITED_HTTP_STATUSES:
        return "limited"

    error_names = set(_error_names(error))
    if error_names & _EXHAUSTED_ERROR_NAMES:
        return "exhausted"
    if error_names & _LIMITED_ERROR_NAMES:
        return "limited"

    message = str(error)
    if any(pattern.search(message) for pattern in _EXHAUSTED_MESSAGE_PATTERNS):
        return "exhausted"
    if any(pattern.search(message) for pattern in _LIMITED_MESSAGE_PATTERNS):
        return "limited"

    return "ok"


def _coerce_failure_class(failure_class: FailureClass | str | None) -> FailureClass:
    if failure_class is None:
        return FailureClass.none
    if isinstance(failure_class, FailureClass):
        return failure_class
    return FailureClass(failure_class)


def _classification_category(
    failure_class: FailureClass,
    error: BaseException | None,
    context: Mapping[str, Any],
) -> ReasonerErrorCategory:
    if failure_class is FailureClass.task_level:
        return ReasonerErrorCategory.INPUT_CONTRACT
    if _is_timeout_failure(error, context):
        return ReasonerErrorCategory.TIMEOUT
    if _has_provider_context(context):
        return ReasonerErrorCategory.MODEL_PROVIDER
    return ReasonerErrorCategory.INTERNAL


def _classification_retryable(
    category: ReasonerErrorCategory,
    failure_class: FailureClass,
    error: BaseException | None,
    context: Mapping[str, Any],
) -> bool:
    if failure_class is FailureClass.task_level:
        return False
    if category is ReasonerErrorCategory.TIMEOUT:
        return True
    if category is ReasonerErrorCategory.MODEL_PROVIDER:
        return not _is_non_retryable_provider_failure(error, context)
    return False


def _classification_message(
    category: ReasonerErrorCategory,
    failure_class: FailureClass,
    message: str | None,
) -> str:
    if message is not None and message.strip():
        return message.strip()
    if failure_class is FailureClass.task_level:
        return "structured output validation failed"
    if category is ReasonerErrorCategory.TIMEOUT:
        return "reasoner provider request timed out"
    if category is ReasonerErrorCategory.MODEL_PROVIDER:
        return "reasoner model provider failed"
    return "reasoner runtime infrastructure failed"


def _classification_details(
    failure_class: FailureClass,
    error: BaseException | None,
    context: Mapping[str, Any],
) -> dict[str, object]:
    details: dict[str, object] = {"failure_class": failure_class.value}
    if error is not None:
        details["exception_type"] = type(error).__name__

    for key in sorted(_SAFE_DETAIL_KEYS):
        value = _json_safe_detail_value(context.get(key))
        if value is not None:
            details[key] = value
    return details


def _is_timeout_failure(
    error: BaseException | None,
    context: Mapping[str, Any],
) -> bool:
    if isinstance(error, TimeoutError):
        return True
    if error is not None and any(
        "timeout" in name.lower() for name in _error_names(error)
    ):
        return True
    return any(
        "timeout" in str(value).lower() or "timed out" in str(value).lower()
        for key, value in context.items()
        if key in {"error", "error_type", "phase", "failure_source"}
    )


def _is_non_retryable_provider_failure(
    error: BaseException | None,
    context: Mapping[str, Any],
) -> bool:
    if str(context.get("quota_status", "")).lower() == "exhausted":
        return True
    if provider_quota_status_from_error(error) == "exhausted":
        return True

    context_error = context.get("error")
    if context_error is not None and any(
        pattern.search(str(context_error)) for pattern in _EXHAUSTED_MESSAGE_PATTERNS
    ):
        return True

    return False


def _has_provider_context(context: Mapping[str, Any]) -> bool:
    if any(context.get(key) for key in ("provider", "model", "target", "final_target")):
        return True
    if context.get("attempts"):
        return True
    return (
        context.get("failure_source") == "provider"
        or context.get("phase") == "provider"
    )


def _error_names(error: BaseException) -> list[str]:
    return [cls.__name__ for cls in type(error).mro()]


def _error_status_code(error: BaseException) -> int | None:
    for attr_name in ("status_code", "status", "http_status"):
        value = getattr(error, attr_name, None)
        if isinstance(value, int):
            return value

    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value

    return None


def _classification_conflicts(
    supplied: ReasonerErrorClassification,
    expected: ReasonerErrorClassification,
) -> bool:
    return (
        supplied.code is not expected.code
        or supplied.category is not expected.category
        or (not expected.retryable and supplied.retryable)
    )


def _json_safe_detail_value(value: Any) -> object | None:
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list | tuple):
        safe_items = [_json_safe_detail_value(item) for item in value]
        return [item for item in safe_items if item is not None]
    return str(value)
