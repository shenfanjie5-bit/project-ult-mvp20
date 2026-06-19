#!/usr/bin/env python3
"""Realtime data collector daemon.

Loops every ``--interval`` seconds (default 60 = minute-level), pulls a batch
of realtime field values from configured data sources, UPSERTs them into
``runtime/hot.sqlite``. In phase 2 it will also append to Parquet under
``runtime/history/`` (see ``--enable-history``).

Phase-1 wiring: the ``--source mock`` mode generates deterministic mock values
for every (ts_code in mvp20.universe.yaml, dp_id in REALTIME_DP_IDS) — useful
for testing the full pipeline before plugging real Tushare/Futu adapters.

Real sources:
- ``--source tushare`` (full A-share Tushare refresh) — needs ``tushare`` pkg
- focused Tushare routes such as ``tushare-core``, ``tushare-macro``,
  ``tushare-report-rc``, ``tushare-report-signals``,
  ``tushare-earnings-risk``, ``tushare-industry-valuation`` and
  ``tushare-preprice``
- ``--source futu`` (HK/US options / L2 quote) — needs Futu OpenD running
- ``--source fmp`` (US fundamentals) — needs ``FMP_API_KEY``
- ``--source akshare`` (A-share news / 公告 / 雪球热度 / 概念板块) — pip pkg only
- focused AKShare routes such as ``akshare-block-trade`` and ``akshare-cls``
- ``--source real`` / ``--source all`` — composes focused production sources

Run with::

    .venv/bin/python scripts/collector.py --source mock --interval 60
"""

from __future__ import annotations

import argparse
import json
import math
import os
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

# Sentinel data_status for fabricated (mock/offline) rows. A fake value must
# NEVER carry "Known" — downstream consumers (spec checker, derive upstream
# pass, aggregator/coverage, server `WHERE data_status = 'Known'`) treat
# "Known" as real, trustworthy data. "Mock" is deliberately outside that set
# so fabricated rows can seed the pipeline without ever being scored as real.
#
# Note: "Mock" is also deliberately NOT "Inactive". ``compute_data_coverage``
# (mvp20/coverage.py) counts ``data_status in {'Known','Inactive'}`` toward the
# "known" weight, so tagging fabricated rows ``Inactive`` would silently inflate
# coverage. ``Mock`` keeps them out of BOTH the score (via the source-aware
# ``mock:*`` guard in derive.py / aggregator.py) and the coverage numerator.
MOCK_DATA_STATUS = "Mock"

# ---------------------------------------------------------------------------
# Production dev-gate for fabricated (mock) data
# ---------------------------------------------------------------------------
#
# Mock rows are fabricated sine-wave placeholders. They must NEVER feed a
# production score. Two layers defend against that:
#
#   1. Read-side (already present, owned by a parallel task): every score-read
#      path drops rows whose ``source`` starts ``"mock:"`` — see
#      ``mvp20.derive._read_realtime_value_with_source`` and
#      ``mvp20.aggregator.synthesize_realtime_nodes``. So even legacy ``mock:*``
#      rows already sitting in ``runtime/hot.sqlite`` cannot reach the score.
#
#   2. Emission-side (this gate): in PRODUCTION mode the collector daemon
#      refuses to run a mock data source at all, so no new fabricated rows are
#      written to the production DB. Mock collection is opt-in via an explicit
#      flag, so it never happens by accident on a prod host.
#
# Default = production = mock excluded. Opt in with either:
#   - env  ``MVP20_ALLOW_MOCK=1``           (truthy: 1/true/yes/on)
#   - CLI  ``--allow-mock``
#
# Hermetic tests that legitimately exercise the mock path (e.g. the collector
# supervisor smoke test, or direct ``fetch_mock_batch`` unit tests) set the
# flag / call the fetcher directly — they are unaffected. ``fetch_mock_batch``
# itself is intentionally NOT gated (it is a pure fixture helper imported by
# tests); the gate lives at the daemon boundary in ``main()``.
MOCK_GATE_ENV = "MVP20_ALLOW_MOCK"

# Source names whose fetcher fabricates mock rows (vs. pulling a real feed).
# Only ``mock`` today; ``real``/``all`` compose strictly real sources.
MOCK_SOURCE_NAMES = frozenset({"mock"})

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _mock_allowed(cli_allow_mock: bool) -> bool:
    """Return True when fabricated mock collection is permitted.

    Production default is False (mock excluded). Permitted only when the
    operator explicitly opts in via ``--allow-mock`` or a truthy
    ``MVP20_ALLOW_MOCK`` env var. Pure + env-driven so it is trivially
    unit-testable.
    """

    if cli_allow_mock:
        return True
    return os.environ.get(MOCK_GATE_ENV, "").strip().lower() in _TRUTHY

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
    #
    # IMPORTANT: dp_ids that already have a REAL emitter must NOT appear here.
    # The mock fetcher upserts on PRIMARY KEY (ts_code, dp_id), so a fabricated
    # row would silently overwrite real data. The following were intentionally
    # REMOVED because a real source emits them:
    #   L6.mult.pe / L6.mult.pb        → tushare_source (daily_basic)
    #   L6.priced.crowdedness          → tushare_source (turnover percentile)
    #   L7.flow.active_inflow          → tushare_source (moneyflow)
    #   L7.flow.passive_northbound     → tushare_source (hk_hold)
    #   L7.trade.volume_turnover       → tushare_source (turnover_rate + volume_ratio)
    #   L7.flow.margin_balance         → tushare_source (margin 融资余额, ~line 1245)
    #   L7.mood.theme / media_social   → akshare_source (EM hot-rank / concept tags)
    #   L9.event.intraday_news         → akshare_source (EM news headlines)
    #   L9.event.intraday_announcement → akshare_source (Cninfo / EM announcements)
    #   L9.media.social_buzz           → akshare_source (雪球 关注/分享 heat)
    #   L11.trade.signal               → recomputed by derive_l11_trade_signal
    #                                    (participates_in_score: false in
    #                                     config/data_point_roles.yaml)
    #
    # The dp_ids below have NO real emitter wired yet (futu OpenD / BFF are not
    # live in this environment, and intraday_block_trade has no source at all),
    # so the mock fetcher still seeds them — but with data_status="Mock"
    # (see fetch_mock_batch), never "Known".
    ("L7.market.l2_quote", "futu"),
    ("L7.market.tick_count_5min", "futu"),
    ("L9.event.intraday_block_trade", "n/a"),
    ("L11.short_term", "mvp20-bff"),
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
                MOCK_DATA_STATUS,       # never "Known" — fabricated value
                0.55,                   # mock confidence
                f"mock:{source_hint}",
                now,
            ))
    return rows


def fetch_tushare_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull A-share daily/EOD from Tushare (PE/PB/turnover/资金流 + 北向)."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_batch(universe, tick)


def fetch_tushare_core_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only fast A-share market/flow rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_core_batch(universe, tick)


def fetch_tushare_report_rc_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only A-share sell-side forecast/report rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_report_rc_constituents_batch(universe, tick)


def fetch_tushare_report_signals_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only A-share report_rc-derived score signal rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_report_rc_signal_constituents_batch(universe, tick)


def fetch_tushare_crowding_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only A-share turnover-history crowdedness rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_crowding_batch(universe, tick)


def fetch_tushare_market_env_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only A-share market-level environment sentinel rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_market_env_batch(universe, tick)


def fetch_tushare_macro_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull China macro and industry sentinel rows from Tushare."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_macro_china_batch(int(time.time()))


def fetch_tushare_preprice_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only A-share forecast pre-announcement price run-up rows."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_preprice_surprise_constituents_batch(
        universe, tick,
    )


def fetch_tushare_earnings_risk_batch(
    universe: list[dict], tick: int,
) -> list[tuple]:
    """Pull only A-share earnings surprise / financial-risk event rows."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_earnings_risk_constituents_batch(
        universe, tick,
    )


def fetch_tushare_industry_valuation_batch(
    universe: list[dict], tick: int,
) -> list[tuple]:
    """Pull only A-share industry valuation compression sentinel rows."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_industry_valuation_constituents_batch(
        universe, tick,
    )


def fetch_tushare_akshare_replacement_batch(
    universe: list[dict], tick: int,
) -> list[tuple]:
    """Pull the 8 dp_ids re-pointed from akshare onto permitted Tushare
    endpoints (announcement / heat / theme / sector / commodity / outflow)."""

    from mvp20.sources import tushare_source
    return tushare_source.fetch_akshare_replacement_batch(universe, tick)


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


def fetch_akshare_block_trade_batch(
    universe: list[dict], tick: int,
) -> list[tuple]:
    """Pull only A-share block-trade event rows from AKShare."""

    from mvp20.sources import akshare_source

    a_codes = [
        c["ts_code"] for c in universe
        if c.get("ts_code") and akshare_source.is_a_share(c["ts_code"])
    ]
    return akshare_source.fetch_l9_capital_etf_block(a_codes, int(time.time()))


def fetch_akshare_cls_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Pull only CLS market-level media/policy/risk sentinel rows."""

    from mvp20.sources import akshare_source
    return akshare_source.fetch_cls_telegraph_batch(int(time.time()))


def fetch_real_batch(universe: list[dict], tick: int) -> list[tuple]:
    """Dispatch per market + free aggregator:
       - A-share → focused Tushare paths (core/market/macro/crowding/report)
       - HK/US   → Futu OpenD (PE/PB/turnover/资金流/L2 quote)
       - US      → FMP (financial statements / valuation multiples)
       - A-share → akshare (news / 公告 / 雪球热度 / 概念板块)

    This is the production path. Each source's failure is caught per-source
    and logged; the collector cycle continues so partial outages don't kill the
    whole pipeline. The full ``--source tushare`` path is intentionally kept as
    a separate low-frequency/manual refresh because it calls slower financial
    statement endpoints. Low-frequency market/macro rows stay in ``real`` so
    normal runtime refreshes keep industry/market sentinels current.
    """

    rows: list[tuple] = []
    for label, fn in (
        ("tushare-core", fetch_tushare_core_batch),
        ("tushare-market-env", fetch_tushare_market_env_batch),
        ("tushare-macro", fetch_tushare_macro_batch),
        ("tushare-crowding", fetch_tushare_crowding_batch),
        ("tushare-report-rc", fetch_tushare_report_rc_batch),
        ("tushare-report-signals", fetch_tushare_report_signals_batch),
        ("tushare-industry-valuation", fetch_tushare_industry_valuation_batch),
        ("tushare-akshare-repl", fetch_tushare_akshare_replacement_batch),
        ("futu", fetch_futu_batch),
        ("fmp", fetch_fmp_batch),
        ("akshare", fetch_akshare_batch),
    ):
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
    "tushare-core": fetch_tushare_core_batch,
    "tushare-report-rc": fetch_tushare_report_rc_batch,
    "tushare-report-signals": fetch_tushare_report_signals_batch,
    "tushare-earnings-risk": fetch_tushare_earnings_risk_batch,
    "tushare-industry-valuation": fetch_tushare_industry_valuation_batch,
    "tushare-crowding": fetch_tushare_crowding_batch,
    "tushare-market-env": fetch_tushare_market_env_batch,
    "tushare-macro": fetch_tushare_macro_batch,
    "tushare-preprice": fetch_tushare_preprice_batch,
    "tushare-akshare-repl": fetch_tushare_akshare_replacement_batch,
    "futu": fetch_futu_batch,
    "fmp": fetch_fmp_batch,
    "akshare": fetch_akshare_batch,
    "akshare-block-trade": fetch_akshare_block_trade_batch,
    "akshare-cls": fetch_akshare_cls_batch,
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
    parser.add_argument(
        "--allow-mock", action="store_true",
        help=(
            "Permit fabricated mock data collection (default OFF in "
            "production). Also enableable via the MVP20_ALLOW_MOCK env var. "
            "Fabricated rows never reach the score (source-aware mock guard), "
            "but in production the daemon refuses to write them at all."
        ),
    )
    args = parser.parse_args()

    # One wedged HTTP read must not hang a collection cycle forever (the same
    # no-timeout tushare-client failure observed in the derive chain): with a
    # global default timeout a stuck call raises inside the per-source fetcher
    # (which catches per-endpoint) and the cycle moves on.
    import socket
    socket.setdefaulttimeout(60)

    # Production dev-gate: refuse fabricated mock sources unless explicitly
    # allowed. This stops mock rows from ever being written to a production
    # hot.sqlite. The read-side mock guard (derive/aggregator) is the second
    # line of defence for any legacy rows already in the DB.
    if args.source in MOCK_SOURCE_NAMES and not _mock_allowed(args.allow_mock):
        print(
            f"[collector] REFUSED: --source {args.source} fabricates mock data "
            f"and is disabled in production. Set {MOCK_GATE_ENV}=1 or pass "
            f"--allow-mock to enable it (dev/test only).",
            file=sys.stderr,
            flush=True,
        )
        return 2

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
