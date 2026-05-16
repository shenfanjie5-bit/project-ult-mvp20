"""Server endpoint tests for ``/api/project-ult/technicals``.

Spins up an ephemeral mvp20 HTTP server pointed at a per-test SQLite
hot snapshot we pre-populate with the 8 L11.tech.* dp_ids, then hits
the endpoint and asserts shape + sub-keys.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from mvp20 import storage
from mvp20.server import ServerConfig, make_handler_class


@pytest.fixture()
def server_with_technicals(tmp_path: Path):
    """Boot a server bound to a tmp SQLite DB that has 6 of 8 indicators
    seeded for ts_code=TEST.TECH (MA/MACD/RSI/KDJ/BOLL/VOL — we leave
    ATR/OBV missing to exercise the "indicator absent" branch)."""

    db_path = tmp_path / "hot.sqlite"
    storage.init_db(db_path)
    now = int(time.time())
    rows = [
        ("TEST.TECH", "L11.tech.ma",
         json.dumps({"ma5": 10.5, "ma10": 10.2, "ma20": 9.8,
                     "ma60": None, "ma120": None, "ma250": None,
                     "as_of": "2026-05-15", "n_bars": 60,
                     "confidence": 0.95}),
         "Known", 0.95, "derived:technical_indicators", now),
        ("TEST.TECH", "L11.tech.macd",
         json.dumps({"dif": 0.32, "dea": 0.18, "hist": 0.28, "cross": "bull",
                     "as_of": "2026-05-15", "n_bars": 60, "confidence": 0.9}),
         "Known", 0.9, "derived:technical_indicators", now),
        ("TEST.TECH", "L11.tech.rsi",
         json.dumps({"rsi6": 68.2, "rsi12": 61.5, "rsi24": 55.0,
                     "as_of": "2026-05-15", "n_bars": 60, "confidence": 0.9}),
         "Known", 0.9, "derived:technical_indicators", now),
        ("TEST.TECH", "L11.tech.kdj",
         json.dumps({"k": 72.0, "d": 65.0, "j": 86.0,
                     "as_of": "2026-05-15", "n_bars": 60, "confidence": 0.85}),
         "Known", 0.85, "derived:technical_indicators", now),
        ("TEST.TECH", "L11.tech.boll",
         json.dumps({"mid": 10.0, "upper": 11.5, "lower": 8.5,
                     "percent_b": 0.66, "bandwidth": 0.3,
                     "as_of": "2026-05-15", "n_bars": 60, "confidence": 0.9}),
         "Known", 0.9, "derived:technical_indicators", now),
        ("TEST.TECH", "L11.tech.vol_ma",
         json.dumps({"vol5": 12000, "vol10": 11000, "vol_ratio_today": 1.8,
                     "as_of": "2026-05-15", "n_bars": 60, "confidence": 0.9}),
         "Known", 0.9, "derived:technical_indicators", now),
    ]
    storage.upsert_realtime(db_path, rows)

    # Bind ephemeral port.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    cfg = ServerConfig(host="127.0.0.1", port=port,
                       cors_origin="http://127.0.0.1:1420",
                       hot_db_path=db_path)
    handler_cls = make_handler_class(cfg)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    yield "127.0.0.1", port
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def _get(host: str, port: int, path: str) -> tuple[int, dict]:
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", path, headers={"Origin": "http://127.0.0.1:1420"})
    resp = conn.getresponse()
    body = json.loads(resp.read().decode())
    conn.close()
    return resp.status, body


def test_technicals_missing_ts_code_400(server_with_technicals) -> None:
    host, port = server_with_technicals
    status, body = _get(host, port, "/api/project-ult/technicals")
    assert status == 400
    assert body["error"]["code"] == "MISSING_PARAM"


def test_technicals_full_pack(server_with_technicals) -> None:
    host, port = server_with_technicals
    status, body = _get(host, port, "/api/project-ult/technicals?ts_code=TEST.TECH")
    assert status == 200
    data = body["data"]
    assert data["ts_code"] == "TEST.TECH"
    assert data["as_of"] == "2026-05-15"
    assert data["n_bars"] == 60

    indicators = data["indicators"]
    # Six seeded indicators present with right shape.
    assert indicators["ma"]["ma5"] == 10.5
    assert indicators["ma"]["ma20"] == 9.8
    assert indicators["macd"]["cross"] == "bull"
    assert indicators["macd"]["hist"] == 0.28
    assert indicators["rsi"]["rsi12"] == 61.5
    assert indicators["kdj"]["k"] == 72.0
    assert indicators["boll"]["upper"] == 11.5
    assert indicators["vol_ma"]["vol_ratio_today"] == 1.8

    # ATR / OBV not seeded → null under indicators (not omitted).
    assert "atr" in indicators
    assert indicators["atr"] is None
    assert "obv" in indicators
    assert indicators["obv"] is None

    freshness = data["freshness"]
    assert freshness["max_age_seconds"] is not None
    assert freshness["stale"] is False


def test_technicals_include_subset(server_with_technicals) -> None:
    host, port = server_with_technicals
    # Comma-separated include
    status, body = _get(host, port,
                        "/api/project-ult/technicals?ts_code=TEST.TECH&include=ma,macd")
    assert status == 200
    indicators = body["data"]["indicators"]
    # Only ma + macd present; the other 6 should not be in the response.
    assert set(indicators.keys()) == {"ma", "macd"}
    assert indicators["ma"]["ma5"] == 10.5
    assert indicators["macd"]["dif"] == 0.32


def test_technicals_unknown_ts_code_returns_null_indicators(
    server_with_technicals,
) -> None:
    host, port = server_with_technicals
    status, body = _get(host, port,
                        "/api/project-ult/technicals?ts_code=UNKNOWN.SZ")
    assert status == 200
    indicators = body["data"]["indicators"]
    # All 8 keys present but all None — the FrontEnd renders "暂无数据" for each.
    assert set(indicators.keys()) == {
        "ma", "macd", "rsi", "kdj", "boll", "vol_ma", "atr", "obv",
    }
    for k, v in indicators.items():
        assert v is None, f"expected null for {k}, got {v}"
