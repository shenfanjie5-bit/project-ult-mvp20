from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from reasoner_runtime.config.models import CodexCliAuthSpec, ProviderProfile
from reasoner_runtime.providers import (
    CodexAuthError,
    CodexRateLimitError,
    CodexResponsesError,
    ParseValidationError,
    ProviderConfigError,
    build_client,
    build_codex_client,
)
from reasoner_runtime.providers.auth import CodexCredentials


@pytest.fixture(autouse=True)
def _enable_codex_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONER_RUNTIME_ENABLE_CODEX_OAUTH", "1")


_ACCOUNT_ID = "cbd0eb9f-1165-4e41-a20e-61b165b3bf13"


class _Echo(BaseModel):
    answer: str


class _NestedMappingEcho(BaseModel):
    items: list[dict[str, Any]]


def _b64url(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")


def _make_jwt(*, exp: int, account_id: str = _ACCOUNT_ID) -> str:
    header = _b64url({"alg": "RS256", "typ": "JWT"})
    payload = _b64url(
        {
            "exp": exp,
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        }
    )
    return f"{header}.{payload}.sig"


def _fresh_creds() -> CodexCredentials:
    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    return CodexCredentials(
        access_token=_make_jwt(exp=exp),
        refresh_token="rt_fresh",
        account_id=_ACCOUNT_ID,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _StaticAuthSource:
    def __init__(self, creds: CodexCredentials) -> None:
        self.creds = creds
        self.fetch_calls = 0

    def fetch(self) -> CodexCredentials:
        self.fetch_calls += 1
        return self.creds


class _FakeHttp:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return self.response


def _sse_completed_event(text: str, usage: dict[str, int] | None = None) -> str:
    body = {
        "type": "response.completed",
        "response": {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": text},
                    ]
                }
            ],
            "usage": usage or {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
        },
    }
    return f"data: {json.dumps(body)}\n\n"


def _profile() -> ProviderProfile:
    return ProviderProfile(
        provider="openai-codex",
        model="gpt-5-codex",
        timeout_ms=60000,
        fallback_priority=0,
        auth=CodexCliAuthSpec(),
    )


def test_codex_client_sends_required_headers_and_payload() -> None:
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=_sse_completed_event(json.dumps({"answer": "pong"})),
    )
    http = _FakeHttp(response)
    auth = _StaticAuthSource(_fresh_creds())

    client = build_codex_client(_profile(), 0, auth_source=auth, http=http)
    result = client.create_structured(
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say pong"},
        ],
        response_model=_Echo,
    )

    assert auth.fetch_calls == 1
    assert len(http.calls) == 1
    call = http.calls[0]
    headers = call["headers"]
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["chatgpt-account-id"] == _ACCOUNT_ID
    assert headers["originator"] == "reasoner-runtime"
    assert headers["OpenAI-Beta"] == "responses=experimental"

    payload = call["json"]
    assert payload["model"] == "gpt-5-codex"
    assert payload["instructions"] == "Be concise."
    assert payload["input"] == [{"role": "user", "content": "Say pong"}]
    assert payload["stream"] is True
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["name"] == "Echo"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    assert payload["text"]["format"]["schema"]["required"] == ["answer"]

    assert result.parsed_result == {"answer": "pong"}
    assert result.token_usage == {"prompt": 12, "completion": 4, "total": 16}
    assert result.cost_estimate == 0.0


def test_codex_client_rewrites_nested_mapping_schemas_to_strict_objects() -> None:
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=_sse_completed_event(json.dumps({"items": []})),
    )
    http = _FakeHttp(response)
    client = build_codex_client(
        _profile(),
        0,
        auth_source=_StaticAuthSource(_fresh_creds()),
        http=http,
    )

    client.create_structured(
        messages=[{"role": "user", "content": "empty"}],
        response_model=_NestedMappingEcho,
    )

    item_schema = http.calls[0]["json"]["text"]["format"]["schema"]["properties"][
        "items"
    ]["items"]
    assert item_schema["type"] == "object"
    assert item_schema["additionalProperties"] is False


def test_codex_client_strips_provider_prefix_from_model() -> None:
    profile = ProviderProfile(
        provider="openai-codex",
        model="openai-codex/gpt-5-codex-mini",
        timeout_ms=30000,
        auth=CodexCliAuthSpec(),
    )
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=_sse_completed_event(json.dumps({"answer": "ok"})),
    )
    http = _FakeHttp(response)

    client = build_codex_client(profile, 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)
    client.create_structured(messages=[{"role": "user", "content": "hi"}], response_model=_Echo)

    assert http.calls[0]["json"]["model"] == "gpt-5-codex-mini"


def test_codex_client_raises_codex_auth_error_on_401() -> None:
    response = SimpleNamespace(
        status_code=401,
        headers={"content-type": "application/json"},
        text="unauthorized",
        json=lambda: {"error": "unauthorized"},
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    with pytest.raises(CodexAuthError):
        client.create_structured(messages=[{"role": "user", "content": "hi"}], response_model=_Echo)


def test_codex_client_raises_rate_limit_on_429() -> None:
    response = SimpleNamespace(
        status_code=429,
        headers={"content-type": "application/json"},
        text="slow down",
        json=lambda: {},
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    with pytest.raises(CodexRateLimitError):
        client.create_structured(messages=[{"role": "user", "content": "hi"}], response_model=_Echo)


def test_codex_client_raises_responses_error_on_5xx() -> None:
    response = SimpleNamespace(
        status_code=503,
        headers={"content-type": "application/json"},
        text="upstream down",
        json=lambda: {},
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    with pytest.raises(CodexResponsesError):
        client.create_structured(messages=[{"role": "user", "content": "hi"}], response_model=_Echo)


def test_codex_client_raises_parse_validation_error_when_payload_invalid() -> None:
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=_sse_completed_event("not-json"),
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    with pytest.raises(ParseValidationError):
        client.create_structured(messages=[{"role": "user", "content": "hi"}], response_model=_Echo)


def test_codex_client_supports_non_stream_json_response() -> None:
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "application/json"},
        json=lambda: {
            "type": "response.completed",
            "response": {
                "output": [
                    {"content": [{"type": "output_text", "text": json.dumps({"answer": "yes"})}]}
                ],
                "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            },
        },
        text="",
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    result = client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    assert result.parsed_result == {"answer": "yes"}
    assert result.token_usage["total"] == 7


def test_codex_client_aggregates_delta_events() -> None:
    payload = json.dumps({"answer": "streamed"})
    chunks = []
    chunks.append({"type": "response.output_text.delta", "delta": payload[:5]})
    chunks.append({"type": "response.output_text.delta", "delta": payload[5:]})
    chunks.append({"type": "response.completed", "response": {"output": [], "usage": {}}})
    sse = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)

    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=sse,
    )
    http = _FakeHttp(response)
    client = build_codex_client(_profile(), 0, auth_source=_StaticAuthSource(_fresh_creds()), http=http)

    result = client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    assert result.parsed_result == {"answer": "streamed"}


def test_build_client_dispatches_to_codex_when_provider_matches() -> None:
    profile = _profile()

    class _Sentinel:
        provider = "openai-codex"

    sentinel_creds = _fresh_creds()
    response = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        text=_sse_completed_event(json.dumps({"answer": "via-build-client"})),
    )
    http = _FakeHttp(response)

    import reasoner_runtime.providers.client as provider_client_module
    import reasoner_runtime.providers.codex_client as codex_module

    original_build = codex_module.build_codex_client

    def patched_build_codex_client(p, mr, *, auth_source=None, http=None, **kw):
        return original_build(
            p,
            mr,
            auth_source=_StaticAuthSource(sentinel_creds),
            http=http or _FakeHttp(response),
        )

    codex_module.build_codex_client = patched_build_codex_client
    try:
        client = build_client(profile, 0)
        result = client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )
    finally:
        codex_module.build_codex_client = original_build

    assert result.parsed_result == {"answer": "via-build-client"}
    assert provider_client_module is not None  # sanity import keeper


def test_build_codex_client_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        build_codex_client(_profile(), -1, auth_source=_StaticAuthSource(_fresh_creds()), http=_FakeHttp(None))


def test_build_codex_client_rejects_non_codex_provider() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", timeout_ms=10000)
    with pytest.raises(ValueError, match="openai-codex"):
        build_codex_client(profile, 0, auth_source=_StaticAuthSource(_fresh_creds()), http=_FakeHttp(None))


def test_build_client_rejects_codex_when_env_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REASONER_RUNTIME_ENABLE_CODEX_OAUTH", raising=False)

    with pytest.raises(ProviderConfigError, match="REASONER_RUNTIME_ENABLE_CODEX_OAUTH"):
        build_client(_profile(), 0)


def test_build_client_rejects_codex_when_env_flag_is_not_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONER_RUNTIME_ENABLE_CODEX_OAUTH", "true")

    with pytest.raises(ProviderConfigError, match="REASONER_RUNTIME_ENABLE_CODEX_OAUTH"):
        build_client(_profile(), 0)
