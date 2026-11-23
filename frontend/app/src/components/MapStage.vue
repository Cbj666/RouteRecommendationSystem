<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadGeoJSON } from '../lib/geo'
import { MAP_H, MAP_W, project, unproject } from '../lib/projection'
import { SvgAdapter, type ComparisonMark } from '../map/svgAdapter'
import { layerGroupId } from '../map/layerConfig'
import { inspection, inspectRoad } from '../stores/inspection'
import {
  activeLayerIds,
  activeLoop,
  currentView,
  layerFileUrl,
  setLayerData,
  setLayerError,
  setLayerLoading,
  setManifest,
  setOrigin,
  state,
  type Origin,
} from '../stores/planner'
import type {
  AnyGeometry,
  GeoManifest,
  LayerCollection,
  LayerProps,
  MapLayerDef,
} from '../types'

const props = defineProps<{ comparison?: ComparisonMark[]; browse?: boolean }>()
const emit = defineEmits<{ pick: [origin: Origin] }>()
const host = ref<HTMLDivElement | null>(null)
const adapter = new SvgAdapter()
const inflight = new Set<string>()
let disposed = false

const maxZoom = props.comparison ? 32 : 8
const DRAG_THRESHOLD = 5
const viewport = ref({ x: 0, y: 0, zoom: 1 })
const dragging = ref(false)
const pointers = new Map<number, { x: number; y: number }>()
let suppressClick = false

function pointerCenter() {
  const [first, second] = pointers.values()
  if (!second) return { ...first!, distance: 0 }
  return {
    x: (first!.x + second.x) / 2,
    y: (first!.y + second.y) / 2,
    distance: Math.hypot(first!.x - second.x, first!.y - second.y),
  }
}

let gesture: { start: ReturnType<typeof pointerCenter>; view: typeof viewport.value } | null = null

function canvasPoint(clientX: number, clientY: number) {
  const rect = host.value?.getBoundingClientRect()
  if (!rect?.width || !rect.height) return null
  return {
    x: (clientX - rect.left) * MAP_W / rect.width,
    y: (clientY - rect.top) * MAP_H / rect.height,
  }
}

function updateViewport(x: number, y: number, zoom: number): void {
  viewport.value = {
    x: Math.min(Math.max(0, x), MAP_W - MAP_W / zoom),
    y: Math.min(Math.max(0, y), MAP_H - MAP_H / zoom),
    zoom,
  }
  adapter.setViewport(viewport.value.x, viewport.value.y, zoom)
}

function resetViewport(): void {
  updateViewport(0, 0, 1)
}

function zoomAt(
  factor: number,
  anchor = { x: MAP_W / 2, y: MAP_H / 2 },
): void {
  const view = viewport.value
  const zoom = Math.min(maxZoom, Math.max(1, view.zoom * factor))
  const delta = 1 / view.zoom - 1 / zoom
  updateViewport(view.x + anchor.x * delta, view.y + anchor.y * delta, zoom)
}

function onWheel(event: WheelEvent): void {
  const anchor = canvasPoint(event.clientX, event.clientY)
  if (!anchor || !event.deltaY) return
  zoomAt(event.deltaY < 0 ? 1.2 : 1 / 1.2, anchor)
}

function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0 || pointers.size >= 2) return
  if (pointers.size === 0) suppressClick = false
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  host.value?.setPointerCapture(event.pointerId)
  gesture = { start: pointerCenter(), view: viewport.value }
  if (pointers.size === 2) dragging.value = suppressClick = true
}

function onPointerMove(event: PointerEvent): void {
  if (!gesture || !pointers.has(event.pointerId)) return
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  const current = pointerCenter()
  const { start, view } = gesture
  if (!dragging.value && Math.hypot(current.x - start.x, current.y - start.y) < DRAG_THRESHOLD) return
  dragging.value = suppressClick = true
  const origin = canvasPoint(start.x, start.y)
  const destination = canvasPoint(current.x, current.y)
  if (!origin || !destination) return
  const factor = start.distance > 0 ? current.distance / start.distance : 1
  const zoom = Math.min(maxZoom, Math.max(1, view.zoom * factor))
  updateViewport(
    view.x + origin.x / view.zoom - destination.x / zoom,
    view.y + origin.y / view.zoom - destination.y / zoom,
    zoom,
  )
}

function onPointerEnd(event: PointerEvent): void {
  if (!pointers.delete(event.pointerId)) return
  gesture = pointers.size ? { start: pointerCenter(), view: viewport.value } : null
  if (!gesture) dragging.value = false
}

function applyRouteAndOrigin(): void {
  if (props.comparison) {
    adapter.setComparison(props.comparison)
    if (!props.comparison.some((mark) => mark.route)) return
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    for (const { origin, route } of props.comparison) {
      const points = [[origin.lng, origin.lat], ...(route?.geometry.coordinates ?? [])]
      for (const [lng, lat] of points) {
        const [x, y] = project(currentView.value, lng, lat)
        x0 = Math.min(x0, x)
        x1 = Math.max(x1, x)
        y0 = Math.min(y0, y)
        y1 = Math.max(y1, y)
      }
    }
    const zoom = Math.max(1, Math.min(maxZoom, MAP_W / (x1 - x0 + 24), MAP_H / (y1 - y0 + 24)))
    updateViewport((x0 + x1 - MAP_W / zoom) / 2, (y0 + y1 - MAP_H / zoom) / 2, zoom)
    return
  }
  adapter.setRoute(props.browse ? null : activeLoop.value)
  // 只有“地图选点”（自定义起点）才画标记；预设起点保持旧行为
  adapter.setOrigin(!props.browse ? state.origin : null)
}

function applyInspection(): void {
  if (props.comparison) return
  const road = props.browse ? inspection.selected : null
  adapter.highlightRoad(road?.geometry.coordinates ?? null)
  adapter.setToilets(inspection.toiletsEnabled ? inspection.toilets : null)
}

/**
 * 把 store 里“当前应显示”的图层同步到 SVG：
 * - 启用且数据已加载 → 渲染（或按新 view 重投影，adapter 内部去重）；
 * - 停用 → 移除整个 <g>；
 * - 路网三变体共用 data-layer="roads"，只渲染 activeRoadLayerId。
 */
function syncLayers(): void {
  const manifest = state.manifest
  if (!manifest) return
  const active = new Set(visibleLayerIds())
  adapter.setView(currentView.value, state.extent)

  const wanted = new Map<string, MapLayerDef>()
  for (const def of manifest.layers) {
    if (active.has(def.id)) wanted.set(layerGroupId(def), def)
  }

  for (const def of manifest.layers) {
    const gid = layerGroupId(def)
    const want = wanted.get(gid)
    if (!want) {
      adapter.clearLayer(gid)
      continue
    }
    if (want.id !== def.id) continue
    const data = state.layerData[def.id]
    if (data) adapter.setLayer(def, data)
  }
  applyInspection()
}

/** 只请求当前激活但还没缓存的图层（其余首次开启时才懒加载） */
function ensureActiveLayers(): void {
  const manifest = state.manifest
  if (!manifest) return
  const active = new Set(visibleLayerIds())
  for (const def of manifest.layers) {
    if (active.has(def.id) && !state.layerData[def.id]) void loadLayer(def)
  }
}

function visibleLayerIds(): string[] {
  return props.comparison
    ? activeLayerIds.value.filter((id) => ['water', 'green', 'boundary'].includes(id))
    : activeLayerIds.value
}

async function loadLayer(def: MapLayerDef): Promise<void> {
  if (state.layerData[def.id] || inflight.has(def.id)) return
  inflight.add(def.id)
  setLayerLoading(def.id, true)
  try {
    const data = await loadGeoJSON<LayerProps, AnyGeometry>(layerFileUrl(def.file))
    if (disposed) return
    setLayerData(def.id, data as LayerCollection)
    setLayerError('')
    syncLayers()
  } catch (e) {
    if (disposed) return
    setLayerError(`图层「${def.label}」加载失败：${(e as Error).message}`)
  } finally {
    inflight.delete(def.id)
    if (!disposed) setLayerLoading(def.id, false)
  }
}

/** 地图点击选起点：画布像素 → WGS84（用当前 view，全城也能选准） */
function onCanvasClick(e: MouseEvent): void {
  if (suppressClick) return
  const point = canvasPoint(e.clientX, e.clientY)
  if (!point) return
  const { x, y, zoom } = viewport.value
  const [lng, lat] = unproject(currentView.value, x + point.x / zoom, y + point.y / zoom)
  if (props.browse) { void inspectRoad(lng, lat); return }
  const origin = { name: '地图选点', lng: Number(lng.toFixed(6)), lat: Number(lat.toFixed(6)) }
  if (props.comparison) emit('pick', origin)
  else setOrigin(origin, 'custom')
}

onMounted(async () => {
  if (!host.value) return
  adapter.mount(host.value)
  adapter.setView(currentView.value, state.extent)
  if (state.manifest) {
    syncLayers()
    ensureActiveLayers()
    applyRouteAndOrigin()
    return
  }
  try {
    const res = await fetch('/geo/manifest.json')
    if (!res.ok) throw new Error(`/geo/manifest.json → HTTP ${res.status}`)
    const manifest = (await res.json()) as GeoManifest
    if (disposed) return
    setManifest(manifest)
    state.mapReady = true
    syncLayers()
    ensureActiveLayers()
    applyRouteAndOrigin()
  } catch (e) {
    state.mapError = (e as Error).message
  }
})

watch([activeLayerIds, currentView, () => state.extent, () => state.manifest], () => {
  syncLayers()
  ensureActiveLayers()
  if (props.comparison && state.tab === 'compare') applyRouteAndOrigin()
}, { flush: 'post' })

watch(activeLoop, applyRouteAndOrigin, { flush: 'post' })
watch(() => props.browse, () => { applyRouteAndOrigin(); applyInspection() }, { flush: 'post' })
watch(() => [inspection.selected, inspection.toilets, inspection.toiletsEnabled], applyInspection, { flush: 'post' })
watch(() => props.comparison, applyRouteAndOrigin, { flush: 'post' })
watch(() => state.extent, resetViewport)
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
  <div class="map-frame">
    <div
      ref="host"
      class="map-host"
      :class="{ dragging, zoomed: viewport.zoom > 1, browsing: browse }"
      role="img"
      :aria-label="browse ? '武汉慢跑适宜性地图，点击查询路段，滚轮缩放，放大后可拖动' : '武汉慢跑路线地图，点击选点，滚轮或双指缩放，放大后可拖动'"
      @click="onCanvasClick"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerEnd"
      @pointercancel="onPointerEnd"
      @lostpointercapture="onPointerEnd"
    ></div>
    <div class="map-controls glass" role="group" aria-label="地图缩放">
      <button type="button" aria-label="放大地图" title="放大地图" :disabled="viewport.zoom >= maxZoom" @click="zoomAt(1.5)">+</button>
      <button type="button" aria-label="缩小地图" title="缩小地图" :disabled="viewport.zoom <= 1" @click="zoomAt(1 / 1.5)">−</button>
      <button type="button" aria-label="复位地图" title="复位地图" :disabled="viewport.zoom <= 1" @click="resetViewport">复位</button>
    </div>
  </div>
</template>

<style scoped>
.map-frame,
.map-host {
  position: absolute;
  inset: 0;
}

.map-host.browsing:not(.zoomed) { cursor: default; }

.map-frame {
  z-index: 0;
  background: var(--bg);
  overflow: hidden;
}

.map-host {
  cursor: crosshair;
  touch-action: none;
  user-select: none;
}

.map-host.zoomed {
  cursor: grab;
}

.map-host.dragging {
  cursor: grabbing;
}

.map-host :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}

.map-controls {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
}

.map-controls button {
  min-width: 44px;
  min-height: 44px;
  padding: 0 8px;
  font-size: 14px;
}

.map-controls button + button {
  border-left: 1px solid var(--line);
}

.map-controls button:disabled {
  opacity: 0.4;
}
</style>
