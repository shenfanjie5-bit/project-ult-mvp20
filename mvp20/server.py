"""Stdlib HTTP BFF exposing mvp20 data and skeleton adapter routes.

Stdlib-only (no new deps). The server is read-only: every handler is GET,
while POST/PUT/DELETE return 405.

Core mvp20 routes include health, compat, manifests, modules, providers,
profiles, industry graphs, stock overlays, market events, technicals,
history, aggregate, coverage, score, and the realtime SSE stream. Vendored
upstream route families are wired through ``mvp20.adapters`` for graph,
data-platform canonical/raw data, entity-registry, reasoner-runtime,
main-core cycles/stocks/pool/world-state, and audit/backtest surfaces.
Legacy frontend-api admin/alerts paths are local BFF stubs.

Adapter routes normally return 200 fixture envelopes when the vendored
package imports. If a vendor package fails at adapter import time, they
return a structured 503 UPSTREAM_UNAVAILABLE envelope so the frontend can
surface the missing module/dependency rather than crashing. Unmatched
``/api/*`` paths return a 404 envelope.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import yaml

from mvp20 import lock as lock_mod
from mvp20 import manifest as manifest_mod
from mvp20 import providers as providers_mod
from mvp20 import graph as graph_mod
from mvp20.json_utils import dumps_strict_json
from mvp20.adapters import (
    audit_eval as audit_eval_adapter,
    data_platform as data_platform_adapter,
    entity_registry as entity_registry_adapter,
    graph_engine as graph_engine_adapter,
    main_core as main_core_adapter,
    reasoner_runtime as reasoner_runtime_adapter,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
LOCKS_DIR = REPO_ROOT / "locks"
RUNTIME_DIR = REPO_ROOT / "runtime"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8701
    cors_origin: str = "http://127.0.0.1:1420"
    universe_path: Path = CONFIG_DIR / "mvp20.universe.yaml"
    industries_path: Path = CONFIG_DIR / "mvp20.industries.yaml"
    providers_path: Path = CONFIG_DIR / "data_providers.yaml"
    industry_graphs_dir: Path = CONFIG_DIR / "industry_graphs"
    lock_path: Path = LOCKS_DIR / "modules.lock.yaml"
    # ── Data-layer paths (phase 1 hot snapshot + phase 2 history) ──
    stock_overlays_dir: Path = CONFIG_DIR / "stock_overlays"
    industry_overlays_dir: Path = CONFIG_DIR / "industry_overlays"
    hot_db_path: Path = RUNTIME_DIR / "hot.sqlite"
    history_dir: Path = RUNTIME_DIR / "history"


# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------


def _ok_envelope(data: Any) -> dict:
    return {"data": data, "request_id": _request_id()}


def _error_envelope(code: str, message: str, *, status: int = 500,
                    details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": _request_id(),
        }
    }


# ---------------------------------------------------------------------------
# Input validators — security hardening (review #2 P1-A / P1-B)
# ---------------------------------------------------------------------------
#
# Two attack vectors closed here:
#
# 1. ``industry_id`` was concatenated into ``industry_overlays_dir /
#    f"{industry_id}.yaml"`` with no sanitization, allowing path-traversal
#    (``../stock_overlays/AI_COMPUTE/X.yaml``). A double-coincidence with
#    the stock-overlay lookup currently prevents successful arbitrary-file
#    reads, but the gap is one file rename away from being exploitable.
#
# 2. ``ts_code`` was accepted as any string and echoed verbatim in the JSON
#    response. SQLite queries are parameterized so injection is blocked,
#    but downstream consumers that ``innerHTML``-render the field would be
#    XSS-vulnerable, and a 10K-char ``ts_code`` is bounced back unbounded
#    (DoS amplification).

#: Allowlist regex for ts_code — matches the ``constituents[].ts_code`` shape
#: used across config/mvp20.universe.yaml: A股 (.SH/.SZ/.BJ 6-digit), HK
#: (.HK 4-5 digit), US (.US 1-5 alpha). Length capped at 16 chars total.
_TS_CODE_RE = re.compile(r"^[A-Z0-9]{1,10}\.(SH|SZ|BJ|HK|US)$")

#: Allowlist regex for industry_id — uppercase + underscores only, length
#: capped, no path separators / dots. Matches AI_COMPUTE / STORAGE_GRID etc.
_INDUSTRY_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def _validate_ts_code(value: str | None) -> str | None:
    """Return canonical ``ts_code`` or None if input fails the allowlist.
    Use the return value as a pre-flight before any DB / file access."""

    if not value:
        return None
    if len(value) > 16:
        return None
    return value if _TS_CODE_RE.match(value) else None


def _validate_industry_id(value: str | None) -> str | None:
    """Return canonical ``industry_id`` or None. Rejects anything with
    path separators (``/`` ``..`` ``.``) or non-uppercase chars to prevent
    arbitrary-file reads via the ``cfg.industry_overlays_dir /
    f"{industry_id}.yaml"`` path-build pattern."""

    if not value:
        return None
    if len(value) > 32:
        return None
    return value if _INDUSTRY_ID_RE.match(value) else None


def _upstream_unavailable(module: str, path: str) -> dict:
    return _error_envelope(
        code="UPSTREAM_NOT_RUNNING",
        message=(
            f"Endpoint {path} is owned by upstream module "
            f"`{module}` which is not part of mvp20. mvp20 is a manifest "
            "shell — start the upstream service or use VITE_DATA_MODE=demo."
        ),
        status=503,
        details={"upstream_module": module, "path": path},
    )


def _request_id() -> str:
    return f"mvp20-{int(time.time() * 1000)}"


# ---------------------------------------------------------------------------
# Handlers (each returns (status, body_dict))
# ---------------------------------------------------------------------------


HandlerResult = tuple[int, dict]


def handle_health(_: ServerConfig, _q: dict) -> HandlerResult:
    return 200, _ok_envelope({
        "service": "mvp20",
        "status": "ok",
        "version": "0.1.0",
        "scope": "manifest_shell_read_only",
    })


def handle_project_ult_health(cfg: ServerConfig, _q: dict) -> HandlerResult:
    lock = lock_mod.validate_lock(cfg.lock_path)
    return 200, _ok_envelope({
        "service": "mvp20",
        "status": "ok" if lock.ok else "degraded",
        "lock_module_count": lock.module_count,
        "lock_errors": list(lock.errors),
    })


def handle_compat(_: ServerConfig, _q: dict) -> HandlerResult:
    return 200, _ok_envelope({
        "schema_versions": {
            "manifest": 2,
            "industries": 1,
            "industry_graph": 1,
            "data_providers": 1,
            "lock": 1,
        },
        "mvp20_version": "0.1.0",
        "compatibility_note": "manifest+lock+CI shell; no runtime cycle orchestration",
    })


def handle_manifests_latest(cfg: ServerConfig, _q: dict) -> HandlerResult:
    universe = yaml.safe_load(cfg.universe_path.read_text(encoding="utf-8"))
    industries = yaml.safe_load(cfg.industries_path.read_text(encoding="utf-8"))
    return 200, _ok_envelope({
        "universe": universe,
        "industries": industries,
    })


def handle_modules(cfg: ServerConfig, _q: dict) -> HandlerResult:
    payload = yaml.safe_load(cfg.lock_path.read_text(encoding="utf-8"))
    return 200, _ok_envelope(payload)


def handle_providers(cfg: ServerConfig, _q: dict) -> HandlerResult:
    catalog = yaml.safe_load(cfg.providers_path.read_text(encoding="utf-8"))
    validation = providers_mod.validate_provider_catalog(
        cfg.providers_path,
        required_markets={"A", "HK", "US"},
    )
    return 200, _ok_envelope({
        "catalog": catalog,
        "validation": {
            "ok": validation.ok,
            "active_providers": list(validation.active_providers),
            "market_coverage": validation.market_coverage,
            "capability_coverage": validation.capability_coverage,
            "warnings": list(validation.warnings),
            "errors": list(validation.errors),
        },
    })


def handle_profiles(cfg: ServerConfig, query: dict) -> HandlerResult:
    universe = yaml.safe_load(cfg.universe_path.read_text(encoding="utf-8"))
    constituents = universe.get("constituents", [])

    # Optional filtering
    pool = query.get("pool", [None])[0]
    role = query.get("role", [None])[0]
    industry = query.get("industry", [None])[0]
    market = query.get("market", [None])[0]

    profiles = []
    for c in constituents:
        if pool and c.get("pool", "regular") != pool:
            continue
        if role and c.get("role", "target") != role:
            continue
        if industry and industry not in c.get("industry_ids", []):
            continue
        if market:
            ts = c.get("ts_code", "")
            mk = "A" if ts.endswith((".SH", ".SZ", ".BJ")) else \
                 "HK" if ts.endswith(".HK") else \
                 "US" if ts.endswith(".US") else "?"
            if mk != market:
                continue
        profiles.append(c)

    return 200, _ok_envelope({
        "profiles": profiles,
        "total": len(profiles),
        "universe_total": len(constituents),
    })


def handle_industry_graph(cfg: ServerConfig, query: dict) -> HandlerResult:
    industry_id = query.get("industry_id", [None])[0]
    if not industry_id:
        # Return list of available graphs
        graphs = []
        for path in sorted(cfg.industry_graphs_dir.glob("*.yaml")):
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                payload = {}
            if payload.get("graph_status") == "pending":
                continue
            graphs.append({
                "industry_id": path.stem,
                "path": str(path.relative_to(REPO_ROOT)),
            })
        return 200, _ok_envelope({"graphs": graphs})

    target = cfg.industry_graphs_dir / f"{industry_id}.yaml"
    if not target.exists():
        return 404, _error_envelope(
            "INDUSTRY_GRAPH_NOT_FOUND",
            f"No industry graph for {industry_id}; check industries.yaml",
            status=404,
        )
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    return 200, _ok_envelope(payload)


def handle_cycles_list(_: ServerConfig, _q: dict) -> HandlerResult:
    """mvp20 has no cycle orchestration — return empty list (not 503) so the
    UI renders a clean empty state."""

    return 200, _ok_envelope({
        "cycles": [],
        "note": "mvp20 is a manifest shell — cycles are produced by upstream main-core / orchestrator",
    })


def handle_subsystems_status(cfg: ServerConfig, _q: dict) -> HandlerResult:
    """Empty subsystem health array — mvp20 only locks module SHAs."""

    lock = lock_mod.validate_lock(cfg.lock_path)
    return 200, _ok_envelope({
        "subsystems": [
            {
                "id": name,
                "status": "unknown",
                "note": "mvp20 only pins commit SHA; live status requires running upstream",
            }
            for name in sorted(lock_mod.EXPECTED_MODULES)
        ],
        "lock_ok": lock.ok,
    })


def handle_admin_stub(_: ServerConfig, _q: dict) -> HandlerResult:
    """Stub for legacy /api/admin/* — the FrontEnd app uses MSW handlers in
    demo mode for admin controls; in projectUlt mode mvp20 returns an empty
    envelope (no real admin actions are exposed by the manifest shell).

    Owned by mvp20 directly — `frontend-api` is NOT vendored under upstream/
    because the FrontEnd Vite app (under FrontEnd/) is the only frontend in
    this repo, and mvp20 server.py serves as its BFF without needing a
    separate FastAPI module."""

    return 200, _ok_envelope({
        "module": "mvp20-bff",
        "fixture": True,
        "note": "admin actions are mock — mvp20 is a read-only manifest shell",
        "overrides": [],
        "config": {},
        "providers": [],
    })


def handle_alerts_stub(_: ServerConfig, _q: dict) -> HandlerResult:
    """Stub for legacy /api/alerts/* — alert stream is the responsibility of
    a future stream-layer module; mvp20 returns an empty envelope so the UI
    shows a clean empty-state instead of a 503 banner."""

    return 200, _ok_envelope({
        "module": "mvp20-bff",
        "fixture": True,
        "note": "alert stream not implemented — stream-layer is upstream-planned",
        "alerts": [],
        "total": 0,
    })


def handle_orchestrator_runs_stub(_: ServerConfig, _q: dict) -> HandlerResult:
    """Stub for /api/project-ult/orchestrator/runs — orchestrator runs are
    produced by upstream main-core; mvp20 is a manifest shell. Return an empty
    envelope so the UI (EvidenceConsole / AuditReplay) shows a clean empty-state
    instead of a 404 '加载失败'."""

    return 200, _ok_envelope({
        "module": "mvp20-bff",
        "fixture": True,
        "note": "orchestrator runs are upstream-planned (main-core); mvp20 is a manifest shell",
        "runs": [],
        "total": 0,
    })


def handle_pnl_backtests(_: ServerConfig, query: dict) -> HandlerResult:
    """Serve the production P&L feedback loop (G1): per-date score-vs-realized
    forward-return metrics + rolling summary with de-rate flags.

    Data is produced nightly by ``scripts/run_pnl_loop.py`` into
    ``runtime/backtest/pnl.sqlite``. Empty (but honest) envelope until the
    first snapshots mature — never a fixture pretending to be data.

    Query params: ``horizon`` (5|10|20, optional filter), ``limit`` (default
    60 most recent per-date rows).
    """

    try:
        from mvp20 import pnl_loop
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "IMPORT_FAILED", f"pnl_loop import failed: {exc}", status=500
        )

    horizon_raw = (query.get("horizon") or [None])[0]
    horizon = None
    if horizon_raw:
        try:
            horizon = int(horizon_raw)
        except ValueError:
            return 400, _error_envelope(
                "BAD_PARAM", f"horizon must be an int, got {horizon_raw!r}", status=400
            )
    try:
        limit = max(1, min(500, int((query.get("limit") or ["60"])[0])))
    except ValueError:
        limit = 60

    rows = pnl_loop.read_eval(horizon=horizon)
    rows.sort(key=lambda m: (m.get("base_date") or "", m.get("horizon_d") or 0),
              reverse=True)
    summary = pnl_loop.rolling_summary()
    return 200, _ok_envelope({
        "module": "mvp20-pnl-loop",
        "source": str(pnl_loop.DEFAULT_DB),
        "backtests": rows[:limit],
        "total": len(rows),
        "rolling_summary": summary,
        "note": (
            "per-date metrics join the nightly production score snapshot with"
            " realized T+h hfq returns (h=5/10/20 trading days); empty until"
            " the first snapshots mature"
        ),
    })


def handle_history(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Time-series replay for one (ts_code, dp_id) from Parquet history."""

    ts_code = (query.get("ts_code") or [None])[0]
    dp_id = (query.get("dp_id") or [None])[0]
    if not ts_code or not dp_id:
        return 400, _error_envelope(
            "MISSING_PARAM",
            "ts_code and dp_id query parameters required",
            status=400,
        )

    try:
        since = int((query.get("since") or [str(int(time.time()) - 86400)])[0])
        until_raw = (query.get("until") or [None])[0]
        until = int(until_raw) if until_raw else None
        limit = min(int((query.get("limit") or ["5000"])[0]), 50_000)
    except (TypeError, ValueError) as e:
        return 400, _error_envelope(
            "BAD_PARAM", f"invalid integer parameter: {e}", status=400,
        )

    try:
        from mvp20.history import query_history
    except ImportError as e:
        return 503, _error_envelope(
            "HISTORY_UNAVAILABLE",
            f"history layer requires duckdb+pyarrow: {e}",
            status=503,
        )

    points = query_history(cfg.history_dir, ts_code, dp_id, since, until, limit=limit)
    return 200, _ok_envelope({
        "ts_code": ts_code,
        "dp_id": dp_id,
        "since": since,
        "until": until,
        "points": points,
        "total": len(points),
    })


def handle_technicals(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Per-stock technical-indicator pack.

    Reads the 8 ``L11.tech.*`` dp_ids written by the derive layer
    (``mvp20.derive._fetch_a_share_history`` → ``mvp20.technicals.compute_all``)
    out of the SQLite hot snapshot and returns them as one structured
    payload so the frontend can render a K-line + 均线 + MACD/RSI panel
    in a single network round-trip.

    Query params:
      * ``ts_code`` (required) — e.g. ``000977.SZ``
      * ``include`` (optional, repeat-OK) — subset of indicator keys.
        Defaults to all 8 (``ma`` / ``macd`` / ``rsi`` / ``kdj`` / ``boll``
        / ``vol_ma`` / ``atr`` / ``obv``). Unknown keys are silently
        ignored.
      * ``return_series`` (optional int) — when > 0, also returns the most
        recent N OHLCV bars (capped at 250) with per-bar MA5/MA10/MA20/MA60
        overlays under ``data.series`` so the FrontEnd can render a K-line
        + 均线叠加图 in a single round-trip. Reads ``L11.tech.bars`` emitted
        by the derive layer.

    Response shape (``data`` key inside the envelope)::

        {
          "ts_code": "000977.SZ",
          "as_of": "20260515",
          "n_bars": 60,
          "indicators": {
            "ma":     {"ma5": ..., "ma10": ..., "ma20": ..., ...},
            "macd":   {"dif": ..., "dea": ..., "hist": ..., "cross": "bull"},
            "rsi":    {"rsi6": ..., "rsi12": ..., "rsi24": ...},
            "kdj":    {"k": ..., "d": ..., "j": ...},
            "boll":   {"mid": ..., "upper": ..., "lower": ..., ...},
            "vol_ma": {"vol5": ..., "vol10": ..., "vol_ratio_today": ...},
            "atr":    {"scalar": ...},
            "obv":    {"scalar": ...}
          },
          "freshness": {
            "max_age_seconds": 1234,
            "stale": false
          }
        }

    A dp_id missing from SQLite (e.g. derive layer didn't run for that
    stock yet) shows as ``null`` under ``indicators.<key>``. The
    frontend should render a "暂无数据" placeholder rather than crash.
    """

    ts_code = (query.get("ts_code") or [None])[0]
    if not ts_code:
        return 400, _error_envelope(
            "MISSING_PARAM", "ts_code query parameter required", status=400,
        )

    requested_raw = query.get("include") or []
    # `?include=ma,macd` → ["ma,macd"] needs flattening; also `?include=ma&include=macd`
    include: set[str] = set()
    for entry in requested_raw:
        for token in (entry or "").split(","):
            t = token.strip().lower()
            if t:
                include.add(t)

    # `?return_series=N` — opt-in K-line + 均线序列. Clamp to [0, 250].
    return_series_raw = (query.get("return_series") or [None])[0]
    return_series_n: int = 0
    if return_series_raw is not None:
        try:
            return_series_n = int(return_series_raw)
        except (TypeError, ValueError):
            return 400, _error_envelope(
                "BAD_PARAM",
                "return_series must be an integer",
                status=400,
            )
        if return_series_n < 0:
            return_series_n = 0
        if return_series_n > 250:
            return_series_n = 250

    # dp_id ↔ short-name mapping used by the response.
    indicator_dp_ids = {
        "ma":     "L11.tech.ma",
        "macd":   "L11.tech.macd",
        "rsi":    "L11.tech.rsi",
        "kdj":    "L11.tech.kdj",
        "boll":   "L11.tech.boll",
        "vol_ma": "L11.tech.vol_ma",
        "atr":    "L11.tech.atr",
        "obv":    "L11.tech.obv",
    }
    if not include:
        include = set(indicator_dp_ids.keys())

    from mvp20.storage import read_hot_snapshot
    snapshot = read_hot_snapshot(cfg.hot_db_path, ts_code)

    indicators: dict[str, Any] = {}
    max_age: int | None = None
    latest_as_of: str | None = None
    latest_n_bars: int | None = None
    for short_name, dp_id in indicator_dp_ids.items():
        if short_name not in include:
            continue
        row = snapshot.get(dp_id)
        if not row:
            indicators[short_name] = None
            continue
        value = row.get("value")
        if isinstance(value, dict):
            indicators[short_name] = value
            if isinstance(value.get("as_of"), str):
                latest_as_of = latest_as_of or value["as_of"]
            if isinstance(value.get("n_bars"), int):
                latest_n_bars = latest_n_bars or value["n_bars"]
        else:
            indicators[short_name] = {"scalar": value}
        age = row.get("age_seconds")
        if isinstance(age, int):
            max_age = age if max_age is None else max(max_age, age)

    # Optional series payload — read L11.tech.bars, compute MAs, slice to N.
    series: list[dict] | None = None
    if return_series_n > 0:
        bars_row = snapshot.get("L11.tech.bars")
        bars_value = bars_row.get("value") if bars_row else None
        raw_bars: list = []
        if isinstance(bars_value, dict):
            candidate = bars_value.get("bars")
            if isinstance(candidate, list):
                raw_bars = candidate
            if latest_as_of is None and isinstance(bars_value.get("as_of"), str):
                latest_as_of = bars_value["as_of"]
            if latest_n_bars is None and isinstance(bars_value.get("n_bars"), int):
                latest_n_bars = bars_value["n_bars"]
            age = bars_row.get("age_seconds") if bars_row else None
            if isinstance(age, int):
                max_age = age if max_age is None else max(max_age, age)

        from mvp20.technicals import compute_series_with_ma
        full_series = compute_series_with_ma(raw_bars) if raw_bars else []
        # Tail-slice to the most recent N bars (ascending by date already).
        series = full_series[-return_series_n:] if full_series else []

    stale = max_age is not None and max_age > 86400  # > 1 day
    payload: dict[str, Any] = {
        "ts_code": ts_code,
        "as_of": latest_as_of,
        "n_bars": latest_n_bars,
        "indicators": indicators,
        "freshness": {
            "max_age_seconds": max_age,
            "stale": stale,
        },
    }
    if series is not None:
        payload["series"] = series
    return 200, _ok_envelope(payload)


def handle_market_events(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Cross-stock real-time event stream from SQLite.

    Combines three sources:
      * ``MARKET:CN/L9.media.report.top_headlines`` — CLS telegraph rollup
        (market-level; ``time`` field is ISO string).
      * Per-stock ``L9.event.intraday_news.top_headlines`` — EastMoney news
        per A-share (``publish_time`` ``YYYY-MM-DD HH:MM:SS`` string).
      * Per-stock ``L9.company.earnings_guidance`` — 业绩预告 forecast events,
        each carrying a VALIDATED signed ``coefficient`` (expected size-adjusted
        abnormal return; see ``mvp20.event_coefficient``). News rows carry
        ``coefficient: null`` + ``coefficient_meta.validated: false`` because
        Track B (free-text news) is forward-only and not yet validated.

    Returns events sorted by timestamp desc, deduped, limited to ``?limit=N``
    (default 12, max 50). Backs the MarketOverview "实时事件流" timeline.
    """

    import sqlite3
    from datetime import datetime

    try:
        limit = min(int((query.get("limit") or ["12"])[0]), 50)
    except (TypeError, ValueError):
        return 400, _error_envelope(
            "BAD_PARAM", "limit must be an integer", status=400,
        )

    db_path = cfg.hot_db_path
    if not db_path.exists():
        return 200, _ok_envelope({
            "events": [],
            "total": 0,
            "limit": limit,
            "as_of": None,
            "source": "sqlite",
            "note": f"hot.sqlite not found at {db_path}",
        })

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT ts_code, dp_id, value_json, updated_at
              FROM realtime_current
             WHERE data_status = 'Known'
               AND (
                    (ts_code = 'MARKET:CN' AND dp_id = 'L9.media.report')
                 OR dp_id = 'L9.event.intraday_news'
                 OR dp_id = 'L9.company.earnings_guidance'
               )
            """
        ).fetchall()
    except sqlite3.OperationalError as e:
        conn.close()
        return 500, _error_envelope(
            "SQLITE_ERROR", f"read realtime_current failed: {e}", status=500,
        )
    conn.close()

    def _parse_ts(s: str | None) -> int | None:
        # Accept ISO ("2026-05-15T20:15:12"), space-form ("2026-05-15
        # 17:05:00"), or short date — return epoch seconds, None on failure.
        if not s or not isinstance(s, str):
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                return int(datetime.strptime(s[:19], fmt).timestamp())
            except ValueError:
                continue
        return None

    from mvp20.event_coefficient import forecast_coefficient, news_coefficient_meta

    # realtime_current keeps only each stock's LATEST forecast (UPSERT); for a
    # stock that no longer issues 业绩预告 that snapshot can be years old. Only
    # surface forecast events whose ann_date is genuinely recent.
    forecast_max_age = 90 * 86400
    now_epoch = int(datetime.now().timestamp())

    collected: list[dict] = []
    for ts_code, dp_id, val_json, _upd in rows:
        try:
            payload = json.loads(val_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue

        # Structured forecast event → VALIDATED signed coefficient.
        if dp_id == "L9.company.earnings_guidance":
            coef = forecast_coefficient(payload)
            if coef is None:  # no clear direction (不确定/缺失) — skip, never show 0
                continue
            epoch = _parse_ts(payload.get("ann_date"))
            if epoch is None or now_epoch - epoch > forecast_max_age:
                continue
            typ = str(payload.get("type") or "").strip()
            collected.append({
                "ts_code": ts_code,
                "dp_id": dp_id,
                "title": f"业绩预告 · {typ}",
                "timestamp_epoch": epoch,
                "timestamp_iso": datetime.fromtimestamp(epoch).isoformat(
                    timespec="seconds",
                ),
                "url": None,
                "source": "tushare:forecast",
                "coefficient": coef["coefficient"],
                "coefficient_meta": {k: v for k, v in coef.items()
                                     if k != "coefficient"},
            })
            continue

        # Free-text news / CLS rollup → headlines. No validated coefficient yet
        # (Track B is forward-only) → coefficient null + validated:false.
        headlines = payload.get("top_headlines") or []
        if not isinstance(headlines, list):
            continue
        for h in headlines:
            if not isinstance(h, dict):
                continue
            title = (h.get("title") or "").strip()
            if not title:
                continue
            raw_ts = h.get("time") or h.get("publish_time")
            epoch = _parse_ts(raw_ts)
            if epoch is None:
                continue
            collected.append({
                "ts_code": ts_code,
                "dp_id": dp_id,
                "title": title,
                "timestamp_epoch": epoch,
                "timestamp_iso": datetime.fromtimestamp(epoch).isoformat(
                    timespec="seconds",
                ),
                "url": h.get("url"),
                "source": h.get("source"),
                "coefficient": None,
                "coefficient_meta": news_coefficient_meta(),
            })

    # Dedupe: news by title (stocks echo the same headline); forecast events by
    # (ts_code, dp_id) so per-stock guidance isn't collapsed by a shared title.
    seen: set = set()
    deduped: list[dict] = []
    for ev in sorted(collected, key=lambda e: e["timestamp_epoch"], reverse=True):
        key = ((ev["ts_code"], ev["dp_id"])
               if ev["dp_id"] == "L9.company.earnings_guidance" else ev["title"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
        if len(deduped) >= limit:
            break

    as_of_epoch = max((e["timestamp_epoch"] for e in deduped), default=None)
    as_of_iso = (
        datetime.fromtimestamp(as_of_epoch).isoformat(timespec="seconds")
        if as_of_epoch is not None else None
    )

    return 200, _ok_envelope({
        "events": deduped,
        "total": len(deduped),
        "limit": limit,
        "as_of": as_of_iso,
        "source": "sqlite:realtime_current",
    })


def handle_stock_overlay(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Read one company graph overlay plus the minute-level hot snapshot.

    Preferred path is the compiled SQLite snapshot:
    ``company_graph_snapshot.payload_json``. If the compiler has not been run
    yet, this falls back to the YAML overlay so local authoring remains cheap.
    """

    from mvp20.storage import (
        read_available_overlay_industries,
        read_compiled_graph_snapshot,
        read_freshness_meta,
        read_hot_snapshot,
        read_overlay_alerts,
    )

    ts_code = (query.get("ts_code") or [None])[0]
    if not ts_code:
        return 400, _error_envelope(
            "MISSING_PARAM", "ts_code query parameter required", status=400
        )

    requested_industry_id = (query.get("industry_id") or [None])[0]

    # 1. Fast path — compiled SQLite snapshot.
    compiled = read_compiled_graph_snapshot(
        cfg.hot_db_path,
        ts_code,
        industry_id=requested_industry_id,
    )
    realtime = read_hot_snapshot(cfg.hot_db_path, ts_code)
    freshness_layers = read_freshness_meta(cfg.hot_db_path)
    realtime_ages = [v["age_seconds"] for v in realtime.values()]

    if compiled:
        industry_id = compiled.get("industry_id")
        available_industries = read_available_overlay_industries(cfg.hot_db_path, ts_code)
        if not available_industries:
            available_industries = compiled.get("available_industries") or [industry_id]
        alerts = read_overlay_alerts(cfg.hot_db_path, ts_code, industry_id)
        if not alerts:
            alerts = compiled.get("alerts") or []
        static_overlay = compiled.get("static_overlay") or {}
        return 200, _ok_envelope({
            "ts_code": ts_code,
            "industry_id": industry_id,
            "available_industries": available_industries,
            "compiled_graph": compiled.get("compiled_graph") or {},
            "realtime": realtime,
            "scores": compiled.get("scores") or {},
            "coverage": compiled.get("coverage") or {},
            "alerts": alerts,
            "freshness": {
                "static_period": static_overlay.get("period") or compiled.get("data_version"),
                "compiled_at": compiled.get("compiled_at"),
                "realtime_max_age_seconds": max(realtime_ages, default=None),
                "realtime_min_age_seconds": min(realtime_ages, default=None),
                "realtime_node_count": len(realtime),
                "layers": freshness_layers,
            },
            "static_overlay": static_overlay,
            # Backward-compatible aliases for the current frontend/tests.
            "static": static_overlay,
            "industry_context": _read_industry_overlay(cfg, industry_id),
        })

    # 2. Fallback path — YAML authoring files.
    static_path = _find_stock_overlay_path(cfg, ts_code, requested_industry_id)
    if static_path is None:
        # Use logical "config/..." path in the error message — don't leak
        # the server's absolute filesystem path (review #2 P1-A).
        looked_at = (
            f"config/stock_overlays/{requested_industry_id}/{ts_code}.yaml"
            if requested_industry_id
            else f"config/stock_overlays/*/{ts_code}.yaml"
        )
        return 404, _error_envelope(
            "OVERLAY_NOT_FOUND",
            f"no stock_overlay for {ts_code}",
            status=404,
            details={"ts_code": ts_code, "industry_id": requested_industry_id, "looked_at": looked_at},
        )
    try:
        static = yaml.safe_load(static_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return 500, _error_envelope(
            "OVERLAY_PARSE_ERROR",
            f"failed to parse {static_path.name}: {e}",
            status=500,
        )

    industry_id = static.get("industry_id") or (static.get("industry_ids") or [None])[0]
    available_industries = (
        static.get("available_industries")
        or static.get("industry_ids")
        or ([industry_id] if industry_id else [])
    )
    industry_context = _read_industry_overlay(cfg, industry_id)

    return 200, _ok_envelope({
        "ts_code": ts_code,
        "industry_id": industry_id,
        "available_industries": available_industries,
        "compiled_graph": {
            "nodes": static.get("nodes") or [],
            "hierarchy_edges": static.get("hierarchy_edges") or [],
            "causal_edges": static.get("causal_edges") or [],
            "views": static.get("views") or {},
        },
        "scores": static.get("scores") or {},
        "coverage": static.get("coverage") or {},
        "alerts": [],
        "static": static,
        "static_overlay": static,
        "industry_context": industry_context,
        "realtime": realtime,
        "freshness": {
            "static_period": static.get("period"),
            "realtime_max_age_seconds": max(realtime_ages, default=None),
            "realtime_min_age_seconds": min(realtime_ages, default=None),
            "realtime_node_count": len(realtime),
            "layers": freshness_layers,
        },
    })


def _find_stock_overlay_path(
    cfg: ServerConfig,
    ts_code: str,
    industry_id: str | None,
) -> Path | None:
    # Path-traversal hardening: reject ts_code / industry_id values that
    # don't match the allowlist regex. Without this, callers can ask for
    # ``?ts_code=../../../etc/passwd`` and either trigger a yaml.safe_load
    # on an unintended file or leak its absolute path in the 404 details.
    if not _validate_ts_code(ts_code):
        return None
    if industry_id is not None and not _validate_industry_id(industry_id):
        return None

    if industry_id:
        path = cfg.stock_overlays_dir / industry_id / f"{ts_code}.yaml"
        return path if path.exists() else None

    nested = sorted(cfg.stock_overlays_dir.glob(f"*/{ts_code}.yaml"))
    if nested:
        primary = []
        for path in nested:
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            if payload.get("primary_industry") is True:
                primary.append(path)
        return sorted(primary or nested)[0]

    legacy = cfg.stock_overlays_dir / f"{ts_code}.yaml"
    return legacy if legacy.exists() else None


def _load_stock_overlay_payload(
    cfg: ServerConfig,
    ts_code: str,
    requested_industry_id: str | None,
) -> tuple[dict | None, int, dict, str | None]:
    """Locate and parse a stock overlay YAML.

    Returns ``(overlay_or_None, status, envelope, industry_id)``. When
    ``overlay`` is ``None`` the caller must return ``status``+``envelope``
    directly. On success ``status == 200`` and ``envelope == {}``.
    """

    path = _find_stock_overlay_path(cfg, ts_code, requested_industry_id)
    if path is None:
        # Error details intentionally omit the absolute filesystem path —
        # leaking ``/Users/<user>/...`` in 404 responses gives attackers
        # free recon (review #2 P1-A). Use a logical "config/..." prefix
        # so operators still see what was looked up without leaking the
        # server's filesystem layout.
        looked_at = (
            f"config/stock_overlays/{requested_industry_id}/{ts_code}.yaml"
            if requested_industry_id
            else f"config/stock_overlays/*/{ts_code}.yaml"
        )
        return None, 404, _error_envelope(
            "OVERLAY_NOT_FOUND",
            f"no stock_overlay for {ts_code}",
            status=404,
            details={
                "ts_code": ts_code,
                "industry_id": requested_industry_id,
                "looked_at": looked_at,
            },
        ), None
    try:
        overlay = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return None, 500, _error_envelope(
            "OVERLAY_PARSE_ERROR",
            f"failed to parse {path.name}: {exc}",
            status=500,
        ), None

    industry_id = (
        requested_industry_id
        or overlay.get("industry_id")
        or (overlay.get("industry_ids") or [None])[0]
    )
    return overlay, 200, {}, industry_id


def _load_industry_overlay_payload(
    cfg: ServerConfig,
    industry_id: str | None,
) -> dict | None:
    if not industry_id:
        return None
    # Path-traversal hardening — reject anything that isn't a clean
    # ALL_CAPS_UNDERSCORES industry id. Prevents
    # ``?industry_id=../stock_overlays/X`` from resolving outside
    # ``industry_overlays_dir``.
    if not _validate_industry_id(industry_id):
        return None
    path = cfg.industry_overlays_dir / f"{industry_id}.yaml"
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None


def handle_aggregate(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Run aggregator A1 on a stock overlay and return per-node score +
    three-horizon mix. See spec §27 / §29."""

    ts_code = (query.get("ts_code") or [None])[0]
    if not ts_code:
        return 400, _error_envelope(
            "MISSING_PARAM", "ts_code query parameter required", status=400
        )
    requested_industry_id = (query.get("industry_id") or [None])[0]

    overlay, status, err, industry_id = _load_stock_overlay_payload(
        cfg, ts_code, requested_industry_id
    )
    if overlay is None:
        return status, err

    industry_overlay = _load_industry_overlay_payload(cfg, industry_id)

    # Bridge realtime snapshot values into the aggregation (synthetic leaves)
    # so /aggregate reflects the same node set that /score uses.
    try:
        from mvp20.storage import read_hot_snapshot
        realtime_data = read_hot_snapshot(cfg.hot_db_path, ts_code)
    except Exception:  # noqa: BLE001
        realtime_data = {}

    try:
        from mvp20.aggregator import aggregate_company_graph
        nodes = aggregate_company_graph(
            overlay, industry_overlay, realtime_snapshot=realtime_data or None
        ) or {}
    except Exception as exc:  # noqa: BLE001 — surface as 500
        return 500, _error_envelope(
            "AGGREGATE_FAILED",
            f"aggregate_company_graph raised: {exc}",
            status=500,
            details={"ts_code": ts_code, "industry_id": industry_id},
        )

    return 200, _ok_envelope({
        "ts_code": ts_code,
        "industry_id": industry_id,
        "nodes": nodes,
    })


def handle_coverage(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Run coverage A2 on a stock overlay and return Data Coverage + alerts.
    See spec §23."""

    ts_code = (query.get("ts_code") or [None])[0]
    if not ts_code:
        return 400, _error_envelope(
            "MISSING_PARAM", "ts_code query parameter required", status=400
        )
    requested_industry_id = (query.get("industry_id") or [None])[0]

    overlay, status, err, industry_id = _load_stock_overlay_payload(
        cfg, ts_code, requested_industry_id
    )
    if overlay is None:
        return status, err

    try:
        from mvp20.coverage import combined_coverage_summary
        spec_path = CONFIG_DIR / "data_point_roles.yaml"
        report = combined_coverage_summary(
            overlay,
            ts_code=ts_code,
            db_path=cfg.hot_db_path,
            spec_path=spec_path if spec_path.exists() else None,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "COVERAGE_FAILED",
            f"combined_coverage_summary raised: {exc}",
            status=500,
            details={"ts_code": ts_code, "industry_id": industry_id},
        )

    overall = report.get("overall") or {}
    per_node_list = report.get("per_node") or []
    per_node: dict[str, dict] = {}
    for entry in per_node_list:
        key = entry.get("dp_id") or entry.get("node_id")
        if not key:
            continue
        per_node[str(key)] = entry

    return 200, _ok_envelope({
        "ts_code": report.get("ts_code") or ts_code,
        "industry_id": report.get("industry_id") or industry_id,
        "overall_data_coverage": overall.get("data_coverage", 0.0),
        "warning_level": overall.get("warning_level", "ok"),
        "n_parents": overall.get("n_parents", 0),
        "totals": overall.get("totals", {}),
        "sqlite_coverage_pct": overall.get("sqlite_coverage_pct", 0.0),
        "llm_yaml_coverage_pct": overall.get("llm_yaml_coverage_pct", 0.0),
        "combined_coverage_pct": overall.get("combined_coverage_pct", 0.0),
        "yaml_only_data_coverage": overall.get("yaml_only_data_coverage"),
        "n_sqlite_known": overall.get("n_sqlite_known", 0),
        "n_yaml_known": overall.get("n_yaml_known", 0),
        "n_combined_known": overall.get("n_combined_known", 0),
        "spec_total": overall.get("spec_total", 0),
        "per_node": per_node,
        "alerts": report.get("alerts") or [],
    })


def handle_score(cfg: ServerConfig, query: dict) -> HandlerResult:
    """Run scoring A3 on a stock overlay (A1 + A2 fed in) and return the
    top-level company score, mode classification, and trading signal.
    See spec §27.1/27.3/27.4 and §30."""

    ts_code = (query.get("ts_code") or [None])[0]
    if not ts_code:
        return 400, _error_envelope(
            "MISSING_PARAM", "ts_code query parameter required", status=400
        )
    requested_industry_id = (query.get("industry_id") or [None])[0]

    overlay, status, err, industry_id = _load_stock_overlay_payload(
        cfg, ts_code, requested_industry_id
    )
    if overlay is None:
        return status, err

    industry_overlay = _load_industry_overlay_payload(cfg, industry_id)

    try:
        from mvp20.aggregator import aggregate_company_graph
        from mvp20.coverage import coverage_summary_for_overlay
        from mvp20.scoring import score_company
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "IMPORT_FAILED",
            f"failed to import scoring layer: {exc}",
            status=500,
        )

    # Best-effort realtime — read first so the aggregator can bridge realtime
    # values into the score (synthetic leaves) and score_company can reuse it.
    try:
        from mvp20.storage import read_hot_snapshot
        realtime_data = read_hot_snapshot(cfg.hot_db_path, ts_code)
    except Exception:  # noqa: BLE001
        realtime_data = {}

    # R-3a/R-3b.2 cross-sectional scoring: for A-shares, LOAD the precomputed
    # peer-context artifact (priced_in pools + valuation pools). Building it scans
    # the whole universe (~16s) so it is NOT built in the request path — it is
    # generated offline by ``mvp20 build-peer-context`` (refresh after derive) and
    # loaded here in <10ms. Absent artifact / HK / US → None → original absolute
    # behaviour. Best-effort: any failure leaves peer_context None.
    peer_context = None
    try:
        from mvp20.peer_context import default_artifact_path, load_peer_context, market_of
        if market_of(ts_code) == "A":
            peer_context = load_peer_context(default_artifact_path(cfg.hot_db_path, "A"))
    except Exception:  # noqa: BLE001 — de-common-mode is best-effort
        peer_context = None

    try:
        aggregated = aggregate_company_graph(
            overlay, industry_overlay, realtime_snapshot=realtime_data or None,
            peer_context=peer_context,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "AGGREGATE_FAILED",
            f"aggregate_company_graph raised: {exc}",
            status=500,
            details={"ts_code": ts_code, "industry_id": industry_id},
        )

    try:
        coverage_report = coverage_summary_for_overlay(overlay) or {}
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "COVERAGE_FAILED",
            f"coverage_summary_for_overlay raised: {exc}",
            status=500,
            details={"ts_code": ts_code, "industry_id": industry_id},
        )

    # Aggregator returns ``{node_id: {...}}``; score_company auto-detects
    # this flat shape via ``_is_flat_aggregator_output``.
    try:
        result = score_company(
            stock_overlay=overlay,
            aggregated_nodes=aggregated,
            coverage_report=coverage_report,
            realtime_data=realtime_data,
        )
    except Exception as exc:  # noqa: BLE001
        return 500, _error_envelope(
            "SCORE_FAILED",
            f"score_company raised: {exc}",
            status=500,
            details={"ts_code": ts_code, "industry_id": industry_id},
        )

    final_score = result.get("final_score") or {}
    top_paths = result.get("top_paths") or {"positive": [], "negative": []}
    return 200, _ok_envelope({
        "ts_code": result.get("ts_code") or ts_code,
        "industry_id": result.get("industry_id") or industry_id,
        "mode": result.get("mode_display") or result.get("mode"),
        "mode_code": result.get("mode"),
        "mode_confidence": result.get("mode_confidence"),
        "mode_rationale": result.get("mode_rationale"),
        "primary_drivers": result.get("mode_drivers") or [],
        "short_total": result.get("short_total"),
        "medium_total": result.get("medium_total"),
        "long_total": result.get("long_total"),
        "trading_signal": result.get("trading_signal"),
        "trading_meaning": final_score.get("trading_meaning"),
        "company_score": result.get("company_score") or {},
        "final_score": final_score,
        "top_paths": top_paths,
        "signals": result.get("signals") or {},
        # 涨幅预测分数 (validated two-layer quant model) — PARALLEL shadow
        # output, never fused into base_score (tail-anti-alignment, see
        # factor_research/model/REPORT_PROB.md §5.4). Best-effort: absent
        # artifact -> honest available:false block.
        "quant": _quant_block(ts_code),
    })


def _quant_block(ts_code: str) -> dict:
    try:
        from mvp20.peer_context import market_of
        if market_of(ts_code) != "A":
            return {"available": False, "reason": "A-share only (model unvalidated elsewhere)"}
        from mvp20.quant_score import lookup
        return lookup(ts_code)
    except Exception as exc:  # noqa: BLE001 — shadow output must never break /score
        return {"available": False, "reason": f"quant lookup failed: {exc}"}


def _read_industry_overlay(cfg: ServerConfig, industry_id: str | None) -> dict:
    if not industry_id:
        return {}
    # Path-traversal hardening (see _validate_industry_id docstring).
    if not _validate_industry_id(industry_id):
        return {}
    ind_path = cfg.industry_overlays_dir / f"{industry_id}.yaml"
    if not ind_path.exists():
        return {}
    try:
        return yaml.safe_load(ind_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {"error": "industry_overlay_parse_failed"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


# (method, path_regex, handler, upstream_module_if_unavailable)
# Upstream-only routes: pre-empt with 503 envelope so the UI shows a clean
# "this needs upstream X" banner instead of crashing.
# Empty — every former 503-only route is now either wired to a vendored
# upstream module via mvp20.adapters.* (returning 200 fixture) or handled
# directly by mvp20 (admin/alerts stubs above). frontend-api is intentionally
# NOT vendored: the FrontEnd Vite app under FrontEnd/ is the sole frontend,
# and mvp20 server.py serves as its BFF directly. Any future upstream-only
# routes can be added here to surface a 503 banner cleanly.
_UPSTREAM_ONLY: list[tuple[str, str]] = []


# ---------------------------------------------------------------------------
# Add-stock onboarding (P1) — the ONLY whitelisted write endpoints. Everything
# else stays read-only (do_POST → 405). recognize is synchronous; onboard
# enqueues an async job (mvp20.onboard) and returns a job_id the frontend polls.
# ---------------------------------------------------------------------------


def handle_recognize(cfg: ServerConfig, body: dict) -> HandlerResult:
    """POST {market, code} → canonical ts_code + name + industry suggestion."""
    from mvp20 import onboard as onboard_mod
    market = str(body.get("market") or "").strip()
    code = str(body.get("code") or "").strip()
    if not market or not code:
        return 400, _error_envelope("BAD_REQUEST", "market and code are required", status=400)
    return 200, _ok_envelope(onboard_mod.recognize(market, code))


def handle_onboard(cfg: ServerConfig, body: dict) -> HandlerResult:
    """POST {ts_code, name, industry_id, do_codex?} → start async onboard job."""
    from mvp20 import onboard as onboard_mod
    ts_code = _validate_ts_code(str(body.get("ts_code") or "").strip().upper())
    industry_id = str(body.get("industry_id") or "").strip()
    name = str(body.get("name") or "").strip()
    if ts_code is None:
        return 400, _error_envelope("BAD_TS_CODE", "invalid or missing ts_code", status=400)
    if not _INDUSTRY_ID_RE.match(industry_id):
        return 400, _error_envelope("BAD_INDUSTRY", "invalid industry_id", status=400)
    # L4: cap the free-text name (ts_code/industry_id are already length-capped)
    # before it is written verbatim into the versioned universe.yaml.
    if len(name) > 128:
        return 400, _error_envelope("BAD_NAME", "name too long (max 128 chars)", status=400)
    valid = {i["industry_id"] for i in onboard_mod.list_industry_ids()}
    if industry_id not in valid:
        return 400, _error_envelope(
            "UNKNOWN_INDUSTRY", f"{industry_id} is not an active industry",
            status=400, details={"valid": sorted(valid)})
    if onboard_mod.already_in_pool(ts_code):
        return 409, _error_envelope("ALREADY_IN_POOL", f"{ts_code} already in pool", status=409)
    # H2: bounded active-job guard. Reserve a concurrency slot atomically; reject
    # a duplicate in-flight job for the same ts_code (409) or an over-capacity
    # request (429) BEFORE spawning the unbounded worker thread.
    reserved, reason = onboard_mod.try_reserve_onboard_slot(ts_code)
    if not reserved:
        if reason == "duplicate":
            return 409, _error_envelope(
                "ONBOARD_IN_PROGRESS", f"{ts_code} already has an onboard job in progress",
                status=409)
        return 429, _error_envelope(
            "ONBOARD_BUSY",
            f"too many onboard jobs in progress (max {onboard_mod.MAX_ACTIVE_ONBOARD_JOBS})",
            status=429)
    do_codex = bool(body.get("do_codex", True))
    try:
        job_id = onboard_mod.start_onboard_job(
            cfg.hot_db_path, ts_code, name or ts_code, industry_id,
            do_codex=do_codex, _reserved=True)
    except Exception:
        # start failed before the worker took ownership of the slot — release it
        # so a retry isn't permanently blocked.
        onboard_mod.release_onboard_slot(ts_code)
        raise
    return 202, _ok_envelope({
        "job_id": job_id, "ts_code": ts_code, "status": "pending",
        "steps": onboard_mod.ONBOARD_STEPS,
    })


def handle_onboard_status(cfg: ServerConfig, query: dict) -> HandlerResult:
    """GET ?job_id=X → onboarding job progress (poll target)."""
    from mvp20 import onboard as onboard_mod
    job_id = (query.get("job_id") or [None])[0]
    if not job_id:
        return 400, _error_envelope("BAD_REQUEST", "job_id query param required", status=400)
    job = onboard_mod.get_job(cfg.hot_db_path, str(job_id))
    if job is None:
        return 404, _error_envelope("JOB_NOT_FOUND", f"no onboard job {job_id}", status=404)
    return 200, _ok_envelope(job)


def handle_industries(cfg: ServerConfig, query: dict) -> HandlerResult:
    """GET → active industry_ids (for the add-stock industry dropdown)."""
    from mvp20 import onboard as onboard_mod
    return 200, _ok_envelope({"industries": onboard_mod.list_industry_ids()})


#: Whitelisted POST command endpoints (handler signature: (cfg, body_dict)).
def _post_routes() -> list[tuple[re.Pattern[str], Callable[[ServerConfig, dict], HandlerResult]]]:
    return [
        (re.compile(r"^/api/project-ult/recognize$"), handle_recognize),
        (re.compile(r"^/api/project-ult/onboard$"), handle_onboard),
    ]


def _routes(cfg: ServerConfig) -> list[tuple[re.Pattern[str], Callable[[ServerConfig, dict], HandlerResult]]]:
    return [
        # === mvp20 own implementations (read YAML, no upstream dependency) ===
        (re.compile(r"^/api/health$"), handle_health),
        (re.compile(r"^/api/project-ult/health$"), handle_project_ult_health),
        (re.compile(r"^/api/project-ult/compat$"), handle_compat),
        (re.compile(r"^/api/project-ult/manifests/latest$"), handle_manifests_latest),
        (re.compile(r"^/api/project-ult/modules$"), handle_modules),
        (re.compile(r"^/api/project-ult/reasoner/providers$"), handle_providers),
        (re.compile(r"^/api/project-ult/profiles$"), handle_profiles),
        (re.compile(r"^/api/project-ult/industry-graphs$"), handle_industry_graph),
        (re.compile(r"^/api/project-ult/cycles$"), handle_cycles_list),
        (re.compile(r"^/api/subsystems/status$"), handle_subsystems_status),
        # === vendored upstream modules wired via mvp20/adapters/* ===
        # graph-engine
        (re.compile(r"^/api/project-ult/graph/.*$"), graph_engine_adapter.handle_graph_query),
        # data-platform
        (re.compile(r"^/api/project-ult/data/canonical/.*$"), data_platform_adapter.handle_canonical),
        (re.compile(r"^/api/project-ult/data/raw/.*$"), data_platform_adapter.handle_raw),
        # entity-registry
        (re.compile(r"^/api/project-ult/entities.*$"), entity_registry_adapter.handle_entities),
        # reasoner-runtime (note: /reasoner/providers stays on handle_providers above)
        (re.compile(r"^/api/project-ult/reasoner/(?!providers)[^/]+.*$"),
         reasoner_runtime_adapter.handle_reasoner),
        # main-core
        (re.compile(r"^/api/project-ult/cycles/[^/]+$"), main_core_adapter.handle_cycle_detail),
        (re.compile(r"^/api/stocks/.*$"), main_core_adapter.handle_stocks),
        (re.compile(r"^/api/pool/.*$"), main_core_adapter.handle_pool),
        (re.compile(r"^/api/world-state/.*$"), main_core_adapter.handle_world_state),
        # audit-eval
        (re.compile(r"^/api/project-ult/audit/[^/]+$"), audit_eval_adapter.handle_audit),
        (re.compile(r"^/api/audit/.*$"), audit_eval_adapter.handle_audit),
        # backtests — real data from the production P&L feedback loop
        # (mvp20.pnl_loop + scripts/run_pnl_loop.py); replaces the empty
        # audit-eval fixture that capability audit G1 flagged.
        (re.compile(r"^/api/project-ult/backtests/?.*$"), handle_pnl_backtests),
        (re.compile(r"^/api/backtest/.*$"), handle_pnl_backtests),
        # mvp20 own BFF stubs — frontend-api not vendored; FrontEnd/ uses these
        (re.compile(r"^/api/admin/.*$"), handle_admin_stub),
        (re.compile(r"^/api/alerts/.*$"), handle_alerts_stub),
        (re.compile(r"^/api/project-ult/orchestrator/runs/?.*$"), handle_orchestrator_runs_stub),
        # Phase-1 data-layer: merged stock overlay (YAML static + SQLite hot)
        (re.compile(r"^/api/project-ult/stock-overlay$"), handle_stock_overlay),
        # Cross-stock real-time event stream (MarketOverview "实时事件流")
        (re.compile(r"^/api/project-ult/market-events$"), handle_market_events),
        # Per-stock technical-indicator pack (MA / MACD / RSI / KDJ / BOLL / VOL / ATR / OBV)
        (re.compile(r"^/api/project-ult/technicals$"), handle_technicals),
        # Phase-2 data-layer: Parquet minute history replay
        (re.compile(r"^/api/project-ult/history$"), handle_history),
        # Derived layers — A1 / A2 / A3 (spec §23 / §27 / §29 / §30)
        (re.compile(r"^/api/project-ult/aggregate$"), handle_aggregate),
        (re.compile(r"^/api/project-ult/coverage$"), handle_coverage),
        (re.compile(r"^/api/project-ult/score$"), handle_score),
        # Add-stock onboarding (P1): industries dropdown + job-status poll.
        # (POST /recognize + POST /onboard are dispatched via _post_routes.)
        (re.compile(r"^/api/project-ult/industries$"), handle_industries),
        (re.compile(r"^/api/project-ult/onboard$"), handle_onboard_status),
    ]


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    server_version = "mvp20/0.1"
    _config: ServerConfig | None = None  # set by the wrapper class

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Concise access log — single line per request
        print(f"{self.log_date_time_string()} {self.address_string()} "
              f"{format % args}", flush=True)

    def _set_cors(self) -> None:
        cfg = self._config
        if cfg is None:
            return
        self.send_header("Access-Control-Allow-Origin", cfg.cors_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _write_json(self, status: int, body: dict) -> None:
        encoded = dumps_strict_json(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        cfg = self._config
        if cfg is None:
            self._write_json(500, _error_envelope(
                "SERVER_NOT_CONFIGURED", "ServerConfig not bound", status=500))
            return

        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Long-lived SSE streams take over the response — do not pass through
        # the normal _write_json envelope. Each stream blocks the handler
        # thread for its duration; ThreadingHTTPServer handles concurrency.
        if path == "/api/project-ult/stream/realtime":
            self._serve_sse_realtime(cfg, query)
            return

        # Match exact handlers first
        for pattern, handler in _routes(cfg):
            if pattern.match(path):
                try:
                    status, body = handler(cfg, query)
                except Exception as exc:  # noqa: BLE001 - surface as 500
                    body = _error_envelope(
                        "HANDLER_ERROR", str(exc), status=500,
                        details={"path": path},
                    )
                    status = 500
                self._write_json(status, body)
                return

        # Upstream-only patterns return 503 envelope
        for pattern_str, module in _UPSTREAM_ONLY:
            if re.match(pattern_str, path):
                self._write_json(503, _upstream_unavailable(module, path))
                return

        # Unknown path
        if path.startswith("/api/"):
            self._write_json(404, _error_envelope(
                "ROUTE_NOT_FOUND",
                f"No mvp20 handler for {path}; this might be served by "
                "an upstream module or the frontend's MSW mock layer.",
                status=404,
                details={"path": path},
            ))
        else:
            self._write_json(404, _error_envelope(
                "NOT_API_PATH",
                f"mvp20 server only exposes /api/*; got {path}",
                status=404,
            ))

    def do_POST(self) -> None:  # noqa: N802
        cfg = self._config
        if cfg is None:
            self._write_json(500, _error_envelope(
                "SERVER_NOT_CONFIGURED", "ServerConfig not bound", status=500))
            return
        path = urlsplit(self.path).path
        for pattern, handler in _post_routes():
            if pattern.match(path):
                body = self._read_json_body()
                if body is None:
                    self._write_json(400, _error_envelope(
                        "BAD_JSON", "request body is not valid JSON object", status=400))
                    return
                try:
                    status, resp = handler(cfg, body)
                except Exception as exc:  # noqa: BLE001 — surface as 500
                    resp = _error_envelope("HANDLER_ERROR", str(exc), status=500,
                                           details={"path": path})
                    status = 500
                self._write_json(status, resp)
                return
        # Non-whitelisted POST stays read-only.
        self._reject_write()

    def _read_json_body(self) -> dict | None:
        """Parse a JSON request body. ``{}`` for empty, ``None`` for invalid
        (so the caller can 400). Capped at 1 MB."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return None
        if length <= 0:
            return {}
        if length > 1_000_000:
            return None
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, TypeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def do_PUT(self) -> None:  # noqa: N802
        self._reject_write()

    def do_DELETE(self) -> None:  # noqa: N802
        self._reject_write()

    def _reject_write(self) -> None:
        self._write_json(405, _error_envelope(
            "METHOD_NOT_ALLOWED",
            f"mvp20 server is read-only; {self.command} not allowed",
            status=405,
        ))

    # ── SSE: long-lived event stream for one ts_code ──────────────────────
    def _serve_sse_realtime(self, cfg: ServerConfig, query: dict) -> None:
        """Open a Server-Sent Events stream of realtime_current deltas.

        Sends headers first, then loops in ``mvp20.sse.stream_realtime_delta``.
        Connection stays open until client disconnects or max-duration hits.
        """

        from mvp20 import sse as sse_mod

        ts_code_list = query.get("ts_code") or []
        if not ts_code_list:
            self._write_json(400, _error_envelope(
                "MISSING_PARAM",
                "ts_code query parameter required for SSE stream",
                status=400,
            ))
            return
        ts_code = ts_code_list[0]
        industry_id = (query.get("industry_id") or [None])[0]

        try:
            poll = int((query.get("poll_seconds") or [str(sse_mod.DEFAULT_POLL_INTERVAL_SECONDS)])[0])
        except (TypeError, ValueError):
            poll = sse_mod.DEFAULT_POLL_INTERVAL_SECONDS
        # Hard-cap poll interval so a client can't ask for 0.1s polling
        poll = max(1, min(poll, 60))

        # Headers for SSE — chunked-friendly, no compression, no caching
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # disable proxy buffering
        self._set_cors()
        self.end_headers()

        try:
            sse_mod.stream_realtime_delta(
                write_bytes=self.wfile.write,
                flush=self.wfile.flush,
                hot_db_path=cfg.hot_db_path,
                ts_code=ts_code,
                industry_id=industry_id,
                poll_interval_seconds=poll,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: tell the client we crashed, then close.
            try:
                self.wfile.write(
                    f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n".encode("utf-8")
                )
                self.wfile.flush()
            except OSError:
                pass


def make_handler_class(cfg: ServerConfig) -> type[_Handler]:
    cls = type("BoundHandler", (_Handler,), {"_config": cfg})
    return cls


def serve_forever(cfg: ServerConfig) -> None:
    handler_cls = make_handler_class(cfg)
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), handler_cls)
    # Daemonize request threads so finished/long-lived SSE threads don't pile up
    # in ThreadingMixIn._threads (a slow leak that degrades a long-running server).
    httpd.daemon_threads = True
    print(f"mvp20 HTTP server listening on http://{cfg.host}:{cfg.port}/api/*")
    print(f"  CORS origin allowed: {cfg.cors_origin}")
    print(f"  Universe:    {cfg.universe_path}")
    print(f"  Industries:  {cfg.industries_path}")
    print(f"  Providers:   {cfg.providers_path}")
    print(f"  Lock:        {cfg.lock_path}")
    print("  Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down …")
        httpd.shutdown()
