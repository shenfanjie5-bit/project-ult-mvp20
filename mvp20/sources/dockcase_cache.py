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
# lazy ts_code -> name map (for write-back filenames), built from stock_basic once.
_NAME_CACHE: dict[str, str] = {}


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


def _is_by_symbol(kwargs: dict[str, Any]) -> bool:
    """True if this is a single-symbol call we can serve / write (no cross-
    sectional ``trade_date=`` or date-range / multi-code filters)."""
    ts_code = kwargs.get("ts_code")
    return bool(ts_code and "," not in str(ts_code)
                and not kwargs.get("trade_date") and not kwargs.get("start_date")
                and not kwargs.get("end_date") and not kwargs.get("ann_date"))


def _apply_filters(df, endpoint: str, kwargs: dict[str, Any]):
    """Replicate tushare's period / limit / fields semantics on a full-history df."""
    period = kwargs.get("period")
    if period and "end_date" in df.columns:
        df = df[df["end_date"].astype(str) == str(period)]

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


def read(endpoint: str, kwargs: dict[str, Any]):
    """Return a tushare-shaped DataFrame for a by-symbol call, or ``None`` to fall
    through to the live API (cache disabled / miss / unsupported call shape)."""
    if not _is_by_symbol(kwargs):
        return None
    path = _csv_path(endpoint, str(kwargs["ts_code"]))
    if not path:
        return None
    try:
        df = _read_faithful(path)
    except Exception as exc:  # noqa: BLE001 — any read error → fall through to live
        log.debug("[dockcase] read failed %s %s: %s", endpoint, kwargs.get("ts_code"), exc)
        return None
    if df is None or len(df) == 0:
        return None
    # Archive hygiene: some by-symbol files carry exact-duplicate rows (notably
    # fina_indicator — ~33% of rows/file, each filing ingested 2×). Drop full-row
    # duplicates on the CONSUMER path only (refresh_existing keeps its faithful
    # never-dedup append). Only byte-identical rows are removed, so legitimate
    # multi-report_type / multi-product / multi-analyst rows are all preserved.
    before = len(df)
    df = df.drop_duplicates(ignore_index=True)
    if len(df) != before:
        log.debug("[dockcase] dedup %s %s: %d→%d rows",
                  endpoint, kwargs.get("ts_code"), before, len(df))
    return _apply_filters(df, endpoint, kwargs)


# ── write-back: persist freshly-downloaded per-symbol data INTO DockCase ──────
# Honors "新数据写进 DockCase": on a by-symbol cache MISS we fetch the full history
# live, write it as a new <分类>/by_symbol/<ts_code>+<name>.csv (matching the
# archive's layout + CRLF style), and serve the filtered subset. CREATE-ONLY — an
# existing DockCase file is NEVER modified, so the user's archive can't be broken.
# Toggle with DOCKCASE_WRITEBACK=0.


def writeback_enabled() -> bool:
    return available() and os.environ.get("DOCKCASE_WRITEBACK", "1") != "0"


def _name_for(ts_code: str, real_pro) -> str:
    """ts_code -> stock name for the filename (lazy stock_basic map; falls back to
    the numeric symbol so the file always carries the '+<name>' the reader globs)."""
    code = ts_code.upper()
    if not _NAME_CACHE:
        try:
            sb = real_pro.stock_basic(exchange="", list_status="L",
                                      fields="ts_code,name")
            for r in (sb.to_dict(orient="records") if sb is not None else []):
                _NAME_CACHE[str(r.get("ts_code", "")).upper()] = str(r.get("name") or "")
        except Exception:  # noqa: BLE001 — name lookup is best-effort
            pass
    name = _NAME_CACHE.get(code) or code.split(".")[0]
    # filesystem-safe: DockCase names contain CJK but never '/' or '+'.
    return name.replace("/", "_").replace("+", "_")


def _write_csv(endpoint: str, ts_code: str, name: str, full_df) -> bool:
    """Write full history to DockCase by_symbol as <ts_code>+<name>.csv. Returns
    True on a new write; refuses to overwrite an existing file (archive safety)."""
    r = root()
    folder = _ENDPOINT_FOLDER.get(endpoint)
    if r is None or not folder or full_df is None or len(full_df) == 0:
        return False
    bysym = r / folder / "by_symbol"
    out = bysym / f"{ts_code}+{name}.csv"
    if out.exists():  # CREATE-ONLY — never touch an existing archive file.
        return False
    try:
        bysym.mkdir(parents=True, exist_ok=True)
        tmp = bysym / f".{ts_code}.tmp.csv"  # atomic: write tmp then rename
        full_df.to_csv(tmp, index=False, lineterminator="\r\n", encoding="utf-8")
        os.replace(tmp, out)
        _PATH_CACHE[(endpoint, ts_code.upper())] = str(out)  # now cached
        log.info("[dockcase] write-back %s %s (%d rows)", endpoint, ts_code, len(full_df))
        return True
    except Exception as exc:  # noqa: BLE001 — write failure must never break onboard
        log.warning("[dockcase] write-back failed %s %s: %s", endpoint, ts_code, exc)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return False


def refresh_existing(endpoint: str, ts_code: str, real_method) -> int:
    """Append live rows STRICTLY NEWER than the existing file's max date-key into
    the existing DockCase file. Returns rows appended (0 if no file / nothing new /
    disabled). Safety:
      * never reorders/dedups/edits existing rows — appends only genuinely-new
        periods (financials) or trading days (market) → multi-report_type rows per
        period are preserved (a naive end_date-dedup would DROP them).
      * preserves the existing column order + CRLF; atomic tmp+rename write.
    Honors "增量追加到对应文件" while only fetching the small recent delta."""
    if not writeback_enabled():
        return 0
    path = _csv_path(endpoint, ts_code)
    if not path or not os.path.exists(path):
        return 0
    try:
        existing = _read_faithful(path)
    except Exception:  # noqa: BLE001
        return 0
    if existing is None or len(existing) == 0:
        return 0
    cols = list(existing.columns)
    key = _RECENCY_COL.get(endpoint)
    if not key:
        for cand in ("end_date", "trade_date", "ann_date", "report_date"):
            if cand in cols:
                key = cand
                break
    if not key or key not in cols:
        return 0
    fmax = str(existing[key].dropna().astype(str).max())
    try:
        if key == "trade_date":
            live = real_method(ts_code=ts_code, start_date=fmax)  # fmax inclusive
        else:
            live = real_method(ts_code=ts_code, limit=8)          # recent filings
    except Exception:  # noqa: BLE001
        return 0
    if live is None or len(live) == 0 or key not in getattr(live, "columns", []):
        return 0
    new = live[live[key].astype(str) > fmax]   # STRICTLY newer only
    if len(new) == 0:
        return 0
    import pandas as pd
    merged = pd.concat([existing, new[[c for c in cols if c in new.columns]]],
                       ignore_index=True)[cols]
    merged = merged.sort_values(key, ascending=False, kind="stable").reset_index(drop=True)
    tmp = path + ".reftmp"
    try:
        merged.to_csv(tmp, index=False, lineterminator="\r\n", encoding="utf-8")
        os.replace(tmp, path)
        log.info("[dockcase] refresh %s %s +%d rows", endpoint, ts_code, len(new))
        return len(new)
    except Exception as exc:  # noqa: BLE001 — never break on a write failure
        log.warning("[dockcase] refresh failed %s %s: %s", endpoint, ts_code, exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return 0


def fetch_writeback(endpoint: str, kwargs: dict[str, Any], real_method, real_pro):
    """Cache-miss handler: for a by-symbol call whose file is absent, fetch the
    FULL history live, write it into DockCase (create-only), and return the
    filtered subset. Any non-by-symbol / disabled / error path just calls live."""
    if not (writeback_enabled() and endpoint in _ENDPOINT_FOLDER
            and _is_by_symbol(kwargs) and _csv_path(endpoint, str(kwargs["ts_code"])) is None):
        return real_method(**kwargs)
    ts_code = str(kwargs["ts_code"])
    try:
        full = real_method(ts_code=ts_code)  # full history, all columns
    except Exception:  # noqa: BLE001 — fall back to the exact requested call
        return real_method(**kwargs)
    if full is None or len(full) == 0:
        return real_method(**kwargs)
    _write_csv(endpoint, ts_code, _name_for(ts_code, real_pro), full)
    return _apply_filters(full, endpoint, kwargs)
