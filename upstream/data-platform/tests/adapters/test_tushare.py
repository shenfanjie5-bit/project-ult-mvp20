from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.base import AdapterRegistry, DataSourceAdapter, schema_hash  # noqa: E402
from data_platform.adapters.tushare import (  # noqa: E402
    TUSHARE_ASSETS,
    TUSHARE_STOCK_BASIC_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402
from data_platform.adapters.tushare.assets import (  # noqa: E402
    TUSHARE_STOCK_BASIC_FIELDS,
    TUSHARE_STOCK_BASIC_FIELDS_CSV,
)


class FakeTushareClient:
    def __init__(self, frame: Any) -> None:
        self.frame = frame
        self.calls: list[dict[str, Any]] = []

    def stock_basic(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.frame


def _stock_basic_row(index: int) -> dict[str, Any]:
    row: dict[str, Any] = {field: f"{field}-{index}" for field in TUSHARE_STOCK_BASIC_FIELDS}
    row.update(
        {
            "ts_code": f"{index:06d}.SZ",
            "symbol": f"{index:06d}",
            "name": f"stock-{index}",
            "list_date": "20260415",
            "delist_date": None,
        }
    )
    return row


def _stock_basic_frame(row_count: int) -> Any:
    frame = pd.DataFrame([_stock_basic_row(index) for index in range(row_count)])
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def test_tushare_adapter_declares_stock_basic_asset_and_quota() -> None:
    adapter = TushareAdapter(token="test-token", client=FakeTushareClient(_stock_basic_frame(1)))

    assert adapter.source_id() == "tushare"
    assert adapter.get_assets() == TUSHARE_ASSETS
    assert adapter.get_assets()[0].dataset == "stock_basic"
    assert adapter.get_assets()[0].partition == "static"
    assert adapter.get_staging_dbt_models() == [
        f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS
    ]
    assert adapter.get_quota_config() == {
        "requests_per_minute": 200,
        "daily_credit_quota": None,
    }


def test_tushare_typed_assets_expose_registry_metadata() -> None:
    by_dataset = {asset.dataset: asset for asset in TUSHARE_ASSETS}

    stock_basic_metadata = by_dataset["stock_basic"].metadata
    assert stock_basic_metadata["provider"] == "tushare"
    assert stock_basic_metadata["source_interface_id"] == "stock_basic"
    assert stock_basic_metadata["doc_api"] == "stock_basic"
    assert stock_basic_metadata["partition_key"] == ()
    assert stock_basic_metadata["schema_hash"] == schema_hash(by_dataset["stock_basic"].schema)

    trade_cal_metadata = by_dataset["trade_cal"].metadata
    assert trade_cal_metadata["source_interface_id"] == "trade_cal_stock"
    assert trade_cal_metadata["doc_api"] == "trade_cal"
    assert trade_cal_metadata["partition_key"] == ("cal_date",)
    assert trade_cal_metadata["production_selectable"] is True


def test_tushare_adapter_matches_documented_datasource_protocol() -> None:
    adapter = TushareAdapter(token="test-token", client=FakeTushareClient(_stock_basic_frame(1)))

    assert isinstance(adapter, DataSourceAdapter)
    assert DataSourceAdapter.__abstractmethods__ == frozenset(
        {
            "get_assets",
            "get_resources",
            "get_staging_dbt_models",
            "get_quota_config",
        }
    )
    assert type(adapter.get_quota_config()) is dict


def test_fetch_stock_basic_returns_declared_schema() -> None:
    client = FakeTushareClient(_stock_basic_frame(2))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch("tushare_stock_basic", {"list_status": "L", "fields": "bad"})

    assert isinstance(table, pa.Table)
    assert table.schema == TUSHARE_STOCK_BASIC_ASSET.schema
    assert table.num_rows == 2
    assert client.calls == [
        {
            "list_status": "L",
            "fields": TUSHARE_STOCK_BASIC_FIELDS_CSV,
        }
    ]


def test_tushare_adapter_can_be_registered_and_fetched() -> None:
    registry = AdapterRegistry()
    adapter = TushareAdapter(token="test-token", client=FakeTushareClient(_stock_basic_frame(1)))

    registry.register(adapter)

    assert registry.get("tushare") is adapter


def test_cli_writes_stock_basic_parquet_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeTushareClient(_stock_basic_frame(5_000))
    tokens = _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / "stock_basic" / "dt=20260415"
    assert artifact_path.suffix == ".parquet"
    assert len(list(artifact_path.parent.glob("*.parquet"))) == 1
    assert pq.read_table(artifact_path).num_rows == 5_000
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert manifest["provider"] == "tushare"
    assert manifest["source_interface_id"] == "stock_basic"
    assert manifest["doc_api"] == "stock_basic"
    assert manifest["partition_key"] == []
    assert manifest["schema_hash"] == schema_hash(TUSHARE_STOCK_BASIC_ASSET.schema)
    assert isinstance(manifest["request_params_hash"], str)
    assert len(manifest["request_params_hash"]) == 64


def test_cli_rejects_missing_required_stock_basic_columns_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frame = _stock_basic_frame(1).drop(columns=["list_date"])
    _install_tushare_client(monkeypatch, FakeTushareClient(frame))

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert "missing required fields" in payload["error"]
    assert "list_date" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_rejects_malformed_stock_basic_rows_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_tushare_client(
        monkeypatch,
        FakeTushareClient([_stock_basic_row(0), ["not", "a", "mapping"]]),
    )

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert "row 1 must be a mapping" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_rejects_null_stock_basic_identity_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frame = _stock_basic_frame(1)
    frame.loc[0, "ts_code"] = None
    _install_tushare_client(monkeypatch, FakeTushareClient(frame))

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert "null identity field: ts_code" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_rejects_pandas_nat_stock_basic_identity_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frame = _stock_basic_frame(1)
    frame.loc[0, "ts_code"] = pd.NaT
    _install_tushare_client(monkeypatch, FakeTushareClient(frame))

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert "null identity field: ts_code" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


@pytest.mark.parametrize(
    ("identity_value", "expected_error"),
    [
        ("", "blank identity field: ts_code"),
        ("   ", "blank identity field: ts_code"),
        ("not-a-code", "malformed identity field: ts_code"),
        ("000001.SHX", "malformed identity field: ts_code"),
        (["000001.SZ"], "non-scalar identity field: ts_code"),
    ],
)
def test_cli_rejects_invalid_stock_basic_identity_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    identity_value: Any,
    expected_error: str,
) -> None:
    frame = _stock_basic_frame(1)
    frame.at[0, "ts_code"] = identity_value
    _install_tushare_client(monkeypatch, FakeTushareClient(frame))

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert expected_error in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_missing_token_outputs_json_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DP_TUSHARE_TOKEN", raising=False)

    exit_code = tushare_adapter_module.main(
        ["--asset", "tushare_stock_basic", "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == "tushare_stock_basic"
    assert "DP_TUSHARE_TOKEN" in payload["error"]
