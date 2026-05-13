"""Stage 4 audit #2 + #15: PII scrub input_callback + trace metadata propagation."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_RUNTIME_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_RUNTIME_ROOT))

from reasoner_runtime.callbacks.base import CallbackContext  # noqa: E402
from reasoner_runtime.callbacks import litellm as litellm_callbacks  # noqa: E402
from reasoner_runtime.core.engine import _callback_context  # noqa: E402
from reasoner_runtime.core.models import ReasonerRequest  # noqa: E402
from reasoner_runtime.structured.parser import _build_callback_metadata  # noqa: E402


def _make_request(**metadata: Any) -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req_test",
        caller_module="main_core.l6_alpha",
        target_schema="alpha_result",
        messages=[{"role": "user", "content": "hi"}],
        configured_provider="anthropic",
        configured_model="claude-sonnet-4-6",
        max_retries=2,
        metadata=dict(metadata),
    )


# ---------------------------------------------------------------------------
# #15 trace metadata: cycle_id / ticker / analyzer_type / regime_label
# ---------------------------------------------------------------------------


def test_callback_context_carries_four_trace_fields_default_empty() -> None:
    ctx = CallbackContext()
    assert ctx.cycle_id == ""
    assert ctx.ticker == ""
    assert ctx.analyzer_type == ""
    assert ctx.regime_label == ""


def test_engine_callback_context_propagates_trace_metadata() -> None:
    request = _make_request(
        cycle_id="CYCLE_20260501",
        ticker="ENT_STOCK_300750.SZ",
        analyzer_type="single_prompt_v1",
        regime_label="neutral",
    )

    ctx = _callback_context(request, provider="anthropic", model="claude-sonnet-4-6")

    assert ctx.cycle_id == "CYCLE_20260501"
    assert ctx.ticker == "ENT_STOCK_300750.SZ"
    assert ctx.analyzer_type == "single_prompt_v1"
    assert ctx.regime_label == "neutral"


def test_engine_callback_context_handles_missing_metadata() -> None:
    request = _make_request()  # empty metadata
    ctx = _callback_context(request, provider="anthropic", model="claude-sonnet-4-6")

    assert ctx.cycle_id == ""
    assert ctx.ticker == ""
    assert ctx.analyzer_type == ""
    assert ctx.regime_label == ""


def test_build_callback_metadata_includes_trace_fields() -> None:
    request = _make_request(
        cycle_id="CYCLE_20260501",
        ticker="ENT_STOCK_300750.SZ",
        analyzer_type="multi_agent_v1",
        regime_label="risk_off",
    )

    metadata = _build_callback_metadata(request)

    assert metadata["cycle_id"] == "CYCLE_20260501"
    assert metadata["ticker"] == "ENT_STOCK_300750.SZ"
    assert metadata["analyzer_type"] == "multi_agent_v1"
    assert metadata["regime_label"] == "risk_off"
    # Existing canonical fields preserved
    assert metadata["request_id"] == "req_test"
    assert metadata["caller_module"] == "main_core.l6_alpha"


def test_build_callback_metadata_omits_unset_trace_fields() -> None:
    request = _make_request(cycle_id="CYCLE_20260501")  # only one field set

    metadata = _build_callback_metadata(request)

    assert metadata["cycle_id"] == "CYCLE_20260501"
    assert "ticker" not in metadata
    assert "analyzer_type" not in metadata
    assert "regime_label" not in metadata


def test_litellm_build_context_extracts_trace_fields_from_kwargs() -> None:
    """LiteLLM-mediated callbacks read kwargs.metadata.reasoner; the four
    trace fields must surface on the resulting CallbackContext.
    """

    kwargs: dict[str, Any] = {
        "model": "anthropic/claude-sonnet-4-6",
        "metadata": {
            "reasoner": {
                "request_id": "req_99",
                "caller_module": "main_core.l7_recommendation",
                "target_schema": "recommendation_snapshot",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "cycle_id": "CYCLE_20260501",
                "ticker": "ENT_STOCK_300750.SZ",
                "analyzer_type": "single_prompt_v1",
                "regime_label": "neutral",
            },
        },
    }

    ctx = litellm_callbacks._build_context(kwargs)

    assert ctx.cycle_id == "CYCLE_20260501"
    assert ctx.ticker == "ENT_STOCK_300750.SZ"
    assert ctx.analyzer_type == "single_prompt_v1"
    assert ctx.regime_label == "neutral"


def test_litellm_build_context_handles_missing_trace_fields() -> None:
    kwargs: dict[str, Any] = {
        "model": "anthropic/claude-sonnet-4-6",
        "metadata": {"reasoner": {"request_id": "req_99"}},
    }

    ctx = litellm_callbacks._build_context(kwargs)

    assert ctx.cycle_id == ""
    assert ctx.ticker == ""


# ---------------------------------------------------------------------------
# #2 PII scrub registered as litellm.input_callback
# ---------------------------------------------------------------------------


def test_input_handler_scrubs_and_logs_warning_on_unscrubbed_pii(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Defense-in-depth: if a caller bypasses the engine wrapper and goes
    straight to litellm.completion, the input_handler must scrub the
    provider-bound payload and surface a WARNING with request_id.
    """

    bridge = litellm_callbacks.LiteLLMCallbackBridge(backends=())

    kwargs: dict[str, Any] = {
        "metadata": {"reasoner": {"request_id": "req_bypass"}},
        "messages": [
            {
                "role": "user",
                # An obvious PII pattern; scrub_text replaces it.
                "content": "phone 13800138000 placed an order",
            }
        ],
    }

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.callbacks.litellm"):
        bridge.input_handler(kwargs)

    assert any(
        "input_callback scrubbed direct-call PII" in record.getMessage()
        for record in caplog.records
    ), [record.getMessage() for record in caplog.records]
    assert "13800138000" not in kwargs["messages"][0]["content"]
    assert kwargs["messages"][0]["content"] != "phone 13800138000 placed an order"
    # The request_id from metadata must surface in the log so observability
    # can trace which call bypassed the engine wrapper.
    assert any(
        "req_bypass" in record.getMessage() for record in caplog.records
    )


def test_input_handler_scrubs_structured_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = litellm_callbacks.LiteLLMCallbackBridge(backends=())
    kwargs: dict[str, Any] = {
        "metadata": {"reasoner": {"request_id": "req_structured"}},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "name Alice phone 13800138000",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/chart.png"},
                    },
                ],
            },
        ],
    }

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.callbacks.litellm"):
        bridge.input_handler(kwargs)

    content = kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "[REDACTED_NAME]" in content[0]["text"]
    assert "[REDACTED_PHONE]" in content[0]["text"]
    assert "Alice" not in content[0]["text"]
    assert "13800138000" not in content[0]["text"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.test/chart.png"},
    }
    assert any(
        "input_callback scrubbed direct-call PII" in record.getMessage()
        for record in caplog.records
    )


def test_input_handler_does_not_warn_on_scrubbed_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = litellm_callbacks.LiteLLMCallbackBridge(backends=())

    kwargs: dict[str, Any] = {
        "metadata": {"reasoner": {"request_id": "req_clean"}},
        "messages": [
            {"role": "user", "content": "summarize earnings expectations for Q3"},
        ],
    }

    with caplog.at_level(logging.WARNING, logger="reasoner_runtime.callbacks.litellm"):
        bridge.input_handler(kwargs)

    assert not any(
        "input_callback scrubbed direct-call PII" in record.getMessage()
        for record in caplog.records
    )


def test_input_handler_does_not_raise_on_malformed_kwargs() -> None:
    bridge = litellm_callbacks.LiteLLMCallbackBridge(backends=())

    # No exception even on weird shapes (defensive contract for callbacks).
    bridge.input_handler({})
    bridge.input_handler({"messages": "not-a-list"})
    bridge.input_handler({"messages": [None, {"role": "user"}]})


def test_configure_litellm_callbacks_registers_input_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """input_callback must register even when no observability backends
    are configured — the PII scrub trip-wire is security-critical and
    should not depend on Langfuse/OTEL being wired up.
    """

    fake_litellm = SimpleNamespace(
        input_callback=[],
        success_callback=[],
        failure_callback=[],
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    # Reset bridge registry so the test is hermetic.
    litellm_callbacks._installed_bridges.clear()

    bridge = litellm_callbacks.configure_litellm_callbacks(backends=())

    # No observability backends → bridge return is None per contract,
    # but input_callback was still registered.
    assert bridge is None
    assert len(fake_litellm.input_callback) == 1
    assert fake_litellm.success_callback == []
    assert fake_litellm.failure_callback == []


def test_configure_litellm_callbacks_with_backends_registers_all_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_litellm = SimpleNamespace(
        input_callback=[],
        success_callback=[],
        failure_callback=[],
    )
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    litellm_callbacks._installed_bridges.clear()

    class _NullBackend:
        def on_start(self, ctx: CallbackContext) -> None: ...
        def on_success(self, ctx: CallbackContext, success: Any) -> None: ...
        def on_error(self, ctx: CallbackContext, error: Any) -> None: ...

    bridge = litellm_callbacks.configure_litellm_callbacks(backends=(_NullBackend(),))

    assert bridge is not None
    assert len(fake_litellm.input_callback) == 1
    assert len(fake_litellm.success_callback) == 1
    assert len(fake_litellm.failure_callback) == 1
