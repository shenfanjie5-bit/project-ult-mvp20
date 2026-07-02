#!/usr/bin/env python3
"""Measure local BFF endpoint latency for the Project ULT frontend hot path.

The script is intentionally stdlib-only. It can either hit an already-running
BFF or start a temporary ``mvp20 serve`` process, warm the routes, measure each
endpoint a few times, and emit JSON evidence for the audit report.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ENDPOINTS = (
    "/api/health",
    "/api/project-ult/health",
    "/api/project-ult/modules",
    "/api/project-ult/compat",
    "/api/project-ult/profiles?ts_code=300750.SZ",
    "/api/project-ult/industry-graphs",
    "/api/project-ult/industry-graphs?industry_id=STORAGE_GRID",
    "/api/project-ult/market-events?limit=8",
    "/api/project-ult/stock-overlay?ts_code=300750.SZ&include_static=0",
    "/api/project-ult/aggregate?ts_code=300750.SZ&industry_id=STORAGE_GRID",
    "/api/project-ult/coverage?ts_code=300750.SZ",
    "/api/project-ult/score?ts_code=300750.SZ",
    "/api/project-ult/technicals?ts_code=300750.SZ",
    "/api/project-ult/backtests",
    "/api/project-ult/graph/query",
    "/api/project-ult/data/canonical/smoke",
    "/api/project-ult/data/raw/smoke",
    "/api/project-ult/entities",
    "/api/project-ult/reasoner/smoke",
    "/api/project-ult/cycles/smoke",
    "/api/stocks/smoke",
    "/api/project-ult/audit/smoke",
    "/api/project-ult/orchestrator/runs",
)


@dataclass
class Hit:
    status: int | None
    ms: float
    bytes: int
    key: str
    error: str = ""


def _url(base: str, endpoint: str) -> str:
    return base.rstrip("/") + "/" + endpoint.lstrip("/")


def _body_key(data: bytes) -> str:
    if not data:
        return ""
    try:
        body = json.loads(data.decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(body, dict):
        return ""
    value = (
        body.get("status")
        or body.get("module")
        or body.get("wire_depth")
        or body.get("ok")
    )
    if value is None and isinstance(body.get("error"), dict):
        value = body["error"].get("code")
    return str(value) if value is not None else ""


def hit(base: str, endpoint: str, *, timeout: float) -> Hit:
    start = time.perf_counter()
    status = None
    data = b""
    error = ""
    try:
        with urllib.request.urlopen(_url(base, endpoint), timeout=timeout) as response:
            status = int(response.status)
            data = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        data = exc.read()
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = (time.perf_counter() - start) * 1000.0
    return Hit(status=status, ms=round(elapsed, 3), bytes=len(data), key=_body_key(data),
               error=error)


def summarize_hits(hits: list[Hit], *, threshold_ms: float) -> dict:
    values = [h.ms for h in hits]
    statuses = sorted({h.status for h in hits})
    return {
        "status_values": statuses,
        "ok": all(h.status == 200 and not h.error for h in hits),
        "under_threshold": all(h.ms <= threshold_ms for h in hits),
        "min_ms": round(min(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "max_ms": round(max(values), 3),
        "bytes_last": hits[-1].bytes,
        "key_last": hits[-1].key,
        "errors": [h.error for h in hits if h.error],
        "samples": [h.__dict__ for h in hits],
    }


def wait_for_health(base: str, *, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if hit(base, "/api/health", timeout=2.0).status == 200:
            return True
        time.sleep(0.2)
    return False


def start_server(port: int) -> subprocess.Popen:
    cmd = [
        ".venv/bin/mvp20",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_audit(
    base: str,
    endpoints: Iterable[str],
    *,
    repeats: int,
    warmups: int,
    timeout: float,
    threshold_ms: float,
) -> dict:
    rows = {}
    for endpoint in endpoints:
        for _ in range(max(0, warmups)):
            hit(base, endpoint, timeout=timeout)
        hits = [hit(base, endpoint, timeout=timeout) for _ in range(max(1, repeats))]
        rows[endpoint] = summarize_hits(hits, threshold_ms=threshold_ms)
    all_ok = all(row["ok"] for row in rows.values())
    all_under = all(row["under_threshold"] for row in rows.values())
    max_ms = max(row["max_ms"] for row in rows.values()) if rows else 0.0
    return {
        "base_url": base,
        "threshold_ms": threshold_ms,
        "repeats": repeats,
        "warmups": warmups,
        "all_ok": all_ok,
        "all_under_threshold": all_under,
        "max_observed_ms": max_ms,
        "endpoints": rows,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8799")
    ap.add_argument("--start-server", action="store_true")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--output", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmups", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--threshold-ms", type=float, default=1000.0)
    ap.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS))
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()
    base = args.base_url
    proc = None
    if args.start_server:
        base = f"http://127.0.0.1:{args.port}"
        proc = start_server(args.port)
        if not wait_for_health(base, timeout_s=20.0):
            if proc:
                proc.terminate()
            print("BFF did not become healthy", file=sys.stderr)
            return 2
    endpoints = tuple(e.strip() for e in args.endpoints.split(",") if e.strip())
    try:
        result = run_audit(
            base,
            endpoints,
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
