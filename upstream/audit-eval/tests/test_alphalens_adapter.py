from __future__ import annotations

import importlib
import os
import socket
import types
import urllib.request
from typing import Any

import pytest

from audit_eval.backtest import (
    AlphalensAdapter,
    BacktestRunnerError,
)


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_socket = socket.socket

    def fail_network_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Alphalens adapter tests must not call network")

    def guarded_socket(
        family: int = socket.AF_INET,
        *args: Any,
        **kwargs: Any,
    ) -> socket.socket:
        if family == socket.AF_UNIX:
            return real_socket(family, *args, **kwargs)
        raise AssertionError("Alphalens adapter tests must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network_call)
    monkeypatch.setattr(socket, "socket", guarded_socket)


class _Gateway:
    def __init__(
        self,
        factor_data: object | None = None,
        returns_data: object | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.factor_data = factor_data or _FakeFactorData()
        self.returns_data = returns_data
        self.exc = exc
        self.calls: list[tuple[str, dict[str, object]]] = []

    def load_factor_data(
        self,
        feature_ref: str,
        snapshot_range: dict[str, object],
    ) -> object:
        self.calls.append((feature_ref, snapshot_range))
        if self.exc is not None:
            raise self.exc
        return self.factor_data

    def load_returns_data(
        self,
        feature_ref: str,
        snapshot_range: dict[str, object],
    ) -> object | None:
        self.calls.append((feature_ref, snapshot_range))
        if self.exc is not None:
            raise self.exc
        return self.returns_data


class _FakeFactorData:
    empty = False
    columns = ("factor", "factor_quantile", "1D")

    def __getitem__(self, key: str) -> "_FakeQuantile":
        if key != "factor_quantile":
            raise KeyError(key)
        return _FakeQuantile()


class _FakeQuantile:
    def dropna(self) -> "_FakeQuantile":
        return self

    def unique(self) -> list[int]:
        return [1, 2]


class _FakeIC:
    def mean(self) -> "_FakeMapping":
        return _FakeMapping({"1D": 0.12})


class _FakeFrame:
    def __init__(self, payload: dict[object, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[object, object]:
        return self.payload


class _FakeMapping:
    def __init__(self, payload: dict[object, object]) -> None:
        self.payload = payload

    def items(self) -> object:
        return self.payload.items()


class _FakeSeries:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def dropna(self) -> "_FakeSeries":
        return self

    def mean(self) -> float:
        return sum(self.values) / len(self.values)


class _ObjectMetric:
    pass


class _FakePerformance:
    @staticmethod
    def factor_information_coefficient(_factor_data: object) -> _FakeIC:
        return _FakeIC()

    @staticmethod
    def mean_return_by_quantile(_factor_data: object) -> tuple[_FakeFrame, None]:
        return (
            _FakeFrame({1: {"1D": 0.01}, 2: {"1D": 0.03}}),
            None,
        )

    @staticmethod
    def factor_rank_autocorrelation(
        _factor_data: object,
        *,
        period: int,
    ) -> _FakeSeries:
        assert period == 1
        return _FakeSeries([0.5, 0.7])

    @staticmethod
    def quantile_turnover(
        _factor_quantile: object,
        *,
        quantile: int,
        period: int,
    ) -> _FakeSeries:
        assert period == 1
        return _FakeSeries([0.1 * quantile, 0.2 * quantile])


def _patch_alphalens(
    monkeypatch: pytest.MonkeyPatch,
    performance: object,
) -> None:
    def fake_import_module(name: str) -> object:
        if name == "alphalens.performance":
            return performance
        return importlib.import_module(name)

    monkeypatch.setattr("audit_eval.backtest.alphalens_adapter.importlib.import_module", fake_import_module)


def _snapshot_range() -> dict[str, object]:
    return {
        "manifest_cycle_id": "cycle_20260418",
        "manifest_snapshot_refs": ["snapshot://features/20260418"],
    }


def test_adapter_module_import_is_lazy() -> None:
    module = importlib.import_module("audit_eval.backtest.alphalens_adapter")

    assert module.AlphalensAdapter is AlphalensAdapter


def test_alphalens_adapter_reports_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_import(name: str) -> object:
        if name == "alphalens.performance":
            raise ImportError("missing")
        return importlib.import_module(name)

    monkeypatch.setattr(
        "audit_eval.backtest.alphalens_adapter.importlib.import_module",
        missing_import,
    )
    gateway = _Gateway()

    with pytest.raises(BacktestRunnerError, match="Alphalens is not installed"):
        AlphalensAdapter(gateway).run("feature://momentum/v1", _snapshot_range())

    assert gateway.calls == []


def test_alphalens_adapter_wraps_gateway_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_alphalens(monkeypatch, _FakePerformance)
    gateway = _Gateway(exc=KeyError("missing factor data"))

    with pytest.raises(BacktestRunnerError, match="input data"):
        AlphalensAdapter(gateway).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_wraps_execution_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingPerformance(_FakePerformance):
        @staticmethod
        def factor_information_coefficient(_factor_data: object) -> _FakeIC:
            raise RuntimeError("alphalens failed")

    _patch_alphalens(monkeypatch, _ExplodingPerformance)

    with pytest.raises(BacktestRunnerError, match="computation failed"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_returns_json_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_alphalens(monkeypatch, _FakePerformance)

    metrics = AlphalensAdapter(_Gateway()).run(
        "feature://momentum/v1",
        _snapshot_range(),
    )

    assert metrics == {
        "ic": {"mean": {"1D": 0.12}},
        "quantile_returns": {
            "1": {"1D": 0.01},
            "2": {"1D": 0.03},
        },
        "decay": {
            "rank_autocorrelation_mean": 0.6,
            "turnover": {"1": 0.15000000000000002, "2": 0.30000000000000004},
        },
    }


def test_alphalens_adapter_threads_metrics_config_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    periods: list[int] = []

    class _ConfigurablePerformance(_FakePerformance):
        @staticmethod
        def factor_rank_autocorrelation(
            _factor_data: object,
            *,
            period: int,
        ) -> _FakeSeries:
            periods.append(period)
            return _FakeSeries([0.2, 0.4])

        @staticmethod
        def quantile_turnover(
            _factor_quantile: object,
            *,
            quantile: int,
            period: int,
        ) -> _FakeSeries:
            periods.append(period)
            return _FakeSeries([0.1 * quantile])

    _patch_alphalens(monkeypatch, _ConfigurablePerformance)

    metrics = AlphalensAdapter(_Gateway()).run(
        "feature://momentum/v1",
        _snapshot_range(),
        {"period": 5},
    )

    assert periods == [5, 5, 5]
    assert metrics["decay"]["rank_autocorrelation_mean"] == 0.30000000000000004


def test_alphalens_adapter_rejects_invalid_metrics_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_alphalens(monkeypatch, _FakePerformance)

    with pytest.raises(BacktestRunnerError, match="metrics_config.period"):
        AlphalensAdapter(_Gateway()).run(
            "feature://momentum/v1",
            _snapshot_range(),
            {"period": 0},
        )


def test_alphalens_adapter_rejects_object_valued_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ObjectMetricPerformance(_FakePerformance):
        @staticmethod
        def mean_return_by_quantile(_factor_data: object) -> tuple[_FakeFrame, None]:
            return _FakeFrame({1: {"1D": _ObjectMetric()}}), None

    _patch_alphalens(monkeypatch, _ObjectMetricPerformance)

    with pytest.raises(BacktestRunnerError, match="JSON convertible"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_failed_numeric_reduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadMeanSeries:
        def dropna(self) -> "_BadMeanSeries":
            return self

        def mean(self) -> object:
            raise RuntimeError("cannot reduce")

    class _BadReductionPerformance(_FakePerformance):
        @staticmethod
        def factor_rank_autocorrelation(  # type: ignore[override]
            _factor_data: object,
            *,
            period: int,
        ) -> _BadMeanSeries:
            assert period == 1
            return _BadMeanSeries()

    _patch_alphalens(monkeypatch, _BadReductionPerformance)

    with pytest.raises(BacktestRunnerError, match="numeric metric reduction"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_object_valued_turnover_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ObjectTurnoverPerformance(_FakePerformance):
        @staticmethod
        def quantile_turnover(  # type: ignore[override]
            _factor_quantile: object,
            *,
            quantile: int,
            period: int,
        ) -> object:
            assert period == 1
            return _ObjectMetric()

    _patch_alphalens(monkeypatch, _ObjectTurnoverPerformance)

    with pytest.raises(BacktestRunnerError, match="must be numeric"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_turnover_reduction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadMeanSeries:
        def dropna(self) -> "_BadMeanSeries":
            return self

        def mean(self) -> object:
            raise RuntimeError("cannot reduce")

    class _BadTurnoverPerformance(_FakePerformance):
        @staticmethod
        def quantile_turnover(  # type: ignore[override]
            _factor_quantile: object,
            *,
            quantile: int,
            period: int,
        ) -> _BadMeanSeries:
            assert period == 1
            return _BadMeanSeries()

    _patch_alphalens(monkeypatch, _BadTurnoverPerformance)

    with pytest.raises(BacktestRunnerError, match="numeric metric reduction"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_turnover_adapter_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingTurnoverPerformance(_FakePerformance):
        @staticmethod
        def quantile_turnover(
            _factor_quantile: object,
            *,
            quantile: int,
            period: int,
        ) -> _FakeSeries:
            assert period == 1
            raise RuntimeError(f"turnover failed for quantile {quantile}")

    _patch_alphalens(monkeypatch, _ExplodingTurnoverPerformance)

    with pytest.raises(BacktestRunnerError, match="quantile turnover"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_forbidden_metric_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ForbiddenPerformance(_FakePerformance):
        @staticmethod
        def mean_return_by_quantile(_factor_data: object) -> tuple[_FakeFrame, None]:
            return _FakeFrame({1: {"feature_weight_multiplier": 1.2}}), None

    _patch_alphalens(monkeypatch, _ForbiddenPerformance)

    with pytest.raises(BacktestRunnerError, match="forbidden"):
        AlphalensAdapter(_Gateway()).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_rejects_malformed_factor_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_alphalens(monkeypatch, _FakePerformance)

    with pytest.raises(BacktestRunnerError, match="required column"):
        AlphalensAdapter(_Gateway(factor_data=types.SimpleNamespace(
            empty=False,
            columns=("factor", "1D"),
        ))).run("feature://momentum/v1", _snapshot_range())


def test_alphalens_adapter_smoke_with_installed_dependency() -> None:
    if os.environ.get("AUDIT_EVAL_REQUIRE_ALPHALENS_SMOKE") == "1":
        importlib.import_module("alphalens")
        pd = importlib.import_module("pandas")
    else:
        pytest.importorskip("alphalens")
        pd = pytest.importorskip("pandas")

    dates = pd.to_datetime(["2026-04-15", "2026-04-16", "2026-04-17"])
    assets = ["A", "B", "C"]
    index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    factor_data = pd.DataFrame(
        {
            "factor": [1, 2, 3, 2, 3, 4, 3, 4, 5],
            "factor_quantile": [1, 2, 3, 1, 2, 3, 1, 2, 3],
            "1D": [0.01, 0.03, 0.04, 0.02, 0.02, 0.05, 0.01, 0.04, 0.06],
        },
        index=index,
    )

    class _PandasGateway:
        def load_factor_data(
            self,
            feature_ref: str,
            snapshot_range: dict[str, object],
        ) -> object:
            assert feature_ref == "feature://momentum/v1"
            assert snapshot_range == _snapshot_range()
            return factor_data

        def load_returns_data(
            self,
            feature_ref: str,
            snapshot_range: dict[str, object],
        ) -> object | None:
            assert feature_ref == "feature://momentum/v1"
            assert snapshot_range == _snapshot_range()
            return None

    metrics = AlphalensAdapter(_PandasGateway()).run(
        "feature://momentum/v1",
        _snapshot_range(),
    )

    assert set(metrics) == {"ic", "quantile_returns", "decay"}
    assert metrics["ic"]
    assert metrics["quantile_returns"]
    assert metrics["decay"]
