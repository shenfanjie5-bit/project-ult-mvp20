# Track-B 字段扩展提案:4 个「可脚本填充」结构化评分节点

状态:**提案 / 待审查**。本提案只产出代码 + 测试 + 抽样验证 + 设计说明,**未合并、未提交、未跑 generate/compile/rescore、未改 `config/stock_overlays/*`、未碰 DockCase 写入与回测产物**。

把分红回购 / 业绩指引 / 股东减持 / 管理层变动 4 个字段从「评分目录里有定义但从未实例化」接进打分图谱,并写确定性抽取。

---

## 1. 字段 → 节点映射

| 用户字段 | dp_id | data_point_roles 语义 | tushare 源 | DockCase 缓存 |
|---|---|---|---|---|
| 分红回购 | `L9.company.buyback_dividend` | score_component → **expectation_gap** (participates=true) | `dividend` | 有(零下载) |
| 业绩指引 | `L9.company.earnings_guidance` | score_component → **expectation_gap** (participates=true) | `forecast` | 有(零下载) |
| 股东减持 | `L8.gov.insider_sell` | discount → **risk_discount** (risk_factor/subtract_risk, participates=true) | `stk_holdertrade` | 有(零下载) |
| 管理层变动 | `L8.gov.management_change` | discount → **risk_discount** (participates=true) | `stk_managers` | **无(live 联网)** |

---

## 2. 打分语义核对结论(本任务最关键的一步)

### 2.1 两条独立的打分路径

研究 `mvp20/aggregator.py` + `mvp20/scoring.py` + `mvp20/field_governance.py` 后,确认存在两条互不相同的入分路径:

1. **Overlay 节点路径**(`aggregate_company_graph` → `_leaf_score` → `_aggregate_parent`):读 overlay YAML 里 author 出来的节点。**这 4 个字段走这条路**(`script_fill.write_to_overlay` 把值写进 overlay YAML)。
2. **Realtime 合成路径**(`synthesize_realtime_nodes` → `_realtime_field_signal`):读 `runtime/hot.sqlite` 的 `realtime_current` 快照,与 overlay 节点去重。该路径已有 `L9.company.earnings_guidance` 的专用规则(读 `change_pct_min/max`),但它消费的是 realtime 快照、不是 overlay 节点 —— 与本提案的 overlay 路径**正交、不冲突**(`existing_dp_ids` 去重保证同一 dp_id 不会被两条路双计)。

### 2.2 口径冲突的解决:谁说了算

`data_point_roles.yaml` 给 buyback/guidance 标的是 `weighted_contribution / weighted_sum`,而既有已实例化的 L9.company catalyst 槽(ma / product_order)用的是 `or_gate / or_max_trigger`。核对发现 **这个冲突在数值上是无害的**:

- `aggregator._leaf_score` 的实际数学 **不读 `calculation_type` / `aggregation_policy`**。叶子分数只由三件事决定:`direction`(符号)、`value` 经 `_to_scalar` 得到的 magnitude、`data_status`(Known/Inactive/Unknown 闸门)。`calculation_type` 只是图谱引擎元数据 + 前端展示用。
- `field_governance.apply_to_node` 在打分时会用 `data_point_roles.yaml` **强制覆盖** `participates_in_score`(无条件),并在节点缺字段时填 `score_target` / `calculation_type` / `aggregation_policy`。所以 `score_target`(expectation_gap / risk_discount)由治理表说了算,SlotDef 写什么 `calculation_type` 不影响最终分。

**决策:SlotDef 的形态对齐【既有同族已实例化槽位】**(任务明确要求),而不是盲从 data_point_roles:

- buyback/guidance → 用 L9.company.ma/product_order 的形态:`or_gate / or_max_trigger`、`data_status="Inactive"`、`missing_policy="inactive_zero_weight"`、`active_weight=0.0`、`default_missing_reason=None`。
- insider_sell/management_change → 用 L8.gov.fraud_control/litigation 的形态:`risk_factor / subtract_risk`、`direction="negative"`、其余 Inactive 默认同上。

### 2.3 关键:`participates_in_score` 的差异(score-drift 的根源)

实测既有已实例化节点(从真实 overlay 读)的治理覆盖:

```
L9.company.ma / product_order : participates_in_score=False  ← 治理表禁掉,完全惰性
L9.media.short_report          : participates_in_score=True
```

而本提案 4 个 dp_id 在 `data_point_roles.yaml` 里 **全是 `participates_in_score: true`**。这意味着:**一旦被 script_fill 填成 `data_status=Known`,它们会真实进分**(既有的 ma/product_order 即使填了也不进分,因为治理把它们禁掉了)。这是本提案与既有惰性 catalyst 的本质区别,也是 score-drift 的唯一来源(见 §7)。

### 2.4 入分链路(逐节点,实测验证)

对每个标准 author 出来的【standalone 叶子】(`parent_node=None`):

1. `_leaf_score`:`Known` → `intrinsic = direction_sign × _to_scalar(value) × recency`;`Inactive` → 0 且被丢出聚合;`Unknown` → 0 但留在分母降覆盖率。
2. **standalone 叶子的 `score` 直接存 `intrinsic`,与 `active_weight` 无关**(实测确认:`aggregator.py` 第 2093 行,叶子结果 `score=leaf["score"]`,不乘 `_effective_weight`)。⟹ 默认 `active_weight=0` **不会**把已填的事件节点清零;它只在节点作为某父节点的 child 时才参与重归一化,而这 4 个是 standalone 叶子。
3. `scoring._role_components_from_flat` 汇总:
   - `expectation_gap = _sum_role_target("expectation_gap", damp=True)` —— **带符号**的 `Σ(score×conf) / max(1, Σconf)`。正向 direction 抬高、负向压低。
   - `risk_discount = _sum_role_targets({risk_discount,...}, absolute=True, damp=True)` —— **取绝对值**(只要 magnitude),然后从最终分**减去**。

### 2.5 由此推导的 value schema(为什么必须带 `value.score`)

`_to_scalar` 优先读 `value` 里的 `score`/`intensity`/`strength` → magnitude。**既有 `_catalysts` 旧实现产出的 value 不带这些 key**(`{cash_div, stk_div, div_proc}`),实测 `_to_scalar` 返回 0 → 贡献为 0。所以本提案的 value schema **必须带一个 `score` 字段**(我编码进的 [0,1] magnitude),否则即使填了也是零贡献。

方向编码:`buyback` 恒 positive;`guidance` 由 forecast `type` 动态定(预增/扭亏 → positive;预减/首亏 → negative),`write_to_overlay` 把每条记录的 `direction` 写进节点(slot 默认 positive,预减时被覆盖为 negative);`insider_sell`/`management_change` 恒 negative(进 risk_discount,符号被 abs 取用,仅用于 top-path 排序)。

---

## 3. 抽取语义(确定性,走 DockCase 缓存只读)

纯解析函数(`parse_*`,接收 `DataFrame.to_dict("records")`,零网络、可 hermetic 单测):

- **`parse_buyback_dividend`** ← `dividend`:取最新【已实施 `div_proc=='实施'`】记录(无已实施则回落最新)。`cash_div<=0 且 stk_div<=0` → None(无实质分红,如 688981 中芯国际从不分红 → 正确返回 None)。`score = clip01(0.8·tanh(cash/1.0) + 0.2·tanh(stk/0.5))`(分红是温和利好,knee 1.0 元/股,不主导 eg)。direction=positive。
- **`parse_earnings_guidance`** ← `forecast`:取最新一期。`type` 定方向(`_FORECAST_POS_TYPES` / `_FORECAST_NEG_TYPES`),未知类型(如「不确定」)→ None(不污染 eg)。`score = clip01(max(tanh(|avg(p_change_min,max)|/100), 0.15))`(floor 0.15 防真实预告塌到 0)。
- **`parse_insider_sell`** ← `stk_holdertrade`:近一年(`ann_date >= asof-365d`)`in_de=='DE'` 减持。`net_decrease_pct = Σ|change_ratio|`;`score = clip01(tanh(net%/3.0) + 0.05·min(笔数,4))`。无 DE → None。direction=negative。
- **`parse_management_change`** ← `stk_managers`(**live 联网,非缓存**):近一年高管【离任 `end_date` 非空】。核心高管(董事长/总经理/CFO/董秘…)×1.5 加权。`score = clip01(tanh(加权离任数/3.0))`。无离任 → None。direction=negative。

evidence_sources 与 codex 同构:`{"kind":"local_dp_id","dp_id":<endpoint>,"source":"tushare:<endpoint>:<period>"}`。

---

## 4. 零下载 vs Live(stk_managers)

- `dividend` / `forecast` / `stk_holdertrade` **都在 DockCase 缓存**(`_ENDPOINT_FOLDER` 含这三个),走缓存只读、零下载。实测 `dc.available()==True`,三者均返回真实缓存数据。
- **`stk_managers` 不在 DockCase 缓存**(`_ENDPOINT_FOLDER` 无此 key)→ 是 **live 网络读**。因此 `management_change` 做成**可关**:`extract(..., include_management_change=False)`(默认关闭),`_catalysts` 只在显式开启时才 fetch `stk_managers`。批量补空建议保持默认关闭,避免为每只股触发网络。
- 全流程置 `DOCKCASE_WRITEBACK=0`,**绝不写 DockCase**;`_get_pro_api()` 返回的是 DockCase-cached pro 包装(命中即不下载)。

---

## 5. 抽样验证(10 只真实 A 股,只读,asof=2026-06-06)

走 DockCase 缓存只读 + 纯解析器(零下载、零写入):

```
600519.SH | buyback s=0.8    实施 cash=23.957 | guid s=0.15  略增 dir=positive | insider=None
000063.SZ | buyback s=0.4392 实施 cash=0.617  | guid s=0.5428 预增 dir=positive | insider=None
688981.SH | buyback=None(从不分红)           | guid=None(type 不确定)        | insider=None(DE 超 1 年窗口)
000001.SZ | buyback s=0.2762 实施 cash=0.36   | guid s=0.15  略增 dir=positive | insider=None
600000.SH | buyback s=0.3108 实施 cash=0.41   | guid=None                      | insider=None
002415.SZ | buyback s=0.5081 实施 cash=0.75   | guid=None                      | insider=None
601857.SH | buyback s=0.1732 实施 cash=0.22   | guid s=0.5546 预增 dir=positive | insider=None
600050.SH | buyback s=0.0886 实施 cash=0.1112 | guid=None                      | insider s=0.5874 pct=1.226 n=4
601728.SH | buyback s=0.0724 实施 cash=0.0908 | guid s=0.2636 略增 dir=positive | insider=None
000338.SZ | buyback s=0.2748 实施 cash=0.358  | guid s=0.4621 预增 dir=positive | insider=None
```

**命中数(of 10):buyback 9 / guidance 6 / insider 1。**

合理性核对:
- buyback magnitude 随 cash_div 单调递增(600519 茅台 23.957 元/股 → 0.8 饱和;普通名 0.07–0.5),梯度 sane。
- guidance 类型/方向正确(预增→positive、score 随幅度增大)。
- insider 命中率低(1/10)是**正确的、非数据缺口**:大盘股近一年普遍无重要股东减持;`stk_holdertrade` 本身稀疏。600050 联通 4 笔减持净 1.226% → 0.587。
- 688981 全 None 经核验是**语义正确**:中芯国际历史分红记录 `cash_div` 全 0、forecast type=「不确定」、最近 DE 在 2025-07(超 1 年窗口)。解析器**没有 bug**。
- `management_change` 因 `stk_managers` 是 live、本环境无 TUSHARE_TOKEN,未在抽样中联网拉取;其逻辑已用 mock 记录在单测中覆盖(见 §6)。

---

## 6. 测试

`tests/test_script_fill.py` 新增 8 个 hermetic 单测(mock records,零网络),覆盖 4 个解析器的:命中、方向(预增 vs 预减)、窗口过滤、核心高管加权、None 边界。

```
pytest tests/test_script_fill.py -q  →  15 passed (7 既有 + 8 新增)
```

---

## 7. 分数漂移方向风险评估

- **只加 SlotDef、不填值 → 零漂移(已实测)**:4 个槽默认 `Inactive` → `_leaf_score` 返回 0 且被丢出聚合 → `eg=0, rd=0`。**仅把 SlotDef 加进图谱、不跑 fill,是 score-neutral 的**,这是本提案最关键的安全性质。
- **填值后的方向(已实测,000063-like 实测值)**:
  - `expectation_gap +0.49`(buyback+ 与 guidance+ 抬高)→ 抬高最终分。
  - `risk_discount +0.52`(insider 与 mgmt)→ 从最终分**减去**,压低最终分。方向全部正确。
- **量级风险(需审查关注)**:
  1. 这 4 个 `participates_in_score=true`,**与既有惰性 ma/product_order(participates=false)不同** —— 它们会真实进分。批量 fill 后,有分红/预增的股 eg 普遍上抬,有减持/高管离任的股 rd 上抬。`damp=True`(`/max(1,Σconf)`)抑制了多信号叠加的膨胀,但单股两个 risk 事件同时触发时 rd 可达 ~0.5,**属实质性扣分**,建议审查 calibration knee(insider `/3.0`、mgmt `/3.0`、buyback knee 1.0 元/股)。
  2. buyback 命中率高(9/10),若 knee 偏松会系统性抬高全市场 eg。当前 0.8·tanh(cash/1.0) 把普通分红压在 0.07–0.5,茅台类极端值才到 0.8,梯度可接受;但仍建议测分后看 eg 分布漂移。
  3. **建议:合并前先在小样本(如本 10 只 + 几十只有减持/预减的股)上跑一次 rescore-dry-run,观察 base_score / eg / rd 的分布漂移,再决定是否全量。**(本提案不跑 rescore。)
- **management_change live 依赖**:`stk_managers` 联网,默认关。开启会为每只股触发网络;批量场景建议预先离线拉一份缓存或保持关闭。

---

## 8. 改动文件清单(确切 diff 摘要)

1. **`mvp20/overlays.py`** —— `_Z3_COMPANY_DERIVED_SLOTS` 内新增 4 个 SlotDef:
   - L8.gov.litigation 之后:`L8.gov.insider_sell`、`L8.gov.management_change`(+ 一段注释)。
   - L9.company.product_order 之后:`L9.company.buyback_dividend`、`L9.company.earnings_guidance`(+ 一段注释)。
   - `ALL_DERIVED_SLOTS` 总数 111 → 115,无重复 dp_id(实测)。
2. **`scripts/script_fill.py`**:
   - 顶部新增 `import math` + Track-B 常量(forecast 方向表、guidance floor、核心高管表、1 年窗口)。
   - 新增 helper:`_to_float`、`_clip01`、`_ev`、`_cutoff`、`_records`。
   - 新增 4 个纯解析器:`parse_buyback_dividend` / `parse_earnings_guidance` / `parse_insider_sell` / `parse_management_change`。
   - 重写 `_catalysts(ts_code, *, include_management_change=False)`:fetch 4 endpoint(stk_managers 仅在开启时)→ 调解析器。
   - `extract(...)` 新增 `include_management_change=False` 参数并透传。
   - `write_to_overlay`:覆盖这 4 个 dp_id;填值时把 `Inactive→Known`、`active_weight 0→base_weight`、`missing_policy inactive_zero_weight→known`,并写入每条记录的 `direction`(guidance 预减时为 negative —— load-bearing)。仍只填 `data_status!='Known'` 的节点(不覆盖既有 codex/LLM fill)。
3. **`tests/test_script_fill.py`**:新增 4 个解析器的 import + 8 个 hermetic 单测。
4. **`docs/audit/track_b_field_extension_proposal.md`**:本文件。

> 注:本 worktree 分支基于较旧快照,`mvp20/sources/dockcase_cache.py` 等不在本树内;§2/§5 的打分核对与抽样均在 feature 分支(`feature/a-share-fixes`)的当前管线上运行验证。`overlays.py` 的 catalyst 段(329–331 行)与 feature 分支逐字一致,4 个 SlotDef 的插入位置在 feature 分支同样成立。
