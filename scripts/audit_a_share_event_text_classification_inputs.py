#!/usr/bin/env python3
"""Package title-level inputs for A-share event-text classification.

This audit is read-only. It gathers the current runtime headline/event
dependency evidence for the 12 event-text Unknown rows and records exactly what
an LLM or reviewer still needs to classify before a Known review packet can be
emitted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_event_text_policy_drafts import _policy_for


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVENT_DRAFTS_PATH = ROOT / "docs/audit/a_share_event_text_policy_drafts_2026-06-19.json"
DEFAULT_CANDIDATE_PATH = ROOT / "docs/audit/a_share_gap_candidate_evidence_2026-06-19.json"
DEFAULT_READINESS_PATH = ROOT / "docs/audit/a_share_non_manual_candidate_readiness_2026-06-19.json"
DEFAULT_JSON_OUTPUT = ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.json"
DEFAULT_MD_OUTPUT = ROOT / "docs/audit/a_share_event_text_classification_inputs_2026-06-19.md"


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


def _rows_by_dp(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _dependencies(candidate_row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    candidate_input = (
        candidate_row.get("candidate_input")
        if isinstance(candidate_row, Mapping)
        else None
    )
    if not isinstance(candidate_input, Mapping):
        return []
    return [
        dict(dep)
        for dep in candidate_input.get("dependencies") or []
        if isinstance(dep, Mapping)
    ]


def _extract_headlines(dep: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    dep_id = str(dep.get("dp_id") or "")
    for sample in dep.get("sample_rows") or []:
        if not isinstance(sample, Mapping):
            continue
        compact = sample.get("value_json_compact")
        if not isinstance(compact, Mapping):
            continue
        for item in compact.get("top_headlines") or []:
            if not isinstance(item, Mapping) or not item.get("title"):
                continue
            out.append(
                {
                    "dependency_dp_id": dep_id,
                    "ts_code": sample.get("ts_code"),
                    "title": item.get("title"),
                    "time": item.get("time"),
                    "url": item.get("url"),
                    "source": item.get("source") or sample.get("source"),
                }
            )
    return out


def _dependency_snapshot(dep: Mapping[str, Any]) -> dict[str, Any]:
    sample_rows = [
        sample
        for sample in dep.get("sample_rows") or []
        if isinstance(sample, Mapping)
    ]
    compact_keys: set[str] = set()
    for sample in sample_rows:
        compact = sample.get("value_json_compact")
        if isinstance(compact, Mapping):
            compact_keys.update(str(key) for key in compact.keys())
    return {
        "dp_id": dep.get("dp_id"),
        "row_count": dep.get("row_count"),
        "known_count": dep.get("known_count"),
        "ts_code_count": dep.get("ts_code_count"),
        "namespace_counts": dep.get("namespace_counts") or {},
        "latest_updated_at_iso": dep.get("latest_updated_at_iso"),
        "sample_value_keys": sorted(compact_keys),
        "headline_count": len(_extract_headlines(dep)),
        "sample_rows": sample_rows,
    }


def _classification_schema(dp_id: str, score_target: str) -> dict[str, Any]:
    return {
        "target_dp_id": dp_id,
        "score_target": score_target,
        "output_contract": {
            "data_status": "Known | NotApplicable | Unknown",
            "event_match": "yes | no | unknown",
            "event_concept": "short concept label tied to the target dp_id",
            "direction": "positive | negative | neutral | mixed | unknown",
            "magnitude": "bounded numeric scalar in [-1, 1] when Known",
            "a_share_transmission": "direct | industry | macro | sentiment | none | unknown",
            "evidence_refs": "non-empty list of dependency/headline refs",
            "rationale": "short source-grounded explanation",
        },
        "write_policy": {
            "review_status": "review_required",
            "safe_to_upsert_without_review": False,
            "production_write_allowed": False,
        },
    }


def _classification_input_row(
    draft_row: Mapping[str, Any],
    candidate_row: Mapping[str, Any] | None,
    readiness_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    dp_id = str(draft_row.get("dp_id") or "")
    score_target = str(draft_row.get("score_target") or "")
    deps = _dependencies(candidate_row)
    headlines: list[dict[str, Any]] = []
    for dep in deps:
        headlines.extend(_extract_headlines(dep))
    blocked_reason, required_policy = _policy_for(dp_id)
    has_full_text = any(
        "body" in (sample.get("value_json_compact") or {})
        or "content" in (sample.get("value_json_compact") or {})
        for dep in deps
        for sample in dep.get("sample_rows") or []
        if isinstance(sample, Mapping)
    )
    return {
        "dp_id": dp_id,
        "score_target": score_target,
        "source_dependencies": [dep.get("dp_id") for dep in deps],
        "dependency_snapshots": [_dependency_snapshot(dep) for dep in deps],
        "headline_inputs": headlines,
        "headline_input_count": len(headlines),
        "unique_headline_count": len(
            {str(item.get("title") or "") for item in headlines if item.get("title")}
        ),
        "title_level_input_ready": bool(headlines),
        "full_article_text_available": has_full_text,
        "classification_status": "classification_input_ready" if headlines else "missing_headline_input",
        "blocked_reason": blocked_reason,
        "required_policy": required_policy,
        "classification_schema": _classification_schema(dp_id, score_target),
        "readiness_route_bucket": (readiness_row or {}).get("route_bucket"),
        "readiness_dependency_state": (readiness_row or {}).get("dependency_readiness"),
        "review_status": "review_required",
        "runtime_write_allowed": False,
        "production_write_allowed": False,
    }


def build_report(
    *,
    event_drafts_path: Path,
    candidate_path: Path,
    readiness_path: Path,
) -> dict[str, Any]:
    started = time.time()
    event_drafts = _load_json(event_drafts_path)
    candidate = _load_json(candidate_path)
    readiness = _load_json(readiness_path)
    candidate_rows = _rows_by_dp(candidate)
    readiness_rows = _rows_by_dp(readiness)
    rows = [
        _classification_input_row(
            draft_row=row,
            candidate_row=candidate_rows.get(str(row.get("dp_id") or "")),
            readiness_row=readiness_rows.get(str(row.get("dp_id") or "")),
        )
        for row in event_drafts.get("rows") or []
        if isinstance(row, Mapping)
        and str(row.get("draft_status") or "").startswith("unknown_")
    ]
    rows.sort(key=lambda row: str(row.get("dp_id") or ""))
    status_counts = Counter(str(row.get("classification_status") or "") for row in rows)
    source_dependency_counts = Counter(
        dep
        for row in rows
        for dep in row.get("source_dependencies") or []
        if dep
    )
    unique_headlines = {
        str(item.get("title") or "")
        for row in rows
        for item in row.get("headline_inputs") or []
        if item.get("title")
    }
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "event_drafts_path": _portable_path(event_drafts_path),
            "candidate_path": _portable_path(candidate_path),
            "readiness_path": _portable_path(readiness_path),
        },
        "summary": {
            "classification_input_packet_count": len(rows),
            "classification_input_ready_count": sum(
                1 for row in rows if row.get("classification_status") == "classification_input_ready"
            ),
            "missing_headline_input_count": sum(
                1 for row in rows if row.get("classification_status") == "missing_headline_input"
            ),
            "headline_input_count": sum(int(row.get("headline_input_count") or 0) for row in rows),
            "unique_headline_count": len(unique_headlines),
            "full_article_text_available_count": sum(
                1 for row in rows if row.get("full_article_text_available")
            ),
            "title_level_only_count": sum(
                1
                for row in rows
                if row.get("title_level_input_ready")
                and not row.get("full_article_text_available")
            ),
            "classified_known_count": 0,
            "review_required_count": len(rows),
            "safe_to_upsert_without_review_count": 0,
            "production_write_allowed_count": 0,
            "classification_status_counts": dict(sorted(status_counts.items())),
            "source_dependency_counts": dict(sorted(source_dependency_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share event-text classification inputs",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Classification input packets: `{summary['classification_input_packet_count']}`",
        f"- Input-ready packets: `{summary['classification_input_ready_count']}`",
        f"- Missing headline input: `{summary['missing_headline_input_count']}`",
        f"- Headline inputs: `{summary['headline_input_count']}`",
        f"- Unique headlines: `{summary['unique_headline_count']}`",
        f"- Full article text available: `{summary['full_article_text_available_count']}`",
        f"- Title-level only packets: `{summary['title_level_only_count']}`",
        f"- Classified Known packets: `{summary['classified_known_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | target | status | headline inputs | unique titles | full text |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row.get('score_target', '-')}` | "
            f"`{row.get('classification_status', '-')}` | "
            f"{row.get('headline_input_count', 0)} | "
            f"{row.get('unique_headline_count', 0)} | "
            f"{'yes' if row.get('full_article_text_available') else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- These are classification inputs, not classified Known values.",
            "- Current evidence is title-level; full article text is not present in these packets.",
            "- The classifier/reviewer must still decide concept, direction, magnitude, and A-share transmission before any Known review packet can be emitted.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-drafts-path", type=Path, default=DEFAULT_EVENT_DRAFTS_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--readiness-path", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        event_drafts_path=args.event_drafts_path,
        candidate_path=args.candidate_path,
        readiness_path=args.readiness_path,
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
