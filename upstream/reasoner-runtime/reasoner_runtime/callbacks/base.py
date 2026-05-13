from __future__ import annotations

from typing import Annotated, Protocol, runtime_checkable

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.schemas.reasoner import ReasonerErrorClassification
from pydantic import BaseModel, Field


NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


class CallbackContext(BaseModel):
    request_id: str = ""
    caller_module: str = ""
    target_schema: str = ""
    provider: str = ""
    model: str = ""
    # spec v5.0.1 §14A.3: callers (main-core L6/L7) put `cycle_id`,
    # `ticker`, `analyzer_type`, `regime_label` into ReasonerRequest.metadata
    # so external observability backends (Langfuse / OTEL) can compose
    # `session_id = f"{cycle_id}_{ticker}"`, `tags = ["L6", analyzer_type,
    # regime_label]`, `user_id = ticker`. Optional default-empty so existing
    # callers that omit them don't break — backends decide whether absence
    # is acceptable.
    cycle_id: str = ""
    ticker: str = ""
    analyzer_type: str = ""
    regime_label: str = ""


class CallbackSuccess(BaseModel):
    token_usage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    cost_estimate: NonNegativeFloat = 0.0
    latency_ms: NonNegativeInt = 0
    fallback_path: list[str] = Field(default_factory=list)
    retry_count: NonNegativeInt = 0
    failure_class: str | None = None


class CallbackError(BaseModel):
    error_type: str
    error_message: str
    failure_class: str | None = None
    error_classification: ReasonerErrorClassification | None = None
    latency_ms: NonNegativeInt | None = None


@runtime_checkable
class CallbackBackend(Protocol):
    def on_start(self, context: CallbackContext) -> None:
        ...

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        ...

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        ...
