"""Tests for the industry-level source-evidence aggregation in
``scripts/codex_prompt_gen.py``.

Background / root cause guarded here
------------------------------------
Industry L0 dp_ids declare ``source_dependencies`` (e.g. ``L5.is.revenue``,
``L9.media.report``) in ``config/llm_field_governance.yaml``. Those deps are
stored in ``realtime_current`` EITHER per-constituent (``000063.SZ`` …) OR
under the ``MARKET:CN`` sentinel — never under the ``INDUSTRY:<id>`` key that
``build_industry_prompt`` reads the snapshot against. Before the fix every L0
dep rendered as "(missing in SQLite)", so a codex fill produced only Unknown /
``no_local_evidence`` nodes.

The fix resolves each industry dep through a tier ladder:
  1. industry-sentinel direct hit,
  2. aggregate across the industry's constituents (numeric → mean/median +
     per-member sample; text → per-member compact value),
  3. fall back to the ``MARKET:CN`` sentinel row.

These tests pin that ladder + the invariant that the company prompt path is
unchanged (no aggregation, legacy "(missing in SQLite)").
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "codex_prompt_gen",
    ROOT / "scripts" / "codex_prompt_gen.py",
)
assert _SPEC is not None and _SPEC.loader is not None
codex_prompt_gen = importlib.util.module_from_spec(_SPEC)
sys.modules["codex_prompt_gen"] = codex_prompt_gen
_SPEC.loader.exec_module(codex_prompt_gen)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, rows: list[tuple]) -> Path:
    """Build a realtime_current SQLite matching storage.SCHEMA_SQL columns."""

    db_path = tmp_path / "hot.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE realtime_current (
                ts_code TEXT NOT NULL,
                dp_id TEXT NOT NULL,
                value_json TEXT NOT NULL,
                data_status TEXT NOT NULL,
                confidence REAL,
                source TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (ts_code, dp_id)
            )
            """
        )
        # overlay_manifest is queried by read_hot_snapshot's sentinel fan-out;
        # create it empty so the fan-out finds no industry for a stock.
        conn.execute(
            """
            CREATE TABLE overlay_manifest (
                ts_code TEXT NOT NULL,
                industry_id TEXT NOT NULL,
                overlay_path TEXT NOT NULL,
                period TEXT,
                primary_industry INTEGER NOT NULL DEFAULT 0,
                overlay_status TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (ts_code, industry_id)
            )
            """
        )
        conn.executemany(
            "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ---------------------------------------------------------------------------
# _primary_numeric — headline-number extraction
# ---------------------------------------------------------------------------


def test_primary_numeric_scalar():
    assert codex_prompt_gen._primary_numeric(
        {"scalar": 100.0, "unit": "元"}
    ) == (100.0, "scalar")


def test_primary_numeric_yoy_pct():
    assert codex_prompt_gen._primary_numeric(
        {"yoy_pct": 6.13, "qoq_pct": -1.0}
    ) == (6.13, "yoy_pct")


def test_primary_numeric_fallback_first_leaf():
    n, field = codex_prompt_gen._primary_numeric({"weird_metric": 3.3})
    assert n == 3.3 and field == "weird_metric"


def test_primary_numeric_ignores_bool_and_nan():
    # bool is not a number for our purposes
    assert codex_prompt_gen._primary_numeric({"flag": True}) is None
    nan = float("nan")
    assert codex_prompt_gen._primary_numeric({"scalar": nan}) is None


def test_primary_numeric_non_dict_none():
    assert codex_prompt_gen._primary_numeric("text") is None
    assert codex_prompt_gen._primary_numeric(None) is None


# ---------------------------------------------------------------------------
# _is_market_level_dep
# ---------------------------------------------------------------------------


def test_market_level_dep_classification():
    assert codex_prompt_gen._is_market_level_dep("L9.media.report")
    assert codex_prompt_gen._is_market_level_dep("L9.industry.compete_risk")
    assert codex_prompt_gen._is_market_level_dep("L9.macro.fx")
    # per-stock deps are NOT market-level
    assert not codex_prompt_gen._is_market_level_dep("L5.is.revenue")
    assert not codex_prompt_gen._is_market_level_dep("L9.disclosure.qa_recent")
    assert not codex_prompt_gen._is_market_level_dep("L9.media.social_buzz")


# ---------------------------------------------------------------------------
# _aggregate_industry_dep_value — numeric + text paths
# ---------------------------------------------------------------------------


def test_aggregate_numeric_mean_median_members(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.revenue",
         '{"scalar": 100.0, "period": "20260331"}', "Known", 0.9, "t", 1),
        ("B.SZ", "L5.is.revenue",
         '{"scalar": 200.0, "period": "20260331"}', "Known", 0.9, "t", 1),
        ("C.SZ", "L5.is.revenue",
         '{"scalar": 300.0, "period": "20260331"}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.revenue", ["A.SZ", "B.SZ", "C.SZ"], db
    )
    assert out is not None
    assert "industry-aggregate over 3 constituents" in out
    assert "field=scalar" in out
    assert "mean=200.00" in out
    assert "median=200.00" in out
    assert "min=100.00" in out and "max=300.00" in out
    assert "latest_period=20260331" in out
    # per-member figures are quotable
    assert "A.SZ=100.00" in out


def test_aggregate_skips_member_missing_dep(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.revenue", '{"scalar": 100.0}', "Known", 0.9, "t", 1),
        # B.SZ has no L5.is.revenue row
        ("B.SZ", "L5.is.gross_margin", '{"scalar": 0.3}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.revenue", ["A.SZ", "B.SZ"], db
    )
    # Only A.SZ present → single-member aggregate path may not trigger the
    # numeric branch (needs >=2); falls through to text listing of the 1 member.
    assert out is not None
    assert "A.SZ" in out
    assert "B.SZ" not in out


def test_aggregate_returns_none_when_no_member_has_dep(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.gross_margin", '{"scalar": 0.3}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.revenue", ["A.SZ", "B.SZ"], db
    )
    assert out is None


def test_aggregate_text_path_lists_members(tmp_path: Path):
    rows = [
        ("A.SZ", "L1.company.main_business",
         '{"main_business": "做芯片"}', "Known", 0.9, "t", 1),
        ("B.SZ", "L1.company.main_business",
         '{"main_business": "做光模块"}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._aggregate_industry_dep_value(
        "L1.company.main_business", ["A.SZ", "B.SZ"], db
    )
    assert out is not None
    assert "constituents (text)" in out
    assert "做芯片" in out and "做光模块" in out


def test_aggregate_sample_caps_and_reports_more(tmp_path: Path):
    members = [f"{i:06d}.SZ" for i in range(10)]
    rows = [
        (m, "L5.is.revenue", f'{{"scalar": {100 + i}.0}}', "Known", 0.9, "t", 1)
        for i, m in enumerate(members)
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.revenue", members, db
    )
    assert out is not None
    # 10 members, sample cap is _INDUSTRY_SAMPLE_N → reports the remainder
    more = 10 - codex_prompt_gen._INDUSTRY_SAMPLE_N
    assert f"(+{more} more)" in out


def test_aggregate_snapshot_cache_reads_each_member_once(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.revenue", '{"scalar": 100.0}', "Known", 0.9, "t", 1),
        ("B.SZ", "L5.is.revenue", '{"scalar": 200.0}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    cache: dict[str, dict] = {}
    codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.revenue", ["A.SZ", "B.SZ"], db, snapshot_cache=cache
    )
    # Cache now holds both members' snapshots; a second dep reuses them.
    assert set(cache.keys()) == {"A.SZ", "B.SZ"}
    codex_prompt_gen._aggregate_industry_dep_value(
        "L5.is.gross_margin", ["A.SZ", "B.SZ"], db, snapshot_cache=cache
    )
    assert set(cache.keys()) == {"A.SZ", "B.SZ"}


# ---------------------------------------------------------------------------
# _resolve_dep_value_text — the tier ladder
# ---------------------------------------------------------------------------


def test_resolve_company_path_missing_is_legacy(tmp_path: Path):
    """Company prompt (industry_constituents=None) must NOT aggregate."""

    db = _make_db(tmp_path, [])
    out = codex_prompt_gen._resolve_dep_value_text(
        "L5.is.revenue", {}, industry_constituents=None, db_path=db
    )
    assert out == "(missing in SQLite)"


def test_resolve_industry_aggregates_per_stock_dep(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.revenue", '{"scalar": 100.0}', "Known", 0.9, "t", 1),
        ("B.SZ", "L5.is.revenue", '{"scalar": 200.0}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._resolve_dep_value_text(
        "L5.is.revenue", {}, industry_constituents=["A.SZ", "B.SZ"], db_path=db
    )
    assert "industry-aggregate over 2 constituents" in out


def test_resolve_industry_market_dep_falls_back_to_market_cn(tmp_path: Path):
    rows = [
        ("MARKET:CN", "L9.media.report",
         '{"count_24h": 3, "top_headlines": ["x"]}', "Known", 0.6, "cls", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._resolve_dep_value_text(
        "L9.media.report", {}, industry_constituents=["A.SZ"], db_path=db
    )
    assert out.startswith("[MARKET:CN")
    assert "count_24h" in out


def test_resolve_industry_market_dep_surfaces_inactive_status(tmp_path: Path):
    """When MARKET:CN feed is Inactive/empty, surface the status honestly."""

    rows = [
        ("MARKET:CN", "L9.media.report",
         '{"count_24h": 0, "reason": "upstream_error"}',
         "Inactive", 0.5, "cls", 1),
    ]
    db = _make_db(tmp_path, rows)
    out = codex_prompt_gen._resolve_dep_value_text(
        "L9.media.report", {}, industry_constituents=["A.SZ"], db_path=db
    )
    assert "status=Inactive" in out
    assert "upstream_error" in out


def test_resolve_industry_sentinel_direct_hit_wins(tmp_path: Path):
    """A dep already present under INDUSTRY:<id> is used directly (no agg)."""

    # snapshot here represents the INDUSTRY:<id> read result already holding
    # the dep (e.g. L0.cost.raw_material from the akshare commodity fetch).
    snapshot = {
        "L0.cost.raw_material": {
            "value": {"avg_pct_change": 1.23},
            "data_status": "Known",
        }
    }
    db = _make_db(tmp_path, [])
    out = codex_prompt_gen._resolve_dep_value_text(
        "L0.cost.raw_material",
        snapshot,
        industry_constituents=["A.SZ"],
        db_path=db,
    )
    assert "avg_pct_change" in out
    assert "industry-aggregate" not in out  # direct hit, not aggregated


def test_resolve_industry_missing_everywhere_is_missing(tmp_path: Path):
    db = _make_db(tmp_path, [])
    out = codex_prompt_gen._resolve_dep_value_text(
        "L5.is.revenue", {}, industry_constituents=["A.SZ"], db_path=db
    )
    assert out == "(missing in SQLite)"


# ---------------------------------------------------------------------------
# _load_industry_constituents
# ---------------------------------------------------------------------------


def test_load_industry_constituents_filters_by_industry(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "mvp20.universe.yaml").write_text(
        """
constituents:
  - ts_code: 000063.SZ
    industry_ids: [AI_COMPUTE]
  - ts_code: 600276.SH
    industry_ids: [INNOVATIVE_PHARMA]
  - ts_code: TSM.US
    industry_ids: [AI_COMPUTE, SEMI_EQUIPMENT]
""",
        encoding="utf-8",
    )
    out = codex_prompt_gen._load_industry_constituents("AI_COMPUTE", tmp_path)
    assert out == ["000063.SZ", "TSM.US"]


def test_load_industry_constituents_missing_universe_returns_empty(
    tmp_path: Path,
):
    out = codex_prompt_gen._load_industry_constituents("AI_COMPUTE", tmp_path)
    assert out == []


# ---------------------------------------------------------------------------
# Integration through _build_source_value_table
# ---------------------------------------------------------------------------


def test_build_source_value_table_industry_aggregates(tmp_path: Path):
    rows = [
        ("A.SZ", "L5.is.revenue", '{"scalar": 100.0}', "Known", 0.9, "t", 1),
        ("B.SZ", "L5.is.revenue", '{"scalar": 300.0}', "Known", 0.9, "t", 1),
    ]
    db = _make_db(tmp_path, rows)
    governance = {
        "data_points": {
            "L0.demand.terminal": {
                "route": "llm_close",
                "source_dependencies": ["L5.is.revenue"],
            }
        }
    }
    nodes = [{"dp_id": "L0.demand.terminal", "data_status": "Unknown"}]
    table = codex_prompt_gen._build_source_value_table(
        nodes,
        governance,
        "INDUSTRY:AI_COMPUTE",
        db,
        industry_constituents=["A.SZ", "B.SZ"],
    )
    assert len(table) == 1
    dp_id, dep, value_text = table[0]
    assert dp_id == "L0.demand.terminal"
    assert dep == "L5.is.revenue"
    assert "industry-aggregate over 2 constituents" in value_text
    assert "mean=200.00" in value_text


def test_build_source_value_table_company_unchanged(tmp_path: Path):
    """Company path (no industry_constituents) keeps legacy semantics."""

    db = _make_db(tmp_path, [])
    governance = {
        "data_points": {
            "L1.position.brand": {
                "route": "llm_close",
                "source_dependencies": ["L5.is.revenue"],
            }
        }
    }
    nodes = [{"dp_id": "L1.position.brand", "data_status": "Unknown"}]
    table = codex_prompt_gen._build_source_value_table(
        nodes, governance, "000063.SZ", db
    )
    assert table == [("L1.position.brand", "L5.is.revenue", "(missing in SQLite)")]
