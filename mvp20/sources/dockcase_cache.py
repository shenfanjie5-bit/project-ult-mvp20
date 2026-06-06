"""Read-only DockCase 2TB tushare cache.

The external drive ``/Volumes/dockcase2tb`` holds a full tushare archive organised
by the tushare doc hierarchy::

    database_all/<分类>/<子类>/<叶子>/by_symbol/<ts_code>+<name>.csv

Each CSV is a verbatim dump of that endpoint's tushare response columns for ONE
symbol's full history. We READ it to avoid re-downloading per-symbol data that is
already on disk; we NEVER write to it — its storage layout is preserved untouched.

Only single-``ts_code`` ("by symbol") calls for the mapped endpoints are served
from cache. Cross-sectional (``trade_date=``), date-range (``start_date``/
``end_date``/``ann_date``) and multi-code calls fall through to the live tushare
API, so we never feed mis-filtered data into scoring. Faithful to tushare dtypes:
date/code/flag columns stay strings, value columns stay numeric.

Toggle: ``DOCKCASE_CACHE=0`` disables; ``DOCKCASE_ROOT`` overrides the mount path.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_ROOT = "/Volumes/dockcase2tb/database_all"

# endpoint -> by_symbol folder (relative to database_all). Only endpoints whose
# DockCase folder has a populated by_symbol/ dir (verified 2026-06-06: each holds
# ~3.7k–5.8k per-symbol CSVs). Immutable financials are the safe high-value win;
# daily/daily_basic/moneyflow are cached too (the archive's price tail is stale by
# a couple months, but onboard's *current* price comes from the cross-sectional
# realtime path which still hits live tushare).
_ENDPOINT_FOLDER: dict[str, str] = {
    "income": "股票数据/财务数据/利润表",
    "balancesheet": "股票数据/财务数据/资产负债表",
    "cashflow": "股票数据/财务数据/现金流量表",
    "fina_indicator": "股票数据/财务数据/财务指标数据",
    "forecast": "股票数据/财务数据/业绩预告",
    "express": "股票数据/财务数据/业绩快报",
    "dividend": "股票数据/财务数据/分红送股数据",
    "fina_mainbz": "股票数据/财务数据/主营业务构成",
    "daily": "股票数据/行情数据/历史日线",
    "daily_basic": "股票数据/行情数据/每日指标",
    "moneyflow": "股票数据/资金流向数据/个股资金流向",
    "report_rc": "股票数据/特色数据/券商盈利预测数据",
    "stk_holdertrade": "股票数据/参考数据/股东增减持",
}

# recency column for the `limit` (most-recent-N) semantics. Financials default to
# end_date; market data uses trade_date.
_RECENCY_COL: dict[str, str] = {
    "daily": "trade_date", "daily_basic": "trade_date", "moneyflow": "trade_date",
}

# A column is a string (not numeric) in tushare if its name carries any of these.
_STR_HINTS = ("code", "date", "type", "name", "flag", "proc", "period", "status",
              "quarter", "report", "comp", "currency", "exchange", "industry", "area")

CACHEABLE_ENDPOINTS = frozenset(_ENDPOINT_FOLDER)

# in-process cache of resolved file paths (globbing a slow USB drive is costly).
_PATH_CACHE: dict[tuple[str, str], str | None] = {}


def root() -> Path | None:
    if os.environ.get("DOCKCASE_CACHE", "1") == "0":
        return None
    r = Path(os.environ.get("DOCKCASE_ROOT", _DEFAULT_ROOT))
    try:
        return r if r.is_dir() else None
    except OSError:
        return None


def available() -> bool:
    return root() is not None


def _csv_path(endpoint: str, ts_code: str) -> str | None:
    r = root()
    if r is None:
        return None
    folder = _ENDPOINT_FOLDER.get(endpoint)
    if not folder:
        return None
    key = (endpoint, ts_code.upper())
    if key in _PATH_CACHE:
        return _PATH_CACHE[key]
    # filename is "<ts_code>+<name>.csv"; ts_code is an exact prefix before '+'.
    pattern = str(r / folder / "by_symbol" / f"{glob.escape(ts_code)}+*.csv")
    hits = glob.glob(pattern)
    path = hits[0] if hits else None
    _PATH_CACHE[key] = path
    return path


def _read_faithful(path: str):
    """Read a DockCase CSV into a tushare-shaped DataFrame (str date/code columns,
    numeric value columns, NaN for blanks — matching pro.<endpoint> output)."""
    import pandas as pd

    header = pd.read_csv(path, nrows=0)
    str_cols = {c: str for c in header.columns
                if any(h in c.lower() for h in _STR_HINTS)}
    df = pd.read_csv(path, dtype=str_cols or None)
    # blanks in forced-str columns read back as NaN; leave numeric NaN as-is (tushare
    # also returns NaN), but normalise str-column NaN to None to match tushare.
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].where(df[c].notna(), None)
    return df


def read(endpoint: str, kwargs: dict[str, Any]):
    """Return a tushare-shaped DataFrame for a by-symbol call, or ``None`` to fall
    through to the live API (cache disabled / miss / unsupported call shape)."""
    ts_code = kwargs.get("ts_code")
    # only by-symbol: a single ts_code and no cross-sectional / date-range param.
    if (not ts_code or "," in str(ts_code)
            or kwargs.get("trade_date") or kwargs.get("start_date")
            or kwargs.get("end_date") or kwargs.get("ann_date")):
        return None
    path = _csv_path(endpoint, str(ts_code))
    if not path:
        return None
    try:
        df = _read_faithful(path)
    except Exception as exc:  # noqa: BLE001 — any read error → fall through to live
        log.debug("[dockcase] read failed %s %s: %s", endpoint, ts_code, exc)
        return None
    if df is None or len(df) == 0:
        return None

    # period filter (financials): exact end_date match, as tushare does.
    period = kwargs.get("period")
    if period and "end_date" in df.columns:
        df = df[df["end_date"].astype(str) == str(period)]

    # recency sort so `limit` returns the most recent N (tushare default order).
    col = _RECENCY_COL.get(endpoint)
    if not col:
        for cand in ("end_date", "trade_date", "ann_date", "report_date"):
            if cand in df.columns:
                col = cand
                break
    if col and col in df.columns:
        df = df.sort_values(col, ascending=False, kind="stable")

    limit = kwargs.get("limit")
    if limit:
        try:
            df = df.head(int(limit))
        except (ValueError, TypeError):
            pass

    fields = kwargs.get("fields")
    if fields:
        want = [c.strip() for c in str(fields).split(",") if c.strip()]
        keep = [c for c in want if c in df.columns]
        if keep:
            df = df[keep]

    return df.reset_index(drop=True)
