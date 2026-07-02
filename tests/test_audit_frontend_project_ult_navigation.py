import json
from pathlib import Path

from scripts import audit_frontend_project_ult_navigation as audit


def test_extract_app_routes_marks_project_ult_and_guarded_routes() -> None:
    text = """
    <Route path="/" element={<MarketOverviewPage />} />
    <Route path="/stock/:id" element={<ProjectUltBlockedRoute><StockDetailPage /></ProjectUltBlockedRoute>} />
    <Route path="/project-ult/system" element={<SystemMapPage />} />
    <Route path="*" element={<UnknownRouteFallback />} />
    """

    routes = audit.extract_app_routes(text)

    assert [row["path"] for row in routes] == ["/", "/stock/:id", "/project-ult/system"]
    assert routes[1]["sample_path"] == "/stock/300750.SZ"
    assert routes[1]["project_ult_blocked"] is True
    assert routes[2]["project_ult_native"] is True


def test_navigation_contract_matches_routes_links_and_shell_latency(tmp_path: Path) -> None:
    app = tmp_path / "App.tsx"
    links = tmp_path / "links.ts"
    shell = tmp_path / "shell.json"
    app.write_text(
        """
        <Route path="/" element={<MarketOverviewPage />} />
        <Route path="/pool" element={<PoolManagementPage />} />
        <Route path="/project-ult/system" element={<SystemMapPage />} />
        """,
        encoding="utf-8",
    )
    links.write_text(
        """
        export const PROJECT_ULT_READ_ONLY_LINKS = [
          { label: 'System Map', path: '/project-ult/system', eyebrow: 'API-1', description: 'health' },
          { label: 'Market Overview', path: '/', eyebrow: 'API-2B', description: 'world' },
        ]
        """,
        encoding="utf-8",
    )
    shell_routes = {
        "/?data_mode=projectUlt": {"ok": True, "under_threshold": True, "max_ms": 10},
        "/pool?data_mode=projectUlt": {"ok": True, "under_threshold": True, "max_ms": 11},
        "/project-ult/system?data_mode=projectUlt": {
            "ok": True,
            "under_threshold": True,
            "max_ms": 12,
        },
    }
    shell.write_text(
        json.dumps(
            {
                "route_count": len(shell_routes),
                "all_ok": True,
                "all_under_threshold": True,
                "max_observed_ms": 12,
                "routes": shell_routes,
            }
        ),
        encoding="utf-8",
    )

    report = audit.build_report(app_source=app, link_source=links, shell_latency_path=shell)

    assert report["all_ok"] is True
    assert report["summary"]["app_route_count"] == 3
    assert report["summary"]["read_only_link_count"] == 2
    assert report["summary"]["missing_route_shell_count"] == 0
    assert report["summary"]["missing_link_shell_count"] == 0
    assert report["summary"]["undeclared_read_only_link_count"] == 0


def test_navigation_contract_reports_missing_shell_latency(tmp_path: Path) -> None:
    app = tmp_path / "App.tsx"
    links = tmp_path / "links.ts"
    shell = tmp_path / "shell.json"
    app.write_text(
        '<Route path="/project-ult/evidence" element={<EvidenceConsolePage />} />',
        encoding="utf-8",
    )
    links.write_text(
        "export const PROJECT_ULT_READ_ONLY_LINKS = ["
        "{ label: 'Evidence', path: '/project-ult/evidence', eyebrow: 'API-4A', description: 'audit' }"
        "]",
        encoding="utf-8",
    )
    shell.write_text(
        json.dumps(
            {
                "route_count": 0,
                "all_ok": True,
                "all_under_threshold": True,
                "max_observed_ms": 0,
                "routes": {},
            }
        ),
        encoding="utf-8",
    )

    report = audit.build_report(app_source=app, link_source=links, shell_latency_path=shell)

    assert report["all_ok"] is False
    assert report["missing_route_shell"] == ["/project-ult/evidence?data_mode=projectUlt"]
    assert report["missing_link_shell"] == ["/project-ult/evidence?data_mode=projectUlt"]
