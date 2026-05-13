"""DataSourceAdapter protocol definition."""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from contracts.core import ContractBaseModel
from contracts.errors import ErrorCode, validation_error_message
from contracts.schemas.cycle import CycleMetadata
from contracts.schemas.ex_payloads import (
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
)


class DataSourceBatch(ContractBaseModel):
    """Collected Ex payloads for one cycle."""

    metadata: Ex0Metadata
    facts: list[Ex1CandidateFact] = Field(default_factory=list)
    signals: list[Ex2CandidateSignal] = Field(default_factory=list)
    graph_deltas: list[Ex3CandidateGraphDelta] = Field(default_factory=list)

    @model_validator(mode="after")
    def nested_payload_subsystems_must_match_metadata(self) -> Self:
        """Keep all nested Ex payloads scoped to the metadata subsystem."""

        expected_subsystem_id = self.metadata.subsystem_id
        for field_name, payloads in (
            ("facts", self.facts),
            ("signals", self.signals),
            ("graph_deltas", self.graph_deltas),
        ):
            mismatched_subsystem_ids = sorted(
                {
                    payload.subsystem_id
                    for payload in payloads
                    if payload.subsystem_id != expected_subsystem_id
                }
            )
            if mismatched_subsystem_ids:
                raise ValueError(
                    validation_error_message(
                        ErrorCode.CONTRACT_VALIDATION_ERROR,
                        f"{field_name} subsystem_id must match "
                        "metadata.subsystem_id "
                        f"{expected_subsystem_id!r}; got "
                        + ", ".join(mismatched_subsystem_ids),
                    )
                )

        return self


@runtime_checkable
class DataSourceAdapter(Protocol):
    """Shared interface for producer-side data source adapters."""

    @property
    def adapter_name(self) -> str:
        """Stable adapter implementation name."""

        ...

    @property
    def adapter_version(self) -> str:
        """Adapter implementation version."""

        ...

    def collect(self, cycle: CycleMetadata) -> DataSourceBatch:
        """Collect Ex payloads for one orchestrator cycle."""

        ...


__all__ = ["DataSourceAdapter", "DataSourceBatch"]
