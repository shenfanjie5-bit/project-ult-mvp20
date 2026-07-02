#!/usr/bin/env python3
"""Fetch + ingest A-share annual reports from cninfo (巨潮资讯网).

Phase C0 of the LLM closed-loop rollout. The closed-loop codex fill leans
heavily on local annual-report section text (revenue structure / customer
segments / region distribution / risk disclosure), but ``ingest_annual_report``
was a manual demo (it takes a pre-downloaded ``--pdf``). This script automates
acquisition so the same evidence is available for every A-share:

    ts_code → cninfo orgId        (topSearch/query)
            → annual-report PDF    (hisAnnouncement/query, category=年度报告 → adjunctUrl)
            → download PDF         (static.cninfo.com.cn/<adjunctUrl>)
            → extract + upsert     (reuses ingest_annual_report.extract_sections)

All endpoints are cninfo's own free JSON APIs (no token). Verified end-to-end:
000063.SZ → orgId gssz0000063 → finalpage/2026-03-07/1225000301.PDF (%PDF-).

Usage::

    # one stock
    python scripts/fetch_annual_report.py --ts-code 000063.SZ --year 2025

    # all A-share constituents of an industry that still lack a report
    python scripts/fetch_annual_report.py --industry AI_COMPUTE --year 2025

    # explicit list
    python scripts/fetch_annual_report.py --ts-codes 000063.SZ,002463.SZ --year 2025

    # re-fetch even if already ingested
    python scripts/fetch_annual_report.py --industry AI_COMPUTE --force
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.storage import upsert_realtime  # noqa: E402
from scripts.ingest_annual_report import (  # noqa: E402
    extract_pdf_text,
    extract_sections,
)

HOT_DB_PATH = ROOT / "runtime" / "hot.sqlite"
AR_DIR = ROOT / "runtime" / "annual_reports"

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TOPSEARCH = "http://www.cninfo.com.cn/new/information/topSearch/query"
_HISANN = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_STATIC = "http://static.cninfo.com.cn/"

# cninfo column / plate per exchange suffix.
_MARKET = {
    ".SZ": ("szse", "sz"),
    ".SH": ("sse", "sh"),
    ".BJ": ("bj", "bj"),
}

# Titles that look like an annual report but are not the full filing.
_TITLE_REJECT = ("摘要", "英文", "english", "已取消", "取消", "更正", "补充", "意见", "审计报告")


def _post(url: str, data: dict, timeout: int = 25) -> dict | list:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_orgid(code: str) -> str | None:
    """cninfo internal orgId for a 6-digit stock code (topSearch/query)."""
    try:
        rows = _post(_TOPSEARCH, {"keyWord": code, "maxNum": "10"})
    except Exception as exc:  # noqa: BLE001
        print(f"    [orgid] {code} failed: {exc}")
        return None
    if isinstance(rows, list):
        for r in rows:
            if str(r.get("code")) == code:
                return r.get("orgId")
        if rows:
            return rows[0].get("orgId")
    return None


def find_annual_report(
    code: str, orgid: str, column: str, plate: str, year: int
) -> dict | None:
    """Return {title, pdf_url, ann_time, adjunct} for ``year``'s annual report."""
    pub_year = year + 1  # FY2025 report publishes in 2026
    try:
        payload = _post(
            _HISANN,
            {
                "stock": f"{code},{orgid}",
                "tabName": "fulltext",
                "pageSize": "50",
                "pageNum": "1",
                "column": column,
                "category": "category_ndbg_szsh",  # 年度报告
                "plate": plate,
                "seDate": f"{pub_year}-01-01~{pub_year}-12-31",
                "searchkey": "",
                "secid": "",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    [hisann] {code} failed: {exc}")
        return None

    anns = (payload or {}).get("announcements") or []
    want = f"{year}年年度报告"
    cands = []
    for a in anns:
        title = (a.get("announcementTitle") or "").replace(" ", "")
        if want not in title:
            continue
        low = title.lower()
        if any(bad in low for bad in _TITLE_REJECT):
            continue
        adj = a.get("adjunctUrl") or ""
        if not adj.lower().endswith(".pdf"):
            continue
        cands.append((a.get("announcementTitle"), adj, a.get("announcementTime")))
    if not cands:
        return None
    # Prefer the exact "YYYY年年度报告" title; newest first.
    cands.sort(key=lambda c: (c[0].strip() == want, c[2] or 0), reverse=True)
    title, adj, ann_time = cands[0]
    return {
        "title": title,
        "pdf_url": _STATIC + adj,
        "adjunct": adj,
        "ann_time": ann_time,
    }


def download_pdf(url: str, dest: Path, timeout: int = 60) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if body[:4] != b"%PDF":
        raise ValueError(f"not a PDF (magic={body[:8]!r})")
    dest.write_bytes(body)
    return len(body)


def has_annual_report(db_path: Path, ts_code: str) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM realtime_current WHERE ts_code=? AND "
            "dp_id='L9.disclosure.annual_report'",
            (ts_code,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()
    return row is not None


def fetch_and_ingest(
    ts_code: str, year: int, db_path: Path, *, dry_run: bool = False
) -> dict:
    """Resolve → download → extract → upsert one ts_code's annual report."""
    suffix = ts_code[-3:].upper()
    code = ts_code.split(".")[0]
    if suffix not in _MARKET:
        return {"ts_code": ts_code, "ok": False, "reason": f"unsupported market {suffix}"}
    column, plate = _MARKET[suffix]

    orgid = resolve_orgid(code)
    if not orgid:
        return {"ts_code": ts_code, "ok": False, "reason": "orgId not found"}

    info = find_annual_report(code, orgid, column, plate, year)
    if info is None:
        return {"ts_code": ts_code, "ok": False, "reason": f"no {year} annual report found"}

    if dry_run:
        return {"ts_code": ts_code, "ok": True, "dry_run": True, **info}

    pdf_path = AR_DIR / ts_code / f"{year}_annual.pdf"
    try:
        size = download_pdf(info["pdf_url"], pdf_path)
    except Exception as exc:  # noqa: BLE001
        return {"ts_code": ts_code, "ok": False, "reason": f"download failed: {exc}"}

    full_text = extract_pdf_text(pdf_path)
    sections = extract_sections(full_text)
    payload = {
        "ar_year": year,
        "ar_url": info["pdf_url"],
        "ar_local_path": str(pdf_path),
        "total_text_chars": len(full_text),
        "sections": sections,
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    now = int(time.time())
    upsert_realtime(
        db_path,
        [(
            ts_code, "L9.disclosure.annual_report", payload,
            "Known", 0.9, f"annual_report:cninfo:{year}", now,
        )],
    )
    nonempty = {k: len(v) for k, v in sections.items() if v}
    return {
        "ts_code": ts_code, "ok": True, "pdf_bytes": size,
        "total_chars": len(full_text), "sections": nonempty,
        "title": info["title"], "pdf_url": info["pdf_url"],
    }


def _a_share_constituents(industry: str) -> list[str]:
    d = ROOT / "config" / "stock_overlays" / industry
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.yaml")):
        ts = f.stem
        if ts.upper().endswith((".SH", ".SZ", ".BJ")):
            out.append(ts)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ts-code")
    ap.add_argument("--ts-codes", help="comma-separated list")
    ap.add_argument("--industry", help="fetch all A-share constituents")
    ap.add_argument("--year", type=int, default=2025, help="fiscal year (default 2025)")
    ap.add_argument("--db", type=Path, default=HOT_DB_PATH)
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument("--dry-run", action="store_true", help="resolve PDF url, don't download")
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between stocks")
    args = ap.parse_args()

    targets: list[str] = []
    if args.ts_code:
        targets.append(args.ts_code)
    if args.ts_codes:
        targets += [t.strip() for t in args.ts_codes.split(",") if t.strip()]
    if args.industry:
        targets += _a_share_constituents(args.industry)
    targets = list(dict.fromkeys(targets))  # de-dupe, preserve order
    if not targets:
        ap.error("provide --ts-code / --ts-codes / --industry")

    print(f"[fetch_annual_report] {len(targets)} target(s), year={args.year}")
    results = []
    for i, ts in enumerate(targets):
        if not args.force and not args.dry_run and has_annual_report(args.db, ts):
            print(f"  • {ts}: skip (already ingested)")
            results.append({"ts_code": ts, "ok": True, "skipped": True})
            continue
        print(f"  • {ts}: fetching…")
        try:
            res = fetch_and_ingest(ts, args.year, args.db, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001 — isolate per-stock failures (PDF parse /
            # sqlite-lock under parallel writers) so one bad stock can't kill a worker;
            # the stock simply stays un-ingested and is retried on a later resume pass.
            res = {"ts_code": ts, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        if res.get("ok") and not res.get("dry_run"):
            print(f"      ✓ {res.get('total_chars')} chars; sections={res.get('sections')}")
        elif res.get("dry_run"):
            print(f"      [dry-run] {res.get('title')} → {res.get('pdf_url')}")
        else:
            print(f"      ✗ {res.get('reason')}")
        results.append(res)
        if i < len(targets) - 1 and args.sleep:
            time.sleep(args.sleep)

    ok = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
    skip = sum(1 for r in results if r.get("skipped"))
    fail = [r for r in results if not r.get("ok")]
    print(f"\n[fetch_annual_report] done: {ok} fetched, {skip} skipped, {len(fail)} failed")
    for r in fail:
        print(f"  ✗ {r['ts_code']}: {r.get('reason')}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
