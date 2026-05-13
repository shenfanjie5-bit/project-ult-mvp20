from __future__ import annotations

from collections.abc import Mapping
from typing import get_type_hints

import pydantic
import pytest

from tests.conftest import import_contract_module


def valid_alpha_result_payload() -> dict[str, object]:
    return {
        "score": 0.5,
        "direction": "bullish",
        "confidence": 0.8,
        "rationale": "fixture rationale",
        "evidence_refs": ["fact-1"],
        "analyzer_name": "fixture",
        "analyzer_version": "0.1.0",
    }


def test_alpha_public_api_imports() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    assert hasattr(schemas, "AlphaResult")
    assert "AlphaResult" in schemas.__all__
    assert hasattr(protocols, "AlphaAnalyzer")
    assert "AlphaAnalyzer" in protocols.__all__


def test_alpha_result_required_fields_are_frozen() -> None:
    schemas = import_contract_module("contracts.schemas")

    required_fields = set(schemas.AlphaResult.model_json_schema()["required"])

    assert {
        "score",
        "direction",
        "confidence",
        "rationale",
        "evidence_refs",
        "analyzer_name",
        "analyzer_version",
    }.issubset(required_fields)


@pytest.mark.parametrize(
    "field_name",
    [
        "score",
        "direction",
        "confidence",
        "rationale",
        "evidence_refs",
        "analyzer_name",
        "analyzer_version",
    ],
)
def test_alpha_result_required_fields_are_enforced(field_name: str) -> None:
    schemas = import_contract_module("contracts.schemas")
    payload = valid_alpha_result_payload()
    payload.pop(field_name)

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(**payload)


@pytest.mark.parametrize("score", [-1.01, 1.01])
def test_alpha_result_score_rejects_out_of_bounds_values(score: float) -> None:
    schemas = import_contract_module("contracts.schemas")

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(**{**valid_alpha_result_payload(), "score": score})


@pytest.mark.parametrize("score", ["0.5", True, float("inf"), float("nan")])
def test_alpha_result_score_rejects_coercion_and_non_finite_values(
    score: object,
) -> None:
    schemas = import_contract_module("contracts.schemas")

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(**{**valid_alpha_result_payload(), "score": score})


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_alpha_result_confidence_rejects_out_of_bounds_values(
    confidence: float,
) -> None:
    schemas = import_contract_module("contracts.schemas")

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(
            **{**valid_alpha_result_payload(), "confidence": confidence}
        )


def test_alpha_result_evidence_refs_must_be_non_empty() -> None:
    schemas = import_contract_module("contracts.schemas")

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(
            **{**valid_alpha_result_payload(), "evidence_refs": []}
        )


@pytest.mark.parametrize(
    "field_name",
    ["rationale", "analyzer_name", "analyzer_version"],
)
def test_alpha_result_string_fields_must_be_non_empty(field_name: str) -> None:
    schemas = import_contract_module("contracts.schemas")

    with pytest.raises(pydantic.ValidationError):
        schemas.AlphaResult(**{**valid_alpha_result_payload(), field_name: " "})


def test_alpha_analyzer_protocol_type_hints_resolve() -> None:
    core = import_contract_module("contracts.core")
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    plain_hints = get_type_hints(protocols.AlphaAnalyzer.analyze)
    rich_hints = get_type_hints(
        protocols.AlphaAnalyzer.analyze,
        include_extras=True,
    )

    assert plain_hints["stock"] is str
    assert rich_hints["stock"] == core.EntityId
    assert plain_hints["context"] == Mapping[str, object]
    assert plain_hints["return"] is schemas.AlphaResult


def test_fake_alpha_analyzer_satisfies_runtime_protocol() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    class FakeAlphaAnalyzer:
        @property
        def analyzer_name(self) -> str:
            return "fixture"

        @property
        def analyzer_version(self) -> str:
            return "0.1.0"

        def analyze(
            self,
            stock: str,
            context: Mapping[str, object],
        ) -> schemas.AlphaResult:
            del stock, context
            return schemas.AlphaResult(**valid_alpha_result_payload())

    fake = FakeAlphaAnalyzer()
    result = fake.analyze("stock-1", {"source": "fixture"})

    assert isinstance(fake, protocols.AlphaAnalyzer)
    assert result.score == 0.5
    assert result.analyzer_name == fake.analyzer_name


def test_analyze_only_alpha_analyzer_satisfies_base_runtime_protocol() -> None:
    schemas = import_contract_module("contracts.schemas")
    protocols = import_contract_module("contracts.protocols")

    class AnalyzeOnlyAlphaAnalyzer:
        def analyze(
            self,
            stock: str,
            context: Mapping[str, object],
        ) -> schemas.AlphaResult:
            del stock, context
            return schemas.AlphaResult(**valid_alpha_result_payload())

    fake = AnalyzeOnlyAlphaAnalyzer()

    assert isinstance(fake, protocols.AlphaAnalyzer)
