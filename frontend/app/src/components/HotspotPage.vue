<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { unproject } from '../lib/projection'
import HotspotDetails from './HotspotDetails.vue'
import HotspotLegend from './HotspotLegend.vue'
import HotspotOverlay from './HotspotOverlay.vue'
import HotspotRanking from './HotspotRanking.vue'
import MapStage from './MapStage.vue'
import FooterBar from './FooterBar.vue'
import StatusOverlay from './StatusOverlay.vue'
import { filteredHotspots, hotspotState, selectHotspot } from '../stores/hotspot'
import { currentView } from '../stores/planner'

const root = ref<HTMLElement | null>(null)
const pixelBox = ref('0 0 1600 1000')
let frame: HTMLElement | null = null
let svg: SVGSVGElement | null = null
let observer: MutationObserver | null = null

function syncPixelBox(): void {
  if (svg) pixelBox.value = svg.getAttribute('viewBox') || '0 0 1600 1000'
}

function onMapClick(event: MouseEvent): void {
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

onMounted(() => {
  frame = (root.value?.querySelector('.map-frame') as HTMLElement | null) ?? null
  svg = (frame?.querySelector('svg') as SVGSVGElement | null) ?? null
  if (frame) {
    // 覆盖层跟随地图框，而不是整个 stage；否则移动端会按整页高度拉伸。
    if (getComputedStyle(frame).position === 'static') frame.style.position = 'relative'
    const overlay = root.value?.querySelector('.hotspot-overlay') as SVGElement | null
    const controls = frame.querySelector('.map-controls')
    if (overlay) frame.insertBefore(overlay, controls)
  }
  if (svg) {
    syncPixelBox()
    observer = new MutationObserver(syncPixelBox)
    observer.observe(svg, { attributes: true, attributeFilter: ['viewBox'] })
  }
  frame?.addEventListener('click', onMapClick, true)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  frame?.removeEventListener('click', onMapClick, true)
})
</script>

<template>
  <div ref="root" class="hotspot-page">
    <MapStage :browse="true" />
    <HotspotOverlay
      :cells="filteredHotspots"
      :view="currentView"
      :pixel-box="pixelBox"
      :selected-id="hotspotState.selectedId"
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
