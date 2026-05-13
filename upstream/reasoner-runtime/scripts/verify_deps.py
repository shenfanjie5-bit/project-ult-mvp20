from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"\s*(?P<operator>==)?\s*(?P<version>[^\s\\;]+)?"
)
_HASH_RE = re.compile(r"--hash\s*=\s*sha256:(?P<hash>[^\s\\]+)")
_VALID_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class LockedRequirement:
    package: str
    version: str | None
    hashes: tuple[str, ...]
    raw: str


def parse_requirements(path: Path) -> dict[str, LockedRequirement]:
    requirements: dict[str, LockedRequirement] = {}
    for logical_line in _logical_requirement_lines(path):
        match = _REQUIREMENT_RE.match(logical_line)
        if match is None:
            continue

        package = match.group("name")
        if not package:
            continue

        normalized_package = _normalize_package_name(package)
        version = match.group("version") if match.group("operator") == "==" else None
        hashes = tuple(
            hash_match.group("hash") for hash_match in _HASH_RE.finditer(logical_line)
        )
        requirements[normalized_package] = LockedRequirement(
            package=package,
            version=version,
            hashes=hashes,
            raw=logical_line,
        )
    return requirements


def verify_dependency_hashes(
    path: Path,
    packages: Iterable[str] = ("litellm", "instructor"),
) -> list[str]:
    requirements = parse_requirements(path)
    errors: list[str] = []

    for package in packages:
        normalized_package = _normalize_package_name(package)
        requirement = requirements.get(normalized_package)
        if requirement is None:
            errors.append(f"{package} is missing from {path}")
            continue
        if requirement.version is None:
            errors.append(f"{requirement.package} must be pinned with ==")
        if not requirement.hashes:
            errors.append(f"{requirement.package} must include a sha256 hash")
        for hash_value in requirement.hashes:
            if _VALID_SHA256_RE.fullmatch(hash_value) is None:
                errors.append(
                    f"{requirement.package} has an invalid sha256 hash: {hash_value}"
                )

    return errors


def verify_all_requirements_locked(path: Path) -> list[str]:
    errors: list[str] = []
    for logical_line in _logical_requirement_lines(path):
        if logical_line.startswith("-"):
            continue

        match = _REQUIREMENT_RE.match(logical_line)
        if match is None or not match.group("name"):
            errors.append(f"unrecognized requirement line: {logical_line}")
            continue

        package = match.group("name")
        version = match.group("version") if match.group("operator") == "==" else None
        hashes = tuple(
            hash_match.group("hash") for hash_match in _HASH_RE.finditer(logical_line)
        )
        if version is None:
            errors.append(f"{package} must be pinned with ==")
        if not hashes:
            errors.append(f"{package} must include a sha256 hash")
        for hash_value in hashes:
            if _VALID_SHA256_RE.fullmatch(hash_value) is None:
                errors.append(f"{package} has an invalid sha256 hash: {hash_value}")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "usage: verify_deps.py REQUIREMENTS [--all] [PACKAGE ...]",
            file=sys.stderr,
        )
        return 2

    path = Path(args[0])
    require_all = "--all" in args[1:]
    packages = [arg for arg in args[1:] if arg != "--all"] or [
        "litellm",
        "instructor",
    ]
    errors = verify_dependency_hashes(path, packages)
    if require_all:
        errors.extend(verify_all_requirements_locked(path))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    return 0


def _logical_requirement_lines(path: Path) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = _strip_comment(raw_line).strip()
        if not stripped:
            continue

        if stripped.endswith("\\"):
            current += stripped[:-1].rstrip() + " "
            continue

        current += stripped
        lines.append(current.strip())
        current = ""

    if current:
        lines.append(current.strip())

    return lines


def _strip_comment(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    return line.split(" #", 1)[0]


def _normalize_package_name(package: str) -> str:
    return package.replace("_", "-").lower()


if __name__ == "__main__":
    raise SystemExit(main())
