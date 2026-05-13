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

from data_platform.adapters.tushare import (  # noqa: E402
    REFERENCE_DATA_IDENTITY_FIELDS,
    TUSHARE_ASSETS,
    TUSHARE_INDEX_BASIC_ASSET,
    TUSHARE_INDEX_CLASSIFY_ASSET,
    TUSHARE_INDEX_DAILY_ASSET,
    TUSHARE_INDEX_MEMBER_ASSET,
    TUSHARE_INDEX_WEIGHT_ASSET,
    TUSHARE_NAMECHANGE_ASSET,
    TUSHARE_STOCK_COMPANY_ASSET,
    TUSHARE_TRADE_CAL_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402


REFERENCE_ASSETS = [
    TUSHARE_INDEX_BASIC_ASSET,
    TUSHARE_INDEX_DAILY_ASSET,
    TUSHARE_INDEX_WEIGHT_ASSET,
    TUSHARE_INDEX_MEMBER_ASSET,
    TUSHARE_INDEX_CLASSIFY_ASSET,
    TUSHARE_TRADE_CAL_ASSET,
    TUSHARE_STOCK_COMPANY_ASSET,
    TUSHARE_NAMECHANGE_ASSET,
]
STATIC_REFERENCE_ASSETS = [
    TUSHARE_INDEX_BASIC_ASSET,
    TUSHARE_INDEX_CLASSIFY_ASSET,
    TUSHARE_STOCK_COMPANY_ASSET,
]
METHOD_BY_DATASET = {
    "index_basic": "index_basic",
    "index_daily": "index_daily",
    "index_weight": "index_weight",
    "index_member": "index_member",
    "index_classify": "index_classify",
    "trade_cal": "trade_cal",
    "stock_company": "stock_company",
    "namechange": "namechange",
}
FETCH_PARAMS_BY_DATASET = {
    "index_basic": {"market": "SSE", "fields": "bad"},
    "index_daily": {"trade_date": "20260415", "market": "SSE", "fields": "bad"},
    "index_weight": {"trade_date": "20260415", "index_code": "000300.SH", "fields": "bad"},
    "index_member": {
        "start_date": "20260415",
        "end_date": "20260415",
        "index_code": "000300.SH",
        "fields": "bad",
    },
    "index_classify": {"src": "SW2021", "fields": "bad"},
    "trade_cal": {"start_date": "20260415", "end_date": "20260415", "fields": "bad"},
    "stock_company": {"exchange": "SZSE", "fields": "bad"},
    "namechange": {"start_date": "20260415", "end_date": "20260415", "fields": "bad"},
}


class FakeTushareReferenceClient:
    def __init__(self, frames_by_method: dict[str, Any]) -> None:
        self.frames_by_method = frames_by_method
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def index_basic(self, **kwargs: Any) -> Any:
        return self._record_call("index_basic", kwargs)

    def index_daily(self, **kwargs: Any) -> Any:
        return self._record_call("index_daily", kwargs)

    def index_weight(self, **kwargs: Any) -> Any:
        return self._record_call("index_weight", kwargs)

    def index_member(self, **kwargs: Any) -> Any:
        return self._record_call("index_member", kwargs)

    def index_classify(self, **kwargs: Any) -> Any:
        return self._record_call("index_classify", kwargs)

    def trade_cal(self, **kwargs: Any) -> Any:
        return self._record_call("trade_cal", kwargs)

    def stock_company(self, **kwargs: Any) -> Any:
        return self._record_call("stock_company", kwargs)

    def namechange(self, **kwargs: Any) -> Any:
        return self._record_call("namechange", kwargs)

    def _record_call(self, method_name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method_name, kwargs))
        return self.frames_by_method[method_name]


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _reference_row(asset: Any, index: int = 0, partition_date: str = "20260415") -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in asset.schema:
        if field.name == "ts_code":
            row[field.name] = "000300.SH" if asset.dataset.startswith("index_") else "000001.SZ"
        elif field.name == "index_code":
            row[field.name] = "000300.SH"
        elif field.name == "con_code":
            row[field.name] = "000001.SZ"
        elif field.name in {"trade_date", "cal_date", "start_date", "in_date"}:
            row[field.name] = partition_date
        elif field.name == "is_open":
            row[field.name] = "1"
        else:
            row[field.name] = f"{field.name}-{index}"
    return row


def _reference_frame(asset: Any, row_count: int, partition_date: str = "20260415") -> Any:
    frame = pd.DataFrame(
        [
            _reference_row(asset, index=index, partition_date=partition_date)
            for index in range(row_count)
        ]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _client_for_asset(asset: Any, frame: Any) -> FakeTushareReferenceClient:
    method_name = METHOD_BY_DATASET[asset.dataset]
    return FakeTushareReferenceClient({method_name: frame})


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareReferenceClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareReferenceClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


def _fields_csv(asset: Any) -> str:
    return ",".join(asset.schema.names)


def _raw_partition_call_params(asset: Any) -> dict[str, str]:
    if asset.dataset in {"index_daily", "index_weight"}:
        return {"trade_date": "20260415", "fields": _fields_csv(asset)}
    if asset.dataset in {"index_member", "trade_cal", "namechange"}:
        return {
            "start_date": "20260415",
            "end_date": "20260415",
            "fields": _fields_csv(asset),
        }
    return {"fields": _fields_csv(asset)}


def test_reference_data_identity_fields_are_declared() -> None:
    assert REFERENCE_DATA_IDENTITY_FIELDS == {
        "index_basic": ("ts_code",),
        "index_daily": ("ts_code", "trade_date"),
        "index_weight": ("index_code", "con_code", "trade_date"),
        "index_member": ("index_code", "con_code", "in_date"),
        "index_classify": ("index_code",),
        "trade_cal": ("cal_date", "is_open"),
        "stock_company": ("ts_code",),
        "namechange": ("ts_code", "start_date"),
    }


def test_reference_assets_and_staging_models_are_registered() -> None:
    client = _client_for_asset(TUSHARE_INDEX_BASIC_ASSET, _reference_frame(TUSHARE_INDEX_BASIC_ASSET, 1))
    adapter = TushareAdapter(token="test-token", client=client)

    assets_by_name = {asset.name: asset for asset in adapter.get_assets()}

    for asset in REFERENCE_ASSETS:
        assert assets_by_name[asset.name] == asset
    assert adapter.get_staging_dbt_models() == [
        f"stg_{asset.dataset}" for asset in TUSHARE_ASSETS
    ]
    assert type(adapter.get_quota_config()) is dict


@pytest.mark.parametrize("asset", REFERENCE_ASSETS, ids=lambda asset: asset.name)
def test_fetch_reference_data_asset_returns_declared_schema(asset: Any) -> None:
    client = _client_for_asset(asset, _reference_frame(asset, 2))
    adapter = TushareAdapter(token="test-token", client=client)

    params = FETCH_PARAMS_BY_DATASET[asset.dataset]
    table = adapter.fetch(asset.name, params)

    expected_params = {**params, "fields": _fields_csv(asset)}
    assert isinstance(table, pa.Table)
    assert table.schema == asset.schema
    assert table.num_rows == 2
    assert table.column_names == asset.schema.names
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], expected_params)]


def test_to_reference_table_reuses_declared_schema_and_identity_validation() -> None:
    table = tushare_adapter_module._to_reference_table(
        "index_weight",
        _reference_frame(TUSHARE_INDEX_WEIGHT_ASSET, 1),
        TUSHARE_INDEX_WEIGHT_ASSET.schema,
    )

    assert table.schema == TUSHARE_INDEX_WEIGHT_ASSET.schema
    assert table.column_names == TUSHARE_INDEX_WEIGHT_ASSET.schema.names


@pytest.mark.parametrize("asset", REFERENCE_ASSETS, ids=lambda asset: asset.name)
def test_cli_writes_reference_data_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
) -> None:
    client = _client_for_asset(asset, _reference_frame(asset, 3))
    tokens = _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text(encoding="utf-8"))
    table = pq.read_table(artifact_path).select(asset.schema.names)

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / asset.dataset / "dt=20260415"
    assert table.schema == asset.schema
    assert table.num_rows == 3
    assert manifest["partition_date"] == "2026-04-15"
    assert manifest["artifacts"][0]["partition_date"] == "2026-04-15"
    assert manifest["artifacts"][0]["dataset"] == asset.dataset
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], _raw_partition_call_params(asset))]


@pytest.mark.parametrize("asset", STATIC_REFERENCE_ASSETS, ids=lambda asset: asset.name)
def test_static_reference_assets_do_not_inject_date_params(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
) -> None:
    client = _client_for_asset(asset, _reference_frame(asset, 1))
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())

    assert exit_code == 0
    assert artifact_path.parent == raw_zone_path / "tushare" / asset.dataset / "dt=20260415"
    assert client.calls == [(METHOD_BY_DATASET[asset.dataset], {"fields": _fields_csv(asset)})]


@pytest.mark.parametrize(
    ("asset", "missing_field"),
    [
        (TUSHARE_INDEX_WEIGHT_ASSET, "index_code"),
        (TUSHARE_INDEX_WEIGHT_ASSET, "con_code"),
        (TUSHARE_TRADE_CAL_ASSET, "cal_date"),
    ],
    ids=lambda value: getattr(value, "name", str(value)),
)
def test_cli_rejects_missing_reference_identity_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
    missing_field: str,
) -> None:
    frame = _reference_frame(asset, 1).drop(columns=[missing_field])
    client = _client_for_asset(asset, frame)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == asset.name
    assert "missing required fields" in payload["error"]
    assert missing_field in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []


@pytest.mark.parametrize(
    ("asset", "identity_field"),
    [
        (TUSHARE_INDEX_DAILY_ASSET, "trade_date"),
        (TUSHARE_INDEX_WEIGHT_ASSET, "index_code"),
        (TUSHARE_INDEX_WEIGHT_ASSET, "con_code"),
        (TUSHARE_TRADE_CAL_ASSET, "cal_date"),
        (TUSHARE_TRADE_CAL_ASSET, "is_open"),
    ],
    ids=lambda value: getattr(value, "name", str(value)),
)
def test_cli_rejects_null_reference_identity_without_artifact(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asset: Any,
    identity_field: str,
) -> None:
    frame = _reference_frame(asset, 1)
    frame.loc[0, identity_field] = None
    client = _client_for_asset(asset, frame)
    _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(["--asset", asset.name, "--date", "20260415"])

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert captured.out == ""
    assert payload["asset"] == asset.name
    assert f"null identity field: {identity_field}" in payload["error"]
    assert list(raw_zone_path.rglob("*.parquet")) == []
