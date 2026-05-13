#!/usr/bin/env python
"""Local evidence runner for entity-registry production readiness gates."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from entity_registry.core import CanonicalEntity, EntityAlias
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.readiness import (
    EntityRegistryRuntimeConfig,
    ProductionReadinessError,
    assert_runtime_readiness,
    check_runtime_readiness,
)
from entity_registry.references import EntityReference, ResolutionCase
from entity_registry.resolution import resolve_mention_with_repositories
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)


NON_GOALS = {
    "splink_backend": "not_proven",
    "reasoner_runtime": "injected_or_not_configured",
    "durable_backend": "adapter_contract_only",
}
FIXTURE_PATH = Path("tests/fixtures/stock_basic_sample.json")


@dataclass(frozen=True, slots=True)
class ProbeCheck:
    name: str
    status: str
    latency_ms: float
    error_type: str | None
    message: str | None
    non_goals: dict[str, str]
    details: dict[str, object]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "message": self.message,
            "non_goals": dict(self.non_goals),
            "details": dict(self.details),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run entity-registry production readiness evidence locally.",
    )
    parser.add_argument("--profile", default="production")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    summary = run_probe(profile=args.profile)
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{summary['probe']} "
            f"profile={summary['profile']} "
            f"status={summary['status']}"
        )
        for check in summary["checks"]:
            print(
                f"- {check['name']}: "
                f"{check['status']} ({check['latency_ms']:.3f} ms)"
            )
    return 0 if summary["status"] == "passed" else 1


def run_probe(*, profile: str) -> dict[str, object]:
    start = time.monotonic()
    checks = [
        _run_check(
            "strict_adapter_protocol_passes_gate",
            lambda: _strict_adapter_protocol_passes_gate(profile),
        ),
        _run_check(
            "production_rejects_in_memory_repositories",
            lambda: _production_rejects_in_memory_repositories(profile),
        ),
        _run_check(
            "split_audit_repository_fails_gate",
            lambda: _split_audit_repository_fails_gate(profile),
        ),
        _run_check(
            "missing_audit_repository_fails_gate",
            lambda: _missing_audit_repository_fails_gate(profile),
        ),
        _run_check(
            "deterministic_audit_write_failure_fails_closed",
            lambda: _deterministic_audit_write_failure_fails_closed(profile),
        ),
        _run_check(
            "unresolved_writes_reference_case_without_synthetic_id",
            lambda: _unresolved_writes_reference_case_without_synthetic_id(profile),
        ),
    ]
    failed = [check for check in checks if check.status != "passed"]
    duration_ms = (time.monotonic() - start) * 1000.0
    return {
        "probe": "entity-registry-production-readiness-gate",
        "profile": profile,
        "status": "failed" if failed else "passed",
        "metrics": {
            "runner_local": {
                "duration_ms": duration_ms,
                "total_checks": len(checks),
                "passed": len(checks) - len(failed),
                "failed": len(failed),
            },
        },
        "non_goals": dict(NON_GOALS),
        "checks": [check.to_json_dict() for check in checks],
    }


def _run_check(
    name: str,
    callback: Callable[[], dict[str, object]],
) -> ProbeCheck:
    start = time.monotonic()
    try:
        details = callback()
    except Exception as exc:
        return ProbeCheck(
            name=name,
            status="failed",
            latency_ms=(time.monotonic() - start) * 1000.0,
            error_type=type(exc).__name__,
            message=str(exc),
            non_goals=dict(NON_GOALS),
            details={},
        )
    return ProbeCheck(
        name=name,
        status="passed",
        latency_ms=(time.monotonic() - start) * 1000.0,
        error_type=None,
        message=None,
        non_goals=dict(NON_GOALS),
        details=details,
    )


def _strict_adapter_protocol_passes_gate(profile: str) -> dict[str, object]:
    fixture = _strict_fixture()
    runtime = _runtime(profile, fixture)
    readiness_checks = check_runtime_readiness(runtime)
    failures = [check for check in readiness_checks if check.status == "failed"]
    if failures:
        raise AssertionError("; ".join(check.message or check.name for check in failures))
    return {
        "readiness_checks": [
            check.to_json_dict()
            for check in readiness_checks
        ],
        "adapter": "strict_fake_durable_protocol",
    }


def _production_rejects_in_memory_repositories(profile: str) -> dict[str, object]:
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)
    runtime = EntityRegistryRuntimeConfig(
        profile=profile,
        entity_repo=InMemoryEntityRepository(),
        alias_repo=InMemoryAliasRepository(),
        reference_repo=reference_repo,
        case_repo=case_repo,
    )
    error = _expect_readiness_error(runtime)
    return {"observed_error_type": type(error).__name__, "message": str(error)}


def _split_audit_repository_fails_gate(profile: str) -> dict[str, object]:
    fixture = _strict_fixture()
    split_case_repo = StrictResolutionCaseRepository()
    runtime = _runtime(profile, fixture, case_repo=split_case_repo)
    error = _expect_readiness_error(runtime)
    return {"observed_error_type": type(error).__name__, "message": str(error)}


def _missing_audit_repository_fails_gate(profile: str) -> dict[str, object]:
    fixture = _strict_fixture()
    runtime = _runtime(profile, fixture, reference_repo=None)
    error = _expect_readiness_error(runtime)
    return {"observed_error_type": type(error).__name__, "message": str(error)}


def _deterministic_audit_write_failure_fails_closed(profile: str) -> dict[str, object]:
    fixture = _strict_fixture()
    failing_reference_repo = FailingResolutionAuditReferenceRepository(
        fixture.case_repo,
    )
    assert_runtime_readiness(
        _runtime(profile, fixture, reference_repo=failing_reference_repo),
    )
    try:
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=fixture.entity_repo,
            alias_repo=fixture.alias_repo,
            reference_repo=failing_reference_repo,
            case_repo=fixture.case_repo,
        )
    except RuntimeError as exc:
        if "simulated audit write failure" not in str(exc):
            raise
        return {
            "observed_error_type": type(exc).__name__,
            "references_written": len(failing_reference_repo.references),
            "cases_written": len(fixture.case_repo.cases),
        }
    raise AssertionError("resolution returned success after audit write failure")


def _unresolved_writes_reference_case_without_synthetic_id(
    profile: str,
) -> dict[str, object]:
    fixture = _strict_fixture()
    assert_runtime_readiness(_runtime(profile, fixture))
    result = resolve_mention_with_repositories(
        "不存在的公司",
        {"probe": "readiness"},
        entity_repo=fixture.entity_repo,
        alias_repo=fixture.alias_repo,
        reference_repo=fixture.reference_repo,
        case_repo=fixture.case_repo,
    )
    unresolved = fixture.reference_repo.find_unresolved()
    if result.resolved_entity_id is not None:
        raise AssertionError("unresolved result carried a resolved entity id")
    if len(unresolved) != 1:
        raise AssertionError("unresolved path did not write exactly one reference")
    cases = fixture.case_repo.find_by_reference(unresolved[0].reference_id)
    if len(cases) != 1:
        raise AssertionError("unresolved path did not write exactly one case")
    if (
        unresolved[0].resolved_entity_id is not None
        or cases[0].selected_entity_id is not None
    ):
        raise AssertionError("unresolved audit carried a synthetic entity id")
    return {
        "resolution_method": result.resolution_method.value,
        "resolved_entity_id": result.resolved_entity_id,
        "reference_id": unresolved[0].reference_id,
        "case_id": cases[0].case_id,
        "selected_entity_id": cases[0].selected_entity_id,
    }


def _expect_readiness_error(
    runtime: EntityRegistryRuntimeConfig,
) -> ProductionReadinessError:
    try:
        assert_runtime_readiness(runtime)
    except ProductionReadinessError as exc:
        return exc
    raise AssertionError("readiness gate unexpectedly passed")


def _runtime(
    profile: str,
    fixture: "StrictFixture",
    *,
    reference_repo: Any = ...,
    case_repo: Any = ...,
) -> EntityRegistryRuntimeConfig:
    return EntityRegistryRuntimeConfig(
        profile=profile,
        entity_repo=fixture.entity_repo,
        alias_repo=fixture.alias_repo,
        reference_repo=fixture.reference_repo if reference_repo is ... else reference_repo,
        case_repo=fixture.case_repo if case_repo is ... else case_repo,
    )


@dataclass(frozen=True, slots=True)
class StrictFixture:
    entity_repo: "StrictEntityRepository"
    alias_repo: "StrictAliasRepository"
    reference_repo: "StrictResolutionAuditReferenceRepository"
    case_repo: "StrictResolutionCaseRepository"


def _strict_fixture() -> StrictFixture:
    entity_repo = StrictEntityRepository()
    alias_repo = StrictAliasRepository()
    case_repo = StrictResolutionCaseRepository()
    reference_repo = StrictResolutionAuditReferenceRepository(case_repo)
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    if result.errors:
        raise AssertionError(result.errors)
    return StrictFixture(entity_repo, alias_repo, reference_repo, case_repo)


class StrictEntityRepository:
    """Runner-local fake durable adapter for protocol evidence only."""

    def __init__(self) -> None:
        self.entities: dict[str, CanonicalEntity] = {}

    def get(self, entity_id: str) -> CanonicalEntity | None:
        return self.entities.get(entity_id)

    def save(self, entity: CanonicalEntity) -> None:
        self.entities[entity.canonical_entity_id] = entity

    def save_if_absent(self, entity: CanonicalEntity) -> bool:
        if entity.canonical_entity_id in self.entities:
            return False
        self.entities[entity.canonical_entity_id] = entity
        return True

    def list_all(self) -> list[CanonicalEntity]:
        return list(self.entities.values())

    def exists(self, entity_id: str) -> bool:
        return entity_id in self.entities


class StrictAliasRepository:
    """Runner-local fake durable adapter for protocol evidence only."""

    def __init__(self) -> None:
        self.by_text: dict[str, list[EntityAlias]] = {}
        self.by_entity: dict[str, list[EntityAlias]] = {}
        self.semantic_keys: set[tuple[str, str, str]] = set()

    def find_by_text(self, alias_text: str) -> list[EntityAlias]:
        return list(self.by_text.get(alias_text, []))

    def find_by_entity(self, entity_id: str) -> list[EntityAlias]:
        return list(self.by_entity.get(entity_id, []))

    def list_all(self) -> list[EntityAlias]:
        return [
            alias
            for aliases in self.by_entity.values()
            for alias in aliases
        ]

    def save(self, alias: EntityAlias) -> None:
        self.save_if_absent(alias)

    def save_if_absent(self, alias: EntityAlias) -> bool:
        key = (alias.canonical_entity_id, alias.alias_text, alias.alias_type.value)
        if key in self.semantic_keys:
            return False
        self.semantic_keys.add(key)
        self.by_text.setdefault(alias.alias_text, []).append(alias)
        self.by_entity.setdefault(alias.canonical_entity_id, []).append(alias)
        return True

    def save_batch(self, aliases: list[EntityAlias]) -> None:
        self.save_batch_if_absent(aliases)

    def save_batch_if_absent(self, aliases: list[EntityAlias]) -> int:
        return sum(1 for alias in aliases if self.save_if_absent(alias))


class StrictResolutionCaseRepository:
    """Runner-local fake durable adapter for protocol evidence only."""

    def __init__(self) -> None:
        self.cases: dict[str, ResolutionCase] = {}

    def save(self, case: ResolutionCase) -> None:
        self.cases[case.case_id] = case

    def get(self, case_id: str) -> ResolutionCase | None:
        return self.cases.get(case_id)

    def find_by_reference(self, reference_id: str) -> list[ResolutionCase]:
        return [
            case
            for case in self.cases.values()
            if case.reference_id == reference_id
        ]


class StrictResolutionAuditReferenceRepository:
    """Runner-local fake durable adapter for protocol evidence only."""

    def __init__(self, case_repo: StrictResolutionCaseRepository) -> None:
        self.references: dict[str, EntityReference] = {}
        self._case_repo = case_repo

    def save(self, ref: EntityReference) -> None:
        self.references[ref.reference_id] = ref

    def delete(self, reference_id: str) -> None:
        self.references.pop(reference_id, None)

    def get(self, reference_id: str) -> EntityReference | None:
        return self.references.get(reference_id)

    def find_unresolved(self) -> list[EntityReference]:
        return [
            reference
            for reference in self.references.values()
            if reference.resolved_entity_id is None
        ]

    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        if case.reference_id != reference.reference_id:
            raise ValueError("case reference_id must match reference")
        self.references[reference.reference_id] = reference
        self._case_repo.save(case)

    def owns_resolution_case_repository(
        self,
        case_repo: StrictResolutionCaseRepository,
    ) -> bool:
        return case_repo is self._case_repo


class FailingResolutionAuditReferenceRepository(
    StrictResolutionAuditReferenceRepository
):
    def save_resolution(
        self,
        reference: EntityReference,
        case: ResolutionCase,
    ) -> None:
        raise RuntimeError("simulated audit write failure")


if __name__ == "__main__":
    raise SystemExit(main())
