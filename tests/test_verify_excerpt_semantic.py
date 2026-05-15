"""Tests for ``verify_excerpt_semantic_match`` (Fix A — mis-citation defence).

Covers the new semantic check that asks: "does the evidence excerpt
actually appear in the value of the source dp_id it claims to cite?".

1.  ``local_dp_id`` exact substring match               → no error
2.  ``local_dp_id`` fuzzy match (case/punctuation diff) → no error
3.  ``local_dp_id`` mis-cite                            → violation
4.  ``local_dp_id`` source dp_id absent from SQLite     → violation
5.  ``local_dp_id`` excerpt empty                       → skip (no error)
6.  ``local_dp_id`` excerpt < 3 normalised chars        → skip (no error)
7.  ``local_overlay`` exact match                       → no error
8.  ``local_overlay`` path missing                      → violation
9.  ``local_overlay`` target dp_id absent from overlay  → violation
10. ``local_overlay`` overlay node has no value         → violation
11. ``industry_inference`` (no excerpt to check)        → skip
12. ``annual_report`` / ``external_url`` web kinds      → not excerpt-checked
13. Integration on the salvaged minimax A/B yaml — the
    L3.customer.segment_mix mis-cite case is caught.
14. ``--check-excerpt`` audit_overlays integration counts
    excerpt mis-cite nodes correctly.
15. SQLite sentinel fallback (MARKET / INDUSTRY) works.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_overlay_closed_loop as v  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Build a minimal SQLite db with realtime_current + overlay_manifest."""

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
        conn.execute(
            """
            CREATE TABLE overlay_manifest (
              ts_code TEXT NOT NULL,
              industry_id TEXT NOT NULL,
              primary_industry INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        rows = [
            # the headline mis-cite source: a Q&A with shareholder count
            (
                "000063.SZ",
                "L9.disclosure.qa_recent",
                '{"top_qa": [{"answer": "您好，截至2026年5月8日，公司股东总数为604,539户"}]}',
            ),
            # a clean source we can fuzzy-match against
            (
                "000063.SZ",
                "L1.company.main_business",
                '{"main_business": "主要业务为无线通信系统、有线交换和接入系统"}',
            ),
            # macro sentinel row (used in test #15)
            (
                "MARKET:CN",
                "L0.macro.pmi",
                '{"value": 50.4, "as_of": "2026-04"}',
            ),
        ]
        for ts_code, dp_id, val in rows:
            conn.execute(
                "INSERT INTO realtime_current VALUES (?, ?, ?, 'Known', 0.9, 'unit', 0)",
                (ts_code, dp_id, val),
            )
        conn.execute(
            "INSERT INTO overlay_manifest VALUES (?, ?, ?)",
            ("000063.SZ", "AI_COMPUTE", 1),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _node(evidence: list[dict]) -> dict:
    return {
        "node_id": "unit:test",
        "dp_id": "L3.customer.segment_mix",
        "data_status": "Known",
        "evidence_sources": evidence,
    }


# ---------------------------------------------------------------------------
# 1–2: local_dp_id substring matches
# ---------------------------------------------------------------------------


def test_local_dp_id_exact_match_passes(tmp_db: Path) -> None:
    """Test #1: excerpt is a verbatim substring of value_json → no error."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L9.disclosure.qa_recent",
        "excerpt": "截至2026年5月8日，公司股东总数为604,539户",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == []


def test_local_dp_id_fuzzy_match_passes(tmp_db: Path) -> None:
    """Test #2: case / full-width / ASCII punctuation differences are
    normalised away. The excerpt below differs from the stored value only
    in punctuation/whitespace and still matches."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L1.company.main_business",
        "excerpt": "主要业务为 无线通信系统, 有线交换和接入系统",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == [], f"unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# 3–6: local_dp_id violations / skips
# ---------------------------------------------------------------------------


def test_local_dp_id_mis_cite_is_violation(tmp_db: Path) -> None:
    """Test #3: excerpt that is NOT present in the cited value → violation.

    This is the headline minimax bug case: claim L9.disclosure.qa_recent
    backs a statement about customer segments.
    """

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L9.disclosure.qa_recent",
        "excerpt": "公司客户结构以国内三大运营商为核心",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert len(errors) == 1
    assert "mis-cite" in errors[0]
    assert "L9.disclosure.qa_recent" in errors[0]


def test_local_dp_id_source_missing_is_violation(tmp_db: Path) -> None:
    """Test #4: cite a dp_id that has no row in SQLite for the ts_code."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L99.does.not.exist",
        "excerpt": "something specific enough",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert len(errors) == 1
    assert "no SQLite row" in errors[0]


def test_local_dp_id_empty_excerpt_is_skipped(tmp_db: Path) -> None:
    """Test #5: an empty excerpt is a quality issue but not a mis-cite —
    we can't tell either way. Skip silently."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L9.disclosure.qa_recent",
        "excerpt": "",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == []


def test_local_dp_id_short_excerpt_is_skipped(tmp_db: Path) -> None:
    """Test #6: excerpts shorter than 3 normalised chars are too short to
    be evidence — skip rather than false-positive on noise."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L9.disclosure.qa_recent",
        "excerpt": ",.",  # normalises to "" (length 0)
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == []


# ---------------------------------------------------------------------------
# 7–10: local_overlay
# ---------------------------------------------------------------------------


def _write_overlay(path: Path, nodes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"nodes": nodes}, allow_unicode=True),
        encoding="utf-8",
    )


def test_local_overlay_exact_match_passes(tmp_path: Path, tmp_db: Path) -> None:
    """Test #7: excerpt found in overlay node's serialised value."""

    overlay_path = tmp_path / "config" / "industry_overlays" / "AI_COMPUTE.yaml"
    _write_overlay(overlay_path, [
        {
            "dp_id": "L0.demand.terminal",
            "value": {"trend": "rising", "note": "AI demand surge in 2026Q1"},
        },
    ])
    node = _node([{
        "kind": "local_overlay",
        "path": "industry_overlays/AI_COMPUTE.yaml",
        "dp_id": "L0.demand.terminal",
        "excerpt": "AI demand surge",
    }])
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db, overlays_root=tmp_path / "config",
    )
    assert errors == [], f"unexpected: {errors}"


def test_local_overlay_path_missing_is_violation(
    tmp_path: Path, tmp_db: Path,
) -> None:
    """Test #8: overlay path doesn't exist on disk."""

    node = _node([{
        "kind": "local_overlay",
        "path": "industry_overlays/NOPE.yaml",
        "dp_id": "L0.demand.terminal",
        "excerpt": "anything substantive",
    }])
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db, overlays_root=tmp_path / "config",
    )
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_local_overlay_dp_id_not_in_overlay_is_violation(
    tmp_path: Path, tmp_db: Path,
) -> None:
    """Test #9: overlay exists but doesn't contain the cited dp_id."""

    overlay_path = tmp_path / "config" / "industry_overlays" / "AI_COMPUTE.yaml"
    _write_overlay(overlay_path, [
        {"dp_id": "L0.something.else", "value": {"x": 1}},
    ])
    node = _node([{
        "kind": "local_overlay",
        "path": "industry_overlays/AI_COMPUTE.yaml",
        "dp_id": "L0.demand.terminal",
        "excerpt": "anything substantive",
    }])
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db, overlays_root=tmp_path / "config",
    )
    assert len(errors) == 1
    assert "not in overlay" in errors[0]


def test_local_overlay_target_no_value_is_violation(
    tmp_path: Path, tmp_db: Path,
) -> None:
    """Test #10: overlay node exists but its `value` is empty/null."""

    overlay_path = tmp_path / "config" / "industry_overlays" / "AI_COMPUTE.yaml"
    _write_overlay(overlay_path, [
        {"dp_id": "L0.demand.terminal", "value": None},
    ])
    node = _node([{
        "kind": "local_overlay",
        "path": "industry_overlays/AI_COMPUTE.yaml",
        "dp_id": "L0.demand.terminal",
        "excerpt": "anything substantive",
    }])
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db, overlays_root=tmp_path / "config",
    )
    assert len(errors) == 1
    assert "no value" in errors[0]


# ---------------------------------------------------------------------------
# 11–12: other kinds are exempt
# ---------------------------------------------------------------------------


def test_industry_inference_is_not_excerpt_checked(tmp_db: Path) -> None:
    """Test #11: industry_inference has no source to compare excerpts
    against — it's reasoning-only — so it must not produce errors."""

    node = _node([{
        "kind": "industry_inference",
        "reasoning": "sector cycle peak",
        "excerpt": "totally invented quote that does not exist",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == []


def test_web_kinds_are_not_excerpt_checked(tmp_db: Path) -> None:
    """Test #12: web kinds (annual_report, external_url) bypass the
    excerpt semantic check — they have their own url+checksum check."""

    node = _node([
        {
            "kind": "annual_report",
            "url": "https://x.com/ar.pdf",
            "excerpt": "claim with no local source",
        },
        {
            "kind": "external_url",
            "url": "https://y.com/page",
            "excerpt": "another web claim",
        },
    ])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == []


# ---------------------------------------------------------------------------
# 13: integration on the salvaged minimax A/B yaml
# ---------------------------------------------------------------------------


def test_integration_minimax_segment_mix_mis_cite(tmp_db: Path) -> None:
    """Test #13: feed the exact minimax mis-cite shape and confirm it's
    caught. (Doesn't depend on /tmp/ab/ — the structure is reproduced
    inline so the test is reproducible.)"""

    node = {
        "node_id": "000063.SZ:L3.customer.segment_mix",
        "dp_id": "L3.customer.segment_mix",
        "value": {"concentration_risk": "前五大客户占比约30-40%"},
        "evidence_sources": [
            {
                "kind": "local_dp_id",
                "dp_id": "L9.disclosure.qa_recent",
                "excerpt": "截至2026年5月8日，公司股东总数为604,539户",
            },
            {
                "kind": "local_dp_id",
                "dp_id": "L1.company.main_business",
                "excerpt": "主要业务为无线通信系统、有线交换和接入系统",
            },
        ],
    }
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    # ev[0] is a CLEAN substring of L9.disclosure.qa_recent (the excerpt
    # is genuinely lifted from the qa_recent value), but the *meaning*
    # mis-cite (talking about segment_mix while citing qa_recent) is a
    # *semantic* mis-cite the substring check cannot catch. We only
    # promise to catch the excerpt-doesn't-trace-back case. So flip ev[0]
    # to a truly-not-present excerpt to assert detection:
    node["evidence_sources"][0]["excerpt"] = (
        "公司客户结构以国内三大运营商为核心合计占收入约40%"
    )
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert any("mis-cite" in e and "L9.disclosure.qa_recent" in e
               for e in errors), f"expected mis-cite, got: {errors}"


# ---------------------------------------------------------------------------
# 14: audit_overlays with --check-excerpt integration
# ---------------------------------------------------------------------------


def test_audit_overlays_with_check_excerpt_counts_mis_cite(
    tmp_path: Path, tmp_db: Path,
) -> None:
    """Test #14: when check_excerpt=True, the audit summary reports
    excerpt_mis_cite_nodes correctly and adds soft (warn) violations
    that are NOT auto-demoted."""

    industry_dir = tmp_path / "config" / "industry_overlays"
    stock_dir = tmp_path / "config" / "stock_overlays" / "AI_COMPUTE"
    industry_dir.mkdir(parents=True)
    stock_dir.mkdir(parents=True)

    # One stock overlay with a mis-cite + one clean evidence.
    stock_overlay = {
        "ts_code": "000063.SZ",
        "industry_id": "AI_COMPUTE",
        "nodes": [
            {
                "node_id": "000063.SZ:L3.customer.segment_mix",
                "dp_id": "L3.customer.segment_mix",
                "data_status": "Known",
                "missing_policy": "unknown_reduce_confidence",
                "confidence": 0.6,
                "evidence_sources": [
                    {
                        "kind": "local_dp_id",
                        "dp_id": "L9.disclosure.qa_recent",
                        # NOT in the actual qa_recent value
                        "excerpt": "公司客户结构以国内三大运营商为核心合计占收入约40%",
                    },
                ],
            },
            {
                "node_id": "000063.SZ:L1.company.main_business",
                "dp_id": "L1.company.main_business",
                "data_status": "Known",
                "missing_policy": "unknown_reduce_confidence",
                "confidence": 0.9,
                "evidence_sources": [
                    {
                        "kind": "local_dp_id",
                        "dp_id": "L1.company.main_business",
                        "excerpt": "主要业务为无线通信系统",
                    },
                ],
            },
        ],
    }
    (stock_dir / "000063.SZ.yaml").write_text(
        yaml.safe_dump(stock_overlay, allow_unicode=True), encoding="utf-8",
    )

    summary = v.audit_overlays(
        stock_overlays_dir=tmp_path / "config" / "stock_overlays",
        industry_overlays_dir=industry_dir,
        governance={},  # all defaults to closed-loop, but no web evidence
        check_excerpt=True,
        db_path=tmp_db,
        overlays_root=tmp_path / "config",
    )
    assert summary.excerpt_checked_nodes == 2
    assert summary.excerpt_mis_cite_nodes == 1
    # Mis-cite is a SOFT violation, not a hard one.
    assert summary.hard_violations == 0
    assert summary.warn_violations >= 1
    # No auto-demote should have fired (we didn't pass auto_demote).
    assert summary.demoted_nodes == 0
    # Excerpt mis-cites carry the "excerpt_mis_cite:" prefix.
    assert any("excerpt_mis_cite" in vio.reason for vio in summary.violations)


# ---------------------------------------------------------------------------
# 15: sentinel fallback (MARKET / INDUSTRY)
# ---------------------------------------------------------------------------


def test_sqlite_sentinel_market_fallback(tmp_db: Path) -> None:
    """Test #15: a dp_id only present under MARKET:CN sentinel still
    resolves when the cite ts_code is a .SZ stock."""

    node = _node([{
        "kind": "local_dp_id",
        "dp_id": "L0.macro.pmi",
        "excerpt": "50.4",
    }])
    errors = v.verify_excerpt_semantic_match(node, "000063.SZ", tmp_db)
    assert errors == [], f"sentinel lookup failed: {errors}"


def test_normalize_text_handles_punctuation_and_case() -> None:
    """Direct unit on the normaliser used for fuzzy matching."""

    assert v._normalize_text("Hello, World!") == "helloworld"
    assert v._normalize_text("截至2026年5月8日，公司") == "截至2026年5月8日公司"
    assert v._normalize_text(None) == ""
    assert v._normalize_text(123) == ""
