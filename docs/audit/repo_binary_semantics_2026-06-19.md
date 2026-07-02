# Repo binary/large skipped-file semantic audit

- Generated: `2026-06-19T18:28:14+0800`
- Scan mode: `type_aware_semantic_audit_for_repo_skipped_files`
- Skipped files audited: `2170` / `2170`
- Semantic errors: `0`
- Missing files: `0`
- PDFs: `1494` files / `351040` pages
- SQLite DBs: `32` files / `439` schema objects
- Python bytecode: `547` files / `2` missing source files

## Semantic Kinds

| Kind | Count |
|---|---:|
| `gzip_stream` | 28 |
| `large_or_non_utf8_text` | 10 |
| `macos_ds_store` | 8 |
| `numpy_npz` | 9 |
| `pdf` | 1494 |
| `pickle_payload` | 4 |
| `png_image` | 2 |
| `python_bytecode` | 547 |
| `sqlite_database` | 32 |
| `sqlite_shm` | 18 |
| `sqlite_wal` | 18 |

## Largest Records

| Path | Kind | Bytes | Status |
|---|---|---:|---|
| `runtime/hot.sqlite` | `sqlite_database` | 2257051648 | `ok` |
| `runtime/hot.sqlite.bak.scorefix` | `sqlite_database` | 385024000 | `ok` |
| `runtime/hot.sqlite.bak.reviewfix` | `sqlite_database` | 385024000 | `ok` |
| `runtime/hot.sqlite.bak.pre_r3a.20260605_002703` | `sqlite_database` | 385024000 | `ok` |
| `runtime/hot.sqlite.bak.batch3pre` | `sqlite_database` | 385024000 | `ok` |
| `runtime/hot.sqlite.bak.pre_onboard_test` | `sqlite_database` | 384057344 | `ok` |
| `runtime/hot.sqlite.bak.precollect.20260529_222237` | `sqlite_database` | 383447040 | `ok` |
| `runtime/hot.sqlite.bak.pre_mock_cleanup.20260602_171920` | `sqlite_database` | 383447040 | `ok` |
| `runtime/hot.sqlite.bak.pre_ar_reingest.20260530_095413` | `sqlite_database` | 383447040 | `ok` |
| `runtime/hot.sqlite.bak.pre_ar_fetch.20260602_174958` | `sqlite_database` | 383447040 | `ok` |
| `runtime/hot.sqlite.bak.20260529_002303` | `sqlite_database` | 383447040 | `ok` |
| `factor_research/04_event_study/adv/full_panel.npz` | `numpy_npz` | 109710300 | `ok` |
| `runtime/annual_reports/300677.SZ/2025_annual.pdf` | `pdf` | 83217916 | `ok` |
| `runtime/annual_reports/600886.SH/2025_annual.pdf` | `pdf` | 77748102 | `ok` |
| `runtime/backtest/20260421/pit.sqlite` | `sqlite_database` | 50110464 | `ok` |
| `runtime/backtest/20260116/pit.sqlite` | `sqlite_database` | 50094080 | `ok` |
| `runtime/backtest/20260309/pit.sqlite` | `sqlite_database` | 50003968 | `ok` |
| `runtime/annual_reports/601168.SH/2025_annual.pdf` | `pdf` | 37463426 | `ok` |
| `runtime/annual_reports/600000.SH/2025_annual.pdf` | `pdf` | 36054699 | `ok` |
| `FrontEnd/.playwright-mcp/console-2026-04-24T13-35-42-909Z.log` | `large_or_non_utf8_text` | 34197151 | `ok` |

## Notes

- This audit covers every binary/large file skipped by the repo text-body audit with format classification and safe structural metadata.
- Pickle payloads are not loaded; only opcode samples are inspected to avoid code execution.
- PDF coverage records document family/path metadata and page counts, not OCR or human reading of every page.
