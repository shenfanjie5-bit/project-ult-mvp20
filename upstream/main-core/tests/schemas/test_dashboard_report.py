"""Tests for L8 dashboard and formal report schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from main_core.common.schemas import DashboardSnapshot, FormalReport


def _dashboard_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "world_state_ref": "world_state_snapshot/cycle_001",
        "pool_ref": "official_alpha_pool/cycle_001",
        "recommendation_ref": "recommendation_snapshot/cycle_001",
        "summary_cards": {"top_action": "buy"},
    }


def _report_payload() -> dict[str, object]:
    return {
        "cycle_id": "cycle_001",
        "report_type": "daily",
        "recommendation_ref": "recommendation_snapshot/cycle_001",
        "narrative_sections": {"overview": "Market risk appetite improved."},
        "appendix_refs": {"audit": "audit/cycle_001"},
    }


def test_dashboard_happy_path_round_trips_json() -> None:
    dashboard = DashboardSnapshot(**_dashboard_payload())

    assert DashboardSnapshot.from_json(dashboard.to_json()) == dashboard


def test_dashboard_missing_field_fails() -> None:
    payload = _dashboard_payload()
    payload.pop("pool_ref")

    with pytest.raises(ValidationError):
        DashboardSnapshot(**payload)


def test_dashboard_rejects_wrong_summary_cards_type() -> None:
    payload = _dashboard_payload()
    payload["summary_cards"] = []

    with pytest.raises(ValidationError):
        DashboardSnapshot(**payload)


def test_formal_report_happy_path_round_trips_json() -> None:
    report = FormalReport(**_report_payload())

    assert FormalReport.from_json(report.to_json()) == report


def test_formal_report_missing_field_fails() -> None:
    payload = _report_payload()
    payload.pop("report_type")

    with pytest.raises(ValidationError):
        FormalReport(**payload)


def test_formal_report_rejects_wrong_narrative_sections_type() -> None:
    payload = _report_payload()
    payload["narrative_sections"] = []

    with pytest.raises(ValidationError):
        FormalReport(**payload)
