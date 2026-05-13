from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers.auth import (
    CodexAuthError,
    CodexAuthSource,
    CodexCliAuthSource,
    CodexCredentials,
)
from reasoner_runtime.providers.routing import ParseValidationError
from reasoner_runtime.structured.parser import StructuredCallResult

_CODEX_PROVIDER = "openai-codex"
_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_DEFAULT_ORIGINATOR = "reasoner-runtime"
_DEFAULT_OPENAI_BETA = "responses=experimental"


class CodexResponsesError(RuntimeError):
    """Non-auth failure returned by the codex responses endpoint."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"codex responses error {status_code}: {body}")


class CodexRateLimitError(CodexResponsesError):
    """Raised when the codex endpoint returns 429."""


@dataclass
class CodexResponsesClient:
    profile: ProviderProfile
    max_retries: int
    auth_source: CodexAuthSource
    http: Any
    originator: str = _DEFAULT_ORIGINATOR
    responses_url: str = _CODEX_RESPONSES_URL
    openai_beta: str = _DEFAULT_OPENAI_BETA
    _http_owned: bool = field(default=False, repr=False)

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        metadata: Mapping[str, Any] | None = None,
        callback_metadata: Mapping[str, Any] | None = None,
    ) -> StructuredCallResult:
        if response_model is None:
            raise ValueError("response_model is required")

        creds = self.auth_source.fetch()
        instructions, input_messages = _split_system_messages(messages)
        payload = self._build_payload(
            input_messages=input_messages,
            instructions=instructions,
            response_model=response_model,
        )
        headers = self._build_headers(creds)
        timeout_s = self.profile.timeout_ms / 1000

        started_at = perf_counter()
        try:
            response = self.http.post(
                self.responses_url,
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )
        except Exception as error:  # noqa: BLE001 — surface transport errors to fallback
            raise CodexResponsesError(0, f"transport error: {error}") from error
        elapsed_ms = max(int((perf_counter() - started_at) * 1000), 0)

        status_code = getattr(response, "status_code", 0)
        if status_code in (401, 403):
            raise CodexAuthError(
                f"codex responses endpoint returned {status_code}: "
                f"{_safe_response_text(response)}"
            )
        if status_code == 429:
            raise CodexRateLimitError(status_code, _safe_response_text(response))
        if status_code >= 400:
            raise CodexResponsesError(status_code, _safe_response_text(response))

        text, token_usage = _consume_responses(response)
        if not text.strip():
            raise ParseValidationError("codex responses endpoint returned empty output")

        try:
            parsed_model = response_model.model_validate_json(text)
        except ValidationError as error:
            raise ParseValidationError(str(error)) from error

        return StructuredCallResult(
            parsed_result=parsed_model.model_dump(mode="json"),
            raw_output=text,
            token_usage=token_usage,
            cost_estimate=0.0,
            latency_ms=elapsed_ms,
        )

    def _build_headers(self, creds: CodexCredentials) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds.access_token}",
            "chatgpt-account-id": creds.account_id,
            "originator": self.originator,
            "OpenAI-Beta": self.openai_beta,
            "accept": "text/event-stream",
            "content-type": "application/json",
        }

    def _build_payload(
        self,
        *,
        input_messages: list[dict[str, Any]],
        instructions: str | None,
        response_model: type[BaseModel],
    ) -> dict[str, Any]:
        schema = _to_strict_schema(response_model.model_json_schema())
        schema_name = _sanitize_schema_name(response_model.__name__)
        payload: dict[str, Any] = {
            "model": _strip_provider_prefix(self.profile.model),
            "input": input_messages,
            "instructions": instructions or " ",
            "stream": True,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        return payload


def build_codex_client(
    profile: ProviderProfile,
    max_retries: int,
    *,
    auth_source: CodexAuthSource | None = None,
    http: Any | None = None,
    originator: str = _DEFAULT_ORIGINATOR,
    responses_url: str = _CODEX_RESPONSES_URL,
    openai_beta: str = _DEFAULT_OPENAI_BETA,
) -> CodexResponsesClient:
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")
    if profile.provider != _CODEX_PROVIDER:
        raise ValueError(
            f"build_codex_client requires provider='{_CODEX_PROVIDER}', "
            f"got '{profile.provider}'"
        )

    resolved_auth_source = auth_source or _resolve_auth_source(profile)
    resolved_http, owned = _resolve_http(http)

    client = CodexResponsesClient(
        profile=profile,
        max_retries=max_retries,
        auth_source=resolved_auth_source,
        http=resolved_http,
        originator=originator,
        responses_url=responses_url,
        openai_beta=openai_beta,
    )
    client._http_owned = owned
    return client


def _resolve_auth_source(profile: ProviderProfile) -> CodexAuthSource:
    auth_spec = profile.auth
    if auth_spec is None:
        return CodexCliAuthSource()
    if auth_spec.kind != "codex_cli":
        raise ValueError(
            f"unsupported codex auth kind: {auth_spec.kind!r}"
        )
    if auth_spec.path:
        from pathlib import Path

        return CodexCliAuthSource(path=Path(auth_spec.path).expanduser())
    return CodexCliAuthSource()


def _resolve_http(http: Any | None) -> tuple[Any, bool]:
    if http is not None:
        return http, False
    try:
        import httpx
    except ImportError as error:
        raise CodexAuthError(
            "httpx is required for the openai-codex provider; install it via requirements.txt"
        ) from error
    return httpx.Client(timeout=60.0), True


def _split_system_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    instructions_parts: list[str] = []
    rest: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            content = message.get("content", "")
            if isinstance(content, str) and content:
                instructions_parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text_value = item.get("text") or item.get("content")
                        if isinstance(text_value, str) and text_value:
                            instructions_parts.append(text_value)
            continue
        rest.append(message)
    instructions = "\n\n".join(instructions_parts) if instructions_parts else None
    return instructions, rest


def _strip_provider_prefix(model: str) -> str:
    if model.startswith(f"{_CODEX_PROVIDER}/"):
        return model.split("/", 1)[1]
    return model


def _sanitize_schema_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name).lstrip("_-")
    return cleaned or "ReasonerSchema"


def _to_strict_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        rewritten: dict[str, Any] = {key: _to_strict_schema(value) for key, value in schema.items()}
        if rewritten.get("type") == "object" or "properties" in rewritten:
            rewritten["additionalProperties"] = False
            properties = rewritten.get("properties")
            if isinstance(properties, dict):
                rewritten["required"] = list(properties.keys())
        return rewritten
    if isinstance(schema, list):
        return [_to_strict_schema(item) for item in schema]
    return schema


def _safe_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text[:512]
    return repr(response)[:512]


def _consume_responses(response: Any) -> tuple[str, dict[str, int]]:
    """Aggregate text and usage from an SSE or JSON codex responses payload."""

    content_type = _content_type(response)
    is_event_stream = "text/event-stream" in content_type

    accumulated: list[str] = []
    completed_text: str | None = None
    usage: dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}

    for event in _iter_events(response, is_event_stream):
        event_type = event.get("type") if isinstance(event, dict) else None

        if isinstance(event, dict):
            delta = event.get("delta")
            if isinstance(delta, str) and event_type and "delta" in event_type:
                accumulated.append(delta)
            elif isinstance(event_type, str) and event_type.endswith(".done") and isinstance(event.get("text"), str):
                completed_text = event["text"]
            elif event_type == "response.completed" or event_type == "response.done":
                response_obj = event.get("response")
                if isinstance(response_obj, dict):
                    completed_text = _extract_response_text(response_obj) or completed_text
                    usage = _extract_usage(response_obj.get("usage"))

    text = completed_text if completed_text is not None else "".join(accumulated)
    return text, usage


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() == "content-type":
                return str(value).lower()
    if headers is not None and hasattr(headers, "get"):
        value = headers.get("content-type") or headers.get("Content-Type")
        if isinstance(value, str):
            return value.lower()
    return ""


def _iter_events(response: Any, is_event_stream: bool) -> Iterable[Any]:
    text = getattr(response, "text", None)
    if isinstance(text, str) and _looks_like_sse(text):
        return _events_from_lines(text.splitlines())

    iter_lines = getattr(response, "iter_lines", None)
    if not is_event_stream and not (isinstance(text, str) and _looks_like_sse(text)):
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return payload

    if isinstance(text, str):
        return _events_from_lines(text.splitlines())
    if callable(iter_lines):
        return _events_from_lines(iter_lines())
    return []


def _looks_like_sse(text: str) -> bool:
    head = text.lstrip()[:64]
    return head.startswith("event:") or head.startswith("data:")


def _events_from_lines(lines: Iterable[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    data_buffer: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
        line = line.rstrip("\r")
        if not line:
            if data_buffer:
                payload = "\n".join(data_buffer).strip()
                data_buffer.clear()
                event = _parse_data_payload(payload)
                if event is not None:
                    events.append(event)
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_buffer.append(line[5:].lstrip())
    if data_buffer:
        payload = "\n".join(data_buffer).strip()
        event = _parse_data_payload(payload)
        if event is not None:
            events.append(event)
    return events


def _parse_data_payload(payload: str) -> dict[str, Any] | None:
    if not payload or payload == "[DONE]":
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_response_text(response_obj: dict[str, Any]) -> str | None:
    output = response_obj.get("output")
    if not isinstance(output, list):
        return None
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for entry in content:
            if not isinstance(entry, dict):
                continue
            text_value = entry.get("text")
            if isinstance(text_value, str):
                chunks.append(text_value)
    if not chunks:
        return None
    return "".join(chunks)


def _extract_usage(usage_obj: Any) -> dict[str, int]:
    if not isinstance(usage_obj, dict):
        return {"prompt": 0, "completion": 0, "total": 0}

    def _read_int(*keys: str) -> int:
        for key in keys:
            value = usage_obj.get(key)
            if isinstance(value, (int, float)):
                return max(int(value), 0)
        return 0

    prompt = _read_int("input_tokens", "prompt_tokens", "prompt")
    completion = _read_int("output_tokens", "completion_tokens", "completion")
    total = _read_int("total_tokens", "total")
    if total == 0:
        total = prompt + completion
    return {"prompt": prompt, "completion": completion, "total": total}
