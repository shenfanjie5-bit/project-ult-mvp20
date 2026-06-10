# 会话交接 — 2026-06-07(compact 前落盘)

> 续会话先读此文 + `docs/audit/bulk_onboard_ths_2026-06-06.md`。分支 feature/a-share-fixes。只 A股、中文。

## 已完成(全部已提交,工作树干净)
1. **全 1525 冻结清单 A股定量 onboard 完成**(801 >200亿 + 724 ≤200亿,0 失败)。universe A股 116→1641。
   - 定量 parity ①②③⑤⑥ = 1524/1525 (99.9%);④ 定性层(LLM)未启用=本轮预期。
   - 提交:`f253cd4`(801) + `c3bf9d8`(724)。
2. **同花顺二级行业→12主题 永久分类路径**(`config/ths_industry_map.yaml` + `ths_industry_members.json` + recognize 改造)。提交 `e6cfc2f`。后续新增股永久走同花顺分类。
3. **DockCase 2TB tushare 数据集成**(`mvp20/sources/dockcase_cache.py` + tushare_source wrapper):
   - 只读缓存(按股命中本地不下载)+ 写回(miss 拉 live 写新文件,create-only)+ **增量追加**(refresh_existing:新季报/新交易日 append 进现有文件,严格大于、保留多report_type行)。
   - `scripts/refresh_dockcase.py` 已对在用 ~1607 股×13端点跑过:1587股/16162文件/26万行追加。**DockCase 现有文件只 append、绝不删/改/重排**。
   - 提交 `984ba2c`(缓存)+ `940d912`(写回)+ `a25ac6b`(增量追加)。
   - 开关:`DOCKCASE_CACHE=0` 关读 / `DOCKCASE_WRITEBACK=0` 关写。
4. **执行器/工具**:`scripts/run_bulk_onboard.py`(--no-codex禁LLM、--concurrency、市值降序、defer延迟编译+peer);`scripts/onboard_parity.py`(取证);ledger=`runtime/bulk_onboard/ledger.json`(状态全 done)。

## 关键发现(别重查)
- **新股 spec 完成度**:量化层 ~40% = 现有 parity ✓;LLM 定性层 ≤200亿=0%、>200亿~11%(早期codex残留)、现有14%;合并 ≈ 现有 81%。差距=LLM 定性层(item④),本轮特意停的。
- **script_fill 字段脚本化研究结论**:差异**不是 DockCase 落后**(已追平 live,fina_mainbz 全116最新=20251231)。差异源:①codex 大量留空、脚本能补 ②tushare fina_mainbz 对最新财年(FY2025)**缺境内行**(年报才全)③产品异质表格=codex/LLM 真价值。
- DockCase fina_mainbz bz_code:P=产品 D=地区 I=行业 455006000=销售模式。年报章节在 realtime_current 的 `L9.disclosure.annual_report.sections`(revenue_structure/customer_segment 等)。

## script_fill 填充器(提交 `dee551c`,已测)
`scripts/script_fill.py`:年报优先(解析 revenue_structure 按产品/地区 + customer_segment)+ fina_mainbz 兜底(最新完整期 P/D)+ catalysts(dividend/forecast)。`write_to_overlay` 只补空(Unknown→Known)不覆盖 codex、保留结构。
- 验证(10原有股 vs codex):地区 **5/5 一致 + 补 4 空缺**;产品 5/10 名匹配。真测 600171(纯no-LLM)补 2 空节点。7 单测过。

## 下一步(用户待定,建议序号 1)
1. **批量补空 runner**:对 1525 新股(尤其 ≤200亿 L3 空着的)跑 `script_fill.write_to_overlay`,补地区/产品/客户 → 零 LLM 成本提完成度。需新写批量 runner（仿 refresh_dockcase）。⚠️ 补完要重 compile+rescore;改 overlay 前后跑全套件 rc=0;新 overlay 是 tracked 提交。
2. **扩展 script_fill 字段**:管理层变动(stk_managers)/增减持(stk_holdertrade)/分红回购 映射到实际 overlay 节点(注意 catalyst dp_id 可能非 overlay 节点,需查模板实际节点名)。
3. **LLM 补真定性字段**:护城河/竞争格局/前瞻/新业务(L1.position.brand/moat、L2.segment.compete_landscape、L2.newbiz.* 等)——codex/claude 不可替代的部分。codex 可靠;claude 质量≈codex 但慢+有结构破坏风险(已加 restore_overlay_top_level 守卫)。

## 硬约束(别踩)
- DockCase 2TB 现有文件【只能 append 新行,绝不删/改/重排】;缺失股才 create 新文件。
- 回测产物只读勿改:pit_backtest/、scripts/run_pit_backtest.py、scripts/verify_pit_no_leak.py、tests/test_pit_*、tests/test_backtest_*、docs/audit/production_lookahead_findings.md、runtime/backtest/。
- 改打分/分类代码前后跑全套件 rc=0(corpus 大、跑全套件需无 live batch + corpus validate 干净;约 16min)。
- 审计/状态文档 untracked;hot.sqlite/ledger gitignore;stock_overlays/ 是 tracked 跟随提交;别提交 hot.sqlite(435MB二进制)。
- 提交链:e6cfc2f → 3bfc113 → 4264cd1 → 2f16f51 → 984ba2c → 940d912 → f253cd4 → a25ac6b → c3bf9d8 → dee551c → **5c0cbbc**。

---

## Round 3(2026-06-07 续):①批量补空 + ②扩展字段 + ③年报采集 三轨并行

用户拍板:①批量补空(做)+ ②扩展字段(加节点,审查后合并)+ ③年报采集(解锁客户)。

### Track A — L3 批量补空 ✅ 已提交 `5c0cbbc`
- `scripts/run_script_fill.py`(新,仿 refresh_dockcase):对冻结清单 1525 新股跑 `script_fill`,
  补【为空】的 L3 节点。结果:**2032 节点 / 1046 股 / 0 错**(region 1089 + product 986,dry-run 口径)。
- `L3.customer.concentration` 本轮=0:只能从年报抽,新股没采年报 → 由 Track C 解锁。
- `script_fill.py` 加 `include_catalysts` 开关(旧 catalyst dp_id 未实例化为节点,批量时关掉省抓取)。
- 验证:compile-overlays **error_count=0**;score-company 抽样无错;targeted tests **rc=0(68 passed)**。
- 关键发现:tier-1 结构化字段(分红/指引/减持/管理层)在 SLOT_DEFS【无 overlay 节点】,只在
  data_point_roles+master_list 有定义 → 「接进来」=新增 SlotDef=改打分图谱(全 corpus 分数漂移)。

### Track B — 扩展字段(加 4 个评分节点)🔄 提案已完成待集成
- 后台 agent 在【隔离 worktree】产出【可审查提案】,**未合并/未提交/未跑 compile/rescore**。
  worktree 在【旧 base b5aaed4】(缺 dockcase_cache.py)→ **不能 git-merge,需 PORT 到 feature 分支**。
- worktree 路径:`.claude/worktrees/agent-ad8be74841d85c86e/`;提案文档:其内
  `docs/audit/track_b_field_extension_proposal.md`(已审,质量高)。
- 4 个节点(全 participates_in_score=true → 填值会真实进分):
  | 字段 | dp_id | 方向 | 源 | 缓存 |
  |---|---|---|---|---|
  | 分红回购 | L9.company.buyback_dividend | +expectation_gap | dividend | 有 |
  | 业绩指引 | L9.company.earnings_guidance | +expectation_gap | forecast | 有 |
  | 股东减持 | L8.gov.insider_sell | −risk_discount | stk_holdertrade | 有 |
  | 管理层变动 | L8.gov.management_change | −risk_discount | stk_managers | **无(live,默认关)** |
- 4 个 SlotDef 逐字(插入 `_Z3_COMPANY_DERIVED_SLOTS`):buyback/guidance 仿 L9.company.ma 形态
  (or_gate/Inactive),insider/mgmt 仿 L8.gov.litigation(risk_factor/subtract_risk/negative/Inactive)。
- **关键打分洞见**:catalyst/risk 节点 value【必须带 `value.score`([0,1] magnitude)】否则 `_to_scalar`
  返回 0、贡献为 0(旧 _catalysts 没带 → 即使填也零贡献)。agent 的 parser 已编码 score+direction。
- **安全性质**:只加 SlotDef 不填值 = Inactive → 零漂移;漂移只来自 fill。
- 抽样命中(10 股):buyback 9 / guidance 6 / insider 1;单股实测 Δeg=+0.49 / Δrd=+0.52(方向对)。
- **集成计划(待 Track C 完成后做,避免 hot.sqlite 争用)**:PORT 4 SlotDef + script_fill 扩展 + 8 单测
  → generate-overlays(加节点,score-neutral)→ fill(buyback/guidance/insider;mgmt 默认关)
  → compile → **小样本 rescore-dry-run 看 eg/rd 分布漂移** → 给用户看漂移 → 批准后全量 rescore + 全套件 rc=0 + 提交。

### Track C — 年报采集(解锁客户)⏳ 运行中
- `scripts/fetch_annual_report.py`(巨潮 cninfo 免费 PDF + 正则抽章节,**零 LLM/零 token**)对 1525 新股跑。
- 装了 `pdfplumber`(--user --break-system-packages,装进 ~/Library/Python/3.14,不碰 brew)。
- **已并行提速(用户拍板 4 路)**:`/tmp/trackC_parallel.py`(task bs4mhfq57)把【未 ingest】的 1115 只
  round-robin 切 4 份不重叠、起 4 worker(各 ~279 只,worker 日志 /tmp/trackC_w{0..3}.log);hot.sqlite 转 WAL
  降锁争用;ETA ~4.5h→**~1.2h**。已 ingest 424/1525。
- **改了 `scripts/fetch_annual_report.py`**(未提交):main 循环加逐股 try/except,隔离单股 PDF 解析/sqlite 锁
  失败(防一只崩掉整个 worker;resumable)。这一改随里程碑2 一起提交。
- 完成后:【清扫 pass】单线程跑一遍补任何 BUSY/错误漏掉的股 → 再 re-run script_fill 补客户。
- **⚠️ harness-tracked 后台任务会被 session resume/compact 杀掉**(bs4mhfq57 在 713/1525 被杀)。
  已改用【nohup+disown 脱离进程】重启:剩余 822 只切 4 份(slice 文件 /tmp/trackC_slice{0..3}.txt,
  worker 日志 /tmp/trackC_p2_w{0..3}.log),脱离 session 不会再被杀。截至重启:713 ingested,WAL 已开。
  续跑无 harness 通知 → 靠 ScheduleWakeup 到点收尾。ETA ~45-50min。
- 收尾检查命令:`SELECT COUNT(*) FROM realtime_current WHERE dp_id='L9.disclosure.annual_report'`(目标≈1200+,
  因小盘/次新股无2025年报会有合法缺口);worker 全死 + 计数不再涨 = 跑完。

### Track C ✅ 完成 + 里程碑2 进行中
- **年报采集完成:1483/1525 frozen ingest(97.3%)**。未 ingest 42 只=合法缺口:cninfo 该 category 只回了
  「年度报告**摘要**」未回全文(如 600050 联通)/ 次新股 0 公告 / 科创北交所 orgid 边角。已诊断非 bug、非限流
  (单线程亦复现)→ 不再追这 2.7%。
- **里程碑2 写入完成**:`run_script_fill --frozen-only` 补 **1596 节点 / 1349 股 / 0 错**:
  **L3.customer.concentration 1345**(年报解锁,之前=0)+ L3.region 131 + L3.product 120(年报比 fina_mainbz 多覆盖的)。
  product/region 既有 Track A 的 fina_mainbz Known 值不被覆盖(write 只填非 Known)——年报版质量升级属另一独立 pass。
- 里程碑2 diff = 1349 overlay + scripts/fetch_annual_report.py(try/except)。compile-overlays 跑中(待 error_count=0)→ 提交。
- **里程碑2 已提交 `7fe92c0`**(1349 overlay + fetch_annual_report try/except)。

### 里程碑3(Track B 扩展字段)进行中
- **已 PORT 到 feature 分支**(worktree 旧 base 故手动移植,非 merge):
  - `mvp20/overlays.py`:`_Z3_COMPANY_DERIVED_SLOTS` 加 4 SlotDef(insider_sell/management_change 在 L8.gov.litigation 后;
    buyback_dividend/earnings_guidance 在 L9.company.product_order 后)。ALL_DERIVED_SLOTS 111→115,无 dup。
  - `scripts/script_fill.py`:整体采用 worktree 版(=feature base + 4 parser + _catalysts 重写 + value.score + write 激活 direction);
    L3 逻辑字节一致。`tests/test_script_fill.py`:+8 单测(共 15 passed)。
- **单股验证**:generate-overlays --only-ts-code 688981 → product/customer/region Known 保留 + 4 新节点 Inactive(零漂移确认)。
- **正在跑全量 generate-overlays**(加 4 Inactive 节点到全 1878 overlay,merge-preserve 保留既有 fill)。
- **下一步**:fill(run_script_fill --frozen-only --catalysts,填 buyback/guidance/insider;mgmt 默认关)→ compile(error_count须0)
  → AFTER 测分(/tmp/measure_drift.py,64 股样本,BEFORE 已存 /tmp/drift_before.json:AVOID48/WATCH13/BUY2)→ diff 漂移
  → **给用户看 → 等批准** → 全套件 rc=0 → 提交。
- 回退:若用户否,`git checkout -- config/stock_overlays mvp20/overlays.py scripts/script_fill.py tests/test_script_fill.py` 即恢复(里程碑2 已提交不受影响)。

### 里程碑3 ✅ 已提交 `04cb9f9`(用户审过漂移后批准)
- 4 SlotDef(ALL_DERIVED_SLOTS 111→115)+ script_fill 4 parser/扩展 + 8 单测 + 1878 overlay 加节点 + 12 industry 规范化重序列化。
- 填充 **3546 节点 / 1520 股**:业绩指引 1490 + 分红回购 1352 + 股东减持 704(管理层 0,默认关需联网)。
- 漂移(64 样本):信号翻转 ~8%(多 WATCH↔HOLD,1 下调)、均值 +0.03、幅度 ±0.14、无剧烈跳变 → 方向正确。
- 验证:compile error_count=0;全套件仅 1 失败=test_required_node_fields 硬编码 111→改 115;test_overlays rc=0。
- 设计说明留档:docs/audit/track_b_field_extension_proposal.md。
- 关键知识:catalyst/risk 节点 value **必须带 `value.score`**([0,1] magnitude)否则贡献 0;direction 编码正负方向。
- 管理层变动后续若要补:`stk_managers` 不在 DockCase 缓存,需联网或先加进缓存端点;extract(...,include_management_change=True)。

## Round 3 完整提交链
e6cfc2f→…→dee551c→**5c0cbbc**(TrackA 地区/产品)→**7fe92c0**(里程碑2 客户/年报)→**04cb9f9**(里程碑3 TrackB 4评分节点)。
全 1525 新股完成度:量化 L3 product/region 已补、customer 1345 已解锁、Track B 分红/指引/减持 3 节点已入分。
仍缺:① ≤42 只无 2025 年报股的客户(cninfo 无全文,合法);③ 真定性字段(护城河/竞争格局,需 LLM)。

## 任务2 ✅ 已提交 `14ee05e`(管理层变动)
- 填 L8.gov.management_change(联网 stk_managers,238 股/~15.6%/0 错);新增 run_script_fill `--management-change` flag。
- **修复严重标定 bug**:原 parser 把 stk_managers【每职位一行】当一次离任、不排换届再任 → 蓝筹换届被判全员离任风险拉满
  (茅台 0.9991)。修复=按人去重 + 排除回任(有在任 end_date 空记录)+ 只计核心高管(董事长/总经理/CFO/董秘)。
  茅台→None,只 C 位中途离任才触发(score=tanh(1.5×人数/3),1名→0.46)。+2 hermetic 单测。
- 增量漂移(64样本):0 信号翻转、仅 11 股微降(均值 -0.007)→ 轻、方向对。compile error_count=0,test_overlays 0 失败。

## 回测(t-30/60/90)✅ 完成(2026-06-08)
- 用户拍板:扩冻结表到 L8/L9 + 全 1641 池。
- **lookahead 修复**(用户同意改只读 pit_backtest/score.py;注意 pit_backtest/ + test_pit_* 全是 untracked 本地文件,不提交):
  `_FROZEN_EVENT_DPIDS`={4个TrackB节点},`_freeze_qualitative_layers` 额外 strip 之 → 防 as-of-today 事件数据泄漏过去日期。
  **只冻这 4 个(非整层 L8./L9.)**:L8.fin.* 是量化 PIT-safe 要保留。test_pit_leakage 原测过 + 新增 1 测锁定。
- **关键认知**:PIT 回测冻 L0-L3 + 4个TrackB事件节点 → 回测只反映【PIT 可重建的量化核 L5-L7】,
  我 Round3 的所有填充(L3/L8/L9)都在冻结层 → **回测不反映 Round3 完成度工作**,只验证底层量化引擎。
- 运行:`run_pit_backtest.py --today 20260607`(base 20260605→t30=20260421/t60=20260309/t90=20260116,n=1641)。
  collector 走 DockCase 缓存(miss→live+create-only写回,安全)。跑完 run --report 出指标。
- ⚠️ 回测 universe = mvp20.universe.yaml 全 A股,Round3 已扩到 1641(README 还写 116,已过时)。
- **速率真相**:每基准日采集 ~5.7s/股(读+PIT过滤+derive ~10端点,非 forecast写回)→ **每日 ~2.5h**,三日全跑 ~5h。
- **date1 20260116(t-90)已出结果**(1641全打分;/tmp/bt_short.py <base> 复用):
  - **关键发现:量化核是「2-4 周」短中期信号**。+10d rankIC **+0.113**(p<.001)、+15d +0.088、+20d +0.078,十档单调正向(+0.41~0.48);+5d 无信号(噪声)。
  - 衰减:+30d rankIC +0.064(弱);**+60-90d 反转**(+90d 单调 −0.65,最低分档 D1 +16.8% 碾压最高分 D10 +9.4%)——普涨市低质量反弹冲淡质量分。
- ~~**增量计划**:date2/date3 打完各跑 bt_short 复核;全完跑框架 --report~~ → **✅ 全完**:三日各 1641 全打分、run_all 结束、泄漏审计 PASS(HARD=0 / WARN=27)。官方 hfq 报告 `docs/audit/a_share_pit_backtest_20260607.md`(+30/60/90d;pooled BUY−AVOID 三档全负 = 60-90d 价值回归坐实)。

### bt_short 三日短周期表(`base_score` rank-IC vs +N 交易日前向收益,原始收盘;n≈1580–1612)
| base | +5d | +10d | +15d | +20d | 单调(+10/+20d) |
|---|---|---|---|---|---|
| date1 0116 | −0.016(p.53) | **+0.113**(p.00) | +0.088(p.00) | +0.078(p.00) | +0.48 / +0.43 |
| date2 0309 | **+0.158**(p.00) | +0.093(p.00) | +0.063(p.01) | +0.027(p.29) | +0.34 / −0.53 |
| date3 0421 | −0.013(p.61) | **−0.241**(p.00) | −0.213(p.00) | −0.205(p.00) | −0.97 / −0.95 |

- **date1**=模板(10-20d 甜蜜点正向、缓衰减)。**date2**=甜蜜点前移 +5d(+0.158 最强)、衰减更快(+20d 归零)、**仍同向 ✅**。**date3**=从 +10d **硬反转**(单调 −0.97 近完美倒序)。
- 短中期 edge 3 日 **2 日成立(date1/date2),date3 反转** → 引擎**非无条件稳健、regime 依赖**。
- **date3 反转诊断**(`/tmp/date3_regime.py`):0421→0508 = **科技/成长/小盘动量 melt-up**(半导体 +14% / 电子 +10.6% / AI +9.4% / 机器人 +9.2%;小盘 Q1 +10.9%;动量续涨 IC +0.19,**不是反转**)。引擎(价值+质量+反拥挤+均值回归)fade 热票 → **AVOID +8.0% vs BUY +0.5%** 完美倒挂。叠加 survivorship(池=热门主题龙头)放大。
- **market_regime 激活核心结论(反直觉)**:① 现有 `growth_minus_value`(L7.env.style)方向对但**非干净触发器**(date1 gmv+0.052 ≈ date3+0.059 却结果相反 → 需加**小盘 froth 腿** 中证2000/沪深300 RS);② **MARKET:CN 标量乘子数学上修不了 rank 倒挂**(全市场统一缩放 → rank-IC 不变,只能调 BUY 数量/激进度)。真修需 **(a)** regime 条件化**成分权重**(动量市收缩 priced_in_discount/crowdedness/overheat_risk,挂钩已有 `mode` trend_reversal/digestion)改横截面排名,或 **(b)** 组合级 regime 过滤器(敌对 regime 中性化敞口,不碰打分)。这正是 scoring.py:134/190 注释里 deferred 到 **R-7「由 PIT 回测验证」** 的工作。**✅ A/B 两原型已跑(2026-06-08),正式结论见 `docs/audit/regime_conditioning_r7_2026-06-08.md`**:① 标量乘子修不了倒挂(坐实);② 成分收缩(缩 priced_in_discount+overheat_risk)只修 ⅓(s=0.0 后 date3 +10d 仍 −0.168)→ 倒挂大部分是引擎价值内核的内生属性;③ froth 检测器 PIT 不可得(date1 比 date3 更 frothy,假设反向)。**两条都别在 3 日上上线,需 ≥15-20 基准日**;近期保护用组合级 de-gross(不碰打分)。原型:`/tmp/regime_filter.py`、`/tmp/regime_component.py`。
- **moneyflow 重设计 → 否决**(`docs/audit/moneyflow_crossdate_validation_2026-06-08.md`):`smart_money_signal_5d` 跨日 **1/3 有效**(date1 +0.16 / date2 ~0 / date3 负),7 种构造无一稳健;**date2 对照**(base_score work、moneyflow 死,同池同窗)证明是信号本身不稳健、非死区。已 `git checkout` 撤销 tushare_source 改动 + 删 test_smart_money,**全套件 rc=0**。引擎对 moneyflow 的保守处理(flow_boost=audit_only、active_inflow 无 value.score、fomo 只做衰减)被坐实正确。
- 完成后:re-run script_fill 补 `L3.customer.concentration`(+ 可能更优 product/region)→ compile → 提交(里程碑2)。
- 注:download_pdf 每只都重下(不复用 runtime/annual_reports/ 旧 PDF)——可后续优化,不影响正确性。
