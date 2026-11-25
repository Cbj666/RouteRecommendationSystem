import { computed, reactive } from 'vue'
import { apiMessage, fetchLoops, searchPlaces as fetchPlaces } from '../api/client'
import { VIEW, VIEW_PADDING, fitViewBBox } from '../lib/projection'
import type {
  GeoManifest,
  LayerCollection,
  LoopCollection,
  LoopFeature,
  Place,
  ViewBox,
} from '../types'

export type TabKey = 'map' | 'loops' | 'hotspots'
export type Mode = 'loop' | 'oneway'

export interface Origin {
  name: string
  lng: number
  lat: number
}

export const PRESET_ORIGINS: Origin[] = [
  { name: '武汉大学 · 八一路珞珈山', lng: 114.3547, lat: 30.5342 },
  { name: '东湖绿道 · 示例起点', lng: 114.411923, lat: 30.555589 },
  { name: '街道口 · 珞喻路', lng: 114.349, lat: 30.5256 },
  { name: '东湖磨山景区', lng: 114.4076, lat: 30.5458 },
]

/** 默认全市 bbox（与 manifest.view.city 一致，避免 manifest 到达前视野跳动） */
const DEFAULT_CITY_BBOX: [number, number, number, number] = [
  113.698077, 29.971928, 115.076651, 31.362866,
]

export interface PlannerState {
  tab: TabKey
  /** 环线模式起点 */
  origin: Origin
  /** 预设起点 / 地图选点 / 地点搜索，决定起点标记的来源 */
  originSource: 'preset' | 'custom' | 'search'
  /** 单行线 A（起点）与 B（终点） */
  onewayA: Origin | null
  onewayB: Origin | null
  /** 单行线当前地图点选目标 */
  pickingPoint: 'A' | 'B'
  /** 单行线选点错误（显示在 B 卡下方，保留已选点） */
  onewayError: string
  /** 接口返回 notice 或 target_ok=false 时的温和提示 */
  routeNotice: string
  mode: Mode
  targetM: number
  /** 界面开关；提交时换算成后端权重 */
  prefs: { green: boolean; safe: boolean; flat: boolean; facility: boolean }
  loops: LoopCollection | null
  activeIndex: number
  loading: boolean
  /** 环线生成接口错误 */
  error: string
  /** 接口正常但 features 为空 */
  emptyMsg: string
  /** 底图加载错误 */
  mapError: string
  mapReady: boolean
  /** /geo/manifest.json：图层清单 */
  manifest: GeoManifest | null
  /** 每个图层的开关（初始值来自 manifest.layers[].default） */
  layersEnabled: Record<string, boolean>
  /** 公厕图层是否仅看无障碍 */
  accessibleOnly: boolean
  /** 已加载的静态图层数据缓存 */
  layerData: Record<string, LayerCollection | null>
  /** 每个图层是否正在加载 */
  layerLoading: Record<string, boolean>
  /** 图层加载错误 */
  layerError: string
  /** 地点搜索结果：地图编号标记与搜索下拉共用 */
  places: Place[]
  /** 产生 places 的关键词（用于空态与结果标题） */
  placeQuery: string
  /** 地点搜索中 */
  placeLoading: boolean
  /** 地点搜索错误（503 未配置 Key / 504 超时 / 502 高德不可用等） */
  placeError: string
  /** 最近从下拉里选中的地点；地图据此定位 */
  focusedPlace: Place | null
  /** 每次选中自增，保证重复选同一条也能重新定位 */
  placeFocusToken: number
  /** 视口细粒度路网加载状态与截断降级提示 */
  roadsDetailLoading: boolean
  roadsTruncatedMsg: string
  roadsDetailed: boolean
}

export const state = reactive<PlannerState>({
  // 默认进入环线推荐（适宜性地图页只保留源码，不展示入口）
  tab: 'loops',
  origin: PRESET_ORIGINS[0],
  originSource: 'preset',
  onewayA: null,
  onewayB: null,
  pickingPoint: 'A',
  onewayError: '',
  routeNotice: '',
  mode: 'loop',
  targetM: 5000,
  prefs: { green: true, safe: true, flat: false, facility: true },
  loops: null,
  activeIndex: 0,
  loading: false,
  error: '',
  emptyMsg: '',
  mapError: '',
  mapReady: false,
  manifest: null,
  layersEnabled: {},
  accessibleOnly: false,
  layerData: {},
  layerLoading: {},
  layerError: '',
  places: [],
  placeQuery: '',
  placeLoading: false,
  placeError: '',
  focusedPlace: null,
  placeFocusToken: 0,
  roadsDetailLoading: false,
  roadsTruncatedMsg: '',
  roadsDetailed: false,
})

export const loopCount = computed(() => state.loops?.features.length ?? 0)

export const activeLoop = computed<LoopFeature | null>(() => {
  const features = state.loops?.features
  if (!features || features.length === 0) return null
  return features[Math.min(state.activeIndex, features.length - 1)] ?? null
})

export const targetOptions = [3000, 5000, 10000] as const

function prefsPayload() {
  return {
    green: state.prefs.green ? 1 : 0,
    safe: state.prefs.safe ? 1 : 0,
    flat: state.prefs.flat ? 0.6 : 0,
  }
}

let requestId = 0
let controller: AbortController | null = null

export async function generate(): Promise<void> {
  if (state.mode === 'oneway' && (!state.onewayA || !state.onewayB)) {
    return
  }
  controller?.abort()
  controller = new AbortController()
  const myId = ++requestId

  state.loading = true
  state.loops = null
  state.error = ''
  state.onewayError = ''
  state.emptyMsg = ''
  state.routeNotice = ''

  try {
    const payload =
      state.mode === 'oneway'
        ? {
            lng: state.onewayA!.lng,
            lat: state.onewayA!.lat,
            mode: 'oneway' as const,
            end_lng: state.onewayB!.lng,
            end_lat: state.onewayB!.lat,
            prefs: prefsPayload(),
          }
        : {
            lng: state.origin.lng,
            lat: state.origin.lat,
            target_m: state.targetM,
            mode: 'loop' as const,
            prefs: prefsPayload(),
            max_candidates: 8,
          }

    const res = await fetchLoops(payload, controller.signal)
    if (myId !== requestId) return
    state.loops = res
    state.activeIndex = 0

    const msg = res.message
    if (!res.features || res.features.length === 0) {
      state.emptyMsg =
        msg ||
        (state.mode === 'oneway'
          ? '起点与终点之间没有找到可达的慢跑路径，请重新选点。'
          : '没有找到符合条件的路线，试试调整目标距离或偏好。')
    } else if (
      state.mode === 'oneway' &&
      (res.notice || res.features.some((f) => f.properties.target_ok === false))
    ) {
      state.routeNotice = '以终点为准，实际距离与目标距离存在偏差'
    }
  } catch (e) {
    if (myId !== requestId) return
    if ((e as Error).name === 'AbortError') return
    const message = apiMessage(e)
    if (state.mode === 'oneway') {
      state.onewayError = message
    } else {
      state.error = message
    }
  } finally {
    if (myId === requestId) state.loading = false
  }
}

export function setTarget(targetM: number): void {
  if (state.targetM === targetM) return
  state.targetM = targetM
  if (state.mode === 'loop') void generate()
}

export function setMode(mode: Mode): void {
  if (state.mode === mode) return
  controller?.abort()
  requestId++
  state.mode = mode
  state.loading = false
  state.loops = null
  state.error = ''
  state.onewayError = ''
  state.emptyMsg = ''
  state.routeNotice = ''
  if (mode === 'oneway') {
    state.onewayA = null
    state.onewayB = null
    state.pickingPoint = 'A'
  } else {
    void generate()
  }
}

export function setPickingPoint(target: 'A' | 'B'): void {
  state.pickingPoint = target
}

export function setOrigin(origin: Origin, source: PlannerState['originSource'] = 'preset'): void {
  state.origin = origin
  state.originSource = source
  void generate()
}

/* ------------------------------------------------------------------
 * 地点搜索（GET /api/places/search）
 * ------------------------------------------------------------------ */

let placeRequestId = 0
let placeController: AbortController | null = null

/** 清空搜索结果与下拉状态；同时取消还在飞的请求。 */
export function clearPlaces(): void {
  placeController?.abort()
  placeController = null
  placeRequestId++
  state.places = []
  state.placeQuery = ''
  state.placeLoading = false
  state.placeError = ''
  state.focusedPlace = null
}

/**
 * 调后端搜地点。store 负责防抖之外的竞态：后发请求会取消先发请求，
 * 过期响应按 requestId 丢弃；错误转成中文提示放进 placeError。
 */
export async function searchPlaces(query: string): Promise<void> {
  const keywords = query.trim()
  if (!keywords) {
    clearPlaces()
    return
  }

  placeController?.abort()
  placeController = new AbortController()
  const myId = ++placeRequestId

  state.placeLoading = true
  state.placeError = ''
  state.places = []
  state.focusedPlace = null
  state.placeQuery = keywords

  try {
    const res = await fetchPlaces(keywords, placeController.signal)
    if (myId !== placeRequestId) return
    state.places = res.places
    state.placeQuery = res.query || keywords
  } catch (e) {
    if (myId !== placeRequestId) return
    if ((e as Error).name === 'AbortError') return
    state.places = []
    state.placeError = apiMessage(e)
  } finally {
    if (myId === placeRequestId) state.placeLoading = false
  }
}

/** 选中一条搜索结果：环线模式设为起点，单行线模式依次设 A / B；并请求地图定位。 */
export function selectPlace(place: Place): void {
  const point = { name: place.name, lng: place.lng, lat: place.lat }
  if (state.mode === 'loop') setOrigin(point, 'search')
  else pickOriginOrDest(point, 'search')
  // 输入框会回填地点名，让 placeQuery 跟着走，避免 TopBar 把“查询词不一致”误判成还在输入
  state.placeQuery = place.name
  state.focusedPlace = { ...place }
  state.placeFocusToken++
}

/** 地图点击或顶部搜索选点：环线模式设起点；单行线模式依次设 A / B */
export function pickOriginOrDest(
  point: Origin,
  source: 'preset' | 'custom' | 'search' = 'custom',
): void {
  const label = (suffix: 'A' | 'B') => (source === 'custom' ? `地图选点 ${suffix}` : point.name)
  if (state.mode === 'loop') {
    setOrigin(point, source === 'search' ? 'search' : source)
    return
  }
  state.onewayError = ''
  state.emptyMsg = ''
  if (state.pickingPoint === 'A') {
    state.onewayA = {
      ...point,
      name: label('A'),
    }
    state.pickingPoint = 'B'
    if (state.onewayB) void generate()
  } else {
    state.onewayB = {
      ...point,
      name: label('B'),
    }
    // 保持 B 为当前重选目标：想重选 B 直接再点地图即可
    state.pickingPoint = 'B'
    if (state.onewayA) void generate()
  }
}

export function togglePref(key: keyof PlannerState['prefs']): void {
  const payloadKeys = ['green', 'safe', 'flat'] as const
  if (state.prefs[key] && (payloadKeys as readonly string[]).includes(key)) {
    const enabled = payloadKeys.filter((k) => state.prefs[k])
    if (enabled.length === 1 && enabled[0] === key) return
  }
  state.prefs[key] = !state.prefs[key]
}

export function selectLoop(index: number): void {
  if (!state.loops) return
  if (index < 0 || index >= state.loops.features.length) return
  state.activeIndex = index
}

export function prevLoop(): void {
  const n = loopCount.value
  if (n === 0) return
  state.activeIndex = (state.activeIndex - 1 + n) % n
}

export function nextLoop(): void {
  const n = loopCount.value
  if (n === 0) return
  state.activeIndex = (state.activeIndex + 1) % n
}

export function clearError(): void {
  state.error = ''
  state.onewayError = ''
  state.emptyMsg = ''
}

/* ------------------------------------------------------------------
 * 统一单图视图 + 空间图层（由 public/geo/manifest.json 驱动）
 * ------------------------------------------------------------------ */

/** 热点页专用视野：武汉全市域（与 build_hotspot_grid.py 输出的 view 一致）。 */
export const HOTSPOT_VIEW: ViewBox = fitViewBBox([113.6928, 30.006, 115.076, 31.338], VIEW_PADDING)

/** 全市统一底图投影视图（zoom=1 时一屏看完整座武汉）；热点页改用全市域视野 */
export const currentView = computed<ViewBox>(() => {
  if (state.tab === 'hotspots') return HOTSPOT_VIEW
  const city = state.manifest?.view.city
  if (city) {
    return fitViewBBox([city.lon0, city.lat0, city.lon1, city.lat1], VIEW_PADDING)
  }
  return fitViewBBox(DEFAULT_CITY_BBOX, VIEW_PADDING)
})

/** 适宜性路网是否开启 */
export const roadSuitabilityEnabled = computed<boolean>(() => {
  return !!state.layersEnabled['roads_arterial']
})

/** 当前应该显示的图层 id 列表 */
export const activeLayerIds = computed<string[]>(() => {
  const manifest = state.manifest
  if (!manifest) return []
  const out: string[] = []
  for (const def of manifest.layers) {
    if (state.layersEnabled[def.id]) out.push(def.id)
  }
  return out
})

export function layerFileUrl(file: string): string {
  return `/geo/${file}`
}

export function setManifest(manifest: GeoManifest): void {
  state.manifest = manifest
  const enabled: Record<string, boolean> = {}
  for (const def of manifest.layers) enabled[def.id] = def.default
  state.layersEnabled = enabled
  state.layerData = {}
  state.layerLoading = {}
  state.layerError = ''
  state.mapError = ''
}

export function toggleLayer(id: string): void {
  const targetId = id === 'roads' ? 'roads_arterial' : id
  const def = state.manifest?.layers.find((layer) => layer.id === targetId)
  if (!def) return
  state.layersEnabled[targetId] = !state.layersEnabled[targetId]
  state.layerError = ''
}

export function setLayerData(id: string, data: LayerCollection): void {
  state.layerData[id] = data
}

export function setLayerLoading(id: string, loading: boolean): void {
  state.layerLoading[id] = loading
}

export function setLayerError(message: string): void {
  state.layerError = message
}
