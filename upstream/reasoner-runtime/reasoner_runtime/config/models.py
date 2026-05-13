from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CodexCliAuthSpec(BaseModel):
    kind: Literal["codex_cli"] = "codex_cli"
    path: str | None = None


class ClaudeCodeCliAuthSpec(BaseModel):
    kind: Literal["claude_code_cli"] = "claude_code_cli"
    binary_path: str | None = None


AuthSpec = Annotated[
    Union[CodexCliAuthSpec, ClaudeCodeCliAuthSpec],
    Field(discriminator="kind"),
]


class ProviderProfile(BaseModel):
    provider: str
    model: str
    timeout_ms: int = Field(default=30000, gt=0)
    fallback_priority: int = Field(default=0, ge=0)
    rate_limit_rpm: int | None = Field(default=None, gt=0)
    auth: AuthSpec | None = None


class ScrubRule(BaseModel):
    pattern_type: Literal["name", "phone", "account"]
    enabled: bool = True


class ScrubRuleSet(BaseModel):
    enabled: bool = True
    rules: list[ScrubRule] = Field(default_factory=list)


class CallbackProfile(BaseModel):
    backend: Literal["otel", "langfuse", "none"] = "none"
    endpoint: str | None = None
    enabled: bool = False


class DependencyLockEntry(BaseModel):
    package: str
    version: str
    sha256: str
