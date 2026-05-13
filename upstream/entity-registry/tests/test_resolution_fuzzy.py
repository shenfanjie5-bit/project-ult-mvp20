from pathlib import Path

import pytest

from entity_registry.core import AliasType, DecisionType, ResolutionMethod
from entity_registry.fuzzy import FuzzyCandidate
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.ner import ExtractedMention
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution import resolve_mention_with_repositories
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionCaseRepository,
)


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@pytest.fixture
def initialized_repositories() -> tuple[
    InMemoryEntityRepository,
    InMemoryAliasRepository,
]:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert result.errors == []
    return entity_repo, alias_repo


def make_candidate(
    entity_id: str = "ENT_STOCK_600519.SH",
    *,
    score: float = 0.97,
    alias_text: str = "贵州茅台",
) -> FuzzyCandidate:
    return FuzzyCandidate(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=AliasType.SHORT_NAME,
        score=score,
        source="unit-test",
        blocking_key=alias_text[:2],
    )


def test_unique_deterministic_hit_does_not_call_fuzzy(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher([make_candidate()])
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "贵州茅台",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=fuzzy_matcher,
    )

    assert result.resolution_method is ResolutionMethod.DETERMINISTIC
    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert fuzzy_matcher.calls == []
    assert audit_repo.cases[0].candidate_entity_ids == ["ENT_STOCK_600519.SH"]


def test_unique_high_confidence_fuzzy_candidate_auto_resolves(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher([make_candidate(score=0.97)])
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "贵州茅台股份",
        {"document_id": "doc-fuzzy"},
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=fuzzy_matcher,
    )

    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert result.resolution_method is ResolutionMethod.FUZZY
    assert result.resolution_confidence == 0.97
    assert fuzzy_matcher.calls == ["贵州茅台股份"]
    assert audit_repo.references[0].source_context == {"document_id": "doc-fuzzy"}
    assert audit_repo.cases[0].candidate_entity_ids == ["ENT_STOCK_600519.SH"]
    assert audit_repo.cases[0].decision_type is DecisionType.AUTO


def test_low_confidence_fuzzy_candidate_returns_unresolved_with_case(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher([make_candidate(score=0.80)])
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "贵州茅台股份",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=fuzzy_matcher,
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert result.resolution_confidence is None
    assert audit_repo.references[0].resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].candidate_entity_ids == ["ENT_STOCK_600519.SH"]
    assert audit_repo.cases[0].selected_entity_id is None
    assert audit_repo.cases[0].decision_type is DecisionType.MANUAL_REVIEW


def test_ambiguous_deterministic_candidates_are_not_collapsed_by_fuzzy(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher(
        [make_candidate("ENT_STOCK_300750.SZ", alias_text="宁德时代")]
    )
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=fuzzy_matcher,
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert set(audit_repo.cases[0].candidate_entity_ids) == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }
    assert audit_repo.cases[0].selected_entity_id is None
    assert fuzzy_matcher.calls == ["宁德时代"]


def test_single_ner_mention_is_used_as_fuzzy_query(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher([make_candidate(score=0.97)])
    ner_extractor = StaticNERExtractor("贵州茅台股份")

    result = resolve_mention_with_repositories(
        "公告称贵州茅台股份上涨",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=CapturingAuditRepository(),
        fuzzy_matcher=fuzzy_matcher,
        ner_extractor=ner_extractor,
    )

    assert result.resolution_method is ResolutionMethod.FUZZY
    assert fuzzy_matcher.calls == ["贵州茅台股份"]
    assert ner_extractor.calls == ["公告称贵州茅台股份上涨"]


def test_fuzzy_audit_save_failure_does_not_delete_or_half_save(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    reference_repo = DeleteTrackingReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(RuntimeError, match="audit failure"):
        resolve_mention_with_repositories(
            "贵州茅台股份",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_repo=FailingAuditRepository(),
            reference_repo=reference_repo,
            case_repo=case_repo,
            fuzzy_matcher=RecordingFuzzyMatcher([make_candidate(score=0.97)]),
        )

    assert reference_repo.delete_calls == []
    assert reference_repo.find_unresolved() == []
    assert case_repo.find_by_reference("any") == []


def test_fuzzy_backend_failure_writes_unresolved_audit(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "贵州茅台股份",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=FailingFuzzyMatcher(),
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.references[0].resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].candidate_entity_ids == []
    assert "fuzzy candidate generation failed" in audit_repo.cases[0].decision_rationale


@pytest.mark.parametrize(
    "threshold",
    [-0.01, 1.01, float("inf"), float("nan")],
)
def test_invalid_fuzzy_auto_resolve_threshold_fails_fast(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
    threshold: float,
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = ThresholdFuzzyMatcher(threshold)

    with pytest.raises(ValueError, match="auto_resolve_score"):
        resolve_mention_with_repositories(
            "贵州茅台股份",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_repo=CapturingAuditRepository(),
            fuzzy_matcher=fuzzy_matcher,
        )


def test_resolution_candidate_set_snapshot_includes_deterministic_and_fuzzy_ids(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    resolve_mention_with_repositories(
        "宁德时代",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [make_candidate("ENT_STOCK_600519.SH", alias_text="贵州茅台")]
        ),
    )

    assert audit_repo.cases[0].candidate_entity_ids == [
        "ENT_STOCK_03750.HK",
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_600519.SH",
    ]


def test_resolution_ner_fuzzy_modules_have_no_provider_sdk_imports() -> None:
    for path in (
        "src/entity_registry/resolution.py",
        "src/entity_registry/ner.py",
        "src/entity_registry/fuzzy.py",
    ):
        text = Path(path).read_text(encoding="utf-8")
        for forbidden in ("openai", "anthropic", "google.generativeai"):
            assert forbidden not in text


class RecordingFuzzyMatcher:
    auto_resolve_score = 0.96

    def __init__(self, candidates: list[FuzzyCandidate]) -> None:
        self._candidates = candidates
        self.calls: list[str] = []

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: object = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        self.calls.append(raw_mention_text)
        return self._candidates[:limit]


class ThresholdFuzzyMatcher(RecordingFuzzyMatcher):
    def __init__(self, auto_resolve_score: float) -> None:
        super().__init__([])
        self.auto_resolve_score = auto_resolve_score


class FailingFuzzyMatcher(RecordingFuzzyMatcher):
    def __init__(self) -> None:
        super().__init__([])

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: object = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        raise RuntimeError("fuzzy backend unavailable")


class StaticNERExtractor:
    def __init__(self, mention_text: str) -> None:
        self._mention_text = mention_text
        self.calls: list[str] = []

    def extract_mentions(
        self,
        text: str,
        *,
        context: object = None,
    ) -> list[ExtractedMention]:
        self.calls.append(text)
        return [ExtractedMention(mention_text=self._mention_text)]


class CapturingAuditRepository:
    def __init__(self) -> None:
        self.references: list[EntityReference] = []
        self.cases: list[ResolutionCase] = []

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        self.references.append(reference)
        self.cases.append(case)


class FailingAuditRepository:
    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        raise RuntimeError("audit failure")


class DeleteTrackingReferenceRepository(InMemoryReferenceRepository):
    def __init__(self) -> None:
        super().__init__()
        self.delete_calls: list[str] = []

    def delete(self, reference_id: str) -> None:
        self.delete_calls.append(reference_id)
        super().delete(reference_id)
