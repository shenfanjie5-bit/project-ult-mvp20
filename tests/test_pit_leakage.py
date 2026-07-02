"""Leakage-audit + L0-freeze tests (offline)."""

from pit_backtest import leakage_audit
from pit_backtest.score import _freeze_qualitative_layers


def test_audit_detects_future_observation(tmp_path):
    from mvp20 import storage

    db = tmp_path / "pit.sqlite"
    storage.upsert_realtime(db, [
        ("X", "L6.mult.pe", {"scalar": 10, "trade_date": "20260116"}, "Known", 0.7, "tushare:daily_basic", 1),
        ("X", "L7.flow.active_inflow", {"main_net": 1, "trade_date": "20260201"}, "Known", 0.7, "tushare:moneyflow", 1),
    ])
    rep = leakage_audit.audit_pit_db(db, "20260116")
    assert len(rep["hard"]) == 1
    assert "20260201" in rep["hard"][0]
    assert rep["dp_max_date"]["L6.mult.pe"] == "20260116"


def test_audit_forbidden_feature_key(tmp_path):
    from mvp20 import storage

    db = tmp_path / "pit.sqlite"
    storage.upsert_realtime(db, [
        ("X", "L6.mult.pe", {"scalar": 10, "fwd_ret": 0.2, "trade_date": "20260116"}, "Known", 0.7, "s", 1),
    ])
    rep = leakage_audit.audit_pit_db(db, "20260116")
    assert any("forbidden feature key" in h for h in rep["hard"])


def test_audit_allows_future_report_period_as_warn(tmp_path):
    from mvp20 import storage

    db = tmp_path / "pit.sqlite"
    storage.upsert_realtime(db, [
        # forecast target period in the future is a WARN, not HARD
        ("X", "L9.company.earnings_guidance",
         {"type": "预增", "ann_date": "20260101", "period": "20261231"}, "Known", 0.85, "tushare:forecast", 1),
    ])
    rep = leakage_audit.audit_pit_db(db, "20260116")
    assert rep["hard"] == []
    assert any("20261231" in w for w in rep["warn"])


def test_freeze_strips_l0_through_l3_only():
    overlay = {"nodes": [
        {"node_id": "X:L0.demand.terminal", "dp_id": "L0.demand.terminal"},
        {"node_id": "X:L1.position.moat", "dp_id": "L1.position.moat"},
        {"node_id": "X:L2.segment.cash", "dp_id": "L2.segment.cash_contrib"},
        {"node_id": "X:L3.product.portfolio", "dp_id": "L3.product.portfolio"},
        {"node_id": "X:L5.fina.roe", "dp_id": "L5.fina.roe"},
        {"node_id": "X:L6.mult.pe", "dp_id": "L6.mult.pe"},
        {"node_id": "X:L8.fin.debt_pressure", "dp_id": "L8.fin.debt_pressure"},
    ]}
    out = _freeze_qualitative_layers(overlay)
    kept = {n["dp_id"] for n in out["nodes"]}
    assert kept == {"L5.fina.roe", "L6.mult.pe", "L8.fin.debt_pressure"}


def test_freeze_strips_track_b_event_nodes_but_keeps_quant_l8_and_nontrackb():
    # Track B(2026-06)的 4 个 as-of-today 事件节点必须被冻结(防 PIT 泄漏未来),
    # 但 L8.fin.*(量化、PIT 可重建)与未填的其它 L8/L9 事件节点(Inactive=0)照常保留。
    overlay = {"nodes": [
        {"node_id": "X:L8.gov.insider_sell", "dp_id": "L8.gov.insider_sell"},
        {"node_id": "X:L8.gov.management_change", "dp_id": "L8.gov.management_change"},
        {"node_id": "X:L9.company.buyback_dividend", "dp_id": "L9.company.buyback_dividend"},
        {"node_id": "X:L9.company.earnings_guidance", "dp_id": "L9.company.earnings_guidance"},
        {"node_id": "X:L8.fin.debt_pressure", "dp_id": "L8.fin.debt_pressure"},   # 量化 → 保留
        {"node_id": "X:L9.company.ma", "dp_id": "L9.company.ma"},                  # 非Track-B → 保留
        {"node_id": "X:L5.fina.roe", "dp_id": "L5.fina.roe"},
    ]}
    kept = {n["dp_id"] for n in _freeze_qualitative_layers(overlay)["nodes"]}
    assert kept == {"L8.fin.debt_pressure", "L9.company.ma", "L5.fina.roe"}
