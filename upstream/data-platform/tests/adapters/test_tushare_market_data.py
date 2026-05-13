from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.base import AdapterFetchError  # noqa: E402
from data_platform.adapters.tushare import (  # noqa: E402
    TUSHARE_ADJ_FACTOR_ASSET,
    TUSHARE_DAILY_ASSET,
    TUSHARE_DAILY_BASIC_ASSET,
    TUSHARE_MONEYFLOW_ASSET,
    TUSHARE_MONTHLY_ASSET,
    TUSHARE_STK_LIMIT_ASSET,
    TUSHARE_WEEKLY_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402
from data_platform.adapters.tushare.assets import (  # noqa: E402
    TUSHARE_ADJ_FACTOR_FIELDS_CSV,
    TUSHARE_BAR_FIELDS_CSV,
    TUSHARE_DAILY_BASIC_FIELDS_CSV,
    TUSHARE_MONEYFLOW_FIELDS_CSV,
    TUSHARE_STK_LIMIT_FIELDS_CSV,
)


HIGH_PRECISION_VENDOR_VALUE = "12345678901234567890.123456789012345678"
MARKET_ASSETS = [
    TUSHARE_DAILY_ASSET,
    TUSHARE_WEEKLY_ASSET,
    TUSHARE_MONTHLY_ASSET,
    TUSHARE_ADJ_FACTOR_ASSET,
    TUSHARE_DAILY_BASIC_ASSET,
    # Plan §5 expansion
    TUSHARE_STK_LIMIT_ASSET,
    TUSHARE_MONEYFLOW_ASSET,
]

METHOD_BY_ASSET_NAME = {
    TUSHARE_DAILY_ASSET.name: "daily",
    TUSHARE_WEEKLY_ASSET.name: "weekly",
    TUSHARE_MONTHLY_ASSET.name: "monthly",
    TUSHARE_ADJ_FACTOR_ASSET.name: "adj_factor",
    TUSHARE_DAILY_BASIC_ASSET.name: "daily_basic",
    # Plan §5 expansion
    TUSHARE_STK_LIMIT_ASSET.name: "stk_limit",
    TUSHARE_MONEYFLOW_ASSET.name: "moneyflow",
}

FIELDS_CSV_BY_ASSET_NAME = {
    TUSHARE_DAILY_ASSET.name: TUSHARE_BAR_FIELDS_CSV,
    TUSHARE_WEEKLY_ASSET.name: TUSHARE_BAR_FIELDS_CSV,
    TUSHARE_MONTHLY_ASSET.name: TUSHARE_BAR_FIELDS_CSV,
    TUSHARE_ADJ_FACTOR_ASSET.name: TUSHARE_ADJ_FACTOR_FIELDS_CSV,
    TUSHARE_DAILY_BASIC_ASSET.name: TUSHARE_DAILY_BASIC_FIELDS_CSV,
    # Plan §5 expansion
    TUSHARE_STK_LIMIT_ASSET.name: TUSHARE_STK_LIMIT_FIELDS_CSV,
    TUSHARE_MONEYFLOW_ASSET.name: TUSHARE_MONEYFLOW_FIELDS_CSV,
}


class FakeTushareMarketClient:
    def __init__(self, frames_by_method: dict[str, Any]) -> None:
        self.frames_by_method = frames_by_method
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def daily(self, **kwargs: Any) -> Any:
        return self._record_call("daily", kwargs)

    def weekly(self, **kwargs: Any) -> Any:
        return self._record_call("weekly", kwargs)

    def monthly(self, **kwargs: Any) -> Any:
        return self._record_call("monthly", kwargs)

    def adj_factor(self, **kwargs: Any) -> Any:
        return self._record_call("adj_factor", kwargs)

    def daily_basic(self, **kwargs: Any) -> Any:
        return self._record_call("daily_basic", kwargs)

    # Plan §5 expansion
    def stk_limit(self, **kwargs: Any) -> Any:
        return self._record_call("stk_limit", kwargs)

    def moneyflow(self, **kwargs: Any) -> Any:
        return self._record_call("moneyflow", kwargs)

    def _record_call(self, method_name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method_name, kwargs))
        return self.frames_by_method[method_name]


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _market_row(asset: Any, index: int = 0, trade_date: str = "20260415") -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in asset.schema:
        if field.name == "ts_code":
            row[field.name] = f"{index:06d}.SZ"
        elif field.name == "trade_date":
            row[field.name] = trade_date
        else:
            row[field.name] = f"{field.name}-{index}"
    return row


def _market_frame(asset: Any, row_count: int, trade_date: str = "20260415") -> Any:
    frame = pd.DataFrame(
        [_market_row(asset, index=index, trade_date=trade_date) for index in range(row_count)]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _client_for_asset(asset: Any, frame: Any) -> FakeTushareMarketClient:
    method_name = METHOD_BY_ASSET_NAME[asset.name]
    return FakeTushareMarketClient({method_name: frame})


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareMarketClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareMarketClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


@pytest.mark.parametrize("asset", MARKET_ASSETS, ids=lambda asset: asset.name)
def test_fetch_market_data_asset_returns_declared_schema(asset: Any) -> None:
    client = _client_for_asset(asset, _market_frame(asset, 2))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(asset.name, {"trade_date": "20260415", "fields": "bad"})

    assert isinstance(table, pa.Table)
    assert table.schema == asset.schema
    assert table.num_rows == 2
    assert client.calls == [
        (
            METHOD_BY_ASSET_NAME[asset.name],
            {
                "trade_date": "20260415",
                "fields": FIELDS_CSV_BY_ASSET_NAME[asset.name],
            },
        )
    ]


def test_cli_writes_daily_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _client_for_asset(TUSHARE_DAILY_ASSET, _market_frame(TUSHARE_DAILY_ASSET, 3))
    tokens = _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_DAILY_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    manifest_path = artifact_path.parent / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / "daily" / "dt=20260415"
    assert artifact_path.suffix == ".parquet"
    assert pq.read_table(artifact_path).num_rows == 3
    assert manifest["artifacts"][0]["path"] == str(artifact_path)
    assert manifest["artifacts"][0]["row_count"] == 3
    assert client.calls == [
        (
            "daily",
            {
                "trade_date": "20260415",
                "fields": TUSHARE_BAR_FIELDS_CSV,
            },
        )
    ]


def test_cli_preserves_high_precision_market_numeric_value(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    row = _market_row(TUSHARE_DAILY_ASSET)
    row["amount"] = HIGH_PRECISION_VENDOR_VALUE
    client = _client_for_asset(TUSHARE_DAILY_ASSET, pd.DataFrame([row]))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_DAILY_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    table = pq.read_table(artifact_path)

    assert exit_code == 0
    assert captured.err == ""
    assert artifact_path.parent == raw_zone_path / "tushare" / "daily" / "dt=20260415"
    assert table.schema.field("amount").type == pa.string()
    assert table["amount"].to_pylist() == [HIGH_PRECISION_VENDOR_VALUE]


def test_run_tushare_asset_rejects_param_trade_date_mismatch_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_for_asset(TUSHARE_DAILY_ASSET, _market_frame(TUSHARE_DAILY_ASSET, 1))
    _install_tushare_client(monkeypatch, client)

    with pytest.raises(ValueError, match="does not match Raw partition date"):
        tushare_adapter_module.run_tushare_asset(
            TUSHARE_DAILY_ASSET.name,
            date(2026, 4, 15),
            {"trade_date": "20260414"},
        )

    assert client.calls == []
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_run_tushare_asset_rejects_returned_trade_date_mismatch_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_for_asset(
        TUSHARE_DAILY_ASSET,
        _market_frame(TUSHARE_DAILY_ASSET, 1, trade_date="20260414"),
    )
    _install_tushare_client(monkeypatch, client)

    with pytest.raises(ValueError, match="does not match Raw partition date"):
        tushare_adapter_module.run_tushare_asset(
            TUSHARE_DAILY_ASSET.name,
            date(2026, 4, 15),
        )

    assert client.calls == [
        (
            "daily",
            {
                "trade_date": "20260415",
                "fields": TUSHARE_BAR_FIELDS_CSV,
            },
        )
    ]
    assert list(raw_zone_path.rglob("*.parquet")) == []


@pytest.mark.parametrize("missing_field", ["ts_code", "trade_date"])
def test_cli_rejects_market_data_missing_identity_field_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing_field: str,
) -> None:
    frame = _market_frame(TUSHARE_DAILY_ASSET, 1).drop(columns=[missing_field])
    client = _client_for_asset(TUSHARE_DAILY_ASSET, frame)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_DAILY_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_DAILY_ASSET.name
    assert "missing required fields" in payload["error"]
    assert missing_field in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_fetch_rejects_invalid_trade_date_without_calling_client() -> None:
    client = _client_for_asset(TUSHARE_DAILY_ASSET, _market_frame(TUSHARE_DAILY_ASSET, 1))
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(AdapterFetchError, match="valid YYYYMMDD date"):
        adapter.fetch(TUSHARE_DAILY_ASSET.name, {"trade_date": "20260431"})

    assert client.calls == []
