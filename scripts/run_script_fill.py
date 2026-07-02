"""Batch gap-fill runner — 零 LLM 成本对全 A 股跑 ``script_fill`` 的确定性抽取,
把【当前为空】的 L3 结构化节点(产品/地区/客户)补成 Known。

来源:年报优先(realtime_current 的 L9.disclosure.annual_report.sections)+ fina_mainbz
兜底(走 DockCase 缓存,命中不下载)。``write_to_overlay`` 只补 ``data_status != Known``
的节点,绝不覆盖 codex/LLM 既有填充,且只改 overlay yaml —— 幂等可重跑。

⚠️ 跑完需要【重新 compile-overlays + rescore】才会反映进快照/打分;改 overlay 前后
按硬约束跑全套件 rc=0。本脚本只改 ``config/stock_overlays/`` 下的 yaml,不碰 DockCase、
不碰打分代码。

Usage:
    python scripts/run_script_fill.py --concurrency 4              # 全 A 股
    python scripts/run_script_fill.py --codes 600171.SH,000063.SZ  # 指定
    python scripts/run_script_fill.py --dry-run                    # 只报告,不写盘
    python scripts/run_script_fill.py --frozen-only                # 仅冻结清单 1525 新股
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UNIVERSE = ROOT / "config" / "mvp20.universe.yaml"
FROZEN = ROOT / "config" / "bulk_onboard_a_share_ths.json"
_A_SUFFIX = (".SH", ".SZ", ".BJ")


def _a_share_codes() -> list[str]:
    uni = yaml.safe_load(UNIVERSE.read_text(encoding="utf-8")) or {}
    return [c["ts_code"] for c in uni.get("constituents", [])
            if str(c.get("ts_code", "")).upper().endswith(_A_SUFFIX)]


def _frozen_codes() -> set[str]:
    if not FROZEN.exists():
        return set()
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    rows = data.get("constituents") or data.get("stocks") or data if isinstance(data, list) else \
        (data.get("constituents") or data.get("stocks") or [])
    out: set[str] = set()
    for r in rows:
        c = r.get("ts_code") if isinstance(r, dict) else r
        if c:
            out.add(str(c).upper())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--codes", default=None, help="逗号分隔的 ts_code 子集")
    ap.add_argument("--frozen-only", action="store_true",
                    help="仅跑冻结清单 1525 新股(交 universe 取)")
    ap.add_argument("--catalysts", action="store_true",
                    help="抓 dividend/forecast/stk_holdertrade 填 Track-B 节点(走 DockCase 缓存)")
    ap.add_argument("--management-change", action="store_true",
                    help="额外填 L8.gov.management_change(走【联网】stk_managers,慢;隐含开 --catalysts)")
    ap.add_argument("--dry-run", action="store_true", help="只统计,不写 overlay")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只(冒烟用)")
    args = ap.parse_args()

    # 读缓存、不写回(本轮只读 DockCase + 改 overlay)
    os.environ.setdefault("DOCKCASE_CACHE", "1")
    os.environ["DOCKCASE_WRITEBACK"] = "0"

    from scripts import script_fill as sf

    codes = ([c.strip().upper() for c in args.codes.split(",")] if args.codes
             else _a_share_codes())
    if args.frozen_only:
        fz = _frozen_codes()
        codes = [c for c in codes if c in fz]
    if args.limit:
        codes = codes[: args.limit]
    conc = max(1, min(args.concurrency, 8))

    print(f"== script-fill 批量补空: {len(codes)} 只 A 股, concurrency={conc}, "
          f"catalysts={'on' if (args.catalysts or args.management_change) else 'off'}, "
          f"mgmt_change={'on(live)' if args.management_change else 'off'}, "
          f"{'DRY-RUN' if args.dry_run else 'WRITE'} ==", flush=True)

    lock = threading.Lock()
    tot = {"done": 0, "stocks_filled": 0, "nodes": 0, "err": 0}
    by_node: Counter = Counter()
    errors: list[str] = []

    def work(ts_code: str):
        try:
            ex = sf.extract(ts_code,
                            include_catalysts=args.catalysts or args.management_change,
                            include_management_change=args.management_change)
            if args.dry_run:
                # 统计「将被补」的节点数:extract 命中且节点当前为空
                n, hit_nodes = _count_would_fill(ts_code, ex)
            else:
                n = sf.write_to_overlay(ts_code, ex)
                hit_nodes = [dp for dp in ex] if n else []
            return ts_code, n, hit_nodes, None
        except Exception as e:  # noqa: BLE001
            return ts_code, 0, [], f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=conc) as exr:
        futs = {exr.submit(work, c): c for c in codes}
        for fut in as_completed(futs):
            ts_code, n, hit_nodes, err = fut.result()
            with lock:
                tot["done"] += 1
                if err:
                    tot["err"] += 1
                    if len(errors) < 30:
                        errors.append(f"{ts_code}: {err}")
                elif n:
                    tot["stocks_filled"] += 1
                    tot["nodes"] += n
                    for dp in hit_nodes:
                        by_node[dp] += 1
                if tot["done"] % 100 == 0 or (n and tot["done"] % 25 == 0):
                    print(f"[{tot['done']}/{len(codes)}] {ts_code} +{n} | "
                          f"累计 {tot['stocks_filled']}股 {tot['nodes']}节点 "
                          f"{tot['err']}错", flush=True)

    print(f"\n== 完成: {tot['stocks_filled']}/{len(codes)} 股被补, "
          f"{tot['nodes']} 节点填充, {tot['err']} 错 ==", flush=True)
    print("按节点分布:")
    for dp, c in by_node.most_common():
        print(f"  {c:5} {dp}")
    if errors:
        print(f"\n前 {len(errors)} 个错误:")
        for e in errors:
            print(f"  {e}")
    if not args.dry_run and tot["nodes"]:
        print("\n⚠️ 下一步必须: compile-overlays → rescore → 全套件 rc=0 → 提交。")


def _count_would_fill(ts_code: str, extracted: dict) -> tuple[int, list[str]]:
    import glob as _glob
    hits = _glob.glob(str(ROOT / "config" / "stock_overlays" / "*" / f"{ts_code}.yaml"))
    if not hits:
        return 0, []
    ov = yaml.safe_load(Path(hits[0]).read_text(encoding="utf-8")) or {}
    filled: list[str] = []
    for node in ov.get("nodes") or []:
        dp = node.get("dp_id")
        if dp in extracted and node.get("data_status") != "Known":
            filled.append(dp)
    return len(filled), filled


if __name__ == "__main__":
    main()
