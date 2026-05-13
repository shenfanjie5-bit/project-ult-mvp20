"""Source fingerprint for refresh-trigger decisions (Z2).

Each LLM-derived dp_id has ``source_dependencies`` declared in
``config/llm_field_governance.yaml``. We compute a short stable
fingerprint over those dependencies' current state in SQLite. Codex
writes that fingerprint back into the overlay node under
``source_fingerprint_at_fill`` when it fills the slot.

On the next codex run, ``codex_prompt_gen._is_fillable`` re-computes
the current fingerprint and compares it against the stored value:

* same fingerprint → source unchanged → Known is preserved as-is.
* different fingerprint → source has rotated (new filing period, new
  event, new value) → slot re-enters the codex prompt queue.

Hashing strategy (per Z2 design):

* ``dp_id + source + updated_at + normalized value_json`` is the base
  payload. Normalising ``value_json`` (sorting dict keys) defends
  against semantically-equal payloads producing different hashes.
* ``updated_at`` alone is too brittle — some collectors rewrite the
  timestamp without touching the body, and the body can change
  without an updated_at bump.
* For filing-class dp_ids (income/balance/cashflow/fina_indicator and
  the three X5 text disclosures) we additionally fold
  ``period`` / ``end_date`` / ``ann_date`` / ``latest_period`` into
  the hash so a new filing trips the refresh even if intra-period
  values stay flat.
* Each per-dp_id sub-hash is concatenated in sorted dp_id order, and
  SHA256-hashed again. The final 16-char hex prefix is the
  fingerprint.

The module is intentionally side-effect free and read-only against
SQLite — it is safe to call from prompt-gen, verification, or any
other audit path.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


# Filing-related source dp_ids whose period / end_date / ann_date should be
# part of the fingerprint. These come from Tushare income / balance / cashflow
# / fina_indicator + the three X5 text disclosures, all of which carry a
# ``period`` or ``end_date`` field in their value_json.
FILING_SOURCE_DP_IDS: frozenset[str] = frozenset({
    # Income statement
    "L5.is.revenue", "L5.is.gross_profit", "L5.is.net_profit",
    "L5.is.operating_profit", "L5.is.eps", "L5.is.margins",
    "L5.is.revenue_growth", "L5.is.gross_margin", "L5.is.sga_rd",
    # Balance sheet
    "L5.bs.cash_debt", "L5.bs.inventory", "L5.bs.ar_ap",
    "L5.bs.goodwill_ppe", "L5.bs.leverage",
    # Cash flow
    "L5.cf.ocf", "L5.cf.fcf", "L5.cf.capex", "L5.cf.icf_fcf",
    # Fina indicator
    "L5.fina.eps", "L5.fina.roe", "L5.fina.roa",
    # X5 text disclosures (each row carries an end_date / ann_date in value)
    "L1.company.main_business", "L9.disclosure.qa_recent",
    "L8.gov.management_table",
})


def _normalize_value(value_json: str) -> str:
    """Canonicalise ``value_json`` so semantically-equal payloads hash same.

    JSON object key order is non-deterministic between writers; sorting
    keys before hashing guarantees identical content → identical hash.
    Falls back to the raw string if the input is not valid JSON.
    """

    if not value_json:
        return ""
    try:
        obj = json.loads(value_json)
    except (json.JSONDecodeError, TypeError):
        return value_json
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _row_fingerprint(row: tuple) -> str:
    """Hash a single ``realtime_current`` row.

    Args:
        row: tuple of ``(dp_id, value_json, data_status, confidence,
             source, updated_at)``.

    Returns:
        16-char hex prefix of SHA256. Caller is responsible for
        combining per-dp_id sub-hashes.
    """

    dp_id, value_json, _data_status, _confidence, source, updated_at = row
    payload = "|".join([
        str(dp_id or ""),
        str(source or ""),
        str(updated_at or 0),
        _normalize_value(value_json or ""),
    ])
    # For filing dp_ids, fold period / end_date / ann_date into the hash so
    # a new filing rotates the fingerprint even when intra-period values
    # are bit-identical.
    if dp_id in FILING_SOURCE_DP_IDS:
        try:
            v = json.loads(value_json or "{}")
            if isinstance(v, dict):
                extras = "|".join([
                    str(v.get("period", "")),
                    str(v.get("end_date", "")),
                    str(v.get("ann_date", "")),
                    str(v.get("latest_period", "")),
                ])
                payload = f"{payload}|filing:{extras}"
        except (json.JSONDecodeError, TypeError):
            pass
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _candidate_ts_codes(ts_code: str) -> list[str]:
    """Build the lookup-priority list for a given ts_code.

    Mirrors ``storage.read_hot_snapshot``'s preference: per-stock row
    first, then ``MARKET:<market>`` sentinel as a fallback.
    """

    out = [ts_code]
    if ts_code.endswith((".SH", ".SZ", ".BJ")):
        out.append("MARKET:CN")
    elif ts_code.endswith(".HK"):
        out.append("MARKET:HK")
    elif ts_code.endswith(".US"):
        out.append("MARKET:US")
    return out


def compute_dependency_fingerprint(
    ts_code: str,
    dependencies: list[str],
    db_path: Path,
) -> str | None:
    """Compute the combined fingerprint over a dp_id's source dependencies.

    Args:
        ts_code: target ts_code (or ``INDUSTRY:<id>`` sentinel for L0).
        dependencies: list of source dp_ids declared under
            ``governance.source_dependencies``.
        db_path: path to ``runtime/hot.sqlite``.

    Returns:
        16-char hex SHA256 prefix, or ``None`` if no dependencies were
        declared, the db is missing, or none of the dependencies were
        found in ``realtime_current``. Caller decides what to do with
        a ``None`` result — for refresh logic we treat it as "no
        signal, do not refresh".
    """

    if not dependencies:
        return None
    if not db_path.exists():
        return None

    candidates = _candidate_ts_codes(ts_code)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" * len(candidates))
        deps_placeholders = ",".join("?" * len(dependencies))
        rows = conn.execute(
            f"""
            SELECT dp_id, value_json, data_status, confidence, source,
                   updated_at, ts_code
            FROM realtime_current
            WHERE ts_code IN ({placeholders})
              AND dp_id IN ({deps_placeholders})
            """,
            (*candidates, *dependencies),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    # Pick the highest-priority row per dp_id (ts_code-specific over MARKET
    # sentinel) so MARKET data only contributes when no ts-specific row exists.
    priority = {t: i for i, t in enumerate(candidates)}
    best_per_dp: dict[str, tuple[int, tuple]] = {}
    for r in rows:
        dp_id = r[0]
        ts = r[6]
        p = priority.get(ts, 999)
        existing = best_per_dp.get(dp_id)
        if existing is None or existing[0] > p:
            best_per_dp[dp_id] = (p, r[:6])

    if not best_per_dp:
        return None

    sub_hashes = []
    for dp_id in sorted(best_per_dp.keys()):
        _, r = best_per_dp[dp_id]
        sub_hashes.append(_row_fingerprint(r))
    combined = "|".join(sub_hashes)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def is_refresh_triggered(
    node: dict,
    governance_entry: dict,
    db_path: Path,
    ts_code: str,
) -> tuple[bool, str]:
    """Decide whether to refresh an LLM-filled node based on governance.

    The five ``refresh_trigger`` values supported in governance.yaml
    map as follows:

    * ``static_picture`` — never auto-refresh; only explicit operator
      request rotates it. Returns ``(False, "static_picture")``.
    * ``explicit_refresh`` — same as above but semantically operator-
      driven. Returns ``(False, "explicit_refresh_only")``.
    * ``source_fingerprint_changed`` — refresh iff fingerprint
      differs from stored ``source_fingerprint_at_fill``.
    * ``quarterly_filing`` / ``annual_filing`` — refresh iff
      fingerprint over filing-class source dp_ids changed (period /
      end_date / ann_date are folded in for those dp_ids).
    * ``event_driven`` — refresh iff fingerprint over event-class
      source dp_ids (L9.media.*, L9.industry.*, L9.macro.* etc)
      changed. New events rotate updated_at and value_json, so the
      same hash diff catches them.

    Returns:
        ``(need_refresh, reason)``. ``reason`` is a short tag the
        caller can surface in ``--list-only`` reports.
    """

    trigger = governance_entry.get("refresh_trigger", "static_picture")
    stored_fp = node.get("source_fingerprint_at_fill")
    deps = governance_entry.get("source_dependencies") or []

    if trigger == "static_picture":
        return False, "static_picture"

    if trigger == "explicit_refresh":
        return False, "explicit_refresh_only"

    if not deps:
        # Conservative: without declared dependencies we have nothing
        # to fingerprint, so don't trigger spurious re-runs.
        return False, "no_source_dependencies"

    current_fp = compute_dependency_fingerprint(ts_code, deps, db_path)
    if current_fp is None:
        return False, "no_source_data"

    if stored_fp is None:
        # Legacy fill predating Z2 — refresh once to establish baseline.
        return True, "fingerprint_baseline_missing"

    if current_fp != stored_fp:
        return True, f"source_changed_{trigger}"

    return False, "fingerprint_unchanged"
