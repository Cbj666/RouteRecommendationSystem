import { reactive } from 'vue'
import { apiMessage, getJson, USE_MOCK } from '../api/client'
import type { LayerCollection } from '../types'

export interface RoadDetail {
  type: 'Feature'
  properties: Record<string, string | number | null>
  geometry: { type: 'LineString'; coordinates: [number, number][] }
}

export const inspection = reactive({
  selected: null as RoadDetail | null,
  loading: false,
  message: '',
  toilets: null as LayerCollection | null,
  toiletsEnabled: false,
  accessible: false,
})
let controller: AbortController | null = null

export async function inspectRoad(lng: number, lat: number): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  inspection.loading = true
  inspection.message = ''
  inspection.selected = null
  try {
    const delta = 0.001
    const query = new URLSearchParams({
      min_lng: String(lng - delta), max_lng: String(lng + delta),
      min_lat: String(lat - delta), max_lat: String(lat + delta),
      detail: 'full', limit: '2000',
    })
    const collection = USE_MOCK
      ? (await import('../mocks/segments.json')).default as unknown as { features: RoadDetail[] }
      : await getJson<{ features: RoadDetail[] }>('/api/segments?' + query, signal)
    if (signal.aborted) return
    let best: RoadDetail | null = null
    let nearest = 40 * 40
    const metersX = 111320 * Math.cos(lat * Math.PI / 180)
    for (const road of collection.features) {
      if (road.geometry.type !== 'LineString') continue
      const coordinates = road.geometry.coordinates
      for (let i = 1; i < coordinates.length; i++) {
        const [ax, ay] = [(coordinates[i - 1][0] - lng) * metersX, (coordinates[i - 1][1] - lat) * 111320]
        const [bx, by] = [(coordinates[i][0] - lng) * metersX, (coordinates[i][1] - lat) * 111320]
        const dx = bx - ax, dy = by - ay
        const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)))
        const distance = (ax + t * dx) ** 2 + (ay + t * dy) ** 2
        if (distance < nearest) { best = road; nearest = distance }
      }
    }
    inspection.selected = best
    if (!best) inspection.message = '附近 40 m 内没有可查询路段，请放大后点击道路。'
  } catch (error) {
    if (!signal.aborted) inspection.message = apiMessage(error)
  } finally {
    if (!signal.aborted) inspection.loading = false
  }
}
