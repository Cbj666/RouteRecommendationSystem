export interface LoopRequest {
  lng: number
  lat: number
  target_m: number
  prefs: { green: number; safe: number; flat: number }
}

export interface LoopProps {
  origin: string
  label: string
  rank: number
  length_m: number
  minutes: number
  score: number
  tree_share: number
  slope_mean_pct: number
  facility_m: number
  sub: string
}

export interface LoopFeature {
  type: 'Feature'
  properties: LoopProps
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}

export interface LoopCollection {
  type: 'FeatureCollection'
  features: LoopFeature[]
  message?: string
}

export interface SegmentFeature {
  type: 'Feature'
  properties: { osm_id: number; score: number; grade: string; fclass: string; [k: string]: unknown }
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}
