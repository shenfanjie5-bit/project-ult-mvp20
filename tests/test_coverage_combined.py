"""Tests for ``combined_coverage_summary`` — the SQLite + yaml union layer
that augments spec §23 yaml-only coverage with hard-data from the realtime
hot snapshot.

Each test pins one behavioural contract:

- SQLite-only contribution → headline reflects ``|sqlite ∩ spec| / |spec|``.
- yaml-only contribution → headline reflects ``|yaml_known ∩ spec| / |spec|``.
- Disjoint SQLite + yaml → headline = sum / |spec|.
- Overlapping SQLite + yaml → union is de-duplicated.
- ``db_path=None`` → graceful fallback to yaml-only behaviour.
- ``spec_path=None`` → graceful fallback (headline keeps yaml-only value).
- Legacy dp_ids outside the spec universe are excluded from the numerator.
- Backend endpoint smoke (000063.SZ): headline > 0 once SQLite hard data is
  pulled in, even when overlay yaml is all Unknown.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest
import yaml

from mvp20.coverage import (
    _collect_sqlite_known_dps,
    combined_coverage_summary,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config" / "data_point_roles.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    """Build a minimal hot.sqlite with ``realtime_current``.

    rows = [(ts_code, dp_id, data_status, value_json), ...]
    """
    db = tmp_path / "hot.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE realtime_current (
            ts_code TEXT NOT NULL,
            dp_id   TEXT NOT NULL,
            value_json TEXT NOT NULL,
            data_status TEXT,
            confidence REAL,
            source TEXT,
            updated_at INTEGER,
            PRIMARY KEY (ts_code, dp_id)
        )
        """
    )
    now = int(time.time())
    for ts_code, dp_id, status, val in rows:
        conn.execute(
            "INSERT INTO realtime_current VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts_code, dp_id, val, status, 1.0, "test", now),
        )
    conn.commit()
    conn.close()
    return db


def _make_spec(tmp_path: Path, dp_ids: list[str]) -> Path:
    """Build a tiny spec yaml file with the given dp_id universe."""
    spec = {
        "schema_version": 1,
        "spec_total_dp_ids": len(dp_ids),
        "data_points": {dp: {"field_role": "raw_input"} for dp in dp_ids},
    }
    p = tmp_path / "spec.yaml"
    p.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return p


def _overlay(known_dps: list[str], unknown_dps: list[str]) -> dict:
    """Build a minimal overlay payload with one parent and given children."""
    nodes = [{"node_id": "P", "parent_node": None, "child_nodes": [], "dp_id": "P"}]
    child_ids: list[str] = []
    for dp in known_dps:
        nid = f"N.{dp}"
        nodes.append({
            "node_id": nid, "parent_node": "P", "dp_id": dp,
            "data_status": "Known", "active_weight": 1.0, "base_weight": 1.0,
        })
        child_ids.append(nid)
    for dp in unknown_dps:
        nid = f"N.{dp}"
        nodes.append({
            "node_id": nid, "parent_node": "P", "dp_id": dp,
            "data_status": "Unknown", "active_weight": 1.0, "base_weight": 1.0,
        })
        child_ids.append(nid)
    nodes[0]["child_nodes"] = child_ids
    return {"ts_code": "TEST.SZ", "industry_id": "TEST", "nodes": nodes}


# ---------------------------------------------------------------------------
# _collect_sqlite_known_dps — unit
# ---------------------------------------------------------------------------


def test_collect_sqlite_only_in_spec(tmp_path: Path) -> None:
    """SQLite dp_ids outside the spec universe are filtered out."""
    db = _make_db(
        tmp_path,
        [
            ("TEST.SZ", "L0.demand.terminal", "Known", "1.0"),
            ("TEST.SZ", "L5.fina.legacy_old", "Known", "1.0"),  # not in spec
            ("TEST.SZ", "L0.demand.user_count", "Unknown", "1.0"),
        ],
    )
    spec = _make_spec(tmp_path, ["L0.demand.terminal", "L0.demand.user_count"])
    sqlite_known, spec_dps = _collect_sqlite_known_dps(db, "TEST.SZ", spec)
    assert sqlite_known == {"L0.demand.terminal"}
    assert spec_dps == {"L0.demand.terminal", "L0.demand.user_count"}


def test_collect_proxy_status_counts_as_known(tmp_path: Path) -> None:
    """Proxy data_status is accepted as 'effectively Known' for coverage."""
    db = _make_db(
        tmp_path,
        [
            ("TEST.SZ", "L0.demand.terminal", "Known", "1.0"),
            ("TEST.SZ", "L0.demand.user_count", "Proxy", "1.0"),
            ("TEST.SZ", "L0.demand.frequency", "Inactive", "1.0"),  # not Known/Proxy
        ],
    )
    spec = _make_spec(
        tmp_path,
        ["L0.demand.terminal", "L0.demand.user_count", "L0.demand.frequency"],
    )
    sqlite_known, _ = _collect_sqlite_known_dps(db, "TEST.SZ", spec)
    assert sqlite_known == {"L0.demand.terminal", "L0.demand.user_count"}


def test_collect_db_path_missing_returns_empty(tmp_path: Path) -> None:
    """Non-existent db path → empty sqlite set, spec still parsed."""
    spec = _make_spec(tmp_path, ["a", "b", "c"])
    sqlite_known, spec_dps = _collect_sqlite_known_dps(
        tmp_path / "does_not_exist.sqlite", "TEST.SZ", spec
    )
    assert sqlite_known == set()
    assert spec_dps == {"a", "b", "c"}


def test_collect_spec_path_missing_returns_empty_spec(tmp_path: Path) -> None:
    """Missing spec → empty spec universe, fallback caller responsibility."""
    db = _make_db(tmp_path, [("TEST.SZ", "L0.demand.terminal", "Known", "1.0")])
    sqlite_known, spec_dps = _collect_sqlite_known_dps(db, "TEST.SZ", None)
    assert spec_dps == set()
    # When spec is empty we don't filter, so the dp_id passes through
    assert sqlite_known == {"L0.demand.terminal"}


# ---------------------------------------------------------------------------
# combined_coverage_summary — integration
# ---------------------------------------------------------------------------


def test_combined_sqlite_only_yaml_all_unknown(tmp_path: Path) -> None:
    """50 SQLite Known + 250 yaml Unknown → coverage = 50/250 = 0.20."""
    spec_dps = [f"dp_{i:03d}" for i in range(250)]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(
        tmp_path,
        [("TEST.SZ", dp, "Known", "1.0") for dp in spec_dps[:50]],
    )
    overlay = _overlay(known_dps=[], unknown_dps=spec_dps)
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    overall = report["overall"]
    assert overall["n_sqlite_known"] == 50
    assert overall["n_yaml_known"] == 0
    assert overall["n_combined_known"] == 50
    assert overall["spec_total"] == 250
    assert overall["data_coverage"] == pytest.approx(50 / 250)
    assert overall["combined_coverage_pct"] == pytest.approx(0.20)
    assert overall["sqlite_coverage_pct"] == pytest.approx(0.20)
    assert overall["llm_yaml_coverage_pct"] == pytest.approx(0.0)


def test_combined_yaml_only_sqlite_empty(tmp_path: Path) -> None:
    """SQLite empty, yaml 25 Known → coverage = 25/250 = 0.10."""
    spec_dps = [f"dp_{i:03d}" for i in range(250)]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(tmp_path, [])
    overlay = _overlay(known_dps=spec_dps[:25], unknown_dps=spec_dps[25:])
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    overall = report["overall"]
    assert overall["n_sqlite_known"] == 0
    assert overall["n_yaml_known"] == 25
    assert overall["n_combined_known"] == 25
    assert overall["data_coverage"] == pytest.approx(25 / 250)


def test_combined_disjoint_sqlite_and_yaml(tmp_path: Path) -> None:
    """SQLite 50 + yaml 25 (no overlap) → 75/250 = 0.30."""
    spec_dps = [f"dp_{i:03d}" for i in range(250)]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(
        tmp_path,
        [("TEST.SZ", dp, "Known", "1.0") for dp in spec_dps[:50]],
    )
    overlay = _overlay(
        known_dps=spec_dps[50:75],
        unknown_dps=spec_dps[75:],
    )
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    overall = report["overall"]
    assert overall["n_sqlite_known"] == 50
    assert overall["n_yaml_known"] == 25
    assert overall["n_combined_known"] == 75
    assert overall["data_coverage"] == pytest.approx(75 / 250)
    assert overall["warning_level"] == "low_confidence"  # 0.30 < 0.50, >= 0.30


def test_combined_overlapping_sqlite_and_yaml_deduped(tmp_path: Path) -> None:
    """SQLite 50 + yaml 25 with 10 overlap → 65/250, NOT 75/250."""
    spec_dps = [f"dp_{i:03d}" for i in range(250)]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(
        tmp_path,
        [("TEST.SZ", dp, "Known", "1.0") for dp in spec_dps[:50]],
    )
    # yaml Known covers dp_040..dp_064 → overlap dp_040..dp_049 (10 items)
    overlay = _overlay(
        known_dps=spec_dps[40:65],
        unknown_dps=spec_dps[65:],
    )
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    overall = report["overall"]
    assert overall["n_sqlite_known"] == 50
    assert overall["n_yaml_known"] == 25
    assert overall["n_combined_known"] == 65  # union, deduped
    assert overall["data_coverage"] == pytest.approx(65 / 250)


def test_combined_db_path_none_falls_back_to_yaml_only(tmp_path: Path) -> None:
    """db_path=None → coverage uses only yaml-known dp_ids in spec."""
    spec_dps = [f"dp_{i:03d}" for i in range(250)]
    spec = _make_spec(tmp_path, spec_dps)
    overlay = _overlay(known_dps=spec_dps[:30], unknown_dps=spec_dps[30:])
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=None, spec_path=spec,
    )
    overall = report["overall"]
    assert overall["n_sqlite_known"] == 0
    assert overall["n_yaml_known"] == 30
    assert overall["n_combined_known"] == 30
    assert overall["data_coverage"] == pytest.approx(30 / 250)


def test_combined_spec_path_none_keeps_yaml_only_headline(tmp_path: Path) -> None:
    """spec_path=None → preserve original yaml-only data_coverage."""
    db = _make_db(
        tmp_path,
        [("TEST.SZ", "L0.demand.terminal", "Known", "1.0")],
    )
    # 1 known + 1 unknown → yaml-only coverage = 0.5
    overlay = _overlay(known_dps=["dp_a"], unknown_dps=["dp_b"])
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=None,
    )
    overall = report["overall"]
    # Spec missing → spec_total=0, headline stays yaml-only (0.5)
    assert overall["spec_total"] == 0
    assert overall["data_coverage"] == pytest.approx(0.5)
    # SQLite layer still ran but no spec filter so sqlite_known=1
    assert overall["n_sqlite_known"] == 1
    assert overall["n_yaml_known"] == 0


def test_combined_legacy_dp_ids_excluded_from_numerator(tmp_path: Path) -> None:
    """SQLite legacy ids (L5.fina.*) must NOT inflate combined_known."""
    spec_dps = ["L0.demand.terminal", "L0.demand.user_count"]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(
        tmp_path,
        [
            ("TEST.SZ", "L0.demand.terminal", "Known", "1.0"),     # in spec
            ("TEST.SZ", "L5.fina.eps", "Known", "1.0"),           # legacy
            ("TEST.SZ", "L5.fina.roe", "Known", "1.0"),           # legacy
        ],
    )
    overlay = _overlay(known_dps=[], unknown_dps=spec_dps)
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    overall = report["overall"]
    # Only 1 of 2 spec dp_ids has SQLite Known data — legacy 2 ignored.
    assert overall["n_sqlite_known"] == 1
    assert overall["n_combined_known"] == 1
    assert overall["spec_total"] == 2
    assert overall["data_coverage"] == pytest.approx(0.5)


def test_combined_preserves_yaml_only_per_node_fields(tmp_path: Path) -> None:
    """per_node and alerts must remain unchanged (back-compat)."""
    spec_dps = [f"dp_{i:03d}" for i in range(10)]
    spec = _make_spec(tmp_path, spec_dps)
    db = _make_db(
        tmp_path,
        [("TEST.SZ", spec_dps[0], "Known", "1.0")],
    )
    overlay = _overlay(known_dps=[], unknown_dps=spec_dps)
    report = combined_coverage_summary(
        overlay, ts_code="TEST.SZ", db_path=db, spec_path=spec,
    )
    # per_node should still exist and reflect yaml-only counts
    assert "per_node" in report
    assert len(report["per_node"]) >= 1
    # The yaml-only headline is preserved in a separate field
    overall = report["overall"]
    assert "yaml_only_data_coverage" in overall
    # yaml-only: 0 known / 10 unknown = 0.0
    assert overall["yaml_only_data_coverage"] == pytest.approx(0.0)
    # But the new headline reflects SQLite contribution
    assert overall["data_coverage"] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Backend integration smoke (uses real repo runtime DB)
# ---------------------------------------------------------------------------


def test_backend_handler_includes_sqlite_layer(tmp_path: Path) -> None:
    """Smoke test: handle_coverage for 000063.SZ via the real config + DB
    should return overall_data_coverage > 0 once SQLite hard data is mixed in,
    even though the overlay yaml is currently all Unknown.

    Skips if the repo runtime DB or overlay file is missing (fresh checkout).
    """
    db_path = ROOT / "runtime" / "hot.sqlite"
    overlay_path = ROOT / "config" / "stock_overlays" / "AI_COMPUTE" / "000063.SZ.yaml"
    if not db_path.exists() or not overlay_path.exists() or not SPEC_PATH.exists():
        pytest.skip("repo runtime not provisioned — skipping integration smoke")

    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    report = combined_coverage_summary(
        overlay,
        ts_code="000063.SZ",
        db_path=db_path,
        spec_path=SPEC_PATH,
    )
    overall = report["overall"]
    assert overall["spec_total"] == 250
    assert overall["n_sqlite_known"] > 0, (
        "expected at least some SQLite Known dp_ids for 000063.SZ; "
        f"got {overall['n_sqlite_known']}"
    )
    assert overall["data_coverage"] > 0.0, (
        "headline should reflect SQLite hard data, not just yaml. "
        f"overall={overall}"
    )
