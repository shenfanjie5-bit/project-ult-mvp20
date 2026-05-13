from __future__ import annotations

from typing import Any

import pytest

from graph_engine.propagation._gds import probe_gds_availability


class RecordingGDSProbeClient:
    def __init__(self, responses: list[list[dict[str, Any]] | Exception]) -> None:
        self.responses = responses
        self.read_calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append((query, parameters or {}))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.write_calls.append((query, parameters or {}))
        raise AssertionError("GDS availability probe must not write")


def test_probe_gds_availability_returns_required_procedure_facts() -> None:
    client = RecordingGDSProbeClient(
        [
            [{"gdsVersion": "2.13.1"}],
            [{"exists": False}],
        ],
    )

    result = probe_gds_availability(client)  # type: ignore[arg-type]

    assert result.gds_version == "2.13.1"
    assert result.graph_exists_procedure_available is True
    assert client.write_calls == []
    assert len(client.read_calls) == 2
    assert "gds.version" in client.read_calls[0][0]
    assert "gds.graph.exists" in client.read_calls[1][0]
    assert client.read_calls[1][1] == {"graph_name": "__graph_engine_gds_probe__"}


def test_probe_gds_availability_blocks_when_gds_version_is_missing() -> None:
    client = RecordingGDSProbeClient(
        [
            RuntimeError("There is no function with the name `gds.version` registered"),
        ],
    )

    with pytest.raises(RuntimeError, match="^GDS plugin not available$"):
        probe_gds_availability(client)  # type: ignore[arg-type]

    assert len(client.read_calls) == 1
    assert client.write_calls == []


def test_probe_gds_availability_blocks_when_graph_exists_is_missing() -> None:
    client = RecordingGDSProbeClient(
        [
            [{"gdsVersion": "2.13.1"}],
            RuntimeError(
                "There is no procedure with the name `gds.graph.exists` registered",
            ),
        ],
    )

    with pytest.raises(RuntimeError, match="^GDS plugin not available$"):
        probe_gds_availability(client)  # type: ignore[arg-type]

    assert len(client.read_calls) == 2
    assert client.write_calls == []


def test_probe_gds_availability_preserves_non_missing_runtime_errors() -> None:
    client = RecordingGDSProbeClient(
        [
            RuntimeError("gds.version failed at runtime"),
        ],
    )

    with pytest.raises(RuntimeError, match="failed at runtime"):
        probe_gds_availability(client)  # type: ignore[arg-type]

    assert client.write_calls == []
