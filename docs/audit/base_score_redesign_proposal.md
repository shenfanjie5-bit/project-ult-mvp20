# base_score 重设计提案

> 2026-06-04，4-agent 深度审查 + 我逐条 trust-but-verify 后产出。
> 目标:把 spec 字段→分数 的转化,从"测估值/情绪择时 + 一串 artifact 压负"改成"诚实的 merit/timing 双轴绝对信号"。

## 1. 诊断(全部已实证验证）

| # | 结构性问题 | 证据(已验) | agent |
|---|---|---|---|
| A | **base 测择时非 merit** | vr 47%+cs 27%=74% 方差,fundamental 仅 13%/corr(fund,base)=**0.27**;龙头 fund+1.09 被 priced_in 压成 HOLD | ④+我 |
| B | **fundamental 是覆盖率代理** | corr(非零industry节点数, \|fundamental\|)=**0.952**;非零节点中位 1、范围[1,24] → \|fund\| 95% 由节点数决定非质量;"Σ后tanh"机制 | ③+我 |
| C | **confidence 是死常数 0.65** | sd **0.012**(122/122≈0.65),来自 2 个估值字段 provider 置信(非本股覆盖),×整个 base → 保序无用却把 BUY 阈值从 0.20 烘到 0.30 | ③④+我 |
| D | **multiplier_stack 在 tanh 后乘带符号 fund** | 121/121 顶出 F7 边界;**41%(fund<0)被顺风乘子(≥1)乘得更负**(scoring.py:1657) | ①③+我 |
| E | **abs()/absolute=True 把利好翻 penalty** | risk/priced/valuation_pressure `absolute=True`(scoring.py:1208);**503/7614 个 raw<0 利好节点被 abs 成拖累** | ③+我 |
| F | **同一估值/动量事实多桶重计** | valuation_rerating(pe%)+overvalued(max(pe,pb)%)+priced_in+crowding 同源;199/223 co-fire;**28% 估值轴矛盾**(pe-only vs max(pe,pb),如 002466 pe_pct0.00 但被判 overvalued) | ①②+我 |
| G | **共模时序百分位**(crowding/historical_pct/overvalued) | 把市场状态烤进绝对分;但**只占方差 9%、只平移水位不毁区分** | ①②④+我 |
| — | **§27 父节点树聚合是死代码** | `_aggregate_parent` 树根不喂最终分;fundamental 走独立 flat Σ(scoring.py:390-423),role_components 走 flat score_target rollup | ③+我 |
| — | **市场乘子惰性≈1.0077** | 120/121 同值、factor≈0 → 不是污染源;但 `max:null` 是哑弹(理论4.95×,F2回填激活) | ②④+我 |
| — | **US/HK 数据 artifact** | US capital_sentiment 均值-0.677/max 0.0(永不为正→67%AVOID);HK 33 dp/股(A股123)饿死→93%HOLD是缺失伪装中性 | ④+我 |
| — | **signal/展示割裂** | signal 比 base、展示比 horizon → 5/122 BUY 但三周期全负("短-0.19/中-0.14 =>积极介入") | ③④ |

## 2. 根因一句话
**base_score 名义"综合投资分",实际测的是估值/情绪均值回归择时;唯一的"质量"桶 fundamental 是覆盖率代理(corr 0.952);并被 abs翻符号/multiplier符号/估值多计/conf死常数 系统性压负(-0.22)。阈值 0.30 在补偿这些 artifact(注释自承从 0.20 抬上来补 F7+confmult)。** → 在修这些前,任何阈值/拥挤标定都是治标。

## 3. 重设计原则
1. **分离 merit 与 timing**(不混成单一 base)。
2. **每轴诚实**:覆盖率归一(不 Σ→tanh)、符号正确(不 abs、不盲乘带符号量)、该相对的横截面(非时序绝对)。
3. **覆盖率是置信 qualifier,不是分数乘子**。
4. **signal = 展示 同源**。
5. **先修刻度,再标阈值**(阈值最后)。

## 4. 新架构

### 4.1 双轴(替单一 base)
- **Merit M ∈[-1,1]** = 公司质量:fundamental(覆盖率归一加权均值)+ 盈利质量 + expectation_gap(分析师/盈利修正)+ 资产负债健康。回答"是不是好公司"。
- **Timing T ∈[-1,1]** = 入场时机:valuation(单一/统一轴/横截面)+ flow/sentiment − priced-in(动量簇 soft-OR)。回答"现在是不是好时机"。

### 4.2 fundamental 聚合:加权均值替 Σ→tanh(修 B/D)
`M_fund = Σ(score×weight×confidence) / Σ(weight×confidence)` —— 节点多不膨胀,质量(score)驱动,覆盖驱动 confidence。顺风 multiplier 符号感知或前置(只放大有利方向)。

### 4.3 折扣桶:只收"坏的量级",不 abs 带符号(修 E)
路由到 risk/priced 的 dp_id 应发 magnitude≥0;若是带符号信号,取坏侧 `max(0,−s)` 而非 `abs(s)`。利好不再变 penalty。

### 4.4 估值:单一/统一轴/横截面(修 F/G)
一个估值信号(统一 PE/PB 轴 + 窗口),**横截面**(vs 同业/archetype)而非自身历史绝对;动量簇(crowding/run_up/fomo/news_age)收成一个 priced-in 因子(soft-OR/max 非 sum)。

### 4.5 覆盖率→置信带(修 C)
用真 per-stock `data_coverage`(实测 0.86 有区分度,非死常数 0.65)。覆盖**不缩分**,定 call 的**置信**:厚覆盖→自信 BUY/AVOID;薄覆盖→"数据不足/低置信"。薄数据股不是被 ×0.65,是被标低置信(可前端单独呈现)。

### 4.6 signal 决策:2D 而非单阈值(修 A/I)
| | T>0(好时机) | T<0(贵/已price-in) |
|---|---|---|
| **M>0(好公司)** | **BUY** | **HOLD/WATCH**("好公司,等回调"，非 AVOID) |
| **M<0(差公司)** | WATCH("便宜的烂公司/value trap") | **AVOID** |
低置信(薄覆盖)→ 任何象限降级为"数据不足"。**好公司不再因为贵被判 AVOID。**

### 4.7 分市场 + signal=展示(修 artifact/H)
A/HK/US 分市场阈值,或先补 HK(33dp)/US(cap_sentiment artifact)数据再打分;trading_signal 与展示分同源。market_adapter `max:1.5` 拆哑弹。

## 5. 分阶段迁移(每阶段可验,plan→分批→agent实施+我验)
- **R-1 修 concrete bug**:E(去 abs 符号锁)+ D(multiplier 符号感知/前置)。低风险,先让 fundamental/折扣桶符号干净。**验**:abs翻转归零、fund<0 不被顺风加深。
- **R-2 fundamental 覆盖率归一(B)+ conf 移出 base→置信带(C)**。**验**:corr(节点数,fund) 大幅降、conf 不再 ×base、阈值回 0.30 真口径。
- **R-3 估值去重计 + 统一轴 + 横截面(F/G)**。**验**:估值矛盾率 28%→~0、共模水位剥离。
- **R-4 merit/timing 双轴 + 2D signal(A)**。架构变更。**验**:龙头不再因贵被 AVOID、value trap 被识别。
- **R-5 分市场 + 阈值重标(I)+ market max:1.5**。LAST。**验**:三市场分布合理、端到端 sanity。
每阶段都:全池重打分 + 端到端 sanity(已知强/弱真股)+ 全套测试 + before/after 归因。

## 6. 与本会话已做的关系
R1(去 market 双计)/R2(接 realtime 死沉)/F6(archetype margin 中位)/诚实度批 都是**信号层卫生**,与本重设计**兼容、且是其前置**(信号层干净了,merit/timing 才有料喂)。**已落地不回退**;重设计动的是它们下游的"桶→base"那层。

## 7. 风险 / 工作量
大(动 scoring.py 核心 compute_company_score/compute_final_score/score_company + aggregator 聚合)。R-1/R-2 是高 ROI 低风险起点;R-4(双轴)是最大架构变更需最谨慎。建议每批 agent 实施 + 我逐 diff 验 + 重打分门。

## 8. 讨论定稿(2026-06-04,与用户逐点确认)

- **D1 — Merit 主干 = 公司财务硬数据**:Merit 以 `L5.fina.*`(ROE/净利率/成长/盈利质量/杠杆,**每股都有、覆盖好**)为主干 → 必须先**治理这批当前未路由的财务 dp_id** 进 Merit(它们在 collected 里却不在 spec score_target → 现在死在打分外,是"Merit 轴空"的根因);稀疏的 L0 industry 块只作"赛道景气"调味。Merit 语义 = 公司质量(财务)为主 + 行业景气调味。
- **D2 — 输出 = merit/timing 双轴**:内部存 Merit M、Timing T 两分 + 2D 推导的 signal;前端默认 signal + 一个主分,高级视图展开 M/T。
- **D3 — 同业参照 = 细分赛道 + 跨市场池 + 分层回退**:
  - 参照系用**细分赛道**(半导体→{HBM, NAND, DRAM, GPU/AI芯片, MCU, 模拟, 射频, 功率, 光模块, 设备, 材料, ...}),**非**粗粒度 archetype——HBM/NAND/光模块 估值景气天差地别。
  - **样本不足处理**:细赛道基准 = 该赛道**全球可比池的"去市场溢价"中位**(A股 HBM 用全球 HBM 池、去掉 A股-vs-美股 的市场层 PE 溢价后比);**仍不足才分层回退**(细赛道成员≥N → 父级 archetype → 行业 → 市场)。
  - **赛道分类**:LLM agent 按 business_desc **自动细分**打赛道标签 + QC 收紧度 + 用户审 low-confidence(沿用 F6 archetype 那套流程,更细一层)。
  - 用于:估值(R-3)+ 拥挤(R-3)横截面参照,可选 margin(替/补 F6 archetype)。
- **待实现期带方案定的收尾项**:① 置信带机制(覆盖率→置信,低置信标"数据不足"而非缩分);② M/T 阈值(绝对口径、放最后标);③ 去市场溢价因子算法;④ 回退 N 阈值。

## 9. 实施进展(2026-06-04)

**已提交(feature/a-share-fixes)**:`7d8e534` R1 · `b5ca128` R2+F6 · `8cd8bb1` 诚实度 · `8a10695` **R-2a+b**。

- **R-1 ❌ 蒸发**(验证后):abs 翻转(③ item E)是**假阳**——3 个折扣桶的 dp_id 全 `field_role=discount`(坏概念),abs 取 magnitude 正确,盲删会把 penalty 反成 credit(灾难)。multiplier_stack 符号(真,41%)+ F7-越界 → 被 R-2b 自然修掉。**结论:R-1 无需独立做。**
- **R-2a+b ✅ 提交 `8a10695`**:① 6 财务硬指标(ROE/ROA/负债率/现金流质量/成长/周转)治理进 fundamental_score(spec+桥归一,SPEC_TOTAL 250→256);② fundamental Σ→tanh 改**覆盖率加权均值**(去 F7、去 multiplier_stack)。**效果**:corr(ROE,fundamental) ~0→**0.727**(质量驱动)、corr(节点数,|fundamental|) 0.952→0.815。9 测试更新到均值语义(手算验证非 force-pass),全套 1152 绿。
  - ⚠️ **merit 量级弱**(sd 0.018,等权均值让混合财务抵消)——**有意留 R-4**(merit 成独立轴 + 因子权重 ROE/成长>周转)。
- **R-2c ⏳ 未做**:conf 移出 base→置信带。**耦合 R-5**:去掉恒定 0.65 haircut 会让 base 涨 ~1.54×→阈值需同步重标。
- **R-3/R-4/R-5 ⏳ 未做**:细分赛道横截面(LLM agent 分类+跨市场池+回退)、merit/timing 双轴+因子权重+2D signal、分市场+阈值重标。

## 10. A 股实测(2026-06-04,3-agent + 验证)+ R-2b 跟进

**实测裁决:R-2a+b 第一版后,A 股信号仍基本不可用**(BUY 1.7%、base 中位 -0.22、10/12 行业零 BUY、龙头寒武纪/天孚/沪硅集体 AVOID)。3 agent 收敛 + 我抽验:
- 🔴 **抓出 R-2b 第一版回归**:覆盖率均值 **average-in 60+ 零分节点**(占分母 74-96%)→ 财务真信号被压 22× → fund sd 0.018、方差 0.1%、merit 进不了信号。corr(|fund|,节点数) 反号 -0.82。
- 龙头被估值杀:valr 单桶 55% 方差垄断 + priced_in 共模(均值 0.337/100%);fund≈0 无力对冲。
- 财务桥本身全对(6 方向+benchmark 100%、corr ROE 0.727 multi-node)。
- 数据 bug:`300750.SZ.yaml` 空壳(0 节点)shadow `STORAGE_GRID/300750.SZ.yaml`(112 节点)→ CATL 错打分(已开 spin-off)。

**✅ R-2b 跟进已提交 `f4a63a7`(排零分节点出分母)**:fund sd 0.018→**0.224**、corr ROE **0.671**、corr 节点数 -0.82→**0.028**(artifact 消除)、寒武纪 AVOID→WATCH。**merit 现在是干净的质量信号、真进信号了——R-2 至此做对。**

**重排剩余(实测驱动,signal 可用性优先)**:
1. 🔴 **R-3 估值去垄断**(最高 ROI 给可用性):valr 横截面化(细分赛道)+ priced_in 去共模/去簇——修"龙头被估值杀"。
2. R-2c(conf 死常数→置信带)· R-5(阈值,base 刻度对了再标,符合用户"不 peg 百分位")· 300750 空壳快修 · R-4(merit/timing 双轴+因子权重,merit 已有量级,此为锦上添花)。

**提交链**:…`8a10695` R-2a+b · `f4a63a7` R-2b 跟进 · `87e28c3` **R-3a**(priced_in 横截面去共模) · `a3ad2bc` **R-3b.2**(valr 分层横截面) · `30afd1b` **Phase-2a**(funding wiring:active_inflow 接进 funding_score)。全套绿。

**R-3 后剩余(实测驱动)**:R-2c(conf 死常数→置信带,**与 R-5 耦合**:去 0.65 haircut 使 base ↑~1.54×)· **R-5**(按新 base 刻度重标 BUY/HOLD/WATCH 阈值,修 BUY% 6.0——base 刻度现已诚实可标)· 300750 空壳快修 · R-3b.3(A+US 跨市场去溢价,救寒武纪/天孚型)· R-4(merit/timing 2D)。

**SPEC 完整度填充主线(用户转向,详见 `a_share_spec_completeness_2026-06-05.md`)**:`30afd1b` Phase-2a(funding wiring)· `3c4ce93` Phase-2b(11 行业 L0 景气)· `2ddd122` Phase-2c(全 A 股 L1-L3 codex 填,Unknown 4022→837)。**完整度达成 → Phase 3 标定(R-2c/R-5)现可在非稀疏数据上做(避免用户担心的过拟合)。**

## 13. 用户战略转向(2026-06-05):先 SPEC 完整度,后标定

**用户裁决**:"一直用这些少数样本(116 只、字段残缺)标阈值会**过拟合**。先把 SPEC 字段完整度 + 如何算进公式搞定,再补齐 A 股所有公司的 SPEC 字段,**然后**才标定。" → **R-2c/R-5 暂停**(R-2c 已实装即**回退**,保持停在 `a3ad2bc` R-3b.2;1 行,恢复秒重做)。

**接地勘察(116 A 股)**:
- **公式链 + realtime 层完整度**:fundamental_score(102 dp→merit+)realtime 仅 **21 个有数据/均 20%**;valuation_rerating(15)**61%**(故 valr 主导);risk(39)14%;eg(24)34%;**152 个参与打分 dp_id realtime 覆盖<50%**(大头 L0.* 行业定性)。
- **harness 真实到达(overlay+realtime+继承)纠正**:fundamental **median 14 非零节点/股、100% 股≥1**(L0.* 经 industry_overlays 继承到达)→ merit 非"节点饿死",但 realtime 仅 20% → **这 14 节点的真实性(真源 vs overlay 手填 proxy/默认中性)是关键未知**。funding_score **median 0、仅 1% 股**(基本死)。priced_in median 1/53%(R-3a 去共模后正常)。
- 既有 `a_share_score_fidelity_audit_2026-06-03.md` 仅 5 只 AI_COMPUTE(per-stock 223节点/71 known),非全 A 股。

**计划(待批)**:
- **Phase 1 — 全 A 股 SPEC 完整度 + provenance 审计**:逐 dp_id × A 股分类 真源/overlay/proxy/mock/可解释缺失 + 是否到达分数 + 经哪条链;按 score_target 汇总"真值喂入率"。产出全宇宙保真度账本(扩展 5 股版到 116)。
- **Phase 2 — 补齐**:对真值缺口(尤其 fundamental 的 L0.* 行业定性 + funding_score)按市场/行业批量填(LLM 闭环 + 真源采集),覆盖全 A 股。
- **Phase 3 — 然后** R-2c/R-5 标定(在完整诚实 base 上,不过拟合)。

## 12. R-3b.2 诊断清单(2026-06-05,只读、用户要求"先查清再动码")

每个 valuation_rerating 信号的 derive 基础 + aggregator 归一 + 分类(以 002371 北方华创为锚:peer_compare +0.256 说"vs 同业便宜"却被淹没):

| # | 信号 | derive 基础 | aggregator 归一 | 分类 | 贡献 |
|---|---|---|---|---|---|
| 1 | **L6.state.peer_compare** | `premium_vs_industry_pct`=stock_pe vs **行业中位** | `tanh(prem/30)` flip | **横截面 ✓(行业级)** | 是(sd0.69) |
| 2 | L6.state.historical_percentile | `_percentile_rank(pe, 自身183d历史)` | `(pct−.5)×2` invert | **时序 ✗(自身历史)** | 是(龙头杀手) |
| 3 | L6.state.expansion_compression | `ratio_vs_250d`=PE vs **自身250d MA** | `−tanh((r−1)×2)` | **时序 ✗** | 是 |
| 4 | L6.path.tag | 自身 `pe_percentile`/state_expansion | tag→score | **时序 ✗** | 是 |
| 5 | L6.mult.ps | `−tanh(log(ps/_PS_REF=4 全局))` | 同 | **绝对 ✗(全局ref,非池)** | 是(饱和−0.99) |
| 6 | L6.mult.ev_ebitda | `−tanh(log(ev/13 全局))` | 同 | 绝对 ✗(全局) | 部分(conf低) |
| 7 | L6.mult.forward_pe | `−tanh(log(fpe/22 全局))` | 同 | 绝对 ✗(全局) | 是 |
| 8 | L6.state.peg_match | PEG vs 固定带(1,2)、**growth 调整** | banded score | 绝对但 **growth-adj(最不污染)** | 是 |
| 9 | L6.path.second_derivative | 估值扩张加速度 | `tanh(x/1)` | **path(≈0,sd0.009)** | 可忽略 |
| — | pe/pb/mcap_fcf/dcf/peg/industry_center | — | data-only/None | — | 否(mapped=0) |

**裁决**:9 个有效信号里**唯一干净横截面**是 peer_compare(行业级);3 个时序(自身历史)+ 3 个绝对(全局 ref)把它淹没。

**R-3b.2 推荐术式(待用户确认后实施)**:
- **锚**:peer_compare 升级到**分层池**(archetype≥N→industry→market),PE 主 + PS 补(负 PE 股)。
- **压制**(peer_context 门控、仅 A 股):historical_percentile + expansion_compression + path.tag(3 时序)+ ps + ev_ebitda + forward_pe(3 全局绝对)。
- **保留**:peg_match(growth-adj GARP、与 level 正交)+ second_derivative(≈0 无害)。
- **诚实预期**:北方华创型(vs 同业便宜却被自身历史杀)回升;寒武纪(+342% vs AI_COMPUTE)/天孚 仍负(vs A 股同业真贵;全球 AI 芯片/光模块对比 = 跨市场 R-3b.3;R-4 的 merit/timing 2D 让"好公司但贵"=HOLD 而非 AVOID)。

### 12.1 R-3b.2 实施结果(用户定术式照做)

**实现**:① `peer_context.py` 加 `build_valuation_pools`(分层 archetype≥5→industry→market,PE/PS 池)+ artifact 持久化(`save/load_peer_context`、`build_and_save`);② aggregator `_xs_valuation_signal`(PE 主/PS 补 vs 池 percentile)+ `_VALR_SUPPRESSED_WHEN_POOLED`(6 信号)+ peer_compare 锚分支 + 扩展 fallthrough 守卫;③ **架构修正:冷建 peer_context=16s,绝不能在请求路径**——改 server/CLI **加载预计算 artifact(<10ms)**,离线 `mvp20 build-peer-context` 刷新(derive 后跑)。

**实测(116 A 股 3-way:none/r3a/r3a+r3b2)**:
- valr mean +0.046→**+0.002**、median +0.129→**+0.001**、sd 0.414→**0.328**(诚实零心横截面)。
- base median −0.122→**−0.154**、BUY 16→**7**、AVOID 27→**25**、HOLD 37→44。**BUY% 降是 valr 去掉人为正偏的正确代价**(对陈旧 0.30 阈值敏感→R-5 重标)。
- **北方华创 AVOID→HOLD**(valr −0.533→+0.476、PE 81.9<SEMI 池中位 96.8)✓ 核心目标;一批"vs同业便宜却被自身历史杀"AVOID→HOLD。
- 变差的均为**真·vs同业贵**(中免 31>22.6、福耀 15.3>13.7、国航 59.8>28.7)— 横截面判断正确。
- 寒武纪/天孚 仍负(vs A 股 AI 真贵 = 预期,需跨市场 R-3b.3)。
- 测试:`test_peer_context.py` +14(分层池/xs信号/压制+守卫/peg不压/save-load),全套绿。
- **artifact 是 runtime 态**(`runtime/peer_context_A.json`、23KB、gitignore;derive 后 `build-peer-context` 刷新)。

## 11. R-3 计划(2026-06-04,接地调查后；草稿待用户批准）

### 11.1 现状实证(当前 `f4a63a7` 代码、116 A 股重打分）
- base mean **−0.261** / sd 0.414 / **BUY 7.8%**(9/116)；中位仍负。
- **方差归因(cov→base)**:valuation_rerating **70.9%**(sd 0.414=base 全部 sd)> capital_sentiment 36.4% > fundamental(merit)24.7% > priced_in 15.1% > risk 5.2% > eg 2.0%。**timing(valr+cs+priced_in)≈122% vs merit≈27%** → R-2b 修对 merit 量级(sd 0.225)但 signal 仍被 timing 垄断。
- **priced_in 共模 −0.332/100% 股票**:源头 = `L6.priced.run_up`(116/116、mean **+0.438**、`max(d20,0)/0.20` 绝对标度;全市场普涨→人人被扣)。news_age 仅 10 只、crowdedness 已是 percentile。
- **valr 71% 方差源**:`historical_percentile`(sd 0.771,**时序自身历史** `_percentile_rank(cur, 该股历史)`→龙头自身高位被杀)+ `ps`(sd 0.669 绝对)+ `path.tag`(sd 0.765)。`peer_compare`(sd 0.694)已横截面但**粗**(行业级)。
- **latent gap**:`L6.mult.pe`(112/116 present)/`pb`(116)/`mcap_fcf`/`industry_center` 全 **mapped=0** → PE/PB 当前对 valr **零贡献**(归一器读不出 payload）。
- **架构约束**:当前**无横截面(同时点对同业)估值机制**;percentile 类全是时序自身历史。R-3 须新增"**横截面参照 pass**"(见全体票→算 universe/同业/细分赛道分布→per-stock 归一器回读)。**R-3a/R-3b 共享此基建**。

### 11.2 R-3a — priced_in 去共模 ✅ 已实施(先行、低风险、纯逻辑、无新数据）
- **机制(定稿)**:新增 `build_peer_context`(aggregator)+ `mvp20/peer_context.py`(provisioning + db-mtime 失效缓存)——A 股池横截面参照 pass。run_up/crowdedness 归一器在有 peer_context 时改"**横截面 percentile、只取高尾** `max(0,(xs−0.5)×2)`"(中位股→0 by construction、只罚比同业更 priced-in 的),无 peer_context 落回原绝对行为(bit-for-bit back-compat)。peer_context 经 `aggregate_company_graph→synthesize→_realtime_signal→_realtime_field_signal` 线程化。**只对 A 股建池**(HK/US→None→不变)。
- **实施中两处关键发现**:① 打分里 **run_up 普遍=0**(freshness gate 因数据陈旧清零)——"run_up 是共模源"是 raw 信号的误判,**真正共模是 crowdedness**(node score −0.65,abs 把 uncrowded 也罚满,§4.3 预见);② 必须加 **fallthrough 守卫**:peer 治理的 dp_id 返回 None 时不能落回 legacy generic-percentile 路径(否则去共模被撤销)。
- **实测裁决(116 A 股 before/after)**:priced_in median **+0.355→+0.026**(共模消除)、sd 0.173→0.231(判别力↑);base median **−0.216→−0.122**、mean −0.261→−0.163;**BUY 9→16(7.8%→13.8%)**、AVOID 34→27。valr 不变(=R-3b)。龙头仍被 valr 杀(寒武纪 WATCH/天孚 AVOID/北方华创 AVOID)——证实分工:R-3a 修全体共模、R-3b 修龙头(valr)。
- **测试**:`tests/test_peer_context.py` 15 新测(helpers/build/normalizer/**守卫**/back-compat/provisioning);全套绿。
- **接线**:CLI `score-company` + server `handle_score`(仅 A 股、缓存)均已用 peer_context → app 与 harness 同口径。

### 11.3 R-3b — valr 细分赛道横截面(复用 R-3a 基建、设计面大、带用户审）
- **R-3b.1 细分赛道分类(LLM agent + 用户审)**:按 business_desc 自动打细赛道标签(半导体→HBM/NAND/DRAM/GPU/MCU/模拟/射频/功率/光模块/设备/材料…),QC 收紧度,low-confidence 用户审(沿用 F6 archetype 流程更细一层)→ 落 config。
- **R-3b.2 valr 横截面化**:扩展参照 pass 到细赛道池;valr = 估值 vs 细赛道池横截面 percentile;**分层回退**(细赛道成员≥N → 父 archetype → 行业 → 市场);valr 权重从时序(historical_percentile)→横截面;可选修 PE/PB mapped=0。
- **R-3b.3(可选/后续)**:A+US 跨市场池(数据在:US 115 只有估值)+ 去 A-vs-US 市场层 PE 溢价。细赛道样本薄→去溢价噪声大,故列为后续。

### 11.4 用户已定(2026-06-04）
- **Q1 顺序 → R-3a 先行 + 提交门、R-3b 随后**(✅ R-3a 已实施待提交)。
- **Q2 R-3b 池范围 → A 股池 + 分层回退先行**,A+US 跨市场去溢价留 R-3b.3 后续。

## 14. Phase 3 标定已实施(2026-06-05,R-6 后,在诚实 base 上)

R-6 收口 SPEC 完整度(55 个死定性 dp_id 改非打分,score-neutral)后,Phase 3 校诚实**刻度 + 阈值**。

### 14.1 R-2c(去 confidence 死乘数)✅
`scoring.py:1719`:低置信股的 `confidence_multiplier`(≈0.65)原**乘进** short/med/long/base,把分数整体压 ~1.54×、把"有多确定"和"信号多强"揉成一个数 → BUY 被压到 6%。R-2c:**记录 confidence 作 band、不再乘进 base**。效果:base 解压、sd 0.298→0.462(分布展宽),signal 极化(强信号回全幅度)。测试 `test_confidence_role_recorded_as_band_without_compressing_base` 重写;全套件绿。

### 14.2 R-5(阈值按诚实绝对刻度重标)✅
**关键发现**:market_adapter 对 A 股**经验上 ≈ 恒等**(multiplier median 1.007、range 0.995–1.05)→ `market base ≈ core base = 直接(merit+估值+资金−risk−priced_in)`,**base=0 是干净绝对中性**。旧阈值 0.30/−0.10/−0.45 是 T3 **按 p70 卡百分位**定的(用户要弃)。R-5 按**绝对意义**重标(用户:不卡百分位、市场差可没 buy):
- **BUY ≥ +0.20**(正分量明显盖过风险=有把握,非 base 刚过 0)/ **HOLD ≥ −0.15** / **WATCH ≥ −0.50** / **AVOID < −0.50**。
- 弱市 mix:**BUY 18(16%)/ HOLD 33 / WATCH 29 / AVOID 36(31%)**。vs R-6 基线(BUY 7/HOLD 44/WATCH 42/AVOID 23):WATCH→AVOID 13、HOLD→BUY 11、92/116 不变。

### 14.3 R-7(动态宏观 regime)— 已诊断、deferred 到回测
用户问"有没有动态方案"。诊断:**regime 层已建但休眠**——`market_adapter` 的 `market_regime` 因子分 = +0.0815 恒定(真算出的温和正 regime),但 beta 把它压成 multiplier ≈1.0(±5% 封顶、几乎不动 base)。**真正动态 = 放大 market_regime_beta 让牛市整场抬升/熊市整场下沉 + 固定绝对阈值**(不卡百分位,自然实现"市场差→少 buy")。
**caveat**:R-3 横截面去共模使个股 base 对宏观**半钝感**(齐涨齐跌被剔),所以宏观 regime 叠加恰恰是"市场差→少 buy"的正解;但放大 regime = **择时押注**,beta 手调=猜。**用户定:留 R-7,用 PIT 回测验证"加宏观择时是否提升前向 IC"后再用数据定 beta**。

**gotcha**:回测若复用 live `mvp20.scoring`,Phase 3 改了打分输出 → 应分别钉 `c258154`(R-6 后/Phase3 前)与 Phase-3 提交两个 commit 对比。

## 15. Review 返工(2026-06-06,3-agent review + 我逐条自验后)

3-agent 对抗 review 查出**两个 BLOCKER,我自验属实**:

1. **R-6 运行时是 no-op**:`field_governance.apply_to_node(overwrite=False)` 不覆盖 overlay 节点 baked-in 的 `participates_in_score: true` → spec 的 false 进不到 scorer。我"R-6 score-neutral 已验"是真的,但**原因是改动没传播**,不是本就中性。
2. **死节点稀释 damp 虚高 base**:`_sum_role_target(damp=True)` 的分母把 score=0 死节点也算进去。拆解:damp 分母里 **LIVE 真信号仅 36%、DEAD55 假零占 40%**、Inactive 9.7%、真零 13.4%、未知 0.3%。f4a63a7 只修了 merit mean、没修 damp。

**返工(commit,5 文件):**
- **field_governance.apply_to_node**:`participates_in_score` 改由 spec **权威覆盖**(它是治理决策非 codex 数据)→ 55 个死节点运行时**真退出 damp**。验证:运行时节点 participates→false、LIVE 不变 79、全套件绿。
- **效果(诚实刻度)**:risk 去稀释 → base median **−0.236→−0.401**、BUY 18→**10**、AVOID 36→**48**(Δbase 中位 −0.16、31/116 翻)。这是"诚实风险揭示弱市"的真相,之前 risk 被假零稀释 40% 而虚高。
- **R-5 阈值不变**(0.20/−0.15/−0.50 绝对意义;base=0 仍中性、market≈identity),只更新注释 mix 到诚实数。AVOID 41% 是诚实结论(用户确认保持绝对刻度)。
- **onboard(Agent 3 MAJOR)**:`save_peer_context` 改**原子写**(temp + os.replace,失败保留旧产物、无 torn read)+ build 失败 `log.warning` + preliminary 挂 `valuation_warning`(不再静默吞掉新股估值退化)+ 原子写测试。

**留回测(R-7 同批):** Inactive(9.7%,无事件=真 benign)/ 真零(13.4%,真实中性读数)该不该稀释 damp = 建模分岔(去掉再 −0.20 到 base −0.60)。用 PIT 回测验"排除 benign 读数是否提升前向 IC"再定,不手调。

**minor(顺手/后续):** derive.py `L11.trade.signal` 阈值(0.45/0.10/−0.20)与 scoring 脱节、test_scoring 注释 nit;pit_backtest/report.py 硬编码旧阈值=回测对话隔离文件,归其处理。
