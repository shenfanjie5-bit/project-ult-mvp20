"""Tests for collector source dispatch composition."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_collector():
    spec = importlib.util.spec_from_file_location(
        "collector",
        ROOT / "scripts" / "collector.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_real_batch_uses_focused_tushare_sources(monkeypatch):
    collector = _load_collector()
    calls: list[str] = []

    def _fetcher(label: str):
        def inner(universe, tick):
            calls.append(label)
            return [(
                "000001.SZ", f"test.{label}", "{}", "Known", 0.5,
                f"test:{label}", 1700000000,
            )]
        return inner

    monkeypatch.setattr(
        collector,
        "fetch_tushare_batch",
        lambda universe, tick: (_ for _ in ()).throw(
            AssertionError("full tushare path should not run under real/all"),
        ),
    )
    monkeypatch.setattr(collector, "fetch_tushare_core_batch", _fetcher("tushare-core"))
    monkeypatch.setattr(collector, "fetch_tushare_market_env_batch", _fetcher("tushare-market-env"))
    monkeypatch.setattr(collector, "fetch_tushare_crowding_batch", _fetcher("tushare-crowding"))
    monkeypatch.setattr(collector, "fetch_tushare_report_rc_batch", _fetcher("tushare-report-rc"))
    # The akshare-replacement batch (8 dp_ids moved off akshare onto permitted
    # Tushare endpoints) is now part of the real/all dispatch — stub it so the
    # test never hits live Tushare.
    monkeypatch.setattr(collector, "fetch_tushare_akshare_replacement_batch", _fetcher("tushare-akshare-repl"))
    monkeypatch.setattr(collector, "fetch_futu_batch", _fetcher("futu"))
    monkeypatch.setattr(collector, "fetch_fmp_batch", _fetcher("fmp"))
    monkeypatch.setattr(collector, "fetch_akshare_batch", _fetcher("akshare"))

    rows = collector.fetch_real_batch([{"ts_code": "000001.SZ"}], tick=0)

    assert calls == [
        "tushare-core",
        "tushare-market-env",
        "tushare-crowding",
        "tushare-report-rc",
        "tushare-akshare-repl",
        "futu",
        "fmp",
        "akshare",
    ]
    assert len(rows) == len(calls)


# ---------------------------------------------------------------------------
# Data-integrity: the mock fetcher must never fabricate trustworthy ("Known")
# rows, and dp_ids that have a real emitter must not be mocked at all (the
# upsert PRIMARY KEY (ts_code, dp_id) would otherwise overwrite real data).
# ---------------------------------------------------------------------------

# dp_ids that have a real Tushare emitter — the mock list must NOT fabricate
# these (they would clobber real upstream rows via the upsert).
CORE_REPOINTED_DP_IDS = (
    "L6.mult.pe",
    "L6.mult.pb",
    "L6.priced.crowdedness",
    "L7.flow.active_inflow",
    "L7.trade.volume_turnover",
)


def test_fetch_mock_batch_never_emits_known_status():
    """A fabricated value must never carry data_status='Known'.

    Row layout (see ``upsert_realtime``):
        (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
    """

    collector = _load_collector()
    universe = [{"ts_code": "000001.SZ"}, {"ts_code": "600000.SH"}]

    rows = collector.fetch_mock_batch(universe, tick=3)

    assert rows, "mock batch should still seed the no-real-source dp_ids"
    statuses = {row[3] for row in rows}
    # The fabricated rows must use the Mock sentinel — never Known.
    assert "Known" not in statuses
    assert statuses <= {"Mock", "Unknown"}, statuses
    # And concretely the chosen sentinel is exposed as a constant.
    assert collector.MOCK_DATA_STATUS == "Mock"
    assert all(row[3] == collector.MOCK_DATA_STATUS for row in rows)
    # Mock rows are still tagged with a mock:* source so the derive upstream
    # pass keeps excluding them.
    assert all(row[5].startswith("mock:") for row in rows)


def test_core_dp_ids_removed_from_mock_list():
    """The re-pointed core dp_ids are no longer fabricated by --source mock."""

    collector = _load_collector()
    mock_dp_ids = {dp_id for dp_id, _hint in collector.REALTIME_DP_IDS}

    for dp_id in CORE_REPOINTED_DP_IDS:
        assert dp_id not in mock_dp_ids, (
            f"{dp_id} has a real emitter and must not be in REALTIME_DP_IDS"
        )

    # L11.trade.signal is recomputed by the derive layer (participates_in_score
    # is false) — it must not be fabricated either.
    assert "L11.trade.signal" not in mock_dp_ids

    # And fetch_mock_batch must not emit them.
    rows = collector.fetch_mock_batch([{"ts_code": "000001.SZ"}], tick=0)
    emitted = {row[1] for row in rows}
    for dp_id in CORE_REPOINTED_DP_IDS:
        assert dp_id not in emitted
    assert "L11.trade.signal" not in emitted


def test_core_dp_ids_emitted_by_real_tushare_source():
    """The re-pointed core dp_ids are produced by the real Tushare emitters.

    Asserted offline (no network, no Tushare token) by checking the emitter
    module actually references each dp_id as an emit target.
    """

    src = (ROOT / "mvp20" / "sources" / "tushare_source.py").read_text(
        encoding="utf-8"
    )
    for dp_id in CORE_REPOINTED_DP_IDS:
        # Each dp_id appears both in SUPPORTED_DP_IDS and in at least one
        # emit tuple — i.e. it shows up more than once in the source.
        assert src.count(f'"{dp_id}"') >= 2, (
            f"{dp_id} is expected to be emitted by tushare_source.py"
        )
