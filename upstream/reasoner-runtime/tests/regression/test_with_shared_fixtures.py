"""Regression tests consuming the shared ``audit_eval_fixtures`` package.

Per SUBPROJECT_TESTING_STANDARD.md §10 ``reasoner-runtime`` heavy-uses
``historical_replay_pack`` as the replay-bundle baseline. This module:

1. Walks every ``historical_replay_pack`` case and validates each
   ``replay_record.replay_bundle`` against the **five-field invariant**
   (sanitized_input/input_hash/raw_output/parsed_result/output_hash).
2. Confirms the ``audit_eval_fixtures`` package is actually installed.
3. **Really exercises the runtime sha256_text() path against the fixture
   hashes** — not just shape/format checks (codex stage-2.2 review #2,
   stage-2 plan iron rule #5: regression must touch real runtime code,
   not just fixture self-validation).

**Hard-import on purpose** (codex review #1 of stage 2.1, reusable rule):
the regression tier must really consume the fixture corpus, no
``pytest.skip(allow_module_level=True)``. ImportError bubbles to pytest
collection so ``make regression`` / the regression CI lane fail loud.

Install path: ``pip install -e ".[dev,shared-fixtures]"`` (requires
audit-eval @ v0.2.1+ where the fixture hashes are real sha256 hex).
"""

from __future__ import annotations

# Hard import — fail collection if shared-fixtures extra is not installed.
from audit_eval_fixtures import (  # noqa: F401
    Case,
    CaseRef,
    iter_cases,
    list_packs,
    load_case,
)

# Hard import the runtime function we exercise so a refactor that drops
# sha256_text from the public path fails immediately at collection.
from reasoner_runtime.replay.builder import sha256_text


class TestSharedFixturesAreReachable:
    def test_historical_replay_pack_present(self) -> None:
        assert "historical_replay_pack" in list_packs()

    def test_pack_has_at_least_one_case(self) -> None:
        cases = list(iter_cases("historical_replay_pack"))
        assert cases, "historical_replay_pack is empty"


class TestReplayBundleFiveFieldInvariant:
    """Every historical_replay_pack case must carry a replay_record with
    a replay_bundle whose five required fields are all present.

    This is the single most important reasoner-runtime regression
    invariant — drift in any case here would let downstream replay
    consumers (audit-eval, main-core T+1 retro) read a malformed bundle
    without surfacing a diff.
    """

    REPLAY_FIELD_NAMES = (
        "sanitized_input",
        "input_hash",
        "raw_output",
        "parsed_result",
        "output_hash",
    )

    def test_every_case_has_complete_five_field_bundle(self) -> None:
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            replay_record = case.input.get("replay_record", {})
            replay_bundle = replay_record.get("replay_bundle", {})

            missing = [
                fname for fname in self.REPLAY_FIELD_NAMES if fname not in replay_bundle
            ]
            assert not missing, (
                f"{ref.case_id}: replay_bundle missing required fields: {missing}"
            )

    def test_every_case_input_hash_is_sha256_hex(self) -> None:
        import re

        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            replay_bundle = case.input.get("replay_record", {}).get(
                "replay_bundle", {}
            )

            input_hash = replay_bundle.get("input_hash", "")
            # Either a sha256: prefixed value or a 64-char hex string —
            # both are accepted shapes per stage 1.3 sample case.
            assert input_hash.startswith("sha256:") or re.fullmatch(
                r"[0-9a-fA-F]{64}", input_hash
            ), f"{ref.case_id}: input_hash {input_hash!r} is not sha256-shaped"


class TestReplayHashesRoundTripAgainstRuntime:
    """**This is the real-runtime regression** (stage-2 plan iron rule #5).

    For every historical_replay_pack case whose metadata declares
    ``hash_kind == "real_sha256"``, recompute input_hash and output_hash
    via the runtime ``reasoner_runtime.replay.builder.sha256_text`` and
    assert byte-for-byte equality with the stored fixture hashes.

    This catches:
      - sha256_text getting accidentally swapped to a different hash (md5
        / sha1 / blake2)
      - encoding drift (e.g. utf-8 → latin-1 silently)
      - the fixture's sanitized_input string drifting away from its
        recorded hash
      - the fixture's raw_output drifting away from its recorded hash

    Cases without ``hash_kind: real_sha256`` are skipped per-case (not
    module-level) so a fixture-only-shape case can still ship without
    blocking this regression. As of audit-eval v0.2.1, only
    case_replay_t1_basic carries real hashes; future cases in
    historical_replay_pack should follow the same recipe.
    """

    def test_input_hash_roundtrip_via_runtime_sha256_text(self) -> None:
        exercised_at_least_one = False
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            if case.metadata.get("hash_kind") != "real_sha256":
                continue
            exercised_at_least_one = True

            replay_bundle = case.input["replay_record"]["replay_bundle"]
            sanitized_input_str = replay_bundle["sanitized_input"]
            stored_hash = replay_bundle["input_hash"]

            recomputed = sha256_text(sanitized_input_str)
            assert recomputed == stored_hash, (
                f"{ref.case_id}: runtime sha256_text(sanitized_input) "
                f"= {recomputed!r}, but fixture stores {stored_hash!r}"
            )

        assert exercised_at_least_one, (
            "expected at least one case with hash_kind=real_sha256 in "
            "historical_replay_pack — fixture promotion regressed?"
        )

    def test_output_hash_roundtrip_via_runtime_sha256_text(self) -> None:
        exercised_at_least_one = False
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            if case.metadata.get("hash_kind") != "real_sha256":
                continue
            exercised_at_least_one = True

            replay_bundle = case.input["replay_record"]["replay_bundle"]
            raw_output = replay_bundle["raw_output"]
            stored_hash = replay_bundle["output_hash"]

            recomputed = sha256_text(raw_output)
            assert recomputed == stored_hash, (
                f"{ref.case_id}: runtime sha256_text(raw_output) "
                f"= {recomputed!r}, but fixture stores {stored_hash!r}"
            )

        assert exercised_at_least_one, (
            "expected at least one case with hash_kind=real_sha256 in "
            "historical_replay_pack — fixture promotion regressed?"
        )

    def test_audit_record_lineage_hashes_match_replay_bundle(self) -> None:
        """audit_record.llm_lineage carries copies of the same hashes;
        if they drift apart inside one fixture, downstream consumers
        (audit-eval retro, main-core T+1) will get inconsistent views.
        """
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            if case.metadata.get("hash_kind") != "real_sha256":
                continue
            audit_lineage = case.input["audit_record"]["llm_lineage"]
            replay_bundle = case.input["replay_record"]["replay_bundle"]
            assert audit_lineage["input_hash"] == replay_bundle["input_hash"]
            assert audit_lineage["output_hash"] == replay_bundle["output_hash"]


class TestReplayPathInvariantsExpected:
    """Every historical_replay_pack case must declare the expected
    replay-path invariants in context.json that reasoner-runtime
    promises (no_live_model_call, manifest_must_exist_before_read,
    five_replay_fields_present, hash equality).

    Drift in the *expected* invariant set would mean the fixture stops
    asserting the contract reasoner-runtime owns.
    """

    REQUIRED_INVARIANTS = {
        "no_live_model_call",
        "manifest_must_exist_before_read",
        "five_replay_fields_present",
        "input_hash_matches_recomputed_input",
        "output_hash_matches_recomputed_output",
    }

    def test_every_case_declares_required_invariants(self) -> None:
        for ref in iter_cases("historical_replay_pack"):
            case = load_case(ref.pack_name, ref.case_id)
            declared = set(
                case.context.get("expected_replay_path_invariants", [])
            )
            missing = self.REQUIRED_INVARIANTS - declared
            assert not missing, (
                f"{ref.case_id}: context missing replay-path invariants: {missing}"
            )
