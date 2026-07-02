# DOCKCASE semantic audit backlog

- Generated: `2026-06-19T00:26:17+0800`
- Source: `/Users/fanjie/Desktop/Cowork/project-ult-mvp20/docs/audit/dockcase_csv_semantics_2026-06-18.json`
- Completion status: `not_complete`
- CSV files seen: `160567`
- Header signatures: `187`
- Sampled files / rows: `329` / `25205`
- Unselected CSV files due to per-signature cap: `160235`
- Signatures with no sampled rows or empty selected files: `3`
- Signatures with sampled issues: `115`

## Next Batches

### `p0_no_sampled_rows`

| Rank | Files | Unselected | Sampled rows | Issue score | Priority | Columns | Example |
|---:|---:|---:|---:|---:|---:|---|---|
| `121` | `1` | `0` | `0` | `6.0` | `170.0` | `group, api, label, path, normalized_path, rate_limit` | `_workspace/_meta/manifests/master_dictionary_index.csv` |
| `124` | `1` | `0` | `0` | `6.0` | `170.0` | `ts_code, name, enname, classify, list_date, delist_date` | `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/dim_us_security.csv` |
| `128` | `1` | `0` | `0` | `6.0` | `170.0` | `market, ts_code, security_name, end_date, report_type, ind_type` | `_workspace/_meta/exports/curated_sample_20260310_60d_20stocks/tables/fact_overseas_financial_indicator.csv` |

### `p1_high_issue_signatures`

| Rank | Files | Unselected | Sampled rows | Issue score | Priority | Columns | Example |
|---:|---:|---:|---:|---:|---:|---|---|
| `46` | `28` | `25` | `300` | `1522.0` | `38075.0` | `ts_code, trade_date, open, close, high, low` | `指数专题/国际主要指数/by_symbol/652689.MI+MSCI金砖四国中盘价值.csv` |
| `27` | `192` | `189` | `300` | `1501.0` | `37714.0` | `ts_code, trade_date, name, open, low, high` | `指数专题/申万行业指数日行情/by_symbol/114701.MI+MSCI中国_食品饮料与烟草.csv` |
| `31` | `132` | `129` | `300` | `1501.0` | `37654.0` | `ts_code, trade_date, open, low, high, close` | `指数专题/中信行业指数日行情/by_symbol/106507.MI+MSCI欧盟(除德国).csv` |
| `42` | `58` | `55` | `251` | `720.0` | `18055.0` | `ts_code, end_date, ind_type, name, ind_name, ind_value` | `美股数据/美股利润表/by_symbol/AACBU+AACBU.csv` |
| `144` | `1` | `0` | `100` | `404.0` | `10100.0` | `trade_date, ts_code, ts_name, com_count, total_share, float_share` | `指数专题/沪深市场每日交易统计/all.csv` |
| `153` | `1` | `0` | `100` | `401.0` | `10025.0` | `ts_code, trade_date, close, open, high, low` | `现货数据/上海黄金现货日行情/all.csv` |
| `145` | `1` | `0` | `100` | `333.0` | `8325.0` | `trade_date, ts_code, count, amount, vol, total_share` | `指数专题/深圳市场每日交易情况/all.csv` |
| `37` | `71` | `68` | `257` | `255.0` | `6443.0` | `ts_code, ann_date, float_date, float_share, float_ratio, holder_name` | `股票数据/参考数据/限售股解禁/by_symbol/000002.SZ+万科Ａ.csv` |
| `51` | `18` | `15` | `50` | `225.0` | `5640.0` | `ts_code, end_date, ind_type, security_name_abbr, accounting_standards, notice_date` | `美股数据/美股财务指标数据/by_symbol/AACB+AACB.csv` |
| `38` | `70` | `67` | `33` | `144.0` | `3667.0` | `ts_code, name, end_date, report_type, std_report_date, per_netcash_operate` | `港股数据/港股财务指标数据/by_symbol/00001.HK+长和.csv` |

### `p1_high_volume_unselected_files`

| Rank | Files | Unselected | Sampled rows | Issue score | Priority | Columns | Example |
|---:|---:|---:|---:|---:|---:|---|---|
| `46` | `28` | `25` | `300` | `1522.0` | `38075.0` | `ts_code, trade_date, open, close, high, low` | `指数专题/国际主要指数/by_symbol/652689.MI+MSCI金砖四国中盘价值.csv` |
| `27` | `192` | `189` | `300` | `1501.0` | `37714.0` | `ts_code, trade_date, name, open, low, high` | `指数专题/申万行业指数日行情/by_symbol/114701.MI+MSCI中国_食品饮料与烟草.csv` |
| `31` | `132` | `129` | `300` | `1501.0` | `37654.0` | `ts_code, trade_date, open, low, high, close` | `指数专题/中信行业指数日行情/by_symbol/106507.MI+MSCI欧盟(除德国).csv` |
| `42` | `58` | `55` | `251` | `720.0` | `18055.0` | `ts_code, end_date, ind_type, name, ind_name, ind_value` | `美股数据/美股利润表/by_symbol/AACBU+AACBU.csv` |
| `1` | `17738` | `17735` | `196` | `2.0` | `17785.0` | `ts_code, trade_date, fd_share, fund_type, market` | `公募基金/基金规模/by_symbol/000003.OF+中海可转换债券A.csv` |
| `2` | `13656` | `13653` | `300` | `1.0` | `13678.0` | `l1_code, l1_name, l2_code, l2_name, l3_code, l3_name` | `指数专题/申万行业成分（分级）/by_symbol/000008.CJ+信息技术与硬件(长江).csv` |
| `3` | `11827` | `11824` | `300` | `1.0` | `11849.0` | `ts_code, trade_date, close, open, high, low` | `股票数据/行情数据/周线行情/by_symbol/000004.SZ+_ST国华.csv` |
| `9` | `5764` | `5761` | `52` | `77.0` | `7686.0` | `ts_code, ann_date, f_ann_date, end_date, report_type, comp_type` | `股票数据/财务数据/资产负债表/by_symbol/000063.SZ+中兴通讯.csv` |
| `7` | `5787` | `5784` | `112` | `33.0` | `6609.0` | `ts_code, ann_date, f_ann_date, end_date, report_type, comp_type` | `股票数据/财务数据/利润表/by_symbol/688783.SH+西安奕材-U.csv` |
| `10` | `5757` | `5754` | `133` | `30.0` | `6504.0` | `ts_code, ann_date, f_ann_date, end_date, comp_type, report_type` | `股票数据/财务数据/现金流量表/by_symbol/688256.SH+寒武纪-U.csv` |

## Interpretation

This backlog does not claim full semantic completion. It ranks the exact
remaining bounded-sampling gaps from the existing DockCase CSV semantic
audit so follow-up passes can target high-volume signatures, no-row
signatures, and issue-heavy signatures first.
