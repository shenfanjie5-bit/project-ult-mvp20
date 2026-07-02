# 框架达标审计(增量)+ 四增强轴研究 —— 最终报告

> 2026-06-10,11 agents(2 审计 + 3 增强族 + 4 对抗,1 个断连补跑)。续 [REPORT.md](REPORT.md)(排序分)与 [REPORT_PROB.md](REPORT_PROB.md)(概率+幅度两层)。
> 范围纪律:已有结论(公开资金流死亡 / 4 类事件仅业绩预告有 alpha / 评分引擎字段级修复 Batch1-3 / 因子面板全部结论)**直接复用不重测**;本轮只做增量。
> 证据文件:`reports/audit_residual.json`、`reports/audit_capability.json`、`reports/enh_*.json`、`factor_research/enhancers/`。

## 0. TL;DR

1. **框架修复现状(代码为准)**:19 项历史问题里大部分已修好且核实(C-1..C-3/H-1..H-3/M-1/M-2/FU-1/重设计 B/C/D/F/G 全 fixed_verified)。**最大残余 = RD-A:merit/timing 双轴始终没实施**——base 仍是单轴混合分,"好公司但贵→AVOID"失效模式实测仍在。其次:R-7 动态 regime 未实施、M-3 guidance 陈旧无年龄门(修起来最小)。
2. **能力缺口(框架 vs"上涨概率+幅度"目标)**:系统的数值主干与目标之间**没有任何连接**——G1 无生产 P&L 反馈闭环(/api/backtest 是空 fixture,分数从不对照真实前向收益);G2 无概率语义载体;G3 spec 自己写的预测目标(剥离 beta 的 alpha)从未被计算;G5 **唯一验证过的增强器(业绩预告系数)只进展示层,而同一数据的未验证编码却在喂分数**;G6 无流动性门控(全部已验证 alpha 都是 liquid-70-only 的)。
3. **题材炒作轴:✅ 第二个双 lens 存活的信号(反向)**。`t5a 概念涨停热度`(THS 概念 5 日涨停密度):热门题材股未来 10-20d **上涨概率低 ~2.5pp、ic20 ≈ −0.026**,对现有概率层完全正交(ρ −0.017)且增量;朴素涨停/连板因子负 IC 真实但 100% 被 max5/turnover 包含。**用途 = 概率层第 5 因子(反号)/ 风险门控,不是幅度层**。
4. **产业链传导轴:❌ 击杀(但留线索)**。客户行业动量→供应商(c2cu,Cohen-Frazzini 方向)点估计 +1.2pp/20d t2.0,但**行业标签重排零假设就能达到同等效应**——有效样本只有 5 个供应商行业,无法与运气区分。本轮顺带把目录 T3-3(行业动量)正式判死。
5. **催化时点轴:❌ 干净阴性(诚实关闭此前的"最高 ROI 升级"假设)**。预告/快报更早时点惊喜**不能**增强 PEAD 幅度层(预注册增量测试 −10bp/20d):Track A 的预告 alpha 是**事件窗现象**,不能翻译成双周横截面排序。大资金残余:龙虎榜/金股数据在盘上**物理为空**,筹码集中度被 turnover_20 包含。
6. **接入蓝图共识(两个审计独立收敛)**:以 `event_coefficient.py` 的诚实契约为模板,把已验证两层模型作为**并行影子输出**(`L11.quant.*`,participates_in_score=false)接入,先立 P&L 反馈闭环,**不要**把任何东西融进 base_score(融合已被实证证伪)。

## 1. 修复现状核查(fix_residual 审计,HEAD 80a5346)

**已修并核实(摘要)**:C-1 情绪双计 / C-2 trend:up 饱和 / C-3 run_up 陈旧(freshness gate)/ H-1+H-1b+H-2 revenue_growth / H-3 估值窗口 / M-1 top_path / M-2 毛利非对称+原型中位 / FU-1 估值双渠道(×0.5)/ D-low mock 门 / RD-B 覆盖率代理(corr 0.952→0.028)/ RD-C confidence 死常数(改 conviction band)/ RD-D multiplier 位置 / RD-F 估值多桶(pooled 压制)/ RD-G 共模时序百分位(横截面 bad-tail)/ LA-L1 前视(f_ann_date 过滤)。RD-E 经对抗裁定为假阳(abs 对 discount 桶语义正确)。

**残余(按优先级)**:

| # | 项 | 状态 | 要点 |
|---|---|---|---|
| 1 | **RD-A merit/timing 双轴** | not_implemented(HIGH) | base 仍单轴 = fund+eg+valr+cs−risk−priced;timing 方差垄断;M>0,T<0 应 HOLD/WATCH 而非 AVOID。merit 量级已被 R-2b 修好,双轴是临门一脚 |
| 2 | **R-7 动态 regime** | not_implemented(MED) | scoring.py:190-193 自带"须 PIT 回测验证后接"的 mandate;回测框架已在 |
| 3 | **M-3 guidance 陈旧** | unfixed(MED) | 20 个月前的预告对仍全额喂 expectation_gap(floor 0.1 永不归零);server 事件流已有 90d age gate,打分层没有——镜像 C-3 freshness 模式即可,**改动最小收益直接** |
| 4 | damp 分母稀释 | partial | Inactive/真零进分母,base 中位 ±0.2 建模分岔,与 R-7 同批回测裁决 |
| 5 | RD-F/G 的 HK/US 回退面 | by-design 缺口 | 无 peer_context 时回退旧多桶/时序行为 |
| 6 | H-4 双引擎 | partial(已降级 audit_only) | L11.trade.signal 不进分不上 server;残余可合法分歧 |
| 7 | 卫生项 | — | D-nit inert-overlay 未单列 / NEW-1 dividend 节点方向与事件研究张力 / NEW-3 iv 同源同桶 / LA-L4 now 锚定 |

## 2. 能力缺口(capability_gap 审计)——框架 vs 目标"没达标"清单

| ID | 缺口 | 证据 | 严重度 |
|---|---|---|---|
| **G1** | **无生产 P&L 反馈闭环**:分数从不对照真实前向收益;/api/backtest 返回空 fixture;唯一监督是隔离的手动 pit_backtest | audit_eval.py:44-48;mvp20 全文无 realized-return 引用 | CRITICAL |
| **G2** | **无概率语义载体**:产出只有 base_score/三 horizon 重权/绝对阈值 signal(0.20/−0.15/−0.50);无 P(up)、无 E[ret]、无区间 | scoring.py:194-196,1793-1797 | CRITICAL |
| **G3** | **预测目标失配**:industry_graphs yaml 自己写明目标=剥离市场+行业 beta 的 alpha,但管线从不算 beta、从不减基准;graph 的 priors/shock_model 只服务 LLM overlay 规划与展示 | AI_COMPUTE.yaml:25-27;graph.py 仅做结构校验 | CRITICAL |
| **G5** | **验证与入分倒挂**:`forecast_coefficient`(唯一验证过的事件信号,带 validated/90d 门)只进 /market-events 展示;而同一 forecast payload 的未验证 tanh 编码在喂 expectation_gap | server.py:650,669 vs aggregator 路径 | HIGH |
| **G4** | horizon 无监督:关键词分类的 short/medium/long 从未对照对应前向窗验证;signal 对 horizon 视而不见 | aggregator.py:297-315 | HIGH |
| **G6** | **无流动性门控**:全部已验证 alpha 都是 liquid-70-only,生产对全部股票等置信发信号(微盘是已实证的默认失败模式) | score_company/handle_score 无任何流动性过滤 | HIGH |
| **G7** | regime 层接线但休眠:market_regime multiplier ≈ identity,K 固定带 TODO | scoring.py:1337 | MED |
| **G8** | 死通道:company_event_score 结构性为 0(§27.3 事件项无人发);confidence 记录但不门控任何决策(无 abstain 态) | scoring.py:1627-1629,1739-1749 | MED |
| **G9** | 无横截面输出语义:/score 单股;绝对阈值随覆盖率治理漂移(历史上一次治理修复使 base 平移 0.16);信息在横截面而产品不提供排名面 | server.py:1332-1386 路由表 | MED |

**架构裁决(审计原话)**:数值主干(overlay 树→damped means→六分量和→绝对阈值)与目标(校准的每股上涨概率+幅度,spec 自定义为剥 beta 的 alpha)之间**当前由"无"连接**——无监督、无概率载体、无基准剥离、无流动性作用域。修复的全部原料已在仓库:event_coefficient.py 的验证先例 + factor_research/model 的两层模型 + pit_backtest 的指标机器。

## 3. 增强轴实证

### 3.1 题材炒作:✅ t5a 概念涨停热度(反向,双 lens 存活)

数据:`涨跌停和炸板数据/all.csv`(145,735 行,2020-02→2026-03,覆盖 64/67 面板日,行业字段 PIT)+ THS 概念成分(快照,已做 pre-2023 概念重建缓解)。

| 因子 | 结论 |
|---|---|
| t1 个股涨停动量 / t2 连板高度 | 原始负 IC 真实(t −2.5~−3.3,追高被实证)但 **100% 被 max5/turnover_20/strev 包含** —— 模型已拥有朴素打板信号 |
| t3 炸板率 / t4 行业热度/轮动 | 无边际 |
| **t5a 概念热度(5d 概念涨停密度,概念规模归一)** | **唯一正交存活**:残差化(max5/turnover/ivol/strev/mom 控制后)ic20 −0.032 t−3.75;跑赢率 disc h20 −3.7pp t−3.4 |

**双 lens 对抗结果**(均存活,带强制折减):
- PIT/可交易性:NW 重叠校正 t 仍 2.6-3.3;快照缓解(仅用 2022 前已存在的概念)信号不变 ic20 t−3.3;效应缩 ~25% 后仍立。
- statistics(补跑):精确复现至 4 位小数;200 次日内 shuffle 全清(9.7 个零分布 σ);过 30 配置 max-of-null 95 分位;奇偶半样本同号(−0.023/−0.042);**加 ep_ttm+rvol 控制后仍存活(ic20 −0.026 t−3.06)**;对生产概率层组合正交(ρ −0.017)且残差化后仍判别(disc20 −2.95pp t−2.59);旋转零假设揭示 ~25-30% 是静态"投机股特质",纯时变成分自身存活(ic20 −0.027 t−3.2)。
- **诚实参数**:消费此信号请按 ic20 ≈ −0.026 / disc ≈ −2.5pp 计,非头条 −0.032/−3.7;ex-2025 ic20 NW t −1.95 边际(disc 仍持有);2026 仅 4 日翻号(小样本)。
- **用途边界**:幅度尾 t−1.78 不显著 → **只进概率层(反号第 5 因子)或风险/避开门控,不进幅度层**。

### 3.2 产业链传导:❌ 击杀(留 1 线索 + 1 干净阴性)

- THS 概念指数行情文件实为年末快照(中位每码 13 行)不可用 → 行业价格序列改由成员股日收益自建(与面板逐字节对齐)。
- **c1 自行业动量:干净阴性,正式判死目录 T3-3**(2-4 周行业动量在 2023-26 A 股不存在,行业级 IC 反而轻度反转号)。
- **c2cu 客户行业动量→供应商股**(下游需求信号向上游传导):点估计 h20 +1.24pp t2.0、过日内 shuffle 和 liquid-50——**但被 statistics skeptic 击杀**:结构上正确的零假设是**行业标签重排**(因子是行业级广播,有效样本=5 个供应商行业),5 个新 seed 里 1 个就达到真实效应规模 → 与运气不可分。**地位:未验证线索**,需更细行业图(12 组太粗)+更长样本才能复检。
- c4 行业内龙头→跟随:平,若有方向是跟随者反而领先(反 lead-lag)。

### 3.3 催化时点 + 大资金残余:❌ 全部干净阴性(关闭两条假设线)

- **预告/快报时点惊喜不增强 PEAD**(此前被标为"最高 ROI 升级",现诚实关闭):f1 预告新鲜惊喜(30/60d 窗)、f2 快报、f3 速度加权合成——全部平到负 IC;**预注册增量测试 blend(sue,f1) − sue alone = −4bp/10d、−10bp/20d(t−1.24)**。机理:Track A 的预告 alpha 是 t+1 事件窗现象(~+30bp hedged),在双周采样的横截面排序里早已耗散;且 fresh 覆盖率均值仅 14.8%/日(季节性 0.6-46%)。PEAD 基线本身复现无误(+0.82%/20d t2.87 ✓)。
- **大资金残余物理关闭**:龙虎榜每日统计单/机构交易单/券商月度金股 目录**为空**(0 文件,比此前"覆盖率 5-20% 低优先"的判断更强:根本无法测);机构调研数据格式不可对齐;大宗交易 by_symbol 覆盖率过低未过门;**筹码集中度(chip_conc)负尾 −0.72%/20d t−4 看似可用,但 turnover 残差化后死亡(−0.34% t−1.38)= turnover_20 已交付该信息**,加入会双计。
- PIT 注:预告复核用 min(first_ann_date, ann_date),4.3% 修订行回溯到首告日——偏向**有利于**发现 alpha,故阴性结论保守可信。

## 4. 接入蓝图(综合两审计 + 三轮实证)

**总原则(实证强加)**:base_score 是手调合成分,融合已被证伪 → 一切增强以**并行通道**进入,绝不混入单一分。模板 = `event_coefficient.py` 诚实契约(bounded 系数 + validated 标志 + caveats 随行 + 年龄衰减)。

```
优先级 1  G1 P&L 反馈闭环:T+5/10/20 定时任务,存储分数 join 真实 hfq 收益
          (复用 pit_backtest/metrics.py),填充空的 /api/backtests
          —— 让每个校准常数第一次有真值可对
优先级 2  G2/G3/G6 两层模型作为影子输出:mvp20/quant_score.py 纯模块
          (拷贝 emit_score.py 逻辑),L11.quant.mag / L11.quant.prob
          (participates_in_score=false),liquid-70 门控,门外 validated:false
优先级 3  G5 事件编码统一:forecast_coefficient 成为唯一真源,短窗通道
          + ann_date 衰减(~5 交易日归零),替换未验证 tanh 分支;
          顺手修 M-3(同一 freshness 模式)
优先级 4  概率层 v3:t5a 概念热度反号加入 ic_weighted(ivol,max5,turnover,ep)
          → 5 因子;同时作为"题材过热"避开门控(展示层)
优先级 5  RD-A merit/timing 双轴 + G8 confidence abstain 态 + G9 排名面
优先级 6  R-7 regime(只降权;经 G1 闭环回测后定参)
```

**用户四增强轴的最终对账**:

| 用户假设 | 实证裁决 |
|---|---|
| 大资金入场 | **死**(公开数据无前瞻已证 + 残余源物理为空 + 筹码=turnover 重复)。唯一活口:若未来接入 L2/真龙虎榜数据源可复检 |
| 题材炒作 | **活但反向**:题材热度是**风险/概率负信号**(追高者亏),不是增强;价值在"避开门控"+概率层第 5 因子 |
| 重大相关利好 | **窄而真**:仅业绩预告事件窗(t+1,~+30bp hedged)有效,已编码为 event_coefficient;**不能**泛化为横截面排序因子;新闻类待 Track B 前向数据成熟 |
| 产业链传导 | **方向有线索证据不足**(c2cu 被零假设达到);需更细行业图+长样本;商品传导腿因无商品日频数据未测 |

## 5. 复现

```bash
PY=factor_research/.venv_research/bin/python
# 题材热度(存活信号)
ls factor_research/enhancers/theme_speculation/   # builder 脚本
cat factor_research/model/reports/enh_theme_speculation.json
cat factor_research/model/reports/enh_theme_speculation_stats_skeptic2.json  # 补跑对抗
# 审计
cat factor_research/model/reports/audit_residual.json
cat factor_research/model/reports/audit_capability.json
```

---

## 附录 2026-06-10 晚:高波×高惊喜交互线索——已击杀(双 lens)

融合研究标记的线索(mag 顶档漂移集中高波半区 +1.63%/20d t2.88,事后单切分)经专项验证(3 agents,22 配置):

- **builder**(weak_positive):线索精确复现;可实施的 walk-forward 倾斜增益 +0.72%/20d t2.22、18/18 变体格同号、liquid-50/逐年存活;但 h10 不过自己的零分布、重叠校正后 NW t1.81/非重叠 t1.13。
- **statistics skeptic(击杀)**:倾斜序列 acf1=0.554(持仓持续+窗口重叠)而置换零分布是 iid——同口径 MA(1) t1.56 < 零分布 q95 1.72;maxT 多重检验 p≈0.14;剔 2026+up_calm → +0.20% t0.48 消失;**"walk-forward"跑在发现线索的同一面板上,零独立数据**。
- **economics skeptic(击杀)**:**不是交互,是彩票/ivol 因子再加载**——rvol⊥(ivol,max5) 后倾斜 t0.33,lottery⊥rvol 保留 t2.34;对全宇宙 vol 因子收益 beta 1.28,残差交互 alpha 仅 t1.56;换手 2.25×(~10-15bp/20d 成本);倾斜桶恰落概率层底部五分位。
- **裁决**:不动生产;唯一可辩护残留 = c_cf 区间已按 vol 分桶(继续)。复活条件:~6 个月新面板日期 + 预注册非重叠重测。

证据:`factor_research/enhancers/vol_surprise/` + `reports/enh_vol_surprise*.json`。
