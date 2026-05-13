"""Analytical storage boundaries for backtest results."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Protocol

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.backtest.errors import BacktestStorageError
from audit_eval.contracts.backtest_result import BacktestResult


class BacktestResultStorage(Protocol):
    """Analytical storage boundary for validated backtest results."""

    def append_backtest_result(self, result: BacktestResult) -> str:
        """Append one validated backtest result and return its backtest_id."""


class InMemoryBacktestResultStorage:
    """In-memory analytical backtest storage for tests and Lite workflows."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.append_calls = 0
        self._lock = Lock()

    def append_backtest_result(self, result: BacktestResult) -> str:
        row = result.model_dump(mode="json")
        assert_no_forbidden_write(row, path="$.backtest_result")
        with self._lock:
            self.append_calls += 1
            self.rows.append(deepcopy(row))
        return result.backtest_id


def get_default_backtest_result_storage() -> BacktestResultStorage:
    """Return configured backtest analytical storage, or fail closed."""

    raise BacktestStorageError(
        "No default backtest result storage is configured; pass storage=..."
    )


__all__ = [
    "BacktestResultStorage",
    "InMemoryBacktestResultStorage",
    "get_default_backtest_result_storage",
]
