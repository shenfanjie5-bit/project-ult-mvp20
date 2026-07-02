# 涨幅预测分数:上涨概率 P(up) + 上涨幅度 —— 两层架构与诚实校准

> 续 [REPORT.md](REPORT.md)(排序分研究)。本篇回答产品问题:**"涨幅预测分数"= 每股的上涨概率 + 上涨幅度**。隔离只读,代码在 `factor_research/model/caliblib.py` + `prob_variants/`,研究 venv `.venv_research`,未碰生产。
>
> **状态:已完结。§1–§4 本人构建+验证;§5–§6 由 4 族 agent 工作流(8 agents,statistics+economics 双 lens 对抗)回填。最终规格见 §6,产品演示 `emit_score.py`。**

## 0. TL;DR(已确立部分)

1. **P(up) 与 E[ret] 是两个目标,且在 A 股横截面上由不同因子驱动、互不区分**:
   - 盈余惊喜分(已验证的幅度层)**完全不区分上涨概率**——各分数桶 P(up) 平在 ±2pp 内,顶桶并不更常涨;它赢在**右尾**(低频大涨)。
   - **低波动(ivol_60:上涨率 Q5−Q1 = −4.6pp,t−2.9)/低换手(−3.3pp,t−2.7)/便宜(ep_ttm:+4.5pp,t+2.5)** 才横截面区分 P(up),且跨 up/down regime 稳定——而这些恰是均值层"倒U"失败的因子(频繁小涨,无大涨尾部)。
   - **这解开了 base_score 之谜**:它(质量+价值+低波合成)本质是个 **P(up) 型分数**(此前实证 P(up) rank-IC +0.05~0.11)而非收益分数——"score 越高→概率和幅度都越高"用单一信号**不可兼得**,必须两层。
2. **绝对 P(up) 的"水平"不可校准,只有"倾斜"可信**:42 个测试日的当日上涨率从 **0.12 到 0.97**(市场决定);任何每股绝对概率都被日期淹没(Brier skill ≈ 0)。**市场相对目标 P(跑赢当日中位数) 的水平可校准**(walk-forward 可靠性曲线单调:预测 0.451→实际 0.462,…,0.523→0.519)。
3. **概率层组合**(等权:−rvol_20 −ivol_60 −max5 −turnover_20 +ep_ttm,中性化后)在 liquid-70 范围、+10d 的**日内区分度:+4.9pp(绝对,t2.6)/ +4.6pp(相对,t1.7)**;shuffle 零分布 std≈1.3pp(6 seeds 两尾对称),真值 ≈3.5σ 超出——**真实但边际**。
4. **幅度层沿用已验证结果**(REPORT.md):ew(sue,npq_yoy),liquid-70 顶档超额 +0.40%/10d(t1.8)、+0.83%/20d(t2.9);分位区间 q10–q90 覆盖率 0.78(目标 0.80,待细化)。

## 1. 架构

```
            ┌─ 幅度层 mag_score = ew(sue, npq_yoy)          [已验证: PEAD 右尾]
排序+校准 ──┤
            └─ 概率层 prob_score = ew(−rvol,−ivol,−max5,−turnover,+ep) [频率倾斜]

校准层 caliblib.py(全 walk-forward,预测日 t 只用 <t 的训练日):
  每个训练日把 liquid-70 横截面按分数切 10 桶 → 跨训练日汇聚每桶的真实前向收益分布
  → 测试日股票按其桶获得:P(up) / P(跑赢中位) / E[ret] / E[ret|up] / q10..q90
  可选 regime 条件化(同 regime 训练日 shrink-blend)
评测层:Brier skill vs 训练基准率 / 可靠性曲线 / 日内 disc / 区间覆盖率 / 日期-个股方差分解
对抗:--shuffle(日内打乱分数→桶失去信息,disc/skill 必须塌)
```

## 2. 关键诊断(定稿)

**分数桶 × regime 的 P(up)/均值轮廓**(盈余惊喜分,liquid-70):+20d 顶桶(bin9)均值 +2.66%(up regime)/+5.71%(down regime)明显高于中位桶,但 **P(up) 0.508/0.596 不高于中位桶**(如 bin3 0.517/0.650)——幅度靠尾部不靠频率。bin0 也微抬(轻倒U:两端都动)。

**P(up) 横截面驱动因子**(+10d,liquid-70,上涨率 Q5−Q1):

| 因子 | 全样本 | UP regime | DOWN regime |
|---|---|---|---|
| ivol_60 | **−4.6pp (t−2.9)** | −4.5 | −4.9 |
| rvol_20 | −4.1 (t−2.7) | −3.6 | −5.8 |
| max5 | −4.0 (t−2.7) | −4.0 | −3.9 |
| turnover_20 | −3.3 (t−2.7) | −3.8 | −1.6 |
| **ep_ttm** | **+4.5 (t+2.5)** | +4.0 | +6.3 |
| sue / npq_yoy | +0.2 / +1.0(无) | — | — |

**日期 vs 个股方差分解**:+20d 上涨率方差中日期份额 ~21%,且当日基准率范围 0.12–0.97 → **绝对概率的主体是市场属性**,个股层最多贡献 ±5pp 左右的倾斜。

**零假设(6 seeds,日内打乱)**:disc 零分布 {+2.0, −1.7, +0.3, −1.0, −0.2, +0.9}pp——均值 0、两尾对称;harness 不会无中生有。

## 3. 诚实的产品语义(由以上直接导出)

- **上涨概率**显示为:`regime 基准率 ± 个股倾斜`(或直接用市场相对概率"跑赢中位数概率")。给精确到个位的绝对概率(如"73% 会涨")是不诚实的——日期不确定性 ±30pp 远大于个股区分 ±5pp。
- **上涨幅度**显示为:`E[超额收益] + q10–q90 区间 + E[涨幅|上涨]`,由幅度层分数桶的训练期经验分布给出。
- 两个数字**不可合并为单一"又高概率又高幅度"的分数**而不丢信息;若必须单一分,用期望收益排序(幅度层),概率作为属性标注。

## 4. 复现命令

```bash
PY=factor_research/.venv_research/bin/python
PROB='{"name":"prob_layer","method":"ew_signed","features":["rvol_20","ivol_60","max5","turnover_20","ep_ttm"],"params":{"min_cov":0.5},"min_train_dates":12}'
$PY factor_research/model/caliblib.py --horizon 10 --variant empirical --target rel --config "$PROB"   # 概率层校准
$PY factor_research/model/caliblib.py --horizon 20 --variant empirical --target abs                      # 幅度层(默认 final_model.json)
#   对抗: --shuffle N | 变体: --variant empirical_regime --shrink 0.5
```

## 5. 变体搜索 / 融合 / 对照 base_score(4 族 agent 工作流,8 agents)

每个正向声称经 statistics + economics 双 lens 对抗(skeptic 自己复现全部数字 + 新 seed 零分布 + 多重检验折减)。

### 5.1 prob_features:✅ 正向且存活(本研究系列首个双 lens 存活的声称)

**最优概率层 = `ic_weighted(ivol_60, max5, turnover_20, ep_ttm)`,h=20,target=rel,liquid-70:**

| 指标 | 值 |
|---|---|
| 日内跑赢率区分(顶/底 20%) | **+7.06pp(t2.83,n42,pos% 69%)**;abs 目标 +7.48pp(t3.96) |
| vs shuffle 零分布 | 14 seeds 合并:mean −0.07、std 0.83pp → 真值 **8.6σ** 超出;120 配置 Bonferroni 阈 ~2.9pp,**清 2.5×** |
| 可靠性(rel) | 单调(spearman 0.93,6/7 步);**abs 水平不可校准**(spearman −0.29) |
| liquid-50 | +7.26pp(t3.09)——更强,非微盘 |
| 留一切割 | 全正:最弱为剔 up_turbulent(31/42 日)+4.71pp t1.70 |
| 非重叠对照 | h20 标签重叠(step=10):奇偶半样本 6.99/7.13pp(t~1.9-2.1)——效应量不变 |

**消融**:ivol_60 + ep_ttm 扛全部区分度;**rvol_20 是纯稀释(每个 horizon 上剔掉都更好)**;beta_60 有害;turnover_20 在 h20 有贡献;区分度随 horizon 增强(h5 无边际→h10 +5.5pp→h20 +7.1pp)。regime 条件化校准对概率层同样无益(只动水平,而水平=不可知的市场)。
**必须随声称同行的 caveats**:① Brier skill ~0.0015——校准的是**倾斜**不是水平;② 最高预测桶在两个 horizon 都欠交付(h20 预测 0.538→实际 0.516)→ 产品显示需收缩极端桶;③ 31% 的日期上区分为负——逐日振幅大;④ 120 选 1 的乐观点估,**诚实前瞻预期 ~5-7pp**;⑤ 测试窗 0 个 down_turbulent 日——该 regime 未受测;⑥ 高 P(up) 股**不**多赚(disc_ret −0.56pp)——绝不能当收益预测卖。

### 5.2 prob_logistic:✅ 干净阴性(确认经验分桶是对的校准器)

walk-forward logistic 与经验分桶是**同一信号**(逐日区分相关 0.94-0.96)但全部 4 个 horizon×liquidity 格子上名义更差(h20: +5.55pp t1.86 vs 经验 +6.20pp t2.48),且原始概率过自信(顶桶预测 .564→实际 .509,Brier skill −0.001 vs +0.001)、共线性翻系数。**第二个硬结论:盈余惊喜对 P(up) 贡献为零**(条件于 vol/value 后 surprise-only disc −0.56pp t−0.34)——两层正交从两个方向都确认。

### 5.3 magnitude_band:✅ 正向且存活(幅度区间细化)

**最优 = `c_cf`:分数桶 × 当日 rvol_20 三分位 池化 + walk-forward conformal 宽度因子**(λ≈1.07-1.09,只用已到期的 OOS 残差,lag-aware 无泄漏):

| 指标 | bin-pooled 基线 | **c_cf** |
|---|---|---|
| q10/q90 pinball | — | **−4.4%/h10、−4.1%/h20(t 11.1/9.5,95-98% 日期为正)** |
| q10–q90 覆盖率(目标 0.80) | 0.777/0.787 | **0.799/0.805** |
| E[ret\|up] 校准斜率 | 0.36/−0.23(失真) | **1.15/1.02** |

vol-shuffle 零假设塌到 −0.1%(真值 +4.1~4.4%);liquid-50/剔年/剔 regime 全持有(t 5.2-16)。**Caveat:这是波动模型不是 alpha 模型**——区分来自 rvol,不是 PEAD 分数的功劳;0.80 覆盖率是**池化**保证,逐日覆盖仍随市场摆动(剔 2025 后其余日 0.73)。

### 5.4 fusion_product:✅ 决定性阴性(产品必须显示两个数字)

**两信号尾部反向对齐**(整体 spearman 仅 −0.04,但关键在尾部):**mag 顶档内,全部 PEAD 漂移在高波半区(+1.63%/20d,t2.88)——恰是 prob 分要剔除的;低波半区零漂移(+0.02%,t0.09)且无概率优势**。融合权重扫描(w_mag 1.0→0.0):顶档超额 +0.82%(w=1)→+0.08%(w=0.8)→负(w≤0.7);区分度 ≥3pp 需 w≤0.3;**判据交集为空**。且 w=0.3 融合分的区分度 2025 集中(剔 2025 → +0.21pp 噪声)——融合分连概率用途都不如纯概率分。

**对照 base_score(realbase 250×14 cells)**:prob 层与 base_score 作为 P(up) 预测器**打平**(fwd10:IC 0.057 vs 0.061;fwd20:0.079 t3.19 vs 0.072 t2.81;paired |t|<0.3;rank-corr 0.39——base_score 本就内嵌低波倾斜)。新概率层的优势是**透明、可校准、可控**,不是精度(n=14 上不可分)。

**标记的未验证线索**:高波×高惊喜交互(+1.63%/20d)是事后单次切分——值得作为下一个研究对象,须过完整 honesty bar。

## 6. 最终规格与天花板

**涨幅预测分数 = 两个独立显示的数字 + 区间(见 `emit_score.py` 产品形态演示):**

```
幅度层  mag_score_pct(盈余惊喜百分位)→ exp_excess(+20d 期望超额,顶档 ~+0.8%)
        + q10–q90 区间(c_cf 波动感知带,覆盖率 0.80)+ E[涨幅|上涨]
概率层  p_beat_median(校准的跑赢当日中位概率,基准率 ± 倾斜,顶/底差 ~5-7pp)
        ※ 不输出绝对 P(up)(市场主导,日基准率 0.12–0.97)
```

**天花板(出样本、liquid、walk-forward、对抗后)**:
- 幅度:顶档超额 **+0.8%/20d 毛**(t2.9;见 REPORT.md——净成本后仅月度调仓可能为正)
- 概率:跑赢中位的日内倾斜 **顶/底 ~5-7pp**(120 选 1 折减后的诚实预期;31% 日期为负)
- 水平校准:**仅市场相对目标可行**;绝对概率水平 Brier skill≈0,是市场属性
- 失效面:down_turbulent **未受测**(测试窗 0 日);极端高概率桶欠交付需收缩;两层都对 regime 条件化无响应
- vs base_score:概率上打平(它本就是 P(up) 型分数),幅度上严格更好(base_score 顶档≈0)

**上线前提**(承 REPORT.md §8 全部 6 条,另加):⑦ 两数字分开显示,禁止融合为单一"又高概率又高幅度"分;⑧ 极端概率桶收缩(clip/shrink);⑨ down_turbulent regime 出现时概率层降置信。
