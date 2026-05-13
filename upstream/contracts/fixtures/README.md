# Contract Fixtures

These fixtures are shared JSON payloads for downstream contract tests in
`data-platform`, `subsystem-sdk`, and `main-core`. They are intentionally small
and readable, and they validate against the Pydantic models in `contracts`.

Use `fixtures/manifest.json` as the source of truth for fixture metadata:

- `path`: fixture path relative to this directory.
- `model`: import path for the declared Pydantic model.
- `schema_name`: JSON Schema artifact name from `SCHEMA_MODEL_REGISTRY`.
- `valid`: whether the payload is expected to validate.
- `consumer`: downstream consumers expected to reuse the fixture.
- `validation`: validation path used by the tests.
- `expected_exception`: expected exception for invalid fixtures.
- `expected_error_code`: expected `ContractError` code when applicable.

Valid Ex payload fixtures never include Layer B ingest metadata fields
`submitted_at` or `ingest_seq`. The `backtest_result` name is intentionally only
present in invalid fixtures because it is an analytical asset, not a formal
object.
