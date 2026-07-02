#!/usr/bin/env python3
"""Audit extractability of DockCase market news HTML and announcement PDFs."""
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = "/Volumes/dockcase2tb/market_data"
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESC_RE = re.compile(
    r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](.*?)[\"']",
    re.IGNORECASE | re.DOTALL,
)
DROP_BLOCK_RE = re.compile(
    r"<(script|style|noscript|svg)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
PATH_DATE_RE = re.compile(r"/(?P<year>20\d{2})/(?P<month>\d{2})(?:/|$)")
PDF_PAGE_RE = re.compile(rb"/Type\s*/Page\b")
PDF_VERSION_RE = re.compile(rb"%PDF-(\d\.\d)")
STOCK_CODE_RE = re.compile(r"(?<!\d)(?:[036]\d{5})(?!\d)")
INLINE_DATE_RE = re.compile(
    r"20\d{2}(?:[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)?|20\d{4}",
)
COMPANY_NAME_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:股份有限公司|有限公司|集团|证券|银行)",
)
EVENT_KEYWORDS = {
    "fundamental": ("业绩", "营收", "利润", "增长", "预告", "快报", "年报", "季报"),
    "capital_action": ("回购", "增持", "减持", "定增", "分红", "股东", "质押"),
    "order_product": ("订单", "合同", "中标", "产品", "产能", "项目"),
    "risk_regulatory": ("诉讼", "处罚", "调查", "监管", "风险", "停牌", "问询"),
    "market_movement": ("涨停", "跌停", "涨幅", "跌幅", "资金", "主力", "北向"),
}
BOILERPLATE_HINTS = (
    "东方财富产品",
    "扫一扫下载APP",
    "当前公告无法在线阅读",
)


@dataclass
class GroupSummary:
    group: str
    extension: str
    file_count: int = 0
    selected_count: int = 0
    sampled_count: int = 0
    total_bytes: int = 0
    date_months: set[str] = field(default_factory=set)
    samples: list[dict[str, object]] = field(default_factory=list)
    text_chars_values: list[int] = field(default_factory=list)
    pdf_page_values: list[int] = field(default_factory=list)
    pdf_text_chars_values: list[int] = field(default_factory=list)
    issue_counts: dict[str, int] = field(default_factory=dict)
    signal_counts: Counter[str] = field(default_factory=Counter)
    event_category_counts: Counter[str] = field(default_factory=Counter)
    errors: list[dict[str, str]] = field(default_factory=list)

    def issue(self, code: str) -> None:
        self.issue_counts[code] = self.issue_counts.get(code, 0) + 1

    def signal(self, code: str) -> None:
        self.signal_counts[code] += 1


def _iter_files(root: Path, suffix: str) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def _group_for_news(path: Path, news_root: Path) -> str:
    try:
        return path.relative_to(news_root).parts[0]
    except Exception:
        return "unknown"


def _group_for_pdf(path: Path, announcements_root: Path) -> str:
    try:
        return path.relative_to(announcements_root).parts[0]
    except Exception:
        return "unknown"


def _path_month(path: Path) -> str | None:
    match = PATH_DATE_RE.search(path.as_posix())
    if not match:
        return None
    return f"{match.group('year')}-{match.group('month')}"


def _clean_html_text(text: str) -> str:
    text = DROP_BLOCK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _path_entity_codes(path: Path) -> list[str]:
    if "/announcements/" not in path.as_posix():
        return []
    return sorted(set(STOCK_CODE_RE.findall(path.as_posix())))


def _event_keyword_hits(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for category, keywords in EVENT_KEYWORDS.items():
        found = [keyword for keyword in keywords if keyword in text]
        if found:
            hits[category] = found
    return hits


def _signal_excerpt(text: str, hints: list[str], *, limit: int = 240) -> str:
    if not text:
        return ""
    first_pos: int | None = None
    for hint in hints:
        if not hint:
            continue
        pos = text.find(hint)
        if pos >= 0 and (first_pos is None or pos < first_pos):
            first_pos = pos
    if first_pos is None:
        return text[:limit]
    start = max(0, first_pos - limit // 3)
    return text[start : start + limit]


def _text_signals(path: Path, text: str) -> dict[str, object]:
    stock_codes = sorted(set(STOCK_CODE_RE.findall(text)))
    path_codes = _path_entity_codes(path)
    company_names = sorted(set(COMPANY_NAME_RE.findall(text)))
    date_hints = sorted(set(INLINE_DATE_RE.findall(text)))
    event_keywords = _event_keyword_hits(text)
    event_categories = sorted(event_keywords)
    flat_event_terms = [
        keyword
        for keywords in event_keywords.values()
        for keyword in keywords
    ]
    citation_hints = stock_codes + path_codes + company_names + date_hints + flat_event_terms
    return {
        "path_entity_code_hints": path_codes[:20],
        "stock_code_hints": stock_codes[:20],
        "stock_code_hint_count": len(stock_codes),
        "company_name_hints": company_names[:10],
        "company_name_hint_count": len(company_names),
        "date_hints": date_hints[:10],
        "date_hint_count": len(date_hints),
        "event_keywords": event_keywords,
        "event_categories": event_categories,
        "event_category_count": len(event_categories),
        "entity_signal_present": bool(stock_codes or path_codes or company_names),
        "date_signal_present": bool(date_hints or _path_month(path)),
        "event_signal_present": bool(event_keywords),
        "citation_preview": _signal_excerpt(text, citation_hints),
    }


def _record_signals(summary: GroupSummary, item: dict[str, object]) -> None:
    summary.signal("sampled_documents")
    if item.get("entity_signal_present"):
        summary.signal("entity_signal_samples")
    if item.get("date_signal_present"):
        summary.signal("date_signal_samples")
    if item.get("event_signal_present"):
        summary.signal("event_keyword_samples")
    if item.get("citation_preview"):
        summary.signal("citation_preview_samples")
    for category in item.get("event_categories", []):
        summary.event_category_counts[str(category)] += 1


def _extract_html(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title_match = TITLE_RE.search(raw)
    desc_match = META_DESC_RE.search(raw)
    title = _clean_html_text(title_match.group(1)) if title_match else ""
    description = _clean_html_text(desc_match.group(1)) if desc_match else ""
    text = _clean_html_text(raw)
    boilerplate_hints = [hint for hint in BOILERPLATE_HINTS if hint in text]
    return {
        "title": title,
        "title_chars": len(title),
        "description": description[:240],
        "description_chars": len(description),
        "text_chars": len(text),
        "boilerplate_hints": boilerplate_hints,
        "text_preview": text[:240],
        **_text_signals(path, text),
    }


def _pdf_text_sample(path: Path, *, page_limit: int) -> tuple[int | None, str | None, str]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except Exception:
        return None, "pdfplumber_unavailable", ""
    try:
        parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:page_limit]:
                parts.append(page.extract_text() or "")
        text = _clean_html_text("\n".join(parts))
        return len(text), None, text
    except Exception as exc:  # noqa: BLE001
        return None, str(exc), ""


def _extract_pdf(path: Path, *, text_page_limit: int) -> dict[str, object]:
    data = path.read_bytes()
    version_match = PDF_VERSION_RE.search(data[:1024])
    estimated_pages = len(PDF_PAGE_RE.findall(data))
    text_chars, text_error, sample_text = _pdf_text_sample(path, page_limit=text_page_limit)
    out: dict[str, object] = {
        "pdf_header_ok": data.startswith(b"%PDF-"),
        "pdf_version": version_match.group(1).decode("ascii") if version_match else "",
        "estimated_page_count": estimated_pages,
        "sample_text_chars": text_chars,
        "sample_text_preview": sample_text[:240],
        **_text_signals(path, sample_text),
    }
    if text_error:
        out["text_extract_error"] = text_error
    return out


def _stats(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _retain_sample(
    summary: GroupSummary,
    item: dict[str, object],
    *,
    retained_sample_limit: int,
) -> None:
    if retained_sample_limit <= 0 or len(summary.samples) < retained_sample_limit:
        summary.samples.append(item)


def _record_stats(summary: GroupSummary, item: dict[str, object]) -> None:
    if "text_chars" in item and item["text_chars"] is not None:
        summary.text_chars_values.append(int(item["text_chars"]))
    if "estimated_page_count" in item and item["estimated_page_count"] is not None:
        summary.pdf_page_values.append(int(item["estimated_page_count"]))
    if "sample_text_chars" in item and item["sample_text_chars"] is not None:
        summary.pdf_text_chars_values.append(int(item["sample_text_chars"]))


def _summarize_group(summary: GroupSummary) -> dict[str, object]:
    return {
        "group": summary.group,
        "extension": summary.extension,
        "file_count": summary.file_count,
        "selected_count": summary.selected_count,
        "sampled_count": summary.sampled_count,
        "retained_sample_count": len(summary.samples),
        "unselected_count": max(summary.file_count - summary.selected_count, 0),
        "selected_without_successful_parse": max(
            summary.selected_count - summary.sampled_count,
            0,
        ),
        "sampling_coverage": {
            "selected_file_ratio": round(
                summary.selected_count / summary.file_count,
                4,
            ) if summary.file_count else 0.0,
            "successful_parse_ratio_of_selected": round(
                summary.sampled_count / summary.selected_count,
                4,
            ) if summary.selected_count else 0.0,
        },
        "total_bytes": summary.total_bytes,
        "date_months": sorted(summary.date_months),
        "issue_counts": dict(sorted(summary.issue_counts.items())),
        "signal_counts": dict(sorted(summary.signal_counts.items())),
        "event_category_counts": dict(sorted(summary.event_category_counts.items())),
        "errors": summary.errors[:20],
        "text_chars": _stats(summary.text_chars_values),
        "estimated_page_count": _stats(summary.pdf_page_values),
        "sample_text_chars": _stats(summary.pdf_text_chars_values),
        "samples": summary.samples,
    }


def _sample_paths(paths: list[Path], *, sample_limit: int) -> set[Path]:
    if sample_limit <= 0 or len(paths) <= sample_limit:
        return set(paths)
    if sample_limit == 1:
        return {paths[0]}
    indexes = {
        round(idx * (len(paths) - 1) / (sample_limit - 1))
        for idx in range(sample_limit)
    }
    return {paths[idx] for idx in sorted(indexes)}


def _audit_html(
    root: Path,
    *,
    sample_per_group: int,
    retained_samples_per_group: int,
) -> dict[str, object]:
    news_root = root / "news"
    groups: dict[str, GroupSummary] = {}
    paths = list(_iter_files(news_root, ".html"))
    grouped_paths: dict[str, list[Path]] = {}
    for path in paths:
        group = _group_for_news(path, news_root)
        grouped_paths.setdefault(group, []).append(path)
    for group, group_paths in sorted(grouped_paths.items()):
        summary = GroupSummary(group=group, extension=".html")
        samples = _sample_paths(group_paths, sample_limit=sample_per_group)
        summary.selected_count = len(samples)
        for path in group_paths:
            st = path.stat()
            summary.file_count += 1
            summary.total_bytes += int(st.st_size)
            month = _path_month(path)
            if month:
                summary.date_months.add(month)
            if path not in samples:
                continue
            try:
                extracted = _extract_html(path)
                item = {
                    "path": str(path),
                    "bytes": int(st.st_size),
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    **extracted,
                }
                summary.sampled_count += 1
                _record_stats(summary, item)
                _record_signals(summary, item)
                _retain_sample(
                    summary,
                    item,
                    retained_sample_limit=retained_samples_per_group,
                )
                if not item["title"]:
                    summary.issue("missing_title")
                if int(item["text_chars"]) < 80:
                    summary.issue("short_extracted_text")
                if item["boilerplate_hints"] and (
                    not item["title"] or int(item["text_chars"]) < 600
                ):
                    summary.issue("boilerplate_or_placeholder_text")
            except Exception as exc:  # noqa: BLE001
                summary.issue("parse_error")
                summary.errors.append({"path": str(path), "error": str(exc)})
        groups[group] = summary
    return {
        "root": str(news_root),
        "file_count": sum(item.file_count for item in groups.values()),
        "sampled_count": sum(item.sampled_count for item in groups.values()),
        "groups": [_summarize_group(item) for item in groups.values()],
    }


def _audit_pdf(
    root: Path,
    *,
    sample_per_group: int,
    text_page_limit: int,
    retained_samples_per_group: int,
) -> dict[str, object]:
    announcements_root = root / "announcements"
    groups: dict[str, GroupSummary] = {}
    paths = list(_iter_files(announcements_root, ".pdf"))
    grouped_paths: dict[str, list[Path]] = {}
    for path in paths:
        group = _group_for_pdf(path, announcements_root)
        grouped_paths.setdefault(group, []).append(path)
    for group, group_paths in sorted(grouped_paths.items()):
        summary = GroupSummary(group=group, extension=".pdf")
        samples = _sample_paths(group_paths, sample_limit=sample_per_group)
        summary.selected_count = len(samples)
        for path in group_paths:
            st = path.stat()
            summary.file_count += 1
            summary.total_bytes += int(st.st_size)
            month = _path_month(path)
            if month:
                summary.date_months.add(month)
            if path not in samples:
                continue
            try:
                extracted = _extract_pdf(path, text_page_limit=text_page_limit)
                item = {
                    "path": str(path),
                    "bytes": int(st.st_size),
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    **extracted,
                }
                summary.sampled_count += 1
                _record_stats(summary, item)
                _record_signals(summary, item)
                _retain_sample(
                    summary,
                    item,
                    retained_sample_limit=retained_samples_per_group,
                )
                if not item["pdf_header_ok"]:
                    summary.issue("bad_pdf_header")
                if int(item["estimated_page_count"]) <= 0:
                    summary.issue("no_estimated_pages")
                text_chars = item.get("sample_text_chars")
                if text_chars is not None and int(text_chars) < 40:
                    summary.issue("short_pdf_text_extract")
            except Exception as exc:  # noqa: BLE001
                summary.issue("parse_error")
                summary.errors.append({"path": str(path), "error": str(exc)})
        groups[group] = summary
    return {
        "root": str(announcements_root),
        "file_count": sum(item.file_count for item in groups.values()),
        "sampled_count": sum(item.sampled_count for item in groups.values()),
        "groups": [_summarize_group(item) for item in groups.values()],
    }


def build_report(
    *,
    root: Path,
    sample_per_group: int,
    pdf_text_page_limit: int,
    retained_samples_per_group: int = 20,
) -> dict[str, object]:
    started = time.time()
    news = _audit_html(
        root,
        sample_per_group=sample_per_group,
        retained_samples_per_group=retained_samples_per_group,
    )
    announcements = _audit_pdf(
        root,
        sample_per_group=sample_per_group,
        text_page_limit=pdf_text_page_limit,
        retained_samples_per_group=retained_samples_per_group,
    )
    issue_counts: dict[str, int] = {}
    signal_counts: Counter[str] = Counter()
    event_category_counts: Counter[str] = Counter()
    source_group_coverage: list[dict[str, object]] = []
    for section in (news, announcements):
        for group in section["groups"]:
            for code, count in group["issue_counts"].items():
                issue_counts[code] = issue_counts.get(code, 0) + int(count)
            signal_counts.update(group.get("signal_counts", {}))
            event_category_counts.update(group.get("event_category_counts", {}))
            source_group_coverage.append(
                {
                    "source": f"{'news' if section is news else 'announcements'}/{group['group']}",
                    "extension": group["extension"],
                    "file_count": group["file_count"],
                    "selected_count": group["selected_count"],
                    "sampled_count": group["sampled_count"],
                    "retained_sample_count": group["retained_sample_count"],
                    "unselected_count": group["unselected_count"],
                    "selected_without_successful_parse": group[
                        "selected_without_successful_parse"
                    ],
                    "sampling_coverage": group["sampling_coverage"],
                }
            )
    total_files = int(news["file_count"]) + int(announcements["file_count"])
    selected_documents = sum(int(item["selected_count"]) for item in source_group_coverage)
    sampled_documents = sum(int(item["sampled_count"]) for item in source_group_coverage)
    selected_without_successful_parse = sum(
        int(item["selected_without_successful_parse"]) for item in source_group_coverage
    )
    unselected_documents = max(total_files - selected_documents, 0)
    coverage_gaps = {
        "document_files_not_selected_for_extractability_sampling": unselected_documents,
        "selected_documents_without_successful_parse": selected_without_successful_parse,
        "news_html_files_not_selected": max(
            int(news["file_count"]) - sum(
                int(item["selected_count"])
                for item in source_group_coverage
                if str(item["source"]).startswith("news/")
            ),
            0,
        ),
        "announcement_pdf_files_not_selected": max(
            int(announcements["file_count"]) - sum(
                int(item["selected_count"])
                for item in source_group_coverage
                if str(item["source"]).startswith("announcements/")
            ),
            0,
        ),
        "bounded_document_sampling": selected_documents < total_files,
        "entity_event_signals_are_sample_based": sampled_documents < total_files,
        "retained_samples_are_bounded": retained_samples_per_group > 0,
    }
    sampling_coverage = {
        "selected_document_ratio": round(
            selected_documents / total_files,
            4,
        ) if total_files else 0.0,
        "successful_parse_ratio_of_total_documents": round(
            sampled_documents / total_files,
            4,
        ) if total_files else 0.0,
        "successful_parse_ratio_of_selected_documents": round(
            sampled_documents / selected_documents,
            4,
        ) if selected_documents else 0.0,
        "entity_signal_ratio_of_sampled_documents": round(
            signal_counts.get("entity_signal_samples", 0) / sampled_documents,
            4,
        ) if sampled_documents else 0.0,
        "event_keyword_ratio_of_sampled_documents": round(
            signal_counts.get("event_keyword_samples", 0) / sampled_documents,
            4,
        ) if sampled_documents else 0.0,
        "citation_preview_ratio_of_sampled_documents": round(
            signal_counts.get("citation_preview_samples", 0) / sampled_documents,
            4,
        ) if sampled_documents else 0.0,
    }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - started, 3),
        "scan_mode": (
            "full_market_document_extractability_entity_event_signals"
            if sampled_documents == total_files
            else "bounded_market_document_extractability_entity_event_signals"
        ),
        "root": str(root),
        "sample_per_group": sample_per_group,
        "pdf_text_page_limit": pdf_text_page_limit,
        "retained_samples_per_group": retained_samples_per_group,
        "summary": {
            "news_html_files": news["file_count"],
            "news_html_selected": sum(
                int(item["selected_count"])
                for item in source_group_coverage
                if str(item["source"]).startswith("news/")
            ),
            "news_html_sampled": news["sampled_count"],
            "announcement_pdf_files": announcements["file_count"],
            "announcement_pdf_selected": sum(
                int(item["selected_count"])
                for item in source_group_coverage
                if str(item["source"]).startswith("announcements/")
            ),
            "announcement_pdf_sampled": announcements["sampled_count"],
            "document_files_total": total_files,
            "documents_selected_for_extractability_sampling": selected_documents,
            "documents_successfully_parsed": sampled_documents,
            "retained_sample_examples": sum(
                int(item["retained_sample_count"]) for item in source_group_coverage
            ),
            "coverage_gaps": coverage_gaps,
            "sampling_coverage": sampling_coverage,
            "source_group_coverage": source_group_coverage,
            "issue_counts": dict(sorted(issue_counts.items())),
            "signal_counts": dict(sorted(signal_counts.items())),
            "event_category_counts": dict(sorted(event_category_counts.items())),
        },
        "news": news,
        "announcements": announcements,
    }


def _markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Market document extractability audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Root: `{report['root']}`",
        f"- Scan mode: `{report['scan_mode']}`",
        f"- Sample per group: `{report['sample_per_group']}`",
        f"- Retained samples per group: `{report.get('retained_samples_per_group')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if key in {"coverage_gaps", "sampling_coverage", "source_group_coverage"}:
            continue
        lines.append(f"| `{key}` | `{value}` |")
    coverage = summary.get("sampling_coverage", {})
    gaps = summary.get("coverage_gaps", {})
    lines.extend(["", "## Sampling Coverage", ""])
    if coverage:
        lines.extend(["| Metric | Value |", "|---|---:|"])
        for key, value in coverage.items():
            lines.append(f"| `{key}` | `{value}` |")
    if gaps:
        lines.extend(["", "| Coverage gap | Count / flag |", "|---|---:|"])
        for key, value in gaps.items():
            lines.append(f"| `{key}` | `{value}` |")
    lines.extend([
        "",
        "## Source Group Coverage",
        "",
        "| Source | Files | Selected | Parsed | Retained examples | Unselected | Selected parse misses | Selected ratio | Parse ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in summary.get("source_group_coverage", []):
        row_coverage = row.get("sampling_coverage", {})
        lines.append(
            f"| `{row['source']}` | {row['file_count']} | {row['selected_count']} | "
            f"{row['sampled_count']} | {row['retained_sample_count']} | "
            f"{row['unselected_count']} | "
            f"{row['selected_without_successful_parse']} | "
            f"{row_coverage.get('selected_file_ratio')} | "
            f"{row_coverage.get('successful_parse_ratio_of_selected')} |"
        )
    lines.extend([
        "",
        "## Entity/Event Signals",
        "",
        "| Source | Sampled | Entity signal | Date signal | Event keyword | Citation preview | Event categories |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for section_name in ("news", "announcements"):
        for group in report[section_name]["groups"]:
            signals = group.get("signal_counts", {})
            categories = ", ".join(
                f"{key}={value}"
                for key, value in group.get("event_category_counts", {}).items()
            ) or "-"
            lines.append(
                f"| `{section_name}/{group['group']}` | {signals.get('sampled_documents', 0)} | "
                f"{signals.get('entity_signal_samples', 0)} | "
                f"{signals.get('date_signal_samples', 0)} | "
                f"{signals.get('event_keyword_samples', 0)} | "
                f"{signals.get('citation_preview_samples', 0)} | {categories} |"
            )
    lines.extend([
        "",
        "## News HTML",
        "",
        "| Group | Files | Selected | Parsed | Months | Text chars median | Issues |",
        "|---|---:|---:|---:|---|---:|---|",
    ])
    for group in report["news"]["groups"]:
        months = ", ".join(group["date_months"])
        lines.append(
            f"| `{group['group']}` | {group['file_count']} | {group['selected_count']} | "
            f"{group['sampled_count']} | {months} | {group['text_chars']['median']} | "
            f"{group['issue_counts']} |"
        )
    lines.extend([
        "",
        "## Announcement PDFs",
        "",
        "| Group | Files | Selected | Parsed | Months | Page median | Sample text median | Issues |",
        "|---|---:|---:|---:|---|---:|---:|---|",
    ])
    for group in report["announcements"]["groups"]:
        months = ", ".join(group["date_months"])
        lines.append(
            f"| `{group['group']}` | {group['file_count']} | {group['selected_count']} | "
            f"{group['sampled_count']} | {months} | {group['estimated_page_count']['median']} | "
            f"{group['sample_text_chars']['median']} | {group['issue_counts']} |"
        )
    full_signal_pass = not gaps.get("entity_event_signals_are_sample_based")
    signal_note = (
        "- Entity/date/event signals were computed for every audited HTML/PDF file; "
        "retained `samples` are bounded only to keep the JSON reviewable."
        if full_signal_pass
        else "- Entity/date/event signals are sample-based; unselected files are counted but not semantically linked."
    )
    lines.extend([
        "",
        "## Notes",
        "",
        "- HTML extraction uses generic tag/script/style removal and is intended to prove bounded text extractability, not perfect article parsing.",
        "- PDF extraction records header/page metadata and uses optional `pdfplumber` text extraction when available; failures are reported per selected sample.",
        signal_note,
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument(
        "--sample-per-group",
        type=int,
        default=0,
        help="Files selected for extraction per source group; <=0 means all files.",
    )
    ap.add_argument("--pdf-text-page-limit", type=int, default=2)
    ap.add_argument(
        "--retained-samples-per-group",
        type=int,
        default=20,
        help="Example samples retained in JSON/Markdown per group; <=0 retains all.",
    )
    ap.add_argument("--output-json", default="docs/audit/market_documents_2026-06-18.json")
    ap.add_argument("--output-md", default="docs/audit/market_documents_2026-06-18.md")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        root=Path(args.root),
        sample_per_group=args.sample_per_group,
        pdf_text_page_limit=args.pdf_text_page_limit,
        retained_samples_per_group=args.retained_samples_per_group,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
