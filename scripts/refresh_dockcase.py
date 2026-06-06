"""Freshen existing DockCase files for the in-use A-shares — append the recent
delta (new quarterly filings / trading days) to each (endpoint, ts_code) existing
file via ``dockcase_cache.refresh_existing`` (strictly-newer append, preserves all
existing rows + format). Read+append only; missing-stock files are left to the
write-back path. Honors "增量追加到对应文件".

Usage:
    python scripts/refresh_dockcase.py --concurrency 3
    python scripts/refresh_dockcase.py --codes 600519.SH,000001.SZ
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UNIVERSE = ROOT / "config" / "mvp20.universe.yaml"
_A_SUFFIX = (".SH", ".SZ", ".BJ")


def _a_share_codes() -> list[str]:
    uni = yaml.safe_load(UNIVERSE.read_text(encoding="utf-8")) or {}
    return [c["ts_code"] for c in uni.get("constituents", [])
            if str(c.get("ts_code", "")).upper().endswith(_A_SUFFIX)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--codes", default=None)
    ap.add_argument("--throttle", type=float, default=0.08)
    args = ap.parse_args()

    from mvp20.sources import dockcase_cache as dc, tushare_source as tsrc

    # Unwrapped LIVE pro for the delta fetches (set CACHE=0 only across this call
    # so _get_pro_api returns the raw pro), then re-enable so refresh_existing's
    # writeback_enabled()/available() gate is satisfied while it writes.
    os.environ["DOCKCASE_CACHE"] = "0"
    real = tsrc._get_pro_api()
    os.environ["DOCKCASE_CACHE"] = "1"
    if real is None:
        print("FATAL: no tushare pro (token?)"); return

    codes = [c.strip() for c in args.codes.split(",")] if args.codes else _a_share_codes()
    eps = sorted(dc.CACHEABLE_ENDPOINTS)
    conc = max(1, min(args.concurrency, 6))
    print(f"== refresh DockCase: {len(codes)} A-shares × {len(eps)} endpoints, "
          f"concurrency={conc} ==", flush=True)

    lock = threading.Lock()
    tot = {"rows": 0, "stocks": 0, "files": 0, "done": 0}

    def work(ts_code: str) -> tuple[str, int, int]:
        added = files = 0
        for ep in eps:
            try:
                n = dc.refresh_existing(ep, ts_code, getattr(real, ep))
                if n:
                    added += n
                    files += 1
            except Exception:  # noqa: BLE001
                pass
            time.sleep(args.throttle)
        return ts_code, added, files

    with ThreadPoolExecutor(max_workers=conc) as ex:
        futs = {ex.submit(work, c): c for c in codes}
        for fut in as_completed(futs):
            ts_code, added, files = fut.result()
            with lock:
                tot["done"] += 1
                if added:
                    tot["rows"] += added; tot["stocks"] += 1; tot["files"] += files
                if tot["done"] % 50 == 0 or added:
                    print(f"[{tot['done']}/{len(codes)}] {ts_code} +{added}行/{files}文件 "
                          f"| 累计 {tot['stocks']}股 {tot['files']}文件 {tot['rows']}行", flush=True)

    print(f"\n== refresh done: {tot['stocks']} 股更新, {tot['files']} 文件追加, "
          f"{tot['rows']} 行新增 ==", flush=True)


if __name__ == "__main__":
    main()
