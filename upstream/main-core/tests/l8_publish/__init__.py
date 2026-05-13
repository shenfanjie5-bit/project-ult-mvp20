"""Local fakes and factories for L8 publish tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import (
    AlphaResultSnapshot,
    OfficialAlphaPool,
    RecommendationSnapshot,
    WorldStateSnapshot,
)
from main_core.common.types import CycleId
from main_core.l8_publish import CommittedFormalObject, ManifestWriteResult


def world_state(cycle_id: str = "cycle_l8") -> WorldStateSnapshot:
    return WorldStateSnapshot(
        cycle_id=cycle_id,
        baseline_regime="neutral",
        llm_delta=0,
        final_regime="neutral",
        llm_rationale="fixture",
        actual_model_used="fixture",
        actual_provider="local",
        fallback_path=[],
    )


def pool(
    selected_entities: Sequence[str] = ("ENT_A", "ENT_B"),
    *,
    cycle_id: str = "cycle_l8",
) -> OfficialAlphaPool:
    return OfficialAlphaPool(
        cycle_id=cycle_id,
        observation_pool_size=len(selected_entities),
        official_alpha_pool_capacity=100,
        selected_entities=list(selected_entities),
        added_entities=list(selected_entities),
        removed_entities=[],
        freeze_reason_map={},
    )


def alpha_result(
    entity_id: str,
    *,
    cycle_id: str = "cycle_l8",
    score: float | None = 0.7,
    status: str = "ok",
) -> AlphaResultSnapshot:
    return AlphaResultSnapshot(
        cycle_id=cycle_id,
        entity_id=entity_id,
        analyzer_type="single_prompt_v1",
        score=score,
        confidence=0.8 if status == "ok" else 0.0,
        rationale="fixture alpha",
        similar_cases=[],
        status=status,
    )


def recommendation(
    entity_id: str,
    *,
    cycle_id: str = "cycle_l8",
    action_type: str = "buy",
    override_applied: bool = False,
) -> RecommendationSnapshot:
    return RecommendationSnapshot(
        cycle_id=cycle_id,
        entity_id=entity_id,
        action_type=action_type,
        rating=None if action_type == "inconclusive" else (
            "A" if action_type == "buy" else "B"
        ),
        confidence=None if action_type == "inconclusive" else 0.8,
        triggered_by="human_decision" if override_applied else "system",
        override_applied=override_applied,
        constraints_applied={},
    )


class FakeFormalObjectSource:
    def __init__(
        self,
        *,
        loaded_world_state: WorldStateSnapshot | None = None,
        loaded_pool: OfficialAlphaPool | None = None,
        loaded_alpha_results: Sequence[AlphaResultSnapshot] | None = None,
        loaded_recommendations: Sequence[RecommendationSnapshot] | None = None,
    ) -> None:
        self.world_state = loaded_world_state or world_state()
        self.pool = loaded_pool or pool()
        default_alpha_results = (
            alpha_result("ENT_A"),
            alpha_result("ENT_B", score=None, status="inconclusive"),
        )
        self.alpha_results = tuple(
            default_alpha_results
            if loaded_alpha_results is None
            else loaded_alpha_results
        )
        default_recommendations = (
            recommendation("ENT_A", override_applied=True),
            RecommendationSnapshot(
                cycle_id="cycle_l8",
                entity_id="ENT_B",
                action_type="inconclusive",
                rating=None,
                confidence=None,
                triggered_by="system",
                override_applied=False,
                constraints_applied={},
            ),
        )
        self.recommendations = tuple(
            default_recommendations
            if loaded_recommendations is None
            else loaded_recommendations
        )
        self.calls: list[tuple[str, CycleId]] = []

    def load_world_state(self, cycle_id: CycleId) -> WorldStateSnapshot:
        self.calls.append(("world_state", cycle_id))
        return self.world_state

    def load_official_alpha_pool(self, cycle_id: CycleId) -> OfficialAlphaPool:
        self.calls.append(("pool", cycle_id))
        return self.pool

    def load_alpha_results(self, cycle_id: CycleId) -> Sequence[AlphaResultSnapshot]:
        self.calls.append(("alpha", cycle_id))
        return self.alpha_results

    def load_recommendations(self, cycle_id: CycleId) -> Sequence[RecommendationSnapshot]:
        self.calls.append(("recommendation", cycle_id))
        return self.recommendations


class RecordingPublishPort:
    def __init__(
        self,
        *,
        fail_on_object_key: str | None = None,
        fail_manifest: bool = False,
        manifest_ref: str | None = None,
    ) -> None:
        self.fail_on_object_key = fail_on_object_key
        self.fail_manifest = fail_manifest
        self.manifest_ref = manifest_ref
        self.commit_calls: list[tuple[CycleId, str, Mapping[str, Any]]] = []
        self.manifest_calls: list[
            tuple[CycleId, tuple[CommittedFormalObject, ...]]
        ] = []
        self.reserve_manifest_ref_calls: list[CycleId] = []

    def reserve_cycle_manifest_ref(
        self,
        *,
        cycle_id: CycleId,
    ) -> str:
        self.reserve_manifest_ref_calls.append(cycle_id)
        return self.manifest_ref or f"manifest/{cycle_id}"

    def commit_formal_object(
        self,
        *,
        cycle_id: CycleId,
        object_key: str,
        payload: Mapping[str, Any],
    ) -> CommittedFormalObject:
        self.commit_calls.append((cycle_id, object_key, payload))
        if object_key == self.fail_on_object_key:
            raise RuntimeError(f"commit failed for {object_key}")
        row_count = int(payload.get("count", 1))
        return CommittedFormalObject(
            object_key=object_key,
            ref=f"{object_key}/{cycle_id}/ref",
            snapshot_id=f"{object_key}-snapshot",
            payload_hash=f"{object_key}-hash",
            row_count=row_count,
        )

    def write_cycle_manifest(
        self,
        *,
        cycle_id: CycleId,
        committed_objects: Sequence[CommittedFormalObject],
        expected_manifest_ref: str | None = None,
    ) -> ManifestWriteResult:
        committed_tuple = tuple(committed_objects)
        if self.fail_manifest:
            raise RuntimeError("manifest write failed")
        manifest_ref = self.manifest_ref or f"manifest/{cycle_id}"
        if (
            expected_manifest_ref is not None
            and manifest_ref != expected_manifest_ref
        ):
            raise ManifestPublishError(
                "reserved manifest_ref does not match publish target",
            )
        self.manifest_calls.append((cycle_id, committed_tuple))
        return ManifestWriteResult(
            manifest_ref=manifest_ref,
            manifest_version="v1",
            table_snapshots={
                committed.object_key: committed.snapshot_id
                for committed in committed_tuple
            },
        )
