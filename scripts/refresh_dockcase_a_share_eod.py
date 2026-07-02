#!/usr/bin/env python3
"""Refresh DockCase A-share EOD by-symbol CSVs from cross-sectional snapshots.

The normal DockCase cache is optimized for per-symbol reads. Updating it by
calling tushare once per stock is slow and fragile, so this script pulls each
EOD endpoint once by ``trade_date`` and appends the matching row into the
corresponding ``by_symbol/<ts_code>+<name>.csv`` file.

Default endpoints are the market data needed by the quant/signal builders:
``daily``, ``daily_basic`` and ``moneyflow``.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.sources import load_dotenv  # noqa: E402
from mvp20.sources import dockcase_cache  # noqa: E402
from mvp20.sources.tushare_source import _get_pro_api  # noqa: E402


ENDPOINT_FOLDERS = {
    "daily": "股票数据/行情数据/历史日线/by_symbol",
    "daily_basic": "股票数据/行情数据/每日指标/by_symbol",
    "moneyflow": "股票数据/资金流向数据/个股资金流向/by_symbol",
}

DATE_KEY = {
    "daily": "trade_date",
    "daily_basic": "trade_date",
    "moneyflow": "trade_date",
}


@dataclass(frozen=True)
class AppendResult:
    status: str
    rows_added: int = 0
    error: str | None = None


def load_a_share_universe(overlays_dir: Path) -> list[str]:
    return sorted({
        p.stem
        for p in overlays_dir.glob("*/*.yaml")
        if p.stem.endswith((".SH", ".SZ", ".BJ"))
    })


def dockcase_root() -> Path:
    root = dockcase_cache.root()
    if root is None:
        raise RuntimeError("DockCase root is unavailable; check /Volumes/dockcase2tb")
    return root


def csv_path(data_root: Path, endpoint: str, ts_code: str) -> Path | None:
    folder = ENDPOINT_FOLDERS[endpoint]
    hits = glob.glob(str(data_root / folder / f"{glob.escape(ts_code)}+*.csv"))
    return Path(hits[0]) if hits else None


def _read_existing(path: Path, key: str) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0)
    dtype = {c: str for c in header.columns if c == key or "date" in c.lower() or "code" in c.lower()}
    return pd.read_csv(path, dtype=dtype or None, low_memory=False)


def append_snapshot_row(
    *,
    path: Path,
    row: dict[str, Any],
    key: str,
    trade_date: str,
    dry_run: bool = False,
) -> AppendResult:
    try:
        existing = _read_existing(path, key)
    except Exception as exc:  # noqa: BLE001
        return AppendResult("read_error", error=str(exc))
    if key not in existing.columns:
        return AppendResult("missing_key", error=f"{key} not in {path.name}")

    existing_dates = set(existing[key].dropna().astype(str))
    if trade_date in existing_dates:
        return AppendResult("already_current")

    cols = list(existing.columns)
    row_df = pd.DataFrame([{c: row.get(c) for c in cols}])
    if key in row_df.columns:
        row_df[key] = row_df[key].astype(str)
    if dry_run:
        return AppendResult("would_append", rows_added=1)

    merged = pd.concat([existing, row_df], ignore_index=True)
    merged[key] = merged[key].astype(str)
    merged = merged.sort_values(key, ascending=False, kind="stable").reset_index(drop=True)

    tmp = Path(str(path) + ".reftmp")
    try:
        merged.to_csv(tmp, index=False, lineterminator="\r\n", encoding="utf-8")
        os.replace(tmp, path)
        return AppendResult("appended", rows_added=1)
    except Exception as exc:  # noqa: BLE001
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return AppendResult("write_error", error=str(exc))


def _snapshot_for_endpoint(pro: Any, endpoint: str, trade_date: str) -> pd.DataFrame:
    method = getattr(pro, endpoint)
    df = method(trade_date=trade_date)
    if df is None:
        return pd.DataFrame()
    return df


def resolve_trade_date(
    pro: Any,
    requested: str | None,
    *,
    min_rows: int,
    lookback_days: int,
) -> tuple[str, pd.DataFrame]:
    candidates: list[str]
    if requested:
        candidates = [requested]
    else:
        today = datetime.now().strftime("%Y%m%d")
        base = datetime.strptime(today, "%Y%m%d")
        candidates = [
            (base - timedelta(days=i)).strftime("%Y%m%d")
            for i in range(max(1, lookback_days))
        ]

    last_df = pd.DataFrame()
    for d in candidates:
        df = _snapshot_for_endpoint(pro, "daily_basic", d)
        last_df = df
        if len(df) >= min_rows:
            return d, df
    if requested:
        raise RuntimeError(
            f"daily_basic snapshot for requested trade_date={requested} has "
            f"{len(last_df)} rows < min_rows={min_rows}"
        )
    raise RuntimeError(
        f"no daily_basic snapshot reached min_rows={min_rows} in last {lookback_days} days"
    )


def refresh_endpoint(
    *,
    pro: Any,
    data_root: Path,
    endpoint: str,
    trade_date: str,
    universe: list[str],
    preloaded_snapshot: pd.DataFrame | None = None,
    create_missing_full: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    key = DATE_KEY[endpoint]
    df = preloaded_snapshot if preloaded_snapshot is not None else _snapshot_for_endpoint(pro, endpoint, trade_date)
    if df is None or len(df) == 0:
        return {
            "endpoint": endpoint,
            "trade_date": trade_date,
            "snapshot_rows": 0,
            "error": "empty snapshot",
        }
    if "ts_code" not in df.columns or key not in df.columns:
        return {
            "endpoint": endpoint,
            "trade_date": trade_date,
            "snapshot_rows": int(len(df)),
            "error": f"snapshot missing ts_code or {key}",
        }

    snapshot = {
        str(row["ts_code"]).upper(): row.to_dict()
        for _, row in df.iterrows()
        if str(row.get(key) or "") == trade_date
    }

    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    errors: list[dict[str, str]] = []
    rows_added = 0

    for idx, ts_code in enumerate(universe, start=1):
        row = snapshot.get(ts_code)
        if row is None:
            status = "missing_snapshot"
            counts[status] = counts.get(status, 0) + 1
            samples.setdefault(status, []).append(ts_code)
            continue

        path = csv_path(data_root, endpoint, ts_code)
        if path is None and create_missing_full and not dry_run:
            try:
                getattr(pro, endpoint)(ts_code=ts_code)
            except Exception as exc:  # noqa: BLE001
                errors.append({"ts_code": ts_code, "status": "create_missing_error", "error": str(exc)[:200]})
            path = csv_path(data_root, endpoint, ts_code)
        if path is None:
            status = "missing_file"
            counts[status] = counts.get(status, 0) + 1
            samples.setdefault(status, []).append(ts_code)
            continue

        result = append_snapshot_row(
            path=path,
            row=row,
            key=key,
            trade_date=trade_date,
            dry_run=dry_run,
        )
        counts[result.status] = counts.get(result.status, 0) + 1
        rows_added += result.rows_added
        if result.status not in {"already_current", "appended", "would_append"}:
            samples.setdefault(result.status, []).append(ts_code)
        if result.error:
            errors.append({"ts_code": ts_code, "status": result.status, "error": result.error[:200]})
        if idx % 200 == 0:
            print(
                f"[{endpoint}] {idx}/{len(universe)} "
                f"appended={counts.get('appended', 0)} already={counts.get('already_current', 0)}",
                flush=True,
            )

    return {
        "endpoint": endpoint,
        "trade_date": trade_date,
        "snapshot_rows": int(len(df)),
        "universe_count": len(universe),
        "rows_added": rows_added,
        "counts": dict(sorted(counts.items())),
        "samples": {k: v[:20] for k, v in samples.items()},
        "errors": errors[:50],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trade-date", help="YYYYMMDD. Defaults to latest recent daily_basic snapshot with enough rows.")
    ap.add_argument("--min-rows", type=int, default=1000)
    ap.add_argument("--lookback-days", type=int, default=10)
    ap.add_argument("--endpoints", default="daily,daily_basic,moneyflow")
    ap.add_argument("--overlays-dir", type=Path, default=ROOT / "config" / "stock_overlays")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--create-missing-full", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    os.environ.setdefault("DOCKCASE_CACHE", "1")
    os.environ.setdefault("DOCKCASE_WRITEBACK", "1")
    pro = _get_pro_api()
    if pro is None:
        raise SystemExit("TUSHARE_TOKEN is unavailable")
    data_root = dockcase_root()
    universe = load_a_share_universe(args.overlays_dir)
    if not universe:
        raise SystemExit("A-share universe is empty")

    t0 = time.time()
    trade_date, daily_basic_snapshot = resolve_trade_date(
        pro,
        args.trade_date,
        min_rows=args.min_rows,
        lookback_days=args.lookback_days,
    )
    endpoints = [e.strip() for e in args.endpoints.split(",") if e.strip()]
    unknown = [e for e in endpoints if e not in ENDPOINT_FOLDERS]
    if unknown:
        raise SystemExit(f"unsupported endpoints: {', '.join(unknown)}")

    report: dict[str, Any] = {
        "trade_date": trade_date,
        "data_root": str(data_root),
        "universe_count": len(universe),
        "dry_run": bool(args.dry_run),
        "create_missing_full": bool(args.create_missing_full),
        "endpoints": {},
    }
    for endpoint in endpoints:
        preloaded = daily_basic_snapshot if endpoint == "daily_basic" else None
        result = refresh_endpoint(
            pro=pro,
            data_root=data_root,
            endpoint=endpoint,
            trade_date=trade_date,
            universe=universe,
            preloaded_snapshot=preloaded,
            create_missing_full=args.create_missing_full,
            dry_run=args.dry_run,
        )
        report["endpoints"][endpoint] = result

    report["elapsed_s"] = round(time.time() - t0, 1)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
