from pathlib import Path
from shutil import copyfile

import pytest
from pydantic import ValidationError

from data_platform.config import get_settings, reset_settings_cache


PROJECT_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.usefixtures("isolated_settings_cache")


def set_required_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DP_PG_DSN", "postgresql://user:pass@localhost/data_platform")
    monkeypatch.setenv("DP_DATA_STORAGE_ROOT_PATH", str(tmp_path / "data"))
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DP_PROCESSED_DATA_PATH", str(tmp_path / "processed"))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "duckdb" / "data_platform.duckdb"))


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DP_ICEBERG_CATALOG_NAME", "test_catalog")
    monkeypatch.setenv("DP_ENV", "test")

    settings = get_settings()

    assert str(settings.pg_dsn).startswith("postgresql://user:pass@localhost/")
    assert settings.data_storage_root_path == tmp_path / "data"
    assert settings.raw_zone_path == tmp_path / "raw"
    assert settings.processed_data_path == tmp_path / "processed"
    assert settings.iceberg_warehouse_path == tmp_path / "iceberg" / "warehouse"
    assert settings.duckdb_path == tmp_path / "duckdb" / "data_platform.duckdb"
    assert settings.iceberg_catalog_name == "test_catalog"
    assert settings.env == "test"


def test_settings_load_from_env_file_copy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    copyfile(PROJECT_ROOT / ".env.example", tmp_path / ".env")

    settings = get_settings()

    assert settings.data_storage_root_path == Path("data_platform/data")
    assert settings.raw_zone_path == Path("data_platform/data/raw")
    assert settings.processed_data_path == Path("data_platform/data/processed")
    assert settings.iceberg_warehouse_path == Path("data_platform/iceberg/warehouse")
    assert settings.duckdb_path == Path("data_platform/duckdb/data_platform.duckdb")
    assert settings.iceberg_catalog_name == "data_platform"
    assert settings.env == "dev"


def test_data_storage_root_derives_raw_and_processed_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    data_root = tmp_path / "downloaded-data"
    monkeypatch.setenv("DP_PG_DSN", "postgresql://user:pass@localhost/data_platform")
    monkeypatch.setenv("DP_DATA_STORAGE_ROOT_PATH", str(data_root))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "duckdb" / "data_platform.duckdb"))

    settings = get_settings()

    assert settings.data_storage_root_path == data_root
    assert settings.raw_zone_path == data_root / "raw"
    assert settings.processed_data_path == data_root / "processed"


def test_data_storage_directories_are_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    set_required_env(monkeypatch, tmp_path)

    settings = get_settings()
    settings.ensure_data_storage_directories()

    assert settings.data_storage_root_path.is_dir()
    assert settings.raw_zone_path.is_dir()
    assert settings.processed_data_path.is_dir()


def test_missing_pg_dsn_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DP_DATA_STORAGE_ROOT_PATH", str(tmp_path / "data"))
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "raw"))
    monkeypatch.setenv("DP_PROCESSED_DATA_PATH", str(tmp_path / "processed"))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    monkeypatch.setenv("DP_DUCKDB_PATH", str(tmp_path / "duckdb" / "data_platform.duckdb"))

    with pytest.raises(ValidationError) as error:
        get_settings()

    assert "pg_dsn" in str(error.value)


def test_get_settings_uses_lru_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    set_required_env(monkeypatch, tmp_path)

    first_settings = get_settings()
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(tmp_path / "new_raw"))

    assert get_settings() is first_settings

    reset_settings_cache()

    refreshed_settings = get_settings()
    assert refreshed_settings is not first_settings
    assert refreshed_settings.raw_zone_path == tmp_path / "new_raw"
