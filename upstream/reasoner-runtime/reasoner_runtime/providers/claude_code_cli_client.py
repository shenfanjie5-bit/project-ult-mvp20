from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from reasoner_runtime.config.models import ClaudeCodeCliAuthSpec, ProviderProfile
from reasoner_runtime.providers.routing import ParseValidationError
from reasoner_runtime.structured.parser import StructuredCallResult

_CLAUDE_CODE_PROVIDER = "claude-code"
_DEFAULT_CLAUDE_BINARY = "claude"
_EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
_DEFAULT_SYSTEM_PROMPT = "Return only output matching the supplied JSON schema."


def _safe_print_flags() -> list[str]:
    # These flags are supported by the local `claude --help` surface and keep
    # `--print` in a schema-only subprocess lane: no tools, no MCP, no
    # project/local settings, no slash-command skills, and no bypass mode.
    return [
        "--tools",
        "",
        "--mcp-config",
        _EMPTY_MCP_CONFIG,
        "--strict-mcp-config",
        "--setting-sources",
        "user",
        "--disable-slash-commands",
        "--no-chrome",
        "--permission-mode",
        "default",
    ]


class ClaudeCodeError(RuntimeError):
    """Raised when the claude CLI fails or is unavailable."""


@dataclass
class ClaudeCodeCliClient:
    profile: ProviderProfile
    max_retries: int
    binary_path: str = _DEFAULT_CLAUDE_BINARY

    def create_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel],
        metadata: Mapping[str, Any] | None = None,
        callback_metadata: Mapping[str, Any] | None = None,
    ) -> StructuredCallResult:
        if response_model is None:
            raise ValueError("response_model is required")

        instructions, user_prompt = _split_and_flatten(messages)
        schema = response_model.model_json_schema()

        cmd: list[str] = [
            self.binary_path,
            "--print",
            "--output-format",
            "json",
            "--input-format",
            "text",
            "--no-session-persistence",
            *_safe_print_flags(),
            "--model",
            _strip_provider_prefix(self.profile.model),
            "--json-schema",
            json.dumps(schema),
            "--system-prompt",
            instructions or _DEFAULT_SYSTEM_PROMPT,
        ]
        cmd.append(user_prompt)

        timeout_s = self.profile.timeout_ms / 1000

        started_at = perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except FileNotFoundError as error:
            raise ClaudeCodeError(
                f"claude CLI not found at {self.binary_path!r} — "
                "install via `npm install -g @anthropic-ai/claude-code` "
                "or set `auth.binary_path` in the provider profile"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ClaudeCodeError(
                f"claude CLI timed out after {self.profile.timeout_ms}ms"
            ) from error
        elapsed_ms = max(int((perf_counter() - started_at) * 1000), 0)

        if proc.returncode != 0:
            raise ClaudeCodeError(
                f"claude CLI exited {proc.returncode}: {proc.stderr[:512].strip()}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as error:
            raise ClaudeCodeError(
                f"claude CLI returned non-JSON stdout: {proc.stdout[:256].strip()!r}"
            ) from error

        if not isinstance(payload, dict):
            raise ClaudeCodeError(
                f"claude CLI returned non-object payload: {payload!r}"
            )

        if payload.get("is_error") is True:
            err_text = payload.get("result") or payload.get("error") or "unknown"
            raise ClaudeCodeError(f"claude CLI reported is_error: {str(err_text)[:512]}")

        structured = payload.get("structured_output")
        if structured is None:
            raise ParseValidationError(
                "claude CLI did not return structured_output (json-schema enforcement failed)"
            )

        try:
            parsed_model = response_model.model_validate(structured)
        except ValidationError as error:
            raise ParseValidationError(str(error)) from error

        token_usage = _extract_usage(payload.get("usage"))
        cost = payload.get("total_cost_usd")
        cost_estimate = float(cost) if isinstance(cost, (int, float)) else 0.0

        api_ms = payload.get("duration_api_ms") or payload.get("duration_ms")
        latency_ms = int(api_ms) if isinstance(api_ms, (int, float)) else elapsed_ms

        raw_output = payload.get("result")
        if not isinstance(raw_output, str) or not raw_output:
            raw_output = json.dumps(structured, ensure_ascii=False)

        return StructuredCallResult(
            parsed_result=parsed_model.model_dump(mode="json"),
            raw_output=raw_output,
            token_usage=token_usage,
            cost_estimate=cost_estimate,
            latency_ms=latency_ms,
        )


def build_claude_code_cli_client(
    profile: ProviderProfile,
    max_retries: int,
    *,
    binary_path: str | None = None,
) -> ClaudeCodeCliClient:
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")
    if profile.provider != _CLAUDE_CODE_PROVIDER:
        raise ValueError(
            f"build_claude_code_cli_client requires provider='{_CLAUDE_CODE_PROVIDER}', "
            f"got '{profile.provider}'"
        )

    resolved_binary = binary_path or _resolve_binary_from_profile(profile)
    return ClaudeCodeCliClient(
        profile=profile,
        max_retries=max_retries,
        binary_path=resolved_binary,
    )


def _resolve_binary_from_profile(profile: ProviderProfile) -> str:
    auth_spec = profile.auth
    if auth_spec is None:
        return _DEFAULT_CLAUDE_BINARY
    if not isinstance(auth_spec, ClaudeCodeCliAuthSpec):
        raise ValueError(
            f"unsupported claude-code auth kind: {getattr(auth_spec, 'kind', auth_spec)!r}"
        )
    return auth_spec.binary_path or _DEFAULT_CLAUDE_BINARY


def _split_and_flatten(messages: list[dict[str, Any]]) -> tuple[str | None, str]:
    instructions_parts: list[str] = []
    user_parts: list[str] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        text = _coerce_content_text(content)
        if not text:
            continue
        if role == "system":
            instructions_parts.append(text)
        else:
            prefix = ""
            if role and role != "user":
                prefix = f"[{role}] "
            user_parts.append(f"{prefix}{text}")

    instructions = "\n\n".join(instructions_parts) if instructions_parts else None
    user_prompt = "\n\n".join(user_parts) if user_parts else ""
    return instructions, user_prompt


def _coerce_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for entry in content:
            if isinstance(entry, dict):
                value = entry.get("text") or entry.get("content")
                if isinstance(value, str) and value:
                    chunks.append(value)
            elif isinstance(entry, str):
                chunks.append(entry)
        return "\n".join(chunks)
    return ""


def _strip_provider_prefix(model: str) -> str:
    if model.startswith(f"{_CLAUDE_CODE_PROVIDER}/"):
        return model.split("/", 1)[1]
    return model


def _extract_usage(usage_obj: Any) -> dict[str, int]:
    if not isinstance(usage_obj, dict):
        return {"prompt": 0, "completion": 0, "total": 0}

    def _read_int(*keys: str) -> int:
        for key in keys:
            value = usage_obj.get(key)
            if isinstance(value, (int, float)):
                return max(int(value), 0)
        return 0

    prompt = _read_int("input_tokens", "prompt_tokens", "prompt")
    completion = _read_int("output_tokens", "completion_tokens", "completion")
    total = _read_int("total_tokens", "total")
    if total == 0:
        total = prompt + completion
    return {"prompt": prompt, "completion": completion, "total": total}
