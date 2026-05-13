from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_SRC = PROJECT_ROOT.parent / "contracts" / "src"
MIN_CONTRACTS_VERSION = (0, 1, 3)


def _installed_contracts_version() -> tuple[int, int, int] | None:
    try:
        raw_version = version("project-ult-contracts")
    except PackageNotFoundError:
        return None
    try:
        major, minor, patch = raw_version.split(".", maxsplit=2)
        return int(major), int(minor), int(patch)
    except ValueError:
        return None


installed_contracts_version = _installed_contracts_version()
if (
    CONTRACTS_SRC.exists()
    and (
        installed_contracts_version is None
        or installed_contracts_version < MIN_CONTRACTS_VERSION
    )
):
    sys.path.insert(0, str(CONTRACTS_SRC))
