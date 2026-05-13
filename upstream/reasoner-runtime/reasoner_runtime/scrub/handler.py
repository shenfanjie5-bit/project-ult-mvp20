from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from reasoner_runtime.config.models import ScrubRuleSet
from reasoner_runtime.scrub.rules import scrub_text


@dataclass(frozen=True)
class ScrubbedRequest:
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]
    sanitized_input: str


def scrub_payload(
    value: Any,
    rule_set: ScrubRuleSet | None = None,
    *,
    scrub_keys: bool = True,
) -> Any:
    if isinstance(value, str):
        return scrub_text(value, rule_set)
    if isinstance(value, dict):
        scrubbed: dict[Any, Any] = {}
        for key, item in value.items():
            scrubbed_key = (
                scrub_text(key, rule_set)
                if scrub_keys and isinstance(key, str)
                else key
            )
            output_key = _unique_scrubbed_key(scrubbed_key, scrubbed)
            scrubbed[output_key] = scrub_payload(
                item,
                rule_set,
                scrub_keys=scrub_keys,
            )
        return scrubbed
    if isinstance(value, list):
        return [scrub_payload(item, rule_set, scrub_keys=scrub_keys) for item in value]
    if isinstance(value, tuple):
        return tuple(
            scrub_payload(item, rule_set, scrub_keys=scrub_keys) for item in value
        )

    return value


def _unique_scrubbed_key(key: Any, scrubbed: dict[Any, Any]) -> Any:
    if key not in scrubbed:
        return key

    if not isinstance(key, str):
        return key

    collision_index = 2
    while True:
        candidate = f"{key} [DUPLICATE_KEY_{collision_index}]"
        if candidate not in scrubbed:
            return candidate
        collision_index += 1


def scrub_request(
    messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    rule_set: ScrubRuleSet | None = None,
) -> ScrubbedRequest:
    scrubbed_messages = cast(list[dict[str, Any]], scrub_payload(messages, rule_set))
    scrubbed_metadata = cast(dict[str, Any], scrub_payload(metadata or {}, rule_set))
    sanitized_input = json.dumps(
        {
            "messages": scrubbed_messages,
            "metadata": scrubbed_metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return ScrubbedRequest(
        messages=scrubbed_messages,
        metadata=scrubbed_metadata,
        sanitized_input=sanitized_input,
    )


def scrub_input(
    messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    rule_set: ScrubRuleSet | None = None,
) -> str:
    return scrub_request(messages, metadata, rule_set).sanitized_input


__all__ = [
    "ScrubbedRequest",
    "scrub_input",
    "scrub_payload",
    "scrub_request",
]
