"""Per-base-date PIT pipeline: collect → derive → peer_context → score.

Each base date gets its OWN directory ``runtime/backtest/<asof>/`` holding
``pit.sqlite`` + ``peer_context_A.json``. Per-date isolation (a) sidesteps the
``ts_code``-keyed module caches in the production fetchers/peer_context, and
(b) makes ``default_artifact_path`` resolve to a per-date peer-context artifact
for free. Nothing here touches the live ``runtime/hot.sqlite``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping, Sequence

from mvp20 import peer_context as pc
from pit_backtest import collector, score
from pit_backtest.derive_pit import PITDeriveRunner

log = logging.getLogger("pit_backtest.pipeline")

_ROOT = Path("runtime/backtest")


def asof_db_path(asof: str, root: Path | str = _ROOT) -> Path:
    return Path(root) / asof / "pit.sqlite"


def build_pit_for_asof(asof: str, codes: Sequence[str],
                       industry_of: Mapping[str, str | None], *,
                       root: Path | str = _ROOT, resume: bool = True,
                       pro=None, progress=None) -> tuple[Path, dict]:
    """Collect + derive + build peer_context for one base date. Returns
    (db_path, collect_stats)."""

    db_path = asof_db_path(asof, root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    stats = collector.collect_universe_asof(
        asof, codes, db_path, industry_of, pro=pro, resume=resume, progress=progress
    )
    log.info("collect %s: %s", asof, stats)

    # snapshot-derive (ev_ebitda/forward_pe/peg/peg_match/sens/path/priced_in/...)
    drv = PITDeriveRunner(db_path, collector.asof_epoch(asof)).run_all(list(codes))
    log.info("derive %s: rows=%s", asof, drv.get("rows_emitted"))

    # cross-sectional peer context (per-date artifact beside the DB)
    pc.build_and_save_peer_context(db_path, list(codes), "A")
    return db_path, stats


def score_universe_asof(asof: str, codes: Sequence[str], db_path: Path,
                        *, freeze_l0: bool = True) -> list[dict]:
    """Score every code against the PIT DB for one base date. Skips codes with
    no overlay (logged)."""

    rows: list[dict] = []
    for ts in codes:
        try:
            result = score.score_one(ts, db_path, freeze_l0=freeze_l0)
        except Exception as e:  # noqa: BLE001
            log.warning("score %s @ %s failed: %s", ts, asof, str(e)[:160])
            continue
        if result is None:
            log.warning("no overlay for %s — skipped", ts)
            continue
        rows.append(score.extract_row(result, ts, asof))
    return rows
