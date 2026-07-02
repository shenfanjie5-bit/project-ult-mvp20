#!/usr/bin/env python3
"""Surgically relabel ``data_source`` on nodes written by the 2026-06-24
non-LLM materialization run (review findings #1/#6/#7).

That run stamped every patched node lacking a ``data_source`` with the
blanket label ``llm_derived`` even though its candidates are deterministic
parser/formula/event/runtime extractions (and 3,829 Unknown/Unavailable
cells carry value=None with nothing to attribute at all).

This script rewrites ONLY the ``data_source`` key of exactly those nodes.
Nothing else in the node (value/evidence/last_updated/...) changes.

Node selection — a node is relabeled only when ALL hold:
  1. its dp_id is one of the run's target (promoted non-LLM-first) fields;
  2. its current ``data_source`` is exactly ``llm_derived`` (the
     ``llm_derived_local*`` variants predate the run and are left alone);
  3. its ``last_updated`` equals the run's single write timestamp
     (--run-stamp), so codex-filled nodes from other campaigns are never
     touched. Only the materializer ever wrote this exact stamp.

Label choice:
  * node data_status in {Unknown, Unavailable, N/A} → ``null`` — a missing
    value has no derivation to attribute (missing_reason explains the gap);
  * otherwise → classify the dp_id's deterministic extractor via
    ``_source_from_candidate`` on a freshly recomputed candidate (the full
    audit reports stripped per-cell records, so methods are recomputed with
    the same compare-script chain the materializer used). The LLM/non-LLM
    boundary is exact by construction; for the few dp_ids with chained
    extractors the parser/formula split reflects today's chain choice.
  * unclassifiable available methods are left as-is and reported (exit 1) —
    never guess a label.

Usage:
  .venv/bin/python scripts/relabel_a_share_non_llm_data_source.py --dry-run
  .venv/bin/python scripts/relabel_a_share_non_llm_data_source.py \
      --report docs/audit/2026-07-01_a_share_data_source_relabel.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import compare_llm_vs_non_llm_extractors as cmp  # noqa: E402
from materialize_a_share_non_llm_fields import (  # noqa: E402
    _build_candidates_for_info,
    _latest_target_source,
    _load_target_fields,
    _load_yaml,
    _source_from_candidate,
    _write_yaml,
)

RUN_STAMP_DEFAULT = "2026-06-24T01:59:58+08:00"
MISSING_STATUSES = {"Unknown", "Unavailable", "N/A"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--db-path", type=Path, default=REPO_ROOT / "runtime" / "hot.sqlite")
    parser.add_argument("--run-stamp", default=RUN_STAMP_DEFAULT,
                        help="exact last_updated written by the materialization run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="max overlays (0 = all)")
    parser.add_argument("--stocks", nargs="*", default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--progress-every", type=int, default=200)
    args = parser.parse_args()

    root = args.root.resolve()
    db_path = args.db_path.resolve()
    target_fields = _load_target_fields(_latest_target_source(root))
    scope = cmp._llm_scope(root, include_cheap_extract=True)
    roles = cmp._field_roles(root)
    infos = cmp._overlay_infos(root)
    if args.stocks:
        wanted = set(args.stocks)
        infos = [info for info in infos if info.ts_code in wanted]
    if args.limit:
        infos = infos[: args.limit]

    conn = sqlite3.connect(db_path)
    peer_map = cmp._peer_stats(sqlite3.connect(db_path), infos)

    relabeled = Counter()  # "old -> new" -> count
    skipped = Counter()
    unclassified: list[dict[str, str]] = []
    overlays_written = 0

    try:
        for idx, info in enumerate(infos, start=1):
            overlay = _load_yaml(info.path)
            nodes_by_dp = {
                str(node.get("dp_id")): node
                for node in overlay.get("nodes") or []
                if isinstance(node, dict) and node.get("dp_id")
            }
            candidates = None  # computed lazily: only when an available node needs a label
            changed = False
            for dp_id in target_fields:
                node = nodes_by_dp.get(dp_id)
                if node is None:
                    continue
                if node.get("data_source") != "llm_derived":
                    skipped["data_source_not_llm_derived"] += 1
                    continue
                if str(node.get("last_updated") or "") != args.run_stamp:
                    skipped["last_updated_not_run_stamp"] += 1
                    continue
                status = str(node.get("data_status") or "")
                if status in MISSING_STATUSES:
                    label = None
                else:
                    if candidates is None:
                        candidates = _build_candidates_for_info(
                            info=info, conn=conn, db_path=db_path, scope=scope,
                            roles=roles, peer=peer_map.get(info.ts_code, {}),
                            target_fields=target_fields,
                        )
                    candidate = dict(candidates.get(dp_id) or {})
                    # Classify by the extractor method/category; the node's
                    # own (available) status drives the not-missing branch.
                    candidate["data_status"] = status
                    label = _source_from_candidate(candidate)
                    if label is None:
                        unclassified.append({
                            "ts_code": info.ts_code,
                            "dp_id": dp_id,
                            "method": str(candidate.get("method")),
                            "status": status,
                        })
                        skipped["unclassified_available_left_as_is"] += 1
                        continue
                node["data_source"] = label
                relabeled[f"llm_derived -> {label}"] += 1
                changed = True
            if changed and not args.dry_run:
                _write_yaml(info.path, overlay)
                overlays_written += 1
            if args.progress_every and idx % args.progress_every == 0:
                print(f"processed {idx}/{len(infos)} overlays", file=sys.stderr)
    finally:
        conn.close()

    summary = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_stamp": args.run_stamp,
        "dry_run": bool(args.dry_run),
        "overlays_scanned": len(infos),
        "overlays_written": overlays_written,
        "relabeled_counts": dict(relabeled),
        "relabeled_total": sum(relabeled.values()),
        "skip_counts": dict(skipped),
        "unclassified_available_count": len(unclassified),
        "unclassified_available_sample": unclassified[:50],
        "note": (
            "LLM/non-LLM boundary is exact (run-stamp + llm_derived guards); "
            "parser-vs-formula split for chained extractors reflects today's "
            "recomputed chain choice because the full-run audit stripped "
            "per-cell records."
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.report and not args.dry_run:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    # Non-zero exit when available values could not be classified, so a
    # pipeline run cannot silently leave mislabeled provenance behind.
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())
