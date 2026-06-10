# 生产评分链 · 超前 (look-ahead) 泄漏清单

> 这些是 **PIT 回测过程中发现的现有生产代码泄漏**。回测本身通过**独立 PIT 采集器**
> (`pit_backtest/collector.py`) 绕开它们，**未修改任何生产文件**。本清单交由你另行验证/处理。
> 行号基于分支 `feature/a-share-fixes`（采集时工作树）。

## 影响概览
现有 `score-company` / collector daemon 在**当前时点**打分时这些泄漏多数无害（“现在”就是最新）。
但任何**历史/回测/复算**场景，或当某条数据的“最新已知”晚于其报告期时，都会把未来信息带进分数。

## 状态（2026-06-06 处理，用户定 scope = 修 L3 + L1/L2、L4 暂缓）
- **L1 ✅ 已修**：`_fetch_a_share_fina_indicator` / income / cashflow / balancesheet(limit 1→5) / `_get_fina_records` / `_get_forecast_records` 加 `_visibility_date`(f_ann_date 优先) + `_drop_future_filings(asof=today)`；income/cashflow/balance 的 `fields=` 补 `f_ann_date,ann_date`。`fina_mainbz`(分部、非打分、无 ann_date) 留作不动。
- **L2 ✅ 已修**：`_fetch_a_share_forecast` + cache helper 加同款过滤(空→镜像 no-forecast Inactive)。
- **L3 ✅ 已修**：`_fetch_a_share_history` 用 `pro.adj_factor` → hfq 复权 OHLC(run_up/technicals/250d-MA 除权日不再假跳);vol 与 PE/PB/turnover 复权无关、不动;adj_factor 缺失则降级裸价。
- **L4 ⏸ 暂缓**：now 锚定/缓存串日/peer_context 读活库 = asof 贯穿全链的大架构改,仅 recompute 用;回测已有独立 PIT harness、live 本就正确 → 留待"生产需历史复算"时做。
- 验证:全套件绿 + `_drop_future_filings`/`_visibility_date` 单测 + L3 复权逻辑核对。helper 与单测见 `mvp20/sources/tushare_source.py` / `tests/test_tushare_core_batch.py`。

---

## L1 — 财报选取无 `f_ann_date` 过滤（第 1 大泄漏）
**位置:** `mvp20/sources/tushare_source.py`
- `_fetch_a_share_fina_indicator` (~L2774)：按 `end_date` desc 取 `records[0]`，**从不**看 `ann_date`。
- `_fetch_a_share_financials`：income (~L2297) / balancesheet (`limit=1`, ~L2556) / cashflow (~L2476) 同样取最近报告期，**无** `f_ann_date` 过滤；且 income/balance 的 `fields=` **未请求** `f_ann_date`。
- `_fetch_a_share_derived_metrics` 的 `_get_*_records` (~L4928–5055)：`limit=8`，`records[0]`，同样无过滤。

**后果:** 报告期 end_date 早、但**披露日在基准日之后**的财报会被当作“已知”。例：基准日 2026-01-16
取到 2025 年报（披露 2026-04-11）或 2026Q1（披露 2026-04-30）= 直接泄漏未来。
**建议修复:** 各 fetcher 加 `asof_date`，fetch 后先 `filter (f_ann_date or ann_date) <= asof` 再取最近期；
income/balance 的 `fields=` 补 `f_ann_date`。（PIT 采集器已用此法，见 `pit_backtest/collector.py::_visible_records`。）

## L2 — `pro.forecast` 完全无日期过滤
**位置:** `_fetch_a_share_forecast` (~L3081) 调 `pro.forecast(ts_code=...)`，按 end_date/ann_date 取最新。
**后果:** 基准日之后发布的业绩预告（`L9.company.earnings_guidance` / `L5.fcst.guidance_change`）会泄漏。
**建议修复:** `filter ann_date <= asof`。

## L3 — 全链价格无复权
**位置:** `mvp20/derive.py::_fetch_a_share_history` (~L1802) 用裸 `pro.daily`（未复权）。
**后果:** `L6.priced.run_up`、250 日 PE 均线、技术指标在除权除息处计算错误（拆股/分红当日跳变）。
**建议修复:** 包一层 `pro.adj_factor`，统一 qfq/hfq；run_up / 250d-MA / 收益全程一致。
（PIT 采集器用 hfq，见 `pit_backtest/prices.py`。）

## L4 — `now` / `今天` 锚定 + 模块缓存串日 + peer_context 读活库
**位置:**
- `tushare_source._today_yyyymmdd` (~L412) / `_previous_n_days` (~L416)：daily_basic 快照、moneyflow、report_rc、historical_percentile、Bucket A/B 历史窗口全部锚定 `end=today`。
- 模块缓存（`_DAILY_BASIC_HISTORY_CACHE` 等，按 `ts_code` 键）：跨基准日复用会串日返回错日期行。
- `mvp20/peer_context.py::peer_context_for_market`：读**活库**快照、按 DB mtime 缓存，**无日期维**。
- `mvp20/aggregator.py::_recency` (~L231/245)：用 `datetime.now()` wall-clock 衰减（仅作用于定性/overlay 节点）。
- `mvp20/derive.py::DeriveRunner.run_all` (~L3010)：`now=int(time.time())` 喂 `news_age` 衰减并作 `updated_at` 戳。

**后果:** 历史复算时窗口/缓存/横截面都会指向“现在”。
**建议修复:** 所有窗口贯穿 `asof`；缓存键含 asof 或每基准日独立进程；`peer_context_for_market` 加 `as_of`；
`aggregate_company_graph`/`DeriveRunner` 加 `ref_now`/`now_epoch`。（PIT 管线用每基准日独立 DB+子进程
+ asof 戳规避，见 `pit_backtest/`。）

---

## 备注：非泄漏但相关的口径问题（来自既有审计）
- per-stock 定性 L0-L3（codex 填）经 `_to_scalar` 贡献≈0（仅 ~114 个裸 `trend` 节点 0.2 cap 漏入）；
  回测已整体排除 L0-L3。
- 拟合常数（BUY≥0.30 阈值、ROE_BENCH=3.1 等再中心化基准、archetype 毛利率中位数）在当前池标定 —
  回测按确认接受并书面说明（标签层二阶超前）。
