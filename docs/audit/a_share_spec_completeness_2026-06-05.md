# A股 SPEC 字段完整度 + 公式链审计(全 116 只)

> 2026-06-05。用户战略转向:先搞清 SPEC 完整度 + 如何算进公式,补齐全 A 股字段,**再**标定(避免在稀疏样本过拟合)。本文是 Phase 1 账本(只读、harness ground-truth)。停在 `a3ad2bc`(R-3a+R-3b.2)。

## 1. 公式链(dp_id → score_target → base 分量)

`base = fundamental + expectation_gap + valuation_rerating + capital_sentiment − risk − priced_in`(各 ~[-1,1] 求和)。

| score_target | → base 分量 | spec #dp(参与) |
|---|---|---|
| fundamental_score(+optionality) | **fundamental(+)** | 106 |
| expectation_gap | expectation_gap(+) | 24 |
| valuation_rerating | valuation_rerating(+) | 15 |
| sentiment_score + funding_score | capital_sentiment(+) | 7 |
| risk_discount(+overheat/vol/uncertainty) | risk(−) | 43 |
| priced_in_discount | priced_in(−) | 5 |
| *_multiplier(funding/theme/regime/…) | 乘子(非 base 加项) | ~30 |
| audit_only / none | 不进分 | 27 |

## 2. 保真度账本:到达分数的**全是真 realtime 数据**(116 股 harness)

| base 分量 | 非零节点/股(median) | %realtime | %行业继承 | %overlay手填 |
|---|---|---|---|---|
| fundamental(+) | 14 | **89%** | 0% | 11% |
| expectation_gap(+) | 3 | 100% | 0% | 0% |
| valuation_rerating(+) | 2 | 100% | 0% | 0% |
| capital_sentiment(+) | 1 | 100% | 0% | 0% |
| risk(−) | 5 | 100% | 0% | 0% |
| priced_in(−) | 1 | 100% | 0% | 0% |

**裁决**:实际进分的信号 89–100% 是 realtime 真值(L4 运营/L5 财务/L6 估值/L9 资金),**不是假值/继承/proxy/mock**。每股约 **26 个节点真正贡献**(14+3+2+1+5+1)。

## 3. 完整度缺口:声称参与 200,实到 ~26 → **134 个从不到达分数**

source_status(200 参与打分 dp_id):**✓39 / ○122 / missing39**。
- **✓ 39**=真骨干(L5 财务13、L6 估值8、L9 7…)。
- **○ 122 = "handled≠有真值"**(用户一贯警惕):spec 标 partial,但每股大多贡献 0 → 名义参与、实则空。
- **missing 39**=无源。

**134 个参与但从不到达分数**,按 base 分量:

| base 分量 | 从不到达 dp 数 | 缺什么 |
|---|---|---|
| **fundamental(+)** | **65** | 整个 L0 行业景气 + L1 护城河/竞争位 + L2 分部/新业务 + L3 渠道/客户/产品/交付 **定性层** |
| risk(−) | 31 | L8 风险簇大头 ○ |
| expectation_gap(+) | 19 | 预期/修正定性 |
| valuation_rerating(+) | 12 | 稀疏多重(dcf/peg/mcap_fcf 等) |
| capital_sentiment(+) | 5 | funding_score(median 0、仅 1% 股,**基本死**) |
| priced_in(−) | 2 | discussion/realization_risk |

## 4. 核心结论 + Phase 2 缺口分层

- **merit 当前 = 纯财务(L4/L5),缺整个"生意质量"定性维度**(L0-L3,~74 dp_id 几乎全空)。这是为何同行业内 merit 区分度有限、信号被估值/财务主导。
- **按层缺口(fundamental 侧,Phase 2 填值优先级)**:
  - L0 行业景气(30:17missing+13○)— 行业级,可批量(沿用 C1 codex-fill L0,已对 AI_COMPUTE 做过,需扩到 12 行业)。
  - L1 护城河/竞争位(12 多○)+ L2 分部经济(14 ○)+ L3 渠道/客户/产品(18)— **股票特定定性**,需 LLM 闭环逐股研究。
  - funding_score(资金流 4 字段,基本死)— 查数据源(北向/龙虎榜/大单)。
- **填值方法**:定性层 = LLM 闭环(prompt→fill→verify→compile→score,沿用 C1/000977 试点流程);定量缺口(funding/部分 L4)= 真源采集。

## 5. 三阶段(用户定序)
1. ✅ **Phase 1 完整度账本**(本文)。
2. ⏳ **Phase 2 补齐全 A 股 SPEC 字段**:按 §4 分层填(L0 行业批量 + L1-L3 逐股 LLM + funding 源)。规模大(~134 字段 × 116 股),需 plan + agents。
3. ⏳ **Phase 3 标定**:R-2c(conf→band)+ R-5(阈值)在完整诚实 base 上做。

**gotcha**:到达分数的是真值(别误以为分数建在假数据上);缺的是**定性维度从未填**(不是被污染)。R-3a/R-3b.2 的横截面修复 + artifact 仍有效(`build-peer-context` derive 后刷新)。

## 6. 3-agent 交叉验证(2026-06-05,用户要求"谨慎、3 agent 交叉验证")

**强收敛:核心确认,2 处措辞 over-claim 已校正,1 个新 bug。**

### 6.1 确认(3 agent 独立复跑一致)
- **~26 进分 / 134 never-reach 准确**:Agent A 独立 harness mean=**26.03**、median 24.5、union ever=66、never=**134**,逐 score_target 对账(fundamental never 61/risk 28/eg 19/valr 12…)。Agent C median=**26**(22 股/11 行业)。✅
- **到达分数的是真值**(非假/proxy/mock/继承伪装)。✅
- **缺口真实、未被既往工作关闭**(全池口径):L0 接线(63d25cb)只填了 **AI_COMPUTE 1/12 行业**;R-2 建的是**财务** merit(L5.fina 6 比率,实盘进分),与"缺**定性** merit"不冲突。✅

### 6.2 校正(我 §3/§4 的 over-claim)
1. **"L0/定性层 never reach score" → 错**。定性机理**已建成并实盘进分**(git 63d25cb:L0 激活使 688256 industry_contrib 2.32→3.48 需 tanh 限幅;L1/L2/L3 对 10 只 LLM-pilot 股有真实 Known 进分实例)。真相 = **机理已通、仅 ~8% 覆盖**(L0:1/12 行业;L1-L3:10/116 股)。**是 coverage rollout 问题,不是维度缺失/设计缺陷。** 我的 harness 误读了"继承前快照"。
2. **"○122 mostly empty" → 夸大**。○ 桶**双峰**:~34-46 个有真值且进分(segment.revenue_share 116/116、roe 116/116、roa 108、active_inflow 116/116、margin_short 116/116)+ ~97 真空。
3. 既往改进时间线(Agent C):Batch-1~6 + F1/F4/F8 + C1 + R-1/2/3 已关闭大量缺口;官方 checker 220/256(85.9%)是"handled"虚高(计 Unknown 占位),README 104/250(41.6%)stale 于 campaign 前;**真实"真值进分"中位 ≈26/256(~10%)、AI_COMPUTE ≈48(~19%)**——这才是诚实数。

### 6.3 新发现(Agent C,需我复验后修)
- **funding_score 不是"缺数据死",是 WIRING BUG**:`L7.flow.active_inflow` + `L7.trade.margin_short` 在 DB **116/116 有真值**,但 `synthesize_realtime_nodes` **无对应规则 → 静默丢弃**(同 F1 scalar-key 类 bug)。→ 应**改代码接线**(快),不是 Phase 2 填值(填了也会在进分端再丢)。

### 6.4 校正后 Phase 2(coverage rollout,非"建维度")
1. **funding wiring 修** ✅ **已做**:`L7.flow.active_inflow`(main_net 万元、signed)接进 funding_score(`tanh(main_net/50000)`);funding 从 median 0/1%股 → **median≥1/100%股**(方向已验:+28121→+0.51、−4958→−0.10)。**`L7.trade.margin_short` 经复验是共模正**(融资买入/余额 turnover 人人为正、A 股融券噪声)→**故意不接**(注释说明,留 cross-sectional/趋势 future),避免重蹈 priced_in 共模。
2. **L0 × 其余行业** ✅ **已做(Phase 2b)**:pilot SEMI_EQUIPMENT(我审)+ 10 行业并行 agents(各 1 opus、distinct 文件、本地接地+industry_inference conf≤0.5、event 节点诚实留 Inactive)。**12/13 行业现填 L0**(SPACE_ECONOMY 无 A 股跳过)。验证:全局 verify 0 hard/0 schema;**L0 100% 股票到达分数**(median 13-16 节点/股);base median −0.174→−0.152、AVOID 30→25、按行业景气分化(fund Δ +0.072 ~ +0.72 好行业 / −0.45 差行业)。demand.terminal 多 down(A 股成分股 −40~−77%、外资拉高均值已标注)。**数据质量 flag**(多 agent 提):A 股 revenue_growth 疑有 qoq-vs-cumulative base artifact,待后续核查。
3. **L1-L3 × 全 A 股** ✅ **已做(Phase 2c,用户指定 codex)**:codex 闭环(codex_prompt_gen + codex_run_prompt_low,run_c2_fill 驱动)逐股填 120 只 + pilot 002371(我审)。**L1-L3 participating Unknown 4022→837(填 3185、79%)**。诚实:本地接地 + industry_inference conf≤0.5 + 无源留 Unknown/N/A(不编造)。验证:verify_overlay 全局 0 hard/0 soft;**compile ok**(修了 20 个 N/A 节点缺 `not_applicable_remove` policy 的 batch 低-effort 疏漏,4 股);L1-L3 到分 57% 股票(median 1 节点);base median 稳(−0.152→−0.153)、AVOID 25→23。score 影响 modest=诚实(定性标签非主导)。**完整度主目标达成**。
4. 不填:L0.compete.*(Inactive 事件驱动、源 down)、所有 multiplier(缺=中性、设计如此)。
- **规模校正**:不是"134×116 全量铺";机理零改动,是 11 行业 L0 + 106 股 L1-L3 的覆盖推广 + 1 个 wiring 修。

## 7. 严格链重测(Phase 2c 后,全 116 股聚合链口径)— 发现 DEAD_FILLED 系统性裂缝

> 2026-06-05,用户"查看全 a 股 spec 字段完整度"。这次不看 DB 原始覆盖(只见 realtime 骨干、看不到 overlay 填值),也不看 node Known-status(会把"填了"误当"进分"),而是**逐 dp_id 走完整聚合链**,对全 116 股统计 present/known(missing_balance==known)/reaches(`abs(leaf score)>1e-9`)。harness:`/tmp/spec_strict_chain.py`(只读)。

### 7.1 裁决:200 个"参与打分"dp_id 的真实归宿

| 类别 | 数 | 含义 |
|---|---:|---|
| **LIVE**(真进分) | **79** | 至少 1 股 `score≠0` —— 真实打分面 |
| **DEAD_FILLED**(填了但全死) | **66** | known≥1 股(有真值)但**全 116 股 score=0** |
| HONEST_NA | 6 | 节点在但 Unknown/N-A |
| EMPTY(真空) | 49 | 全池无节点/无值 |

按 base 分量:fundamental(+) LIVE 51 / DEAD 45;risk(−) LIVE 13 / DEAD 15;expectation_gap LIVE 6 / DEAD 5。
按层:LIVE = L0:17 L4:17 L5:15 L8:12 L6:7 L3:4 L7:3 L1:2 L9:2;DEAD = L3:14 L2:11 L8:11 L0:10 L1:10 L4:5 L9:4 L5:1;EMPTY = L6:15 L9:12 L5:7 L8:6 L7:4 L2:3 L0:1 L4:1。
(66 DEAD + 6 NA + 49 EMPTY = 121 never-reach,与 §3 phase1_audit 的 121 完全对齐。)

### 7.2 根因(已自验,两个铁证)— 不是缺数据,是 `value` 没归一成可打分标量

**机制**:`aggregator._leaf_score` 对 Known 叶子调 `magnitude = _to_scalar(node.value)`,而 `_to_scalar`(aggregator.py:138-210)**只认固定键** `score/intensity/strength/yoy_pct/magnitude/trend/future_option_value`,**其它键一律返回 0.0**(:210)。
Phase 2c(codex)把丰富值塞进**语义键**:`L1.moat.tags→{tags:[...]}`、`L2.segment.opex_ratio→{opex_ratio_pct, components, notes}`、`L1.position.tech_barrier→{moat_score,...}`、`L1.position.cost_edge→{drivers, evidence_summary,...}` —— 全部不在识别表 → magnitude 0 → leaf score 0。

- **铁证 1(`_to_scalar`)**:对 16 个 DEAD_FILLED dp_id 取真实填值直接调 `_to_scalar` → **全部 0.0000**。含两类陷阱:① 用了**未识别键**(`moat_score`/`opex_ratio_pct`/`tags`);② 用了**识别键但值为 None/非数**(`L1.position.pricing_power` 有 `strength` 键但值 None;`L2.newbiz.tam` 有 `current_contribution` 键但值非数)。
- **铁证 2(消融)**:取最满的 6 股,**只抹 L0-L3 的 `value`、保持 status/confidence 不动**重打分 → 002916/000977/300394/688256 **Δbase=Δfund=0.00000**(41 个填值零贡献);300502/601138 Δfund 仅 +0.0035/−0.0030(极少数恰用 `yoy_pct`/`strength`+真数字者微弱漏进)。

**含义**:Phase 2c 填的 ~3185 个 per-stock L0-L3 定性节点,**到 final_score 贡献 ≈ 0**。这也校正了 §6.4-3 当时的措辞——"base −0.152→−0.153 几乎不动 = 定性标签非主导"**实为"根本没接进打分"**(value 键 `_to_scalar` 读不到)。Phase 2c 把"数据填了",但"连进打分"的**归一层从未建** → Phase 2 只完成一半。
L0 同时出现在 LIVE(17,行业景气经 `industry_contrib` 路由,Phase 2b 的功真实可见)与 DEAD(10,per-stock 专属、不路由),两者不矛盾。

### 7.3 66 DEAD_FILLED 的两类(决定修法)

- **A. 数值有底**(value 里就有真数,只是键名不对):`L2.segment.opex_ratio_pct`、`L1.position.tech_barrier.moat_score`、`rd_intensity_pct`、`asp_yoy_pct`、`L2.segment.profit_share`、`L3.product.margin_mix`、`L2.newbiz.*_contrib` 等 → 可**确定性横截面归一成 strength**(沿用 R-2/R-3 机理,无编造)。
- **B. 纯定性标签**(无数):`L1.moat.tags`/`model.tag`/`role.tag`/`stock_attr.tags`、`L1.position.brand/stickiness`(drivers/evidence 文字)→ 要进分须**保守评分 rubric**(偏软)或**诚实改 `participates_in_score=False`**(让 spec 别再声称参与)。

**gotcha**:这块**直接挡 Phase 3 标定**——在"缺整个生意质量定性维度"的 base 上重标阈值,会把缺口焊死。修法须 plan→批准→agents→复审(spec 字段按用户规矩需 3-agent 交叉验证),**未动手**。

### 7.4 3-agent 交叉验证结论(2026-06-05)+ 框架校正

派 3 个对抗性 agent(代码路径 / 独立消融 / 结论证伪),**机制三方铁证收敛、但框架被校正**(我已逐条自核):

**收敛确认(机制,可完全信任、据此行动)**:
- `_to_scalar`(aggregator.py:138-210,else `return 0.0`@:210)是唯一幅度来源;`_node_status`(:356 先读 data_status)使这些节点走 Known 分支。Agent A 全库扫:3433 个 Known+value 节点,3319 个 `_to_scalar==0`,非零的 114 个**全靠 `trend` 键**(0.2 cap)、无一靠语义数字键。
- **救援路径全否**:scoring `_industry_variables_from_flat` 读的是已归零的 `agg["score"]`;死汇救援仅对 `synthetic_realtime`(overlay 中 0 个);derive.py `_FORMULA_REGISTRY` 不输出任何 L0-L3;schema_validator 只校验不打分;无任何写入器把语义键映射成 score/strength。
- **链路是通的、是 payload 契约不匹配**:Agent B 注入 `{"score":0.9}` → base 抬 +0.18~+0.29、fund +0.39~+0.58;但 codex 原值消融 mean|Δbase|=0.002/max0.02(4/8 股精确 0)。**filled-but-dead,非 gated**。
- **旧"L1-L3 到分 57%"是测量错误**(把 present/Known 或 L0 行业继承经 industry_contrib 进分,误当 per-stock L1-L3 到分)= 用户一贯警惕的 handled≠reaches 混淆。严格复跑:per-stock 定性 reaches=0/116。

**框架校正(我原"wiring bug / Phase2 半成品"措辞被 Agent C 推翻、已自核 spec 证据)**:
- spec 本身把 L1-L3 定义成**描述性 payload、从未给 `_to_scalar` 能读的量级**:`docs/data_sources/llm_derived_nodes.md` —— `brand→{tier:enum,qualitative_signals:[text]}`(纯文)、`pricing_power→{strength:enum[强/中/弱],asp_yoy_pct}`、`tech_barrier→{moat_score:0-5,rd_intensity_pct}`(有数但键名不认)。L0 行业模板却显式要 `magnitude/yoy_pct/trend`(AI_COMPUTE.yaml:25/27 `yoy_pct:29.19 magnitude:moderate`)→ 所以 L0 LIVE。**这是 spec 内部 L0 模板 vs L1-L3 schema 的不一致;"定性→标量"归一层从未设计**。codex 是严格照(无量级的)spec 填的;验收门(verify_overlay_closed_loop)也从不查"进分"。
- **79 LIVE 是整个打分面**(含 realtime 财务/资金骨干 L5-L9 + L0 行业继承);**per-stock codex 真正 LIVE ≈ 39**(且多为 `trend:'up'` 0.2 弱信号)。今天分数靠的是 realtime 骨干,健康、不受影响。

**66 DEAD 按可修性拆分(`/tmp/dead_partition.py`,扫真实填值)**:
| 类 | 数 | 性质 | 修法 |
|---|---:|---|---|
| **NUMERIC** | **10** | value 里有真数字、仅键名错(opex_ratio/moat_score/profit_share/industry_exposure/cash_contrib/product.portfolio/lifecycle/margin_mix/buy_whisper/volume.users,多数121/121) | **确定性横截面归一**(低风险,沿用 R-2/R-3)= 真·接线漏 |
| **ENUM/TEXT** | **45** | 无量级(强/中/弱枚举、tags、drivers 文字);含 ~15 个 L8/L9 `risk_detected:false`=查无事件多半本就正确 | **建模决策**:保守 rubric(主观/共模风险)或诚实 `participates_in_score=false` |
| **NO_KNOWN_FILL** | **11** | L0.tech/policy/compete/sentiment per-stock 实际没填(行业继承充数)| 归入 EMPTY |

→ 真正"填了真值却死"= **55**(非 66),其中**仅 10 个确定性可修**,45 个是建模选择。**裁决:硬数据 100% 可信据此行动;但 headline 须从"Phase2 半成品/66 根线没接"改为"数据填充是真的,但 ~82% 是 by-design 描述性(spec 从未给量级),仅 ~18% 是可确定性修的真接线漏;Phase3 前需要的是'该层要不要/怎么进分'的建模决策,而非单纯接线"**。

### 7.5 R-6 已实施(2026-06-05,用户定"诚实派:0 接线 + 全 55 改非打分")

进一步核验后,连那 10 个 NUMERIC 也都不该接:**margin_mix/opex_ratio/profit_share 与 L5 realtime 骨干双算**(`L5.is.gross_margin` aggregator.py:1204 已按 archetype median 横截面打公司毛利率;margin_mix.gross_margin_pct 就是公司毛利率本身)、**moat_score/competitive_score 是 LLM 主观 0-5 评分**(接进=软判断驱动分,违反反过拟合)、其余列表/稀疏。→ 用户选 **R-6a 接 0 个**。

**改动(3 文件,`git`):**
1. **`config/data_point_roles.yaml`**:55 个真填却死的定性 dp_id `participates_in_score: true→false`(block-scoped,精确 55 翻转;value 载荷保留为描述性上下文供展示)。清单见 `/tmp/r6_set.txt`:L1.* 全部、L2.segment/newbiz、L3.product/customer/region/channel/delivery、L4.price/volume/eff 稀疏、L5.surprise.buy_whisper、L8.* / L9.* 事件。
2. **`mvp20/onboard.py`**:新增 `build_peer_context` 步(ONBOARD_STEPS index 6,compile 后 / score 前,A 股 only,pipeline-locked,best-effort)。修新股链路硬缺口——否则 score-company 加载 stale artifact、新股不在估值池→`_xs_valuation_signal` return None→估值退回 R-3 前(实测 valr 漂移达 ~0.19)。
3. **`tests/test_onboard.py`**:步骤序不变量测试(build_peer_context 必在 derive 后、score 前)+ 假桩 progress 索引同步。

**验证(全过):**
- **score-neutral**:116 股 base 分布**逐位不变**(median −0.1530 / mean −0.1643 / sd 0.2978;fund median +0.0743;BUY=7 HOLD=44 WATCH=42 AVOID=23 before==after)。证实死节点早被 coverage/merit-mean 排除(f4a63a7),改非打分无分数副作用。
- **严格链**:participating 200→145;raw-filled-but-dead **55→0**;LIVE 不变 **79**。残留 11 个 DEAD_FILLED = NO_KNOWN_FILL(L0.tech/policy/compete per-stock 没填、仅行业继承显 known),性质不同(有行业继承打分路径),**未纳入本轮**(待后续:要么行业 overlay 补 magnitude,要么一并 relabel)。
- governance 校验 **0 errors / 0 warnings**;compile-overlays **error_count 0**;verify_overlay 闭环 **0 hard / 0 soft**;**全测试套件绿**。
- peer_context artifact **无需重建**(R-6 只改 participates_in_score,不动 PE/PS 快照或 industry_id 这些 peer_context 输入)。

**净效果**:spec 不再声称 55 个没接/重复的打分面;merit = L5 财务质量 + L0 行业景气(诚实、量化、无 LLM 软判断);新股走 onboard 不再因"缺定性"被惩罚、且估值横截面不退化。**定性 value 仍保留供前端展示**。下一步 Phase 3(R-2c+R-5)在此诚实 base 上做。
