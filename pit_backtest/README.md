# pit_backtest — A 股评分系统无超前回测 (isolated)

以「30 / 60 / 90 个交易日前」为基准日，对全 A 股池打分并评估其后前向收益的预测力
(rank-IC / 分位多空 / signal 桶)，**严格杜绝 look-ahead**。

## 隔离保证
- **不修改任何 `mvp20/*` 或 `scripts/collector.py`**；评分引擎只通过 `import` 复用。
- 直接调 tushare `pro` API 自建 PIT 数据（`f_ann_date/ann_date ≤ 基准日` 过滤 + qfq 复权），
  **现有泄漏 fetcher 根本不被调用**。
- 只写 `runtime/backtest/`（独立 DB，每基准日一子目录）与 `docs/audit/`；**绝不碰** `runtime/hot.sqlite`。

## 口径（已与用户确认）
- 分数**排除 LLM 定性层 L0-L3**（`score._freeze_qualitative_layers`）+ **冻结行业景气 L0**（`industry_overlay=None`）。
  fundamental 退化为硬财务(L5)+估值(L6)+资金(L7)+风险(L8)骨干。
- 池子 = `config/mvp20.universe.yaml` 的 116 只 A 股（**survivorship-biased**，报告中标注）。
- 拟合常数（阈值/再中心化基准）**接受当前固定值**（标签层二阶超前，书面说明）。

## 模块
| 文件 | 职责 |
|---|---|
| `calendar.py` | `trade_cal` 解析 T-30/-60/-90/T0 交易日 + 6 个前向 (base→end) 对 |
| `collector.py` | 直连 `pro` 的 PIT 采集器（复刻生产 emitter payload，逐条 `f_ann_date≤asof` 过滤） |
| `prices.py` | hfq 复权收盘 / 前向收益 / 停牌顺延 |
| `derive_pit.py` | `DeriveRunner` 子类，注入 asof 时间戳（纯 DB→公式→DB 复用） |
| `score.py` | 复刻 `cli.score_company_command` glue + L0-L3 冻结 |
| `pipeline.py` | 单基准日 collect→derive→peer_context→score |
| `runner.py` | 全流程编排（3 基准日 × 116 股）+ 前向收益，可断点续跑 |
| `store.py` | 结果 sqlite（scores / returns / manifest），幂等 resume |
| `metrics.py` | numpy rank-IC / 分位 / signal 桶 / bootstrap / 跨窗口聚合 |
| `leakage_audit.py` | 独立泄漏复验（observation-date ≤ asof / 收益已实现 / 前向价隔离） |
| `report.py` | 指标聚合 → `docs/audit/a_share_pit_backtest_<today>.md` + `backtest_results_<today>.csv` |

## 运行
```bash
export TUSHARE_TOKEN=...                       # 或 .env
python scripts/run_pit_backtest.py --today 20260605    # 采集+衍生+peer+打分+收益
python scripts/run_pit_backtest.py --report            # 指标 + 报告
python scripts/verify_pit_no_leak.py                   # 独立泄漏复验（exit≠0 = FAIL）
```
单基准日重跑/调试见 `pipeline.build_pit_for_asof()`。

## 产物
- `runtime/backtest/<asof>/pit.sqlite` + `peer_context_A.json`（每基准日 PIT 快照）
- `runtime/backtest/backtest.sqlite`（scores / returns，可复跑源数据）
- `docs/audit/a_share_pit_backtest_<today>.md`（结论 + 方法论 + 残留泄漏/survivorship/LLM 隐性记忆/小样本声明）
- `docs/audit/backtest_results_<today>.csv`、`docs/audit/production_lookahead_findings.md`

## 已知局限
见报告「方法论与残留风险」段：行业 L0 冻结降低 fundamental 覆盖度、拟合常数二阶超前、
情绪类 dp_id 无历史端点、survivorship 上偏、小样本功效不足、LLM 隐性记忆不可清除（故分数不含 LLM 主观判断）。
