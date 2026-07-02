#!/usr/bin/env python3
"""Measure Project ULT frontend SPA shell route latency.

This audit is intentionally browser-free and stdlib-only. It complements the
browser H1 timing evidence by checking that every direct Project ULT route can
return the Vite SPA shell quickly and consistently. It does not claim React
hydration or downstream data rendering timing.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ROUTES = (
    "/?data_mode=projectUlt",
    "/pool?data_mode=projectUlt",
    "/recommend?data_mode=projectUlt",
    "/graph?data_mode=projectUlt",
    "/report?data_mode=projectUlt",
    "/subsystems?data_mode=projectUlt",
    "/audit?data_mode=projectUlt",
    "/audit/CYCLE_20260424?data_mode=projectUlt",
    "/backtest?data_mode=projectUlt",
    "/options?data_mode=projectUlt",
    "/alerts?data_mode=projectUlt",
    "/admin?data_mode=projectUlt",
    "/admin/health?data_mode=projectUlt",
    "/project-ult/system?data_mode=projectUlt",
    "/project-ult/cycles?data_mode=projectUlt",
    "/project-ult/data?data_mode=projectUlt",
    "/project-ult/graph?data_mode=projectUlt",
    "/project-ult/evidence?data_mode=projectUlt",
    "/stock/300750.SZ?data_mode=projectUlt",
    "/add-stock?data_mode=projectUlt",
)


@dataclass
class Hit:
    status: int | None
    ms: float
    bytes: int
    content_type: str
    shell_ok: bool
    error: str = ""


def _url(base: str, route: str) -> str:
    return base.rstrip("/") + "/" + route.lstrip("/")


def _is_spa_shell(data: bytes, content_type: str) -> bool:
    if "text/html" not in content_type.lower():
        return False
    sample = data[:200_000].decode("utf-8", errors="replace")
    return 'id="root"' in sample and "<script" in sample


def hit(base: str, route: str, *, timeout: float) -> Hit:
    start = time.perf_counter()
    status = None
    data = b""
    content_type = ""
    error = ""
    try:
        with urllib.request.urlopen(_url(base, route), timeout=timeout) as response:
            status = int(response.status)
            content_type = response.headers.get("content-type", "")
            data = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        content_type = exc.headers.get("content-type", "") if exc.headers else ""
        data = exc.read()
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = (time.perf_counter() - start) * 1000.0
    return Hit(
        status=status,
        ms=round(elapsed, 3),
        bytes=len(data),
        content_type=content_type,
        shell_ok=(status == 200 and _is_spa_shell(data, content_type)),
        error=error,
    )


def summarize_hits(hits: list[Hit], *, threshold_ms: float) -> dict:
    values = [hit.ms for hit in hits]
    statuses = sorted({hit.status for hit in hits})
    return {
        "status_values": statuses,
        "ok": all(hit.status == 200 and hit.shell_ok and not hit.error for hit in hits),
        "under_threshold": all(hit.ms <= threshold_ms for hit in hits),
        "min_ms": round(min(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "max_ms": round(max(values), 3),
        "bytes_last": hits[-1].bytes,
        "content_type_last": hits[-1].content_type,
        "shell_ok_last": hits[-1].shell_ok,
        "errors": [hit.error for hit in hits if hit.error],
        "samples": [hit.__dict__ for hit in hits],
    }


def wait_for_frontend(base: str, *, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        probe = hit(base, "/?data_mode=projectUlt", timeout=2.0)
        if probe.status == 200 and probe.shell_ok:
            return True
        time.sleep(0.2)
    return False


def start_frontend(repo: Path, *, port: int, proxy_target: str) -> subprocess.Popen:
    frontend = repo / "FrontEnd"
    env = os.environ.copy()
    env["VITE_PROJECT_ULT_PROXY_TARGET"] = proxy_target
    cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    return subprocess.Popen(
        cmd,
        cwd=frontend,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_audit(
    base: str,
    routes: Iterable[str],
    *,
    repeats: int,
    warmups: int,
    timeout: float,
    threshold_ms: float,
) -> dict:
    rows = {}
    for route in routes:
        for _ in range(max(0, warmups)):
            hit(base, route, timeout=timeout)
        hits = [hit(base, route, timeout=timeout) for _ in range(max(1, repeats))]
        rows[route] = summarize_hits(hits, threshold_ms=threshold_ms)
    all_ok = all(row["ok"] for row in rows.values())
    all_under = all(row["under_threshold"] for row in rows.values())
    max_ms = max(row["max_ms"] for row in rows.values()) if rows else 0.0
    return {
        "base_url": base,
        "threshold_ms": threshold_ms,
        "repeats": repeats,
        "warmups": warmups,
        "route_count": len(rows),
        "all_ok": all_ok,
        "all_under_threshold": all_under,
        "max_observed_ms": max_ms,
        "scope_note": (
            "HTTP SPA shell latency only; browser H1 visibility and hydration "
            "remain covered by frontend_browser_qa artifacts."
        ),
        "routes": rows,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--base-url", default="http://127.0.0.1:1421")
    ap.add_argument("--start-server", action="store_true")
    ap.add_argument("--port", type=int, default=1421)
    ap.add_argument("--proxy-target", default="http://127.0.0.1:8701")
    ap.add_argument("--output", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmups", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--threshold-ms", type=float, default=1000.0)
    ap.add_argument("--routes", default=",".join(DEFAULT_ROUTES))
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    repo = Path(args.repo_root).resolve()
    base = args.base_url
    proc = None
    if args.start_server:
        base = f"http://127.0.0.1:{args.port}"
        proc = start_frontend(repo, port=args.port, proxy_target=args.proxy_target)
        if not wait_for_frontend(base, timeout_s=20.0):
            if proc:
                proc.terminate()
            print("Frontend did not become healthy", file=sys.stderr)
            return 2
    routes = tuple(route.strip() for route in args.routes.split(",") if route.strip())
    try:
        result = run_audit(
            base,
            routes,
            repeats=args.repeats,
            warmups=args.warmups,
            timeout=args.timeout,
            threshold_ms=args.threshold_ms,
        )
        result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        result["elapsed_s"] = round(time.time() - started, 3)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0 if result["all_ok"] and result["all_under_threshold"] else 1
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
