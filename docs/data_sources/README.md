# Data Sources Inventory

Per-provider endpoint catalogues backing `config/data_providers.yaml`. Each
provider's full available endpoints / SDK methods are mapped to mvp20
capability slugs so `mvp20 validate-providers` can prove every market and
every important capability is covered.

Current catalog scope: 5 active providers expose 47 active capability slugs.
The wider vocabulary is 51 slugs when FMP tier-locked capabilities and planned
FRED macro/commodity fields are counted.

## Files

| File | Rows | Source of truth |
|---|---:|---|
| [`tushare_endpoints.csv`](tushare_endpoints.csv) | 145 | User-supplied `available_complete_interfaces_20260428.csv` plus current code-path additions |
| [`futu_endpoints.csv`](futu_endpoints.csv) | 47 | Futu Python SDK read-only method/capability mappings + trading methods (out-of-scope flagged) |
| [`fmp_endpoints.csv`](fmp_endpoints.csv) | 80 | FMP REST API public docs + tier requirements |
| [`FMP_TIER_REQUIREMENTS.md`](FMP_TIER_REQUIREMENTS.md) | — | Which FMP plan each capability needs (Free / Starter / Premium / Ultimate) |

## CSV schema

### `tushare_endpoints.csv`
| column | meaning |
|---|---|
| `doc_api` | Tushare API name (e.g. `daily`, `moneyflow_hsgt`) |
| `label` | Chinese display label |
| `level1` / `level2` | Tushare doc category |
| `mvp20_capability` | mvp20 capability slug it maps to (empty if out-of-scope) |
| `status` | `covered` / `out_of_scope` / `uncovered` |
| `notes` | Reason for out-of-scope or future review hint |

### `futu_endpoints.csv`
| column | meaning |
|---|---|
| `sdk_method` | Python SDK method name |
| `label_cn` | Chinese display label |
| `mvp20_capability` | Capability slug |
| `status` | `covered` / `operational` / `out_of_scope` / `uncovered` |
| `notes` | Why excluded or special notes (HK 独家 / 配额 / read-only 边界) |

### `fmp_endpoints.csv`
| column | meaning |
|---|---|
| `endpoint` | REST path (relative to `https://financialmodelingprep.com/api`) |
| `label_en` | English display label |
| `mvp20_capability` | Capability slug |
| `fmp_tier_required` | `F` Free / `S` Starter / `P` Premium / `U` Ultimate |
| `currently_subscribed` | `yes` / `no` based on the FMP plan operator currently holds (Starter as of 2026-05-10) |
| `status` | `covered` / `out_of_scope` |
| `notes` | Tier note or out-of-scope reason |

When you upgrade FMP, regenerate this column. Today (Starter): 48 endpoint
rows accessible / 32 endpoint rows tier-locked; 46 accessible rows are covered
mvp20 capabilities and 2 accessible rows remain out-of-scope.

## Coverage summary (after Round 4 audit)

| Provider | Total endpoints | Covered | Out-of-scope | Operational | Coverage % |
|---|---:|---:|---:|---:|---:|
| Tushare | 145 | 107 | 38 | 0 | **100% in-universe** (38 are asset-class outside universe) |
| Futu OpenD | 47 | 34 | 7 (trading/account) | 5 (operational) | 34 covered data mappings; `get_security_filter` remains a future universe/screener hook |
| FMP | 80 | 77 | 3 (crypto/commodity/COT) | 0 | **100% in-universe** |

## How this maps to `data_providers.yaml`

Each capability slug appearing in the CSV's `mvp20_capability` column is a key
under `providers[].capabilities` in `config/data_providers.yaml`. The set of
slugs in the CSV is a **superset** of what each provider declares — empty /
out-of-scope rows document deliberate exclusions, not silent gaps.

To regenerate these CSVs after a provider catalog change, see
`/tmp/mvp20_gen/build_endpoint_csvs.py` (the build script, kept outside the
repo because it embeds curated knowledge that isn't part of mvp20 runtime).
