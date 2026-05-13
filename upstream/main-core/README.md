# main-core

This module is scaffold-only.

Source of truth:

- `docs/main-core.project-doc.md`

Current workspace state:

- `docs/` keeps the source project doc
- `pyproject.toml` is placeholder project metadata
- implementation directories are created only when real work starts

Execution rule:

1. read the project doc first
2. keep work inside this module unless the issue explicitly targets shared contracts
3. do not treat this scaffold as finished implementation

Boundary checks:

- After installing development dependencies, run `bash scripts/check_boundaries.sh` to execute
  Ruff, import-linter, and the package boundary tests.
