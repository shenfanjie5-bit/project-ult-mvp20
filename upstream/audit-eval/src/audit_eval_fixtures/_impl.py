"""Implementation of the audit_eval_fixtures public API.

Storage layout (under ``audit_eval_fixtures/data/``):

    <pack_name>/
        <case_id>/
            input.json          — the input the case feeds into the unit under test
            context.json        — surrounding state, prior cycle artifacts, etc.
            expected.json       — golden output to assert against
            manifest_refs.json  — cycle_publish_manifest snapshot ids this case binds to
            metadata.json       — fixture_id, source_module, contract_version,
                                  created_from_cycle_id, fixture_kind,
                                  golden_updated_at, notes, ...

JSON (not YAML) is used to avoid pulling in PyYAML as a runtime dep on the
consumer side. Metadata is a flat dict so it round-trips cleanly with json.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from pathlib import Path

from audit_eval_fixtures._models import Case, CaseRef

_PACKAGE = "audit_eval_fixtures"
_DATA_SUBDIR = "data"
_REQUIRED_FILES = (
    "input.json",
    "context.json",
    "expected.json",
    "manifest_refs.json",
    "metadata.json",
)


class FixtureError(Exception):
    """Raised when a fixture pack/case is missing or malformed."""


def _data_root() -> Path:
    """Return the on-disk path of the package's bundled ``data/`` dir."""
    # importlib.resources.files() works for installed wheels and for editable
    # installs. The returned object is a Traversable, but in practice (for a
    # plain package_data layout) it's a concrete pathlib.Path.
    root = resources.files(_PACKAGE) / _DATA_SUBDIR
    # ``resources.as_file`` would be safer for ZIP imports, but our wheel is
    # a regular sdist/wheel so the path is on disk.
    return Path(str(root))


def fixture_root(pack_name: str) -> Path:
    """Return the on-disk root of a fixture pack."""
    pack_dir = _data_root() / pack_name
    if not pack_dir.is_dir():
        raise FixtureError(
            f"unknown fixture pack {pack_name!r}; "
            f"expected directory at {pack_dir}"
        )
    return pack_dir


def iter_cases(pack_name: str) -> Iterator[CaseRef]:
    """Yield every case in a pack as a lightweight CaseRef (no I/O on contents).

    Cases are yielded in lexicographic order by case_id for deterministic
    test execution.
    """
    pack_dir = fixture_root(pack_name)
    case_dirs = sorted(
        p for p in pack_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    for case_dir in case_dirs:
        yield CaseRef(
            pack_name=pack_name, case_id=case_dir.name, case_dir=case_dir
        )


def load_case(pack_name: str, case_id: str) -> Case:
    """Load all 5 files of a single case into memory."""
    case_dir = fixture_root(pack_name) / case_id
    if not case_dir.is_dir():
        raise FixtureError(
            f"unknown case {case_id!r} in pack {pack_name!r}; "
            f"expected directory at {case_dir}"
        )

    missing = [name for name in _REQUIRED_FILES if not (case_dir / name).is_file()]
    if missing:
        raise FixtureError(
            f"case {pack_name}/{case_id} missing required files: {missing}"
        )

    payloads = {
        name: json.loads((case_dir / name).read_text(encoding="utf-8"))
        for name in _REQUIRED_FILES
    }

    ref = CaseRef(pack_name=pack_name, case_id=case_id, case_dir=case_dir)
    return Case(
        ref=ref,
        input=payloads["input.json"],
        context=payloads["context.json"],
        expected=payloads["expected.json"],
        manifest_refs=payloads["manifest_refs.json"],
        metadata=payloads["metadata.json"],
    )


def fixture_version() -> str:
    """Return a version string for the bundled fixture corpus.

    Tracks the audit-eval package version exactly. Consumers can pin against
    this when their regression goldens are fragile.
    """
    from audit_eval import __version__

    return __version__


def list_packs() -> list[str]:
    """Return all available pack names (deterministic, sorted)."""
    root = _data_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


__all__ = [
    "Case",
    "CaseRef",
    "FixtureError",
    "fixture_root",
    "fixture_version",
    "iter_cases",
    "list_packs",
    "load_case",
]
