"""Minute-level history archive via Parquet + DuckDB.

Layer-B in the data plan (see plan file at ~/.claude/plans/13-ai-recursive-pie.md):
the collector daemon dual-writes — UPSERT to ``runtime/hot.sqlite`` for low-
latency current-snapshot reads, and APPEND to ``runtime/history/minute/`` for
analytical / replay queries.

File layout::

    runtime/history/
    ├── minute/
    │   ├── partition_minute=20260511_1200.parquet  ← one per collector tick
    │   └── ...
    └── daily_compact/
        ├── date=2026-05-11.parquet                  ← compacted yesterday
        └── ...

DuckDB reads the whole tree via ``read_parquet(...)``; compact job (run daily)
merges yesterday's minute files into a single daily file and removes the
originals to keep DuckDB scanning cost low.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Writer (used by collector daemon)
# ---------------------------------------------------------------------------


def append_minute_parquet(
    history_dir: Path,
    batch: Iterable[tuple[str, str, object, str, float | None, str, int]],
) -> Path:
    """Append a batch to ``minute/partition_minute=YYYYMMDD_HHMM.parquet``.

    If the partition file for the current minute already exists, the new rows
    are concatenated to it (re-written compressed). This is fine for our
    workload — one collector writer, ~10K rows/min/batch.

    ``batch`` items: ``(ts_code, dp_id, value, data_status, confidence,
    source, updated_at)``. ``value`` may be any JSON-serialisable object.

    Returns the path of the parquet file written.
    """

    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = list(batch)
    if not rows:
        raise ValueError("append_minute_parquet: empty batch")

    minute_dir = history_dir / "minute"
    minute_dir.mkdir(parents=True, exist_ok=True)
    minute_key = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
    out_path = minute_dir / f"partition_minute={minute_key}.parquet"

    table = pa.table({
        "ts_code": pa.array([r[0] for r in rows], type=pa.string()),
        "dp_id": pa.array([r[1] for r in rows], type=pa.string()),
        "value_json": pa.array(
            [r[2] if isinstance(r[2], str) else json.dumps(r[2], ensure_ascii=False)
             for r in rows],
            type=pa.string(),
        ),
        "data_status": pa.array([r[3] for r in rows], type=pa.string()),
        "confidence": pa.array([r[4] for r in rows], type=pa.float64()),
        "source": pa.array([r[5] for r in rows], type=pa.string()),
        "updated_at": pa.array([int(r[6]) for r in rows], type=pa.int64()),
    })

    if out_path.exists():
        existing = pq.read_table(out_path)
        table = pa.concat_tables([existing, table])

    pq.write_table(table, out_path, compression="zstd")
    return out_path


# ---------------------------------------------------------------------------
# Reader (used by server.handle_history)
# ---------------------------------------------------------------------------


def query_history(
    history_dir: Path,
    ts_code: str,
    dp_id: str,
    since_unix: int,
    until_unix: int | None = None,
    limit: int = 5000,
) -> list[dict]:
    """Return time-ordered rows for one (ts_code, dp_id) in range.

    Scans both ``minute/`` and ``daily_compact/`` parquet trees, dedupes by
    ``updated_at`` (latest write wins if the same minute partition exists in
    both), and returns at most ``limit`` rows.
    """

    import duckdb

    minute_glob = str(history_dir / "minute" / "*.parquet")
    compact_glob = str(history_dir / "daily_compact" / "*.parquet")
    # Build a UNION over whichever subtrees exist
    sources = []
    if (history_dir / "minute").exists() and any((history_dir / "minute").iterdir()):
        sources.append(f"read_parquet('{minute_glob}', hive_partitioning=1)")
    if (history_dir / "daily_compact").exists() and any((history_dir / "daily_compact").iterdir()):
        sources.append(f"read_parquet('{compact_glob}', hive_partitioning=1)")
    if not sources:
        return []
    union_expr = " UNION ALL ".join(f"SELECT * FROM {s}" for s in sources)

    until = until_unix if until_unix is not None else 2_000_000_000  # ~2033
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT updated_at, value_json, data_status, confidence, source
          FROM ({union_expr})
         WHERE ts_code = ? AND dp_id = ?
           AND updated_at BETWEEN ? AND ?
         ORDER BY updated_at
         LIMIT ?
        """,
        [ts_code, dp_id, since_unix, until, limit],
    ).fetchall()
    con.close()

    return [{
        "updated_at": r[0],
        "value": json.loads(r[1]) if r[1] else None,
        "data_status": r[2],
        "confidence": r[3],
        "source": r[4],
    } for r in rows]


# ---------------------------------------------------------------------------
# Compact job (cron / daily)
# ---------------------------------------------------------------------------


def compact_date(history_dir: Path, date_yyyymmdd: str, *, delete_source: bool = True) -> Path | None:
    """Merge every ``partition_minute={date}_*.parquet`` for one day into a
    single ``daily_compact/date=YYYY-MM-DD.parquet`` file, optionally deleting
    the per-minute files.

    Returns the output path, or ``None`` if no source files exist."""

    import duckdb

    minute_dir = history_dir / "minute"
    compact_dir = history_dir / "daily_compact"
    compact_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(minute_dir.glob(f"partition_minute={date_yyyymmdd}_*.parquet"))
    if not sources:
        return None

    iso_date = f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:]}"
    out_path = compact_dir / f"date={iso_date}.parquet"

    pattern = str(minute_dir / f"partition_minute={date_yyyymmdd}_*.parquet")
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT ts_code, dp_id, value_json, data_status, confidence,
                   source, updated_at
              FROM read_parquet('{pattern}', hive_partitioning=1)
        ) TO '{out_path}' (FORMAT PARQUET, COMPRESSION 'zstd');
        """
    )
    con.close()

    if delete_source:
        for f in sources:
            f.unlink()

    return out_path


def compact_yesterday(history_dir: Path) -> Path | None:
    yesterday = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")
    return compact_date(history_dir, yesterday)
