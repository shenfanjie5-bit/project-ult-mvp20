import { useEffect, useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiClient } from '../../api/client'
import {
  useIndustryGraphList,
  type IndustryGraphPayload,
} from '../../api/hooks/useIndustryGraphs'
import { useSignal5dTop, type Signal5dRow } from '../../api/hooks/useSignal5d'
import { ContentCard } from '../../components/common/ContentCard'
import { PageLayout } from '../../components/common/PageLayout'
import { MetricCard } from '../../components/data/MetricCard'
import { StatusDot } from '../../components/data/StatusDot'
import { TagBadge } from '../../components/data/TagBadge'
import { EventTimeline } from '../../components/explanation/EventTimeline'
import { FriendlyApiErrorState } from '../../components/feedback/FriendlyApiErrorState'
import { LoadingState } from '../../components/feedback/LoadingState'
import {
  deriveIndustryHeat,
  type ConstituentProfile,
} from '../../utils/mockDerive'
import type { IndustryHeat, SignalGrade } from '../../types/derived'
import { useRealMarketEvents } from './hooks/useRealMarketEvents'
import { useUniverseProfiles } from './hooks/useUniverseProfiles'

type MarketCode = 'ALL' | 'A' | 'HK' | 'US'
type RoleFilter = 'ALL' | 'target' | 'customer' | 'both'

const MARKET_LABEL: Record<MarketCode, string> = {
  ALL: '全部',
  A: 'A 股',
  HK: '港股',
  US: '美股',
}

const ROLE_LABEL: Record<RoleFilter, string> = {
  ALL: '全部',
  target: '目标',
  customer: '客户',
  both: '兼具',
}

function inferMarket(tsCode: string): MarketCode {
  if (/\.(SH|SZ|BJ)$/i.test(tsCode)) return 'A'
  if (/\.HK$/i.test(tsCode) || /^0\d{4}\.HK$/i.test(tsCode)) return 'HK'
  if (/\.US$/i.test(tsCode)) return 'US'
  return 'A'
}

function gradeColor(grade: SignalGrade | undefined): string {
  switch (grade) {
    case 'S':
    case 'A':
      return 'var(--danger)'
    case 'B':
      return 'var(--warning)'
    case 'C':
      return 'var(--info)'
    default:
      return 'var(--text-secondary)'
  }
}

function gradeBg(grade: SignalGrade | undefined): string {
  switch (grade) {
    case 'S':
    case 'A':
      return 'var(--danger-bg)'
    case 'B':
      return 'var(--warning-bg)'
    case 'C':
      return 'var(--info-bg)'
    default:
      return 'var(--bg-secondary)'
  }
}

function heatColor(score: number): { bg: string; fg: string } {
  if (score >= 40) return { bg: 'var(--danger-bg)', fg: 'var(--danger)' }
  if (score >= 10) return { bg: 'var(--warning-bg)', fg: 'var(--warning)' }
  if (score > -10) return { bg: 'var(--bg-secondary)', fg: 'var(--text-secondary)' }
  if (score > -40) return { bg: 'var(--info-bg)', fg: 'var(--info)' }
  return { bg: 'var(--success-bg)', fg: 'var(--success)' }
}

export function MarketOverviewPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [selectedMarket, setSelectedMarket] = useState<MarketCode>('ALL')
  const [selectedIndustryId, setSelectedIndustryId] = useState<string>('ALL')
  const [selectedRole, setSelectedRole] = useState<RoleFilter>('ALL')

  const universeQuery = useUniverseProfiles({})
  const graphListQuery = useIndustryGraphList()
  const signal5dQuery = useSignal5dTop({
    market: selectedMarket === 'ALL' ? 'A_share' : selectedMarket,
    industryId: selectedIndustryId,
    role: selectedRole === 'ALL' ? undefined : selectedRole,
    limit: 12,
  })
  // Pull real headlines from mvp20 SQLite (CLS + EastMoney). Loading & error
  // states fall through to an empty timeline rather than the old fixture so
  // we never silently regress to stale mock dates.
  const eventsResult = useRealMarketEvents(8)

  useEffect(() => {
    void import('../StockDetail')
  }, [])

  const industryIds = useMemo(
    () => (graphListQuery.data?.graphs ?? []).map((g) => g.industry_id),
    [graphListQuery.data],
  )

  const graphQueries = useQueries({
    queries: industryIds.map((id) => ({
      queryKey: ['project-ult', 'industry-graphs', id] as const,
      queryFn: ({ signal }) =>
        apiClient.get<IndustryGraphPayload>(
          `/project-ult/industry-graphs?industry_id=${encodeURIComponent(id)}`,
          { signal },
        ),
      retry: false,
      enabled: id.length > 0,
    })),
  })

  const isLoadingPrimary = universeQuery.isLoading || graphListQuery.isLoading
  const isLoadingGraphs =
    industryIds.length > 0 && graphQueries.some((q) => q.isLoading)

  if (isLoadingPrimary || isLoadingGraphs) {
    return (
      <PageLayout title="工作台" description="正在加载行业图谱与全市场池数据…">
        <LoadingState />
      </PageLayout>
    )
  }

  if (universeQuery.isError || !universeQuery.data) {
    return (
      <PageLayout title="工作台" description="全市场池数据暂时无法加载。">
        <FriendlyApiErrorState
          title="池数据加载失败"
          error={
            universeQuery.error ??
            new Error('Universe profiles returned an empty response.')
          }
        />
      </PageLayout>
    )
  }

  if (graphListQuery.isError || !graphListQuery.data) {
    return (
      <PageLayout title="工作台" description="行业图谱列表暂时无法加载。">
        <FriendlyApiErrorState
          title="行业图谱加载失败"
          error={
            graphListQuery.error ??
            new Error('Industry-graph list returned empty.')
          }
        />
      </PageLayout>
    )
  }

  const universe = universeQuery.data.profiles ?? []
  const graphs: IndustryGraphPayload[] = graphQueries
    .map((q) => q.data)
    .filter((g): g is IndustryGraphPayload => Boolean(g))

  const topSignals = signal5dQuery.data?.rows ?? []
  const signalArtifact = signal5dQuery.data?.artifact
  const unsupportedSignalMarket = selectedMarket === 'HK' || selectedMarket === 'US'
  const signalEmptyMessage = unsupportedSignalMarket
    ? '港股 / 美股 5 日相对信号尚未完成独立校准。'
    : '当前筛选条件下没有命中 A 股 5 日信号。'
  const signalCardDescription = signal5dQuery.isLoading
    ? '正在加载 A 股 signal_5d 后端信号。'
    : signal5dQuery.isError
      ? 'A 股 signal_5d 后端信号暂时不可用。'
      : unsupportedSignalMarket
        ? '当前市场暂无已校准的 5 日相对信号。'
        : signalArtifact?.stale && signalArtifact.asof
          ? `A 股 5 日相对信号已陈旧（asof ${signalArtifact.asof}）。`
          : signalArtifact?.available === false
            ? 'A 股 signal_5d artifact 暂不可用。'
            : `A 股 5 日相对胜率排序（top ${topSignals.length}）。`

  function signalIsRenderable(row: Signal5dRow): boolean {
    return (
      row.available !== false &&
      row.validated === true &&
      row.stale !== true &&
      typeof row.probability === 'number'
    )
  }

  function openStock(row: Signal5dRow): void {
    const cachedProfile =
      universe.find((profile) => profile.ts_code === row.ts_code) ??
      ({
        ts_code: row.ts_code,
        name: row.name,
        role: row.role ?? 'target',
        pool: row.pool ?? 'regular',
        industry_ids: row.industry_ids ?? (row.industry_id ? [row.industry_id] : []),
      } as ConstituentProfile)
    queryClient.setQueryData(['project-ult', 'profiles', cachedProfile.ts_code], {
      profiles: [cachedProfile],
      total: 1,
      universe_total: universe.length,
    })
    navigate({
      pathname: `/stock/${row.ts_code}`,
      search: location.search,
    })
  }

  // Heatmap: one card per industry graph, sorted desc
  const industryHeatList: IndustryHeat[] = graphs.map((g) => deriveIndustryHeat(g))
  const sortedHeat = [...industryHeatList].sort(
    (a, b) => b.heat_score - a.heat_score,
  )

  // Current signal list summary. Counts only rows returned by the real
  // signal_5d endpoint; no options/fallback mock is included.
  const coreSummary = (() => {
    const active = topSignals.filter((s) => signalIsRenderable(s))
    const strongUp = active.filter(
      (s) => s.direction === '上涨' && s.signal_strength === '强',
    ).length
    const strongDown = active.filter(
      (s) => s.direction === '下跌' && s.signal_strength === '强',
    ).length
    return {
      total: topSignals.length,
      strongUp,
      strongDown,
      validated: active.length,
      invalid: topSignals.length - active.length,
    }
  })()

  // industry options (all 12 graphs)
  const industryOptions: Array<{ value: string; label: string }> = [
    { value: 'ALL', label: '全部行业' },
    ...graphs.map((g) => ({
      value: g.industry_id,
      label: g.industry_name_cn,
    })),
  ]

  return (
    <PageLayout
      title="工作台"
      description="今日值得关注的 A 股 5 日相对信号、行业热度与事件流。"
    >
      {/* Filters */}
      <ContentCard
        title="筛选"
        description="按市场、行业、角色缩小关注范围；下方重点信号会同步更新。"
      >
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <span className="text-[12px] text-[var(--text-secondary)]">市场</span>
            <div className="flex flex-wrap gap-2">
              {(['ALL', 'A', 'HK', 'US'] as MarketCode[]).map((m) => {
                const active = m === selectedMarket
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setSelectedMarket(m)}
                    className={`rounded-md border px-3 py-1 text-[12px] ${
                      active
                        ? 'border-transparent bg-[var(--info-bg)] text-[var(--info)]'
                        : 'border-[var(--border-light)] bg-white/70 text-[var(--text-secondary)]'
                    }`}
                  >
                    {MARKET_LABEL[m]}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="space-y-1">
            <span className="text-[12px] text-[var(--text-secondary)]">行业</span>
            <select
              value={selectedIndustryId}
              onChange={(e) => setSelectedIndustryId(e.target.value)}
              className="w-full rounded-md border border-[var(--border-light)] bg-white/70 px-3 py-1.5 text-[12px] text-[var(--text-primary)]"
            >
              {industryOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <span className="text-[12px] text-[var(--text-secondary)]">角色</span>
            <div className="flex flex-wrap gap-2">
              {(['ALL', 'target', 'customer', 'both'] as RoleFilter[]).map((r) => {
                const active = r === selectedRole
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setSelectedRole(r)}
                    className={`rounded-md border px-3 py-1 text-[12px] ${
                      active
                        ? 'border-transparent bg-[var(--info-bg)] text-[var(--info)]'
                        : 'border-[var(--border-light)] bg-white/70 text-[var(--text-secondary)]'
                    }`}
                  >
                    {ROLE_LABEL[r]}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </ContentCard>

      {/* Top signals + Event timeline */}
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <ContentCard
          title="今日重点信号"
          description={signalCardDescription}
        >
          {signal5dQuery.isLoading ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              正在加载 A 股 5 日信号…
            </div>
          ) : signal5dQuery.isError ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              A 股 5 日信号接口不可用。
            </div>
          ) : topSignals.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              {signalEmptyMessage}
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {topSignals.map((signal) => {
                const renderable = signalIsRenderable(signal)
                const isUp = signal.direction === '上涨'
                const isDown = signal.direction === '下跌'
                const directionColor = isUp
                  ? 'var(--danger)'
                  : isDown
                    ? 'var(--success)'
                    : 'var(--text-secondary)'
                return (
                  <div
                    key={signal.ts_code}
                    className="surface-card flex flex-col gap-3 p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <div className="truncate text-[14px] font-semibold text-[var(--text-primary)]">
                          {signal.name}
                        </div>
                        <div className="font-mono text-[11px] text-[var(--text-tertiary)]">
                          {signal.ts_code} · {MARKET_LABEL[inferMarket(signal.ts_code)]}
                        </div>
                      </div>
                      <span
                        className="flex h-7 w-7 items-center justify-center rounded-md text-[13px] font-semibold"
                        style={{
                          background: gradeBg(signal.signal_grade),
                          color: gradeColor(signal.signal_grade),
                        }}
                      >
                        {signal.signal_grade}
                      </span>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      <TagBadge label={signal.industry_name ?? signal.industry_id ?? 'A 股'} />
                      <TagBadge
                        label={
                          signal.role === 'target'
                            ? '目标'
                            : signal.role === 'customer'
                              ? '客户'
                              : signal.role === 'both'
                                ? '兼具'
                                : signal.pool === 'regular'
                                  ? '常规'
                                  : (signal.pool ?? '常规')
                        }
                      />
                      {signal.stale ? <TagBadge label="陈旧" /> : null}
                      {signal.validated === false ? <TagBadge label="未验证" /> : null}
                    </div>

                    <div className="grid grid-cols-2 gap-2 rounded-md bg-[var(--bg-secondary)] px-3 py-2">
                      <div>
                        <div className="text-[10px] text-[var(--text-tertiary)]">5 日相对胜率</div>
                        <div
                          className="text-[16px] font-semibold tabular-nums"
                          style={{ color: directionColor }}
                        >
                          {renderable ? `${((signal.probability ?? 0) * 100).toFixed(1)}%` : '--'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-[var(--text-tertiary)]">方向 / 强度</div>
                        <div
                          className="text-[13px] font-medium"
                          style={{ color: directionColor }}
                        >
                          {renderable
                            ? `${signal.direction ?? '震荡'} · ${signal.signal_strength ?? '弱'}`
                            : '无有效信号'}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="text-[10px] text-[var(--text-tertiary)]">主要驱动</div>
                      <ul className="space-y-0.5 text-[12px] text-[var(--text-secondary)]">
                        {(signal.drivers ?? []).slice(0, 3).map((d) => (
                          <li
                            key={d.factor_id}
                            className="flex items-center justify-between gap-2"
                          >
                            <span className="truncate">· {d.factor_label}</span>
                            <span
                              className="font-mono tabular-nums text-[11px]"
                              style={{ color: 'var(--danger)' }}
                            >
                              {d.contribution > 0 ? '+' : ''}
                              {d.contribution.toFixed(2)}
                            </span>
                          </li>
                        ))}
                        {(signal.drivers ?? []).length === 0 ? (
                          <li className="text-[var(--text-tertiary)]">暂无驱动数据</li>
                        ) : null}
                      </ul>
                    </div>

                    {(signal.risks ?? []).length > 0 ? (
                      <div className="space-y-1">
                        <div className="text-[10px] text-[var(--text-tertiary)]">风险提示</div>
                        <ul className="space-y-0.5 text-[12px] text-[var(--text-secondary)]">
                          {(signal.risks ?? []).slice(0, 2).map((r) => (
                            <li
                              key={r.factor_id}
                              className="flex items-center justify-between gap-2"
                            >
                              <span className="truncate">· {r.factor_label}</span>
                              <span
                                className="font-mono tabular-nums text-[11px]"
                                style={{ color: 'var(--success)' }}
                              >
                                {r.contribution.toFixed(2)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {!renderable ? (
                      <div className="rounded-md bg-[var(--bg-secondary)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
                        {signal.reason ?? 'signal_5d 当前未通过有效性检查。'}
                      </div>
                    ) : null}

                    <button
                      type="button"
                      onClick={() => openStock(signal)}
                      className="mt-auto rounded-md border border-[var(--border-light)] bg-white/70 px-3 py-1.5 text-[12px] font-medium text-[var(--info)] hover:bg-[var(--info-bg)]"
                    >
                      查看个股
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </ContentCard>

        <ContentCard
          title="实时事件流"
          description={
            eventsResult.asOf
              ? `财联社电报 + 个股新闻（数据截至 ${eventsResult.asOf.replace('T', ' ')}）。`
              : '财联社电报 + 个股新闻（来自 mvp20 SQLite 实时层）。'
          }
        >
          {eventsResult.isLoading ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              正在加载实时事件…
            </div>
          ) : eventsResult.isError ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              实时事件流暂时不可用（mvp20 SQLite 未连接）。
            </div>
          ) : eventsResult.data.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
              暂无实时事件流。
            </div>
          ) : (
            <EventTimeline events={eventsResult.data} />
          )}
        </ContentCard>
      </div>

      {/* Industry heatmap */}
      <ContentCard
        title="行业热力图"
        description="基于行业先验状态分布派生的相对热度（强多头 + 0.6×温和多头 - 杀估值）。点击行业可筛选上方信号。"
      >
        {sortedHeat.length === 0 ? (
          <div className="rounded-lg border border-dashed border-[var(--border-medium)] px-3 py-8 text-center text-[12px] text-[var(--text-secondary)]">
            暂无行业图谱数据。
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sortedHeat.map((heat) => {
              const colors = heatColor(heat.heat_score)
              const isActive = selectedIndustryId === heat.industry_id
              return (
                <button
                  key={heat.industry_id}
                  type="button"
                  onClick={() =>
                    setSelectedIndustryId((cur) =>
                      cur === heat.industry_id ? 'ALL' : heat.industry_id,
                    )
                  }
                  className={`surface-card flex flex-col gap-2 p-4 text-left transition ${
                    isActive ? 'ring-2 ring-[var(--info)]' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[13px] font-semibold text-[var(--text-primary)]">
                      {heat.industry_name_cn}
                    </span>
                    <StatusDot
                      status={
                        heat.heat_score >= 30
                          ? 'ok'
                          : heat.heat_score >= 0
                            ? 'warning'
                            : 'error'
                      }
                    />
                  </div>
                  <div
                    className="rounded-md px-3 py-2 text-center"
                    style={{ background: colors.bg }}
                  >
                    <div
                      className="text-[28px] font-semibold leading-tight tabular-nums"
                      style={{ color: colors.fg }}
                    >
                      {heat.heat_score > 0 ? '+' : ''}
                      {heat.heat_score}
                    </div>
                    <div className="text-[10px] text-[var(--text-tertiary)]">heat score</div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {heat.top_drivers.slice(0, 3).map((d) => (
                      <TagBadge key={d} label={d} />
                    ))}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </ContentCard>

      {/* Core pool summary */}
      <ContentCard
        title="信号摘要"
        description={`当前 A 股 signal_5d 返回 ${coreSummary.total} 只，validated ${coreSummary.validated} 只。`}
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="强上涨"
            value={String(coreSummary.strongUp)}
            hint="方向=上涨 且 强度=强"
          />
          <MetricCard
            label="强下跌"
            value={String(coreSummary.strongDown)}
            hint="方向=下跌 且 强度=强"
          />
          <MetricCard
            label="已验证"
            value={String(coreSummary.validated)}
            hint="validated=true 且 artifact 未陈旧"
          />
          <MetricCard
            label="暂停展示"
            value={String(coreSummary.invalid)}
            hint="stale 或 validated=false"
          />
        </div>
      </ContentCard>
    </PageLayout>
  )
}
