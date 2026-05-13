from __future__ import annotations

import json
from copy import deepcopy
from time import perf_counter

from reasoner_runtime.config import ScrubRule, ScrubRuleSet
from reasoner_runtime.scrub import (
    ScrubbedRequest,
    scrub_input,
    scrub_payload,
    scrub_request,
    scrub_text,
)
from reasoner_runtime.scrub.rules import enabled_rule_types


def test_enabled_rule_types_defaults_to_all_builtin_rules() -> None:
    assert enabled_rule_types() == {"name", "phone", "account"}


def test_enabled_rule_types_respects_disabled_rule_set() -> None:
    assert enabled_rule_types(ScrubRuleSet(enabled=False)) == set()


def test_enabled_rule_types_skips_disabled_single_rules() -> None:
    rule_set = ScrubRuleSet(
        rules=[
            ScrubRule(pattern_type="name"),
            ScrubRule(pattern_type="phone", enabled=False),
            ScrubRule(pattern_type="account"),
        ]
    )

    assert enabled_rule_types(rule_set) == {"name", "account"}


def test_scrub_text_redacts_name_variants() -> None:
    samples = [
        ("姓名 张三", "张三"),
        ("客户李四", "李四"),
        ("联系人：王五", "王五"),
        ("name Alice", "Alice"),
        ("customer Bob Smith", "Bob Smith"),
        ("contact: Carol Jones", "Carol Jones"),
    ]

    for source, raw_value in samples:
        scrubbed = scrub_text(source)

        assert "[REDACTED_NAME]" in scrubbed
        assert raw_value not in scrubbed


def test_scrub_text_redacts_phone_variants() -> None:
    samples = [
        "手机 13800138000",
        "手机 138-0013-8000",
        "电话 +86 138 0013 8000",
        "phone +86-139-0013-9000",
    ]

    for source in samples:
        scrubbed = scrub_text(source)

        assert "[REDACTED_PHONE]" in scrubbed
        assert "13800138000" not in scrubbed
        assert "138-0013-8000" not in scrubbed
        assert "139-0013-9000" not in scrubbed


def test_scrub_text_redacts_account_variants() -> None:
    samples = [
        ("账户 6222021234567890123", "6222021234567890123"),
        ("账号：123456789012", "123456789012"),
        ("account 1234567890123456", "1234567890123456"),
        ("acct: 1234-5678-9012-3456", "1234-5678-9012-3456"),
        ("acct number 123456789012", "123456789012"),
        ("acct no. 123456789012", "123456789012"),
        ("card 6222 0212 3456 7890 123", "6222 0212 3456 7890 123"),
    ]

    for source, raw_value in samples:
        scrubbed = scrub_text(source)

        assert "[REDACTED_ACCOUNT]" in scrubbed
        assert raw_value not in scrubbed


def test_scrub_text_redacts_account_identifier_variants() -> None:
    samples = [
        ("account_id=acct_123456", "acct_123456"),
        ("account-id: acct-123456", "acct-123456"),
        ("account id ACCT_123456", "ACCT_123456"),
        ("account number user-123456", "user-123456"),
        ("account acct_123456", "acct_123456"),
        ("acct_id=acct_123456", "acct_123456"),
        ("账户ID：acct_123456", "acct_123456"),
        ("账号id=acct-123456", "acct-123456"),
    ]

    for source, raw_value in samples:
        scrubbed = scrub_text(source)

        assert "[REDACTED_ACCOUNT]" in scrubbed
        assert raw_value not in scrubbed


def test_scrub_text_redacts_english_account_labels_with_chinese_separators() -> None:
    samples = [
        ("account：acct_123456", "acct_123456"),
        ("acct为acct-123456", "acct-123456"),
        ("card是6222021234567890123", "6222021234567890123"),
    ]

    for source, raw_value in samples:
        scrubbed = scrub_text(source)

        assert "[REDACTED_ACCOUNT]" in scrubbed
        assert raw_value not in scrubbed


def test_scrub_text_uses_account_id_labels_as_field_boundaries() -> None:
    scrubbed = scrub_text("name Alice account_id=acct_123456")

    assert scrubbed == "name [REDACTED_NAME] account_id=[REDACTED_ACCOUNT]"
    assert "Alice" not in scrubbed
    assert "acct_123456" not in scrubbed


def test_scrub_text_does_not_redact_account_like_non_labels() -> None:
    samples = [
        "accounting2024",
        "accountability-2024",
        "account_idacct_123456",
        "my_account_id=acct_123456",
        "account active",
        "account 123456",
    ]

    for source in samples:
        assert scrub_text(source) == source


def test_scrub_text_redacts_compact_chinese_fields_without_losing_account_label() -> None:
    scrubbed = scrub_text("姓名张三账户6222021234567890123手机13800138000")

    assert scrubbed == (
        "姓名[REDACTED_NAME]账户[REDACTED_ACCOUNT]手机[REDACTED_PHONE]"
    )
    assert "张三" not in scrubbed
    assert "6222021234567890123" not in scrubbed
    assert "13800138000" not in scrubbed


def test_scrub_text_respects_disabled_rules() -> None:
    rule_set = ScrubRuleSet(
        rules=[
            ScrubRule(pattern_type="name"),
            ScrubRule(pattern_type="phone", enabled=False),
            ScrubRule(pattern_type="account"),
        ]
    )

    scrubbed = scrub_text(
        "姓名 张三 手机 13800138000 账户 6222021234567890123",
        rule_set,
    )

    assert "张三" not in scrubbed
    assert "6222021234567890123" not in scrubbed
    assert "13800138000" in scrubbed


def test_scrub_payload_recurses_without_mutating_input() -> None:
    payload = {
        "role": "user",
        "content": "姓名 张三 手机 13800138000",
        "metadata": {
            "contact": "name Alice account 123456789012",
            "flags": [True, 3, None],
            "tuple": ("账号 123456789012", 7),
        },
    }
    original = deepcopy(payload)

    scrubbed = scrub_payload(payload)

    assert payload == original
    assert scrubbed["role"] == "user"
    assert scrubbed["metadata"]["flags"] == [True, 3, None]
    assert scrubbed["metadata"]["tuple"][1] == 7
    assert "张三" not in json.dumps(scrubbed, ensure_ascii=False)
    assert "Alice" not in json.dumps(scrubbed, ensure_ascii=False)
    assert "123456789012" not in json.dumps(scrubbed, ensure_ascii=False)


def test_scrub_payload_scrubs_string_dict_keys() -> None:
    payload = {
        "name Alice account 123456789012": {
            "13800138000": "ok",
            "nested": {"acct 999988887777": "姓名 张三"},
            7: "kept",
        }
    }

    scrubbed = scrub_payload(payload)
    serialized = json.dumps(scrubbed, ensure_ascii=False)

    assert "Alice" not in serialized
    assert "123456789012" not in serialized
    assert "13800138000" not in serialized
    assert "999988887777" not in serialized
    assert "张三" not in serialized
    assert "name [REDACTED_NAME] account [REDACTED_ACCOUNT]" in scrubbed
    nested = scrubbed["name [REDACTED_NAME] account [REDACTED_ACCOUNT]"]
    assert "[REDACTED_PHONE]" in nested
    assert "acct [REDACTED_ACCOUNT]" in nested["nested"]
    assert nested[7] == "kept"


def test_scrub_payload_preserves_account_like_nested_metadata_keys() -> None:
    payload = {
        "accounting2024": {
            "accountability-2024": "kept",
            "nested": {
                "account_idacct_123456": "also kept",
                "my_account_id=acct_123456": "not a label boundary",
            },
        }
    }

    assert scrub_payload(payload) == payload


def test_scrub_payload_preserves_colliding_sanitized_dict_keys() -> None:
    payload = {
        "name Alice": "first",
        "name Bob": "second",
    }

    scrubbed = scrub_payload(payload)
    serialized = json.dumps(scrubbed, ensure_ascii=False)

    assert scrubbed == {
        "name [REDACTED_NAME]": "first",
        "name [REDACTED_NAME] [DUPLICATE_KEY_2]": "second",
    }
    assert "Alice" not in serialized
    assert "Bob" not in serialized


def test_scrub_request_builds_deterministic_sanitized_input() -> None:
    messages = [
        {"role": "system", "content": "保持结构化输出"},
        {
            "role": "user",
            "content": "姓名 张三 手机 138-0013-8000 账户 6222021234567890123",
        },
    ]
    metadata = {"z": 2, "a": "contact Alice account 123456789012"}

    first = scrub_request(messages, metadata)
    second = scrub_request(messages, metadata)
    payload = json.loads(first.sanitized_input)

    assert isinstance(first, ScrubbedRequest)
    assert first.sanitized_input == second.sanitized_input
    assert payload == {"messages": first.messages, "metadata": first.metadata}
    assert first.messages[0]["role"] == "system"
    assert first.messages[1]["role"] == "user"
    assert "张三" not in first.sanitized_input
    assert "138-0013-8000" not in first.sanitized_input
    assert "6222021234567890123" not in first.sanitized_input
    assert "Alice" not in first.sanitized_input


def test_scrub_request_scrubs_metadata_keys_before_serialization() -> None:
    messages = [{"role": "user", "content": "ok"}]
    metadata = {
        "name Alice account 123456789012": "value",
        "nested": {
            "13800138000": {
                "acct 999988887777": "kept",
            }
        },
    }

    scrubbed = scrub_request(messages, metadata)
    payload = json.loads(scrubbed.sanitized_input)

    assert "Alice" not in scrubbed.sanitized_input
    assert "123456789012" not in scrubbed.sanitized_input
    assert "13800138000" not in scrubbed.sanitized_input
    assert "999988887777" not in scrubbed.sanitized_input
    assert "name [REDACTED_NAME] account [REDACTED_ACCOUNT]" in payload["metadata"]
    assert "[REDACTED_PHONE]" in payload["metadata"]["nested"]
    assert (
        "acct [REDACTED_ACCOUNT]"
        in payload["metadata"]["nested"]["[REDACTED_PHONE]"]
    )


def test_scrub_request_serializes_all_colliding_sanitized_metadata_keys() -> None:
    messages = [{"role": "user", "content": "ok"}]
    metadata = {
        "name Alice": "first",
        "name Bob": "second",
    }

    scrubbed = scrub_request(messages, metadata)
    payload = json.loads(scrubbed.sanitized_input)

    assert payload["metadata"] == {
        "name [REDACTED_NAME]": "first",
        "name [REDACTED_NAME] [DUPLICATE_KEY_2]": "second",
    }
    assert "Alice" not in scrubbed.sanitized_input
    assert "Bob" not in scrubbed.sanitized_input


def test_scrub_input_is_sanitized_input_wrapper() -> None:
    messages = [{"role": "user", "content": "name Alice account 123456789012"}]
    metadata = {"phone": "13800138000"}

    assert scrub_input(messages, metadata) == scrub_request(
        messages,
        metadata,
    ).sanitized_input


def test_scrub_request_runtime_baseline_under_100ms() -> None:
    messages = [
        {
            "role": "user",
            "content": "姓名 张三 手机 13800138000 账户 6222021234567890123",
        }
    ]
    metadata = {"contact": "name Alice account 123456789012"}

    scrub_request(messages, metadata)
    started_at = perf_counter()
    scrub_request(messages, metadata)
    elapsed_ms = (perf_counter() - started_at) * 1000

    assert elapsed_ms < 100
