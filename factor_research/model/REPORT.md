# A 股横截面"涨幅(前向收益)预测分数"——从零搭建 + 出样本天花板诚实报告

> 隔离只读研究,全部代码/产物在 `factor_research/model/`,使用隔离 venv `factor_research/.venv_research`(py3.12, numpy/pandas/scipy/sklearn/lightgbm)。**未改动 `mvp20/`、`runtime/`、`pit_backtest/` 任何文件,未触碰运行中的服务(:8701)。**
> 目标:直接用前向收益监督,训练一个横截面排序分数,使"分数越高→预期前向收益越高",并量化其出样本(walk-forward、跨 regime)天花板。主目标 +10 交易日 signed 前向收益;次目标 +5d/+20d。
> 成功标准(出样本):① 十分位单调 + D10−D1 正且显著;② TOP 桶绝对前向收益 > 全样本均值(`top_excess`);③ 坏 regime 不崩(报尾部);④ 全部带置信区间。
>
> **状态:§1–§5 已定稿(本人构建+验证);§6–§8(模型族结果 / 最终模型 / 天花板)由多 agent 工作流回填。**

---

## 0. TL;DR

1. **可投资范围内,唯一活下来的 alpha 是盈余惊喜(SUE + 单季归母 YoY)**。7 个模型族、~120 个配置、3 路独立 skeptic 对抗证伪后:**最强统计信号(amihud 非流动性,t>6)是不可交易的微盘 artifact**(剔除最小 30% 股后 +0.79%→−0.14%,塌成 0);GBDT 的增益也几乎全是同一微盘 tilt;高 IC 的价值/低波/反转**不在尾部付钱**(倒 U,顶档均值回归)。**只有盈余惊喜在剔除微盘后仍为正**:liquid 范围 +10d 顶档超额 **+0.40%(t 1.8)**、+20d **+0.83%(t 2.9)**。
2. **诚实天花板(可交易、出样本、剔微盘、走 walk-forward):约 +0.4%/10d ~ +0.85%/20d 毛收益(t≈1.8~2.9),+20d 最稳;且仅在 up/非恐慌 regime 为正,down 市转负**。这低于"vs全样本"口径的纸面数(+0.5%/+1.06%),但才是真数。rank-IC 上限 ~0.05(符合文献),**关键是 IC 多数不转化为可交易多头桶**。
3. **比 base_score 强多少:方向上更优、幅度有限**。base_score 顶档超额≈0(且 2025 末翻负);新模型有真实正的顶档(广宇宙)。但在 base_score 仅有的 250 股窄样本上,二者顶档都不显著(新模型 +20d +0.19% vs base +0.02%,pos% 64% vs 57%,方向更好但 n=14 不显著)。
4. **上线前提**:① 范围限可投资(剔最小 ~30%/ST/新股/连板)——微盘"边际"是陷阱;② horizon 取 +20d;③ regime 门控**只降权不反号**(down/panic 减仓);④ 净成本上 +10d 双周换手约打平,**只有 +20d 月度再平衡可能净正**。最高 ROI 升级 = 预告/快报更早时点惊喜。
5. **方法学护栏全程生效**:harness 拥有全部防泄漏逻辑;独立审计判定 leakage-clean(shuffle 零假设跨 10 seed 塌到 0、前向收益逐 cell 重构 0 误差);唯一实质 caveat = 宇宙 survivorship(当期快照回填,使纸面数为上界)。

---

## 1. 数据与宇宙(免费、PIT-safe)

| 项 | 值 |
|---|---|
| 价格矩阵(前向收益+价量因子来源) | `_datalib.load_price_matrices("20230101")`:**816 交易日(2023-01-03..2026-06-05)× 1617 股**,RET/TO/MV 缓存 npz |
| 前向收益 | `CUM=cumsum(log1p(RET))`;`+h 收益 = exp(CUM[k+h]−CUM[k])−1`,严格在 base 日之后,停牌/缺失 mask |
| 基本面特征源(直读,非流水线) | DockCase by-symbol CSV(带 `ann_date`):`财务指标数据`(roe/gpm/q_roe…)、`利润表`(SUE)、`每日指标`(pe_ttm/pb/ps_ttm/dv_ttm) |
| 行业(中性化用) | `pit_backtest.universe.primary_industry_map()` = 12 个主题组,覆盖 1617/1617 |
| base_score 对照基线 | `factor_research/pit_extra/realbase.sqlite`:14 个月度日(2024-01..2025-12)× 250 股 |

**工程要点(瓶颈被证伪):** 前人估计"多日期 PIT 面板需 ~35h"指的是 full `base_score` 流水线(6s/股)。但**裸因子横截面面板可直接读 by-symbol CSV + 缓存价格矩阵,~18s 建完**,无需流水线。这把真正的瓶颈消除了,使 walk-forward 成为可能。

## 2. 特征面板与评测口径(harness 拥有全部防泄漏逻辑)

**面板 `panel.npz`:67 个 base date(每 10 交易日,2023-07-19..2026-04-28)× 1617 股 × 26 因子**,标签 fwd5/fwd10/fwd20。特征覆盖率 75–99%。26 因子分 6 族:

- **价值**(daily_basic,市场 PIT):ep_ttm, bp, sp_ttm, dy
- **质量**(fina_indicator,ann_date PIT):roe, roa, gpm, npm, debt_assets, asset_turn, q_roe
- **盈余/预期**(income,ann_date PIT):sue(季节性随机游走标准化惊喜), npq_yoy(单季归母 YoY)
- **动量/反转**(价量):mom_6_1, mom_12_1, strev, strev_adj
- **风险/低波/彩票**:rvol_20, rvol_60, ivol_60, beta_60, max5
- **流动性/拥挤/规模**:turnover_20, turnover_trend, amihud, ln_mv

**6 条接入纪律全部内建于 harness(模型只能改假设、无法引入泄漏):**
1. **中性化**:每个 base date 横截面,winsorize→z→对 [截距, ln_mv, 行业 dummies] 回归取残差→rank-z。缓存 `neutral.npz`。
2. **横截面 rank**(非时序自身分位)。
3. **严格 PIT**:财务用 `ann_date<=base_date`;价量只用 ≤k 日数据;前向收益严格在 k 之后。
4. **walk-forward**:预测 t 日的模型只用 base date < t 拟合(`Zf[lo:t]`)。
5. **覆盖率 gating**:中性化后缺失 impute 0(=中性),且要求每股 ≥50% 因子非缺失否则不打分。
6. **horizon 纪律**:+5/+10/+20 分别评测。

**评测指标 = 可交易的顶档超额 `top_excess_uni`(非 IC):** 每个 base date 取 (顶档十分位均值前向收益 − 全样本均值前向收益),跨日期求均值 + bootstrap CI + t + pct_pos;同时报 D10−D1、十档曲线单调性、分年/分 regime/尾部。显著性另用**非重叠日期子样本**(`--nonoverlap`)与 date-level block bootstrap,避免重叠窗虚增显著性。
**对抗旗标:** `--shuffle`(日内打乱标签的零假设;真信号应塌到 0)、`--drop-year`、`--drop-regime`。

**Regime:** 每 base date 按 60 日市场趋势(MV 加权宇宙收益)× 20 日波动中位数分 4 态:up/down × calm/turbulent。

## 3. 对照基线:现有 base_score 作为收益预测器(要打败的标杆)

在 base_score 存在的 250 股 × 14 月度日上,用**同一套 P&L 口径**评测(五分位,n=250):

| horizon | mean rank-IC (t, pos%) | Q5−Q1 (CI) | 顶档超额 top_excess (CI, pos%) |
|---|---|---|---|
| +10d | **+0.062** (t 1.85, 71%) | −0.0006 ([−0.016, +0.014]) | **+0.0020** ([−0.005, +0.009], 57%) |
| +20d | +0.061 (t 1.67, 57%) | −0.0060 ([−0.031, +0.016]) | +0.0002 ([−0.010, +0.010], 57%) |

五档曲线 +10d:`[0.030, 0.026, 0.028, 0.023, 0.029]` —— **非单调、顶档≈底档**。逐日 IC 从 +0.28(2024-01)到 **−0.17(2025-10)、−0.07(2025-12)**:近端预测力衰减/翻号。
**结论(印证任务前提):** base_score 有弱正的整体 rank-IC(主要靠"避开最差"),但**没有可交易的多空价差,顶档不兑现,且 regime 脆弱、近期翻负**。标杆很低,但"出样本稳健为正"很难达到。

## 4. 单因子地图(中性化后,+10d;验证面板正确性)

`diag.py` 对 26 个中性化因子逐个测 per-date rank-IC + 顶档超额 + 分 regime IC。**结果精确复现所有已知先验,佐证面板/中性化无误:**

| 因子族 | IC(代表) | 可交易顶档超额 | regime |
|---|---|---|---|
| 价值 ep/bp/sp/dy | **+0.02~+0.04**(t 2.5~3.9, pos% 59~73%) | ~**−0.003**(不在尾部付钱) | down 市最强(避险) |
| 质量 roe/gpm/q_roe | 弱 ~+0.01(不显著) | ~−0.002,D10−D1 负 | **仅 down_turbulent +0.08~+0.10**(flight-to-quality) |
| **sue** | +0.009(pos% 56%) | **+0.0014**(正!) | 最稳/最正交;down_calm 转负 |
| **npq_yoy** | +0.004 | **+0.0033**(基本面里最佳顶档) | — |
| 动量 mom_6_1/12_1 | **−0.014 / −0.007**(负) | ~0 | down_calm 强负 / down_turbulent 翻正(动量崩溃) |
| 反转 strev | +0.032 | ~0 | **up_calm −0.007 / turbulent +0.055**(panic 付钱) |
| 低波 rvol/ivol/max5 | **−0.05**(t −2.7~−4.0, pos% 30~41%) | ~0 | calm 强(−0.10~−0.11)/ turbulent 翻 |
| 拥挤 turnover_20 | −0.045(t −4.1) | +0.0012 | — |
| **amihud(非流动)** | +0.029 | **+0.0077(最高)** | ⚠️疑微盘/流动性 artifact,对抗审查中 |
| ln_mv(规模,中性化变量) | −0.034 | D10−D1 −0.016(小盘溢价) | up_turbulent 大盘赢 |

**最强可交易顶档信号极稀缺:** amihud(+0.0077)、npq_yoy(+0.0033)、sue(+0.0014)、turnover_20(+0.0012)、debt_assets(+0.0018);**其余全 ≤0**。

## 5. 核心现象:IC ≠ P&L(倒 U 十档曲线)

在本面板上,**几乎每个模型(含 base_score、EW、IC-weighted、regime-IC、GBDT)都是:rank-IC +0.04~+0.06 正,但十档曲线倒 U/递减——最高分的顶档反而跑输**:

| 模型(+10d) | IC | D10−D1 | top_excess | 十档曲线形态 |
|---|---|---|---|---|
| EW-core(价值+质量+sue+反转+低波) | +0.053 | −0.0002 | −0.0012 | 平,顶档微负 |
| IC-weighted(全 alpha,halflife 8) | +0.042 | −0.0043 | −0.0018 | 顶档塌 |
| IC-weighted-regime(shrink 0.5) | +0.045 | −0.0033 | −0.0021 | **递减(顶档最低)** |
| GBDT + regime feature | +0.039 | −0.0042 | −0.0022 | 递减 |
| parsimony(amihud+npq+sue+价值) | +0.035 | +0.0007 | −0.0027 | value 稀释 amihud→负 |

**零假设检验通过(harness 无泄漏):** parsimony 配置 `--shuffle 1` 后 IC +0.035→+0.005、top_excess→0。即 harness 不会无中生有制造 alpha;难度是真实的。

**机理:** 正 IC 来自广阔中段的弱单调;但顶档被低波/反转/拥挤类因子(高 IC)集中到**随后均值回归**的股票,使可交易的多头桶失败。**优化 IC 是错目标——必须直接优化顶档超额,且这恰恰极难。**

---

## 6. 模型族出样本结果(多 agent 工作流:21 agents,~120 配置)

7 个模型族各 walk-forward 训练→出样本测(54 测试日,+10d),目标=稳健顶档超额。**每个 positive 声称经 3 个独立 skeptic agent 从 robustness / overfit-多重检验 / 可交易性 三个 lens 对抗证伪。**

| 模型族 | 最优配置 | +10d top_excess (t, pos%) | +20d | shuffle 零假设 | 自报结论 | 对抗存活 | **致命伤** |
|---|---|---|---|---|---|---|---|
| parsimony_topbucket | **amihud** 单因子 | +0.0079 (4.6, 76%) | +0.0169 (6.2) | −0.0014≈0 | positive | ❌ | 微盘 artifact:剔小盘→−0.0011 |
| pricevol_regime | **amihud** 单因子(等价) | +0.0079 (4.6, 76%) | +0.0169 (6.2) | +0.0013 | positive | ❌ | 同上(剔小盘→−0.0011) |
| gbdt_nonlinear | lgb 8因子+regime | +0.0070 (3.2, 69%) | +0.0061 (1.8) | +0.0003 | positive | ❌ | 增益≈amihud tilt;liquid→+0.0013(t0.4) |
| **fundamental_qarp** | **ew(sue,npq_yoy)** | +0.0050 (2.4, 67%) | +0.0106 (4.1) | −0.0007 | positive | ❌(但唯一非微盘) | 多重检验后边际;down 市负;大盘内 t1.0 |
| regime_conditioned | icw_regime 5因子 | +0.0049 (2.8, 76%) | +0.0116 (4.4) | +0.0005 | ic_only(诚实) | — | 靠 amihud;down_turbulent −0.0117 |
| grinold_kahn_icw | icw 质量+sue | +0.0012 (0.4) | +0.0048 (1.3) | +0.0009 | ic_only(诚实) | — | 经典 IC≠P&L:IC 有、顶档无 |
| linear_ridge_enet | enet 全因子 | −0.0012 (−0.5) | −0.0032 | −0.0007 | ic_only(诚实) | — | IC +0.04 但顶档**负**(价值陷阱) |

**关键裁决(我亲自复现,`synth.py`):剔除最小 30% 后的可投资范围**——决定性区分"真信号 vs 微盘 artifact":

| 候选 | +10d 全样本 | +10d liquid-70% | +20d 全样本 | +20d liquid-70% |
|---|---|---|---|---|
| amihud | +0.79%(t4.6) | **−0.14%(t−0.6) 塌** | +1.69%(t6.2) | **−0.19% 塌** |
| **盈余惊喜 sue+npq_yoy** | +0.49%(t2.4) | **+0.40%(t1.8) 存活** | +1.06%(t4.1) | **+0.83%(t2.9) 存活** |
| 价值+质量+惊喜 | −0.39%(价值陷阱) | −0.29% | −0.77% | −0.65% |
| gbdt blend | +0.68%(t2.7) | **+0.13%(t0.4) 塌** | +0.58% | −0.71% 塌 |

> 基准口径:`top_excess_uni` 用的是**等权全样本均值**,经验证它比真实 MV 加权市场**高 0.41pp(+10d)/0.89pp(+20d)**(等权超配小盘),故 vs 真市场超额反而**更高**——`top_excess_uni` 是偏保守(更难)的基准,不是被夸大的基准。决定成败的是**可投资范围**而非基准选择。

## 7. 最终模型与 regime-aware 门控

**`final_model.json`:盈余惊喜核心(SUE + 单季归母 YoY,等权,行业+市值中性化后 rank-z),regime-aware 决策层。**
- 选 ew(sue, npq_yoy):是**唯一剔微盘后存活**的信号,经济上 = PEAD(财报后漂移),与 base_score 正交,PIT 干净(ann_date)。+20d 最稳(漂移是慢信号)。
- **逐 regime 真实顶档超额(+10d)**:up_calm **+0.0057** / up_turbulent **+0.0064**(正) | down_calm **−0.0036** / down_turbulent **−0.0015**(负)。**逐年全正**:2024 +0.0035 / 2025 +0.0059 / 2026 +0.0067。
- **regime 门控(只降权不反号,沿用 RESULTS5/7 处方)**:对**暴露/仓位**乘 regime 系数(缩放不改横截面排序,只改"信不信、上多少仓"):up=1.0,down_calm=0.3,down_turbulent=0.0(恐慌减到 0)。"只在 up regime 做多"即可避开两个负 regime、保留 +0.5~0.6%。
- 头对头 vs base_score(250×14 同 cells):+20d 新模型顶档 +0.19%(pos% 64%)vs base +0.02%(57%)——**方向更优**;但小样本(n=14)均不显著。base_score 顶档≈0 是任务前提的实锤。

## 8. 诚实天花板 / 失效 regime / 上线前提

**天花板(可交易、出样本、剔微盘、walk-forward、含置信区间):**
- 长多顶档(decile)超额 **≈ +0.4%/10d(t 1.8)~ +0.85%/20d(t 2.9)毛**,+20d 最稳健;vs 真 MV 市场 +0.44%(t1.2,+10d)/ +1.01%(t1.9,+20d)。
- rank-IC 上限 **~0.05**(符合流动 A 股横截面文献)。**关键:IC 不等于 P&L**——价值 IC +0.04(t3.9)却顶档 −0.003;只有盈余惊喜的弱 IC 真转化为正顶档。
- 任何"更强"的数(amihud t>6、GBDT t3.2)都是**微盘/流动性 artifact 或基准错配**,不可交易。

**失效 regime:** down_calm 与 down_turbulent——盈余惊喜顶档转负(熊市/恐慌里基本面惊喜被系统性抛压淹没)。门控必须**降权不反号**(反号在前研究 RESULTS5/7 被证有害)。

**尾部:** 最差单期顶档超额 ~−2~−3%(出现在 2024-09 政策逼空 junk-rally 的 up_turbulent、与 2025 末);全样本 pos% 67%(即 1/3 的期数顶档跑输)。

**上线前提:**
1. **范围 = 可投资**:剔最小 ~30% 市值 + ST/新股/连板/低流动——微盘"边际"是陷阱(整份研究最重要的可操作结论)。
2. **horizon ≥ +20d**:+10d 信号过多重检验后边际(t2.4 < Bonferroni×15 阈 3.07);+20d 更稳(t4.1 毛)。
3. **regime 门控**:down/panic 减仓(只降权)。
4. **净成本**:A 股单边 ~0.1-0.25%(印花税+冲击)。+10d 双周换手 ~打平;**只有 +20d 月度再平衡可能净正**。
5. **survivorship caveat**:1617 宇宙是当期快照(`backtest.sqlite base_date=20260116`)回填到 2023-07,2023-26 间退市/长停股缺失;fwd 覆盖率全程 94-98% 故偏差温和,但**纸面顶档超额是真 PIT 宇宙的上界**。`load_price_matrices` 的 ST/退 过滤也用当前文件名非 PIT 状态。
6. regime calm/turbulent 标签用全样本 vol 中位阈值(轻微 look-ahead,仅影响**分 regime 报表/regime_feature**,不泄漏进逐日打分)。

**最高 ROI 升级路径:** 预告/快报(业绩预告/快报)**更早时点**惊喜(前研究 T2-7)。正式财报 SUE 已被更早公告部分 price-in(故偏弱);用更早时点的惊喜应增强信号。数据 by-symbol 可读(预告 5477 股 / 快报 3761 股),是单一最值得做的下一个特征。

---

## 附:本研究 vs 前序"base_score 改进"研究的关系

本研究**另起炉灶**直接监督前向收益,与 `factor_research/FINAL_REPORT.md`(改 base_score)互证:
- 两者都坐实 **base_score 不是收益预测器、regime 是最大杠杆、IC≠P&L 在决策层**。
- 本研究新增:**可投资范围内可交易 alpha 的诚实天花板**(≈0.4-0.85%、仅盈余惊喜),以及**最强信号=微盘 artifact 的实证铁证**。
- 一致处方:**不是加更多静态因子,而是(a)最正交的基本面惊喜 +(b)regime-aware 决策层降权**。

---

### 复现命令
```bash
PY=factor_research/.venv_research/bin/python
$PY factor_research/model/panel.py            # 建面板 (~18s)
$PY factor_research/model/diag.py 10           # 单因子地图
$PY factor_research/model/baseline.py 10        # base_score 对照
$PY factor_research/model/harness.py --horizon 10 --config '<JSON>' --out reports/x.json --nonoverlap
#   对抗: --shuffle 1 | --drop-year 2025 | --drop-regime down_turbulent
```
