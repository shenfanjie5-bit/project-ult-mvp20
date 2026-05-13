import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import entity_registry
import entity_registry.contracts as registry_contracts
import contracts.schemas as contract_schemas
import pytest
from contracts.core import __version__ as contracts_package_version

from entity_registry.core import (
    AliasType,
    CanonicalEntity as RuntimeCanonicalEntity,
    DecisionType,
    EntityAlias as RuntimeEntityAlias,
    EntityStatus,
    EntityType,
    ResolutionMethod,
)
from entity_registry.init import (
    FileStockBasicSnapshotReader,
    initialize_from_stock_basic_into,
)
from entity_registry.references import (
    EntityReference as RuntimeEntityReference,
    ResolutionCase as RuntimeResolutionCase,
)
from entity_registry.resolution_types import MentionResolutionResult
from entity_registry.storage import (
    InMemoryAliasRepository,
    InMemoryEntityRepository,
    InMemoryResolutionAuditReferenceRepository,
    InMemoryResolutionCaseRepository,
)


NOW = datetime(2026, 4, 15, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "stock_basic_sample.json"
CONTRACTS_LOWER_BOUND_SMOKE_ENV = "ENTITY_REGISTRY_CONTRACTS_LOWER_BOUND_SMOKE"
CONTRACTS_PACKAGE_NAME = "project-ult-contracts"
CONTRACTS_RELEASE_WITH_RULE_VERSION = "0.1.3"
# CI's contracts-oldest-published-tag-smoke job installs the OLDEST COMPATIBLE
# git tag (currently v0.1.3). The DECLARED floor in pyproject is `>=0.1.3`.
# Keep this constant in sync with the workflow's pinned tag —
# both are validated by `test_ci_pins_contracts_oldest_published_tag_smoke_to_pinned_release`.
CONTRACTS_OLDEST_PUBLISHED_TAG = "0.1.3"


@pytest.fixture(autouse=True)
def reset_public_repositories() -> Iterator[None]:
    entity_registry.reset_default_repositories()
    yield
    entity_registry.reset_default_repositories()


def test_installed_contracts_dependency_exports_canonical_id_rule_version(
    tmp_path: Path,
) -> None:
    _run_contracts_import_smoke(
        tmp_path,
        minimum_version=_declared_contracts_lower_bound(),
    )


def test_declared_contracts_lower_bound_install_smoke(
    tmp_path: Path,
) -> None:
    """CI smoke job installs the oldest compatible contracts git tag and
    runs this test with the env var set. The job (renamed from
    `contracts-lower-bound-smoke` to `contracts-oldest-published-tag-smoke`,
    see ci.yml comment) pins `@v0.1.3`. This test therefore asserts:

    1. installed contracts == CONTRACTS_OLDEST_PUBLISHED_TAG (the actually
       pinned tag — keeps the test honest if the workflow's pin drifts);
    2. installed version still meets the pyproject declared floor
       `>=0.1.3` (so we never accidentally pin BELOW the declared minimum);
    3. CANONICAL_ID_RULE_VERSION is exported (the original purpose).

    Test name is preserved for CI workflow `-k` selector compatibility.
    """
    if os.environ.get(CONTRACTS_LOWER_BOUND_SMOKE_ENV) != "1":
        pytest.skip(
            f"set {CONTRACTS_LOWER_BOUND_SMOKE_ENV}=1 after installing "
            "the contracts oldest-published-tag exactly"
        )

    declared_floor = _declared_contracts_lower_bound()
    assert _version_tuple(CONTRACTS_OLDEST_PUBLISHED_TAG) >= _version_tuple(
        declared_floor
    ), (
        f"CONTRACTS_OLDEST_PUBLISHED_TAG ({CONTRACTS_OLDEST_PUBLISHED_TAG}) is "
        f"BELOW the declared pyproject floor ({declared_floor}); the smoke "
        "lane would silently certify a too-old release. Bump the constant or "
        "fix pyproject."
    )

    _run_contracts_import_smoke(
        tmp_path,
        exact_version=CONTRACTS_OLDEST_PUBLISHED_TAG,
    )


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise AssertionError(f"unsupported version string: {value!r}")
    return tuple(int(part) for part in match.groups())


def test_ci_pins_contracts_oldest_published_tag_smoke_to_pinned_release() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    # Iron rule #6: CI cross-repo git+URL must pin a release tag, never @main.
    # contracts is not published to PyPI; the smoke job installs the OLDEST
    # compatible git tag of project-ult-contracts (currently v0.1.3).

    # Find EVERY `contracts.git@<ref>` occurrence in the workflow (across all
    # jobs / lanes) so a future job can't silently regress to @main without
    # this test catching it. Match the whole ref token until whitespace or a
    # closing quote — covers both `"git+...contracts.git@v0.1.3"` quoted and
    # bare `git+...contracts.git@v0.1.3` forms.
    pin_pattern = re.compile(
        r"project-ult-contracts\.git@(?P<ref>[^\s\"']+)"
    )
    matches = pin_pattern.findall(workflow)
    assert matches, (
        "no `project-ult-contracts.git@<ref>` pins found in ci.yml; either "
        "ci.yml stopped installing contracts at all, or this regex needs a "
        "follow-up to match the new install style."
    )

    bad_pins = [
        ref
        for ref in matches
        # Branch refs (anything that isn't a vMAJOR.MINOR.PATCH or full SHA)
        # would constitute a rule #6 violation. Today the only forbidden
        # ref we've actually seen drift to is `main`, but be a bit broader:
        # anything that doesn't look like a release tag (`v\d+\.\d+\.\d+`)
        # or a 40-char SHA also fails.
        if not re.fullmatch(r"v\d+\.\d+\.\d+|[0-9a-f]{40}", ref)
    ]
    assert not bad_pins, (
        f"iron rule #6 violation: contracts git+URL pin(s) not on a "
        f"release tag / full SHA: {bad_pins}; all {len(matches)} pin(s) "
        f"in ci.yml were: {matches}"
    )

    # Spot-check the specific pin we expect today; if v0.1.3 is rolled, this
    # assertion plus CONTRACTS_OLDEST_PUBLISHED_TAG must move together.
    assert all(ref == f"v{CONTRACTS_OLDEST_PUBLISHED_TAG}" for ref in matches), (
        f"expected every contracts pin to be v{CONTRACTS_OLDEST_PUBLISHED_TAG} "
        f"(matching CONTRACTS_OLDEST_PUBLISHED_TAG); got {matches}"
    )

    assert "contracts-oldest-published-tag-smoke" in workflow
    assert CONTRACTS_LOWER_BOUND_SMOKE_ENV in workflow
    assert "test_declared_contracts_lower_bound_install_smoke" in workflow


def test_project_requires_contracts_release_with_rule_version_export() -> None:
    assert _declared_contracts_lower_bound() == CONTRACTS_RELEASE_WITH_RULE_VERSION


def _declared_contracts_lower_bound() -> str:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]
    dependency_prefix = f"{CONTRACTS_PACKAGE_NAME}>="

    for dependency in dependencies:
        if dependency.startswith(dependency_prefix):
            return dependency.removeprefix(dependency_prefix)

    raise AssertionError(f"{dependency_prefix}<version> dependency is required")


def _run_contracts_import_smoke(
    tmp_path: Path,
    *,
    exact_version: str | None = None,
    minimum_version: str | None = None,
) -> None:
    if (exact_version is None) == (minimum_version is None):
        raise ValueError("set exactly one of exact_version or minimum_version")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["ENTITY_REGISTRY_CONTRACTS_SRC"] = str(
        (PROJECT_ROOT.parent / "contracts" / "src").resolve()
    )
    script = f"""
import importlib.metadata
import os
import re

import contracts.schemas as contract_schemas
import entity_registry.contracts as registry_contracts

def version_tuple(value):
    match = re.match(r"^(\\d+)\\.(\\d+)\\.(\\d+)", value)
    if match is None:
        raise AssertionError(f"unsupported contracts version: {{value}}")
    return tuple(int(part) for part in match.groups())

exact_version = {exact_version!r}
minimum_version = {minimum_version!r}
installed_version = importlib.metadata.version({CONTRACTS_PACKAGE_NAME!r})
if exact_version is not None:
    assert installed_version == exact_version
if minimum_version is not None:
    assert version_tuple(installed_version) >= version_tuple(minimum_version)
assert isinstance(contract_schemas.CANONICAL_ID_RULE_VERSION, str)
assert contract_schemas.CANONICAL_ID_RULE_VERSION
assert (
    registry_contracts.CANONICAL_ID_RULE_VERSION
    == contract_schemas.CANONICAL_ID_RULE_VERSION
)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_entity_registry_reexports_contract_entity_schemas() -> None:
    assert registry_contracts.CanonicalEntity is contract_schemas.CanonicalEntity
    assert registry_contracts.EntityAlias is contract_schemas.EntityAlias
    assert registry_contracts.EntityReference is contract_schemas.EntityReference
    assert registry_contracts.ResolutionCase is contract_schemas.ResolutionCase

    assert entity_registry.CanonicalEntity is contract_schemas.CanonicalEntity
    assert entity_registry.EntityAlias is contract_schemas.EntityAlias
    assert entity_registry.EntityReference is contract_schemas.EntityReference
    assert entity_registry.ResolutionCase is contract_schemas.ResolutionCase
    assert entity_registry.ContractCanonicalEntity is contract_schemas.CanonicalEntity
    assert entity_registry.ContractEntityAlias is contract_schemas.EntityAlias
    assert entity_registry.ContractEntityReference is contract_schemas.EntityReference
    assert entity_registry.ContractResolutionCase is contract_schemas.ResolutionCase
    assert not hasattr(entity_registry, "CanonicalEntityProfile")
    assert not hasattr(entity_registry, "MentionResolutionResult")


def test_import_order_does_not_patch_contracts_resolution_case() -> None:
    script = """
from contracts.schemas.entities import ResolutionCase as OriginalResolutionCase
import contracts.schemas as contract_schemas
import entity_registry
from contracts.schemas.entities import ResolutionCase as AfterResolutionCase
from entity_registry.storage import InMemoryAliasRepository, InMemoryEntityRepository

assert AfterResolutionCase is OriginalResolutionCase
assert contract_schemas.ResolutionCase is OriginalResolutionCase
assert entity_registry.ResolutionCase is OriginalResolutionCase

entity_registry.configure_default_in_memory_audit_repositories(
    InMemoryEntityRepository(),
    InMemoryAliasRepository(),
)
case = entity_registry.resolve_mention(
    "不存在公司",
    {"source": "import-order-regression"},
)
payload = case.model_dump(mode="json")
assert payload["candidate_entities"] == []
OriginalResolutionCase.model_validate(payload)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str((PROJECT_ROOT.parent / "contracts" / "src").resolve()),
            str((PROJECT_ROOT / "src").resolve()),
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_root_public_api_payloads_validate_against_contract_schemas() -> None:
    entity_repo = InMemoryEntityRepository()
    alias_repo = InMemoryAliasRepository()
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo,
        alias_repo,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert result.errors == []
    entity_registry.configure_default_in_memory_audit_repositories(
        entity_repo,
        alias_repo,
    )

    alias_hit = entity_registry.lookup_alias("贵州茅台")
    assert alias_hit is not None
    contract_schemas.CanonicalEntity.model_validate(
        alias_hit.model_dump(mode="json"),
    )

    resolution_case = entity_registry.resolve_mention(
        "贵州茅台",
        {"source": "contract-boundary-test"},
    )
    contract_schemas.ResolutionCase.model_validate(
        resolution_case.model_dump(mode="json"),
    )

    batch_cases = entity_registry.batch_resolve(["平安银行", "不存在公司"])
    assert len(batch_cases) == 2
    for batch_case in batch_cases:
        contract_schemas.ResolutionCase.model_validate(
            batch_case.model_dump(mode="json"),
        )

    unresolved_case = entity_registry.register_unresolved_reference(
        {
            "reference_id": "ref-contract-boundary",
            "raw_mention_text": "Unknown Corp",
            "source_context": {"source": "contract-boundary-test"},
        }
    )
    contract_schemas.ResolutionCase.model_validate(
        unresolved_case.model_dump(mode="json"),
    )

    profile = entity_registry.get_entity_profile("ENT_STOCK_000001.SZ")
    contract_schemas.CanonicalEntity.model_validate(
        profile["canonical_entity"].model_dump(mode="json"),
    )
    for alias in profile["aliases"]:
        contract_schemas.EntityAlias.model_validate(alias.model_dump(mode="json"))


def test_root_batch_resolve_uses_one_repository_context_for_audit_conversion() -> None:
    entity_repo_a = InMemoryEntityRepository()
    alias_repo_a = InMemoryAliasRepository()
    result = initialize_from_stock_basic_into(
        str(FIXTURE_PATH),
        entity_repo_a,
        alias_repo_a,
        stock_basic_reader=FileStockBasicSnapshotReader(),
    )
    assert result.errors == []

    entity_repo_b = InMemoryEntityRepository()
    alias_repo_b = InMemoryAliasRepository()
    case_repo_a = InMemoryResolutionCaseRepository()
    case_repo_b = InMemoryResolutionCaseRepository()
    reference_repo_b = InMemoryResolutionAuditReferenceRepository(case_repo_b)
    reconfigured = False

    def switch_to_context_b() -> None:
        nonlocal reconfigured
        if reconfigured:
            return
        reconfigured = True
        entity_registry.configure_default_repositories(
            entity_repo_b,
            alias_repo_b,
            reference_repo=reference_repo_b,
            case_repo=case_repo_b,
        )

    reference_repo_a = ReconfiguringAuditReferenceRepository(
        case_repo_a,
        switch_to_context_b,
    )
    entity_registry.configure_default_repositories(
        entity_repo_a,
        alias_repo_a,
        reference_repo=reference_repo_a,
        case_repo=case_repo_a,
    )

    batch_cases = entity_registry.batch_resolve(
        [
            {
                "reference_id": "ref-root-batch-context-race",
                "raw_mention_text": "平安银行",
            }
        ]
    )

    assert reconfigured is True
    default_entity_repo, default_alias_repo = entity_registry.get_default_repositories()
    assert default_entity_repo is entity_repo_b
    assert default_alias_repo is alias_repo_b
    assert case_repo_b.find_by_reference("ref-root-batch-context-race") == []

    persisted_cases = case_repo_a.find_by_reference("ref-root-batch-context-race")
    assert len(persisted_cases) == 1
    assert batch_cases[0].resolution_case_id == persisted_cases[0].case_id
    assert batch_cases[0].resolved_entity is not None
    assert batch_cases[0].resolved_entity.entity_id == "ENT_STOCK_000001.SZ"
    contract_schemas.ResolutionCase.model_validate(
        batch_cases[0].model_dump(mode="json"),
    )


def test_canonical_id_rule_version_tracks_entity_id_rule_not_package_release() -> None:
    entity = make_entity()
    alias = make_alias()
    reference = make_reference()
    case = make_case()
    rule_version = registry_contracts.CANONICAL_ID_RULE_VERSION

    assert entity_registry.CANONICAL_ID_RULE_VERSION == rule_version
    assert rule_version != contracts_package_version
    assert entity.canonical_id_rule_version == rule_version
    assert alias.canonical_id_rule_version == rule_version
    assert reference.canonical_id_rule_version == rule_version
    assert case.canonical_id_rule_version == rule_version


def test_internal_canonical_entity_projects_to_contract_schema() -> None:
    entity = make_entity()
    rule_version = registry_contracts.CANONICAL_ID_RULE_VERSION

    contract_entity = registry_contracts.to_contract_canonical_entity(entity)

    assert isinstance(contract_entity, contract_schemas.CanonicalEntity)
    assert contract_entity.model_dump(mode="json") == {
        "canonical_entity_id": "ENT_STOCK_300750.SZ",
        "entity_type": "stock",
        "display_name": "CATL",
        "canonical_id_rule_version": rule_version,
        "created_at": "2026-04-15T00:00:00Z",
        "attributes": {
            "status": "active",
            "anchor_code": "300750.SZ",
            "cross_listing_group": "CATL",
            "updated_at": "2026-04-15T00:00:00Z",
        },
    }


def test_internal_entity_alias_projects_to_contract_schema() -> None:
    alias = make_alias()
    rule_version = registry_contracts.CANONICAL_ID_RULE_VERSION

    contract_alias = registry_contracts.to_contract_entity_alias(alias)

    assert isinstance(contract_alias, contract_schemas.EntityAlias)
    assert contract_alias.canonical_entity_id == "ENT_STOCK_300750.SZ"
    assert contract_alias.alias == "CATL"
    assert contract_alias.alias_type == "short_name"
    assert contract_alias.source_reference == {
        "source": "unit-test",
        "is_primary": True,
    }
    assert contract_alias.canonical_id_rule_version == rule_version


def test_internal_entity_projects_to_contract_entity_reference() -> None:
    entity = make_entity()
    rule_version = registry_contracts.CANONICAL_ID_RULE_VERSION

    contract_reference = registry_contracts.to_contract_entity_reference(entity)

    assert isinstance(contract_reference, contract_schemas.EntityReference)
    assert contract_reference.model_dump(mode="json") == {
        "entity_id": "ENT_STOCK_300750.SZ",
        "entity_type": "stock",
        "canonical_id_rule_version": rule_version,
        "display_name": "CATL",
    }


def test_internal_resolution_case_projects_to_contract_schema() -> None:
    entity = make_entity()
    case = make_case()

    contract_case = registry_contracts.to_contract_resolution_case(
        case,
        input_alias="CATL",
        candidate_entities=[entity],
        decision=contract_schemas.EntityResolutionDecision.MATCHED,
    )

    assert isinstance(contract_case, contract_schemas.ResolutionCase)
    assert contract_case.resolution_case_id == "case-1"
    assert contract_case.input_alias == "CATL"
    assert contract_case.decision is contract_schemas.EntityResolutionDecision.MATCHED
    assert contract_case.confidence == 1.0
    assert contract_case.candidate_entities == [
        registry_contracts.to_contract_entity_reference(entity)
    ]
    assert contract_case.resolved_entity == registry_contracts.to_contract_entity_reference(
        entity
    )
    assert (
        contract_case.canonical_id_rule_version
        == registry_contracts.CANONICAL_ID_RULE_VERSION
    )


@pytest.mark.parametrize(
    "rationale",
    [
        "reasoner declined: both listings remain plausible",
        "reasoner disambiguation failed: timed out",
        "reasoner confidence below threshold 0.70: weak context",
    ],
)
def test_llm_unresolved_multi_candidate_cases_project_as_unresolved(
    rationale: str,
) -> None:
    candidate_entities = [make_hk_entity(), make_entity()]
    case = RuntimeResolutionCase(
        case_id="case-llm-unresolved",
        reference_id="ref-llm-unresolved",
        candidate_entity_ids=[
            "ENT_STOCK_03750.HK",
            "ENT_STOCK_300750.SZ",
        ],
        selected_entity_id=None,
        decision_type=DecisionType.LLM_ASSISTED,
        decision_rationale=rationale,
        created_at=NOW,
    )

    contract_case = registry_contracts.to_contract_resolution_case(
        case,
        input_alias="宁德时代新能源",
        candidate_entities=candidate_entities,
        decision=contract_schemas.EntityResolutionDecision.UNRESOLVED,
    )

    assert contract_case.decision is contract_schemas.EntityResolutionDecision.UNRESOLVED
    assert contract_case.resolved_entity is None
    assert contract_case.confidence == 0.0
    assert contract_case.candidate_entities == [
        registry_contracts.to_contract_entity_reference(candidate)
        for candidate in candidate_entities
    ]


def test_no_candidate_unresolved_case_projects_to_contract_schema() -> None:
    case = RuntimeResolutionCase(
        case_id="case-no-candidate",
        reference_id="ref-no-candidate",
        candidate_entity_ids=[],
        selected_entity_id=None,
        decision_type=DecisionType.AUTO,
        decision_rationale="no candidates found",
        created_at=NOW,
    )

    contract_case = registry_contracts.to_contract_resolution_case(
        case,
        input_alias="不存在公司",
        candidate_entities=[],
        decision=contract_schemas.EntityResolutionDecision.UNRESOLVED,
    )

    assert contract_case.decision is contract_schemas.EntityResolutionDecision.UNRESOLVED
    assert contract_case.resolved_entity is None
    assert contract_case.candidate_entities == []

    dumped = contract_case.model_dump(mode="json")
    assert dumped["candidate_entities"] == []
    assert "ENT_UNRESOLVED_NO_CANDIDATE" not in str(dumped)

    reparsed = contract_schemas.ResolutionCase.model_validate(dumped)
    assert reparsed.candidate_entities == []
    assert reparsed.resolved_entity is None


def test_mention_resolution_result_uses_stable_contract_shape() -> None:
    result = MentionResolutionResult(
        raw_mention_text="贵州茅台",
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )

    assert result.model_dump(mode="json") == {
        "raw_mention_text": "贵州茅台",
        "resolved_entity_id": "ENT_STOCK_600519.SH",
        "resolution_method": "deterministic",
        "resolution_confidence": 1.0,
    }


def test_mention_resolution_result_preserves_raw_mention_whitespace() -> None:
    result = MentionResolutionResult(
        raw_mention_text="  贵州茅台  ",
        resolved_entity_id="ENT_STOCK_600519.SH",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
    )

    assert result.raw_mention_text == "  贵州茅台  "


def make_entity() -> RuntimeCanonicalEntity:
    return RuntimeCanonicalEntity(
        canonical_entity_id="ENT_STOCK_300750.SZ",
        entity_type=EntityType.STOCK,
        display_name="CATL",
        status=EntityStatus.ACTIVE,
        anchor_code="300750.SZ",
        cross_listing_group="CATL",
        created_at=NOW,
        updated_at=NOW,
    )


def make_hk_entity() -> RuntimeCanonicalEntity:
    return RuntimeCanonicalEntity(
        canonical_entity_id="ENT_STOCK_03750.HK",
        entity_type=EntityType.STOCK,
        display_name="宁德时代",
        status=EntityStatus.ACTIVE,
        anchor_code="03750.HK",
        cross_listing_group="CATL",
        created_at=NOW,
        updated_at=NOW,
    )


def make_alias() -> RuntimeEntityAlias:
    return RuntimeEntityAlias(
        canonical_entity_id="ENT_STOCK_300750.SZ",
        alias_text="CATL",
        alias_type=AliasType.SHORT_NAME,
        confidence=1.0,
        source="unit-test",
        is_primary=True,
        created_at=NOW,
    )


def make_reference() -> RuntimeEntityReference:
    return RuntimeEntityReference(
        reference_id="ref-1",
        raw_mention_text="CATL",
        source_context={"source": "unit-test"},
        resolved_entity_id="ENT_STOCK_300750.SZ",
        resolution_method=ResolutionMethod.DETERMINISTIC,
        resolution_confidence=1.0,
        created_at=NOW,
    )


def make_case() -> RuntimeResolutionCase:
    return RuntimeResolutionCase(
        case_id="case-1",
        reference_id="ref-1",
        candidate_entity_ids=["ENT_STOCK_300750.SZ"],
        selected_entity_id="ENT_STOCK_300750.SZ",
        decision_type=DecisionType.AUTO,
        decision_rationale="unique deterministic match",
        created_at=NOW,
    )


class ReconfiguringAuditReferenceRepository(InMemoryResolutionAuditReferenceRepository):
    def __init__(
        self,
        case_repo: InMemoryResolutionCaseRepository,
        callback: Callable[[], None],
    ) -> None:
        super().__init__(case_repo)
        self._callback = callback

    def save_resolution(
        self,
        reference: RuntimeEntityReference,
        case: RuntimeResolutionCase,
    ) -> None:
        super().save_resolution(reference, case)
        self._callback()
