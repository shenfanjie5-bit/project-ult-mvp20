#!/usr/bin/env python
"""M4.8 focused proof for entity-registry mention resolution.

The proof uses the existing in-memory repositories and resolution chain. It
injects a tiny fake fuzzy matcher so the harness can verify fuzzy candidate
handling without depending on an external matcher backend.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from entity_registry.contracts import (
    EntityResolutionDecision,
    to_contract_resolution_case,
)
from entity_registry.core import (
    AliasType,
    CanonicalEntity,
    DecisionType,
    EntityAlias,
    EntityStatus,
    EntityType,
    ResolutionMethod,
)
from entity_registry.fuzzy import FuzzyCandidate
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution import resolve_mention_with_repositories
from entity_registry.review import get_resolution_audit_payload
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)


@dataclass(frozen=True)
class ProofFixture:
    entity_repo: InMemoryEntityRepository
    alias_repo: InMemoryAliasRepository
    reference_repo: InMemoryResolutionAuditReferenceRepository
    case_repo: InMemoryResolutionCaseRepository
    fuzzy_matcher: "InjectedFakeFuzzyMatcher"


class InjectedFakeFuzzyMatcher:
    """Static fuzzy matcher used only by this proof harness."""

    auto_resolve_score = 0.96

    def __init__(self, candidates_by_mention: dict[str, list[FuzzyCandidate]]) -> None:
        self._candidates_by_mention = candidates_by_mention
        self.calls: list[str] = []

    def generate_candidates(
        self,
        raw_mention_text: str,
        *,
        context: object = None,
        limit: int = 10,
    ) -> list[FuzzyCandidate]:
        self.calls.append(raw_mention_text)
        return list(self._candidates_by_mention.get(raw_mention_text, []))[:limit]


def build_fixture() -> ProofFixture:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)

    for entity in [
        _make_stock("ENT_STOCK_600519.SH", "贵州茅台", "600519.SH"),
        _make_stock("ENT_STOCK_000001.SZ", "平安银行", "000001.SZ"),
        _make_stock(
            "ENT_STOCK_300750.SZ",
            "宁德时代",
            "300750.SZ",
            cross_listing_group="CATL",
        ),
        _make_stock(
            "ENT_STOCK_03750.HK",
            "宁德时代",
            "03750.HK",
            cross_listing_group="CATL",
        ),
    ]:
        entity_repo.save(entity)

    for alias in [
        _make_alias("ENT_STOCK_600519.SH", "贵州茅台", AliasType.SHORT_NAME),
        _make_alias("ENT_STOCK_600519.SH", "600519", AliasType.CODE),
        _make_alias("ENT_STOCK_000001.SZ", "平安银行", AliasType.SHORT_NAME),
        _make_alias("ENT_STOCK_000001.SZ", "000001", AliasType.CODE),
        _make_alias("ENT_STOCK_300750.SZ", "宁德时代", AliasType.SHORT_NAME),
        _make_alias("ENT_STOCK_03750.HK", "宁德时代", AliasType.SHORT_NAME),
    ]:
        alias_repo.save(alias)

    fuzzy_matcher = InjectedFakeFuzzyMatcher(
        {
            "宁德时代新能源": [
                _make_fuzzy_candidate(
                    "ENT_STOCK_300750.SZ",
                    "宁德时代",
                    0.91,
                ),
                _make_fuzzy_candidate(
                    "ENT_STOCK_03750.HK",
                    "宁德时代",
                    0.89,
                ),
            ],
        }
    )
    return ProofFixture(
        entity_repo=entity_repo,
        alias_repo=alias_repo,
        reference_repo=reference_repo,
        case_repo=case_repo,
        fuzzy_matcher=fuzzy_matcher,
    )


def run_proof() -> dict[str, Any]:
    fixture = build_fixture()
    case_summaries = [
        _run_case(
            fixture,
            name="deterministic_exact",
            mention="贵州茅台",
            context={"document_id": "m4-8-proof-exact"},
            expected_entity_id="ENT_STOCK_600519.SH",
            expected_method=ResolutionMethod.DETERMINISTIC,
            expected_decision_type=DecisionType.AUTO,
            expected_candidate_ids=["ENT_STOCK_600519.SH"],
        ),
        _run_case(
            fixture,
            name="deterministic_code",
            mention="000001",
            context={"document_id": "m4-8-proof-code"},
            expected_entity_id="ENT_STOCK_000001.SZ",
            expected_method=ResolutionMethod.DETERMINISTIC,
            expected_decision_type=DecisionType.AUTO,
            expected_candidate_ids=["ENT_STOCK_000001.SZ"],
        ),
        _run_case(
            fixture,
            name="deterministic_rule",
            mention="600519.SH",
            context={"document_id": "m4-8-proof-rule"},
            expected_entity_id="ENT_STOCK_600519.SH",
            expected_method=ResolutionMethod.DETERMINISTIC,
            expected_decision_type=DecisionType.AUTO,
            expected_candidate_ids=["ENT_STOCK_600519.SH"],
        ),
        _run_case(
            fixture,
            name="ambiguous_fuzzy_candidate",
            mention="宁德时代新能源",
            context={"document_id": "m4-8-proof-fuzzy"},
            expected_entity_id=None,
            expected_method=ResolutionMethod.UNRESOLVED,
            expected_decision_type=DecisionType.MANUAL_REVIEW,
            expected_candidate_ids=[
                "ENT_STOCK_300750.SZ",
                "ENT_STOCK_03750.HK",
            ],
        ),
        _run_case(
            fixture,
            name="unresolved_fail_closed",
            mention="不存在的公司",
            context={"document_id": "m4-8-proof-unresolved"},
            expected_entity_id=None,
            expected_method=ResolutionMethod.UNRESOLVED,
            expected_decision_type=DecisionType.AUTO,
            expected_candidate_ids=[],
        ),
    ]

    _assert_equal(
        "fake fuzzy calls",
        fixture.fuzzy_matcher.calls,
        ["宁德时代新能源", "不存在的公司"],
    )

    return {
        "proof": "m4.8-focused-resolution-proof",
        "case_count": len(case_summaries),
        "cases": case_summaries,
        "audit_payload_verified": all(
            item["audit_payload_verified"] for item in case_summaries
        ),
        "contract_projection_verified": all(
            item["contract_projection_verified"] for item in case_summaries
        ),
        "fuzzy_backend": "injected_fake",
        "core_library_changes_required": False,
        "productionization_pending": [
            "durable repository adapter wiring",
            "external fuzzy backend implementation",
            "larger fixture coverage",
        ],
    }


def _run_case(
    fixture: ProofFixture,
    *,
    name: str,
    mention: str,
    context: dict[str, object],
    expected_entity_id: str | None,
    expected_method: ResolutionMethod,
    expected_decision_type: DecisionType,
    expected_candidate_ids: list[str],
) -> dict[str, Any]:
    result = resolve_mention_with_repositories(
        mention,
        context,
        entity_repo=fixture.entity_repo,
        alias_repo=fixture.alias_repo,
        reference_repo=fixture.reference_repo,
        case_repo=fixture.case_repo,
        fuzzy_matcher=fixture.fuzzy_matcher,
    )
    reference = _latest_reference_for_mention(fixture.reference_repo, mention)
    payload = get_resolution_audit_payload(
        reference.reference_id,
        reference_repo=fixture.reference_repo,
        case_repo=fixture.case_repo,
    )
    case = payload.resolution_case
    candidate_entities = [
        _require_entity(fixture.entity_repo, entity_id)
        for entity_id in case.candidate_entity_ids
    ]
    contract_case = to_contract_resolution_case(
        case,
        input_alias=mention,
        candidate_entities=candidate_entities,
        decision=(
            EntityResolutionDecision.MATCHED
            if expected_entity_id is not None
            else EntityResolutionDecision.UNRESOLVED
        ),
        resolved_entity=(
            None
            if expected_entity_id is None
            else _require_entity(fixture.entity_repo, expected_entity_id)
        ),
        confidence=result.resolution_confidence,
    )

    _assert_equal(
        f"{name} result entity",
        result.resolved_entity_id,
        expected_entity_id,
    )
    _assert_equal(f"{name} result method", result.resolution_method, expected_method)
    _assert_equal(
        f"{name} reference entity",
        reference.resolved_entity_id,
        expected_entity_id,
    )
    _assert_equal(
        f"{name} reference method",
        reference.resolution_method,
        expected_method,
    )
    _assert_equal(f"{name} case selected", case.selected_entity_id, expected_entity_id)
    _assert_equal(f"{name} case decision", case.decision_type, expected_decision_type)
    _assert_equal(
        f"{name} candidates",
        case.candidate_entity_ids,
        expected_candidate_ids,
    )
    _assert_equal(f"{name} payload reference", payload.entity_reference, reference)
    _assert_equal(
        f"{name} payload unresolved",
        payload.unresolved,
        expected_entity_id is None,
    )
    _assert_equal(f"{name} contract input", contract_case.input_alias, mention)
    _assert_equal(
        f"{name} contract evidence",
        contract_case.evidence_refs,
        [reference.reference_id],
    )

    return {
        "name": name,
        "mention": mention,
        "resolved_entity_id": result.resolved_entity_id,
        "resolution_method": result.resolution_method.value,
        "resolution_confidence": result.resolution_confidence,
        "decision_type": case.decision_type.value,
        "candidate_entity_ids": list(case.candidate_entity_ids),
        "audit_payload_verified": True,
        "contract_projection_verified": True,
        "auto_selected": case.selected_entity_id is not None,
    }


def _latest_reference_for_mention(
    reference_repo: InMemoryResolutionAuditReferenceRepository,
    mention: str,
) -> EntityReference:
    references = [
        reference
        for reference in reference_repo._references.values()
        if reference.raw_mention_text == mention
    ]
    if not references:
        raise AssertionError(f"missing reference for mention: {mention}")
    return max(references, key=lambda reference: reference.created_at)


def _make_stock(
    entity_id: str,
    display_name: str,
    anchor_code: str,
    *,
    cross_listing_group: str | None = None,
) -> CanonicalEntity:
    return CanonicalEntity(
        canonical_entity_id=entity_id,
        entity_type=EntityType.STOCK,
        display_name=display_name,
        status=EntityStatus.ACTIVE,
        anchor_code=anchor_code,
        cross_listing_group=cross_listing_group,
    )


def _make_alias(
    entity_id: str,
    alias_text: str,
    alias_type: AliasType,
) -> EntityAlias:
    return EntityAlias(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=alias_type,
        confidence=1.0,
        source="m4.8-proof-fixture",
        is_primary=alias_type is not AliasType.CODE,
    )


def _make_fuzzy_candidate(
    entity_id: str,
    alias_text: str,
    score: float,
) -> FuzzyCandidate:
    return FuzzyCandidate(
        canonical_entity_id=entity_id,
        alias_text=alias_text,
        alias_type=AliasType.SHORT_NAME,
        score=score,
        source="m4.8-proof-fake-fuzzy",
        blocking_key=alias_text[:2],
    )


def _require_entity(
    entity_repo: InMemoryEntityRepository,
    entity_id: str,
) -> CanonicalEntity:
    entity = entity_repo.get(entity_id)
    if entity is None:
        raise AssertionError(f"missing fixture entity: {entity_id}")
    return entity


def _assert_equal(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _write_summary(summary: dict[str, Any], path: Path | None) -> None:
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if path is None:
        print(rendered)
        return
    path.write_text(rendered + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional path for writing the stable JSON proof summary.",
    )
    args = parser.parse_args(argv)
    summary = run_proof()
    _write_summary(summary, args.summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
