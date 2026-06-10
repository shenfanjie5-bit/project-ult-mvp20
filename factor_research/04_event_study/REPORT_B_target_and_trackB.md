# Track B: Signed Impact Coefficient — Target Definition, LLM Extraction Spec, and Forward-Validation Protocol

**Status: DESIGNED; NOT YET VALIDATED.**
Track A (structured forecast events, `eventlib.py`) has a validated live candidate (forecast signed CAR ~+0.55%/−0.46% at h=1 decaying by h≈3). Track B (free-text news) has no historical archive — `realtime_current` is a hot-upsert snapshot, not a log. Everything in this document is forward-looking design. No Track B coefficient should be shown as validated until the forward-collection protocol below (Section 4) has run to completion and all three kill criteria pass.

---

## 1. Signed Impact Coefficient — Formal Target Definition

### 1.1 The Quantity Being Predicted

The coefficient predicts the **expected size-adjusted abnormal cumulative return (CAR)** over a forward horizon h, strictly PIT-clean:

```
abn_h(stock j, event e) = exp(CUM[e+h,j] - CUM[e,j]) - 1
                         - MV_decile_mean_fwd_h(j, e)
```

where:
- `e` = index of the last trading day on or before the headline's `publish_time`
  (A-share news can post intraday; per `eventlib.py` convention, the first tradeable
  reaction is open of `e+1`; weekend/after-hours posts roll to next trading day)
- `CUM` = cumulative log-return panel (computed in `eventlib.py::_xsec`)
- `MV_decile_mean_fwd_h(j,e)` = mean h-day forward return of stock j's MV-decile on day e
  (the "size" benchmark from `eventlib.py::abnormal_series(method="size")`)
- **h = 1 trading day** (see justification below)

### 1.2 Horizon Justification

Track A forecast shows CAR decaying rapidly: ~+0.55%/−0.46% at h=1, indistinguishable from noise by h≈3. Free-text EastMoney ticker-level headlines are typically lower-information than structured earnings guidance and reflect faster-moving intraday signals. Information half-life for headline-driven impact is therefore expected to be shorter still.

- **Primary display horizon: h=1** (close-to-close abnormal return, next trading day)
- Secondary tracking: h=3 (for slow-moving corporate action news posted after close)
- h=5 retained only for the kill-3 portfolio test to match Track A's pre-registered protocol

### 1.3 The Display Coefficient

Raw `E[abn_h]` is unbounded and noisy. The backend emits a display coefficient `coef` bounded to [−1, +1]:

```
coef = tanh(k · E[abn_1])     where k = 200
```

**Choice of k = 200, with reasoning:**
Track A's empirically strongest signal is ~0.5% absolute abnormal return.
`tanh(200 × 0.005) = tanh(1.0) ≈ 0.76` — places the strongest validated signal at ±0.76 on
the chip, visually meaningful without saturating. A 2% abnormal move (strong event, e.g.
regulatory investigation) maps to `tanh(200×0.02) = tanh(4) ≈ 1.0`. The range is well-used.

*Alternative once N_events_per_day > 20:* replace with cross-sectional rank normalization
(percentile within the day's event set) which is more robust to outliers.

### 1.4 Neutral Band, Sign → Color Mapping, and Current Bug Fix

**Neutral band:** |coef| < 0.05 (equivalent to |E[abn_1]| < 0.025% — economically zero).

**Sign → Color Mapping (A-share convention: red = rise/up, green = fall/down):**

| coef value   | label | chip color (CSS var)                                  |
|--------------|-------|-------------------------------------------------------|
| coef > +0.05 | 利好  | `color: var(--danger)` / `bg: var(--danger-bg)` RED   |
| coef < −0.05 | 利空  | `color: var(--success)` / `bg: var(--success-bg)` GREEN|
| |coef| ≤ 0.05 | 中性  | `color: var(--text-tertiary)` / grey bg               |

**Current bug in `EventTimeline.tsx` (lines 80–86):**

```typescript
// BUG — current code
const positive = c.coefficient >= 0   // 0 treated as positive → always RED
const color = positive ? 'var(--danger)' : 'var(--success)'
```

`coefficient = 0` (the hardcoded placeholder in `useRealMarketEvents.ts` line 48:
`coefficient: 0`) is rendered RED as "利好" for every headline. Corrected semantics:

```typescript
// CORRECTED
const positive = c.coefficient > 0.05
const negative = c.coefficient < -0.05
const color = positive ? 'var(--danger)' : negative ? 'var(--success)' : 'var(--text-tertiary)'
const bg    = positive ? 'var(--danger-bg)' : negative ? 'var(--success-bg)' : 'var(--surface-subtle)'
```

This change is in `FrontEnd/src/components/explanation/EventTimeline.tsx`. Flag for Track B integration sprint (frontend read-only in this session).

### 1.5 Exact Backend Emission Schema

`handle_market_events` (server.py ~line 578) currently returns events without a coefficient.
When Track B integrates, augment each per-stock event with:

```json
{
  "ts_code": "600519.SH",
  "dp_id": "L9.event.intraday_news",
  "title": "贵州茅台：拟推出第二期员工持股计划",
  "timestamp_iso": "2026-06-09T14:30:00",
  "url": "...",
  "source": "东方财富",
  "coefficient": 0.61,
  "coefficient_meta": {
    "horizon_days": 1,
    "formula": "tanh(200·E[abn_1])",
    "polarity": "利好",
    "strength": 2,
    "event_type": "equity_incentive",
    "model": "trackB_llm_haiku4.5",
    "validated": false
  }
}
```

`coefficient` is the display value in [−1, +1]. **`validated: false` must be set until Section 4
forward-validation protocol passes all three kill criteria.** Until then the field is for
development/UI testing only and must not be presented to users as a predictive signal.

---

## 2. Track B LLM Extraction Prompt

### 2.1 Event-Type Taxonomy (14 types)

| Code                | Chinese label    | Typical A-share headlines                    |
|---------------------|------------------|----------------------------------------------|
| `earnings_guidance` | 业绩预告/快报     | 预增、预减、扭亏、业绩快报                    |
| `order_contract`    | 订单/中标         | 中标、签署合同、战略合作、框架协议            |
| `restructuring`     | 资产重组/并购     | 收购、出售资产、控股、筹划重大事项            |
| `regulatory_penalty`| 监管处罚          | 立案调查、收到罚款、证监会警告                |
| `mgmt_change`       | 高管变动          | 董事长辞职、CEO被查、新任高管                 |
| `buyback_increase`  | 回购/增持         | 回购计划、大股东增持、实控人增持              |
| `shareholder_reduce`| 股东减持          | 拟减持、减持完毕、控股股东减持计划            |
| `litigation`        | 诉讼/仲裁         | 被起诉、仲裁裁决、索赔                        |
| `equity_incentive`  | 股权激励          | 员工持股计划、限制性股票授予                  |
| `lockup_expiry`     | 限售解禁          | 限售股解禁、首发股份上市流通                  |
| `dividend`          | 分红/送股         | 现金分红方案、送红股、利润分配预案            |
| `financing`         | 融资/定增         | 定向增发、可转债发行、配股                    |
| `macro_policy`      | 宏观/行业政策     | 国常会支持行业、新规发布、关税调整            |
| `other`             | 其他              | 不属于以上分类                               |

### 2.2 Output JSON Schema (Tool Use / Structured Output)

```json
{
  "name": "classify_news_impact",
  "description": "Classify a Chinese A-share news headline for event type, sentiment polarity, and impact strength.",
  "input_schema": {
    "type": "object",
    "properties": {
      "event_type": {
        "type": "string",
        "enum": ["earnings_guidance","order_contract","restructuring","regulatory_penalty",
                 "mgmt_change","buyback_increase","shareholder_reduce","litigation",
                 "equity_incentive","lockup_expiry","dividend","financing","macro_policy","other"],
        "description": "Primary event category from taxonomy."
      },
      "polarity": {
        "type": "string",
        "enum": ["利好","利空","中性"],
        "description": "Expected directional impact on the stock price."
      },
      "strength": {
        "type": "integer",
        "minimum": 0,
        "maximum": 3,
        "description": "Magnitude: 0=无/不明, 1=轻微, 2=中等, 3=重大."
      },
      "rationale": {
        "type": "string",
        "description": "One sentence ≤40 chars justifying classification, in Chinese."
      }
    },
    "required": ["event_type","polarity","strength","rationale"]
  }
}
```

### 2.3 System Prompt

```
你是A股新闻事件分类专家。给定一条中文新闻标题（和可选正文片段），请判断该新闻
对涉及股票的短期股价（1个交易日）的影响。

规则：
1. polarity（极性）：仅考虑对该股票的直接影响；宏观利好但个股无直接联系 → 中性。
2. strength（强度）：
   0 = 无法判断或无实质内容（如一般性战略声明）
   1 = 边际影响（如小额常规合同、轻微技术性调整）
   2 = 中等影响（如大额订单、小额处罚、一般分红）
   3 = 重大影响（如被立案调查、重大资产重组、业绩大幅预增/预减）
3. event_type：选最贴近一个，不要根据标题未提及的信息推测。
4. 不受当前市场情绪影响；严格基于新闻内容本身。
5. 输出必须调用工具 classify_news_impact，不得输出其他文字。

示例：

输入：股票：600519.SH  标题：贵州茅台：2025年拟每股分红359元，现金分红率约75%
输出：{"event_type":"dividend","polarity":"利好","strength":2,"rationale":"大额现金分红利好股东回报"}

输入：股票：002415.SZ  标题：海康威视：收到证监会立案通知书
输出：{"event_type":"regulatory_penalty","polarity":"利空","strength":3,"rationale":"立案调查属重大利空事件"}

输入：股票：300750.SZ  标题：宁德时代：控股股东拟减持不超过1%股份
输出：{"event_type":"shareholder_reduce","polarity":"利空","strength":1,"rationale":"小额减持对流通有轻微压力"}

输入：股票：002049.SZ  标题：紫光股份：子公司中标政府专网项目，合同金额0.8亿元
输出：{"event_type":"order_contract","polarity":"利好","strength":1,"rationale":"合同金额相对营收较小，边际正面"}

输入：股票：601318.SH  标题：中国平安：与阿里巴巴签署战略合作协议
输出：{"event_type":"order_contract","polarity":"中性","strength":0,"rationale":"无实质业绩承诺，影响不明"}

输入：股票：000001.SZ  标题：限售股解禁：平安银行4.2亿股将于下周一上市流通
输出：{"event_type":"lockup_expiry","polarity":"利空","strength":2,"rationale":"大额解禁构成短期抛压"}
```

### 2.4 User Prompt Template

```
股票：{ts_code}
标题：{title}
{body_snippet}
请分类。
```

Where `{body_snippet}` is either omitted (when no body available) or:
`正文片段（前200字）：{body[:200]}`

Currently `realtime_current` stores only `title`/`url`/`source`/`time` in `top_headlines` dicts —
no body text. The prompt works headline-only; body can be added later via async URL fetch.

### 2.5 API Call Pattern (Python, with prompt caching)

```python
import anthropic

client = anthropic.Anthropic()

SYSTEM_WITH_EXAMPLES = "..."  # Section 2.3 full text

TOOL_DEF = {
    "name": "classify_news_impact",
    "description": "Classify a Chinese A-share news headline...",
    "input_schema": { ... }  # Section 2.2 schema
}

def classify_headline(ts_code: str, title: str) -> dict:
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": SYSTEM_WITH_EXAMPLES,
                "cache_control": {"type": "ephemeral"}  # cache system+few-shots
            }
        ],
        tools=[TOOL_DEF],
        tool_choice={"type": "tool", "name": "classify_news_impact"},
        messages=[
            {"role": "user", "content": f"股票：{ts_code}\n标题：{title}\n请分类。"}
        ],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("no tool_use block in response")
```

### 2.6 Polarity × Strength → Prior Coefficient

Before any forward validation, the prior display coefficient is rule-based:

```python
import numpy as np

POLARITY_SIGN   = {"利好": +1, "利空": -1, "中性": 0}
STRENGTH_ABN    = {0: 0.000, 1: 0.0010, 2: 0.0035, 3: 0.0070}  # E[|abn_1|] prior

def prior_coefficient(polarity: str, strength: int) -> float:
    sign = POLARITY_SIGN.get(polarity, 0)
    abn  = STRENGTH_ABN.get(strength, 0.0)
    return float(np.tanh(200 * sign * abn))
```

Resulting prior coefficients:

| Polarity | Strength | coef   | display |
|----------|----------|--------|---------|
| 利好     | 3        | +0.60  | RED     |
| 利好     | 2        | +0.62  | RED     |
| 利好     | 1        | +0.20  | RED     |
| 中性     | any      |  0.00  | GREY    |
| 利空     | 1        | −0.20  | GREEN   |
| 利空     | 2        | −0.62  | GREEN   |
| 利空     | 3        | −0.60  | GREEN   |

Strength=3 prior (0.70% expected abnormal) is intentionally shrunk vs Track A's +0.55% observed
— these priors update toward the empirical posterior once forward data accrues.

### 2.7 Model Recommendation: Haiku 4.5

**Model: `claude-haiku-4-5-20251001`**

Rationale:
- Fixed 14-class taxonomy + 4-field structured output: no complex multi-step reasoning needed
- Tool-use with `tool_choice: {type:"tool", name:...}` forces valid enum output
- Haiku 4.5 handles Chinese text well; Sonnet 4.6 would be 3–4× more expensive for no gain
- Lowest latency → nightly batch classification finishes in minutes, not hours

**Cost estimate:**
- Per headline: ~200 input tokens (system prompt cached) + ~60 output tokens
- Haiku 4.5: input ~$0.80/MTok, output ~$4.00/MTok
- With prompt caching (system reused): ~60 output tokens ≈ **$0.00024/headline**
- At 1,000 headlines/day: **~$0.24/day** (~$87/year) — negligible
- Cold (no cache): ~200 in + 60 out ≈ $0.0004/headline → $0.40/1K

Use `cache_control: {"type": "ephemeral"}` on the system prompt block to eliminate >90%
of input costs on any batch run.

---

## 3. Cheap Baseline (for Measuring LLM Marginal Value)

### 3.1 Keyword/Lexicon Baseline

```python
POS_WORDS = [
    "中标","增持","回购","分红","扭亏","预增","业绩超预期","战略合作",
    "新签合同","获批","涨价","提价","大客户","量产","重组","并购完成",
    "股权激励","增资","扩产","政策支持","上调评级","首次盈利","获得专利",
]
NEG_WORDS = [
    "立案","被查","处罚","罚款","亏损","预减","首亏","续亏","减持",
    "诉讼","仲裁","股权被冻结","债务违约","被ST","暂停","停产","召回",
    "降价","竞争加剧","大额解禁","高管辞职","下调评级","信用评级下调",
]

def lexicon_score(title: str) -> float:
    pos = sum(1 for kw in POS_WORDS if kw in title)
    neg = sum(1 for kw in NEG_WORDS if kw in title)
    return float(np.tanh(50 * (pos - neg) / 100.0))
```

Cost: zero. Speed: microseconds. Expected sign accuracy: ~55–58% (literature for Chinese
financial news keyword lexicons).

### 3.2 FinBERT-Chinese Off-the-Shelf

`yiyanghkust/finbert-tone` or `snunlp/KR-FinBert-SC` (Chinese) provide a 3-class probability
vector (positive/negative/neutral). Map to coefficient via:
`coef = tanh(200 × (p_pos − p_neg) × 0.005)` or similar calibration.
Cost: local GPU inference, zero API cost.

**Measurement plan:** run all three methods (lexicon, FinBERT, Haiku-LLM) on the same
collected-forward event set. Compute per-method sign accuracy and mean abn CAR by predicted
polarity bucket. The LLM is justified if: (a) sign accuracy is meaningfully higher (>2pp), or
(b) strength=3 subset shows sharper CAR discrimination.

---

## 4. Forward-Validation Protocol

### 4.1 Why Forward-Only

`runtime/hot.sqlite::realtime_current` is a hot-upsert snapshot: each row holds only the
**most recent** value for `(ts_code, dp_id)`. There is no append log, no historical archive
of past headlines. Therefore:

- Track B CANNOT be backtested on existing data.
- All validation must be collected-forward from the date collection begins.
- No Track B coefficient should be presented as validated before the protocol completes.

### 4.2 Archive Table Schema (append-only)

New file: `runtime/trackB_archive.sqlite` (separate from hot.sqlite).

```sql
CREATE TABLE IF NOT EXISTS trackB_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at     TEXT NOT NULL,       -- ISO: when this row was written
    publish_time     TEXT NOT NULL,       -- original L9.event.intraday_news publish_time
    ts_code          TEXT NOT NULL,
    title            TEXT NOT NULL,
    title_hash       TEXT NOT NULL,       -- sha256(title)[:16] for dedup
    source           TEXT,
    url              TEXT,

    -- LLM classification (NULL until nightly classify job runs)
    llm_event_type   TEXT,
    llm_polarity     TEXT,                -- 利好/利空/中性
    llm_strength     INTEGER,             -- 0–3
    llm_rationale    TEXT,
    prior_coef       REAL,               -- tanh(200·prior_abn) at classify time

    -- Forward outcome (NULL until h trading days after entry)
    entry_trading_day TEXT,              -- YYYYMMDD: last cal day <= publish_time
    abn_h1           REAL,              -- size-adj abnormal return at h=1
    abn_h3           REAL,              -- h=3
    abn_h5           REAL,              -- h=5 (for kill-3 portfolio test)
    outcome_filled_at TEXT,

    -- Validity flags
    is_cross_echo    INTEGER DEFAULT 0,  -- 1 = same title echoed for >=2 ts_codes
    excluded         INTEGER DEFAULT 0   -- 1 = entry_day outside price panel
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_trackB_ts_title
    ON trackB_events(ts_code, title_hash);

CREATE INDEX IF NOT EXISTS ix_trackB_entry_day
    ON trackB_events(entry_trading_day);
```

**Cross-echo dedup rule:** if the same `title_hash` appears for ≥2 distinct `ts_code` values
within a 30-minute collection window, set `is_cross_echo=1` on ALL rows for that title.
These rows are excluded from the validation event set (they are market-wide news echoed by the
vendor, not stock-specific signals).

### 4.3 Collection Procedure

1. **Daily collection job** (run at 15:30 CST, market close):
   Read all `L9.event.intraday_news` rows from `hot.sqlite::realtime_current`,
   extract `top_headlines` list, upsert into `trackB_archive` via `UNIQUE INDEX`.

2. **Nightly LLM classification job** (run at 22:00 CST):
   Fetch all rows where `llm_polarity IS NULL AND excluded=0`.
   Batch 50 headlines at a time. Call Haiku 4.5. Write back `llm_*` and `prior_coef`.

3. **Outcome fill job** (run 3 trading days after collection):
   For each row with `entry_trading_day IS NOT NULL AND abn_h1 IS NULL`:
   Compute `abnormal_series` via `eventlib.py` and write `abn_h1/h3/h5`.

### 4.4 Expected Volume and Sample-Size Estimate

**Expected live volume:**
- EastMoney covers ~1,600 A-share stocks in the panel universe
- ~5–10% have active per-stock news on any trading day → 80–160 headlines/day
- After dedup (`is_cross_echo=1` removed) and strength≥1 filter: ~50 classifiable signed events/day
- At 22 trading days/month: **~1,100 signed events/month** (conservative)

**Power for sign-accuracy test (KILL #2):**
- Target: detect 53% sign accuracy (small real edge) at 80% power, one-sided α=0.05
- Required N ≈ 1,500 events (standard proportion test, p0=0.50, p1=0.53)
- At 1,100/month: **~6–7 weeks** to reach N=1,500

If the true effect is closer to Track A's performance (sign accuracy ~55–57%),
required N drops to 400–600 → **3–4 weeks** to significance.

**Recommended minimum collection period: 6 weeks** (conservative; accounts for earnings
seasonality, regime shifts, and tail-event weeks).

### 4.5 Pre-Registered Kill Criteria (Track B)

Same structure as Track A's three kills, applied to the collected-forward event set:

**KILL #1 — Monotonic + Significant @ h=1:**
- Mean(abn_h1 | llm_polarity="利好") > 0, 95% bootstrap CI excluding 0
- Mean(abn_h1 | llm_polarity="利空") < 0, 95% bootstrap CI excluding 0
- Spread (positive minus negative bucket mean) > 0.30% abnormal return

**KILL #2 — OOS Sign Accuracy (95% CI lower bound > 0.50):**
- Predict sign(abn_h1) using sign(prior_coef)
- Restricted to events with llm_strength ≥ 1 (exclude strength=0 "无法判断")
- Binomial CI lower bound > 0.50
- Minimum N = 300 per polarity bucket

**KILL #3 — Portfolio Majority:**
- Long-only (利好 events), net of 25 bps round-trip cost, by weekly cohort
- Win rate > 50% across ≥ 6 non-overlapping weekly cohorts

**Failure mode:** if any kill fails after 8 weeks of data (N > 2,000 events), Track B
coefficient is not displayed — the `coefficient` field is either omitted or set to `null`
with a grey "N/A" chip. **Prior coefficients must never be displayed as validated signals.**

### 4.6 Timeline to Significance

| Milestone | Days from collection start |
|---|---|
| Collection starts | Day 0 |
| First outcome fill available (h=1) | Day 2 |
| Early-signal sanity check (N~200) | Week 2 |
| Formal kill test #1 and #2 (N~1,500) | Week 6–7 |
| Kill test #3 (6 weekly cohorts complete) | Week 6 |
| Decision: validate coefficient or kill Track B | Week 7 |
| If passed: transition prior_coef to empirical posterior | Month 3 |

If collection starts 2026-06-10:
- Earliest credible kill-test date: **~2026-07-25**
- Empirical posterior calibration: **~2026-09-10**

---

## 5. Summary

### Target formula

```
coef = tanh(200 · E[abn_1(size)])
```

Prior (before validation): `coef = tanh(200 · POLARITY_SIGN[polarity] · STRENGTH_ABN[strength])`

### Sign → Color fix (EventTimeline.tsx)

Current bug: `coefficient >= 0` always true for placeholder 0 → wrongly RED.
Fix: threshold at ±0.05; neutral band = grey chip labeled "中性".

### Track B extraction

Model: `claude-haiku-4-5-20251001`, tool-use, system prompt cached.
Output: `{event_type, polarity, strength(0–3), rationale}`.
Cost: ~$0.24/day at 1,000 headlines/day.
Baseline to benchmark against: lexicon score (zero cost) and FinBERT-Chinese.

### Forward-validation timeline

6 weeks collection → N~1,500 signed events → kill tests #1/2/3.
Earliest validation decision: ~2026-07-25.
Until then: `"validated": false` on every emitted coefficient.
