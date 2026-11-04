import type { LoopCollection, LoopRequest, SegmentCollection } from '../types'

/**
 * 接口封装 —— 契约见 `docs/接口契约.md`。
 *
 * 两种模式：
 *   VITE_USE_MOCK=1 → 读 src/mocks/*.json（真实响应快照），不需要 Python 后端
 *   否则            → 请求 /api/*，由 vite 代理到 127.0.0.1:8000
 *
 * TODO（前端组）：
 *   - 错误提示区分 503（数据没生成）与 500（算法异常）；
 *   - 百度地图 AK 走 import.meta.env.VITE_BAIDU_AK，别写死在代码里。
 */

const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1'

const MOCKS = {
  health: () => import('../mocks/health.json'),
  meta: () => import('../mocks/meta.json'),
  segments: () => import('../mocks/segments.json'),
  facilities: () => import('../mocks/facilities.json'),
  loops: () => import('../mocks/loops.json'),
}

async function mock<T>(name: keyof typeof MOCKS): Promise<T> {
  const mod = await MOCKS[name]()
  return (mod as unknown as { default: T }).default
}

export class ApiError extends Error {
  readonly status: number
  readonly body: string

  constructor(status: number, body: string) {
    super(`${status} ${body}`)
    this.status = status
    this.body = body
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return (await res.json()) as T
}

/** GET /health —— 服务与图状态 */
export async function fetchHealth(): Promise<Record<string, unknown>> {
  if (USE_MOCK) return mock('health')
  return getJson('/health')
}

/** GET /api/meta —— 权重、分档、数据版本 */
export async function fetchMeta(): Promise<Record<string, unknown>> {
  if (USE_MOCK) return mock('meta')
  return getJson('/api/meta')
}

/** GET /api/segments —— bbox 内评分路段（注意：不含 s_air） */
export async function fetchSegments(
  bbox: [number, number, number, number],
  limit = 20000,
): Promise<SegmentCollection> {
  if (USE_MOCK) return mock('segments')
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng), min_lat: String(minLat),
    max_lng: String(maxLng), max_lat: String(maxLat),
    limit: String(limit),
  })
  return getJson(`/api/segments?${q}`)
}

/** GET /api/facilities —— 设施点（kinds: sport | support | all） */
export async function fetchFacilities(
  bbox: [number, number, number, number],
  kinds: 'sport' | 'support' | 'all' = 'all',
): Promise<Record<string, unknown>> {
  if (USE_MOCK) return mock('facilities')
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng), min_lat: String(minLat),
    max_lng: String(maxLng), max_lat: String(maxLat), kinds,
  })
  return getJson(`/api/facilities?${q}`)
}

/** POST /api/loops —— 生成候选环线（第 1 条是推荐） */
export async function fetchLoops(req: LoopRequest): Promise<LoopCollection> {
  if (USE_MOCK) return mock('loops')
  const res = await fetch('/api/loops', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return (await res.json()) as LoopCollection
}
