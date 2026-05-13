from pathlib import Path
from collections.abc import Iterator

import pytest

import entity_registry
import entity_registry.init as init_module
from entity_registry.core import AliasType, DecisionType, ResolutionMethod
from entity_registry.fuzzy import FuzzyCandidate
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.llm_client import (
    LLMDisambiguationRequest,
    LLMDisambiguationResponse,
)
from entity_registry.ner import ExtractedMention
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution import resolve_mention_with_repositories
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryReferenceRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


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
    entity_id: str,
    *,
    score: float = 0.90,
    alias_text: str = "宁德时代新能源",
) -> FuzzyCandidate:
    return FuzzyCandidate(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=AliasType.FULL_NAME,
        score=score,
        source="unit-test",
        blocking_key=alias_text[:2],
    )


def test_unique_deterministic_hit_does_not_call_fuzzy_or_reasoner(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    fuzzy_matcher = RecordingFuzzyMatcher(
        [make_candidate("ENT_STOCK_300750.SZ")]
    )
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_300750.SZ",
            confidence=0.9,
            rationale="should not be used",
        )
    )

    result = resolve_mention_with_repositories(
        "贵州茅台",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=CapturingAuditRepository(),
        fuzzy_matcher=fuzzy_matcher,
        reasoner_client=reasoner_client,
    )

    assert result.resolution_method is ResolutionMethod.DETERMINISTIC
    assert result.resolved_entity_id == "ENT_STOCK_600519.SH"
    assert fuzzy_matcher.calls == []
    assert reasoner_client.calls == []


def test_unique_high_confidence_fuzzy_hit_does_not_call_reasoner(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_600519.SH",
            confidence=0.9,
            rationale="should not be used",
        )
    )

    result = resolve_mention_with_repositories(
        "贵州茅台股份",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=CapturingAuditRepository(),
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                FuzzyCandidate(
                    canonical_entity_id="ENT_STOCK_600519.SH",
                    alias_text="贵州茅台",
                    alias_type=AliasType.SHORT_NAME,
                    score=0.97,
                    source="unit-test",
                )
            ]
        ),
        reasoner_client=reasoner_client,
    )

    assert result.model_dump(mode="json") == {
        "raw_mention_text": "贵州茅台股份",
        "resolved_entity_id": "ENT_STOCK_600519.SH",
        "resolution_method": "fuzzy",
        "resolution_confidence": 0.97,
    }
    assert reasoner_client.calls == []


def test_ambiguous_fuzzy_candidates_resolve_via_reasoner(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_03750.HK",
            confidence=0.89,
            rationale="context points to the HK listing",
        )
    )

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        {"market": "HK"},
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate(
                    "ENT_STOCK_03750.HK",
                    score=0.91,
                    alias_text="宁德时代新能源科技股份有限公司",
                ),
                make_candidate(
                    "ENT_STOCK_300750.SZ",
                    score=0.90,
                    alias_text="宁德时代新能源科技股份有限公司",
                ),
            ]
        ),
        reasoner_client=reasoner_client,
    )

    assert result.model_dump(mode="json") == {
        "raw_mention_text": "宁德时代新能源",
        "resolved_entity_id": "ENT_STOCK_03750.HK",
        "resolution_method": "llm",
        "resolution_confidence": 0.89,
    }
    assert [candidate.canonical_entity_id for candidate in reasoner_client.calls[0].candidates] == [
        "ENT_STOCK_03750.HK",
        "ENT_STOCK_300750.SZ",
    ]
    assert reasoner_client.calls[0].candidates[0].display_name == "宁德时代"
    assert audit_repo.references[0].resolution_method is ResolutionMethod.LLM
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert audit_repo.cases[0].selected_entity_id == "ENT_STOCK_03750.HK"


def test_reasoner_decline_returns_unresolved_llm_assisted_case(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate("ENT_STOCK_03750.HK"),
                make_candidate("ENT_STOCK_300750.SZ"),
            ]
        ),
        reasoner_client=RecordingReasonerClient(
            LLMDisambiguationResponse(
                selected_entity_id=None,
                confidence=None,
                rationale="both listings remain plausible",
            )
        ),
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert result.resolution_confidence is None
    assert audit_repo.references[0].resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "declined" in audit_repo.cases[0].decision_rationale


def test_reasoner_low_confidence_returns_unresolved(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate("ENT_STOCK_03750.HK"),
                make_candidate("ENT_STOCK_300750.SZ"),
            ]
        ),
        reasoner_client=RecordingReasonerClient(
            LLMDisambiguationResponse(
                selected_entity_id="ENT_STOCK_03750.HK",
                confidence=0.50,
                rationale="weak context",
            )
        ),
    )

    assert result.model_dump(mode="json") == {
        "raw_mention_text": "宁德时代新能源",
        "resolved_entity_id": None,
        "resolution_method": "unresolved",
        "resolution_confidence": None,
    }
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "below threshold" in audit_repo.cases[0].decision_rationale


def test_reasoner_invalid_candidate_id_returns_unresolved(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate("ENT_STOCK_03750.HK"),
                make_candidate("ENT_STOCK_300750.SZ"),
            ]
        ),
        reasoner_client=RecordingReasonerClient(
            LLMDisambiguationResponse(
                selected_entity_id="ENT_STOCK_000001.SZ",
                confidence=0.91,
                rationale="bad selection",
            )
        ),
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "invalid reasoner selection" in audit_repo.cases[0].decision_rationale


def test_reasoner_error_returns_unresolved_llm_assisted_case(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate("ENT_STOCK_03750.HK"),
                make_candidate("ENT_STOCK_300750.SZ"),
            ]
        ),
        reasoner_client=FailingReasonerClient(),
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "timed out" in audit_repo.cases[0].decision_rationale


def test_malformed_reasoner_response_returns_unresolved_audit_case(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代新能源",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=RecordingFuzzyMatcher(
            [
                make_candidate("ENT_STOCK_03750.HK"),
                make_candidate("ENT_STOCK_300750.SZ"),
            ]
        ),
        reasoner_client=MalformedReasonerClient(),
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert result.resolution_confidence is None
    assert audit_repo.references[0].resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "unsupported response type" in audit_repo.cases[0].decision_rationale


def test_missing_reasoner_client_returns_manual_review_unresolved(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()

    result = resolve_mention_with_repositories(
        "宁德时代",
        None,
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
    )

    assert result.resolved_entity_id is None
    assert result.resolution_method is ResolutionMethod.UNRESOLVED
    assert audit_repo.cases[0].decision_type is DecisionType.MANUAL_REVIEW
    assert audit_repo.cases[0].decision_rationale == "reasoner client is not configured"


def test_public_resolve_mention_uses_configured_reasoner_client(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_300750.SZ",
            confidence=0.86,
            rationale="A-share context",
        )
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
        reasoner_client=reasoner_client,
    )

    result = entity_registry.resolve_mention("宁德时代", {"market": "A-share"})

    references = list(reference_repo._references.values())
    assert result.resolved_entity is not None
    assert result.resolved_entity.entity_id == "ENT_STOCK_300750.SZ"
    assert result.confidence == 0.86
    assert len(reasoner_client.calls) == 1
    assert case_repo.find_by_reference(references[0].reference_id)[0].decision_type is (
        DecisionType.LLM_ASSISTED
    )


def test_public_resolve_mention_uses_configured_ner_fuzzy_and_reasoner(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    fuzzy_matcher = RecordingFuzzyMatcher(
        [
            make_candidate(
                "ENT_STOCK_03750.HK",
                score=0.91,
                alias_text="宁德时代新能源科技股份有限公司",
            ),
            make_candidate(
                "ENT_STOCK_300750.SZ",
                score=0.90,
                alias_text="宁德时代新能源科技股份有限公司",
            ),
        ]
    )
    ner_extractor = StaticNERExtractor("宁德时代新能源")
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_03750.HK",
            confidence=0.89,
            rationale="HK market context",
        )
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
        fuzzy_matcher=fuzzy_matcher,
        ner_extractor=ner_extractor,
        reasoner_client=reasoner_client,
    )

    result = entity_registry.resolve_mention(
        "公告称宁德时代新能源获增持",
        {"market": "HK", "document_id": "doc-full-chain"},
    )

    references = list(reference_repo._references.values())
    case = case_repo.find_by_reference(references[0].reference_id)[0]
    assert result.input_alias == "公告称宁德时代新能源获增持"
    assert result.resolved_entity is not None
    assert result.resolved_entity.entity_id == "ENT_STOCK_03750.HK"
    assert result.confidence == 0.89
    assert ner_extractor.calls == ["公告称宁德时代新能源获增持"]
    assert fuzzy_matcher.calls == ["宁德时代新能源"]
    assert [candidate.canonical_entity_id for candidate in reasoner_client.calls[0].candidates] == [
        "ENT_STOCK_03750.HK",
        "ENT_STOCK_300750.SZ",
    ]
    assert references[0].source_context == {
        "market": "HK",
        "document_id": "doc-full-chain",
    }
    assert references[0].resolution_method is ResolutionMethod.LLM
    assert case.decision_type is DecisionType.LLM_ASSISTED
    assert case.selected_entity_id == "ENT_STOCK_03750.HK"


def test_public_resolve_mention_uses_one_default_context_snapshot(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_repo, alias_repo = initialized_repositories
    case_repo_a = InMemoryResolutionCaseRepository()
    reference_repo_a = InMemoryResolutionAuditReferenceRepository(case_repo_a)
    reasoner_a = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_300750.SZ",
            confidence=0.86,
            rationale="first configured context",
        )
    )
    case_repo_b = InMemoryResolutionCaseRepository()
    reference_repo_b = InMemoryResolutionAuditReferenceRepository(case_repo_b)
    reasoner_b = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_03750.HK",
            confidence=0.86,
            rationale="replacement context",
        )
    )
    entity_registry.configure_default_repositories(
        entity_repo,
        alias_repo,
        reference_repo=reference_repo_a,
        case_repo=case_repo_a,
        reasoner_client=reasoner_a,
    )
    original_get_context = init_module._get_default_repository_context
    read_count = 0

    def reconfiguring_get_context() -> object:
        nonlocal read_count
        context = original_get_context()
        read_count += 1
        if read_count == 1:
            entity_registry.configure_default_repositories(
                entity_repo,
                alias_repo,
                reference_repo=reference_repo_b,
                case_repo=case_repo_b,
                reasoner_client=reasoner_b,
            )
        return context

    monkeypatch.setattr(
        init_module,
        "_get_default_repository_context",
        reconfiguring_get_context,
    )

    result = entity_registry.resolve_mention("宁德时代", {"market": "A-share"})

    references_a = list(reference_repo_a._references.values())
    assert read_count == 1
    assert result.resolved_entity is not None
    assert result.resolved_entity.entity_id == "ENT_STOCK_300750.SZ"
    assert result.confidence == 0.86
    assert len(reasoner_a.calls) == 1
    assert reasoner_b.calls == []
    assert len(references_a) == 1
    assert case_repo_a.find_by_reference(references_a[0].reference_id)[0].selected_entity_id == (
        "ENT_STOCK_300750.SZ"
    )
    assert reference_repo_b._references == {}
    assert case_repo_b.find_by_reference("any") == []


def test_llm_audit_failure_propagates_without_delete(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    reference_repo = DeleteTrackingReferenceRepository()
    case_repo = InMemoryResolutionCaseRepository()

    with pytest.raises(RuntimeError, match="audit failure"):
        resolve_mention_with_repositories(
            "宁德时代新能源",
            None,
            entity_repo=entity_repo,
            alias_repo=alias_repo,
            audit_repo=FailingAuditRepository(),
            reference_repo=reference_repo,
            case_repo=case_repo,
            fuzzy_matcher=RecordingFuzzyMatcher(
                [
                    make_candidate("ENT_STOCK_03750.HK"),
                    make_candidate("ENT_STOCK_300750.SZ"),
                ]
            ),
            reasoner_client=RecordingReasonerClient(
                LLMDisambiguationResponse(
                    selected_entity_id="ENT_STOCK_03750.HK",
                    confidence=0.90,
                    rationale="HK listing",
                )
            ),
        )

    assert reference_repo.delete_calls == []
    assert reference_repo.find_unresolved() == []
    assert case_repo.find_by_reference("any") == []


def test_ambiguous_deterministic_candidates_still_use_reasoner_when_fuzzy_fails(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    audit_repo = CapturingAuditRepository()
    reasoner_client = RecordingReasonerClient(
        LLMDisambiguationResponse(
            selected_entity_id="ENT_STOCK_300750.SZ",
            confidence=0.86,
            rationale="A-share context",
        )
    )

    result = resolve_mention_with_repositories(
        "宁德时代",
        {"market": "A-share"},
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        audit_repo=audit_repo,
        fuzzy_matcher=FailingFuzzyMatcher(),
        reasoner_client=reasoner_client,
    )

    assert result.resolution_method is ResolutionMethod.LLM
    assert result.resolved_entity_id == "ENT_STOCK_300750.SZ"
    assert len(reasoner_client.calls) == 1
    assert audit_repo.cases[0].decision_type is DecisionType.LLM_ASSISTED
    assert "A-share context" in audit_repo.cases[0].decision_rationale
    assert (
        "fuzzy candidate generation failed"
        in audit_repo.cases[0].decision_rationale
    )


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


class FailingFuzzyMatcher:
    auto_resolve_score = 0.96

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


class RecordingReasonerClient:
    def __init__(self, response: LLMDisambiguationResponse) -> None:
        self._response = response
        self.calls: list[LLMDisambiguationRequest] = []

    def disambiguate(
        self,
        request: LLMDisambiguationRequest,
    ) -> LLMDisambiguationResponse:
        self.calls.append(request)
        return self._response


class FailingReasonerClient:
    def disambiguate(
        self,
        request: LLMDisambiguationRequest,
    ) -> LLMDisambiguationResponse:
        raise TimeoutError("runtime timed out")


class MalformedReasonerClient:
    def disambiguate(self, request: LLMDisambiguationRequest) -> object:
        return ["not", "a", "reasoner", "response"]


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
