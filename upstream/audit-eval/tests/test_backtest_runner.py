from __future__ import annotations

import socket
import urllib.request
from datetime import datetime, timezone
from typing import Any

import pytest

from audit_eval.backtest import (
    BacktestInputError,
    BacktestJob,
    BacktestRunnerError,
    BacktestStorageError,
    InMemoryBacktestResultStorage,
    PITCheckResult,
    PITViolationError,
    persist_backtest_result,
    run_backtest,
)
from audit_eval.contracts import BacktestResult


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_socket = socket.socket

    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Backtests must not call network")

    def guarded_socket(
        family: int = socket.AF_INET,
        *args: Any,
        **kwargs: Any,
    ) -> socket.socket:
        if family == socket.AF_UNIX:
            return real_socket(family, *args, **kwargs)
        raise AssertionError("Backtests must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", guarded_socket)


class _RecordingPITChecker:
    def __init__(
        self,
        call_log: list[str],
        result: PITCheckResult | None = None,
    ) -> None:
        self.call_log = call_log
        self.result = result or PITCheckResult(passed=True)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def validate(
        self,
        feature_ref: str,
        snapshot_range: dict[str, object],
    ) -> PITCheckResult:
        self.call_log.append("pit")
        self.calls.append((feature_ref, snapshot_range))
        return self.result


class _RecordingAdapter:
    def __init__(
        self,
        call_log: list[str],
        metrics: object | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.call_log = call_log
        self.metrics = _metrics() if metrics is None else metrics
        self.exc = exc
        self.calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def run(
        self,
        feature_ref: str,
        snapshot_range: dict[str, object],
        metrics_config: dict[str, object],
    ) -> Any:
        self.call_log.append("adapter")
        self.calls.append((feature_ref, snapshot_range, metrics_config))
        if self.exc is not None:
            raise self.exc
        return self.metrics


class _RecordingStorage(InMemoryBacktestResultStorage):
    def __init__(
        self,
        call_log: list[str],
        exc: Exception | None = None,
    ) -> None:
        super().__init__()
        self.call_log = call_log
        self.exc = exc

    def append_backtest_result(self, result: BacktestResult) -> str:
        self.call_log.append("storage")
        if self.exc is not None:
            raise self.exc
        return super().append_backtest_result(result)


def _snapshot_range() -> dict[str, object]:
    return {
        "manifest_cycle_id": "cycle_20260418",
        "manifest_snapshot_refs": ["snapshot://features/20260418"],
    }


def _job(*, engine: str = "alphalens") -> BacktestJob:
    return BacktestJob(
        job_ref="job://alphalens-1",
        feature_ref="feature://momentum/v1",
        formal_snapshot_range=_snapshot_range(),
        engine=engine,  # type: ignore[arg-type]
    )


def _unsafe_job_with_run_mode(run_mode: str) -> BacktestJob:
    job = object.__new__(BacktestJob)
    object.__setattr__(job, "job_ref", "job://alphalens-1")
    object.__setattr__(job, "feature_ref", "feature://momentum/v1")
    object.__setattr__(job, "formal_snapshot_range", _snapshot_range())
    object.__setattr__(job, "engine", "alphalens")
    object.__setattr__(job, "run_mode", run_mode)
    object.__setattr__(job, "metrics_config", {})
    return job


def _created_at() -> datetime:
    return datetime(2026, 4, 18, 9, 30, tzinfo=timezone.utc)


def _metrics() -> dict[str, object]:
    return {
        "ic": {"mean": {"1D": 0.12}},
        "quantile_returns": {"1": {"1D": 0.01}, "2": {"1D": 0.03}},
        "decay": {"rank_autocorrelation_mean": 0.6, "turnover": {"1": 0.2}},
    }


def test_run_backtest_validates_pit_then_adapter_then_storage() -> None:
    call_log: list[str] = []
    pit_checker = _RecordingPITChecker(call_log)
    adapter = _RecordingAdapter(call_log)
    storage = _RecordingStorage(call_log)

    result = run_backtest(
        _job(),
        pit_checker=pit_checker,  # type: ignore[arg-type]
        adapter=adapter,
        storage=storage,
        created_at=_created_at(),
    )

    assert call_log == ["pit", "adapter", "storage"]
    assert pit_checker.calls == [("feature://momentum/v1", _snapshot_range())]
    assert adapter.calls == [("feature://momentum/v1", _snapshot_range(), {})]
    assert result.metrics == _metrics()
    assert result.pit_check_passed is True
    assert storage.append_calls == 1
    assert storage.rows[0]["backtest_id"] == result.backtest_id


def test_run_backtest_pit_failure_does_not_call_adapter_or_storage() -> None:
    call_log: list[str] = []
    pit_checker = _RecordingPITChecker(
        call_log,
        PITCheckResult(passed=False, violations=("look-ahead bias",)),
    )
    adapter = _RecordingAdapter(call_log)
    storage = _RecordingStorage(call_log)

    with pytest.raises(PITViolationError, match="look-ahead bias"):
        run_backtest(
            _job(),
            pit_checker=pit_checker,  # type: ignore[arg-type]
            adapter=adapter,
            storage=storage,
        )

    assert call_log == ["pit"]
    assert adapter.calls == []
    assert storage.append_calls == 0
    assert storage.rows == []


@pytest.mark.parametrize("run_mode", ["daily_cycle", "online", "read_head"])
def test_run_backtest_rejects_non_offline_mode_before_boundaries(
    run_mode: str,
) -> None:
    call_log: list[str] = []

    with pytest.raises(BacktestInputError, match="offline_research"):
        run_backtest(
            _unsafe_job_with_run_mode(run_mode),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            adapter=_RecordingAdapter(call_log),
            storage=_RecordingStorage(call_log),
        )

    assert call_log == []


def test_run_backtest_wraps_adapter_exceptions() -> None:
    call_log: list[str] = []
    storage = _RecordingStorage(call_log)

    with pytest.raises(BacktestRunnerError, match="metrics adapter failed"):
        run_backtest(
            _job(),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            adapter=_RecordingAdapter(call_log, exc=ValueError("boom")),
            storage=storage,
        )

    assert call_log == ["pit", "adapter"]
    assert storage.append_calls == 0
    assert storage.rows == []


def test_run_backtest_passes_copied_metrics_config_to_adapter() -> None:
    call_log: list[str] = []
    pit_checker = _RecordingPITChecker(call_log)
    adapter = _RecordingAdapter(call_log)
    storage = _RecordingStorage(call_log)
    metrics_config = {"period": 5, "nested": {"enabled": True}}
    job = BacktestJob(
        job_ref="job://alphalens-1",
        feature_ref="feature://momentum/v1",
        formal_snapshot_range=_snapshot_range(),
        metrics_config=metrics_config,
    )

    run_backtest(
        job,
        pit_checker=pit_checker,  # type: ignore[arg-type]
        adapter=adapter,
        storage=storage,
        created_at=_created_at(),
    )
    metrics_config["period"] = 1
    adapter.calls[0][2]["period"] = 9

    assert adapter.calls[0] == (
        "feature://momentum/v1",
        _snapshot_range(),
        {"period": 9, "nested": {"enabled": True}},
    )
    assert job.metrics_config == {"period": 5, "nested": {"enabled": True}}


def test_run_backtest_wraps_storage_exceptions_without_half_write() -> None:
    call_log: list[str] = []
    storage = _RecordingStorage(call_log, exc=ValueError("disk unavailable"))

    with pytest.raises(BacktestStorageError, match="storage append failed"):
        run_backtest(
            _job(),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            adapter=_RecordingAdapter(call_log),
            storage=storage,
            created_at=_created_at(),
        )

    assert call_log == ["pit", "adapter", "storage"]
    assert storage.append_calls == 0
    assert storage.rows == []


def test_run_backtest_fails_closed_without_default_storage() -> None:
    call_log: list[str] = []

    with pytest.raises(BacktestStorageError, match="No default backtest"):
        run_backtest(
            _job(),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            adapter=_RecordingAdapter(call_log),
            created_at=_created_at(),
        )

    assert call_log == ["pit", "adapter"]


def test_writer_rejects_failed_pit_even_if_contract_validation_was_bypassed() -> None:
    result = BacktestResult.model_construct(
        backtest_id="backtest-unsafe",
        job_ref="job://alphalens-1",
        engine="alphalens",
        feature_ref="feature://momentum/v1",
        formal_snapshot_range=_snapshot_range(),
        metrics=_metrics(),
        pit_check_passed=False,
        created_at=_created_at(),
    )
    storage = InMemoryBacktestResultStorage()

    with pytest.raises(BacktestStorageError, match="PIT check"):
        persist_backtest_result(result, storage=storage)

    assert storage.append_calls == 0
    assert storage.rows == []


def test_writer_rejects_storage_backtest_id_mismatch() -> None:
    class MismatchedStorage(InMemoryBacktestResultStorage):
        def append_backtest_result(self, result: BacktestResult) -> str:
            super().append_backtest_result(result)
            return "backtest-other"

    result = BacktestResult(
        backtest_id="backtest-expected",
        job_ref="job://alphalens-1",
        engine="alphalens",
        feature_ref="feature://momentum/v1",
        formal_snapshot_range=_snapshot_range(),
        metrics=_metrics(),
        pit_check_passed=True,
        created_at=_created_at(),
    )
    storage = MismatchedStorage()

    with pytest.raises(BacktestStorageError, match="mismatched backtest_id"):
        persist_backtest_result(result, storage=storage)


@pytest.mark.parametrize(
    "metrics",
    [
        {},
        [],
        {"bad": object()},
        {"bad": float("nan")},
        {"nested": {"feature_weight_multiplier": 1.2}},
    ],
)
def test_run_backtest_rejects_invalid_adapter_metrics_before_storage(
    metrics: object,
) -> None:
    call_log: list[str] = []
    storage = _RecordingStorage(call_log)

    with pytest.raises(BacktestRunnerError):
        run_backtest(
            _job(),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            adapter=_RecordingAdapter(call_log, metrics=metrics),
            storage=storage,
            created_at=_created_at(),
        )

    assert call_log == ["pit", "adapter"]
    assert storage.append_calls == 0
    assert storage.rows == []


def test_backtrader_requires_explicit_adapter_after_pit_validation() -> None:
    call_log: list[str] = []
    storage = _RecordingStorage(call_log)

    with pytest.raises(BacktestInputError, match="Backtrader"):
        run_backtest(
            _job(engine="backtrader"),
            pit_checker=_RecordingPITChecker(call_log),  # type: ignore[arg-type]
            storage=storage,
        )

    assert call_log == ["pit"]
    assert storage.append_calls == 0
    assert storage.rows == []
