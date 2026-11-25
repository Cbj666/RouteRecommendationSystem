import type { LoopCollection, LoopRequest, SegmentCollection } from '../types'

/**
 * 接口封装 —— 契约见 `docs/接口契约.md`。
 *
 * 两种模式：
 *   VITE_USE_MOCK=0 → 请求 /api/*，由 vite 代理到 127.0.0.1:8000
 *   否则（默认，含未配置）→ 读 src/mocks/*.json（真实响应快照），不需要 Python 后端
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

/** 3 组真实 A→B 单行线快照（武大→东湖、武大→街道口、东湖→磨山），按起终点就近匹配 */
const ONEWAY_MOCK_CASES = [
  {
    a: [114.3547, 30.5342] as const,
    b: [114.411923, 30.555589] as const,
    load: () => import('../mocks/oneway_wuda_donghu.json'),
  },
  {
    a: [114.3547, 30.5342] as const,
    b: [114.349, 30.5256] as const,
    load: () => import('../mocks/oneway_wuda_jiedaokou.json'),
  },
  {
    a: [114.411923, 30.555589] as const,
    b: [114.4076, 30.5458] as const,
    load: () => import('../mocks/oneway_donghu_moshan.json'),
  },
]

async function mock<T>(name: keyof typeof MOCKS): Promise<T> {
  const mod = await MOCKS[name]()
  return (mod as unknown as { default: T }).default
}

/**
 * mock 模式下按「模式 + 起终点 / 距离」挑一份真实快照。
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
      message:
        req.mode === 'oneway'
          ? '起点与终点之间没有可达的慢跑路径，试试重新选择终点。'
          : '该起点附近没有满足 85%–115% 长度窗的候选环线，试试调整目标距离或换个起点。',
    } as unknown as LoopCollection
  }

  if (req.mode === 'oneway') {
    if (req.end_lng == null || req.end_lat == null) {
      throw new ApiError(422, '{"detail":"请先在地图上选择终点 B"}')
    }
    let best = ONEWAY_MOCK_CASES[0]
    let bestDist = Infinity
    for (const item of ONEWAY_MOCK_CASES) {
      const dist =
        Math.hypot(req.lng - item.a[0], req.lat - item.a[1]) +
        Math.hypot(req.end_lng - item.b[0], req.end_lat - item.b[1])
      if (dist < bestDist) {
        bestDist = dist
        best = item
      }
    }
    const mod = await best.load()
    return (mod as unknown as { default: LoopCollection }).default
  }

  const targetM = req.target_m ?? 5000
  const nearDonghu =
    Math.hypot(req.lng - 114.411923, req.lat - 30.555589) <
    Math.hypot(req.lng - 114.3547, req.lat - 30.5342)

  let key: keyof typeof LOOP_MOCKS = 'loops_5km_wuda'
  if (targetM <= 4000) key = 'loops_3km_wuda'
  else if (targetM >= 7500) key = 'loops_10km_wuda'
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
  } catch {
    /* 非 JSON 响应使用通用提示。 */
  }
  return error.status === 503 ? '数据暂不可用，请稍后重试。' : '计算暂未完成，请重试。'
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

let mockCentralSegmentsCache: SegmentCollection | null = null

/** GET /api/segments —— bbox 内评分路段（F1 按视口动态加载） */
export async function fetchSegments(
  bbox: [number, number, number, number],
  limit = 40000,
  signal?: AbortSignal,
): Promise<SegmentCollection> {
  if (USE_MOCK) {
    if (!mockCentralSegmentsCache) {
      const data = await getJson<SegmentCollection>('/geo/segments_city.geojson', signal)
      mockCentralSegmentsCache = { ...data, truncated: false }
    }
    const [minLng, minLat, maxLng, maxLat] = bbox
    // 核心区离线静态兜底范围
    const overlapsCentral =
      maxLng >= 114.29 && minLng <= 114.43 && maxLat >= 30.48 && minLat <= 30.59
    if (!overlapsCentral) {
      return { type: 'FeatureCollection', features: [], truncated: false, bbox }
    }
    return { ...mockCentralSegmentsCache, bbox }
  }
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng),
    min_lat: String(minLat),
    max_lng: String(maxLng),
    max_lat: String(maxLat),
    detail: 'basic',
    limit: String(Math.min(limit, 40000)),
  })
  return getJson(`/api/segments?${q}`, signal)
}

/** GET /api/pois —— 运动场馆 */
export async function fetchFacilities(
  bbox: [number, number, number, number],
  kinds: 'sport' | 'all' = 'all',
): Promise<Record<string, unknown>> {
  if (USE_MOCK) return mock('facilities')
  const [minLng, minLat, maxLng, maxLat] = bbox
  const q = new URLSearchParams({
    min_lng: String(minLng),
    min_lat: String(minLat),
    max_lng: String(maxLng),
    max_lat: String(maxLat),
    kinds,
  })
  return getJson(`/api/pois?${q}`)
}

/** POST /api/routes —— 生成环线或指定终点 A→B 单行线 */
export async function fetchLoops(
  req: LoopRequest,
  signal?: AbortSignal,
): Promise<LoopCollection> {
  if (USE_MOCK) {
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
