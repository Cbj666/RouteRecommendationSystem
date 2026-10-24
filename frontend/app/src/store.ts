import { reactive } from 'vue'
import type { LoopFeature, LoopRequest } from './types'

export interface State {
  origin: { lng: number; lat: number; label: string }
  targetM: number
  prefs: { green: number; safe: number; flat: number }
  loading: boolean
  error: string | null
  loops: LoopFeature[]
  activeIndex: number
  lastMs: number | null
}

export const state = reactive<State>({
  origin: { lng: 114.3547, lat: 30.5342, label: '武汉大学（八一路珞珈山）' },
  targetM: 5000,
  prefs: { green: 1.0, safe: 1.0, flat: 0.6 },
  loading: false,
  error: null,
  loops: [],
  activeIndex: 0,
  lastMs: null,
})

export function requestPayload(): LoopRequest {
  return {
    lng: state.origin.lng,
    lat: state.origin.lat,
    target_m: state.targetM,
    prefs: { ...state.prefs },
  }
}

export const activeLoop = (): LoopFeature | undefined => state.loops[state.activeIndex]
