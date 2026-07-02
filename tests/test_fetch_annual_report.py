"""Tests for ``scripts/fetch_annual_report.py``.

The cninfo HTTP calls are monkeypatched so the suite stays hermetic — the
point is to lock down the announcement-selection logic (pick the full annual
report, reject 摘要 / 英文 / 取消 variants) and the market mapping.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.fetch_annual_report as far  # noqa: E402


def test_find_annual_report_picks_full_rejects_summary_and_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, data, timeout=25):
        return {
            "announcements": [
                {"announcementTitle": "2025年年度报告摘要",
                 "adjunctUrl": "finalpage/2026-03-07/SUMMARY.PDF", "announcementTime": 30},
                {"announcementTitle": "2025年年度报告（英文版）",
                 "adjunctUrl": "finalpage/2026-03-07/EN.PDF", "announcementTime": 20},
                {"announcementTitle": "2025年年度报告",
                 "adjunctUrl": "finalpage/2026-03-07/FULL.PDF", "announcementTime": 10},
            ]
        }

    monkeypatch.setattr(far, "_post", fake_post)
    r = far.find_annual_report("000063", "gssz0000063", "szse", "sz", 2025)
    assert r is not None
    assert r["adjunct"] == "finalpage/2026-03-07/FULL.PDF"
    assert r["pdf_url"] == far._STATIC + "finalpage/2026-03-07/FULL.PDF"


def test_find_annual_report_handles_company_name_prefixed_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, data, timeout=25):
        return {
            "announcements": [
                {"announcementTitle": "海光信息技术股份有限公司2025年年度报告",
                 "adjunctUrl": "finalpage/2026-04-08/X.PDF", "announcementTime": 10},
            ]
        }

    monkeypatch.setattr(far, "_post", fake_post)
    r = far.find_annual_report("688041", "org", "sse", "sh", 2025)
    assert r is not None and r["adjunct"] == "finalpage/2026-04-08/X.PDF"


def test_find_annual_report_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(far, "_post", lambda *a, **k: {"announcements": []})
    assert far.find_annual_report("000063", "org", "szse", "sz", 2025) is None


def test_find_annual_report_rejects_non_pdf_adjunct(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, data, timeout=25):
        return {"announcements": [
            {"announcementTitle": "2025年年度报告",
             "adjunctUrl": "finalpage/2026-03-07/FULL.html", "announcementTime": 10},
        ]}

    monkeypatch.setattr(far, "_post", fake_post)
    assert far.find_annual_report("000063", "org", "szse", "sz", 2025) is None


def test_market_map_covers_sh_sz_bj() -> None:
    assert far._MARKET[".SZ"] == ("szse", "sz")
    assert far._MARKET[".SH"] == ("sse", "sh")
    assert ".BJ" in far._MARKET
