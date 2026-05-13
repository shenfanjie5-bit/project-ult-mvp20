"""Tests for L6 analyzer A/B report generation."""

from __future__ import annotations

import json

import pytest

from main_core.common.contexts import AlphaAnalysisContext
from main_core.common.schemas import AlphaResultSnapshot, FeatureSignalBundle, WorldStateSnapshot
from main_core.l6_alpha.ab_runner import (
    AbEvaluationCase,
    format_ab_report_json,
    format_ab_report_markdown,
    run_ab_evaluation,
    write_ab_report,
)

EXPECTED_CONFIDENCE_MAE = 0.25
EXPECTED_OK_SCORE_MAE = 0.3
EXPECTED_STATUS_MATCH_RATE = 0.5
TOTAL_AB_CASES = 2


class RecordingAnalyzer:
    def __init__(
        self,
        analyzer_type: str,
        results: dict[str, AlphaResultSnapshot],
    ) -> None:
        self.analyzer_type = analyzer_type
        self.results = results
        self.calls: list[tuple[str, AlphaAnalysisContext]] = []

    def analyze(
        self,
        entity_id: str,
        context: AlphaAnalysisContext,
    ) -> AlphaResultSnapshot:
        self.calls.append((entity_id, context))
        return self.results[entity_id]


def test_run_ab_evaluation_computes_metrics_from_same_contexts(monkeypatch) -> None:
    def fail_if_l3_builder_is_called(*args, **kwargs):
        raise AssertionError("A/B runner must use supplied contexts")

    monkeypatch.setattr(
        "main_core.l3_features.build_feature_signal_bundle",
        fail_if_l3_builder_is_called,
    )
    monkeypatch.setattr(
        "main_core.l3_features.build_feature_signal_bundles",
        fail_if_l3_builder_is_called,
    )
    contexts = [_context("ENT_A"), _context("ENT_B")]
    cases = [
        AbEvaluationCase("case-a", "ENT_A", contexts[0]),
        AbEvaluationCase("case-b", "ENT_B", contexts[1]),
    ]
    baseline = RecordingAnalyzer(
        "single_prompt_v1",
        {
            "ENT_A": _alpha_result("ENT_A", "single_prompt_v1", 0.5, 0.7, "ok"),
            "ENT_B": _alpha_result("ENT_B", "single_prompt_v1", None, 0.0, "inconclusive"),
        },
    )
    challenger = RecordingAnalyzer(
        "multi_agent_v1",
        {
            "ENT_A": _alpha_result("ENT_A", "multi_agent_v1", 0.8, 0.6, "ok"),
            "ENT_B": _alpha_result("ENT_B", "multi_agent_v1", 0.2, 0.4, "ok"),
        },
    )

    report = run_ab_evaluation(cases, baseline=baseline, challenger=challenger)

    assert baseline.calls == [("ENT_A", contexts[0]), ("ENT_B", contexts[1])]
    assert challenger.calls == [("ENT_A", contexts[0]), ("ENT_B", contexts[1])]
    assert report.total_cases == TOTAL_AB_CASES
    assert report.status_match_rate == EXPECTED_STATUS_MATCH_RATE
    assert report.ok_pair_score_mae == pytest.approx(EXPECTED_OK_SCORE_MAE)
    assert report.confidence_mae == pytest.approx(EXPECTED_CONFIDENCE_MAE)
    assert report.baseline_inconclusive_count == 1
    assert report.challenger_inconclusive_count == 0
    assert report.inconclusive_count_delta == -1
    assert report.cases[0].score_delta == pytest.approx(EXPECTED_OK_SCORE_MAE)
    assert report.cases[1].score_delta is None


def test_ab_report_json_is_parseable_and_excludes_context_models() -> None:
    report = run_ab_evaluation(
        [AbEvaluationCase("case-a", "ENT_A", _context("ENT_A"))],
        baseline=RecordingAnalyzer(
            "single_prompt_v1",
            {"ENT_A": _alpha_result("ENT_A", "single_prompt_v1", 0.5, 0.7, "ok")},
        ),
        challenger=RecordingAnalyzer(
            "multi_agent_v1",
            {"ENT_A": _alpha_result("ENT_A", "multi_agent_v1", 0.6, 0.8, "ok")},
        ),
    )

    payload = json.loads(format_ab_report_json(report))

    assert payload["baseline_analyzer_type"] == "single_prompt_v1"
    assert payload["challenger_analyzer_type"] == "multi_agent_v1"
    assert payload["cases"][0]["case_id"] == "case-a"
    assert "context" not in payload["cases"][0]
    assert "feature_bundle" not in json.dumps(payload)


def test_ab_report_markdown_uses_stable_summary_and_case_tables() -> None:
    report = run_ab_evaluation(
        [AbEvaluationCase("case-a", "ENT_A", _context("ENT_A"))],
        baseline=RecordingAnalyzer(
            "single_prompt_v1",
            {"ENT_A": _alpha_result("ENT_A", "single_prompt_v1", 0.5, 0.7, "ok")},
        ),
        challenger=RecordingAnalyzer(
            "multi_agent_v1",
            {"ENT_A": _alpha_result("ENT_A", "multi_agent_v1", 0.6, 0.8, "ok")},
        ),
    )

    markdown = format_ab_report_markdown(report)

    assert "| metric | value |" in markdown
    assert (
        "| case_id | entity_id | baseline_analyzer_type | challenger_analyzer_type |"
        in markdown
    )
    assert "| case-a | ENT_A | single_prompt_v1 | multi_agent_v1 |" in markdown


def test_run_ab_evaluation_rejects_empty_cases() -> None:
    baseline = RecordingAnalyzer("single_prompt_v1", {})
    challenger = RecordingAnalyzer("multi_agent_v1", {})

    with pytest.raises(ValueError, match="at least one case"):
        run_ab_evaluation([], baseline=baseline, challenger=challenger)


def test_run_ab_evaluation_records_per_case_analyzer_failures() -> None:
    class FailingAnalyzer:
        analyzer_type = "multi_agent_v1"

        def analyze(self, entity_id, context):  # type: ignore[no-untyped-def]
            raise RuntimeError("provider unavailable")

    baseline = RecordingAnalyzer(
        "single_prompt_v1",
        {"ENT_A": _alpha_result("ENT_A", "single_prompt_v1", 0.5, 0.7, "ok")},
    )
    cases = [AbEvaluationCase("case-a", "ENT_A", _context("ENT_A"))]

    report = run_ab_evaluation(cases, baseline=baseline, challenger=FailingAnalyzer())

    assert report.challenger_failure_count == 1
    assert report.baseline_failure_count == 0
    assert report.cases[0].challenger_status == "error"
    assert "RuntimeError" in (report.cases[0].challenger_error or "")
    assert report.cases[0].status_matches is False


def test_write_ab_report_writes_json_and_markdown(tmp_path) -> None:
    report = run_ab_evaluation(
        [AbEvaluationCase("case-a", "ENT_A", _context("ENT_A"))],
        baseline=RecordingAnalyzer(
            "single_prompt_v1",
            {"ENT_A": _alpha_result("ENT_A", "single_prompt_v1", 0.5, 0.7, "ok")},
        ),
        challenger=RecordingAnalyzer(
            "multi_agent_v1",
            {"ENT_A": _alpha_result("ENT_A", "multi_agent_v1", 0.6, 0.8, "ok")},
        ),
    )

    paths = write_ab_report(report, tmp_path, stem="custom_ab")

    assert paths["json"].name == "custom_ab.json"
    assert paths["markdown"].name == "custom_ab.md"
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["total_cases"] == 1
    assert "# L6 A/B Evaluation" in paths["markdown"].read_text(encoding="utf-8")


def _context(entity_id: str) -> AlphaAnalysisContext:
    cycle_id = "cycle_ab"
    return AlphaAnalysisContext(
        cycle_id=cycle_id,
        entity_id=entity_id,
        feature_bundle=FeatureSignalBundle(
            cycle_id=cycle_id,
            entity_id=entity_id,
            feature_values={"momentum": 1.0},
            signal_values={"signal": "positive"},
            graph_features={},
            feature_weight_multiplier={"momentum": 1.0},
        ),
        world_state=WorldStateSnapshot(
            cycle_id=cycle_id,
            baseline_regime="neutral",
            llm_delta=0,
            final_regime="neutral",
            llm_rationale="fixture",
            actual_model_used="fixture",
            actual_provider="local",
            fallback_path=[],
        ),
        similar_cases=[],
    )


def _alpha_result(
    entity_id: str,
    analyzer_type: str,
    score: float | None,
    confidence: float,
    status: str,
) -> AlphaResultSnapshot:
    return AlphaResultSnapshot(
        cycle_id="cycle_ab",
        entity_id=entity_id,
        analyzer_type=analyzer_type,
        score=score,
        confidence=confidence,
        rationale=f"{analyzer_type} {status}",
        similar_cases=[],
        status=status,
    )
