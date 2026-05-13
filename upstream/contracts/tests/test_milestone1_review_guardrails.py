from __future__ import annotations

import inspect
import pathlib
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import get_type_hints

import pydantic
import pytest

import contracts.protocols as protocols
import contracts.schemas as schemas
from contracts.core import EntityId
from contracts.errors import ContractError, ErrorCode
from contracts.protocols import AlphaAnalyzer, DataSourceAdapter, DataSourceBatch
from contracts.schemas import (
    FORBIDDEN_INGEST_METADATA_FIELDS,
    FORMAL_OBJECT_REGISTRY,
    AlphaResult,
    AlphaResultSnapshot,
    AuditRecord,
    CycleMetadata,
    DashboardSnapshot,
    Ex0Metadata,
    Ex1CandidateFact,
    Ex2CandidateSignal,
    Ex3CandidateGraphDelta,
    FormalObjectBase,
    FormalObjectName,
    OfficialAlphaPool,
    RecommendationSnapshot,
    ReplayRecord,
    Report,
    WorldStateSnapshot,
    get_formal_object_model,
)


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)


def valid_ex0_payload() -> dict[str, object]:
    return {
        "subsystem_id": "subsystem-news",
        "version": "0.1.0",
        "heartbeat_at": NOW,
        "status": "ok",
        "last_output_at": NOW - timedelta(minutes=5),
        "pending_count": 0,
    }


def valid_ex1_payload() -> dict[str, object]:
    return {
        "fact_id": "fact-1",
        "entity_id": "AAPL",
        "fact_type": "earnings",
        "fact_content": {"headline": "sample"},
        "confidence": 0.8,
        "source_reference": {"source": "fixture"},
        "extracted_at": NOW,
        "subsystem_id": "subsystem-news",
    }


def valid_ex2_payload() -> dict[str, object]:
    return {
        "signal_id": "signal-1",
        "signal_type": "sentiment_shift",
        "direction": "bullish",
        "magnitude": 0.4,
        "affected_entities": ["AAPL"],
        "affected_sectors": ["technology"],
        "time_horizon": "short_term",
        "evidence": ["fact-1"],
        "confidence": 0.7,
        "subsystem_id": "subsystem-news",
    }


def valid_ex3_payload() -> dict[str, object]:
    return {
        "delta_id": "delta-1",
        "delta_type": "upsert_relation",
        "source_node": "AAPL",
        "target_node": "technology",
        "relation_type": "belongs_to_sector",
        "properties": {"weight": 1.0},
        "evidence": ["fact-1"],
        "subsystem_id": "subsystem-news",
    }


def valid_cycle() -> CycleMetadata:
    return CycleMetadata.model_validate(
        {
            "cycle_id": "cycle-20260415-001",
            "phase": "collecting",
            "started_at": NOW,
        }
    )


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


EX_PAYLOAD_CONTRACTS = (
    (
        Ex0Metadata,
        valid_ex0_payload,
        {
            "subsystem_id",
            "version",
            "heartbeat_at",
            "status",
            "last_output_at",
            "pending_count",
        },
    ),
    (
        Ex1CandidateFact,
        valid_ex1_payload,
        {
            "fact_id",
            "entity_id",
            "fact_type",
            "fact_content",
            "confidence",
            "source_reference",
            "extracted_at",
            "subsystem_id",
        },
    ),
    (
        Ex2CandidateSignal,
        valid_ex2_payload,
        {
            "signal_id",
            "signal_type",
            "direction",
            "magnitude",
            "affected_entities",
            "affected_sectors",
            "time_horizon",
            "evidence",
            "confidence",
            "subsystem_id",
        },
    ),
    (
        Ex3CandidateGraphDelta,
        valid_ex3_payload,
        {
            "delta_id",
            "delta_type",
            "source_node",
            "target_node",
            "relation_type",
            "properties",
            "evidence",
            "subsystem_id",
        },
    ),
)


PayloadFactory = Callable[[], dict[str, object]]


FORMAL_OBJECT_CONTRACTS: dict[FormalObjectName, type[FormalObjectBase]] = {
    FormalObjectName.WORLD_STATE_SNAPSHOT: WorldStateSnapshot,
    FormalObjectName.OFFICIAL_ALPHA_POOL: OfficialAlphaPool,
    FormalObjectName.ALPHA_RESULT_SNAPSHOT: AlphaResultSnapshot,
    FormalObjectName.RECOMMENDATION_SNAPSHOT: RecommendationSnapshot,
    FormalObjectName.DASHBOARD_SNAPSHOT: DashboardSnapshot,
    FormalObjectName.REPORT: Report,
    FormalObjectName.AUDIT_RECORD: AuditRecord,
    FormalObjectName.REPLAY_RECORD: ReplayRecord,
}


def test_milestone_review_public_imports_are_exposed() -> None:
    expected_schema_exports = {
        "FORBIDDEN_INGEST_METADATA_FIELDS": FORBIDDEN_INGEST_METADATA_FIELDS,
        "Ex0Metadata": Ex0Metadata,
        "Ex1CandidateFact": Ex1CandidateFact,
        "Ex2CandidateSignal": Ex2CandidateSignal,
        "Ex3CandidateGraphDelta": Ex3CandidateGraphDelta,
        "AlphaResult": AlphaResult,
        "CycleMetadata": CycleMetadata,
        "FormalObjectName": FormalObjectName,
        "FORMAL_OBJECT_REGISTRY": FORMAL_OBJECT_REGISTRY,
        "get_formal_object_model": get_formal_object_model,
    }
    expected_protocol_exports = {
        "AlphaAnalyzer": AlphaAnalyzer,
        "DataSourceAdapter": DataSourceAdapter,
        "DataSourceBatch": DataSourceBatch,
    }

    for public_name, exported_object in expected_schema_exports.items():
        assert getattr(schemas, public_name) is exported_object
        assert public_name in schemas.__all__

    for public_name, exported_object in expected_protocol_exports.items():
        assert getattr(protocols, public_name) is exported_object
        assert public_name in protocols.__all__


def test_milestone_review_ex_payload_required_fields_are_exact() -> None:
    for model, _, expected_required_fields in EX_PAYLOAD_CONTRACTS:
        schema = model.model_json_schema()

        assert set(schema["required"]) == expected_required_fields
        assert FORBIDDEN_INGEST_METADATA_FIELDS.isdisjoint(schema["properties"])


@pytest.mark.parametrize(
    ("model", "payload_factory", "required_fields"),
    EX_PAYLOAD_CONTRACTS,
)
def test_milestone_review_ex_payload_validation_blocks_drift(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
    required_fields: set[str],
) -> None:
    payload = payload_factory()
    assert model.model_validate(payload)

    for field_name in sorted(required_fields):
        invalid_payload = {**payload}
        invalid_payload.pop(field_name)
        with pytest.raises(pydantic.ValidationError):
            model.model_validate(invalid_payload)


@pytest.mark.parametrize(
    ("model", "payload_factory", "ingest_field"),
    [
        (model, payload_factory, ingest_field)
        for model, payload_factory, _ in EX_PAYLOAD_CONTRACTS
        for ingest_field in sorted(FORBIDDEN_INGEST_METADATA_FIELDS)
    ],
)
def test_milestone_review_ex_payloads_reject_layer_b_ingest_metadata(
    model: type[pydantic.BaseModel],
    payload_factory: PayloadFactory,
    ingest_field: str,
) -> None:
    payload = {**payload_factory(), ingest_field: NOW}

    with pytest.raises(pydantic.ValidationError, match="ingest metadata"):
        model.model_validate(payload)


def test_milestone_review_formal_object_registry_is_closed() -> None:
    expected_values = {
        "world_state_snapshot",
        "official_alpha_pool",
        "alpha_result_snapshot",
        "recommendation_snapshot",
        "dashboard_snapshot",
        "report",
        "audit_record",
        "replay_record",
    }

    assert {name.value for name in FormalObjectName} == expected_values
    assert "backtest_result" not in expected_values
    assert dict(FORMAL_OBJECT_REGISTRY) == FORMAL_OBJECT_CONTRACTS
    assert len(FORMAL_OBJECT_REGISTRY) == 8

    with pytest.raises(ValueError):
        FormalObjectName("backtest_result")

    with pytest.raises(ContractError) as exc_info:
        get_formal_object_model("backtest_result")
    assert exc_info.value.code is ErrorCode.UNKNOWN_FORMAL_OBJECT


def test_milestone_review_formal_objects_and_cycle_metadata_validate() -> None:
    formal_object = Report.model_validate(
        {
            "object_id": "report-1",
            "version": "0.1.0",
            "created_at": NOW,
            "payload": {"status": "ready"},
        }
    )
    cycle = valid_cycle()

    assert formal_object.object_name is FormalObjectName.REPORT
    assert set(Report.model_json_schema()["required"]) == {
        "object_id",
        "version",
        "created_at",
        "payload",
    }
    assert set(CycleMetadata.model_json_schema()["required"]) == {
        "cycle_id",
        "phase",
        "started_at",
    }
    assert cycle.ended_at is None

    with pytest.raises(pydantic.ValidationError, match="ended_at"):
        CycleMetadata.model_validate(
            {
                "cycle_id": "cycle-20260415-001",
                "phase": "completed",
                "started_at": NOW,
                "ended_at": NOW - timedelta(seconds=1),
            }
        )


def test_milestone_review_protocol_signatures_are_stable() -> None:
    collect_signature = inspect.signature(DataSourceAdapter.collect)
    collect_hints = get_type_hints(DataSourceAdapter.collect)
    analyze_signature = inspect.signature(AlphaAnalyzer.analyze)
    analyze_hints = get_type_hints(AlphaAnalyzer.analyze)
    rich_analyze_hints = get_type_hints(
        AlphaAnalyzer.analyze,
        include_extras=True,
    )

    assert tuple(collect_signature.parameters) == ("self", "cycle")
    assert collect_hints["cycle"] is CycleMetadata
    assert collect_hints["return"] is DataSourceBatch
    assert tuple(analyze_signature.parameters) == ("self", "stock", "context")
    assert analyze_hints["stock"] is str
    assert rich_analyze_hints["stock"] == EntityId
    assert analyze_hints["context"] == Mapping[str, object]
    assert analyze_hints["return"] is AlphaResult


def test_milestone_review_fake_protocol_implementations_work() -> None:
    class FakeDataSourceAdapter:
        @property
        def adapter_name(self) -> str:
            return "fixture-adapter"

        @property
        def adapter_version(self) -> str:
            return "0.1.0"

        def collect(self, cycle: CycleMetadata) -> DataSourceBatch:
            del cycle
            return DataSourceBatch(
                metadata=valid_ex0_payload(),
                facts=[valid_ex1_payload()],
                signals=[valid_ex2_payload()],
                graph_deltas=[valid_ex3_payload()],
            )

    class FakeAlphaAnalyzer:
        @property
        def analyzer_name(self) -> str:
            return "fixture-analyzer"

        @property
        def analyzer_version(self) -> str:
            return "0.1.0"

        def analyze(
            self,
            stock: EntityId,
            context: Mapping[str, object],
        ) -> AlphaResult:
            del stock, context
            return AlphaResult.model_validate(valid_alpha_result_payload())

    adapter = FakeDataSourceAdapter()
    analyzer = FakeAlphaAnalyzer()
    batch = adapter.collect(valid_cycle())
    result = analyzer.analyze("AAPL", {"batch": batch})

    assert isinstance(adapter, DataSourceAdapter)
    assert isinstance(analyzer, AlphaAnalyzer)
    assert batch.metadata.subsystem_id == "subsystem-news"
    assert batch.facts[0].fact_id == "fact-1"
    assert batch.signals[0].signal_id == "signal-1"
    assert batch.graph_deltas[0].delta_id == "delta-1"
    assert result.analyzer_name == analyzer.analyzer_name


def test_milestone_review_ci_does_not_mask_pytest_collection_failures() -> None:
    ci_script = (PROJECT_ROOT / "scripts" / "ci.sh").read_text(encoding="utf-8")
    test_files = sorted((PROJECT_ROOT / "tests").glob("test_*.py"))

    assert test_files
    assert "-m pytest" in ci_script
    assert "|| true" not in ci_script
