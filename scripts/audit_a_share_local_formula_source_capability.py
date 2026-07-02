#!/usr/bin/env python3
"""Audit source capability for the remaining local formula blockers.

This read-only audit checks whether the current Tushare/DOCKCASE inventory can
cover the missing formula inputs for rent burden and product ASP. It separates
field/header availability from score readiness: a matching source column is only
context until the missing denominator, quantity/price-index, and formula policy
can produce a bounded value_json.score.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_review_staging_manifest import ROOT


DEFAULT_REVIEW_PACKETS_PATH = (
    ROOT / "docs/audit/a_share_unknown_local_formula_review_packets_2026-06-19.json"
)
DEFAULT_SEMANTICS_PATH = ROOT / "docs/audit/dockcase_csv_semantics_2026-06-18.json"
DEFAULT_FILE_EVIDENCE_PATH = (
    ROOT / "docs/audit/dockcase_csv_file_evidence_2026-06-19.jsonl.gz"
)
DEFAULT_TUSHARE_SOURCE_PATH = ROOT / "mvp20/sources/tushare_source.py"
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_formula_source_capability_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_formula_source_capability_2026-06-19.md"
)

TRADING_VOLUME_PATH_TERMS = (
    "行情数据",
    "资金流向",
    "指数专题",
    "打板专题",
    "大宗交易",
    "债券",
    "期货",
    "现货",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(path)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    text_lower = text.lower()
    return any(term.lower() in text_lower for term in terms)


def _column_matches(column: str, terms: Iterable[str]) -> bool:
    column_lower = column.lower()
    for term in terms:
        term_lower = term.lower()
        if any(ord(char) > 127 for char in term):
            if term_lower in column_lower:
                return True
        elif column_lower == term_lower:
            return True
    return False


def _profile_for(sig: Mapping[str, Any], column: str) -> dict[str, Any] | None:
    for kind, profiles in (sig.get("column_profiles") or {}).items():
        for profile in profiles or []:
            if isinstance(profile, Mapping) and profile.get("column") == column:
                return {"kind": kind, **dict(profile)}
    return None


def _signature_matches(
    semantics: Mapping[str, Any],
    *,
    column_terms: Iterable[str] = (),
    path_terms: Iterable[str] = (),
    max_matches: int = 12,
) -> list[dict[str, Any]]:
    column_terms = list(column_terms)
    path_terms = list(path_terms)
    matches: list[dict[str, Any]] = []
    for sig in semantics.get("signatures") or []:
        if not isinstance(sig, Mapping):
            continue
        columns = [str(column) for column in sig.get("columns") or []]
        examples = [str(example) for example in sig.get("examples") or []]
        column_hits = [
            column for column in columns if column_terms and _column_matches(column, column_terms)
        ]
        path_hits = [
            example for example in examples if path_terms and _contains_any(example, path_terms)
        ]
        if not column_hits and not path_hits:
            continue
        profile_hits = [
            _profile_for(sig, column)
            for column in column_hits[:8]
            if _profile_for(sig, column) is not None
        ]
        matches.append(
            {
                "signature_rank": sig.get("signature_rank"),
                "file_count": sig.get("file_count"),
                "column_hits": column_hits[:12],
                "path_hits": path_hits[:5],
                "examples": examples[:3],
                "profile_hits": profile_hits,
                "trading_volume_like": any(
                    _contains_any(example, TRADING_VOLUME_PATH_TERMS)
                    for example in examples
                ),
            }
        )
    matches.sort(
        key=lambda item: (
            1 if item.get("trading_volume_like") else 0,
            int(item.get("signature_rank") or 999999),
        )
    )
    return matches[:max_matches]


def _iter_file_evidence(path: Path) -> Iterable[Mapping[str, Any]]:
    if not path.exists():
        return
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[arg-type]
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, Mapping):
                yield payload


def _path_scan(
    path: Path,
    *,
    terms: Iterable[str],
    max_examples: int = 20,
) -> dict[str, Any]:
    terms = list(terms)
    match_count = 0
    examples: list[str] = []
    scanned = 0
    for row in _iter_file_evidence(path):
        scanned += 1
        file_path = str(row.get("path") or "")
        if not _contains_any(file_path, terms):
            continue
        match_count += 1
        if len(examples) < max_examples:
            examples.append(file_path)
    return {
        "files_scanned": scanned,
        "path_match_count": match_count,
        "path_examples": examples,
    }


def _source_hits(path: Path, terms: Iterable[str], max_hits: int = 20) -> dict[str, Any]:
    terms = list(terms)
    if not path.exists():
        return {"source_file_exists": False, "hit_count": 0, "hits": []}
    hits: list[dict[str, Any]] = []
    hit_count = 0
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _contains_any(line, terms):
            continue
        hit_count += 1
        if len(hits) < max_hits:
            hits.append({"line": line_no, "text": line.strip()[:240]})
    return {"source_file_exists": True, "hit_count": hit_count, "hits": hits}


def _non_empty_profile_count(matches: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for match in matches:
        for profile in match.get("profile_hits") or []:
            if not isinstance(profile, Mapping):
                continue
            if int(profile.get("non_empty") or 0) > 0:
                count += 1
    return count


def _column_hit_count(matches: Iterable[Mapping[str, Any]]) -> int:
    return sum(len(match.get("column_hits") or []) for match in matches)


def _check(
    *,
    input_name: str,
    status: str,
    conclusion: str,
    next_action: str,
    semantics: Mapping[str, Any],
    file_evidence_path: Path,
    tushare_source_path: Path,
    column_terms: Iterable[str],
    path_terms: Iterable[str],
    source_terms: Iterable[str],
    required_for_formula: bool = True,
) -> dict[str, Any]:
    signature_matches = _signature_matches(
        semantics,
        column_terms=column_terms,
        path_terms=path_terms,
    )
    path_scan = _path_scan(file_evidence_path, terms=path_terms)
    source_hits = _source_hits(tushare_source_path, source_terms)
    return {
        "input_name": input_name,
        "required_for_formula": required_for_formula,
        "source_status": status,
        "source_candidate_present": bool(signature_matches or path_scan["path_match_count"]),
        "non_empty_profile_hit_count": _non_empty_profile_count(signature_matches),
        "column_hit_count": _column_hit_count(signature_matches),
        "signature_match_count": len(signature_matches),
        "path_match_count": path_scan["path_match_count"],
        "tushare_source_hit_count": source_hits["hit_count"],
        "signature_matches": signature_matches,
        "path_scan": path_scan,
        "tushare_source_hits": source_hits,
        "formula_blocker_resolved_by_current_sources": False,
        "conclusion": conclusion,
        "next_action": next_action,
    }


def _review_rows(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = dict(row)
    return rows


def _rent_row(
    *,
    review_row: Mapping[str, Any],
    semantics: Mapping[str, Any],
    file_evidence_path: Path,
    tushare_source_path: Path,
) -> dict[str, Any]:
    checks = [
        _check(
            input_name="lease_proxy_numerator",
            status="candidate_proxy_present_review_required",
            conclusion=(
                "DOCKCASE cashflow has use_right_asset_dep with non-empty samples, "
                "but it is a proxy rather than direct rent expense."
            ),
            next_action="Review whether right-of-use asset depreciation is acceptable as a conservative lease-burden proxy.",
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
            column_terms=["use_right_asset_dep"],
            path_terms=["现金流量表", "租赁", "使用权"],
            source_terms=["use_right_asset_dep", "cashflow"],
        ),
        _check(
            input_name="direct_lease_payment",
            status="header_available_but_sample_empty",
            conclusion=(
                "The cashflow header includes fa_fnc_leases, but the sampled "
                "semantic profile has zero non-empty rows."
            ),
            next_action="Run a wider company/date scan for fa_fnc_leases, then fall back to annual-report lease-note extraction if it remains sparse.",
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
            column_terms=["fa_fnc_leases", "lease", "rent"],
            path_terms=["租赁", "租金", "使用权", "现金流量表"],
            source_terms=["fa_fnc_leases", "cashflow"],
        ),
        _check(
            input_name="denominator",
            status="candidate_denominator_available_policy_required",
            conclusion=(
                "Revenue, operating cash flow, operating cost, and balance-sheet "
                "scale fields exist, but no denominator has been reviewed for "
                "the rent-burden formula."
            ),
            next_action="Choose and bound a denominator policy, for example revenue, operating cash flow, or total operating cost.",
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
            column_terms=[
                "total_revenue",
                "revenue",
                "oper_cost",
                "n_cashflow_act",
                "c_inf_fr_operate_a",
                "c_paid_goods_s",
                "total_assets",
                "total_liab",
            ],
            path_terms=["利润表", "现金流量表", "资产负债表"],
            source_terms=["total_revenue", "oper_cost", "n_cashflow_act", "balancesheet"],
        ),
        {
            "input_name": "formula_policy",
            "required_for_formula": True,
            "source_status": "review_policy_required",
            "source_candidate_present": False,
            "non_empty_profile_hit_count": 0,
            "column_hit_count": 0,
            "signature_match_count": 0,
            "path_match_count": 0,
            "tushare_source_hit_count": 0,
            "signature_matches": [],
            "path_scan": {"files_scanned": 0, "path_match_count": 0, "path_examples": []},
            "tushare_source_hits": {"source_file_exists": True, "hit_count": 0, "hits": []},
            "formula_blocker_resolved_by_current_sources": False,
            "conclusion": "Formula bounds and proxy policy are governance decisions, not data-source fields.",
            "next_action": "Define cap/floor, direction, denominator, and confidence policy before any Known draft.",
        },
    ]
    return _row("L0.cost.rent", review_row, checks)


def _asp_row(
    *,
    review_row: Mapping[str, Any],
    semantics: Mapping[str, Any],
    file_evidence_path: Path,
    tushare_source_path: Path,
) -> dict[str, Any]:
    quantity_check = _check(
        input_name="quantity_or_price_index",
        status="external_or_text_required",
        conclusion=(
            "The current structured inventory has business-segment revenue and "
            "macro PPI context, but no company product quantity, shipment volume, "
            "or governed product-level price index ready for ASP."
        ),
        next_action="Extract product sales volume/shipment volume from annual reports or exchange Q&A, or map a governed product/industry price index.",
        semantics=semantics,
        file_evidence_path=file_evidence_path,
        tushare_source_path=tushare_source_path,
        column_terms=[
            "unit_volume",
            "shipment_volume",
            "product_quantity",
            "sales_volume",
            "ppi_yoy",
            "ppi_mp_yoy",
            "ppi_mom",
            "price_avg",
        ],
        path_terms=["销量", "销售量", "产量", "出货", "发货", "价格指数", "PPI"],
        source_terms=["fina_mainbz", "cn_ppi", "ppi_yoy"],
    )
    trading_volume_false_positive = _signature_matches(
        semantics,
        column_terms=["vol", "amount"],
        path_terms=["行情", "资金流向", "交易"],
        max_matches=20,
    )
    quantity_check["trading_volume_false_positive_count"] = len(
        trading_volume_false_positive
    )
    quantity_check["trading_volume_false_positive_examples"] = (
        trading_volume_false_positive[:5]
    )
    checks = [
        _check(
            input_name="business_segment_revenue_numerator",
            status="candidate_context_present_review_required",
            conclusion=(
                "fina_mainbz / 主营业务构成 supplies bz_item and bz_sales, "
                "which are numerator and product-mix context only."
            ),
            next_action="Keep bz_sales as numerator context and review which bz_item rows are product rows before pairing with quantity.",
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
            column_terms=["bz_item", "bz_sales", "bz_cost", "bz_profit"],
            path_terms=["主营业务构成"],
            source_terms=["fina_mainbz", "bz_item", "bz_sales"],
        ),
        _check(
            input_name="product_mapping",
            status="review_policy_required",
            conclusion=(
                "bz_item mixes product, geography, channel, industry, and customer labels; "
                "it needs row-level product mapping before ASP."
            ),
            next_action="Classify bz_item rows into product/geography/channel/customer/other before any ASP formula.",
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
            column_terms=["bz_item"],
            path_terms=["主营业务构成"],
            source_terms=["fina_mainbz", "bz_item"],
        ),
        quantity_check,
        {
            "input_name": "formula_policy",
            "required_for_formula": True,
            "source_status": "review_policy_required",
            "source_candidate_present": False,
            "non_empty_profile_hit_count": 0,
            "column_hit_count": 0,
            "signature_match_count": 0,
            "path_match_count": 0,
            "tushare_source_hit_count": 0,
            "signature_matches": [],
            "path_scan": {"files_scanned": 0, "path_match_count": 0, "path_examples": []},
            "tushare_source_hits": {"source_file_exists": True, "hit_count": 0, "hits": []},
            "formula_blocker_resolved_by_current_sources": False,
            "conclusion": "ASP normalization, product mapping, and bounds require reviewed policy.",
            "next_action": "Define numerator/volume pairing, product mapping rules, and clamp bounds before any Known draft.",
        },
    ]
    return _row("L0.price.product_asp", review_row, checks)


def _row(dp_id: str, review_row: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    formula_ready = all(
        bool(check["formula_blocker_resolved_by_current_sources"])
        for check in checks
        if check["required_for_formula"]
    )
    return {
        "dp_id": dp_id,
        "score_target": review_row.get("score_target") or "fundamental_score",
        "data_status": "Unknown",
        "review_missing_before_known": review_row.get("missing_before_known") or [],
        "candidate_columns": review_row.get("candidate_columns") or [],
        "source_capability_checks": checks,
        "source_capability_check_count": len(checks),
        "source_candidate_present_count": sum(
            1 for check in checks if check["source_candidate_present"]
        ),
        "formula_blocker_resolved_count": sum(
            1 for check in checks if check["formula_blocker_resolved_by_current_sources"]
        ),
        "formula_inputs_ready_after_source_scan": formula_ready,
        "formula_probe_available": False,
        "known_draft_sufficient": False,
        "approval_ready": False,
        "review_status": "review_required",
        "safe_to_upsert_without_review": False,
        "runtime_write_allowed": False,
        "production_write_allowed": False,
        "score_mutation": "none",
    }


def build_report(
    *,
    review_packets_path: Path,
    semantics_path: Path,
    file_evidence_path: Path,
    tushare_source_path: Path,
) -> dict[str, Any]:
    started = time.time()
    review_rows = _review_rows(_load_json(review_packets_path))
    semantics = _load_json(semantics_path)
    rows = [
        _rent_row(
            review_row=review_rows.get("L0.cost.rent", {}),
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
        ),
        _asp_row(
            review_row=review_rows.get("L0.price.product_asp", {}),
            semantics=semantics,
            file_evidence_path=file_evidence_path,
            tushare_source_path=tushare_source_path,
        ),
    ]
    checks = [
        check for row in rows for check in row.get("source_capability_checks") or []
    ]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "inputs": {
            "review_packets_path": _portable_path(review_packets_path),
            "semantics_path": _portable_path(semantics_path),
            "file_evidence_path": _portable_path(file_evidence_path),
            "tushare_source_path": _portable_path(tushare_source_path),
        },
        "summary": {
            "local_formula_source_capability_row_count": len(rows),
            "source_capability_check_count": len(checks),
            "source_candidate_present_count": sum(
                1 for check in checks if check["source_candidate_present"]
            ),
            "header_available_but_sample_empty_count": sum(
                1
                for check in checks
                if check["source_status"] == "header_available_but_sample_empty"
            ),
            "candidate_context_or_proxy_count": sum(
                1
                for check in checks
                if check["source_status"]
                in {
                    "candidate_proxy_present_review_required",
                    "candidate_context_present_review_required",
                    "candidate_denominator_available_policy_required",
                }
            ),
            "review_policy_required_count": sum(
                1
                for check in checks
                if check["source_status"] == "review_policy_required"
            ),
            "external_or_text_required_count": sum(
                1 for check in checks if check["source_status"] == "external_or_text_required"
            ),
            "formula_blocker_resolved_by_current_source_count": sum(
                1 for check in checks if check["formula_blocker_resolved_by_current_sources"]
            ),
            "formula_inputs_ready_after_source_scan_count": sum(
                1 for row in rows if row["formula_inputs_ready_after_source_scan"]
            ),
            "formula_probe_available_count": 0,
            "known_draft_sufficient_count": 0,
            "approval_ready_count": 0,
            "production_write_allowed_count": 0,
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share local formula source capability",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Rows: `{summary['local_formula_source_capability_row_count']}`",
        f"- Source capability checks: `{summary['source_capability_check_count']}`",
        f"- Checks with source candidates: `{summary['source_candidate_present_count']}`",
        f"- Header available but sample-empty checks: `{summary['header_available_but_sample_empty_count']}`",
        f"- Candidate context/proxy checks: `{summary['candidate_context_or_proxy_count']}`",
        f"- Review-policy-required checks: `{summary['review_policy_required_count']}`",
        f"- External/text-required checks: `{summary['external_or_text_required_count']}`",
        f"- Formula blockers resolved by current sources: `{summary['formula_blocker_resolved_by_current_source_count']}`",
        f"- Formula inputs ready after source scan: `{summary['formula_inputs_ready_after_source_scan_count']}`",
        f"- Formula probes available: `{summary['formula_probe_available_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## Rows",
        "",
        "| dp_id | candidates | blockers resolved | formula ready | key conclusion |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        conclusions = [
            check["conclusion"]
            for check in row["source_capability_checks"]
            if check["input_name"] in {"direct_lease_payment", "quantity_or_price_index"}
        ]
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"{row['source_candidate_present_count']} | "
            f"{row['formula_blocker_resolved_count']} | "
            f"{'yes' if row['formula_inputs_ready_after_source_scan'] else 'no'} | "
            f"{' '.join(conclusions)[:220]} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Existing structured data can provide rent and ASP context, but it does not close the formula blockers.",
            "- Rent needs either non-empty direct lease payment coverage or reviewed right-of-use proxy policy plus denominator.",
            "- Product ASP needs company product quantity/shipment volume or a governed product/industry price index.",
            "- Stock/futures trading volume fields are rejected as product quantity false positives.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-packets-path", type=Path, default=DEFAULT_REVIEW_PACKETS_PATH)
    parser.add_argument("--semantics-path", type=Path, default=DEFAULT_SEMANTICS_PATH)
    parser.add_argument("--file-evidence-path", type=Path, default=DEFAULT_FILE_EVIDENCE_PATH)
    parser.add_argument("--tushare-source-path", type=Path, default=DEFAULT_TUSHARE_SOURCE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        review_packets_path=args.review_packets_path,
        semantics_path=args.semantics_path,
        file_evidence_path=args.file_evidence_path,
        tushare_source_path=args.tushare_source_path,
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
