from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import get_type_hints

import pydantic
import pytest

from tests.conftest import import_contract_module


def valid_cycle_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle-20260415-001",
        "phase": "collecting",
        "started_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    }


def valid_metadata_payload() -> dict[str, object]:
    return {
        "subsystem_id": "subsystem-news",
        "version": "0.1.0",
        "heartbeat_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "status": "ok",
        "last_output_at": datetime(2026, 4, 15, 11, 55, tzinfo=timezone.utc),
        "pending_count": 0,
    }


def valid_fact_payload() -> dict[str, object]:
    return {
        "fact_id": "fact-1",
        "entity_id": "AAPL",
        "fact_type": "earnings",
        "fact_content": {"headline": "sample"},
        "confidence": 0.8,
        "source_reference": {"source": "fixture"},
        "extracted_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        "subsystem_id": "subsystem-news",
    }


def valid_signal_payload() -> dict[str, object]:
    return {
        "signal_id": "signal-1",
        "signal_type": "earnings_surprise",
        "direction": "bullish",
        "magnitude": 0.7,
        "affected_entities": ["AAPL"],
        "affected_sectors": ["technology"],
        "time_horizon": "short",
        "evidence": ["fact-1"],
        "confidence": 0.8,
        "subsystem_id": "subsystem-news",
    }


def valid_graph_delta_payload() -> dict[str, object]:
    return {
        "delta_id": "delta-1",
        "delta_type": "upsert_edge",
        "source_node": "AAPL",
        "target_node": "technology",
        "relation_type": "belongs_to_sector",
        "properties": {"weight": 1.0},
        "evidence": ["fact-1"],
        "subsystem_id": "subsystem-news",
    }


def test_data_source_adapter_public_api_imports() -> None:
    protocols = import_contract_module("contracts.protocols")

    from contracts.protocols import DataSourceAdapter, DataSourceBatch

    assert DataSourceAdapter is protocols.DataSourceAdapter
    assert DataSourceBatch is protocols.DataSourceBatch
    assert "DataSourceAdapter" in protocols.__all__
    assert "DataSourceBatch" in protocols.__all__


def test_data_source_adapter_collect_type_hints_resolve() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    hints = get_type_hints(protocols.DataSourceAdapter.collect)

    assert hints["cycle"] is schemas.CycleMetadata
    assert hints["return"] is protocols.DataSourceBatch


def test_fake_data_source_adapter_satisfies_runtime_protocol() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    class FakeDataSourceAdapter:
        @property
        def adapter_name(self) -> str:
            return "fixture"

        @property
        def adapter_version(self) -> str:
            return "0.1.0"

        def collect(self, cycle: schemas.CycleMetadata) -> protocols.DataSourceBatch:
            del cycle
            return protocols.DataSourceBatch(
                metadata=schemas.Ex0Metadata.model_validate(valid_metadata_payload()),
                facts=[
                    schemas.Ex1CandidateFact.model_validate(valid_fact_payload()),
                ],
                signals=[
                    schemas.Ex2CandidateSignal.model_validate(valid_signal_payload()),
                ],
                graph_deltas=[
                    schemas.Ex3CandidateGraphDelta.model_validate(
                        valid_graph_delta_payload()
                    ),
                ],
            )

    fake = FakeDataSourceAdapter()
    cycle = schemas.CycleMetadata.model_validate(valid_cycle_payload())
    result = fake.collect(cycle)

    assert isinstance(fake, protocols.DataSourceAdapter)
    assert result.metadata.subsystem_id == "subsystem-news"
    assert result.facts[0].fact_id == "fact-1"
    assert result.signals[0].signal_id == "signal-1"
    assert result.graph_deltas[0].delta_id == "delta-1"


def test_data_source_batch_keeps_ex_payloads_as_model_instances() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    batch = protocols.DataSourceBatch(
        metadata=schemas.Ex0Metadata.model_validate(valid_metadata_payload()),
        facts=[schemas.Ex1CandidateFact.model_validate(valid_fact_payload())],
        signals=[schemas.Ex2CandidateSignal.model_validate(valid_signal_payload())],
        graph_deltas=[
            schemas.Ex3CandidateGraphDelta.model_validate(
                valid_graph_delta_payload()
            ),
        ],
    )

    assert isinstance(batch.metadata, schemas.Ex0Metadata)
    assert isinstance(batch.facts[0], schemas.Ex1CandidateFact)
    assert isinstance(batch.signals[0], schemas.Ex2CandidateSignal)
    assert isinstance(batch.graph_deltas[0], schemas.Ex3CandidateGraphDelta)


def test_data_source_batch_rejects_invalid_nested_payloads() -> None:
    protocols = import_contract_module("contracts.protocols")
    metadata_payload = {**valid_metadata_payload(), "pending_count": -1}

    with pytest.raises(pydantic.ValidationError):
        protocols.DataSourceBatch(metadata=metadata_payload)


@pytest.mark.parametrize(
    ("field_name", "payload_factory"),
    [
        ("facts", valid_fact_payload),
        ("signals", valid_signal_payload),
        ("graph_deltas", valid_graph_delta_payload),
    ],
)
def test_data_source_batch_rejects_mixed_subsystem_payloads(
    field_name: str,
    payload_factory: Callable[[], dict[str, object]],
) -> None:
    protocols = import_contract_module("contracts.protocols")
    payload = {**payload_factory(), "subsystem_id": "subsystem-filings"}

    with pytest.raises(
        pydantic.ValidationError,
        match="CONTRACT_VALIDATION_ERROR",
    ):
        protocols.DataSourceBatch(
            metadata=valid_metadata_payload(),
            **{field_name: [payload]},
        )


def test_data_source_batch_defaults_payload_lists() -> None:
    protocols = import_contract_module("contracts.protocols")

    batch = protocols.DataSourceBatch(metadata=valid_metadata_payload())

    assert batch.facts == []
    assert batch.signals == []
    assert batch.graph_deltas == []


def test_data_source_batch_json_schema_contract() -> None:
    protocols = import_contract_module("contracts.protocols")

    schema = protocols.DataSourceBatch.model_json_schema()

    assert set(schema["properties"]) >= {
        "metadata",
        "facts",
        "signals",
        "graph_deltas",
    }
    assert set(schema["required"]) == {"metadata"}
