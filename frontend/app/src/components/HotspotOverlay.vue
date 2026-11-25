<script setup lang="ts">
import { computed } from 'vue'
import { segmentColor } from '../lib/color'
import { project, type ViewBox } from '../lib/projection'
import type { HotspotCell } from '../types'

const props = defineProps<{
  cells: HotspotCell[]
  view: ViewBox
  pixelBox: string
  selectedId: string
}>()

/** 按分数从低到高画，避免高分格被低分格盖住 */
const ordered = computed(() => [...props.cells].sort((a, b) => a.score - b.score))

const selectedCell = computed(
  () => props.cells.find((cell) => cell.id === props.selectedId) ?? null,
)

/**
 * 全城上千个格子逐个建 <path> 会产生同样多的 DOM 节点，
 * 这里按填充色合并成「每种档次一条 path」，既快又不会出现白色接缝。
 */
interface Layer {
  fill: string
  d: string
}

function grouped(cells: HotspotCell[]): Layer[] {
  const groups = new Map<string, string[]>()
  for (const cell of cells) {
    const fill = segmentColor(cell.score, cell.grade)
    const paths = groups.get(fill) ?? []
    paths.push(cellPath(cell))
    groups.set(fill, paths)
  }
  return [...groups].map(([fill, paths]) => ({ fill, d: paths.join('') }))
}

const baseLayers = computed(() => grouped(ordered.value.filter((cell) => !cell.isHotspot)))
const hotLayers = computed(() => grouped(ordered.value.filter((cell) => cell.isHotspot)))

function cellPath(cell: HotspotCell): string {
  const halfW = cell.widthLng / 2
  const halfH = cell.heightLat / 2
  const [x0, y0] = project(props.view, cell.lng - halfW, cell.lat + halfH)
  const [x1, y1] = project(props.view, cell.lng + halfW, cell.lat - halfH)
  // 相邻格各扩 0.25px，消除缩放时的亚像素白缝；数值再大就会看起来像格间留了缓冲带
  const xa = (Math.min(x0, x1) - 0.25).toFixed(1)
  const xb = (Math.max(x0, x1) + 0.25).toFixed(1)
  const ya = (Math.min(y0, y1) - 0.25).toFixed(1)
  const yb = (Math.max(y0, y1) + 0.25).toFixed(1)
  return `M${xa},${ya}L${xb},${ya}L${xb},${yb}L${xa},${yb}Z`
}

const selectedPath = computed(() => (selectedCell.value ? cellPath(selectedCell.value) : ''))
</script>

<template>
  <svg
    class="hotspot-overlay"
    :viewBox="pixelBox"
    preserveAspectRatio="none"
    :data-cells="cells.length"
    aria-hidden="true"
  >
    <path
      v-for="layer in baseLayers"
      :key="'base-' + layer.fill"
      :d="layer.d"
      :fill="layer.fill"
      fill-opacity="0.38"
      stroke="none"
      shape-rendering="crispEdges"
    />
    <path
      v-for="layer in hotLayers"
      :key="'hot-' + layer.fill"
      :d="layer.d"
      :fill="layer.fill"
      fill-opacity="0.62"
      stroke="none"
      shape-rendering="crispEdges"
    />
    <path
      v-if="selectedPath"
      :d="selectedPath"
      fill="none"
      stroke="#1f2a26"
      stroke-width="2.4"
      stroke-linejoin="round"
    />
  </svg>
</template>

<style scoped>
.hotspot-overlay {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
