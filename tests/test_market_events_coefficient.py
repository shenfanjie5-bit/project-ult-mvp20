"""handle_market_events: validated forecast coefficient + unvalidated news.

Calls the handler directly against a temp hot.sqlite (no running server needed).
"""
from __future__ import annotations

import datetime
import time

from mvp20.server import ServerConfig, handle_market_events
from mvp20.storage import upsert_realtime


def _cfg(tmp_path):
    overlays_dir = tmp_path / "stock_overlays"
    overlays_dir.mkdir()
    industry_dir = tmp_path / "industry_overlays"
    industry_dir.mkdir()
    return ServerConfig(
        host="127.0.0.1", port=0, cors_origin="http://127.0.0.1:1420",
        stock_overlays_dir=overlays_dir, industry_overlays_dir=industry_dir,
        hot_db_path=tmp_path / "hot.sqlite",
    )


def _seed(tmp_path):
    now = int(time.time())
    today = datetime.date.today().strftime("%Y%m%d")
    now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upsert_realtime(tmp_path / "hot.sqlite", [
        # recent positive forecast → validated positive coefficient
        ("000021.SZ", "L9.company.earnings_guidance",
         {"type": "预增", "change_pct_min": 50.0, "change_pct_max": 80.0,
          "ann_date": today, "period": "20251231"},
         "Known", 0.85, "tushare:forecast", now),
        # recent negative forecast → validated negative coefficient
        ("000009.SZ", "L9.company.earnings_guidance",
         {"type": "预减", "change_pct_min": -77.0, "change_pct_max": -69.0,
          "ann_date": today, "period": "20251231"},
         "Known", 0.85, "tushare:forecast", now),
        # STALE forecast (2016) → must be excluded as not real-time
        ("000001.SZ", "L9.company.earnings_guidance",
         {"type": "略增", "change_pct_min": 5.0, "change_pct_max": 15.0,
          "ann_date": "20160121", "period": "20151231"},
         "Known", 0.85, "tushare:forecast", now),
        # 不确定 forecast → no clear direction → skipped (never shown as 0)
        ("000333.SZ", "L9.company.earnings_guidance",
         {"type": "不确定", "ann_date": today, "period": "20251231"},
         "Known", 0.85, "tushare:forecast", now),
        # free-text news → coefficient null + validated:false
        ("600000.SH", "L9.event.intraday_news",
         {"top_headlines": [{"title": "某公司中标大单", "time": now_dt,
                             "url": "http://x", "source": "EM"}]},
         "Known", 0.6, "akshare:em_news", now),
    ])


def test_forecast_events_carry_validated_coefficient(tmp_path):
    _seed(tmp_path)
    status, env = handle_market_events(_cfg(tmp_path), {"limit": ["20"]})
    assert status == 200
    by_code = {e["ts_code"]: e for e in env["data"]["events"]}

    pos = by_code["000021.SZ"]
    assert pos["coefficient"] > 0.7
    assert pos["coefficient_meta"]["validated"] is True
    assert pos["coefficient_meta"]["direction"] == "positive"
    assert "业绩预告" in pos["title"]

    neg = by_code["000009.SZ"]
    assert neg["coefficient"] < -0.7
    assert "short_leg_survivorship_fragile" in neg["coefficient_meta"]["caveats"]


def test_stale_and_directionless_forecasts_excluded(tmp_path):
    _seed(tmp_path)
    _status, env = handle_market_events(_cfg(tmp_path), {"limit": ["20"]})
    codes = {e["ts_code"] for e in env["data"]["events"]}
    assert "000001.SZ" not in codes   # 2016 forecast is stale
    assert "000333.SZ" not in codes   # 不确定 has no direction


def test_news_events_unvalidated_null_coefficient(tmp_path):
    _seed(tmp_path)
    _status, env = handle_market_events(_cfg(tmp_path), {"limit": ["20"]})
    news = next(e for e in env["data"]["events"] if e["ts_code"] == "600000.SH")
    assert news["coefficient"] is None
    assert news["coefficient_meta"]["validated"] is False
    assert news["coefficient_meta"]["reason"] == "track_b_forward_only"


def test_no_dockcase_writeback_side_effect(tmp_path, monkeypatch):
    # The handler must never flip DockCase write-back on.
    monkeypatch.delenv("DOCKCASE_WRITEBACK", raising=False)
    _seed(tmp_path)
    handle_market_events(_cfg(tmp_path), {"limit": ["5"]})
    import os
    assert os.environ.get("DOCKCASE_WRITEBACK") in (None, "0")
