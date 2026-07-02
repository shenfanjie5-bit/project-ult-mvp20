# P&L 闭环 + 涨幅预测分数影子输出 —— 实施状态(2026-06-10)

> 落地 `factor_research/model/REPORT_FRAMEWORK_ENHANCERS.md` §4 接入蓝图的 Phase 0-2。
> 全部经独立对抗验证(代码评审 request_changes→9 项已修;数学一致性 BIT-EXACT)。

## 已交付(按提交)

| commit | 内容 |
|---|---|
| `c4efdba` | **Phase 0 G1**:生产 P&L 反馈闭环(`mvp20/pnl_loop.py` + `scripts/run_pnl_loop.py` + `/api/backtest` 真实化) |
| `b0e74be` | **Phase 1 G2/G3/G6**:两层模型影子输出(`config/quant_score_params.json` 冻结参数 + `mvp20/quant_score.py` + `scripts/build_quant_scores.py` + `/score` 附 `quant` 块) |
| `3360bf5` | **M-3**:guidance_change 公告年龄门(90→270d) |
| `bb192ec` | **对抗评审修复批**:1 HIGH(价格源故障永久污染)+3 MED(盘中/回填防护+墙钟审计、REPO_ROOT 锚定、ep_ttm 漂移)+5 LOW;黄金一致性钉测试 |
| `80d7af3` | **Phase 2 G5**:forecast 喂分编码统一为 `forecast_coefficient` + 2→7d 事件窗衰减 |

## 运行契约

```
夜间(收盘后,二者独立幂等):
  .venv/bin/python scripts/run_pnl_loop.py        # 快照→到期回填→评测;15:30 前自动拒绝
  .venv/bin/python scripts/build_quant_scores.py  # 重建 quant 工件(~15s,asof=档案最新日)
月度(研究 venv):
  factor_research/.venv_research/bin/python factor_research/model/panel.py
  factor_research/.venv_research/bin/python factor_research/model/export_params.py
```
- P&L 库:`runtime/backtest/pnl.sqlite`(与 PIT 实验库分离);首个合规快照 base_date=20260610(15:35+ 重建;此前 13:50 的盘中快照已删——评审抓的违约)。**首批真值:h=5 于 2026-06-17 到期,h=10 于 06-24,h=20 于 07-08**。
- de-rate 规则(预注册):trailing 12 个到期日,顶五分位超额 bootstrap 95% CI 上界 <0 且 ≥8 日 → `de_rated:true`(只标记不动分)。
- quant 工件:`runtime/quant_score/A_share.json`(liquid-70 门外/覆盖不足 → validated:false;>10 天 → stale 降级;**绝不输出绝对 P(up)**)。

## 已知边界(诚实)

1. **:8701 旧代码**:重启后 `/score` 才带 `quant` 块、新事件编码才生效——P&L 快照(脚本进程)已用新代码,旧服务展示与快照存在短暂语义差,重启即收敛。
2. quant 工件 asof 跟随 DockCase 档案(当前 20260605,落后 3 个交易日);>10 天自动 stale。档案刷新频率决定特征新鲜度。
3. pnl eval 严格同日收盘 join,停牌股缺价被剔除(轻微幸存者偏置,评审已记录)。
4. 冻结概率层权重为全样本 IC;regime 翻转时降级(down_turbulent 未受测,见 params caveats)。

## 待做(蓝图顺位)

- **Phase 3**:概率层 v3(+t5a 题材热度反号第 5 因子;需把 涨跌停和炸板数据+THS 概念成分 接入 builder 特征)+ 题材过热避开标记
- **Phase 4**:RD-A merit/timing 双轴 + confidence abstain + G9 排名面
- **Phase 5**:R-7 regime 降权(P&L 闭环积累一个季度后定参)
- 运维:夜间两脚本挂 cron(待用户确认方式);前端 quant 块展示
