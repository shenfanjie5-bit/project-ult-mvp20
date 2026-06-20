// Top conclusion banner. A-share 5d absolute upside probability comes from
// backend signal_up_5d. The separate signal_5d block is relative win-rate
// versus the same-day liquid median. The older derived preview is retained
// only as a non-model fallback preview.

import { AlertTriangle, ArrowUpRight, BellPlus, FileSearch, GitBranch, TrendingUp } from 'lucide-react'
import type {
  Signal5dBlock,
  SignalUp5dBlock,
  StockModeKey,
  TradingSignal,
} from '../../../api/hooks/useStockScore'
import type { StockOverlayValue } from '../../../api/hooks/useStockOverlay'
import type { DerivedSignal, SignalGrade } from '../../../types/derived'
import { TagBadge } from '../../../components/data/TagBadge'
import { ModeBadge } from './ModeBadge'

interface StockHeaderProps {
  name: string
  tsCode: string
  market: string
  industryIds: string[]
  industryNameCn?: string
  pool?: string
  role?: string
  signal: DerivedSignal
  signalUp5d?: SignalUp5dBlock | null
  signal5d?: Signal5dBlock | null
  onOpenChain: () => void
  /** A3 mode classification (derived server-side). Optional — when absent
   * the header just hides the chip. */
  mode?: StockModeKey | null
  modeDisplay?: string | null
  modeConfidence?: number | null
  modeRationale?: string | null
  tradingSignal?: TradingSignal | null
  tradingMeaning?: string | null
  scoreLoading?: boolean
  /** Realtime overlay block keyed by dp_id — used for the options-consistency
   * widget. We read three dp_ids: `L6.priced.iv`, `L7.trade.iv`,
   * `L7.trade.options_cp`. When the prop is missing or none of the three slots
   * are `Known`, the widget renders the "no data" state instead of fabricating
   * a verdict. */
  realtime?: Record<string, StockOverlayValue> | null
}

/** Shape of the JSON payload stored under `L6.priced.iv` /
 * `L7.trade.iv`.value. We only read fields we actually use. */
interface OptionsIvPayload {
  atm_iv?: number | null
  regime?: 'high' | 'low' | 'normal' | string | null
}

interface OptionsCpPayload {
  cp_ratio?: number | null
  oi_ratio?: number | null
  call_volume?: number | null
  put_volume?: number | null
}

type ConsistencyTone = 'positive' | 'negative' | 'neutral' | 'warning' | 'muted'

interface ConsistencyVerdict {
  label: string
  tone: ConsistencyTone
}

const CONSISTENCY_COLORS: Record<ConsistencyTone, string> = {
  positive: 'var(--success)',
  negative: 'var(--danger)',
  warning: 'var(--warning)',
  neutral: 'var(--text-secondary)',
  muted: 'var(--text-tertiary)',
}

function isAShareTsCode(tsCode: string): boolean {
  return (
    tsCode.endsWith('.SH') ||
    tsCode.endsWith('.SZ') ||
    tsCode.endsWith('.BJ')
  )
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function pickNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function pickString(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

/** Combine A3 mode + trading signal + cp_ratio into a short consistency
 * verdict. Intentionally conservative — when inputs are partially missing we
 * fall back to "中性" rather than fabricating direction. */
function computeOptionsConsistency(
  mode: StockModeKey | null | undefined,
  tradingSignal: TradingSignal | null | undefined,
  cpRatio: number | null,
): ConsistencyVerdict {
  if (cpRatio == null) {
    return { label: '数据不足', tone: 'muted' }
  }
  // cp_ratio = put_volume / call_volume. <0.5 = call-heavy (bullish skew);
  // >1.0 = put-heavy (bearish skew); in between = neutral.
  const callHeavy = cpRatio < 0.5
  const putHeavy = cpRatio > 1.0
  const signal = tradingSignal ?? null
  if (signal === 'BUY') {
    if (callHeavy) return { label: '一致看多', tone: 'positive' }
    if (putHeavy) return { label: '信号矛盾', tone: 'negative' }
    return { label: '中性', tone: 'neutral' }
  }
  if (signal === 'AVOID') {
    if (putHeavy) return { label: '一致看空', tone: 'muted' }
    if (callHeavy) return { label: '信号矛盾', tone: 'negative' }
    return { label: '中性', tone: 'neutral' }
  }
  // WATCH / HOLD / null
  if (callHeavy) return { label: '略偏多', tone: 'positive' }
  if (putHeavy) return { label: '略偏空', tone: 'warning' }
  void mode
  return { label: '中性', tone: 'neutral' }
}

const GRADE_TONE: Record<SignalGrade, { color: string; bg: string; border: string }> = {
  S: { color: 'var(--danger)', bg: 'var(--danger-bg)', border: 'var(--danger)' },
  A: { color: 'var(--danger)', bg: 'var(--danger-bg)', border: 'var(--danger)' },
  B: { color: 'var(--warning)', bg: 'var(--warning-bg)', border: 'var(--warning)' },
  C: { color: 'var(--info)', bg: 'var(--info-bg)', border: 'var(--info)' },
  D: { color: 'var(--success)', bg: 'var(--success-bg)', border: 'var(--success)' },
}

function inferMarket(tsCode: string): string {
  if (tsCode.endsWith('.SH') || tsCode.endsWith('.SZ') || tsCode.endsWith('.BJ')) {
    return 'A 股'
  }
  if (tsCode.endsWith('.HK')) {
    return '港股'
  }
  if (tsCode.endsWith('.US')) {
    return '美股'
  }
  return '未知市场'
}

export function StockHeader({
  name,
  tsCode,
  market,
  industryIds,
  industryNameCn,
  pool,
  role,
  signal,
  signalUp5d,
  signal5d,
  onOpenChain,
  mode,
  modeDisplay,
  modeConfidence,
  modeRationale,
  tradingSignal,
  tradingMeaning,
  scoreLoading,
  realtime,
}: StockHeaderProps) {
  const resolvedMarket = market || inferMarket(tsCode)
  const signalUp5dProbability =
    isAShareTsCode(tsCode) &&
    signalUp5d?.available !== false &&
    typeof signalUp5d?.probability === 'number' &&
    Number.isFinite(signalUp5d.probability)
      ? signalUp5d.probability
      : null
  const usesSignalUp5d = signalUp5dProbability !== null
  const signal5dProbability =
    isAShareTsCode(tsCode) &&
    signal5d?.available !== false &&
    typeof signal5d?.probability === 'number' &&
    Number.isFinite(signal5d.probability)
      ? signal5d.probability
      : null
  const usesSignal5d = signal5dProbability !== null
  const displayProbability = usesSignalUp5d ? signalUp5dProbability : signal.upside_probability
  const probabilityPercent = Math.round(displayProbability * 10000) / 100
  const relativePercent = usesSignal5d
    ? Math.round(signal5dProbability * 10000) / 100
    : null
  const displayGrade =
    usesSignalUp5d && signalUp5d?.signal_grade
      ? signalUp5d.signal_grade
      : usesSignal5d && signal5d?.signal_grade
        ? signal5d.signal_grade
        : signal.signal_grade
  const displayStrength =
    usesSignalUp5d && signalUp5d?.signal_strength
      ? signalUp5d.signal_strength
      : usesSignal5d && signal5d?.signal_strength
        ? signal5d.signal_strength
        : signal.signal_strength
  const displayDirection =
    usesSignalUp5d && signalUp5d?.direction
      ? signalUp5d.direction
      : usesSignal5d && signal5d?.direction
        ? signal5d.direction
        : signal.direction
  const tone = GRADE_TONE[displayGrade]
  const drivers = (
    usesSignalUp5d && signalUp5d?.drivers?.length
      ? signalUp5d.drivers
      : usesSignal5d && signal5d?.drivers?.length
        ? signal5d.drivers
        : signal.primary_drivers
  ).slice(0, 3)
  const risks = (
    usesSignalUp5d && signalUp5d?.risks?.length
      ? signalUp5d.risks
      : usesSignal5d && signal5d?.risks?.length
        ? signal5d.risks
        : signal.primary_risks
  ).slice(0, 2)
  const signalUp5dStatus = usesSignalUp5d
    ? signalUp5d?.stale || signalUp5d?.validated === false
      ? '过期预览，不作为有效信号'
      : 'signal_up_5d 后端信号'
    : '派生预览，不是上涨概率模型'
  const signal5dStatus = usesSignal5d
    ? signal5d?.stale || signal5d?.validated === false
      ? '过期预览，不作为有效信号'
      : 'signal_5d 后端信号'
    : 'relative signal unavailable'
  const probabilityTitle = usesSignalUp5d ? '5 日上涨概率' : '派生预览概率'
  const probabilitySubtitle = usesSignalUp5d ? 'absolute P(5d return > 0)' : 'derived preview'
  const dataQualityLabel = usesSignalUp5d
    ? [
        'signal_up_5d',
        signalUp5d?.probability_source ?? null,
        typeof signalUp5d?.feature_coverage === 'number'
          ? `覆盖 ${(signalUp5d.feature_coverage * 100).toFixed(0)}%`
          : null,
      ].filter(Boolean).join(' · ')
    : usesSignal5d
      ? [
          'signal_5d',
          signal5d?.probability_source ?? null,
          typeof signal5d?.feature_coverage === 'number'
            ? `覆盖 ${(signal5d.feature_coverage * 100).toFixed(0)}%`
            : null,
        ].filter(Boolean).join(' · ')
      : signal.data_quality

  /* ---------------- options-consistency widget (real data) ---------------- */
  const isAShare = isAShareTsCode(tsCode)
  const ivSlot = realtime?.['L6.priced.iv']
  const regimeSlot = realtime?.['L7.trade.iv']
  const cpSlot = realtime?.['L7.trade.options_cp']

  const ivPayload: OptionsIvPayload | null = isPlainObject(ivSlot?.value)
    ? (ivSlot!.value as OptionsIvPayload)
    : null
  const regimePayload: OptionsIvPayload | null = isPlainObject(regimeSlot?.value)
    ? (regimeSlot!.value as OptionsIvPayload)
    : null
  const cpPayload: OptionsCpPayload | null = isPlainObject(cpSlot?.value)
    ? (cpSlot!.value as OptionsCpPayload)
    : null

  const atmIv = pickNumber(ivPayload?.atm_iv)
  const regime = pickString(regimePayload?.regime)
  const cpRatio = pickNumber(cpPayload?.cp_ratio)

  // "Active" = at least one of the three options slots reported Known data.
  // Inactive / missing slots all collapse to "no data".
  const optionsKnown =
    ivSlot?.data_status === 'Known' ||
    regimeSlot?.data_status === 'Known' ||
    cpSlot?.data_status === 'Known'

  const consistencyVerdict = computeOptionsConsistency(mode, tradingSignal, cpRatio)
  const consistencyColor = CONSISTENCY_COLORS[consistencyVerdict.tone]

  const narrative = usesSignalUp5d
    ? `未来 5 个交易日，系统判断 ${name} 上涨概率为 ${probabilityPercent.toFixed(2)}%，` +
      `信号等级为 ${displayGrade}（${displayStrength}信号 · ${displayDirection}）。` +
      (drivers.length > 0
        ? `主要由 ${drivers.map((d) => d.factor_label).join('、')} 驱动。`
        : '') +
      (risks.length > 0
        ? `需要关注 ${risks.map((r) => r.factor_label).join(' 与 ')}。`
        : '') +
      `（${signalUp5dStatus}）` +
      (usesSignal5d && relativePercent !== null
        ? ` 另：5 日相对胜率为 ${relativePercent.toFixed(2)}%（${signal5dStatus}）。`
        : '')
    : `未来 5 个交易日，系统给出 ${name} 派生预览概率为 ${probabilityPercent.toFixed(2)}%，` +
      `信号等级为 ${displayGrade}（${displayStrength}信号 · ${displayDirection}）。` +
      (drivers.length > 0
        ? `主要由 ${drivers.map((d) => d.factor_label).join('、')} 驱动。`
        : '') +
      (risks.length > 0
        ? `需要关注 ${risks.map((r) => r.factor_label).join(' 与 ')}。`
        : '') +
      '（派生预览，不是上涨概率模型）' +
      (usesSignal5d && relativePercent !== null
        ? ` 另：5 日相对胜率为 ${relativePercent.toFixed(2)}%（${signal5dStatus}）。`
        : '')

  return (
    <section className="surface-card relative flex min-w-0 flex-col gap-5 p-4 sm:p-6">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-1 rounded-t-xl"
        style={{ background: tone.color }}
      />

      <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex min-w-0 flex-wrap items-baseline gap-3">
            <h1 className="break-words text-[24px] font-semibold leading-[1.2] text-[var(--text-primary)]">
              {name}
            </h1>
            <span className="font-mono text-[13px] text-[var(--text-secondary)]">{tsCode}</span>
            <span className="rounded-md bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
              {resolvedMarket}
            </span>
            {role ? (
              <span className="rounded-md bg-[var(--info-bg)] px-2 py-0.5 text-[11px] text-[var(--info)]">
                role · {role}
              </span>
            ) : null}
            {pool ? (
              <span className="rounded-md bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
                pool · {pool}
              </span>
            ) : null}
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {industryNameCn ? <TagBadge label={industryNameCn} /> : null}
            {industryIds.map((id) => (
              <TagBadge key={id} label={id} />
            ))}
            {scoreLoading || mode || tradingSignal ? (
              <ModeBadge
                mode={mode ?? null}
                modeDisplay={modeDisplay ?? null}
                modeConfidence={modeConfidence ?? null}
                modeRationale={modeRationale ?? null}
                signal={tradingSignal ?? null}
                signalMeaning={tradingMeaning ?? null}
                loading={scoreLoading}
              />
            ) : null}
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-2">
          <span
            className="max-w-full rounded-full border px-3 py-1 text-[10px] font-mono uppercase tracking-wide text-[var(--text-tertiary)] break-words"
            style={{ borderColor: 'var(--border-light)' }}
            title={
              usesSignalUp5d
                ? (signalUp5d?.probability_semantics ?? 'signal_up_5d backend probability')
                : usesSignal5d
                  ? (signal5d?.probability_semantics ?? 'signal_5d backend relative probability')
                  : '所有数值由 industry_graph priors 派生，未接入上涨概率模型'
            }
          >
            {signalUp5dStatus}
          </span>
        </div>
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-2 xl:grid-cols-[1.1fr_1fr_1fr_1fr]">
        <div
          className="min-w-0 rounded-xl border p-4"
          style={{ borderColor: tone.border, background: tone.bg }}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide" style={{ color: tone.color }}>
              {probabilityTitle}
            </span>
            <span className="text-[11px] text-[var(--text-tertiary)]">{probabilitySubtitle}</span>
          </div>
          <div className="mt-2 flex min-w-0 items-baseline gap-3">
            <span
              className="text-[40px] font-semibold leading-none"
              style={{ color: tone.color }}
            >
              {probabilityPercent.toFixed(2)}%
            </span>
            <TrendingUp className="h-5 w-5" style={{ color: tone.color }} aria-hidden="true" />
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/60">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max(2, Math.min(100, probabilityPercent))}%`,
                background: tone.color,
              }}
            />
          </div>
        </div>

        <div className="min-w-0 rounded-xl border border-[var(--border-light)] bg-white p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
              5 日相对胜率
            </span>
            <span className="text-[11px] text-[var(--text-tertiary)]">beat liquid median</span>
          </div>
          {usesSignal5d && relativePercent !== null ? (
            <>
              <div className="mt-2 flex min-w-0 items-baseline gap-3">
                <span className="text-[32px] font-semibold leading-none text-[var(--text-primary)]">
                  {relativePercent.toFixed(2)}%
                </span>
              </div>
              <p className="mt-3 break-words text-[12px] leading-5 text-[var(--text-secondary)]">
                {signal5d?.stale || signal5d?.validated === false
                  ? signal5d.reason ?? '过期预览，不作为有效信号'
                  : '跑赢同日流动性股票中位数概率。'}
              </p>
            </>
          ) : (
            <>
              <div className="mt-2 flex min-w-0 items-baseline gap-3">
                <span className="text-[32px] font-semibold leading-none text-[var(--text-tertiary)]">
                  --
                </span>
              </div>
              <p className="mt-3 break-words text-[12px] leading-5 text-[var(--text-secondary)]">
                signal_5d 暂无可展示的相对胜率。
              </p>
            </>
          )}
        </div>

        <div className="min-w-0 rounded-xl border border-[var(--border-light)] bg-white p-4">
          <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
            信号等级
          </span>
          <div className="mt-2 flex min-w-0 items-baseline gap-3">
            <span
              className="text-[40px] font-semibold leading-none"
              style={{ color: tone.color }}
            >
              {displayGrade}
            </span>
            <span className="text-[12px] text-[var(--text-secondary)]">
              {displayStrength} · {displayDirection}
            </span>
          </div>
          <div className="mt-3 break-words text-[12px] text-[var(--text-secondary)]">
            数据来源 · <span className="font-mono text-[11px] break-all">{dataQualityLabel}</span>
          </div>
        </div>

        <div className="min-w-0 rounded-xl border border-[var(--border-light)] bg-white p-4">
          <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
            期权一致性
          </span>
          {isAShare ? (
            <>
              <div className="mt-2 flex min-w-0 items-baseline gap-3">
                <span
                  className="text-[28px] font-semibold leading-none"
                  style={{ color: CONSISTENCY_COLORS.muted }}
                >
                  N/A
                </span>
              </div>
              <p className="mt-3 break-words text-[12px] leading-5 text-[var(--text-secondary)]">
                A 股个股期权市场未覆盖（Futu fetcher 仅拉取 HK / US 期权链）。
              </p>
            </>
          ) : optionsKnown ? (
            <>
              <div className="mt-2 flex min-w-0 items-baseline gap-3">
                <span
                  className="text-[28px] font-semibold leading-none"
                  style={{ color: consistencyColor }}
                >
                  {consistencyVerdict.label}
                </span>
              </div>
              <p className="mt-3 break-words text-[12px] leading-5 text-[var(--text-secondary)]">
                {atmIv != null ? <>ATM IV {atmIv.toFixed(1)}%</> : <>ATM IV —</>}
                {regime ? <> · regime {regime}</> : null}
                {cpRatio != null ? <> · C/P {cpRatio.toFixed(2)}</> : null}
                <> · 数据源 Futu OpenD</>
              </p>
            </>
          ) : (
            <>
              <div className="mt-2 flex min-w-0 items-baseline gap-3">
                <span
                  className="text-[28px] font-semibold leading-none"
                  style={{ color: CONSISTENCY_COLORS.muted }}
                >
                  无数据
                </span>
              </div>
              <p className="mt-3 break-words text-[12px] leading-5 text-[var(--text-secondary)]">
                Futu OpenD 该标的期权链未返回数据（OpenD 未启动或行情会话无期权权限）。
              </p>
            </>
          )}
        </div>
      </div>

      <p className="min-w-0 break-words rounded-lg border border-dashed border-[var(--border-medium)] bg-white/60 px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]">
        {narrative}
      </p>

      <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
        <div className="grid min-w-0 flex-1 gap-3 md:grid-cols-2">
          <div className="min-w-0 rounded-lg border border-[var(--danger)] bg-[var(--danger-bg)] px-3 py-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: 'var(--danger)' }}>
              <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
              主要驱动 · top {drivers.length}
            </div>
            <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
              {drivers.length === 0 ? (
                <span className="text-[12px] text-[var(--text-tertiary)]">无正向驱动</span>
              ) : (
                drivers.map((d) => (
                  <span
                    key={d.factor_id}
                    className="max-w-full break-words rounded-md bg-white/80 px-2 py-0.5 text-[11px] font-medium"
                    style={{ color: 'var(--danger)' }}
                    title={`β ${d.contribution.toFixed(2)} · ${d.source_node_id}`}
                  >
                    {d.factor_label} · +{d.contribution.toFixed(2)}
                  </span>
                ))
              )}
            </div>
          </div>

          <div className="min-w-0 rounded-lg border border-[var(--success)] bg-[var(--success-bg)] px-3 py-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: 'var(--success)' }}>
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              主要风险 · top {risks.length}
            </div>
            <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
              {risks.length === 0 ? (
                <span className="text-[12px] text-[var(--text-tertiary)]">无负向风险</span>
              ) : (
                risks.map((r) => (
                  <span
                    key={r.factor_id}
                    className="max-w-full break-words rounded-md bg-white/80 px-2 py-0.5 text-[11px] font-medium"
                    style={{ color: 'var(--success)' }}
                    title={`β ${r.contribution.toFixed(2)} · ${r.source_node_id}`}
                  >
                    {r.factor_label} · {r.contribution.toFixed(2)}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onOpenChain}
            className="inline-flex items-center gap-2 rounded-md border border-[var(--info)] bg-[var(--info-bg)] px-3 py-2 text-[12px] font-medium text-[var(--info)] transition hover:bg-white"
          >
            <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
            查看解释链
          </button>
          <button
            type="button"
            disabled
            className="inline-flex cursor-not-allowed items-center gap-2 rounded-md border border-[var(--border-light)] px-3 py-2 text-[12px] font-medium text-[var(--text-tertiary)]"
            title="alerts 模块尚未接入"
          >
            <BellPlus className="h-3.5 w-3.5" aria-hidden="true" />
            加入预警
          </button>
          <button
            type="button"
            disabled
            className="inline-flex cursor-not-allowed items-center gap-2 rounded-md border border-[var(--border-light)] px-3 py-2 text-[12px] font-medium text-[var(--text-tertiary)]"
            title="reasoner-runtime 未接入"
          >
            <FileSearch className="h-3.5 w-3.5" aria-hidden="true" />
            生成深度分析
          </button>
        </div>
      </div>
    </section>
  )
}
