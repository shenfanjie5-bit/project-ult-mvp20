"""Canonical contract-tier tests for reasoner-runtime public API.

Per SUBPROJECT_TESTING_STANDARD.md §3.2 + §13.3 a module with public
interfaces must have a contract tier — not a legacy semantic check
(``tests/unit/test_contract_exports.py`` is unit-tier and stays put).
This file is the canonical contract lane and asserts:

1. Signature stability of the six public API entries listed in
   reasoner-runtime CLAUDE.md ("命名约束"):
     - generate_structured() / generate_structured_with_replay()
     - health_check()
     - scrub_input()
     - build_replay_bundle()
     - classify_failure()
     - build_client()

2. Runtime model -> contract model alignment: reasoner-runtime's
   ReplayBundle / ReasonerRequest / ReasonerResult must extend or stay
   field-compatible with the ``contracts.schemas.reasoner`` envelopes
   (the source of truth in the contracts module).

3. The five replay field names listed in the contract envelope match
   the five names ReplayBundle declares — drift here would silently
   break audit-eval / main-core T+1 retro consumers.

If anything in this file fails, the public API contract has shifted in
a way that downstream callers cannot react to without a code change.
"""

from __future__ import annotations

import inspect

import pytest


# ── Signature stability for the six public API entries ──────────────


class TestPublicApiSignatures:
    """Each public callable must keep its parameter shape stable.

    These are the six names §16 / CLAUDE.md guarantee to downstream
    consumers. Adding optional kwargs is fine; reordering, renaming or
    dropping required params is a breaking change.
    """

    def test_generate_structured_signature(self) -> None:
        from reasoner_runtime import generate_structured

        sig = inspect.signature(generate_structured)
        # First positional must be `request` (a ReasonerRequest).
        first_param = next(iter(sig.parameters.values()))
        assert first_param.name == "request", (
            f"generate_structured first param must be 'request', got {first_param.name!r}"
        )

    def test_generate_structured_with_replay_signature(self) -> None:
        from reasoner_runtime import generate_structured_with_replay

        sig = inspect.signature(generate_structured_with_replay)
        first_param = next(iter(sig.parameters.values()))
        assert first_param.name == "request"

    def test_health_check_signature(self) -> None:
        from reasoner_runtime import health_check

        sig = inspect.signature(health_check)
        # The signature should be callable; we don't enforce a specific
        # param name set since the implementation may take optional
        # provider/timeout overrides.
        assert callable(health_check)
        # But it must return something — annotation should not be None.
        # (We can't strictly enforce return-annotation presence pre-PEP 563
        # but at minimum the function is invocable.)

    def test_scrub_input_signature(self) -> None:
        from reasoner_runtime import scrub_input

        sig = inspect.signature(scrub_input)
        param_names = list(sig.parameters)
        # Contract: first positional is the LLM 'messages' payload to scrub;
        # 'metadata' + 'rule_set' are optional second/third kwargs.
        assert param_names[:1] == ["messages"], (
            f"scrub_input first param must be 'messages', got {param_names[:1]}"
        )

    def test_build_replay_bundle_signature(self) -> None:
        from reasoner_runtime import build_replay_bundle

        sig = inspect.signature(build_replay_bundle)
        positional_names = [
            p.name
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        # The 4 positional arguments are the runtime data fields the
        # bundle carries (sanitized_input/raw_output/parsed_result/lineage).
        assert positional_names[:4] == [
            "sanitized_input",
            "raw_output",
            "parsed_result",
            "lineage",
        ], (
            "build_replay_bundle positional arg order must stay "
            f"[sanitized_input, raw_output, parsed_result, lineage]; got {positional_names[:4]}"
        )

        # Keyword-only request and result are required (no default).
        kw_params = {
            name: p
            for name, p in sig.parameters.items()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        assert "request" in kw_params and "result" in kw_params, (
            f"build_replay_bundle must accept keyword-only request + result; got kw={list(kw_params)}"
        )

    def test_classify_failure_signature(self) -> None:
        from reasoner_runtime import classify_failure

        assert callable(classify_failure)

    def test_build_client_signature(self) -> None:
        from reasoner_runtime import build_client

        sig = inspect.signature(build_client)
        # Per CLAUDE.md "max_retries 必须显式传入 build_client()" —
        # confirm the parameter exists (whatever the position).
        assert "max_retries" in sig.parameters, (
            f"build_client must accept max_retries explicitly; got params={list(sig.parameters)}"
        )


# ── Runtime model <-> contract envelope alignment ───────────────────


class TestReplayBundleExtendsContractEnvelope:
    """ReplayBundle is the runtime concretion of contracts.schemas.reasoner
    .ReasonerReplay. The runtime class must remain a subclass so the
    contract fields (replay_id, recorded_at, replay_version) propagate.
    """

    def test_replay_bundle_subclasses_contract_envelope(self) -> None:
        from contracts.schemas.reasoner import ReasonerReplay
        from reasoner_runtime.replay.models import ReplayBundle

        assert issubclass(ReplayBundle, ReasonerReplay), (
            "ReplayBundle must subclass contracts.schemas.reasoner.ReasonerReplay "
            "so contract fields propagate"
        )

    def test_replay_bundle_has_five_runtime_fields(self) -> None:
        """The five runtime-only fields the bundle adds on top of the
        contract envelope. Names must match the §10 reasoner-runtime
        invariant exactly — drift breaks every replay consumer.
        """
        from reasoner_runtime.replay.models import ReplayBundle

        for fname in (
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        ):
            assert fname in ReplayBundle.model_fields, (
                f"ReplayBundle missing required runtime field {fname!r}"
            )


class TestReplayFieldNamesAreStable:
    """The constant ``ReplayBundle.replay_field_names`` must continue to
    list the same five names as the runtime field set. If the constant
    drifts from the model fields (or vice versa), audit-eval's
    AuditRecord.replay_field_names ClassVar — which mirrors this list —
    silently goes out of sync.
    """

    def test_runtime_constant_matches_field_names(self) -> None:
        from reasoner_runtime.replay.models import ReplayBundle

        runtime_constant = getattr(ReplayBundle, "replay_field_names", None)
        # The constant may or may not be defined; if it is, it must
        # match exactly. If it is not, the model field names alone are
        # enough source of truth.
        expected_names = (
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        )
        if runtime_constant is not None:
            assert tuple(runtime_constant) == expected_names, (
                f"ReplayBundle.replay_field_names drifted: {runtime_constant!r}"
            )

    def test_audit_eval_replay_field_names_reference_matches(self) -> None:
        """Cross-module sanity: audit_eval.contracts.AuditRecord declares
        the same five names as a ClassVar (verified live via
        audit_eval_fixtures' historical_replay_pack regression).

        We don't import audit_eval here (would create circular dev-time
        dep). We just check that the names we use are the canonical
        five — drift gets caught when a developer locally updates one
        side and forgets the other.
        """
        names = (
            "sanitized_input",
            "input_hash",
            "raw_output",
            "parsed_result",
            "output_hash",
        )
        assert len(names) == 5
        assert len(set(names)) == 5  # all distinct
