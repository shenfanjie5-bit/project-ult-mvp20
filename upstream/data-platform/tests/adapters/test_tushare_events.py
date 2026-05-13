from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.base import AdapterFetchError  # noqa: E402
from data_platform.adapters.tushare import (  # noqa: E402
    EVENT_METADATA_FIELDS,
    TUSHARE_ANNS_ASSET,
    TUSHARE_ASSETS,
    TUSHARE_BLOCK_TRADE_ASSET,
    TUSHARE_DISCLOSURE_DATE_ASSET,
    TUSHARE_DIVIDEND_ASSET,
    TUSHARE_HM_DETAIL_ASSET,
    TUSHARE_LIMIT_LIST_D_ASSET,
    TUSHARE_LIMIT_LIST_THS_ASSET,
    TUSHARE_PLEDGE_DETAIL_ASSET,
    TUSHARE_PLEDGE_STAT_ASSET,
    TUSHARE_REPURCHASE_ASSET,
    TUSHARE_SHARE_FLOAT_ASSET,
    TUSHARE_STK_HOLDERNUMBER_ASSET,
    TUSHARE_STK_HOLDERTRADE_ASSET,
    TUSHARE_STK_SURV_ASSET,
    TUSHARE_SUSPEND_D_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402
from data_platform.adapters.tushare.assets import (  # noqa: E402
    ALLOW_NULL_IDENTITY_METADATA_KEY,
    ALLOW_NULL_IDENTITY_METADATA_VALUE,
)


EVENT_ASSETS = [
    TUSHARE_ANNS_ASSET,
    TUSHARE_SUSPEND_D_ASSET,
    TUSHARE_DIVIDEND_ASSET,
    TUSHARE_SHARE_FLOAT_ASSET,
    TUSHARE_STK_HOLDERNUMBER_ASSET,
    TUSHARE_DISCLOSURE_DATE_ASSET,
    TUSHARE_BLOCK_TRADE_ASSET,  # Plan §5 expansion
    # M1.13 expansion (precondition 9 closure) — 8 candidate
    # event_timeline sources promoted.
    TUSHARE_PLEDGE_STAT_ASSET,
    TUSHARE_PLEDGE_DETAIL_ASSET,
    TUSHARE_REPURCHASE_ASSET,
    TUSHARE_STK_HOLDERTRADE_ASSET,
    TUSHARE_STK_SURV_ASSET,
    TUSHARE_LIMIT_LIST_THS_ASSET,
    TUSHARE_LIMIT_LIST_D_ASSET,
    TUSHARE_HM_DETAIL_ASSET,
]
METHOD_BY_DATASET = {
    "anns": "anns",
    "suspend_d": "suspend_d",
    "dividend": "dividend",
    "share_float": "share_float",
    "stk_holdernumber": "stk_holdernumber",
    "disclosure_date": "disclosure_date",
    "block_trade": "block_trade",  # Plan §5 expansion
    # M1.13 expansion (precondition 9 closure).
    "pledge_stat": "pledge_stat",
    "pledge_detail": "pledge_detail",
    "repurchase": "repurchase",
    "stk_holdertrade": "stk_holdertrade",
    "stk_surv": "stk_surv",
    "limit_list_ths": "limit_list_ths",
    "limit_list_d": "limit_list_d",
    "hm_detail": "hm_detail",
}
FETCH_PARAMS_BY_DATASET = {
    "anns": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "suspend_d": {
        "ts_code": "000001.SZ",
        "trade_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "dividend": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "share_float": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "stk_holdernumber": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "disclosure_date": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "block_trade": {  # Plan §5 expansion
        "ts_code": "000001.SZ",
        "trade_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    # M1.13 expansion (precondition 9 closure) — 8 fetch parameter
    # dictionaries mirroring partition_request_params + date_param_names.
    "pledge_stat": {
        "ts_code": "000001.SZ",
        "end_date": "20260415",
        "ann_date": "20260415",
        "start_date": "20260415",
        "fields": "bad",
    },
    "pledge_detail": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "repurchase": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "stk_holdertrade": {
        "ts_code": "000001.SZ",
        "ann_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "stk_surv": {
        "ts_code": "000001.SZ",
        "surv_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "limit_list_ths": {
        "ts_code": "000001.SZ",
        "trade_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "limit_list_d": {
        "ts_code": "000001.SZ",
        "trade_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
    "hm_detail": {
        "ts_code": "000001.SZ",
        "trade_date": "20260415",
        "start_date": "20260415",
        "end_date": "20260415",
        "fields": "bad",
    },
}


class FakeTushareEventClient:
    def __init__(self, frames_by_method: dict[str, Any]) -> None:
        self.frames_by_method = frames_by_method
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def anns(self, **kwargs: Any) -> Any:
        return self._record_call("anns", kwargs)

    def suspend_d(self, **kwargs: Any) -> Any:
        return self._record_call("suspend_d", kwargs)

    def dividend(self, **kwargs: Any) -> Any:
        return self._record_call("dividend", kwargs)

    def share_float(self, **kwargs: Any) -> Any:
        return self._record_call("share_float", kwargs)

    def stk_holdernumber(self, **kwargs: Any) -> Any:
        return self._record_call("stk_holdernumber", kwargs)

    def disclosure_date(self, **kwargs: Any) -> Any:
        return self._record_call("disclosure_date", kwargs)

    def block_trade(self, **kwargs: Any) -> Any:  # Plan §5 expansion
        return self._record_call("block_trade", kwargs)

    # M1.13 expansion (precondition 9 closure) — 8 new fake fetch methods.
    def pledge_stat(self, **kwargs: Any) -> Any:
        return self._record_call("pledge_stat", kwargs)

    def pledge_detail(self, **kwargs: Any) -> Any:
        return self._record_call("pledge_detail", kwargs)

    def repurchase(self, **kwargs: Any) -> Any:
        return self._record_call("repurchase", kwargs)

    def stk_holdertrade(self, **kwargs: Any) -> Any:
        return self._record_call("stk_holdertrade", kwargs)

    def stk_surv(self, **kwargs: Any) -> Any:
        return self._record_call("stk_surv", kwargs)

    def limit_list_ths(self, **kwargs: Any) -> Any:
        return self._record_call("limit_list_ths", kwargs)

    def limit_list_d(self, **kwargs: Any) -> Any:
        return self._record_call("limit_list_d", kwargs)

    def hm_detail(self, **kwargs: Any) -> Any:
        return self._record_call("hm_detail", kwargs)

    def _record_call(self, method_name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method_name, kwargs))
        return self.frames_by_method[method_name]


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _event_row(asset: Any, index: int = 0, partition_date: str = "20260415") -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in asset.schema:
        if field.name == "ts_code":
            row[field.name] = f"{index:06d}.SZ"
        elif field.name in {
            "actual_date",
            "ann_date",
            "base_date",
            "div_listdate",
            "end_date",
            "ex_date",
            "exp_date",
            "float_date",
            "imp_ann_date",
            "modify_date",
            "pay_date",
            "pre_date",
            "record_date",
            "release_date",
            "start_date",
            "surv_date",
            "trade_date",
        }:
            row[field.name] = partition_date
        elif field.name == "url":
            row[field.name] = f"https://example.invalid/ann/{index}"
        elif field.name == "title":
            row[field.name] = f"announcement title {index}"
        else:
            row[field.name] = f"{field.name}-{index}"
    return row


def _event_frame(asset: Any, row_count: int, partition_date: str = "20260415") -> Any:
    if row_count == 0:
        return pd.DataFrame(columns=asset.schema.names)

    frame = pd.DataFrame(
        [
            _event_row(asset, index=index, partition_date=partition_date)
            for index in range(row_count)
        ]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _client_for_asset(asset: Any, frame: Any) -> FakeTushareEventClient:
    method_name = METHOD_BY_DATASET[asset.dataset]
    return FakeTushareEventClient({method_name: frame})


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareEventClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareEventClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


def _fields_csv(asset: Any) -> str:
    return ",".join(asset.schema.names)


def _raw_partition_call_params(asset: Any) -> dict[str, str]:
    # Plan §5 expansion — block_trade also partitions on trade_date.
    # M1.13 expansion (precondition 9 closure) — additional sources
    # partitioned on trade_date (limit_list_*, hm_detail) / surv_date
    # (stk_surv) / end_date (pledge_stat); the rest are ann_date.
    if asset.dataset in {
        "suspend_d",
        "block_trade",
        "limit_list_ths",
        "limit_list_d",
        "hm_detail",
    }:
        date_param = "trade_date"
    elif asset.dataset == "stk_surv":
        date_param = "surv_date"
    elif asset.dataset == "pledge_stat":
        date_param = "end_date"
    else:
        date_param = "ann_date"
    return {date_param: "20260415", "fields": _fields_csv(asset)}


def test_event_metadata_assets_and_staging_models_are_registered() -> None:
    client = _client_for_asset(TUSHARE_ANNS_ASSET, _event_frame(TUSHARE_ANNS_ASSET, 1))
    adapter = TushareAdapter(token="test-token", client=client)
    assets_by_name = {asset.name: asset for asset in adapter.get_assets()}
    asset_names = [asset.name for asset in adapter.get_assets()]

    assert EVENT_METADATA_FIELDS == {
        asset.dataset: tuple(asset.schema.names) for asset in EVENT_ASSETS
    }
    for asset in EVENT_ASSETS:
        assert assets_by_name[asset.name] == asset
        assert f"stg_{asset.dataset}" in adapter.get_staging_dbt_models()
    assert len(asset_names) == len(set(asset_names))
    assert {asset.name for asset in adapter.get_assets()} == {asset.name for asset in TUSHARE_ASSETS}
    assert type(adapter.get_quota_config()) is dict

    ts_code_metadata = TUSHARE_ANNS_ASSET.schema.field("ts_code").metadata or {}
    assert ts_code_metadata[ALLOW_NULL_IDENTITY_METADATA_KEY] == ALLOW_NULL_IDENTITY_METADATA_VALUE


@pytest.mark.parametrize("asset", EVENT_ASSETS, ids=lambda asset: asset.name)
def test_fetch_event_asset_returns_declared_metadata_schema(asset: Any) -> None:
    client = _client_for_asset(asset, _event_frame(asset, 2))
    adapter = TushareAdapter(token="test-token", client=client)

    params = FETCH_PARAMS_BY_DATASET[asset.dataset]
    table = adapter.fetch(asset.name, params)

    expected_params = {**params, "fields": _fields_csv(asset)}
    assert isinstance(table, pa.Table)
    assert table.schema == asset.schema
    assert table.num_rows == 2
    assert table.column_names == asset.schema.names
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], expected_params)]


@pytest.mark.parametrize("asset", EVENT_ASSETS, ids=lambda asset: asset.name)
def test_cli_writes_event_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
) -> None:
    client = _client_for_asset(asset, _event_frame(asset, 3))
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
    assert table.num_rows == 3
    assert manifest["partition_date"] == "2026-04-15"
    assert artifact_entry["path"] == str(artifact_path)
    assert artifact_entry["dataset"] == asset.dataset
    assert artifact_entry["row_count"] == 3
    assert artifact_path.stem == run_id
    assert uuid.UUID(run_id).version == 4
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], _raw_partition_call_params(asset))]


def test_announcement_raw_schema_keeps_metadata_only() -> None:
    frame = _event_frame(TUSHARE_ANNS_ASSET, 1)
    frame["content"] = ["正文不应进入 Raw"]
    frame["body"] = ["body should not be persisted"]
    frame["pdf"] = ["https://example.invalid/file.pdf"]
    client = _client_for_asset(TUSHARE_ANNS_ASSET, frame)
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_ANNS_ASSET.name, {"ann_date": "20260415"})

    assert table.column_names == TUSHARE_ANNS_ASSET.schema.names
    assert {"content", "body", "pdf", "html", "text"}.isdisjoint(table.column_names)


@pytest.mark.parametrize(
    ("asset", "missing_field"),
    [
        (TUSHARE_ANNS_ASSET, "ann_date"),
        (TUSHARE_SUSPEND_D_ASSET, "trade_date"),
    ],
    ids=lambda value: getattr(value, "name", str(value)),
)
def test_cli_rejects_missing_event_date_field_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
    missing_field: str,
) -> None:
    frame = _event_frame(asset, 1).drop(columns=[missing_field])
    client = _client_for_asset(asset, frame)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == asset.name
    assert payload["error_type"] == "upstream_missing_columns"
    assert "missing required fields" in payload["error"]
    assert missing_field in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_rejects_empty_event_response_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _client_for_asset(TUSHARE_DIVIDEND_ASSET, _event_frame(TUSHARE_DIVIDEND_ASSET, 0))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_DIVIDEND_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_DIVIDEND_ASSET.name
    assert payload["error_type"] == "upstream_empty_table"
    assert "empty table" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


def test_cli_event_missing_token_reports_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DP_TUSHARE_TOKEN", raising=False)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_ANNS_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == TUSHARE_ANNS_ASSET.name
    assert payload["error_type"] == "config_error"
    assert "DP_TUSHARE_TOKEN" in payload["error"]


def test_event_table_allows_annotated_empty_announcement_ts_code() -> None:
    frame = _event_frame(TUSHARE_ANNS_ASSET, 1)
    frame.loc[0, "ts_code"] = None
    client = _client_for_asset(TUSHARE_ANNS_ASSET, frame)
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_ANNS_ASSET.name, {"ann_date": "20260415"})

    assert table["ts_code"].to_pylist() == [None]


def test_event_table_rejects_unannotated_empty_ts_code() -> None:
    frame = _event_frame(TUSHARE_DIVIDEND_ASSET, 1)
    frame.loc[0, "ts_code"] = None
    client = _client_for_asset(TUSHARE_DIVIDEND_ASSET, frame)
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(AdapterFetchError, match="null identity field: ts_code"):
        adapter.fetch(TUSHARE_DIVIDEND_ASSET.name, {"ann_date": "20260415"})


def test_block_trade_rejects_null_ts_code() -> None:
    """Codex review #1 P2 regression guard: block_trade.ts_code is NOT
    allow_null_identity. A block trade by definition has a counterparty
    security — accepting ts_code=None would let a malformed upstream
    row into Raw Zone with no way to tie it back to an instrument.
    Unlike anns (where exchange-wide bulk announcements can legitimately
    lack a security key), block_trade must reject null ts_code."""
    frame = _event_frame(TUSHARE_BLOCK_TRADE_ASSET, 1)
    frame.loc[0, "ts_code"] = None
    client = _client_for_asset(TUSHARE_BLOCK_TRADE_ASSET, frame)
    adapter = TushareAdapter(token="test-token", client=client)

    with pytest.raises(AdapterFetchError, match="null identity field: ts_code"):
        adapter.fetch(TUSHARE_BLOCK_TRADE_ASSET.name, {"trade_date": "20260415"})
