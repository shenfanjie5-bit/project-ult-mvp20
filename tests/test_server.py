"""Smoke tests for mvp20.server (boots an in-process server, hits each
endpoint, asserts on JSON envelope shape)."""

from __future__ import annotations

import json
import math
import socket
import threading
import time
from http.client import HTTPConnection
from urllib.parse import urlencode

import pytest

from mvp20.server import ServerConfig, make_handler_class
from http.server import ThreadingHTTPServer


@pytest.fixture()
def running_server() -> tuple[str, int, ThreadingHTTPServer, threading.Thread]:
    # Bind to an ephemeral port to avoid collisions with a dev server.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    cfg = ServerConfig(host="127.0.0.1", port=port,
                       cors_origin="http://127.0.0.1:1420")
    handler_cls = make_handler_class(cfg)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    # Wait briefly for the listening socket
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)

    yield "127.0.0.1", port, httpd, thread

    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def _get(host: str, port: int, path: str) -> tuple[int, dict, dict]:
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", path, headers={"Origin": "http://127.0.0.1:1420"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    headers = {k.lower(): v for k, v in resp.getheaders()}
    payload = json.loads(body) if body else {}
    conn.close()
    return resp.status, headers, payload


def test_health_envelope(running_server) -> None:
    host, port, *_ = running_server

    status, headers, body = _get(host, port, "/api/health")

    assert status == 200
    assert "data" in body
    assert body["data"]["service"] == "mvp20"
    assert body["data"]["status"] == "ok"
    # CORS header must be present for the configured origin
    assert headers.get("access-control-allow-origin") == "http://127.0.0.1:1420"


def test_project_ult_health(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/health")
    assert status == 200
    assert body["data"]["lock_module_count"] == 14


def test_compat(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/compat")
    assert status == 200
    assert body["data"]["schema_versions"]["manifest"] == 2


def test_manifests_latest_includes_universe_and_industries(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/manifests/latest")
    assert status == 200
    data = body["data"]
    assert data["universe"]["universe_id"] == "mvp-13-industry-v1"
    assert "industries" in data["industries"]
    assert len(data["industries"]["industries"]) == 13


def test_modules_lock_returned(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/modules")
    assert status == 200
    modules = body["data"]["modules"]
    assert "frontend-api" in modules
    assert "contracts" in modules


def test_providers_returns_validation_summary(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/reasoner/providers")
    assert status == 200
    validation = body["data"]["validation"]
    assert validation["ok"] is True
    assert "fmp" in validation["active_providers"]
    assert "futu" in validation["active_providers"]


def test_profiles_returns_universe_constituents(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/profiles")
    assert status == 200
    assert body["data"]["universe_total"] >= 300
    assert body["data"]["total"] == body["data"]["universe_total"]


def test_profiles_filter_by_industry(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"industry": "AI_COMPUTE"})
    status, _, body = _get(host, port, f"/api/project-ult/profiles{qs}")
    assert status == 200
    profiles = body["data"]["profiles"]
    # Each returned profile must include AI_COMPUTE
    for p in profiles:
        assert "AI_COMPUTE" in p["industry_ids"]


def test_industry_graphs_index(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/industry-graphs")
    assert status == 200
    assert len(body["data"]["graphs"]) == 12  # SPACE_ECONOMY pending


def test_industry_graph_specific(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"industry_id": "AI_COMPUTE"})
    status, _, body = _get(host, port, f"/api/project-ult/industry-graphs{qs}")
    assert status == 200
    assert body["data"]["industry_id"] == "AI_COMPUTE"
    assert "priors" in body["data"]


def test_industry_graph_unknown_returns_404(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"industry_id": "NOT_REAL"})
    status, _, body = _get(host, port, f"/api/project-ult/industry-graphs{qs}")
    assert status == 404
    assert body["error"]["code"] == "INDUSTRY_GRAPH_NOT_FOUND"


def test_cycles_returns_empty_list(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/cycles")
    assert status == 200
    assert body["data"]["cycles"] == []


def test_admin_alerts_handled_by_mvp20_bff(running_server) -> None:
    """frontend-api is NOT vendored under upstream/ — FrontEnd/ is the only
    frontend in this repo, and mvp20 server.py is the BFF. /api/admin/* and
    /api/alerts/* return 200 stub envelopes owned by mvp20 itself rather
    than 503 UPSTREAM_NOT_RUNNING."""
    host, port, *_ = running_server
    for path in ("/api/admin/foo", "/api/alerts/bar"):
        status, _, body = _get(host, port, path)
        assert status == 200, f"{path} expected 200, got {status}; body={body}"
        assert body["data"]["module"] == "mvp20-bff"
        assert body["data"]["fixture"] is True


# Skeleton-wired adapter routes — should all 200 because vendor packages are
# installed in editable mode under `upstream/`. If vendor import fails (e.g.
# in a stripped environment without `pip install -e ./upstream/<name>`), the
# adapter falls back to 503 UPSTREAM_UNAVAILABLE — that case is exercised by
# test_adapter_import_fallback_returns_503.
_ADAPTER_ROUTES = [
    "/api/project-ult/graph/test",
    "/api/project-ult/data/canonical/some_table",
    "/api/project-ult/data/raw/some_table",
    "/api/project-ult/entities",
    "/api/project-ult/entities/ENT_X",
    "/api/project-ult/reasoner/results",
    "/api/project-ult/cycles/cycle-2026q1",
    "/api/stocks/300750",
    "/api/pool/observation",
    "/api/world-state/latest",
    "/api/project-ult/audit/audit-x",
    "/api/audit/replay/foo",
    "/api/project-ult/backtests",
    "/api/backtest/list",
]


@pytest.mark.parametrize("path", _ADAPTER_ROUTES)
def test_adapter_routes_return_200(running_server, path: str) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, path)
    assert status == 200, f"{path} expected 200, got {status}; body={body}"
    assert "data" in body, f"{path} missing 'data' in envelope: {body}"
    data = body["data"]
    assert data.get("fixture") is True, f"{path} fixture flag missing: {data}"
    assert data.get("wire_depth") == "skeleton", f"{path} wire_depth wrong: {data}"
    assert data.get("module"), f"{path} missing module label: {data}"


def test_adapter_import_fallback_returns_503(running_server, monkeypatch) -> None:
    """When an adapter's vendor package is unavailable (e.g. uninstalled or
    runtime deps missing), the adapter must return a 503 envelope with
    error.code == 'UPSTREAM_UNAVAILABLE' instead of crashing the handler."""
    from mvp20.adapters import graph_engine as ge

    monkeypatch.setattr(ge, "_AVAILABLE", False)
    monkeypatch.setattr(ge, "_IMPORT_ERR", "ModuleNotFoundError: simulated")

    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/graph/test")
    assert status == 503
    assert body["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert body["error"]["details"]["upstream_module"] == "graph-engine"
    assert "simulated" in body["error"]["details"]["import_error"]


def test_unknown_api_path_returns_404_envelope(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/totally/bogus/path")
    assert status == 404
    assert body["error"]["code"] == "ROUTE_NOT_FOUND"


def test_non_api_path_rejected(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/index.html")
    assert status == 404
    assert body["error"]["code"] == "NOT_API_PATH"


def test_stock_overlay_missing_param_returns_400(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port, "/api/project-ult/stock-overlay")
    assert status == 400
    assert body["error"]["code"] == "MISSING_PARAM"


def test_stock_overlay_unknown_ts_code_returns_404(running_server) -> None:
    host, port, *_ = running_server
    status, _, body = _get(host, port,
                            "/api/project-ult/stock-overlay?ts_code=NEVER.EXIST")
    assert status == 404
    assert body["error"]["code"] == "OVERLAY_NOT_FOUND"
    assert body["error"]["details"]["ts_code"] == "NEVER.EXIST"


def test_stock_overlay_merges_static_and_realtime(running_server, tmp_path) -> None:
    """End-to-end: write a temp YAML overlay + temp SQLite, hit endpoint.
    This bypasses running_server's default config paths by using a fresh
    cfg with tmp_path-rooted overlays. We use a dedicated server."""
    from pathlib import Path
    from mvp20.server import ServerConfig, make_handler_class
    from mvp20.storage import upsert_realtime
    import socket as _socket
    import threading as _threading
    from http.server import ThreadingHTTPServer as _TS

    # Set up isolated dirs
    overlays_dir = tmp_path / "stock_overlays"
    overlays_dir.mkdir()
    industry_dir = tmp_path / "industry_overlays"
    industry_dir.mkdir()
    (overlays_dir / "TEST.SZ.yaml").write_text(
        "ts_code: TEST.SZ\nname: 测试公司\nindustry_ids: [TEST_IND]\n"
        "schema_version: 1\nperiod: 2026-Q1\n",
        encoding="utf-8",
    )
    (industry_dir / "TEST_IND.yaml").write_text(
        "industry_id: TEST_IND\nschema_version: 1\nperiod: 2026-Q1\n",
        encoding="utf-8",
    )
    hot_db = tmp_path / "hot.sqlite"
    upsert_realtime(hot_db, [
        ("TEST.SZ", "L7.flow.netbuy", {"scalar": 12345.0},
         "Known", 0.7, "tushare", int(time.time())),
        ("TEST.SZ", "L7.trade.iv", {"scalar": 0.45},
         "Known", 0.6, "futu", int(time.time())),
    ])

    sock = _socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    cfg = ServerConfig(
        host="127.0.0.1", port=port, cors_origin="http://127.0.0.1:1420",
        stock_overlays_dir=overlays_dir,
        industry_overlays_dir=industry_dir,
        hot_db_path=hot_db,
    )
    httpd = _TS((cfg.host, cfg.port), make_handler_class(cfg))
    thread = _threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(20):
            try:
                _socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)
        status, _h, body = _get("127.0.0.1", port,
                                 "/api/project-ult/stock-overlay?ts_code=TEST.SZ")
        assert status == 200
        data = body["data"]
        assert data["ts_code"] == "TEST.SZ"
        assert data["static"]["name"] == "测试公司"
        assert data["industry_context"]["industry_id"] == "TEST_IND"
        assert set(data["realtime"].keys()) == {"L7.flow.netbuy", "L7.trade.iv"}
        assert data["freshness"]["realtime_node_count"] == 2
        assert data["freshness"]["static_period"] == "2026-Q1"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_stock_overlay_response_replaces_nan_with_null(tmp_path) -> None:
    """Browser JSON.parse rejects Python's default NaN tokens."""
    from mvp20.server import ServerConfig, make_handler_class
    from mvp20.storage import upsert_realtime
    import socket as _socket
    import threading as _threading
    from http.server import ThreadingHTTPServer as _TS

    overlays_dir = tmp_path / "stock_overlays"
    overlays_dir.mkdir()
    industry_dir = tmp_path / "industry_overlays"
    industry_dir.mkdir()
    (overlays_dir / "TEST.SZ.yaml").write_text(
        "ts_code: TEST.SZ\nname: 测试公司\nindustry_ids: [TEST_IND]\n"
        "schema_version: 1\nperiod: 2026-Q1\n",
        encoding="utf-8",
    )
    (industry_dir / "TEST_IND.yaml").write_text(
        "industry_id: TEST_IND\nschema_version: 1\nperiod: 2026-Q1\n",
        encoding="utf-8",
    )
    hot_db = tmp_path / "hot.sqlite"
    upsert_realtime(hot_db, [
        (
            "TEST.SZ",
            "L7.dividend",
            {"pay_date": math.nan, "record_date": math.nan},
            "Known",
            0.7,
            "test",
            int(time.time()),
        ),
    ])

    sock = _socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    cfg = ServerConfig(
        host="127.0.0.1", port=port, cors_origin="http://127.0.0.1:1420",
        stock_overlays_dir=overlays_dir,
        industry_overlays_dir=industry_dir,
        hot_db_path=hot_db,
    )
    httpd = _TS((cfg.host, cfg.port), make_handler_class(cfg))
    thread = _threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(20):
            try:
                _socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/project-ult/stock-overlay?ts_code=TEST.SZ")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()

        assert resp.status == 200
        assert "NaN" not in body
        payload = json.loads(body)
        value = payload["data"]["realtime"]["L7.dividend"]["value"]
        assert value == {"pay_date": None, "record_date": None}
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_stock_overlay_endpoint_primary_default_and_industry_switch(tmp_path) -> None:
    """Compiled SQLite snapshots are the preferred API read path."""
    from mvp20.server import ServerConfig, make_handler_class
    from mvp20.storage import replace_compiled_overlays, upsert_realtime
    import socket as _socket
    import threading as _threading
    from http.server import ThreadingHTTPServer as _TS

    now = int(time.time())
    hot_db = tmp_path / "hot.sqlite"
    upsert_realtime(hot_db, [
        ("SWITCH.SZ", "L7.flow.netbuy", {"scalar": 1}, "Known", 0.8, "test", now),
    ])
    replace_compiled_overlays(
        hot_db,
        manifests=[
            {
                "ts_code": "SWITCH.SZ",
                "industry_id": "PRIMARY_IND",
                "overlay_path": "config/stock_overlays/PRIMARY_IND/SWITCH.SZ.yaml",
                "period": "2026-Q1",
                "primary_industry": 1,
                "overlay_status": "compiled",
                "updated_at": now,
            },
            {
                "ts_code": "SWITCH.SZ",
                "industry_id": "SECONDARY_IND",
                "overlay_path": "config/stock_overlays/SECONDARY_IND/SWITCH.SZ.yaml",
                "period": "2026-Q1",
                "primary_industry": 0,
                "overlay_status": "compiled",
                "updated_at": now,
            },
        ],
        nodes=[],
        edges=[],
        snapshots=[
            {
                "ts_code": "SWITCH.SZ",
                "industry_id": "PRIMARY_IND",
                "payload_json": json.dumps({
                    "ts_code": "SWITCH.SZ",
                    "industry_id": "PRIMARY_IND",
                    "available_industries": ["PRIMARY_IND", "SECONDARY_IND"],
                    "compiled_graph": {"nodes": [{"node_id": "p"}], "views": {}},
                    "scores": {"stock_final_score": {"current_mode": "等待验证"}},
                    "coverage": {"data_coverage": None},
                    "alerts": [],
                    "static_overlay": {"period": "2026-Q1", "name": "主行业"},
                    "compiled_at": now,
                }, ensure_ascii=False),
                "graph_version": "stock-overlay-v2",
                "data_version": "2026-Q1",
                "updated_at": now,
            },
            {
                "ts_code": "SWITCH.SZ",
                "industry_id": "SECONDARY_IND",
                "payload_json": json.dumps({
                    "ts_code": "SWITCH.SZ",
                    "industry_id": "SECONDARY_IND",
                    "available_industries": ["PRIMARY_IND", "SECONDARY_IND"],
                    "compiled_graph": {"nodes": [{"node_id": "s"}], "views": {}},
                    "scores": {"stock_final_score": {"current_mode": "等待验证"}},
                    "coverage": {"data_coverage": None},
                    "alerts": [],
                    "static_overlay": {"period": "2026-Q1", "name": "副行业"},
                    "compiled_at": now,
                }, ensure_ascii=False),
                "graph_version": "stock-overlay-v2",
                "data_version": "2026-Q1",
                "updated_at": now,
            },
        ],
        alerts=[],
    )

    sock = _socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    cfg = ServerConfig(host="127.0.0.1", port=port,
                       cors_origin="http://127.0.0.1:1420",
                       hot_db_path=hot_db)
    httpd = _TS((cfg.host, cfg.port), make_handler_class(cfg))
    thread = _threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(20):
            try:
                _socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

        status, _h, body = _get("127.0.0.1", port,
                                 "/api/project-ult/stock-overlay?ts_code=SWITCH.SZ")
        assert status == 200
        data = body["data"]
        assert data["industry_id"] == "PRIMARY_IND"
        assert data["available_industries"] == ["PRIMARY_IND", "SECONDARY_IND"]
        assert data["compiled_graph"]["nodes"][0]["node_id"] == "p"
        assert set(data["realtime"]) == {"L7.flow.netbuy"}

        status, _h, body = _get(
            "127.0.0.1",
            port,
            "/api/project-ult/stock-overlay?ts_code=SWITCH.SZ&industry_id=SECONDARY_IND",
        )
        assert status == 200
        assert body["data"]["industry_id"] == "SECONDARY_IND"
        assert body["data"]["compiled_graph"]["nodes"][0]["node_id"] == "s"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_sse_stream_emits_initial_snapshot(running_server, tmp_path) -> None:
    """SSE smoke: open the stream, read until first data event, verify
    snapshot shape, then close. Uses ephemeral cfg so we control the DB."""
    from mvp20.server import ServerConfig, make_handler_class
    from mvp20.storage import upsert_realtime
    import socket as _socket
    import threading as _threading
    from http.server import ThreadingHTTPServer as _TS

    hot_db = tmp_path / "hot.sqlite"
    upsert_realtime(hot_db, [
        ("SSE.SZ", "dp1", {"v": 1}, "Known", 0.5, "test", int(time.time())),
    ])
    sock = _socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    cfg = ServerConfig(host="127.0.0.1", port=port,
                       cors_origin="http://127.0.0.1:1420",
                       hot_db_path=hot_db)
    httpd = _TS((cfg.host, cfg.port), make_handler_class(cfg))
    thread = _threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(20):
            try:
                _socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

        # Open SSE
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET",
                     "/api/project-ult/stream/realtime?ts_code=SSE.SZ&industry_id=TEST_IND&poll_seconds=1")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type", "").startswith("text/event-stream")
        # Read up to ~1KB to capture the initial snapshot frame
        buf = b""
        for _ in range(50):
            chunk = resp.fp.read1(256)
            if not chunk:
                break
            buf += chunk
            if b"\"kind\": \"snapshot\"" in buf:
                break
        conn.close()
        text = buf.decode("utf-8", errors="replace")
        assert "retry: 5000" in text
        assert "\"kind\": \"snapshot\"" in text
        assert "\"ts_code\": \"SSE.SZ\"" in text
        assert "\"industry_id\": \"TEST_IND\"" in text
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_options_preflight_returns_cors_headers(running_server) -> None:
    host, port, *_ = running_server
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("OPTIONS", "/api/health",
                 headers={"Origin": "http://127.0.0.1:1420"})
    resp = conn.getresponse()
    resp.read()
    headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    assert resp.status == 204
    assert headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert "GET" in headers["access-control-allow-methods"]


def test_post_rejected(running_server) -> None:
    host, port, *_ = running_server
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("POST", "/api/health", body=b"{}",
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    body = json.loads(resp.read().decode("utf-8"))
    conn.close()
    assert resp.status == 405
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# Derived-layer endpoints — A1 aggregator, A2 coverage, A3 scoring
# ---------------------------------------------------------------------------


def test_aggregate_endpoint_returns_per_node_scores(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "300750.SZ", "industry_id": "STORAGE_GRID"})
    status, _h, body = _get(host, port, f"/api/project-ult/aggregate{qs}")
    assert status == 200, body
    data = body["data"]
    assert data["ts_code"] == "300750.SZ"
    assert data["industry_id"] == "STORAGE_GRID"
    nodes = data["nodes"]
    assert isinstance(nodes, dict) and len(nodes) > 0
    sample = next(iter(nodes.values()))
    # Each aggregated node carries the three-horizon mix + parent rollup.
    for key in ("score", "short_score", "medium_score", "long_score",
                "confidence", "data_coverage"):
        assert key in sample, f"missing {key} in {sample}"


def test_aggregate_missing_ts_code_returns_400(running_server) -> None:
    host, port, *_ = running_server
    status, _h, body = _get(host, port, "/api/project-ult/aggregate")
    assert status == 400
    assert body["error"]["code"] == "MISSING_PARAM"


def test_aggregate_unknown_ts_code_returns_404(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "NEVER.EXIST"})
    status, _h, body = _get(host, port, f"/api/project-ult/aggregate{qs}")
    assert status == 404
    assert body["error"]["code"] == "OVERLAY_NOT_FOUND"


def test_coverage_endpoint_returns_overall_and_per_node(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "300750.SZ", "industry_id": "STORAGE_GRID"})
    status, _h, body = _get(host, port, f"/api/project-ult/coverage{qs}")
    assert status == 200, body
    data = body["data"]
    assert data["ts_code"] == "300750.SZ"
    assert data["industry_id"] == "STORAGE_GRID"
    assert 0.0 <= data["overall_data_coverage"] <= 1.0
    assert data["warning_level"] in (
        "ok", "below_average", "low_confidence", "no_strong_conclusion",
    )
    assert isinstance(data["per_node"], dict)
    assert isinstance(data["alerts"], list)
    assert "totals" in data


def test_coverage_missing_ts_code_returns_400(running_server) -> None:
    host, port, *_ = running_server
    status, _h, body = _get(host, port, "/api/project-ult/coverage")
    assert status == 400
    assert body["error"]["code"] == "MISSING_PARAM"


def test_coverage_unknown_ts_code_returns_404(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "NEVER.EXIST"})
    status, _h, body = _get(host, port, f"/api/project-ult/coverage{qs}")
    assert status == 404
    assert body["error"]["code"] == "OVERLAY_NOT_FOUND"


def test_score_endpoint_returns_mode_and_signal(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "300750.SZ", "industry_id": "STORAGE_GRID"})
    status, _h, body = _get(host, port, f"/api/project-ult/score{qs}")
    assert status == 200, body
    data = body["data"]
    assert data["ts_code"] == "300750.SZ"
    assert data["industry_id"] == "STORAGE_GRID"
    # Mode + signal are the headline frontend fields.
    assert data["mode"], f"empty mode in {data}"
    assert data["trading_signal"] in {"BUY", "HOLD", "WATCH", "AVOID"}
    assert "mode_confidence" in data
    assert "mode_rationale" in data
    # Horizon mix + paths + final/company scores must round-trip.
    for k in ("short_total", "medium_total", "long_total"):
        assert isinstance(data[k], (int, float)), f"{k}={data[k]!r}"
    assert "company_score" in data
    assert "final_score" in data
    top_paths = data["top_paths"]
    assert isinstance(top_paths.get("positive"), list)
    assert isinstance(top_paths.get("negative"), list)


def test_score_missing_ts_code_returns_400(running_server) -> None:
    host, port, *_ = running_server
    status, _h, body = _get(host, port, "/api/project-ult/score")
    assert status == 400
    assert body["error"]["code"] == "MISSING_PARAM"


def test_score_unknown_ts_code_returns_404(running_server) -> None:
    host, port, *_ = running_server
    qs = "?" + urlencode({"ts_code": "NEVER.EXIST"})
    status, _h, body = _get(host, port, f"/api/project-ult/score{qs}")
    assert status == 404
    assert body["error"]["code"] == "OVERLAY_NOT_FOUND"
