import { computed, reactive } from 'vue'
import { HOTSPOT_CELLS, type HotspotCell } from '../mocks/hotspot'
import { setOrigin, state } from './planner'

export type HotspotFilter = 'all' | 'hotspot'

export const hotspotState = reactive({
  selectedId: HOTSPOT_CELLS[0]?.id ?? '',
  filter: 'all' as HotspotFilter,
})

export const filteredHotspots = computed<HotspotCell[]>(() => {
  const list =
    hotspotState.filter === 'hotspot'
      ? HOTSPOT_CELLS.filter((cell) => cell.isHotspot)
      : HOTSPOT_CELLS
  return [...list].sort((a, b) => a.rank - b.rank)
})

export const selectedHotspot = computed<HotspotCell | null>(
  () => HOTSPOT_CELLS.find((cell) => cell.id === hotspotState.selectedId) ?? null,
)

export const hotspotCount = computed(
  () => HOTSPOT_CELLS.filter((cell) => cell.isHotspot).length,
)

export function selectHotspot(id: string): void {
  if (HOTSPOT_CELLS.some((cell) => cell.id === id)) hotspotState.selectedId = id
}

export function setHotspotFilter(filter: HotspotFilter): void {
  hotspotState.filter = filter
  if (!filteredHotspots.value.some((cell) => cell.id === hotspotState.selectedId)) {
    hotspotState.selectedId = filteredHotspots.value[0]?.id ?? ''
  }
}

/** 只回填起点并跳到环线页，不自动生成路线（与任务书交互约定一致）。 */
export function useHotspotAsOrigin(): void {
  const cell = selectedHotspot.value
  if (!cell) return
  setOrigin(
    {
      name: `${cell.name}（热点网格）`,
      lng: cell.lng,
      lat: cell.lat,
    },
    'preset',
  )
  state.tab = 'loops'
}
