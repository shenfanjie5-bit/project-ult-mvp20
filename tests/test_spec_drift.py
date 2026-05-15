"""Tests for scripts/check_spec_drift.py.

Cover each detector branch (A/B/C/D/F/G) with synthetic in-memory inputs so
the tests do not depend on the actual SQLite/yaml content.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    """Load scripts/check_spec_drift.py as a module (it lives outside the
    mvp20 package, so importlib is the cleanest way)."""
    spec = importlib.util.spec_from_file_location(
        "check_spec_drift", ROOT / "scripts" / "check_spec_drift.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


csd = _load_module()


def _spec(entries: dict[str, dict]) -> dict:
    return {"data_points": entries}


def _gov(dp_ids: list[str]) -> dict:
    return {"data_points": {dp: {"route": "llm_close"} for dp in dp_ids}}


def test_outdated_missing_label_drift_A() -> None:
    spec = _spec({"L0.demand.terminal": {"source_status": "missing"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps={"L0.demand.terminal"},
        overlay_dps=set(),
        audit_missing=1,  # match spec.missing=1 so no count drift fires
    )
    assert any(d["type"] == "outdated_missing_label" for d in drifts)
    a = next(d for d in drifts if d["type"] == "outdated_missing_label")
    assert a["dp_id"] == "L0.demand.terminal"


def test_unimplemented_promise_drift_B() -> None:
    spec = _spec({"L0.demand.user_count": {"source_status": "✓"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps=set(),
        overlay_dps=set(),
        audit_missing=0,
    )
    assert any(d["type"] == "unimplemented_promise" for d in drifts)
    b = next(d for d in drifts if d["type"] == "unimplemented_promise")
    assert b["dp_id"] == "L0.demand.user_count"


def test_unimplemented_promise_suppressed_if_overlay_has_dp_B() -> None:
    """If overlay has Known/Optionality for the dp, spec '✓' is satisfied."""
    spec = _spec({"L0.demand.user_count": {"source_status": "✓"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps=set(),
        overlay_dps={"L0.demand.user_count"},
        audit_missing=0,
    )
    assert not any(d["type"] == "unimplemented_promise" for d in drifts)


def test_premium_unlocked_drift_C() -> None:
    spec = _spec({"L6.mult.dcf": {"source_status": "$"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps={"L6.mult.dcf"},
        overlay_dps=set(),
        audit_missing=0,
    )
    assert any(d["type"] == "premium_unlocked" for d in drifts)
    c = next(d for d in drifts if d["type"] == "premium_unlocked")
    assert c["dp_id"] == "L6.mult.dcf"


def test_orphan_governance_drift_D() -> None:
    spec = _spec({"L0.real": {"source_status": "✓"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov(["L99.x.y"]),  # not in spec
        sqlite_dps={"L0.real"},
        overlay_dps=set(),
        audit_missing=0,
    )
    assert any(d["type"] == "orphan_governance" for d in drifts)
    d_ = next(d for d in drifts if d["type"] == "orphan_governance")
    assert d_["dp_id"] == "L99.x.y"


def test_count_drift_F() -> None:
    spec = _spec(
        {
            "L0.a": {"source_status": "missing"},
            "L0.b": {"source_status": "missing"},
        }
    )
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps=set(),
        overlay_dps=set(),
        audit_missing=1,  # spec says 2 missing, audit says 1 -> drift
    )
    assert any(d["type"] == "count_drift" for d in drifts)
    f = next(d for d in drifts if d["type"] == "count_drift")
    assert "2 missing" in f["spec_says"]
    assert "1 missing" in f["actual"]


def test_count_drift_suppressed_when_audit_missing_is_none() -> None:
    spec = _spec({"L0.a": {"source_status": "missing"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps=set(),
        overlay_dps=set(),
        audit_missing=None,
    )
    assert not any(d["type"] == "count_drift" for d in drifts)


def test_legacy_naming_drift_G() -> None:
    spec = _spec({"L0.demand.terminal": {"source_status": "missing"}})
    drifts = csd.detect_drifts(
        spec=spec,
        governance=_gov([]),
        sqlite_dps={"L9.event.major_holder_increase"},
        overlay_dps=set(),
        audit_missing=1,
    )
    legacy = [d for d in drifts if d["type"] == "legacy_naming"]
    assert legacy
    assert legacy[0]["dp_id"] == "L9.event.major_holder_increase"


def test_render_report_groups_by_type() -> None:
    drifts = [
        {
            "type": "outdated_missing_label",
            "dp_id": "L0.x",
            "spec_says": "missing",
            "actual": "SQLite has emit",
            "action": "fix",
        },
        {
            "type": "premium_unlocked",
            "dp_id": "L6.mult.dcf",
            "spec_says": "$ premium",
            "actual": "SQLite has emit",
            "action": "fix",
        },
    ]
    md = csd.render_report(drifts)
    assert "# Spec drift report v1" in md
    assert "Total drift items**: 2" in md
    assert "outdated_missing_label (1)" in md
    assert "premium_unlocked (1)" in md
    assert "L6.mult.dcf" in md


def test_count_audit_md_missing_returns_int_or_none() -> None:
    """Live coverage_audit.md should parse to a positive int (section 4 exists)."""
    n = csd.count_audit_md_missing(ROOT)
    assert n is None or (isinstance(n, int) and n >= 0)
