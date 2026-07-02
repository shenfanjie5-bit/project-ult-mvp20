"""Partial-source freshness labeling in ``scripts/collector.py`` (review #8).

A fetch_real_batch cycle where some of the 11 sources raised must be
labelled sync_status="partial" in freshness_meta — previously any non-empty
batch was stamped "ok" even with 10/11 sources down, making partial outages
invisible on dashboards.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import collector  # noqa: E402


def _rows(label: str) -> list[tuple]:
    # Shape only matters to upsert_realtime, which is not exercised here.
    return [(f"{label}-row",)]


def test_fetch_real_batch_records_failed_sources(monkeypatch) -> None:
    # tushare-core survives; every other source raises.
    def _boom(*_a, **_k):
        raise RuntimeError("source down")

    monkeypatch.setattr(collector, "fetch_tushare_core_batch", lambda u, t: _rows("core"))
    for name in (
        "fetch_tushare_market_env_batch",
        "fetch_tushare_macro_batch",
        "fetch_tushare_crowding_batch",
        "fetch_tushare_report_rc_batch",
        "fetch_tushare_report_signals_batch",
        "fetch_tushare_industry_valuation_batch",
        "fetch_tushare_akshare_replacement_batch",
        "fetch_futu_batch",
        "fetch_fmp_batch",
        "fetch_akshare_batch",
    ):
        monkeypatch.setattr(collector, name, _boom)

    rows = collector.fetch_real_batch([], 0)

    assert rows == _rows("core")
    assert len(collector.LAST_BATCH_SOURCE_FAILURES) == 10
    assert "futu" in collector.LAST_BATCH_SOURCE_FAILURES
    assert "tushare-core" not in collector.LAST_BATCH_SOURCE_FAILURES


def test_fetch_real_batch_clean_run_resets_failures(monkeypatch) -> None:
    for name in (
        "fetch_tushare_core_batch",
        "fetch_tushare_market_env_batch",
        "fetch_tushare_macro_batch",
        "fetch_tushare_crowding_batch",
        "fetch_tushare_report_rc_batch",
        "fetch_tushare_report_signals_batch",
        "fetch_tushare_industry_valuation_batch",
        "fetch_tushare_akshare_replacement_batch",
        "fetch_futu_batch",
        "fetch_fmp_batch",
        "fetch_akshare_batch",
    ):
        monkeypatch.setattr(collector, name, lambda u, t: [])

    # Seed a stale failure from a hypothetical previous cycle; a clean run
    # must clear it (the label is per-cycle, not cumulative).
    collector.LAST_BATCH_SOURCE_FAILURES[:] = ["futu"]
    collector.fetch_real_batch([], 0)

    assert collector.LAST_BATCH_SOURCE_FAILURES == []


def test_main_loop_marks_partial_freshness(monkeypatch, tmp_path) -> None:
    statuses: list[str] = []

    def _fake_real(universe, tick):
        collector.LAST_BATCH_SOURCE_FAILURES[:] = ["futu", "fmp"]
        return _rows("core")

    monkeypatch.setitem(collector.SOURCE_DISPATCH, "real", _fake_real)
    monkeypatch.setattr(collector, "init_db", lambda _db: None)
    monkeypatch.setattr(collector, "load_universe", lambda _p: [])
    monkeypatch.setattr(collector, "upsert_realtime", lambda _db, batch: len(batch))
    monkeypatch.setattr(
        collector, "update_freshness",
        lambda _db, layer, sync_status, is_full: statuses.append(sync_status),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["collector.py", "--source", "real", "--max-cycles", "1",
         "--hot-db", str(tmp_path / "hot.sqlite")],
    )

    rc = collector.main()

    assert rc == 0
    assert statuses == ["partial"]
