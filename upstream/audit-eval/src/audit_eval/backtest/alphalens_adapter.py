"""Lazy Alphalens metrics adapter for offline backtests."""

from __future__ import annotations

import importlib
import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from numbers import Real
from typing import Any, Protocol

from audit_eval._boundary import BoundaryViolationError, assert_no_forbidden_write
from audit_eval.backtest.errors import BacktestRunnerError
from audit_eval.contracts.common import JsonObject

_RESERVED_FACTOR_COLUMNS = frozenset({"factor", "factor_quantile", "group"})


class AlphalensInputGateway(Protocol):
    """Input boundary for point-in-time Alphalens factor and return data."""

    def load_factor_data(self, feature_ref: str, snapshot_range: JsonObject) -> Any:
        """Load point-in-time factor observations for feature_ref."""

    def load_returns_data(self, feature_ref: str, snapshot_range: JsonObject) -> Any:
        """Load point-in-time forward returns for feature_ref."""


class AlphalensAdapter:
    """Compute signal quality metrics with Alphalens."""

    def __init__(self, gateway: AlphalensInputGateway | None = None) -> None:
        self.gateway = gateway

    def run(
        self,
        feature_ref: str,
        snapshot_range: JsonObject,
        metrics_config: JsonObject | None = None,
    ) -> JsonObject:
        """Return JSON metrics for one point-in-time factor snapshot range."""

        config = _normalize_metrics_config(metrics_config)
        performance = _load_alphalens_performance()
        factor_data = self._load_factor_data(feature_ref, snapshot_range)
        metrics = self._run_performance_metrics(performance, factor_data, config)
        try:
            assert_no_forbidden_write(metrics, path="$.backtest_metrics")
        except BoundaryViolationError as exc:
            raise BacktestRunnerError(
                "Alphalens metrics contain forbidden write fields"
            ) from exc
        _assert_json_object(metrics, path="$.backtest_metrics")
        return metrics

    def _load_factor_data(self, feature_ref: str, snapshot_range: JsonObject) -> Any:
        if self.gateway is None:
            raise BacktestRunnerError(
                "No Alphalens input gateway is configured; pass adapter=..."
            )
        try:
            factor_data = self.gateway.load_factor_data(
                feature_ref,
                deepcopy(snapshot_range),
            )
            returns_data = self.gateway.load_returns_data(
                feature_ref,
                deepcopy(snapshot_range),
            )
        except Exception as exc:
            raise BacktestRunnerError("Alphalens input data is unavailable") from exc

        factor_data = _combine_factor_and_returns(factor_data, returns_data)
        _validate_factor_data_shape(factor_data)
        return factor_data

    def _run_performance_metrics(
        self,
        performance: Any,
        factor_data: Any,
        metrics_config: JsonObject,
    ) -> JsonObject:
        period = _metrics_period(metrics_config)
        try:
            ic = performance.factor_information_coefficient(factor_data)
            mean_returns, _ = performance.mean_return_by_quantile(factor_data)
            autocorrelation = performance.factor_rank_autocorrelation(
                factor_data,
                period=period,
            )
            turnover = _compute_quantile_turnover(
                performance,
                factor_data,
                period=period,
            )
        except BacktestRunnerError:
            raise
        except Exception as exc:
            raise BacktestRunnerError("Alphalens metrics computation failed") from exc

        metrics: JsonObject = {
            "ic": _series_or_frame_summary(ic),
            "quantile_returns": _frame_to_nested_json(mean_returns),
            "decay": {
                "rank_autocorrelation_mean": _mean_numeric(autocorrelation),
                "turnover": turnover,
            },
        }
        return _json_clean(metrics)


def _load_alphalens_performance() -> Any:
    try:
        return importlib.import_module("alphalens.performance")
    except ImportError as exc:
        raise BacktestRunnerError(
            "Alphalens is not installed; install the backtest extra"
        ) from exc


def _combine_factor_and_returns(factor_data: Any, returns_data: Any) -> Any:
    if returns_data is None:
        return factor_data
    if not hasattr(factor_data, "join"):
        raise BacktestRunnerError("Alphalens factor data must support DataFrame joins")
    try:
        return factor_data.join(returns_data)
    except Exception as exc:
        raise BacktestRunnerError("Unable to join factor data with returns data") from exc


def _validate_factor_data_shape(factor_data: Any) -> None:
    if factor_data is None:
        raise BacktestRunnerError("Alphalens factor data is missing")
    if bool(getattr(factor_data, "empty", False)):
        raise BacktestRunnerError("Alphalens factor data must not be empty")

    columns = getattr(factor_data, "columns", None)
    if columns is None:
        raise BacktestRunnerError("Alphalens factor data must expose columns")
    column_names = {str(column) for column in columns}
    missing = {"factor", "factor_quantile"} - column_names
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise BacktestRunnerError(
            f"Alphalens factor data missing required column(s): {missing_names}"
        )
    forward_return_columns = column_names - _RESERVED_FACTOR_COLUMNS
    if not forward_return_columns:
        raise BacktestRunnerError(
            "Alphalens factor data must include forward return columns"
        )


def _normalize_metrics_config(metrics_config: JsonObject | None) -> JsonObject:
    if metrics_config is None:
        return {}
    if not isinstance(metrics_config, dict):
        raise BacktestRunnerError("metrics_config must be a JSON object")
    return deepcopy(metrics_config)


def _metrics_period(metrics_config: JsonObject) -> int:
    raw_period = metrics_config.get("period", 1)
    if isinstance(raw_period, bool) or not isinstance(raw_period, int):
        raise BacktestRunnerError("metrics_config.period must be a positive integer")
    if raw_period <= 0:
        raise BacktestRunnerError("metrics_config.period must be a positive integer")
    return raw_period


def _compute_quantile_turnover(
    performance: Any,
    factor_data: Any,
    *,
    period: int,
) -> JsonObject:
    quantiles = _unique_quantiles(factor_data)
    turnover: JsonObject = {}
    if not quantiles:
        return turnover

    factor_quantile = factor_data["factor_quantile"]
    for quantile in quantiles:
        try:
            quantile_turnover = performance.quantile_turnover(
                factor_quantile,
                quantile=quantile,
                period=period,
            )
        except Exception as exc:
            raise BacktestRunnerError(
                "Alphalens quantile turnover computation failed"
            ) from exc
        turnover[str(quantile)] = _mean_numeric(quantile_turnover)
    return turnover


def _unique_quantiles(factor_data: Any) -> list[int]:
    try:
        raw_values = factor_data["factor_quantile"].dropna().unique()
    except Exception:
        return []
    quantiles: list[int] = []
    for value in raw_values:
        try:
            quantiles.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(quantiles))


def _series_or_frame_summary(value: Any) -> JsonObject:
    if hasattr(value, "mean"):
        mean_value = value.mean()
        if _is_mapping_like(mean_value):
            return {"mean": _mapping_to_json(mean_value)}
        return {"mean": _json_scalar(mean_value)}
    return {"mean": _json_scalar(value)}


def _frame_to_nested_json(value: Any) -> JsonObject:
    if hasattr(value, "to_dict"):
        return _json_clean(value.to_dict())
    if _is_mapping_like(value):
        return _mapping_to_json(value)
    raise BacktestRunnerError("Alphalens metric output is not JSON convertible")


def _mapping_to_json(value: Any) -> JsonObject:
    if hasattr(value, "items"):
        return {
            str(key): _json_clean(nested_value)
            for key, nested_value in value.items()
        }
    raise BacktestRunnerError("Alphalens metric output is not a mapping")


def _mean_numeric(value: Any) -> float:
    if value is None:
        raise BacktestRunnerError("Alphalens numeric metric is missing")
    try:
        if hasattr(value, "dropna"):
            value = value.dropna()
        if hasattr(value, "mean"):
            value = value.mean()
        return _json_number(value)
    except BacktestRunnerError:
        raise
    except Exception as exc:
        raise BacktestRunnerError("Alphalens numeric metric reduction failed") from exc


def _json_number(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestRunnerError("Alphalens metric value must be numeric") from exc
    if math.isnan(numeric) or math.isinf(numeric):
        raise BacktestRunnerError("Alphalens metric value must be finite")
    return numeric


def _json_scalar(value: Any) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise BacktestRunnerError("Alphalens metric value must be finite")
        return value
    if isinstance(value, Real):
        return _json_number(value)
    raise BacktestRunnerError("Alphalens metric output is not JSON convertible")


def _json_clean(value: Any) -> Any:
    if _is_mapping_like(value):
        return {str(key): _json_clean(nested) for key, nested in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_clean(nested) for nested in value]
    return _json_scalar(value)


def _is_mapping_like(value: Any) -> bool:
    return isinstance(value, Mapping) or hasattr(value, "items")


def _assert_json_object(value: object, *, path: str) -> None:
    if not isinstance(value, dict):
        raise BacktestRunnerError(f"{path} must be a JSON object")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BacktestRunnerError(f"{path} must contain only JSON values") from exc


__all__ = [
    "AlphalensAdapter",
    "AlphalensInputGateway",
]
