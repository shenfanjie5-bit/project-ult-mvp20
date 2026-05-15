"""Tests for the Bucket-A options dp_ids in ``mvp20.sources.futu_source``.

OpenD calls are mocked via a fake ``QuoteCtx`` so the suite is hermetic
(no daemon, no Futu account required). We lock down:

  * ``SUPPORTED_DP_IDS`` covers the three new options dp_ids.
  * ts_code → Futu code conversion (HK / US prefix; A-share returns None).
  * No OpenD → 3 fetchers emit Inactive rows for HK + US, **never crash**.
  * Happy path → emit Known rows with the documented payload schema.
  * A-share constituents (.SH / .SZ / .BJ) are skipped (Futu has no
    A-share options coverage worth speaking of).
  * 10-minute TTL cache: two back-to-back fetches reuse one chain.
"""

from __future__ import annotations

import json

import pytest

from mvp20.sources import futu_source


# ---------------------------------------------------------------------------
# Test doubles — fake OpenD QuoteCtx
# ---------------------------------------------------------------------------


RET_OK = 0  # matches futu.RET_OK; we never import futu in test code so OpenD
            # missing on CI isn't fatal.


class _FakeDF:
    """Minimal stand-in for pandas DataFrame: just need .to_dict('records')."""

    def __init__(self, records: list[dict]):
        self._records = records

    def to_dict(self, orient: str = "records") -> list[dict]:
        assert orient == "records"
        return list(self._records)


class FakeQuoteCtx:
    """Mock ``OpenQuoteContext`` that records every call and returns fixtures."""

    def __init__(self, spot_price: float = 460.0, chain: list[dict] | None = None,
                 option_snap: list[dict] | None = None,
                 expirations: list[dict] | None = None,
                 fail_expiration: bool = False,
                 empty_chain: bool = False):
        self.spot_price = spot_price
        self.calls: list[tuple] = []
        self._chain = chain
        self._option_snap = option_snap
        self._expirations = expirations
        self.fail_expiration = fail_expiration
        self.empty_chain = empty_chain
        self.closed = False

    def get_market_snapshot(self, codes):
        self.calls.append(("snapshot", tuple(codes)))
        # If we get exactly one code that doesn't start with HK./US., it's
        # the underlying — return the spot. Option codes get an option_snap row.
        if all(c in {"HK.00700", "US.NVDA"} for c in codes):
            rows = [{"code": c, "last_price": self.spot_price,
                     "pe_ratio": 15.0, "pb_ratio": 2.5,
                     "turnover": 1e8, "turnover_rate": 1.2,
                     "bid_price": self.spot_price - 0.1, "ask_price": self.spot_price + 0.1,
                     "bid_vol": 100, "ask_vol": 200} for c in codes]
            return RET_OK, _FakeDF(rows)
        # Option contract codes
        if self._option_snap is None:
            return RET_OK, _FakeDF([])
        # Return only the rows whose 'code' matches the request
        wanted = set(codes)
        return RET_OK, _FakeDF([r for r in self._option_snap if r.get("code") in wanted])

    def get_option_expiration_date(self, code, index_option_type=None):
        self.calls.append(("expiration", code))
        if self.fail_expiration:
            return 1, "permission denied"
        if self._expirations is not None:
            return RET_OK, _FakeDF(self._expirations)
        return RET_OK, _FakeDF([
            {"strike_time": "2026-05-15", "option_expiry_date_distance": 1,
             "expiration_cycle": "WEEK"},
            {"strike_time": "2026-05-22", "option_expiry_date_distance": 8,
             "expiration_cycle": "WEEK"},
        ])

    def get_option_chain(self, code, start=None, end=None, **kwargs):
        self.calls.append(("chain", code, start, end))
        if self.empty_chain:
            return RET_OK, _FakeDF([])
        if self._chain is not None:
            return RET_OK, _FakeDF(self._chain)
        # Default tiny chain: 3 strikes × {call, put}
        rows = []
        for strike in (450.0, 460.0, 470.0):
            rows.append({"code": f"{code[:2]}.OPT{int(strike)}C", "option_type": "CALL",
                         "strike_price": strike, "strike_time": "2026-05-15"})
            rows.append({"code": f"{code[:2]}.OPT{int(strike)}P", "option_type": "PUT",
                         "strike_price": strike, "strike_time": "2026-05-15"})
        return RET_OK, _FakeDF(rows)

    def close(self):
        self.closed = True


# Build a coherent option_snap fixture so volume / OI / IV are present.
def _default_option_snap(prefix: str = "HK") -> list[dict]:
    """Return option-contract snapshots matching the default chain. ATM
    (450/460/470 with 460 ATM if spot=460); ATM IV ≈ 30%."""

    out = []
    for strike, vol_c, vol_p, oi_c, oi_p, iv_c, iv_p in (
        (450.0, 100, 300, 1000, 2000, 25.0, 26.0),  # ITM call / OTM put
        (460.0, 500, 700,  500, 1500, 30.0, 31.0),  # ATM
        (470.0,  80, 200,  300,  900, 28.0, 29.0),  # OTM call / ITM put
    ):
        out.append({
            "code": f"{prefix}.OPT{int(strike)}C",
            "option_type": "CALL",
            "strike_price": strike,
            "option_strike_price": strike,
            "volume": vol_c,
            "option_open_interest": oi_c,
            "option_implied_volatility": iv_c,
            "last_price": strike * 0.05,
        })
        out.append({
            "code": f"{prefix}.OPT{int(strike)}P",
            "option_type": "PUT",
            "strike_price": strike,
            "option_strike_price": strike,
            "volume": vol_p,
            "option_open_interest": oi_p,
            "option_implied_volatility": iv_p,
            "last_price": strike * 0.04,
        })
    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_option_cache():
    """Clear module-level option-chain cache between tests."""

    futu_source._OPTION_CHAIN_CACHE.clear()
    yield
    futu_source._OPTION_CHAIN_CACHE.clear()


@pytest.fixture()
def fake_universe() -> list[dict]:
    return [
        {"ts_code": "00700.HK", "name": "腾讯"},
        {"ts_code": "NVDA.US",  "name": "NVIDIA"},
        {"ts_code": "300750.SZ", "name": "宁德时代"},  # A-share — skipped
    ]


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_covers_options() -> None:
    expected = {"L6.priced.iv", "L7.trade.iv", "L7.trade.options_cp"}
    assert expected.issubset(futu_source.SUPPORTED_DP_IDS), (
        expected - futu_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# ts_code conversion sanity
# ---------------------------------------------------------------------------


def test_to_futu_code_hk_us_a() -> None:
    assert futu_source.to_futu_code("00700.HK") == "HK.00700"
    assert futu_source.to_futu_code("NVDA.US") == "US.NVDA"
    assert futu_source.to_futu_code("BRK.B.US") == "US.BRK.B"
    assert futu_source.to_futu_code("300750.SZ") is None
    assert futu_source.to_futu_code("600519.SH") is None


# ---------------------------------------------------------------------------
# No OpenD → 3 fetchers all emit Inactive, never crash
# ---------------------------------------------------------------------------


def test_l6_priced_iv_no_opend_emits_inactive(monkeypatch, fake_universe) -> None:
    monkeypatch.setattr(futu_source, "_open_ctx",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no daemon")))
    rows = futu_source.fetch_l6_priced_iv(fake_universe, now=1_000_000)

    assert len(rows) == 2  # HK + US (A-share skipped)
    for r in rows:
        ts_code, dp_id, value_json, status, conf, source, ts = r
        assert ts_code in {"00700.HK", "NVDA.US"}
        assert dp_id == "L6.priced.iv"
        assert status == "Inactive"
        assert conf == 0.0
        assert json.loads(value_json)["reason"] == "no_opend"


def test_l7_trade_iv_no_opend_emits_inactive(monkeypatch, fake_universe) -> None:
    monkeypatch.setattr(futu_source, "_open_ctx",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no daemon")))
    rows = futu_source.fetch_l7_trade_iv(fake_universe, now=1_000_000)

    assert {r[0] for r in rows} == {"00700.HK", "NVDA.US"}
    for r in rows:
        assert r[1] == "L7.trade.iv"
        assert r[3] == "Inactive"


def test_l7_trade_options_cp_no_opend_emits_inactive(monkeypatch, fake_universe) -> None:
    monkeypatch.setattr(futu_source, "_open_ctx",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no daemon")))
    rows = futu_source.fetch_l7_trade_options_cp(fake_universe, now=1_000_000)

    assert {r[0] for r in rows} == {"00700.HK", "NVDA.US"}
    for r in rows:
        assert r[1] == "L7.trade.options_cp"
        assert r[3] == "Inactive"


def test_no_opend_a_share_only_returns_empty(monkeypatch) -> None:
    """If the universe is all A-share, no Inactive rows are emitted either
    (the fetchers correctly skip A-share rather than mark every one Inactive)."""

    monkeypatch.setattr(futu_source, "_open_ctx",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no daemon")))
    a_only = [{"ts_code": "300750.SZ"}, {"ts_code": "600519.SH"}]
    assert futu_source.fetch_l6_priced_iv(a_only, now=1_000_000) == []
    assert futu_source.fetch_l7_trade_iv(a_only, now=1_000_000) == []
    assert futu_source.fetch_l7_trade_options_cp(a_only, now=1_000_000) == []


# ---------------------------------------------------------------------------
# Happy path: emit Known + correct payload
# ---------------------------------------------------------------------------


def _shared_ctx() -> FakeQuoteCtx:
    return FakeQuoteCtx(
        spot_price=460.0,
        option_snap=_default_option_snap("HK"),
    )


def test_l6_priced_iv_happy_path(fake_universe) -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    rows = futu_source.fetch_l6_priced_iv(
        [c for c in fake_universe if c["ts_code"].endswith(".HK")],
        now=1_000_000, ctx=ctx,
    )

    assert len(rows) == 1
    r = rows[0]
    assert r[0] == "00700.HK"
    assert r[1] == "L6.priced.iv"
    assert r[3] == "Known"
    assert r[4] == 0.7
    assert r[5] == "futu:option_chain"
    payload = json.loads(r[2])
    # ATM IV = avg(call IV, put IV) at strike 460 → (30+31)/2 = 30.5
    assert payload["atm_iv"] == pytest.approx(30.5)
    assert payload["atm_call_iv"] == pytest.approx(30.0)
    assert payload["atm_put_iv"] == pytest.approx(31.0)
    assert payload["atm_strike"] == pytest.approx(460.0)
    assert payload["spot"] == pytest.approx(460.0)
    assert payload["nearest_expiry"] == "2026-05-15"
    assert payload["unit"] == "pct"
    assert "as_of" in payload
    # OpenD context not closed by fetcher when caller passed it in.
    assert ctx.closed is False


def test_l7_trade_iv_normal_band_emits_inactive(fake_universe) -> None:
    """ATM IV ≈ 30% sits in the normal band → Inactive (event hasn't fired)."""

    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    rows = futu_source.fetch_l7_trade_iv(
        [{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx,
    )

    assert len(rows) == 1
    r = rows[0]
    assert r[3] == "Inactive"
    payload = json.loads(r[2])
    assert payload["regime"] == "normal"


def test_l7_trade_iv_high_band_triggers_known() -> None:
    """ATM IV pushed above the 40% threshold → Known (regime=high)."""

    snap = _default_option_snap("HK")
    # Bump the ATM (460) IVs above 40.
    for row in snap:
        if row["strike_price"] == 460.0:
            row["option_implied_volatility"] = 55.0
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=snap)

    rows = futu_source.fetch_l7_trade_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)
    assert len(rows) == 1
    r = rows[0]
    assert r[3] == "Known"
    payload = json.loads(r[2])
    assert payload["regime"] == "high"
    assert payload["atm_iv"] == pytest.approx(55.0)


def test_l7_trade_iv_low_band_triggers_known() -> None:
    """ATM IV below the 15% threshold → Known (regime=low)."""

    snap = _default_option_snap("HK")
    for row in snap:
        if row["strike_price"] == 460.0:
            row["option_implied_volatility"] = 10.0
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=snap)
    rows = futu_source.fetch_l7_trade_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)

    payload = json.loads(rows[0][2])
    assert rows[0][3] == "Known"
    assert payload["regime"] == "low"


def test_l7_trade_options_cp_happy_path() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    rows = futu_source.fetch_l7_trade_options_cp(
        [{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx,
    )

    assert len(rows) == 1
    r = rows[0]
    assert r[1] == "L7.trade.options_cp"
    assert r[3] == "Known"
    assert r[5] == "futu:option_chain.cp"
    payload = json.loads(r[2])
    # call_volume = 100 + 500 + 80 = 680;  put_volume = 300 + 700 + 200 = 1200
    assert payload["call_volume"] == pytest.approx(680.0)
    assert payload["put_volume"] == pytest.approx(1200.0)
    # cp_ratio = put/call = 1200/680
    assert payload["cp_ratio"] == pytest.approx(1200.0 / 680.0)
    # call_oi = 1000 + 500 + 300 = 1800;  put_oi = 2000 + 1500 + 900 = 4400
    assert payload["call_oi"] == pytest.approx(1800.0)
    assert payload["put_oi"] == pytest.approx(4400.0)
    assert payload["oi_ratio"] == pytest.approx(4400.0 / 1800.0)
    assert payload["n_calls"] == 3
    assert payload["n_puts"] == 3
    assert payload["expiry"] == "2026-05-15"


# ---------------------------------------------------------------------------
# A-share rows are skipped (Futu has no A-share options coverage worth using)
# ---------------------------------------------------------------------------


def test_a_share_silently_skipped(fake_universe) -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    a_only = [{"ts_code": "300750.SZ"}]
    assert futu_source.fetch_l6_priced_iv(a_only, now=1_000_000, ctx=ctx) == []
    assert futu_source.fetch_l7_trade_iv(a_only, now=1_000_000, ctx=ctx) == []
    assert futu_source.fetch_l7_trade_options_cp(a_only, now=1_000_000, ctx=ctx) == []
    # And no OpenD calls should have been issued for A-share.
    assert ctx.calls == []


# ---------------------------------------------------------------------------
# Cache TTL: 2 successive fetches share one chain pull
# ---------------------------------------------------------------------------


def test_chain_cache_ttl_reuses_within_600s() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))

    # First call — populates cache.
    futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)
    n_chain_calls_first = sum(1 for c in ctx.calls if c[0] == "chain")

    # Reset call log; second call 100s later should NOT re-hit get_option_chain.
    ctx.calls.clear()
    futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_100, ctx=ctx)
    n_chain_calls_second = sum(1 for c in ctx.calls if c[0] == "chain")

    assert n_chain_calls_first >= 1, "first call should hit OpenD"
    assert n_chain_calls_second == 0, "within TTL should use cache"


def test_chain_cache_expires_past_ttl() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)

    ctx.calls.clear()
    # > 600s later → must re-fetch.
    futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_000 + 700, ctx=ctx)
    n_chain_calls = sum(1 for c in ctx.calls if c[0] == "chain")
    assert n_chain_calls >= 1, "past TTL should re-hit OpenD"


def test_cache_reused_across_dp_ids() -> None:
    """L6.priced.iv + L7.trade.iv + L7.trade.options_cp should share one
    fetch of the underlying chain (single ctx.calls 'chain' entry)."""

    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    target = [{"ts_code": "00700.HK"}]
    now = 2_000_000

    futu_source.fetch_l6_priced_iv(target, now=now, ctx=ctx)
    futu_source.fetch_l7_trade_iv(target, now=now, ctx=ctx)
    futu_source.fetch_l7_trade_options_cp(target, now=now, ctx=ctx)

    chain_calls = [c for c in ctx.calls if c[0] == "chain"]
    assert len(chain_calls) == 1, (
        f"expected the 3 fetchers to share one chain pull, got {len(chain_calls)}")


# ---------------------------------------------------------------------------
# Row shape always conforms to the 7-tuple ``upsert_realtime`` schema
# ---------------------------------------------------------------------------


def test_row_shape_seven_tuple_happy() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))
    target = [{"ts_code": "00700.HK"}]
    for fetch in (futu_source.fetch_l6_priced_iv,
                  futu_source.fetch_l7_trade_iv,
                  futu_source.fetch_l7_trade_options_cp):
        # fresh cache per fetcher
        futu_source._OPTION_CHAIN_CACHE.clear()
        rows = fetch(target, now=1_000_000, ctx=ctx)
        for r in rows:
            assert len(r) == 7, r
            ts_code, dp_id, value_json, status, conf, source, ts = r
            assert ts_code == "00700.HK"
            assert isinstance(dp_id, str) and dp_id
            payload = json.loads(value_json)
            assert isinstance(payload, dict)
            assert status in ("Known", "Inactive")
            assert 0.0 <= conf <= 1.0
            assert source.startswith("futu:")
            assert isinstance(ts, int)


# ---------------------------------------------------------------------------
# Failure modes that should degrade to Inactive (not crash)
# ---------------------------------------------------------------------------


def test_expiration_lookup_failure_degrades_to_inactive() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, fail_expiration=True)
    rows = futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)

    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    assert json.loads(rows[0][2])["reason"] == "no_iv_data"


def test_empty_chain_degrades_to_inactive() -> None:
    ctx = FakeQuoteCtx(spot_price=460.0, empty_chain=True)
    rows = futu_source.fetch_l7_trade_options_cp(
        [{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx,
    )

    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


def test_chain_with_only_calls_degrades_to_inactive() -> None:
    """If a chain has no put contracts (extreme thin market), ATM lookup
    is meaningless — emit Inactive instead of crashing."""

    only_calls = [{"code": "HK.OPT460C", "option_type": "CALL",
                   "strike_price": 460.0, "strike_time": "2026-05-15"}]
    ctx = FakeQuoteCtx(spot_price=460.0, chain=only_calls,
                       option_snap=[])
    rows = futu_source.fetch_l6_priced_iv([{"ts_code": "00700.HK"}], now=1_000_000, ctx=ctx)
    assert rows[0][3] == "Inactive"


# ---------------------------------------------------------------------------
# fetch_batch wiring: extends existing rows with the 3 new dp_ids
# ---------------------------------------------------------------------------


def test_fetch_batch_extends_with_options(monkeypatch) -> None:
    """End-to-end: fetch_batch opens one ctx, runs spot + capital flow, then
    the 3 options fetchers, all sharing the same ctx."""

    universe = [{"ts_code": "00700.HK"}, {"ts_code": "300750.SZ"}]

    ctx = FakeQuoteCtx(spot_price=460.0, option_snap=_default_option_snap("HK"))

    # Stub _open_ctx + capital_flow (not on FakeQuoteCtx) so the inner batch
    # path works.
    def _fake_open(host="127.0.0.1", port=11111):
        return ctx
    monkeypatch.setattr(futu_source, "_open_ctx", _fake_open)

    def _fake_capital_flow(code, period_type="INTRADAY"):
        return RET_OK, _FakeDF([{"in_flow": 1e6, "main_in_flow": 5e5}])
    ctx.get_capital_flow = _fake_capital_flow

    # Patch RET_OK import used inside fetch_batch
    import futu  # type: ignore[import-not-found]
    monkeypatch.setattr(futu, "RET_OK", RET_OK, raising=False)

    rows = futu_source.fetch_batch(universe, tick=0)

    dp_ids = {r[1] for r in rows}
    # All 3 new dp_ids present.
    assert "L6.priced.iv" in dp_ids
    assert "L7.trade.iv" in dp_ids
    assert "L7.trade.options_cp" in dp_ids
    # Original 4 dp_ids still present.
    assert "L6.mult.pe" in dp_ids
    assert "L7.flow.active_inflow" in dp_ids
    assert "L7.trade.volume_turnover" in dp_ids
    # ctx was closed exactly once at the very end.
    assert ctx.closed is True
