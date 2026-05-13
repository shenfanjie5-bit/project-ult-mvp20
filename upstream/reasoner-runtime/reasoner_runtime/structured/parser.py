from __future__ import annotations

from collections.abc import Mapping
from inspect import Parameter, signature
from time import perf_counter
from typing import Annotated, Any

from pydantic import BaseModel, Field, ValidationError

from reasoner_runtime.core.models import ReasonerRequest
from reasoner_runtime.providers.routing import ParseValidationError


NonNegativeInt = Annotated[int, Field(ge=0)]


class StructuredCallResult(BaseModel):
    parsed_result: dict[str, Any]
    raw_output: str
    token_usage: dict[str, NonNegativeInt]
    cost_estimate: float = Field(ge=0)
    latency_ms: int = Field(ge=0)


def resolve_response_model(
    target_schema: str,
    schema_registry: Mapping[str, type[BaseModel]],
) -> type[BaseModel]:
    response_model = schema_registry.get(target_schema)
    if response_model is None:
        raise ParseValidationError(
            f"target schema '{target_schema}' is not registered"
        )
    if not isinstance(response_model, type) or not issubclass(
        response_model, BaseModel
    ):
        raise ParseValidationError(
            f"target schema '{target_schema}' must map to a Pydantic BaseModel"
        )

    return response_model


def run_structured_call(
    client: Any,
    request: ReasonerRequest,
    response_model: type[BaseModel],
) -> StructuredCallResult:
    started_at = perf_counter()
    callback_metadata = _build_callback_metadata(request)
    client_response = _invoke_client(
        client,
        messages=request.messages,
        provider_metadata=_provider_metadata(request.metadata, callback_metadata),
        response_model=response_model,
        callback_metadata=callback_metadata,
    )
    if isinstance(client_response, StructuredCallResult):
        return client_response

    parsed_payload, completion = _split_client_response(client_response)
    parsed_model = _coerce_parsed_model(parsed_payload, response_model)
    elapsed_ms = int((perf_counter() - started_at) * 1000)

    return StructuredCallResult(
        parsed_result=parsed_model.model_dump(mode="json"),
        raw_output=_extract_raw_output(completion, parsed_model),
        token_usage=_extract_token_usage(completion),
        cost_estimate=_extract_cost_estimate(completion),
        latency_ms=_extract_latency_ms(completion, elapsed_ms),
    )


def _invoke_client(
    client: Any,
    *,
    messages: list[dict[str, Any]],
    provider_metadata: dict[str, Any],
    response_model: type[BaseModel],
    callback_metadata: dict[str, Any],
) -> Any:
    if hasattr(client, "create_structured"):
        kwargs: dict[str, Any] = {
            "messages": messages,
            "response_model": response_model,
        }
        kwargs = _with_optional_keyword(
            client.create_structured,
            kwargs,
            "callback_metadata",
            callback_metadata,
        )
        kwargs = _with_optional_keyword(
            client.create_structured,
            kwargs,
            "metadata",
            provider_metadata,
        )
        return client.create_structured(**kwargs)

    try:
        completions = client.chat.completions
    except AttributeError as error:
        raise TypeError(
            "client must expose create_structured() or chat.completions"
        ) from error

    if hasattr(completions, "create_with_completion"):
        return _call_with_optional_metadata(
            completions.create_with_completion,
            {
                "messages": messages,
                "response_model": response_model,
            },
            "metadata",
            provider_metadata,
        )

    return _call_with_optional_metadata(
        completions.create,
        {
            "messages": messages,
            "response_model": response_model,
        },
        "metadata",
        provider_metadata,
    )


_TRACE_METADATA_KEYS: tuple[str, ...] = (
    "cycle_id",
    "ticker",
    "analyzer_type",
    "regime_label",
)


def _build_callback_metadata(request: ReasonerRequest) -> dict[str, Any]:
    """Build the metadata block read by LiteLLM callbacks.

    spec v5.0.1 §14A.3 four trace fields (`cycle_id`, `ticker`,
    `analyzer_type`, `regime_label`) flow through `request.metadata` from
    the caller (main-core L6/L7). They are surfaced here so the LiteLLM
    callback bridge can read them out of the nested `reasoner` block and
    expose them on `CallbackContext`.
    """

    metadata = {
        "request_id": request.request_id,
        "caller_module": request.caller_module,
        "target_schema": request.target_schema,
        "provider": request.configured_provider,
        "model": request.configured_model,
    }
    request_metadata = request.metadata or {}
    for key in _TRACE_METADATA_KEYS:
        value = request_metadata.get(key)
        if value is None:
            continue
        metadata[key] = str(value)
    return metadata


def _call_with_optional_metadata(
    call_fn: Any,
    kwargs: dict[str, Any],
    metadata_key: str,
    metadata_value: Any,
) -> Any:
    if _supports_keyword(call_fn, metadata_key):
        kwargs = {**kwargs, metadata_key: metadata_value}
    return call_fn(**kwargs)


def _with_optional_keyword(
    call_fn: Any,
    kwargs: dict[str, Any],
    keyword: str,
    value: Any,
) -> dict[str, Any]:
    if _supports_keyword(call_fn, keyword):
        return {**kwargs, keyword: value}
    return kwargs


def _provider_metadata(
    request_metadata: dict[str, Any],
    callback_metadata: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(request_metadata)
    metadata["reasoner"] = callback_metadata
    return metadata


def _supports_keyword(call_fn: Any, keyword: str) -> bool:
    try:
        parameters = signature(call_fn).parameters.values()
    except (TypeError, ValueError):
        return False

    for parameter in parameters:
        if parameter.kind is Parameter.VAR_KEYWORD:
            return True
        if parameter.name == keyword and parameter.kind in {
            Parameter.KEYWORD_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        }:
            return True
    return False


def _split_client_response(response: Any) -> tuple[Any, Any | None]:
    if isinstance(response, tuple) and len(response) >= 2:
        return response[0], response[1]

    parsed_payload = _read_value(response, "parsed")
    if parsed_payload is not None and _read_value(response, "raw_output") is not None:
        return parsed_payload, response

    parsed_result = _read_value(response, "parsed_result")
    if parsed_result is not None and _read_value(response, "raw_output") is not None:
        return parsed_result, response

    return response, None


def _coerce_parsed_model(
    parsed_payload: Any,
    response_model: type[BaseModel],
) -> BaseModel:
    try:
        if isinstance(parsed_payload, response_model):
            return parsed_payload
        return response_model.model_validate(parsed_payload)
    except ValidationError as error:
        raise ParseValidationError(str(error)) from error


def _extract_raw_output(completion: Any | None, parsed_model: BaseModel) -> str:
    raw_output = _read_value(completion, "raw_output")
    if raw_output is not None:
        return str(raw_output)

    content = _extract_message_content(completion)
    if content is not None:
        return content

    return parsed_model.model_dump_json()


def _extract_message_content(completion: Any | None) -> str | None:
    choices = _read_value(completion, "choices")
    if not choices:
        return None

    first_choice = choices[0]
    message = _read_value(first_choice, "message")
    if message is not None:
        content = _read_value(message, "content")
        if content is not None:
            return str(content)

    text = _read_value(first_choice, "text")
    if text is not None:
        return str(text)

    return None


def _extract_token_usage(completion: Any | None) -> dict[str, int]:
    usage = _read_value(completion, "token_usage")
    if usage is None:
        usage = _read_value(completion, "usage")

    prompt = _read_nonnegative_int(usage, "prompt")
    if prompt == 0:
        prompt = _read_nonnegative_int(usage, "prompt_tokens")

    completion_tokens = _read_nonnegative_int(usage, "completion")
    if completion_tokens == 0:
        completion_tokens = _read_nonnegative_int(usage, "completion_tokens")

    total = _read_nonnegative_int(usage, "total")
    if total == 0:
        total = _read_nonnegative_int(usage, "total_tokens")
    if total == 0:
        total = prompt + completion_tokens

    return {
        "prompt": prompt,
        "completion": completion_tokens,
        "total": total,
    }


def _extract_cost_estimate(completion: Any | None) -> float:
    cost = _read_value(completion, "cost_estimate")
    if cost is None:
        cost = _read_value(completion, "response_cost")
    if cost is None:
        hidden_params = _read_value(completion, "_hidden_params")
        cost = _read_value(hidden_params, "response_cost")

    return _coerce_nonnegative_float(cost)


def _extract_latency_ms(completion: Any | None, elapsed_ms: int) -> int:
    latency_ms = _read_value(completion, "latency_ms")
    if latency_ms is None:
        latency_ms = _read_value(completion, "latency")
    if latency_ms is None:
        return max(elapsed_ms, 0)

    return _coerce_nonnegative_int(latency_ms)


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


def _read_value(source: Any | None, key: str) -> Any | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)
