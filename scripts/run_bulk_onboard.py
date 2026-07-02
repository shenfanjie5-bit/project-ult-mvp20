"""Bulk-onboard batch runner — drives runtime/bulk_onboard/ledger.json.

Processes a batch of pending A-shares from the frozen manifest through the FULL
onboard pipeline (including the codex L1-L3 qualitative fill), updating the
ledger atomically after EACH stock so the run is resumable if killed. Runs
stocks sequentially (one codex process at a time) to keep token/API rate bounded
and timing clean; the spec's MAX_ACTIVE_ONBOARD_JOBS=2 concurrency is reserved
for the daemon UI path, not this batch driver.

Per stock it records: status (done/failed), attempts, reason, wall_s,
codex_warning, the parity_check() result, and the produced signal. Designed to
be launched in the background; progress is printed to stdout (captured to a log).

Usage:
    python scripts/run_bulk_onboard.py --codes 688808.SH,920186.BJ   # explicit
    python scripts/run_bulk_onboard.py --limit 15                     # next N pending
    python scripts/run_bulk_onboard.py --limit 15 --no-codex          # skip codex
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEDGER_PATH = ROOT / "runtime" / "bulk_onboard" / "ledger.json"
LOG_DIR = ROOT / "runtime" / "bulk_onboard"
DB_PATH = ROOT / "runtime" / "hot.sqlite"
MAX_ATTEMPTS = 3
# Serializes the ledger/log read-modify-write so >1 worker can't race on it.
# (run_onboard has its own _ONBOARD_PIPELINE_LOCK for universe/overlay/compile.)
_WRITE_LOCK = threading.Lock()


def _load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _save_ledger(d: dict) -> None:
    tmp = LEDGER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LEDGER_PATH)


def _select(ledger: dict, codes: list[str] | None, limit: int | None) -> list[dict]:
    ents = ledger["entries"]
    by_code = {e["ts_code"].upper(): e for e in ents}
    if codes:
        out = []
        for c in codes:
            e = by_code.get(c.upper())
            if e is None:
                print(f"WARN: {c} not in ledger; skipping")
            else:
                out.append(e)
        return out
    # next pending (or retryable failed with attempts < MAX_ATTEMPTS), biggest
    # market cap first (operator policy: prioritise large caps; ``reserved``
    # entries — the ≤200亿 placeholders — are excluded by the status filter).
    pend = [e for e in ents if e["status"] == "pending"
            or (e["status"] == "failed" and e.get("attempts", 0) < MAX_ATTEMPTS)]
    pend.sort(key=lambda e: e.get("total_mv_yi") or 0, reverse=True)
    return pend[: (limit or len(pend))]


def _onboard_one(entry: dict, *, do_codex: bool, defer_heavy: bool = True,
                 fill_engine: str = "codex") -> dict:
    """Run the full pipeline for one stock; return a result record (never raises).

    ``defer_heavy`` (default) skips the per-stock whole-corpus compile + peer-
    context rebuild — both O(corpus) per stock → O(corpus²) over the batch. They
    are run ONCE at end-of-batch (Phase 4: final compile + peer rebuild + full
    rescore), so item ②/⑥ parity is "deferred" (GAP) during the batch and
    resolved at the finalize pass. ``fill_engine`` picks the qualitative-fill
    provider (codex/OpenAI or claude/Anthropic Opus) so the batch fans out
    across both."""
    from mvp20.onboard import run_onboard
    from scripts.onboard_parity import parity_check

    ts_code, name, theme = entry["ts_code"], entry["name"], entry["theme"]
    t0 = time.time()
    rec: dict = {"ts_code": ts_code, "theme": theme, "fill_engine": fill_engine}
    try:
        res = run_onboard(DB_PATH, ts_code, name, theme, do_codex=do_codex,
                          do_compile=not defer_heavy, do_peer_context=not defer_heavy,
                          fill_engine=fill_engine)
        full = res.get("full") or {}
        prelim = res.get("preliminary") or {}
        rec["codex_warning"] = full.get("codex_warning")
        rec["compile_warning"] = (prelim or {}).get("compile_warning")
        rec["valuation_warning"] = (prelim or {}).get("valuation_warning")
        scored = full or prelim
        rec["signal"] = scored.get("signal")
        rec["score_error"] = scored.get("error")
        # trust-but-verify parity (reads DB/overlay/score directly)
        par = parity_check(ts_code, DB_PATH, theme)
        rec["parity_items"] = par["items"]
        rec["core_l567"] = par["core_l567"]
        rec["dp_total"] = par["dp_total"]
        rec["ev_filled"] = par["ev_filled"]
        rec["base_score"] = par["base_score"]
        rec["trading_signal"] = par["trading_signal"]
        rec["peer_context_member"] = par["peer_context_member"]
        # In defer_heavy mode, items ② (compiled snapshot) and ⑥ (peer_context)
        # are EXPECTED to gap — resolved by the end-of-batch finalize pass. When
        # the LLM fill is OFF (do_codex=False) item ④ (qualitative fill) is also
        # intentionally deferred. Judge per-stock success on the remaining items.
        deferred = {"2_overlay_compiled", "6_peer_context"} if defer_heavy else set()
        if not do_codex:
            deferred.add("4_codex_qual_filled")
        core_items = {k: v for k, v in par["items"].items() if k not in deferred}
        rec["parity_pass"] = par["pass"]
        rec["core_parity_pass"] = all(core_items.values())
        rec["deferred_items"] = sorted(deferred)
        # status: done if pipeline produced a score with no hard error
        if scored.get("error"):
            rec["status"] = "failed"
            rec["reason"] = f"score error: {scored.get('error')}"[:300]
        else:
            rec["status"] = "done"
            gaps = [k for k, v in core_items.items() if not v]
            rec["reason"] = None if not gaps else "onboarded; core parity gaps: " + ",".join(gaps)
    except Exception as exc:  # noqa: BLE001 — capture, mark failed, continue batch
        rec["status"] = "failed"
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:300]
        rec["traceback"] = traceback.format_exc()[-800:]
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


def _record(rec: dict) -> None:
    """Fold one stock's result into the ledger + append the log, under the write
    lock so concurrent workers don't clobber the read-modify-write."""
    ts_code = rec["ts_code"]
    with _WRITE_LOCK:
        ledger = _load_ledger()
        for e in ledger["entries"]:
            if e["ts_code"].upper() == ts_code.upper():
                e["status"] = rec["status"]
                e["reason"] = rec.get("reason")
                e["attempts"] = e.get("attempts", 0) + 1
                e["wall_s"] = rec.get("wall_s")
                e["codex_warning"] = rec.get("codex_warning")
                e["parity_pass"] = rec.get("parity_pass")
                e["parity_items"] = rec.get("parity_items")
                e["core_l567"] = rec.get("core_l567")
                e["ev_filled"] = rec.get("ev_filled")
                e["signal"] = rec.get("trading_signal")
                e["base_score"] = rec.get("base_score")
                e["fill_engine"] = rec.get("fill_engine")
                break
        if rec["status"] == "done":
            td = ledger["meta"].setdefault("phase2", {}).setdefault("trial_done", [])
            if ts_code not in td:
                td.append(ts_code)
        _save_ledger(ledger)
        with (LOG_DIR / "runlog.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None, help="comma-separated ts_codes (explicit batch)")
    ap.add_argument("--limit", type=int, default=None, help="process next N pending")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="parallel onboard workers (spec ceiling MAX_ACTIVE_ONBOARD_JOBS=2)")
    ap.add_argument("--no-codex", action="store_true")
    ap.add_argument("--no-defer", action="store_true",
                    help="run per-stock compile + peer-context (default defers both to finalize)")
    ap.add_argument("--claude-frac", type=float, default=0.0,
                    help="fraction of stocks filled by claude/Opus (rest by codex); 0.5 = "
                         "half-and-half. Spreads the LLM load across two providers.")
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None
    do_codex = not args.no_codex
    defer_heavy = not args.no_defer
    claude_frac = max(0.0, min(args.claude_frac, 1.0))
    # defer mode holds the pipeline lock only for the ~1-2s universe append, so
    # concurrency scales near-linearly until codex/claude/tushare rate limits bite.
    # Spec default is 2; the operator raised it to shorten wall-clock. Hard cap 16
    # (10-core/32GB box; fills are I/O-bound API waits, so CPU isn't the limit).
    conc = max(1, min(args.concurrency, 16))

    def engine_for(i: int) -> str:
        if claude_frac <= 0:
            return "codex"
        if claude_frac >= 1:
            return "claude"
        # even spread: claude when the running fraction crosses an integer boundary
        return "claude" if int((i + 1) * claude_frac) > int(i * claude_frac) else "codex"

    ledger = _load_ledger()
    batch = _select(ledger, codes, args.limit)
    if not batch:
        print("nothing to do (no pending/selected entries)")
        return
    n = len(batch)
    n_claude = sum(1 for i in range(n) if engine_for(i) == "claude")
    print(f"== bulk onboard: {n} stocks, codex={'ON' if do_codex else 'OFF'}, "
          f"concurrency={conc}, defer_heavy={'ON' if defer_heavy else 'OFF'}, "
          f"engines: codex={n - n_claude} claude={n_claude} ==", flush=True)

    done = failed = parity_pass = 0
    completed = 0

    def work(entry: dict, idx: int) -> dict:
        rec = _onboard_one(entry, do_codex=do_codex, defer_heavy=defer_heavy,
                           fill_engine=engine_for(idx))
        _record(rec)
        return rec

    def report(rec: dict) -> None:
        nonlocal done, failed, parity_pass, completed
        completed += 1
        if rec["status"] == "done":
            done += 1
            parity_pass += 1 if rec.get("parity_pass") else 0
        else:
            failed += 1
        print(f"[{completed}/{n}] {rec['ts_code']} ({rec.get('theme')}/{rec.get('fill_engine')}) "
              f"→ {rec['status']} | wall={rec.get('wall_s')}s | signal={rec.get('trading_signal')} "
              f"| core_dp={rec.get('core_l567')} | ev={rec.get('ev_filled')} "
              f"| parity={'PASS' if rec.get('parity_pass') else 'GAP'} "
              f"| fill_warn={'Y' if rec.get('codex_warning') else 'N'}", flush=True)
        if rec.get("reason"):
            print(f"    reason: {rec['reason']}", flush=True)

    if conc == 1:
        for i, entry in enumerate(batch):
            report(work(entry, i))
    else:
        with ThreadPoolExecutor(max_workers=conc) as ex:
            futs = {ex.submit(work, entry, i): entry for i, entry in enumerate(batch)}
            for fut in as_completed(futs):
                try:
                    report(fut.result())
                except Exception as exc:  # noqa: BLE001 — a worker crashed outside _onboard_one
                    e = futs[fut]
                    print(f"    WORKER CRASH {e['ts_code']}: {exc}", flush=True)
                    failed += 1

    print(f"\n== batch done: {done} done ({parity_pass} full-parity), {failed} failed ==", flush=True)


if __name__ == "__main__":
    main()
