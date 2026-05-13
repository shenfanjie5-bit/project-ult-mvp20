"""A/B evaluation utilities for L6 analyzer parity checks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.protocols import AnalyzerInterface
from main_core.common.types import EntityId


@dataclass(frozen=True)
class AbEvaluationCase:
    """One L6 A/B input case with a prebuilt analyzer context."""

    case_id: str
    entity_id: EntityId
    context: AlphaAnalysisContext

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must be non-empty")


@dataclass(frozen=True)
class AbCaseResult:
    """Per-case L6 A/B comparison result."""

    case_id: str
    entity_id: EntityId
    baseline_analyzer_type: str
    challenger_analyzer_type: str
    baseline_status: str
    challenger_status: str
    baseline_score: float | None
    challenger_score: float | None
    baseline_confidence: float
    challenger_confidence: float
    score_delta: float | None
    confidence_delta: float
    status_matches: bool
    baseline_error: str | None = None
    challenger_error: str | None = None


@dataclass(frozen=True)
class AbEvaluationReport:
    """Aggregate L6 A/B report with JSON-compatible fields."""

    baseline_analyzer_type: str
    challenger_analyzer_type: str
    total_cases: int
    status_match_rate: float
    ok_pair_score_mae: float | None
    confidence_mae: float | None
    baseline_inconclusive_count: int
    challenger_inconclusive_count: int
    inconclusive_count_delta: int
    baseline_failure_count: int
    challenger_failure_count: int
    cases: tuple[AbCaseResult, ...]


def run_ab_evaluation(
    cases: Sequence[AbEvaluationCase],
    *,
    baseline: AnalyzerInterface,
    challenger: AnalyzerInterface,
) -> AbEvaluationReport:
    """Run baseline and challenger analyzers on the same supplied contexts.

    Per-analyzer exceptions are captured per case rather than aborting the
    whole run. Empty case sequences are rejected so callers cannot interpret a
    no-op as a successful comparison.
    """

    if not cases:
        raise ValueError("run_ab_evaluation requires at least one case")

    case_results: list[AbCaseResult] = []
    score_abs_deltas: list[float] = []
    confidence_abs_deltas: list[float] = []
    status_match_count = 0
    baseline_inconclusive_count = 0
    challenger_inconclusive_count = 0
    baseline_failure_count = 0
    challenger_failure_count = 0

    for case in cases:
        baseline_result, baseline_error = _safe_analyze(baseline, case)
        challenger_result, challenger_error = _safe_analyze(challenger, case)

        baseline_status = (
            baseline_result.status if baseline_result is not None else "error"
        )
        challenger_status = (
            challenger_result.status if challenger_result is not None else "error"
        )
        status_matches = baseline_status == challenger_status
        if status_matches:
            status_match_count += 1
        if baseline_status == "inconclusive":
            baseline_inconclusive_count += 1
        if challenger_status == "inconclusive":
            challenger_inconclusive_count += 1
        if baseline_error is not None:
            baseline_failure_count += 1
        if challenger_error is not None:
            challenger_failure_count += 1

        baseline_score = baseline_result.score if baseline_result is not None else None
        challenger_score = (
            challenger_result.score if challenger_result is not None else None
        )
        baseline_confidence = (
            baseline_result.confidence if baseline_result is not None else 0.0
        )
        challenger_confidence = (
            challenger_result.confidence if challenger_result is not None else 0.0
        )

        score_delta: float | None = None
        if baseline_score is not None and challenger_score is not None:
            score_delta = challenger_score - baseline_score
            if baseline_status == "ok" and challenger_status == "ok":
                score_abs_deltas.append(abs(score_delta))

        confidence_delta = challenger_confidence - baseline_confidence
        confidence_abs_deltas.append(abs(confidence_delta))

        case_results.append(
            AbCaseResult(
                case_id=case.case_id,
                entity_id=case.entity_id,
                baseline_analyzer_type=(
                    baseline_result.analyzer_type
                    if baseline_result is not None
                    else baseline.analyzer_type
                ),
                challenger_analyzer_type=(
                    challenger_result.analyzer_type
                    if challenger_result is not None
                    else challenger.analyzer_type
                ),
                baseline_status=baseline_status,
                challenger_status=challenger_status,
                baseline_score=baseline_score,
                challenger_score=challenger_score,
                baseline_confidence=baseline_confidence,
                challenger_confidence=challenger_confidence,
                score_delta=score_delta,
                confidence_delta=confidence_delta,
                status_matches=status_matches,
                baseline_error=baseline_error,
                challenger_error=challenger_error,
            )
        )

    total_cases = len(cases)
    return AbEvaluationReport(
        baseline_analyzer_type=baseline.analyzer_type,
        challenger_analyzer_type=challenger.analyzer_type,
        total_cases=total_cases,
        status_match_rate=(
            status_match_count / total_cases if total_cases > 0 else 0.0
        ),
        ok_pair_score_mae=_mean(score_abs_deltas),
        confidence_mae=_mean(confidence_abs_deltas),
        baseline_inconclusive_count=baseline_inconclusive_count,
        challenger_inconclusive_count=challenger_inconclusive_count,
        inconclusive_count_delta=(
            challenger_inconclusive_count - baseline_inconclusive_count
        ),
        baseline_failure_count=baseline_failure_count,
        challenger_failure_count=challenger_failure_count,
        cases=tuple(case_results),
    )


def _safe_analyze(
    analyzer: AnalyzerInterface,
    case: AbEvaluationCase,
) -> tuple[Any | None, str | None]:
    """Run analyzer.analyze; return (result, error_message_or_none).

    Captures per-case analyzer exceptions so an A/B run can complete and
    record partial outcomes rather than aborting on the first failure.
    """

    try:
        return analyzer.analyze(case.entity_id, case.context), None
    except Exception as exc:  # noqa: BLE001 - explicit per-case capture
        return None, f"{type(exc).__name__}: {exc}"


def format_ab_report_json(report: AbEvaluationReport) -> str:
    """Format an A/B report as stable, parseable JSON."""

    return json.dumps(_report_payload(report), allow_nan=False, indent=2, sort_keys=True)


def format_ab_report_markdown(report: AbEvaluationReport) -> str:
    """Format an A/B report as stable Markdown tables."""

    summary_rows = [
        ("baseline_analyzer_type", report.baseline_analyzer_type),
        ("challenger_analyzer_type", report.challenger_analyzer_type),
        ("total_cases", report.total_cases),
        ("status_match_rate", _format_value(report.status_match_rate)),
        ("ok_pair_score_mae", _format_value(report.ok_pair_score_mae)),
        ("confidence_mae", _format_value(report.confidence_mae)),
        ("baseline_inconclusive_count", report.baseline_inconclusive_count),
        ("challenger_inconclusive_count", report.challenger_inconclusive_count),
        ("inconclusive_count_delta", report.inconclusive_count_delta),
        ("baseline_failure_count", report.baseline_failure_count),
        ("challenger_failure_count", report.challenger_failure_count),
    ]
    lines = [
        "# L6 A/B Evaluation",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    lines.extend(f"| {metric} | {_escape_markdown(value)} |" for metric, value in summary_rows)
    lines.extend(
        [
            "",
            "## Per Case",
            "",
            (
                "| case_id | entity_id | baseline_analyzer_type | "
                "challenger_analyzer_type | baseline_status | challenger_status | "
                "score_delta | confidence_delta | status_matches |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(_case_markdown_row(case) for case in report.cases)
    return "\n".join(lines) + "\n"


def write_ab_report(
    report: AbEvaluationReport,
    output_dir: Path,
    *,
    stem: str = "multi_agent_ab",
) -> dict[str, Path]:
    """Write JSON and Markdown A/B reports and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(format_ab_report_json(report), encoding="utf-8")
    markdown_path.write_text(format_ab_report_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _report_payload(report: AbEvaluationReport) -> dict[str, object]:
    return {
        "baseline_analyzer_type": report.baseline_analyzer_type,
        "challenger_analyzer_type": report.challenger_analyzer_type,
        "total_cases": report.total_cases,
        "status_match_rate": report.status_match_rate,
        "ok_pair_score_mae": report.ok_pair_score_mae,
        "confidence_mae": report.confidence_mae,
        "baseline_inconclusive_count": report.baseline_inconclusive_count,
        "challenger_inconclusive_count": report.challenger_inconclusive_count,
        "inconclusive_count_delta": report.inconclusive_count_delta,
        "baseline_failure_count": report.baseline_failure_count,
        "challenger_failure_count": report.challenger_failure_count,
        "cases": [_case_payload(case) for case in report.cases],
    }


def _case_payload(case: AbCaseResult) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "entity_id": case.entity_id,
        "baseline_analyzer_type": case.baseline_analyzer_type,
        "challenger_analyzer_type": case.challenger_analyzer_type,
        "baseline_status": case.baseline_status,
        "challenger_status": case.challenger_status,
        "baseline_score": case.baseline_score,
        "challenger_score": case.challenger_score,
        "baseline_confidence": case.baseline_confidence,
        "challenger_confidence": case.challenger_confidence,
        "score_delta": case.score_delta,
        "confidence_delta": case.confidence_delta,
        "status_matches": case.status_matches,
        "baseline_error": case.baseline_error,
        "challenger_error": case.challenger_error,
    }


def _case_markdown_row(case: AbCaseResult) -> str:
    values = [
        case.case_id,
        case.entity_id,
        case.baseline_analyzer_type,
        case.challenger_analyzer_type,
        case.baseline_status,
        case.challenger_status,
        _format_value(case.score_delta),
        _format_value(case.confidence_delta),
        case.status_matches,
    ]
    return "| " + " | ".join(_escape_markdown(value) for value in values) + " |"


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    if value is None:
        return "null"
    return str(value)


def _escape_markdown(value: object) -> str:
    return _format_value(value).replace("|", "\\|")


__all__ = [
    "AbCaseResult",
    "AbEvaluationCase",
    "AbEvaluationReport",
    "format_ab_report_json",
    "format_ab_report_markdown",
    "run_ab_evaluation",
    "write_ab_report",
]
