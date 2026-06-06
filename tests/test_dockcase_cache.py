"""Hermetic tests for the read-only DockCase tushare cache (no real drive)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mvp20.sources import dockcase_cache as dc  # noqa: E402


def _seed(root: Path, endpoint_folder: str, ts_code: str, csv: str) -> None:
    d = root / endpoint_folder / "by_symbol"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ts_code}+测试.csv").write_text(csv, encoding="utf-8")


def _income_csv() -> str:
    # newest first NOT guaranteed on disk — the cache must sort by end_date desc.
    return (
        "ts_code,end_date,ann_date,total_revenue,n_income\n"
        "600519.SH,20240331,20240425,100.5,40.0\n"
        "600519.SH,20250930,20251030,300.0,120.0\n"
        "600519.SH,20241231,20250330,200.0,80.0\n"
    )


@pytest.fixture()
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKCASE_ROOT", str(tmp_path))
    monkeypatch.setenv("DOCKCASE_CACHE", "1")
    dc._PATH_CACHE.clear()
    _seed(tmp_path, "股票数据/财务数据/利润表", "600519.SH", _income_csv())
    return tmp_path


def test_available_and_root(cache_root, monkeypatch):
    assert dc.available() is True
    monkeypatch.setenv("DOCKCASE_CACHE", "0")
    assert dc.available() is False  # explicit disable


def test_read_by_symbol_sorts_and_limits(cache_root):
    df = dc.read("income", {"ts_code": "600519.SH", "limit": 2})
    assert df is not None and len(df) == 2
    # sorted by end_date desc → newest 2 are 2025Q3 then 2024-annual
    assert list(df["end_date"]) == ["20250930", "20241231"]


def test_read_period_filter(cache_root):
    df = dc.read("income", {"ts_code": "600519.SH", "period": "20241231"})
    assert df is not None and len(df) == 1
    assert df["end_date"].iloc[0] == "20241231"
    assert float(df["total_revenue"].iloc[0]) == 200.0


def test_read_fields_subset(cache_root):
    df = dc.read("income", {"ts_code": "600519.SH", "fields": "ts_code,end_date,n_income"})
    assert df is not None
    assert list(df.columns) == ["ts_code", "end_date", "n_income"]


def test_str_columns_stay_strings(cache_root):
    df = dc.read("income", {"ts_code": "600519.SH"})
    # end_date / ts_code must be strings (tushare-faithful), not int64
    assert isinstance(df["end_date"].iloc[0], str)
    assert df["end_date"].iloc[0] == "20250930"


def test_cross_sectional_call_falls_through(cache_root):
    # trade_date / start_date / no-ts_code → None (caller hits live API)
    assert dc.read("daily", {"trade_date": "20260605"}) is None
    assert dc.read("income", {"ts_code": "600519.SH", "start_date": "20240101"}) is None
    assert dc.read("income", {"ts_code": "600519.SH,000001.SZ"}) is None
    assert dc.read("income", {}) is None


def test_unmapped_endpoint_and_miss(cache_root):
    assert dc.read("stock_basic", {"ts_code": "600519.SH"}) is None  # not cacheable
    assert dc.read("income", {"ts_code": "999999.SZ"}) is None       # no file → miss


def test_disabled_returns_none(cache_root, monkeypatch):
    monkeypatch.setenv("DOCKCASE_CACHE", "0")
    assert dc.read("income", {"ts_code": "600519.SH"}) is None


# ── write-back ──────────────────────────────────────────────────────────────

class _FakePro:
    """Minimal stand-in: full_method returns full history; stock_basic a name."""
    def __init__(self, full_df):
        self._full = full_df
        self.calls = []

    def income(self, **kw):
        self.calls.append(kw)
        if "limit" in kw or "fields" in kw:  # the requested (filtered) shape
            return dc._apply_filters(self._full.copy(), "income", kw)
        return self._full.copy()  # full history

    def stock_basic(self, **kw):
        import pandas as pd
        return pd.DataFrame([{"ts_code": "999001.SZ", "name": "新股测试"}])


def test_writeback_creates_file_and_serves_filtered(cache_root, monkeypatch):
    import pandas as pd
    dc._PATH_CACHE.clear(); dc._NAME_CACHE.clear()
    full = pd.read_csv(__import__("io").StringIO(_income_csv()), dtype=str)
    pro = _FakePro(full)
    monkeypatch.setenv("DOCKCASE_WRITEBACK", "1")
    # 999001.SZ is absent → write-back path
    out = dc.fetch_writeback("income", {"ts_code": "999001.SZ", "limit": 2},
                             pro.income, pro)
    assert out is not None and len(out) == 2          # filtered subset returned
    # a new file was created under by_symbol with the resolved name + CRLF
    f = cache_root / "股票数据/财务数据/利润表/by_symbol/999001.SZ+新股测试.csv"
    assert f.exists()
    raw = f.read_bytes()
    assert b"\r\n" in raw                             # CRLF like the archive
    assert len(pd.read_csv(f, dtype=str)) == 3        # FULL history written


def test_writeback_never_overwrites_existing(cache_root, monkeypatch):
    import pandas as pd
    dc._PATH_CACHE.clear()
    full = pd.read_csv(__import__("io").StringIO(_income_csv()), dtype=str)
    pro = _FakePro(full)
    # 600519.SH already exists (seeded) → write-back must NOT touch it / re-fetch
    before = (cache_root / "股票数据/财务数据/利润表/by_symbol/600519.SH+测试.csv").read_bytes()
    out = dc.fetch_writeback("income", {"ts_code": "600519.SH", "limit": 2},
                             pro.income, pro)
    assert out is not None
    after = (cache_root / "股票数据/财务数据/利润表/by_symbol/600519.SH+测试.csv").read_bytes()
    assert before == after  # untouched


def test_writeback_disabled_just_calls_live(cache_root, monkeypatch):
    import pandas as pd
    monkeypatch.setenv("DOCKCASE_WRITEBACK", "0")
    pro = _FakePro(pd.read_csv(__import__("io").StringIO(_income_csv()), dtype=str))
    out = dc.fetch_writeback("income", {"ts_code": "999002.SZ", "limit": 12,
                                        "fields": "ts_code,end_date"}, pro.income, pro)
    assert out is not None
    # no file created
    assert not (cache_root / "股票数据/财务数据/利润表/by_symbol/999002.SZ+新股测试.csv").exists()
