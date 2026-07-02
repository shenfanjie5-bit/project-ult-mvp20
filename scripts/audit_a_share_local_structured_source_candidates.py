#!/usr/bin/env python3
"""Find DOCKCASE/Tushare source candidates for local-structured A-share gaps.

This audit is deliberately read-only. It scans the existing DOCKCASE CSV
semantic index for the four local-structured A-share Unknown fields and records
which Tushare-style fields can help a reviewer, which are false positives, and
why none can be converted to Known without a reviewed mapping.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.audit_a_share_local_single_dependency_policy_drafts import (
    ROOT,
    _load_json,
    _portable_path,
)
from scripts.audit_a_share_local_structured_unknown_source_options import (
    DEFAULT_JSON_OUTPUT as DEFAULT_UNKNOWN_OPTIONS_PATH,
)


DEFAULT_DOCKCASE_SEMANTICS_PATH = (
    ROOT / "docs/audit/dockcase_csv_semantics_2026-06-18.json"
)
DEFAULT_JSON_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_source_candidates_2026-06-19.json"
)
DEFAULT_MD_OUTPUT = (
    ROOT / "docs/audit/a_share_local_structured_source_candidates_2026-06-19.md"
)


FIELD_POLICIES: dict[str, dict[str, Any]] = {
    "L0.cost.rent": {
        "search_terms": [
            "lease",
            "leases",
            "rent",
            "rental",
            "use_right_asset",
            "use_right_asset_dep",
            "fa_fnc_leases",
            "使用权",
            "租赁",
            "租金",
        ],
        "review_candidate_columns": {
            "use_right_asset_dep": (
                "现金流量表里有使用权资产折旧样本，可作为租赁负担候选，但不是租金费用。"
            )
        },
        "empty_candidate_columns": {
            "fa_fnc_leases": (
                "融资租赁支付字段在当前语义样本中为空，不能直接落地。"
            )
        },
        "exclude_column_patterns": [
            "current",
            "parent",
            "release",
            "current_price",
            "current_account",
        ],
        "next_tushare_action": (
            "优先复核现金流量表 use_right_asset_dep，并补充租赁负债、租金费用或 "
            "经营租赁披露映射；若只用 use_right_asset_dep，必须定义保守 proxy 方向。"
        ),
        "llm_or_web_fallback": (
            "从年报管理层讨论、财报附注、交易所问询或公告正文抽取租赁/门店/物流/能源成本。"
        ),
    },
    "L0.demand.frequency": {
        "search_terms": [
            "freq",
            "frequency",
            "order",
            "orders",
            "transaction",
            "transactions",
            "usage",
            "repeat",
            "shipment",
            "shipments",
            "volume",
            "vol",
            "turnover",
            "订单",
            "交易",
            "使用",
            "复购",
            "销量",
            "出货",
        ],
        "review_candidate_columns": {},
        "exclude_path_patterns": [
            "行情数据",
            "资金流向",
            "特色数据",
            "指数专题",
            "ETF专题",
            "期货数据",
            "两融",
            "大宗交易",
            "港股通",
            "交易日历",
            "tushare_api_request_manifest",
        ],
        "exclude_column_patterns": [
            "vol",
            "volume_ratio",
            "turnover",
            "amount",
            "buy_",
            "sell_",
            "net_mf",
            "freq",
            "request_volume_note",
        ],
        "next_tushare_action": (
            "现有 Tushare/DOCKCASE 目录没有客户订单频次、交易笔数、复购或使用 cadence "
            "字段；不能用股票成交量、换手率或资金流替代。"
        ),
        "llm_or_web_fallback": (
            "从年报、经营数据公告、互动易/交易所问答、行业运营数据中抽取订单数、活跃客户、"
            "出货/使用频次，并与收入拆分校验。"
        ),
    },
    "L0.demand.penetration": {
        "search_terms": [
            "penetration",
            "market_share",
            "mkt_share",
            "share_pct",
            "tam",
            "installed",
            "customer",
            "customers",
            "user",
            "users",
            "holder",
            "share",
            "ratio",
            "market",
            "渗透",
            "市占",
            "占有率",
            "客户",
            "用户",
            "装机",
        ],
        "review_candidate_columns": {},
        "exclude_path_patterns": [
            "股东",
            "指数",
            "行情",
            "资金流向",
            "基金",
            "ETF",
            "IPO新股上市",
            "_workspace/_meta",
        ],
        "exclude_column_patterns": [
            "share",
            "holder",
            "ratio",
            "market",
            "percent",
            "weight",
            "total_share",
            "float_share",
            "fd_share",
            "timestamp",
        ],
        "next_tushare_action": (
            "当前目录未发现公司业务口径的 TAM、市场份额、装机基数或客户渗透率字段；"
            "不能用股本、股东、指数权重、市场行情 percent/ratio 替代。"
        ),
        "llm_or_web_fallback": (
            "补行业 TAM/市占率来源，或从招股书、年报、研究报告、协会数据、交易所问答中抽取"
            "分母和公司口径分子。"
        ),
    },
    "L0.price.product_asp": {
        "search_terms": [
            "asp",
            "avg_price",
            "price",
            "unit",
            "volume",
            "shipment",
            "shipments",
            "sales",
            "bz_sales",
            "bz_cost",
            "bz_profit",
            "bz_item",
            "amount",
            "product",
            "单价",
            "均价",
            "售价",
            "销量",
            "出货",
            "主营业务",
        ],
        "supporting_candidate_columns": {
            "bz_item": (
                "主营业务构成的产品/地区项目可帮助识别收入结构，但没有销量。"
            ),
            "bz_sales": (
                "主营业务构成的分项收入可作为 ASP 分子或 mix 证据，但缺少单位销量。"
            ),
            "bz_cost": (
                "主营业务构成的分项成本可支撑毛利结构复核，但不能单独得到 ASP。"
            ),
            "bz_profit": (
                "主营业务构成的分项利润可支撑毛利结构复核，但不能单独得到 ASP。"
            ),
        },
        "exclude_path_patterns": [
            "行情数据",
            "资金流向",
            "特色数据",
            "指数专题",
            "ETF专题",
            "期货数据",
            "大宗交易",
            "打板专题",
            "港股通",
            "股东",
            "回购",
            "债券专题",
            "公募基金",
            "_workspace/_meta",
        ],
        "exclude_column_patterns": [
            "price",
            "avg_price",
            "current_price",
            "close_price",
            "amount",
            "vol",
            "volume_ratio",
            "buy_",
            "sell_",
            "unit_nav",
            "cogs_of_sales",
            "expense_of_sales",
            "ocf_sales",
        ],
        "next_tushare_action": (
            "优先复核 fina_mainbz/主营业务构成的 bz_item、bz_sales、bz_cost、bz_profit，"
            "把它们作为产品 mix/分子证据；仍需单位销量、出货量或外部价格指数才能计算 ASP。"
        ),
        "llm_or_web_fallback": (
            "从年报分产品销量、产销存、公告、行业价格指数、交易所问答或公司披露中抽取数量/"
            "价格口径，和 bz_sales 做公式校验。"
        ),
    },
}


def _unknown_option_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id in FIELD_POLICIES:
            rows.append(row)
    return rows


def _compile_terms(terms: Iterable[str]) -> re.Pattern[str]:
    escaped = [re.escape(str(term)) for term in terms if str(term)]
    return re.compile("|".join(escaped), flags=re.IGNORECASE) if escaped else re.compile(r"$^")


def _first_profile(signature: Mapping[str, Any], column: str) -> dict[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for values in (signature.get("column_profiles") or {}).values():
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, Mapping) and value.get("column") == column:
                matches.append(value)
    if not matches:
        return {}
    return dict(
        sorted(
            matches,
            key=lambda item: int(item.get("non_empty") or 0),
            reverse=True,
        )[0]
    )


def _profile_summary(profile: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "column",
        "non_empty",
        "empty",
        "numeric_valid",
        "parse_ratio",
        "min",
        "max",
        "non_empty_ratio",
        "samples",
    ]
    return {key: profile[key] for key in keys if key in profile}


def _non_empty(profile: Mapping[str, Any]) -> int:
    try:
        return int(profile.get("non_empty") or 0)
    except (TypeError, ValueError):
        return 0


def _contains_any(value: str, patterns: Iterable[str]) -> str | None:
    lower_value = value.lower()
    for pattern in patterns:
        if str(pattern).lower() in lower_value:
            return str(pattern)
    return None


def _signature_path_text(signature: Mapping[str, Any]) -> str:
    return " ".join(str(value) for value in signature.get("examples") or [])


def _candidate_match(
    *,
    dp_id: str,
    signature: Mapping[str, Any],
    column: str,
    classification: str,
    reason: str,
    profile: Mapping[str, Any],
    exclusion_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "dp_id": dp_id,
        "classification": classification,
        "reason": reason,
        "exclusion_reason": exclusion_reason,
        "signature_rank": signature.get("signature_rank"),
        "file_count": int(signature.get("file_count") or 0),
        "sampled_rows": int(signature.get("sampled_rows") or 0),
        "column": column,
        "profile": _profile_summary(profile),
        "examples": list(signature.get("examples") or [])[:3],
    }


def _scan_dp_candidates(
    dp_id: str,
    dockcase_semantics: Mapping[str, Any],
    *,
    excluded_limit: int = 12,
) -> dict[str, Any]:
    policy = FIELD_POLICIES[dp_id]
    terms_re = _compile_terms(policy.get("search_terms") or [])
    review_columns: Mapping[str, str] = policy.get("review_candidate_columns") or {}
    supporting_columns: Mapping[str, str] = policy.get("supporting_candidate_columns") or {}
    empty_columns: Mapping[str, str] = policy.get("empty_candidate_columns") or {}

    review_candidates: list[dict[str, Any]] = []
    supporting_candidates: list[dict[str, Any]] = []
    empty_candidates: list[dict[str, Any]] = []
    excluded_matches: list[dict[str, Any]] = []
    seen_excluded: set[tuple[Any, str, str]] = set()

    for signature in dockcase_semantics.get("signatures") or []:
        if not isinstance(signature, Mapping):
            continue
        path_text = _signature_path_text(signature)
        columns = [str(column) for column in signature.get("columns") or []]
        matched_columns = [column for column in columns if terms_re.search(column)]
        if not matched_columns and terms_re.search(path_text):
            matched_columns = ["<path>"]
        for column in matched_columns:
            profile = _first_profile(signature, column)
            non_empty = _non_empty(profile)
            if column in review_columns and non_empty > 0:
                review_candidates.append(
                    _candidate_match(
                        dp_id=dp_id,
                        signature=signature,
                        column=column,
                        classification="review_candidate",
                        reason=review_columns[column],
                        profile=profile,
                    )
                )
                continue
            if column in supporting_columns and non_empty > 0:
                supporting_candidates.append(
                    _candidate_match(
                        dp_id=dp_id,
                        signature=signature,
                        column=column,
                        classification="supporting_candidate",
                        reason=supporting_columns[column],
                        profile=profile,
                    )
                )
                continue
            if column in empty_columns and non_empty == 0:
                empty_candidates.append(
                    _candidate_match(
                        dp_id=dp_id,
                        signature=signature,
                        column=column,
                        classification="empty_candidate_not_ready",
                        reason=empty_columns[column],
                        profile=profile,
                    )
                )
                continue

            matched_path = _contains_any(path_text, policy.get("exclude_path_patterns") or [])
            matched_column = _contains_any(column, policy.get("exclude_column_patterns") or [])
            if matched_path or matched_column:
                key = (signature.get("signature_rank"), column, matched_path or matched_column or "")
                if key in seen_excluded:
                    continue
                seen_excluded.add(key)
                if len(excluded_matches) < excluded_limit:
                    excluded_matches.append(
                        _candidate_match(
                            dp_id=dp_id,
                            signature=signature,
                            column=column,
                            classification="excluded_false_positive",
                            reason="字段名或路径命中关键词，但语义不是目标业务字段。",
                            exclusion_reason=(
                                f"path:{matched_path}" if matched_path else f"column:{matched_column}"
                            ),
                            profile=profile,
                        )
                    )

    candidate_count = len(review_candidates) + len(supporting_candidates)
    if review_candidates:
        candidate_status = "review_candidate_found"
    elif supporting_candidates:
        candidate_status = "supporting_candidate_found"
    else:
        candidate_status = "no_direct_catalog_source"

    return {
        "candidate_status": candidate_status,
        "direct_known_ready": False,
        "direct_known_blocker": (
            "Existing DOCKCASE/Tushare fields do not directly contain the full target business "
            "metric and formula inputs required for a production Known value."
        ),
        "review_candidate_count": len(review_candidates),
        "supporting_candidate_count": len(supporting_candidates),
        "empty_candidate_count": len(empty_candidates),
        "excluded_false_positive_count": len(seen_excluded),
        "review_candidates": review_candidates,
        "supporting_candidates": supporting_candidates,
        "empty_candidates": empty_candidates,
        "excluded_false_positive_examples": excluded_matches,
        "next_tushare_action": policy["next_tushare_action"],
        "llm_or_web_fallback": policy["llm_or_web_fallback"],
    }


def build_report(
    unknown_options_path: Path,
    dockcase_semantics_path: Path,
) -> dict[str, Any]:
    started = time.time()
    unknown_options = _load_json(unknown_options_path)
    dockcase_semantics = _load_json(dockcase_semantics_path)

    rows: list[dict[str, Any]] = []
    for option_row in _unknown_option_rows(unknown_options):
        dp_id = str(option_row.get("dp_id") or "")
        scan = _scan_dp_candidates(dp_id, dockcase_semantics)
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": option_row.get("score_target"),
                "prior_resolution_status": option_row.get("resolution_status"),
                "runtime_dependency_ready": bool(option_row.get("runtime_dependency_ready")),
                **scan,
                "production_write_allowed": False,
                "score_mutation": "none",
            }
        )

    direct_known_ready_count = sum(1 for row in rows if row["direct_known_ready"])
    review_candidate_dp_count = sum(
        1
        for row in rows
        if row["review_candidate_count"] > 0 or row["supporting_candidate_count"] > 0
    )
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["candidate_status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - started, 3),
        "unknown_options_path": _portable_path(unknown_options_path),
        "dockcase_semantics_path": _portable_path(dockcase_semantics_path),
        "dockcase_semantics_summary": {
            key: (dockcase_semantics.get("summary") or {}).get(key)
            for key in [
                "csv_files_seen",
                "signature_count",
                "sampled_signature_count",
                "sampled_files",
                "sampled_rows",
            ]
        },
        "summary": {
            "unknown_dp_count": len(rows),
            "runtime_dependency_ready_count": sum(1 for row in rows if row["runtime_dependency_ready"]),
            "direct_known_ready_count": direct_known_ready_count,
            "review_candidate_dp_count": review_candidate_dp_count,
            "review_candidate_match_count": sum(row["review_candidate_count"] for row in rows),
            "supporting_candidate_match_count": sum(row["supporting_candidate_count"] for row in rows),
            "empty_candidate_match_count": sum(row["empty_candidate_count"] for row in rows),
            "no_direct_catalog_source_count": sum(
                1 for row in rows if row["candidate_status"] == "no_direct_catalog_source"
            ),
            "excluded_false_positive_count": sum(row["excluded_false_positive_count"] for row in rows),
            "production_write_allowed_count": 0,
            "candidate_status_counts": dict(sorted(status_counts.items())),
            "score_mutation": "none; this audit is read-only and does not alter realtime_current",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    dockcase = report["dockcase_semantics_summary"]
    lines = [
        "# A-share local structured source candidates",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Unknown dp_ids checked: `{summary['unknown_dp_count']}`",
        f"- Runtime dependencies ready: `{summary['runtime_dependency_ready_count']}`",
        f"- Direct Known-ready rows: `{summary['direct_known_ready_count']}`",
        f"- Review/source candidate rows: `{summary['review_candidate_dp_count']}`",
        f"- Review candidate matches: `{summary['review_candidate_match_count']}`",
        f"- Supporting candidate matches: `{summary['supporting_candidate_match_count']}`",
        f"- Empty candidate matches: `{summary['empty_candidate_match_count']}`",
        f"- No direct catalog source rows: `{summary['no_direct_catalog_source_count']}`",
        f"- Excluded false-positive matches: `{summary['excluded_false_positive_count']}`",
        f"- Production writes allowed: `{summary['production_write_allowed_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "## DOCKCASE Scope",
        "",
        f"- CSV files seen: `{dockcase.get('csv_files_seen')}`",
        f"- Header signatures: `{dockcase.get('signature_count')}`",
        f"- Sampled signatures: `{dockcase.get('sampled_signature_count')}`",
        f"- Sampled files: `{dockcase.get('sampled_files')}`",
        f"- Sampled rows: `{dockcase.get('sampled_rows')}`",
        "",
        "## Candidate Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in summary["candidate_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| dp_id | status | direct Known | review candidates | supporting candidates | excluded false positives | next Tushare action |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['candidate_status']}` | "
            f"{'yes' if row['direct_known_ready'] else 'no'} | "
            f"{row['review_candidate_count']} | "
            f"{row['supporting_candidate_count']} | "
            f"{row['excluded_false_positive_count']} | "
            f"{row['next_tushare_action']} |"
        )

    lines.extend(["", "## Candidate Details", ""])
    for row in report["rows"]:
        lines.extend([f"### `{row['dp_id']}`", ""])
        if row["review_candidates"]:
            lines.append("- Review candidates:")
            for match in row["review_candidates"]:
                lines.append(
                    "  - "
                    f"`{match['column']}` in signature `{match['signature_rank']}` "
                    f"(`{match['file_count']}` files, sampled non-empty "
                    f"`{match['profile'].get('non_empty', 0)}`): {match['reason']}"
                )
        if row["supporting_candidates"]:
            lines.append("- Supporting candidates:")
            for match in row["supporting_candidates"]:
                lines.append(
                    "  - "
                    f"`{match['column']}` in signature `{match['signature_rank']}` "
                    f"(`{match['file_count']}` files, sampled non-empty "
                    f"`{match['profile'].get('non_empty', 0)}`): {match['reason']}"
                )
        if row["empty_candidates"]:
            lines.append("- Empty candidates:")
            for match in row["empty_candidates"]:
                lines.append(
                    "  - "
                    f"`{match['column']}` in signature `{match['signature_rank']}`: "
                    f"{match['reason']}"
                )
        if not row["review_candidates"] and not row["supporting_candidates"]:
            lines.append("- No source-ready or supporting catalog candidate was found.")
        lines.append(f"- LLM/web fallback: {row['llm_or_web_fallback']}")
        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- `L0.cost.rent` has a Tushare/DOCKCASE lease-related candidate (`use_right_asset_dep`), but it is a lease-depreciation proxy rather than rent expense.",
            "- `L0.price.product_asp` has product/region revenue and cost mix support from `主营业务构成`, but no unit volume, shipment, or governed price index in the current catalog.",
            "- `L0.demand.frequency` and `L0.demand.penetration` have no direct business-field source in the current catalog; market trading volume, turnover, stock price, share capital, holder, and index-weight fields are explicitly rejected as false positives.",
            "- All rows remain read-only review candidates or no-source rows; none can write score-affecting Known values without governed mapping or extracted evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--unknown-options-path",
        type=Path,
        default=DEFAULT_UNKNOWN_OPTIONS_PATH,
    )
    parser.add_argument(
        "--dockcase-semantics-path",
        type=Path,
        default=DEFAULT_DOCKCASE_SEMANTICS_PATH,
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.unknown_options_path, args.dockcase_semantics_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
