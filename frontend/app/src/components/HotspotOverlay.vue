<script setup lang="ts">
import { computed } from 'vue'
import { GRADE_BINS, ramp } from '../lib/color'
import { MAP_H, MAP_W, project, type ViewBox } from '../lib/projection'
import type { HotspotCell } from '../types'
import type { RegionShape } from '../stores/hotspot'

const props = defineProps<{
  cells: HotspotCell[]
  view: ViewBox
  pixelBox: string
  selectedId: string
  region?: RegionShape | null
  draft?: RegionShape | null
}>()

/** 按分数从低到高画，避免高分格被低分格盖住 */
const ordered = computed(() => [...props.cells].sort((a, b) => a.score - b.score))

const selectedCell = computed(
  () => props.cells.find((cell) => cell.id === props.selectedId) ?? null,
)

/**
 * 全城上千个格子逐个建 <path> 会产生同样多的 DOM 节点，
 * 这里按「量化后的连续色阶」合并成几十条 path（不按五档离散分桶），
 * 再由 <filter> 做一次高斯模糊，颜色在格间平滑过渡；方框边线另画一层。
 */
interface Layer {
  fill: string
  d: string
}

/** 色阶量化级数：越多越平滑，合并成的 path 也越多 */
const RAMP_STEPS = 28

/**
 * 把分数映射到色带上，且让五档分界正好落在 0/0.25/0.5/0.75/1：
 * 图例的五种颜色仍然对得上，但档内连续过渡，不再是一块块跳色。
 */
function scoreT(score: number): number {
  if (score <= GRADE_BINS[0]) return Math.max(0, score / GRADE_BINS[0]) * 0.25
  for (let i = 1; i < GRADE_BINS.length; i++) {
    const lo = GRADE_BINS[i - 1]
    const hi = GRADE_BINS[i]
    if (score <= hi) return i * 0.25 + ((score - lo) / (hi - lo)) * 0.25
  }
  return 1
}

function scoreColor(score: number): string {
  return ramp(Math.round(scoreT(score) * RAMP_STEPS) / RAMP_STEPS)
}

function grouped(cells: HotspotCell[]): Layer[] {
  const groups = new Map<string, string[]>()
  for (const cell of cells) {
    const fill = scoreColor(cell.score)
    const paths = groups.get(fill) ?? []
    paths.push(cellPath(cell))
    groups.set(fill, paths)
  }
  return [...groups].map(([fill, paths]) => ({ fill, d: paths.join('') }))
}

const baseLayers = computed(() => grouped(ordered.value.filter((cell) => !cell.isHotspot)))
const hotLayers = computed(() => grouped(ordered.value.filter((cell) => cell.isHotspot)))

/** 所有格子的边框合成一条 path，作为「方框」的细线，压住模糊后的颜色场 */
const gridPath = computed(() => {
  const parts: string[] = []
  for (const cell of props.cells) {
    const halfW = cell.widthLng / 2
    const halfH = cell.heightLat / 2
    const [x0, y0] = project(props.view, cell.lng - halfW, cell.lat + halfH)
    const [x1, y1] = project(props.view, cell.lng + halfW, cell.lat - halfH)
    const xa = Math.min(x0, x1).toFixed(1)
    const xb = Math.max(x0, x1).toFixed(1)
    const ya = Math.min(y0, y1).toFixed(1)
    const yb = Math.max(y0, y1).toFixed(1)
    parts.push(`M${xa},${ya}H${xb}V${yb}H${xa}Z`)
  }
  return parts.join('')
})

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

/* ------------------------------------------------------------------
 * 区域筛选：矩形 / 圆（几何在经纬度上，画到画布再换算成像素）
 * ------------------------------------------------------------------ */

const METERS_PER_DEG_LAT = 111_320

function rectPath(region: Extract<RegionShape, { kind: 'rect' }>): string {
  const lon0 = Math.min(region.lon0, region.lon1)
  const lon1 = Math.max(region.lon0, region.lon1)
  const lat0 = Math.min(region.lat0, region.lat1)
  const lat1 = Math.max(region.lat0, region.lat1)
  const [xa, ya] = project(props.view, lon0, lat1)
  const [xb, yb] = project(props.view, lon1, lat0)
  return `M${xa.toFixed(1)},${ya.toFixed(1)}H${xb.toFixed(1)}V${yb.toFixed(1)}H${xa.toFixed(1)}Z`
}

function circlePath(region: Extract<RegionShape, { kind: 'circle' }>): string {
  const [cx, cy] = project(props.view, region.lng, region.lat)
  const kx = Math.cos((region.lat * Math.PI) / 180)
  const pxPerLon = MAP_W / (props.view.lon1 - props.view.lon0)
  const pxPerLat = MAP_H / (props.view.lat1 - props.view.lat0)
  const rx = (region.radiusM / (METERS_PER_DEG_LAT * kx)) * pxPerLon
  const ry = (region.radiusM / METERS_PER_DEG_LAT) * pxPerLat
  if (!(rx > 0) || !(ry > 0)) return ''
  return [
    `M${(cx - rx).toFixed(1)},${cy.toFixed(1)}`,
    `A${rx.toFixed(1)},${ry.toFixed(1)} 0 1 0 ${(cx + rx).toFixed(1)},${cy.toFixed(1)}`,
    `A${rx.toFixed(1)},${ry.toFixed(1)} 0 1 0 ${(cx - rx).toFixed(1)},${cy.toFixed(1)}`,
    'Z',
  ].join('')
}

function shapePath(shape: RegionShape | null | undefined): string {
  if (!shape) return ''
  return shape.kind === 'rect' ? rectPath(shape) : circlePath(shape)
}

const regionPath = computed(() => shapePath(props.region))
/** 区域之外的半透明遮罩：整块画布 + 区域形状（evenodd 挖洞） */
const veilPath = computed(() => {
  if (!regionPath.value) return ''
  return `M0,0H${MAP_W}V${MAP_H}H0Z${regionPath.value}`
})
const draftPath = computed(() => shapePath(props.draft))
</script>

<template>
  <svg
    class="hotspot-overlay"
    :viewBox="pixelBox"
    preserveAspectRatio="none"
    :data-cells="cells.length"
    aria-hidden="true"
  >
    <defs>
      <filter id="hotspot-smooth" x="-8%" y="-8%" width="116%" height="116%">
        <feGaussianBlur stdDeviation="3.2" />
      </filter>
    </defs>
    <g filter="url(#hotspot-smooth)" shape-rendering="geometricPrecision" style="mix-blend-mode: multiply">
      <path
        v-for="layer in baseLayers"
        :key="'base-' + layer.fill"
        :d="layer.d"
        :fill="layer.fill"
        fill-opacity="0.72"
        stroke="none"
      />
      <path
        v-for="layer in hotLayers"
        :key="'hot-' + layer.fill"
        :d="layer.d"
        :fill="layer.fill"
        fill-opacity="0.85"
        stroke="none"
      />
    </g>
    <path
      v-if="gridPath"
      :d="gridPath"
      fill="none"
      stroke="#1f2a26"
      stroke-opacity="0.14"
      stroke-width="1"
      vector-effect="non-scaling-stroke"
    />
    <path
      v-if="selectedPath"
      :d="selectedPath"
      fill="none"
      stroke="#1f2a26"
      stroke-width="2.4"
      stroke-linejoin="round"
    />
    <path
      v-if="veilPath"
      :d="veilPath"
      fill="#ffffff"
      fill-opacity="0.55"
      fill-rule="evenodd"
      stroke="none"
    />
    <path
      v-if="regionPath"
      :d="regionPath"
      fill="rgba(21, 80, 60, 0.10)"
      stroke="#15503c"
      stroke-width="1.6"
      stroke-dasharray="6 4"
      vector-effect="non-scaling-stroke"
      data-region="active"
    />
    <path
      v-if="draftPath"
      :d="draftPath"
      fill="rgba(21, 80, 60, 0.14)"
      stroke="#15503c"
      stroke-width="1.4"
      stroke-dasharray="4 3"
      vector-effect="non-scaling-stroke"
      data-region="draft"
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






