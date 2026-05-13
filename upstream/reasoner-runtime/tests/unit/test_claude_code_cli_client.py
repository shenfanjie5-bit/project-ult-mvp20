from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from reasoner_runtime.config.models import ClaudeCodeCliAuthSpec, ProviderProfile
from reasoner_runtime.providers import (
    ClaudeCodeError,
    ParseValidationError,
    ProviderConfigError,
    build_claude_code_cli_client,
    build_client,
)


class _Echo(BaseModel):
    answer: str


@pytest.fixture(autouse=True)
def _enable_claude_code_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI", "1")


def _profile(model: str = "claude-sonnet-4-6") -> ProviderProfile:
    return ProviderProfile(
        provider="claude-code",
        model=model,
        timeout_ms=60000,
        fallback_priority=0,
        auth=ClaudeCodeCliAuthSpec(),
    )


def _success_payload(*, structured: dict[str, Any], cost: float = 0.12) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": json.dumps(structured),
            "structured_output": structured,
            "duration_ms": 4500,
            "duration_api_ms": 4400,
            "total_cost_usd": cost,
            "session_id": "test-session",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 5,
                "total_tokens": 17,
            },
        }
    )


def _make_run_stub(captured: dict[str, Any], stdout: str, stderr: str = "", returncode: int = 0):
    def fake_run(cmd, *, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        captured["check"] = check
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return fake_run


def test_claude_code_client_invokes_cli_and_returns_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"answer": "pong"})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))

    client = build_claude_code_cli_client(_profile(), 0)
    result = client.create_structured(
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say pong"},
        ],
        response_model=_Echo,
    )

    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--input-format" in cmd and "text" in cmd
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == "user"
    assert "--disable-slash-commands" in cmd
    assert "--no-chrome" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "default"
    assert "--dangerously-skip-permissions" not in cmd
    assert "--allow-dangerously-skip-permissions" not in cmd
    assert "--model" in cmd
    model_index = cmd.index("--model")
    assert cmd[model_index + 1] == "claude-sonnet-4-6"
    assert "--json-schema" in cmd
    schema_index = cmd.index("--json-schema")
    parsed_schema = json.loads(cmd[schema_index + 1])
    assert parsed_schema["properties"]["answer"]["type"] == "string"
    assert "--system-prompt" in cmd
    sys_index = cmd.index("--system-prompt")
    assert cmd[sys_index + 1] == "Be concise."
    assert cmd[-1] == "Say pong"
    assert captured["timeout"] == 60.0

    assert result.parsed_result == {"answer": "pong"}
    assert result.token_usage == {"prompt": 12, "completion": 5, "total": 17}
    assert result.cost_estimate == pytest.approx(0.12)
    assert result.latency_ms == 4400


def test_claude_code_client_strips_provider_prefix_in_model_arg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"answer": "ok"})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))

    profile = ProviderProfile(
        provider="claude-code",
        model="claude-code/claude-opus-4-7",
        timeout_ms=30000,
        auth=ClaudeCodeCliAuthSpec(),
    )
    client = build_claude_code_cli_client(profile, 0)
    client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-7"


def test_claude_code_client_uses_custom_binary_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"answer": "ok"})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))

    profile = ProviderProfile(
        provider="claude-code",
        model="claude-sonnet-4-6",
        timeout_ms=30000,
        auth=ClaudeCodeCliAuthSpec(binary_path="/opt/custom/claude"),
    )
    client = build_claude_code_cli_client(profile, 0)
    client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    assert captured["cmd"][0] == "/opt/custom/claude"


def test_claude_code_client_uses_default_system_prompt_when_no_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"answer": "ok"})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))

    client = build_claude_code_cli_client(_profile(), 0)
    client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    cmd = captured["cmd"]
    assert "--system-prompt" in cmd
    sys_index = cmd.index("--system-prompt")
    assert cmd[sys_index + 1] == "Return only output matching the supplied JSON schema."


def test_claude_code_client_raises_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ClaudeCodeError, match="claude CLI not found"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else ["claude"], timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ClaudeCodeError, match="timed out"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        subprocess,
        "run",
        _make_run_stub(captured, stdout="", stderr="auth required", returncode=2),
    )
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ClaudeCodeError, match="exited 2"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_raises_on_is_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    payload = json.dumps(
        {
            "type": "result",
            "is_error": True,
            "result": "API authentication failed",
        }
    )
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout=payload))
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ClaudeCodeError, match="is_error"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_parse_validation_when_structured_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    payload = json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": "no schema enforced",
        }
    )
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout=payload))
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ParseValidationError, match="structured_output"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_parse_validation_when_schema_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"unexpected": 1})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ParseValidationError):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_claude_code_client_raises_on_garbled_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        subprocess, "run", _make_run_stub(captured, stdout="not json")
    )
    client = build_claude_code_cli_client(_profile(), 0)

    with pytest.raises(ClaudeCodeError, match="non-JSON"):
        client.create_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Echo
        )


def test_build_claude_code_cli_client_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        build_claude_code_cli_client(_profile(), -1)


def test_build_claude_code_cli_client_rejects_non_claude_provider() -> None:
    profile = ProviderProfile(provider="openai", model="gpt-4", timeout_ms=10000)
    with pytest.raises(ValueError, match="claude-code"):
        build_claude_code_cli_client(profile, 0)


def test_build_client_dispatches_to_claude_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    stdout = _success_payload(structured={"answer": "via-build-client"})
    monkeypatch.setattr(subprocess, "run", _make_run_stub(captured, stdout))

    client = build_client(_profile(), 0)
    result = client.create_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=_Echo
    )

    assert result.parsed_result == {"answer": "via-build-client"}
    assert captured["cmd"][0] == "claude"


def test_build_client_rejects_claude_code_when_env_flag_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI", raising=False)

    with pytest.raises(ProviderConfigError, match="REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI"):
        build_client(_profile(), 0)


def test_build_client_rejects_claude_code_when_env_flag_is_not_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI", "true")

    with pytest.raises(ProviderConfigError, match="REASONER_RUNTIME_ENABLE_CLAUDE_CODE_CLI"):
        build_client(_profile(), 0)
