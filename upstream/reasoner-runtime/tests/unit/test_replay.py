from __future__ import annotations

from time import perf_counter

from reasoner_runtime.core import ReasonerRequest, StructuredGenerationResult
from reasoner_runtime.replay import (
    ReplayBundle,
    build_llm_lineage,
    build_replay_bundle,
    sha256_text,
)


def _result(
    *,
    fallback_path: list[str] | None = None,
    retry_count: int = 0,
    parsed_result: dict[str, object] | None = None,
) -> StructuredGenerationResult:
    return StructuredGenerationResult(
        result_id="req-replay:result",
        request_id="req-replay",
        parsed_result=parsed_result or {"answer": "ok"},
        actual_provider="openai",
        actual_model="gpt-4",
        fallback_path=fallback_path or [],
        retry_count=retry_count,
        token_usage={"prompt": 1, "completion": 2, "total": 3},
        cost_estimate=0.01,
        latency_ms=5,
    )


def _request() -> ReasonerRequest:
    return ReasonerRequest(
        request_id="req-replay",
        caller_module="unit-test",
        target_schema="ReplayPayload",
        messages=[{"role": "user", "content": "sanitized input"}],
        configured_provider="openai",
        configured_model="gpt-4",
        max_retries=2,
        metadata={"cycle_id": "cycle-replay"},
    )


def test_sha256_text_hashes_utf8_text() -> None:
    assert (
        sha256_text("hello")
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_sha256_text_hashes_empty_string() -> None:
    assert (
        sha256_text("")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_build_llm_lineage_reads_fields_from_result() -> None:
    lineage = build_llm_lineage(
        _result(
            fallback_path=["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
            retry_count=2,
        )
    )

    assert lineage == {
        "provider": "openai",
        "model": "gpt-4",
        "configured_target": None,
        "failure_class": "none",
        "fallback_path": ["openai/gpt-4", "anthropic/claude-sonnet-4.5"],
        "retry_count": 2,
    }


def test_build_llm_lineage_keeps_primary_path_as_list() -> None:
    lineage = build_llm_lineage(_result())

    assert lineage["fallback_path"] == []


def test_build_replay_bundle_populates_core_five_fields_and_lineage() -> None:
    parsed_result = {"answer": "ok", "score": 1}
    result = _result(fallback_path=["openai/gpt-4"], parsed_result=parsed_result)
    lineage = build_llm_lineage(result)

    bundle = build_replay_bundle(
        "sanitized input",
        '{"answer":"ok","score":1}',
        parsed_result,
        lineage,
        request=_request(),
        result=result,
    )

    assert isinstance(bundle, ReplayBundle)
    assert bundle.sanitized_input == "sanitized input"
    assert bundle.input_hash == sha256_text("sanitized input")
    assert bundle.raw_output == '{"answer":"ok","score":1}'
    assert bundle.parsed_result == parsed_result
    assert bundle.output_hash == sha256_text('{"answer":"ok","score":1}')
    assert bundle.llm_lineage == lineage


def test_build_replay_bundle_preserves_raw_output_without_normalizing() -> None:
    raw_output = ' \n{"b":2,"a":1}\n '
    result = _result(parsed_result={"a": 1, "b": 2})

    bundle = build_replay_bundle(
        "in",
        raw_output,
        {"a": 1, "b": 2},
        build_llm_lineage(result),
        request=_request(),
        result=result,
    )

    assert bundle.raw_output == raw_output
    assert bundle.output_hash == sha256_text(raw_output)


def test_build_replay_bundle_runtime_baseline_under_100ms() -> None:
    result = _result(parsed_result={})
    build_replay_bundle(
        "warmup",
        "{}",
        {},
        build_llm_lineage(result),
        request=_request(),
        result=result,
    )

    started_at = perf_counter()
    result = _result(parsed_result={"answer": "ok"})
    build_replay_bundle(
        "input",
        '{"answer":"ok"}',
        {"answer": "ok"},
        build_llm_lineage(result),
        request=_request(),
        result=result,
    )
    elapsed_ms = (perf_counter() - started_at) * 1000

    assert elapsed_ms < 100
