"""Draft replay contracts for offline replay spikes."""

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ReplayBundleFields(BaseModel):
    """Historical LLM replay fields captured at original execution time."""

    model_config = ConfigDict(extra="forbid")

    sanitized_input: str | None
    input_hash: str | None
    raw_output: str | None
    parsed_result: dict[str, Any] | None
    output_hash: str | None


class AuditRecordDraft(ReplayBundleFields):
    """Draft formal audit record shape used by the replay spike."""

    replay_field_names: ClassVar[tuple[str, ...]] = (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    )

    record_id: str
    cycle_id: str
    layer: Literal["L3", "L4", "L5", "L6", "L7", "L8"]
    object_ref: str
    params_snapshot: dict[str, Any]
    llm_lineage: dict[str, Any]
    llm_cost: dict[str, Any]
    degradation_flags: dict[str, Any]
    created_at: datetime

    @model_validator(mode="after")
    def require_replay_fields_when_llm_called(self) -> "AuditRecordDraft":
        """C5: formal LLM calls must carry a complete replay bundle."""

        if self.llm_lineage.get("called") is True:
            missing_fields = [
                field_name
                for field_name in self.replay_field_names
                if getattr(self, field_name) is None
            ]
            if missing_fields:
                fields = ", ".join(missing_fields)
                raise ValueError(
                    "LLM-called audit records require replay fields: "
                    f"{fields}"
                )
        return self


class ReplayRecordDraft(BaseModel):
    """Draft replay record shape for read-history reconstruction."""

    model_config = ConfigDict(extra="forbid")

    replay_id: str
    cycle_id: str
    object_ref: str
    audit_record_ids: list[str]
    manifest_cycle_id: str
    formal_snapshot_refs: dict[str, str]
    graph_snapshot_ref: str | None
    dagster_run_id: str
    replay_mode: Literal["read_history"]
    created_at: datetime


class ReplayViewDraft(BaseModel):
    """Draft read-history replay view returned by the offline spike."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: str
    object_ref: str
    replay_record: ReplayRecordDraft
    audit_records: list[AuditRecordDraft]
    manifest_snapshot_set: dict[str, str]
    historical_formal_objects: dict[str, dict[str, Any]]
    graph_snapshot_ref: str | None
    graph_snapshot_summary: dict[str, Any] | None
    dagster_run_summary: dict[str, Any]


__all__ = [
    "AuditRecordDraft",
    "ReplayBundleFields",
    "ReplayRecordDraft",
    "ReplayViewDraft",
]
