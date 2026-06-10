# Bulk Onboard（同花顺分类）— 本轮终报 2026-06-06

> 审计文档（untracked）。本轮把冻结清单中 **市值 >200亿** 的 A股 onboard 进系统，
> **定量轮**（LLM 定性层未启用），tushare 按股数据走 **DockCase 2TB 只读缓存 + 写回**。

## 口径与范围
- **批次来源**：`config/bulk_onboard_a_share_ths.json`（冻结清单 1525 只，口径=净增 ∩ 同花顺二级成员 ∩ total_mv≥100亿@20260605 ∩ A股在市，含 ST/北交所）。
- **本轮范围**：`total_mv_yi > 200亿` 的 **801 只**（大盘优先，_select 按市值降序）。
- **留站位（reserved）**：`≤200亿` 的 **724 只**，本轮不跑，ledger 标 `reserved`，后续轮把状态翻回 pending 即可续跑。
- **LLM**：codex + claude **均未启用**（用户本轮指令）。定性 L1-L3 层留后续 LLM 轮补（item④）。

## 分类路径（永久）
- `config/ths_industry_map.yaml`：同花顺二级行业名 → 12 主题（62 行业 1:1 无歧义）。
- `config/ths_industry_members.json`：ts_code → {ths_industry, theme}（4129 成员）。
- `mvp20.onboard.recognize`：A股 THS 优先 → tushare 回退 → 标记需人工。**后续新增股票永久走同花顺分类。**

## tushare 数据 — DockCase 2TB
- **只读缓存**：按股端点（income/balancesheet/cashflow/fina_indicator/forecast/express/dividend/fina_mainbz/daily/daily_basic/moneyflow/report_rc/stk_holdertrade）命中 `<分类>/by_symbol/<ts_code>+<名>.csv`，**不重复下载**。横截面/当前价 → 回退 live（新鲜）。
- **vintage**：DockCase 财务截至 **2025Q3**（落后 live 2026Q1 约 2-3 季）→ 本轮新股财务为 2025Q3；当前价仍新鲜。验证：缓存值与 live 重叠期 **0 不一致**。
- **写回**：缓存 MISS 时拉完整历史 live、写成 by_symbol CSV（**create-only，绝不改现有归档文件**，CRLF/UTF-8/全列匹配）。本轮 9 只 miss 新股已回填。
- **开关**：`DOCKCASE_CACHE=0` 关读、`DOCKCASE_WRITEBACK=0` 关写。**DockCase 现有文件只读、零改动。**

## Phase4 收尾
- peer_context 全A重建：828 估值池 / 917 run_up 池。
- compile-overlays：**error_count=0**，1129 ts_code 入快照。
- 全量 rescore（peer_context 重建后）。

## Parity 审计（801 只 >200亿）
| 项 | 结果 |
|---|---|
| ① universe + industry_ids(=同花顺主题) | **801/801 (100%)** |
| ② overlay_manifest + 编译快照 | **801/801 (100%)** |
| ③ core_dp(L5/L6/L7)≥40 | **801/801 (100%)**；min/中位/max = 58/71/74（基线中位 68）|
| ⑤ 六分项 + base_score + signal | **801/801 (100%)** |
| ⑥ peer_context | **801/801 (100%)** |
| ④ 定性层（LLM L1-L3） | 719 缺 / 82 有 — **本轮 no-LLM 预期**，后续 LLM 轮补 |

- **定量 parity（①②③⑤⑥）= 801/801 = 100%**，超 ≥95% 目标。
- signal 分布：AVOID 565 / WATCH 128 / HOLD 73 / BUY 34。**AVOID 偏高（71%）属预期**：no-LLM 缺定性正向层（expectation_gap/capital_sentiment narrative）→ 偏空；LLM 轮补后会回升。
- 北交所子样本（3 只 920186/920045/920185）：全 done+scored，core_dp 68-71。
- 失败：**0**。

## 提交链
- `e6cfc2f` 同花顺分类永久路径 + 冻结 manifest
- `3bfc113` codex 后归一化 status 不变量（防 N/A overlay 毒化编译）
- `4264cd1` bulk 延迟全编译+peer 到收尾（去 O(corpus²)）
- `2f16f51` 双引擎(codex+Claude Opus)填充 + 节点标量消毒（**本轮已停用 LLM**）
- `984ba2c` DockCase 2TB 只读缓存 + 市值优先 + no-LLM
- `940d912` DockCase 写回（create-only）
- `f253cd4` onboard 801 只 >200亿 A股（universe 116→917 + 801 overlay）

---

# Round2 + 全 1525 完成 + DockCase 增量追加

## Round2：≤200亿 的 724 只（同 no-LLM + 缓存路径）
- reserved 的 724 只 ≤200亿 翻回 pending 续跑，**0 失败**。与 Round1 的 801 只 >200亿 合计 **全 1525 只完成**。universe A股 116→**1641**。
- 提交 `c3bf9d8`（universe +724 + 724 overlay）。

## Phase4 收尾（全 1525）
- peer_context 全A重建：1405 估值池 / 1641 run_up。
- compile-overlays：**error_count=0**，1853 ts_code 入快照。

## Parity 审计（全 1525）
| 项 | 结果 |
|---|---|
| ① universe + industry_ids | **1525/1525 (100%)** |
| ② overlay_manifest + 快照 | **1525/1525 (100%)** |
| ③ core_dp≥40 | **1525/1525 (100%)**；min/中位/max = 54/71/75（基线 68）|
| ⑤ signal 已产出 | **1525/1525 (100%)** |
| ⑥ peer_context | 1524/1525（缺 1：688759.SH 必贝特-U 未盈利无估值指标）|
| ④ 定性层（LLM） | no-LLM 预期缺，后续 LLM 轮补 |
- **定量 parity（①②③⑤⑥）= 1524/1525 = 99.9%**，超 ≥95%；**0 失败**。
- signal：AVOID 1090 / WATCH 253 / HOLD 126 / BUY 56（no-LLM 偏 AVOID = 预期）。
- ST 10 只、北交所 10 只:全 done+scored。
- 全套件 1223 passed / rc=0。

## DockCase 增量追加机制（提交 a25ac6b）
- **检查发现**:原写回是 create-only,**现有文件的新季报/新交易日没追加**(财务停 2025Q3、日线停 ~3月底)。
- **`refresh_existing`**:对已在 DockCase 的股,把 live【严格新于文件最大日期】的行追加进现有文件。安全保证:
  - **现有行一个不动、不去重、不重排** → 财报同期多 report_type 行(合并/母公司/调整后)不会被误删(naive end_date 去重会删,已加回归测试)。
  - 保留现有列序 + CRLF;原子 tmp+rename;只拉小增量不重下全历史。
- **freshen pass**(`scripts/refresh_dockcase.py`):对在用 ~1607 只 A股×13端点增量追加,把 DockCase 在用股刷新到最新季报/交易日。
- **DockCase 只读现有文件:只 append 新行,绝不删/改/重排;缺失股才 create 新文件。**

## 全部完成 — 后续可选
1. ✅ **全 1525 冻结清单定量 onboard 完成**(801 >200亿 + 724 ≤200亿)。
2. **LLM 定性层（item④）**:对 1525 只跑 codex/claude 定性填充补齐 full parity（codex 可靠；claude 质量≈codex 但慢+有结构风险，已加 restore_overlay_top_level 守卫）。
3. DockCase 已增量刷新到最新;要更新鲜可重跑 refresh_dockcase 或 `DOCKCASE_CACHE=0` 走 live。

## 提交链(完整)
e6cfc2f 同花顺分类路径 → 3bfc113 N/A归一化 → 4264cd1 去O(corpus²) → 2f16f51 双引擎(已停用LLM) → 984ba2c DockCase缓存 → 940d912 写回 → f253cd4 onboard 801>200亿 → a25ac6b 增量追加 → c3bf9d8 onboard 724≤200亿(全1525完成)
