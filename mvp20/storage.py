"""SQLite hot-snapshot storage for minute-level data points.

Single-file SQLite WAL database under ``runtime/hot.sqlite`` keeps the
**current value** of every realtime data point for every constituent. UPSERT
semantics: same (ts_code, dp_id) overwrites in place — no history is kept
here (history is the responsibility of ``mvp20.history`` Parquet store).

Used by:
- ``scripts/collector.py``: writes batches every ~60s via ``upsert_realtime``
- ``mvp20.server.handle_stock_overlay``: reads a stock's current snapshot
  via ``read_hot_snapshot`` to merge with the static YAML overlay
- ``mvp20.server.handle_stream_realtime``: polls ``read_hot_snapshot_changed_since``
  every N seconds to emit SSE deltas

Reader is single-statement and uses URI mode=ro so multiple server threads
can read concurrently without blocking the collector writer.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;

CREATE TABLE IF NOT EXISTS realtime_current (
    ts_code TEXT NOT NULL,
    dp_id TEXT NOT NULL,
    value_json TEXT NOT NULL,
    data_status TEXT NOT NULL,
    confidence REAL,
    source TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (ts_code, dp_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_rt_ts_code
  ON realtime_current(ts_code);

CREATE INDEX IF NOT EXISTS idx_rt_updated_at
  ON realtime_current(updated_at);

CREATE TABLE IF NOT EXISTS alert_state (
    ts_code TEXT NOT NULL,
    dp_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    reason TEXT NOT NULL,
    triggered_at INTEGER NOT NULL,
    cleared_at INTEGER,
    PRIMARY KEY (ts_code, dp_id, triggered_at)
);

CREATE INDEX IF NOT EXISTS idx_alert_active
  ON alert_state(ts_code, dp_id)
  WHERE cleared_at IS NULL;

CREATE TABLE IF NOT EXISTS freshness_meta (
    layer TEXT PRIMARY KEY,
    last_full_sync_at INTEGER,
    last_partial_sync_at INTEGER,
    sync_status TEXT
);

CREATE TABLE IF NOT EXISTS overlay_manifest (
    ts_code TEXT NOT NULL,
    industry_id TEXT NOT NULL,
    overlay_path TEXT NOT NULL,
    period TEXT,
    primary_industry INTEGER NOT NULL DEFAULT 0,
    overlay_status TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (ts_code, industry_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_overlay_manifest_ts
  ON overlay_manifest(ts_code, primary_industry DESC, industry_id);

CREATE TABLE IF NOT EXISTS company_node_instance (
    ts_code TEXT NOT NULL,
    industry_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    dp_id TEXT,
    payload_json TEXT NOT NULL,
    data_status TEXT,
    required_level TEXT,
    missing_policy TEXT,
    calculation_type TEXT,
    aggregation_policy TEXT,
    materiality REAL,
    confidence REAL,
    source_overlay_path TEXT,
    PRIMARY KEY (ts_code, industry_id, node_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_company_node_dp
  ON company_node_instance(ts_code, industry_id, dp_id);

CREATE TABLE IF NOT EXISTS company_edge_instance (
    ts_code TEXT NOT NULL,
    industry_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    edge_kind TEXT NOT NULL,
    from_node TEXT,
    to_node TEXT,
    edge_type TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (ts_code, industry_id, edge_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_company_edge_kind
  ON company_edge_instance(ts_code, industry_id, edge_kind);

CREATE TABLE IF NOT EXISTS company_graph_snapshot (
    ts_code TEXT NOT NULL,
    industry_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    graph_version TEXT,
    data_version TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (ts_code, industry_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS overlay_alert (
    alert_id TEXT PRIMARY KEY,
    ts_code TEXT NOT NULL,
    industry_id TEXT NOT NULL,
    dp_id TEXT,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_overlay_alert_active
  ON overlay_alert(ts_code, industry_id, severity)
  WHERE resolved_at IS NULL;
"""


def init_db(db_path: Path) -> None:
    """Create schema if not present. Idempotent."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Read side (used by server)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Sentinel ts_code helpers
# ---------------------------------------------------------------------------
#
# Macro fetchers (Tushare / FMP / akshare cls.cn) write market-level and
# industry-level dp_ids using sentinel ts_codes:
#
#   ``MARKET:CN`` / ``MARKET:HK`` / ``MARKET:US`` — one row per market for
#       e.g. ``L7.env.rates`` (treasury curve), ``L9.macro.cpi_employment``.
#   ``INDUSTRY:<industry_id>``                    — one row per industry for
#       e.g. ``L10.industry.fund_flow``, ``L10.industry.pmi`` (per-sector).
#
# When a caller asks for ``read_hot_snapshot('300750.SZ')`` they should also
# see the MARKET:CN macro context AND the INDUSTRY:<id>(s) the stock belongs
# to. We fan-out the SQL to the union of (ts_code, sentinel ts_codes) and
# merge with priority: ts_code-specific > INDUSTRY > MARKET. So if for any
# reason a per-stock fetcher emits its own L9.macro.cpi_employment it wins
# over the MARKET:CN one.


def _ts_code_to_market(ts_code: str) -> str | None:
    """Map a stock ts_code to its market sentinel suffix.

    Returns ``"CN"`` / ``"HK"`` / ``"US"`` or ``None`` for unknown forms
    (sentinel ts_codes themselves return ``None`` so we don't recurse).
    """

    if ts_code.endswith((".SH", ".SZ", ".BJ")):
        return "CN"
    if ts_code.endswith(".HK"):
        return "HK"
    if ts_code.endswith(".US"):
        return "US"
    return None


def _industries_for_ts_code(conn: sqlite3.Connection, ts_code: str) -> list[str]:
    """Return industry_ids this ts_code belongs to (primary first).

    Sourced from ``overlay_manifest`` populated by ``compile-overlays``;
    returns an empty list if the table is missing or no rows match.
    """

    try:
        rows = conn.execute(
            """
            SELECT industry_id
              FROM overlay_manifest
             WHERE ts_code = ?
             ORDER BY primary_industry DESC, industry_id
            """,
            (ts_code,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def read_hot_snapshot(
    db_path: Path,
    ts_code: str,
    *,
    include_sentinels: bool = True,
) -> dict[str, dict]:
    """Read realtime_current for one ts_code, merging sentinel rows.

    Pulls per-stock rows plus market-level (``MARKET:<market>``) and
    industry-level (``INDUSTRY:<id>``) sentinel rows so callers see macro /
    sector context without an extra round-trip. Merge priority:

        ts_code > INDUSTRY:<primary> > INDUSTRY:<other> > MARKET:<market>

    Each returned dp_id payload includes ``_origin_ts_code`` so callers can
    tell whether a value came from the stock itself or a sentinel.

    Pass ``include_sentinels=False`` to get the legacy ts_code-only behaviour
    (e.g. for SSE delta where we don't want to flood every connection with
    market-level updates).
    """

    if not db_path.exists():
        return {}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Build priority list (lower index = higher priority for merge).
        all_ts_codes: list[str] = [ts_code]
        if include_sentinels:
            industries = _industries_for_ts_code(conn, ts_code)
            for ind in industries:
                all_ts_codes.append(f"INDUSTRY:{ind}")
            market = _ts_code_to_market(ts_code)
            if market is not None:
                all_ts_codes.append(f"MARKET:{market}")

        placeholders = ",".join(["?"] * len(all_ts_codes))
        rows = conn.execute(
            f"""
            SELECT ts_code, dp_id, value_json, data_status, confidence,
                   source, updated_at
              FROM realtime_current
             WHERE ts_code IN ({placeholders})
            """,
            all_ts_codes,
        ).fetchall()
    finally:
        conn.close()

    priority = {t: i for i, t in enumerate(all_ts_codes)}
    now = int(time.time())
    best: dict[str, dict] = {}
    for ts, dp, val, status, conf, src, upd in rows:
        p = priority.get(ts, 999)
        existing = best.get(dp)
        if existing is None or existing["_priority"] > p:
            best[dp] = {
                "value": json.loads(val),
                "data_status": status,
                "confidence": conf,
                "source": src,
                "updated_at": upd,
                "age_seconds": now - upd,
                "_origin_ts_code": ts,
                "_priority": p,
            }
    for v in best.values():
        v.pop("_priority", None)
    return best


def read_hot_snapshot_changed_since(
    db_path: Path, ts_code: str, since_unix: int
) -> dict[str, dict]:
    """Read only rows with updated_at > since_unix. Used by SSE delta loop."""

    if not db_path.exists():
        return {}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT dp_id, value_json, data_status, confidence, source, updated_at
              FROM realtime_current
             WHERE ts_code = ? AND updated_at > ?
            """,
            (ts_code, since_unix),
        ).fetchall()
    finally:
        conn.close()

    now = int(time.time())
    return {
        r[0]: {
            "value": json.loads(r[1]),
            "data_status": r[2],
            "confidence": r[3],
            "source": r[4],
            "updated_at": r[5],
            "age_seconds": now - r[5],
        }
        for r in rows
    }


def read_freshness_meta(db_path: Path) -> dict[str, dict]:
    """Read sync freshness metadata across layers (realtime / daily / static)."""

    if not db_path.exists():
        return {}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT layer, last_full_sync_at, last_partial_sync_at, sync_status
              FROM freshness_meta
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        r[0]: {
            "last_full_sync_at": r[1],
            "last_partial_sync_at": r[2],
            "sync_status": r[3],
        }
        for r in rows
    }


def read_available_overlay_industries(db_path: Path, ts_code: str) -> list[str]:
    """Return compiled industry views available for one company."""

    if not db_path.exists():
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT industry_id
              FROM overlay_manifest
             WHERE ts_code = ?
             ORDER BY primary_industry DESC, industry_id
            """,
            (ts_code,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    return [r[0] for r in rows]


def read_compiled_graph_snapshot(
    db_path: Path,
    ts_code: str,
    industry_id: str | None = None,
) -> dict[str, Any] | None:
    """Read the precompiled frontend snapshot for ``ts_code``.

    When ``industry_id`` is omitted, the primary industry view is returned.
    Returns ``None`` when the SQLite file or compiled snapshot is missing.
    """

    if not db_path.exists():
        return None

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if industry_id is None:
            row = conn.execute(
                """
                SELECT s.payload_json
                  FROM company_graph_snapshot s
                  JOIN overlay_manifest m
                    ON m.ts_code = s.ts_code AND m.industry_id = s.industry_id
                 WHERE s.ts_code = ?
                 ORDER BY m.primary_industry DESC, s.industry_id
                 LIMIT 1
                """,
                (ts_code,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT payload_json
                  FROM company_graph_snapshot
                 WHERE ts_code = ? AND industry_id = ?
                """,
                (ts_code, industry_id),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()

    if row is None:
        return None
    return json.loads(row[0])


def read_overlay_alerts(
    db_path: Path,
    ts_code: str,
    industry_id: str,
) -> list[dict[str, Any]]:
    """Read unresolved compiler alerts for one company-industry overlay."""

    if not db_path.exists():
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT alert_id, dp_id, severity, code, message, created_at, resolved_at
              FROM overlay_alert
             WHERE ts_code = ? AND industry_id = ? AND resolved_at IS NULL
             ORDER BY severity, dp_id
            """,
            (ts_code, industry_id),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    return [
        {
            "alert_id": r[0],
            "ts_code": ts_code,
            "industry_id": industry_id,
            "dp_id": r[1],
            "severity": r[2],
            "code": r[3],
            "message": r[4],
            "created_at": r[5],
            "resolved_at": r[6],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Write side (used by collector)
# ---------------------------------------------------------------------------


def upsert_realtime(
    db_path: Path,
    batch: Iterable[tuple[str, str, Any, str, float | None, str, int]],
) -> int:
    """Batch UPSERT into realtime_current.

    ``batch`` items: ``(ts_code, dp_id, value, data_status, confidence,
    source, updated_at)``. ``value`` may be any JSON-serialisable object; it
    is encoded internally so callers don't have to do ``json.dumps`` first.

    Returns count of upserted rows.
    """

    init_db(db_path)
    rows = [
        (
            ts_code,
            dp_id,
            value if isinstance(value, str) else json.dumps(value),
            data_status,
            confidence,
            source,
            int(updated_at),
        )
        for ts_code, dp_id, value, data_status, confidence, source, updated_at in batch
    ]
    if not rows:
        return 0

    with sqlite3.connect(str(db_path), isolation_level=None) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executemany(
            """
            INSERT INTO realtime_current
              (ts_code, dp_id, value_json, data_status, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ts_code, dp_id) DO UPDATE SET
              value_json = excluded.value_json,
              data_status = excluded.data_status,
              confidence = excluded.confidence,
              source = excluded.source,
              updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def update_freshness(
    db_path: Path,
    layer: str,
    sync_status: str = "ok",
    is_full: bool = False,
) -> None:
    """Stamp sync freshness for a layer."""

    init_db(db_path)
    now = int(time.time())
    with sqlite3.connect(str(db_path), isolation_level=None) as conn:
        if is_full:
            conn.execute(
                """
                INSERT INTO freshness_meta
                  (layer, last_full_sync_at, last_partial_sync_at, sync_status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (layer) DO UPDATE SET
                  last_full_sync_at = excluded.last_full_sync_at,
                  last_partial_sync_at = excluded.last_partial_sync_at,
                  sync_status = excluded.sync_status
                """,
                (layer, now, now, sync_status),
            )
        else:
            conn.execute(
                """
                INSERT INTO freshness_meta
                  (layer, last_full_sync_at, last_partial_sync_at, sync_status)
                VALUES (?, NULL, ?, ?)
                ON CONFLICT (layer) DO UPDATE SET
                  last_partial_sync_at = excluded.last_partial_sync_at,
                  sync_status = excluded.sync_status
                """,
                (layer, now, sync_status),
            )


def replace_compiled_overlays(
    db_path: Path,
    manifests: Iterable[dict[str, Any]],
    nodes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
    snapshots: Iterable[dict[str, Any]],
    alerts: Iterable[dict[str, Any]],
) -> None:
    """Replace compiled overlay tables atomically.

    Realtime rows are intentionally untouched. The compiler owns only
    ``overlay_*`` and ``company_*`` tables.
    """

    init_db(db_path)
    manifest_rows = list(manifests)
    node_rows = list(nodes)
    edge_rows = list(edges)
    snapshot_rows = list(snapshots)
    alert_rows = list(alerts)

    with sqlite3.connect(str(db_path), isolation_level=None) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM overlay_alert")
            conn.execute("DELETE FROM company_graph_snapshot")
            conn.execute("DELETE FROM company_edge_instance")
            conn.execute("DELETE FROM company_node_instance")
            conn.execute("DELETE FROM overlay_manifest")

            conn.executemany(
                """
                INSERT INTO overlay_manifest
                  (ts_code, industry_id, overlay_path, period, primary_industry,
                   overlay_status, updated_at)
                VALUES
                  (:ts_code, :industry_id, :overlay_path, :period, :primary_industry,
                   :overlay_status, :updated_at)
                """,
                manifest_rows,
            )
            conn.executemany(
                """
                INSERT INTO company_node_instance
                  (ts_code, industry_id, node_id, dp_id, payload_json, data_status,
                   required_level, missing_policy, calculation_type,
                   aggregation_policy, materiality, confidence, source_overlay_path)
                VALUES
                  (:ts_code, :industry_id, :node_id, :dp_id, :payload_json, :data_status,
                   :required_level, :missing_policy, :calculation_type,
                   :aggregation_policy, :materiality, :confidence, :source_overlay_path)
                """,
                node_rows,
            )
            conn.executemany(
                """
                INSERT INTO company_edge_instance
                  (ts_code, industry_id, edge_id, edge_kind, from_node, to_node,
                   edge_type, payload_json)
                VALUES
                  (:ts_code, :industry_id, :edge_id, :edge_kind, :from_node, :to_node,
                   :edge_type, :payload_json)
                """,
                edge_rows,
            )
            conn.executemany(
                """
                INSERT INTO company_graph_snapshot
                  (ts_code, industry_id, payload_json, graph_version, data_version, updated_at)
                VALUES
                  (:ts_code, :industry_id, :payload_json, :graph_version, :data_version, :updated_at)
                """,
                snapshot_rows,
            )
            conn.executemany(
                """
                INSERT INTO overlay_alert
                  (alert_id, ts_code, industry_id, dp_id, severity, code, message,
                   created_at, resolved_at)
                VALUES
                  (:alert_id, :ts_code, :industry_id, :dp_id, :severity, :code, :message,
                   :created_at, :resolved_at)
                """,
                alert_rows,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
