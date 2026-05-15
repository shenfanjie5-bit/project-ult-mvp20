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
from datetime import datetime, timedelta, timezone
from typing import Iterable

log = logging.getLogger("mvp20.sources.futu")

# ---------------------------------------------------------------------------
# Module-level caches for options ingestion (per-ts_code, 10 min TTL).
# Keyed by ts_code (e.g. "00700.HK"); value = (timestamp, payload_dict).
# Payload schema: see _fetch_atm_option_snapshot for the dict shape.
# ---------------------------------------------------------------------------

_OPTION_CACHE_TTL_S = 600
_OPTION_CHAIN_CACHE: dict[str, tuple[int, dict | None]] = {}

# IV percentile thresholds used by L7.trade.iv when 30-day history is
# unavailable (we have no minute-bar option archive yet). >40% = high, <15%
# = low. Any IV in between emits Inactive (event hasn't triggered).
_IV_HIGH_THRESHOLD = 40.0
_IV_LOW_THRESHOLD = 15.0

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
    # ---- Bucket A options (HK + US only; A-share options ignored) ----
    "L6.priced.iv",                # ATM IV snapshot
    "L7.trade.iv",                 # IV event state (high/low/normal)
    "L7.trade.options_cp",         # Call/Put volume + open-interest ratio
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

        # ── Bucket A: options-derived dp_ids (HK + US) ─────────────────
        # Re-use the same ctx; each fetcher is TTL-cached so cost per cycle
        # is bounded.  Each call is wrapped so a broken contract code never
        # blocks the rest of the batch (or the next fetcher).
        options_constituents = [{"ts_code": ts} for ts in futu_to_ts.values()]
        try:
            rows.extend(fetch_l6_priced_iv(options_constituents, now, ctx=ctx))
        except Exception as e:  # noqa: BLE001
            log.warning("[futu] l6_priced_iv FAILED: %s", e)
        try:
            rows.extend(fetch_l7_trade_iv(options_constituents, now, ctx=ctx))
        except Exception as e:  # noqa: BLE001
            log.warning("[futu] l7_trade_iv FAILED: %s", e)
        try:
            rows.extend(fetch_l7_trade_options_cp(options_constituents, now, ctx=ctx))
        except Exception as e:  # noqa: BLE001
            log.warning("[futu] l7_trade_options_cp FAILED: %s", e)
    finally:
        ctx.close()

    return rows


# ---------------------------------------------------------------------------
# Options (Bucket A) — three dp_ids on top of the spot/flow batch.
# ---------------------------------------------------------------------------


def _emit_options_inactive(ts_code: str, dp_id: str, reason: str,
                           now: int, source: str = "futu:option_chain") -> tuple:
    """Build a 7-tuple Inactive row for options fetchers that couldn't
    reach OpenD / lacked permission / found no chain data."""

    return (
        ts_code, dp_id,
        json.dumps({"reason": reason}, ensure_ascii=False),
        "Inactive", 0.0, source, now,
    )


def _as_of_iso(now: int | None = None) -> str:
    """ISO-8601 UTC timestamp; used in payload "as_of" fields."""

    ts = now if now is not None else int(time.time())
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _open_ctx_safe(host: str, port: int):
    """Open a Quote context, returning None if futu-api is missing or OpenD
    is unreachable. Never raises — options fetchers must degrade to Inactive."""

    try:
        return _open_ctx(host, port)
    except ImportError as e:
        log.info("[futu] options skipped — futu-api not installed: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("[futu] options skipped — OpenD connect failed: %s", e)
        return None


def _fetch_atm_option_snapshot(ctx, futu_code: str, ts_code: str,
                               now: int) -> dict | None:
    """Fetch ATM call + put market_snapshot for the nearest expiry.

    Returns a dict::

        {
            "spot": float,
            "expiry": "YYYY-MM-DD",
            "atm_strike": float,
            "atm_call": {code, iv, volume, open_interest, last_price},
            "atm_put":  {code, iv, volume, open_interest, last_price},
            "chain_summary": {
                "call_volume": int, "put_volume": int,
                "call_oi": int,     "put_oi": int,
                "n_calls": int,     "n_puts": int,
            },
        }

    Or ``None`` if any step fails / data is empty. The result is cached per
    ts_code with TTL=``_OPTION_CACHE_TTL_S``. Callers must NOT raise from
    here — every fetch is wrapped in try/except.
    """

    cached = _OPTION_CHAIN_CACHE.get(ts_code)
    if cached is not None and (now - cached[0]) < _OPTION_CACHE_TTL_S:
        return cached[1]

    payload: dict | None
    try:
        from futu import RET_OK  # type: ignore
    except ImportError:
        payload = None
        _OPTION_CHAIN_CACHE[ts_code] = (now, payload)
        return payload

    try:
        # 1. spot price for the underlying
        ret, snap = ctx.get_market_snapshot([futu_code])
        if ret != RET_OK:
            log.info("[futu] snapshot %s failed: %s", futu_code, snap)
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None
        snap_rows = snap.to_dict(orient="records") if hasattr(snap, "to_dict") else snap
        if not snap_rows:
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None
        spot = _safe(snap_rows[0], "last_price")
        if not isinstance(spot, (int, float)) or spot <= 0:
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None

        # 2. nearest expiry — first row from get_option_expiration_date
        ret, exp_df = ctx.get_option_expiration_date(futu_code)
        if ret != RET_OK:
            log.info("[futu] expiration %s failed: %s", futu_code, exp_df)
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None
        exp_rows = exp_df.to_dict(orient="records") if hasattr(exp_df, "to_dict") else exp_df
        future_exps = [
            r for r in exp_rows
            if (r.get("option_expiry_date_distance") or 0) > 0
        ]
        if not future_exps:
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None
        # Choose the nearest future expiry.
        future_exps.sort(key=lambda r: r.get("option_expiry_date_distance") or 9999)
        expiry = future_exps[0].get("strike_time")
        if not isinstance(expiry, str):
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None

        # 3. option chain for that expiry (start=end=expiry)
        ret, chain_df = ctx.get_option_chain(futu_code, start=expiry, end=expiry)
        if ret != RET_OK:
            log.info("[futu] option_chain %s @ %s failed: %s",
                     futu_code, expiry, chain_df)
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None
        chain_rows = chain_df.to_dict(orient="records") if hasattr(chain_df, "to_dict") else chain_df
        if not chain_rows:
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None

        calls = [r for r in chain_rows if r.get("option_type") == "CALL"]
        puts = [r for r in chain_rows if r.get("option_type") == "PUT"]
        if not calls or not puts:
            _OPTION_CHAIN_CACHE[ts_code] = (now, None)
            return None

        # 4. ATM = strike closest to spot for both call and put
        def _by_dist(row):
            try:
                return abs(float(row.get("strike_price", 0)) - float(spot))
            except (TypeError, ValueError):
                return float("inf")

        atm_call_row = min(calls, key=_by_dist)
        atm_put_row = min(puts, key=_by_dist)
        atm_call_code = atm_call_row.get("code")
        atm_put_code = atm_put_row.get("code")
        atm_strike = _safe(atm_call_row, "strike_price") or _safe(atm_put_row, "strike_price")

        # 5. one batched snapshot for ATM contracts + all chain contracts
        #    (one call so we get volume + OI + IV at the same time for the
        #    aggregate C/P ratio too). Chunk if needed — Futu caps at 400.
        all_codes = [r.get("code") for r in chain_rows if r.get("code")]
        CHUNK = 200
        opt_snap_rows: list[dict] = []
        for i in range(0, len(all_codes), CHUNK):
            chunk = all_codes[i:i + CHUNK]
            ret, opt_snap = ctx.get_market_snapshot(chunk)
            if ret != RET_OK:
                log.info("[futu] option market_snapshot failed: %s", opt_snap)
                continue
            opt_snap_rows.extend(opt_snap.to_dict(orient="records") if hasattr(opt_snap, "to_dict") else opt_snap)
            time.sleep(0.2)  # polite pacing between chunks

        by_code = {r.get("code"): r for r in opt_snap_rows}

        def _opt_payload(row: dict | None) -> dict:
            if not row:
                return {"code": None, "iv": None, "volume": None,
                        "open_interest": None, "last_price": None}
            return {
                "code": row.get("code"),
                "iv": _safe(row, "option_implied_volatility"),
                "volume": _safe(row, "volume"),
                "open_interest": _safe(row, "option_open_interest"),
                "last_price": _safe(row, "last_price"),
            }

        atm_call = _opt_payload(by_code.get(atm_call_code))
        atm_put = _opt_payload(by_code.get(atm_put_code))

        # 6. aggregate call vs put volume / open interest across the chain
        call_codes = {r.get("code") for r in calls}
        put_codes = {r.get("code") for r in puts}
        call_volume = 0.0
        put_volume = 0.0
        call_oi = 0.0
        put_oi = 0.0
        for code, row in by_code.items():
            vol = _safe(row, "volume")
            oi = _safe(row, "option_open_interest")
            v = float(vol) if isinstance(vol, (int, float)) else 0.0
            o = float(oi) if isinstance(oi, (int, float)) else 0.0
            if code in call_codes:
                call_volume += v
                call_oi += o
            elif code in put_codes:
                put_volume += v
                put_oi += o

        payload = {
            "spot": float(spot),
            "expiry": expiry,
            "atm_strike": float(atm_strike) if isinstance(atm_strike, (int, float)) else None,
            "atm_call": atm_call,
            "atm_put": atm_put,
            "chain_summary": {
                "call_volume": call_volume,
                "put_volume": put_volume,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "n_calls": len(calls),
                "n_puts": len(puts),
            },
        }
    except Exception as e:  # noqa: BLE001
        log.warning("[futu] options fetch %s failed: %s", ts_code, e)
        payload = None

    _OPTION_CHAIN_CACHE[ts_code] = (now, payload)
    return payload


def fetch_l6_priced_iv(constituents: Iterable[dict], now: int,
                       host: str = "127.0.0.1", port: int = 11111,
                       ctx=None) -> list[tuple]:
    """L6.priced.iv — per-stock ATM IV snapshot.

    Inactive when OpenD is unreachable / chain data missing. A-share rows
    are silently skipped (Futu has no A-share options coverage worth
    speaking of)."""

    constituents = list(constituents)
    # Filter to HK + US only.
    target = [c for c in constituents if (c.get("ts_code") or "").endswith((".HK", ".US"))]
    if not target:
        return []

    own_ctx = False
    if ctx is None:
        ctx = _open_ctx_safe(host, port)
        own_ctx = True
        if ctx is None:
            return [
                _emit_options_inactive(c["ts_code"], "L6.priced.iv", "no_opend", now)
                for c in target
            ]

    rows: list[tuple] = []
    try:
        for c in target:
            ts_code = c["ts_code"]
            futu_code = to_futu_code(ts_code)
            if not futu_code:
                continue
            try:
                data = _fetch_atm_option_snapshot(ctx, futu_code, ts_code, now)
            except Exception as e:  # noqa: BLE001
                log.warning("[futu] iv fetch %s failed: %s", ts_code, e)
                data = None
            if not data:
                rows.append(_emit_options_inactive(ts_code, "L6.priced.iv", "no_iv_data", now))
                continue
            call_iv = (data.get("atm_call") or {}).get("iv")
            put_iv = (data.get("atm_put") or {}).get("iv")
            if call_iv is None and put_iv is None:
                rows.append(_emit_options_inactive(ts_code, "L6.priced.iv", "no_iv_data", now))
                continue
            # Average call+put IV when both are present.
            ivs = [v for v in (call_iv, put_iv) if isinstance(v, (int, float))]
            atm_iv = sum(ivs) / len(ivs) if ivs else None
            payload = {
                "atm_iv": atm_iv,
                "atm_call_iv": call_iv,
                "atm_put_iv": put_iv,
                "nearest_expiry": data.get("expiry"),
                "atm_strike": data.get("atm_strike"),
                "spot": data.get("spot"),
                "unit": "pct",  # Futu returns IV as a percent (e.g. 17.17)
                "as_of": _as_of_iso(now),
            }
            rows.append((
                ts_code, "L6.priced.iv",
                json.dumps(payload, ensure_ascii=False),
                "Known", 0.7, "futu:option_chain", now,
            ))
    finally:
        if own_ctx and ctx is not None:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

    return rows


def fetch_l7_trade_iv(constituents: Iterable[dict], now: int,
                      host: str = "127.0.0.1", port: int = 11111,
                      ctx=None) -> list[tuple]:
    """L7.trade.iv — event-view IV.

    We have no rolling 30-day option history yet, so this uses static
    thresholds (>40% high, <15% low). IV in the middle band emits Inactive
    so downstream knows the event hasn't triggered. Same fetch as
    L6.priced.iv but the data_status flip is the interesting bit here."""

    constituents = list(constituents)
    target = [c for c in constituents if (c.get("ts_code") or "").endswith((".HK", ".US"))]
    if not target:
        return []

    own_ctx = False
    if ctx is None:
        ctx = _open_ctx_safe(host, port)
        own_ctx = True
        if ctx is None:
            return [
                _emit_options_inactive(c["ts_code"], "L7.trade.iv", "no_opend", now)
                for c in target
            ]

    rows: list[tuple] = []
    try:
        for c in target:
            ts_code = c["ts_code"]
            futu_code = to_futu_code(ts_code)
            if not futu_code:
                continue
            try:
                data = _fetch_atm_option_snapshot(ctx, futu_code, ts_code, now)
            except Exception as e:  # noqa: BLE001
                log.warning("[futu] iv-event fetch %s failed: %s", ts_code, e)
                data = None
            if not data:
                rows.append(_emit_options_inactive(ts_code, "L7.trade.iv", "no_iv_data", now))
                continue
            call_iv = (data.get("atm_call") or {}).get("iv")
            put_iv = (data.get("atm_put") or {}).get("iv")
            ivs = [v for v in (call_iv, put_iv) if isinstance(v, (int, float))]
            if not ivs:
                rows.append(_emit_options_inactive(ts_code, "L7.trade.iv", "no_iv_data", now))
                continue
            atm_iv = sum(ivs) / len(ivs)

            if atm_iv >= _IV_HIGH_THRESHOLD:
                regime = "high"
                status = "Known"
            elif atm_iv <= _IV_LOW_THRESHOLD:
                regime = "low"
                status = "Known"
            else:
                regime = "normal"
                status = "Inactive"

            payload = {
                "atm_iv": atm_iv,
                "regime": regime,
                "threshold_high": _IV_HIGH_THRESHOLD,
                "threshold_low": _IV_LOW_THRESHOLD,
                "nearest_expiry": data.get("expiry"),
                "spot": data.get("spot"),
                "unit": "pct",
                "as_of": _as_of_iso(now),
            }
            confidence = 0.7 if status == "Known" else 0.4
            rows.append((
                ts_code, "L7.trade.iv",
                json.dumps(payload, ensure_ascii=False),
                status, confidence, "futu:option_chain", now,
            ))
    finally:
        if own_ctx and ctx is not None:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

    return rows


def fetch_l7_trade_options_cp(constituents: Iterable[dict], now: int,
                              host: str = "127.0.0.1", port: int = 11111,
                              ctx=None) -> list[tuple]:
    """L7.trade.options_cp — daily aggregated Call/Put volume and OI ratios.

    cp_ratio = put_volume / call_volume (classic put/call ratio; >1 = bearish
    skew). oi_ratio = put_oi / call_oi. Inactive when chain is empty or
    OpenD unreachable."""

    constituents = list(constituents)
    target = [c for c in constituents if (c.get("ts_code") or "").endswith((".HK", ".US"))]
    if not target:
        return []

    own_ctx = False
    if ctx is None:
        ctx = _open_ctx_safe(host, port)
        own_ctx = True
        if ctx is None:
            return [
                _emit_options_inactive(c["ts_code"], "L7.trade.options_cp", "no_opend", now)
                for c in target
            ]

    rows: list[tuple] = []
    try:
        for c in target:
            ts_code = c["ts_code"]
            futu_code = to_futu_code(ts_code)
            if not futu_code:
                continue
            try:
                data = _fetch_atm_option_snapshot(ctx, futu_code, ts_code, now)
            except Exception as e:  # noqa: BLE001
                log.warning("[futu] options_cp fetch %s failed: %s", ts_code, e)
                data = None
            if not data:
                rows.append(_emit_options_inactive(
                    ts_code, "L7.trade.options_cp", "no_chain_data", now))
                continue
            summary = data.get("chain_summary") or {}
            call_volume = summary.get("call_volume") or 0.0
            put_volume = summary.get("put_volume") or 0.0
            call_oi = summary.get("call_oi") or 0.0
            put_oi = summary.get("put_oi") or 0.0
            if call_volume == 0 and put_volume == 0 and call_oi == 0 and put_oi == 0:
                rows.append(_emit_options_inactive(
                    ts_code, "L7.trade.options_cp", "no_chain_data", now))
                continue

            cp_ratio = (put_volume / call_volume) if call_volume > 0 else None
            oi_ratio = (put_oi / call_oi) if call_oi > 0 else None
            payload = {
                "call_volume": call_volume,
                "put_volume": put_volume,
                "cp_ratio": cp_ratio,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "oi_ratio": oi_ratio,
                "n_calls": summary.get("n_calls"),
                "n_puts": summary.get("n_puts"),
                "expiry": data.get("expiry"),
                "as_of": _as_of_iso(now),
            }
            rows.append((
                ts_code, "L7.trade.options_cp",
                json.dumps(payload, ensure_ascii=False),
                "Known", 0.7, "futu:option_chain.cp", now,
            ))
    finally:
        if own_ctx and ctx is not None:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

    return rows
