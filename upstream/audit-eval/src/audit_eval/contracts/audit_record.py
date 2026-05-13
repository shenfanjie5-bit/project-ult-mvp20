"""Formal audit record runtime contract."""

import hashlib
import re
from datetime import datetime
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from audit_eval.contracts.common import JsonObject, LayerName

_SHA256_RE = re.compile(r"^(?:sha256:)?(?P<digest>[0-9a-fA-F]{64})$")


class AuditRecord(BaseModel):
    """Formal Zone audit record shape."""

    replay_field_names: ClassVar[tuple[str, ...]] = (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    )

    model_config = ConfigDict(extra="forbid")

    record_id: str
    cycle_id: str
    layer: LayerName
    object_ref: str
    params_snapshot: JsonObject
    llm_lineage: JsonObject
    llm_cost: JsonObject
    sanitized_input: str | None
    input_hash: str | None
    raw_output: str | None
    parsed_result: JsonObject | None
    output_hash: str | None
    degradation_flags: JsonObject
    created_at: datetime

    @field_validator("llm_lineage", mode="after")
    @classmethod
    def validate_llm_lineage_called_flag(cls, value: JsonObject) -> JsonObject:
        """Require an explicit typed LLM call marker."""

        if "called" not in value:
            raise ValueError("llm_lineage.called must be present")
        if not isinstance(value["called"], bool):
            raise ValueError("llm_lineage.called must be a boolean")
        return value

    @model_validator(mode="after")
    def require_replay_fields_when_llm_called(self) -> Self:
        """Formal LLM calls must carry a complete replay bundle."""

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
            _validate_replay_hash(
                field_name="input_hash",
                hash_value=self.input_hash,
                source_field="sanitized_input",
                source_value=self.sanitized_input,
                lineage=self.llm_lineage,
            )
            _validate_replay_hash(
                field_name="output_hash",
                hash_value=self.output_hash,
                source_field="raw_output",
                source_value=self.raw_output,
                lineage=self.llm_lineage,
            )
        return self


def _validate_replay_hash(
    *,
    field_name: str,
    hash_value: str | None,
    source_field: str,
    source_value: str | None,
    lineage: JsonObject,
) -> None:
    if hash_value is None or source_value is None:
        raise ValueError(f"LLM-called audit records require {field_name}")

    recorded_digest = _normalize_sha256(field_name, hash_value)
    recomputed_digest = hashlib.sha256(source_value.encode("utf-8")).hexdigest()
    if recorded_digest != recomputed_digest:
        raise ValueError(
            f"{field_name} does not match sha256({source_field})"
        )

    lineage_value = lineage.get(field_name)
    if lineage_value is None:
        return
    if not isinstance(lineage_value, str):
        raise ValueError(f"llm_lineage.{field_name} must be a sha256 string")
    lineage_digest = _normalize_sha256(f"llm_lineage.{field_name}", lineage_value)
    if lineage_digest != recorded_digest:
        raise ValueError(f"llm_lineage.{field_name} does not match {field_name}")


def _normalize_sha256(field_name: str, value: str) -> str:
    match = _SHA256_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must be a sha256 digest")
    return match.group("digest").lower()


__all__ = ["AuditRecord"]
