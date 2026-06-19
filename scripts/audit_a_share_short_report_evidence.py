#!/usr/bin/env python3
"""Dedicated short-report evidence audit for A-share scoring gaps.

The generic media/social rows are not enough to prove ``L9.media.short_report``
semantics.  This read-only audit scans local DockCase market news HTML for
high-precision short-seller / short-report language, separates direct A-share
mentions from foreign or market-only context, and emits a bounded evidence
package for candidate review.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_UNIVERSE_PATH = ROOT / "config/mvp20.universe.yaml"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_short_report_evidence_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_short_report_evidence_2026-06-19.md"

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DROP_BLOCK_RE = re.compile(r"<(script|style|noscript|svg)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
STOCK_CODE_RE = re.compile(r"(?<!\d)(?:[036]\d{5})(?!\d)")
TEMPLATE_TAIL_MARKERS = (
    "相关阅读",
    "财联社声明",
    "免责声明",
    "风险提示",
)

STRICT_SHORT_REPORT_PATTERNS = (
    re.compile(r"做空报告|沽空报告|卖空报告|看空报告"),
    re.compile(r"short[-\s]?seller\s+report|short[-\s]?selling\s+report|short\s+report", re.IGNORECASE),
    re.compile(r"(做空机构|沽空机构|空头机构).{0,40}(发布|报告|称|正在做空|看空消息|看空|突袭|指控)"),
    re.compile(r"(香橼|浑水|Muddy\s*Waters|Citron|Hindenburg).{0,60}(做空|看空|short|空头)", re.IGNORECASE),
    re.compile(r"(发布|发表|出具).{0,20}(做空|沽空|卖空|看空).{0,20}(报告|观点|指控|消息)"),
)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _clean_html_text(text: str) -> str:
    text = DROP_BLOCK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _trim_template_tail(text: str) -> str:
    end = len(text)
    for marker in TEMPLATE_TAIL_MARKERS:
        pos = text.find(marker)
        if pos >= 0:
            end = min(end, pos)
    return text[:end].strip()


def _extract_html(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title_match = TITLE_RE.search(raw)
    title = _clean_html_text(title_match.group(1)) if title_match else ""
    return title, _trim_template_tail(_clean_html_text(raw))


def _source_group(path: Path, market_root: Path) -> str:
    try:
        rel = path.relative_to(market_root / "news")
        return f"news/{rel.parts[0]}"
    except Exception:
        return "news/unknown"


def _load_a_share_code_map(universe_path: Path) -> dict[str, list[str]]:
    if not universe_path.exists():
        return {}
    payload = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for row in payload.get("constituents") or []:
        if not isinstance(row, dict):
            continue
        ts_code = str(row.get("ts_code") or "")
        if not ts_code.endswith((".SH", ".SZ", ".BJ")):
            continue
        raw = ts_code.split(".", 1)[0]
        out.setdefault(raw, []).append(ts_code)
    return out


def _matched_patterns(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in STRICT_SHORT_REPORT_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def _excerpt(text: str, patterns: list[str], *, limit: int = 260) -> str:
    first_pos: int | None = None
    for pattern_text in patterns:
        try:
            pattern = re.compile(pattern_text, re.IGNORECASE)
        except re.error:
            continue
        match = pattern.search(text)
        if match and (first_pos is None or match.start() < first_pos):
            first_pos = match.start()
    if first_pos is None:
        return text[:limit]
    start = max(0, first_pos - limit // 3)
    return text[start : start + limit]


def _iter_news_html(market_root: Path) -> list[Path]:
    news_root = market_root / "news"
    if not news_root.exists():
        return []
    return sorted(path for path in news_root.rglob("*.html") if path.is_file())


def build_report(
    *,
    market_root: Path,
    universe_path: Path,
    retained_sample_limit: int,
) -> dict[str, Any]:
    started = time.time()
    code_map = _load_a_share_code_map(universe_path)
    paths = _iter_news_html(market_root)
    source_counts: Counter[str] = Counter()
    strict_source_counts: Counter[str] = Counter()
    direct_a_share_codes: Counter[str] = Counter()
    strict_samples: list[dict[str, Any]] = []
    direct_samples: list[dict[str, Any]] = []
    foreign_or_market_samples: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    strict_count = 0
    direct_count = 0
    foreign_or_market_count = 0

    for path in paths:
        source = _source_group(path, market_root)
        source_counts[source] += 1
        try:
            title, text = _extract_html(path)
        except Exception as exc:  # noqa: BLE001
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue

        haystack = f"{title} {text}"
        matched = _matched_patterns(haystack)
        if not matched:
            continue
        strict_count += 1
        strict_source_counts[source] += 1
        raw_codes = sorted(set(STOCK_CODE_RE.findall(haystack)))
        a_share_ts_codes = sorted(
            {
                ts_code
                for raw in raw_codes
                for ts_code in code_map.get(raw, [])
            }
        )
        item = {
            "path": str(path),
            "source": source,
            "title": title,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "matched_patterns": matched,
            "raw_stock_codes": raw_codes[:20],
            "a_share_ts_codes": a_share_ts_codes[:20],
            "excerpt": _excerpt(haystack, matched),
        }
        if len(strict_samples) < retained_sample_limit:
            strict_samples.append(item)
        if a_share_ts_codes:
            direct_count += 1
            for ts_code in a_share_ts_codes:
                direct_a_share_codes[ts_code] += 1
            if len(direct_samples) < retained_sample_limit:
                direct_samples.append(item)
        else:
            foreign_or_market_count += 1
            if len(foreign_or_market_samples) < retained_sample_limit:
                foreign_or_market_samples.append(item)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "market_root": str(market_root),
        "universe_path": _portable_path(universe_path),
        "summary": {
            "news_html_files_scanned": len(paths),
            "parse_error_count": len(parse_errors),
            "strict_short_report_documents": strict_count,
            "direct_a_share_short_report_documents": direct_count,
            "foreign_or_market_short_report_documents": foreign_or_market_count,
            "direct_a_share_ts_code_count": len(direct_a_share_codes),
            "candidate_evidence_ready": len(paths) > 0 and len(parse_errors) == 0,
            "source_counts": dict(sorted(source_counts.items())),
            "strict_source_counts": dict(sorted(strict_source_counts.items())),
            "direct_a_share_top_ts_codes": dict(direct_a_share_codes.most_common(20)),
            "score_mutation": "none; audit is read-only",
        },
        "strict_samples": strict_samples,
        "direct_a_share_samples": direct_samples,
        "foreign_or_market_samples": foreign_or_market_samples,
        "parse_errors": parse_errors[:20],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share short-report evidence audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- News HTML scanned: `{summary['news_html_files_scanned']}`",
        f"- Strict short-report documents: `{summary['strict_short_report_documents']}`",
        f"- Direct A-share short-report documents: `{summary['direct_a_share_short_report_documents']}`",
        f"- Foreign/market-only short-report documents: `{summary['foreign_or_market_short_report_documents']}`",
        f"- Candidate evidence ready: `{summary['candidate_evidence_ready']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Strict Source Counts",
        "",
        "| Source | Count |",
        "|---|---:|",
    ]
    for source, count in summary["strict_source_counts"].items():
        lines.append(f"| `{source}` | {count} |")

    lines.extend(["", "## Direct A-share Samples", ""])
    if report["direct_a_share_samples"]:
        for item in report["direct_a_share_samples"]:
            lines.append(f"- `{item['path']}` — `{', '.join(item['a_share_ts_codes'])}` — {item['title']}")
    else:
        lines.append("- No direct A-share short-report document was found in the scanned local corpus.")

    lines.extend(["", "## Foreign Or Market Samples", ""])
    for item in report["foreign_or_market_samples"][:10]:
        lines.append(f"- `{item['path']}` — {item['title']}")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is dedicated short-report evidence, not a score mutation.",
            "- If direct A-share samples are absent, candidate generation should produce reviewed neutral/Unknown outputs for A-share targets rather than fabricate active short-report events.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--retained-sample-limit", type=int, default=20)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        market_root=args.market_root,
        universe_path=args.universe_path,
        retained_sample_limit=args.retained_sample_limit,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
