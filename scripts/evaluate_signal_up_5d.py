#!/usr/bin/env python3
"""Walk-forward evaluation for A-share absolute 5d upside probability."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from factor_research.model import signal_up_5d_common as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", default=None)
    ap.add_argument("--n-dates", type=int, default=12)
    ap.add_argument("--dates", default=None)
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--min-train-dates", type=int, default=C.MIN_TRAIN_DATES)
    ap.add_argument("--logistic-l2", type=float, default=C.MODEL_L2)
    args = ap.parse_args()

    payload = C.run_walk_forward(
        n_dates=args.n_dates,
        dates=args.dates,
        top_n=args.top_n,
        min_train_dates=args.min_train_dates,
        logistic_l2=args.logistic_l2,
    )
    payload = {
        "audit": "a_share_signal_up_5d_model_backtest",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    out = (
        Path(args.out)
        if args.out
        else ROOT / "docs" / "audit" / f"{args.date}_a_share_signal_up_5d_model_backtest_{args.n_dates}_dates.json"
    )
    C.write_json(out, payload)
    print(out)
    print(json.dumps(C.jsonable(payload["summary"]), ensure_ascii=False, indent=2))
    print(f"primary_model_passed={payload['primary_model_passed']}")
    return 0


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"elapsed_s={time.time() - t0:.1f}")
    raise SystemExit(rc)
