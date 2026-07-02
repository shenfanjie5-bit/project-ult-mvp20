# A股评分修复 campaign — 续作状态（压缩前存盘 2026-06-03）

> 分支 `feature/a-share-fixes`。本 doc + `a_share_score_fidelity_audit_2026-06-03.md` 均为工作参照，campaign 全部收尾后可废弃。

## 已提交 commits（本 campaign 相关）
- `bfc704a` P1 加股票后端 · `e3bede2` onboard 初步分早持久化 · `f40d37f` governance 测试 hermetic
- `c38495a` **Batch1+2 评分修复**（消费侧,已验证,suite 1031 绿）：
  - C-1 情绪双计（market_adapters.yaml 删 sentiment_score）· M-1 top_path 按 effective sign 排序（scoring.py）
  - C-2 trend:up 满格 cap 0.2 · C-3 run_up freshness gate · M-2 gross_margin 非对称负尾（aggregator.py）
  - 效果(已验证)：000063/601138 假 BUY→HOLD；000977 量级回归；300308 真涨；688256 稳 BUY。

## ✅ Batch-3 已提交 commit `ee7e78d`（H-1/H-2/H-1b/H-3,2026-06-03 22:45）
**Phase A 收尾结果（已验证）**：
- **A0**: 10/10 AI_COMPUTE revenue_growth 修正（yoy_compare=20250331,percent,QoQ 非零）。**新发现 H-1b**：原 H-1 不完整——income `limit=5` 在有 update_flag 重述行时 distinct 周期不足 5 个,上年同期被挤出窗口→静默跳过（4/10 滞留旧值:000063/000977/300308/688041）,且重复行使 records[1] 同周期→QoQ=0。补丁 `limit=12`+按 end_date 去重（优先 update_flag='1'）,镜像 cashflow 段。300308 验证 192.12%。+1 hermetic 测试。
- **A2/H-3**: re-derive 后 `L8.val.overvalued` 与 `L6.state.historical_percentile` 的 pe 百分位 **10/10 完全一致**（BEFORE 矛盾:000063 state0.91/val0.0、300502 state0.97/val标 normal）。H-3 代码已确认正确 scoped:仅 PE/PB 走 250d,close/run_up 仍走短 90d。
- **A4 打分**（BEFORE 21:21 baseline 含旧 revenue_growth+旧估值 → AFTER）:篮子普遍下移、多只降级(002463 BUY→HOLD、002916/300394→AVOID、601138 HOLD→AVOID、300502/300308 留 BUY 但 long 大降)。**归因（path 分解已验证）**:跌分 = H-3 估值正确施压(95-318x PE 高估股)+ revenue_growth 现为真信号(正向 path 部分抵消)+ re-derive 新鲜价格使 run_up 的 d60 首次填充(300308 +129%/300502 +95% 真实暴涨)且 C-3 freshness gate 放行新鲜过热罚分。**非回归**——正是审计要的"假 BUY 修正";模型仍有区分度(强基本面 300308 留 BUY、弱基本面 601138→AVOID)。**qoq_pct 不被任何打分代码消费**(已确认),故 H-2 的 qoq×100 无害。
- **A5**: 全套 1037 passed/0 fail。**A6**: commit `ee7e78d`(4 文件)。

**Batch-3 衍生 follow-up（预存,非本批引入,待定）**：
- **FU-1 估值双渠道(已验证 2026-06-03)**:同一 PE/PB 百分位经两条渠道进分——`L8.val.overvalued`→`risk_discount`(company_score 风险侧,用 max_quantile)+ `L6.state.historical_percentile`(及 expansion_compression/pe/pb)→`valuation_rerating`(final_score 再定价侧,weighted_sum)。**spec 显式给两个不同 score_target,属有意设计(去估值风险 vs 再定价),非代码 bug**;H-3 使两侧都正确变强→叠加罚分大(并入 FU-2 校准)。**B2 的 ev_ebitda/forward_pe/peg/peg_match 全部 score_target=valuation_rerating**(已查 spec),只进再定价侧 weighted_sum、不碰 risk_discount → 不制造新跨渠道双计,B2 安全(只让贵票的估值证据更全)。校准决策(两渠道是否过罚)留用户定。
- **FU-2 负向簇饱和**:run_up+overvalued+path.tag/fomo 同时贴 -0.9~-1.0 堆叠,过热但强基本面股可能被过罚(校准问题,类比 C-2/C-3/M-2)。

## （原）⏳ Batch-3 未提交记录（保留供追溯）
**代码(未提交,在磁盘)**：`mvp20/sources/tushare_source.py`(H-1 revenue_growth 用 `_find_record(_yoy_period())` 选上年同期 + H-2 ×100 改 percent；goodwill_ppe 发射条件待修见下) · `mvp20/derive.py`(H-3 `_fetch_a_share_history` 加 `pe_pb_days=250` 统一估值窗口) · `tests/test_derive.py`+`tests/test_tushare_derive.py`(5 新 hermetic 测试)。**全套 1036 passed/0 fail 已验证。**

**DB 已做**：re-collect 10 只 AI_COMPUTE(`--source tushare --universe /tmp/uni10.yaml`)+ 4 只重试(/tmp/uni4.yaml,网络 flake 后)→ **revenue_growth 应已全部修正**（验证：`SELECT value_json ... dp_id='L5.is.revenue_growth'`，yoy_cmp 应=2025**0331**、percent 值如 688256=159.55/601138=56.5/300308=192）。
**DB 备份**：`runtime/hot.sqlite.bak.scorefix`。BEFORE 分数：`/tmp/score_before_batch3.txt`。

**Batch-3 还差（续作步骤）**：
1. 确认 10 只 revenue_growth 全部 yoy_cmp=20250331（4 只重试后复查）。
2. **valuation re-derive(H-3)**：`derive_all(db, ts_codes=[10], a_share_only=True)` + `DeriveRunner(db).run_all([10])` → 重算估值百分位(统一窗口)。
3. `compile-overlays --db runtime/hot.sqlite` + score-company 10 只。
4. 验证审计预测：688256 long 升(~0.82)、300308 revenue 正向进分、L8.val.overvalued 与 L6.state.historical_percentile 一致。
5. 跑全套 → **提交 Batch-3**（4 文件）。
6. （可选全量回填：re-collect/re-derive 全 116 A 股,使全池修正——重,网络/token。）

## 62 字段缺口分析（688256 代表,已验证）
in-score 118/250；**不进分 131 = 数据缺口 62 + Inactive 休眠 42 + spec 非计分 27**。
62 缺口再分（已 agent 分析+独立验证）：
- **A 能算但没算 8**（输入全在 DB,加 derive 即补）：`L5.bs.goodwill_ppe`(改发射条件:goodwill=null→0)、`L6.mult.ev_ebitda`(EV=mcap+debt−cash / EBITDA 已在 L8.fin.debt_pressure.ebitda_cny)、`L6.mult.forward_pe`(一致预期 EPS 11.70 在 L5.fcst.eps_cf)、`L6.mult.peg`(PE÷增速)、`L6.state.peg_match`、`L6.priced.news_age`(公告时间衰减)、`L7.env.style`(消费方 derive_l7_env_risk_appetite 已留 style 形参,接 index_daily 成长/价值)、(L6.mult.dcf 边界)。
- **B 能 LLM 填但 codex 这轮漏填 40**：全 L0(25)+L1-L4(14)+L8.reg —— 都在 governance(route=llm_close/web)、source_deps+年报已在库。说明即便填充股,codex 也没填满 L0-L4。
- **C 需新数据源 11**：fx(fx_daily 没接,L7.env.fx/L9.macro.fx)、机构流向(龙虎榜/L2,L7.flow.institutional/L9.capital.inst_buy_sell)、行业库存/价格 L10、DCF、IV。
- **D 真缺失 3**：L7.trade.gamma/iv/options_cp(个股期权,寒武纪无)。
- **头条:48/62(77%)不是数据缺、是"没接线"(40 codex+8 derive);仅 3 真缺失。**

## spec 完成度（A股,116 只;10 LLM填充,106 未填）
填充 cohort 均值/250：participates 223(89%)、usable 145(58%)、real_self 83(33%)、overlay 46(18%)、in-score 118(47%)；**但"真数进分"仅 ~72/250≈30%**(其余 in-score 靠 18% LLM 定性 overlay)。未填充股 in-score ~78(31%,纯真数,overlay 0)。诚实校正：mock_only 工具报 0,实每股 4 条非 canonical mock 行(盲区)。

## xhigh vs low（之前 C1）质量对比（3 只 000063/300308/688256,已跑）
schema 违规 0=0(平)、hard 证据违规 0=0(平)、**excerpt 误引 low=60 vs xhigh=0**(xhigh 胜)、引用更细、grounding 更直接(如 L2.newbiz.tam xhigh 引佐证行+加 revenue_pct)。结论:换 xhigh 不显著改分数(结论一致),但证据保真度更高。建议维持 hybrid(low 主力,xhigh 用于高价值/审计股)。产物 /tmp/xhigh_cmp/*.{low,xhigh}.yaml。

## 审计剩余未修（低优先）
M-3 guidance 陈旧(刷新 forecast) · D-low 非 canonical mock 行写入生产快照(collector/BFF mock feed 加 dev gate) · D-nit 覆盖率 honesty 口径(dump 工具把 overlay-authored 算 usable)。

## 下一步（已定:A→B 全做,B=8 个；用户已批准）
- Phase A（Batch-3）✅ 完成提交 `ee7e78d`。
- **进行中:Phase B = Batch-4 derive 快赢**(顺序+逐个独立验证 diff;FU-1 已验证非阻塞)。进度:
  - **B1 `L5.bs.goodwill_ppe`(null→0)✅ 实现+实盘验证**(inline):688256/000063 imputed 0(`goodwill_imputed_zero=true`),300308/601138 保留真实 goodwill。+2 hermetic 测试。
  - **B2 4 个 L6 估值倍数 ✅ 实现(agent ae7a228)+实盘验证**:collect 侧把 mcap/shares 持久化进 `L6.mult.pe` payload(`total_mv_cny`/`total_share`,total_share 单位万股已实盘确认,隐含价=实际收盘);快照 derive 公式发射 ev_ebitda/forward_pe/peg/peg_match。688256:ev_ebitda 370.46、forward_pe 117.78、peg 1.997(全对预测)。000977 PEG 因增长 -24.3% 负 → 正确 Inactive。新增 `_INACTIVE_TOLERANT_INPUTS={L8.fin.debt_pressure}`(ebitda_cny 在 Inactive 行仍有效,已核)。+12 测试,受影响测试 115 passed。小瑕疵:000977 PEG Inactive 的 missing_inputs 标签不精确(实为增长负,非缺输入)——待 polish。
  - **B3 `L6.priced.news_age` ✅ 实现(agent a53cec2)+实盘验证**:快照 derive,读 L9.event.intraday_announcement 最新 ann_date,magnitude=0.6×0.5^(age/30),peak damp 到 0.6(FU-2,routine 公告不饱和)。DeriveRunner 加 `_FORMULAS_WANTING_NOW` now-注入(签名内省,只给声明 now 的公式追加,其他不变)。10 只:9 Known(0.39-0.55 按 age 衰减)+688041 Inactive(无公告)。
  - **B4 `L7.env.style` ✅ 实现(agent a53cec2)+实盘验证**:collect 侧 `_emit_market_style`,MARKET:CN 成长(399370.SZ)−价值(399371.SZ)20d 收益差。实盘 growth_minus_value=+0.0497(regime=growth)。
  - **✅ Batch-4 提交 `1572923`**(5 文件,+1136/−12):全套 **1063 passed/0 fail**。评分影响(vs Batch-3):小且混合——PEG/peg_match 加细致度(高增长 justify 高 PE),部分抵消 H-3 估值钝罚(002463 HOLD→BUY、300308/300502 BUY↑、688256 BUY↓微)。
  - **dcf(L6.mult.dcf)缓做**:边界项,需 DCF 假设(折现率/永续增长/终值),数据无法干净提供,deferred。
  - **B2 小 polish 待办**:000977 PEG Inactive 的 missing_inputs 标签不精确(实为增长负)。

## campaign 收尾态(2026-06-04)
- **提交**:Batch-1/2 `c38495a` · Batch-3 `ee7e78d` · Batch-4 `1572923`(均 feature/a-share-fixes,未推)。
- **新接线 dp_id(7)**:goodwill_ppe(imputed0)、ev_ebitda、forward_pe、peg、peg_match、news_age、env.style。+ revenue_growth/估值窗口修复(Batch-3)。
- **DB**:10 只 AI_COMPUTE 已全量 re-collect+re-derive,新 dp_id 已落库。备份 hot.sqlite.bak.batch3pre / .bak.scorefix。
- **校准 follow-up(待用户定)**:FU-1(估值双渠道 risk_discount+valuation_rerating,spec 有意但 H-3 后叠加大)、FU-2(run_up+overvalued+fomo+news_age 负向簇饱和堆叠)。
- **可选全量回填**:其余 106 只 A 股未含新 dp_id(只 10 只做了);全池 re-collect+re-derive 重(网络/token)。

## 并行批次 Batch-5/6(2026-06-04,用户要求并行 opus agents)
- **Batch-5 `0160774`**:fx(`L7.env.fx`/`L9.macro.fx`,USDCNH.FXCM 20d)+ 龙虎榜(`L9.capital.inst_buy_sell`/`L7.flow.institutional`,top_inst 机构净买,enriched score/direction)新 producer(agent ac18970,worktree)+ Inactive 标签 polish(missing_inputs vs `formula_undefined`)+ 顺手修午夜 flaky 测试(test_akshare_cls 跨午夜日期/时间不一致)。⚠️ **worktree 从旧基线 b5aaed4 fork(harness 问题,缺 Batch-3/4)→ 3-way apply 到当前树(与 Batch-4 零重叠,干净)+ 实盘核 endpoints(USDCNH.FXCM 11 行、top_inst 910 行)**。全套 1077。000063 inst_net_buy +11.4 亿→score 0.90。
- **Batch-6 `17bbd40`(FU-1/FU-2 校准)**:验证 **risk_discount 双减 bug**——core `−risk` + market adapter `local_risk_discount` 同值再减(601138 0.347×2、300394 0.119×2,实测 market 折扣==core risk)。**完整修**:三市场 market_adapters `discounts: {}` + `overvalued→risk ×0.5`(A)。**不回紧阈值(let-flow)**。效果:10 只里 002916/300394/601138 **AVOID→WATCH**,无 BUY 降级,000063/000977 仍 HOLD;全池 121 A 股 BUY 43%/WATCH21%/HOLD23%/AVOID13%(区分度保留)。全套 1077(2 处断言更新为单计/0.5×)。
- **FU-1/FU-2 分析产物**:`/tmp/calibration_proposal_FU1_FU2.md`(只读 agent a3a3738)。
- **校准余项**:BUY% 升 43%(let-flow 自然结果,想收紧重定 SIGNAL 阈值);**FU-2 run_up 单节点卡 0.6** 仍是独立 priced_in 杠杆(C+A 未触及,去底后不紧迫)。
- **提交链**:c38495a→ee7e78d→1572923→**0160774→17bbd40**(feature/a-share-fixes,均未推)。
- **仍缓**:dcf、全量回填、40 codex 重填 L0-L4、M-3 guidance、D-low mock gate。
- 余下低优先:FU-1/FU-2(上)、40 codex 重填 L0-L4、接新源(fx/龙虎榜)、M-3 guidance 刷新、D-low mock gate。

## ════ Post-Batch-6:PR + 路线审计 + L0 校准(2026-06-04,压缩存盘)════

### PR + CI
- **PR #1**:`feature/a-share-fixes → main`,OPEN,https://github.com/shenfanjie5-bit/project-ult-mvp20/pull/1。**分支已 push**(有 upstream)。
- **CI**:`.github/workflows/ci.yml`(ubuntu/py3.12,`pip install -e .[dev]` → mvp20 validate/verify/plan/fixture → pytest)。**曾绿过一次**;最新 push CI 在跑。
- **CI 修复 `17da200`**:46 失败(test_server 28 + test_futu_options 18)全是**预存 CI 环境问题**(main 自 5-13 就红、本地全绿):futu SDK 不在 `[dev]`→加 `futu-api`;vendor adapter 包(graph_engine 等)CI 装不了→test_server 在 `_AVAILABLE=False` 时 skip。**与 campaign 无关**。

### 完整提交链(feature/a-share-fixes,均已 push)
`c38495a`(B1/2)→`ee7e78d`(B3)→`1572923`(B4)→`0160774`(B5)→`17bbd40`(B6 FU-1)→`17da200`(CI)→`2f8813c`(F1)→`70deee2`(F4)→`ec15894`(C1-unblock)→`f335c26`(F8)→`63d25cb`(L0+F7+F5 校准)。

### Post-Batch-6 修复(全已提交+验证,全套 1126 绿)
- **F1 `2f8813c`**:Batch-4 的 4 个 dp_id(ev_ebitda/forward_pe/peg/news_age)发 `scalar` 键、`_realtime_signal` 不读→ZERO 进分(peg_match 能用掩盖了)。修在 aggregator `_realtime_field_signal`:news_age 读 magnitude;ev_ebitda/forward_pe 用 **log-ratio `-tanh(ln(m/REF)/SCALE)`**(高倍数→负;fwd_pe REF22/SCALE1.1、ev REF13/SCALE1.4);**raw peg 留 data-only**(peg_match 已 band 它,避免 PEG 双计);pe/pb 不动(走 historical_percentile)。+9 bridge 测试。
- **F4 `70deee2`**:`L9.capital.inst_buy_sell` score_target `expectation_gap`→`funding_score`(机构净买是资金流,进 capital_sentiment)。000063(+11.4亿净买)→capital_sentiment 0.72。
- **F8 `f335c26`**:mock dev-gate(`MVP20_ALLOW_MOCK`/`--allow-mock`,默认拒绝)。**实测确认打分侧早已按 source 丢弃 mock:*** —— HK/US 的 canonical mock 行**不进分**(Agent B 那点偏重了)。
- **C1-unblock `ec15894`**:industry L0 prompt 之前查 `INDUSTRY:` 键→读不到 per-stock 源。改 codex_prompt_gen **按成员聚合**(mean/median/min/max+成员样本)。
- **C1 L0 填充 + 校准 `63d25cb`(capstone)**:
  - **填充**:AI_COMPUTE 行业 overlay 19 个 L0 Known(财务驱动)+ 12 Inactive(policy/tech/compete 的 CLS 新闻源 upstream 挂——`ak.stock_info_global_cls` 超时;恢复后 `--source akshare` 重采即填)。
  - **接线**:`cli.py` score-company 加载并传 `industry_overlay` → 股票 overlay 里 `inherit_from_industry` 的 L0 节点继承填好的值 → **L0 真进分**(688256 industry_contrib 2.32→3.48)。server.py 本就传了。
  - **F7 定界**:`compute_company_score` 把 `industry_total → tanh(/K)` 进 total(raw 留 components.industry_contrib)。**K=`_INDUSTRY_TOTAL_SCALE`=2.0**。
  - **F5 阈值**:`SIGNAL_BUY_THRESHOLD` 0.20→**0.30** → 全池 **31% BUY**(WATCH 23/HOLD 45/AVOID 16/BUY 37)。

### ⚠️ 当前打分模型的关键校准状态(post-compact 必读)
- **信号基准 = `base_score`**(不是 horizon-mix!我曾在 mix 上浪费时间;base_score p70≈0.30=31%BUY 临界,688256 base=0.327→BUY)。`_trading_signal_from_mix` 用 HORIZON 权重 0.3/0.45/0.25 但**trading_signal 实际比 base_score**。
- **K=2.0 是 fundamental-vs-估值 旋钮**(小 K=成长偏重,强基本面留 BUY;大 K=估值感知)。688256 在 K≤2.0 回 BUY。
- **🔴 用户要求(待设计讨论):K 应做成市场regime联动**——牛市/risk-on 小 K、熊市/risk-off 大 K,接 L7.env.market_trend / market_regime_multiplier。代码里已写 TODO(scoring.py `_INDUSTRY_TOTAL_SCALE` 注释)。**这是下一步重点之一。**
- 估值链(FU-1 已修):同一 PE/PB 百分位经 risk_discount(L8.val.overvalued,已×0.5)+ valuation_rerating(historical_percentile/pe/pb/ev_ebitda/forward_pe/peg_match)两条;market_adapters 三市场 `discounts:{}`(去双减)。
- L0 经 industry→stock `inherit_from_industry` 进分(必须传 industry_overlay)。

### 关键 gotcha(避免重踩)
- **Agent worktree 从旧基线 b5aaed4 fork**(缺全部 campaign)→ 代码 agent 用**主树**(严格分文件)或 3-way apply,别盲合并。
- **无 live collector daemon**(某 agent 误读 DB mtime;ps 干净)。
- DB:10 只 AI_COMPUTE 已 re-collect+re-derive(含新 dp_id);**106 只未做**(F2)。备份 hot.sqlite.bak.batch3pre/.scorefix。
- 2 个 untracked docs(audit + 本 status)可弃、不进 PR。

### 剩余路线(用户待定,无优先级锁定)
1. **🔴 市场regime联动 K**(用户提,待设计讨论)。
2. **F6 行业级 margin 中位**(用户并行批次选了但只做了 F7,**F6 未做**)——替 aggregator `_GROSS_MARGIN_MEDIAN=0.29`。
3. **F2 全池回填 106 只 A 股**(旗舰 revenue_growth/估值/L0/倍数 目前只覆盖 10/116;DB-串行、重)。
4. **11 个 CLS-blocked L0**——akshare CLS upstream 恢复后重采。
5. 低优先:C2 空源核查、C3 接 3 个无产出 dp_id(L7.reflex.tag/L8.val.slope_risk_off/L6.priced.realization_risk)、C4 M-3 guidance、company_score 仍未在 final 之外裁剪的边角、dcf。
- 完整审计/路线产物:`/tmp/a_share_progress_gap_roadmap_2026-06-04.md`、`/tmp/calibration_proposal_FU1_FU2.md`。

## ════ SPEC 体检 + 3-agent 整体 Review(2026-06-04,post-63d25cb)════

### SPEC 字段体检
- `validate-manifest` ✅(13 行业/328 成分;仅 SPACE_ECONOMY 无成分=占位)· `verify-lock` ✅(14 模块 0 错)。
- 250 dp_id 结构完整(field_role/score_target/participates_in_score/source_status)。
- `check_spec_drift.py` 报 56 项,**全是标签滞后不破坏打分**;**真实 legacy=45 非 30**(脚本 `check_spec_drift.py:189` `legacy[:30]` 截断,已核实,隐 15 个)。

### 3-agent Review 发现(均经我亲自 trust-but-verify)
- **🔴 R1(P0,真破坏分数)**:`market_adapter` 的 `local_scores` 把 core base 已含的 `funding_score`(在 capital_sentiment 桶)+ `expectation_gap` **二次加到 base_score**(`base_score∈HORIZON_KEYS`,market_adapter.py:21),signal(scoring.py:1747-1748 读 `market_final["base_score"]`)被抬 → **全池实测翻 17 只**(6 BUY→HOLD 如 002460/600030、4 HOLD→BUY、7 其它;整体分布 BUY 14%→13% 稳)。FU-1 删了对称的 `discounts:{}` 却漏了 `local_scores`。分解证明 `event_impulse_score` 恒 0(无 producer)、清空安全。**修法=三市场 `local_scores: {}`(已落地+test_market_adapter 改 2 断言为回归守卫,8 测试绿)**。
- **🟠 R2(P1,真信号丢失,agent 实施中)**:F1 没收口的 realtime 桥死沉:① `percentile` **裸键**(aggregator.py:955 `endswith("_percentile")`=False)→ `L6.priced.crowdedness` 0.969 在 116 只零进分;② L8 风险簇(`cash_ar`/`cost_overrun` 发 `alert_severity`+方向值)无规则→risk_discount 少计;③ `ps`/`mcap_fcf` 发 scalar 无 percentile 兜底→valuation_rerating 丢证据。
- **🟠 R3(P1 诚实度,未做/Batch C)**:25 条 `source_status` 陈旧(forward_pe/inst_buy_sell/institutional/social 等已接 producer 仍标 `$`/`missing`)→ 污染覆盖率读数,不进分。① 给了 S1–S25 精确目标。
- **🟠 R4(P1-conditional,未做)**:龙虎榜 `inst_buy_sell` net_amount **fallback** 单位(top_list.net_amount ×1e4 vs 同库 moneyflow 不乘)内部不一致;只影响 top_inst 权限锁时 fallback(primary 已实盘核)。需抓 1 行实盘 `pro.top_list` 定论。
- **🟡 X1(P1.5 数据卫生,已裁决)**:2544 行 `mock:*` 误标 `data_status=Known`。**不进分**(aggregator.py:1013/1088 source-gate 按 `startswith("mock:")` 拦,且 `realtime_current` 主键 (ts_code,dp_id) 单行,mock/真源跨股分区交集=0)。仅污染按 Known 计的覆盖率。修=重采覆盖(=F2)或 coverage 侧过滤。
- **⚪ P2(未做/Batch D)**:6 真死参与者(gamma/reflex.tag/realization_risk/slope_risk_off/L10×2,标 ○/$ 假装有 proxy)给 missing/pending;`L6.priced.iv`vs`L7.trade.iv` 同源同桶显式去重;`_trading_signal_from_mix` 名不副实(传 base,base,base)改名/加 assert;`_l6_sens_factor` 死代码;多处 `or` falsy-zero;count_drift 文档同步。

### 本轮执行(用户批 A+B)
- **R1 ✅ 已落地**(config/market_adapters.yaml 三市场 local_scores:{} + test_market_adapter.py 2 断言改回归守卫,8 测试绿)。DB 备份 `runtime/hot.sqlite.bak.reviewfix`。
- **R2 🔄 opus agent 实施中**(只碰 aggregator.py + test_realtime_bridge.py)。
- **待 R2 落地后**:重打分全池核 R1+R2 合并效果 + 核 0.30 阈值(分布稳,大概率不动)→ 跑全套 → 提交。
- **本轮未做(用户暂缓)**:Batch C(R3 标签+6 死参与者+count_drift+脚本截断)、R4、Batch D(P2)。
- 3-agent Review 原始产物:task 输出 a0a93193(SPEC)、ae98fec7(scoring)、af2484fc(derive)。

### Phase-2 执行进展(2026-06-04 续,用户批 A+B+推荐序)
- **R1 ✅ 验证**:三市场 `local_scores:{}`;test_market_adapter 8 绿;diff 审过。
- **R2 ✅ 验证**:aggregator percentile 裸键(1045)+ L8 风险簇 9 个(489-528/954+)+ ps log-ratio(833+,mcap_fcf 判 data-only);test_realtime_bridge 75 绿;diff 审过。**真实路径重打分:全池 BUY 13%→5%**(R2 把死沉的拥挤+L8 风险接回),688256(锚点)/300750 BUY→HOLD。诊断:crowdedness 百分位中位 0.81(热市快照)、L8 告警 57% 股。**用户裁定:R2 正确,Phase-2 只重定阈值;拥挤相对化留 Phase-4 regime-K**。
- **诚实度批 ✅ 验证**:25 stale source_status(8 $→✓/9 $→○/8 missing→○)+ 5 死参与者 ○→missing(gamma 留 $)+ count_drift→0 + 脚本去 `[:30]`(legacy 报全 45);data_point_roles diff **100% source_status 行**=零分数变化;97 spec 测试绿。
- **F6 改道 = business-model archetype tag**(用户选):per-theme 中位实测 backfire(11/12 行业 margin 宽,主题捆薄利+高毛利;代码注释早预言)。POC 验证:AI_COMPUTE 内按业务模型拆 EMS~7%/PCB~32%/光模块~53%/IC~55% **收紧**,浪潮/工业富联不再 floor。分类 agent(a3e1d74c)跑中 → 产 `config/business_model_archetypes.yaml`(222 只 gm 股 → archetype)→ 我 fit 各 archetype 中位/scale + QC 收紧 → 接 aggregator(threading:synthesize_realtime_nodes 有 ts_code → 穿 gm_median 到 _realtime_field_signal,回退 universe)→ 测试。
- **待**:F6-tag 接线 → 重打分全池 → **重校 0.30 阈值**(R1+R2+F6 合并分布,目标恢复合理 BUY%)→ 全套 → 提交(**用户未批 commit,先报**)。
- DB 备份 `runtime/hot.sqlite.bak.reviewfix`。未提交工作树:market_adapters.yaml(R1)、aggregator.py(R2)、test_market_adapter/test_realtime_bridge、data_point_roles.yaml(honesty)+ check_spec_drift.py + coverage_audit.md + spec_drift_report 产物。
