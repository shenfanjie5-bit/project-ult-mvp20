"""Tests for the X5 text-disclosure fetchers in ``mvp20.sources.tushare_source``.

All Tushare HTTP calls are stubbed via monkeypatch so the suite stays
hermetic. The point is to lock down:

  * ``SUPPORTED_DP_IDS`` covers the three X5 disclosure dp_ids
    (``L9.disclosure.qa_recent``, ``L1.company.main_business``,
    ``L8.gov.management_table``).
  * Sentinel ts_codes are NOT used here — these are per A-share emits.
  * Per-stock cache (10-min TTL) short-circuits a second call inside the
    window.
  * Truncation: question/answer clipped to 300 chars; main_business clipped
    to 500.
  * Missing rows emit ``data_status="Inactive"`` rather than dropping
    silently — the codex prompt template relies on every per-stock dp_id
    having *some* row, even if just to signal "no data available".
  * Permission errors short-circuit after 3 consecutive failures without
    poisoning the rest of the batch.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mvp20.sources import tushare_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubDF:
    """Quacks like a tiny pandas.DataFrame for the calls our code makes."""

    def __init__(self, records: list[dict[str, Any]]):
        self._rows = list(records)

    def __len__(self) -> int:
        return len(self._rows)

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return list(self._rows)


class _StubPro:
    """Captures call counts so the cache test can verify replays."""

    def __init__(self, **endpoint_data):
        self._data = endpoint_data
        self.call_counts: dict[str, int] = {k: 0 for k in endpoint_data}

    def _dispatch(self, name: str, **kwargs):
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        v = self._data.get(name)
        if isinstance(v, Exception):
            raise v
        if callable(v):
            return v(**kwargs)
        return v

    def irm_qa_sh(self, **kw):       return self._dispatch("irm_qa_sh", **kw)
    def irm_qa_sz(self, **kw):       return self._dispatch("irm_qa_sz", **kw)
    def stock_company(self, **kw):   return self._dispatch("stock_company", **kw)
    def stk_managers(self, **kw):    return self._dispatch("stk_managers", **kw)


@pytest.fixture(autouse=True)
def _clear_disclosure_caches() -> None:
    """Reset module-level caches between tests so they stay independent."""

    tushare_source._IRM_QA_CACHE.clear()
    tushare_source._STOCK_COMPANY_CACHE.clear()
    tushare_source._STK_MANAGERS_CACHE.clear()
    yield
    tushare_source._IRM_QA_CACHE.clear()
    tushare_source._STOCK_COMPANY_CACHE.clear()
    tushare_source._STK_MANAGERS_CACHE.clear()


# ---------------------------------------------------------------------------
# 1. SUPPORTED_DP_IDS contract
# ---------------------------------------------------------------------------


def test_supported_dp_ids_includes_x5_disclosure_set() -> None:
    expected = {
        "L9.disclosure.qa_recent",
        "L1.company.main_business",
        "L8.gov.management_table",
    }
    assert expected.issubset(tushare_source.SUPPORTED_DP_IDS)


# ---------------------------------------------------------------------------
# 2. irm_qa — picks SH/SZ variant by ts_code suffix, truncates, sorts latest
# ---------------------------------------------------------------------------


def test_irm_qa_sh_emits_known_with_top10_truncated() -> None:
    long_question = "请问" + "a" * 500
    pro = _StubPro(irm_qa_sh=_StubDF([
        {"q": long_question, "a": "long answer " + "b" * 400,
         "trade_date": "20260420"},
        {"q": "Q2 update", "a": "good guidance",
         "trade_date": "20260101"},
    ]))
    rows = tushare_source._fetch_a_share_irm_qa(
        pro, ["600519.SH"], now=1700000000,
    )
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, ts = rows[0]
    assert ts_code == "600519.SH"
    assert dp_id == "L9.disclosure.qa_recent"
    assert status == "Known"
    assert source == "tushare:irm_qa_sh"
    payload = json.loads(value_json)
    assert payload["count_recent"] == 2
    # Latest first (20260420 > 20260101)
    assert payload["top_qa"][0]["date"] == "20260420"
    # Truncated to 300 chars max
    assert len(payload["top_qa"][0]["question"]) <= 300
    assert len(payload["top_qa"][0]["answer"]) <= 300
    assert payload["latest_date"] == "20260420"


def test_irm_qa_sz_routes_to_sz_endpoint_for_sz_ts_code() -> None:
    pro = _StubPro(irm_qa_sz=_StubDF([
        {"q": "Q?", "a": "A", "ann_date": "20260301"},
    ]))
    rows = tushare_source._fetch_a_share_irm_qa(
        pro, ["300750.SZ"], now=1700000000,
    )
    assert pro.call_counts.get("irm_qa_sz", 0) == 1
    assert pro.call_counts.get("irm_qa_sh", 0) == 0
    assert rows[0][5] == "tushare:irm_qa_sz"


def test_irm_qa_empty_returns_inactive_row() -> None:
    pro = _StubPro(irm_qa_sh=_StubDF([]))
    rows = tushare_source._fetch_a_share_irm_qa(
        pro, ["600000.SH"], now=1700000000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"
    payload = json.loads(rows[0][2])
    assert payload["count_recent"] == 0
    assert payload["top_qa"] == []


def test_irm_qa_cache_short_circuits_within_ttl() -> None:
    pro = _StubPro(irm_qa_sh=_StubDF([
        {"q": "Q1", "a": "A1", "trade_date": "20260420"},
    ]))
    rows_1 = tushare_source._fetch_a_share_irm_qa(
        pro, ["600519.SH"], now=1700000000,
    )
    rows_2 = tushare_source._fetch_a_share_irm_qa(
        pro, ["600519.SH"], now=1700000060,  # 1 min later — within 10-min TTL
    )
    assert pro.call_counts["irm_qa_sh"] == 1
    assert len(rows_1) == len(rows_2) == 1


def test_irm_qa_permission_error_after_threshold_emits_inactive() -> None:
    pro = _StubPro(irm_qa_sh=RuntimeError("您的积分不足"))
    # After 3 permission errors we must keep emitting Inactive rows for
    # subsequent ts_codes without re-attempting the API call. We pass 5
    # codes and expect at most 3 real API attempts.
    rows = tushare_source._fetch_a_share_irm_qa(
        pro, [f"60000{i}.SH" for i in range(5)], now=1700000000,
    )
    # 3 first attempts each raise → no row appended pre-threshold; the 4th
    # and 5th hit the short-circuit and emit Inactive rows.
    assert pro.call_counts["irm_qa_sh"] <= 3
    inactives = [r for r in rows if r[3] == "Inactive"]
    assert len(inactives) >= 1


# ---------------------------------------------------------------------------
# 3. stock_company → L1.company.main_business
# ---------------------------------------------------------------------------


def test_stock_company_emits_known_with_truncated_main_business() -> None:
    long_main = "主要从事" + "x" * 800
    pro = _StubPro(stock_company=_StubDF([
        {"ts_code": "300750.SZ",
         "chairman": "曾毓群",
         "manager": "总裁",
         "main_business": long_main,
         "business_scope": "动力电池研发、生产和销售",
         "introduction": "全球领先的动力电池制造商"},
    ]))
    rows = tushare_source._fetch_a_share_stock_company(
        pro, ["300750.SZ"], now=1700000000,
    )
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, ts = rows[0]
    assert dp_id == "L1.company.main_business"
    assert status == "Known"
    assert source == "tushare:stock_company"
    payload = json.loads(value_json)
    assert len(payload["main_business"]) <= 500
    assert payload["business_scope"] == "动力电池研发、生产和销售"
    assert payload["chairman"] == "曾毓群"


def test_stock_company_empty_emits_inactive() -> None:
    pro = _StubPro(stock_company=_StubDF([]))
    rows = tushare_source._fetch_a_share_stock_company(
        pro, ["000001.SZ"], now=1700000000,
    )
    assert len(rows) == 1
    assert rows[0][3] == "Inactive"


def test_stock_company_all_text_none_emits_inactive() -> None:
    pro = _StubPro(stock_company=_StubDF([
        {"ts_code": "000002.SZ",
         "chairman": "X",
         "manager": "Y",
         "main_business": None,
         "business_scope": None,
         "introduction": None},
    ]))
    rows = tushare_source._fetch_a_share_stock_company(
        pro, ["000002.SZ"], now=1700000000,
    )
    assert rows[0][3] == "Inactive"


def test_stock_company_cache_short_circuits() -> None:
    pro = _StubPro(stock_company=_StubDF([
        {"ts_code": "600519.SH", "chairman": "丁雄军",
         "manager": "李静仁", "main_business": "白酒",
         "business_scope": "酒类生产销售", "introduction": "中国白酒龙头"},
    ]))
    tushare_source._fetch_a_share_stock_company(
        pro, ["600519.SH"], now=1700000000,
    )
    tushare_source._fetch_a_share_stock_company(
        pro, ["600519.SH"], now=1700000300,
    )
    assert pro.call_counts["stock_company"] == 1


# ---------------------------------------------------------------------------
# 4. stk_managers table → L8.gov.management_table
# ---------------------------------------------------------------------------


def test_stk_managers_table_emits_top10_with_change_count() -> None:
    today = tushare_source._today_yyyymmdd()
    # 3 records: 2 in the last year, 1 a long time ago.
    pro = _StubPro(stk_managers=_StubDF([
        {"name": "张三", "title": "董事长", "gender": "M", "edu": "博士",
         "ann_date": today, "take_office_date": today,
         "begin_date": today, "end_date": None},
        {"name": "李四", "title": "总裁", "gender": "M", "edu": "硕士",
         "ann_date": today, "take_office_date": today,
         "begin_date": today, "end_date": None},
        {"name": "王五", "title": "独立董事", "gender": "F", "edu": "本科",
         "ann_date": "20100101", "take_office_date": "20100101",
         "begin_date": "20100101", "end_date": None},
    ]))
    rows = tushare_source._fetch_a_share_stk_managers_table(
        pro, ["000063.SZ"], now=1700000000,
    )
    assert len(rows) == 1
    ts_code, dp_id, value_json, status, conf, source, ts = rows[0]
    assert dp_id == "L8.gov.management_table"
    assert status == "Known"
    assert source == "tushare:stk_managers"
    payload = json.loads(value_json)
    assert len(payload["managers"]) == 3
    assert payload["change_count_recent_year"] == 2
    assert payload["lookback_days"] == 365
    # Most-recent first
    assert payload["managers"][0]["name"] in ("张三", "李四")


def test_stk_managers_table_empty_emits_inactive() -> None:
    pro = _StubPro(stk_managers=_StubDF([]))
    rows = tushare_source._fetch_a_share_stk_managers_table(
        pro, ["000001.SZ"], now=1700000000,
    )
    assert rows[0][3] == "Inactive"
    payload = json.loads(rows[0][2])
    assert payload["managers"] == []
    assert payload["change_count_recent_year"] == 0


def test_stk_managers_table_cache_short_circuits() -> None:
    today = tushare_source._today_yyyymmdd()
    pro = _StubPro(stk_managers=_StubDF([
        {"name": "X", "title": "T", "gender": "M", "edu": "B",
         "ann_date": today, "take_office_date": today},
    ]))
    tushare_source._fetch_a_share_stk_managers_table(
        pro, ["300750.SZ"], now=1700000000,
    )
    tushare_source._fetch_a_share_stk_managers_table(
        pro, ["300750.SZ"], now=1700000060,
    )
    assert pro.call_counts["stk_managers"] == 1


# ---------------------------------------------------------------------------
# 5. fetch_disclosure_batch — aggregator stays isolated on per-endpoint fail
# ---------------------------------------------------------------------------


def test_fetch_disclosure_batch_aggregates_three_endpoints() -> None:
    today = tushare_source._today_yyyymmdd()
    pro = _StubPro(
        irm_qa_sh=_StubDF([
            {"q": "Q1", "a": "A1", "trade_date": "20260420"},
        ]),
        stock_company=_StubDF([
            {"ts_code": "600519.SH", "chairman": "X", "manager": "Y",
             "main_business": "白酒", "business_scope": "酒类",
             "introduction": "龙头"},
        ]),
        stk_managers=_StubDF([
            {"name": "Z", "title": "董事长", "gender": "M", "edu": "本科",
             "ann_date": today, "take_office_date": today},
        ]),
    )
    rows = tushare_source.fetch_disclosure_batch(
        pro, ["600519.SH"], now=1700000000,
    )
    by_dp = {r[1] for r in rows}
    assert by_dp == {
        "L9.disclosure.qa_recent",
        "L1.company.main_business",
        "L8.gov.management_table",
    }


def test_fetch_disclosure_batch_isolates_endpoint_failure() -> None:
    """If irm_qa_sh blows up entirely, stock_company + stk_managers still emit."""

    today = tushare_source._today_yyyymmdd()
    pro = _StubPro(
        irm_qa_sh=RuntimeError("permission denied"),
        stock_company=_StubDF([
            {"ts_code": "600519.SH", "chairman": "X", "manager": "Y",
             "main_business": "白酒", "business_scope": "酒类",
             "introduction": "龙头"},
        ]),
        stk_managers=_StubDF([
            {"name": "Z", "title": "董事长", "gender": "M", "edu": "本科",
             "ann_date": today, "take_office_date": today},
        ]),
    )
    rows = tushare_source.fetch_disclosure_batch(
        pro, ["600519.SH"], now=1700000000,
    )
    by_dp = {r[1] for r in rows}
    assert "L1.company.main_business" in by_dp
    assert "L8.gov.management_table" in by_dp
