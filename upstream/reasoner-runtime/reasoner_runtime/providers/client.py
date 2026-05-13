from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reasoner_runtime.config.models import ProviderProfile
from reasoner_runtime.providers.routing import ProviderConfigError

_CODEX_GATE_ENV = "REASONER_RUNTIME_ENABLE_CODEX_OAUTH"
_CLAUDE_CODE_GATE_ENV = "REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI"


@dataclass(frozen=True)
class LiteLLMInstructorClient:
    profile: ProviderProfile
    max_retries: int
    litellm_model: str
    instructor_client: Any

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[Any],
        callback_metadata: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Any:
        provider_metadata = dict(metadata or {})
        reasoner_metadata = dict(callback_metadata or {})
        reasoner_metadata.update(
            {
                "provider": self.profile.provider,
                "model": self.profile.model,
            }
        )
        provider_metadata["reasoner"] = reasoner_metadata
        kwargs = build_litellm_completion_kwargs(
            self.profile,
            messages=messages,
            timeout_s=self.profile.timeout_ms / 1000,
            metadata=provider_metadata,
        )
        kwargs.update(
            {
                "response_model": response_model,
                "max_retries": self.max_retries,
            }
        )

        completions = self.instructor_client.chat.completions
        if hasattr(completions, "create_with_completion"):
            return completions.create_with_completion(**kwargs)

        return completions.create(**kwargs)


def build_client(profile: ProviderProfile, max_retries: int) -> Any:
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    if profile.provider == "openai-codex":
        if os.environ.get(_CODEX_GATE_ENV) != "1":
            raise ProviderConfigError(
                f"openai-codex provider is gated; set {_CODEX_GATE_ENV}=1 to enable"
            )
        from reasoner_runtime.providers.codex_client import build_codex_client

        return build_codex_client(profile, max_retries)

    if profile.provider == "claude-code":
        if os.environ.get(_CLAUDE_CODE_GATE_ENV) != "1":
            raise ProviderConfigError(
                f"claude-code provider is gated; set {_CLAUDE_CODE_GATE_ENV}=1 to enable"
            )
        from reasoner_runtime.providers.claude_code_cli_client import (
            build_claude_code_cli_client,
        )

        return build_claude_code_cli_client(profile, max_retries)

    litellm_model = litellm_model_name(profile)

    return LiteLLMInstructorClient(
        profile=profile,
        max_retries=max_retries,
        litellm_model=litellm_model,
        instructor_client=_create_instructor_client(),
    )


def _create_instructor_client() -> Any:
    try:
        import instructor
        from litellm import completion
    except ImportError as error:
        raise ProviderConfigError(
            "litellm and instructor must be installed to build a provider client"
        ) from error

    return instructor.from_litellm(completion)


def build_litellm_completion_kwargs(
    profile: ProviderProfile,
    *,
    messages: list[dict[str, Any]],
    timeout_s: float,
    max_tokens: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": litellm_model_name(profile),
        "messages": messages,
        "timeout": min(timeout_s, profile.timeout_ms / 1000),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if metadata is not None:
        kwargs["metadata"] = dict(metadata)

    return kwargs


def litellm_model_name(profile: ProviderProfile) -> str:
    if "/" in profile.model:
        provider_prefix, _, _ = profile.model.partition("/")
        if provider_prefix != profile.provider:
            raise ProviderConfigError(
                "profile.model provider prefix must match profile.provider: "
                f"{profile.model!r} conflicts with {profile.provider!r}"
            )
        return profile.model

    return f"{profile.provider}/{profile.model}"


def _litellm_model_name(profile: ProviderProfile) -> str:
    return litellm_model_name(profile)
