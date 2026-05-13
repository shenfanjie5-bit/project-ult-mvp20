#!/usr/bin/env python3
"""Realtime data collector daemon.

Loops every ``--interval`` seconds (default 60 = minute-level), pulls a batch
of realtime field values from configured data sources, UPSERTs them into
``runtime/hot.sqlite``. In phase 2 it will also append to Parquet under
``runtime/history/`` (see ``--enable-history``).

Phase-1 wiring: the ``--source mock`` mode generates deterministic mock values
for every (ts_code in mvp20.universe.yaml, dp_id in REALTIME_DP_IDS) — useful
for testing the full pipeline before plugging real Tushare/Futu adapters.

Real sources will be added incrementally:
- ``--source tushare`` (A-share moneyflow / volume) — needs ``tushare`` pkg
- ``--source futu`` (HK/US options / L2 quote) — needs Futu OpenD running
- ``--source fmp`` (US fundamentals) — needs ``FMP_API_KEY``
- ``--source akshare`` (A-share news / 公告 / 雪球热度 / 概念板块) — pip pkg only
- ``--source real`` / ``--source all`` — composes every source above

Run with::

    .venv/bin/python scripts/collector.py --source mock --interval 60
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from mvp20.sources import load_dotenv  # noqa: E402
from mvp20.storage import upsert_realtime, init_db, update_freshness  # noqa: E402

# Load TUSHARE_TOKEN / FUTU_OPEND_PASSWORD / etc. from .env (idempotent;
# os.environ overrides take precedence).
load_dotenv()

# ---------------------------------------------------------------------------
# Data points the collector is responsible for (the ~30 minute-level fields
# from the v2 spec; see docs/data_sources/coverage_audit.md §7).
# ---------------------------------------------------------------------------

REALTIME_DP_IDS: list[tuple[str, str]] = [
    # (dp_id, primary_source_hint)
    #
    # Options-related dp_ids (L7.trade.iv / L7.trade.options_cp /
    # L7.trade.gamma / L7.options.chain / L7.options.oi_change) are
    # intentionally excluded — options ingestion will be wired in a
    # separate later phase and is NOT collected by mvp20 today. The schema
    # slots still exist in stock_overlays so codex marks them
    # ``data_status: Inactive`` until that phase ships.
    #
    # L7.flow.broker_queue_hk also excluded — current Futu account has
    # only HK Stocks LV1, broker queue requires LV2 BMP.
    # spec-aligned dp_ids (renamed from L6.priced.intraday_*/L7.flow.netbuy/L7.trade.turnover_pct)
    ("L6.mult.pe", "tushare/futu/fmp"),
    ("L6.mult.pb", "tushare/futu/fmp"),
    ("L6.priced.crowdedness", "futu"),
    ("L7.flow.active_inflow", "tushare/futu"),    # bundles main_net + 大单 net
    ("L7.flow.passive_northbound", "tushare"),
    ("L7.flow.margin_balance", "tushare"),
    ("L7.trade.volume_turnover", "tushare/futu"), # bundles turnover_rate + volume_ratio
    ("L7.market.l2_quote", "futu"),
    ("L7.market.tick_count_5min", "futu"),
    ("L7.mood.theme", "akshare"),
    ("L7.mood.media_social", "akshare"),
    ("L9.event.intraday_news", "akshare"),
    ("L9.event.intraday_announcement", "tushare"),
    ("L9.event.intraday_block_trade", "tushare"),
    ("L9.media.social_buzz", "akshare"),
    ("L11.short_term", "mvp20-bff"),
    ("L11.trade.signal", "mvp20-bff"),
]


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------


def load_universe(universe_path: Path) -> list[dict]:
    """Read constituents from mvp20.universe.yaml."""

    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    return list(payload.get("constituents") or [])


def _mock_value(ts_code: str, dp_id: str, tick: int) -> dict:
    """Deterministic mock: sin wave per (ts_code, dp_id), shifted by tick."""

    seed = abs(hash((ts_code, dp_id))) % 10_000
    phase = (tick * 0.1 + seed * 0.001)
    amplitude = 100.0 + (seed % 50)
    value = amplitude * (math.sin(phase) + 1) / 2  # 0..2*amplitude
    return {
        "scalar": round(value, 4),
        "unit": "mock",
        "tick": tick,
    }


def fetch_mock_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Generate one minute's worth of mock data for every (ts_code, dp_id).
    Returns rows ready for ``upsert_realtime``."""

    now = int(time.time())
    rows: list[tuple] = []
    for c in universe:
        ts_code = c.get("ts_code")
        if not ts_code:
            continue
        for dp_id, source_hint in REALTIME_DP_IDS:
            value = _mock_value(ts_code, dp_id, tick)
            rows.append((
                ts_code, dp_id,
                json.dumps(value, ensure_ascii=False),
                "Known",
                0.55,                   # mock confidence
                f"mock:{source_hint}",
                now,
            ))
    return rows


def fetch_tushare_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull A-share daily/EOD from Tushare (PE/PB/turnover/资金流 + 北向)."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_batch(universe, tick)


def fetch_futu_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull HK + US snapshot/capital-flow from Futu OpenD."""

    from mvp20.sources import futu_source
    return futu_source.fetch_batch(universe, tick)


def fetch_fmp_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull US fundamentals/multiples from FMP Starter."""

    from mvp20.sources import fmp_source
    return fmp_source.fetch_batch(universe, tick)


def fetch_akshare_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull A-share news/公告/concept-tag/Xueqiu heat from akshare."""

    from mvp20.sources import akshare_source
    return akshare_source.fetch_batch(universe, tick)


def fetch_real_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Dispatch per market + free aggregator:
       - A-share → Tushare (PE/PB/turnover/资金流)
       - HK/US   → Futu OpenD (PE/PB/turnover/资金流/L2 quote)
       - US      → FMP (financial statements / valuation multiples)
       - A-share → akshare (news / 公告 / 雪球热度 / 概念板块)

    This is the production path. Each source's failure is caught per-source
    and logged; the collector cycle continues so partial outages don't kill
    the whole pipeline."""

    rows: list[tuple] = []
    for label, fn in (("tushare", fetch_tushare_batch),
                       ("futu", fetch_futu_batch),
                       ("fmp", fetch_fmp_batch),
                       ("akshare", fetch_akshare_batch)):
        try:
            new_rows = fn(universe, tick)
            rows.extend(new_rows)
            print(f"[collector]   {label}: {len(new_rows)} rows", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[collector]   {label}: FAILED ({exc})", flush=True)
    return rows


SOURCE_DISPATCH = {
    "mock": fetch_mock_batch,
    "tushare": fetch_tushare_batch,
    "futu": fetch_futu_batch,
    "fmp": fetch_fmp_batch,
    "akshare": fetch_akshare_batch,
    "real": fetch_real_batch,
    "all": fetch_real_batch,  # alias — "all" composes every wired source
}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=sorted(SOURCE_DISPATCH.keys()), default="mock",
        help="Data source (mock = generate deterministic test data).",
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Seconds between collection cycles (default 60 = minute).",
    )
    parser.add_argument(
        "--universe", type=Path, default=ROOT / "config" / "mvp20.universe.yaml",
        help="Path to constituents universe YAML.",
    )
    parser.add_argument(
        "--hot-db", type=Path, default=ROOT / "runtime" / "hot.sqlite",
        help="Path to SQLite hot snapshot database.",
    )
    parser.add_argument(
        "--enable-history", action="store_true",
        help="Also append every batch to Parquet history (phase 2).",
    )
    parser.add_argument(
        "--history-dir", type=Path, default=ROOT / "runtime" / "history",
        help="Parquet history directory (phase 2).",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=0,
        help="Stop after N cycles (0 = forever). Useful for tests.",
    )
    args = parser.parse_args()

    init_db(args.hot_db)
    universe = load_universe(args.universe)
    fetcher = SOURCE_DISPATCH[args.source]
    print(f"[collector] source={args.source} interval={args.interval}s "
          f"universe={len(universe)} constituents dp_ids={len(REALTIME_DP_IDS)}",
          flush=True)

    history_writer = None
    if args.enable_history:
        try:
            from mvp20.history import append_minute_parquet  # noqa: F401
            history_writer = append_minute_parquet
            print(f"[collector] history enabled → {args.history_dir}", flush=True)
        except ImportError as e:
            print(f"[collector] WARN: --enable-history but mvp20.history not "
                  f"available ({e}); continuing without history", flush=True)

    running = True

    def stop(*_):
        nonlocal running
        running = False
        print("[collector] received stop signal", flush=True)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    tick = 0
    while running:
        t0 = time.time()
        batch = fetcher(universe, tick)
        if batch:
            n = upsert_realtime(args.hot_db, batch)
            update_freshness(args.hot_db, layer="realtime", sync_status="ok",
                             is_full=True)
            if history_writer is not None:
                try:
                    out_path = history_writer(args.history_dir, batch)
                    print(f"[collector] tick={tick} upserted={n} parquet={out_path.name}",
                          flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"[collector] tick={tick} upserted={n} parquet=FAILED({exc})",
                          flush=True)
            else:
                print(f"[collector] tick={tick} upserted={n}", flush=True)
        else:
            print(f"[collector] tick={tick} empty batch", flush=True)

        tick += 1
        if args.max_cycles and tick >= args.max_cycles:
            print(f"[collector] reached --max-cycles {args.max_cycles}", flush=True)
            break

        elapsed = time.time() - t0
        remaining = max(0.0, args.interval - elapsed)
        # Sleep in small slices so SIGTERM is responsive.
        slept = 0.0
        while slept < remaining and running:
            chunk = min(1.0, remaining - slept)
            time.sleep(chunk)
            slept += chunk

    print("[collector] stopped cleanly", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
