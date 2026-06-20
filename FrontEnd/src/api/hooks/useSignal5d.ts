import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../client'
import type {
  FactorContribution,
  SignalDirection,
  SignalGrade,
  SignalStrength,
} from '../../types/derived'

export type Signal5dMarket = 'A_share' | 'A' | 'HK' | 'US' | 'ALL'

export interface Signal5dArtifactInfo {
  available: boolean
  market?: string
  asof?: string
  horizon_days?: number
  target?: string
  target_display?: string
  model_method?: string
  probability_source?: string
  probability_semantics?: string
  stale?: boolean
  source_artifact?: string
  n_rows?: number
  n_available?: number
  n_validated?: number
  coverage?: {
    row_count?: number
    available_count?: number
    validated_count?: number
    validated_ratio?: number
    liquid_frac?: number
    min_feature_coverage?: number
  }
  calibration?: Record<string, unknown>
  caveats?: string[]
  reason?: string
}

export interface Signal5dRow {
  ts_code: string
  name: string
  market: string
  industry_id?: string | null
  industry_ids?: string[]
  industry_name?: string | null
  role?: 'target' | 'customer' | 'both' | string | null
  pool?: string | null
  available?: boolean
  validated?: boolean
  stale?: boolean
  reason?: string
  asof?: string
  horizon_days?: number
  target?: string
  target_display?: string
  probability?: number
  p_beat_median?: number
  model_method?: string
  probability_semantics?: string
  feature_coverage?: number | null
  model_probability?: number | null
  model_probability_shadow?: number | null
  legacy_bin_probability?: number | null
  fallback_probability?: number | null
  probability_source?: string
  base_rate?: number
  tilt_pp?: number
  direction?: SignalDirection
  signal_strength?: SignalStrength
  signal_grade?: SignalGrade
  score_pct?: number | null
  drivers?: FactorContribution[]
  risks?: FactorContribution[]
  source_artifact?: string
}

export interface Signal5dTopResponse {
  module: string
  market: string
  horizon_days: number
  target?: string
  target_display?: string
  rows: Signal5dRow[]
  total: number
  returned: number
  artifact: Signal5dArtifactInfo
  reason?: string
}

export interface UseSignal5dTopParams {
  market?: Signal5dMarket
  industryId?: string
  role?: 'target' | 'customer' | 'both'
  limit?: number
}

export function useSignal5dTop({
  market = 'A_share',
  industryId,
  role,
  limit = 12,
}: UseSignal5dTopParams = {}) {
  const normalizedIndustryId = industryId && industryId !== 'ALL' ? industryId : ''
  const normalizedMarket = market === 'ALL' ? 'A_share' : market
  return useQuery<Signal5dTopResponse>({
    queryKey: ['project-ult', 'signal-5d-top', normalizedMarket, normalizedIndustryId, role ?? '', limit],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        horizon: '5',
        market: normalizedMarket,
        limit: String(limit),
      })
      if (normalizedIndustryId) {
        params.set('industry_id', normalizedIndustryId)
      }
      if (role) {
        params.set('role', role)
      }
      return apiClient.get<Signal5dTopResponse>(
        `/project-ult/signals/top?${params.toString()}`,
        { signal },
      )
    },
    retry: false,
    staleTime: 5 * 60_000,
  })
}
