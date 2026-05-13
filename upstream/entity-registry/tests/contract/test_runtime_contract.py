"""Canonical contract-tier tests for entity-registry public API.

Per SUBPROJECT_TESTING_STANDARD.md §3.2 + §13.3 + iron rule #4.

entity-registry's contract surface per §10:
- ``resolve_mention(raw_mention_text, context=None)`` — single mention
- ``lookup_alias(alias_text)`` — alias-table lookup
- ``batch_resolve(references)`` — batch path
- 5 public entrypoint signatures (assembly Protocol contract)
"""

from __future__ import annotations

import inspect

import pytest


class TestRuntimeApiSignatures:
    def test_resolve_mention_signature(self) -> None:
        from entity_registry import resolve_mention

        sig = inspect.signature(resolve_mention)
        params = list(sig.parameters)
        assert params[:1] == ["raw_mention_text"], (
            f"resolve_mention first param must be 'raw_mention_text', got {params[:1]}"
        )

    def test_lookup_alias_signature(self) -> None:
        from entity_registry import lookup_alias

        sig = inspect.signature(lookup_alias)
        params = list(sig.parameters)
        assert params[:1] == ["alias_text"], (
            f"lookup_alias first param must be 'alias_text', got {params[:1]}"
        )

    def test_batch_resolve_signature(self) -> None:
        from entity_registry import batch_resolve

        sig = inspect.signature(batch_resolve)
        params = list(sig.parameters)
        assert params[:1] == ["references"], (
            f"batch_resolve first param must be 'references', got {params[:1]}"
        )


class TestPublicEntrypointsSignatures:
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
        from entity_registry import public

        instance = getattr(public, kind)
        method = getattr(instance, method_name)
        sig = inspect.signature(method)
        params = [
            p for p in sig.parameters.values()
            if p.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert len(params) == 1
        actual = params[0]
        assert actual.name == param_name
        assert actual.kind == param_kind
        assert actual.default is inspect.Parameter.empty

    def test_version_declaration_declare_no_params(self) -> None:
        from entity_registry import public

        sig = inspect.signature(public.version_declaration.declare)
        params = [
            p for p in sig.parameters.values()
            if p.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert params == []
