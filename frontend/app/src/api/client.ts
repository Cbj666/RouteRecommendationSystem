import type { LoopCollection, LoopRequest, SegmentCollection } from '../types'

/**
 * 接口封装 —— 契约见 `docs/接口契约.md`。
 *
 * 两种模式：
 *   VITE_USE_MOCK=0 → 请求 /api/*，由 vite 代理到 127.0.0.1:8000
 *   否则（默认，含未配置）→ 读 src/mocks/*.json（真实响应快照），不需要 Python 后端
 *
 */

/** 关闭 mock 必须显式写 0：未配置/漏配时默认走 mock，保证页面可演示 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== '0'

const MOCKS = {
  health: () => import('../mocks/health.json'),
  meta: () => import('../mocks/meta.json'),
  segments: () => import('../mocks/segments.json'),
  facilities: () => import('../mocks/facilities.json'),
  loops: () => import('../mocks/loops.json'),
}

const LOOP_MOCKS = {
  loops_3km_wuda: () => import('../mocks/loops_3km_wuda.json'),
  loops_5km_wuda: () => import('../mocks/loops_5km_wuda.json'),
  loops_10km_wuda: () => import('../mocks/loops_10km_wuda.json'),
  loops_5km_donghu: () => import('../mocks/loops_5km_donghu.json'),
}

async function mock<T>(name: keyof typeof MOCKS): Promise<T> {
  const mod = await MOCKS[name]()
  return (mod as unknown as { default: T }).default
}

/**
 * mock 模式下按「距离 + 起点」挑一份真实快照。
 * 快照只覆盖武大 3/5/10 km 与东湖 5 km；其余组合回落到 5 km 武大。
 * 接真后端后这段整体失效（USE_MOCK=0）。
 *
 * 另支持 `?mock=empty|error|slow`，用于自测四态与截图（不影响正常访问）。
 */
async function mockLoops(req: LoopRequest): Promise<LoopCollection> {
  const scenario =
    typeof location === 'undefined'
      ? null
      : new URLSearchParams(location.search).get('mock')

  if (scenario === 'slow') await new Promise((r) => setTimeout(r, 2600))
  else await new Promise((r) => setTimeout(r, 160))

  if (scenario === 'error') {
    throw new ApiError(500, '模拟：服务端异常（自测用，访问 ?mock=error 触发）')
  }
  if (scenario === 'empty') {
    return {
      type: 'FeatureCollection',
      features: [],
      message: '该起点附近没有满足 85%–115% 长度窗的候选环线，试试调整目标距离或换个起点。',
    } as unknown as LoopCollection
  }

  const nearDonghu =
    Math.hypot(req.lng - 114.411923, req.lat - 30.555589) <
    Math.hypot(req.lng - 114.3547, req.lat - 30.5342)

  let key: keyof typeof LOOP_MOCKS = 'loops_5km_wuda'
  if (req.target_m <= 4000) key = 'loops_3km_wuda'
  else if (req.target_m >= 7500) key = 'loops_10km_wuda'
  else if (nearDonghu) key = 'loops_5km_donghu'

  const mod = await LOOP_MOCKS[key]()
  return (mod as unknown as { default: LoopCollection }).default
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

export function apiMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return '网络连接失败，请检查服务后重试。'
  try {
    const detail = JSON.parse(error.body).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join('；')
  } catch { /* 非 JSON 响应使用通用提示。 */ }
  return error.status === 503 ? '数据暂不可用，请稍后重试。' : '计算暂未完成，请重试。'
}

export function fetchToilets(accessible: boolean): Promise<import('../types').LayerCollection> {
  return getJson('/api/toilets?limit=10000' + (accessible ? '&accessible=true' : ''))
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(30000)
  const res = await fetch(url, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout })
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

/** GET /api/segments —— bbox 内评分路段 */
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

/** GET /api/pois —— 运动场馆 */
export async function fetchFacilities(
  bbox: [number, number, number, number],
  kinds: 'sport' | 'all' = 'all',
): Promise<Record<string, unknown>> {
  if (USE_MOCK) return mock('facilities')
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng), min_lat: String(minLat),
    max_lng: String(maxLng), max_lat: String(maxLat), kinds,
  })
  return getJson(`/api/pois?${q}`)
}

/** POST /api/routes —— 生成环线或单行线（rank=1 推荐） */
export async function fetchLoops(
  req: LoopRequest,
  signal?: AbortSignal,
): Promise<LoopCollection> {
  if (USE_MOCK) {
    if (req.mode === 'oneway') throw new ApiError(422, '{"detail":"单行线需要连接真实后端，请切换为环线查看示例。"}')
    return mockLoops(req)
  }
  const res = await fetch('/api/routes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000),
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return (await res.json()) as LoopCollection
}
