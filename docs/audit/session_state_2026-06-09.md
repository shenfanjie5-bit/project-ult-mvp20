# Session state handoff — 2026-06-09 (compact-safe)

## 正在运行的服务(均 nohup 脱离,扛 session 重启/compact)
- **backend**: `mvp20.cli serve` :8701(健康检查会按 pgrep 认出 PID)。
- **frontend**: vite dev :1420(`cd FrontEnd && npm run dev`)。
- **20分钟健康监控**:ScheduleWakeup 循环(prompt 自包含)+ `/tmp/health_check.sh`(在盘上)。
  - 自愈:组件 DOWN→重启;/score >1.5s→重启(退化);backend 跑满 6h→预防性重启(SSE 累积根因的兜底)。
  - **compact 后监控照常**:wakeup prompt 自包含(跑 /tmp/health_check.sh + 重 arm),脚本在盘上。

## 今天(06-09)完成的改动
### 生产代码(git 跟踪,**未提交** — 用户要提交再提)
- `mvp20/sources/dockcase_cache.py`:read() 加 `drop_duplicates`(修 fina_indicator ~33%/文件 完全重复;只删整行重复,保留多report_type/多产品/多券商)。`test_dockcase_cache` 过。
- `mvp20/server.py`:① `handle_orchestrator_runs_stub` + 路由(修 /orchestrator/runs 404→200 空态,EvidenceConsole/Audit 不再加载失败);② `httpd.daemon_threads = True`(防 ThreadingMixIn._threads 死线程累积)。
- `mvp20/sse.py`:max_duration 30→10min、heartbeat 30→15s(半开/遗弃 SSE 流早释放)。
- 全套件 0 失败(SSE 修复后)。
### 前端(`FrontEnd/` 被 gitignore,改动在盘上、已 build)
- `pages/StockDetail/components/GovernanceEventsPanel.tsx`(新):治理与事件面板,展示 4 个新 Track B 节点(L8.gov 减持/管理层 + L9.company 分红回购/业绩指引),读真 /aggregate。已接入 StockDetail。
- `pages/MarketOverview/index.tsx`:**修 fan-out bug**——工作台原本给全宇宙 ~1641 只股各发 /score(>30s 卡死);改成先用客户端 mock 排序、只 score 前 `SCORE_FANOUT_CAP=30` 只。卡片走 mock 即时渲染(DOM 101ms),分数背景精修。

## 已验证的 SSE 泄漏修复
开 5 SSE 流 → 杀客户端 → 连接立即回 baseline(`/tmp/sse_leak_test.sh`)。常见泄漏(导航/关页)已清理;半开连接由 10min 上限 + 6h 预防重启兜底。

## base_score 建模核心结论(今天确立,别再绕 rank-IC)
- **base_score 是"质量/安全"排序,不是"预期收益"预测器。** 17日校准:P(涨)弱正向但区间极窄(~50-60%),**E[收益]反向**(corr −0.7~−0.95,均值回归)。高分=胜率略高涨幅小,低分=博彩型涨幅大。
- **Tier-0 静态校准 + regime gate 在真实 base_score 上都被否决**(详 docs/audit/regime_conditioning_r7_2026-06-08.md、moneyflow_crossdate_validation_2026-06-08.md、factor_research/.../RESULTS8_gate2_dual.md)。
- **真问题在 P&L 层不在 IC 层**:date3 rank-IC 倒挂在真实 BUY 组合上其实没亏(+0.73%),真亏的是 date2(−4.83%)却 IC 好。
- 已给用户一个**新对话 prompt**(让多 agent 搭"涨幅预测模型",return-trained + walk-forward + P&L 验证,诚实天花板 rank-IC~0.05)。

## 待办 / 已 offer(用户未拍板)
- batch `/scores?ts_codes=` 接口(消除工作台 30-请求突发的后端 GIL 尾巴)。
- 前端 hero(上涨概率/主要驱动 = mockDerive 占位)接真后端 /score。
- 一批 project-ult 控制台页是桩(graph/data/cycle/backtest/alerts 返回空)→ 接真后端清单。
- SSE 泄漏根治已做(上面);若仍长跑退化,查 hot.sqlite 增长/锁。

## 关键文件
- /tmp 留底:health_check.sh、sse_leak_test.sh、redesign_plan.md、calibrate_prob.py、gate_realbase.py、regime_filter.py、regime_component.py、bt_short.py、date3_regime.py。
- docs/audit/:session_handoff_2026-06-07.md(回测线)、moneyflow_crossdate_validation_2026-06-08.md、regime_conditioning_r7_2026-06-08.md、本文件。
