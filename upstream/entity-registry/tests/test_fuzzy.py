from pathlib import Path

import pytest
from pydantic import ValidationError

import entity_registry
import entity_registry.fuzzy as fuzzy_module
from entity_registry.core import AliasType
from entity_registry.fuzzy import (
    FuzzyCandidate,
    FuzzyMatcherUnavailable,
    NullFuzzyMatcher,
    SimpleFuzzyMatcher,
    SplinkFuzzyMatcher,
    build_alias_blocking_key,
    score_alias_similarity,
)
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


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


@pytest.fixture
def fake_splink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fuzzy_module.importlib,
        "import_module",
        lambda name: object() if name == "splink" else None,
    )


def test_package_exports_fuzzy_public_types() -> None:
    assert entity_registry.FuzzyCandidate is FuzzyCandidate
    assert entity_registry.NullFuzzyMatcher is NullFuzzyMatcher
    assert entity_registry.SimpleFuzzyMatcher is SimpleFuzzyMatcher
    assert entity_registry.SplinkFuzzyMatcher is SplinkFuzzyMatcher


def test_fuzzy_candidate_validates_fields() -> None:
    candidate = FuzzyCandidate(
        canonical_entity_id="ENT_STOCK_600519.SH",
        alias_text="贵州茅台",
        alias_type=AliasType.SHORT_NAME,
        score=0.98,
        source="unit-test",
        blocking_key="贵州",
    )

    assert candidate.score == 0.98
    with pytest.raises(ValidationError):
        FuzzyCandidate(
            canonical_entity_id="bad-id",
            alias_text="贵州茅台",
            alias_type=AliasType.SHORT_NAME,
            score=0.98,
            source="unit-test",
        )
    with pytest.raises(ValidationError):
        FuzzyCandidate(
            canonical_entity_id="ENT_STOCK_600519.SH",
            alias_text="贵州茅台",
            alias_type=AliasType.SHORT_NAME,
            score=1.1,
            source="unit-test",
        )


def test_null_fuzzy_matcher_returns_empty_list() -> None:
    assert NullFuzzyMatcher().generate_candidates("贵州茅台公告") == []


def test_alias_similarity_helpers_are_stable() -> None:
    assert build_alias_blocking_key(" 贵州茅台 ") == "贵州"
    assert build_alias_blocking_key("600519.SH") == "6005"
    assert score_alias_similarity("贵州茅台", "贵州茅台") == 1.0
    assert score_alias_similarity("贵州茅台股份", "贵州茅台") > 0.79
    assert score_alias_similarity("", "贵州茅台") == 0.0


def test_splink_fuzzy_matcher_raises_when_backend_missing(
    monkeypatch: pytest.MonkeyPatch,
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories

    def fail_import(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(fuzzy_module.importlib, "import_module", fail_import)
    matcher = SplinkFuzzyMatcher(entity_repo=entity_repo, alias_repo=alias_repo)

    with pytest.raises(FuzzyMatcherUnavailable, match="Splink is not installed"):
        matcher.generate_candidates("贵州茅台股份")


def test_simple_fuzzy_matcher_sorts_and_dedupes_candidates_by_entity(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    matcher = SimpleFuzzyMatcher(
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        min_score=0.75,
    )

    candidates = matcher.generate_candidates("贵州茅台股份", limit=5)

    assert [candidate.canonical_entity_id for candidate in candidates] == [
        "ENT_STOCK_600519.SH"
    ]
    assert candidates[0].alias_text == "贵州茅台"
    assert candidates[0].source == "simple"
    assert candidates[0].score >= 0.8


def test_simple_fuzzy_matcher_keeps_a_h_listings_as_separate_candidates(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    matcher = SimpleFuzzyMatcher(
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        min_score=0.75,
    )

    candidates = matcher.generate_candidates("宁德时代新能", limit=10)

    assert {candidate.canonical_entity_id for candidate in candidates} == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }
    assert len(candidates) == 2


def test_simple_fuzzy_matcher_respects_limit(
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, alias_repo = initialized_repositories
    matcher = SimpleFuzzyMatcher(
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        min_score=0.70,
    )

    candidates = matcher.generate_candidates("银行股份", limit=1)

    assert len(candidates) <= 1


def test_splink_fuzzy_matcher_does_not_use_simple_heuristic_backend(
    fake_splink: None,
    monkeypatch: pytest.MonkeyPatch,
    initialized_repositories: tuple[InMemoryEntityRepository, InMemoryAliasRepository],
) -> None:
    entity_repo, _ = initialized_repositories
    alias_repo = ExplodingAliasRepository()

    def fail_similarity(raw_mention_text: str, alias_text: str) -> float:
        raise AssertionError("SplinkFuzzyMatcher must not call local similarity")

    monkeypatch.setattr(fuzzy_module, "score_alias_similarity", fail_similarity)
    matcher = SplinkFuzzyMatcher(entity_repo=entity_repo, alias_repo=alias_repo)

    with pytest.raises(NotImplementedError, match="real Splink candidate generator"):
        matcher.generate_candidates("贵州茅台股份")


class ExplodingAliasRepository(InMemoryAliasRepository):
    def list_all(self) -> list[object]:
        raise AssertionError("SplinkFuzzyMatcher must not scan aliases locally")
