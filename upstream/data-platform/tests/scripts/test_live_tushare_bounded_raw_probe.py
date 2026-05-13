from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from data_platform.adapters.tushare import (
    TUSHARE_ASSETS,
    TUSHARE_DAILY_ASSET,
    TUSHARE_STOCK_BASIC_ASSET,
    TUSHARE_TRADE_CAL_ASSET,
)
from scripts import live_tushare_bounded_raw_probe


class FakeTushareAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def source_id(self) -> str:
        return "tushare"

    def get_assets(self) -> list[Any]:
        return list(TUSHARE_ASSETS)

    def fetch(self, asset_name: str, params: dict[str, Any]) -> Any:
        self.calls.append((asset_name, params))
        if asset_name == TUSHARE_DAILY_ASSET.name:
            return _table_for_asset(
                TUSHARE_DAILY_ASSET,
                [
                    {
                        "ts_code": params["ts_code"],
                        "trade_date": params["trade_date"],
                    }
                ],
            )
        if asset_name == TUSHARE_TRADE_CAL_ASSET.name:
            return _table_for_asset(
                TUSHARE_TRADE_CAL_ASSET,
                [
                    {
                        "exchange": "SSE",
                        "cal_date": params["start_date"],
                        "is_open": "1",
                    }
                ],
            )
        if asset_name == TUSHARE_STOCK_BASIC_ASSET.name:
            return _table_for_asset(
                TUSHARE_STOCK_BASIC_ASSET,
                [
                    {"ts_code": "600519.SH", "symbol": "600519"},
                    {"ts_code": "000001.SZ", "symbol": "000001"},
                    {"ts_code": "999999.SZ", "symbol": "999999"},
                ],
            )
        raise AssertionError(f"unexpected asset: {asset_name}")


def test_run_probe_writes_bounded_daily_and_trade_cal_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    adapter = FakeTushareAdapter()

    report = live_tushare_bounded_raw_probe.run_probe(
        partition_date=date(2026, 4, 15),
        symbols=["600519.SH", "000001.SZ"],
        datasets=["daily", "trade_cal"],
        raw_zone_path=tmp_path / "raw",
        iceberg_warehouse_path=tmp_path / "warehouse",
        adapter=adapter,  # type: ignore[arg-type]
    )

    assert report["ok"] is True
    assert report["live_tushare_token_used"] is True
    assert report["scope"] == {
        "date": "20260415",
        "symbols": ["600519.SH", "000001.SZ"],
        "datasets": ["daily", "trade_cal"],
    }
    assert adapter.calls == [
        (TUSHARE_DAILY_ASSET.name, {"ts_code": "600519.SH", "trade_date": "20260415"}),
        (TUSHARE_DAILY_ASSET.name, {"ts_code": "000001.SZ", "trade_date": "20260415"}),
        (TUSHARE_TRADE_CAL_ASSET.name, {"start_date": "20260415", "end_date": "20260415"}),
    ]

    by_dataset = {item["dataset"]: item for item in report["datasets"]}
    assert by_dataset["daily"]["request_count"] == 2
    assert by_dataset["daily"]["row_count"] == 2
    assert by_dataset["daily"]["supports_symbol_filter"] is True
    assert by_dataset["trade_cal"]["row_count"] == 1
    assert by_dataset["trade_cal"]["bounded_strategy"] == (
        "single-day start_date=end_date; no symbol dimension"
    )
    assert pq.read_table(by_dataset["daily"]["artifact_paths"][0]).num_rows == 2
    assert pq.read_table(by_dataset["trade_cal"]["artifact_paths"][0]).num_rows == 1


def test_stock_basic_is_post_filtered_and_reported_as_non_symbol_api(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DP_TUSHARE_TOKEN", "test-token")
    adapter = FakeTushareAdapter()

    report = live_tushare_bounded_raw_probe.run_probe(
        partition_date=date(2026, 4, 15),
        symbols=["600519.SH", "000001.SZ"],
        datasets=["stock_basic"],
        raw_zone_path=tmp_path / "raw",
        iceberg_warehouse_path=tmp_path / "warehouse",
        adapter=adapter,  # type: ignore[arg-type]
    )

    result = report["datasets"][0]
    assert adapter.calls == [(TUSHARE_STOCK_BASIC_ASSET.name, {"list_status": "L"})]
    assert result["supports_symbol_filter"] is False
    assert result["symbol_filter_applied"] is False
    assert result["upstream_row_count"] == 3
    assert result["row_count"] == 2
    assert result["calls"][0]["post_fetch_symbol_filter_applied"] is True
    table = pq.read_table(result["artifact_paths"][0])
    assert table.column("ts_code").to_pylist() == ["600519.SH", "000001.SZ"]


def test_main_writes_blocked_report_without_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DP_TUSHARE_TOKEN", raising=False)
    report_path = tmp_path / "report.json"

    exit_code = live_tushare_bounded_raw_probe.main(
        [
            "--date",
            "20260415",
            "--symbols",
            "600519.SH",
            "--datasets",
            "daily",
            "--raw-zone-path",
            str(tmp_path / "raw"),
            "--iceberg-warehouse-path",
            str(tmp_path / "warehouse"),
            "--json-report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["live_tushare_token_used"] is False
    assert "DP_TUSHARE_TOKEN is required" in payload["error"]


def _table_for_asset(asset: Any, overrides: list[dict[str, Any]]) -> Any:
    rows: list[dict[str, Any]] = []
    for index, override in enumerate(overrides):
        row: dict[str, Any] = {}
        for field in asset.schema:
            if field.name == "ts_code":
                row[field.name] = f"{index:06d}.SZ"
            elif field.name in {"trade_date", "cal_date", "list_date"}:
                row[field.name] = "20260415"
            elif field.name == "delist_date":
                row[field.name] = None
            elif field.name == "is_open":
                row[field.name] = "1"
            else:
                row[field.name] = f"{field.name}-{index}"
        row.update(override)
        rows.append(row)
    return live_tushare_bounded_raw_probe.pa.table(
        {field.name: [row[field.name] for row in rows] for field in asset.schema},
        schema=asset.schema,
    )
