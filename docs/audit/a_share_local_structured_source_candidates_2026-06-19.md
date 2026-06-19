# A-share local structured source candidates

- Generated: `2026-06-19T12:38:08+08:00`
- Unknown dp_ids checked: `4`
- Runtime dependencies ready: `4`
- Direct Known-ready rows: `0`
- Review/source candidate rows: `2`
- Review candidate matches: `1`
- Supporting candidate matches: `4`
- Empty candidate matches: `1`
- No direct catalog source rows: `2`
- Excluded false-positive matches: `407`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## DOCKCASE Scope

- CSV files seen: `160567`
- Header signatures: `187`
- Sampled signatures: `184`
- Sampled files: `329`
- Sampled rows: `25205`

## Candidate Status Counts

| Status | Count |
|---|---:|
| `no_direct_catalog_source` | 2 |
| `review_candidate_found` | 1 |
| `supporting_candidate_found` | 1 |

## Rows

| dp_id | status | direct Known | review candidates | supporting candidates | excluded false positives | next Tushare action |
|---|---|---:|---:|---:|---:|---|
| `L0.cost.rent` | `review_candidate_found` | no | 1 | 0 | 21 | 优先复核现金流量表 use_right_asset_dep，并补充租赁负债、租金费用或 经营租赁披露映射；若只用 use_right_asset_dep，必须定义保守 proxy 方向。 |
| `L0.demand.frequency` | `no_direct_catalog_source` | no | 0 | 0 | 96 | 现有 Tushare/DOCKCASE 目录没有客户订单频次、交易笔数、复购或使用 cadence 字段；不能用股票成交量、换手率或资金流替代。 |
| `L0.demand.penetration` | `no_direct_catalog_source` | no | 0 | 0 | 142 | 当前目录未发现公司业务口径的 TAM、市场份额、装机基数或客户渗透率字段；不能用股本、股东、指数权重、市场行情 percent/ratio 替代。 |
| `L0.price.product_asp` | `supporting_candidate_found` | no | 0 | 4 | 148 | 优先复核 fina_mainbz/主营业务构成的 bz_item、bz_sales、bz_cost、bz_profit，把它们作为产品 mix/分子证据；仍需单位销量、出货量或外部价格指数才能计算 ASP。 |

## Candidate Details

### `L0.cost.rent`

- Review candidates:
  - `use_right_asset_dep` in signature `10` (`5757` files, sampled non-empty `31`): 现金流量表里有使用权资产折旧样本，可作为租赁负担候选，但不是租金费用。
- Empty candidates:
  - `fa_fnc_leases` in signature `10`: 融资租赁支付字段在当前语义样本中为空，不能直接落地。
- LLM/web fallback: 从年报管理层讨论、财报附注、交易所问询或公告正文抽取租赁/门店/物流/能源成本。

### `L0.demand.frequency`

- No source-ready or supporting catalog candidate was found.
- LLM/web fallback: 从年报、经营数据公告、互动易/交易所问答、行业运营数据中抽取订单数、活跃客户、出货/使用频次，并与收入拆分校验。

### `L0.demand.penetration`

- No source-ready or supporting catalog candidate was found.
- LLM/web fallback: 补行业 TAM/市占率来源，或从招股书、年报、研究报告、协会数据、交易所问答中抽取分母和公司口径分子。

### `L0.price.product_asp`

- Supporting candidates:
  - `bz_item` in signature `11` (`5741` files, sampled non-empty `145`): 主营业务构成的产品/地区项目可帮助识别收入结构，但没有销量。
  - `bz_sales` in signature `11` (`5741` files, sampled non-empty `144`): 主营业务构成的分项收入可作为 ASP 分子或 mix 证据，但缺少单位销量。
  - `bz_profit` in signature `11` (`5741` files, sampled non-empty `87`): 主营业务构成的分项利润可支撑毛利结构复核，但不能单独得到 ASP。
  - `bz_cost` in signature `11` (`5741` files, sampled non-empty `88`): 主营业务构成的分项成本可支撑毛利结构复核，但不能单独得到 ASP。
- LLM/web fallback: 从年报分产品销量、产销存、公告、行业价格指数、交易所问答或公司披露中抽取数量/价格口径，和 bz_sales 做公式校验。

## Interpretation

- `L0.cost.rent` has a Tushare/DOCKCASE lease-related candidate (`use_right_asset_dep`), but it is a lease-depreciation proxy rather than rent expense.
- `L0.price.product_asp` has product/region revenue and cost mix support from `主营业务构成`, but no unit volume, shipment, or governed price index in the current catalog.
- `L0.demand.frequency` and `L0.demand.penetration` have no direct business-field source in the current catalog; market trading volume, turnover, stock price, share capital, holder, and index-weight fields are explicitly rejected as false positives.
- All rows remain read-only review candidates or no-source rows; none can write score-affecting Known values without governed mapping or extracted evidence.
