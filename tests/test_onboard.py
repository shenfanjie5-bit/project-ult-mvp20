"""Tests for the add-stock onboarding backend (P1).

Hermetic: no network (tushare) and no universe/DB mutation. We exercise the
recognize *validation* paths, the industry map, the job-state table CRUD, and
the server command-endpoint guards (which return 400/409 BEFORE any job starts).
The successful onboard pipeline is covered separately by an end-to-end run.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mvp20 import onboard  # noqa: E402
from mvp20 import server  # noqa: E402


def test_list_industry_ids_excludes_pending() -> None:
    inds = onboard.list_industry_ids()
    ids = {i["industry_id"] for i in inds}
    assert "AI_COMPUTE" in ids
    assert "SPACE_ECONOMY" not in ids  # graph_status=pending → excluded
    assert len(inds) == 12


def test_recognize_rejects_bad_market_and_format() -> None:
    assert onboard.recognize("X", "000977")["ok"] is False      # unknown market
    assert onboard.recognize("A", "abc")["ok"] is False          # non-numeric
    assert onboard.recognize("A", "00700")["ok"] is False        # 5-digit ≠ A-share 6


def test_suggest_industries_mapping() -> None:
    assert onboard._suggest_industries("IT设备") == ["AI_COMPUTE"]
    assert onboard._suggest_industries("半导体")[0] == "SEMI_EQUIPMENT"  # ranked
    assert onboard._suggest_industries("白酒") == []                      # unmapped


def test_already_in_pool() -> None:
    assert onboard.already_in_pool("000977.SZ") is True
    assert onboard.already_in_pool("999999.SZ") is False


def test_job_table_crud(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    onboard._onboard_db_init(db)
    jid = onboard._job_create(db, "600519.SH", "贵州茅台", "DOMESTIC_CONSUMPTION")
    j = onboard.get_job(db, jid)
    assert j is not None and j["ts_code"] == "600519.SH" and j["status"] == "pending"
    onboard._job_update(db, jid, status="running", step="collect", step_idx=2)
    j = onboard.get_job(db, jid)
    assert j["status"] == "running" and j["step"] == "collect" and j["step_idx"] == 2
    assert onboard.get_job(db, "no-such-job") is None


def test_handle_onboard_guards_do_not_start_jobs(tmp_path: Path) -> None:
    cfg = server.ServerConfig(hot_db_path=tmp_path / "x.sqlite")
    st, _ = server.handle_onboard(cfg, {"ts_code": "@@@", "industry_id": "AI_COMPUTE"})
    assert st == 400  # bad ts_code
    st, _ = server.handle_onboard(cfg, {"ts_code": "600519.SH", "industry_id": "NOPE"})
    assert st == 400  # unknown industry
    st, _ = server.handle_onboard(cfg, {"ts_code": "000977.SZ", "industry_id": "AI_COMPUTE"})
    assert st == 409  # already in pool


def test_handle_onboard_status_codes(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    onboard._onboard_db_init(db)
    cfg = server.ServerConfig(hot_db_path=db)
    assert server.handle_onboard_status(cfg, {"job_id": ["nope"]})[0] == 404
    assert server.handle_onboard_status(cfg, {})[0] == 400


def test_handle_recognize_requires_fields() -> None:
    cfg = server.ServerConfig()
    assert server.handle_recognize(cfg, {})[0] == 400
    assert server.handle_recognize(cfg, {"market": "A"})[0] == 400


def test_handle_industries_returns_active() -> None:
    cfg = server.ServerConfig()
    st, body = server.handle_industries(cfg, {})
    assert st == 200 and len(body["data"]["industries"]) == 12


def test_onboard_rebuilds_peer_context_before_scoring() -> None:
    """R-6: a newly-added stock must rebuild the cross-sectional peer-context
    AFTER its data is collected/derived but BEFORE it is scored. Otherwise
    score-company loads a stale artifact that lacks the new stock →
    _xs_valuation_signal returns None → valuation_rerating / priced_in fall back
    to the pre-R-3 absolute path (quantified regression: valr drift up to ~0.19)."""
    steps = onboard.ONBOARD_STEPS
    assert "build_peer_context" in steps
    assert steps.index("derive") < steps.index("build_peer_context") < steps.index("score_preliminary")


def test_onboard_job_surfaces_preliminary_then_full(tmp_path: Path, monkeypatch) -> None:
    """The job must expose the preliminary score *while still running* (so the
    frontend can show it during the minutes-long codex fill), then the full
    score once codex completes. Uses a fake run_onboard so the test is hermetic
    (no CLI / network) and Events instead of sleeps for synchronisation."""
    db = tmp_path / "jobs.sqlite"
    seen_prelim = threading.Event()
    proceed = threading.Event()

    def fake_run_onboard(db_path, ts_code, name, industry_id, *,
                         do_codex=True, year=2025, progress=None,
                         on_preliminary=None):
        if progress:
            progress(7, "score_preliminary")
        prelim = {"ts_code": ts_code, "mode": "neutral", "signal": "WATCH",
                  "short": -0.18, "medium": -0.18, "long": -0.14, "top_path": None}
        if on_preliminary:
            on_preliminary(prelim)
        seen_prelim.set()
        proceed.wait(timeout=5)        # hold mid-run so the test can observe state
        full = {**prelim, "short": 0.05, "signal": "WATCH"}
        return {"ts_code": ts_code, "preliminary": prelim, "full": full}

    monkeypatch.setattr(onboard, "run_onboard", fake_run_onboard)
    job_id = onboard.start_onboard_job(db, "300999.SZ", "测试股", "AI_COMPUTE", do_codex=True)

    assert seen_prelim.wait(timeout=5)
    mid = onboard.get_job(db, job_id)
    assert mid is not None and mid["status"] == "running"      # codex still in flight
    assert mid.get("preliminary") and mid["preliminary"]["signal"] == "WATCH"
    assert mid.get("full") is None                              # full not ready yet

    proceed.set()
    final = None
    for _ in range(100):
        final = onboard.get_job(db, job_id)
        if final and final["status"] in ("ready_full", "error"):
            break
        time.sleep(0.02)
    assert final is not None and final["status"] == "ready_full"
    assert final["full"] and final["full"]["short"] == 0.05
    assert final["preliminary"]["signal"] == "WATCH"


def test_onboard_job_without_codex_is_preliminary_terminal(tmp_path: Path, monkeypatch) -> None:
    """do_codex=False → job ends at ready_preliminary with no full score."""
    db = tmp_path / "jobs.sqlite"

    def fake_run_onboard(db_path, ts_code, name, industry_id, *,
                         do_codex=True, year=2025, progress=None,
                         on_preliminary=None):
        prelim = {"ts_code": ts_code, "mode": "neutral", "signal": "AVOID",
                  "short": -0.4, "medium": -0.3, "long": -0.2, "top_path": None}
        if on_preliminary:
            on_preliminary(prelim)
        return {"ts_code": ts_code, "preliminary": prelim}

    monkeypatch.setattr(onboard, "run_onboard", fake_run_onboard)
    job_id = onboard.start_onboard_job(db, "300999.SZ", "测试股", "AI_COMPUTE", do_codex=False)

    final = None
    for _ in range(100):
        final = onboard.get_job(db, job_id)
        if final and final["status"] in ("ready_preliminary", "ready_full", "error"):
            break
        time.sleep(0.02)
    assert final is not None and final["status"] == "ready_preliminary"
    assert final["preliminary"]["signal"] == "AVOID"
    assert final.get("full") is None


def _wait_job(db: Path, job_id: str, terminal: set[str]):
    final = None
    for _ in range(200):
        final = onboard.get_job(db, job_id)
        if final and final["status"] in terminal:
            return final
        time.sleep(0.02)
    return final


def test_onboard_job_error_score_sets_status_error(tmp_path: Path, monkeypatch) -> None:
    """M4: _score returns {"error": ...} on a parse failure (it never raises).
    A preliminary score carrying an "error" key must end the job as 'error',
    not ready_preliminary/ready_full (don't report a non-scored stock OK)."""
    db = tmp_path / "jobs.sqlite"

    def fake_run_onboard(db_path, ts_code, name, industry_id, *,
                         do_codex=True, year=2025, progress=None,
                         on_preliminary=None):
        prelim = {"ts_code": ts_code, "error": "score line not parsed",
                  "raw_tail": "..."}
        if on_preliminary:
            on_preliminary(prelim)
        return {"ts_code": ts_code, "preliminary": prelim}

    monkeypatch.setattr(onboard, "run_onboard", fake_run_onboard)
    job_id = onboard.start_onboard_job(db, "300998.SZ", "解析失败股", "AI_COMPUTE",
                                       do_codex=False)
    final = _wait_job(db, job_id, {"ready_preliminary", "ready_full", "error"})
    assert final is not None and final["status"] == "error"
    assert "score line not parsed" in (final.get("error") or "")


def test_onboard_job_error_full_score_sets_status_error(tmp_path: Path, monkeypatch) -> None:
    """M4 (full path): a good preliminary but an errored full score → 'error'."""
    db = tmp_path / "jobs.sqlite"

    def fake_run_onboard(db_path, ts_code, name, industry_id, *,
                         do_codex=True, year=2025, progress=None,
                         on_preliminary=None):
        prelim = {"ts_code": ts_code, "mode": "neutral", "signal": "WATCH",
                  "short": 0.1, "medium": 0.1, "long": 0.1, "top_path": None}
        if on_preliminary:
            on_preliminary(prelim)
        full = {"ts_code": ts_code, "error": "score line not parsed"}
        return {"ts_code": ts_code, "preliminary": prelim, "full": full}

    monkeypatch.setattr(onboard, "run_onboard", fake_run_onboard)
    job_id = onboard.start_onboard_job(db, "300997.SZ", "全量失败股", "AI_COMPUTE",
                                       do_codex=True)
    final = _wait_job(db, job_id, {"ready_preliminary", "ready_full", "error"})
    assert final is not None and final["status"] == "error"
    assert "full score failed" in (final.get("error") or "")
    # preliminary is still persisted so the UI can show what it got.
    assert final["preliminary"]["signal"] == "WATCH"


def test_try_reserve_onboard_slot_duplicate_and_capacity(monkeypatch) -> None:
    """H2: the admission guard rejects a duplicate ts_code and over-capacity
    requests. We reset the module state and pin a small cap for the test."""
    with onboard._ACTIVE_JOBS_LOCK:
        onboard._ACTIVE_JOBS.clear()
    monkeypatch.setattr(onboard, "MAX_ACTIVE_ONBOARD_JOBS", 2)
    try:
        ok, reason = onboard.try_reserve_onboard_slot("000001.SZ")
        assert ok and reason is None
        # same ts_code again → duplicate (case-insensitive)
        ok, reason = onboard.try_reserve_onboard_slot("000001.sz")
        assert not ok and reason == "duplicate"
        # second distinct code fills the cap
        ok, _ = onboard.try_reserve_onboard_slot("000002.SZ")
        assert ok
        # third distinct code → at capacity
        ok, reason = onboard.try_reserve_onboard_slot("000003.SZ")
        assert not ok and reason == "at_capacity"
        # releasing one frees a slot
        onboard.release_onboard_slot("000001.SZ")
        ok, reason = onboard.try_reserve_onboard_slot("000003.SZ")
        assert ok and reason is None
    finally:
        with onboard._ACTIVE_JOBS_LOCK:
            onboard._ACTIVE_JOBS.clear()


def test_handle_onboard_rejects_long_name(tmp_path: Path) -> None:
    """L4: name longer than 128 chars is rejected with 400 (before any job)."""
    cfg = server.ServerConfig(hot_db_path=tmp_path / "x.sqlite")
    st, _ = server.handle_onboard(cfg, {
        "ts_code": "600519.SH", "industry_id": "DOMESTIC_CONSUMPTION",
        "name": "x" * 129,
    })
    assert st == 400


# ---------------------------------------------------------------------------
# 同花顺 (THS) L2-industry classification path (recognize preferred route).
# Hermetic: stock_basic + the THS index are monkeypatched; no network.
# ---------------------------------------------------------------------------

def _fake_basic(symbol: str, ts_code: str, name: str, industry: str):
    return [{"symbol": symbol, "ts_code": ts_code, "name": name,
             "industry": industry, "market": "主板"}]


def test_ths_map_loads_real_config() -> None:
    """The committed ths_industry_map.yaml resolves a known L2 industry → theme."""
    m = onboard._ths_map()
    assert m.get("半导体") == "SEMI_EQUIPMENT"
    assert m.get("银行") == "FINANCIAL_HIGH_DIVIDEND"
    assert len(m) == 62  # the frozen 62-industry partition


def test_recognize_a_prefers_ths(monkeypatch) -> None:
    """THS hit: industry comes from the THS index, NOT the tushare map — even
    when the tushare industry would have mapped elsewhere."""
    monkeypatch.setattr(onboard, "_stock_basic_a",
                        lambda *a, **k: _fake_basic("688981", "688981.SH", "中芯国际", "半导体"))
    monkeypatch.setattr(onboard, "_ths_members_index",
                        lambda: {"688981.SH": {"ths_industry": "半导体", "theme": "SEMI_EQUIPMENT"}})
    # tushare map would also say SEMI_EQUIPMENT; force it to something else so we
    # can prove the THS branch (source=ths) actually won.
    monkeypatch.setattr(onboard, "_suggest_industries", lambda tind: ["WRONG_FALLBACK"])
    res = onboard.recognize("A", "688981")
    assert res["ok"] is True
    assert res["classification_source"] == "ths"
    assert res["suggested_industry_id"] == "SEMI_EQUIPMENT"
    assert res["candidate_industry_ids"] == ["SEMI_EQUIPMENT"]
    assert res["ths_industry"] == "半导体"


def test_recognize_a_falls_back_to_tushare(monkeypatch) -> None:
    """THS miss (and no refresh) → legacy tushare stock_basic.industry map."""
    monkeypatch.setattr(onboard, "_stock_basic_a",
                        lambda *a, **k: _fake_basic("000001", "000001.SZ", "测试", "IT设备"))
    monkeypatch.setattr(onboard, "_ths_members_index", lambda: {})
    monkeypatch.setattr(onboard, "_ths_refresh_members_index", lambda: False)
    res = onboard.recognize("A", "000001")
    assert res["ok"] is True
    assert res["classification_source"] == "tushare_fallback"
    assert res["suggested_industry_id"] == "AI_COMPUTE"  # IT设备 → AI_COMPUTE
    assert res["ths_industry"] is None


def test_recognize_a_unknown_needs_manual(monkeypatch) -> None:
    """Neither THS nor tushare resolves → needs_manual, no guessed industry."""
    monkeypatch.setattr(onboard, "_stock_basic_a",
                        lambda *a, **k: _fake_basic("000002", "000002.SZ", "测试", "白酒"))
    monkeypatch.setattr(onboard, "_ths_members_index", lambda: {})
    monkeypatch.setattr(onboard, "_ths_refresh_members_index", lambda: False)
    res = onboard.recognize("A", "000002")
    assert res["ok"] is True
    assert res["classification_source"] == "none"
    assert res["needs_manual_classification"] is True
    assert res["suggested_industry_id"] is None
    assert res["candidate_industry_ids"] == []


def test_ths_theme_for_on_demand_refresh_retry(monkeypatch) -> None:
    """On a cache miss the resolver triggers one refresh, then re-reads the index
    and resolves the now-present code."""
    state = {"refreshed": False}

    def fake_index():
        return {"301308.SZ": {"ths_industry": "消费电子", "theme": "CONSUMER_ELECTRONICS"}} \
            if state["refreshed"] else {}

    def fake_refresh():
        state["refreshed"] = True
        return True

    monkeypatch.setattr(onboard, "_ths_members_index", fake_index)
    monkeypatch.setattr(onboard, "_ths_refresh_members_index", fake_refresh)
    theme, ind = onboard._ths_theme_for("301308.SZ")
    assert theme == "CONSUMER_ELECTRONICS"
    assert ind == "消费电子"
    assert state["refreshed"] is True


def test_handle_onboard_guard_duplicate_and_capacity(tmp_path: Path, monkeypatch) -> None:
    """H2 at the HTTP layer: a reserved (in-flight) ts_code → 409, and an
    over-capacity request → 429. Pre-reserve via the public helper so no real
    job thread is spawned (admission is checked before start)."""
    cfg = server.ServerConfig(hot_db_path=tmp_path / "x.sqlite")
    with onboard._ACTIVE_JOBS_LOCK:
        onboard._ACTIVE_JOBS.clear()
    monkeypatch.setattr(onboard, "MAX_ACTIVE_ONBOARD_JOBS", 1)
    try:
        # Reserve 600519.SH out-of-band → the request for it must 409.
        ok, _ = onboard.try_reserve_onboard_slot("600519.SH")
        assert ok
        st, _ = server.handle_onboard(cfg, {
            "ts_code": "600519.SH", "industry_id": "DOMESTIC_CONSUMPTION"})
        assert st == 409  # duplicate in-flight job
        # A *different*, not-in-pool code now hits the capacity cap (1) → 429.
        st, _ = server.handle_onboard(cfg, {
            "ts_code": "000999.SZ", "industry_id": "AI_COMPUTE"})
        assert st == 429
    finally:
        with onboard._ACTIVE_JOBS_LOCK:
            onboard._ACTIVE_JOBS.clear()
