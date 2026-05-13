from __future__ import annotations

from collections.abc import Generator

import pytest


DP_SETTINGS_ENV_KEYS = (
    "DP_PG_DSN",
    "DP_RAW_ZONE_PATH",
    "DP_ICEBERG_WAREHOUSE_PATH",
    "DP_DUCKDB_PATH",
    "DP_ICEBERG_CATALOG_NAME",
    "DP_ENV",
)


@pytest.fixture()
def isolated_settings_cache(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    from data_platform.config import reset_settings_cache

    reset_settings_cache()
    for key in DP_SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    reset_settings_cache()
