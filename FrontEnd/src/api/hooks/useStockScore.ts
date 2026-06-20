// Hook: fetch derived A3 stock score (mode classification + final scores +
// trading signal + top paths) for one ts_code from mvp20 server endpoint:
// /api/project-ult/score?ts_code=X[&industry_id=Y]
//
// Schema mirrors `mvp20/scoring.py::score_company` return shape. All values
// are pre-derived server-side from aggregator (A1) + coverage (A2) + realtime
// snapshot inputs. Hook just renders.

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'

export type TradingSignal = 'BUY' | 'HOLD' | 'WATCH' | 'AVOID'

/** One of seven mode-classification keys from `scoring.classify_mode`. */
export type StockModeKey =
  | 'strong_bull'
  | 'moderate_bull'
  | 'digestion'
  | 'structural_divergence'
  | 'de_rating'
  | 'trend_reversal'
  | 'wait_for_confirmation'
  | string // fallback for forward-compat

export interface StockScorePathInfo {
  dp_id?: string
  node_id?: string
  score: number
  description?: string
  rationale?: string
  direction?: number
}

export interface StockScoreTopPaths {
  positive: StockScorePathInfo[]
  negative: StockScorePathInfo[]
}

export interface StockScoreCompanyComponents {
  industry_contrib?: number
  event?: number
  capital?: number
  risk?: number
  valuation?: number
  priced_in?: number
  [key: string]: number | undefined
}

export interface StockScoreCompanyScore {
  score: number
  components: StockScoreCompanyComponents
}

export interface StockScoreFinalDetail {
  short_total?: number
  medium_total?: number
  long_total?: number
  base_score?: number
  components?: Record<string, number>
  trading_meaning?: string
}

/** 涨幅预测分数 (two-layer quant shadow output) — mirrors the server `quant`
 * block. Honesty contract: NO absolute P(up); `p_beat_median` = base_rate ±
 * tilt; outside the liquid-70 gate / stale artifact → `validated:false`. */
export interface QuantMag {
  score_pct: number
  horizon_days: number
  exp_excess: number
  q10: number
  q90: number
  mean_if_up: number
}

export interface QuantProb {
  horizon_days: number
  p_beat_median: number
  tilt_pp: number
  base_rate: number
}

export interface QuantTheme {
  heat_pct: number
  overheat: boolean
}

export interface QuantBlock {
  available: boolean
  validated?: boolean
  reason?: string
  asof?: string
  stale?: boolean
  mag?: QuantMag
  prob?: QuantProb
  theme?: QuantTheme
  caveats?: string[]
}

/** A-share 5d relative signal used by MarketOverview. It is P(beat same-day
 * liquid median), not absolute P(up); stale or unvalidated rows must not be
 * displayed as active probabilities. */
export interface Signal5dBlock {
  available: boolean
  validated?: boolean
  stale?: boolean
  reason?: string
  asof?: string
  horizon_days?: number
  target?: string
  target_display?: string
  probability?: number
  p_beat_median?: number
  base_rate?: number
  tilt_pp?: number
  direction?: '上涨' | '下跌' | '震荡'
  signal_strength?: '强' | '中' | '弱'
  signal_grade?: 'S' | 'A' | 'B' | 'C' | 'D'
  source_artifact?: string
  caveats?: string[]
}

/** G8 evidence marker — `abstain:true` means the signal rests on too little
 * data to be shown as a confident label. */
export interface SignalEvidence {
  n_known_fields: number
  n_realtime_nodes: number
  abstain: boolean
  floor: number
}

export interface StockScoreResponse {
  ts_code: string
  industry_id?: string | null
  /** Raw mode key, e.g. ``strong_bull``. */
  mode: StockModeKey
  /** Localised display string (Chinese), e.g. ``强多头``. */
  mode_display?: string
  /** 0..1 confidence on the mode label. */
  mode_confidence: number
  /** Free-form rationale from classify_mode. */
  mode_rationale: string
  /** Mode evidence drivers (signal pack keys). */
  mode_drivers?: string[]
  /** Per-horizon final scores. */
  short_total: number
  medium_total: number
  long_total: number
  /** Translated BUY / HOLD / WATCH / AVOID label. */
  trading_signal: TradingSignal
  /** Plain-Chinese trading-narrative string. */
  trading_meaning: string
  /** Spec §27.3 company score + component breakdown. */
  company_score: StockScoreCompanyScore
  /** Optional final-score breakdown (spec §27.4). */
  final_score?: StockScoreFinalDetail
  /** Top-3 positive / negative paths. */
  top_paths?: StockScoreTopPaths
  /** Primary drivers / signal pack keys surfaced by ``classify_mode``. */
  primary_drivers?: string[]
  /** Raw signal pack — useful for debugging. */
  signals?: Record<string, unknown>
  /** 涨幅预测分数 (validated two-layer model) — parallel shadow output. */
  quant?: QuantBlock
  /** A-share 5d relative signal — parallel shadow output. */
  signal_5d?: Signal5dBlock
  /** RD-A dual-axis (parallel v2; headline stays trading_signal until the
   * P&L loop's matured comparison promotes it). merit+timing == core base. */
  merit?: number
  timing?: number
  trading_signal_v2?: TradingSignal
  /** G8 evidence/abstain marker. */
  signal_evidence?: SignalEvidence
  /** Freshness of the realtime rows this score consumed (mock excluded). */
  freshness?: {
    newest_age_seconds: number | null
    median_age_seconds: number | null
    stale: boolean
    n_rows: number
  }
}

/**
 * Fetch derived A3 score for one ts_code. ``industry_id`` is optional; when
 * absent the server uses the company's primary industry from
 * ``config/universe.yaml``. Returns `undefined` while disabled (no tsCode).
 */
export function useStockScore(tsCode: string | undefined, industryId?: string) {
  const normalizedIndustryId = industryId?.trim() || ''
  return useQuery<StockScoreResponse>({
    queryKey: ['project-ult', 'stock-score', tsCode, normalizedIndustryId],
    enabled: Boolean(tsCode),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ ts_code: tsCode! })
      if (normalizedIndustryId) {
        params.set('industry_id', normalizedIndustryId)
      }
      return apiClient.get<StockScoreResponse>(
        `/project-ult/score?${params.toString()}`,
        { signal },
      )
    },
    refetchOnWindowFocus: false,
    staleTime: 5 * 60_000,
    // Score is the only one of A1/A2/A3 we may want to refresh after the
    // overlay refetches (every 60s) — but per task brief we keep it cheap.
    retry: 1,
  })
}
