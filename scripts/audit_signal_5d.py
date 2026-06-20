#!/usr/bin/env python3
"""Audit A-share signal_5d artifact, BFF endpoints, and frontend binding.

Examples:
  .venv/bin/python scripts/audit_signal_5d.py --date 2026-06-20
  .venv/bin/python scripts/audit_signal_5d.py --base-url http://127.0.0.1:8701
"""
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

from mvp20 import signal_5d  # noqa: E402


EXAMPLES = ["002236.SZ", "000066.SZ", "300750.SZ"]


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact_audit(today: str) -> dict[str, Any]:
    params = signal_5d.load_params()
    artifact = signal_5d.load_artifact("A_share")
    rows = (artifact or {}).get("rows") or {}
    examples = {
        ts: signal_5d.lookup(ts, today=today)
        for ts in EXAMPLES
    }
    validated = [r for r in rows.values() if r.get("validated")]
    emitted_keys = sorted({k for r in rows.values() for k in r.keys()})
    return {
        "audit": "a_share_signal_5d_artifact",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "today": today,
        "params_path": "config/signal_5d_params.json",
        "artifact_path": "runtime/signal_5d/A_share.json",
        "params_exists": params is not None,
        "artifact_exists": artifact is not None,
        "target_contract": {
            "target": (artifact or params or {}).get("target"),
            "target_display": (artifact or {}).get("target_display") or signal_5d.TARGET_DISPLAY,
            "absolute_p_up_emitted": any(k == "p_up" for k in emitted_keys),
            "not_absolute_p_up_reason": (
                "REPORT_PROB.md / prob_sweep evidence treats absolute P(up) as "
                "market-dominated; production emits relative P(beat median)."
            ),
        },
        "artifact": {
            "market": (artifact or {}).get("market"),
            "asof": (artifact or {}).get("asof"),
            "stale": signal_5d.is_stale(artifact or {}, today=today),
            "stale_after_days": signal_5d.STALE_AFTER_DAYS,
            "n_rows": (artifact or {}).get("n_rows", 0),
            "n_available": (artifact or {}).get("n_available", 0),
            "n_validated": (artifact or {}).get("n_validated", 0),
            "coverage": (artifact or {}).get("coverage") or {},
            "probability_range_validated": [
                min((r.get("probability") for r in validated), default=None),
                max((r.get("probability") for r in validated), default=None),
            ],
            "caveats": (artifact or {}).get("caveats") or [],
        },
        "calibration": (artifact or {}).get("calibration") or (params or {}).get("calibration") or {},
        "example_lookups": examples,
        "requirements": {
            "a_share_artifact_built": artifact is not None and (artifact or {}).get("n_rows", 0) > 0,
            "validated_reason_present": all("reason" in r for r in examples.values()),
            "stale_explicit": all("stale" in r for r in examples.values() if r.get("available")),
            "no_absolute_p_up": not any(k == "p_up" for k in emitted_keys),
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
        "/api/project-ult/signals/stock?ts_code=002236.SZ&horizon=5",
        "/api/project-ult/signals/stock?ts_code=000066.SZ&horizon=5",
        "/api/project-ult/signals/top?horizon=5&market=A_share&limit=5",
        "/api/project-ult/signals/top?horizon=5&market=US&limit=5",
        "/api/project-ult/score?ts_code=002236.SZ",
    ]
    if not base_url:
        return {
            "audit": "a_share_signal_5d_bff_smoke",
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

    stock_checks = [c for c in checks if "/signals/stock" in c["url"]]
    top_check = next((c for c in checks if "/signals/top" in c["url"] and "market=A_share" in c["url"]), None)
    us_check = next((c for c in checks if "/signals/top" in c["url"] and "market=US" in c["url"]), None)
    score_check = next((c for c in checks if "/score?" in c["url"]), None)
    return {
        "audit": "a_share_signal_5d_bff_smoke",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "checks": checks,
        "summary": {
            "all_http_ok": all(c.get("ok") for c in checks),
            "stock_endpoint_has_required_fields": all(
                isinstance(_data(c), dict)
                and {"ts_code", "horizon_days", "target", "validated", "stale", "reason"} <= set(_data(c))
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
            "score_endpoint_embeds_signal_5d": bool(
                isinstance(_data(score_check or {}), dict)
                and "signal_5d" in _data(score_check or {})
            ),
        },
    }


def _frontend_binding_audit() -> dict[str, Any]:
    page = ROOT / "FrontEnd/src/pages/MarketOverview/index.tsx"
    hook = ROOT / "FrontEnd/src/api/hooks/useSignal5d.ts"
    page_text = page.read_text(encoding="utf-8")
    hook_text = hook.read_text(encoding="utf-8") if hook.exists() else ""
    return {
        "audit": "a_share_signal_5d_frontend_binding",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "files": [str(page.relative_to(ROOT)), str(hook.relative_to(ROOT))],
        "checks": {
            "hook_exists": hook.exists(),
            "market_overview_calls_signal_endpoint": "/project-ult/signals/top" in hook_text,
            "market_overview_no_derive_stock_signal": "deriveStockSignal" not in page_text,
            "market_overview_no_score_fanout": "/project-ult/score?" not in page_text,
            "market_overview_no_upside_probability": "upside_probability" not in page_text,
            "stale_or_invalid_hides_probability": bool(
                "renderable ? `${((signal.probability" in page_text
                and ": '--'" in page_text
                and "无有效信号" in page_text
            ),
            "label_uses_relative_probability": "5 日相对胜率" in page_text,
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
        f"{day}_a_share_signal_5d_artifact_audit.json": _artifact_audit(today_yyyymmdd),
        f"{day}_a_share_signal_5d_bff_smoke.json": _bff_smoke(args.base_url),
        f"{day}_a_share_signal_5d_frontend_binding.json": _frontend_binding_audit(),
    }
    for name, payload in payloads.items():
        _write(out_dir / name, payload)
        print(out_dir / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
