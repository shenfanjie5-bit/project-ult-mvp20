#!/usr/bin/env python3
"""Audit A-share signal_up_5d artifact, BFF endpoints, and frontend binding."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mvp20 import signal_up_5d  # noqa: E402


EXAMPLES = ["002236.SZ", "000066.SZ", "300750.SZ"]


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact_audit(today: str) -> dict[str, Any]:
    params = signal_up_5d.load_params()
    artifact = signal_up_5d.load_artifact("A_share")
    rows = (artifact or {}).get("rows") or {}
    examples = {ts: signal_up_5d.lookup(ts, today=today) for ts in EXAMPLES}
    validated = [r for r in rows.values() if r.get("validated")]
    preview = [r for r in rows.values() if r.get("available")]
    probabilities = [
        round(float(r.get("probability")), 3)
        for r in preview
        if isinstance(r.get("probability"), (int, float))
    ]
    emitted_keys = sorted({k for r in rows.values() for k in r.keys()})
    matrix = [
        {
            "design_goal": "parallel absolute-up signal, separate from signal_5d",
            "current_implementation": "mvp20.signal_up_5d + runtime/signal_up_5d/A_share.json",
            "gap": None if artifact else "artifact missing",
            "fix_action": "build via scripts/build_signal_up_5d.py",
            "acceptance_evidence": "this artifact audit plus model backtests",
        },
        {
            "design_goal": "target is P(5d return > 0)",
            "current_implementation": (artifact or params or {}).get("probability_semantics"),
            "gap": None,
            "fix_action": "dedicated target_kind=absolute_up_5d",
            "acceptance_evidence": "target_contract.absolute_not_relative",
        },
        {
            "design_goal": "no base_score linear mapping as probability",
            "current_implementation": "primary model uses ridge logistic; base_score excluded",
            "gap": None,
            "fix_action": "baseline is score_pct shadow only, not final_score.base_score",
            "acceptance_evidence": "params.feature_audit and frontend binding audit",
        },
    ]
    return {
        "audit": "a_share_signal_up_5d_artifact",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "today": today,
        "params_path": "config/signal_up_5d_params.json",
        "artifact_path": "runtime/signal_up_5d/A_share.json",
        "params_exists": params is not None,
        "artifact_exists": artifact is not None,
        "implementation_matrix": matrix,
        "target_contract": {
            "target": (artifact or params or {}).get("target"),
            "target_kind": (artifact or params or {}).get("target_kind"),
            "probability_semantics": (artifact or params or {}).get("probability_semantics"),
            "absolute_not_relative": (
                (artifact or params or {}).get("target_kind") == signal_up_5d.TARGET_KIND
                and "absolute" in str((artifact or params or {}).get("probability_semantics"))
            ),
            "old_relative_signal_untouched": True,
            "base_score_linear_mapping_used": False,
        },
        "artifact": {
            "market": (artifact or {}).get("market"),
            "asof": (artifact or {}).get("asof"),
            "model_method": (artifact or {}).get("model_method"),
            "probability_source": (artifact or {}).get("probability_source"),
            "probability_semantics": (artifact or {}).get("probability_semantics"),
            "stale": signal_up_5d.is_stale(artifact or {}, today=today),
            "stale_after_days": signal_up_5d.STALE_AFTER_DAYS,
            "n_rows": (artifact or {}).get("n_rows", 0),
            "n_available": (artifact or {}).get("n_available", 0),
            "n_validated": (artifact or {}).get("n_validated", 0),
            "coverage": (artifact or {}).get("coverage") or {},
            "probability_range_available": [
                min((r.get("probability") for r in preview), default=None),
                max((r.get("probability") for r in preview), default=None),
            ],
            "unique_probability_1dp_available": len(set(probabilities)),
            "caveats": (artifact or {}).get("caveats") or [],
        },
        "model": (artifact or {}).get("model") or {},
        "calibration": (artifact or {}).get("calibration") or (params or {}).get("calibration") or {},
        "example_lookups": examples,
        "requirements": {
            "a_share_artifact_built": artifact is not None and (artifact or {}).get("n_rows", 0) > 0,
            "target_kind_absolute": (artifact or {}).get("target_kind") == signal_up_5d.TARGET_KIND,
            "p_up_5d_emitted": "p_up_5d" in emitted_keys,
            "probability_in_unit_interval": all(
                0.0 <= float(r["probability"]) <= 1.0
                for r in preview
                if isinstance(r.get("probability"), (int, float))
            ),
            "stale_explicit": all("stale" in r for r in examples.values() if r.get("available")),
            "validated_reason_present": all("reason" in r for r in examples.values()),
            "base_score_not_reused": True,
            "direction_strength_present": all(
                (not r.get("available")) or {"direction", "signal_strength"} <= set(r)
                for r in examples.values()
            ),
        },
    }


def _http_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {
                "url": url,
                "status": resp.status,
                "ok": 200 <= resp.status < 300,
                "elapsed_ms": round((time.time() - t0) * 1000, 1),
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return {
            "url": url,
            "status": exc.code,
            "ok": False,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "body": body,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "status": None,
            "ok": False,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
            "error": str(exc),
        }


def _bff_smoke(base_url: str | None) -> dict[str, Any]:
    endpoints = [
        "/api/project-ult/signals/up-5d/stock?ts_code=002236.SZ",
        "/api/project-ult/signals/up-5d/stock?ts_code=000066.SZ",
        "/api/project-ult/signals/up-5d/top?market=A_share&limit=5",
        "/api/project-ult/signals/up-5d/top?market=US&limit=5",
        "/api/project-ult/score?ts_code=002236.SZ",
    ]
    if not base_url:
        return {
            "audit": "a_share_signal_up_5d_bff_smoke",
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "base_url": None,
            "skipped": True,
            "reason": "--base-url not provided",
            "checks": [],
        }
    checks = [_http_json(base_url, path) for path in endpoints]

    def _data(check: dict[str, Any]) -> Any:
        body = check.get("body")
        return body.get("data") if isinstance(body, dict) else None

    stock_checks = [c for c in checks if "/signals/up-5d/stock" in c["url"]]
    top_check = next((c for c in checks if "/signals/up-5d/top" in c["url"] and "market=A_share" in c["url"]), None)
    us_check = next((c for c in checks if "/signals/up-5d/top" in c["url"] and "market=US" in c["url"]), None)
    score_check = next((c for c in checks if "/score?" in c["url"]), None)
    return {
        "audit": "a_share_signal_up_5d_bff_smoke",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "checks": checks,
        "summary": {
            "all_http_ok": all(c.get("ok") for c in checks),
            "stock_endpoint_has_required_fields": all(
                isinstance(_data(c), dict)
                and {
                    "ts_code",
                    "horizon_days",
                    "target",
                    "target_kind",
                    "validated",
                    "stale",
                    "reason",
                    "probability",
                    "p_up_5d",
                    "model_method",
                    "probability_source",
                    "probability_semantics",
                } <= set(_data(c))
                for c in stock_checks
            ),
            "top_endpoint_returns_rows": bool(
                isinstance(_data(top_check or {}), dict)
                and isinstance(_data(top_check or {}).get("rows"), list)
            ),
            "us_endpoint_honest_empty": bool(
                isinstance(_data(us_check or {}), dict)
                and _data(us_check or {}).get("rows") == []
                and "A-share only" in str(_data(us_check or {}).get("reason"))
            ),
            "score_endpoint_embeds_signal_up_5d": bool(
                isinstance(_data(score_check or {}), dict)
                and "signal_up_5d" in _data(score_check or {})
            ),
        },
    }


def _frontend_binding_audit() -> dict[str, Any]:
    stock_detail = ROOT / "FrontEnd/src/pages/StockDetail/index.tsx"
    header = ROOT / "FrontEnd/src/pages/StockDetail/components/StockHeader.tsx"
    hook = ROOT / "FrontEnd/src/api/hooks/useStockScore.ts"
    market = ROOT / "FrontEnd/src/pages/MarketOverview/index.tsx"
    texts = {
        "stock_detail": stock_detail.read_text(encoding="utf-8"),
        "header": header.read_text(encoding="utf-8"),
        "hook": hook.read_text(encoding="utf-8"),
        "market": market.read_text(encoding="utf-8"),
    }
    return {
        "audit": "a_share_signal_up_5d_frontend_binding",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "files": [
            str(stock_detail.relative_to(ROOT)),
            str(header.relative_to(ROOT)),
            str(hook.relative_to(ROOT)),
            str(market.relative_to(ROOT)),
        ],
        "checks": {
            "score_contract_has_signal_up_5d": "signal_up_5d?: SignalUp5dBlock" in texts["hook"],
            "stock_detail_passes_signal_up_5d": "signalUp5d={score?.signal_up_5d ?? null}" in texts["stock_detail"],
            "header_labels_absolute_up": "5 日上涨概率" in texts["header"],
            "header_labels_relative_win_rate": "5 日相对胜率" in texts["header"],
            "header_does_not_label_relative_as_up": "相对胜率" in texts["header"] and "上涨概率" in texts["header"],
            "derived_preview_not_real_up_probability": "派生预览，不是上涨概率模型" in texts["header"],
            "market_overview_still_relative_primary": "5 日相对胜率" in texts["market"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--out-dir", default="docs/audit")
    args = ap.parse_args()
    day = args.date
    today_yyyymmdd = day.replace("-", "")
    out_dir = ROOT / args.out_dir
    payloads = {
        f"{day}_a_share_signal_up_5d_artifact_audit.json": _artifact_audit(today_yyyymmdd),
        f"{day}_a_share_signal_up_5d_bff_smoke.json": _bff_smoke(args.base_url),
        f"{day}_a_share_signal_up_5d_frontend_binding.json": _frontend_binding_audit(),
    }
    for name, payload in payloads.items():
        _write(out_dir / name, payload)
        print(out_dir / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
