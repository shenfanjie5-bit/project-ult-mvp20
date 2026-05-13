"""Point-in-time backtest interfaces."""

from audit_eval.backtest.alphalens_adapter import (
    AlphalensAdapter,
    AlphalensInputGateway,
)
from audit_eval.backtest.errors import (
    BacktestInputError,
    BacktestRunnerError,
    BacktestStorageError,
    PITViolationError,
)
from audit_eval.backtest.job import BacktestJob
from audit_eval.backtest.pit_checker import (
    InMemoryPointInTimeFeatureGateway,
    InMemoryPointInTimeManifestGateway,
    PointInTimeChecker,
    PointInTimeFeatureGateway,
    PointInTimeManifestGateway,
    get_default_pit_feature_gateway,
)
from audit_eval.backtest.schema import (
    BacktestEngine,
    FeatureAvailability,
    PITCheckResult,
)
from audit_eval.backtest.runner import BacktestMetricsAdapter, run_backtest
from audit_eval.backtest.storage import (
    BacktestResultStorage,
    InMemoryBacktestResultStorage,
    get_default_backtest_result_storage,
)
from audit_eval.backtest.writer import persist_backtest_result

__all__ = [
    "AlphalensAdapter",
    "AlphalensInputGateway",
    "BacktestEngine",
    "BacktestInputError",
    "BacktestJob",
    "BacktestMetricsAdapter",
    "BacktestResultStorage",
    "BacktestRunnerError",
    "BacktestStorageError",
    "FeatureAvailability",
    "InMemoryBacktestResultStorage",
    "InMemoryPointInTimeFeatureGateway",
    "InMemoryPointInTimeManifestGateway",
    "PITCheckResult",
    "PITViolationError",
    "PointInTimeChecker",
    "PointInTimeFeatureGateway",
    "PointInTimeManifestGateway",
    "get_default_backtest_result_storage",
    "get_default_pit_feature_gateway",
    "persist_backtest_result",
    "run_backtest",
]
