from __future__ import annotations

import json

from graph_engine.live_metrics import read_live_graph_metric_payload


class FakeTemporal:
    def isoformat(self) -> str:
        return "2026-04-28T01:02:03+00:00"


class FakeMetricsClient:
    def execute_read(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "node_count": 1,
                "edge_count": 0,
                "label_counts": [{"label": "Entity", "count": 1}],
                "nodes": [
                    {
                        "labels": ["Entity"],
                        "node_id": "node-1",
                        "canonical_entity_id": "entity-1",
                        "properties": {
                            "node_id": "node-1",
                            "created_at": FakeTemporal(),
                        },
                    },
                ],
                "relationships": [],
            },
        ]


def test_live_metric_payload_normalizes_driver_temporals_to_jsonable_values() -> None:
    metrics = read_live_graph_metric_payload(FakeMetricsClient())  # type: ignore[arg-type]

    assert metrics.nodes[0]["properties"] == {
        "node_id": "node-1",
        "created_at": "2026-04-28T01:02:03+00:00",
    }
    json.dumps(metrics.nodes)
