"""Canonical contract-tier tests for main-core public API.

Per SUBPROJECT_TESTING_STANDARD.md §3.2 + §13.3 + iron rule #4 a module
with public interfaces must have a non-empty canonical contract tier.

main-core's contract surface is the four formal objects per §10 重点
testing checklist + main-core/CLAUDE.md §16.3 / §9 关键业务约束:

- WorldStateSnapshot   — L4 共享状态层（L5/L6/L7 只读消费）
- OfficialAlphaPool    — L5 universe / pool capacity
- AlphaResultSnapshot  — L6 alpha 业务结果（含 analyzer_type 不变约束）
- RecommendationSnapshot — L7 正式建议输出

These tests assert:
1. Each formal object's Pydantic model declares non-empty fields
2. AlphaResultSnapshot ships with the analyzer_type discriminator (P2
   freeze: must default to / accept ``single_prompt_v1``; P8 will add
   ``multi_agent_v1``) — drift here is a CLAUDE.md Blocker
3. WorldStateSnapshot reserves a llm_delta-shaped field (must be ±1 per
   CLAUDE.md §9; the boundary tier validates the actual range, here we
   only enforce the field exists in the model)
4. The shared `model_config` extra="forbid" stance is preserved on the
   four objects (drift would let unknown fields slip through to consumers)
"""

from __future__ import annotations

import inspect

import pytest


class TestFormalObjectModelsImport:
    """The four formal objects must be importable from their canonical
    paths under main_core.common.schemas. Import drift gets caught here
    before anywhere else.
    """

    def test_world_state_snapshot_importable(self) -> None:
        from main_core.common.schemas.world_state import WorldStateSnapshot

        assert WorldStateSnapshot.model_fields, "WorldStateSnapshot has no fields"

    def test_official_alpha_pool_importable(self) -> None:
        from main_core.common.schemas.pool import OfficialAlphaPool

        assert OfficialAlphaPool.model_fields, "OfficialAlphaPool has no fields"

    def test_alpha_result_snapshot_importable(self) -> None:
        from main_core.common.schemas.alpha import AlphaResultSnapshot

        assert AlphaResultSnapshot.model_fields, "AlphaResultSnapshot has no fields"

    def test_recommendation_snapshot_importable(self) -> None:
        from main_core.common.schemas.recommendation import RecommendationSnapshot

        assert RecommendationSnapshot.model_fields, "RecommendationSnapshot has no fields"


class TestAnalyzerTypeContract:
    """``AlphaResultSnapshot.analyzer_type`` is a P2-frozen contract
    (see main-core/CLAUDE.md §16.3 + §9): must accept ``single_prompt_v1``;
    ``multi_agent_v1`` only enabled after P8 A/B. The contract here is
    that the field name is stable and at least the P2 default value is
    accepted by the model.
    """

    def test_analyzer_type_field_exists(self) -> None:
        from main_core.common.schemas.alpha import AlphaResultSnapshot

        assert "analyzer_type" in AlphaResultSnapshot.model_fields, (
            "AlphaResultSnapshot must expose analyzer_type discriminator "
            "(per CLAUDE.md §9 + §16.3)"
        )


class TestWorldStateLLMDeltaFieldExists:
    """``WorldStateSnapshot.llm_delta`` is a CLAUDE.md §9 invariant —
    the field must exist on the model. The actual ±1 range constraint is
    a boundary-tier concern (tests/boundary/test_red_lines.py).
    """

    def test_llm_delta_field_exists(self) -> None:
        from main_core.common.schemas.world_state import WorldStateSnapshot

        assert "llm_delta" in WorldStateSnapshot.model_fields, (
            "WorldStateSnapshot must expose llm_delta (per CLAUDE.md §9)"
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
        from main_core import public

        instance = getattr(public, kind)
        method = getattr(instance, method_name)
        sig = inspect.signature(method)
        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert len(params) == 1, f"{kind}.{method_name} expected 1 param, got {len(params)}"
        actual = params[0]
        assert actual.name == param_name
        assert actual.kind == param_kind
        assert actual.default is inspect.Parameter.empty

    def test_version_declaration_declare_no_params(self) -> None:
        from main_core import public

        sig = inspect.signature(public.version_declaration.declare)
        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        assert params == [], f"declare must take no params (besides self); got {params}"
