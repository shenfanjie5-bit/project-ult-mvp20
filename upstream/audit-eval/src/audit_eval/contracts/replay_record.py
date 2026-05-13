"""Formal replay record runtime contract."""

from datetime import datetime
from typing import Self

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from audit_eval.contracts.common import ReplayMode


class ReplayRecord(BaseModel):
    """Formal Zone replay record shape for read-history reconstruction."""

    model_config = ConfigDict(extra="forbid")

    replay_id: str
    cycle_id: str
    object_ref: str
    audit_record_ids: list[str]
    manifest_cycle_id: str
    formal_snapshot_refs: dict[str, str]
    graph_snapshot_ref: str | None
    dagster_run_id: str
    replay_mode: ReplayMode = "read_history"
    created_at: datetime

    @field_validator("formal_snapshot_refs", mode="before")
    @classmethod
    def validate_formal_snapshot_refs_contract(
        cls,
        value: object,
    ) -> dict[str, str]:
        """Require explicit string-to-string formal snapshot references."""

        if not isinstance(value, Mapping):
            raise ValueError("ReplayRecord.formal_snapshot_refs must be an object")
        refs: dict[str, str] = {}
        for key, ref in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    "ReplayRecord.formal_snapshot_refs keys must be non-empty strings"
                )
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(
                    "ReplayRecord.formal_snapshot_refs values must be non-empty "
                    "strings"
                )
            refs[key] = ref
        return refs

    @model_validator(mode="after")
    def require_replay_bound_fields(self) -> Self:
        """Replay records must be bound to manifest and run-history inputs."""

        if not self.audit_record_ids:
            raise ValueError("ReplayRecord.audit_record_ids must not be empty")
        if not self.manifest_cycle_id:
            raise ValueError("ReplayRecord.manifest_cycle_id must not be empty")
        if not self.formal_snapshot_refs:
            raise ValueError("ReplayRecord.formal_snapshot_refs must not be empty")
        if not self.dagster_run_id:
            raise ValueError("ReplayRecord.dagster_run_id must not be empty")
        return self


__all__ = ["ReplayRecord"]
