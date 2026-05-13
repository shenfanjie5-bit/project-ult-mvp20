from __future__ import annotations

from typing import Any

import pytest

from graph_engine.evidence import evidence_refs_from_mapping, evidence_refs_from_value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        (" fact-1 ", ["fact-1"]),
        (["fact-2", "fact-1", "fact-2"], ["fact-1", "fact-2"]),
        (("fact-2", "fact-1"), ["fact-1", "fact-2"]),
        ({"fact-2", "fact-1"}, ["fact-1", "fact-2"]),
    ],
)
def test_evidence_refs_from_value_normalizes_supported_inputs(
    value: Any,
    expected: list[str],
) -> None:
    assert evidence_refs_from_value(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        ["fact-1", ""],
        ["fact-1", None],
        {"evidence_refs": ["fact-1"]},
        42,
    ],
)
def test_evidence_refs_from_value_rejects_invalid_inputs(value: Any) -> None:
    with pytest.raises(ValueError, match="evidence refs"):
        evidence_refs_from_value(value)


def test_evidence_refs_from_value_can_read_allowed_mapping() -> None:
    assert evidence_refs_from_value(
        {"evidence_ref": "fact-1", "evidence_refs": ["fact-2"]},
        allow_mapping=True,
    ) == ["fact-1", "fact-2"]


def test_evidence_refs_from_mapping_merges_singular_and_plural_refs() -> None:
    assert evidence_refs_from_mapping(
        {"evidence_ref": "fact-1", "evidence_refs": ["fact-2", "fact-1"]},
    ) == ["fact-1", "fact-2"]
