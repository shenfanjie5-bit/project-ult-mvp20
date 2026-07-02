# 事件→个股影响系数:最终结论 + 集成预案 (Track A, 2026-06-09)

**一句话:** 在 5 类结构化事件里,**只有「业绩预告 forecast」一类扛过了预注册 kill 标准**——它是一个 **市场/规模中性的对冲 alpha(~+30bps/事件,扣 25bps 成本)**,按公告增速幅度加权做多正面预告,集中在每年 1 月/7 月;其余 3 类(评级/分红/增减持)判负;自由文本新闻(Track B)无历史、只能向前验证。**未经许可不落地;以下是证据 + 最小集成 diff 预案。**

研究产物(均未跟踪、未 commit):`factor_research/04_event_study/`(`eventlib.py` 脊柱、`run_A1_forecast.py`、`run_A2_other.py`、`REPORT_B_*.md`、`REPORT_C_adversarial.md`、`adv/` 去幸存者面板)。生产 `mvp20/` 全程只读未改。

---

## 1. 预注册 KILL 标准 · 逐事件判定

| 事件类型 | 样本(窗内) | K1 单调+显著 | K2 OOS 符号率 CI>50% | K3 多窗扣成本跑赢 | 判定 |
|---|---|---|---|---|---|
| **forecast 业绩预告** | 5,210→18,127* | ✅ +55/−46bps h1, both sig | ✅ pooled(短边弱) | ✅ **7/7 折**(去幸存者后) | **✅ 过(受限)** |
| report_rc 评级(level) | 98,856 | ❌ 买入≈中性 +0.12% | ❌ | ❌ 2/7 | ❌ 负 |
| report_rc 评级**变动** | 10,933 | ❌ 下调也**正**漂移 | ❌ | ❌ L/S 0/7 | ❌ 负 |
| dividend 分红预案 | 7,905 | ❌ 分红股**跑输**不分红股 | ❌ | ❌ 1/5 | ❌ 负 |
| stk_holdertrade 增减持 | 6,407 | ❌ 增持 1 日即退、减持反弹 | ❌ 0.48 | ❌ 2/7 | ❌ 负 |

\* forecast 在去幸存者全宇宙(5602 股)上 18,127 事件,长端 gross +57.3bps **t=14.0**(survivor 1617 股为 +55.2bps t=8.4)。**幸存者偏差不仅没撑信号,去掉后信号更强**——见 §3。

**诚实负结果同等有价值**:评级是卖方一边倒买入(86k 买/8 卖)无区分度,且下调后竟正漂移(分析师滞后);分红被预期且分红股反而漂移更少;增减持是一日脉冲随后均值回复。三类都不是"做错了",是**真没有可交易的带符号 alpha**。

---

## 2. 存活信号:forecast 系数模型(可上线的形态)

业绩预告事件 → 带符号显示系数(代表 **t+1 起 h=1 的规模调整超额收益** 预期):

```
sign = +1 if type∈{预增,略增,扭亏,续盈,减亏} else −1 if type∈{预减,略减,首亏,续亏,增亏} else 0
m    = (p_change_min + p_change_max)/2 / 100          # 扭亏/首亏 p_change 为 NaN → 用类别默认
# E[abn_1] 由 A1 的分位曲线标定(单调于公告增速,非二值):
#   预增 Q1→Q5: +0.22% … +1.18%(增速≥~90% 在 Q4–Q5 才显著)
#   预减 深跌端: −0.62% … 浅跌≈0
#   略增/略减/续盈/不确定 ≈ 0(零权重)
E_abn = forecast_curve(sign, m, type)                # 常数冻结自 run_A1_forecast.py
coefficient = tanh(200 · E_abn)                      # 有界[−1,1];+0.55%→0.75,+1.1%→0.98
```

**诚实边界(必须随系数一起暴露,别又造装饰数字):**
- 它是 **对冲后** 的超额收益:裸多头实收 ≈+9bps、5/7、随大盘 ±100bps/折 → 系数代表的是"相对同规模股的超额",不是裸收益。
- **短边(负面预告)脆弱**:清洁 预减/略减 短腿仅 +1.3bps、2/7;负端的 fold 胜靠 续亏/首亏。→ 负系数显示但标"soft/低置信",不当强空。
- **日历**:83% 正面事件落在 1 月/7 月预告窗 → 一年两次批量,其余时间该信号"无事件"。
- **容量**:赢家是中盘(中位市值 ¥8bn),可部署区间 数千万~低数亿/窗,不可大规模摊。

---

## 3. 对抗审查要点(独立 agent + 本人复核)

- **幸存者偏差被证伪、且反向**:1617 面板是"选择"偏差(只取已打分股 + 滤 ST/退);DockCase 日线有 5825 股。去幸存者建 5602×816 面板后,长端 net +31.1bps(6/7)→ **+32.8bps(7/7)**,t 翻倍。机制:幸存者同时抬高个股收益与同规模基准 → **在超额数里抵消**。全宇宙 placebo(打乱日期)+4.5bps vs 真 +57bps → PIT 干净。
- **非规模/行业假象**:换 market-adjust(+31.1)、110 行业 industry-adjust(+31.5)皆 7/7;超额在每个规模十分位都为正。
- **非少数极端撑起**:剔头尾 1%(+27.2)、winsor(+30.4)仍 7/7;扣 40bps 仍 +17.8/6-7。
- **聚类显著性**:朴素 t=14 高估(窗内相关),按日聚类 t=6.0、按月 t=5.3,仍决定性为正。

> 关键更正(写给后续):**别再叫它"+30bps 多头"**——那是对冲 alpha,裸多头只有 ~+9bps。

---

## 4. Track B(自由文本新闻 + LLM)——只能向前,现在不上真系数

`realtime_current` 是热 UPSERT 快照、无历史 → **无法历史回测**。设计已就绪(`REPORT_B_*.md`):
- 抽取:Haiku 4.5(`claude-haiku-4-5-20251001`)+ tool-use 结构化输出 `{event_type(14类), polarity, strength(0-3), rationale}`,~$0.24/千条;便宜基线=关键词词典 + FinBERT-中文 对照。
- 先验系数(验证前):`tanh(200 · sign(polarity) · {0:0,1:.001,2:.0035,3:.007}[strength])`。
- **向前验证协议**:今起每日快照新闻入 append-only 归档(`runtime/trackB_archive.sqlite`,`(ts_code,title_hash)` 唯一索引 + 跨股回声标记),累计 ≥6–7 周(~2026-07-25)后跑同一套 eventlib + kill 标准。**在通过前,系数一律 `validated:false`,不得当预测信号呈现。**

---

## 5. Phase 4 · 最小集成 diff 预案(**未应用,待你拍板**)

> 原则:**只让"挣到验证"的系数流通**。业绩预告=validated:true;自由文本新闻=`null`+validated:false(不显示假数字),并修 chip 语义。改 `mvp20/server.py`(生产)前后须 `pytest` 全绿(rc=0)。

**(A) 后端——真正的验证赢点:新增「业绩预告」事件源 + 系数**
`mvp20/server.py::handle_market_events`(事件 dict 组装在 `server.py:666`,返回在 `:695`)。
- 新增一个 DockCase 业绩预告读取(只读、`DOCKCASE_WRITEBACK=0`),取近 N 日 `ann_date` 事件,按 §2 公式算 `coefficient`,并入 `collected`,字段:
  ```python
  {"ts_code":..., "dp_id":"L?.event.forecast", "title": f"业绩预告·{type}", "timestamp_epoch":...,
   "coefficient": round(coef,4),
   "coefficient_meta": {"validated": True, "model":"forecast_v1", "horizon_days":1,
                        "basis":"size-adj abnormal CAR", "caveats":["short_leg_soft","jan_jul_seasonal"]}}
  ```
- 现有自由文本新闻 dict(`server.py:666`)追加 `"coefficient": None, "coefficient_meta": {"validated": False, "reason":"track_b_forward_only"}`。

**(B) 前端——去写死 0 + 不展示未验证假值**
`FrontEnd/src/pages/MarketOverview/hooks/useRealMarketEvents.ts`:
- `MarketEvent` 接口(:17)加 `coefficient: number | null` 与 `coefficient_meta?: {...}`。
- reshape(:48)把 `coefficient: 0` → `coefficient: e.coefficient`(null 表示未验证);`affected_companies` 项透传 `validated`。

**(C) chip 颜色/符号语义修复(确认是 bug)**
`FrontEnd/src/components/explanation/EventTimeline.tsx:80` 现为 `const positive = c.coefficient >= 0` → **0/未验证被判正染红"利好"**(文件注释自称"0 灰",实际不是)。改为三态 + 未验证态:
```tsx
const EPS = 0.05
const tone = c.coefficient == null ? 'unknown'
           : c.coefficient > EPS ? 'pos' : c.coefficient < -EPS ? 'neg' : 'neutral'
// A 股惯例:pos→红(danger), neg→绿(success), neutral→灰, unknown→灰+虚线/"未验证"角标
```
(A 股红涨绿跌,故 正系数=红=利好 正确;只需修零/中性/未验证三态。)

**(D) 测试计划**
- 后端:`tests/test_market_events_coefficient.py` —(1)forecast 事件带 `validated:true` 且 `coefficient∈[−1,1]`;(2)自由文本新闻 `coefficient:null, validated:false`;(3)系数符号与 type 映射一致(预增>0、预减<0、略增≈0);(4)`DOCKCASE_WRITEBACK` 未被置 1。改 server.py 后跑**全套 `pytest` rc=0**。
- 前端:`EventTimeline` 单测 — coefficient=0/null→灰/未验证(非红);>EPS→红;<−EPS→绿;`formatCoefficient(null)` 不崩。
- 端到端:`/market-events` 返回含 forecast 事件时,面板 chip 显示真符号与色。

---

## 6. 建议(你来定)

1. **上线 forecast 系数**(业绩预告事件,validated:true)+ **修 chip bug** + **新闻系数置 null/未验证** —— 这是诚实的最小赢点。按 §5 出 PR(我可落地 diff + 测试,改 server.py 跑全 pytest)。
2. **同时启动 Track B 向前归档**(今起收集),~7 周后用同一 kill 标准判 Track B 能否上真系数。
3. **不做**:把 Track B 先验系数当真值显示(=任务明令禁止的装饰数字)。
4. forecast 作为**研究/批量信号**(每年 1/7 月、中性对冲、中盘容量)比作"实时每条新闻系数"更贴合它的真实形态——值得讨论它在产品里的正确位置。

**预注册标准全程未挪;负结果如实判负;forecast 的天花板与边界已量化(§2/§3)。等你拍板再落地任何 diff。**
