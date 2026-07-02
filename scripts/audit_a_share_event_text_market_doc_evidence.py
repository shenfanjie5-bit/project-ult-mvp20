#!/usr/bin/env python3
"""Search DOCKCASE market documents for A-share event-text evidence.

The first-pass CLS event-text packets are fetchable but need local evidence for
target events plus direct A-share transmission. This read-only audit scans the
local DOCKCASE news HTML corpus for conservative candidate snippets that can be
reviewed later. It preserves the full first-pass event-text universe so the
policy-draft pass remains reproducible after some rows become Known.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_local_single_dependency_policy_drafts import (  # noqa: E402
    ROOT,
    _load_json,
    _portable_path,
)


DEFAULT_EVENT_UNKNOWN_PATH = (
    ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
)
DEFAULT_MARKET_ROOT = Path("/Volumes/dockcase2tb/market_data")
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_event_text_market_doc_evidence_2026-06-19.md"
)

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DROP_BLOCK_RE = re.compile(
    r"<(script|style|noscript|svg)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；;!?])\s*|\n+")

TARGET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "L0.compete.new_entrant": (
        "新进入者",
        "新玩家",
        "入局",
        "跨界进入",
        "新厂商",
        "新公司",
    ),
    "L0.compete.price_war": (
        "价格战",
        "降价",
        "低价竞争",
        "补贴大战",
        "促销",
        "打价格",
    ),
    "L0.compete.share_concentration": (
        "集中度",
        "市占率",
        "市场份额",
        "份额提升",
        "出清",
        "行业集中",
    ),
    "L0.policy.access_license": (
        "准入",
        "牌照",
        "许可",
        "审批",
        "备案",
        "资质",
        "目录",
    ),
    "L0.policy.regulation": (
        "监管",
        "处罚",
        "调查",
        "问询",
        "反垄断",
        "合规",
        "制裁",
    ),
    "L0.policy.subsidy": (
        "补贴",
        "扶持",
        "财政支持",
        "以旧换新",
        "贴息",
        "奖励资金",
        "政策支持",
    ),
    "L0.policy.tax_trade": (
        "关税",
        "出口管制",
        "贸易壁垒",
        "反倾销",
        "进口税",
        "301调查",
        "制裁",
    ),
    "L0.tech.ai_automation": (
        "人工智能",
        "AI",
        "大模型",
        "自动化",
        "机器人",
        "智能制造",
        "算力",
    ),
    "L0.tech.breakthrough": (
        "突破",
        "技术突破",
        "首创",
        "研发成功",
        "量产",
        "新技术",
        "重大进展",
    ),
    "L0.tech.substitute_tech": (
        "替代",
        "国产替代",
        "替代技术",
        "进口替代",
        "颠覆",
        "取代",
    ),
    "L8.shock.black_swan": (
        "黑天鹅",
        "冲突",
        "战争",
        "袭击",
        "枪击",
        "地震",
        "爆炸",
        "霍尔木兹",
        "核电站",
        "受损",
    ),
    "L8.shock.supply_break": (
        "供应中断",
        "断供",
        "停产",
        "缺货",
        "物流受阻",
        "航运受阻",
        "封锁",
        "延迟交付",
    ),
}

DIRECT_TRANSMISSION_KEYWORDS = (
    "A股",
    "A股公司",
    "上市公司",
    "个股",
    "板块",
    "概念股",
    "产业链",
    "供应链",
    "出口",
    "进口",
    "沪深",
    "创业板",
)
BROAD_MARKET_ONLY_KEYWORDS = (
    "A50",
    "富时中国A50",
    "股指期货",
    "期货夜盘",
    "三大指数",
    "沪指",
    "深成指",
)


def _clean_html_text(text: str) -> str:
    text = DROP_BLOCK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _html_title(raw: str) -> str:
    match = TITLE_RE.search(raw)
    return _clean_html_text(match.group(1)) if match else ""


def _primary_article_text(text: str) -> str:
    cut_markers = (
        "财联社声明",
        "郑重声明",
        "相关阅读",
        "热门解锁",
        "商务合作",
        "展开 收起 评论",
        "评论 热度 最新",
    )
    cut_positions = [text.find(marker) for marker in cut_markers if marker in text]
    if cut_positions:
        text = text[: min(pos for pos in cut_positions if pos >= 0)]
    return text.strip()


def _iter_html_files(market_root: Path) -> Iterable[Path]:
    news_root = market_root / "news"
    if not news_root.exists():
        return []
    return sorted(path for path in news_root.rglob("*.html") if path.is_file())


def _hits(text: str, keywords: Iterable[str]) -> list[str]:
    return sorted({keyword for keyword in keywords if keyword in text})


def _sentences_with_hits(
    text: str,
    target_keywords: tuple[str, ...],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sentence in SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        target_hits = _hits(sentence, target_keywords)
        direct_hits = _hits(sentence, DIRECT_TRANSMISSION_KEYWORDS)
        if target_hits and direct_hits:
            out.append(
                {
                    "target_hits": target_hits,
                    "direct_transmission_hits": direct_hits,
                    "excerpt": sentence[:320],
                }
            )
    return out


def _doc_record(path: Path, market_root: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _primary_article_text(_clean_html_text(raw))
    return {
        "path": _portable_path(path) if path.is_relative_to(ROOT) else str(path),
        "market_relative_path": str(path.relative_to(market_root)),
        "title": _html_title(raw),
        "text": text,
    }


def _example(
    *,
    doc: Mapping[str, Any],
    target_hits: list[str],
    direct_hits: list[str],
    broad_hits: list[str],
    same_sentence_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    text = str(doc.get("text") or "")
    first_keyword = (target_hits + direct_hits + broad_hits)[0] if (
        target_hits or direct_hits or broad_hits
    ) else ""
    pos = text.find(first_keyword) if first_keyword else -1
    if pos < 0:
        pos = 0
    start = max(0, pos - 120)
    excerpt = text[start : start + 420]
    return {
        "path": doc.get("path"),
        "market_relative_path": doc.get("market_relative_path"),
        "title": doc.get("title"),
        "target_hits": target_hits,
        "direct_transmission_hits": direct_hits,
        "broad_market_hits": broad_hits,
        "same_sentence_hits": same_sentence_hits[:2],
        "excerpt": excerpt,
    }


def _unknown_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("production_write_allowed"):
            continue
        rows.append(dict(row))
    return rows


def build_report(
    *,
    event_unknown_path: Path,
    market_root: Path,
    retained_examples_per_dp: int = 5,
) -> dict[str, Any]:
    started = time.time()
    event_unknown = _load_json(event_unknown_path)
    unknown_rows = _unknown_rows(event_unknown)
    dp_ids = [str(row.get("dp_id") or "") for row in unknown_rows]
    target_keywords_by_dp = {
        dp_id: TARGET_KEYWORDS.get(dp_id, ())
        for dp_id in dp_ids
        if TARGET_KEYWORDS.get(dp_id)
    }

    row_state: dict[str, dict[str, Any]] = {
        dp_id: {
            "dp_id": dp_id,
            "score_target": next(
                (row.get("score_target") for row in unknown_rows if row.get("dp_id") == dp_id),
                None,
            ),
            "target_keywords": list(target_keywords_by_dp.get(dp_id, ())),
            "docs_with_target_evidence": 0,
            "docs_with_direct_transmission": 0,
            "docs_with_target_and_direct": 0,
            "docs_with_same_sentence_target_direct": 0,
            "docs_with_broad_market_only": 0,
            "retained_examples": [],
            "market_doc_review_candidate": False,
            "auto_known_candidate_allowed": False,
            "review_required": True,
            "safe_to_upsert_without_review": False,
            "production_write_allowed": False,
        }
        for dp_id in dp_ids
    }

    html_files = list(_iter_html_files(market_root))
    read_error_count = 0
    for path in html_files:
        try:
            doc = _doc_record(path, market_root)
        except Exception:  # noqa: BLE001
            read_error_count += 1
            continue
        text = str(doc.get("text") or "")
        if not text:
            continue
        direct_hits = _hits(text, DIRECT_TRANSMISSION_KEYWORDS)
        broad_hits = _hits(text, BROAD_MARKET_ONLY_KEYWORDS)
        for dp_id, target_keywords in target_keywords_by_dp.items():
            target_hits = _hits(text, target_keywords)
            if not target_hits and not broad_hits:
                continue
            same_sentence_hits = _sentences_with_hits(text, target_keywords)
            row = row_state[dp_id]
            if target_hits:
                row["docs_with_target_evidence"] += 1
            if direct_hits:
                row["docs_with_direct_transmission"] += 1
            if target_hits and direct_hits:
                row["docs_with_target_and_direct"] += 1
            if same_sentence_hits:
                row["docs_with_same_sentence_target_direct"] += 1
            if broad_hits and not direct_hits:
                row["docs_with_broad_market_only"] += 1
            examples = row["retained_examples"]
            if target_hits and direct_hits and same_sentence_hits and len(
                examples
            ) < retained_examples_per_dp:
                examples.append(
                    _example(
                        doc=doc,
                        target_hits=target_hits,
                        direct_hits=direct_hits,
                        broad_hits=broad_hits,
                        same_sentence_hits=same_sentence_hits,
                    )
                )

    rows = []
    for dp_id in dp_ids:
        row = row_state[dp_id]
        row["market_doc_review_candidate"] = (
            row["docs_with_same_sentence_target_direct"] > 0
        )
        if row["docs_with_target_evidence"] == 0:
            row["resolution_status"] = "market_docs_require_target_event_evidence"
        elif row["docs_with_same_sentence_target_direct"] == 0:
            row["resolution_status"] = "market_docs_require_direct_transmission_link"
        else:
            row["resolution_status"] = "market_docs_candidate_requires_review"
        rows.append(row)

    rows.sort(key=lambda row: str(row["dp_id"]))
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "event_unknown_path": _portable_path(event_unknown_path),
            "market_root": str(market_root),
        },
        "summary": {
            "unknown_event_text_rows_checked": len(rows),
            "market_html_files_scanned": len(html_files),
            "market_html_read_error_count": read_error_count,
            "rows_with_market_doc_target_evidence_count": sum(
                1 for row in rows if row["docs_with_target_evidence"] > 0
            ),
            "rows_with_market_doc_direct_transmission_count": sum(
                1 for row in rows if row["docs_with_direct_transmission"] > 0
            ),
            "rows_with_market_doc_target_and_direct_count": sum(
                1 for row in rows if row["docs_with_target_and_direct"] > 0
            ),
            "rows_with_same_sentence_candidate_count": sum(
                1 for row in rows if row["docs_with_same_sentence_target_direct"] > 0
            ),
            "rows_still_requiring_target_evidence_count": sum(
                1 for row in rows if row["docs_with_target_evidence"] == 0
            ),
            "rows_still_requiring_direct_transmission_link_count": sum(
                1
                for row in rows
                if row["docs_with_target_evidence"] > 0
                and row["docs_with_same_sentence_target_direct"] == 0
            ),
            "market_doc_review_candidate_count": sum(
                1 for row in rows if row["market_doc_review_candidate"]
            ),
            "auto_known_candidate_count": 0,
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text market document evidence",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown event-text rows checked: `{summary['unknown_event_text_rows_checked']}`",
        f"- Market HTML files scanned: `{summary['market_html_files_scanned']}`",
        f"- Market HTML read errors: `{summary['market_html_read_error_count']}`",
        f"- Rows with market-doc target evidence: `{summary['rows_with_market_doc_target_evidence_count']}`",
        f"- Rows with market-doc direct transmission: `{summary['rows_with_market_doc_direct_transmission_count']}`",
        f"- Rows with target and direct transmission in a document: `{summary['rows_with_market_doc_target_and_direct_count']}`",
        f"- Rows with same-sentence target/direct candidates: `{summary['rows_with_same_sentence_candidate_count']}`",
        f"- Rows still requiring target evidence: `{summary['rows_still_requiring_target_evidence_count']}`",
        f"- Rows still requiring direct transmission link: `{summary['rows_still_requiring_direct_transmission_link_count']}`",
        f"- Market-doc review candidates: `{summary['market_doc_review_candidate_count']}`",
        f"- Auto Known candidates allowed: `{summary['auto_known_candidate_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | target docs | direct docs | target+direct docs | same-sentence candidates | status | production write |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{row['docs_with_target_evidence']} | "
            f"{row['docs_with_direct_transmission']} | "
            f"{row['docs_with_target_and_direct']} | "
            f"{row['docs_with_same_sentence_target_direct']} | "
            f"`{row['resolution_status']}` | "
            f"{'yes' if row['production_write_allowed'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Same-sentence candidates are review inputs only, not automatic Known values.",
            "- Direct A-share transmission excludes broad A50/futures-only market context.",
            "- Production score-affecting writes remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-unknown-path", type=Path, default=DEFAULT_EVENT_UNKNOWN_PATH)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--retained-examples-per-dp", type=int, default=5)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        event_unknown_path=args.event_unknown_path,
        market_root=args.market_root,
        retained_examples_per_dp=args.retained_examples_per_dp,
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
