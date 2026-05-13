#!/usr/bin/env python3
"""Plan or explicitly execute bounded holdings Raw Zone backfills."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from data_platform.holdings_backfill import (
    DEFAULT_MAX_PLAN_ITEMS,
    MVP20_BOUNDED_BACKFILL_MAX_PLAN_ITEMS,
    SUPPORTED_HOLDINGS_BACKFILL_DATASETS,
    build_holdings_backfill_plan,
    build_mvp20_bounded_backfill_manifest,
    execute_holdings_backfill_plan,
    public_execution_summary,
    public_mvp20_bounded_backfill_summary,
    public_plan_summary,
    validate_holdings_backfill_live_gate,
)
from data_platform.raw import RawWriter


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.mvp20_bounded_backfill:
            if args.execute_live:
                msg = "--mvp20-bounded-backfill is plan-only and cannot execute live"
                raise ValueError(msg)
            manifest = build_mvp20_bounded_backfill_manifest(
                stock_codes=_split_many(args.stock_code),
                end_month=args.mvp20_end_month,
                max_plan_items=_max_plan_items(
                    args.max_plan_items,
                    default=MVP20_BOUNDED_BACKFILL_MAX_PLAN_ITEMS,
                ),
            )
            payload: dict[str, Any] = {
                "mode": "mvp20_bounded_backfill",
                "execute_live": False,
                "manifest": public_mvp20_bounded_backfill_summary(manifest),
            }
            _emit_payload(payload, args.json_report)
            return 0 if manifest.ok else 2

        plan = build_holdings_backfill_plan(
            datasets=_split_many(args.dataset),
            stock_codes=_split_many(args.stock_code),
            fund_codes=_split_many(args.fund_code),
            periods=_split_many(args.period),
            trade_dates=_split_many(args.trade_date),
            start_date=args.start_date,
            end_date=args.end_date,
            market_types=_split_many(args.market_type),
            exchanges=_split_many(args.exchange),
            max_plan_items=_max_plan_items(args.max_plan_items, default=DEFAULT_MAX_PLAN_ITEMS),
        )
        payload: dict[str, Any] = {
            "mode": "holdings_backfill",
            "execute_live": args.execute_live,
            "plan": public_plan_summary(plan),
        }
        if plan.has_rejections:
            _emit_payload(payload, args.json_report)
            return 2
        if args.execute_live:
            validate_holdings_backfill_live_gate(execute_live=args.execute_live)
            if args.raw_zone_path is None or args.iceberg_warehouse_path is None:
                msg = "--execute-live requires --raw-zone-path and --iceberg-warehouse-path"
                raise ValueError(msg)
            from data_platform.adapters.tushare.adapter import TushareAdapter

            result = execute_holdings_backfill_plan(
                plan,
                adapter=TushareAdapter(),
                raw_writer=RawWriter(
                    raw_zone_path=args.raw_zone_path,
                    iceberg_warehouse_path=args.iceberg_warehouse_path,
                ),
                execute_live=args.execute_live,
            )
            payload["execution"] = public_execution_summary(result)
        _emit_payload(payload, args.json_report)
    except Exception as exc:
        mode = "mvp20_bounded_backfill" if args.mvp20_bounded_backfill else "holdings_backfill"
        payload = {
            "mode": mode,
            "execute_live": args.execute_live,
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
        _emit_payload(payload, args.json_report)
        return 2
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        action="append",
        help=(
            "Holdings dataset to backfill. Repeat or comma-separate. Supported: "
            + ", ".join(SUPPORTED_HOLDINGS_BACKFILL_DATASETS)
        ),
    )
    parser.add_argument(
        "--stock-code",
        action="append",
        help="Bounded A-share code scope. Required exactly 20 times or comma-separated for MVP20.",
    )
    parser.add_argument("--fund-code", action="append", help="Bounded fund code scope.")
    parser.add_argument("--period", action="append", help="Report period in YYYYMMDD.")
    parser.add_argument("--trade-date", action="append", help="Trade date in YYYYMMDD.")
    parser.add_argument("--start-date", help="Inclusive trade-date range start in YYYYMMDD.")
    parser.add_argument("--end-date", help="Inclusive trade-date range end in YYYYMMDD.")
    parser.add_argument("--market-type", action="append", help="Bounded hsgt_top10 market type.")
    parser.add_argument("--exchange", action="append", help="Bounded hsgt_hold_top10 exchange.")
    parser.add_argument("--max-plan-items", type=int)
    parser.add_argument(
        "--mvp20-bounded-backfill",
        action="store_true",
        help="Emit the fixed MVP20 20-stock, two-hop, 120-month plan-only manifest.",
    )
    parser.add_argument(
        "--mvp20-end-month",
        help="MVP20 window end month in YYYYMM or YYYYMMDD. Defaults to provider cutoff month.",
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Opt in to live adapter execution. Omit for plan-only dry run.",
    )
    parser.add_argument("--raw-zone-path", type=Path)
    parser.add_argument("--iceberg-warehouse-path", type=Path)
    parser.add_argument("--json-report", type=Path, help="Write JSON payload to this path.")
    args = parser.parse_args(argv)
    if not args.mvp20_bounded_backfill and not args.dataset:
        parser.error("--dataset is required unless --mvp20-bounded-backfill is set")
    return args


def _split_many(values: Sequence[str] | None) -> list[str]:
    if values is None:
        return []
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def _max_plan_items(value: int | None, *, default: int) -> int:
    return default if value is None else value


def _emit_payload(payload: dict[str, Any], path: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
