# DOCKCASE CSV file evidence audit

- Generated: `2026-06-19T02:45:06+0800`
- Data root: `/Volumes/dockcase2tb/database_all`
- Scan mode: `all_business_csv_file_evidence`
- Elapsed: `79.908` seconds
- CSV files seen: `160596`
- File evidence rows: `160596`
- Header signatures: `187`
- Header read errors: `0`
- Fingerprint errors: `0`
- Files with first/tail data-row evidence: `160592`
- First/tail width mismatches: `0`

## Boundary

- Every business CSV gets a file-level evidence row when the root is mounted.
- The JSON output keeps a compact sample; the full per-file evidence list is stored as gzip JSONL.
- This pass fingerprints head/tail bytes and checks first/tail row widths; it does not semantically validate every row.

## Top Column Counts

| Columns | Files |
|---:|---:|
| `11` | `41935` |
| `5` | `23636` |
| `13` | `10824` |
| `15` | `9816` |
| `4` | `8234` |
| `18` | `5822` |
| `85` | `5787` |
| `7` | `5776` |
| `108` | `5765` |
| `152` | `5764` |
| `97` | `5757` |
| `8` | `5750` |
| `261` | `5702` |
| `14` | `5676` |
| `20` | `5607` |
| `21` | `4670` |
| `89` | `3208` |
| `9` | `345` |
| `31` | `146` |
| `10` | `102` |

## Top Header Signatures

| SHA-256 | Files |
|---|---:|
| `12b19a2d5876b643cf2d5a94117bb17935a6abd1661f46031a59dc246fb7dfd8` | `17738` |
| `4796da88dc65926c3358735d28406f3dc68dffc732964dc8d6fbdb87e92537db` | `13656` |
| `babb7a89817667592b8bdbbf0abfd2bd2f17223d7c3e46e8119a0063142eb506` | `11827` |
| `c00a50db1789a41108a9c682898cc2237e9a38405143a6c2beb0294e127785cd` | `5833` |
| `3546f354c743f50f06826758cf6bf4823822afb2753d8b241eab57ce40b77558` | `5816` |
| `d8e7b4f9bd7824b9526b85463f4642b8afdffe4609c02317ec96cfa82115de7f` | `5800` |
| `a0bd3c991042edf40edbd34a815a07d892a750db2e4aed5937b4367076a36c55` | `5787` |
| `e19a0e459f5c1e3aeb146cba0a9f0fa1fc202866a128605f0a8c39315b98f985` | `5765` |
| `f46907a0d8bc2627a8b7e7fa5ae34b8a7b0fa991efddad65bae1f0b2cd57617d` | `5764` |
| `3bf00731c9cdc79419868e7d33f3901c2edf1b73ce978b8fc3e3669959b8343a` | `5757` |
