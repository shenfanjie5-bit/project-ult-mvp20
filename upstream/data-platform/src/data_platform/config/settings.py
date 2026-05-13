"""Runtime settings shared by data-platform components."""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DP_", env_file=".env", extra="ignore")

    pg_dsn: PostgresDsn
    data_storage_root_path: Path = Path("data_platform/data")
    raw_zone_path: Path
    processed_data_path: Path
    iceberg_warehouse_path: Path
    duckdb_path: Path
    iceberg_catalog_name: str = "data_platform"
    env: Literal["dev", "test", "prod"] = "dev"

    @model_validator(mode="before")
    @classmethod
    def _derive_data_storage_paths(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data

        values = dict(data)
        default_storage_root = cls.model_fields["data_storage_root_path"].default
        data_storage_root = Path(
            values.get("data_storage_root_path") or default_storage_root
        )
        values.setdefault("raw_zone_path", data_storage_root / "raw")
        values.setdefault("processed_data_path", data_storage_root / "processed")
        return values

    @model_validator(mode="after")
    def _expand_data_storage_paths(self) -> Self:
        self.data_storage_root_path = self.data_storage_root_path.expanduser()
        self.raw_zone_path = self.raw_zone_path.expanduser()
        self.processed_data_path = self.processed_data_path.expanduser()
        return self

    def ensure_data_storage_directories(self) -> None:
        """Create the configured data storage root and raw/processed subdirectories."""

        self.data_storage_root_path.mkdir(parents=True, exist_ok=True)
        self.raw_zone_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.model_validate({})


def reset_settings_cache() -> None:
    get_settings.cache_clear()
