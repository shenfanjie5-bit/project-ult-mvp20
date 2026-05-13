"""Tests for L8 formal report builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from main_core.common.errors import ManifestPublishError
from main_core.common.schemas import PublishBundle
from main_core.l8_publish import build_formal_report, prepare_publish_bundle
from main_core.l8_publish.refs import RECOMMENDATION_SNAPSHOT_KEY
from tests.l8_publish import FakeFormalObjectSource, RecordingPublishPort, pool


def test_build_formal_report_happy_path() -> None:
    bundle = _base_bundle()

    report = build_formal_report("cycle_l8", bundle)

    assert report.cycle_id == "cycle_l8"
    assert report.report_type == "daily"
    assert report.recommendation_ref == "recommendation_snapshot/cycle_l8/ref"
    assert set(report.narrative_sections) == {
        "overview",
        "world_state",
        "pool_changes",
        "recommendation_summary",
        "inconclusive_summary",
        "override_summary",
    }
    assert report.appendix_refs == {
        "world_state_ref": "world_state_snapshot/cycle_l8/ref",
        "pool_ref": "official_alpha_pool/cycle_l8/ref",
        "alpha_result_ref": "alpha_result_snapshot/cycle_l8/ref",
        "recommendation_ref": "recommendation_snapshot/cycle_l8/ref",
        "manifest_ref": "manifest/cycle_l8",
        "audit_payload_ref": "audit_payload/cycle_l8",
    }


def test_build_formal_report_rejects_missing_ref() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["formal_objects"][RECOMMENDATION_SNAPSHOT_KEY].pop("ref")
    )

    with pytest.raises(ManifestPublishError, match="ref"):
        build_formal_report("cycle_l8", bundle)


def test_build_formal_report_rejects_missing_manifest_ref() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload["manifest_candidate"].pop("manifest_ref")
    )

    with pytest.raises(ManifestPublishError, match="manifest_ref"):
        build_formal_report("cycle_l8", bundle)


def test_build_formal_report_rejects_cycle_mismatch() -> None:
    bundle = _mutated_bundle(
        lambda payload: payload.__setitem__("cycle_id", "cycle_other")
    )

    with pytest.raises(ManifestPublishError, match="cycle_id"):
        build_formal_report("cycle_l8", bundle)


def test_build_formal_report_keeps_inconclusive_outcomes_visible() -> None:
    report = build_formal_report("cycle_l8", _base_bundle()).model_dump(mode="json")

    inconclusive = report["narrative_sections"]["inconclusive_summary"]
    assert inconclusive["alpha_inconclusive_count"] == 1
    assert inconclusive["recommendation_inconclusive_count"] == 1
    assert inconclusive["alpha_entity_ids"] == ["ENT_B"]
    assert inconclusive["recommendation_entity_ids"] == ["ENT_B"]
    assert "Inconclusive outcomes remain explicit" in inconclusive["summary"]


def test_build_formal_report_counts_override_applied_recommendations() -> None:
    report = build_formal_report("cycle_l8", _base_bundle()).model_dump(mode="json")

    assert report["narrative_sections"]["override_summary"] == {
        "summary": "Human overrides applied to 1 recommendations.",
        "override_applied_count": 1,
        "entity_ids": ["ENT_A"],
    }
    assert report["narrative_sections"]["recommendation_summary"][
        "override_applied_count"
    ] == 1


def test_build_formal_report_allows_empty_recommendation_list() -> None:
    bundle = _base_bundle(
        FakeFormalObjectSource(
            loaded_pool=pool(()),
            loaded_alpha_results=[],
            loaded_recommendations=[],
        )
    )

    report = build_formal_report("cycle_l8", bundle)

    assert report.narrative_sections["recommendation_summary"]["by_action"] == {
        "buy": 0,
        "hold": 0,
        "reduce": 0,
        "inconclusive": 0,
    }
    assert report.narrative_sections["inconclusive_summary"][
        "summary"
    ] == "No inconclusive alpha results or recommendations for this cycle."


def _base_bundle(source: FakeFormalObjectSource | None = None) -> PublishBundle:
    return prepare_publish_bundle(
        "cycle_l8",
        source=source or FakeFormalObjectSource(),
        publish_port=RecordingPublishPort(),
        derived_builders=(),
    )


def _mutated_bundle(mutator: Callable[[dict[str, Any]], None]) -> PublishBundle:
    payload = _base_bundle().model_dump(mode="python")
    mutator(payload)
    return PublishBundle(**payload)
