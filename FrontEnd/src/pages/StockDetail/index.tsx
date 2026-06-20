// derived mock for frontend preview — StockDetail page (A-route demo).
//
// This page is a derived-preview surface: backend stays untouched and we
// project the constituent profile + the loaded industry_graph YAML through
// `mockDerive.ts` to produce signals, factor contributions, timeline events
// and explanation paths. Nothing here is a real model output.

import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  useIndustryGraph,
  type IndustryGraphPayload,
} from '../../api/hooks/useIndustryGraphs'
import { useProjectUltProfiles } from '../../api/projectUlt/hooks'
import { PageLayout } from '../../components/common/PageLayout'
import { ErrorState } from '../../components/feedback/ErrorState'
import { LoadingState } from '../../components/feedback/LoadingState'
import {
  deriveFactorContributions,
  deriveRiskContributions,
  deriveStockSignal,
  type ConstituentProfile,
} from '../../utils/mockDerive'
import { useStockOverlay } from '../../api/hooks/useStockOverlay'
import { useRealtimeStream } from '../../api/hooks/useRealtimeStream'
import { useStockScore } from '../../api/hooks/useStockScore'
import { useStockCoverage } from '../../api/hooks/useStockCoverage'
import { useStockAggregate } from '../../api/hooks/useStockAggregate'
import { useTechnicals } from '../../api/hooks/useTechnicals'
import { CoverageBanner } from './components/CoverageBanner'
import { EventTimelinePanel } from './components/EventTimelinePanel'
import { ExplanationDrawer } from './components/ExplanationDrawer'
import { FactorPanel } from './components/FactorPanel'
import { GovernanceEventsPanel } from './components/GovernanceEventsPanel'
import {
  BacktestPlaceholder,
  LLMPlaceholder,
  OptionsPanel,
} from './components/PlaceholderPanels'
import { ScorePanel } from './components/ScorePanel'
import { QuantPanel } from './components/QuantPanel'
import { TechnicalsPanel } from './components/TechnicalsPanel'
import { StockGraphPanel } from './components/StockGraphPanel'
import { StockHeader } from './components/StockHeader'
import { buildTimelineForStock } from './components/buildTimeline'

const PathGraphPanel = lazy(() =>
  import('./components/PathGraphPanel').then((module) => ({
    default: module.PathGraphPanel,
  })),
)

const CORE_DETAIL_DATA_DEFER_MS = 120
const ENRICHED_DETAIL_DATA_DEFER_MS = 300

/* -------------------------------------------------------------------------- */
/* Envelope-aware payload extraction                                           */
/* -------------------------------------------------------------------------- */

interface ProfilesEnvelopeShape {
  profiles?: ConstituentProfile[]
  total?: number
  universe_total?: number
}

function isWrappedEnvelope<T>(value: unknown): value is { data: T; request_id?: string } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'data' in (value as Record<string, unknown>)
  )
}

function extractProfiles(payload: unknown): ConstituentProfile[] {
  if (!payload) return []
  // mvp20 server wraps everything in { data, request_id }; demo mocks do not.
  const inner = isWrappedEnvelope<ProfilesEnvelopeShape>(payload) ? payload.data : payload
  if (
    inner &&
    typeof inner === 'object' &&
    Array.isArray((inner as ProfilesEnvelopeShape).profiles)
  ) {
    return (inner as ProfilesEnvelopeShape).profiles ?? []
  }
  return []
}

function extractIndustryGraph(payload: unknown): IndustryGraphPayload | null {
  if (!payload) return null
  const inner = isWrappedEnvelope<IndustryGraphPayload>(payload) ? payload.data : payload
  if (
    inner &&
    typeof inner === 'object' &&
    Array.isArray((inner as IndustryGraphPayload).nodes) &&
    Array.isArray((inner as IndustryGraphPayload).edges)
  ) {
    return inner as IndustryGraphPayload
  }
  return null
}

function inferMarketLabel(tsCode: string): string {
  if (
    tsCode.endsWith('.SH') ||
    tsCode.endsWith('.SZ') ||
    tsCode.endsWith('.BJ')
  ) {
    return 'A 股'
  }
  if (tsCode.endsWith('.HK')) return '港股'
  if (tsCode.endsWith('.US')) return '美股'
  return '未知市场'
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.isContentEditable
  )
}

function mergeIndustryIds(primary: string, profileIds: string[], overlayIds: string[]): string[] {
  const ids = new Set<string>()
  if (primary) ids.add(primary)
  profileIds.forEach((id) => ids.add(id))
  overlayIds.forEach((id) => ids.add(id))
  return Array.from(ids).filter(Boolean)
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export function StockDetailPage() {
  const navigate = useNavigate()
  const { id: rawId = '600519.SH' } = useParams<{ id: string }>()
  const tsCode = useMemo(() => decodeURIComponent(rawId), [rawId])
  const [chainOpen, setChainOpen] = useState(false)
  const [selectedIndustryId, setSelectedIndustryId] = useState('')

  // Backspace → back, mirrors the previous behaviour.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape' && chainOpen) {
        setChainOpen(false)
        return
      }
      if (event.key !== 'Backspace' || isEditableTarget(event.target)) {
        return
      }
      event.preventDefault()
      navigate(-1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [chainOpen, navigate])

  const profilesQuery = useProjectUltProfiles({ ts_code: tsCode })
  const profiles = useMemo(
    () => extractProfiles(profilesQuery.data),
    [profilesQuery.data],
  )
  const profile = useMemo<ConstituentProfile | null>(
    () => profiles.find((p) => p.ts_code === tsCode) ?? null,
    [profiles, tsCode],
  )

  const primaryIndustryId = profile?.industry_ids?.[0] ?? ''
  const queryIndustryId = selectedIndustryId || primaryIndustryId
  const detailDataKey = profile ? `${tsCode}:${queryIndustryId}` : ''
  const [readyCoreDetailDataKey, setReadyCoreDetailDataKey] = useState('')
  const [readyEnrichedDetailDataKey, setReadyEnrichedDetailDataKey] = useState('')
  useEffect(() => {
    if (!detailDataKey) return undefined
    const timer = window.setTimeout(
      () => setReadyCoreDetailDataKey(detailDataKey),
      CORE_DETAIL_DATA_DEFER_MS,
    )
    return () => window.clearTimeout(timer)
  }, [detailDataKey])

  useEffect(() => {
    if (!detailDataKey) return undefined
    const timer = window.setTimeout(
      () => setReadyEnrichedDetailDataKey(detailDataKey),
      ENRICHED_DETAIL_DATA_DEFER_MS,
    )
    return () => window.clearTimeout(timer)
  }, [detailDataKey])

  const coreDetailTsCode =
    detailDataKey && readyCoreDetailDataKey === detailDataKey ? tsCode : undefined
  const timedEnrichedDetailTsCode =
    detailDataKey && readyEnrichedDetailDataKey === detailDataKey ? tsCode : undefined

  // A1/A2/A3 derived layers. These do not block the page render — if any of
  // the three endpoints 404 (backend not yet wired) the UI falls back to
  // "暂无" placeholders inside each component.
  const scoreQuery = useStockScore(coreDetailTsCode, queryIndustryId || undefined)
  const coverageQuery = useStockCoverage(coreDetailTsCode, queryIndustryId || undefined)
  const score = scoreQuery.data ?? null
  const coverage = coverageQuery.data ?? null
  const coreDetailSettled =
    Boolean(coreDetailTsCode) &&
    (scoreQuery.isSuccess || scoreQuery.isError) &&
    (coverageQuery.isSuccess || coverageQuery.isError)
  const enrichedDetailTsCode = coreDetailSettled ? timedEnrichedDetailTsCode : undefined
  const overlayQuery = useStockOverlay(enrichedDetailTsCode, queryIndustryId || undefined)
  const overlay = overlayQuery.data ?? null
  useRealtimeStream(enrichedDetailTsCode, queryIndustryId || overlay?.industry_id, { pollSeconds: 5 })

  // P3-Z1: aggregate now feeds PathGraphPanel for per-node value/coverage
  // overlays on the graph nodes; we still warm the cache for future surfaces.
  const aggregateQuery = useStockAggregate(enrichedDetailTsCode, queryIndustryId || undefined)
  // Technical indicators (MA/MACD/RSI/KDJ/BOLL/VOL/ATR/OBV) computed daily by
  // ``mvp20.derive_all`` from OHLCV bars. Endpoint returns null per-indicator
  // when derive hasn't covered the stock yet — the panel renders a placeholder.
  const technicalsQuery = useTechnicals(enrichedDetailTsCode, { returnSeries: 30 })
  const aggregate = aggregateQuery.data ?? null
  const technicals = technicalsQuery.data ?? null

  const overlayAvailableIndustryIds = useMemo(
    () => overlay?.available_industries ?? [],
    [overlay?.available_industries],
  )
  const availableIndustryIds = useMemo(
    () =>
      mergeIndustryIds(
        primaryIndustryId,
        profile?.industry_ids ?? [],
        overlayAvailableIndustryIds,
      ),
    [overlayAvailableIndustryIds, primaryIndustryId, profile?.industry_ids],
  )

  const effectiveIndustryId =
    selectedIndustryId && availableIndustryIds.includes(selectedIndustryId)
      ? selectedIndustryId
      : primaryIndustryId

  useEffect(() => {
    if (!profile) return
    const timer = window.setTimeout(() => {
      setSelectedIndustryId((current) => {
        if (current && availableIndustryIds.includes(current)) {
          return current
        }
        return primaryIndustryId
      })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [availableIndustryIds, primaryIndustryId, profile])

  const industryGraphQuery = useIndustryGraph(effectiveIndustryId, {
    enabled: Boolean(effectiveIndustryId),
  })
  const industryGraph = useMemo(
    () => extractIndustryGraph(industryGraphQuery.data),
    [industryGraphQuery.data],
  )

  /* ----------------------------- loading / error ------------------------- */

  if (profilesQuery.isLoading) {
    return (
      <PageLayout
        title={`个股详情 · ${tsCode}`}
        description="正在加载 universe 列表，准备派生预览。"
      >
        <LoadingState />
      </PageLayout>
    )
  }

  if (profilesQuery.isError) {
    return (
      <PageLayout
        title={`个股详情 · ${tsCode}`}
        description="universe profiles 接口加载失败。"
      >
        <ErrorState
          title="universe 数据未就绪"
          description="未能从 /api/project-ult/profiles 拿到 universe 列表，请检查 mvp20 server 是否运行。"
        />
      </PageLayout>
    )
  }

  if (!profile) {
    return (
      <PageLayout
        title={`个股详情 · ${tsCode}`}
        description="该 ts_code 不在当前 universe 列表中。"
      >
        <ErrorState
          title="未在 universe 中找到该 ts_code"
          description={`请检查 config/mvp20.universe.yaml 是否包含 ${tsCode}，或切换到其它 universe 内的标的。`}
        />
      </PageLayout>
    )
  }

  if (!primaryIndustryId) {
    return (
      <PageLayout
        title={`个股详情 · ${profile.name}`}
        description="该标的没有 industry_ids，无法构建派生预览。"
      >
        <ErrorState
          title="industry_ids 缺失"
          description="universe.yaml 中该 ts_code 没有 industry_ids，派生信号需要至少一个行业图谱。"
        />
      </PageLayout>
    )
  }

  if (industryGraphQuery.isLoading) {
    return (
      <PageLayout
        title={`个股详情 · ${profile.name}`}
        description={`正在加载 ${effectiveIndustryId} 行业图谱。`}
      >
        <LoadingState />
      </PageLayout>
    )
  }

  if (industryGraphQuery.isError || !industryGraph) {
    return (
      <PageLayout
        title={`个股详情 · ${profile.name}`}
        description={`${effectiveIndustryId} 行业图谱加载失败。`}
      >
        <ErrorState
          title="行业图谱数据未就绪"
          description={`未能从 /api/project-ult/industry-graphs?industry_id=${effectiveIndustryId} 拿到图谱。请检查 config/industry_graphs/${effectiveIndustryId}.yaml 是否存在。`}
        />
      </PageLayout>
    )
  }

  /* ----------------------------- derive layer ----------------------------- */

  // The header renders backend signal_up_5d and signal_5d as two different
  // metrics. The derived signal remains only as a fallback preview for
  // unsupported markets and lower-page panels that still use industry priors.
  const signal = deriveStockSignal(profile, industryGraph, score)
  const drivers = deriveFactorContributions(profile, industryGraph, 5)
  const risks = deriveRiskContributions(profile, industryGraph, 3)
  const timelineEvents = buildTimelineForStock(industryGraph, tsCode)

  return (
    <PageLayout
      title={`个股详情 · ${profile.name}`}
      description={`公司图谱 · ${industryGraph.industry_name_cn}（${effectiveIndustryId}）。Backspace 返回上一页，Esc 关闭解释链。`}
    >
      <CoverageBanner
        coverage={coverage}
        loading={coverageQuery.isLoading}
        error={coverageQuery.isError}
      />

      <StockHeader
        name={profile.name}
        tsCode={tsCode}
        market={inferMarketLabel(tsCode)}
        industryIds={availableIndustryIds}
        industryNameCn={industryGraph.industry_name_cn}
        pool={typeof profile.pool === 'string' ? profile.pool : undefined}
        role={typeof profile.role === 'string' ? profile.role : undefined}
        signal={signal}
        signalUp5d={score?.signal_up_5d ?? null}
        signal5d={score?.signal_5d ?? null}
        onOpenChain={() => setChainOpen(true)}
        mode={score?.mode ?? null}
        modeDisplay={score?.mode_display ?? null}
        modeConfidence={score?.mode_confidence ?? null}
        modeRationale={score?.mode_rationale ?? null}
        tradingSignal={score?.trading_signal ?? null}
        tradingMeaning={score?.trading_meaning ?? null}
        scoreLoading={scoreQuery.isLoading}
        realtime={overlay?.realtime ?? null}
      />

      {availableIndustryIds.length > 1 ? (
        <section className="surface-card flex flex-wrap items-center justify-between gap-3 p-4">
          <div>
            <div className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
              行业图谱视图
            </div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">
              同一家公司会按 company × industry overlay 切换解释路径。
            </div>
          </div>
          <div className="inline-flex flex-wrap gap-1 rounded-lg bg-[var(--bg-secondary)] p-1">
            {availableIndustryIds.map((industryId) => {
              const active = industryId === effectiveIndustryId
              return (
                <button
                  key={industryId}
                  type="button"
                  onClick={() => setSelectedIndustryId(industryId)}
                  className={
                    active
                      ? 'rounded-md bg-white px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] shadow-sm'
                      : 'rounded-md px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition hover:bg-white/70'
                  }
                  title={`切换到 ${industryId} overlay`}
                >
                  {industryId}
                </button>
              )
            })}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <FactorPanel
          drivers={drivers}
          risks={risks}
          onOpenChain={() => setChainOpen(true)}
        />
        <EventTimelinePanel
          tsCode={tsCode}
          events={timelineEvents}
          emptyHint="当前行业图谱中没有 event/signal 节点可派生时间轴；切换其它行业可重试。"
        />
      </div>

      <StockGraphPanel
        graph={industryGraph}
        overlay={overlay}
        overlayLoading={overlayQuery.isLoading}
        overlayError={overlayQuery.isError}
        drivers={drivers}
        risks={risks}
        targetNodeId={tsCode}
        targetNodeLabel={profile.name}
        targetIndustryTags={availableIndustryIds}
        tsCode={enrichedDetailTsCode}
        coverage={coverage}
      />

      <ScorePanel
        score={score}
        loading={scoreQuery.isLoading}
        error={scoreQuery.isError}
      />

      <QuantPanel score={score} loading={scoreQuery.isLoading} />

      <TechnicalsPanel
        data={technicals}
        loading={technicalsQuery.isLoading}
        error={technicalsQuery.isError}
      />

      <Suspense
        fallback={
          <div className="surface-card p-4 text-[12px] text-[var(--text-tertiary)]">
            影响传导路径稍后加载
          </div>
        }
      >
        <PathGraphPanel
          score={score}
          aggregate={aggregate}
          coverage={coverage}
          loading={scoreQuery.isLoading}
          error={scoreQuery.isError}
        />
      </Suspense>

      <GovernanceEventsPanel aggregate={aggregate} overlay={overlay} />

      <LLMPlaceholder graph={industryGraph} companyName={profile.name} />

      <OptionsPanel
        tsCode={tsCode}
        realtime={overlay?.realtime ?? null}
      />

      <BacktestPlaceholder />

      <ExplanationDrawer
        open={chainOpen}
        graph={industryGraph}
        targetCompany={profile.name}
        targetNodeId={tsCode}
        onClose={() => setChainOpen(false)}
      />
    </PageLayout>
  )
}
