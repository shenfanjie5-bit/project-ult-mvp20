"""Base abstractions for data source adapters."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
from threading import Lock
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    TypeAlias,
    cast,
)

import pyarrow as pa  # type: ignore[import-untyped]
from pyarrow import Schema, Table

FetchParams: TypeAlias = Mapping[str, Any]
FetchResult: TypeAlias = Table | list[dict[str, Any]]
PartitionType: TypeAlias = Literal["daily", "static"]
_ARROW_TABLE_TYPE: type[Any] = pa.Table


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """Data structure describing an adapter-provided asset."""

    name: str
    dataset: str
    partition: PartitionType
    schema: Schema
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True, slots=True)
class QuotaConfig:
    """Rate and credit quota configuration for an adapter."""

    requests_per_minute: int
    daily_credit_quota: int | None
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.requests_per_minute <= 0:
            msg = "requests_per_minute must be greater than zero"
            raise ValueError(msg)
        if self.daily_credit_quota is not None and self.daily_credit_quota < 0:
            msg = "daily_credit_quota must be non-negative or None"
            raise ValueError(msg)
        if self.backoff_seconds < 0:
            msg = "backoff_seconds must be non-negative"
            raise ValueError(msg)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> QuotaConfig:
        """Build the internal quota config from the external adapter contract dict."""

        return cls(
            requests_per_minute=int(value["requests_per_minute"]),
            daily_credit_quota=_optional_int(value.get("daily_credit_quota")),
            backoff_seconds=float(value.get("backoff_seconds", 1.0)),
        )


class AdapterQuotaExceeded(RuntimeError):
    """Raised when an adapter-level quota is exhausted."""


class AdapterAlreadyRegistered(RuntimeError):
    """Raised when registering another adapter for the same source."""


class AdapterFetchError(RuntimeError):
    """Raised when adapter fetch I/O fails."""

    def __init__(self, source_id: str, asset_id: str, cause: BaseException) -> None:
        self.source_id = source_id
        self.asset_id = asset_id
        self.cause = cause
        super().__init__(
            f"adapter fetch failed for source_id={source_id!r}, asset_id={asset_id!r}: {cause}"
        )


class DataSourceAdapter(ABC):
    """Contract implemented by data source adapters."""

    @abstractmethod
    def get_assets(self) -> list[AssetSpec]:
        """Return data assets exposed by this adapter."""

    @abstractmethod
    def get_resources(self) -> dict[str, Any]:
        """Return runtime resources required by this adapter."""

    @abstractmethod
    def get_staging_dbt_models(self) -> list[str]:
        """Return staging dbt model names required for this adapter."""

    @abstractmethod
    def get_quota_config(self) -> dict[str, Any]:
        """Return quota configuration for this adapter."""


class FetchableAdapter(DataSourceAdapter):
    """Runtime adapter layer with source identity and fetch behavior."""

    @abstractmethod
    def source_id(self) -> str:
        """Return the unique source identifier for this adapter."""

    @abstractmethod
    def fetch(self, asset_id: str, params: FetchParams) -> FetchResult:
        """Fetch one asset from the source."""


class BaseAdapter(FetchableAdapter):
    """Base adapter with shared throttling, retry, and fetch error handling."""

    def __init__(
        self,
        *,
        max_retries: int = 3,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if max_retries < 0:
            msg = "max_retries must be non-negative"
            raise ValueError(msg)
        self._max_retries = max_retries
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._quota_lock = Lock()
        self._daily_credit_lock = Lock()
        self._tokens = 0.0
        self._last_token_refill = self._clock()
        self._daily_credits_used = 0
        self._daily_credit_date = self._utc_today()

    def fetch(self, asset_id: str, params: FetchParams) -> FetchResult:
        """Fetch with quota throttling, retry-on-429, and error wrapping."""

        self._reserve_daily_credit()
        start = self._clock()
        attempt = 0
        while True:
            self._throttle()
            try:
                result = self._fetch(asset_id, params)
            except Exception as exc:
                if self._is_rate_limit_error(exc) and attempt < self._max_retries:
                    attempt += 1
                    self._sleep(self._runtime_quota_config().backoff_seconds)
                    continue
                raise AdapterFetchError(self.source_id(), asset_id, exc) from exc

            duration_s = self._clock() - start
            self.on_fetch_complete(asset_id, self._row_count(result), duration_s)
            return result

    def _throttle(self) -> None:
        """Block until this adapter has a request token available."""

        quota = self._runtime_quota_config()
        seconds_per_token = 60.0 / quota.requests_per_minute
        while True:
            with self._quota_lock:
                now = self._clock()
                elapsed = max(0.0, now - self._last_token_refill)
                self._tokens = min(1.0, self._tokens + (elapsed / seconds_per_token))
                self._last_token_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                wait_seconds = (1.0 - self._tokens) * seconds_per_token

            self._sleep(wait_seconds)

    def on_fetch_complete(self, asset_id: str, row_count: int, duration_s: float) -> None:
        """Hook called after successful fetch completion."""

    @abstractmethod
    def _fetch(self, asset_id: str, params: FetchParams) -> FetchResult:
        """Fetch one asset without shared BaseAdapter error handling."""

    def _reserve_daily_credit(self) -> None:
        quota = self._runtime_quota_config()
        if quota.daily_credit_quota is None:
            return

        with self._daily_credit_lock:
            today = self._utc_today()
            if today != self._daily_credit_date:
                self._daily_credits_used = 0
                self._daily_credit_date = today

            if self._daily_credits_used >= quota.daily_credit_quota:
                msg = f"daily credit quota exceeded for source_id={self.source_id()!r}"
                raise AdapterQuotaExceeded(msg)
            self._daily_credits_used += 1

    def _runtime_quota_config(self) -> QuotaConfig:
        return QuotaConfig.from_mapping(self.get_quota_config())

    @staticmethod
    def _utc_today() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def _row_count(result: FetchResult) -> int:
        if isinstance(result, _ARROW_TABLE_TYPE):
            return int(cast(Any, result).num_rows)
        return len(result)

    @staticmethod
    def _is_rate_limit_error(exc: BaseException) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True

        response = getattr(exc, "response", None)
        response_status_code = getattr(response, "status_code", None)
        if response_status_code == 429:
            return True

        code = getattr(exc, "code", None)
        return code == 429


class AdapterRegistry:
    """Thread-safe registry for source adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, FetchableAdapter] = {}
        self._lock = Lock()

    def register(self, adapter: FetchableAdapter) -> None:
        source_id = adapter.source_id()
        with self._lock:
            if source_id in self._adapters:
                msg = f"adapter already registered for source_id={source_id!r}"
                raise AdapterAlreadyRegistered(msg)
            self._adapters[source_id] = adapter

    def get(self, source_id: str) -> FetchableAdapter:
        with self._lock:
            return self._adapters[source_id]

    def list_sources(self) -> list[str]:
        with self._lock:
            return list(self._adapters)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def schema_hash(schema: Schema) -> str:
    """Return a stable hash for an Arrow schema contract."""

    fields = []
    for field in schema:
        fields.append(
            {
                "name": field.name,
                "type": str(field.type),
                "nullable": field.nullable,
                "metadata": _bytes_mapping(field.metadata),
            }
        )
    payload = {
        "fields": fields,
        "metadata": _bytes_mapping(schema.metadata),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _bytes_mapping(value: Mapping[bytes, bytes] | None) -> dict[str, str]:
    if not value:
        return {}
    return {
        key.decode("utf-8", errors="surrogateescape"): item.decode(
            "utf-8",
            errors="surrogateescape",
        )
        for key, item in sorted(value.items())
    }


REGISTRY = AdapterRegistry()
"""Process-global adapter registry for orchestrator assembly."""

__all__ = [
    "AdapterAlreadyRegistered",
    "AdapterFetchError",
    "AdapterQuotaExceeded",
    "AdapterRegistry",
    "AssetSpec",
    "BaseAdapter",
    "DataSourceAdapter",
    "FetchableAdapter",
    "FetchParams",
    "FetchResult",
    "PartitionType",
    "QuotaConfig",
    "REGISTRY",
    "schema_hash",
]
