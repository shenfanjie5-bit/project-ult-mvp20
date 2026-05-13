"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``entity-registry`` heavy-uses
``event_cases`` for fuzzy alias / unresolved / A+H boundaries.

This module:

1. Walks every ``event_cases`` case and validates fixture metadata.
2. **Really exercises a runtime function**: drives
   ``entity_registry.aliases.lookup_alias_in_repositories`` (a
   repository-injectable variant that doesn't need configured-default
   repos) using the fixture's ``alias_table_snapshot``; asserts the
   produced ``CanonicalEntity`` for ``case_fuzzy_alias_simple`` matches
   the fixture's expected resolved_entity_id (iron rule #5 + sub-rule).

**Hard-import on purpose** (iron rule #1).

Install path: ``pip install -e ".[dev,shared-fixtures]"``.
"""

from __future__ import annotations

# Hard import — fail collection if shared-fixtures extra not installed.
from audit_eval_fixtures import (  # noqa: F401
    Case,
    CaseRef,
    iter_cases,
    list_packs,
    load_case,
)

# Hard-import the runtime aliases function we exercise.
from entity_registry.aliases import lookup_alias_in_repositories  # noqa: F401


class TestSharedFixturesAreReachable:
    def test_event_cases_pack_present(self) -> None:
        assert "event_cases" in list_packs()


class TestEventCaseMetadataIsContractCompatible:
    REQUIRED_METADATA_KEYS = {
        "fixture_id", "source_module", "contract_version",
        "fixture_kind", "golden_updated_at",
    }

    def test_every_case_metadata_has_required_keys(self) -> None:
        for ref in iter_cases("event_cases"):
            case = load_case(ref.pack_name, ref.case_id)
            missing = self.REQUIRED_METADATA_KEYS - set(case.metadata.keys())
            assert not missing, (
                f"{ref.case_id} missing metadata keys: {missing}"
            )


class TestRuntimeAliasResolutionAgainstFixture:
    """**Real-runtime regression** (iron rule #5).

    For ``case_fuzzy_alias_simple``: the fixture provides an alias
    table containing "宁德" → ENT_STOCK_300750.SZ; the expected
    resolved_entity_id is ENT_STOCK_300750.SZ. We instantiate an
    in-memory entity + alias repository from the fixture's
    ``alias_table_snapshot``, call the runtime
    ``lookup_alias_in_repositories``, and assert the resolved entity's
    canonical_entity_id matches the fixture's expected value.
    """

    def test_case_fuzzy_alias_simple_resolves_to_expected_entity(self) -> None:
        from datetime import UTC, datetime

        from entity_registry.core import (
            AliasType,
            CanonicalEntity,
            EntityAlias,
            EntityStatus,
            EntityType,
        )
        from entity_registry.storage import (
            InMemoryAliasRepository,
            InMemoryEntityRepository,
        )

        case = load_case("event_cases", "case_fuzzy_alias_simple")
        expected_id = case.expected["resolved_entity_id"]

        # Build an in-memory entity + alias state from the fixture.
        entity_repo = InMemoryEntityRepository()
        alias_repo = InMemoryAliasRepository()

        # The fixture's alias_table_snapshot lists multiple aliases
        # for ENT_STOCK_300750.SZ; we need at least one entity record.
        catl = CanonicalEntity(
            canonical_entity_id=expected_id,
            entity_type=EntityType.STOCK,
            display_name="宁德时代",
            status=EntityStatus.ACTIVE,
            anchor_code="300750.SZ",
            cross_listing_group=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        entity_repo.save(catl)

        alias_type_map = {
            "full_name": AliasType.FULL_NAME,
            "short_name": AliasType.SHORT_NAME,
            "english": AliasType.ENGLISH,
            "former_name": AliasType.FORMER_NAME,
            "code": AliasType.CODE,
            "cnspell": AliasType.CNSPELL,
        }
        for alias_record in case.context["alias_table_snapshot"]:
            alias_repo.save(
                EntityAlias(
                    canonical_entity_id=alias_record["canonical_entity_id"],
                    alias_text=alias_record["alias_text"],
                    alias_type=alias_type_map[alias_record["alias_type"]],
                    is_primary=alias_record.get("is_primary", False),
                    confidence=alias_record["confidence"],
                    source="regression-test",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        # Run the runtime alias lookup (positional args: alias_text,
        # alias_repo, entity_repo per aliases.py:78 signature).
        raw_mention = case.input["raw_mention_text"]  # "宁德"
        resolved = lookup_alias_in_repositories(
            raw_mention,
            alias_repo,
            entity_repo,
        )

        # Business expectation: the runtime resolves "宁德" to the
        # expected ENT_* canonical id (sub-rule: keyed to fixture's
        # specific business outcome, not generic invariant).
        assert resolved is not None, (
            f"lookup_alias_in_repositories returned None for {raw_mention!r}"
        )
        assert resolved.canonical_entity_id == expected_id, (
            f"resolved id {resolved.canonical_entity_id!r} != "
            f"fixture expected {expected_id!r}"
        )
        # ENT_* canonical id rule (CLAUDE.md): must start with ENT_.
        assert resolved.canonical_entity_id.startswith("ENT_"), (
            f"canonical_entity_id violates ENT_* rule: {resolved.canonical_entity_id!r}"
        )


class TestRuntimeNamechangeRegressionAgainstFixture:
    """**Real-runtime regression for the tushare-derived namechange case**
    (codex review #1 P2 follow-up).

    Phase B added ``event_cases/case_tushare_namechange_alias`` (in
    audit-eval v0.2.3) cut from a real ``300209.SZ`` namechange event
    (有棵树 → 行云科技, ann_date 2026-02-13). The earlier follow-up only
    asserted the case loadable from the audit-eval side; this class
    closes the gap on the entity-registry side by **really exercising**
    the runtime alias-lookup path against the case's mention samples
    and asserting they all resolve to the case's
    expected_canonical_entity_id.

    The test also pins the canonical_entity_id format contract end to
    end: the case's expected id MUST equal
    ``generate_stock_entity_id(ts_code)`` so the two sides cannot drift
    apart again. If the audit-eval case ever regresses to the older
    underscore-only ``ENT_STOCK_*_<exchange>`` format, this test fails
    loudly.
    """

    def test_case_tushare_namechange_alias_resolves_three_mentions(
        self,
    ) -> None:
        from datetime import UTC, datetime

        from entity_registry.aliases import lookup_alias_in_repositories
        from entity_registry.core import (
            AliasType,
            CanonicalEntity,
            EntityAlias,
            EntityStatus,
            EntityType,
            generate_stock_entity_id,
        )
        from entity_registry.storage import (
            InMemoryAliasRepository,
            InMemoryEntityRepository,
        )

        case = load_case("event_cases", "case_tushare_namechange_alias")

        # Cross-side format contract — the fixture's expected id MUST
        # be the runtime-generated id for its ts_code (codex review #1
        # P2 strict regression).
        ts_code = case.input["namechange_event"]["ts_code"]
        runtime_id = generate_stock_entity_id(ts_code)
        expected_id = case.expected["expected_canonical_entity_id"]
        assert expected_id == runtime_id, (
            f"case.expected.expected_canonical_entity_id {expected_id!r} "
            f"diverged from runtime generate_stock_entity_id({ts_code!r}) "
            f"= {runtime_id!r}; the audit-eval case has drifted from the "
            f"live entity-registry runtime rule"
        )

        # Build in-memory state representing post-namechange registry:
        # one canonical entity + 3 aliases (former_name + full_name + code)
        # so the alias-lookup runtime can resolve every mention.
        entity_repo = InMemoryEntityRepository()
        alias_repo = InMemoryAliasRepository()

        entity_repo.save(
            CanonicalEntity(
                canonical_entity_id=expected_id,
                entity_type=EntityType.STOCK,
                display_name=case.input["subject"]["current_name"],
                status=EntityStatus.ACTIVE,
                anchor_code=ts_code,
                cross_listing_group=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )

        # Register the 3 aliases the case's mention_samples will probe:
        # former_name (有棵树), full_name (行云科技), code (300209.SZ).
        event = case.input["namechange_event"]
        aliases_to_register = [
            (event["before_name"], AliasType.FORMER_NAME),
            (event["after_name"], AliasType.FULL_NAME),
            (event["ts_code"], AliasType.CODE),
        ]
        for alias_text, alias_type in aliases_to_register:
            alias_repo.save(
                EntityAlias(
                    canonical_entity_id=expected_id,
                    alias_text=alias_text,
                    alias_type=alias_type,
                    is_primary=(alias_type is AliasType.FULL_NAME),
                    confidence=1.0,
                    source="phase-b-namechange-regression",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        # Drive the runtime resolver against EACH mention sample and
        # assert the case's expected_resolutions invariants hold.
        mention_samples = case.input["mention_samples"]
        expected_resolutions_by_id = {
            r["mention_id"]: r for r in case.expected["expected_resolutions"]
        }
        assert len(mention_samples) >= 3, (
            f"case must carry at least 3 mention samples (old name + new "
            f"name + ts_code); got {len(mention_samples)}"
        )

        for mention in mention_samples:
            resolved = lookup_alias_in_repositories(
                mention["raw_text"],
                alias_repo,
                entity_repo,
            )
            assert resolved is not None, (
                f"mention {mention['mention_id']!r} ({mention['raw_text']!r}) "
                f"failed runtime alias lookup; namechange handling is broken"
            )
            assert resolved.canonical_entity_id == expected_id, (
                f"mention {mention['mention_id']!r} resolved to "
                f"{resolved.canonical_entity_id!r}, not expected "
                f"{expected_id!r} — CLAUDE.md A+H zero-tolerance "
                f"mirror invariant: namechange must NOT split into "
                f"two canonical ids"
            )

            # Cross-check with case.expected if the resolution is named.
            expected_resolution = expected_resolutions_by_id.get(
                mention["mention_id"]
            )
            if expected_resolution is not None:
                assert resolved.canonical_entity_id == expected_resolution[
                    "canonical_entity_id"
                ]
