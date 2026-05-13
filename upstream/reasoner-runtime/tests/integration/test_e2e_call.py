from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

import reasoner_runtime


class E2EPayload(BaseModel):
    answer: str
    confidence: float


def test_generate_structured_with_replay_e2e_scrub_fallback_replay_contract() -> None:
    primary = reasoner_runtime.ProviderProfile(
        provider="openai",
        model="gpt-4",
        fallback_priority=0,
    )
    fallback = reasoner_runtime.ProviderProfile(
        provider="anthropic",
        model="claude-sonnet-4.5",
        fallback_priority=1,
    )
    calls: list[dict[str, Any]] = []
    client_factory_calls: list[tuple[str, str, int]] = []

    def client_factory(
        profile: reasoner_runtime.ProviderProfile,
        max_retries: int,
    ) -> _E2EClient:
        client_factory_calls.append((profile.provider, profile.model, max_retries))
        return _E2EClient(profile, calls)

    request = reasoner_runtime.ReasonerRequest(
        request_id="req-e2e",
        caller_module="main-core-smoke",
        target_schema="E2EPayload",
        messages=[
            {"role": "system", "content": "返回 JSON"},
            {
                "role": "user",
                "content": (
                    "姓名 张三 name Ada Lovelace 手机 +86 138-0013-8000 "
                    "账户 6222021234567890123 account_id=acct_123456 "
                    "account acct-123456"
                ),
            },
        ],
        metadata={
            "case": "联系人 李四 contact Grace Hopper phone 13900139000",
            "billing": {
                "numeric": "账户 6222021234567890123",
                "alpha": "account_id=acct_123456 account acct-123456",
            },
        },
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )

    result, bundle = reasoner_runtime.generate_structured_with_replay(
        request,
        provider_profiles=[fallback, primary],
        schema_registry={"E2EPayload": E2EPayload},
        client_factory=client_factory,
    )

    assert client_factory_calls == [
        ("openai", "gpt-4", 1),
        ("anthropic", "claude-sonnet-4.5", 1),
    ]
    assert [call["target"] for call in calls] == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert result.parsed_result == {"answer": "fallback-ok", "confidence": 0.87}
    assert result.actual_provider == "anthropic"
    assert result.actual_model == "claude-sonnet-4.5"
    assert result.fallback_path == [
        "openai/gpt-4",
        "anthropic/claude-sonnet-4.5",
    ]
    assert result.retry_count == 0
    assert result.token_usage == {"prompt": 21, "completion": 9, "total": 30}
    assert result.cost_estimate == 0.045
    assert result.latency_ms == 37

    replay_fields = bundle.model_dump()
    for field_name in (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    ):
        assert field_name in replay_fields

    raw_output = ' \n{"answer":"fallback-ok","confidence":0.87}\n '
    assert bundle.raw_output == raw_output
    assert bundle.parsed_result == result.parsed_result
    assert bundle.input_hash == _sha256(bundle.sanitized_input)
    assert bundle.output_hash == _sha256(raw_output)
    assert bundle.llm_lineage == {
        "provider": "anthropic",
        "model": "claude-sonnet-4.5",
        "configured_target": "openai/gpt-4",
        "failure_class": "success_with_fallback",
        "fallback_path": result.fallback_path,
        "retry_count": 0,
    }

    sanitized_payload = json.loads(bundle.sanitized_input)
    for call in calls:
        assert call["messages"] == sanitized_payload["messages"]
        provider_metadata = dict(call["metadata"])
        reasoner_metadata = provider_metadata.pop("reasoner")
        assert provider_metadata == sanitized_payload["metadata"]
        assert reasoner_metadata == {
            "request_id": "req-e2e",
            "caller_module": "main-core-smoke",
            "target_schema": "E2EPayload",
            "provider": "openai",
            "model": "gpt-4",
        }

    provider_payload = json.dumps(
        {
            "messages": calls[-1]["messages"],
            "metadata": {
                key: value
                for key, value in calls[-1]["metadata"].items()
                if key != "reasoner"
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert provider_payload == bundle.sanitized_input

    for raw_value in (
        "张三",
        "李四",
        "Ada Lovelace",
        "Grace Hopper",
        "+86 138-0013-8000",
        "13900139000",
        "6222021234567890123",
        "acct_123456",
        "acct-123456",
    ):
        assert raw_value not in provider_payload
        assert raw_value not in bundle.sanitized_input


class _E2EClient:
    def __init__(
        self,
        profile: reasoner_runtime.ProviderProfile,
        calls: list[dict[str, Any]],
    ) -> None:
        self.profile = profile
        self.calls = calls

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        metadata: dict[str, Any],
    ) -> Any:
        target = f"{self.profile.provider}/{self.profile.model}"
        self.calls.append(
            {
                "target": target,
                "messages": messages,
                "metadata": metadata,
            }
        )
        if self.profile.provider == "openai":
            raise ConnectionError("primary unavailable")

        raw_output = ' \n{"answer":"fallback-ok","confidence":0.87}\n '
        completion = SimpleNamespace(
            raw_output=raw_output,
            usage={"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
            response_cost=0.045,
            latency_ms=37,
        )
        return response_model(answer="fallback-ok", confidence=0.87), completion


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
