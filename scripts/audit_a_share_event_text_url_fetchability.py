#!/usr/bin/env python3
"""Fetch and audit CLS article bodies for A-share event-text gaps.

This audit is read-only. It fetches the unique article URLs referenced by the
event-text classification input bundle, extracts bounded primary text, and
checks whether body-level evidence connects the target event to direct A-share
transmission strongly enough to enter classifier review.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_event_text_preclassification_screen import TARGET_KEYWORDS
from scripts.audit_a_share_event_text_sufficiency_gate import (
    BROAD_MARKET_TRANSMISSION_KEYWORDS,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLASSIFICATION_INPUTS_PATH = (
    ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
)
DEFAULT_PRECLASSIFICATION_PATH = (
    ROOT / "docs/audit/a_share_event_text_preclassification_screen_2026-06-19.json"
)
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_event_text_url_fetchability_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_event_text_url_fetchability_2026-06-19.md"

DIRECT_TRANSMISSION_KEYWORDS = (
    "A股",
    "沪深",
    "上市公司",
    "行业",
    "板块",
    "产业链",
    "供应链",
    "出口",
    "进口",
    "人民币",
    "关税",
    "贸易",
)
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
PRIMARY_END_MARKERS = (
    "财联社声明：",
    "商务合作",
    "热门解锁",
    "相关阅读",
    "评论 热度",
)
PRIMARY_PREFIX_MARKERS = ("打开APP",)


@dataclasses.dataclass(frozen=True)
class FetchResult:
    url: str
    ok: bool
    status: int | None = None
    content_type: str = ""
    elapsed_s: float = 0.0
    html_text: str = ""
    error: str = ""


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _clean_html_text(text: str) -> str:
    text = DROP_BLOCK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    folded = text.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in folded]


def _primary_article_text(clean_text: str) -> str:
    text = clean_text
    for marker in PRIMARY_PREFIX_MARKERS:
        marker_pos = text.find(marker)
        if marker_pos >= 0:
            text = text[marker_pos + len(marker) :].strip()
            break
    end_positions = [text.find(marker) for marker in PRIMARY_END_MARKERS if text.find(marker) >= 0]
    if end_positions:
        text = text[: min(end_positions)].strip()
    return text


def _extract_article(html_text: str) -> dict[str, Any]:
    title_match = TITLE_RE.search(html_text)
    desc_match = META_DESC_RE.search(html_text)
    title = _clean_html_text(title_match.group(1)) if title_match else ""
    description = _clean_html_text(desc_match.group(1)) if desc_match else ""
    clean_text = _clean_html_text(html_text)
    primary_text = _primary_article_text(clean_text)
    return {
        "html_chars": len(html_text),
        "clean_text_chars": len(clean_text),
        "primary_text_chars": len(primary_text),
        "title": title,
        "description": description,
        "primary_text_for_matching": primary_text[:4000],
        "primary_text_preview": primary_text[:600],
    }


def _fetch_url(url: str, *, timeout: float) -> FetchResult:
    started = time.time()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 mvp20-event-text-audit/0.1",
            "Referer": "https://www.cls.cn/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return FetchResult(
                url=url,
                ok=200 <= int(response.status) < 400,
                status=int(response.status),
                content_type=response.headers.get("content-type", ""),
                elapsed_s=round(time.time() - started, 3),
                html_text=body.decode(charset, errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        return FetchResult(
            url=url,
            ok=False,
            status=int(exc.code),
            content_type=exc.headers.get("content-type", "") if exc.headers else "",
            elapsed_s=round(time.time() - started, 3),
            error=f"HTTPError:{exc.code}",
        )
    except Exception as exc:
        return FetchResult(
            url=url,
            ok=False,
            elapsed_s=round(time.time() - started, 3),
            error=f"{type(exc).__name__}:{exc}",
        )


def _unique_url_inputs(classification_inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for row in classification_inputs.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        for headline in row.get("headline_inputs") or []:
            if not isinstance(headline, Mapping):
                continue
            url = str(headline.get("url") or "")
            if not url or url in seen:
                continue
            seen[url] = {
                "url": url,
                "title": headline.get("title"),
                "source": headline.get("source"),
                "first_dependency_dp_id": headline.get("dependency_dp_id"),
            }
    return sorted(seen.values(), key=lambda item: str(item.get("url") or ""))


def _url_evidence(
    url_input: Mapping[str, Any],
    fetch_result: FetchResult,
) -> dict[str, Any]:
    article = _extract_article(fetch_result.html_text) if fetch_result.ok else {}
    primary_text = str(article.get("primary_text_preview") or "")
    return {
        **dict(url_input),
        "fetch_ok": fetch_result.ok,
        "http_status": fetch_result.status,
        "content_type": fetch_result.content_type,
        "fetch_elapsed_s": fetch_result.elapsed_s,
        "fetch_error": fetch_result.error,
        "html_chars": article.get("html_chars", 0),
        "clean_text_chars": article.get("clean_text_chars", 0),
        "primary_text_chars": article.get("primary_text_chars", 0),
        "parsed_title": article.get("title", ""),
        "parsed_description": article.get("description", ""),
        "primary_text_for_matching": article.get("primary_text_for_matching", ""),
        "primary_text_preview": primary_text,
        "primary_text_available": bool(article.get("primary_text_chars")),
    }


def _pre_rows_by_dp(preclassification: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in preclassification.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _row_url_set(row: Mapping[str, Any]) -> set[str]:
    urls: set[str] = set()
    for headline in row.get("headline_inputs") or []:
        if isinstance(headline, Mapping) and headline.get("url"):
            urls.add(str(headline["url"]))
    return urls


def _body_row(
    classification_row: Mapping[str, Any],
    preclassification_row: Mapping[str, Any] | None,
    url_evidence_by_url: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    dp_id = str(classification_row.get("dp_id") or "")
    target_keywords = tuple(TARGET_KEYWORDS.get(dp_id, ()))
    urls = sorted(_row_url_set(classification_row))
    url_assessments: list[dict[str, Any]] = []
    packet_target_hits: set[str] = set()
    packet_direct_hits: set[str] = set()
    packet_broad_hits: set[str] = set()
    sufficient_url_count = 0
    for url in urls:
        evidence = url_evidence_by_url.get(url, {})
        text = str(evidence.get("primary_text_for_matching") or "")
        target_hits = _keyword_hits(text, target_keywords)
        direct_hits = _keyword_hits(text, DIRECT_TRANSMISSION_KEYWORDS)
        broad_hits = _keyword_hits(text, tuple(sorted(BROAD_MARKET_TRANSMISSION_KEYWORDS)))
        packet_target_hits.update(target_hits)
        packet_direct_hits.update(direct_hits)
        packet_broad_hits.update(broad_hits)
        sufficient = bool(target_hits and direct_hits)
        if sufficient:
            sufficient_url_count += 1
        url_assessments.append(
            {
                "url": url,
                "title": evidence.get("title"),
                "fetch_ok": bool(evidence.get("fetch_ok")),
                "primary_text_chars": int(evidence.get("primary_text_chars") or 0),
                "target_keyword_hits": target_hits,
                "direct_transmission_keyword_hits": direct_hits,
                "broad_market_transmission_keyword_hits": broad_hits,
                "body_signal_sufficient_for_classifier": sufficient,
                "primary_text_preview": str(evidence.get("primary_text_preview") or ""),
            }
        )
    body_status = "body_signal_sufficient_for_classifier" if sufficient_url_count else (
        "body_available_but_insufficient"
        if any(item["primary_text_chars"] for item in url_assessments)
        else "body_unavailable"
    )
    return {
        "dp_id": dp_id,
        "score_target": classification_row.get("score_target"),
        "source_dependencies": classification_row.get("source_dependencies") or [],
        "url_count": len(urls),
        "url_fetch_ok_count": sum(1 for item in url_assessments if item["fetch_ok"]),
        "body_text_available_count": sum(
            1 for item in url_assessments if item["primary_text_chars"] > 0
        ),
        "target_keyword_hits": sorted(packet_target_hits),
        "direct_transmission_keyword_hits": sorted(packet_direct_hits),
        "broad_market_transmission_keyword_hits": sorted(packet_broad_hits),
        "body_signal_sufficient_url_count": sufficient_url_count,
        "body_signal_sufficient_for_classifier": bool(sufficient_url_count),
        "body_status": body_status,
        "preclassification_status": (
            preclassification_row or {}
        ).get("screening_status"),
        "review_status": "review_required",
        "known_candidate_allowed": False,
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "url_assessments": url_assessments,
    }


def build_report(
    *,
    classification_inputs_path: Path,
    preclassification_path: Path,
    timeout: float = 10.0,
    fetcher: Callable[[str, float], FetchResult] | None = None,
) -> dict[str, Any]:
    started = time.time()
    classification_inputs = _load_json(classification_inputs_path)
    preclassification = _load_json(preclassification_path)
    fetcher = fetcher or (lambda url, timeout: _fetch_url(url, timeout=timeout))
    url_inputs = _unique_url_inputs(classification_inputs)
    url_rows: list[dict[str, Any]] = []
    for url_input in url_inputs:
        url = str(url_input["url"])
        url_rows.append(_url_evidence(url_input, fetcher(url, timeout)))
    url_evidence_by_url = {str(row["url"]): row for row in url_rows}
    pre_rows = _pre_rows_by_dp(preclassification)
    body_rows = [
        _body_row(
            classification_row=row,
            preclassification_row=pre_rows.get(str(row.get("dp_id") or "")),
            url_evidence_by_url=url_evidence_by_url,
        )
        for row in classification_inputs.get("rows") or []
        if isinstance(row, Mapping)
    ]
    body_rows.sort(key=lambda item: str(item.get("dp_id") or ""))
    status_counts = Counter(str(row.get("body_status") or "") for row in body_rows)
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "classification_inputs_path": _portable_path(classification_inputs_path),
            "preclassification_path": _portable_path(preclassification_path),
            "network_timeout_s": timeout,
        },
        "summary": {
            "unique_url_count": len(url_rows),
            "fetch_success_count": sum(1 for row in url_rows if row.get("fetch_ok")),
            "fetch_failure_count": sum(1 for row in url_rows if not row.get("fetch_ok")),
            "primary_text_available_url_count": sum(
                1 for row in url_rows if row.get("primary_text_available")
            ),
            "body_packet_count": len(body_rows),
            "body_text_available_packet_count": sum(
                1 for row in body_rows if int(row.get("body_text_available_count") or 0) > 0
            ),
            "body_target_hit_packet_count": sum(
                1 for row in body_rows if row.get("target_keyword_hits")
            ),
            "body_direct_transmission_hit_packet_count": sum(
                1 for row in body_rows if row.get("direct_transmission_keyword_hits")
            ),
            "body_broad_market_transmission_hit_packet_count": sum(
                1 for row in body_rows if row.get("broad_market_transmission_keyword_hits")
            ),
            "body_signal_sufficient_for_classifier_count": sum(
                1 for row in body_rows if row.get("body_signal_sufficient_for_classifier")
            ),
            "known_candidate_allowed_count": 0,
            "safe_to_upsert_without_review_count": 0,
            "runtime_write_allowed_count": 0,
            "production_write_allowed_count": 0,
            "body_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "url_rows": url_rows,
        "rows": body_rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text URL fetchability",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unique URLs: `{summary['unique_url_count']}`",
        f"- Fetch success: `{summary['fetch_success_count']}`",
        f"- Primary text available URLs: `{summary['primary_text_available_url_count']}`",
        f"- Body packets: `{summary['body_packet_count']}`",
        f"- Body target-hit packets: `{summary['body_target_hit_packet_count']}`",
        f"- Body direct-transmission-hit packets: `{summary['body_direct_transmission_hit_packet_count']}`",
        f"- Body signal sufficient for classifier: `{summary['body_signal_sufficient_for_classifier_count']}`",
        f"- Known candidates allowed: `{summary['known_candidate_allowed_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## URL Fetches",
        "",
        "| title | status | primary chars | url |",
        "|---|---:|---:|---|",
    ]
    for row in report["url_rows"]:
        lines.append(
            "| "
            f"{row.get('title', '')} | "
            f"{row.get('http_status', '-') if row.get('fetch_ok') else row.get('fetch_error', '-')} | "
            f"{row.get('primary_text_chars', 0)} | "
            f"{row.get('url', '')} |"
        )
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | target | body status | urls ok | target hits | direct hits | classifier-ready |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('body_status', '-')}` | "
            f"{row.get('url_fetch_ok_count', 0)} | "
            f"{len(row.get('target_keyword_hits') or [])} | "
            f"{len(row.get('direct_transmission_keyword_hits') or [])} | "
            f"{'yes' if row.get('body_signal_sufficient_for_classifier') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Fetchability and body text are evidence inputs only.",
            "- Body-level target hits still need direct A-share/industry/entity/supply-chain/trade transmission before classifier promotion.",
            "- This audit emits no Known candidates and performs no runtime writes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--classification-inputs-path",
        type=Path,
        default=DEFAULT_CLASSIFICATION_INPUTS_PATH,
    )
    parser.add_argument(
        "--preclassification-path",
        type=Path,
        default=DEFAULT_PRECLASSIFICATION_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        classification_inputs_path=args.classification_inputs_path,
        preclassification_path=args.preclassification_path,
        timeout=args.timeout,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
