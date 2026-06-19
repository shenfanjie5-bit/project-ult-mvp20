#!/usr/bin/env python3
"""Audit whether selected A-share score-target fields affect final score.

This audit is intentionally tiny and deterministic: it injects one synthetic
runtime node into ``score_company`` and compares the final-score outputs against
a fixed baseline. Fields whose base/short/medium/long/market-adapter deltas are
all zero are display or dormant sinks in the current local MVP and should not be
counted as current-MVP final-score denominator closure.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from mvp20.scoring import score_company  # noqa: E402
from scripts.audit_a_share_unknown_acquisition_backlog import ROOT, _portable_path  # noqa: E402


AUDIT_DIR = ROOT / "docs/audit"
DEFAULT_CONVERSION_PATH = AUDIT_DIR / "a_share_spec_score_conversion_path_2026-06-20.json"
DEFAULT_CONFIG_PATH = ROOT / "config/a_share_current_mvp_score_applicability.yaml"
DEFAULT_JSON_OUTPUT = AUDIT_DIR / "a_share_score_sink_effect_2026-06-20.json"
DEFAULT_MD_OUTPUT = AUDIT_DIR / "a_share_score_sink_effect_2026-06-20.md"
SCORE_METRICS = (
    "base_score",
    "short_total",
    "medium_total",
    "long_total",
    "market_adapter_multiplier",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _policy_dp_ids(config: Mapping[str, Any]) -> set[str]:
    policies = config.get("exclusion_policies") or {}
    policy = policies.get("score_sink_no_effect_verified") if isinstance(policies, Mapping) else {}
    applies = policy.get("applies_when") if isinstance(policy, Mapping) else {}
    values = applies.get("dp_id_in") if isinstance(applies, Mapping) else []
    return {str(value) for value in values or [] if str(value)}


def _conversion_rows_by_dp(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        dp_id = str(row.get("dp_id") or "")
        if dp_id:
            rows[dp_id] = row
    return rows


def _snapshot(score_target: str | None = None) -> dict[str, float]:
    nodes: dict[str, Mapping[str, Any]] = {
        "baseline:rt": {
            "node_id": "baseline:rt",
            "synthetic_realtime": True,
            "field_role": "score_component",
            "score_target": "fundamental_score",
            "participates_in_score": True,
            "score_enabled": True,
            "score": 0.3,
            "confidence": 1.0,
        }
    }
    if score_target:
        nodes["probe:rt"] = {
            "node_id": "probe:rt",
            "synthetic_realtime": True,
            "field_role": "score_component",
            "score_target": score_target,
            "participates_in_score": True,
            "score_enabled": True,
            "score": 0.5,
            "confidence": 0.5,
            "data_coverage": 0.5,
        }
    result = score_company({"ts_code": "000001.SZ", "market_code": "CN_A", "nodes": []}, nodes)
    final = result.get("final_score") or {}
    components = final.get("components") if isinstance(final.get("components"), Mapping) else {}
    return {
        "base_score": float(final.get("base_score") or 0.0),
        "short_total": float(final.get("short_total") or 0.0),
        "medium_total": float(final.get("medium_total") or 0.0),
        "long_total": float(final.get("long_total") or 0.0),
        "market_adapter_multiplier": float(components.get("market_adapter_multiplier") or 0.0),
    }


def build_report(*, conversion_path: Path, config_path: Path) -> dict[str, Any]:
    conversion = _load_json(conversion_path)
    config = _load_yaml(config_path)
    rows_by_dp = _conversion_rows_by_dp(conversion)
    baseline = _snapshot()
    rows: list[dict[str, Any]] = []
    for dp_id in sorted(_policy_dp_ids(config)):
        conversion_row = rows_by_dp.get(dp_id, {})
        score_target = str(conversion_row.get("score_target") or "")
        probe = _snapshot(score_target)
        deltas = {
            metric: round(probe[metric] - baseline[metric], 12)
            for metric in SCORE_METRICS
        }
        max_abs_delta = max(abs(value) for value in deltas.values())
        rows.append(
            {
                "dp_id": dp_id,
                "score_target": score_target,
                "current_final_score_numeric": bool(
                    conversion_row.get("current_final_score_numeric")
                ),
                "tested_metrics": list(SCORE_METRICS),
                "baseline": {key: round(value, 12) for key, value in baseline.items()},
                "probe": {key: round(value, 12) for key, value in probe.items()},
                "deltas": deltas,
                "max_abs_delta": max_abs_delta,
                "no_final_score_delta": max_abs_delta == 0.0,
            }
        )
    no_delta = [row for row in rows if row["no_final_score_delta"]]
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": {
            "conversion_path": _portable_path(conversion_path),
            "config_path": _portable_path(config_path),
        },
        "summary": {
            "candidate_count": len(rows),
            "no_final_score_delta_count": len(no_delta),
            "effectful_count": len(rows) - len(no_delta),
            "tested_metrics": list(SCORE_METRICS),
            "score_mutation": "none; deterministic score_company probes only",
        },
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# A-share score sink effect audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Candidates: `{summary['candidate_count']}`",
        f"- No final-score delta: `{summary['no_final_score_delta_count']}`",
        f"- Effectful: `{summary['effectful_count']}`",
        f"- Score mutation: `{summary['score_mutation']}`",
        "",
        "| dp_id | score_target | max_abs_delta | no_final_score_delta |",
        "|---|---|---:|---|",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            f"`{row['dp_id']}` | "
            f"`{row['score_target']}` | "
            f"{row['max_abs_delta']} | "
            f"`{row['no_final_score_delta']}` |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-path", type=Path, default=DEFAULT_CONVERSION_PATH)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(conversion_path=args.conversion_path, config_path=args.config_path)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.md_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
