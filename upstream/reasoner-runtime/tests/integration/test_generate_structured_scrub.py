from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from reasoner_runtime.config import ProviderProfile, ScrubRule, ScrubRuleSet
from reasoner_runtime.core import ReasonerRequest, generate_structured_with_replay
from reasoner_runtime.replay import sha256_text
from reasoner_runtime.structured import StructuredCallResult


class ScrubPayload(BaseModel):
    answer: str


def test_generate_structured_uses_same_scrubbed_messages_for_provider_and_replay() -> None:
    raw_output = '{"answer":"ok"}'
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok"},
            raw_output=raw_output,
            token_usage={"prompt": 2, "completion": 3, "total": 5},
            cost_estimate=0.01,
            latency_ms=8,
        )
    )
    request = ReasonerRequest(
        request_id="req-scrub",
        caller_module="integration-test",
        target_schema="ScrubPayload",
        messages=[
            {"role": "system", "content": "返回 JSON"},
            {
                "role": "user",
                "content": (
                    "姓名 张三 手机 +86 138-0013-8000 "
                    "账户 6222021234567890123"
                ),
            },
        ],
        metadata={
            "contact": "name Alice account 123456789012",
            "nested": {"phone": "13900139000", "count": 3, "active": True},
        },
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=1,
    )

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[
            ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
        ],
        schema_registry={"ScrubPayload": ScrubPayload},
        client_factory=lambda _profile, _max_retries: client,
    )

    replay_payload = json.loads(bundle.sanitized_input)
    outbound_messages = client.calls[0]["messages"]
    outbound_serialized = json.dumps(outbound_messages, ensure_ascii=False)

    assert outbound_messages == replay_payload["messages"]
    assert replay_payload["metadata"]["nested"]["count"] == 3
    assert replay_payload["metadata"]["nested"]["active"] is True
    assert bundle.input_hash == sha256_text(bundle.sanitized_input)
    assert bundle.raw_output == raw_output

    for raw_value in [
        "张三",
        "+86 138-0013-8000",
        "6222021234567890123",
        "Alice",
        "123456789012",
        "13900139000",
    ]:
        assert raw_value not in outbound_serialized
        assert raw_value not in bundle.sanitized_input

    assert request.messages[1]["content"].startswith("姓名 张三")


def test_generate_structured_passes_scrub_rule_set_to_core_boundary() -> None:
    client = _FakeStructuredClient(
        StructuredCallResult(
            parsed_result={"answer": "ok"},
            raw_output='{"answer":"ok"}',
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost_estimate=0.0,
            latency_ms=1,
        )
    )
    request = ReasonerRequest(
        request_id="req-scrub-rule-set",
        caller_module="integration-test",
        target_schema="ScrubPayload",
        messages=[{"role": "user", "content": "姓名 张三 手机 13800138000"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=0,
    )

    _result, bundle = generate_structured_with_replay(
        request,
        provider_profiles=[
            ProviderProfile(provider="openai", model="gpt-4", fallback_priority=0)
        ],
        schema_registry={"ScrubPayload": ScrubPayload},
        client_factory=lambda _profile, _max_retries: client,
        scrub_rule_set=ScrubRuleSet(
            rules=[
                ScrubRule(pattern_type="name"),
                ScrubRule(pattern_type="phone", enabled=False),
            ]
        ),
    )

    replay_payload = json.loads(bundle.sanitized_input)

    assert "张三" not in client.calls[0]["messages"][0]["content"]
    assert "13800138000" in client.calls[0]["messages"][0]["content"]
    assert replay_payload["messages"] == client.calls[0]["messages"]


class _FakeStructuredClient:
    def __init__(self, result: StructuredCallResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
    ) -> StructuredCallResult:
        self.calls.append(
            {
                "messages": messages,
                "response_model": response_model,
            }
        )
        return self.result
