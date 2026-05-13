import pytest

from entity_registry.readiness import (
    EntityRegistryRuntimeConfig,
    ProductionReadinessError,
    assert_runtime_readiness,
)
from entity_registry.resolution import resolve_mention_with_repositories
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)
from scripts.entity_registry_readiness_probe import (
    FailingResolutionAuditReferenceRepository,
    StrictResolutionCaseRepository,
    _runtime,
    _strict_fixture,
    run_probe,
)


def test_production_readiness_rejects_in_memory_repositories() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(ProductionReadinessError, match="in-memory repositories"):
        assert_runtime_readiness(
            EntityRegistryRuntimeConfig(
                profile="production",
                entity_repo=InMemoryEntityRepository(),
                alias_repo=InMemoryAliasRepository(),
                reference_repo=reference_repo,
                case_repo=case_repo,
            )
        )


def test_production_readiness_rejects_in_memory_even_with_allow_flag() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(ProductionReadinessError, match="in-memory repositories"):
        assert_runtime_readiness(
            EntityRegistryRuntimeConfig(
                profile="production",
                allow_in_memory_repositories=True,
                entity_repo=InMemoryEntityRepository(),
                alias_repo=InMemoryAliasRepository(),
                reference_repo=reference_repo,
                case_repo=case_repo,
            )
        )


def test_local_readiness_allows_in_memory_only_with_explicit_allow_flag() -> None:
    case_repo = InMemoryResolutionCaseRepository()
    reference_repo = InMemoryResolutionAuditReferenceRepository(case_repo)

    with pytest.raises(ProductionReadinessError, match="in-memory repositories"):
        assert_runtime_readiness(
            EntityRegistryRuntimeConfig(
                profile="local",
                entity_repo=InMemoryEntityRepository(),
                alias_repo=InMemoryAliasRepository(),
                reference_repo=reference_repo,
                case_repo=case_repo,
            )
        )

    assert_runtime_readiness(
        EntityRegistryRuntimeConfig(
            profile="local",
            allow_in_memory_repositories=True,
            entity_repo=InMemoryEntityRepository(),
            alias_repo=InMemoryAliasRepository(),
            reference_repo=reference_repo,
            case_repo=case_repo,
        )
    )


def test_production_readiness_rejects_split_audit_repository() -> None:
    fixture = _strict_fixture()

    with pytest.raises(ProductionReadinessError, match="does not own"):
        assert_runtime_readiness(
            _runtime(
                "production",
                fixture,
                case_repo=StrictResolutionCaseRepository(),
            )
        )


def test_production_readiness_rejects_missing_audit_repository() -> None:
    fixture = _strict_fixture()

    with pytest.raises(ProductionReadinessError, match="reference_repo and case_repo"):
        assert_runtime_readiness(
            _runtime("production", fixture, reference_repo=None)
        )


def test_deterministic_audit_write_failure_does_not_return_success() -> None:
    fixture = _strict_fixture()
    reference_repo = FailingResolutionAuditReferenceRepository(fixture.case_repo)
    assert_runtime_readiness(
        _runtime("production", fixture, reference_repo=reference_repo)
    )

    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        resolve_mention_with_repositories(
            "贵州茅台",
            None,
            entity_repo=fixture.entity_repo,
            alias_repo=fixture.alias_repo,
            reference_repo=reference_repo,
            case_repo=fixture.case_repo,
        )

    assert reference_repo.references == {}
    assert fixture.case_repo.cases == {}


def test_unresolved_writes_reference_case_and_no_synthetic_entity_id() -> None:
    fixture = _strict_fixture()
    assert_runtime_readiness(_runtime("production", fixture))

    result = resolve_mention_with_repositories(
        "不存在的公司",
        None,
        entity_repo=fixture.entity_repo,
        alias_repo=fixture.alias_repo,
        reference_repo=fixture.reference_repo,
        case_repo=fixture.case_repo,
    )

    unresolved = fixture.reference_repo.find_unresolved()
    assert result.resolved_entity_id is None
    assert len(unresolved) == 1
    assert unresolved[0].resolved_entity_id is None
    cases = fixture.case_repo.find_by_reference(unresolved[0].reference_id)
    assert len(cases) == 1
    assert cases[0].selected_entity_id is None


def test_readiness_probe_reports_runner_local_metrics_and_non_goals() -> None:
    summary = run_probe(profile="production")

    assert summary["status"] == "passed"
    assert summary["metrics"]["runner_local"]["total_checks"] == 6
    assert summary["non_goals"] == {
        "splink_backend": "not_proven",
        "reasoner_runtime": "injected_or_not_configured",
        "durable_backend": "adapter_contract_only",
    }
    for check in summary["checks"]:
        assert set(check) >= {
            "latency_ms",
            "status",
            "error_type",
            "non_goals",
        }
