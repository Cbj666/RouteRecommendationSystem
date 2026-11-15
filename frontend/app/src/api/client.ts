import type { LoopCollection, LoopRequest, SegmentCollection } from '../types'

/**
 * 接口封装 —— 契约见 `docs/接口契约.md`。
 *
 * 两种模式：
 *   VITE_USE_MOCK=0 → 请求 /api/*，由 vite 代理到 127.0.0.1:8000
 *   否则（默认，含未配置）→ 读 src/mocks/*.json（真实响应快照），不需要 Python 后端
 *
 * TODO（前端组）：
 *   - 错误提示区分 503（数据没生成）与 500（算法异常）；
 *   - 百度地图 AK 走 import.meta.env.VITE_BAIDU_AK，别写死在代码里。
 */

/** 关闭 mock 必须显式写 0：未配置/漏配时默认走 mock，保证页面可演示 */
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== '0'

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
    Math.hypot(req.lng - 114.3805, req.lat - 30.549) <
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
export async function fetchLoops(
  req: LoopRequest,
  signal?: AbortSignal,
): Promise<LoopCollection> {
  if (USE_MOCK) return mockLoops(req)
  const res = await fetch('/api/loops', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  return (await res.json()) as LoopCollection
}
