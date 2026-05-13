"""Tests for ``mvp20.sources.akshare_source.fetch_cls_telegraph_batch``.

Covers the three MARKET:CN-keyed CLS telegraph buckets:
  * ``L9.media.report``           — all headlines in 24h window
  * ``L9.industry.policy_change`` — policy-keyword filtered subset
  * ``L9.industry.compete_risk``  — risk-keyword filtered subset

Network calls are stubbed via monkeypatch on the ``akshare`` module's
``stock_info_global_cls`` symbol so the suite stays hermetic.
"""

from __future__ import annotations

import json
import time

import pytest

from mvp20.sources import akshare_source


# ---------------------------------------------------------------------------
# Fixtures: build a fake DataFrame that mimics akshare's CLS payload
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cls_cache() -> None:
    """Clear the module-level TTL cache between tests."""

    akshare_source._LAST_CLS_FETCH["ts"] = 0
    akshare_source._LAST_CLS_FETCH["rows"] = []
    yield
    akshare_source._LAST_CLS_FETCH["ts"] = 0
    akshare_source._LAST_CLS_FETCH["rows"] = []


def _make_cls_frame():
    """5 telegraph rows: 1 policy, 1 risk, 3 unrelated. All within the 24h
    window relative to the test's ``now``. We build a stub object exposing
    the same surface (``len``, ``to_dict``) as a pandas DataFrame so the
    test doesn't need to depend on pandas behaviour."""

    from datetime import datetime, timedelta

    base = datetime.now() - timedelta(hours=1)
    rows = [
        {
            "标题": "央行发布货币政策执行报告 强调灵活精准",
            "内容": "央行今日发布2026年一季度政策报告，提出新的补贴框架。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": base.strftime("%H:%M:%S"),
        },
        {
            "标题": "某上市公司因财务造假被立案调查",
            "内容": "证监会今日对XX公司启动诉讼调查，可能面临处罚。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": (base + timedelta(minutes=1)).strftime("%H:%M:%S"),
        },
        {
            "标题": "A股早盘震荡 沪指微涨",
            "内容": "沪指开盘报3200点，盘中震荡上行。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": (base + timedelta(minutes=2)).strftime("%H:%M:%S"),
        },
        {
            "标题": "国内夜盘期货收盘",
            "内容": "原油、黄金、铜等品种夜盘收盘。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": (base + timedelta(minutes=3)).strftime("%H:%M:%S"),
        },
        {
            "标题": "港股IPO：某公司递表港交所",
            "内容": "公司今日向港交所递交招股说明书。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": (base + timedelta(minutes=4)).strftime("%H:%M:%S"),
        },
    ]

    class _StubDF:
        def __init__(self, records):
            self._records = records

        def __len__(self):
            return len(self._records)

        def to_dict(self, orient="records"):
            return list(self._records)

    return _StubDF(rows)


# ---------------------------------------------------------------------------
# Happy path — all 3 dp_ids emitted with correct keyword filtering
# ---------------------------------------------------------------------------


def test_emits_three_dp_ids_with_market_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    monkeypatch.setattr(ak, "stock_info_global_cls", _make_cls_frame)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)

    assert len(rows) == 3, "must emit exactly 3 rows for the 3 dp_ids"
    dp_ids = {r[1] for r in rows}
    assert dp_ids == {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
    }
    # Sentinel ts_code on every row.
    for r in rows:
        assert r[0] == "MARKET:CN"
        assert len(r) == 7
        # JSON payload must parse.
        json.loads(r[2])
        assert r[5] == "akshare:stock_info_global_cls"


def test_keyword_filter_buckets_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Policy bucket hits the 政策/补贴 row; risk bucket hits the 诉讼/调查 row;
    report bucket contains all 5 within the 24h window."""

    import akshare as ak

    monkeypatch.setattr(ak, "stock_info_global_cls", _make_cls_frame)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    by_dp = {r[1]: json.loads(r[2]) for r in rows}

    # L9.media.report — all 5 headlines flow through.
    assert by_dp["L9.media.report"]["count_24h"] == 5
    assert len(by_dp["L9.media.report"]["top_headlines"]) == 5

    # L9.industry.policy_change — exactly 1 hit (政策/补贴 keywords).
    assert by_dp["L9.industry.policy_change"]["count_24h"] == 1
    policy_title = by_dp["L9.industry.policy_change"]["top_headlines"][0]["title"]
    assert "政策" in policy_title or "补贴" in policy_title

    # L9.industry.compete_risk — exactly 1 hit (诉讼/调查/造假 keywords).
    assert by_dp["L9.industry.compete_risk"]["count_24h"] == 1
    risk_title = by_dp["L9.industry.compete_risk"]["top_headlines"][0]["title"]
    assert any(kw in risk_title for kw in ("诉讼", "调查", "造假"))


def test_status_known_when_bucket_has_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    monkeypatch.setattr(ak, "stock_info_global_cls", _make_cls_frame)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    statuses = {r[1]: r[3] for r in rows}
    # All 3 buckets have at least one hit → Known.
    assert statuses == {
        "L9.media.report": "Known",
        "L9.industry.policy_change": "Known",
        "L9.industry.compete_risk": "Known",
    }


def test_status_inactive_when_bucket_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a bucket has 0 keyword matches, that dp_id is Inactive."""

    from datetime import datetime

    import akshare as ak

    base = datetime.now()

    class _NoKeywordDF:
        def __len__(self):
            return 1

        def to_dict(self, orient="records"):
            return [{
                "标题": "纯财经播报：股市开盘",
                "内容": "今日大盘平稳",
                "发布日期": base.strftime("%Y-%m-%d"),
                "发布时间": base.strftime("%H:%M:%S"),
            }]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _NoKeywordDF())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    statuses = {r[1]: r[3] for r in rows}
    # L9.media.report still has the headline → Known.
    assert statuses["L9.media.report"] == "Known"
    # Policy / risk filters miss → Inactive.
    assert statuses["L9.industry.policy_change"] == "Inactive"
    assert statuses["L9.industry.compete_risk"] == "Inactive"


# ---------------------------------------------------------------------------
# Payload shape constraints
# ---------------------------------------------------------------------------


def test_top_headlines_cap_at_10(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if 20 headlines flow in, top_headlines is capped to 10."""

    from datetime import datetime, timedelta

    import akshare as ak

    base = datetime.now() - timedelta(hours=1)
    records = [
        {
            "标题": f"研报-{i}",  # benign keyword
            "内容": f"内容 {i}",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": (base + timedelta(minutes=i)).strftime("%H:%M:%S"),
        }
        for i in range(20)
    ]

    class _BigDF:
        def __len__(self):
            return len(records)

        def to_dict(self, orient="records"):
            return list(records)

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _BigDF())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    report_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.media.report"),
    )
    assert report_payload["count_24h"] == 20
    assert len(report_payload["top_headlines"]) == 10


def test_title_trimmed_to_200_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    import akshare as ak

    base = datetime.now()
    long_title = "政策" + ("X" * 500)

    class _LongDF:
        def __len__(self):
            return 1

        def to_dict(self, orient="records"):
            return [{
                "标题": long_title,
                "内容": "",
                "发布日期": base.strftime("%Y-%m-%d"),
                "发布时间": base.strftime("%H:%M:%S"),
            }]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _LongDF())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    report_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.media.report"),
    )
    assert len(report_payload["top_headlines"][0]["title"]) == 200


def test_filters_out_headlines_older_than_24h(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta

    import akshare as ak

    stale = datetime.now() - timedelta(hours=48)
    fresh = datetime.now() - timedelta(hours=1)

    class _MixedDF:
        def __len__(self):
            return 2

        def to_dict(self, orient="records"):
            return [
                {
                    "标题": "陈年政策旧闻",
                    "内容": "",
                    "发布日期": stale.strftime("%Y-%m-%d"),
                    "发布时间": stale.strftime("%H:%M:%S"),
                },
                {
                    "标题": "新政策出台",
                    "内容": "",
                    "发布日期": fresh.strftime("%Y-%m-%d"),
                    "发布时间": fresh.strftime("%H:%M:%S"),
                },
            ]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _MixedDF())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    report_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.media.report"),
    )
    # Only the fresh headline survives.
    assert report_payload["count_24h"] == 1
    assert report_payload["top_headlines"][0]["title"] == "新政策出台"


# ---------------------------------------------------------------------------
# Failure-tolerance — Inactive triplet emitted when upstream fails
# ---------------------------------------------------------------------------


def test_inactive_triplet_on_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint 502 / RuntimeError → emit 3 Inactive rows, never crash."""

    import akshare as ak

    def _explode():
        raise RuntimeError("simulated CLS 502")

    monkeypatch.setattr(ak, "stock_info_global_cls", _explode)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)

    assert len(rows) == 3
    assert {r[3] for r in rows} == {"Inactive"}
    assert {r[0] for r in rows} == {"MARKET:CN"}
    assert {r[1] for r in rows} == {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
    }
    # Reason embedded in payload for diagnostics.
    for r in rows:
        payload = json.loads(r[2])
        assert "reason" in payload
        assert "simulated CLS 502" in payload["reason"]


def test_inactive_triplet_on_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty DataFrame → Inactive triplet, not crash."""

    import akshare as ak

    class _Empty:
        def __len__(self):
            return 0

        def to_dict(self, orient="records"):
            return []

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _Empty())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    assert len(rows) == 3
    assert {r[3] for r in rows} == {"Inactive"}


def test_inactive_triplet_when_symbol_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older akshare versions without the symbol → graceful Inactive."""

    import akshare as ak

    monkeypatch.delattr(ak, "stock_info_global_cls", raising=False)
    monkeypatch.delattr(ak, "stock_telegraph_cls", raising=False)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    assert len(rows) == 3
    assert {r[3] for r in rows} == {"Inactive"}


# ---------------------------------------------------------------------------
# TTL cache — second call within window must reuse the cached rows
# ---------------------------------------------------------------------------


def test_ttl_cache_hits_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call within ``_CLS_CACHE_TTL_S`` must not hit upstream."""

    import akshare as ak

    call_count = {"n": 0}

    def _counting_fetch():
        call_count["n"] += 1
        return _make_cls_frame()

    monkeypatch.setattr(ak, "stock_info_global_cls", _counting_fetch)

    now = int(time.time())
    rows_1 = akshare_source.fetch_cls_telegraph_batch(now)
    # Second call just 30s later — well within 600s TTL.
    rows_2 = akshare_source.fetch_cls_telegraph_batch(now + 30)

    assert call_count["n"] == 1, "upstream must be hit exactly once"
    # Cached rows replayed verbatim.
    assert rows_1 == rows_2


def test_ttl_cache_expires_after_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After ``_CLS_CACHE_TTL_S`` seconds, the upstream is hit again."""

    import akshare as ak

    call_count = {"n": 0}

    def _counting_fetch():
        call_count["n"] += 1
        return _make_cls_frame()

    monkeypatch.setattr(ak, "stock_info_global_cls", _counting_fetch)

    now = int(time.time())
    akshare_source.fetch_cls_telegraph_batch(now)
    # Jump past the TTL window.
    akshare_source.fetch_cls_telegraph_batch(
        now + akshare_source._CLS_CACHE_TTL_S + 1,
    )

    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS contract — module-level set declares the 3 new dp_ids
# ---------------------------------------------------------------------------


def test_supported_dp_ids_contains_market_level() -> None:
    expected = {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
    }
    assert expected.issubset(akshare_source.SUPPORTED_DP_IDS)
    assert expected == akshare_source.MARKET_LEVEL_DP_IDS
