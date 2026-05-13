from __future__ import annotations

import inspect
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from contracts.core import EntityId
from contracts.protocols import AlphaAnalyzer, DataSourceAdapter, DataSourceBatch
from contracts.schemas import AlphaResult, CycleMetadata


def valid_cycle() -> CycleMetadata:
    return CycleMetadata(
        cycle_id="cycle-20260415-001",
        phase="collecting",
        started_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
    )


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


def valid_alpha_result_payload() -> dict[str, object]:
    return {
        "score": 0.5,
        "direction": "bullish",
        "confidence": 0.8,
        "rationale": "fixture rationale",
        "evidence_refs": ["fact-1"],
        "analyzer_name": "fixture-analyzer",
        "analyzer_version": "0.1.0",
    }


class FakeDataSourceAdapter:
    adapter_name: str = "fixture-adapter"
    adapter_version: str = "0.1.0"

    def collect(self, cycle: CycleMetadata) -> DataSourceBatch:
        del cycle
        return DataSourceBatch(
            metadata=valid_metadata_payload(),
            facts=[valid_fact_payload()],
            signals=[valid_signal_payload()],
            graph_deltas=[valid_graph_delta_payload()],
        )


class FakeAlphaAnalyzer:
    analyzer_name: str = "fixture-analyzer"
    analyzer_version: str = "0.1.0"

    def analyze(
        self,
        stock: EntityId,
        context: Mapping[str, object],
    ) -> AlphaResult:
        del stock, context
        return AlphaResult(**valid_alpha_result_payload())


def test_data_source_adapter_protocol_signature() -> None:
    signature = inspect.signature(DataSourceAdapter.collect)
    hints = get_type_hints(DataSourceAdapter.collect)

    assert tuple(signature.parameters) == ("self", "cycle")
    assert (
        signature.parameters["cycle"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert hints["cycle"] is CycleMetadata
    assert hints["return"] is DataSourceBatch


def test_alpha_analyzer_protocol_signature() -> None:
    signature = inspect.signature(AlphaAnalyzer.analyze)
    plain_hints = get_type_hints(AlphaAnalyzer.analyze)
    rich_hints = get_type_hints(AlphaAnalyzer.analyze, include_extras=True)

    assert tuple(signature.parameters) == ("self", "stock", "context")
    assert (
        signature.parameters["stock"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert (
        signature.parameters["context"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert plain_hints["stock"] is str
    assert rich_hints["stock"] == EntityId
    assert plain_hints["context"] == Mapping[str, object]
    assert plain_hints["return"] is AlphaResult


def test_runtime_checkable_protocols_accept_fake_implementations() -> None:
    adapter = FakeDataSourceAdapter()
    analyzer = FakeAlphaAnalyzer()

    batch = adapter.collect(valid_cycle())
    alpha_result = analyzer.analyze("AAPL", {"batch": batch})
    metadata_model = DataSourceBatch.model_fields["metadata"].annotation

    assert isinstance(adapter, DataSourceAdapter)
    assert isinstance(analyzer, AlphaAnalyzer)
    assert isinstance(batch, DataSourceBatch)
    assert metadata_model.__name__ == "Ex0Metadata"
    assert isinstance(batch.metadata, metadata_model)
    assert batch.metadata.subsystem_id == "subsystem-news"
    assert len(batch.facts) == 1
    assert len(batch.signals) == 1
    assert len(batch.graph_deltas) == 1
    assert type(batch.facts[0]).__name__ == "Ex1CandidateFact"
    assert type(batch.signals[0]).__name__ == "Ex2CandidateSignal"
    assert type(batch.graph_deltas[0]).__name__ == "Ex3CandidateGraphDelta"
    assert alpha_result.analyzer_name == analyzer.analyzer_name


def test_alpha_result_required_fields_are_enforced() -> None:
    required_fields = (
        "score",
        "direction",
        "confidence",
        "rationale",
        "evidence_refs",
        "analyzer_name",
        "analyzer_version",
    )

    assert set(required_fields).issubset(
        AlphaResult.model_json_schema()["required"]
    )

    for field_name in required_fields:
        payload = valid_alpha_result_payload()
        payload.pop(field_name)

        with pytest.raises(ValidationError):
            AlphaResult(**payload)
