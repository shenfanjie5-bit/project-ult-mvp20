from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.base import DataSourceAdapter  # noqa: E402
from data_platform.adapters.tushare import (  # noqa: E402
    FINANCIAL_DATASET_FIELDS,
    FINANCIAL_VERSION_FIELDS,
    TUSHARE_ASSETS,
    TUSHARE_BALANCESHEET_ASSET,
    TUSHARE_CASHFLOW_ASSET,
    TUSHARE_FINA_INDICATOR_ASSET,
    TUSHARE_INCOME_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402


HIGH_PRECISION_VENDOR_VALUE = "12345678901234567890.123456789012345678"
FINANCIAL_ASSETS = [
    TUSHARE_INCOME_ASSET,
    TUSHARE_BALANCESHEET_ASSET,
    TUSHARE_CASHFLOW_ASSET,
    TUSHARE_FINA_INDICATOR_ASSET,
]
METHOD_BY_DATASET = {
    "income": "income",
    "balancesheet": "balancesheet",
    "cashflow": "cashflow",
    "fina_indicator": "fina_indicator",
}
FETCH_PARAMS = {
    "ts_code": "000001.SZ",
    "ann_date": "20260415",
    "start_date": "20260401",
    "end_date": "20260430",
    "period": "20260331",
    "fields": "bad",
}


class FakeTushareFinancialClient:
    def __init__(self, frames_by_method: dict[str, Any]) -> None:
        self.frames_by_method = frames_by_method
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def income(self, **kwargs: Any) -> Any:
        return self._record_call("income", kwargs)

    def balancesheet(self, **kwargs: Any) -> Any:
        return self._record_call("balancesheet", kwargs)

    def cashflow(self, **kwargs: Any) -> Any:
        return self._record_call("cashflow", kwargs)

    def fina_indicator(self, **kwargs: Any) -> Any:
        return self._record_call("fina_indicator", kwargs)

    def _record_call(self, method_name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method_name, kwargs))
        return self.frames_by_method[method_name]


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _financial_row(
    asset: Any,
    index: int = 0,
    *,
    ann_date: str = "20260415",
    end_date: str = "20260331",
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in asset.schema:
        if field.name == "ts_code":
            row[field.name] = f"{index:06d}.SZ"
        elif field.name == "ann_date":
            row[field.name] = ann_date
        elif field.name == "f_ann_date":
            row[field.name] = "20260416"
        elif field.name == "end_date":
            row[field.name] = end_date
        elif field.name == "report_type":
            row[field.name] = "1"
        elif field.name == "comp_type":
            row[field.name] = "1"
        elif field.name == "update_flag":
            row[field.name] = str(index)
        else:
            row[field.name] = f"{index + 1}.123456789012345678"
    return row


def _financial_frame(
    asset: Any,
    row_count: int,
    *,
    ann_date: str = "20260415",
    end_date: str = "20260331",
) -> Any:
    if row_count == 0:
        return pd.DataFrame(columns=asset.schema.names)

    frame = pd.DataFrame(
        [
            _financial_row(asset, index=index, ann_date=ann_date, end_date=end_date)
            for index in range(row_count)
        ]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _client_for_asset(asset: Any, frame: Any) -> FakeTushareFinancialClient:
    method_name = METHOD_BY_DATASET[asset.dataset]
    return FakeTushareFinancialClient({method_name: frame})


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareFinancialClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareFinancialClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


def _fields_csv(asset: Any) -> str:
    return ",".join(asset.schema.names)


def test_financial_assets_and_staging_models_are_registered() -> None:
    client = _client_for_asset(TUSHARE_INCOME_ASSET, _financial_frame(TUSHARE_INCOME_ASSET, 1))
    adapter = TushareAdapter(token="test-token", client=client)
    assets_by_name = {asset.name: asset for asset in adapter.get_assets()}

    assert isinstance(adapter, DataSourceAdapter)
    assert FINANCIAL_VERSION_FIELDS == (
        "ts_code",
        "ann_date",
        "f_ann_date",
        "end_date",
        "report_type",
        "comp_type",
        "update_flag",
    )
    assert FINANCIAL_DATASET_FIELDS == {
        asset.dataset: tuple(asset.schema.names) for asset in FINANCIAL_ASSETS
    }
    for asset in FINANCIAL_ASSETS:
        assert assets_by_name[asset.name] == asset
        assert asset.partition == "daily"
        assert f"stg_{asset.dataset}" in adapter.get_staging_dbt_models()
        for field in asset.schema:
            if field.name not in FINANCIAL_VERSION_FIELDS:
                assert pa.types.is_decimal(field.type)
    assert {asset.name for asset in adapter.get_assets()} == {asset.name for asset in TUSHARE_ASSETS}
    assert type(adapter.get_quota_config()) is dict


@pytest.mark.parametrize("asset", FINANCIAL_ASSETS, ids=lambda asset: asset.name)
def test_fetch_financial_asset_returns_declared_schema(asset: Any) -> None:
    client = _client_for_asset(asset, _financial_frame(asset, 2))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(asset.name, FETCH_PARAMS)

    expected_params = {**FETCH_PARAMS, "fields": _fields_csv(asset)}
    assert isinstance(table, pa.Table)
    assert table.schema == asset.schema
    assert table.num_rows == 2
    assert table.column_names == asset.schema.names
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], expected_params)]


def test_financial_versions_are_not_deduplicated() -> None:
    rows = [
        _financial_row(TUSHARE_INCOME_ASSET, ann_date="20260415"),
        _financial_row(TUSHARE_INCOME_ASSET, ann_date="20260420"),
    ]
    rows[0]["update_flag"] = "0"
    rows[1]["update_flag"] = "1"
    client = _client_for_asset(TUSHARE_INCOME_ASSET, pd.DataFrame(rows))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_INCOME_ASSET.name, {"period": "20260331"})

    assert table.num_rows == 2
    assert table["ts_code"].to_pylist() == ["000000.SZ", "000000.SZ"]
    assert table["end_date"].to_pylist() == ["20260331", "20260331"]
    assert table["ann_date"].to_pylist() == ["20260415", "20260420"]
    assert table["update_flag"].to_pylist() == ["0", "1"]


def test_financial_dates_are_trimmed_and_numeric_nulls_are_preserved() -> None:
    row = _financial_row(TUSHARE_CASHFLOW_ASSET)
    row["ann_date"] = " 20260415 "
    row["f_ann_date"] = " 20260416 "
    row["end_date"] = " 20260331 "
    row["net_profit"] = None
    client = _client_for_asset(TUSHARE_CASHFLOW_ASSET, pd.DataFrame([row]))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_CASHFLOW_ASSET.name, {"period": "20260331"})

    assert table["ann_date"].to_pylist() == ["20260415"]
    assert table["f_ann_date"].to_pylist() == ["20260416"]
    assert table["end_date"].to_pylist() == ["20260331"]
    assert table["net_profit"].to_pylist() == [None]


@pytest.mark.parametrize("asset", FINANCIAL_ASSETS, ids=lambda asset: asset.name)
def test_financial_empty_response_returns_declared_empty_table(asset: Any) -> None:
    client = _client_for_asset(asset, _financial_frame(asset, 0))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(asset.name, {"period": "20260331"})

    assert table.schema == asset.schema
    assert table.num_rows == 0


@pytest.mark.parametrize("asset", FINANCIAL_ASSETS, ids=lambda asset: asset.name)
def test_cli_writes_financial_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
) -> None:
    client = _client_for_asset(
        asset,
        _financial_frame(asset, 3, ann_date="20260430", end_date="20260415"),
    )
    tokens = _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text(encoding="utf-8"))
    artifact_entry = manifest["artifacts"][0]
    table = pq.read_table(artifact_path).select(asset.schema.names)
    run_id = artifact_entry["run_id"]

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / asset.dataset / "dt=20260415"
    assert artifact_path.suffix == ".parquet"
    assert table.schema == asset.schema
    assert table.num_rows == 3
    assert artifact_entry["dataset"] == asset.dataset
    assert artifact_entry["row_count"] == 3
    assert artifact_path.stem == run_id
    assert uuid.UUID(run_id).version == 4
    assert client.calls == [
        (
            METHOD_BY_DATASET[asset.dataset],
            {"period": "20260415", "fields": _fields_csv(asset)},
        )
    ]


def test_cli_preserves_high_precision_financial_numeric_value(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    row = _financial_row(TUSHARE_INCOME_ASSET, end_date="20260415")
    row["total_revenue"] = HIGH_PRECISION_VENDOR_VALUE
    client = _client_for_asset(TUSHARE_INCOME_ASSET, pd.DataFrame([row]))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_INCOME_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    table = pq.read_table(artifact_path).select(TUSHARE_INCOME_ASSET.schema.names)

    assert exit_code == 0
    assert captured.err == ""
    assert artifact_path.parent == raw_zone_path / "tushare" / "income" / "dt=20260415"
    assert table.schema.field("total_revenue").type == pa.decimal128(38, 18)
    assert table["total_revenue"].to_pylist() == [Decimal(HIGH_PRECISION_VENDOR_VALUE)]


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_error"),
    [
        ("report_type", None, "null identity field: report_type"),
        ("comp_type", "   ", "blank identity field: comp_type"),
        ("update_flag", None, "null identity field: update_flag"),
    ],
)
def test_cli_rejects_invalid_financial_version_fields_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field_name: str,
    field_value: Any,
    expected_error: str,
) -> None:
    row = _financial_row(TUSHARE_INCOME_ASSET, end_date="20260415")
    row[field_name] = field_value
    client = _client_for_asset(TUSHARE_INCOME_ASSET, pd.DataFrame([row]))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_INCOME_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_INCOME_ASSET.name
    assert payload["error_type"] == "upstream_data_quality"
    assert expected_error in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_reports_invalid_financial_numeric_as_data_quality_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    row = _financial_row(TUSHARE_INCOME_ASSET, end_date="20260415")
    row["total_revenue"] = "not-a-decimal"
    client = _client_for_asset(TUSHARE_INCOME_ASSET, pd.DataFrame([row]))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_INCOME_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_INCOME_ASSET.name
    assert payload["error_type"] == "upstream_data_quality"
    assert "invalid numeric field: total_revenue" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


@pytest.mark.parametrize("missing_field", ["ts_code", "ann_date", "end_date"])
def test_cli_rejects_missing_financial_key_field_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing_field: str,
) -> None:
    frame = _financial_frame(TUSHARE_INCOME_ASSET, 1, end_date="20260415").drop(
        columns=[missing_field]
    )
    client = _client_for_asset(TUSHARE_INCOME_ASSET, frame)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_INCOME_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_INCOME_ASSET.name
    assert payload["error_type"] == "upstream_missing_columns"
    assert "missing required fields" in payload["error"]
    assert missing_field in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_run_tushare_asset_rejects_financial_report_period_mismatch_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_for_asset(
        TUSHARE_INCOME_ASSET,
        _financial_frame(TUSHARE_INCOME_ASSET, 1, end_date="20260331"),
    )
    _install_tushare_client(monkeypatch, client)

    with pytest.raises(ValueError, match="does not match Raw partition date"):
        tushare_adapter_module.run_tushare_asset(
            TUSHARE_INCOME_ASSET.name,
            date(2026, 4, 15),
        )

    assert client.calls == [
        ("income", {"period": "20260415", "fields": _fields_csv(TUSHARE_INCOME_ASSET)})
    ]
    assert list(raw_zone_path.rglob("*.parquet")) == []
