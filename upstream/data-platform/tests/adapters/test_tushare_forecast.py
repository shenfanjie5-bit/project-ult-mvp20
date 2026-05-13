"""Adapter unit tests for the Tushare forecast dataset (Plan §5).

forecast is a new "FORECAST" family — structurally similar to
FINANCIAL datasets (multi-version via update_flag) but with a
different field set (no f_ann_date / report_type / comp_type) and
string numerics instead of decimal(38,18). Parallels
test_tushare_financials.py but scoped to the single forecast asset.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from data_platform.adapters.base import DataSourceAdapter  # noqa: E402
from data_platform.adapters.tushare import (  # noqa: E402
    FORECAST_DATASET_FIELDS,
    FORECAST_VERSION_FIELDS,
    TUSHARE_ASSETS,
    TUSHARE_FORECAST_ASSET,
    TushareAdapter,
)
from data_platform.adapters.tushare import adapter as tushare_adapter_module  # noqa: E402


FETCH_PARAMS = {
    "ts_code": "000001.SZ",
    "ann_date": "20260415",
    "end_date": "20260331",
    "start_date": "20260401",
    "period": "20260331",
    "fields": "bad",
}


class FakeTushareForecastClient:
    def __init__(self, frame: Any) -> None:
        self.frame = frame
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def forecast(self, **kwargs: Any) -> Any:
        self.calls.append(("forecast", kwargs))
        return self.frame


@pytest.fixture
def raw_zone_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raw_path = tmp_path / "raw"
    monkeypatch.setenv("DP_RAW_ZONE_PATH", str(raw_path))
    monkeypatch.setenv("DP_ICEBERG_WAREHOUSE_PATH", str(tmp_path / "iceberg" / "warehouse"))
    return raw_path


def _forecast_row(
    index: int = 0,
    *,
    ann_date: str = "20260415",
    end_date: str = "20260331",
    update_flag: str | None = None,
) -> dict[str, Any]:
    return {
        "ts_code": f"{index:06d}.SZ",
        "ann_date": ann_date,
        "end_date": end_date,
        "type": "预增",
        "p_change_min": f"{150 + index}",
        "p_change_max": f"{200 + index}",
        "net_profit_min": f"{1_000_000 + index}.12",
        "net_profit_max": f"{2_000_000 + index}.34",
        "last_parent_net": f"{500_000 + index}.56",
        "first_ann_date": ann_date,
        "summary": f"summary-{index}",
        "change_reason": f"reason-{index}",
        "update_flag": str(index) if update_flag is None else update_flag,
    }


def _forecast_frame(row_count: int, **kwargs: Any) -> Any:
    if row_count == 0:
        return pd.DataFrame(columns=TUSHARE_FORECAST_ASSET.schema.names)
    frame = pd.DataFrame(
        [_forecast_row(index=index, **kwargs) for index in range(row_count)]
    )
    frame["extra_column"] = ["ignored"] * row_count
    return frame


def _install_tushare_client(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeTushareForecastClient,
) -> list[str]:
    tokens: list[str] = []

    def pro_api(token: str) -> FakeTushareForecastClient:
        tokens.append(token)
        return client

    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api))
    return tokens


def _fields_csv() -> str:
    return ",".join(TUSHARE_FORECAST_ASSET.schema.names)


def test_forecast_asset_and_staging_model_registered() -> None:
    client = FakeTushareForecastClient(_forecast_frame(1))
    adapter = TushareAdapter(token="test-token", client=client)
    assets_by_name = {asset.name: asset for asset in adapter.get_assets()}

    assert isinstance(adapter, DataSourceAdapter)
    # Plan §5: forecast has its own family, distinct from
    # FINANCIAL_VERSION_FIELDS. Codex review #1 P2 fix: identity
    # includes `type` — 55% of corpus forecast files have rows that
    # share (ts_code, ann_date, end_date, update_flag) but differ in
    # type (e.g. "续亏" + "不确定" flavors for the same period). The
    # tuple order here must match FORECAST_IDENTITY_FIELDS in
    # adapter.py so the adapter's dedup path keeps all real rows.
    assert FORECAST_VERSION_FIELDS == (
        "ts_code",
        "ann_date",
        "end_date",
        "update_flag",
        "type",
    )
    assert FORECAST_DATASET_FIELDS == {
        "forecast": tuple(TUSHARE_FORECAST_ASSET.schema.names)
    }
    assert assets_by_name[TUSHARE_FORECAST_ASSET.name] == TUSHARE_FORECAST_ASSET
    assert TUSHARE_FORECAST_ASSET.partition == "daily"
    assert "stg_forecast" in adapter.get_staging_dbt_models()
    # Forecast numerics are pa.string() (Plan §2.1 — not decimal(38,18)).
    for field in TUSHARE_FORECAST_ASSET.schema:
        assert field.type == pa.string(), (
            f"forecast field {field.name!r} expected pa.string(), got {field.type}"
        )
    assert TUSHARE_FORECAST_ASSET in TUSHARE_ASSETS


def test_fetch_forecast_returns_declared_schema() -> None:
    client = FakeTushareForecastClient(_forecast_frame(2))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_FORECAST_ASSET.name, FETCH_PARAMS)

    expected_params = {**FETCH_PARAMS, "fields": _fields_csv()}
    assert isinstance(table, pa.Table)
    assert table.schema == TUSHARE_FORECAST_ASSET.schema
    assert table.num_rows == 2
    assert table.column_names == TUSHARE_FORECAST_ASSET.schema.names
    assert client.calls == [("forecast", expected_params)]


def test_forecast_versions_are_not_deduplicated() -> None:
    # Codex review #1 P2: three rows — two share all of (ts_code,
    # ann_date, end_date, update_flag) but differ in `type` (mirrors
    # the 000056.SZ/20240710/20240630 "续亏" + "不确定" corpus case);
    # the third has a different update_flag. All three must survive
    # because identity = (ts_code, ann_date, end_date, update_flag,
    # type).
    base = _forecast_row(ann_date="20260415", update_flag="0")
    rows = [
        {**base, "type": "续亏"},
        {**base, "type": "不确定"},
        _forecast_row(ann_date="20260415", update_flag="1"),
    ]
    client = FakeTushareForecastClient(pd.DataFrame(rows))
    adapter = TushareAdapter(token="test-token", client=client)

    table = adapter.fetch(TUSHARE_FORECAST_ASSET.name, {"period": "20260331"})

    assert table.num_rows == 3
    assert table["ts_code"].to_pylist() == ["000000.SZ"] * 3
    assert table["ann_date"].to_pylist() == ["20260415"] * 3
    assert table["end_date"].to_pylist() == ["20260331"] * 3
    # Rows 0 and 1 share update_flag='0' but have different type;
    # row 2 has update_flag='1'.
    assert table["update_flag"].to_pylist() == ["0", "0", "1"]
    assert table["type"].to_pylist() == ["续亏", "不确定", "预增"]


def test_cli_writes_forecast_raw_artifact_and_manifest(
    raw_zone_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeTushareForecastClient(
        _forecast_frame(3, ann_date="20260415", end_date="20260331"),
    )
    tokens = _install_tushare_client(monkeypatch, client)

    exit_code = tushare_adapter_module.main(
        ["--asset", TUSHARE_FORECAST_ASSET.name, "--date", "20260415"]
    )

    captured = capsys.readouterr()
    artifact_path = Path(captured.out.strip())
    manifest = json.loads((artifact_path.parent / "_manifest.json").read_text(encoding="utf-8"))
    artifact_entry = manifest["artifacts"][0]
    table = pq.read_table(artifact_path).select(TUSHARE_FORECAST_ASSET.schema.names)
    run_id = artifact_entry["run_id"]

    assert exit_code == 0
    assert captured.err == ""
    assert tokens == ["test-token"]
    assert artifact_path.parent == raw_zone_path / "tushare" / "forecast" / "dt=20260415"
    assert artifact_path.suffix == ".parquet"
    assert table.num_rows == 3
    assert manifest["partition_date"] == "2026-04-15"
    assert artifact_entry["path"] == str(artifact_path)
    assert artifact_entry["dataset"] == "forecast"
    assert artifact_entry["row_count"] == 3
    assert artifact_path.stem == run_id
    assert uuid.UUID(run_id).version == 4
    # forecast partitions on ann_date (Plan §5 — distinct from financial's end_date partition).
    assert client.calls == [
        (
            "forecast",
            {"ann_date": "20260415", "fields": _fields_csv()},
        )
    ]
