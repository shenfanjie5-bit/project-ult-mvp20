from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from reasoner_runtime.config.models import (
    CallbackProfile,
    ProviderProfile,
    ScrubRuleSet,
)


def _load_yaml(config_path: Path) -> Any:
    with config_path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_provider_profiles(
    config_path: Path,
    *,
    selector: str | None = None,
) -> list[ProviderProfile]:
    data = _load_yaml(config_path)
    if selector is not None:
        data = _select_provider_profiles(data, selector)
        return TypeAdapter(list[ProviderProfile]).validate_python(data)

    if isinstance(data, dict) and "providers" in data:
        data = data["providers"]
    return TypeAdapter(list[ProviderProfile]).validate_python(data)


def _select_provider_profiles(data: Any, selector: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError("provider selector requires a mapping config")

    normalized_selector = selector.strip().replace("-", "_")
    selector_keys = [selector.strip()]
    if not normalized_selector.startswith("providers_"):
        selector_keys.append(f"providers_{normalized_selector}")
    selector_keys.append(normalized_selector)

    for selector_key in selector_keys:
        if selector_key in data:
            return data[selector_key]

    available = ", ".join(sorted(key for key in data if key.startswith("providers")))
    raise ValueError(
        f"provider selector {selector!r} was not found"
        + (f"; available selectors: {available}" if available else "")
    )


def load_scrub_rules(config_path: Path) -> ScrubRuleSet:
    data = _load_yaml(config_path)
    if isinstance(data, dict) and "scrub" in data:
        data = data["scrub"]
    return ScrubRuleSet.model_validate(data)


def load_callback_profile(config_path: Path) -> CallbackProfile:
    data = _load_yaml(config_path)
    if isinstance(data, dict) and "callback" in data:
        data = data["callback"]
    return CallbackProfile.model_validate(data)
