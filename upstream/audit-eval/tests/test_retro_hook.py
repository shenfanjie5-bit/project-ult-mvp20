from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import pytest

from audit_eval.audit import (
    DuckDBReplayRepository,
    ManagedDuckDBFormalAuditStorageAdapter,
)
from audit_eval.contracts import AuditRecord, CyclePublishManifestDraft, ReplayRecord
from audit_eval.contracts.common import RetrospectiveHorizon
from audit_eval.retro import (
    InMemoryRetrospectiveHookStatusStorage,
    MarketOutcome,
    RetrospectiveHookError,
    RetrospectiveHookRequest,
    RetrospectiveInputError,
    RetrospectiveTarget,
    run_real_retrospective_hook,
)

CYCLE_ID = "CYCLE_20260415"
OBJECT_REF = "recommendation_snapshot"
SNAPSHOT_REF = "data-platform://formal/recommendation_snapshot/snapshots/104"
AUDIT_ID = "audit-CYCLE_20260415-L7-recommendation_snapshot"
REPLAY_ID = "replay-CYCLE_20260415-recommendation_snapshot"


class StaticRepository:
    def __init__(
        self,
        *,
        replay_records: Sequence[ReplayRecord] = (),
        audit_records: Sequence[AuditRecord] = (),
    ) -> None:
        self.replay_by_id = {record.replay_id: record for record in replay_records}
        self.replay_by_object = {
            (record.cycle_id, record.object_ref): record for record in replay_records
        }
        self.audit_by_id = {record.record_id: record for record in audit_records}

    def get_replay_record(
        self,
        cycle_id: str,
        object_ref: str,
    ) -> ReplayRecord | None:
        return self.replay_by_object.get((cycle_id, object_ref))

    def get_replay_record_by_id(self, replay_id: str) -> ReplayRecord | None:
        return self.replay_by_id.get(replay_id)

    def get_audit_records(self, record_ids: Sequence[str]) -> list[AuditRecord]:
        return [
            self.audit_by_id[record_id]
            for record_id in record_ids
            if record_id in self.audit_by_id
        ]


class MissingManifestGateway:
    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        raise KeyError(cycle_id)


class StaticManifestGateway:
    def __init__(self, manifest: CyclePublishManifestDraft | None = None) -> None:
        self.manifest = manifest or _manifest()
        self.calls: list[str] = []

    def load(self, cycle_id: str) -> CyclePublishManifestDraft:
        self.calls.append(cycle_id)
        return self.manifest


class MissingOutcomeGateway:
    def list_targets(
        self,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> Sequence[RetrospectiveTarget]:
        return (RetrospectiveTarget(CYCLE_ID, OBJECT_REF),)

    def load_market_outcome(
        self,
        target: RetrospectiveTarget,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> MarketOutcome:
        raise RetrospectiveInputError("real outcome row is not available")


class StaticOutcomeGateway:
    def __init__(self, outcome: MarketOutcome) -> None:
        self.outcome = outcome

    def list_targets(
        self,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> Sequence[RetrospectiveTarget]:
        return (RetrospectiveTarget(CYCLE_ID, OBJECT_REF),)

    def load_market_outcome(
        self,
        target: RetrospectiveTarget,
        horizon: RetrospectiveHorizon,
        date_ref: date,
    ) -> MarketOutcome:
        return self.outcome


def _manifest() -> CyclePublishManifestDraft:
    return CyclePublishManifestDraft(
        published_cycle_id=CYCLE_ID,
        published_at=datetime(2026, 4, 15, 16, tzinfo=timezone.utc),
        snapshot_refs={OBJECT_REF: SNAPSHOT_REF},
    )


def _audit_record(
    *,
    record_id: str = AUDIT_ID,
    params_snapshot: dict[str, Any] | None = None,
) -> AuditRecord:
    return AuditRecord(
        record_id=record_id,
        cycle_id=CYCLE_ID,
        layer="L7",
        object_ref=OBJECT_REF,
        params_snapshot=params_snapshot
        or {"source": "production", "code_version": {"git_commit_hash": "abc123"}},
        llm_lineage={"called": False, "provider": "litellm"},
        llm_cost={},
        sanitized_input=None,
        input_hash=None,
        raw_output=None,
        parsed_result={
            "retrospective_seed": {
                "trend_score": 1.0,
                "risk_score": 2.0,
                "baseline_vs_llm_breakdown": {"layer": "L7"},
            }
        },
        output_hash=None,
        degradation_flags={},
        created_at=datetime(2026, 4, 15, 16, 1, tzinfo=timezone.utc),
    )


def _replay_record(
    *,
    replay_id: str = REPLAY_ID,
    audit_record_ids: Sequence[str] = (AUDIT_ID,),
) -> ReplayRecord:
    return ReplayRecord(
        replay_id=replay_id,
        cycle_id=CYCLE_ID,
        object_ref=OBJECT_REF,
        audit_record_ids=list(audit_record_ids),
        manifest_cycle_id=CYCLE_ID,
        formal_snapshot_refs={OBJECT_REF: SNAPSHOT_REF},
        graph_snapshot_ref=None,
        dagster_run_id="dagster-run-CYCLE_20260415",
        replay_mode="read_history",
        created_at=datetime(2026, 4, 15, 16, 2, tzinfo=timezone.utc),
    )


def _request(**updates: Any) -> RetrospectiveHookRequest:
    payload: dict[str, Any] = {
        "cycle_id": CYCLE_ID,
        "date_ref": date(2026, 4, 15),
        "manifest": _manifest(),
        "replay_ids": (REPLAY_ID,),
        "audit_record_ids": (AUDIT_ID,),
        "horizons": ("T+1",),
    }
    payload.update(updates)
    return RetrospectiveHookRequest(**payload)


def test_real_retrospective_hook_manifest_missing_fails_closed() -> None:
    request = RetrospectiveHookRequest(
        cycle_id=CYCLE_ID,
        date_ref=date(2026, 4, 15),
        manifest_ref=CYCLE_ID,
        replay_ids=(REPLAY_ID,),
        horizons=("T+1",),
    )

    with pytest.raises(RetrospectiveHookError, match="cycle_publish_manifest"):
        run_real_retrospective_hook(
            request,
            repository=StaticRepository(),
            manifest_gateway=MissingManifestGateway(),
        )


def test_real_retrospective_hook_missing_replay_or_audit_fails_closed() -> None:
    with pytest.raises(RetrospectiveHookError, match="replay_record"):
        run_real_retrospective_hook(
            _request(),
            repository=StaticRepository(audit_records=(_audit_record(),)),
        )

    replay = _replay_record()
    with pytest.raises(RetrospectiveHookError, match="audit_record"):
        run_real_retrospective_hook(
            _request(),
            repository=StaticRepository(replay_records=(replay,)),
        )


def test_real_retrospective_hook_can_require_durable_manifest_gateway() -> None:
    with pytest.raises(RetrospectiveHookError, match="durable cycle_publish_manifest"):
        run_real_retrospective_hook(
            _request(),
            repository=StaticRepository(
                replay_records=(_replay_record(),),
                audit_records=(_audit_record(),),
            ),
            require_manifest_gateway=True,
        )

    manifest_gateway = StaticManifestGateway()
    result = run_real_retrospective_hook(
        _request(),
        repository=StaticRepository(
            replay_records=(_replay_record(),),
            audit_records=(_audit_record(),),
        ),
        manifest_gateway=manifest_gateway,
        require_manifest_gateway=True,
        as_of_date=date(2026, 4, 15),
    )

    assert manifest_gateway.calls == [CYCLE_ID]
    assert result.manifest_cycle_id == CYCLE_ID


def test_real_retrospective_hook_rejects_in_memory_manifest_mismatch_when_durable_required() -> None:
    stale_manifest = _manifest().model_copy(
        update={"snapshot_refs": {OBJECT_REF: "data-platform://formal/stale/snapshots/1"}},
    )

    with pytest.raises(RetrospectiveHookError, match="durable manifest.*snapshot_refs"):
        run_real_retrospective_hook(
            _request(manifest=stale_manifest),
            repository=StaticRepository(
                replay_records=(_replay_record(),),
                audit_records=(_audit_record(),),
            ),
            manifest_gateway=StaticManifestGateway(),
            require_manifest_gateway=True,
        )


@pytest.mark.parametrize("marker", ["smoke", "fixture", "historical"])
def test_real_retrospective_hook_forbidden_provenance_fails_closed(
    marker: str,
) -> None:
    request = _request(provenance={"source": f"production-{marker}"})

    with pytest.raises(RetrospectiveHookError, match=marker):
        run_real_retrospective_hook(
            request,
            repository=StaticRepository(
                replay_records=(_replay_record(),),
                audit_records=(_audit_record(),),
            ),
        )


@pytest.mark.parametrize("marker", ["smoke", "fixture", "historical"])
def test_real_retrospective_hook_forbidden_audit_payload_provenance_fails_closed(
    marker: str,
) -> None:
    audit_record = _audit_record().model_copy(
        update={
            "parsed_result": {
                "retrospective_seed": {
                    "trend_score": 1.0,
                    "risk_score": 2.0,
                    "baseline_vs_llm_breakdown": {"source": marker},
                }
            }
        }
    )

    with pytest.raises(RetrospectiveHookError, match=marker):
        run_real_retrospective_hook(
            _request(),
            repository=StaticRepository(
                replay_records=(_replay_record(),),
                audit_records=(audit_record,),
            ),
        )


@pytest.mark.parametrize("marker", ["smoke", "fixture", "historical"])
def test_real_retrospective_hook_forbidden_outcome_provenance_fails_closed(
    marker: str,
) -> None:
    outcome = MarketOutcome(
        cycle_id=CYCLE_ID,
        object_ref=OBJECT_REF,
        horizon="T+1",
        realized_trend_score=1.0,
        realized_risk_score=2.0,
        hit_rate_rel=None,
        baseline_vs_llm_breakdown={"source": marker},
    )

    with pytest.raises(RetrospectiveHookError, match=marker):
        run_real_retrospective_hook(
            _request(),
            repository=StaticRepository(
                replay_records=(_replay_record(),),
                audit_records=(_audit_record(),),
            ),
            input_gateway=StaticOutcomeGateway(outcome),
            as_of_date=date(2026, 4, 16),
        )


def test_real_retrospective_hook_durable_duckdb_query_succeeds(tmp_path) -> None:
    db_path = tmp_path / "audit_eval.duckdb"
    storage = ManagedDuckDBFormalAuditStorageAdapter(db_path)
    audit_record = _audit_record()
    replay_record = _replay_record()
    storage.append_audit_records([audit_record])
    storage.append_replay_records([replay_record])
    manifest_gateway = StaticManifestGateway()
    status_storage = InMemoryRetrospectiveHookStatusStorage()

    result = run_real_retrospective_hook(
        _request(),
        repository=DuckDBReplayRepository(db_path),
        manifest_gateway=manifest_gateway,
        require_manifest_gateway=True,
        status_storage=status_storage,
        as_of_date=date(2026, 4, 15),
        recorded_at=datetime(2026, 4, 15, 16, 5, tzinfo=timezone.utc),
    )

    assert manifest_gateway.calls == [CYCLE_ID]
    assert result.replay_ids == (REPLAY_ID,)
    assert result.audit_record_ids == (AUDIT_ID,)
    assert result.completed_evaluation_ids == ()
    assert len(result.statuses) == 1
    status = result.statuses[0]
    assert status.status == "pending"
    assert status.reason == "outcome_not_mature"
    assert status.evaluation_id is None
    assert result.recorded_status_ids == (status.status_id,)
    assert status_storage.rows[0]["replay_id"] == REPLAY_ID


def test_real_retrospective_hook_t_plus_1_unavailable_returns_pending() -> None:
    status_storage = InMemoryRetrospectiveHookStatusStorage()

    result = run_real_retrospective_hook(
        _request(),
        repository=StaticRepository(
            replay_records=(_replay_record(),),
            audit_records=(_audit_record(),),
        ),
        input_gateway=MissingOutcomeGateway(),
        status_storage=status_storage,
        as_of_date=date(2026, 4, 16),
        recorded_at=datetime(2026, 4, 16, 9, tzinfo=timezone.utc),
    )

    assert result.completed_evaluation_ids == ()
    assert len(result.pending_statuses) == 1
    status = result.pending_statuses[0]
    assert status.horizon == "T+1"
    assert status.status == "pending"
    assert status.reason == "outcome_unavailable"
    assert status.evaluation_id is None
    assert status_storage.rows[0]["status"] == "pending"
    assert "trend_deviation" not in status_storage.rows[0]
    assert "learning_score" not in status_storage.rows[0]
