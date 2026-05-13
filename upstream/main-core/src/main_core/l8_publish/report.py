"""Formal report builders for L8 publication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import DashboardSnapshot, FormalReport, PublishBundle
from main_core.common.types import CycleId
from main_core.l8_publish.dashboard import (
    DASHBOARD_SNAPSHOT_KEY,
    _as_mapping,
    _as_payload_list,
    _build_summary_cards,
    _extract_required_formal_objects,
    _RequiredFormalObjects,
    build_dashboard_snapshot,
)

FORMAL_REPORT_KEY = "report"


def build_formal_report(
    cycle_id: CycleId,
    bundle: PublishBundle,
    *,
    report_type: str = "daily",
) -> FormalReport:
    """Build deterministic analyst-facing report content from published refs."""

    requested_cycle_id = CycleId(str(cycle_id))
    objects = _extract_required_formal_objects(requested_cycle_id, bundle)
    summary_cards = _build_summary_cards(objects)

    return FormalReport(
        cycle_id=requested_cycle_id,
        report_type=report_type,
        recommendation_ref=objects.recommendations.ref,
        narrative_sections=_build_narrative_sections(objects, summary_cards),
        appendix_refs=_build_appendix_refs(requested_cycle_id, bundle, objects),
    )


def build_dashboard_and_report(
    cycle_id: CycleId,
    bundle: PublishBundle,
) -> Mapping[str, DashboardSnapshot | FormalReport]:
    """Build all deterministic L8 derived formal objects for a publish cycle."""

    dashboard = build_dashboard_snapshot(cycle_id, bundle)
    report = build_formal_report(cycle_id, bundle)
    return {
        DASHBOARD_SNAPSHOT_KEY: dashboard,
        FORMAL_REPORT_KEY: report,
    }


def _build_narrative_sections(
    objects: _RequiredFormalObjects,
    summary_cards: Mapping[str, Any],
) -> dict[str, Any]:
    world_state = _as_mapping(objects.world_state.payload)
    pool = _as_mapping(objects.pool.payload)
    alpha_results = _as_payload_list(objects.alpha_results.payload)
    recommendations = _as_payload_list(objects.recommendations.payload)

    by_action = dict(summary_cards["recommendations"]["by_action"])
    selected_count = summary_cards["pool"]["selected_count"]
    recommendation_count = summary_cards["recommendations"]["total_count"]
    final_regime = world_state.get("final_regime")
    alpha_inconclusive = summary_cards["inconclusive"]["alpha_entity_ids"]
    recommendation_inconclusive = summary_cards["inconclusive"][
        "recommendation_entity_ids"
    ]
    override_entity_ids = summary_cards["overrides"]["entity_ids"]

    return {
        "overview": {
            "summary": (
                f"{final_regime} regime with {selected_count} selected entities "
                f"and {recommendation_count} current-cycle recommendations."
            ),
            "recommendation_mix": by_action,
        },
        "world_state": {
            "baseline_regime": world_state.get("baseline_regime"),
            "llm_delta": world_state.get("llm_delta"),
            "final_regime": final_regime,
            "rationale": world_state.get("llm_rationale"),
            "fallback_path": world_state.get("fallback_path", []),
        },
        "pool_changes": {
            "selected_count": selected_count,
            "capacity": summary_cards["pool"]["capacity"],
            "added_entities": _string_list(pool.get("added_entities", [])),
            "removed_entities": _string_list(pool.get("removed_entities", [])),
            "freeze_reason_map": dict(pool.get("freeze_reason_map", {})),
        },
        "recommendation_summary": {
            "by_action": by_action,
            "entity_ids_by_action": _entity_ids_by_action(recommendations),
            "override_applied_count": summary_cards["recommendations"][
                "override_applied_count"
            ],
        },
        "inconclusive_summary": {
            "summary": _inconclusive_summary(
                alpha_entity_ids=alpha_inconclusive,
                recommendation_entity_ids=recommendation_inconclusive,
            ),
            "alpha_inconclusive_count": len(alpha_inconclusive),
            "recommendation_inconclusive_count": len(recommendation_inconclusive),
            "alpha_entity_ids": alpha_inconclusive,
            "recommendation_entity_ids": recommendation_inconclusive,
            "alpha_result_count": len(alpha_results),
        },
        "override_summary": {
            "summary": _override_summary(override_entity_ids),
            "override_applied_count": len(override_entity_ids),
            "entity_ids": override_entity_ids,
        },
    }


def _build_appendix_refs(
    cycle_id: CycleId,
    bundle: PublishBundle,
    objects: _RequiredFormalObjects,
) -> dict[str, Any]:
    return {
        "world_state_ref": objects.world_state.ref,
        "pool_ref": objects.pool.ref,
        "alpha_result_ref": objects.alpha_results.ref,
        "recommendation_ref": objects.recommendations.ref,
        "manifest_ref": _manifest_ref(cycle_id, bundle),
        "audit_payload_ref": _audit_payload_ref(cycle_id, bundle),
    }


def _manifest_ref(cycle_id: CycleId, bundle: PublishBundle) -> str:
    _ensure_same_cycle("manifest_candidate", bundle.manifest_candidate, cycle_id)
    manifest_ref = bundle.manifest_candidate.get("manifest_ref")
    if isinstance(manifest_ref, str) and manifest_ref:
        _ensure_ref_points_to_cycle("manifest_ref", manifest_ref, cycle_id)
        return manifest_ref
    raise ManifestPublishError(
        "manifest_candidate.manifest_ref must be reserved before formal report build",
    )


def _audit_payload_ref(cycle_id: CycleId, bundle: PublishBundle) -> str:
    _ensure_same_cycle("audit_payload", bundle.audit_payload, cycle_id)
    for key in ("audit_payload_ref", "ref"):
        value = bundle.audit_payload.get(key)
        if isinstance(value, str) and value:
            _ensure_ref_points_to_cycle(key, value, cycle_id)
            return value
    return f"audit_payload/{cycle_id}"


def _ensure_same_cycle(
    payload_name: str,
    payload: Mapping[str, Any],
    cycle_id: CycleId,
) -> None:
    payload_cycle_id = payload.get("cycle_id")
    if payload_cycle_id is not None and payload_cycle_id != str(cycle_id):
        raise ManifestPublishError(f"{payload_name}.cycle_id must match")


def _ensure_ref_points_to_cycle(
    ref_name: str,
    ref: str,
    cycle_id: CycleId,
) -> None:
    if str(cycle_id) not in ref:
        raise ManifestPublishError(f"{ref_name} must point to requested cycle_id")


def _entity_ids_by_action(
    recommendations: tuple[Mapping[str, Any], ...],
) -> dict[str, list[str]]:
    entity_ids_by_action = {
        "buy": [],
        "hold": [],
        "reduce": [],
        "inconclusive": [],
    }
    for recommendation in recommendations:
        action_type = str(recommendation.get("action_type", ""))
        entity_ids_by_action.setdefault(action_type, []).append(
            str(recommendation.get("entity_id", ""))
        )
    return entity_ids_by_action


def _inconclusive_summary(
    *,
    alpha_entity_ids: list[str],
    recommendation_entity_ids: list[str],
) -> str:
    if alpha_entity_ids or recommendation_entity_ids:
        return (
            "Inconclusive outcomes remain explicit for analyst review: "
            f"{len(alpha_entity_ids)} alpha results and "
            f"{len(recommendation_entity_ids)} recommendations."
        )
    return "No inconclusive alpha results or recommendations for this cycle."


def _override_summary(entity_ids: list[str]) -> str:
    if entity_ids:
        return f"Human overrides applied to {len(entity_ids)} recommendations."
    return "No human overrides applied for this cycle."


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value]


__all__ = [
    "FORMAL_REPORT_KEY",
    "build_dashboard_and_report",
    "build_formal_report",
]
