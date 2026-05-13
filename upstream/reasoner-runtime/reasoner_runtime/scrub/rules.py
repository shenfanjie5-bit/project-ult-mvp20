from __future__ import annotations

import re

from reasoner_runtime.config.models import ScrubRuleSet


REDACTED_NAME = "[REDACTED_NAME]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_ACCOUNT = "[REDACTED_ACCOUNT]"

_RULE_ORDER = ("name", "phone", "account")

_NEXT_FIELD_BOUNDARY = (
    r"(?=\s*(?:"
    r"姓名|客户|联系人|手机|电话|账户|账号|"
    r"(?i:name|customer|contact|phone|tel|telephone)\b|"
    r"(?i:account(?:[_-]id|\s+id|\s+number|\s+no\.?)?|"
    r"acct(?:[_-]id|\s+id)?|card(?:\s+number|\s+no\.?)?)"
    r"(?![A-Za-z0-9_-])"
    r"|[,，;；。.\n\r]|$))"
)

_NAME_PATTERNS = (
    re.compile(
        r"(?P<prefix>(?:姓名|客户|联系人)\s*(?:为|是|:|：|=)?\s*)"
        r"(?P<value>[\u4e00-\u9fff]{2,4}?|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}?)"
        + _NEXT_FIELD_BOUNDARY
    ),
    re.compile(
        r"(?P<prefix>\b(?i:name|customer|contact)\b\s*"
        r"(?:(?i:is)|=|:|#)?\s*)"
        r"(?P<value>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}?|[\u4e00-\u9fff]{2,4}?)"
        + _NEXT_FIELD_BOUNDARY,
    ),
)

_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[\s-]*)?1[3-9]\d(?:[\s-]*\d){8}(?!\d)"
    r"|(?<!\d)(?:\+?1[\s.-]*)?(?:\(?\d{3}\)?[\s.-]*)\d{3}[\s.-]*\d{4}(?!\d)"
)

_ACCOUNT_VALUE_PATTERN = (
    r"(?:"
    r"(?:\d[\s-]*){11,18}\d"
    r"|"
    r"(?=[A-Za-z0-9_-]{6,})(?=[A-Za-z0-9_-]*\d)"
    r"(?=[A-Za-z0-9_-]*[A-Za-z_])"
    r"[A-Za-z0-9][A-Za-z0-9_-]{4,}[A-Za-z0-9]"
    r")"
)

_ACCOUNT_VALUE_BOUNDARY = r"(?=$|[^A-Za-z0-9_-])"

_CHINESE_ACCOUNT_PATTERN = re.compile(
    rf"(?P<prefix>(?:账户|账号)\s*(?:id|编号|号码|号)?\s*"
    rf"(?:为|是|is|=|:|：|#)?\s*)"
    rf"(?P<value>{_ACCOUNT_VALUE_PATTERN})"
    rf"{_ACCOUNT_VALUE_BOUNDARY}",
    re.IGNORECASE,
)

_ENGLISH_ACCOUNT_PATTERN = re.compile(
    rf"(?P<prefix>"
    rf"(?:"
    rf"\b(?:account[_-]id|account\s+id|account\s+number|account\s+no\.?|"
    rf"acct[_-]id|acct\s+id|acct\s+number|acct\s+no\.?|"
    rf"card\s+number|card\s+no\.?)"
    rf"(?![A-Za-z0-9_-])"
    rf"|"
    rf"\b(?:account|acct|card)(?![A-Za-z0-9_-])"
    rf")"
    rf"(?:\s*(?:is|为|是|=|:|：|#)\s*|\s+)"
    rf")"
    rf"(?P<value>{_ACCOUNT_VALUE_PATTERN})"
    rf"{_ACCOUNT_VALUE_BOUNDARY}",
    re.IGNORECASE,
)

_ACCOUNT_PATTERNS = (_CHINESE_ACCOUNT_PATTERN, _ENGLISH_ACCOUNT_PATTERN)


def enabled_rule_types(rule_set: ScrubRuleSet | None = None) -> set[str]:
    if rule_set is None:
        return set(_RULE_ORDER)
    if not rule_set.enabled:
        return set()

    return {rule.pattern_type for rule in rule_set.rules if rule.enabled}


def scrub_text(value: str, rule_set: ScrubRuleSet | None = None) -> str:
    enabled_rules = enabled_rule_types(rule_set)
    scrubbed = value

    if "name" in enabled_rules:
        scrubbed = _scrub_name(scrubbed)
    if "phone" in enabled_rules:
        scrubbed = _PHONE_PATTERN.sub(REDACTED_PHONE, scrubbed)
    if "account" in enabled_rules:
        for pattern in _ACCOUNT_PATTERNS:
            scrubbed = pattern.sub(
                rf"\g<prefix>{REDACTED_ACCOUNT}",
                scrubbed,
            )

    return scrubbed


def _scrub_name(value: str) -> str:
    scrubbed = value
    for pattern in _NAME_PATTERNS:
        scrubbed = pattern.sub(rf"\g<prefix>{REDACTED_NAME}", scrubbed)
    return scrubbed


__all__ = [
    "REDACTED_ACCOUNT",
    "REDACTED_NAME",
    "REDACTED_PHONE",
    "enabled_rule_types",
    "scrub_text",
]
