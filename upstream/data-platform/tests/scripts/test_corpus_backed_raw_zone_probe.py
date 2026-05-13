from __future__ import annotations

import json
from pathlib import Path

from scripts import corpus_backed_raw_zone_probe


def test_corpus_bridge_writes_bounded_raw_zone_artifacts(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    _write_corpus(corpus_root)

    report_path = tmp_path / "report.json"
    exit_code = corpus_backed_raw_zone_probe.main(
        [
            "--corpus-root",
            str(corpus_root),
            "--raw-zone-path",
            str(tmp_path / "raw"),
            "--iceberg-warehouse-path",
            str(tmp_path / "warehouse"),
            "--dates",
            "20260331",
            "--symbols",
            "600519.SH,000001.SZ",
            "--json-report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "corpus_backed_raw_zone_probe"
    assert payload["live_tushare_token_used"] is False
    assert payload["summary"]["status"] == "ok"
    assert payload["summary"]["artifact_count"] == 3
    assert payload["summary"]["row_count"] == 5
    assert (
        tmp_path
        / "raw"
        / "tushare"
        / "daily"
        / "dt=20260331"
        / "_manifest.json"
    ).is_file()


def _write_corpus(corpus_root: Path) -> None:
    stock_basic = corpus_root / "股票数据" / "基础数据" / "股票列表"
    trade_cal = corpus_root / "股票数据" / "基础数据" / "交易日历"
    daily = corpus_root / "股票数据" / "行情数据" / "历史日线" / "by_symbol"
    stock_basic.mkdir(parents=True)
    trade_cal.mkdir(parents=True)
    daily.mkdir(parents=True)

    (stock_basic / "all.csv").write_text(
        "\n".join(
            [
                "ts_code,symbol,name,area,industry,cnspell,market,list_date,act_name,act_ent_type",
                "600519.SH,600519,贵州茅台,贵州,白酒,GZMT,主板,20010827,owner,type",
                "000001.SZ,000001,平安银行,深圳,银行,PAYH,主板,19910403,owner,type",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (trade_cal / "all.csv").write_text(
        "\n".join(
            [
                "exchange,cal_date,is_open,pretrade_date",
                "SSE,20260331,1,20260330",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for symbol, name in (("600519.SH", "贵州茅台"), ("000001.SZ", "平安银行")):
        (daily / f"{symbol}+{name}.csv").write_text(
            "\n".join(
                [
                    "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
                    f"{symbol},20260331,1,2,1,2,1,1,100,10,20",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
