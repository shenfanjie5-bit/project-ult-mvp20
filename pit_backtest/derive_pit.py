"""PIT-deterministic wrapper over the reused ``mvp20.derive.DeriveRunner``.

``DeriveRunner.run_all`` is pure (DB snapshot → formula → DB, no network) and
the only wall-clock use is the ``now`` epoch it stamps on derived rows + feeds
to the ``news_age`` time-decay formula. We subclass and override ``run_all`` to
inject the as-of epoch instead of ``time.time()`` so (a) all PIT rows share one
timestamp (freshness stays internally consistent) and (b) the run is
reproducible. We do NOT modify ``mvp20/derive.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mvp20.derive import DeriveRunner


class PITDeriveRunner(DeriveRunner):
    def __init__(self, hot_db_path: Path | str, asof_now: int) -> None:
        super().__init__(Path(hot_db_path))
        self._asof_now = int(asof_now)

    def run_all(self, ts_codes: list[str] | None = None) -> dict[str, Any]:
        """Identical to DeriveRunner.run_all but stamps ``now = asof_epoch``."""

        from mvp20.storage import upsert_realtime

        codes = self._list_ts_codes(ts_codes)
        all_rows: list[tuple] = []
        status_counts: dict[str, dict[str, int]] = {}
        now = self._asof_now  # <-- asof, not time.time()
        for ts_code in codes:
            rows, status_map = self._run_one(ts_code, now)
            all_rows.extend(rows)
            for dp_id, status in status_map.items():
                status_counts.setdefault(dp_id, {"Known": 0, "Inactive": 0})
                status_counts[dp_id][status] = status_counts[dp_id].get(status, 0) + 1
        n = upsert_realtime(self.db, all_rows) if all_rows else 0
        return {
            "companies_processed": len(codes),
            "rows_emitted": n,
            "dp_status_counts": status_counts,
        }
