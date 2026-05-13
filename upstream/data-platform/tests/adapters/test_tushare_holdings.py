from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.tushare import (  # noqa: E402
    HOLDINGS_DATASET_FIELDS,
    TUSHARE_ASSETS,
    TUSHARE_FUND_PORTFOLIO_ASSET,
    TUSHARE_HSGT_HOLD_TOP10_ASSET,
    TUSHARE_HSGT_TOP10_ASSET,
    TUSHARE_TOP10_FLOATHOLDERS_ASSET,
    TUSHARE_TOP10_HOLDERS_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402


HOLDINGS_ASSETS = [
    TUSHARE_TOP10_HOLDERS_ASSET,
    TUSHARE_TOP10_FLOATHOLDERS_ASSET,
    TUSHARE_FUND_PORTFOLIO_ASSET,
    TUSHARE_HSGT_TOP10_ASSET,
    TUSHARE_HSGT_HOLD_TOP10_ASSET,
]
METHOD_BY_DATASET = {
    "top10_holders": "top10_holders",
    "top10_floatholders": "top10_floatholders",
    "fund_portfolio": "fund_portfolio",
    "hsgt_top10": "hsgt_top10",
    "hsgt_hold_top10": "hk_hold",
}
FETCH_PARAMS_BY_DATASET = {
    "top10_holders": {
        "ts_code": "000001.SZ",
        "period": "20260415",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "top10_floatholders": {
        "ts_code": "000001.SZ",
        "period": "20260415",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "fund_portfolio": {
        "ts_code": "001753.OF",
        "symbol": "000001.SZ",
        "period": "20260415",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "hsgt_top10": {
        "trade_date": "20260415",
        "market_type": "1",
        "fields": "bad",
    },
    "hsgt_hold_top10": {
        "trade_date": "20260415",
        "exchange": "SH",
        "fields": "bad",
    },
}
LIVE_FETCH_PARAMS_BY_DATASET = {
    "top10_holders": {"ts_code": "000001.SZ", "period": "20240331"},
    "top10_floatholders": {"ts_code": "000001.SZ", "period": "20240331"},
    "fund_portfolio": {"ts_code": "001753.OF", "period": "20240331"},
    "hsgt_top10": {"trade_date": "20240402", "market_type": "1"},
    "hsgt_hold_top10": {"trade_date": "20240402", "exchange": "SH"},
}


class FakeTushareHoldingsClient:
    def __init__(self, frames_by_method: dict[str, Any]) -> None:
        self.frames_by_method = frames_by_method
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def top10_holders(self, **kwargs: Any) -> Any:
        return self._record_call("top10_holders", kwargs)

    def top10_floatholders(self, **kwargs: Any) -> Any:
        return self._record_call("top10_floatholders", kwargs)

    def fund_portfolio(self, **kwargs: Any) -> Any:
        return self._record_call("fund_portfolio", kwargs)

    def hsgt_top10(self, **kwargs: Any) -> Any:
        return self._record_call("hsgt_top10", kwargs)

    def hk_hold(self, **kwargs: Any) -> Any:
        return self._record_call("hk_hold", kwargs)

    def _record_call(self, method_name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method_name, kwargs))
        frame = self.frames_by_method[method_name]
        if callable(frame):
            return frame(**kwargs)
        return frame


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _holdings_row(asset: Any, index: int = 0, partition_date: str = "20260415") -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in asset.schema:
        if field.name == "ts_code":
            row[field.name] = "001753.OF" if asset.dataset == "fund_portfolio" else "000001.SZ"
        elif field.name == "symbol":
            row[field.name] = "000001.SZ"
        elif field.name in {"ann_date", "end_date", "trade_date"}:
            row[field.name] = partition_date
        elif field.name == "rank":
            row[field.name] = str(index + 1)
        elif field.name == "market_type":
            row[field.name] = "1"
        elif field.name == "exchange":
            row[field.name] = "SH"
        else:
            row[field.name] = f"{field.name}-{index}"
    return row


def _holdings_frame(asset: Any, row_count: int, partition_date: str = "20260415") -> Any:
    if row_count == 0:
        return pd.DataFrame(columns=asset.schema.names)

    frame = pd.DataFrame(
        [
            _holdings_row(asset, index=index, partition_date=partition_date)
            for index in range(row_count)
        ]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _client_for_asset(asset: Any, frame: Any) -> FakeTushareHoldingsClient:
    method_name = METHOD_BY_DATASET[asset.dataset]
    return FakeTushareHoldingsClient({method_name: frame})


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareHoldingsClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareHoldingsClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


def _fields_csv(asset: Any) -> str:
    return ",".join(asset.schema.names)


def _raw_partition_call_params(asset: Any) -> dict[str, str]:
    if asset.dataset in {"top10_holders", "top10_floatholders"}:
        return {
            "period": "20260415",
            "ts_code": "000001.SZ",
            "fields": _fields_csv(asset),
        }
    if asset.dataset == "fund_portfolio":
        return {"period": "20260415", "fields": _fields_csv(asset)}
    return {"trade_date": "20260415", "fields": _fields_csv(asset)}


def test_holdings_assets_and_staging_models_are_registered() -> None:
    client = _client_for_asset(
        TUSHARE_TOP10_HOLDERS_ASSET,
        _holdings_frame(TUSHARE_TOP10_HOLDERS_ASSET, 1),
    )
    adapter = TushareAdapter(token="test-token", client=client)
    assets_by_name = {asset.name: asset for asset in adapter.get_assets()}

    assert HOLDINGS_DATASET_FIELDS == {
        asset.dataset: tuple(asset.schema.names) for asset in HOLDINGS_ASSETS
    }
    for asset in HOLDINGS_ASSETS:
        assert assets_by_name[asset.name] == asset
        assert f"stg_{asset.dataset}" in adapter.get_staging_dbt_models()
    assert TUSHARE_TOP10_HOLDERS_ASSET.metadata["required_fetch_params"] == ("ts_code",)
    assert TUSHARE_TOP10_HOLDERS_ASSET.metadata["raw_partition_scope"] == "explicit_ts_code"
    assert (
        TUSHARE_TOP10_FLOATHOLDERS_ASSET.metadata["daily_refresh_scope_env"]
        == "DP_TUSHARE_TOP10_TS_CODES"
    )
    assert {asset.name for asset in adapter.get_assets()} == {asset.name for asset in TUSHARE_ASSETS}


@pytest.mark.parametrize("asset", HOLDINGS_ASSETS, ids=lambda asset: asset.name)
def test_fetch_holdings_asset_returns_declared_schema(asset: Any) -> None:
    client = _client_for_asset(asset, _holdings_frame(asset, 2))
    adapter = TushareAdapter(token="test-token", client=client)

    params = FETCH_PARAMS_BY_DATASET[asset.dataset]
    table = adapter.fetch(asset.name, params)

    expected_params = {**params, "fields": _fields_csv(asset)}
    if asset.dataset == "fund_portfolio":
        expected_params = {
            **expected_params,
            "limit": tushare_adapter_module.FUND_PORTFOLIO_PAGE_LIMIT,
            "offset": 0,
        }
    if asset.dataset == "hsgt_hold_top10":
        expected_params = {
            **expected_params,
            "limit": tushare_adapter_module.HK_HOLD_PAGE_LIMIT,
            "offset": 0,
        }
    assert isinstance(table, pa.Table)
    assert table.schema == asset.schema
    assert table.num_rows == 2
    assert table.column_names == asset.schema.names
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], expected_params)]


def test_fetch_fund_portfolio_pages_until_short_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = TUSHARE_FUND_PORTFOLIO_ASSET
    rows = [
        _holdings_row(asset, index=index, partition_date="20240331")
        for index in range(5)
    ]
    for index, row in enumerate(rows):
        row["symbol"] = f"{index:06d}.SZ"

    def fetch_page(**kwargs: Any) -> Any:
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return pd.DataFrame(rows[offset : offset + limit])

    monkeypatch.setattr(tushare_adapter_module, "FUND_PORTFOLIO_PAGE_LIMIT", 2)
    client = _client_for_asset(asset, fetch_page)
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(asset.name, {"ts_code": "001753.OF", "period": "20240331"})

    assert table.num_rows == 5
    assert table.column("symbol").to_pylist() == [f"{index:06d}.SZ" for index in range(5)]
    assert [call[1]["offset"] for call in client.calls] == [0, 2, 4]
    assert [call[1]["limit"] for call in client.calls] == [2, 2, 2]


def test_fetch_hk_hold_splits_unscoped_trade_date_by_exchange_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = TUSHARE_HSGT_HOLD_TOP10_ASSET
    rows_by_exchange = {
        exchange: [
            {
                **_holdings_row(asset, index=index, partition_date="20240401"),
                "exchange": exchange,
                "ts_code": f"{index:06d}.SZ",
            }
            for index in range(row_count)
        ]
        for exchange, row_count in {"SH": 3, "SZ": 1}.items()
    }

    def fetch_page(**kwargs: Any) -> Any:
        exchange = kwargs["exchange"]
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return pd.DataFrame(rows_by_exchange[exchange][offset : offset + limit])

    monkeypatch.setattr(tushare_adapter_module, "HK_HOLD_PAGE_LIMIT", 2)
    client = _client_for_asset(asset, fetch_page)
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(asset.name, {"trade_date": "20240401"})

    assert table.num_rows == 4
    assert table.column("exchange").to_pylist() == ["SH", "SH", "SH", "SZ"]
    assert [
        (call[1]["exchange"], call[1]["offset"], call[1]["limit"])
        for call in client.calls
    ] == [
        ("SH", 0, 2),
        ("SH", 2, 2),
        ("SZ", 0, 2),
    ]


def test_fetch_hk_hold_empty_page_remains_adapter_error() -> None:
    asset = TUSHARE_HSGT_HOLD_TOP10_ASSET
    client = _client_for_asset(asset, _holdings_frame(asset, 0))
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(tushare_adapter_module.AdapterFetchError, match="empty table"):
        adapter.fetch(asset.name, {"trade_date": "20260504", "exchange": "SH"})

    assert client.calls == [
        (
            "hk_hold",
            {
                "trade_date": "20260504",
                "exchange": "SH",
                "fields": _fields_csv(asset),
                "limit": tushare_adapter_module.HK_HOLD_PAGE_LIMIT,
                "offset": 0,
            },
        )
    ]


def test_fetch_fund_portfolio_rejects_non_advancing_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = TUSHARE_FUND_PORTFOLIO_ASSET
    repeated_page = _holdings_frame(asset, 2, partition_date="20240331")

    monkeypatch.setattr(tushare_adapter_module, "FUND_PORTFOLIO_PAGE_LIMIT", 2)
    client = _client_for_asset(asset, repeated_page)
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(tushare_adapter_module.AdapterFetchError, match="did not advance"):
        adapter.fetch(asset.name, {"ts_code": "001753.OF", "period": "20240331"})

    assert [call[1]["offset"] for call in client.calls] == [0, 2]


def test_fetch_top10_requires_explicit_ts_code() -> None:
    asset = TUSHARE_TOP10_HOLDERS_ASSET
    client = _client_for_asset(asset, _holdings_frame(asset, 1))
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(
        tushare_adapter_module.AdapterFetchError,
        match="requires explicit ts_code",
    ):
        adapter.fetch(asset.name, {"period": "20240331"})

    assert client.calls == []


@pytest.mark.parametrize("asset", HOLDINGS_ASSETS, ids=lambda asset: asset.name)
def test_cli_writes_holdings_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
) -> None:
    if asset.dataset == "hsgt_hold_top10":
        frame = _holdings_frame(asset, 3)
        frame["exchange"] = "SH"
    else:
        frame = _holdings_frame(asset, 3)
    client = _client_for_asset(asset, frame)
    tokens = _install_tushare_client(monkeypatch, client)

    args = ["--asset", asset.name, "--date", "20260415"]
    if asset.dataset in {"top10_holders", "top10_floatholders"}:
        args.extend(["--ts-code", "000001.SZ"])
    if asset.dataset == "hsgt_hold_top10":
        args.extend(["--exchange", "SH"])

    exit_code = tushare_adapter_module.main(args)

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text(encoding="utf-8"))
    artifact_entry = manifest["artifacts"][0]
    table = pq.read_table(artifact_path).select(asset.schema.names)

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / asset.dataset / "dt=20260415"
    assert table.num_rows == 3
    assert manifest["partition_date"] == "2026-04-15"
    assert manifest["source_interface_id"] == asset.metadata["source_interface_id"]
    assert manifest["doc_api"] == asset.metadata["doc_api"]
    assert asset.metadata["raw_dataset"] == asset.dataset
    assert artifact_entry["dataset"] == asset.dataset
    assert artifact_entry["row_count"] == 3
    assert uuid.UUID(artifact_entry["run_id"]).version == 4
    expected_call_params = _raw_partition_call_params(asset)
    if asset.dataset == "fund_portfolio":
        expected_call_params = {
            **expected_call_params,
            "limit": tushare_adapter_module.FUND_PORTFOLIO_PAGE_LIMIT,
            "offset": 0,
        }
    if asset.dataset == "hsgt_hold_top10":
        expected_call_params = {
            **expected_call_params,
            "exchange": "SH",
            "limit": tushare_adapter_module.HK_HOLD_PAGE_LIMIT,
            "offset": 0,
        }
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], expected_call_params)]


def test_cli_rejects_top10_without_explicit_ts_code(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asset = TUSHARE_TOP10_HOLDERS_ASSET
    client = _client_for_asset(asset, _holdings_frame(asset, 1))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", asset.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert "requires explicit ts_code" in payload["error"]
    assert client.calls == []
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_combines_repeated_top10_ts_codes_into_one_raw_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asset = TUSHARE_TOP10_HOLDERS_ASSET

    def fetch_symbol(**kwargs: Any) -> Any:
        row = _holdings_row(asset, partition_date="20260415")
        row["ts_code"] = kwargs["ts_code"]
        return pd.DataFrame([row])

    client = _client_for_asset(asset, fetch_symbol)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        [
            "--asset",
            asset.name,
            "--date",
            "20260415",
            "--ts-code",
            "000001.SZ",
            "--ts-code",
            "600519.SH",
        ]
    )

    artifact_path = Path(capsys.readouterr().out.strip())
    table = pq.read_table(artifact_path).select(asset.schema.names)

    assert exit_code == 0
    assert table.num_rows == 2
    assert table.column("ts_code").to_pylist() == ["000001.SZ", "600519.SH"]
    assert [call[1]["ts_code"] for call in client.calls] == [
        "000001.SZ",
        "600519.SH",
    ]
    assert len(list(raw_zone_path.rglob("*.parquet"))) == 1


def test_live_tushare_holdings_smoke_requires_token() -> None:
    token = os.environ.get("DP_TUSHARE_TOKEN")
    if not token:
        pytest.skip("blocked: DP_TUSHARE_TOKEN is not set")
    if os.environ.get("DP_TUSHARE_LIVE_HOLDINGS_SMOKE") != "1":
        pytest.skip("blocked: DP_TUSHARE_LIVE_HOLDINGS_SMOKE is not set")

    adapter = TushareAdapter(token=token)
    for asset in HOLDINGS_ASSETS:
        table = adapter.fetch(asset.name, LIVE_FETCH_PARAMS_BY_DATASET[asset.dataset])
        assert isinstance(table, pa.Table)
        assert table.schema == asset.schema
        assert table.num_rows > 0
