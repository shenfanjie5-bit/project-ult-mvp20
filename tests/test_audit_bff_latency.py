from scripts import audit_bff_latency


def test_url_join_handles_slashes() -> None:
    assert (
        audit_bff_latency._url("http://127.0.0.1:8799/", "/api/health")
        == "http://127.0.0.1:8799/api/health"
    )


def test_summarize_hits_flags_threshold_and_errors() -> None:
    hits = [
        audit_bff_latency.Hit(status=200, ms=10.0, bytes=2, key="ok"),
        audit_bff_latency.Hit(status=200, ms=20.0, bytes=2, key="ok"),
    ]
    summary = audit_bff_latency.summarize_hits(hits, threshold_ms=1000.0)

    assert summary["ok"] is True
    assert summary["under_threshold"] is True
    assert summary["median_ms"] == 15.0
    assert summary["max_ms"] == 20.0


def test_body_key_extracts_status_or_module() -> None:
    assert audit_bff_latency._body_key(b'{"status":"ok"}') == "ok"
    assert audit_bff_latency._body_key(b'{"module":"mvp20-bff"}') == "mvp20-bff"


def test_default_endpoints_cover_frontend_hot_paths() -> None:
    assert "/api/project-ult/aggregate?ts_code=300750.SZ&industry_id=STORAGE_GRID" in (
        audit_bff_latency.DEFAULT_ENDPOINTS
    )
    assert (
        "/api/project-ult/stock-overlay?ts_code=300750.SZ&include_static=0"
        in audit_bff_latency.DEFAULT_ENDPOINTS
    )
    assert "/api/project-ult/market-events?limit=8" in audit_bff_latency.DEFAULT_ENDPOINTS
    assert "/api/project-ult/compat" in audit_bff_latency.DEFAULT_ENDPOINTS
    assert "/api/project-ult/industry-graphs" in audit_bff_latency.DEFAULT_ENDPOINTS
