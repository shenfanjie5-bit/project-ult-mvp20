#!/usr/bin/env python3
"""Run a 3-stock A/B audit: non-LLM candidates vs GPT-5.5 xhigh output.

This script intentionally runs GPT only inside a copied temporary worktree.
The main repository receives only the final audit JSON/Markdown artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_llm_vs_non_llm_extractors as cmp  # noqa: E402


TODAY = dt.date.today().isoformat()
DEFAULT_STOCKS = ("300750.SZ", "600999.SH", "600754.SH")
DEFAULT_OUTPUT_JSON = ROOT / "docs" / "audit" / f"{TODAY}_a_share_3_stock_non_llm_vs_gpt55_xhigh_ab.json"
DEFAULT_OUTPUT_MD = ROOT / "docs" / "audit" / f"{TODAY}_a_share_3_stock_non_llm_vs_gpt55_xhigh_ab.md"
TARGET_FIELD_SOURCE = ROOT / "docs" / "audit" / f"{TODAY}_a_share_all_stock_llm_vs_non_llm_extractors_summary.json"
MAIN_PYTHON = ROOT / ".venv" / "bin" / "python"
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
YAML_DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)
ALLOWED_CLOSED_LOOP_EVIDENCE = {"local_dp_id", "local_overlay", "industry_inference"}


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=YAML_LOADER)
    return payload if isinstance(payload, dict) else {}


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.dump(
            dict(payload),
            Dumper=YAML_DUMPER,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_safe(value: Any) -> Any:
    return cmp._json_safe(value)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _value_diff_summary(a_value: Any, b_value: Any) -> dict[str, Any]:
    if _canonical(a_value) == _canonical(b_value):
        return {"kind": "same"}
    if isinstance(a_value, Mapping) and isinstance(b_value, Mapping):
        a_keys = set(a_value)
        b_keys = set(b_value)
        changed = [
            key
            for key in sorted(a_keys & b_keys)
            if _canonical(a_value.get(key)) != _canonical(b_value.get(key))
        ]
        return {
            "kind": "mapping",
            "added_keys": sorted(b_keys - a_keys),
            "removed_keys": sorted(a_keys - b_keys),
            "changed_keys": changed[:12],
            "changed_key_count": len(changed),
        }
    if isinstance(a_value, list) and isinstance(b_value, list):
        changed_positions = [
            idx
            for idx, (a_item, b_item) in enumerate(zip(a_value, b_value))
            if _canonical(a_item) != _canonical(b_item)
        ]
        return {
            "kind": "list",
            "a_len": len(a_value),
            "b_len": len(b_value),
            "first_changed_positions": changed_positions[:12],
            "changed_position_count": len(changed_positions),
        }
    return {
        "kind": "scalar_or_type",
        "a_type": type(a_value).__name__,
        "b_type": type(b_value).__name__,
    }


def _load_target_fields(path: Path) -> list[str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    fields = report.get("summary", {}).get("non_llm_first_fields") or []
    if len(fields) != 55:
        raise RuntimeError(f"expected 55 non-LLM-first fields from {path}, got {len(fields)}")
    return [str(field) for field in fields]


def _target_batches(root: Path, target_fields: list[str]) -> list[dict[str, Any]]:
    scope = cmp._llm_scope(root, include_cheap_extract=True)
    by_tier: dict[str, list[str]] = defaultdict(list)
    for field in target_fields:
        tier = (scope.get(field) or {}).get("model_tier")
        if not tier:
            raise RuntimeError(f"target field missing from LLM scope: {field}")
        by_tier[str(tier)].append(field)
    order = [
        ("cheap_extract", 6),
        ("analysis", 10),
        ("cheap_classify", 8),
        ("web_analysis", 4),
    ]
    batches: list[dict[str, Any]] = []
    for tier, chunk_size in order:
        fields = by_tier.get(tier, [])
        for idx in range(0, len(fields), chunk_size):
            chunk = fields[idx : idx + chunk_size]
            if not chunk:
                continue
            batches.append(
                {
                    "name": f"{tier}_{idx // chunk_size + 1}",
                    "model_tier": tier,
                    "fields": chunk,
                }
            )
    accounted = sum(len(batch["fields"]) for batch in batches)
    if accounted != len(target_fields):
        raise RuntimeError(f"target batch count mismatch: {accounted}/{len(target_fields)}")
    return batches


def _target_infos(root: Path, stocks: tuple[str, ...]) -> dict[str, cmp.OverlayInfo]:
    infos = {info.ts_code: info for info in cmp._overlay_infos(root)}
    missing = [stock for stock in stocks if stock not in infos]
    if missing:
        raise RuntimeError(f"sample stocks not found in overlays: {missing}")
    return {stock: infos[stock] for stock in stocks}


def _build_a_group(root: Path, stocks: tuple[str, ...], target_fields: list[str]) -> dict[str, Any]:
    report = cmp.build_report(
        root=root,
        db_path=root / "runtime" / "hot.sqlite",
        sample_size=20,
        include_cheap_extract=True,
    )
    rows = [
        row
        for row in report["rows"]
        if row["ts_code"] in stocks and row["dp_id"] in set(target_fields)
    ]
    if len(rows) != len(stocks) * len(target_fields):
        raise RuntimeError(f"A group row count mismatch: got {len(rows)}, expected {len(stocks) * len(target_fields)}")
    return {
        "source_report_summary": report["summary"],
        "source_sample": report["sample"],
        "rows_by_key": {(row["ts_code"], row["dp_id"]): row for row in rows},
    }


def _copy_temp_worktree(root: Path, temp_root: Path) -> None:
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.parent.mkdir(parents=True, exist_ok=True)
    excludes = [
        "--exclude=.git",
        "--exclude=.venv",
        "--exclude=node_modules",
        "--exclude=FrontEnd/node_modules",
        "--exclude=tmp",
        "--exclude=runtime/annual_reports",
        "--exclude=*.pyc",
        "--exclude=__pycache__",
    ]
    cmd = ["rsync", "-a", "--delete", *excludes, f"{root}/", f"{temp_root}/"]
    subprocess.run(cmd, check=True)
    venv = root / ".venv"
    if venv.exists() and not (temp_root / ".venv").exists():
        os.symlink(venv, temp_root / ".venv")


def _restrict_temp_governance(temp_root: Path, active_fields: set[str]) -> None:
    gov_path = temp_root / "config" / "llm_field_governance.yaml"
    gov = _load_yaml(gov_path)
    data_points = gov.get("data_points") or {}
    for dp_id, entry in data_points.items():
        if not isinstance(entry, dict):
            continue
        if dp_id in active_fields:
            if entry.get("model_tier") == "web_analysis":
                raise RuntimeError(f"target field unexpectedly web_analysis: {dp_id}")
            entry["route"] = "llm_close"
        else:
            entry["route"] = "skip"
    _write_yaml(gov_path, gov)


def _clear_target_nodes(temp_root: Path, infos: Mapping[str, cmp.OverlayInfo], target_fields: set[str]) -> None:
    for info in infos.values():
        path = temp_root / info.path.relative_to(ROOT)
        overlay = _load_yaml(path)
        nodes = overlay.get("nodes") or []
        touched = 0
        for node in nodes:
            if not isinstance(node, dict) or node.get("dp_id") not in target_fields:
                continue
            touched += 1
            node["status"] = "Unknown"
            node["data_status"] = "Unknown"
            node["value"] = None
            node["confidence"] = 0.0
            node["evidence_sources"] = []
            node["evidence_quality"] = None
            node["data_coverage"] = None
            node["missing_reason"] = "ab_validation_target"
            node["source_fingerprint_at_fill"] = None
            node["last_filled_period"] = None
            node["last_event_id"] = None
        if touched != len(target_fields):
            raise RuntimeError(f"{path} has {touched}/{len(target_fields)} target nodes")
        _write_yaml(path, overlay)


def _generate_prompt(temp_root: Path, info: cmp.OverlayInfo, prompt_dir: Path, batch_name: str) -> Path:
    out = prompt_dir / f"{info.ts_code}_{batch_name}.md"
    cmd = [
        str(MAIN_PYTHON if MAIN_PYTHON.exists() else sys.executable),
        str(temp_root / "scripts" / "codex_prompt_gen.py"),
        "--industry",
        info.industry_id,
        "--ts-code",
        info.ts_code,
        "--model-tier",
        "all",
        "--out",
        str(out),
    ]
    subprocess.run(cmd, cwd=temp_root, check=True)
    return out


def _run_gpt_xhigh(temp_root: Path, prompt_path: Path, log_path: Path) -> int:
    env = os.environ.copy()
    env["CODEX_WORKDIR"] = str(temp_root)
    env["CODEX_SERVICE_TIER"] = env.get("CODEX_SERVICE_TIER", "fast")
    cmd = [str(temp_root / "scripts" / "codex_run_prompt.sh"), str(prompt_path)]
    with log_path.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                cmd,
                cwd=temp_root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(os.environ.get("AB_GPT_TIMEOUT_SEC", "900")),
            )
        except subprocess.TimeoutExpired:
            log.write("\nERROR: GPT runner timed out.\n")
            return 124
    return proc.returncode


def _evidence_issues(node: Mapping[str, Any]) -> list[str]:
    status = node.get("data_status")
    if not cmp._available(status):
        return []
    evidence = node.get("evidence_sources") or []
    if not evidence:
        return ["missing_evidence_sources"]
    issues: list[str] = []
    for idx, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            issues.append(f"evidence_{idx}_not_mapping")
            continue
        kind = item.get("kind")
        if kind not in ALLOWED_CLOSED_LOOP_EVIDENCE:
            issues.append(f"evidence_{idx}_bad_kind:{kind}")
        if item.get("url"):
            issues.append(f"evidence_{idx}_url_not_allowed")
    return issues


def _b_node_to_result(dp_id: str, node: Mapping[str, Any]) -> dict[str, Any]:
    candidate = {
        "data_status": node.get("data_status", "Unknown"),
        "value": node.get("value"),
        "confidence": node.get("confidence"),
        "evidence_sources": node.get("evidence_sources") or [],
    }
    schema_errors = cmp._candidate_schema_errors(dp_id, candidate)
    return {
        "data_status": candidate["data_status"],
        "value": _json_safe(candidate["value"]),
        "confidence": candidate["confidence"],
        "evidence_sources": _json_safe(candidate["evidence_sources"]),
        "schema": {
            "valid": not schema_errors,
            "errors": schema_errors,
        },
        "evidence_issues": _evidence_issues(candidate),
    }


def _parse_b_group(temp_root: Path, infos: Mapping[str, cmp.OverlayInfo], target_fields: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for stock, info in infos.items():
        nodes = cmp._nodes_by_dp(temp_root / info.path.relative_to(ROOT))
        for dp_id in target_fields:
            out[(stock, dp_id)] = _b_node_to_result(dp_id, nodes.get(dp_id) or {})
    return out


def _ab_compare(a_candidate: Mapping[str, Any], b_result: Mapping[str, Any]) -> dict[str, Any]:
    if not b_result.get("schema", {}).get("valid", True):
        bucket = "schema_invalid"
    elif b_result.get("evidence_issues"):
        bucket = "evidence_conflict"
    else:
        a_status = a_candidate.get("data_status")
        b_status = b_result.get("data_status")
        a_avail = cmp._available(a_status)
        b_avail = cmp._available(b_status)
        a_value = a_candidate.get("value")
        b_value = b_result.get("value")
        exact = _canonical(a_value) == _canonical(b_value)
        a_scalar = cmp._scalar(a_value)
        b_scalar = cmp._scalar(b_value)
        scalar_delta = None
        scalar_close = False
        if a_scalar is not None and b_scalar is not None:
            scalar_delta = b_scalar - a_scalar
            scalar_close = abs(scalar_delta) <= max(0.05, 0.15 * max(abs(a_scalar), 1.0))
        if a_avail and b_avail and exact:
            bucket = "exact_match"
        elif a_avail and b_avail and scalar_close:
            bucket = "scalar_close"
        elif a_avail and b_avail and a_status == b_status:
            bucket = "status_match_value_differs"
        elif a_avail and not b_avail:
            bucket = "a_only"
        elif not a_avail and b_avail:
            bucket = "b_only"
        elif not a_avail and not b_avail:
            bucket = "both_missing"
        else:
            bucket = "status_diff"
        return {
            "bucket": bucket,
            "exact_value_match": exact,
            "a_scalar": a_scalar,
            "b_scalar": b_scalar,
            "scalar_delta": scalar_delta,
            "scalar_close": scalar_close,
            "value_diff": _value_diff_summary(a_value, b_value),
        }
    return {
        "bucket": bucket,
        "exact_value_match": False,
        "a_scalar": cmp._scalar(a_candidate.get("value")),
        "b_scalar": cmp._scalar(b_result.get("value")),
        "scalar_delta": None,
        "scalar_close": False,
        "value_diff": _value_diff_summary(a_candidate.get("value"), b_result.get("value")),
    }


def _verdict(a_row: Mapping[str, Any], b_result: Mapping[str, Any], comparison: Mapping[str, Any]) -> str:
    bucket = comparison["bucket"]
    a_candidate = a_row["candidate"]
    if bucket == "schema_invalid":
        return "B_GROUP_SCHEMA_INVALID"
    if bucket == "evidence_conflict":
        return "B_GROUP_WEAK_OR_INVALID_EVIDENCE"
    if bucket in {"exact_match", "scalar_close"}:
        return "A_RULE_ACCEPTABLE"
    if bucket == "a_only":
        return "A_RULE_ACCEPTABLE_B_MISSING"
    if bucket == "b_only":
        return "A_RULE_NEEDS_REVIEW_OR_FIX"
    if a_candidate.get("data_status") == "Proxy" and cmp._available(b_result.get("data_status")):
        return "MANUAL_REVIEW_PROXY_DIFF"
    if bucket == "status_match_value_differs":
        if a_candidate.get("quality") in {"direct_parser", "formula", "event_screen", "strict_no_llm"}:
            return "MANUAL_REVIEW_VALUE_DIFF"
        return "MANUAL_REVIEW_PROXY_DIFF"
    return "MANUAL_REVIEW"


def _build_records(
    *,
    stocks: tuple[str, ...],
    target_fields: list[str],
    a_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    b_rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for stock in stocks:
        for dp_id in target_fields:
            a_row = a_rows[(stock, dp_id)]
            b_result = b_rows[(stock, dp_id)]
            comparison = _ab_compare(a_row["candidate"], b_result)
            records.append(
                {
                    "ts_code": stock,
                    "name": a_row["name"],
                    "industry_id": a_row["industry_id"],
                    "dp_id": dp_id,
                    "model_tier": a_row["model_tier"],
                    "participates_in_score": a_row["participates_in_score"],
                    "a_non_llm": {
                        "data_status": a_row["candidate"].get("data_status"),
                        "value": a_row["candidate"].get("value"),
                        "confidence": a_row["candidate"].get("confidence"),
                        "method": a_row["candidate"].get("method"),
                        "quality": a_row["candidate"].get("quality"),
                        "category": a_row["candidate"].get("category"),
                        "evidence_sources": a_row["candidate"].get("evidence_sources") or [],
                        "reason": a_row["candidate"].get("reason"),
                    },
                    "b_gpt55_xhigh": b_result,
                    "comparison": comparison,
                    "verdict": _verdict(a_row, b_result, comparison),
                }
            )
    return records


def _summary(records: list[dict[str, Any]], main_overlay_integrity: Mapping[str, Any]) -> dict[str, Any]:
    bucket_counts = Counter(record["comparison"]["bucket"] for record in records)
    verdict_counts = Counter(record["verdict"] for record in records)
    tier_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        tier_counts[record["model_tier"]][record["comparison"]["bucket"]] += 1
    return {
        "record_count": len(records),
        "bucket_counts": dict(bucket_counts),
        "verdict_counts": dict(verdict_counts),
        "tier_bucket_counts": {tier: dict(counts) for tier, counts in sorted(tier_counts.items())},
        "a_available_count": sum(1 for r in records if cmp._available(r["a_non_llm"]["data_status"])),
        "b_available_count": sum(1 for r in records if cmp._available(r["b_gpt55_xhigh"]["data_status"])),
        "b_schema_invalid_count": sum(1 for r in records if not r["b_gpt55_xhigh"]["schema"]["valid"]),
        "b_evidence_issue_count": sum(1 for r in records if r["b_gpt55_xhigh"]["evidence_issues"]),
        "main_overlay_integrity": dict(main_overlay_integrity),
    }


def _render_md(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share 3-stock non-LLM vs GPT-5.5 xhigh A/B audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Temp worktree: `{report['temp_worktree']}`",
        f"- Target fields: `{len(report['target_fields'])}`",
        f"- Records: `{summary['record_count']}`",
        f"- A available: `{summary['a_available_count']}`",
        f"- B available: `{summary['b_available_count']}`",
        f"- B schema invalid: `{summary['b_schema_invalid_count']}`",
        f"- B evidence issues: `{summary['b_evidence_issue_count']}`",
        f"- Main overlay unchanged: `{summary['main_overlay_integrity']['all_unchanged']}`",
        "",
        "## Samples",
        "",
        "| ts_code | name | industry | batches | prompt/log directory | temp overlay |",
        "|---|---|---|---:|---|---|",
    ]
    run_by_stock: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in report["b_run"]:
        run_by_stock[item["ts_code"]].append(item)
    for sample in report["samples"]:
        stock_runs = run_by_stock.get(sample["ts_code"], [])
        meta = stock_runs[0] if stock_runs else {}
        prompt_dir = str(Path(meta.get("prompt_path", "")).parent) if meta.get("prompt_path") else ""
        lines.append(
            f"| `{sample['ts_code']}` | {sample['name']} | `{sample['industry_id']}` | "
            f"{len(stock_runs)} | `{prompt_dir}` | `{meta.get('temp_overlay_path', '')}` |"
        )
    lines.extend([
        "",
        "## Buckets",
        "",
        "| bucket | count |",
        "|---|---:|",
    ])
    for bucket, count in sorted(summary["bucket_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{bucket}` | {count} |")
    lines.extend([
        "",
        "## Verdicts",
        "",
        "| verdict | count |",
        "|---|---:|",
    ])
    for verdict, count in sorted(summary["verdict_counts"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{verdict}` | {count} |")
    lines.extend([
        "",
        "## Tier Summary",
        "",
        "| tier | buckets |",
        "|---|---|",
    ])
    for tier, buckets in summary["tier_bucket_counts"].items():
        lines.append(f"| `{tier}` | `{json.dumps(buckets, ensure_ascii=False, sort_keys=True)}` |")

    conflicts = [
        r
        for r in report["records"]
        if r["comparison"]["bucket"] not in {"exact_match", "scalar_close"}
        or r["verdict"] not in {"A_RULE_ACCEPTABLE", "A_RULE_ACCEPTABLE_B_MISSING"}
    ]
    lines.extend([
        "",
        "## Conflict / Review Queue",
        "",
        "| ts_code | dp_id | tier | bucket | verdict | A method | A status | B status | diff |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for record in conflicts:
        diff = record["comparison"]["value_diff"]
        diff_text = json.dumps(diff, ensure_ascii=False, sort_keys=True)
        if len(diff_text) > 180:
            diff_text = diff_text[:177] + "..."
        lines.append(
            f"| `{record['ts_code']}` | `{record['dp_id']}` | `{record['model_tier']}` | "
            f"`{record['comparison']['bucket']}` | `{record['verdict']}` | "
            f"`{record['a_non_llm']['method']}` | `{record['a_non_llm']['data_status']}` | "
            f"`{record['b_gpt55_xhigh']['data_status']}` | `{diff_text}` |"
        )

    lines.extend([
        "",
        "## Full A/B Table",
        "",
        "| ts_code | dp_id | tier | score | bucket | verdict | A method | A status | B status |",
        "|---|---|---|---:|---|---|---|---|---|",
    ])
    for record in report["records"]:
        lines.append(
            f"| `{record['ts_code']}` | `{record['dp_id']}` | `{record['model_tier']}` | "
            f"`{record['participates_in_score']}` | `{record['comparison']['bucket']}` | "
            f"`{record['verdict']}` | `{record['a_non_llm']['method']}` | "
            f"`{record['a_non_llm']['data_status']}` | `{record['b_gpt55_xhigh']['data_status']}` |"
        )
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    stocks = tuple(args.stocks)
    target_fields = _load_target_fields(args.target_field_source.resolve())
    batches = _target_batches(root, target_fields)
    infos = _target_infos(root, stocks)
    main_hash_before = {
        stock: _sha256_file(info.path)
        for stock, info in infos.items()
    }
    a_group = _build_a_group(root, stocks, target_fields)

    temp_root = args.temp_root.resolve() if args.temp_root else Path("/tmp") / f"project_ult_ab_gpt55_{int(time.time())}"
    _copy_temp_worktree(root, temp_root)
    _clear_target_nodes(temp_root, infos, set(target_fields))

    prompt_dir = temp_root / "tmp_ab_prompts"
    log_dir = temp_root / "tmp_ab_logs"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    b_run: list[dict[str, Any]] = []
    for stock in stocks:
        info = infos[stock]
        for batch in batches:
            batch_fields = set(batch["fields"])
            _restrict_temp_governance(temp_root, batch_fields)
            prompt_path = _generate_prompt(temp_root, info, prompt_dir, str(batch["name"]))
            prompt_text = prompt_path.read_text(encoding="utf-8")
            if "没有可填字段" in prompt_text or "已全部填完" in prompt_text:
                raise RuntimeError(f"prompt unexpectedly has no fillable fields: {prompt_path}")
            log_path = log_dir / f"{stock}_{batch['name']}.log"
            rc = 0 if args.skip_gpt else _run_gpt_xhigh(temp_root, prompt_path, log_path)
            if rc != 0:
                raise RuntimeError(f"GPT runner failed for {stock} batch={batch['name']}, rc={rc}, log={log_path}")
            b_run.append(
                {
                    "ts_code": stock,
                    "batch": batch["name"],
                    "model_tier": batch["model_tier"],
                    "fields": list(batch["fields"]),
                    "prompt_path": str(prompt_path),
                    "log_path": str(log_path),
                    "returncode": rc,
                    "temp_overlay_path": str(temp_root / info.path.relative_to(root)),
                }
            )

    b_group = _parse_b_group(temp_root, infos, target_fields)
    records = _build_records(
        stocks=stocks,
        target_fields=target_fields,
        a_rows=a_group["rows_by_key"],
        b_rows=b_group,
    )

    main_hash_after = {
        stock: _sha256_file(info.path)
        for stock, info in infos.items()
    }
    integrity = {
        "before": main_hash_before,
        "after": main_hash_after,
        "changed": [stock for stock in stocks if main_hash_before[stock] != main_hash_after[stock]],
    }
    integrity["all_unchanged"] = not integrity["changed"]

    samples = [
        {
            "ts_code": stock,
            "name": infos[stock].name,
            "industry_id": infos[stock].industry_id,
            "overlay_path": str(infos[stock].path.relative_to(root)),
        }
        for stock in stocks
    ]
    report = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "root": str(root),
            "stocks": list(stocks),
            "target_field_source": str(args.target_field_source),
            "model": "gpt-5.5",
            "reasoning_effort": "xhigh",
            "skip_gpt": bool(args.skip_gpt),
        },
        "temp_worktree": str(temp_root),
        "samples": samples,
        "target_fields": target_fields,
        "target_batches": _json_safe(batches),
        "a_source_summary": a_group["source_report_summary"],
        "b_run": b_run,
        "records": _json_safe(records),
    }
    report["summary"] = _summary(report["records"], integrity)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target-field-source", type=Path, default=TARGET_FIELD_SOURCE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--skip-gpt", action="store_true", help="Prepare temp worktree and parse without invoking codex; for debugging only.")
    parser.add_argument("stocks", nargs="*", default=list(DEFAULT_STOCKS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.write_text(_render_md(report), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
