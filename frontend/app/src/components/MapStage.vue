<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadGeoJSON } from '../lib/geo'
import { MAP_H, MAP_W, unproject } from '../lib/projection'
import { DRAW_ORIGIN_MARKER, DRAW_WATER_GREEN } from '../map/config'
import { SvgAdapter } from '../map/svgAdapter'
import { activeLoop, setOrigin, state } from '../stores/planner'
import type {
  LineLikeGeometry,
  PolygonLikeGeometry,
  SegmentGeoCollection,
  SegmentProps,
  WaterGreenCollection,
  WaterGreenProps,
} from '../types'

const host = ref<HTMLDivElement | null>(null)
const adapter = new SvgAdapter()
let disposed = false

function applyRouteAndOrigin(): void {
  adapter.setRoute(activeLoop.value)
  const showMarker = DRAW_ORIGIN_MARKER || state.originSource === 'custom'
  adapter.setOrigin(showMarker ? state.origin : null)
}

/** 地图点击选起点：画布像素 → WGS84（无 AK 时也能选任意点） */
function onCanvasClick(e: MouseEvent): void {
  if (!host.value) return
  const r = host.value.getBoundingClientRect()
  if (r.width === 0 || r.height === 0) return
  const x = ((e.clientX - r.left) / r.width) * MAP_W
  const y = ((e.clientY - r.top) / r.height) * MAP_H
  const [lng, lat] = unproject(x, y)
  setOrigin(
    {
      name: '地图选点',
      lng: Number(lng.toFixed(6)),
      lat: Number(lat.toFixed(6)),
    },
    'custom',
  )
}

onMounted(async () => {
  if (!host.value) return
  adapter.mount(host.value)
  try {
    const segments = await loadGeoJSON<SegmentProps, LineLikeGeometry>(
      '/geo/segments_city.geojson',
    )
    let waterGreen: WaterGreenCollection | undefined
    if (DRAW_WATER_GREEN) {
      waterGreen = await loadGeoJSON<WaterGreenProps, PolygonLikeGeometry>(
        '/geo/water_green.geojson',
      )
    }
    if (disposed) return
    adapter.setBase(segments as SegmentGeoCollection, waterGreen)
    state.mapReady = true
    applyRouteAndOrigin()
  } catch (e) {
    state.mapError = (e as Error).message
  }
})

watch(activeLoop, applyRouteAndOrigin, { flush: 'post' })
watch(
  () => [state.origin.lng, state.origin.lat, state.originSource],
  applyRouteAndOrigin,
  { flush: 'post' },
)

onBeforeUnmount(() => {
  disposed = true
  adapter.destroy()
})
</script>

<template>
  <div
    ref="host"
    class="map-host"
    role="img"
    aria-label="武汉慢跑适宜性地图与推荐路线，点击地图可设置起点"
    title="点击地图设置起点"
    @click="onCanvasClick"
  ></div>
</template>

<style scoped>
.map-host {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: var(--bg);
  cursor: crosshair;
}

.map-host :deep(svg) {
  display: block;
}
</style>
