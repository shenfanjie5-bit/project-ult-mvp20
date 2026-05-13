from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from reasoner_runtime._contracts import ensure_contracts_importable

ensure_contracts_importable()

from contracts.schemas.reasoner import ReasonerReplay as ContractReasonerReplay
from pydantic import ConfigDict, Field, model_validator

from reasoner_runtime.core.models import (
    _RUNTIME_CONTRACT_VERSION,
)


class ReplayBundle(ContractReasonerReplay):
    replay_field_names: ClassVar[tuple[str, ...]] = (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    )

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        validate_assignment=True,
    )

    sanitized_input: str
    input_hash: str
    raw_output: str
    parsed_result: dict[str, Any]
    output_hash: str
    llm_lineage: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_contract_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        recorded_at = values.get("recorded_at", datetime.now(UTC))

        values.setdefault("replay_id", f"replay-{values.get('input_hash', 'runtime')}")
        values.setdefault("recorded_at", recorded_at)
        values.setdefault("replay_version", _RUNTIME_CONTRACT_VERSION)
        return values

    @model_validator(mode="after")
    def validate_contract_identity(self) -> ReplayBundle:
        if self.request.request_id != self.result.request_id:
            raise ValueError("replay request/result request_id values must match")
        return self

    def to_contract(self) -> ContractReasonerReplay:
        return self
