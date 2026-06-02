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
            progress(6, "score_preliminary")
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
