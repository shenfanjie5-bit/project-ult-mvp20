from __future__ import annotations

import numpy as np

from scripts import build_quant_scores as bq


def test_latest_sufficient_asof_skips_partial_latest_date() -> None:
    cal = ["20260622", "20260623", "20260624"]
    ret = np.ones((3, 5), dtype=float)
    mv = np.ones((3, 5), dtype=float)
    ret[-1, 2:] = np.nan
    mv[-1, 1:] = np.nan

    idx, stats = bq._latest_sufficient_asof(
        cal,
        ret,
        mv,
        min_count=3,
        min_ratio=0.6,
    )

    assert idx == 1
    assert stats["raw_asof"] == "20260624"
    assert stats["raw_coverage_count"] == 1
    assert stats["selected_asof"] == "20260623"
    assert stats["selected_coverage_count"] == 5
    assert stats["used_partial_fallback"] is True


def test_latest_sufficient_asof_uses_latest_when_covered() -> None:
    cal = ["20260622", "20260623", "20260624"]
    ret = np.ones((3, 5), dtype=float)
    mv = np.ones((3, 5), dtype=float)
    mv[-1, -1] = np.nan

    idx, stats = bq._latest_sufficient_asof(
        cal,
        ret,
        mv,
        min_count=3,
        min_ratio=0.6,
    )

    assert idx == 2
    assert stats["selected_asof"] == "20260624"
    assert stats["selected_coverage_count"] == 4
    assert stats["used_partial_fallback"] is False
