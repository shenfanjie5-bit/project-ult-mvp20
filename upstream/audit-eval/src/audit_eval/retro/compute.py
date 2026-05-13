"""Retrospective evaluation computation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime, timezone
from numbers import Real
from typing import Any

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.audit import query as audit_query
from audit_eval.audit.query import ReplayQueryContext
from audit_eval.audit.replay_view import ReplayView
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.contracts.retrospective import RetrospectiveEvaluation
from audit_eval.retro.horizon import (
    UnsupportedRetrospectiveHorizon,
    require_mature_horizon,
)
from audit_eval.retro.schema import (
    DeviationResult,
    MarketOutcome,
    RetrospectiveSeed,
    RetrospectiveTarget,
)
from audit_eval.retro.storage import (
    RetrospectiveEvaluationStorage,
    RetrospectiveInputError,
    RetrospectiveInputGateway,
    RetrospectiveStorageError,
    get_default_evaluation_storage,
    get_default_input_gateway,
)


def compute_retrospective(
    horizon: RetrospectiveHorizon,
    date_ref: date,
    *,
    replay_context: ReplayQueryContext | None = None,
    input_gateway: RetrospectiveInputGateway | None = None,
    storage: RetrospectiveEvaluationStorage | None = None,
    as_of_date: date | None = None,
) -> list[RetrospectiveEvaluation]:
    """Compute and append retrospective evaluations for one date/horizon."""

    effective_as_of_date = as_of_date or date.today()
    require_mature_horizon(horizon, date_ref, effective_as_of_date)

    gateway = input_gateway or get_default_input_gateway()
    evaluation_storage = storage or get_default_evaluation_storage()

    evaluations: list[RetrospectiveEvaluation] = []
    targets = list(gateway.list_targets(horizon, date_ref))
    for target in targets:
        assert_no_forbidden_write(asdict(target), path="$.targets[]")
        replay_view = audit_query.replay_cycle_object(
            target.cycle_id,
            target.object_ref,
            context=replay_context,
        )
        seed = extract_retrospective_seed(replay_view)
        outcome = gateway.load_market_outcome(target, horizon, date_ref)
        assert_no_forbidden_write(asdict(outcome), path="$.outcome")
        _validate_outcome_binding(outcome, target, horizon)

        deviation = calculate_deviation(seed, outcome)
        evaluation = _build_evaluation(
            target=target,
            horizon=horizon,
            deviation=deviation,
        )
        assert_no_forbidden_write(
            evaluation.model_dump(mode="python"),
            path="$.evaluations[]",
        )
        evaluations.append(evaluation)

    try:
        evaluation_storage.append_evaluations(evaluations)
    except RetrospectiveStorageError:
        raise
    except Exception as exc:
        raise RetrospectiveStorageError(f"append_evaluations failed: {exc}") from exc
    return evaluations


def extract_retrospective_seed(replay_view: ReplayView) -> RetrospectiveSeed:
    """Extract the target object's retrospective seed from audit records."""

    seeds: list[RetrospectiveSeed] = []
    for audit_record in replay_view.audit_records:
        if audit_record.object_ref != replay_view.object_ref:
            continue
        seed_entry = _select_retrospective_seed_payload(audit_record)
        if seed_entry is None:
            continue
        source_name, seed_payload = seed_entry
        assert_no_forbidden_write(
            seed_payload,
            path=f"$.audit_records[{audit_record.record_id}].{source_name}"
            ".retrospective_seed",
        )
        trend_score = _require_finite_number(
            seed_payload.get("trend_score"),
            field_path="retrospective_seed.trend_score",
        )
        risk_score = _require_finite_number(
            seed_payload.get("risk_score"),
            field_path="retrospective_seed.risk_score",
        )
        breakdown = seed_payload.get("baseline_vs_llm_breakdown", {})
        if not isinstance(breakdown, dict):
            raise RetrospectiveInputError(
                "retrospective_seed.baseline_vs_llm_breakdown must be an object"
            )
        seeds.append(
            RetrospectiveSeed(
                cycle_id=replay_view.cycle_id,
                object_ref=replay_view.object_ref,
                expected_trend_score=trend_score,
                expected_risk_score=risk_score,
                baseline_vs_llm_breakdown=dict(breakdown),
            )
        )

    unique_seeds: list[RetrospectiveSeed] = []
    for seed in seeds:
        if seed not in unique_seeds:
            unique_seeds.append(seed)
    if len(unique_seeds) == 1:
        return unique_seeds[0]
    if len(unique_seeds) > 1:
        raise RetrospectiveInputError(
            "ReplayView.audit_records contained conflicting retrospective_seed values "
            f"for object_ref={replay_view.object_ref!r}"
        )
    raise RetrospectiveInputError(
        "ReplayView.audit_records did not contain a retrospective_seed with "
        f"numeric trend_score and risk_score for object_ref={replay_view.object_ref!r}"
    )


def calculate_deviation(
    seed: RetrospectiveSeed,
    outcome: MarketOutcome,
) -> DeviationResult:
    """Calculate absolute trend/risk deviations."""

    breakdown = dict(seed.baseline_vs_llm_breakdown)
    breakdown.update(outcome.baseline_vs_llm_breakdown)
    return DeviationResult(
        trend_deviation=abs(seed.expected_trend_score - outcome.realized_trend_score),
        risk_deviation=abs(seed.expected_risk_score - outcome.realized_risk_score),
        hit_rate_rel=outcome.hit_rate_rel,
        baseline_vs_llm_breakdown=breakdown,
    )


def _validate_outcome_binding(
    outcome: MarketOutcome,
    target: RetrospectiveTarget,
    horizon: RetrospectiveHorizon,
) -> None:
    if outcome.cycle_id != target.cycle_id:
        raise RetrospectiveInputError("MarketOutcome.cycle_id does not match target")
    if outcome.object_ref != target.object_ref:
        raise RetrospectiveInputError("MarketOutcome.object_ref does not match target")
    if outcome.horizon != horizon:
        raise RetrospectiveInputError("MarketOutcome.horizon does not match request")
    _require_finite_number(
        outcome.realized_trend_score,
        field_path="MarketOutcome.realized_trend_score",
    )
    _require_finite_number(
        outcome.realized_risk_score,
        field_path="MarketOutcome.realized_risk_score",
    )
    if outcome.hit_rate_rel is not None:
        _require_finite_number(
            outcome.hit_rate_rel,
            field_path="MarketOutcome.hit_rate_rel",
        )


def _select_retrospective_seed_payload(
    audit_record: Any,
) -> tuple[str, Mapping[str, Any]] | None:
    for source_name, payload in (
        ("parsed_result", audit_record.parsed_result),
        ("params_snapshot", audit_record.params_snapshot),
    ):
        if not isinstance(payload, Mapping):
            continue
        seed_payload = payload.get("retrospective_seed")
        if seed_payload is None:
            continue
        if not isinstance(seed_payload, Mapping):
            raise RetrospectiveInputError(
                f"AuditRecord.{source_name}.retrospective_seed must be an object"
            )
        return source_name, seed_payload
    return None


def _require_finite_number(value: Any, *, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RetrospectiveInputError(f"{field_path} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RetrospectiveInputError(f"{field_path} must be finite")
    return number


def _build_evaluation(
    *,
    target: RetrospectiveTarget,
    horizon: RetrospectiveHorizon,
    deviation: DeviationResult,
) -> RetrospectiveEvaluation:
    trend_deviation = deviation.trend_deviation
    risk_deviation = deviation.risk_deviation
    alert_score = RetrospectiveEvaluation.derive_alert_score(
        trend_deviation,
        risk_deviation,
    )
    return RetrospectiveEvaluation(
        evaluation_id=_evaluation_id(target, horizon),
        cycle_id=target.cycle_id,
        object_ref=target.object_ref,
        horizon=horizon,
        trend_deviation=trend_deviation,
        risk_deviation=risk_deviation,
        alert_score=alert_score,
        learning_score=RetrospectiveEvaluation.derive_learning_score(
            trend_deviation,
            risk_deviation,
        ),
        deviation_level=_deviation_level(alert_score),
        hit_rate_rel=deviation.hit_rate_rel,
        baseline_vs_llm_breakdown=deviation.baseline_vs_llm_breakdown,
        evaluated_at=datetime.now(timezone.utc),
    )


def _evaluation_id(
    target: RetrospectiveTarget,
    horizon: RetrospectiveHorizon,
) -> str:
    return f"retro-{target.cycle_id}-{target.object_ref}-{horizon}"


def _deviation_level(alert_score: float) -> int:
    return min(4, int(math.floor(alert_score)))


__all__ = [
    "UnsupportedRetrospectiveHorizon",
    "calculate_deviation",
    "compute_retrospective",
    "extract_retrospective_seed",
]
