# Repo content body audit

- Generated at: `2026-06-19T18:24:57+0800`
- Root: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20`
- Scan mode: `full_body_read_for_bounded_text_files`

## Summary

| Metric | Value |
|---|---:|
| `files_seen` | `8023` |
| `text_files_read` | `5853` |
| `text_bytes_read` | `562584191` |
| `text_lines_read` | `19227954` |
| `skipped_binary` | `2152` |
| `skipped_too_large` | `18` |
| `skipped_decode` | `0` |
| `error_count` | `0` |

## Skip Reasons

| Reason | Count |
|---|---:|
| `binary_extension:.pdf` | 1494 |
| `binary_extension:.pyc` | 547 |
| `binary_extension:.gz` | 28 |
| `binary_extension:.sqlite` | 22 |
| `too_large_for_full_text_read` | 18 |
| `binary_extension:.sqlite-shm` | 18 |
| `binary_extension:.sqlite-wal` | 18 |
| `binary_sniff` | 14 |
| `binary_extension:.npz` | 9 |
| `binary_extension:.png` | 2 |

## Largest Skipped Files

| Path | Reason | Bytes | Sample SHA-256 |
|---|---|---:|---|
| `runtime/hot.sqlite` | `binary_extension:.sqlite` | 2257051648 | `3e2ab547be78006de3eab16d411116bb5ff7cc59eb88c87e2a200043a9f777fc` |
| `runtime/hot.sqlite.bak.scorefix` | `too_large_for_full_text_read` | 385024000 | `838e30132eb481280bc0cb4d8c53b3eb4d16449ff14e9a063af552a9cad8da9c` |
| `runtime/hot.sqlite.bak.reviewfix` | `too_large_for_full_text_read` | 385024000 | `38c40e57e6ece55d4391a738f4f93ec85eb5de7b1f395b7756e55844ab9acc5b` |
| `runtime/hot.sqlite.bak.pre_r3a.20260605_002703` | `too_large_for_full_text_read` | 385024000 | `ec39845401a6aa79350deddbe6f36b742c15c84d25e65859e2a2b37ceafa9e4c` |
| `runtime/hot.sqlite.bak.batch3pre` | `too_large_for_full_text_read` | 385024000 | `60086da31f0a7eece4bcce0446e1cffcaf866a67105c8e12fa6120de8406d272` |
| `runtime/hot.sqlite.bak.pre_onboard_test` | `too_large_for_full_text_read` | 384057344 | `4ecdde495fb0b42937a86e1f34eccc61276eb55ed394ec839da53714fc8ccbe1` |
| `runtime/hot.sqlite.bak.precollect.20260529_222237` | `too_large_for_full_text_read` | 383447040 | `a8d7d9870929f902a805315fbefe6a20a351fa73b84001f536076d7eb561ae8d` |
| `runtime/hot.sqlite.bak.pre_mock_cleanup.20260602_171920` | `too_large_for_full_text_read` | 383447040 | `407383185aae55aea7e6cbafd999b1331a657b3e9dffb98ce9ff792f3c3f26ba` |
| `runtime/hot.sqlite.bak.pre_ar_reingest.20260530_095413` | `too_large_for_full_text_read` | 383447040 | `bec308f56597d74bb8898c21aecee63f9044b5b249073fb516a28c497659974c` |
| `runtime/hot.sqlite.bak.pre_ar_fetch.20260602_174958` | `too_large_for_full_text_read` | 383447040 | `0d5f46d9de0ecb4bae7e27574fe1802d379153a8fb7fc1e49cf2e20916432996` |

## Risk Markers

| Pattern | Count |
|---|---:|
| `mock` | 3137 |
| `fixture` | 2750 |
| `placeholder` | 440 |
| `stub` | 321 |
| `skeleton` | 217 |
| `TODO` | 74 |
| `NotImplemented` | 59 |
| `UPSTREAM_UNAVAILABLE` | 39 |
| `raise NotImplemented` | 26 |
| `FIXME` | 9 |

## Notes

- This audit reads full bodies for bounded text files and records SHA-256 digests.
- Binary files, PDFs, SQLite databases, parquet/npz payloads, and text files above the size threshold are counted by reason and fully listed with head/tail SHA-256 fingerprints.
- The audit proves body-level text access and fingerprinting, not human semantic review of every file.
