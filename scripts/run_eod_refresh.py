#!/usr/bin/env python3
"""Nightly EOD data refresh — keeps hot.sqlite derived layers fresh.

The UI's technicals / valuation-percentile / run-up / fomo data (and therefore
the scores themselves) come from the derive layer, which pulls price history
live from tushare and recomputes L6/L8/L10/L11. Without this job the data
silently ages (observed: 113h-stale technicals) and the 22:30 P&L snapshot
scores on stale features.

Chain (all idempotent):
  1. collector tushare       — full A-share financial/event refresh
  2. collector tushare-core  — latest daily_basic / moneyflow cross-section
  3. collector tushare-macro — market/macro sentinels
  4. mvp20 derive            — Tier-0 historical derives
  5. mvp20 derive-snapshot   — Tier-1..4 snapshot derives, incl. L11 signals
  6. mvp20 compile-overlays  — re-merge overlay YAML + fresh hot rows
  7. mvp20 build-peer-context — refresh cross-sectional pools (R-3a/R-3b.2)
  8. quant/signal builders   — refresh homepage and stock-detail artifacts

Cron (weekdays 17:30, AFTER tushare EOD settles, BEFORE the 22:30 P&L
snapshot so it scores fresh features):
  30 17 * * 1-5  cd <repo> && .venv/bin/python scripts/run_eod_refresh.py >> runtime/eod_refresh.cron.log 2>&1
"""
from __future__ import annotations

import json
import logging
import os
import selectors
import signal
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
    tail: list[str] = []
    proc: subprocess.Popen[str] | None = None
    try:
        log.info("%s: start %s", label, " ".join(args))
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            for key, _ in selector.select(timeout=1.0):
                line = key.fileobj.readline()
                if line:
                    msg = line.rstrip()
                    print(msg, flush=True)
                    tail.append(msg)
                    tail = tail[-5:]
            if proc.poll() is not None:
                for rest in proc.stdout:
                    msg = rest.rstrip()
                    print(msg, flush=True)
                    tail.append(msg)
                    tail = tail[-5:]
                break
            if time.time() - t0 > timeout_s:
                raise subprocess.TimeoutExpired(args, timeout_s)
        ok = proc.returncode == 0
        log.info("%s: rc=%d %.0fs %s", label, proc.returncode,
                 time.time() - t0, " | ".join(tail))
        return {"step": label, "ok": ok, "rc": proc.returncode,
                "elapsed_s": round(time.time() - t0, 1), "tail": tail}
    except subprocess.TimeoutExpired:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        log.error("%s: TIMEOUT after %ds", label, timeout_s)
        return {"step": label, "ok": False, "rc": -1, "timeout": True,
                "elapsed_s": round(time.time() - t0, 1), "tail": tail}


def _run_derive_inprocess() -> dict:
    """derive in-process with a GLOBAL socket timeout.

    The tushare client issues HTTP reads with NO timeout; one wedged
    connection hangs the whole nightly chain forever (observed: 93% of
    samples blocked in sock_recv). With the default timeout set, a hung call
    raises inside the per-stock fetch helper (which already catches and
    returns {}), so the loop skips that stock and continues.
    """

    import socket

    t0 = time.time()
    socket.setdefaulttimeout(60)
    try:
        from mvp20.sources import load_dotenv
        load_dotenv()
        from mvp20.derive import derive_all
        stats = derive_all(Path("runtime/hot.sqlite"))
        log.info("derive: %.0fs %s", time.time() - t0, stats)
        return {"step": "derive", "ok": True, "rc": 0,
                "elapsed_s": round(time.time() - t0, 1), "stats": stats}
    except Exception as exc:  # noqa: BLE001
        log.error("derive failed: %s", exc)
        return {"step": "derive", "ok": False, "rc": 1,
                "elapsed_s": round(time.time() - t0, 1), "error": str(exc)}


def main() -> int:
    t0 = time.time()
    results = [
        # step 0: FULL tushare collect (financials/forecast/express/etc. —
        # the slow per-stock fetch_batch the minute-level launchd collector
        # intentionally skips). One cycle then exit. Generous 3h budget.
        _run("collect-full",
             [PY, "scripts/collector.py", "--source", "tushare",
              "--max-cycles", "1"], 10800),
        # The full collector may be slow or partially fail on long per-stock
        # endpoints. Re-run the fast cross-sectional market rows so EOD derives
        # and signal artifacts always see the latest daily_basic / moneyflow.
        _run("collect-core",
             [PY, "scripts/collector.py", "--source", "tushare-core",
              "--max-cycles", "1"], 900),
        _run("collect-macro",
             [PY, "scripts/collector.py", "--source", "tushare-macro",
              "--max-cycles", "1"], 900),
        _run_derive_inprocess(),
        _run("derive-snapshot",
             [PY, "-m", "mvp20.cli", "derive-snapshot",
              "--db", "runtime/hot.sqlite", "--no-show-stats"], 1800),
        _run("compile-overlays",
             [PY, "-m", "mvp20.cli", "compile-overlays",
              "--db", "runtime/hot.sqlite"], 1800),
        _run("build-peer-context",
             [PY, "-m", "mvp20.cli", "build-peer-context"], 1800),
        _run("build-quant-scores",
             [PY, "scripts/build_quant_scores.py"], 1800),
        _run("build-signal-5d",
             [PY, "scripts/build_signal_5d.py"], 1800),
        _run("build-signal-up-5d",
             [PY, "scripts/build_signal_up_5d.py"], 1800),
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
