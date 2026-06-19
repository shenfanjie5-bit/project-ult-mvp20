"""akshare source for A-share / HK news, public-opinion heat, and announcements.

akshare is a free aggregator of Chinese-market public-data feeds. Compared
with Tushare it has no API token / no rate-card; the trade-off is that the
upstream HTML/JSON layouts occasionally break and individual endpoints can
go offline transiently. Every fetcher in this module therefore wraps the
akshare call in a defensive ``try/except`` so a single endpoint failure
never kills the collector cycle.

Tier-1 stock-level dp_ids implemented today
-------------------------------------------

* ``L9.event.intraday_news`` — per A-share, recent EM news headlines + URLs.
* ``L9.event.intraday_announcement`` — per A-share, recent Cninfo / EM
  announcements (公告标题 + 类型 + ann_date + URL).
* ``L7.mood.media_social`` — per A-share, EM hot-rank / heat-keyword
  combined snapshot (排名 / 涨跌幅 / 关键词).
* ``L9.media.social_buzz`` — per A-share, 雪球关注 / 分享 heat from the
  market-wide Xueqiu ranking (single market-wide query, lookup per ts_code).
* ``L7.mood.theme`` — per A-share, EM hot-keyword concept tags that the
  individual ticker shows up under (concept 热度 list, 单股 视角).

Market-level catalyst dp_ids (CLS 财联社电报)
----------------------------------------------

A single ``ak.stock_info_global_cls()`` call returns the latest 财联社
electronic telegraph stream. We bucket the result into 4 market-wide
dp_ids — all keyed to the sentinel ``ts_code='MARKET:CN'`` (same
convention used by ``tushare_source.fetch_macro_china_batch``):

* ``L9.media.report`` — full count + top headlines from the last 24h,
  plus conservative positive/negative headline classification.
* ``L9.industry.policy_change`` — same stream, filtered by policy keywords
  (政策 / 监管 / 牌照 / 反垄断 / 出口管制 / …).
* ``L9.industry.compete_risk`` — same stream, filtered by risk keywords
  (诉讼 / 调查 / 处罚 / 暴雷 / 退市 / 制裁 / …).
* ``L9.macro.geo`` — same stream, filtered by high-precision geopolitical
  keywords (地缘 / 战争 / 冲突 / 制裁 / 出口管制 / …).

Stub Tier-2 / Tier-3 dp_ids (commodity / sector heat) are kept in
``SUPPORTED_DP_IDS`` with TODO notes — they need industry-level fan-out
to be wired through the overlay engine before fetching is worthwhile.

Conventions
-----------

* A-share ``ts_code`` strips the ``.SH`` / ``.SZ`` / ``.BJ`` suffix for
  akshare (e.g. ``300750.SZ`` → ``300750``).
* HK ``ts_code`` strips ``.HK`` (e.g. ``00700.HK`` → ``00700``); some
  akshare endpoints accept ``HK00700`` but our chosen Tier-1 set is
  A-share-only so HK is currently a no-op.
* All emitted ``value_json`` payloads include an ISO-8601 ``as_of``
  timestamp + a ``count_24h`` / ``top_*`` summary aligned with the
  output_schema convention used elsewhere in mvp20.
"""

from __future__ import annotations

import json
import logging
import hashlib
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable

log = logging.getLogger("mvp20.sources.akshare")


# ---------------------------------------------------------------------------
# Per-call hard timeout (B2)
# ---------------------------------------------------------------------------
# akshare endpoints scrape upstream HTML/JSON with no caller-controllable
# timeout, so a single stuck endpoint can block the whole collector cycle
# indefinitely (observed: a 74-minute hang at 0% CPU that needed `kill -9`).
# Every bare ``ak.*`` call is therefore routed through ``_ak_call``, which runs
# it on a daemon worker thread and abandons it if it overruns. The orphaned
# thread cannot be force-killed (CPython has no thread.kill), but it is a daemon
# so it never blocks process exit, and the collector proceeds to the next field.

# Default 25s; override with AKSHARE_CALL_TIMEOUT_S (0 / negative disables).
try:
    _AKSHARE_CALL_TIMEOUT_S = float(os.environ.get("AKSHARE_CALL_TIMEOUT_S", "25"))
except (TypeError, ValueError):
    _AKSHARE_CALL_TIMEOUT_S = 25.0


class AkshareTimeout(Exception):
    """Raised when an akshare call exceeds its wall-clock budget."""


def _ak_call(label: str, fn: Callable[[], Any], *, timeout: float | None = None) -> Any:
    """Run a blocking akshare call with a hard wall-clock timeout.

    Returns ``fn()``'s result, re-raises any exception ``fn`` raised, or raises
    :class:`AkshareTimeout` if it overruns. A non-positive timeout disables the
    guard (runs inline) so tests / offline use can opt out.
    """

    budget = _AKSHARE_CALL_TIMEOUT_S if timeout is None else timeout
    if budget is None or budget <= 0:
        return fn()

    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — propagate to caller thread
            box["error"] = exc

    worker = threading.Thread(
        target=_run, name=f"akshare-{label}", daemon=True
    )
    worker.start()
    worker.join(budget)
    if worker.is_alive():
        log.warning(
            "[akshare] %s exceeded %.0fs timeout — skipping (worker abandoned)",
            label, budget,
        )
        raise AkshareTimeout(label)
    if "error" in box:
        raise box["error"]
    return box.get("value")


# ---------------------------------------------------------------------------
# SUPPORTED_DP_IDS  (Tier-1 wired; Tier-2/3 declared as stubs)
# ---------------------------------------------------------------------------

# Tier-1: per-stock fields actually populated by fetch_batch().
#
# NOTE: intraday_announcement / media_social / social_buzz / mood.theme /
# cap.outflow_cut were MOVED off akshare onto permitted Tushare endpoints
# (``tushare_source.fetch_akshare_replacement_batch``) so they no longer
# appear here — the akshare fetchers for them are also disabled in
# ``fetch_batch`` so the two sources never race on the (ts_code, dp_id) PK.
# The 4 news-based fields (intraday_news + the 3 CLS catalyst dp_ids) stay on
# akshare because Tushare ``news`` is empty for this account.
TIER1_DP_IDS = {
    "L9.event.intraday_news",
    # Bucket A append (per A-share block-trade signal; outflow_cut moved to
    # Tushare).
    "L9.capital.etf_block",
}

# Market-level (sentinel ts_code = 'MARKET:CN'), shared 财联社电报 stream.
# All market-level dp_ids are emitted from a single ``stock_info_global_cls`` call;
# the bucketing logic lives in ``fetch_cls_telegraph_batch``.
MARKET_LEVEL_DP_IDS = {
    "L9.media.report",
    "L9.industry.policy_change",
    "L9.industry.compete_risk",
    "L9.macro.geo",
}

# Tier-2/3: industry / commodity / sector-heat dp_ids. These were MOVED off
# akshare onto permitted Tushare endpoints (fut_daily / moneyflow_ind_ths) in
# ``tushare_source.fetch_akshare_replacement_batch``; the akshare fetchers for
# them are disabled in ``fetch_batch`` so the sources don't race on the PK.
TIER2_TODO_DP_IDS: set[str] = set()

SUPPORTED_DP_IDS = TIER1_DP_IDS | MARKET_LEVEL_DP_IDS | TIER2_TODO_DP_IDS


# ---------------------------------------------------------------------------
# ts_code helpers
# ---------------------------------------------------------------------------


_A_SUFFIXES = (".SH", ".SZ", ".BJ")


def is_a_share(ts_code: str) -> bool:
    return ts_code.endswith(_A_SUFFIXES)


def is_hk(ts_code: str) -> bool:
    return ts_code.endswith(".HK")


def is_us(ts_code: str) -> bool:
    return ts_code.endswith(".US")


def to_a_share_code(ts_code: str) -> str | None:
    """``300750.SZ`` → ``300750``; returns None for non-A-share."""

    if not is_a_share(ts_code):
        return None
    return ts_code[:-3]


def to_a_share_em_symbol(ts_code: str) -> str | None:
    """``300750.SZ`` → ``SZ300750`` (EM convention used by ``stock_hot_*_em``)."""

    if not is_a_share(ts_code):
        return None
    raw = ts_code[:-3]
    if ts_code.endswith(".SH"):
        return f"SH{raw}"
    if ts_code.endswith(".SZ"):
        return f"SZ{raw}"
    return f"BJ{raw}"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def health_check() -> dict:
    """Verify ``import akshare`` works + one cheap remote endpoint reachable.

    Strategy: probe a small set of stable endpoints (cx news / EM heat-rank /
    Xueqiu follow) and report ``ok`` if any one succeeds. akshare's upstreams
    are flaky (HTML/JSON layouts shift, CDN occasionally 502s), so a single
    fixed probe target is fragile — but as long as *one* live data source
    responds we know the wider source is usable in this cycle.
    """

    try:
        import akshare as ak  # type: ignore
    except ImportError as e:
        return {"ok": False, "error": f"akshare not installed: {e}"}

    probes = (
        ("stock_news_main_cx",  lambda: ak.stock_news_main_cx()),
        ("stock_hot_rank_em",   lambda: ak.stock_hot_rank_em()),
    )
    last_error: str | None = None
    for name, fn in probes:
        try:
            df = _ak_call(name, fn)
            n = int(len(df)) if df is not None else 0
            if n > 0:
                return {
                    "ok": True,
                    "akshare_version": getattr(ak, "__version__", "?"),
                    "probe_endpoint": name,
                    "probe_rows": n,
                    "supported_dp_ids_count": len(SUPPORTED_DP_IDS),
                    "tier1_count": len(TIER1_DP_IDS),
                }
            last_error = f"{name} returned 0 rows"
        except Exception as e:  # noqa: BLE001
            last_error = f"{name} failed: {e}"
            continue
    return {
        "ok": False,
        "error": last_error or "no probe succeeded",
        "akshare_version": getattr(ak, "__version__", "?"),
    }


# ---------------------------------------------------------------------------
# Utility: now + as_of
# ---------------------------------------------------------------------------


def _now_epoch() -> int:
    return int(time.time())


def _as_of_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _stringify_date(v) -> str | None:
    """akshare sometimes returns ``datetime.date`` / ``datetime`` / NaT.

    Normalise to ``YYYY-MM-DD`` (or ISO if a time component is present)
    so the JSON payload is deterministic across pandas versions.
    """

    if v is None:
        return None
    try:
        # pandas NaT
        if v != v:  # noqa: PLR0124 — NaN/NaT inequality
            return None
    except TypeError:
        pass
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:  # noqa: BLE001
            pass
    s = str(v).strip()
    return s or None


# ---------------------------------------------------------------------------
# L9.event.intraday_news — EM per-stock news (direct HTTP, bypasses akshare's
# pandas-3-incompatible str.replace regex chain in stock_news_em).
# ---------------------------------------------------------------------------


_EM_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"


def _fetch_em_news(keyword: str, page_size: int = 20, timeout: int = 10) -> list[dict]:
    """Return raw EM 全文搜索 article list (no pandas dependency).

    The akshare wrapper around this endpoint (``stock_news_em``) currently
    crashes on pandas ≥3 because it does ``temp_df['...'].str.replace(
    r'\\u3000', '', regex=True)`` — the new pandas regex engine refuses
    ``\\u`` escapes. Calling the underlying endpoint directly keeps us
    decoupled from akshare's pandas-version drift.
    """

    qs = {
        "cb": "jQuery",
        "param": json.dumps({
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }},
        }, ensure_ascii=False),
    }
    url = f"{_EM_NEWS_URL}?{urllib.parse.urlencode(qs)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 mvp20-collector"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("[akshare-em-news] %s network error: %s", keyword, e)
        return []
    m = re.match(r"^jQuery\((.*)\)\s*$", raw, flags=re.DOTALL)
    body = m.group(1) if m else raw
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        log.warning("[akshare-em-news] %s JSON decode failed: %s", keyword, e)
        return []
    return data.get("result", {}).get("cmsArticleWebOld") or []


def fetch_intraday_news(
    a_codes: list[str],
    now: int,
    top_n_per_stock: int = 5,
    sleep_s: float = 0.15,
) -> list[tuple]:
    """Per A-share ``ts_code``: pull recent EM news headlines.

    Emits one ``L9.event.intraday_news`` row per stock. If the endpoint
    fails for an individual stock we skip that stock (no crash, no
    Inactive marker — collector keeps the existing value if any).
    """

    rows: list[tuple] = []
    as_of = _as_of_iso()
    success = 0
    failed = 0
    for ts_code in a_codes:
        keyword = to_a_share_code(ts_code)
        if not keyword:
            continue
        items = _fetch_em_news(keyword, page_size=max(top_n_per_stock, 10))
        if not items:
            failed += 1
            time.sleep(sleep_s)
            continue
        # Build top_headlines summary — strip <em>...</em> tags inline
        top: list[dict] = []
        for item in items[:top_n_per_stock]:
            title = re.sub(r"</?em>", "", str(item.get("title") or ""))
            top.append({
                "title": title,
                "publish_time": _stringify_date(item.get("date")),
                "url": item.get("url"),
                "source": item.get("mediaName"),
            })
        payload = {
            "count_24h": len(items),
            "top_headlines": top,
            "keyword": keyword,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L9.event.intraday_news",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.6, "akshare:em_news", now,
        ))
        success += 1
        time.sleep(sleep_s)
    log.info("[akshare] intraday_news: %d ok / %d failed → %d rows",
             success, failed, len(rows))
    return rows


# ---------------------------------------------------------------------------
# L9.event.intraday_announcement — per-stock EM/Cninfo 公告
# ---------------------------------------------------------------------------


def fetch_intraday_announcement(
    a_codes: list[str],
    now: int,
    top_n_per_stock: int = 5,
    sleep_s: float = 0.2,
) -> list[tuple]:
    """Per A-share: latest 公告 from EM proxy of Cninfo (``stock_individual_notice_report``).

    ``stock_individual_notice_report(security=<6-digit>)`` returns up to
    several years of announcements ordered most-recent-first; we keep the
    top-N. If akshare or upstream fails for a code, we skip silently.
    """

    try:
        import akshare as ak  # type: ignore
    except ImportError as e:
        log.warning("[akshare] announcement skipped — akshare missing: %s", e)
        return []

    rows: list[tuple] = []
    as_of = _as_of_iso()
    success = 0
    failed = 0
    for ts_code in a_codes:
        sec = to_a_share_code(ts_code)
        if not sec:
            continue
        try:
            df = _ak_call("stock_individual_notice_report",
                          lambda: ak.stock_individual_notice_report(security=sec))
        except Exception as e:  # noqa: BLE001
            log.warning("[akshare] notice_report %s failed: %s", ts_code, e)
            failed += 1
            time.sleep(sleep_s)
            continue
        if df is None or len(df) == 0:
            failed += 1
            time.sleep(sleep_s)
            continue
        # Tolerate column-name drift: pick by Chinese label or position.
        records = df.head(max(top_n_per_stock, 1) * 4).to_dict(orient="records")
        top: list[dict] = []
        for rec in records[:top_n_per_stock]:
            top.append({
                "title": rec.get("公告标题") or rec.get("title"),
                "type": rec.get("公告类型") or rec.get("notice_type"),
                "ann_date": _stringify_date(rec.get("公告日期") or rec.get("ann_date")),
                "url": rec.get("网址") or rec.get("url"),
            })
        payload = {
            "count_recent": len(records),
            "top_announcements": top,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L9.event.intraday_announcement",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.65, "akshare:stock_individual_notice_report", now,
        ))
        success += 1
        time.sleep(sleep_s)
    log.info("[akshare] intraday_announcement: %d ok / %d failed → %d rows",
             success, failed, len(rows))
    return rows


# ---------------------------------------------------------------------------
# L7.mood.media_social — per-stock EM hot rank + heat keywords
# ---------------------------------------------------------------------------


def _fetch_em_hot_rank_snapshot() -> dict[str, dict]:
    """Single market-wide EM 热度排行 snapshot. Returns dict keyed by EM
    symbol (e.g. ``SZ300750``) so we can look up per-stock heat in O(1)."""

    try:
        import akshare as ak  # type: ignore
        df = _ak_call("stock_hot_rank_em", ak.stock_hot_rank_em)
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] stock_hot_rank_em snapshot failed: %s", e)
        return {}
    if df is None or len(df) == 0:
        return {}

    out: dict[str, dict] = {}
    for rec in df.to_dict(orient="records"):
        code = str(rec.get("代码") or rec.get("code") or "").strip()
        if not code:
            continue
        out[code] = {
            "rank": _safe_int(rec.get("当前排名") or rec.get("rank")),
            "name": rec.get("股票名称") or rec.get("name"),
            "last": _safe_float(rec.get("最新价") or rec.get("last")),
            "change_pct": _safe_float(rec.get("涨跌幅") or rec.get("change_pct")),
        }
    return out


def _fetch_em_hot_keywords(em_symbol: str, timeout: int = 8) -> list[dict]:
    """Per-stock ``stock_hot_keyword_em(symbol='SZ300750')`` snapshot."""

    try:
        import akshare as ak  # type: ignore
        df = _ak_call("stock_hot_keyword_em",
                      lambda: ak.stock_hot_keyword_em(symbol=em_symbol))
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] stock_hot_keyword_em %s failed: %s", em_symbol, e)
        return []
    if df is None or len(df) == 0:
        return []
    out: list[dict] = []
    for rec in df.to_dict(orient="records"):
        out.append({
            "time": _stringify_date(rec.get("时间") or rec.get("time")),
            "concept": rec.get("概念名称") or rec.get("concept"),
            "concept_code": rec.get("概念代码") or rec.get("concept_code"),
            "heat": _safe_float(rec.get("热度") or rec.get("heat")),
        })
    return out


def fetch_media_social_and_theme(
    a_codes: list[str],
    now: int,
    sleep_s: float = 0.15,
) -> list[tuple]:
    """Emit both ``L7.mood.media_social`` and ``L7.mood.theme`` rows.

    ``stock_hot_rank_em`` is a single market-wide call (fast) which gives
    us the global rank for every covered ticker. ``stock_hot_keyword_em``
    is per-stock and slower; we use it to populate the *concept tags* a
    given ticker is currently linked to, which is what ``L7.mood.theme``
    needs (热门概念板块 in spec).
    """

    rank_snapshot = _fetch_em_hot_rank_snapshot()
    rows: list[tuple] = []
    as_of = _as_of_iso()
    n_social = 0
    n_theme = 0
    for ts_code in a_codes:
        em_symbol = to_a_share_em_symbol(ts_code)
        if not em_symbol:
            continue

        rank_entry = rank_snapshot.get(em_symbol)
        # Some EM ranks omit the "SH/SZ" prefix; tolerate either form.
        if rank_entry is None:
            rank_entry = rank_snapshot.get(em_symbol[2:])

        keywords = _fetch_em_hot_keywords(em_symbol)
        time.sleep(sleep_s)

        # ---- L7.mood.media_social ----
        social_payload = {
            "rank_overall": rank_entry.get("rank") if rank_entry else None,
            "in_top_100": bool(rank_entry and rank_entry.get("rank") and
                               rank_entry["rank"] <= 100),
            "last_price": rank_entry.get("last") if rank_entry else None,
            "change_pct": rank_entry.get("change_pct") if rank_entry else None,
            "concept_tag_count": len(keywords),
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L7.mood.media_social",
            json.dumps(social_payload, ensure_ascii=False),
            "Known" if rank_entry or keywords else "Inactive",
            0.55, "akshare:stock_hot_rank_em+keyword", now,
        ))
        n_social += 1

        # ---- L7.mood.theme ----
        if keywords:
            theme_payload = {
                "concept_count": len(keywords),
                "top_concepts": keywords[:8],
                "as_of": as_of,
            }
            rows.append((
                ts_code, "L7.mood.theme",
                json.dumps(theme_payload, ensure_ascii=False),
                "Known", 0.55, "akshare:stock_hot_keyword_em", now,
            ))
            n_theme += 1
        else:
            rows.append((
                ts_code, "L7.mood.theme",
                json.dumps({"concept_count": 0, "as_of": as_of},
                           ensure_ascii=False),
                "Inactive", 0.5, "akshare:stock_hot_keyword_em", now,
            ))
            n_theme += 1
    log.info("[akshare] media_social=%d theme=%d → %d rows",
             n_social, n_theme, len(rows))
    return rows


# ---------------------------------------------------------------------------
# L9.media.social_buzz — Xueqiu 关注/分享 排行 (market-wide, look up per stock)
# ---------------------------------------------------------------------------


def _fetch_xq_buzz_snapshot() -> dict[str, dict]:
    """One market-wide Xueqiu 关注 + 分享 snapshot. Keyed by EM-style symbol
    (``SH600519`` / ``SZ300750``) so we can look up per-stock heat O(1).

    Two endpoints combined:
      * ``stock_hot_follow_xq(symbol='最热门')`` — 关注排行
      * ``stock_hot_tweet_xq(symbol='最热门')``  — 分享 / tweet count
    """

    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return {}

    out: dict[str, dict] = {}
    try:
        df = _ak_call("stock_hot_follow_xq",
                      lambda: ak.stock_hot_follow_xq(symbol="最热门"))
        if df is not None and len(df) > 0:
            for rec in df.to_dict(orient="records"):
                code = str(rec.get("股票代码") or "").strip()
                if not code:
                    continue
                out[code] = {
                    "follow": _safe_float(rec.get("关注")),
                    "last": _safe_float(rec.get("最新价")),
                    "name": rec.get("股票简称"),
                }
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] stock_hot_follow_xq failed: %s", e)

    try:
        df = _ak_call("stock_hot_tweet_xq",
                      lambda: ak.stock_hot_tweet_xq(symbol="最热门"))
        if df is not None and len(df) > 0:
            for rec in df.to_dict(orient="records"):
                code = str(rec.get("股票代码") or "").strip()
                if not code:
                    continue
                row = out.setdefault(code, {})
                row["tweet"] = _safe_float(
                    rec.get("分享") or rec.get("分享交易")
                )
                # Don't override last/name if already present
                row.setdefault("last", _safe_float(rec.get("最新价")))
                row.setdefault("name", rec.get("股票简称"))
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] stock_hot_tweet_xq failed: %s", e)

    return out


def fetch_social_buzz(a_codes: list[str], now: int) -> list[tuple]:
    """Emit ``L9.media.social_buzz`` rows from the Xueqiu market-wide snapshot.

    Snapshot is fetched once for the whole universe; per-stock lookup is
    O(1). If a stock isn't in the top-N Xueqiu list we mark Inactive.
    """

    snapshot = _fetch_xq_buzz_snapshot()
    rows: list[tuple] = []
    as_of = _as_of_iso()
    if not snapshot:
        log.warning("[akshare] xq buzz snapshot empty — skipping social_buzz")
        return rows

    # Compute rank ordering by follow desc to expose "rank_among_buzz_top"
    ranked = sorted(
        [(code, e.get("follow") or 0) for code, e in snapshot.items()],
        key=lambda x: x[1], reverse=True,
    )
    rank_lookup = {code: i + 1 for i, (code, _) in enumerate(ranked)}

    for ts_code in a_codes:
        em_symbol = to_a_share_em_symbol(ts_code)
        if not em_symbol:
            continue
        entry = snapshot.get(em_symbol)
        if entry is None:
            rows.append((
                ts_code, "L9.media.social_buzz",
                json.dumps({
                    "in_xq_top_buzz": False,
                    "as_of": as_of,
                }, ensure_ascii=False),
                "Inactive", 0.5, "akshare:xq_hot", now,
            ))
            continue
        payload = {
            "in_xq_top_buzz": True,
            "follow_count": entry.get("follow"),
            "tweet_count": entry.get("tweet"),
            "rank_among_buzz_top": rank_lookup.get(em_symbol),
            "last_price": entry.get("last"),
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L9.media.social_buzz",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.55, "akshare:xq_hot", now,
        ))
    log.info("[akshare] social_buzz → %d rows (snapshot=%d)",
             len(rows), len(snapshot))
    return rows


# ---------------------------------------------------------------------------
# Market-level CLS telegraph stream
# ---------------------------------------------------------------------------
#
# A single ``ak.stock_info_global_cls()`` call produces the 财联社 electronic
# telegraph list (latest ~20 headlines, ordered most-recent-first). We bucket
# the result into four MARKET:CN-keyed dp_ids:
#
#   * ``L9.media.report``           — overall flow + conservative media tilt
#   * ``L9.industry.policy_change`` — policy / regulation keyword bucket
#   * ``L9.industry.compete_risk``  — risk / incident keyword bucket
#   * ``L9.macro.geo``              — geopolitical risk keyword bucket
#
# The CLS endpoint occasionally 502s and akshare sometimes drops the symbol
# (older versions called it ``stock_telegraph_cls``). We TTL-cache the
# successful fetch for 600s so we re-emit the same payload between cycles
# without hammering the upstream.

_CLS_CACHE_TTL_S = 600
_LAST_CLS_FETCH: dict[str, object] = {
    "ts": 0,       # unix epoch of last successful upstream fetch
    "rows": [],    # cached 7-tuple rows
}

_CLS_TELEGRAPH_MARKET = "MARKET:CN"
_CLS_TELEGRAPH_MAX_HEADLINES = 10
_CLS_TELEGRAPH_TITLE_TRIM = 200
_CLS_TELEGRAPH_LOOKBACK_S = 24 * 3600  # 24h window
_CLS_DIRECT_URL = "https://www.cls.cn/v1/roll/get_roll_list"
_CLS_DIRECT_APP = "CailianpressWeb"
_CLS_DIRECT_SV = "8.7.9"
_CLS_DIRECT_RN = 20
try:
    _CLS_DIRECT_TIMEOUT_S = float(
        os.environ.get("AKSHARE_CLS_DIRECT_TIMEOUT_S", "8")
    )
except (TypeError, ValueError):
    _CLS_DIRECT_TIMEOUT_S = 8.0

# Keyword filters. Keep them small and high-precision; we'd rather miss a
# borderline headline than pollute the bucket. All keywords are 2-4 character
# Chinese fragments so substring matching is safe.
_POLICY_KEYWORDS = (
    "政策", "补贴", "反垄断", "监管", "牌照", "税收",
    "出口管制", "限制", "通知", "办法", "意见", "规定", "暂行",
)
_POLICY_POSITIVE_KEYWORDS = (
    "补贴", "支持", "鼓励", "促进", "扶持", "减税", "降费",
    "免税", "放宽", "以旧换新", "专项资金", "利好",
)
_POLICY_NEGATIVE_KEYWORDS = (
    "监管", "反垄断", "限制", "出口管制", "处罚", "禁令",
    "整治", "约谈", "通报", "核查", "收紧", "暂缓",
)
_RISK_KEYWORDS = (
    "诉讼", "调查", "处罚", "退市", "造假", "暴雷", "违约",
    "重大风险", "事故", "突发", "停产", "罢工", "制裁",
)
_GEO_KEYWORDS = (
    "地缘", "战争", "冲突", "军事", "边境", "台海", "海峡",
    "南海", "中东", "红海", "乌克兰", "俄罗斯", "以色列",
    "伊朗", "关税", "制裁", "禁运", "出口管制", "贸易摩擦",
    "贸易争端",
)
_MEDIA_POSITIVE_KEYWORDS = (
    "涨停", "大涨", "强势上涨", "创历史新高", "刷新高", "利好",
    "业绩预增", "业绩大增", "净利大增", "净利润增长", "扭亏",
    "中标", "签订重大合同", "订单大增", "回购", "增持", "上调评级",
    "获批", "突破",
)
_MEDIA_NEGATIVE_KEYWORDS = (
    "跌停", "大跌", "暴跌", "重挫", "跳水", "创新低", "利空",
    "业绩预亏", "业绩下滑", "净利下降", "亏损", "爆雷", "暴雷",
    "违约", "立案调查", "被调查", "处罚", "退市", "减持",
    "下调评级", "重大风险", "停产", "事故",
)


def _cls_sign_params(params: dict[str, object]) -> str:
    """Mirror the current cls.cn web request signature.

    The Next.js client signs the sorted query string with sha1, then md5 of
    that sha1 hex digest. Values used here are scalar, so no nested encoding is
    needed.
    """

    query = "&".join(
        f"{key}={params[key]}"
        for key in sorted(params, key=lambda value: str(value).upper())
    )
    sha1_hex = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1_hex.encode("utf-8")).hexdigest()


def _fetch_cls_telegraph_records_direct() -> list[dict] | None:
    """Fetch current CLS roll_data directly from the web endpoint.

    AKShare's ``stock_info_global_cls`` still points at the removed
    ``/nodeapi/telegraphList`` endpoint. The live web app now calls
    ``/v1/roll/get_roll_list`` with a signed query. Returning ``None`` tells
    the caller to try the legacy AKShare wrapper instead.
    """

    timeout = _CLS_DIRECT_TIMEOUT_S
    if timeout <= 0:
        return None

    params: dict[str, object] = {
        "refresh_type": 1,
        "rn": _CLS_DIRECT_RN,
        "last_time": 0,
        "os": "web",
        "sv": _CLS_DIRECT_SV,
        "app": _CLS_DIRECT_APP,
    }
    params["sign"] = _cls_sign_params(params)
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{_CLS_DIRECT_URL}?{query}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.cls.cn/telegraph",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if str(data.get("errno")) not in {"0"}:
        raise RuntimeError(
            f"cls_direct_errno={data.get('errno')} msg={data.get('msg')}"
        )
    records = (data.get("data") or {}).get("roll_data")
    if not isinstance(records, list):
        raise RuntimeError("cls_direct_missing_roll_data")

    converted: list[dict] = []
    cn_tz = timezone(timedelta(hours=8))
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ctime = rec.get("ctime")
        publish_dt: datetime | None = None
        try:
            publish_dt = datetime.fromtimestamp(float(ctime), tz=timezone.utc)
            publish_dt = publish_dt.astimezone(cn_tz)
        except (TypeError, ValueError, OSError):
            publish_dt = None
        title = str(rec.get("title") or "").strip()
        content = str(rec.get("content") or rec.get("brief") or "").strip()
        if not title:
            title = content
        row = {
            "标题": title,
            "内容": content,
            "等级": rec.get("level"),
            "url": (
                rec.get("shareurl")
                or rec.get("assocArticleUrl")
                or (
                    f"https://www.cls.cn/detail/{rec.get('id')}"
                    if rec.get("id")
                    else None
                )
            ),
            "source": "cls_roll_web",
        }
        if publish_dt is not None:
            row["发布日期"] = publish_dt.date()
            row["发布时间"] = publish_dt.time().replace(microsecond=0)
        converted.append(row)
    return converted


def _parse_cls_publish_epoch(date_val, time_val) -> int | None:
    """Combine CLS '发布日期' + '发布时间' into a unix epoch (local TZ).

    akshare returns both fields as strings — date as ``YYYY-MM-DD`` and
    time as ``HH:MM:SS``. We treat them as the host machine's local time
    because the upstream is a Chinese feed but the collector usually runs
    in CN/HK tz; if parsing fails we return None (caller treats the
    headline as outside the 24h window).
    """

    date_s = _stringify_date(date_val)
    time_s = _stringify_date(time_val)
    if not date_s:
        return None
    try:
        if time_s:
            dt = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(date_s, "%Y-%m-%d")
    except ValueError:
        return None
    # Treat the timestamp as local-time; collector + CLS are both China-tz.
    return int(dt.timestamp())


def _headline_from_record(rec: dict, publish_epoch: int | None) -> dict:
    """Build a single top_headlines entry from a CLS record."""

    raw_title = str(rec.get("标题") or rec.get("title") or "").strip()
    # Some CLS rows have an empty 标题 with the body in 内容 — fall back so
    # the bucketed headline is never empty.
    if not raw_title:
        raw_title = str(rec.get("内容") or rec.get("content") or "").strip()
    title = raw_title[:_CLS_TELEGRAPH_TITLE_TRIM]
    if publish_epoch is not None:
        time_iso = datetime.fromtimestamp(publish_epoch).isoformat(
            timespec="seconds",
        )
    else:
        # Fall back to whatever string upstream returned (best effort).
        date_s = _stringify_date(rec.get("发布日期")) or ""
        time_s = _stringify_date(rec.get("发布时间")) or ""
        time_iso = f"{date_s} {time_s}".strip() or None
    return {
        "title": title,
        "time": time_iso,
        "url": rec.get("url") or rec.get("链接"),
        "source": rec.get("source") or "cls_telegraph",
    }


def _match_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    if not text:
        return False
    return any(kw in text for kw in keywords)


def _policy_tilt_from_text(text: str) -> int:
    """Return +1 for clearly supportive policy, -1 for restrictive policy.

    Generic policy words such as 通知/办法/意见 are intentionally neutral; they
    prove an observed policy headline but not a safe score direction.
    """

    if not text:
        return 0
    pos = _match_any_keyword(text, _POLICY_POSITIVE_KEYWORDS)
    neg = _match_any_keyword(text, _POLICY_NEGATIVE_KEYWORDS)
    if pos and not neg:
        return 1
    if neg and not pos:
        return -1
    return 0


def _media_tilt_from_text(text: str) -> int:
    """Return +1/-1 only for high-precision market-news sentiment terms.

    Raw CLS headline volume is attention, not direction. Generic "涨/跌" words
    are intentionally ignored; only unambiguous terms become score evidence.
    """

    if not text:
        return 0
    pos = _match_any_keyword(text, _MEDIA_POSITIVE_KEYWORDS)
    neg = _match_any_keyword(text, _MEDIA_NEGATIVE_KEYWORDS)
    if pos and not neg:
        return 1
    if neg and not pos:
        return -1
    return 0


def _inactive_cls_row(dp_id: str, now: int, reason: str) -> tuple:
    """Build an Inactive 7-tuple for one of the CLS dp_ids."""

    payload = {
        "count_24h": 0,
        "top_headlines": [],
        "as_of": _as_of_iso(),
        "reason": reason,
    }
    return (
        _CLS_TELEGRAPH_MARKET, dp_id,
        json.dumps(payload, ensure_ascii=False),
        "Inactive", 0.5, "akshare:stock_info_global_cls", now,
    )


def _emit_inactive_cls_rows(now: int, reason: str) -> list[tuple]:
    """Build all MARKET:CN CLS rows in the Inactive state.

    Used when akshare is missing, the endpoint 502s, or the DataFrame
    comes back empty. We still emit rows so the freshness panel knows the
    fetcher ran (and why it produced nothing).
    """

    return [_inactive_cls_row(dp_id, now, reason)
            for dp_id in sorted(MARKET_LEVEL_DP_IDS)]


def fetch_cls_telegraph_batch(now: int) -> list[tuple]:
    """One CLS telegraph fetch → MARKET:CN dp_id rows.

    Returns 7-tuple rows in the standard ``upsert_realtime`` shape. The
    upstream call is wrapped in TTL cache (``_CLS_CACHE_TTL_S``) so we
    don't slam the endpoint on every collector tick. Cache hits return a
    shallow copy of the previous rows (callers may mutate).

    Failure mode: on any error (akshare missing, network 502, JSON
    decode) the function returns three Inactive rows so downstream
    overlays still see ``MARKET:CN`` coverage exists.
    """

    cached_ts = int(_LAST_CLS_FETCH.get("ts") or 0)
    cached_rows = _LAST_CLS_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _CLS_CACHE_TTL_S and cached_rows:
        log.debug("[akshare] cls cache hit (age=%ds, rows=%d)",
                  now - cached_ts, len(cached_rows))
        return list(cached_rows)

    records: list[dict] | None = None
    direct_error: str | None = None
    try:
        records = _fetch_cls_telegraph_records_direct()
    except Exception as e:  # noqa: BLE001 — signed web endpoint can change
        direct_error = str(e)
        log.warning("[akshare] cls direct web fetch failed: %s", e)

    if records is None:
        try:
            import akshare as ak  # type: ignore
        except ImportError as e:
            log.warning(
                "[akshare] cls telegraph skipped — akshare missing: %s", e
            )
            reason = f"akshare_missing: {e}"
            if direct_error:
                reason = f"cls_direct_error: {direct_error}; {reason}"
            return _emit_inactive_cls_rows(now, reason)

        # akshare renamed ``stock_telegraph_cls`` → ``stock_info_global_cls``
        # somewhere around 1.16; we accept either to stay forward/backward
        # compatible with whatever version the host ships.
        fn = getattr(ak, "stock_info_global_cls", None) \
            or getattr(ak, "stock_telegraph_cls", None)
        if fn is None:
            log.warning("[akshare] cls telegraph symbol missing on akshare module")
            reason = "akshare_symbol_missing"
            if direct_error:
                reason = f"cls_direct_error: {direct_error}; {reason}"
            return _emit_inactive_cls_rows(now, reason)

        try:
            df = _ak_call("stock_info_global_cls", fn)
        except Exception as e:  # noqa: BLE001 — upstream can 502 / drop JSON
            log.warning("[akshare] stock_info_global_cls failed: %s", e)
            reason = f"upstream_error: {e}"
            if direct_error:
                reason = f"cls_direct_error: {direct_error}; {reason}"
            return _emit_inactive_cls_rows(now, reason)

        if df is None or len(df) == 0:
            log.warning("[akshare] cls telegraph returned empty frame")
            return _emit_inactive_cls_rows(now, "empty_frame")

        # Convert to records once; iterate three times for the three buckets.
        try:
            records = df.to_dict(orient="records")
        except Exception as e:  # noqa: BLE001 — defensive against weird DF shape
            log.warning("[akshare] cls to_dict failed: %s", e)
            return _emit_inactive_cls_rows(now, f"frame_decode: {e}")

    # Pre-compute headline objects + 24h-window filter once.
    cutoff = now - _CLS_TELEGRAPH_LOOKBACK_S
    enriched: list[tuple[dict, str]] = []  # (headline_dict, search_text)
    for rec in records:
        publish_epoch = _parse_cls_publish_epoch(
            rec.get("发布日期"), rec.get("发布时间"),
        )
        # If we can't parse the timestamp, fall through with epoch=None so
        # the headline is dropped from the 24h window (conservative).
        if publish_epoch is None or publish_epoch < cutoff:
            continue
        headline = _headline_from_record(rec, publish_epoch)
        # Search text = title + body (CLS sometimes hides the keyword in
        # the body, e.g. 标题='【电报解读】…' 内容='证监会处罚…').
        search_text = " ".join(filter(None, [
            str(rec.get("标题") or ""),
            str(rec.get("内容") or ""),
        ]))
        enriched.append((headline, search_text))

    as_of = _as_of_iso()
    rows: list[tuple] = []

    # ---- L9.media.report — full flow + conservative media tilt ----
    # A successful decoded CLS window is valid even when no headline has a safe
    # direction; count_24h remains descriptive, while net_media_score is the
    # only field the scorer is allowed to consume.
    report_headlines = [h for h, _ in enriched[:_CLS_TELEGRAPH_MAX_HEADLINES]]
    media_tilts = [
        0 if (
            _match_any_keyword(text, _POLICY_KEYWORDS)
            or _match_any_keyword(text, _RISK_KEYWORDS)
        ) else _media_tilt_from_text(text)
        for _, text in enriched
    ]
    media_positive_count = sum(1 for tilt in media_tilts if tilt > 0)
    media_negative_count = sum(1 for tilt in media_tilts if tilt < 0)
    media_net_score = media_positive_count - media_negative_count
    rows.append((
        _CLS_TELEGRAPH_MARKET, "L9.media.report",
        json.dumps({
            "count_24h": len(enriched),
            "event_active": bool(media_positive_count or media_negative_count),
            "positive_media_count": media_positive_count,
            "negative_media_count": media_negative_count,
            "net_media_score": media_net_score,
            "classified_media_count": media_positive_count + media_negative_count,
            "top_headlines": report_headlines,
            "as_of": as_of,
        }, ensure_ascii=False),
        "Known",
        0.6, "akshare:stock_info_global_cls", now,
    ))

    # ---- L9.industry.policy_change — policy keywords ----
    # Zero policy hits is a decoded no-policy-change observation. Hits are only
    # directional when high-precision positive/negative policy words classify
    # cleanly; generic policy/legal wording remains Known-neutral.
    policy_pairs = [
        (h, text) for h, text in enriched
        if _match_any_keyword(text, _POLICY_KEYWORDS)
    ]
    policy_hits = [h for h, _ in policy_pairs]
    policy_headlines = policy_hits[:_CLS_TELEGRAPH_MAX_HEADLINES]
    policy_tilts = [_policy_tilt_from_text(text) for _, text in policy_pairs]
    policy_positive_count = sum(1 for tilt in policy_tilts if tilt > 0)
    policy_negative_count = sum(1 for tilt in policy_tilts if tilt < 0)
    policy_net_score = policy_positive_count - policy_negative_count
    rows.append((
        _CLS_TELEGRAPH_MARKET, "L9.industry.policy_change",
        json.dumps({
            "count_24h": len(policy_hits),
            "event_active": bool(policy_hits),
            "positive_policy_count": policy_positive_count,
            "negative_policy_count": policy_negative_count,
            "net_policy_score": policy_net_score,
            "top_headlines": policy_headlines,
            "as_of": as_of,
        }, ensure_ascii=False),
        "Known",
        0.55, "akshare:stock_info_global_cls", now,
    ))

    # ---- L9.industry.compete_risk — risk keywords ----
    # Zero keyword hits is a decoded no-risk observation, not missing data.
    risk_hits = [h for h, text in enriched
                 if _match_any_keyword(text, _RISK_KEYWORDS)]
    risk_headlines = risk_hits[:_CLS_TELEGRAPH_MAX_HEADLINES]
    rows.append((
        _CLS_TELEGRAPH_MARKET, "L9.industry.compete_risk",
        json.dumps({
            "count_24h": len(risk_hits),
            "event_active": bool(risk_hits),
            "top_headlines": risk_headlines,
            "as_of": as_of,
        }, ensure_ascii=False),
        "Known",
        0.55, "akshare:stock_info_global_cls", now,
    ))

    # ---- L9.macro.geo — geopolitical keywords ----
    # Zero geo hits is a decoded no-geo-event observation. The dp_id is not
    # score-participating itself; downstream candidate generation uses it as
    # dependency evidence for black-swan shock classification.
    geo_hits = [h for h, text in enriched
                if _match_any_keyword(text, _GEO_KEYWORDS)]
    geo_headlines = geo_hits[:_CLS_TELEGRAPH_MAX_HEADLINES]
    rows.append((
        _CLS_TELEGRAPH_MARKET, "L9.macro.geo",
        json.dumps({
            "count_24h": len(geo_hits),
            "event_active": bool(geo_hits),
            "top_headlines": geo_headlines,
            "as_of": as_of,
        }, ensure_ascii=False),
        "Known",
        0.55, "akshare:stock_info_global_cls", now,
    ))

    _LAST_CLS_FETCH["ts"] = now
    _LAST_CLS_FETCH["rows"] = list(rows)
    log.info("[akshare] cls telegraph: %d total in 24h, %d policy, %d risk, "
             "%d geo → %d rows (next fetch in %ds)",
             len(enriched), len(policy_hits), len(risk_hits), len(geo_hits),
             len(rows),
             _CLS_CACHE_TTL_S)
    return rows


# ---------------------------------------------------------------------------
# Safe converters
# ---------------------------------------------------------------------------


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # filter NaN
    if f != f:  # noqa: PLR0124
        return None
    return f


def _safe_int(v) -> int | None:
    f = _safe_float(v)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# X2 industry-level fetchers (previously declared but silent in collector)
# ---------------------------------------------------------------------------
#
# Three dp_ids — ``L0.cost.raw_material``, ``L0.cost.energy_logistics``,
# ``L0.sentiment.sector_heat`` — were registered in SUPPORTED_DP_IDS but
# emitted 0 rows pre-X2 because the fetch path was a stub. The X2 wiring
# below pulls real akshare data and emits one row per *mapped* industry
# (sentinel ts_code = ``INDUSTRY:<id>``).
#
# Three TTL caches (10 min) keep us under akshare's flaky upstream so the
# per-cycle collector tick doesn't spam the endpoints (futures_main_sina
# in particular goes through Sina's HTTP redirector and is rate-limited).

_X2_CACHE_TTL_S = 600
_LAST_COMMODITY_FETCH: dict[str, object] = {"ts": 0, "rows": []}
_LAST_LOGISTICS_FETCH: dict[str, object] = {"ts": 0, "rows": []}
_LAST_SECTOR_HEAT_FETCH: dict[str, object] = {"ts": 0, "rows": []}


def _load_industry_yaml(filename: str) -> dict:
    """Load a ``config/<filename>`` YAML and return the ``industries`` dict.

    Returns an empty dict on missing file / parse failure so the caller
    gracefully no-ops without crashing the collector."""

    from pathlib import Path
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    cfg = Path(__file__).resolve().parent.parent.parent / "config" / filename
    if not cfg.exists():
        return {}
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] _load_industry_yaml(%s) parse failed: %s",
                    filename, e)
        return {}
    industries = data.get("industries") or {}
    if not isinstance(industries, dict):
        return {}
    return industries


def _active_industry_ids_akshare() -> list[str]:
    """Same selector as ``tushare_source._active_industry_ids`` — duplicated
    so akshare module stays independent. Reads ``graph_status=present``
    industries from ``config/mvp20.industries.yaml``."""

    from pathlib import Path
    try:
        import yaml  # type: ignore
    except ImportError:
        return []
    cfg = Path(__file__).resolve().parent.parent.parent / "config" / "mvp20.industries.yaml"
    if not cfg.exists():
        return []
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] industries.yaml parse failed: %s", e)
        return []
    out = []
    for entry in data.get("industries") or []:
        if isinstance(entry, dict) and entry.get("graph_status") == "present":
            iid = entry.get("id")
            if iid:
                out.append(str(iid))
    return out


def fetch_raw_material_batch(now: int) -> list[tuple]:
    """``L0.cost.raw_material`` — per active industry, Sina-futures
    continuous-main close + day-over-day change for the mapped commodities.

    Mapping lives in ``config/industry_to_commodity.yaml``. For each
    industry's commodity list we pull ``ak.futures_main_sina(symbol=...)``,
    take the last 2 rows (latest + prior), compute ``pct_change``, then
    aggregate (avg) across all mapped commodities per industry. Industries
    with no mapping are silently skipped (the YAML marks them with ``null``
    + a TODO note).

    Returns one row per *mapped* industry; sentinel ts_code is
    ``INDUSTRY:<id>``. Confidence 0.6 because commodity → BOM cost is a
    proxy not a direct exposure measure.
    """

    cached_ts = int(_LAST_COMMODITY_FETCH.get("ts") or 0)
    cached_rows = _LAST_COMMODITY_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _X2_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    mapping = _load_industry_yaml("industry_to_commodity.yaml")
    if not mapping:
        return []
    active = set(_active_industry_ids_akshare())
    # Collect all unique symbols across all industries so we only hit
    # akshare once per symbol per cycle.
    symbols_needed: set[str] = set()
    industry_symbols: dict[str, list[str]] = {}
    for industry_id, syms in mapping.items():
        if industry_id not in active:
            continue
        if not syms:
            continue
        # Filter out None entries and normalise to list of str
        clean = [str(s) for s in syms if s]
        if not clean:
            continue
        industry_symbols[industry_id] = clean
        symbols_needed.update(clean)
    if not industry_symbols:
        return []

    try:
        import akshare as ak  # type: ignore
    except ImportError as e:
        log.warning("[akshare] futures_main_sina skipped — akshare missing: %s", e)
        return []

    # Per-symbol fetch with throttle. The Sina futures endpoint returns
    # ~5K historical rows by default; we only need the tail.
    per_symbol: dict[str, dict] = {}
    for sym in sorted(symbols_needed):
        try:
            df = _ak_call("futures_main_sina",
                          lambda: ak.futures_main_sina(symbol=sym))
        except Exception as e:  # noqa: BLE001
            log.warning("[akshare] futures_main_sina %s failed: %s", sym, e)
            continue
        if df is None or len(df) < 2:
            continue
        try:
            recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        except Exception:  # noqa: BLE001
            continue
        if len(recs) < 2:
            continue
        latest = recs[-1]
        prior = recs[-2]
        cur_close = _safe_float(latest.get("收盘价") or latest.get("close"))
        prev_close = _safe_float(prior.get("收盘价") or prior.get("close"))
        if cur_close is None or prev_close is None or prev_close == 0:
            continue
        pct_change = (cur_close - prev_close) / prev_close * 100.0
        per_symbol[sym] = {
            "symbol": sym,
            "close": cur_close,
            "pct_change": round(pct_change, 3),
            "date": _stringify_date(latest.get("日期") or latest.get("date")),
        }
        time.sleep(0.15)

    if not per_symbol:
        return []

    rows: list[tuple] = []
    for industry_id, syms in industry_symbols.items():
        present = [per_symbol[s] for s in syms if s in per_symbol]
        if not present:
            continue
        avg_pct = sum(p["pct_change"] for p in present) / len(present)
        payload = {
            "commodities": present,
            "avg_pct_change": round(avg_pct, 3),
            "symbols_resolved": len(present),
            "symbols_requested": len(syms),
            "latest_date": present[0]["date"],
            "unit": "Sina futures continuous main close (CNY)",
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.cost.raw_material",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.6, "akshare:futures_main_sina", now,
        ))

    _LAST_COMMODITY_FETCH["ts"] = now
    _LAST_COMMODITY_FETCH["rows"] = list(rows)
    log.info("[akshare] L0.cost.raw_material: %d industries emitted (next "
             "fetch in %ds)", len(rows), _X2_CACHE_TTL_S)
    return rows


def fetch_energy_logistics_batch(now: int) -> list[tuple]:
    """``L0.cost.energy_logistics`` — MARKET:CN row combining 上海原油
    (SC0 day-over-day change) and Baltic Dry Index (BDI day-over-day).

    BDI fetch uses ``ak.macro_shipping_bdi()`` which currently loads ~19
    progress-bar batches and can take ~30-60s; the 10-min TTL cache mutes
    the cost. SC0 fetch uses the same Sina-futures path as raw_material so
    we accept its rate limits. If either upstream fails we still emit a
    single ``MARKET:CN`` row with whatever components were obtained — the
    payload always tells consumers which fields are ``None``.
    """

    cached_ts = int(_LAST_LOGISTICS_FETCH.get("ts") or 0)
    cached_rows = _LAST_LOGISTICS_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _X2_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    try:
        import akshare as ak  # type: ignore
    except ImportError as e:
        log.warning("[akshare] energy_logistics skipped — akshare missing: %s", e)
        return []

    crude_pct = None
    crude_close = None
    crude_date = None
    try:
        df = _ak_call("futures_main_sina",
                      lambda: ak.futures_main_sina(symbol="SC0"))
        if df is not None and len(df) >= 2:
            recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
            latest = recs[-1]
            prior = recs[-2]
            cur_close = _safe_float(latest.get("收盘价") or latest.get("close"))
            prev_close = _safe_float(prior.get("收盘价") or prior.get("close"))
            if cur_close is not None and prev_close not in (None, 0):
                crude_pct = round((cur_close - prev_close) / prev_close * 100.0, 3)
                crude_close = cur_close
                crude_date = _stringify_date(
                    latest.get("日期") or latest.get("date"))
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] futures_main_sina SC0 failed: %s", e)

    bdi_pct = None
    bdi_close = None
    bdi_date = None
    try:
        df = _ak_call("macro_shipping_bdi", ak.macro_shipping_bdi)
        if df is not None and len(df) >= 2:
            recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
            # BDI frame is date-ascending; take last 2 rows
            latest = recs[-1]
            prior = recs[-2]
            cur = _safe_float(latest.get("最新值") or latest.get("BDI"))
            prev = _safe_float(prior.get("最新值") or prior.get("BDI"))
            if cur is not None and prev not in (None, 0):
                bdi_pct = round((cur - prev) / prev * 100.0, 3)
                bdi_close = cur
                bdi_date = _stringify_date(
                    latest.get("日期") or latest.get("date"))
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] macro_shipping_bdi failed: %s", e)

    if crude_pct is None and bdi_pct is None:
        return []

    payload = {
        "crude_pct": crude_pct,
        "crude_close_cny_per_bbl": crude_close,
        "crude_latest_date": crude_date,
        "bdi_pct": bdi_pct,
        "bdi_close": bdi_close,
        "bdi_latest_date": bdi_date,
        "scope": "A_share_market",
    }
    rows = [(
        "MARKET:CN", "L0.cost.energy_logistics",
        json.dumps(payload, ensure_ascii=False),
        "Known", 0.65, "akshare:futures_main_sina+macro_shipping_bdi", now,
    )]
    _LAST_LOGISTICS_FETCH["ts"] = now
    _LAST_LOGISTICS_FETCH["rows"] = list(rows)
    log.info("[akshare] L0.cost.energy_logistics: 1 MARKET:CN row "
             "(crude_pct=%s, bdi_pct=%s)", crude_pct, bdi_pct)
    return rows


def fetch_sector_heat_batch(now: int) -> list[tuple]:
    """``L0.sentiment.sector_heat`` — per active industry, THS 行业板块
    snapshot (涨跌幅, 净流入, 领涨股) aggregated across the boards mapped
    in ``config/industry_to_em_board.yaml``.

    Source: ``ak.stock_board_industry_summary_ths()`` returns ~90 rows
    (one per THS 行业板块). The fetcher filters to mapped boards per
    industry and aggregates (avg 涨跌幅, sum 净流入, pick the strongest
    领涨股). EM endpoint is intentionally NOT used here because it's
    currently flaky (RemoteDisconnected ~30% of the time); the YAML
    forward-allows an ``em_boards`` extension when the upstream stabilises.

    Industries with no mapping (HK_CN_INTERNET 等) are skipped.
    """

    cached_ts = int(_LAST_SECTOR_HEAT_FETCH.get("ts") or 0)
    cached_rows = _LAST_SECTOR_HEAT_FETCH.get("rows") or []
    if cached_ts and (now - cached_ts) < _X2_CACHE_TTL_S and cached_rows:
        return list(cached_rows)

    mapping = _load_industry_yaml("industry_to_em_board.yaml")
    if not mapping:
        return []
    active = set(_active_industry_ids_akshare())
    industry_boards: dict[str, list[str]] = {}
    for industry_id, boards in mapping.items():
        if industry_id not in active:
            continue
        if not boards:
            continue
        clean = [str(b) for b in boards if b]
        if not clean:
            continue
        industry_boards[industry_id] = clean
    if not industry_boards:
        return []

    try:
        import akshare as ak  # type: ignore
    except ImportError as e:
        log.warning("[akshare] sector_heat skipped — akshare missing: %s", e)
        return []

    # THS upstream is occasionally transient ("No tables found" / 502) —
    # one retry with a 2s back-off recovers ~80% of those.
    df = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            df = _ak_call("stock_board_industry_summary_ths",
                          ak.stock_board_industry_summary_ths)
            if df is not None and len(df) > 0:
                last_err = None
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(2.0)
    if df is None or len(df) == 0:
        if last_err is not None:
            log.warning(
                "[akshare] stock_board_industry_summary_ths failed after retry: %s",
                last_err,
            )
        return []

    try:
        recs = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] sector summary to_dict failed: %s", e)
        return []

    # Index THS boards by name for O(1) lookup. Column names: 板块, 涨跌幅,
    # 总成交量, 总成交额, 净流入, 上涨家数, 下跌家数, 均价, 领涨股,
    # 领涨股-最新价, 领涨股-涨跌幅.
    by_name: dict[str, dict] = {}
    for rec in recs:
        name = rec.get("板块") or rec.get("name")
        if name:
            by_name[str(name)] = rec

    as_of = _as_of_iso()
    rows: list[tuple] = []
    for industry_id, boards in industry_boards.items():
        matched: list[dict] = []
        for b in boards:
            r = by_name.get(b)
            if r is None:
                continue
            change_pct = _safe_float(r.get("涨跌幅"))
            fund_inflow = _safe_float(r.get("净流入"))
            leader_name = r.get("领涨股")
            leader_pct = _safe_float(r.get("领涨股-涨跌幅"))
            matched.append({
                "board_name": b,
                "change_pct": change_pct,
                "fund_inflow_cny": fund_inflow,
                "leader_stock": leader_name,
                "leader_stock_pct": leader_pct,
            })
        if not matched:
            continue
        # Aggregate: average 涨跌幅, sum 净流入, max-leader-pct as
        # "top leader" for the row.
        avg_change = sum(
            m["change_pct"] for m in matched if m["change_pct"] is not None
        )
        n_change = sum(1 for m in matched if m["change_pct"] is not None)
        avg_change_pct = (avg_change / n_change) if n_change else None
        total_inflow = sum(
            m["fund_inflow_cny"] for m in matched
            if m["fund_inflow_cny"] is not None
        )
        # Pick the board whose leader posted the largest pct gain (proxy
        # for "this industry's strongest headline today").
        leaders = [m for m in matched if m["leader_stock_pct"] is not None]
        top_leader = max(leaders, key=lambda m: m["leader_stock_pct"]) \
            if leaders else None
        payload = {
            "boards": matched,
            "avg_change_pct": (round(avg_change_pct, 3)
                               if avg_change_pct is not None else None),
            "total_fund_inflow": total_inflow,
            "top_leader": top_leader,
            "as_of": as_of,
        }
        rows.append((
            f"INDUSTRY:{industry_id}", "L0.sentiment.sector_heat",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.65, "akshare:stock_board_industry_summary_ths", now,
        ))

    _LAST_SECTOR_HEAT_FETCH["ts"] = now
    _LAST_SECTOR_HEAT_FETCH["rows"] = list(rows)
    log.info("[akshare] L0.sentiment.sector_heat: %d industries emitted "
             "(next fetch in %ds)", len(rows), _X2_CACHE_TTL_S)
    return rows


# ---------------------------------------------------------------------------
# Tier-2 / Tier-3 stubs (declared in SUPPORTED_DP_IDS but not yet fetched)
# ---------------------------------------------------------------------------


def fetch_tier2_stubs(*_args, **_kwargs) -> list[tuple]:
    """Deprecated stub for Tier-2/3 industry-level dp_ids.

    Pre-X2 this was a TODO no-op. X2 replaced it with three real
    fetchers (``fetch_raw_material_batch`` /
    ``fetch_energy_logistics_batch`` / ``fetch_sector_heat_batch``)
    invoked from ``fetch_batch``. We keep this symbol exported for
    backward compatibility but it now returns an empty list — call sites
    should migrate to the dedicated batch fetchers above.
    """

    return []


# ---------------------------------------------------------------------------
# Bucket A: per-A-share fund-flow outflow + block-trade event signals.
# ---------------------------------------------------------------------------
#
# Two dp_ids added in this batch:
#
#   * ``L8.cap.outflow_cut`` — 5-day main-fund (主力资金) cumulative net
#     outflow. Single market-wide pull from THS via
#     ``ak.stock_fund_flow_individual(symbol='5日排行')`` (free, no token)
#     followed by a per-stock dict lookup. Signal fires when the cumulative
#     net inflow string parses to ≤ ``-1e8`` 元 (CNY).
#
#   * ``L9.capital.etf_block`` — last-5-trade-day 大宗交易 (block trade)
#     events. Aggregates daily ``ak.stock_dzjy_mrmx`` snapshots; per-stock
#     event count + total ``成交额`` rolled up into ``L9.capital.etf_block``.
#
# Both fetchers share a 10-min TTL cache (matching the X2 cadence) so a
# single cycle of the collector pings each endpoint at most once. Failure
# is per-fetcher isolated — losing the THS pull leaves the dzjy fetcher
# free to run, and vice versa.
#
# Note on the "rank" endpoint we did NOT use: as of 2026-05,
# ``stock_individual_fund_flow_rank`` raises ``JSONDecodeError`` on the
# very first byte (upstream returns HTML). The THS-backed
# ``stock_fund_flow_individual`` returns a string-formatted ``资金流入净额``
# (e.g. ``"-1.23亿"``) which we parse via ``_parse_cn_amount``.

_BUCKET_A_CACHE_TTL_S = 600
_LAST_OUTFLOW_FETCH: dict[str, object] = {"ts": 0, "rows": [], "key": ""}
_LAST_BLOCK_FETCH: dict[str, object] = {"ts": 0, "rows": [], "key": ""}


def _parse_cn_amount(v) -> float | None:
    """Parse a CN-style amount string (``"-1.23亿"`` / ``"4.44亿"`` /
    ``"2832.86万"``) into a plain ``float`` (元).

    Returns ``None`` if input is empty / unparseable. Numeric inputs pass
    through ``_safe_float`` unchanged.
    """

    if v is None:
        return None
    # Numeric passthrough (already in 元)
    if isinstance(v, (int, float)):
        return _safe_float(v)
    s = str(v).strip()
    if not s:
        return None
    if s in {"--", "-", "—"}:
        return None
    # Strip commas / spaces
    s = s.replace(",", "").replace(" ", "")
    mult = 1.0
    suffix = s[-1]
    if suffix == "亿":
        mult = 1e8
        s = s[:-1]
    elif suffix == "万":
        mult = 1e4
        s = s[:-1]
    elif suffix == "%":
        # Caller should call _safe_float instead; defensive only.
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _fetch_main_fund_flow_5d_snapshot() -> dict[str, dict]:
    """One market-wide pull of THS ``5日排行`` 个股资金流, keyed by 6-digit
    A-share code so the per-stock lookup is O(1).

    Returns ``{}`` on any upstream failure — the caller will then emit
    Inactive rows.
    """

    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return {}
    try:
        df = _ak_call("stock_fund_flow_individual",
                      lambda: ak.stock_fund_flow_individual(symbol="5日排行"))
    except Exception as e:  # noqa: BLE001
        log.warning("[akshare] stock_fund_flow_individual(5日排行) failed: %s", e)
        return {}
    if df is None or len(df) == 0:
        return {}
    out: dict[str, dict] = {}
    for rec in df.to_dict(orient="records"):
        code_raw = rec.get("股票代码") or rec.get("代码")
        if code_raw is None:
            continue
        # akshare returns the 股票代码 as int for some indicator variants —
        # left-pad to 6 digits so we match the to_a_share_code output.
        code = str(code_raw).strip()
        if code.isdigit():
            code = code.zfill(6)
        if not code:
            continue
        # Parse the CN-formatted 资金流入净额 (string like '-1.23亿')
        net_amount = _parse_cn_amount(
            rec.get("资金流入净额") or rec.get("主力净流入-净额"),
        )
        # 阶段涨跌幅 may also carry a '%' suffix
        pct_str = rec.get("阶段涨跌幅") or rec.get("主力净流入-净占比")
        pct = None
        if isinstance(pct_str, (int, float)):
            pct = _safe_float(pct_str)
        elif isinstance(pct_str, str):
            pct = _safe_float(pct_str.replace("%", "").strip()) \
                if pct_str.strip() else None
        out[code] = {
            "main_net_5d": net_amount,
            "stage_pct_change": pct,
            "name": rec.get("股票简称"),
            "last_price": _safe_float(rec.get("最新价")),
        }
    return out


def fetch_l8_cap_outflow_cut(a_codes: list[str], now: int) -> list[tuple]:
    """``L8.cap.outflow_cut`` — per A-share, 5-day 主力资金 cumulative
    net outflow.

    Pulls the market-wide THS ``5日排行`` 个股资金流 snapshot once per
    cycle (10-min TTL cache) and looks up each requested ``ts_code`` in
    constant time. Threshold for the ``signal=True`` alert:

      * ``main_net_5d ≤ -1e8`` 元 (≥ 100M CNY net outflow over 5d), or
      * ``stage_pct_change ≤ -10.0`` (5d stage drawdown >= 10%)

    Emits ``Known`` for stocks present in the snapshot and ``Inactive``
    for stocks missing from the THS top list (those are typically
    low-turnover names — absence is informative, not an error).
    """

    if not a_codes:
        return []
    cache_key = ",".join(sorted(a_codes))
    cached_ts = int(_LAST_OUTFLOW_FETCH.get("ts") or 0)
    cached_key = str(_LAST_OUTFLOW_FETCH.get("key") or "")
    cached_rows = _LAST_OUTFLOW_FETCH.get("rows") or []
    if (cached_ts and (now - cached_ts) < _BUCKET_A_CACHE_TTL_S
            and cached_rows and cached_key == cache_key):
        return list(cached_rows)

    snapshot = _fetch_main_fund_flow_5d_snapshot()
    as_of = _as_of_iso()
    rows: list[tuple] = []
    for ts_code in a_codes:
        sec = to_a_share_code(ts_code)
        if not sec:
            continue
        entry = snapshot.get(sec)
        if entry is None:
            rows.append((
                ts_code, "L8.cap.outflow_cut",
                json.dumps({
                    "signal": False,
                    "reason": "not_in_ths_5d_rank_top",
                    "as_of": as_of,
                }, ensure_ascii=False),
                "Inactive", 0.4,
                "akshare:stock_fund_flow_individual.5d", now,
            ))
            continue
        main_net = entry.get("main_net_5d")
        stage_pct = entry.get("stage_pct_change")
        signal = (
            (main_net is not None and main_net <= -1e8)
            or (stage_pct is not None and stage_pct <= -10.0)
        )
        status = "Known" if signal else "Inactive"
        payload = {
            "signal": signal,
            "main_net_5d": main_net,
            "stage_pct_change_5d": stage_pct,
            "last_price": entry.get("last_price"),
            "alert_severity": "WARN" if signal else None,
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L8.cap.outflow_cut",
            json.dumps(payload, ensure_ascii=False),
            status, 0.65,
            "akshare:stock_fund_flow_individual.5d", now,
        ))
    _LAST_OUTFLOW_FETCH["ts"] = now
    _LAST_OUTFLOW_FETCH["rows"] = list(rows)
    _LAST_OUTFLOW_FETCH["key"] = cache_key
    log.info(
        "[akshare] L8.cap.outflow_cut: %d rows (snapshot=%d, signals=%d)",
        len(rows), len(snapshot),
        sum(1 for r in rows if r[3] == "Known"),
    )
    return rows


def _fetch_dzjy_events_last5(
    max_trade_days: int = 5,
    max_calendar_days: int = 12,
    reference_date: date | datetime | str | None = None,
) -> tuple[dict[str, list[dict]], bool]:
    """Aggregate last ``max_trade_days`` of 大宗交易 events keyed by
    6-digit 证券代码.

    The ``ak.stock_dzjy_mrmx`` endpoint is a daily snapshot — weekends /
    holidays return ``None`` (which the underlying akshare wrapper
    surfaces as a ``TypeError`` about subscripting None). We walk back
    calendar days, ignoring days that produce no data, until we have
    accumulated ``max_trade_days`` worth of records OR exceeded
    ``max_calendar_days`` of look-back. The boolean marks whether at least one
    upstream response was successfully decoded, so callers can distinguish
    "valid zero events" from "all endpoint calls failed".
    """

    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return {}, False

    events: dict[str, list[dict]] = {}
    source_ok = False
    base_date = _normalise_dzjy_reference_date(reference_date)
    trade_days_seen = 0
    for d_back in range(0, max_calendar_days + 1):
        date_str = (base_date - timedelta(days=d_back)).strftime("%Y%m%d")
        try:
            df = _ak_call("stock_dzjy_mrmx",
                          lambda: ak.stock_dzjy_mrmx(start_date=date_str, end_date=date_str))
        except Exception:  # noqa: BLE001
            # NoneType subscripting on weekends, network errors, or layout
            # drifts all land here — silently skip and keep walking back.
            continue
        if df is None:
            continue
        source_ok = True
        if len(df) == 0:
            trade_days_seen += 1
            if trade_days_seen >= max_trade_days:
                break
            continue
        trade_days_seen += 1
        for rec in df.to_dict(orient="records"):
            code_raw = (
                rec.get("证券代码") or rec.get("代码") or rec.get("股票代码")
            )
            if code_raw is None:
                continue
            code = str(code_raw).strip()
            if code.isdigit():
                code = code.zfill(6)
            if not code:
                continue
            events.setdefault(code, []).append({
                "date": _stringify_date(rec.get("交易日期")) or date_str,
                "price": _safe_float(rec.get("成交价")),
                "volume": _safe_float(rec.get("成交量")),
                "amount": _safe_float(rec.get("成交额")),
                "buyer": rec.get("买方营业部"),
                "seller": rec.get("卖方营业部"),
            })
        if trade_days_seen >= max_trade_days:
            break
    return events, source_ok


def _normalise_dzjy_reference_date(
    reference_date: date | datetime | str | None,
) -> datetime:
    if reference_date is None:
        return datetime.now()
    if isinstance(reference_date, datetime):
        return reference_date
    if isinstance(reference_date, date):
        return datetime.combine(reference_date, datetime.min.time())
    value = str(reference_date).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def fetch_l9_capital_etf_block(
    a_codes: list[str],
    now: int,
    *,
    reference_date: date | datetime | str | None = None,
) -> list[tuple]:
    """``L9.capital.etf_block`` — per A-share, count + total amount of
    大宗交易 events in the last 5 trade days.

    Aggregates daily ``ak.stock_dzjy_mrmx`` snapshots once per cycle
    (10-min TTL cache), then per-stock lookup. Stocks with zero recent
    events emit ``Known`` neutral; stocks with at least one event emit
    ``Known`` plus a payload that includes total ``成交额`` and a
    sample of up to 5 events. If every upstream request fails, rows remain
    ``Inactive`` with a reason instead of pretending the no-event state is known.
    """

    if not a_codes:
        return []
    base_date = _normalise_dzjy_reference_date(reference_date)
    cache_key = f"{','.join(sorted(a_codes))}|{base_date:%Y%m%d}"
    cached_ts = int(_LAST_BLOCK_FETCH.get("ts") or 0)
    cached_key = str(_LAST_BLOCK_FETCH.get("key") or "")
    cached_rows = _LAST_BLOCK_FETCH.get("rows") or []
    if (cached_ts and (now - cached_ts) < _BUCKET_A_CACHE_TTL_S
            and cached_rows and cached_key == cache_key):
        return list(cached_rows)

    block_by_code, source_ok = _fetch_dzjy_events_last5(reference_date=base_date)
    as_of = _as_of_iso()
    rows: list[tuple] = []
    for ts_code in a_codes:
        sec = to_a_share_code(ts_code)
        if not sec:
            continue
        events = block_by_code.get(sec) or []
        if not events:
            payload = {
                "events_count": 0,
                "event_active": False,
                "as_of": as_of,
            }
            if not source_ok:
                payload["reason"] = "upstream_no_valid_dzjy_days"
            rows.append((
                ts_code, "L9.capital.etf_block",
                json.dumps(payload, ensure_ascii=False),
                "Known" if source_ok else "Inactive",
                0.6 if source_ok else 0.5,
                "akshare:stock_dzjy_mrmx", now,
            ))
            continue
        total_amount = sum(
            e["amount"] for e in events if e["amount"] is not None
        )
        total_volume = sum(
            e["volume"] for e in events if e["volume"] is not None
        )
        avg_price = None
        priced = [e["price"] for e in events if e["price"] is not None]
        if priced:
            avg_price = round(sum(priced) / len(priced), 4)
        payload = {
            "events_count": len(events),
            "event_active": True,
            "total_amount_cny": total_amount,
            "total_volume": total_volume,
            "avg_price": avg_price,
            "events_sample": events[:5],
            "as_of": as_of,
        }
        rows.append((
            ts_code, "L9.capital.etf_block",
            json.dumps(payload, ensure_ascii=False),
            "Known", 0.7,
            "akshare:stock_dzjy_mrmx", now,
        ))
    _LAST_BLOCK_FETCH["ts"] = now
    _LAST_BLOCK_FETCH["rows"] = list(rows)
    _LAST_BLOCK_FETCH["key"] = cache_key
    log.info(
        "[akshare] L9.capital.etf_block: %d rows "
        "(market_events=%d, known_stocks=%d)",
        len(rows), sum(len(v) for v in block_by_code.values()),
        sum(1 for r in rows if r[3] == "Known"),
    )
    return rows


# ---------------------------------------------------------------------------
# Batch entry point used by collector.py
# ---------------------------------------------------------------------------


def fetch_batch(
    constituents: Iterable[dict],
    tick: int = 0,
) -> list[tuple]:
    """Top-level batch fetcher. Returns the standard 7-tuple list ready for
    ``mvp20.storage.upsert_realtime``.

    Only A-share constituents are touched today. HK + US are skipped
    silently (the Futu / FMP sources cover them). Each Tier-1 fetcher
    runs independently so one endpoint outage doesn't block the others.
    """

    try:
        import akshare  # type: ignore  # noqa: F401 (presence check only)
    except ImportError as e:
        log.warning("[akshare] akshare not installed — skipping batch: %s", e)
        return []

    a_codes = [c["ts_code"] for c in constituents
               if c.get("ts_code") and is_a_share(c["ts_code"])]

    now = _now_epoch()
    rows: list[tuple] = []

    # Per-stock Tier-1 fetchers — only run when we have A-share constituents.
    #
    # NOTE: intraday_announcement / media_social+theme / social_buzz /
    # l8_cap_outflow_cut were MOVED to Tushare
    # (``tushare_source.fetch_akshare_replacement_batch``) and are intentionally
    # NOT run here — emitting them from akshare would clobber the Tushare rows
    # via the (ts_code, dp_id) UPSERT primary key. The fetcher functions remain
    # defined for unit-test/back-compat but are no longer wired into the batch.
    if a_codes:
        fetchers = (
            ("intraday_news",         lambda: fetch_intraday_news(a_codes, now)),
            # Bucket A append — block-trade signal (outflow_cut moved to Tushare).
            ("l9_capital_etf_block",  lambda: fetch_l9_capital_etf_block(a_codes, now)),
        )
        for name, fn in fetchers:
            try:
                new_rows = fn()
                rows.extend(new_rows)
                log.info("[akshare] %s → %d rows", name, len(new_rows))
            except Exception as exc:  # noqa: BLE001
                log.warning("[akshare] %s FAILED: %s", name, exc)

    # Market-level CLS telegraph (MARKET:CN sentinel) — runs regardless of
    # the per-stock universe so the catalyst dp_ids are always populated.
    try:
        cls_rows = fetch_cls_telegraph_batch(now)
        rows.extend(cls_rows)
        log.info("[akshare] cls_telegraph → %d rows", len(cls_rows))
    except Exception as exc:  # noqa: BLE001
        log.warning("[akshare] cls_telegraph FAILED: %s", exc)

    # X2 industry-level / market-level dp_ids (raw_material / energy_logistics
    # / sector_heat) were MOVED to Tushare
    # (``tushare_source.fetch_akshare_replacement_batch`` via fut_daily /
    # moneyflow_ind_ths) and are intentionally NOT run here — they would clobber
    # the Tushare rows via the (ts_code, dp_id) UPSERT primary key. The fetcher
    # functions remain defined for unit-test/back-compat but are unwired.

    log.info("[akshare] fetch_batch: total %d rows for %d A-share codes",
             len(rows), len(a_codes))
    return rows
