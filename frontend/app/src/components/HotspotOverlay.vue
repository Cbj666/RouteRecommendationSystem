<script setup lang="ts">
import { computed } from 'vue'
import { segmentColor } from '../lib/color'
import { project, type ViewBox } from '../lib/projection'
import type { HotspotCell } from '../mocks/hotspot'

const props = defineProps<{
  cells: HotspotCell[]
  view: ViewBox
  pixelBox: string
  selectedId: string
}>()

const ordered = computed(() => [...props.cells].sort((a, b) => a.score - b.score))

function cellPath(cell: HotspotCell): string {
  const halfW = cell.widthLng / 2
  const halfH = cell.heightLat / 2
  const [x0, y0] = project(props.view, cell.lng - halfW, cell.lat + halfH)
  const [x1, y1] = project(props.view, cell.lng + halfW, cell.lat - halfH)
  return `M${x0.toFixed(1)},${y0.toFixed(1)}L${x1.toFixed(1)},${y0.toFixed(1)}L${x1.toFixed(1)},${y1.toFixed(1)}L${x0.toFixed(1)},${y1.toFixed(1)}Z`
}

function fillOf(cell: HotspotCell): string {
  return segmentColor(cell.score, cell.grade)
}
</script>

<template>
  <svg
    class="hotspot-overlay"
    :viewBox="pixelBox"
    preserveAspectRatio="none"
    aria-hidden="true"
  >
    <g v-for="cell in ordered" :key="cell.id">
      <path
        :d="cellPath(cell)"
        :fill="fillOf(cell)"
        :fill-opacity="cell.id === selectedId ? 0.82 : cell.isHotspot ? 0.56 : 0.42"
        :stroke="cell.id === selectedId ? '#1f2a26' : cell.isHotspot ? '#15503c' : '#ffffff'"
        :stroke-width="cell.id === selectedId ? 2.2 : cell.isHotspot ? 1.1 : 0.45"
        :stroke-opacity="cell.id === selectedId ? 1 : 0.88"
        stroke-linejoin="round"
      />
      <path
        v-if="cell.id === selectedId"
        :d="cellPath(cell)"
        fill="none"
        stroke="#1f2a26"
        stroke-width="5"
        stroke-opacity="0.18"
        stroke-linejoin="round"
      />
    </g>
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
