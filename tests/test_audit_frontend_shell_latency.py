from scripts import audit_frontend_shell_latency


def test_url_join_handles_route_slashes() -> None:
    assert (
        audit_frontend_shell_latency._url("http://127.0.0.1:1421/", "/pool?data_mode=projectUlt")
        == "http://127.0.0.1:1421/pool?data_mode=projectUlt"
    )


def test_is_spa_shell_requires_html_root_and_script() -> None:
    assert audit_frontend_shell_latency._is_spa_shell(
        b'<html><body><div id="root"></div><script type="module"></script></body></html>',
        "text/html; charset=utf-8",
    )
    assert not audit_frontend_shell_latency._is_spa_shell(b'{"ok": true}', "application/json")
    assert not audit_frontend_shell_latency._is_spa_shell(
        b'<html><body><div id="root"></div></body></html>',
        "text/html",
    )


def test_summarize_hits_flags_shell_and_threshold() -> None:
    hits = [
        audit_frontend_shell_latency.Hit(
            status=200,
            ms=40.0,
            bytes=100,
            content_type="text/html",
            shell_ok=True,
        ),
        audit_frontend_shell_latency.Hit(
            status=200,
            ms=60.0,
            bytes=100,
            content_type="text/html",
            shell_ok=True,
        ),
    ]
    summary = audit_frontend_shell_latency.summarize_hits(hits, threshold_ms=1000.0)

    assert summary["ok"] is True
    assert summary["under_threshold"] is True
    assert summary["median_ms"] == 50.0
    assert summary["max_ms"] == 60.0
