"""Dataclass models for audit-eval shared fixtures consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseRef:
    """Lightweight reference to a fixture case (no file content loaded yet).

    Used by ``iter_cases`` so callers can decide which cases to materialize
    without paying the JSON-parse cost upfront.
    """

    pack_name: str
    case_id: str
    case_dir: Path

    @property
    def metadata_path(self) -> Path:
        return self.case_dir / "metadata.json"

    @property
    def input_path(self) -> Path:
        return self.case_dir / "input.json"

    @property
    def context_path(self) -> Path:
        return self.case_dir / "context.json"

    @property
    def expected_path(self) -> Path:
        return self.case_dir / "expected.json"

    @property
    def manifest_refs_path(self) -> Path:
        return self.case_dir / "manifest_refs.json"


@dataclass(frozen=True)
class Case:
    """A fully loaded fixture case (5 files materialized as dict).

    Returned by ``load_case``. Consumers typically:
        - feed ``case.input`` into the unit under test
        - merge ``case.context`` for surrounding state
        - assert against ``case.expected``
        - use ``case.manifest_refs`` to verify cycle_publish_manifest binding
        - read ``case.metadata`` for golden_updated_at, contract_version, etc.
    """

    ref: CaseRef
    input: dict[str, Any]
    context: dict[str, Any]
    expected: dict[str, Any]
    manifest_refs: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return self.ref.case_id

    @property
    def pack_name(self) -> str:
        return self.ref.pack_name


__all__ = ["Case", "CaseRef"]
