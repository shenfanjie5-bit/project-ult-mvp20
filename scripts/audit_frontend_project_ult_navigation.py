#!/usr/bin/env python3
"""Audit Project ULT frontend route/navigation coverage against latency evidence."""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


DEFAULT_APP_SOURCE = "FrontEnd/src/App.tsx"
DEFAULT_LINK_SOURCE = "FrontEnd/src/components/projectUlt/projectUltReadOnlyLinks.ts"
DEFAULT_SHELL_LATENCY = "docs/audit/frontend_shell_latency_2026-06-19.json"
DEFAULT_OUTPUT = "docs/audit/frontend_project_ult_navigation_2026-06-19.json"

ROUTE_RE = re.compile(r"<Route\s+path=\"([^\"]+)\"[^>]*element=\{(.+?)\}\s*/?>")
LINK_OBJECT_RE = re.compile(r"\{(?P<body>[^{}]*?label:\s*'[^']+'[^{}]*?path:\s*'[^']+'[^{}]*?)\}", re.S)
FIELD_RE = re.compile(r"(?P<field>label|path|eyebrow|description):\s*'(?P<value>[^']*)'")

SAMPLE_VALUES = {
    "/audit/:cycleId": "/audit/CYCLE_20260424",
    "/admin/:tab": "/admin/health",
    "/stock/:id": "/stock/300750.SZ",
}


def _with_data_mode(path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}data_mode=projectUlt"


def _sample_route(path: str) -> tuple[str, str]:
    if path in SAMPLE_VALUES:
        return SAMPLE_VALUES[path], "dynamic_sample"
    return path, "direct"


def _route_payload(path: str, element: str) -> dict[str, Any]:
    sample_path, sample_strategy = _sample_route(path)
    return {
        "path": path,
        "sample_path": sample_path,
        "audit_route": _with_data_mode(sample_path),
        "sample_strategy": sample_strategy,
        "project_ult_blocked": "ProjectUltBlockedRoute" in element,
        "redirect": "Navigate" in element or "GraphRoute" in element,
        "project_ult_native": path.startswith("/project-ult/"),
    }


def extract_app_routes(text: str) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for match in ROUTE_RE.finditer(text):
        path = match.group(1)
        if path == "*":
            continue
        routes.append(_route_payload(path, match.group(2)))
    return routes


def extract_read_only_links(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for match in LINK_OBJECT_RE.finditer(text):
        fields = {m.group("field"): m.group("value") for m in FIELD_RE.finditer(match.group("body"))}
        if {"label", "path", "eyebrow", "description"}.issubset(fields):
            links.append(fields)
    return links


def build_report(
    *,
    app_source: Path,
    link_source: Path,
    shell_latency_path: Path,
) -> dict[str, Any]:
    app_text = app_source.read_text(encoding="utf-8")
    link_text = link_source.read_text(encoding="utf-8")
    routes = extract_app_routes(app_text)
    links = extract_read_only_links(link_text)
    shell_latency = json.loads(shell_latency_path.read_text(encoding="utf-8"))
    shell_routes = shell_latency.get("routes", {})
    shell_route_set = set(shell_routes)

    route_rows = []
    for route in routes:
        audit_route = route["audit_route"]
        shell_row = shell_routes.get(audit_route, {})
        route_rows.append(
            {
                **route,
                "shell_latency_covered": audit_route in shell_route_set,
                "shell_ok": bool(shell_row.get("ok")),
                "shell_under_threshold": bool(shell_row.get("under_threshold")),
                "shell_max_ms": shell_row.get("max_ms"),
            }
        )

    link_rows = []
    for link in links:
        audit_route = _with_data_mode(link["path"])
        shell_row = shell_routes.get(audit_route, {})
        route_match = next(
            (row for row in route_rows if row["sample_path"] == link["path"]),
            None,
        )
        link_rows.append(
            {
                **link,
                "audit_route": audit_route,
                "app_route_declared": route_match is not None,
                "shell_latency_covered": audit_route in shell_route_set,
                "shell_ok": bool(shell_row.get("ok")),
                "shell_under_threshold": bool(shell_row.get("under_threshold")),
                "shell_max_ms": shell_row.get("max_ms"),
            }
        )

    missing_route_shell = [
        row["audit_route"]
        for row in route_rows
        if not row["shell_latency_covered"]
    ]
    missing_link_shell = [
        row["audit_route"]
        for row in link_rows
        if not row["shell_latency_covered"]
    ]
    undeclared_links = [
        row["path"]
        for row in link_rows
        if not row["app_route_declared"]
    ]
    app_routes_ok = all(
        row["shell_latency_covered"] and row["shell_ok"] and row["shell_under_threshold"]
        for row in route_rows
    )
    read_only_links_ok = all(
        row["app_route_declared"]
        and row["shell_latency_covered"]
        and row["shell_ok"]
        and row["shell_under_threshold"]
        for row in link_rows
    )
    all_ok = bool(
        shell_latency.get("all_ok")
        and shell_latency.get("all_under_threshold")
        and app_routes_ok
        and read_only_links_ok
    )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scan_mode": "source_route_registry_plus_shell_latency_contract",
        "app_source": str(app_source),
        "link_source": str(link_source),
        "shell_latency_path": str(shell_latency_path),
        "all_ok": all_ok,
        "summary": {
            "app_route_count": len(route_rows),
            "app_routes_shell_covered": sum(1 for row in route_rows if row["shell_latency_covered"]),
            "project_ult_native_routes": sum(1 for row in route_rows if row["project_ult_native"]),
            "project_ult_blocked_routes": sum(1 for row in route_rows if row["project_ult_blocked"]),
            "read_only_link_count": len(link_rows),
            "read_only_links_declared": sum(1 for row in link_rows if row["app_route_declared"]),
            "read_only_links_shell_covered": sum(1 for row in link_rows if row["shell_latency_covered"]),
            "missing_route_shell_count": len(missing_route_shell),
            "missing_link_shell_count": len(missing_link_shell),
            "undeclared_read_only_link_count": len(undeclared_links),
            "shell_route_count": shell_latency.get("route_count"),
            "shell_all_ok": shell_latency.get("all_ok"),
            "shell_all_under_threshold": shell_latency.get("all_under_threshold"),
            "shell_max_observed_ms": shell_latency.get("max_observed_ms"),
        },
        "missing_route_shell": missing_route_shell,
        "missing_link_shell": missing_link_shell,
        "undeclared_read_only_links": undeclared_links,
        "routes": route_rows,
        "read_only_links": link_rows,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-source", default=DEFAULT_APP_SOURCE)
    ap.add_argument("--link-source", default=DEFAULT_LINK_SOURCE)
    ap.add_argument("--shell-latency", default=DEFAULT_SHELL_LATENCY)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        app_source=Path(args.app_source),
        link_source=Path(args.link_source),
        shell_latency_path=Path(args.shell_latency),
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
