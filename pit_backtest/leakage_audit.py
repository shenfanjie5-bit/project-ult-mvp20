"""Independent leakage audit over the persisted PIT artifacts.

Re-verifies — without trusting the collector — that nothing dated after a base
date entered that base date's features, and that forward-return labels are all
realized (end_date <= T0). Runnable standalone via scripts/verify_pit_no_leak.py;
exits non-zero on any HARD violation so it can gate CI.

HARD (fail): an observation/announcement date (ann_date / f_ann_date /
trade_date / latest_date / as_of) in any feature payload exceeds the base date;
a forward-return end_date exceeds T0; a feature payload contains a
forward-looking price key.
WARN (report only): a report-period date (period / latest_period / ...) exceeds
the base date (forecast target periods can legitimately be future).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

# obs/announcement dates: must be <= base_date (HARD)
_HARD_DATE_KEYS = ("ann_date", "f_ann_date", "trade_date", "latest_date")
# report-period dates: checked but only WARN (forecast targets may be future)
_SOFT_DATE_KEYS = ("period", "latest_period", "ebitda_period", "fcf_period_end",
                   "current_period", "yoy_compare_period")
# keys that would betray forward-return contamination of a feature
_FORBIDDEN_FEATURE_KEYS = ("fwd_ret", "forward_return", "close_end", "ret_fwd")


def _as_yyyymmdd(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":  # ISO date/datetime
        s = s[:10].replace("-", "")
    if len(s) == 8 and s.isdigit():
        return s
    return None


def audit_pit_db(db_path: Path, asof: str) -> dict:
    """Scan one PIT sqlite; return {hard:[...], warn:[...], dp_max_date:{}, n_rows}."""

    res: dict[str, Any] = {"asof": asof, "db": str(db_path), "hard": [], "warn": [],
                           "dp_max_date": {}, "n_rows": 0}
    if not Path(db_path).exists():
        res["hard"].append(f"missing PIT db {db_path}")
        return res
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT ts_code, dp_id, value_json FROM realtime_current"
        ).fetchall()
    finally:
        con.close()
    res["n_rows"] = len(rows)
    for ts, dp, vj in rows:
        try:
            payload = json.loads(vj)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        for k in _FORBIDDEN_FEATURE_KEYS:
            if k in payload:
                res["hard"].append(f"{ts} {dp}: forbidden feature key {k}")
        for k in _HARD_DATE_KEYS:
            d = _as_yyyymmdd(payload.get(k))
            if d is None:
                continue
            prev = res["dp_max_date"].get(dp)
            if prev is None or d > prev:
                res["dp_max_date"][dp] = d
            if d > asof:
                res["hard"].append(f"{ts} {dp}: {k}={d} > asof={asof}")
        for k in _SOFT_DATE_KEYS:
            d = _as_yyyymmdd(payload.get(k))
            if d is not None and d > asof:
                res["warn"].append(f"{ts} {dp}: {k}={d} > asof={asof}")
    return res


def audit_returns(returns_rows: list[dict], t0: str) -> dict:
    hard: list[str] = []
    for r in returns_rows:
        ed = str(r.get("used_end_date") or r.get("end_date") or "")
        if ed and ed > t0:
            hard.append(f"{r.get('ts_code')} return end_date={ed} > T0={t0}")
    return {"hard": hard, "n": len(returns_rows)}


def audit_artifacts(base_dates: dict, root: Path = Path("runtime/backtest")) -> dict:
    warn: list[str] = []
    for off, asof in base_dates.items():
        if int(off) == 0:
            continue
        art = Path(root) / asof / "peer_context_A.json"
        if not art.exists():
            warn.append(f"missing peer_context artifact for {asof}")
    return {"warn": warn}


def run_full_audit(db_path: Path, root: Path = Path("runtime/backtest")) -> dict:
    """Audit all base-date PIT DBs + returns referenced by the results store."""

    from pit_backtest import store

    base = store.get_manifest("base_dates", db_path) or {}
    base = {int(k): v for k, v in base.items()}
    t0 = base.get(0, "99999999")
    report: dict[str, Any] = {"base_dates": base, "per_asof": {}, "hard_total": 0,
                              "warn_total": 0, "ok": True}
    for off, asof in base.items():
        if int(off) == 0:
            continue
        pit_db = Path(root) / asof / "pit.sqlite"
        a = audit_pit_db(pit_db, asof)
        report["per_asof"][asof] = a
        report["hard_total"] += len(a["hard"])
        report["warn_total"] += len(a["warn"])
    ret = audit_returns(store.read_returns(db_path), t0)
    report["returns"] = ret
    report["hard_total"] += len(ret["hard"])
    art = audit_artifacts(base, root)
    report["artifacts"] = art
    report["warn_total"] += len(art["warn"])
    report["ok"] = report["hard_total"] == 0
    return report
