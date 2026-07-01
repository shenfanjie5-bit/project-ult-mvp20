from __future__ import annotations

import json
from pathlib import Path

import yaml

from mvp20.non_llm_extractors import (
    DEFAULT_CANDIDATE_CAPACITY,
    _base_score_percentiles,
    build_candidate_pool,
    clamp_capacity,
    extract_for_stock,
    slice_candidate_pool,
)
from mvp20.server import ServerConfig, handle_candidate_pool
from mvp20.storage import upsert_realtime


def _repo(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "mvp20.universe.yaml").write_text(
        yaml.safe_dump({
            "schema_version": 2,
            "constituents": [
                {
                    "ts_code": "000001.SZ",
                    "name": "One",
                    "role": "target",
                    "pool": "regular",
                    "industry_ids": ["TEST"],
                },
                {
                    "ts_code": "000002.SZ",
                    "name": "Two",
                    "role": "target",
                    "pool": "regular",
                    "industry_ids": ["TEST"],
                },
                {
                    "ts_code": "000003.SZ",
                    "name": "Three",
                    "role": "target",
                    "pool": "regular",
                    "industry_ids": ["TEST"],
                },
                {
                    "ts_code": "AAPL.US",
                    "name": "Apple",
                    "role": "target",
                    "pool": "regular",
                    "industry_ids": ["TEST"],
                },
            ],
        }),
        encoding="utf-8",
    )
    (config / "data_point_roles.yaml").write_text(
        yaml.safe_dump({"L3.product.portfolio": {"participates_in_score": True}}),
        encoding="utf-8",
    )
    return tmp_path


def test_capacity_defaults_and_clamps() -> None:
    assert clamp_capacity(None) == DEFAULT_CANDIDATE_CAPACITY
    assert clamp_capacity("bad") == DEFAULT_CANDIDATE_CAPACITY
    assert clamp_capacity(0) == 1
    assert clamp_capacity(9999) == 300


def test_base_score_percentiles_tie_aware_and_order_independent() -> None:
    forward = _base_score_percentiles({
        "AAA.SZ": {"base_score": 50.0},
        "BBB.SZ": {"base_score": 50.0},
        "CCC.SZ": {"base_score": 10.0},
    })
    reversed_order = _base_score_percentiles({
        "BBB.SZ": {"base_score": 50.0},
        "AAA.SZ": {"base_score": 50.0},
        "CCC.SZ": {"base_score": 10.0},
    })
    # Equal base_scores get equal percentiles, and the result is independent of
    # snapshot iteration order (no tie-driven rank churn across re-score runs).
    assert forward == reversed_order
    assert forward["AAA.SZ"] == forward["BBB.SZ"]
    assert forward["CCC.SZ"] == 0.0


def test_candidate_pool_tie_breaks_by_ts_code(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)

    def fake_snapshot():
        return "20260623", {
            "000002.SZ": {"base_score": 50.0},
            "000001.SZ": {"base_score": 50.0},
            "000003.SZ": {"base_score": 10.0},
        }

    monkeypatch.setattr("mvp20.pnl_loop.latest_snapshot", fake_snapshot)
    monkeypatch.setattr("mvp20.quant_score.load_artifact", lambda market="A_share": {"asof": "20260623", "rows": {}})
    monkeypatch.setattr("mvp20.non_llm_extractors.extract_for_stock", lambda *args, **kwargs: [])

    payload = build_candidate_pool(
        repo_root=repo,
        db_path=repo / "runtime" / "hot.sqlite",
        market="A",
        capacity=2,
        output_path=repo / "runtime" / "candidate_pool" / "A_share.json",
    )
    rows = payload["ranked_rows"]
    # 000001/000002 tie on base_score -> equal base_score_pct -> deterministic
    # ts_code tiebreak puts 000001 ahead of 000002.
    assert [r["ts_code"] for r in rows] == ["000001.SZ", "000002.SZ", "000003.SZ"]
    assert rows[0]["score"]["base_score_pct"] == rows[1]["score"]["base_score_pct"]


def test_candidate_pool_slices_without_reordering_artifact(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)

    def fake_snapshot():
        return "20260623", {
            "000001.SZ": {"base_score": 10.0, "trading_signal": "HOLD"},
            "000002.SZ": {"base_score": 30.0, "trading_signal": "BUY"},
            "000003.SZ": {"base_score": 20.0, "trading_signal": "WATCH"},
        }

    monkeypatch.setattr("mvp20.pnl_loop.latest_snapshot", fake_snapshot)
    monkeypatch.setattr("mvp20.quant_score.load_artifact", lambda market="A_share": {"asof": "20260623", "rows": {}})
    monkeypatch.setattr("mvp20.non_llm_extractors.extract_for_stock", lambda *args, **kwargs: [])

    artifact = repo / "runtime" / "candidate_pool" / "A_share.json"
    payload = build_candidate_pool(
        repo_root=repo,
        db_path=repo / "runtime" / "hot.sqlite",
        market="A",
        capacity=2,
        output_path=artifact,
    )
    assert payload["default_capacity"] == 80
    assert [r["ts_code"] for r in payload["ranked_rows"]] == [
        "000002.SZ",
        "000003.SZ",
        "000001.SZ",
    ]

    first = slice_candidate_pool(payload, 1)
    assert [r["ts_code"] for r in first["rows"]] == ["000002.SZ"]
    assert [r["ts_code"] for r in payload["ranked_rows"]] == [
        "000002.SZ",
        "000003.SZ",
        "000001.SZ",
    ]


def test_candidate_pool_api_capacity_changes_returned_rows(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    runtime = tmp_path / "runtime"
    artifact = runtime / "candidate_pool" / "A_share.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "schema_version": "candidate_pool.v1",
            "generated_at": "2026-06-23T00:00:00+00:00",
            "market": "A_share",
            "default_capacity": 80,
            "policy": {},
            "source_snapshot": {},
            "summary": {},
            "ranked_rows": [
                {"ts_code": "000002.SZ", "rank": 1},
                {"ts_code": "000003.SZ", "rank": 2},
            ],
        }),
        encoding="utf-8",
    )
    cfg = ServerConfig(hot_db_path=runtime / "hot.sqlite", universe_path=repo / "config" / "mvp20.universe.yaml")

    status, envelope = handle_candidate_pool(cfg, {"market": ["A"], "capacity": ["1"]})
    assert status == 200
    data = envelope["data"]
    assert data["capacity"] == 1
    assert data["returned"] == 1
    assert data["total_ranked"] == 2
    assert [r["ts_code"] for r in data["rows"]] == ["000002.SZ"]


def test_event_hit_becomes_review_packet_not_known(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "hot.sqlite"
    upsert_realtime(
        db_path,
        [(
            "000001.SZ",
            "L9.disclosure.annual_report",
            {
                "ar_year": "2025",
                "sections": {"revenue_structure": "", "customer_segment": ""},
            },
            "Known",
            0.9,
            "unit",
            1,
        )],
    )

    monkeypatch.setattr(
        "scripts.script_fill._catalysts",
        lambda ts_code, include_management_change=False: {
            "L9.company.earnings_guidance": {
                "data_status": "Known",
                "direction": "negative",
                "value": {"score": 0.5, "type": "预减"},
                "evidence_sources": [{"kind": "local_dp_id", "dp_id": "forecast"}],
            }
        },
    )
    monkeypatch.setattr("scripts.script_fill._fina_mainbz_latest_complete", lambda ts_code: (None, [], None))

    rows = extract_for_stock("000001.SZ", db_path, repo_root=tmp_path)
    event = next(r for r in rows if r["dp_id"] == "L9.company.earnings_guidance")
    assert event["data_status"] == "ReviewGated"
    assert event["value"] is None
    assert event["review_packet"]["proposed_data_status"] == "Known"
