"""Typed read-history replay view returned by replay queries."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.replay_record import ReplayRecord


@dataclass(frozen=True)
class ReplayView:
    """Reconstructed historical view for one cycle/object replay."""

    cycle_id: str
    object_ref: str
    replay_record: ReplayRecord
    audit_records: tuple[AuditRecord, ...]
    manifest_snapshot_set: dict[str, str]
    historical_formal_objects: dict[str, Any]
    graph_snapshot_ref: str | None
    graph_snapshot: dict[str, Any] | None
    dagster_run_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict compatible with the spike CLI view."""

        return {
            "cycle_id": self.cycle_id,
            "object_ref": self.object_ref,
            "replay_record": self.replay_record.model_dump(mode="json"),
            "audit_records": [
                record.model_dump(mode="json") for record in self.audit_records
            ],
            "manifest_snapshot_set": deepcopy(self.manifest_snapshot_set),
            "historical_formal_objects": deepcopy(self.historical_formal_objects),
            "graph_snapshot_ref": self.graph_snapshot_ref,
            "graph_snapshot": deepcopy(self.graph_snapshot),
            "dagster_run_summary": deepcopy(self.dagster_run_summary),
        }


__all__ = ["ReplayView"]
