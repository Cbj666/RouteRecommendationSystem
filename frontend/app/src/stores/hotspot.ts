import { computed, reactive } from 'vue'
import { apiMessage, fetchHotspot } from '../api/client'
import type { HotspotCell, HotspotPayload } from '../types'
import { setOrigin, state } from './planner'

export type HotspotFilter = 'all' | 'hotspot'

export const hotspotState = reactive({
  /** 全城 1 km 网格；由 /api/hotspot 异步载入（mock 模式读内置示例） */
  payload: null as HotspotPayload | null,
  cells: [] as HotspotCell[],
  selectedId: '',
  filter: 'all' as HotspotFilter,
  loading: false,
  error: '',
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

export const filteredHotspots = computed<HotspotCell[]>(() => {
  const cells = hotspotState.cells
  const list =
    hotspotState.filter === 'hotspot' ? cells.filter((cell) => cell.isHotspot) : cells
  // rank=0 表示样本不足 1 km，不参与榜单，排在最后
  return [...list].sort((a, b) => {
    const ra = a.rank > 0 ? a.rank : Number.MAX_SAFE_INTEGER
    const rb = b.rank > 0 ? b.rank : Number.MAX_SAFE_INTEGER
    return ra - rb
  })
})

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
