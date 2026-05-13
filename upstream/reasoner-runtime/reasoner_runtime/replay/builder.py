from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from reasoner_runtime.replay.models import ReplayBundle

if TYPE_CHECKING:
    from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_llm_lineage(result: StructuredGenerationResult) -> dict[str, Any]:
    return {
        "provider": result.actual_provider,
        "model": result.actual_model,
        "configured_target": result.configured_target,
        "failure_class": result.failure_class,
        "fallback_path": list(result.fallback_path or []),
        "retry_count": result.retry_count,
    }


def build_replay_bundle(
    sanitized_input: str,
    raw_output: str,
    parsed_result: dict[str, Any],
    lineage: dict[str, Any],
    *,
    request: ReasonerRequest,
    result: StructuredGenerationResult,
) -> ReplayBundle:
    return ReplayBundle(
        sanitized_input=sanitized_input,
        input_hash=sha256_text(sanitized_input),
        raw_output=raw_output,
        parsed_result=parsed_result,
        output_hash=sha256_text(raw_output),
        llm_lineage=lineage,
        request=request.to_contract(),
        result=result.to_contract(),
    )
