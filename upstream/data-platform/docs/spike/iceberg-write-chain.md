# Iceberg Write Chain Spike

Generated at: 2026-04-27T05:53:39+00:00
Latest evidence update: 2026-05-04 post-merge run

## Environment

- Python: 3.12.12
- Platform: macOS-26.3.1-arm64-arm-64bit
- PyIceberg: 0.11.1
- PyArrow: 24.0.0
- SQLAlchemy: 2.0.49

## Results

### 2026-05-04 post-merge run

Command shape:

```bash
DATABASE_URL=<redacted> DP_PG_DSN=<redacted> .venv/bin/pytest -m spike tests/spike/test_iceberg_write_chain.py -v
```

Result: 3 passed, 0 failed, 0 skipped, 0 errors in 1.25s.

Covered tests:

- `test_add_column_backward_compat`
- `test_time_travel_by_snapshot`
- `test_concurrent_overwrite`

Runtime note: used the local `.env` PG DSN with temporary schema behavior
because `CREATE DATABASE` privilege was unavailable. No primary worktree
artifacts were created.

### Recorded report table

| Case | Status | Duration ms | Detail |
|------|--------|-------------|--------|
| `add_column_backward_compat` | pass | 309 | pass |
| `time_travel_by_snapshot` | pass | 79 | pass |
| `concurrent_overwrite` | pass | 113 | pass |

## Conclusion

- Completed cases: 3/3
- Conclusion: pass
- P1a Iceberg 写入链 spike 成功率: 100%

## Risk Notes

- PG-backed SQL catalog validated for schema evolution, snapshot time travel, and optimistic commit conflict handling.
- Lite filesystem warehouse only; S3/MinIO is intentionally out of scope.
- PostgreSQL metadata schema is temporary and dropped after each test.
