from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import pytest

from data_platform.adapters import base
from data_platform.adapters.base import (
    AdapterAlreadyRegistered,
    AdapterFetchError,
    AdapterQuotaExceeded,
    AdapterRegistry,
    AssetSpec,
    BaseAdapter,
    DataSourceAdapter,
    FetchableAdapter,
    FetchParams,
    FetchResult,
    QuotaConfig,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.sleep_calls.append(seconds)
        self.now += seconds


class ExampleAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        source: str = "example",
        quota: dict[str, Any] | None = None,
        side_effects: list[FetchResult | BaseException] | None = None,
        clock: FakeClock | None = None,
        max_retries: int = 3,
    ) -> None:
        self._source = source
        self._quota = quota or {"requests_per_minute": 60_000, "daily_credit_quota": None}
        self._side_effects = side_effects or [[{"id": 1}]]
        self.fetch_calls: list[tuple[str, FetchParams]] = []
        self.completed: list[tuple[str, int, float]] = []
        super().__init__(
            max_retries=max_retries,
            clock=clock.monotonic if clock else None,
            sleep=clock.sleep if clock else None,
        )

    def source_id(self) -> str:
        return self._source

    def get_assets(self) -> list[AssetSpec]:
        return []

    def get_resources(self) -> dict[str, Any]:
        return {}

    def get_staging_dbt_models(self) -> list[str]:
        return []

    def get_quota_config(self) -> dict[str, Any]:
        return dict(self._quota)

    def on_fetch_complete(self, asset_id: str, row_count: int, duration_s: float) -> None:
        self.completed.append((asset_id, row_count, duration_s))

    def _fetch(self, asset_id: str, params: Mapping[str, Any]) -> FetchResult:
        self.fetch_calls.append((asset_id, params))
        effect = self._side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def test_data_source_adapter_requires_all_methods() -> None:
    assert DataSourceAdapter.__abstractmethods__ == frozenset(
        {
            "get_assets",
            "get_resources",
            "get_staging_dbt_models",
            "get_quota_config",
        }
    )

    class MissingMethods(DataSourceAdapter):
        pass

    with pytest.raises(TypeError):
        MissingMethods()


def test_fetchable_adapter_adds_runtime_fetch_methods() -> None:
    assert FetchableAdapter.__abstractmethods__ == frozenset(
        {
            "get_assets",
            "get_resources",
            "get_staging_dbt_models",
            "get_quota_config",
            "source_id",
            "fetch",
        }
    )


def test_asset_spec_and_quota_config_validate() -> None:
    string_type = base.pa.string() if hasattr(base.pa, "string") else "string"
    schema = base.pa.schema([("asset_id", string_type)])

    asset = AssetSpec(
        name="stock_basic",
        dataset="canonical",
        partition="static",
        schema=schema,
    )

    assert asset.name == "stock_basic"
    assert asset.partition == "static"

    with pytest.raises(ValueError, match="requests_per_minute"):
        QuotaConfig(requests_per_minute=0, daily_credit_quota=None)

    with pytest.raises(ValueError, match="daily_credit_quota"):
        QuotaConfig(requests_per_minute=1, daily_credit_quota=-1)

    with pytest.raises(ValueError, match="backoff_seconds"):
        QuotaConfig(requests_per_minute=1, daily_credit_quota=None, backoff_seconds=-0.1)


def test_throttle_waits_sixty_seconds_for_sixty_requests_at_sixty_rpm() -> None:
    clock = FakeClock()
    adapter = ExampleAdapter(
        quota={"requests_per_minute": 60, "daily_credit_quota": None},
        clock=clock,
    )

    for _ in range(60):
        adapter._throttle()

    assert clock.now >= 60.0 * 0.95
    assert clock.now <= 60.0 * 1.05


def test_fetch_wraps_unhandled_errors() -> None:
    clock = FakeClock()
    cause = RuntimeError("upstream exploded")
    adapter = ExampleAdapter(source="source-a", side_effects=[cause], clock=clock)

    with pytest.raises(AdapterFetchError) as exc_info:
        adapter.fetch("asset-a", {"date": "2026-04-15"})

    assert exc_info.value.source_id == "source-a"
    assert exc_info.value.asset_id == "asset-a"
    assert exc_info.value.cause is cause


def test_fetch_retries_429_and_calls_completion_hook() -> None:
    class RateLimitError(Exception):
        status_code = 429

    clock = FakeClock()
    rows = [{"id": 1}, {"id": 2}]
    adapter = ExampleAdapter(
        quota={
            "requests_per_minute": 60_000,
            "daily_credit_quota": None,
            "backoff_seconds": 2.0,
        },
        side_effects=[RateLimitError("too many requests"), rows],
        clock=clock,
    )

    result = adapter.fetch("asset-a", {"page": 1})

    assert result == rows
    assert len(adapter.fetch_calls) == 2
    assert 2.0 in clock.sleep_calls
    assert adapter.completed[0][0] == "asset-a"
    assert adapter.completed[0][1] == 2
    assert adapter.completed[0][2] >= 2.0


def test_daily_quota_exceeded() -> None:
    clock = FakeClock()
    adapter = ExampleAdapter(
        quota={"requests_per_minute": 60_000, "daily_credit_quota": 1},
        side_effects=[[{"id": 1}], [{"id": 2}]],
        clock=clock,
    )

    assert adapter.fetch("asset-a", {}) == [{"id": 1}]

    with pytest.raises(AdapterQuotaExceeded):
        adapter.fetch("asset-a", {})


def test_daily_quota_resets_when_utc_day_changes() -> None:
    clock = FakeClock()
    adapter = ExampleAdapter(
        quota={"requests_per_minute": 60_000, "daily_credit_quota": 1},
        side_effects=[[{"id": 1}], [{"id": 2}]],
        clock=clock,
    )

    assert adapter.fetch("asset-a", {}) == [{"id": 1}]
    adapter._daily_credit_date = date.min

    assert adapter.fetch("asset-a", {}) == [{"id": 2}]


def test_adapter_registry_register_get_list_and_duplicate() -> None:
    registry = AdapterRegistry()
    adapter = ExampleAdapter(source="source-a")

    registry.register(adapter)

    assert registry.get("source-a") is adapter
    assert registry.list_sources() == ["source-a"]
    assert isinstance(base.REGISTRY, AdapterRegistry)

    with pytest.raises(AdapterAlreadyRegistered):
        registry.register(adapter)
