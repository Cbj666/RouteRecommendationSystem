<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { MAP_H, unproject } from '../lib/projection'
import HotspotDetails from './HotspotDetails.vue'
import HotspotLegend from './HotspotLegend.vue'
import HotspotOverlay from './HotspotOverlay.vue'
import HotspotRanking from './HotspotRanking.vue'
import MapStage from './MapStage.vue'
import FooterBar from './FooterBar.vue'
import StatusOverlay from './StatusOverlay.vue'
import {
  filteredHotspots,
  hotspotState,
  overlayCells,
  loadHotspot,
  selectHotspot,
  setDrawMode,
  setRegion,
  type RegionShape,
} from '../stores/hotspot'
import { currentView } from '../stores/planner'

const root = ref<HTMLElement | null>(null)
const pixelBox = ref('0 0 1600 1000')
const draft = ref<RegionShape | null>(null)
let frame: HTMLElement | null = null
let svg: SVGSVGElement | null = null
let observer: MutationObserver | null = null
let drawStart: { lng: number; lat: number; x: number; y: number } | null = null
let suppressNextClick = false

const METERS_PER_DEG_LAT = 111_320

function syncPixelBox(): void {
  if (svg) pixelBox.value = svg.getAttribute('viewBox') || '0 0 1600 1000'
}

function onMapClick(event: MouseEvent): void {
  if (suppressNextClick) {
    // 画完区域后的那一次 click 不当作选中格子
    suppressNextClick = false
    event.stopPropagation()
    event.preventDefault()
    return
  }
  const target = event.target as HTMLElement | null
  if (target?.closest('.map-controls')) return
  if (!frame || !svg) return

  // 热点页自己消费地图点击，避免 MapStage 把它当成“查询路段”。
  event.stopPropagation()
  event.preventDefault()

  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const vb = svg.viewBox.baseVal
  const x = vb.x + ((event.clientX - rect.left) / rect.width) * vb.width
  const y = vb.y + ((event.clientY - rect.top) / rect.height) * vb.height
  const [lng, lat] = unproject(currentView.value, x, y)

  const hit = [...filteredHotspots.value]
    .reverse()
    .find(
      (cell) =>
        Math.abs(lng - cell.lng) <= cell.widthLng / 2 &&
        Math.abs(lat - cell.lat) <= cell.heightLat / 2,
    )
  if (hit) selectHotspot(hit.id)
}

/** 屏幕坐标 → 经纬度（用 svg 当前 viewBox，与格子的投影保持一致） */
function pointerLngLat(event: PointerEvent): { lng: number; lat: number; x: number; y: number } | null {
  if (!svg) return null
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  const vb = svg.viewBox.baseVal
  const x = vb.x + ((event.clientX - rect.left) / rect.width) * vb.width
  const y = vb.y + ((event.clientY - rect.top) / rect.height) * vb.height
  const [lng, lat] = unproject(currentView.value, x, y)
  return { lng, lat, x, y }
}

/** 画布单位 → 米（纬度方向；经度按 cos 修正后一致） */
function metersPerUnit(): number {
  const view = currentView.value
  return (METERS_PER_DEG_LAT * (view.lat1 - view.lat0)) / MAP_H
}

function onDrawDown(event: PointerEvent): void {
  if (hotspotState.drawMode === 'none') return
  if (event.button !== 0) return
  const point = pointerLngLat(event)
  if (!point) return
  // 捕获阶段拦下，避免 MapStage 把它当成平移
  event.stopPropagation()
  event.preventDefault()
  drawStart = point
  draft.value =
    hotspotState.drawMode === 'rect'
      ? { kind: 'rect', lon0: point.lng, lat0: point.lat, lon1: point.lng, lat1: point.lat }
      : { kind: 'circle', lng: point.lng, lat: point.lat, radiusM: 0 }
  window.addEventListener('pointermove', onDrawMove, true)
  window.addEventListener('pointerup', onDrawUp, true)
}

function onDrawMove(event: PointerEvent): void {
  if (!drawStart || !draft.value) return
  const point = pointerLngLat(event)
  if (!point) return
  event.stopPropagation()
  event.preventDefault()
  if (draft.value.kind === 'rect') {
    draft.value = { kind: 'rect', lon0: drawStart.lng, lat0: drawStart.lat, lon1: point.lng, lat1: point.lat }
    return
  }
  const distance = Math.hypot(point.x - drawStart.x, point.y - drawStart.y) * metersPerUnit()
  draft.value = { kind: 'circle', lng: drawStart.lng, lat: drawStart.lat, radiusM: distance }
}

function onDrawUp(event: PointerEvent): void {
  window.removeEventListener('pointermove', onDrawMove, true)
  window.removeEventListener('pointerup', onDrawUp, true)
  if (!drawStart || !draft.value) {
    drawStart = null
    draft.value = null
    return
  }
  event.stopPropagation()
  const shape = draft.value
  drawStart = null
  draft.value = null
  const bigEnough =
    shape.kind === 'rect'
      ? Math.abs(shape.lon1 - shape.lon0) * 110_000 > 300 &&
        Math.abs(shape.lat1 - shape.lat0) * 110_000 > 300
      : shape.radiusM > 300
  if (!bigEnough) {
    setDrawMode('none')
    return
  }
  suppressNextClick = true
  setDrawMode('none')
  setRegion(shape)
}

function cancelDraw(): void {
  setDrawMode('none')
  draft.value = null
  drawStart = null
  window.removeEventListener('pointermove', onDrawMove, true)
  window.removeEventListener('pointerup', onDrawUp, true)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && (hotspotState.drawMode !== 'none' || hotspotState.region)) {
    cancelDraw()
    if (hotspotState.region) setRegion(null)
  }
}

onMounted(() => {
  // 网格数据来自后端（/api/hotspot）或静态兜底；失败时页面显示错误态。
  void loadHotspot()
  frame = (root.value?.querySelector('.map-frame') as HTMLElement | null) ?? null
  svg = (frame?.querySelector('svg') as SVGSVGElement | null) ?? null
  if (frame) {
    // 覆盖层跟随地图框，而不是整个 stage；否则移动端会按整页高度拉伸。
    if (getComputedStyle(frame).position === 'static') frame.style.position = 'relative'
    const overlay = root.value?.querySelector('.hotspot-overlay') as SVGElement | null
    const controls = frame.querySelector('.map-controls')
    if (overlay) frame.insertBefore(overlay, controls)
    frame.addEventListener('click', onMapClick, true)
    frame.addEventListener('pointerdown', onDrawDown, true)
  }
  window.addEventListener('keydown', onKeydown)
  if (svg) {
    syncPixelBox()
    observer = new MutationObserver(syncPixelBox)
    observer.observe(svg, { attributes: true, attributeFilter: ['viewBox'] })
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  frame?.removeEventListener('click', onMapClick, true)
  frame?.removeEventListener('pointerdown', onDrawDown, true)
  window.removeEventListener('keydown', onKeydown)
  cancelDraw()
})
</script>

<template>
  <div ref="root" class="hotspot-page">
    <MapStage :browse="true" :pois="false" />
    <HotspotOverlay
      :cells="overlayCells"
      :view="currentView"
      :pixel-box="pixelBox"
      :selected-id="hotspotState.selectedId"
      :region="hotspotState.region"
      :draft="draft"
    />
    <HotspotRanking />
    <HotspotDetails />
    <HotspotLegend />
    <FooterBar />
    <StatusOverlay />
  </div>
</template>

<style scoped>
.hotspot-page {
  display: contents;
}

@media (max-width: 1100px), (max-height: 680px) {
  .hotspot-page :deep(.hotspot-rank),
  .hotspot-page :deep(.hotspot-detail),
  .hotspot-page :deep(.hotspot-legend) {
    position: static;
    inset: auto;
    width: auto;
    max-height: none;
    overflow: visible;
    padding: 16px;
  }

  .hotspot-page :deep(.hotspot-rank) { order: 1; }
  .hotspot-page :deep(.hotspot-detail) { order: 2; }
  .hotspot-page :deep(.hotspot-legend) { order: 3; }
  .hotspot-page :deep(.foot) { order: 4; }
}
</style>
