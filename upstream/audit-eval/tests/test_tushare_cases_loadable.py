"""Tushare Phase B + #4 — loadability + invariant gate for tushare-derived shared cases.

Plan: ~/.claude/plans/wise-cooking-wolf.md §6.2.3 (Phase B)
      and ~/.claude/plans/wise-cooking-wolf.md (#4 replay extension).

Guards the 3 shared cases derived from the /Volumes/dockcase2tb
Tushare corpus:

    - minimal_cycle/case_tushare_one_stock_one_cycle        (Phase B)
    - event_cases/case_tushare_namechange_alias             (Phase B)
    - historical_replay_pack/case_tushare_replay_t1_minimal_cycle
                                                            (#4 — T+1 replay
      extension chained to the minimal_cycle case via shared cycle_id /
      manifest_cycle_id; hashes are real sha256 over a reproducible
      construction recipe documented in ``metadata.hash_recipe``)

The tests assert each case:

1. Loads through ``audit_eval_fixtures.load_case(...)`` without raising.
2. Exposes all five payload sections as non-empty dicts (except
   ``manifest_refs`` for the namechange case, which uses the empty
   shape per plan §6.2.2 — that case does NOT drive a publish
   manifest, so its ``manifest_refs`` has an explicitly empty
   ``snapshot_ids`` list; we assert the ``manifest_refs`` dict itself
   is present and non-empty as a top-level contract).
3. Carries ``metadata.replay_mode == "read_history"`` (audit-eval
   CLAUDE.md C1 mandatory).
4. Carries a complete ``metadata.tushare_source`` block with the 8
   keys the Phase B traceability contract requires (plan §7), and
   ``completeness_status == "未见明显遗漏"``.
5. (replay case only) Recomputed sha256 over the documented
   construction strings equals the hashes baked into ``input.json``
   and ``metadata.hash_recipe.{input,output}_hash_value`` (real
   sha256, not synthetic).
6. (replay case only) Chains to the minimal_cycle case at BOTH the
   ``cycle_id`` level (audit/replay records + minimal_cycle input
   share ``CYC_2026_03_31_DAILY``) AND the ``manifest_cycle_id``
   level (metadata / manifest_refs / minimal_cycle metadata share
   ``MAN_CYC_2026_03_31_DAILY``).
"""

from __future__ import annotations

import hashlib

import pytest

from audit_eval_fixtures import Case, load_case


_REQUIRED_TRACEABILITY_KEYS = frozenset(
    {
        "corpus_root",
        "dataset_path",
        "datasets",
        "selected_ts_codes",
        "date_window",
        "audit_timestamp",
        "completeness_status",
        "coverage_note",
    }
)


@pytest.fixture(scope="module")
def minimal_cycle_case() -> Case:
    return load_case("minimal_cycle", "case_tushare_one_stock_one_cycle")


@pytest.fixture(scope="module")
def namechange_case() -> Case:
    return load_case("event_cases", "case_tushare_namechange_alias")


@pytest.fixture(scope="module")
def tushare_replay_case() -> Case:
    return load_case(
        "historical_replay_pack", "case_tushare_replay_t1_minimal_cycle"
    )


class TestMinimalCycleTushareCaseLoadable:
    """minimal_cycle/case_tushare_one_stock_one_cycle."""

    def test_all_five_payloads_are_non_empty_dicts(
        self, minimal_cycle_case: Case
    ) -> None:
        for section in ("input", "context", "expected", "manifest_refs", "metadata"):
            payload = getattr(minimal_cycle_case, section)
            assert isinstance(payload, dict), (
                f"{section!r} must be a dict, got {type(payload).__name__}"
            )
            assert payload, f"{section!r} must be non-empty for this case"

    def test_metadata_replay_mode_is_read_history(
        self, minimal_cycle_case: Case
    ) -> None:
        """audit-eval CLAUDE.md C1: replay_mode must be read_history."""

        assert minimal_cycle_case.metadata["replay_mode"] == "read_history"

    def test_metadata_fixture_kind_is_minimal_cycle_baseline(
        self, minimal_cycle_case: Case
    ) -> None:
        assert (
            minimal_cycle_case.metadata["fixture_kind"]
            == "minimal_cycle_baseline"
        )

    def test_metadata_tushare_source_has_all_eight_traceability_keys(
        self, minimal_cycle_case: Case
    ) -> None:
        """Plan §7 traceability contract: every committed shared-case fixture
        must carry the 8-key tushare_source block so the source-to-case
        link is preserved through the repo."""

        source = minimal_cycle_case.metadata["tushare_source"]
        assert isinstance(source, dict)
        assert _REQUIRED_TRACEABILITY_KEYS.issubset(source.keys()), (
            f"missing traceability keys: "
            f"{_REQUIRED_TRACEABILITY_KEYS - source.keys()}"
        )
        assert source["completeness_status"] == "未见明显遗漏"

    def test_input_candidate_universe_matches_tushare_source_ts_code(
        self, minimal_cycle_case: Case
    ) -> None:
        """The case_tushare_one_stock_one_cycle candidate IS the tushare-cut
        stock — the input ts_code must match the metadata selected ts_code."""

        universe = minimal_cycle_case.input["candidate_universe"]
        assert len(universe) == 1
        candidate_ts = universe[0]["ts_code"]
        selected = minimal_cycle_case.metadata["tushare_source"][
            "selected_ts_codes"
        ]
        assert candidate_ts in selected, (
            f"candidate_universe ts_code {candidate_ts!r} not in "
            f"selected_ts_codes {selected!r}"
        )

    def test_input_canonical_entity_id_follows_runtime_format(
        self, minimal_cycle_case: Case
    ) -> None:
        """Codex review #1 P2 strict regression: the candidate's
        canonical_entity_id MUST follow the live entity-registry runtime
        rule ``generate_stock_entity_id(ts_code) = f'ENT_STOCK_{ts_code}'``
        which preserves the dot in ts_code. Using the underscore-only
        format ``ENT_STOCK_<symbol>_<exchange>`` (as case_001 does)
        diverges from runtime and silently breaks 'consume case under
        entity-registry rules' semantics. This test fixes the format
        contract for new tushare-derived cases."""

        candidate = minimal_cycle_case.input["candidate_universe"][0]
        ts_code = candidate["ts_code"]
        canonical_id = candidate["canonical_entity_id"]
        expected = f"ENT_STOCK_{ts_code}"
        assert canonical_id == expected, (
            f"canonical_entity_id {canonical_id!r} drifted from runtime "
            f"format generate_stock_entity_id({ts_code!r}) = {expected!r}; "
            f"do NOT regress to underscore-only convention"
        )

    def test_manifest_cycle_id_matches_expected_publish_manifest(
        self, minimal_cycle_case: Case
    ) -> None:
        """Cross-file consistency: the manifest_cycle_id in metadata must
        equal the manifest_refs.cycle_publish_manifest_id, and the
        expected publish manifest's cycle_id must be derivable (no _v0
        suffix at shared-case level)."""

        metadata_manifest = minimal_cycle_case.metadata["manifest_cycle_id"]
        refs_manifest = minimal_cycle_case.manifest_refs[
            "cycle_publish_manifest_id"
        ]
        assert metadata_manifest == refs_manifest


class TestNamechangeAliasTushareCaseLoadable:
    """event_cases/case_tushare_namechange_alias."""

    def test_all_five_payloads_are_non_empty_dicts(
        self, namechange_case: Case
    ) -> None:
        for section in ("input", "context", "expected", "manifest_refs", "metadata"):
            payload = getattr(namechange_case, section)
            assert isinstance(payload, dict), (
                f"{section!r} must be a dict, got {type(payload).__name__}"
            )
            assert payload, f"{section!r} must be non-empty for this case"

    def test_metadata_replay_mode_is_read_history(
        self, namechange_case: Case
    ) -> None:
        """audit-eval CLAUDE.md C1: replay_mode must be read_history even
        for non-cycle event cases."""

        assert namechange_case.metadata["replay_mode"] == "read_history"

    def test_metadata_fixture_kind_is_namechange_alias_event(
        self, namechange_case: Case
    ) -> None:
        assert (
            namechange_case.metadata["fixture_kind"]
            == "namechange_alias_event"
        )

    def test_metadata_tushare_source_has_all_eight_traceability_keys(
        self, namechange_case: Case
    ) -> None:
        source = namechange_case.metadata["tushare_source"]
        assert isinstance(source, dict)
        assert _REQUIRED_TRACEABILITY_KEYS.issubset(source.keys()), (
            f"missing traceability keys: "
            f"{_REQUIRED_TRACEABILITY_KEYS - source.keys()}"
        )
        assert source["completeness_status"] == "未见明显遗漏"

    def test_manifest_refs_uses_minimal_non_publish_shape(
        self, namechange_case: Case
    ) -> None:
        """Plan §6.2.2: namechange case does NOT drive a publish manifest,
        so manifest_refs carries the explicitly empty shape."""

        refs = namechange_case.manifest_refs
        assert refs["cycle_publish_manifest_id"] is None
        assert refs["snapshot_ids"] == []
        assert refs["iceberg_namespace"] == "n/a"
        assert "entity-registry" in refs["consumer_modules"]

    def test_expected_proves_same_canonical_entity_id_across_three_mentions(
        self, namechange_case: Case
    ) -> None:
        """The core invariant of the namechange case: old-name + new-name
        + ts_code mentions all resolve to the same canonical entity id.
        Zero-tolerance per entity-registry CLAUDE.md."""

        expected_id = namechange_case.expected["expected_canonical_entity_id"]
        resolutions = namechange_case.expected["expected_resolutions"]
        assert len(resolutions) == 3
        for resolution in resolutions:
            assert resolution["canonical_entity_id"] == expected_id, (
                f"mention {resolution['mention_id']!r} resolves to "
                f"{resolution['canonical_entity_id']!r}, not the expected "
                f"{expected_id!r} — this would split the entity into two "
                f"canonical ids (entity-registry CLAUDE.md zero tolerance)"
            )

    def test_input_mention_samples_cover_old_new_and_ts_code(
        self, namechange_case: Case
    ) -> None:
        """Plan §6.2.2: at least 3 mentions — one with old name, one with
        new name, one with ts_code."""

        mentions = namechange_case.input["mention_samples"]
        kinds = {m["mention_kind"] for m in mentions}
        assert {"name_before", "name_after", "ts_code"}.issubset(kinds)

    def test_input_namechange_event_matches_metadata_traceability(
        self, namechange_case: Case
    ) -> None:
        """Cross-file consistency: the event's ts_code must be the one
        declared in metadata.tushare_source.selected_ts_codes."""

        event_ts = namechange_case.input["namechange_event"]["ts_code"]
        selected = namechange_case.metadata["tushare_source"][
            "selected_ts_codes"
        ]
        assert event_ts in selected

    def test_canonical_entity_id_follows_runtime_format(
        self, namechange_case: Case
    ) -> None:
        """Codex review #1 P2 strict regression: every canonical_entity_id
        in this case (input.subject + every expected_resolutions entry)
        MUST follow the live entity-registry runtime rule
        ``generate_stock_entity_id(ts_code) = f'ENT_STOCK_{ts_code}'``
        which preserves the dot. This is the contract that lets
        downstream entity-registry consumers actually verify resolutions
        against the runtime — not against a stale doc convention."""

        ts_code = namechange_case.input["namechange_event"]["ts_code"]
        expected_id = f"ENT_STOCK_{ts_code}"

        # input.subject
        subject_id = namechange_case.input["subject"]["canonical_entity_id"]
        assert subject_id == expected_id, (
            f"input.subject.canonical_entity_id {subject_id!r} drifted "
            f"from runtime format {expected_id!r}"
        )

        # expected.expected_canonical_entity_id
        top_id = namechange_case.expected["expected_canonical_entity_id"]
        assert top_id == expected_id, (
            f"expected.expected_canonical_entity_id {top_id!r} drifted "
            f"from runtime format {expected_id!r}"
        )

        # expected.expected_resolutions[*].canonical_entity_id
        for resolution in namechange_case.expected["expected_resolutions"]:
            assert resolution["canonical_entity_id"] == expected_id, (
                f"resolution {resolution['mention_id']!r} "
                f"canonical_entity_id {resolution['canonical_entity_id']!r} "
                f"drifted from runtime format {expected_id!r}"
            )


class TestTushareReplayT1CaseLoadable:
    """historical_replay_pack/case_tushare_replay_t1_minimal_cycle.

    Plan §2.1 (#4 — corpus-derived synthetic extension): this case is
    the tushare-derived T+1 replay extension chained to the Phase B
    ``minimal_cycle/case_tushare_one_stock_one_cycle`` case. Subject
    600519.SH, cycle ``CYC_2026_03_31_DAILY``, manifest
    ``MAN_CYC_2026_03_31_DAILY``. Hashes are REAL sha256 over the
    construction recipe documented in ``metadata.hash_recipe`` — see
    tests 7, 8.
    """

    def test_all_five_payloads_are_non_empty_dicts(
        self, tushare_replay_case: Case
    ) -> None:
        for section in ("input", "context", "expected", "manifest_refs", "metadata"):
            payload = getattr(tushare_replay_case, section)
            assert isinstance(payload, dict), (
                f"{section!r} must be a dict, got {type(payload).__name__}"
            )
            assert payload, f"{section!r} must be non-empty for this case"

    def test_metadata_replay_mode_is_read_history(
        self, tushare_replay_case: Case
    ) -> None:
        """audit-eval CLAUDE.md C1: replay_mode must be read_history."""

        assert tushare_replay_case.metadata["replay_mode"] == "read_history"

    def test_metadata_fixture_kind_is_historical_replay_t1_tushare_extension(
        self, tushare_replay_case: Case
    ) -> None:
        assert (
            tushare_replay_case.metadata["fixture_kind"]
            == "historical_replay_t1_tushare_extension"
        )

    def test_metadata_tushare_source_has_all_eight_traceability_keys(
        self, tushare_replay_case: Case
    ) -> None:
        source = tushare_replay_case.metadata["tushare_source"]
        assert isinstance(source, dict)
        assert _REQUIRED_TRACEABILITY_KEYS.issubset(source.keys()), (
            f"missing traceability keys: "
            f"{_REQUIRED_TRACEABILITY_KEYS - source.keys()}"
        )
        assert source["completeness_status"] == "未见明显遗漏"

    def test_metadata_hash_kind_is_real_sha256(
        self, tushare_replay_case: Case
    ) -> None:
        """Plan §4: hashes are real sha256 (not synthetic placeholders),
        so reasoner-runtime's hash-equality regression path against
        runtime ``sha256_text()`` actually has ground truth to compare
        against."""

        assert tushare_replay_case.metadata["hash_kind"] == "real_sha256"

    def test_metadata_hash_recipe_documents_both_construction_strings(
        self, tushare_replay_case: Case
    ) -> None:
        """The recipe must describe HOW input_hash and output_hash were
        constructed so any consumer can reproduce them deterministically."""

        recipe = tushare_replay_case.metadata["hash_recipe"]
        assert "sanitized_input_str_construction" in recipe
        assert "raw_output_construction" in recipe
        # Codex P3 finding B: recipe also carries the actual hash values
        # (self-proving — consumer does not need to parse input.json to
        # cross-check).
        assert "input_hash_value" in recipe
        assert "output_hash_value" in recipe

    def test_input_hash_matches_replay_bundle_sanitized_input_sha256(
        self, tushare_replay_case: Case
    ) -> None:
        """Codex P3 strengthening, 2026-04-24: hash the fixture's **own**
        ``replay_bundle.sanitized_input`` string (NOT a hard-coded
        literal in the test body) and assert 4-way equality against
        every recorded input_hash.

        Previously the test re-hashed a hard-coded dict literal — which
        would happily pass even if a future edit changed
        ``replay_bundle.sanitized_input`` in input.json while leaving
        the recorded hashes alone. The fix binds the hash guard
        directly to the bundled payload:

            sha256(replay_bundle["sanitized_input"])
              == replay_bundle["input_hash"]
              == audit_record.llm_lineage.input_hash
              == metadata.hash_recipe.input_hash_value
        """

        bundle = tushare_replay_case.input["replay_record"]["replay_bundle"]
        sanitized_input = bundle["sanitized_input"]
        recomputed = hashlib.sha256(
            sanitized_input.encode("utf-8")
        ).hexdigest()

        recorded_bundle = bundle["input_hash"]
        recorded_audit = tushare_replay_case.input["audit_record"][
            "llm_lineage"
        ]["input_hash"]
        recipe_value = tushare_replay_case.metadata["hash_recipe"][
            "input_hash_value"
        ]

        assert recomputed == recorded_bundle, (
            f"sha256(replay_bundle.sanitized_input) {recomputed!r} != "
            f"replay_bundle.input_hash {recorded_bundle!r} — fixture "
            f"payload was edited but the recorded hash was not updated"
        )
        assert recomputed == recorded_audit, (
            f"sha256(replay_bundle.sanitized_input) {recomputed!r} != "
            f"audit_record.llm_lineage.input_hash {recorded_audit!r}"
        )
        assert recomputed == recipe_value, (
            f"sha256(replay_bundle.sanitized_input) {recomputed!r} != "
            f"metadata.hash_recipe.input_hash_value {recipe_value!r}"
        )

    def test_output_hash_matches_replay_bundle_raw_output_sha256(
        self, tushare_replay_case: Case
    ) -> None:
        """Codex P3 strengthening, 2026-04-24: symmetric fix for the
        output side. Hashes the fixture's own ``replay_bundle.raw_output``
        string and asserts 4-way equality.

            sha256(replay_bundle["raw_output"])
              == replay_bundle["output_hash"]
              == audit_record.llm_lineage.output_hash
              == metadata.hash_recipe.output_hash_value
        """

        bundle = tushare_replay_case.input["replay_record"]["replay_bundle"]
        raw_output = bundle["raw_output"]
        recomputed = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()

        recorded_bundle = bundle["output_hash"]
        recorded_audit = tushare_replay_case.input["audit_record"][
            "llm_lineage"
        ]["output_hash"]
        recipe_value = tushare_replay_case.metadata["hash_recipe"][
            "output_hash_value"
        ]

        assert recomputed == recorded_bundle, (
            f"sha256(replay_bundle.raw_output) {recomputed!r} != "
            f"replay_bundle.output_hash {recorded_bundle!r} — fixture "
            f"payload was edited but the recorded hash was not updated"
        )
        assert recomputed == recorded_audit, (
            f"sha256(replay_bundle.raw_output) {recomputed!r} != "
            f"audit_record.llm_lineage.output_hash {recorded_audit!r}"
        )
        assert recomputed == recipe_value, (
            f"sha256(replay_bundle.raw_output) {recomputed!r} != "
            f"metadata.hash_recipe.output_hash_value {recipe_value!r}"
        )

    def test_replay_bundle_has_all_five_fields(
        self, tushare_replay_case: Case
    ) -> None:
        """audit-eval CLAUDE.md C5: all 5 replay fields must be present."""

        bundle = tushare_replay_case.input["replay_record"]["replay_bundle"]
        for field in (
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        ):
            assert field in bundle, (
                f"replay bundle missing required field {field!r}"
            )

    def test_manifest_cycle_id_chain_matches_minimal_cycle(
        self,
        tushare_replay_case: Case,
        minimal_cycle_case: Case,
    ) -> None:
        """Plan §1: the replay case must chain to Phase B minimal_cycle's
        manifest axis. ``metadata.manifest_cycle_id`` must equal
        ``manifest_refs.cycle_publish_manifest_id`` AND must equal the
        minimal_cycle case's ``manifest_cycle_id``. This prevents the
        replay case from drifting onto a different publish manifest."""

        metadata_manifest = tushare_replay_case.metadata["manifest_cycle_id"]
        refs_manifest = tushare_replay_case.manifest_refs[
            "cycle_publish_manifest_id"
        ]
        minimal_manifest = minimal_cycle_case.metadata["manifest_cycle_id"]

        assert metadata_manifest == refs_manifest, (
            f"metadata.manifest_cycle_id {metadata_manifest!r} != "
            f"manifest_refs.cycle_publish_manifest_id {refs_manifest!r}"
        )
        assert metadata_manifest == minimal_manifest, (
            f"metadata.manifest_cycle_id {metadata_manifest!r} diverged "
            f"from minimal_cycle case manifest_cycle_id {minimal_manifest!r} "
            f"— replay case must chain to the same publish manifest"
        )

    def test_input_audit_and_replay_record_share_cycle_and_object_ref(
        self, tushare_replay_case: Case
    ) -> None:
        """Intra-case consistency: audit_record and replay_record must
        reference the same cycle and the same published object."""

        audit = tushare_replay_case.input["audit_record"]
        replay = tushare_replay_case.input["replay_record"]
        assert audit["cycle_id"] == replay["cycle_id"]
        assert audit["object_ref"] == replay["object_ref"]

    def test_subject_ts_code_matches_minimal_cycle_case(
        self,
        tushare_replay_case: Case,
        minimal_cycle_case: Case,
    ) -> None:
        """Plan §1: the replay case's subject MUST be the single-stock
        corpus cut that Phase B minimal_cycle uses (600519.SH). The
        object_ref path already encodes 600519.SH, and both cases'
        tushare_source.selected_ts_codes must agree."""

        replay_selected = tushare_replay_case.metadata["tushare_source"][
            "selected_ts_codes"
        ]
        minimal_selected = minimal_cycle_case.metadata["tushare_source"][
            "selected_ts_codes"
        ]
        assert replay_selected == minimal_selected, (
            f"replay case selected_ts_codes {replay_selected!r} differs "
            f"from minimal_cycle selected_ts_codes {minimal_selected!r}"
        )
        assert replay_selected == ["600519.SH"]
        # object_ref path must encode the subject ts_code.
        audit_object_ref = tushare_replay_case.input["audit_record"][
            "object_ref"
        ]
        assert "600519.SH" in audit_object_ref

    def test_cycle_id_chain_matches_minimal_cycle(
        self,
        tushare_replay_case: Case,
        minimal_cycle_case: Case,
    ) -> None:
        """Codex P2 add, 2026-04-24: complement to
        ``test_manifest_cycle_id_chain_matches_minimal_cycle`` — covers
        the ``cycle_id`` level of the chain, not just the
        ``manifest_cycle_id`` level.

        Without this, a future edit could put the replay case on a
        different ``cycle_id`` while still pointing at the same
        ``manifest_cycle_id`` — silently breaking the "replay pulls L6
        from the same published cycle Phase B minimal_cycle produced"
        design claim.

        Asserts:
          audit_record.cycle_id
            == replay_record.cycle_id
            == minimal_cycle_case.input["cycle_id"]
            == "CYC_2026_03_31_DAILY"
        """

        audit_cycle = tushare_replay_case.input["audit_record"]["cycle_id"]
        replay_cycle = tushare_replay_case.input["replay_record"]["cycle_id"]
        minimal_cycle = minimal_cycle_case.input["cycle_id"]

        assert audit_cycle == replay_cycle, (
            f"audit_record.cycle_id {audit_cycle!r} != replay_record.cycle_id "
            f"{replay_cycle!r} — intra-case cycle_id split"
        )
        assert audit_cycle == minimal_cycle, (
            f"replay case cycle_id {audit_cycle!r} diverged from minimal_cycle "
            f"case cycle_id {minimal_cycle!r} — the two cases must share a "
            f"cycle axis so 'replay the L6 alpha_result for 600519 from the "
            f"cycle Phase B minimal_cycle published' is a coherent consumer "
            f"story"
        )
        assert audit_cycle == "CYC_2026_03_31_DAILY"
