"""Runtime input contract for formal audit/replay writes."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from audit_eval._boundary import assert_no_forbidden_write
from audit_eval.contracts.audit_record import AuditRecord
from audit_eval.contracts.common import JsonObject
from audit_eval.contracts.replay_record import ReplayRecord


class AuditWriteBundle(BaseModel):
    """Validated audit/replay write payload shared by writers and queries."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    manifest_cycle_id: str
    audit_records: list[AuditRecord]
    replay_records: list[ReplayRecord]
    formal_partition_tag: str = "formal"
    analytical_partition_tag: str | None = None
    submitted_at: datetime
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bundle_boundaries(self) -> Self:
        """Validate replay references and package-level forbidden write fields."""

        assert_no_forbidden_write(self.model_dump(mode="python"))
        _require_unique(
            [record.record_id for record in self.audit_records],
            field_name="AuditRecord.record_id",
        )
        _require_unique(
            [record.replay_id for record in self.replay_records],
            field_name="ReplayRecord.replay_id",
        )
        _require_unique(
            [
                f"{record.cycle_id}\0{record.object_ref}"
                for record in self.replay_records
            ],
            field_name="ReplayRecord.cycle_id/object_ref",
        )

        cycle_ids = {
            *(record.cycle_id for record in self.audit_records),
            *(record.cycle_id for record in self.replay_records),
        }
        if len(cycle_ids) != 1:
            cycle_id_text = ", ".join(sorted(cycle_ids))
            raise ValueError(
                "AuditRecord.cycle_id and ReplayRecord.cycle_id must share "
                f"one cycle_id: {cycle_id_text}"
            )

        audit_records_by_id = self.audit_records_by_id()
        for replay_record in self.replay_records:
            if replay_record.manifest_cycle_id != self.manifest_cycle_id:
                raise ValueError(
                    "ReplayRecord.manifest_cycle_id must match "
                    "AuditWriteBundle.manifest_cycle_id"
                )

            missing_record_ids = [
                record_id
                for record_id in replay_record.audit_record_ids
                if record_id not in audit_records_by_id
            ]
            if missing_record_ids:
                missing = ", ".join(missing_record_ids)
                raise ValueError(
                    "ReplayRecord.audit_record_ids reference missing "
                    f"AuditRecord.record_id values: {missing}"
                )
            mismatched_record_ids = [
                record_id
                for record_id in replay_record.audit_record_ids
                if audit_records_by_id[record_id].cycle_id != replay_record.cycle_id
            ]
            if mismatched_record_ids:
                mismatched = ", ".join(mismatched_record_ids)
                raise ValueError(
                    "ReplayRecord.audit_record_ids reference AuditRecord rows "
                    "from a different cycle_id: "
                    f"{mismatched}"
                )
        return self

    def audit_records_by_id(self) -> dict[str, AuditRecord]:
        """Return audit records keyed by record_id."""

        return {record.record_id: record for record in self.audit_records}

    def replay_records_by_object_ref(self) -> dict[str, ReplayRecord]:
        """Return replay records keyed by object_ref."""

        return {record.object_ref: record for record in self.replay_records}


def _require_unique(values: list[str], *, field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        duplicate_text = ", ".join(duplicates)
        raise ValueError(f"{field_name} values must be unique: {duplicate_text}")


__all__ = ["AuditWriteBundle"]
