from datetime import date
from pathlib import Path

from scripts import audit_a_share_data_semantics as audit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_share_data_semantics_reports_clean_core_sources(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    _write(
        root / "股票数据/基础数据/股票列表/all.csv",
        "ts_code,symbol,name,area,industry,market,list_date\n"
        "000001.SZ,000001,平安银行,深圳,银行,主板,19910403\n",
    )
    _write(
        root / "股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv",
        "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount\n"
        "000001.SZ,20260605,10,11,9,10.5,10,5,100,1000\n",
    )
    _write(
        root / "股票数据/财务数据/利润表/by_symbol/000001.SZ+平安银行.csv",
        "ts_code,ann_date,end_date,report_type,total_revenue,operate_profit,n_income,basic_eps\n"
        "000001.SZ,20260601,20260331,1,1000,100,80,0.5\n",
    )
    _write(
        root / "股票数据/资金流向数据/个股资金流向/by_symbol/000001.SZ+平安银行.csv",
        "ts_code,trade_date,buy_elg_amount,sell_elg_amount,net_mf_amount\n"
        "000001.SZ,20260605,10,5,5\n",
    )
    _write(
        root / "股票数据/特色数据/券商盈利预测数据/by_symbol/000001.SZ+平安银行.csv",
        "ts_code,report_date,org_name,author_name,quarter,tp,np,eps,pe,rating\n"
        "000001.SZ,20260601,券商,分析师,2026Q1,12,100,0.6,10,买入\n",
    )
    _write(
        root / "指数专题/指数日线行情/by_symbol/000001.SH+上证指数.csv",
        "ts_code,trade_date,close,open,high,low,pct_chg,vol,amount\n"
        "000001.SH,20260605,3000,2990,3010,2980,0.1,100,1000\n",
    )

    report = audit.build_report(
        data_root=root,
        symbols=("000001.SZ",),
        index_files=("000001.SH+上证指数.csv",),
        max_rows_per_file=0,
        # Pin the freshness reference: fixture dates are fixed (20260601+),
        # so a live date.today() turns this test into a time bomb once the
        # 30-day freshness lag threshold is crossed (bit CI on 2026-07-02).
        today=date(2026, 6, 20),
    )

    assert report["summary"]["dataset_count"] == 6
    assert report["summary"]["total_files_loaded"] == 6
    assert report["summary"]["total_rows_read"] == 6
    assert report["summary"]["ok_dataset_count"] == 6
    assert report["summary"]["total_issues"] == 0


def test_a_share_data_semantics_flags_bad_values_and_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "database_all"
    _write(
        root / "股票数据/基础数据/股票列表/all.csv",
        "ts_code,symbol,name,area,industry,market,list_date\n"
        "000001.SZ,000001,平安银行,深圳,银行,主板,19910403\n",
    )
    _write(
        root / "股票数据/行情数据/历史日线/by_symbol/000001.SZ+平安银行.csv",
        "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount\n"
        "000002.SZ,2026-06-05,bad,11,9,10.5,10,5,100,1000\n",
    )

    report = audit.build_report(
        data_root=root,
        symbols=("000001.SZ",),
        index_files=("000001.SH+上证指数.csv",),
        max_rows_per_file=0,
        # Pin the freshness reference: fixture dates are fixed (20260601+),
        # so a live date.today() turns this test into a time bomb once the
        # 30-day freshness lag threshold is crossed (bit CI on 2026-07-02).
        today=date(2026, 6, 20),
    )
    daily = next(item for item in report["datasets"] if item["dataset_id"] == "daily_bar")
    issue_codes = {issue["code"] for issue in daily["issues"]}

    assert daily["status"] == "review"
    assert "invalid_dates" in issue_codes
    assert "invalid_numeric_values" in issue_codes
    assert "symbol_file_ts_code_mismatch" in issue_codes
    assert report["summary"]["review_dataset_count"] >= 1
