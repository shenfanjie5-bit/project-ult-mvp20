"""Tests for ``_numeric_tolerant_match`` and helpers (Fix A2 — kill the
false-positive flood produced by Fix A on codex analysis tier).

The two helpers under test:

1. ``_extract_numbers(s)`` — regex sweep that pulls every numeric token
   from a string and canonicalises (1,234 → 1234, sci-notation parsed,
   negatives kept). Used on canonical SQLite ``value_json`` strings.

2. ``_extract_numbers_with_scale(s)`` — same regex sweep, but each
   number followed by a CN financial scale suffix (亿元, 万元, 万, 千,
   百, 万亿) also emits its scaled value. Used on excerpts so that
   "248.48541亿元" can match the raw 24848541000.0 stored in SQLite.

3. ``_numeric_tolerant_match(excerpt, actual_value)`` — accepts the
   citation iff every number in the excerpt has a near-equal counterpart
   in the actual value (after scale expansion). Returns False if either
   side has no numbers.

The integration test #8 also confirms the fallback fires from inside
``verify_excerpt_semantic_match`` for the canonical codex failure mode:
excerpt ``"34988057000元"`` vs SQLite value ``'{"scalar": 34988057000.0}'``.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_overlay_closed_loop as v  # noqa: E402


# ---------------------------------------------------------------------------
# 1. _extract_numbers — basic regex extraction
# ---------------------------------------------------------------------------


def test_extract_numbers_handles_thousands_separator_and_unit() -> None:
    """Test #1: 12,345.67 in "营收 12,345.67 亿元" → [12345.67]."""

    nums = v._extract_numbers("营收 12,345.67 亿元")
    assert nums == [12345.67]


def test_extract_numbers_handles_scientific_notation() -> None:
    """Test #2: "scalar=1.23e10" → [1.23e10]."""

    nums = v._extract_numbers("scalar=1.23e10")
    assert nums == [1.23e10]


def test_extract_numbers_finds_multiple_numbers() -> None:
    """Test #3: mixed text "32 亿元 + 4.5%" → [32, 4.5]."""

    nums = v._extract_numbers("32 亿元 + 4.5%")
    assert nums == [32.0, 4.5]


def test_extract_numbers_returns_empty_for_text_only() -> None:
    """Test #4: pure text returns [] (no numbers extracted)."""

    assert v._extract_numbers("公司主营业务") == []
    assert v._extract_numbers("") == []
    assert v._extract_numbers(None) == []


def test_extract_numbers_handles_negatives_and_floats() -> None:
    """Test #5: negative + float forms are preserved."""

    nums = v._extract_numbers("change=-16861904000.0, ratio=-1.5")
    assert -16861904000.0 in nums
    assert -1.5 in nums


# ---------------------------------------------------------------------------
# 2. _extract_numbers_with_scale — CN scale expansion
# ---------------------------------------------------------------------------


def test_extract_numbers_with_scale_expands_cn_units() -> None:
    """Test #6: "248.48541亿元" yields raw + scaled (×1e8)."""

    nums = v._extract_numbers_with_scale("2026Q1应收账款248.48541亿元")
    # The raw 248.48541 AND the scaled 2.4848541e10 should both be present.
    assert 248.48541 in nums
    assert pytest.approx(24848541000.0, rel=1e-9) in nums


def test_extract_numbers_with_scale_handles_multiple_units() -> None:
    """Test #7: mixed 万 / 亿 / % all expand correctly."""

    nums = v._extract_numbers_with_scale("收入5亿元，员工1.2万人，毛利率28%")
    assert 5.0 in nums
    assert pytest.approx(5e8) in nums
    assert 1.2 in nums
    assert pytest.approx(12000.0) in nums
    # 28 has no scale suffix so only the raw value appears.
    assert 28.0 in nums


def test_extract_numbers_with_scale_no_unit_only_raw() -> None:
    """Test #8: plain integer "1234" yields only the raw value."""

    nums = v._extract_numbers_with_scale("1234")
    assert nums == [1234.0]


# ---------------------------------------------------------------------------
# 3. _numeric_tolerant_match — happy paths
# ---------------------------------------------------------------------------


def test_numeric_tolerant_match_raw_number_in_json_wrapper() -> None:
    """Test #9 (from spec): excerpt "34988057000元" matches
    '{"scalar": 34988057000.0}'."""

    assert v._numeric_tolerant_match(
        "34988057000元",
        '{"scalar": 34988057000.0}',
    ) is True


def test_numeric_tolerant_match_percentage_in_json_wrapper() -> None:
    """Test #10 (from spec): excerpt "12.34%" matches
    '{"scalar": 12.34, "unit": "%"}'."""

    assert v._numeric_tolerant_match(
        "12.34%",
        '{"scalar": 12.34, "unit": "%"}',
    ) is True


def test_numeric_tolerant_match_yi_yuan_scaling() -> None:
    """Test #11: excerpt "248.48541亿元" matches the raw 24848541000.0
    stored in SQLite as JSON. Period label "2026" needs the actual value
    to also carry a period — realistic for SQLite rows."""

    assert v._numeric_tolerant_match(
        "2026Q1应收账款248.48541亿元",
        '{"accounts_receivable": 24848541000.0, "unit": "元", '
        '"period": "20260331"}',
    ) is True


def test_numeric_tolerant_match_wan_yuan_scaling() -> None:
    """Test #12: 万元 scale (×1e4) also matches."""

    assert v._numeric_tolerant_match(
        "净利润5万元",
        '{"net_profit": 50000.0, "unit": "元"}',
    ) is True


def test_numeric_tolerant_match_kv_style_excerpt() -> None:
    """Test #13: codex NVDA shape — "rd=18497000000 USD, rd_intensity_pct
    ≈8.57%" matches the JSON dict with rd and ratios."""

    actual = (
        '{"sga": 4579000000.0, "rd": 18497000000.0, "total": 23076000000.0, '
        '"sga_rd_ratio_revenue": 0.10686400726134353, "unit": "USD", '
        '"period": "2026-01-25"}'
    )
    excerpt = (
        "rd=18497000000 USD, sga_rd_ratio_revenue=0.10686400726134353, "
        "period=2026-01-25"
    )
    assert v._numeric_tolerant_match(excerpt, actual) is True


def test_numeric_tolerant_match_negative_number_scaling() -> None:
    """Test #14: negative scaled numbers (e.g. cash flow loss) match."""

    assert v._numeric_tolerant_match(
        "2026Q1经营现金流-19.78648亿元",
        '{"ocf": -1978648000.0, "unit": "元", "period": "20260331"}',
    ) is True


# ---------------------------------------------------------------------------
# 4. _numeric_tolerant_match — rejection paths
# ---------------------------------------------------------------------------


def test_numeric_tolerant_match_different_number_rejected() -> None:
    """Test #15 (from spec): excerpt "12.34" does NOT match
    '{"scalar": 99.99}'."""

    assert v._numeric_tolerant_match(
        "12.34",
        '{"scalar": 99.99}',
    ) is False


def test_numeric_tolerant_match_no_numbers_in_excerpt() -> None:
    """Test #16 (from spec): excerpt "abc" vs "def" — no numbers, no
    jurisdiction. Returns False so caller falls back to substring check."""

    assert v._numeric_tolerant_match("abc", "def") is False


def test_numeric_tolerant_match_excerpt_has_numbers_actual_none() -> None:
    """Test #17: excerpt has numbers but actual is text-only → False."""

    assert v._numeric_tolerant_match(
        "12.34",
        '{"main_business": "主要业务为通信系统"}',
    ) is False


def test_numeric_tolerant_match_one_number_missing_rejected() -> None:
    """Test #18: 3 numbers in excerpt, only 2 match actual → False.
    Catches partial fabrication."""

    # rd, sga match; 99.99 does NOT match anything in actual.
    excerpt = "rd=18497000000, sga=4579000000, fake_ratio=99.99"
    actual = (
        '{"rd": 18497000000.0, "sga": 4579000000.0, '
        '"sga_rd_ratio_revenue": 0.10686400726134353}'
    )
    assert v._numeric_tolerant_match(excerpt, actual) is False


def test_numeric_tolerant_match_excerpt_2026_period_label() -> None:
    """Test #19: 2026 (period label) needs to match something — the
    actual value should also include 2026 somewhere (e.g. period date).
    This documents that period labels MUST appear in both sides."""

    # period appears in both → match
    assert v._numeric_tolerant_match(
        "gross_margin=0.7106808435754708, period=2026-01-25",
        '{"scalar": 0.7106808435754708, "unit": "ratio", '
        '"period": "2026-01-25"}',
    ) is True


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------


def test_numeric_tolerant_match_within_abs_tol() -> None:
    """Test #20: integers within abs_tol=1.0 are accepted (rounding)."""

    # The two differ by 0.4, within abs_tol=1.0 → match.
    assert v._numeric_tolerant_match(
        "value=12345.0",
        '{"scalar": 12345.4}',
    ) is True


def test_numeric_tolerant_match_within_rel_tol() -> None:
    """Test #21: float relative error within rel_tol=1e-6 is accepted."""

    assert v._numeric_tolerant_match(
        "ratio=0.7106808435754708",
        '{"scalar": 0.7106808435754708001}',
    ) is True


def test_numeric_tolerant_match_outside_both_tolerances() -> None:
    """Test #22: numbers that differ by > abs_tol AND > rel_tol → rejected.
    Float-equality is tight (1e-6 rel + 1.0 abs)."""

    # Differ by 100, well outside both tolerances at this scale.
    assert v._numeric_tolerant_match(
        "value=12345.0",
        '{"scalar": 12445.0}',
    ) is False


# ---------------------------------------------------------------------------
# 6. Integration with verify_excerpt_semantic_match
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_numeric(tmp_path: Path) -> Path:
    """Minimal SQLite db carrying the canonical codex failure-mode rows."""

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
            # Raw integer in JSON wrapper — codex paraphrased: "34988057000元"
            (
                "000063.SZ",
                "L5.is.revenue",
                '{"scalar": 34988057000.0, "unit": "元", "period": "20260331"}',
            ),
            # 亿元 scaled number — codex paraphrased: "248.48541亿元"
            (
                "000063.SZ",
                "L5.bs.ar_ap",
                '{"accounts_receivable": 24848541000.0, '
                '"accounts_payable": 41710445000.0, "unit": "元", '
                '"period": "20260331"}',
            ),
        ]
        for ts_code, dp_id, val in rows:
            conn.execute(
                "INSERT INTO realtime_current VALUES (?, ?, ?, 'Known', 0.9, 'unit', 0)",
                (ts_code, dp_id, val),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_integration_codex_numeric_excerpt_passes(tmp_db_numeric: Path) -> None:
    """Test #23: full ``verify_excerpt_semantic_match`` flow accepts the
    codex-style numeric excerpt that previously triggered a false-positive
    mis-cite."""

    node = {
        "node_id": "000063.SZ:L1.position.market_share",
        "dp_id": "L1.position.market_share",
        "data_status": "Known",
        "evidence_sources": [
            {
                "kind": "local_dp_id",
                "dp_id": "L5.is.revenue",
                # codex writes 34988057000元; SQLite has 34988057000.0
                "excerpt": "2026Q1营业收入34988057000元",
            },
            {
                "kind": "local_dp_id",
                "dp_id": "L5.bs.ar_ap",
                # codex writes 亿元-scaled; SQLite has raw 元-scaled
                "excerpt": "2026Q1应收账款248.48541亿元",
            },
        ],
    }
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db_numeric,
    )
    assert errors == [], f"expected no errors, got: {errors}"


def test_integration_codex_fabricated_number_still_rejected(
    tmp_db_numeric: Path,
) -> None:
    """Test #24: numeric tolerant match must NOT mask a genuine
    fabrication. If codex writes a number that doesn't exist in SQLite,
    the mis-cite must still surface."""

    node = {
        "node_id": "000063.SZ:fake",
        "dp_id": "L1.position.market_share",
        "data_status": "Known",
        "evidence_sources": [
            {
                "kind": "local_dp_id",
                "dp_id": "L5.is.revenue",
                # 99999999999 is NOT in the actual stored value.
                "excerpt": "2026Q1营业收入99999999999元",
            },
        ],
    }
    errors = v.verify_excerpt_semantic_match(
        node, "000063.SZ", tmp_db_numeric,
    )
    assert len(errors) == 1
    assert "mis-cite" in errors[0]
    assert "numeric-tolerant both failed" in errors[0]
