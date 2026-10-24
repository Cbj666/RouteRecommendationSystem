import type { LoopCollection, LoopRequest, SegmentFeature } from '../types'

/**
 * 接口封装。开发时由 vite 代理到 http://127.0.0.1:8000。
 *
 * TODO(卡片 1)：删除 mock，接真接口；错误提示要能区分
 *   503（数据没生成）与 500（算法异常）。
 */

const USE_MOCK = false

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return (await res.json()) as T
}

export async function fetchLoops(req: LoopRequest): Promise<LoopCollection> {
  if (USE_MOCK) return mockLoops()
  return post<LoopCollection>('/api/loops', req)
}

export async function fetchSegments(bbox: [number, number, number, number]): Promise<SegmentFeature[]> {
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng), min_lat: String(minLat),
    max_lng: String(maxLng), max_lat: String(maxLat),
  })
  const res = await fetch(`/api/segments?${q}`)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  const fc = (await res.json()) as { features: SegmentFeature[] }
  return fc.features
}

export async function fetchMeta(): Promise<Record<string, unknown>> {
  const res = await fetch('/api/meta')
  if (!res.ok) throw new Error(`${res.status}`)
  return (await res.json()) as Record<string, unknown>
}

/** 没有后端时用的假数据，只保证页面能渲染 */
function mockLoops(): LoopCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {
          origin: 'wuda', label: '武汉大学', rank: 1,
          length_m: 5339.5, minutes: 32, score: 78.5,
          tree_share: 0.576, slope_mean_pct: 3.55, facility_m: 240,
          sub: JSON.stringify({ s_safety: 84.3, s_green: 81.0, s_slope: 64.5 }),
        },
        geometry: {
          type: 'LineString',
          coordinates: [
            [114.3547, 30.5342], [114.3650, 30.5380], [114.3720, 30.5440],
            [114.3660, 30.5510], [114.3540, 30.5470], [114.3480, 30.5390],
            [114.3547, 30.5342],
          ],
        },
      },
    ],
  }
}
