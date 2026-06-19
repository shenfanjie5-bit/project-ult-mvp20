"""Tests for ``mvp20.sources.akshare_source.fetch_cls_telegraph_batch``.

Covers the four MARKET:CN-keyed CLS telegraph buckets:
  * ``L9.media.report``           — all headlines in 24h window
  * ``L9.industry.policy_change`` — policy-keyword filtered subset
  * ``L9.industry.compete_risk``  — risk-keyword filtered subset
  * ``L9.macro.geo``              — geo-risk keyword filtered subset

Network calls are stubbed via monkeypatch on the direct CLS helper or the
``akshare`` module's ``stock_info_global_cls`` symbol so the suite stays
hermetic.
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
def _reset_cls_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the module-level TTL cache between tests."""

    akshare_source._LAST_CLS_FETCH["ts"] = 0
    akshare_source._LAST_CLS_FETCH["rows"] = []
    monkeypatch.setattr(
        akshare_source, "_fetch_cls_telegraph_records_direct", lambda: None,
    )
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
# Happy path — all 4 dp_ids emitted with correct keyword filtering
# ---------------------------------------------------------------------------


def test_emits_market_level_dp_ids_with_market_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    monkeypatch.setattr(ak, "stock_info_global_cls", _make_cls_frame)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)

    assert len(rows) == 4, "must emit exactly 4 rows for the CLS dp_ids"
    dp_ids = {r[1] for r in rows}
    assert dp_ids == {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
        "L9.macro.geo",
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
    # The 造假/调查 headline is consumed by the risk bucket, not double-counted
    # as media-report expectation_gap.
    assert by_dp["L9.media.report"]["net_media_score"] == 0
    assert by_dp["L9.media.report"]["positive_media_count"] == 0
    assert by_dp["L9.media.report"]["negative_media_count"] == 0
    assert by_dp["L9.media.report"]["classified_media_count"] == 0

    # L9.industry.policy_change — exactly 1 hit (政策/补贴 keywords).
    assert by_dp["L9.industry.policy_change"]["count_24h"] == 1
    assert by_dp["L9.industry.policy_change"]["positive_policy_count"] == 1
    assert by_dp["L9.industry.policy_change"]["negative_policy_count"] == 0
    assert by_dp["L9.industry.policy_change"]["net_policy_score"] == 1
    policy_title = by_dp["L9.industry.policy_change"]["top_headlines"][0]["title"]
    assert "政策" in policy_title or "补贴" in policy_title

    # L9.industry.compete_risk — exactly 1 hit (诉讼/调查/造假 keywords).
    assert by_dp["L9.industry.compete_risk"]["count_24h"] == 1
    risk_title = by_dp["L9.industry.compete_risk"]["top_headlines"][0]["title"]
    assert any(kw in risk_title for kw in ("诉讼", "调查", "造假"))

    # L9.macro.geo — no geo keyword in this fixture, but successful decode
    # still records a Known neutral observation.
    assert by_dp["L9.macro.geo"]["count_24h"] == 0
    assert by_dp["L9.macro.geo"]["event_active"] is False


def test_status_known_when_bucket_has_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import akshare as ak

    monkeypatch.setattr(ak, "stock_info_global_cls", _make_cls_frame)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    statuses = {r[1]: r[3] for r in rows}
    # Successful decode makes all 4 buckets Known; empty buckets are neutral
    # observations rather than missing data.
    assert statuses == {
        "L9.media.report": "Known",
        "L9.industry.policy_change": "Known",
        "L9.industry.compete_risk": "Known",
        "L9.macro.geo": "Known",
    }


def test_direct_cls_roll_api_is_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current cls.cn web API rows are used before the stale akshare wrapper."""

    from datetime import datetime

    import akshare as ak

    base = datetime.now()
    direct_records = [
        {
            "标题": "龙头公司涨停并创历史新高",
            "内容": "订单大增推动市场关注。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": base.strftime("%H:%M:%S"),
        },
        {
            "标题": "产业补贴政策发布",
            "内容": "专项资金支持先进制造。",
            "发布日期": base.strftime("%Y-%m-%d"),
            "发布时间": base.strftime("%H:%M:%S"),
        },
    ]

    def _legacy_should_not_run():
        raise RuntimeError("legacy akshare should not be called")

    monkeypatch.setattr(
        akshare_source,
        "_fetch_cls_telegraph_records_direct",
        lambda: list(direct_records),
    )
    monkeypatch.setattr(ak, "stock_info_global_cls", _legacy_should_not_run)

    rows = akshare_source.fetch_cls_telegraph_batch(int(time.time()))
    by_dp = {r[1]: json.loads(r[2]) for r in rows}

    assert len(rows) == 4
    assert by_dp["L9.media.report"]["count_24h"] == 2
    assert by_dp["L9.media.report"]["positive_media_count"] == 1
    assert by_dp["L9.industry.policy_change"]["count_24h"] == 1
    assert by_dp["L9.industry.compete_risk"]["count_24h"] == 0
    assert by_dp["L9.macro.geo"]["count_24h"] == 0


def test_status_inactive_when_bucket_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a bucket has 0 keyword matches, that dp_id is Known-neutral."""

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
    report_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.media.report")
    )
    assert report_payload["net_media_score"] == 0
    assert report_payload["event_active"] is False
    # Policy / risk misses are decoded neutral observations.
    assert statuses["L9.industry.policy_change"] == "Known"
    policy_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.industry.policy_change")
    )
    assert policy_payload["count_24h"] == 0
    assert policy_payload["net_policy_score"] == 0
    assert statuses["L9.industry.compete_risk"] == "Known"
    risk_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.industry.compete_risk")
    )
    assert risk_payload["count_24h"] == 0
    assert risk_payload["event_active"] is False
    assert statuses["L9.macro.geo"] == "Known"
    geo_payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.macro.geo")
    )
    assert geo_payload["count_24h"] == 0
    assert geo_payload["event_active"] is False


def test_geo_bucket_matches_geopolitical_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime

    import akshare as ak

    base = datetime.now()

    class _GeoDF:
        def __len__(self):
            return 2

        def to_dict(self, orient="records"):
            return [
                {
                    "标题": "红海航运冲突扰动出口供应链",
                    "内容": "地缘风险升温，贸易摩擦加剧。",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "A股早盘震荡",
                    "内容": "盘中个股涨跌互现。",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
            ]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _GeoDF())

    rows = akshare_source.fetch_cls_telegraph_batch(int(time.time()))
    payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.macro.geo")
    )
    assert payload["count_24h"] == 1
    assert payload["event_active"] is True
    assert "红海" in payload["top_headlines"][0]["title"]


def test_policy_direction_keeps_generic_words_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime

    import akshare as ak

    base = datetime.now()

    class _PolicyDF:
        def __len__(self):
            return 3

        def to_dict(self, orient="records"):
            return [
                {
                    "标题": "产业补贴政策发布",
                    "内容": "专项资金支持先进制造",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "出口管制措施收紧",
                    "内容": "相关产品限制出口",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "行业管理办法征求意见",
                    "内容": "公开征求意见",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
            ]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _PolicyDF())

    rows = akshare_source.fetch_cls_telegraph_batch(int(time.time()))
    payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.industry.policy_change")
    )
    assert payload["count_24h"] == 3
    assert payload["positive_policy_count"] == 1
    assert payload["negative_policy_count"] == 1
    assert payload["net_policy_score"] == 0


def test_media_report_direction_keeps_generic_volume_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime

    import akshare as ak

    base = datetime.now()

    class _MediaDF:
        def __len__(self):
            return 4

        def to_dict(self, orient="records"):
            return [
                {
                    "标题": "龙头公司涨停并创历史新高",
                    "内容": "订单大增推动市场关注",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "某公司跌停并业绩预亏",
                    "内容": "公司公告业绩预亏",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "A股早盘上涨",
                    "内容": "盘中震荡，个股涨跌互现",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
                {
                    "标题": "行业管理办法征求意见",
                    "内容": "公开征求意见",
                    "发布日期": base.strftime("%Y-%m-%d"),
                    "发布时间": base.strftime("%H:%M:%S"),
                },
            ]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _MediaDF())

    rows = akshare_source.fetch_cls_telegraph_batch(int(time.time()))
    payload = json.loads(
        next(r[2] for r in rows if r[1] == "L9.media.report")
    )
    assert payload["count_24h"] == 4
    assert payload["positive_media_count"] == 1
    assert payload["negative_media_count"] == 1
    assert payload["classified_media_count"] == 2
    assert payload["net_media_score"] == 0
    assert payload["event_active"] is True


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
            # Derive 发布日期 AND 发布时间 from the SAME (base+i) instant so they
            # stay consistent across a midnight boundary. Previously the date was
            # pinned to ``base`` while the time advanced by i minutes — when base
            # sat at 23:5x, records past midnight got time "00:0x" with the prior
            # day's date, which ``_parse_cls_publish_epoch`` reads as ~24h ago →
            # dropped by the 24h window → count_24h flaky (<20) near midnight.
            "发布日期": (base + timedelta(minutes=i)).strftime("%Y-%m-%d"),
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


def test_report_known_neutral_when_no_recent_headlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta

    import akshare as ak

    stale = datetime.now() - timedelta(hours=48)

    class _StaleOnlyDF:
        def __len__(self):
            return 1

        def to_dict(self, orient="records"):
            return [{
                "标题": "陈年利好旧闻",
                "内容": "不应进入24小时窗口",
                "发布日期": stale.strftime("%Y-%m-%d"),
                "发布时间": stale.strftime("%H:%M:%S"),
            }]

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _StaleOnlyDF())

    rows = akshare_source.fetch_cls_telegraph_batch(int(time.time()))
    report_row = next(r for r in rows if r[1] == "L9.media.report")
    payload = json.loads(report_row[2])
    assert report_row[3] == "Known"
    assert payload["count_24h"] == 0
    assert payload["net_media_score"] == 0
    assert payload["event_active"] is False


# ---------------------------------------------------------------------------
# Failure-tolerance — Inactive CLS rows emitted when upstream fails
# ---------------------------------------------------------------------------


def test_inactive_cls_rows_on_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint 502 / RuntimeError → emit Inactive rows, never crash."""

    import akshare as ak

    def _explode():
        raise RuntimeError("simulated CLS 502")

    monkeypatch.setattr(ak, "stock_info_global_cls", _explode)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)

    assert len(rows) == 4
    assert {r[3] for r in rows} == {"Inactive"}
    assert {r[0] for r in rows} == {"MARKET:CN"}
    assert {r[1] for r in rows} == {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
        "L9.macro.geo",
    }
    # Reason embedded in payload for diagnostics.
    for r in rows:
        payload = json.loads(r[2])
        assert "reason" in payload
        assert "simulated CLS 502" in payload["reason"]


def test_inactive_cls_rows_on_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty DataFrame → Inactive rows, not crash."""

    import akshare as ak

    class _Empty:
        def __len__(self):
            return 0

        def to_dict(self, orient="records"):
            return []

    monkeypatch.setattr(ak, "stock_info_global_cls", lambda: _Empty())

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    assert len(rows) == 4
    assert {r[3] for r in rows} == {"Inactive"}


def test_inactive_cls_rows_when_symbol_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older akshare versions without the symbol → graceful Inactive."""

    import akshare as ak

    monkeypatch.delattr(ak, "stock_info_global_cls", raising=False)
    monkeypatch.delattr(ak, "stock_telegraph_cls", raising=False)

    now = int(time.time())
    rows = akshare_source.fetch_cls_telegraph_batch(now)
    assert len(rows) == 4
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
# SUPPORTED_DP_IDS contract — module-level set declares the CLS dp_ids
# ---------------------------------------------------------------------------


def test_supported_dp_ids_contains_market_level() -> None:
    expected = {
        "L9.media.report",
        "L9.industry.policy_change",
        "L9.industry.compete_risk",
        "L9.macro.geo",
    }
    assert expected.issubset(akshare_source.SUPPORTED_DP_IDS)
    assert expected == akshare_source.MARKET_LEVEL_DP_IDS
