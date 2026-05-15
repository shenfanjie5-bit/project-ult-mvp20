#!/usr/bin/env python3
"""Phase A1 demo: extract section excerpts from a downloaded annual-report
PDF and upsert into ``realtime_current`` as a new ``L9.disclosure.annual_report``
dp_id so codex prompts can quote it.

Usage::

    python scripts/ingest_annual_report.py --ts-code 000977.SZ \\
        --pdf runtime/annual_reports/000977.SZ/2025_annual.pdf \\
        --ar-year 2025 \\
        --ar-url http://static.cninfo.com.cn/finalpage/2026-04-11/1225096638.PDF

The sections extracted (best-effort heuristic):

* ``business_overview``  — "报告期内公司从事的主要业务" / "主要业务"
* ``customer_segment``   — "前五名客户" / "主要销售客户"
* ``revenue_structure``  — "营业收入构成" / "分产品" / "分销售模式"
* ``region_distribution`` — "分地区" / "境内/境外" / fallback to
  "分销售模式" (region-vs-industry) when explicit region breakdown is absent
* ``risk_disclosure``    — "可能面临的主要风险" / "风险因素"

Each excerpt is trimmed to roughly 1200 chars to keep the SQLite payload
manageable while still preserving the headline figures codex needs to
quote verbatim in evidence_sources.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mvp20.storage import upsert_realtime  # noqa: E402


EXCERPT_MAXLEN = 1200


def extract_pdf_text(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _slice(text: str, anchor_positions: list[int], window_after: int) -> str:
    """Take the smallest anchor position and slice ``window_after`` chars
    forward. Returns empty string if no anchor found."""

    if not anchor_positions:
        return ""
    start = min(anchor_positions)
    end = min(len(text), start + window_after)
    return text[start:end].strip()


def _find_first(text: str, keywords: list[str]) -> list[int]:
    """Return list of first-occurrence positions for each keyword found."""

    out: list[int] = []
    for kw in keywords:
        m = re.search(re.escape(kw), text)
        if m:
            out.append(m.start())
    return out


def extract_sections(full_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}

    # business_overview: from "报告期内公司从事的主要业务" forward ~1500 chars
    pos = _find_first(
        full_text,
        ["报告期内公司从事的主要业务", "一、报告期内", "主要业务"],
    )
    sections["business_overview"] = _slice(full_text, pos, 1500)[:EXCERPT_MAXLEN]

    # customer_segment: anchor on "前五名客户合计销售金额" — most concrete
    pos = _find_first(
        full_text,
        ["前五名客户合计销售金额", "公司主要销售客户情况", "前五名客户"],
    )
    sections["customer_segment"] = _slice(full_text, pos, 1500)[:EXCERPT_MAXLEN]

    # revenue_structure: from "营业收入构成" forward, captures 分行业/分产品/分销售模式
    pos = _find_first(
        full_text,
        ["营业收入构成", "主营业务分行业", "主营业务收入"],
    )
    sections["revenue_structure"] = _slice(full_text, pos, 1800)[:EXCERPT_MAXLEN]

    # region_distribution: try explicit "分地区" first, fallback to "分销售模式"
    # (which captures the 区域 vs 行业 breakdown that some issuers use as
    # their geographic-ish split).
    pos = _find_first(full_text, ["分地区", "境内地区", "境外地区"])
    if not pos:
        pos = _find_first(full_text, ["分销售模式"])
    sections["region_distribution"] = _slice(full_text, pos, 1500)[
        :EXCERPT_MAXLEN
    ]

    # risk_disclosure: anchor on "可能面临的主要风险" with fallbacks
    pos = _find_first(
        full_text,
        [
            "可能面临的主要风险",
            "公司未来发展可能面临的主要风险",
            "公司业务发展可能面临的主要风险",
            "可能面对的主要风险",
            "风险因素",
        ],
    )
    sections["risk_disclosure"] = _slice(full_text, pos, 1800)[:EXCERPT_MAXLEN]

    return sections


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts-code", required=True)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--ar-year", type=int, required=True)
    ap.add_argument("--ar-url", default="")
    ap.add_argument(
        "--db",
        type=Path,
        default=ROOT / "runtime" / "hot.sqlite",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"pdf not found: {args.pdf}")

    print(f"[A1] extracting text from {args.pdf} ({args.pdf.stat().st_size} bytes)")
    full_text = extract_pdf_text(args.pdf)
    print(f"[A1] total text chars: {len(full_text)}")

    sections = extract_sections(full_text)
    for k, v in sections.items():
        print(f"  section {k:20s} {len(v):4d} chars")

    payload = {
        "ar_year": args.ar_year,
        "ar_url": args.ar_url or str(args.pdf),
        "ar_local_path": str(args.pdf),
        "total_text_chars": len(full_text),
        "sections": sections,
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if args.dry_run:
        print("[A1] dry-run, not writing to SQLite. Payload preview:")
        print(json.dumps(payload, ensure_ascii=False)[:600])
        return

    n = upsert_realtime(
        args.db,
        [
            (
                args.ts_code,
                "L9.disclosure.annual_report",
                payload,
                "Known",
                0.9,
                f"annual_report:cninfo:{args.ar_year}",
                int(time.time()),
            )
        ],
    )
    print(f"[A1] upserted {n} row(s) into {args.db}")


if __name__ == "__main__":
    main()
