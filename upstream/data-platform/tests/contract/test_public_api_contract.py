"""Canonical contract-tier tests for data-platform public API.

Per SUBPROJECT_TESTING_STANDARD.md §3.2 + §13.3 + iron rule #4: a module
with public interfaces must have a non-empty canonical contract tier.

data-platform's contract surface is the five headline runtime functions
listed in §10 and main-core/CLAUDE.md (downstream consumers depend on
these signatures):

- list_cycles(*, limit=..., status=...)
- get_formal_latest(object_type)
- get_formal_by_id(cycle_id, object_type)
- submit_candidate(payload)
- freeze_cycle_candidates(cycle_id)

Plus the five public entrypoint signatures (assembly Protocol contract).
"""

from __future__ import annotations

import inspect

import pytest


class TestRuntimeApiSignatures:
    """Each runtime function must keep its parameter shape stable.
    Adding optional kwargs is fine; reordering, renaming or dropping
    required params is a breaking change for downstream consumers.
    """

    def test_list_cycles_signature(self) -> None:
        from data_platform.cycle import list_cycles

        sig = inspect.signature(list_cycles)
        params = sig.parameters
        assert params["limit"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["limit"].default == 100
        assert params["status"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["status"].default is None

    def test_get_formal_latest_signature(self) -> None:
        from data_platform.serving.formal import get_formal_latest

        sig = inspect.signature(get_formal_latest)
        params = list(sig.parameters)
        assert params[:1] == ["object_type"], (
            f"get_formal_latest first param must be 'object_type', got {params[:1]}"
        )

    def test_get_formal_by_id_signature(self) -> None:
        from data_platform.serving.formal import get_formal_by_id

        sig = inspect.signature(get_formal_by_id)
        params = list(sig.parameters)
        assert params[:2] == ["cycle_id", "object_type"], (
            f"get_formal_by_id params must be (cycle_id, object_type), got {params[:2]}"
        )

    def test_submit_candidate_signature(self) -> None:
        from data_platform.queue.api import submit_candidate

        sig = inspect.signature(submit_candidate)
        params = list(sig.parameters)
        assert params[:1] == ["payload"], (
            f"submit_candidate first param must be 'payload', got {params[:1]}"
        )

    def test_freeze_cycle_candidates_signature(self) -> None:
        from data_platform.cycle.freeze import freeze_cycle_candidates

        sig = inspect.signature(freeze_cycle_candidates)
        params = list(sig.parameters)
        assert params[:1] == ["cycle_id"], (
            f"freeze_cycle_candidates first param must be 'cycle_id', got {params[:1]}"
        )


class TestPublicEntrypointsSignatures:
    """The five public entrypoints' signatures must match assembly
    Protocol exactly (assembly compat checks enforce this; we duplicate
    here so per-module CI catches drift before assembly e2e).
    """

    EXPECT = {
        "health_probe": ("check", "timeout_sec", inspect.Parameter.KEYWORD_ONLY),
        "smoke_hook": ("run", "profile_id", inspect.Parameter.KEYWORD_ONLY),
        "init_hook": ("initialize", "resolved_env", inspect.Parameter.KEYWORD_ONLY),
        "cli": ("invoke", "argv", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    }

    @pytest.mark.parametrize(
        "kind,method_name,param_name,param_kind",
        [(k, m, p, pk) for k, (m, p, pk) in EXPECT.items()],
    )
    def test_method_signature(
        self, kind: str, method_name: str, param_name: str, param_kind: int
    ) -> None:
        from data_platform import public

        instance = getattr(public, kind)
        method = getattr(instance, method_name)
        sig = inspect.signature(method)
        params = [
            p for p in sig.parameters.values()
            if p.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert len(params) == 1, f"{kind}.{method_name} expected 1 param, got {len(params)}"
        actual = params[0]
        assert actual.name == param_name
        assert actual.kind == param_kind
        assert actual.default is inspect.Parameter.empty

    def test_version_declaration_declare_no_params(self) -> None:
        from data_platform import public

        sig = inspect.signature(public.version_declaration.declare)
        params = [
            p for p in sig.parameters.values()
            if p.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert params == [], f"declare must take no params (besides self); got {params}"
