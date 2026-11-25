<script setup lang="ts">
<<<<<<< HEAD
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
=======
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchSegments } from '../api/client'
>>>>>>> 5144d797b2e0359e5163dd17428bfe917c0690eb
import { loadGeoJSON } from '../lib/geo'
import { MAP_H, MAP_W, project, unproject } from '../lib/projection'
import { DETAIL_WIDTH_KM, SvgAdapter } from '../map/svgAdapter'
import { layerGroupId } from '../map/layerConfig'
import { inspection, inspectRoad } from '../stores/inspection'
import {
  activeLayerIds,
  activeLoop,
  currentView,
  layerFileUrl,
  pickOriginOrDest,
  roadSuitabilityEnabled,
  setLayerData,
  setLayerError,
  setExtent,
  setLayerLoading,
  setManifest,
  state,
} from '../stores/planner'
import type {
  AnyGeometry,
  GeoManifest,
  LayerCollection,
  LayerProps,
  LoopFeature,
  MapLayerDef,
  Place,
} from '../types'

const props = defineProps<{ browse?: boolean }>()
const host = ref<HTMLDivElement | null>(null)
const adapter = new SvgAdapter()
const inflight = new Set<string>()
let disposed = false

/** 全市 base view 宽度约 260 km；zoom=128 时约 2 km（街区级细度） */
const MAX_ZOOM = 128
const DRAG_THRESHOLD = 5
const DETAIL_DEBOUNCE_MS = 250
const MAX_CACHE_TILES = 8

const viewport = ref({ x: 0, y: 0, zoom: 1 })
const dragging = ref(false)
const pointers = new Map<number, { x: number; y: number }>()
let suppressClick = false

interface SegmentCacheEntry {
  truncated: boolean
  data: LayerCollection | null
}
const segmentCache = new Map<string, SegmentCacheEntry>()
let segmentsTimer: number | null = null
let segmentsAbort: AbortController | null = null
let symbolTimer: number | null = null

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
    x: ((clientX - rect.left) * MAP_W) / rect.width,
    y: ((clientY - rect.top) * MAP_H) / rect.height,
  }
}

function updateSelectedPoiPosition(): void {
  const poi = inspection.selectedPoi
  if (!poi) return
  const [svgX, svgY] = project(currentView.value, poi.lng, poi.lat)
  const { x, y, zoom } = viewport.value
  poi.screenX = (svgX - x) * zoom
  poi.screenY = (svgY - y) * zoom
}

function updateViewport(x: number, y: number, zoom: number, immediateSymbols = false): void {
  const clampedZoom = Math.min(MAX_ZOOM, Math.max(1, zoom))
  const clampedX = Math.min(Math.max(0, x), MAP_W - MAP_W / clampedZoom)
  const clampedY = Math.min(Math.max(0, y), MAP_H - MAP_H / clampedZoom)
  viewport.value = { x: clampedX, y: clampedY, zoom: clampedZoom }
  adapter.setViewport(clampedX, clampedY, clampedZoom)
  updateSelectedPoiPosition()
  // 视野已改变时，旧请求不能再覆盖当前地图（包括命中缓存的情况）。
  segmentsAbort?.abort()
  segmentsAbort = null
  state.roadsDetailLoading = false

  if (immediateSymbols) {
    if (symbolTimer !== null) {
      window.clearTimeout(symbolTimer)
      symbolTimer = null
    }
    adapter.refreshViewportSymbols()
  } else if (!dragging.value) {
    if (symbolTimer !== null) window.clearTimeout(symbolTimer)
    symbolTimer = window.setTimeout(() => {
      symbolTimer = null
      if (!disposed) adapter.refreshViewportSymbols()
    }, 90)
  }
  if (!dragging.value) scheduleViewportSegments()
}

function resetViewport(): void {
  inspection.selectedPoi = null
  updateViewport(0, 0, 1, true)
}

function zoomAt(
  factor: number,
  anchor = { x: MAP_W / 2, y: MAP_H / 2 },
  immediateSymbols = false,
): void {
  const view = viewport.value
  const zoom = Math.min(MAX_ZOOM, Math.max(1, view.zoom * factor))
  const delta = 1 / view.zoom - 1 / zoom
  updateViewport(view.x + anchor.x * delta, view.y + anchor.y * delta, zoom, immediateSymbols)
}

/** F1 视野联动：生成路线后自动缩放到路线范围，避开左右面板 */
function fitToRoute(loop: LoopFeature): void {
  const coords = loop.geometry.coordinates
  if (!coords || coords.length === 0) return

  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const [lng, lat] of coords) {
    const [px, py] = project(currentView.value, lng, lat)
    if (px < x0) x0 = px
    if (px > x1) x1 = px
    if (py < y0) y0 = py
    if (py > y1) y1 = py
  }
  if (!Number.isFinite(x0)) return

  const isMobile = window.matchMedia('(max-width: 1100px), (max-height: 680px)').matches
  const padLeft = !isMobile && !props.browse ? 360 : 80
  const padRight = !isMobile && !props.browse ? 380 : 80
  const padTop = !isMobile ? 105 : 60
  const padBottom = !isMobile ? 110 : 60

  const availW = Math.max(200, MAP_W - padLeft - padRight)
  const availH = Math.max(200, MAP_H - padTop - padBottom)
  const boxW = Math.max(6, x1 - x0)
  const boxH = Math.max(6, y1 - y0)

  const zoom = Math.min(
    MAX_ZOOM,
    Math.max(1, Math.min((availW * 0.82) / boxW, (availH * 0.82) / boxH)),
  )
  const midX = (x0 + x1) / 2
  const midY = (y0 + y1) / 2
  const targetCenterCanvasX = padLeft + availW / 2
  const targetCenterCanvasY = padTop + availH / 2

  updateViewport(
    midX - targetCenterCanvasX / zoom,
    midY - targetCenterCanvasY / zoom,
    zoom,
    true,
  )
}

/* ---------------- F1 按视口动态加载评分路段 + LRU 缓存 ---------------- */

function scheduleViewportSegments(): void {
  if (segmentsTimer !== null) window.clearTimeout(segmentsTimer)
  segmentsTimer = window.setTimeout(() => {
    segmentsTimer = null
    if (!disposed) void syncViewportSegments()
  }, DETAIL_DEBOUNCE_MS)
}

function quantizedQueryBBox(
  bbox: [number, number, number, number],
): { key: string; bbox: [number, number, number, number] } {
  const [minLng, minLat, maxLng, maxLat] = bbox
  // 可视范围外扩 20%（每侧外扩 10%）
  const padLng = (maxLng - minLng) * 0.1
  const padLat = (maxLat - minLat) * 0.1
  // 网格随缩放缩小，避免街区视野也查询至少 0.1×0.1 度。
  const span = Math.max(maxLng - minLng, maxLat - minLat)
  const step = span > 0.1 ? 0.05 : span > 0.02 ? 0.01 : 0.002
  const qMinLng = Math.floor((minLng - padLng) / step) * step
  const qMinLat = Math.floor((minLat - padLat) / step) * step
  const qMaxLng = Math.ceil((maxLng + padLng) / step) * step
  const qMaxLat = Math.ceil((maxLat + padLat) / step) * step
  const key = `${qMinLng.toFixed(3)},${qMinLat.toFixed(3)},${qMaxLng.toFixed(3)},${qMaxLat.toFixed(3)}`
  return {
    key,
    bbox: [
      Number(qMinLng.toFixed(3)),
      Number(qMinLat.toFixed(3)),
      Number(qMaxLng.toFixed(3)),
      Number(qMaxLat.toFixed(3)),
    ],
  }
}

function rememberSegmentTile(key: string, entry: SegmentCacheEntry): void {
  if (segmentCache.has(key)) segmentCache.delete(key)
  segmentCache.set(key, entry)
  while (segmentCache.size > MAX_CACHE_TILES) {
    const oldest = segmentCache.keys().next().value
    if (oldest !== undefined) segmentCache.delete(oldest)
    else break
  }
}

async function syncViewportSegments(): Promise<void> {
  if (!roadSuitabilityEnabled.value) {
    segmentsAbort?.abort()
    state.roadsDetailLoading = false
    state.roadsDetailed = false
    state.roadsTruncatedMsg = ''
    adapter.setDetailRoads(null)
    return
  }

  const widthKm = adapter.viewportWidthKm()
  if (widthKm > DETAIL_WIDTH_KM) {
    segmentsAbort?.abort()
    state.roadsDetailLoading = false
    state.roadsDetailed = false
    state.roadsTruncatedMsg = ''
    adapter.setDetailRoads(null)
    return
  }

  const { key, bbox } = quantizedQueryBBox(adapter.viewportBBox())
  const cached = segmentCache.get(key)
  if (cached) {
    // 命中 LRU 缓存，刷新顺序，不重复发请求
    rememberSegmentTile(key, cached)
    state.roadsDetailLoading = false
    if (cached.truncated) {
      state.roadsTruncatedMsg = '当前范围路段过多，已简化显示'
      state.roadsDetailed = false
      adapter.setDetailRoads(null)
    } else if (cached.data && cached.data.features.length > 0) {
      state.roadsTruncatedMsg = ''
      state.roadsDetailed = true
      adapter.setDetailRoads(cached.data)
    } else {
      state.roadsTruncatedMsg = ''
      state.roadsDetailed = false
      adapter.setDetailRoads(null)
    }
    return
  }

  segmentsAbort?.abort()
  const controller = new AbortController()
  segmentsAbort = controller
  state.roadsDetailLoading = true

  try {
    const res = await fetchSegments(bbox, 40000, controller.signal)
    if (disposed || controller.signal.aborted) return
    if (res.truncated) {
      rememberSegmentTile(key, { truncated: true, data: null })
      state.roadsTruncatedMsg = '当前范围路段过多，已简化显示'
      state.roadsDetailed = false
      adapter.setDetailRoads(null)
    } else {
      const layerData = res as unknown as LayerCollection
      rememberSegmentTile(key, { truncated: false, data: layerData })
      state.roadsTruncatedMsg = ''
      if (layerData.features.length > 0) {
        state.roadsDetailed = true
        adapter.setDetailRoads(layerData)
      } else {
        state.roadsDetailed = false
        adapter.setDetailRoads(null)
      }
    }
  } catch (e) {
    if (disposed || controller.signal.aborted || (e as Error).name === 'AbortError') return
    // 接口失败时保留概览层，不闪白、不死循环重试
    state.roadsDetailed = false
    adapter.setDetailRoads(null)
  } finally {
    if (!disposed && segmentsAbort === controller) {
      state.roadsDetailLoading = false
    }
  }
}

/* ---------------- 交互：缩放 / 拖拽 / 悬浮 / 点击 ---------------- */

function onWheel(event: WheelEvent): void {
  const anchor = canvasPoint(event.clientX, event.clientY)
  if (!anchor || !event.deltaY) return
  inspection.hoveredPoi = null
  zoomAt(event.deltaY < 0 ? 1.25 : 1 / 1.25, anchor)
}

function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0 || pointers.size >= 2) return
  if (pointers.size === 0) suppressClick = false
  if (segmentsTimer !== null) window.clearTimeout(segmentsTimer)
  segmentsTimer = null
  if (symbolTimer !== null) window.clearTimeout(symbolTimer)
  symbolTimer = null
  segmentsAbort?.abort()
  segmentsAbort = null
  state.roadsDetailLoading = false
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  host.value?.setPointerCapture(event.pointerId)
  gesture = { start: pointerCenter(), view: viewport.value }
  if (pointers.size === 2) dragging.value = suppressClick = true
}

function onPointerMove(event: PointerEvent): void {
  if (gesture && pointers.has(event.pointerId)) {
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
    const current = pointerCenter()
    const { start, view } = gesture
    if (!dragging.value && Math.hypot(current.x - start.x, current.y - start.y) < DRAG_THRESHOLD) {
      return
    }
    dragging.value = suppressClick = true
    inspection.hoveredPoi = null
    const origin = canvasPoint(start.x, start.y)
    const destination = canvasPoint(current.x, current.y)
    if (!origin || !destination) return
    const factor = start.distance > 0 ? current.distance / start.distance : 1
    const zoom = Math.min(MAX_ZOOM, Math.max(1, view.zoom * factor))
    updateViewport(
      view.x + origin.x / view.zoom - destination.x / zoom,
      view.y + origin.y / view.zoom - destination.y / zoom,
      zoom,
    )
    return
  }

  // 非拖拽时检测设施悬浮（运动场馆 / 公共厕所）
  const pt = canvasPoint(event.clientX, event.clientY)
  if (!pt) {
    inspection.hoveredPoi = null
    return
  }
  inspection.hoveredPoi = adapter.hitTestPoi(pt.x, pt.y, 8)
}

function onPointerEnd(event: PointerEvent): void {
  if (!pointers.delete(event.pointerId)) return
  gesture = pointers.size ? { start: pointerCenter(), view: viewport.value } : null
  if (!gesture) {
    if (dragging.value) adapter.refreshViewportSymbols()
    dragging.value = false
    scheduleViewportSegments()
  }
}

function onPointerLeave(): void {
  inspection.hoveredPoi = null
}

function onCanvasClick(e: MouseEvent): void {
  if (suppressClick) return
  const point = canvasPoint(e.clientX, e.clientY)
  if (!point) return
  const { x, y, zoom } = viewport.value
  const [lng, lat] = unproject(currentView.value, x + point.x / zoom, y + point.y / zoom)

  if (props.browse) {
    // 1. 放大状态下优先检测点击运动场馆 / 公厕（仅命中 8px 圆心内，不挡住周围路段点击）
    const poiHit = adapter.hitTestPoi(point.x, point.y, 8)
    if (poiHit) {
      inspection.selectedPoi = poiHit
      return
    }
    // 2. 整城视野下点击聚合圆平滑放大展开
    const clusterHit = adapter.hitTestCluster(point.x, point.y, 12)
    if (clusterHit) {
      inspection.selectedPoi = null
      zoomAt(2.8, point, true)
      return
    }
    inspection.selectedPoi = null
    void inspectRoad(lng, lat)
    return
  }
<<<<<<< HEAD
  adapter.setRoute(props.browse ? null : activeLoop.value)
  // 起点标记与搜索结果标记都只在“路线生成”页面显示
  adapter.setOrigin(!props.browse ? state.origin : null)
  adapter.setPlaces(placesVisible() ? state.places : [])
}

function placesVisible(): boolean {
  return !props.comparison && !props.browse && state.tab === 'loops'
}

/** 地图当前窗口（SVG 用户坐标）能否容纳某点；不能则说明需要换片区或平移。 */
function onCanvas(x: number, y: number): boolean {
  return x >= 0 && x <= MAP_W && y >= 0 && y <= MAP_H
}

/**
 * 搜索结果到达后把视野落到结果上。
 * 结果落在“中心片区”之外时先切全城，再按 bbox 居中缩放；只有 1 个结果时
 * 最多放到 3.2 倍，避免对着一个点糊到最大。
 */
function fitSearchPlaces(places: Place[]): void {
  if (!places.length || !placesVisible()) return
  const points = places.map((place) => project(currentView.value, place.lng, place.lat))
  if (points.some(([x, y]) => !onCanvas(x, y)) && state.extent === 'central') {
    setExtent('city')
    void nextTick(() => fitSearchPlaces(places))
    return
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const [x, y] of points) {
    x0 = Math.min(x0, x); x1 = Math.max(x1, x)
    y0 = Math.min(y0, y); y1 = Math.max(y1, y)
  }
  const pad = 56
  const zoom = Math.min(
    maxZoom,
    3.2,
    Math.max(1, Math.min((MAP_W - pad * 2) / Math.max(x1 - x0, 1), (MAP_H - pad * 2) / Math.max(y1 - y0, 1))),
  )
  updateViewport((x0 + x1) / 2 - MAP_W / (2 * zoom), (y0 + y1) / 2 - MAP_H / (2 * zoom), zoom)
}

/** 从下拉选中一个结果后：地图居中到该点（保持已放大的倍率，至少 2.4 倍）。 */
function focusPlace(place: Place): void {
  if (!placesVisible()) return
  const [x, y] = project(currentView.value, place.lng, place.lat)
  if (!onCanvas(x, y) && state.extent === 'central') {
    setExtent('city')
    void nextTick(() => focusPlace(place))
    return
  }
  const zoom = Math.min(maxZoom, Math.max(viewport.value.zoom, 2.4))
  updateViewport(x - MAP_W / (2 * zoom), y - MAP_H / (2 * zoom), zoom)
=======

  // 路线推荐页：点地图设起点（环线）或依次设 A / B（单行线）
  inspection.selectedPoi = null
  pickOriginOrDest(
    { name: '地图选点', lng: Number(lng.toFixed(6)), lat: Number(lat.toFixed(6)) },
    'custom',
  )
}

function inspectUnderlyingRoad(): void {
  const poi = inspection.selectedPoi
  if (!poi) return
  inspection.selectedPoi = null
  void inspectRoad(poi.lng, poi.lat)
}

/* ---------------- 同步路线 / 标记 / 图层 ---------------- */

function applyRouteAndMarkers(): void {
  if (props.browse) {
    adapter.setRoute(null)
    adapter.setMarkers(null, null, false)
    return
  }
  adapter.setRoute(activeLoop.value)
  if (state.mode === 'oneway') {
    adapter.setMarkers(state.onewayA, state.onewayB, true)
  } else {
    adapter.setMarkers(state.origin, null, false)
  }
>>>>>>> 5144d797b2e0359e5163dd17428bfe917c0690eb
}

function applyInspection(): void {
  const road = props.browse ? inspection.selected : null
  adapter.highlightRoad(road?.geometry.coordinates ?? null)
  adapter.setAccessibleOnly(state.accessibleOnly)
}

function syncLayers(): void {
  const manifest = state.manifest
  if (!manifest) return
  const active = new Set(activeLayerIds.value)
  adapter.setView(currentView.value)

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

function ensureActiveLayers(): void {
  const manifest = state.manifest
  if (!manifest) return
  const active = new Set(activeLayerIds.value)
  for (const def of manifest.layers) {
    if (active.has(def.id) && !state.layerData[def.id]) void loadLayer(def)
  }
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

const poiTypeLabel = computed(() => {
  const poi = inspection.selectedPoi
  if (!poi) return ''
  if (poi.kind === 'toilet') {
    return poi.accessible ? '公共厕所 · 含无障碍标注' : '公共厕所'
  }
  const parts = poi.type.split(/[;|]/).filter(Boolean)
  return parts[parts.length - 1] || '运动场馆'
})

const mapAriaLabel = computed(() => {
  if (props.browse) {
    return '武汉慢跑适宜性地图，点击道路查询详情或点击设施查看信息，滚轮缩放，放大后可拖动'
  }
  if (state.mode === 'oneway') {
    return '武汉单行线规划地图，依次点击地图选择起点 A 与终点 B，滚轮缩放'
  }
  return '武汉慢跑环线地图，点击选起点，滚轮或双指缩放，放大后可拖动'
})

onMounted(async () => {
  if (!host.value) return
  adapter.mount(host.value)
  adapter.setView(currentView.value)
  if (state.manifest) {
    syncLayers()
    ensureActiveLayers()
    applyRouteAndMarkers()
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
    applyRouteAndMarkers()
  } catch (e) {
    state.mapError = (e as Error).message
  }
})

watch(
  [activeLayerIds, currentView, () => state.manifest],
  () => {
    syncLayers()
    ensureActiveLayers()
    scheduleViewportSegments()
  },
  { flush: 'post' },
)

watch(
  activeLoop,
  (loop) => {
    applyRouteAndMarkers()
    if (loop && !props.browse) {
      fitToRoute(loop)
    }
  },
  { flush: 'post' },
)

watch(
  () => props.browse,
  () => {
    inspection.selectedPoi = null
    applyRouteAndMarkers()
    applyInspection()
  },
  { flush: 'post' },
)

watch(
  () => [inspection.selected, state.accessibleOnly],
  applyInspection,
  { flush: 'post' },
)

watch(
  () => [
    state.mode,
    state.origin.lng,
    state.origin.lat,
    state.onewayA?.lng,
    state.onewayA?.lat,
    state.onewayB?.lng,
    state.onewayB?.lat,
  ],
  applyRouteAndMarkers,
  { flush: 'post' },
)
watch(
  () => state.places,
  (places) => {
    adapter.setPlaces(placesVisible() ? places : [])
    fitSearchPlaces(places)
  },
  { flush: 'post' },
)
watch(
  () => state.placeFocusToken,
  () => {
    if (state.focusedPlace) focusPlace(state.focusedPlace)
  },
  { flush: 'post' },
)

onBeforeUnmount(() => {
  disposed = true
  if (segmentsTimer !== null) window.clearTimeout(segmentsTimer)
  if (symbolTimer !== null) window.clearTimeout(symbolTimer)
  segmentsAbort?.abort()
  adapter.destroy()
})
</script>

<template>
  <div class="map-frame">
    <div
      ref="host"
      class="map-host"
      :class="{
        dragging,
        zoomed: viewport.zoom > 1,
        browsing: browse,
        pointing: Boolean(inspection.hoveredPoi),
      }"
      role="img"
      :aria-label="mapAriaLabel"
      @click="onCanvasClick"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerEnd"
      @pointercancel="onPointerEnd"
      @lostpointercapture="onPointerEnd"
      @pointerleave="onPointerLeave"
    ></div>

    <!-- F4 设施悬浮名称提示 -->
    <div
      v-if="inspection.hoveredPoi && !inspection.selectedPoi"
      class="poi-tooltip"
      :style="{
        left: `${(inspection.hoveredPoi.screenX / MAP_W) * 100}%`,
        top: `${(inspection.hoveredPoi.screenY / MAP_H) * 100}%`,
      }"
    >
      <span class="poi-dot" :class="inspection.hoveredPoi.kind"></span>
      <span>{{ inspection.hoveredPoi.name }}</span>
    </div>

    <!-- F4 设施点击详情气泡 -->
    <div
      v-if="inspection.selectedPoi"
      class="poi-popover glass"
      role="dialog"
      aria-label="设施详情"
      :style="{
        left: `${Math.min(82, Math.max(18, (inspection.selectedPoi.screenX / MAP_W) * 100))}%`,
        top: `${Math.min(80, Math.max(16, (inspection.selectedPoi.screenY / MAP_H) * 100))}%`,
      }"
      @click.stop
    >
      <div class="poi-pop-head">
        <span class="poi-badge" :class="inspection.selectedPoi.kind">
          {{ inspection.selectedPoi.kind === 'facility' ? '运动场馆' : '公共厕所' }}
        </span>
        <button
          type="button"
          class="poi-close"
          aria-label="关闭设施详情"
          @click="inspection.selectedPoi = null"
        >
          ×
        </button>
      </div>
      <div class="poi-name">{{ inspection.selectedPoi.name }}</div>
      <div class="poi-meta">{{ poiTypeLabel }}</div>
      <div class="poi-addr">
        {{
          [inspection.selectedPoi.adname, inspection.selectedPoi.address]
            .filter(Boolean)
            .join(' · ') || '暂无详细地址'
        }}
      </div>
      <button
        v-if="browse"
        type="button"
        class="poi-road-link"
        @click="inspectUnderlyingRoad"
      >
        查看此处路段评分
      </button>
    </div>

    <!-- F1 视口路段加载 / 截断降级提示 -->
    <div v-if="state.roadsTruncatedMsg || state.roadsDetailLoading" class="viewport-badge glass">
      <template v-if="state.roadsDetailLoading">正在加载视口细粒度路网…</template>
      <template v-else>{{ state.roadsTruncatedMsg }}</template>
    </div>

    <div class="map-controls glass" role="group" aria-label="地图缩放">
      <button
        type="button"
        aria-label="放大地图"
        title="放大地图"
        :disabled="viewport.zoom >= MAX_ZOOM"
        @click="zoomAt(1.8, undefined, true)"
      >
        +
      </button>
      <button
        type="button"
        aria-label="缩小地图"
        title="缩小地图"
        :disabled="viewport.zoom <= 1"
        @click="zoomAt(1 / 1.8, undefined, true)"
      >
        −
      </button>
      <button
        type="button"
        aria-label="复位全城视野"
        title="复位全城视野"
        :disabled="viewport.zoom <= 1"
        @click="resetViewport"
      >
        复位
      </button>
    </div>
  </div>
</template>

<style scoped>
.map-frame,
.map-host {
  position: absolute;
  inset: 0;
}

.map-host.browsing:not(.zoomed) {
  cursor: default;
}

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

.map-host.pointing {
  cursor: pointer;
}

.map-host.dragging {
  cursor: grabbing;
}

.map-host :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}

.poi-tooltip {
  position: absolute;
  transform: translate(-50%, calc(-100% - 10px));
  pointer-events: none;
  z-index: 12;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: rgba(25, 36, 32, 0.92);
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
}

.poi-dot {
  width: 8px;
  height: 8px;
  flex: none;
}

.poi-dot.facility {
  background: #c2410c;
  border-radius: 2px;
}

.poi-dot.toilet {
  background: #1d4ed8;
  border-radius: 50%;
  box-shadow: 0 0 0 1px #fff;
}

.poi-popover {
  position: absolute;
  transform: translate(-50%, calc(-100% - 12px));
  z-index: 14;
  width: 248px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.96);
  font-size: 12.5px;
  line-height: 1.55;
}

.poi-pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.poi-badge {
  display: inline-block;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
}

.poi-badge.facility {
  background: #c2410c;
}

.poi-badge.toilet {
  background: #1d4ed8;
}

.poi-close {
  width: 22px;
  height: 22px;
  font-size: 16px;
  line-height: 1;
  color: var(--muted);
}

.poi-close:hover {
  color: var(--ink);
}

.poi-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  word-break: break-word;
}

.poi-meta {
  margin-top: 3px;
  font-size: 12px;
  color: var(--sub);
}

.poi-addr {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
  word-break: break-word;
}

.poi-road-link {
  margin-top: 8px;
  padding: 0;
  font-size: 11.5px;
  color: var(--accent);
  text-decoration: underline;
}

.viewport-badge {
  position: absolute;
  bottom: 76px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 12px;
  font-size: 12px;
  color: var(--sub);
  z-index: 6;
  white-space: nowrap;
}

.map-controls {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  z-index: 6;
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
