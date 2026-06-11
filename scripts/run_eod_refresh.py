#!/usr/bin/env python3
"""Nightly EOD data refresh — keeps hot.sqlite derived layers fresh.

The UI's technicals / valuation-percentile / run-up / fomo data (and therefore
the scores themselves) come from the derive layer, which pulls price history
live from tushare and recomputes L6/L8/L10/L11. Without this job the data
silently ages (observed: 113h-stale technicals) and the 22:30 P&L snapshot
scores on stale features.

Chain (all idempotent):
  1. mvp20 derive            — full A-share universe (~2.1s/stock ≈ 65min)
  2. mvp20 compile-overlays  — re-merge overlay YAML + fresh hot rows
  3. mvp20 build-peer-context — refresh cross-sectional pools (R-3a/R-3b.2)

Cron (weekdays 17:30, AFTER tushare EOD settles, BEFORE the 22:30 P&L
snapshot so it scores fresh features):
  30 17 * * 1-5  cd <repo> && .venv/bin/python scripts/run_eod_refresh.py >> runtime/eod_refresh.cron.log 2>&1
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

log = logging.getLogger("eod_refresh")
PY = str(ROOT / ".venv" / "bin" / "python")


def _run(label: str, args: list[str], timeout_s: int) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout_s,
        )
        ok = proc.returncode == 0
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]
        log.info("%s: rc=%d %.0fs %s", label, proc.returncode,
                 time.time() - t0, " | ".join(tail))
        return {"step": label, "ok": ok, "rc": proc.returncode,
                "elapsed_s": round(time.time() - t0, 1), "tail": tail}
    except subprocess.TimeoutExpired:
        log.error("%s: TIMEOUT after %ds", label, timeout_s)
        return {"step": label, "ok": False, "rc": -1, "timeout": True,
                "elapsed_s": round(time.time() - t0, 1)}


def main() -> int:
    t0 = time.time()
    results = [
        # derive pulls per-stock history from tushare; generous timeout (2.5h)
        _run("derive", [PY, "-m", "mvp20.cli", "derive"], 9000),
        _run("compile-overlays",
             [PY, "-m", "mvp20.cli", "compile-overlays",
              "--db", "runtime/hot.sqlite"], 1800),
        _run("build-peer-context",
             [PY, "-m", "mvp20.cli", "build-peer-context"], 1800),
    ]
    out = {"steps": results, "all_ok": all(r["ok"] for r in results),
           "elapsed_s": round(time.time() - t0, 1),
           "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    raise SystemExit(main())
