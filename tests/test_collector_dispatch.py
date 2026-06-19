"""Tests for collector source dispatch composition."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest


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
    monkeypatch.setattr(collector, "fetch_tushare_macro_batch", _fetcher("tushare-macro"))
    monkeypatch.setattr(collector, "fetch_tushare_crowding_batch", _fetcher("tushare-crowding"))
    monkeypatch.setattr(collector, "fetch_tushare_report_rc_batch", _fetcher("tushare-report-rc"))
    monkeypatch.setattr(collector, "fetch_tushare_report_signals_batch", _fetcher("tushare-report-signals"))
    monkeypatch.setattr(collector, "fetch_tushare_industry_valuation_batch", _fetcher("tushare-industry-valuation"))
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
        "tushare-macro",
        "tushare-crowding",
        "tushare-report-rc",
        "tushare-report-signals",
        "tushare-industry-valuation",
        "tushare-akshare-repl",
        "futu",
        "fmp",
        "akshare",
    ]
    assert len(rows) == len(calls)


def test_source_dispatch_exposes_focused_preprice_source():
    collector = _load_collector()

    assert (
        collector.SOURCE_DISPATCH["tushare-preprice"]
        is collector.fetch_tushare_preprice_batch
    )


def test_source_dispatch_exposes_report_signal_source():
    collector = _load_collector()

    assert (
        collector.SOURCE_DISPATCH["tushare-report-signals"]
        is collector.fetch_tushare_report_signals_batch
    )


def test_source_dispatch_exposes_earnings_risk_source():
    collector = _load_collector()

    assert (
        collector.SOURCE_DISPATCH["tushare-earnings-risk"]
        is collector.fetch_tushare_earnings_risk_batch
    )


def test_source_dispatch_exposes_industry_valuation_source():
    collector = _load_collector()

    assert (
        collector.SOURCE_DISPATCH["tushare-industry-valuation"]
        is collector.fetch_tushare_industry_valuation_batch
    )


def test_source_dispatch_exposes_focused_akshare_sources():
    collector = _load_collector()

    assert (
        collector.SOURCE_DISPATCH["akshare-block-trade"]
        is collector.fetch_akshare_block_trade_batch
    )
    assert (
        collector.SOURCE_DISPATCH["akshare-cls"]
        is collector.fetch_akshare_cls_batch
    )


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


# ---------------------------------------------------------------------------
# Production dev-gate: the daemon must refuse fabricated mock sources unless
# explicitly opted in, so mock rows never reach a production hot.sqlite. The
# read-side mock guard (derive/aggregator) handles legacy rows already in the
# DB; this gate stops NEW ones from being written.
# ---------------------------------------------------------------------------


def test_mock_allowed_defaults_off(monkeypatch):
    """Production default: mock collection is disabled (no flag, no env)."""

    collector = _load_collector()
    monkeypatch.delenv(collector.MOCK_GATE_ENV, raising=False)
    assert collector._mock_allowed(cli_allow_mock=False) is False


def test_mock_allowed_via_cli_flag(monkeypatch):
    collector = _load_collector()
    monkeypatch.delenv(collector.MOCK_GATE_ENV, raising=False)
    assert collector._mock_allowed(cli_allow_mock=True) is True


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " On "])
def test_mock_allowed_via_truthy_env(monkeypatch, val):
    collector = _load_collector()
    monkeypatch.setenv(collector.MOCK_GATE_ENV, val)
    assert collector._mock_allowed(cli_allow_mock=False) is True


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "garbage"])
def test_mock_allowed_via_falsy_env(monkeypatch, val):
    collector = _load_collector()
    monkeypatch.setenv(collector.MOCK_GATE_ENV, val)
    assert collector._mock_allowed(cli_allow_mock=False) is False


def _run_main(collector, monkeypatch, argv: list[str]):
    monkeypatch.setattr(collector.sys, "argv", ["collector.py", *argv])
    return collector.main()


def test_main_refuses_mock_in_production(tmp_path, monkeypatch, capsys):
    """``--source mock`` without the gate must refuse (exit 2) and write
    NOTHING to the hot DB — proving no fabricated rows can enter prod."""

    collector = _load_collector()
    monkeypatch.delenv(collector.MOCK_GATE_ENV, raising=False)

    db = tmp_path / "hot.sqlite"
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        "constituents:\n  - ts_code: 000001.SZ\n", encoding="utf-8"
    )

    rc = _run_main(collector, monkeypatch, [
        "--source", "mock",
        "--hot-db", str(db),
        "--universe", str(universe),
        "--max-cycles", "1",
    ])

    assert rc == 2
    err = capsys.readouterr().err
    assert "REFUSED" in err and collector.MOCK_GATE_ENV in err
    # The refusal happens before init_db / any write — DB must not exist, or if
    # it does (it should not), it must hold zero realtime rows.
    if db.exists():
        with sqlite3.connect(str(db)) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM realtime_current"
            ).fetchone()[0]
        assert n == 0
    else:
        assert not db.exists()


def test_main_allows_mock_with_cli_flag(tmp_path, monkeypatch):
    """``--allow-mock`` permits the mock path; rows are written but tagged
    ``data_status='Mock'`` + ``source='mock:*'`` so the score-read drops them."""

    collector = _load_collector()
    monkeypatch.delenv(collector.MOCK_GATE_ENV, raising=False)

    db = tmp_path / "hot.sqlite"
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        "constituents:\n  - ts_code: 000001.SZ\n", encoding="utf-8"
    )

    rc = _run_main(collector, monkeypatch, [
        "--source", "mock",
        "--allow-mock",
        "--hot-db", str(db),
        "--universe", str(universe),
        "--max-cycles", "1",
    ])

    assert rc == 0
    assert db.exists()
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT data_status, source FROM realtime_current"
        ).fetchall()
    assert rows, "mock path with --allow-mock should write rows"
    # Every written mock row is non-scoring: Mock status + mock:* source.
    assert all(r[0] == "Mock" for r in rows)
    assert all(str(r[1]).startswith("mock:") for r in rows)


def test_main_allows_mock_with_env(tmp_path, monkeypatch):
    collector = _load_collector()
    monkeypatch.setenv(collector.MOCK_GATE_ENV, "1")

    db = tmp_path / "hot.sqlite"
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        "constituents:\n  - ts_code: 000001.SZ\n", encoding="utf-8"
    )

    rc = _run_main(collector, monkeypatch, [
        "--source", "mock",
        "--hot-db", str(db),
        "--universe", str(universe),
        "--max-cycles", "1",
    ])

    assert rc == 0
    assert db.exists()


def test_main_real_source_unaffected_by_gate(tmp_path, monkeypatch):
    """A non-mock source must run regardless of the mock gate (default OFF)."""

    collector = _load_collector()
    monkeypatch.delenv(collector.MOCK_GATE_ENV, raising=False)

    db = tmp_path / "hot.sqlite"
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        "constituents:\n  - ts_code: 000001.SZ\n", encoding="utf-8"
    )

    # Stub the real dispatcher so we don't hit any live API.
    captured: dict = {}

    def _fake_real(u, tick):
        captured["called"] = True
        return [(
            "000001.SZ", "test.real", "{}", "Known", 0.9,
            "test:real", 1700000000,
        )]

    monkeypatch.setitem(collector.SOURCE_DISPATCH, "real", _fake_real)

    rc = _run_main(collector, monkeypatch, [
        "--source", "real",
        "--hot-db", str(db),
        "--universe", str(universe),
        "--max-cycles", "1",
    ])

    assert rc == 0
    assert captured.get("called") is True
    assert "mock" in collector.MOCK_SOURCE_NAMES
    assert "real" not in collector.MOCK_SOURCE_NAMES
