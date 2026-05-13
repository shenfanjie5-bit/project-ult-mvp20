from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from reasoner_runtime.config import (
    CallbackProfile,
    load_callback_profile,
    load_provider_profiles,
    load_scrub_rules,
)


def test_load_provider_profiles_from_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(
        """
providers:
  - provider: openai
    model: gpt-5.4
    timeout_ms: 20000
    fallback_priority: 0
  - provider: anthropic
    model: claude-sonnet-4.5
    fallback_priority: 1
""",
        encoding="utf-8",
    )

    profiles = load_provider_profiles(config_path)

    assert len(profiles) == 2
    assert profiles[0].timeout_ms == 20000
    assert profiles[1].timeout_ms == 30000


def test_load_provider_profiles_from_list(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(
        """
- provider: openai
  model: gpt-5.4
- provider: anthropic
  model: claude-sonnet-4.5
""",
        encoding="utf-8",
    )

    profiles = load_provider_profiles(config_path)

    assert [profile.provider for profile in profiles] == ["openai", "anthropic"]


def test_load_provider_profiles_missing_required_field_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.yaml"
    config_path.write_text(
        """
providers:
  - provider: openai
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_provider_profiles(config_path)


def test_load_scrub_rules_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "scrub.yaml"
    config_path.write_text(
        """
enabled: true
rules:
  - pattern_type: name
  - pattern_type: phone
    enabled: false
""",
        encoding="utf-8",
    )

    rule_set = load_scrub_rules(config_path)

    assert rule_set.enabled is True
    assert len(rule_set.rules) == 2
    assert rule_set.rules[1].enabled is False


def test_load_scrub_rules_from_wrapped_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "scrub.yaml"
    config_path.write_text(
        """
scrub:
  enabled: false
  rules:
    - pattern_type: account
""",
        encoding="utf-8",
    )

    rule_set = load_scrub_rules(config_path)

    assert rule_set.enabled is False
    assert rule_set.rules[0].pattern_type == "account"


def test_load_scrub_rules_invalid_pattern_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "scrub.yaml"
    config_path.write_text(
        """
enabled: true
rules:
  - pattern_type: email
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_scrub_rules(config_path)


def test_load_callback_profile_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "callback.yaml"
    config_path.write_text(
        """
backend: otel
endpoint: http://collector.example/v1/traces
enabled: true
""",
        encoding="utf-8",
    )

    profile = load_callback_profile(config_path)

    assert profile == CallbackProfile(
        backend="otel",
        endpoint="http://collector.example/v1/traces",
        enabled=True,
    )


def test_load_callback_profile_from_wrapped_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "callback.yaml"
    config_path.write_text(
        """
callback:
  backend: none
""",
        encoding="utf-8",
    )

    profile = load_callback_profile(config_path)

    assert profile.backend == "none"
    assert profile.enabled is False


def test_load_callback_profile_invalid_backend_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "callback.yaml"
    config_path.write_text(
        """
backend: stdout
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_callback_profile(config_path)


def test_example_provider_config_is_parseable() -> None:
    profiles = load_provider_profiles(Path("config/providers.example.yaml"))

    assert len(profiles) >= 2
    assert profiles[0].provider
    assert profiles[1].model


@pytest.mark.parametrize(
    ("selector", "provider", "model"),
    [
        ("minimax", "minimax", "MiniMax-M2.5"),
        ("codex", "openai-codex", "gpt-5.5"),
        ("claude_code", "claude-code", "claude-sonnet-4-6"),
    ],
)
def test_three_backend_example_loads_selected_backend_only(
    selector: str,
    provider: str,
    model: str,
) -> None:
    profiles = load_provider_profiles(
        Path("config/providers.three-backends.example.yaml"),
        selector=selector,
    )

    assert len(profiles) == 1
    assert profiles[0].provider == provider
    assert profiles[0].model == model
    assert profiles[0].fallback_priority == 0


def test_example_scrub_config_is_parseable() -> None:
    rule_set = load_scrub_rules(Path("config/scrub.example.yaml"))

    assert rule_set.enabled is True
    assert {rule.pattern_type for rule in rule_set.rules} == {"name", "phone", "account"}


@pytest.mark.parametrize("package_name", ["litellm", "instructor"])
def test_requirements_lock_core_dependencies_with_sha256(package_name: str) -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    normalized = requirements.replace("\\\n", " ")
    match = re.search(
        rf"{package_name}==(?P<version>[^\s]+)\s+--hash=sha256:(?P<hash>[a-f0-9]{{64}})",
        normalized,
    )

    assert match is not None
    assert match.group("version")
    assert len(match.group("hash")) == 64
