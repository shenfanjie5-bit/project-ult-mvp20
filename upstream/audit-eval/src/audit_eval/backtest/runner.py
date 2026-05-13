"""Offline backtest orchestration entrypoint."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from audit_eval._boundary import BoundaryViolationError, assert_no_forbidden_write
from audit_eval.backtest.alphalens_adapter import AlphalensAdapter
from audit_eval.backtest.errors import (
    BacktestInputError,
    BacktestRunnerError,
    PITViolationError,
)
from audit_eval.backtest.job import BacktestJob
from audit_eval.backtest.pit_checker import (
    PointInTimeChecker,
    get_default_pit_feature_gateway,
)
from audit_eval.backtest.storage import BacktestResultStorage
from audit_eval.backtest.writer import persist_backtest_result
from audit_eval.contracts.backtest_result import BacktestResult
from audit_eval.contracts.common import JsonObject


class BacktestMetricsAdapter(Protocol):
    """Boundary for computing backtest metrics for one feature snapshot range."""

    def run(
        self,
        feature_ref: str,
        snapshot_range: JsonObject,
        metrics_config: JsonObject,
    ) -> JsonObject:
        """Return JSON metrics for feature_ref over the supplied snapshot range."""


def run_backtest(
    job_config: BacktestJob,
    *,
    pit_checker: PointInTimeChecker | None = None,
    adapter: BacktestMetricsAdapter | None = None,
    storage: BacktestResultStorage | None = None,
    created_at: datetime | None = None,
) -> BacktestResult:
    """Run an offline PIT-validated backtest and persist its analytical result."""

    _validate_offline_job(job_config)
    checker = pit_checker or PointInTimeChecker(get_default_pit_feature_gateway())

    snapshot_range = deepcopy(job_config.formal_snapshot_range)
    pit_result = checker.validate(job_config.feature_ref, snapshot_range)
    if not pit_result.passed:
        raise PITViolationError(pit_result)

    metrics_adapter = adapter or _default_adapter_for_engine(job_config)
    metrics = _run_metrics_adapter(metrics_adapter, job_config)
    effective_created_at = created_at or datetime.now(timezone.utc)
    result = BacktestResult(
        backtest_id=_backtest_id(
            job_ref=job_config.job_ref,
            feature_ref=job_config.feature_ref,
            engine=job_config.engine,
            created_at=effective_created_at,
        ),
        job_ref=job_config.job_ref,
        engine=job_config.engine,
        feature_ref=job_config.feature_ref,
        formal_snapshot_range=deepcopy(job_config.formal_snapshot_range),
        metrics=metrics,
        pit_check_passed=True,
        created_at=effective_created_at,
    )
    persist_backtest_result(result, storage=storage)
    return result


def _validate_offline_job(job_config: BacktestJob) -> None:
    if getattr(job_config, "run_mode", None) != "offline_research":
        raise BacktestInputError(
            "BacktestJob.run_mode must be offline_research; "
            "backtests cannot run in daily cycle or online modes"
        )
    if getattr(job_config, "engine", None) not in {"alphalens", "backtrader"}:
        raise BacktestInputError("engine must be 'alphalens' or 'backtrader'")


def _default_adapter_for_engine(job_config: BacktestJob) -> BacktestMetricsAdapter:
    if job_config.engine == "alphalens":
        return AlphalensAdapter()
    raise BacktestInputError(
        "Backtrader backtests require an explicit adapter; "
        "only Alphalens is wired by default"
    )


def _run_metrics_adapter(
    adapter: BacktestMetricsAdapter,
    job_config: BacktestJob,
) -> JsonObject:
    try:
        raw_metrics = adapter.run(
            job_config.feature_ref,
            deepcopy(job_config.formal_snapshot_range),
            deepcopy(job_config.metrics_config),
        )
    except BacktestRunnerError:
        raise
    except Exception as exc:
        raise BacktestRunnerError("Backtest metrics adapter failed") from exc
    return _validate_metrics_object(raw_metrics)


def _validate_metrics_object(metrics: object) -> JsonObject:
    if not isinstance(metrics, dict):
        raise BacktestRunnerError("Backtest metrics adapter must return a JSON object")
    if not metrics:
        raise BacktestRunnerError("Backtest metrics must not be empty")
    try:
        assert_no_forbidden_write(metrics, path="$.backtest_metrics")
    except BoundaryViolationError as exc:
        raise BacktestRunnerError("Backtest metrics contain forbidden fields") from exc
    try:
        json.dumps(metrics, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BacktestRunnerError("Backtest metrics must contain only JSON values") from exc
    return deepcopy(metrics)


def _backtest_id(
    *,
    job_ref: str,
    feature_ref: str,
    engine: str,
    created_at: datetime,
) -> str:
    digest = hashlib.sha256(
        "\0".join((job_ref, feature_ref, engine, created_at.isoformat())).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"backtest-{digest}"


__all__ = [
    "BacktestMetricsAdapter",
    "run_backtest",
]
