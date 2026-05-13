from pathlib import Path
from time import perf_counter

import entity_registry
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    EntityAlias,
    EntityStatus,
    EntityType,
    FinalStatus,
    ResolutionMethod,
)
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.resolution import DeterministicMatcher
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository


FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


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


def make_matcher() -> DeterministicMatcher:
    entity_repo, alias_repo = initialized_repositories()
    return DeterministicMatcher(entity_repo, alias_repo)


def entity_ids(entities: list[CanonicalEntity]) -> list[str]:
    return [entity.canonical_entity_id for entity in entities]


def make_alias(
    *,
    entity_id: str,
    alias_text: str,
    alias_type: AliasType,
) -> EntityAlias:
    return EntityAlias(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=alias_type,
        confidence=1.0,
        source="unit-test",
        is_primary=False,
    )


def test_package_exports_deterministic_matcher() -> None:
    assert entity_registry.DeterministicMatcher is DeterministicMatcher


def test_exact_match_returns_unique_short_name_and_full_name_hits() -> None:
    matcher = make_matcher()

    assert entity_ids(matcher.exact_match("贵州茅台")) == ["ENT_STOCK_600519.SH"]
    assert entity_ids(matcher.exact_match("贵州茅台酒股份有限公司")) == [
        "ENT_STOCK_600519.SH"
    ]


def test_code_match_returns_existing_code_alias_without_forging_bare_numbers() -> None:
    matcher = make_matcher()

    assert entity_ids(matcher.code_match(" 600519 ")) == ["ENT_STOCK_600519.SH"]
    assert matcher.code_match("999999") == []


def test_rule_match_returns_existing_ts_code_and_entity_id_hits() -> None:
    matcher = make_matcher()

    assert entity_ids(matcher.rule_match("600519.SH")) == ["ENT_STOCK_600519.SH"]
    assert entity_ids(matcher.rule_match(" ENT_STOCK_600519.SH ")) == [
        "ENT_STOCK_600519.SH"
    ]
    assert matcher.rule_match("600519") == []


def test_exact_match_deduplicates_repeated_aliases_for_same_entity() -> None:
    entity_repo, alias_repo = initialized_repositories()
    alias_repo.save(
        make_alias(
            entity_id="ENT_STOCK_600519.SH",
            alias_text="贵州茅台",
            alias_type=AliasType.FULL_NAME,
        )
    )
    matcher = DeterministicMatcher(entity_repo, alias_repo)

    assert entity_ids(matcher.exact_match("贵州茅台")) == ["ENT_STOCK_600519.SH"]


def test_exact_match_ignores_dangling_aliases() -> None:
    entity_repo, alias_repo = initialized_repositories()
    alias_repo.save(
        make_alias(
            entity_id="ENT_STOCK_999999.SZ",
            alias_text="悬空别名",
            alias_type=AliasType.SHORT_NAME,
        )
    )
    matcher = DeterministicMatcher(entity_repo, alias_repo)

    assert matcher.exact_match("悬空别名") == []


def test_collect_candidates_marks_unique_hit_resolved_without_llm() -> None:
    candidate_set = make_matcher().collect_candidates("贵州茅台")

    assert candidate_set.deterministic_hits == ["ENT_STOCK_600519.SH"]
    assert candidate_set.final_status is FinalStatus.RESOLVED
    assert candidate_set.llm_required is False


def test_collect_candidates_marks_missing_hit_unresolved_without_llm() -> None:
    candidate_set = make_matcher().collect_candidates("不存在的公司")

    assert candidate_set.deterministic_hits == []
    assert candidate_set.final_status is FinalStatus.UNRESOLVED
    assert candidate_set.llm_required is False


def test_collect_candidates_marks_a_h_shared_short_name_for_manual_review() -> None:
    candidate_set = make_matcher().collect_candidates("宁德时代")

    assert set(candidate_set.deterministic_hits) == {
        "ENT_STOCK_300750.SZ",
        "ENT_STOCK_03750.HK",
    }
    assert candidate_set.final_status is FinalStatus.MANUAL_REVIEW
    assert candidate_set.llm_required is True


def test_collect_candidates_prefers_direct_ts_code_over_generic_alias_collision() -> None:
    entity_repo, alias_repo = initialized_repositories()
    colliding_entity = CanonicalEntity(
        canonical_entity_id="ENT_STOCK_999998.SZ",
        entity_type=EntityType.STOCK,
        display_name="Collision",
        status=EntityStatus.ACTIVE,
        anchor_code="999998.SZ",
    )
    entity_repo.save(colliding_entity)
    alias_repo.save(
        make_alias(
            entity_id=colliding_entity.canonical_entity_id,
            alias_text="600519.SH",
            alias_type=AliasType.SHORT_NAME,
        )
    )

    candidate_set = DeterministicMatcher(entity_repo, alias_repo).collect_candidates(
        "600519.SH"
    )

    assert candidate_set.deterministic_hits == ["ENT_STOCK_600519.SH"]
    assert candidate_set.final_status is FinalStatus.RESOLVED


def test_collect_candidates_prefers_code_alias_over_generic_alias_collision() -> None:
    entity_repo, alias_repo = initialized_repositories()
    colliding_entity = CanonicalEntity(
        canonical_entity_id="ENT_STOCK_999999.SZ",
        entity_type=EntityType.STOCK,
        display_name="Collision",
        status=EntityStatus.ACTIVE,
        anchor_code="999999.SZ",
    )
    entity_repo.save(colliding_entity)
    alias_repo.save(
        make_alias(
            entity_id=colliding_entity.canonical_entity_id,
            alias_text="600519",
            alias_type=AliasType.SHORT_NAME,
        )
    )

    candidate_set = DeterministicMatcher(entity_repo, alias_repo).collect_candidates(
        "600519"
    )

    assert candidate_set.deterministic_hits == ["ENT_STOCK_600519.SH"]
    assert candidate_set.final_status is FinalStatus.RESOLVED


def test_resolve_returns_deterministic_decision_for_unique_hit() -> None:
    decision = make_matcher().resolve("贵州茅台")

    assert decision.selected_entity_id == "ENT_STOCK_600519.SH"
    assert decision.method is ResolutionMethod.DETERMINISTIC
    assert decision.confidence == 1.0


def test_resolve_returns_unresolved_decision_for_missing_hit() -> None:
    decision = make_matcher().resolve("不存在的公司")

    assert decision.selected_entity_id is None
    assert decision.method is ResolutionMethod.UNRESOLVED
    assert decision.confidence is None
    assert decision.rationale == "no deterministic candidates"


def test_resolve_returns_unresolved_decision_for_ambiguous_hit() -> None:
    decision = make_matcher().resolve("宁德时代")

    assert decision.selected_entity_id is None
    assert decision.method is ResolutionMethod.UNRESOLVED
    assert decision.confidence is None
    assert decision.rationale == "ambiguous deterministic candidates"


def test_resolution_module_has_no_provider_sdk_imports() -> None:
    text = Path("src/entity_registry/resolution.py").read_text(encoding="utf-8")

    for forbidden in ("openai", "anthropic", "google.generativeai"):
        assert forbidden not in text


def test_in_memory_deterministic_lookup_stays_under_50ms() -> None:
    matcher = make_matcher()

    started_at = perf_counter()
    matcher.resolve("贵州茅台")
    elapsed_seconds = perf_counter() - started_at

    assert elapsed_seconds < 0.05
