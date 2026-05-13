"""Futu OpenD source for HK / US realtime data.

Honours the actual quote permissions (HK Stocks LV1 / US Stocks LV3 / no
broker_queue / no indices / no A-share) — we deliberately skip dp_ids that
would require permissions the account does not have, so SDK calls never
return "no permission" errors during normal collection.

Connection model: each ``fetch_batch`` call opens a fresh
``OpenQuoteContext``, issues one or two batched API requests, then closes.
This keeps subscription quota at 0 (we use snapshot-style calls, not
``subscribe``) and avoids long-lived state across collector ticks.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterable

log = logging.getLogger("mvp20.sources.futu")

# ---------------------------------------------------------------------------
# Code conversion: mvp20 ts_code "00700.HK" → Futu "HK.00700"
# ---------------------------------------------------------------------------


def to_futu_code(ts_code: str) -> str | None:
    """Convert ``00700.HK`` / ``NVDA.US`` / ``BRK.B.US`` to Futu format.
    Returns None for A-share / unknown suffixes (Futu has no A permission)."""

    if ts_code.endswith(".HK"):
        return "HK." + ts_code[:-3]
    if ts_code.endswith(".US"):
        # Futu uses dots in symbols too (BRK.B → BRK.B) but prefixed with US.
        return "US." + ts_code[:-3]
    return None


def from_futu_code(futu_code: str) -> str | None:
    """Reverse of to_futu_code."""

    if futu_code.startswith("HK."):
        return futu_code[3:] + ".HK"
    if futu_code.startswith("US."):
        return futu_code[3:] + ".US"
    return None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def _open_ctx(host: str = "127.0.0.1", port: int = 11111):
    """Open an OpenQuoteContext. Late-import keeps mvp20 startup free of
    futu-api dependency for users who only run mock mode."""

    from futu import OpenQuoteContext  # type: ignore

    return OpenQuoteContext(host=host, port=port)


def health_check(host: str = "127.0.0.1", port: int = 11111) -> dict:
    """Probe OpenD: returns {ok, market_states, server_version, error?}.
    Used by ``mvp20 check-futu`` CLI."""

    try:
        from futu import RET_OK  # type: ignore
    except ImportError as e:
        return {"ok": False, "error": f"futu-api not installed: {e}"}

    try:
        ctx = _open_ctx(host, port)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"open ctx failed: {e}"}

    try:
        ret, data = ctx.get_global_state()
        if ret != RET_OK:
            return {"ok": False, "error": f"get_global_state failed: {data}"}
        return {
            "ok": True,
            "server_version": data.get("server_ver"),
            "market_hk": data.get("market_hk"),
            "market_us": data.get("market_us"),
            "market_sh": data.get("market_sh"),
            "market_sz": data.get("market_sz"),
            "trade_logined": data.get("trd_logined"),
            "quote_logined": data.get("qot_logined"),
        }
    finally:
        ctx.close()


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------

# DP-ids this source is *capable* of supplying given the current permission
# matrix (HK Stocks LV1 / US Stocks LV3 — no broker_queue, no L2 deep for HK,
# no indices). Anything not in this set is skipped here and left to other
# sources or `Inactive`.
SUPPORTED_DP_IDS = {
    "L6.mult.pe",                 # was L6.priced.intraday_pe
    "L6.mult.pb",                 # was L6.priced.intraday_pb
    "L7.trade.volume_turnover",   # bundles turnover_rate + volume_ratio
    "L7.flow.active_inflow",      # bundles main_net + big_orders_net
    "L7.market.l2_quote",         # US LV3 only; HK gets nominal price snapshot
    "L7.market.tick_count_5min",
}


def _safe(d: dict, key: str):
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return v


def fetch_batch(
    constituents: Iterable[dict],
    tick: int,
    host: str = "127.0.0.1",
    port: int = 11111,
    skip_capital_flow: bool = False,
) -> list[tuple]:
    """Pull a snapshot of every HK / US constituent from OpenD.

    Returns rows ready for ``upsert_realtime``::

        (ts_code, dp_id, value, data_status, confidence, source, updated_at)

    A-share rows (``.SH/.SZ/.BJ``) are silently skipped (no permission).
    """

    from futu import RET_OK  # type: ignore

    # Build the Futu code → ts_code map for HK + US only
    futu_codes: list[str] = []
    futu_to_ts: dict[str, str] = {}
    for c in constituents:
        ts_code = c.get("ts_code")
        if not ts_code:
            continue
        fc = to_futu_code(ts_code)
        if fc is None:
            continue
        futu_codes.append(fc)
        futu_to_ts[fc] = ts_code

    if not futu_codes:
        return []

    now = int(time.time())
    rows: list[tuple] = []
    ctx = _open_ctx(host, port)
    try:
        # ── Market snapshot (one batched call, ~all PE/PB/turnover) ──
        # Futu caps each get_market_snapshot at 400 codes; chunk if needed.
        CHUNK = 200
        snapshots: list[dict] = []
        for i in range(0, len(futu_codes), CHUNK):
            chunk = futu_codes[i:i + CHUNK]
            ret, snap = ctx.get_market_snapshot(chunk)
            if ret != RET_OK:
                log.warning("get_market_snapshot failed for chunk: %s", snap)
                continue
            # snap is a DataFrame in newer SDKs; normalise to list[dict]
            snapshots.extend(snap.to_dict(orient="records"))

        for snap_row in snapshots:
            fc = snap_row.get("code")
            ts_code = futu_to_ts.get(fc)
            if not ts_code:
                continue

            pe = _safe(snap_row, "pe_ratio")
            pb = _safe(snap_row, "pb_ratio")
            turnover = _safe(snap_row, "turnover")
            turnover_rate = _safe(snap_row, "turnover_rate")

            # spec-aligned dp_ids
            for dp_id, val in (("L6.mult.pe", pe), ("L6.mult.pb", pb)):
                if val is None:
                    continue
                rows.append((
                    ts_code, dp_id,
                    json.dumps({"scalar": float(val), "unit": "ratio",
                                "intraday": True},
                               ensure_ascii=False),
                    "Known", 0.9, "futu:snapshot", now,
                ))
            # bundle turnover + turnover_rate into spec L7.trade.volume_turnover
            if turnover is not None or turnover_rate is not None:
                rows.append((
                    ts_code, "L7.trade.volume_turnover",
                    json.dumps({
                        "turnover_ccy": float(turnover) if turnover is not None else None,
                        "turnover_rate_pct": float(turnover_rate) if turnover_rate is not None else None,
                    }, ensure_ascii=False),
                    "Known", 0.9, "futu:snapshot", now,
                ))

            # L7.market.l2_quote — emit the bid/ask top of book for US LV3 / HK LV1
            quote = {
                "bid": _safe(snap_row, "bid_price"),
                "ask": _safe(snap_row, "ask_price"),
                "bid_size": _safe(snap_row, "bid_vol"),
                "ask_size": _safe(snap_row, "ask_vol"),
                "last": _safe(snap_row, "last_price"),
            }
            if any(v is not None for v in quote.values()):
                rows.append((
                    ts_code, "L7.market.l2_quote",
                    json.dumps(quote, ensure_ascii=False),
                    "Known", 0.9, "futu", now,
                ))

        # ── Capital flow (per-code; one HTTP call each) ──
        # Default-on but can be skipped to keep the cycle fast.
        if not skip_capital_flow:
            for fc, ts_code in futu_to_ts.items():
                ret, cf = ctx.get_capital_flow(fc, period_type="INTRADAY")
                if ret != RET_OK:
                    continue
                records = cf.to_dict(orient="records") if hasattr(cf, "to_dict") else cf
                if not records:
                    continue
                # The most recent record
                last = records[-1]
                main_net = _safe(last, "main_in_flow") or _safe(last, "in_flow_active")
                total_net = _safe(last, "in_flow")
                if main_net is not None or total_net is not None:
                    # spec L7.flow.active_inflow bundles total + main net inflow
                    rows.append((
                        ts_code, "L7.flow.active_inflow",
                        json.dumps({
                            "main_net": float(main_net) if isinstance(main_net, (int, float)) else None,
                            "total_net": float(total_net) if isinstance(total_net, (int, float)) else None,
                            "unit": "ccy",
                        }, ensure_ascii=False),
                        "Known", 0.85, "futu:capital_flow", now,
                    ))
    finally:
        ctx.close()

    return rows
