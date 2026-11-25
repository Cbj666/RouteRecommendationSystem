import { computed, reactive } from 'vue'
import { apiMessage, fetchHotspot } from '../api/client'
import type { HotspotCell, HotspotPayload } from '../types'
import { setOrigin, state } from './planner'

export type HotspotFilter = 'all' | 'hotspot'

/** 区域筛选：矩形用经纬度包围盒，圆用圆心 + 半径（米） */
export type RegionShape =
  | { kind: 'rect'; lon0: number; lat0: number; lon1: number; lat1: number }
  | { kind: 'circle'; lng: number; lat: number; radiusM: number }

export type RegionDrawMode = 'none' | 'rect' | 'circle'

export const hotspotState = reactive({
  /** 全城 1 km 网格；由 /api/hotspot 异步载入（mock 模式读内置示例） */
  payload: null as HotspotPayload | null,
  cells: [] as HotspotCell[],
  selectedId: '',
  filter: 'all' as HotspotFilter,
  loading: false,
  error: '',
  /** 当前生效的区域筛选；null 表示全城 */
  region: null as RegionShape | null,
  /** 正在等待用户在地图上画哪种形状 */
  drawMode: 'none' as RegionDrawMode,
})

let inflight: AbortController | null = null

/** 载入热点网格；重复调用会取消上一次请求。 */
export async function loadHotspot(): Promise<void> {
  if (hotspotState.loading) return
  inflight?.abort()
  const controller = new AbortController()
  inflight = controller
  hotspotState.loading = true
  hotspotState.error = ''
  try {
    const payload = await fetchHotspot(controller.signal)
    hotspotState.payload = payload
    hotspotState.cells = payload.cells
    if (!payload.cells.some((cell) => cell.id === hotspotState.selectedId)) {
      hotspotState.selectedId = topRanked(payload.cells)?.id ?? ''
    }
  } catch (error) {
    if (controller.signal.aborted) return
    hotspotState.error = apiMessage(error)
  } finally {
    if (inflight === controller) inflight = null
    hotspotState.loading = false
  }
}

function topRanked(cells: HotspotCell[]): HotspotCell | null {
  return (
    [...cells]
      .filter((cell) => cell.rank > 0)
      .sort((a, b) => a.rank - b.rank)[0] ?? cells[0] ?? null
  )
}

export const hotspotCellCount = computed(() => hotspotState.cells.length)

export const hotspotSummary = computed(() => hotspotState.payload?.summary ?? null)

export const hotspotNote = computed(
  () => hotspotState.payload?.note ?? '1 km 网格 · 待载入分析结果',
)

/** 页面视野：跟随数据里的全城 bbox（缺失时用 planner 的默认值） */
export const hotspotView = computed(() => hotspotState.payload?.view ?? null)

/** 画到地图上的格子：只跟随「全部 / 仅热点」筛选；区域筛选靠遮罩表现，不删格子 */
export const overlayCells = computed<HotspotCell[]>(() => {
  const cells = hotspotState.cells
  return hotspotState.filter === 'hotspot' ? cells.filter((cell) => cell.isHotspot) : cells
})

export const filteredHotspots = computed<HotspotCell[]>(() => {
  const region = hotspotState.region
  const base = region ? regionCells.value : hotspotState.cells
  const list =
    hotspotState.filter === 'hotspot' ? base.filter((cell) => cell.isHotspot) : base
  if (region) {
    // 区域筛选后按分数排名（全城视图才用全局 rank）
    return [...list].sort((a, b) => b.score - a.score)
  }
  // rank=0 表示样本不足 1 km，不参与榜单，排在最后
  return [...list].sort((a, b) => {
    const ra = a.rank > 0 ? a.rank : Number.MAX_SAFE_INTEGER
    const rb = b.rank > 0 ? b.rank : Number.MAX_SAFE_INTEGER
    return ra - rb
  })
})

const METERS_PER_DEG_LAT = 111_320

/** 网格（含边）是否落在区域内：矩形用包围盒相交，圆用「格中心到圆的最近距离」 */
function cellWithin(cell: HotspotCell, region: RegionShape): boolean {
  const halfW = cell.widthLng / 2
  const halfH = cell.heightLat / 2
  if (region.kind === 'rect') {
    const lon0 = Math.min(region.lon0, region.lon1)
    const lon1 = Math.max(region.lon0, region.lon1)
    const lat0 = Math.min(region.lat0, region.lat1)
    const lat1 = Math.max(region.lat0, region.lat1)
    return (
      cell.lng + halfW >= lon0 &&
      cell.lng - halfW <= lon1 &&
      cell.lat + halfH >= lat0 &&
      cell.lat - halfH <= lat1
    )
  }
  const kx = Math.cos((region.lat * Math.PI) / 180) * METERS_PER_DEG_LAT
  const ky = METERS_PER_DEG_LAT
  const lonMin = (cell.lng - halfW - region.lng) * kx
  const lonMax = (cell.lng + halfW - region.lng) * kx
  const latMin = (cell.lat - halfH - region.lat) * ky
  const latMax = (cell.lat + halfH - region.lat) * ky
  const dx = lonMin > 0 ? lonMin : lonMax < 0 ? -lonMax : 0
  const dy = latMin > 0 ? latMin : latMax < 0 ? -latMax : 0
  return dx * dx + dy * dy <= region.radiusM * region.radiusM
}

/** 区域覆盖到的网格 */
export const regionCells = computed<HotspotCell[]>(() => {
  const region = hotspotState.region
  if (!region) return []
  return hotspotState.cells.filter((cell) => cellWithin(cell, region))
})

/** 区域聚合指标（长度加权，和全城 summary 同一口径） */
export const regionSummary = computed(() => {
  if (!hotspotState.region) return null
  const cells = regionCells.value
  const lenM = cells.reduce((sum, cell) => sum + cell.lenM, 0)
  const weighted = cells.reduce((sum, cell) => sum + cell.score * cell.lenM, 0)
  return {
    cells: cells.length,
    hotspots: cells.filter((cell) => cell.isHotspot).length,
    lenM,
    meanScore: lenM > 0 ? weighted / lenM : 0,
  }
})

/** 筛选按钮上的热点数：区域生效时显示区域内热点数 */
export const visibleHotspotCount = computed(
  () => regionSummary.value?.hotspots ?? hotspotCount.value,
)

export function setRegion(region: RegionShape | null): void {
  hotspotState.region = region
  if (region) {
    const top = filteredHotspots.value[0]
    if (top) hotspotState.selectedId = top.id
    return
  }
  if (!hotspotState.cells.some((cell) => cell.id === hotspotState.selectedId)) {
    hotspotState.selectedId = topRanked(hotspotState.cells)?.id ?? ''
  }
}

export function setDrawMode(mode: RegionDrawMode): void {
  hotspotState.drawMode = mode
}

export const selectedHotspot = computed<HotspotCell | null>(
  () => hotspotState.cells.find((cell) => cell.id === hotspotState.selectedId) ?? null,
)

export const hotspotCount = computed(
  () => hotspotState.cells.filter((cell) => cell.isHotspot).length,
)

export function selectHotspot(id: string): void {
  if (hotspotState.cells.some((cell) => cell.id === id)) hotspotState.selectedId = id
}

export function setHotspotFilter(filter: HotspotFilter): void {
  hotspotState.filter = filter
  if (!filteredHotspots.value.some((cell) => cell.id === hotspotState.selectedId)) {
    hotspotState.selectedId = filteredHotspots.value[0]?.id ?? ''
  }
}

/** 回填起点并跳到环线页；setOrigin 会按新起点生成一次路线。 */
export function useHotspotAsOrigin(): void {
  const cell = selectedHotspot.value
  if (!cell) return
  setOrigin(
    {
      name: `${cell.name}（热点网格）`,
      lng: cell.lng,
      lat: cell.lat,
    },
    'custom',
  )
  state.tab = 'loops'
}
