import { computed, reactive } from 'vue'
import { apiMessage, fetchLoops } from '../api/client'
import { VIEW, VIEW_PADDING, fitViewBBox } from '../lib/projection'
import type {
  Extent,
  GeoManifest,
  LayerCollection,
  LoopCollection,
  LoopFeature,
  ViewBox,
} from '../types'

export type TabKey = 'map' | 'loops' | 'compare'
export type Mode = 'loop' | 'oneway'

export interface Origin {
  name: string
  lng: number
  lat: number
}

/** M1 只放「有对应 mock 响应」的两个起点，M2 接后端再开放任意选点 */
export const PRESET_ORIGINS: Origin[] = [
  { name: '武汉大学 · 八一路珞珈山', lng: 114.3547, lat: 30.5342 },
  { name: '东湖绿道 · 示例起点', lng: 114.411923, lat: 30.555589 },
]

export interface PlannerState {
  tab: TabKey
  origin: Origin
  /** 预设起点 / 地图选点，决定是否显示起点标记 */
  originSource: 'preset' | 'custom'
  mode: Mode
  targetM: number
  /** 界面开关；提交时换算成后端权重 */
  prefs: { green: boolean; safe: boolean; flat: boolean; facility: boolean }
  loops: LoopCollection | null
  activeIndex: number
  loading: boolean
  /** 生成接口的错误 */
  error: string
  /** 接口正常但 features 为空 */
  emptyMsg: string
  /** 底图加载错误 */
  mapError: string
  mapReady: boolean
  /** 地图范围：片区（central）/ 全城（city） */
  extent: Extent
  /** /geo/manifest.json：图层清单（null = 还没加载到） */
  manifest: GeoManifest | null
  /** 每个图层的开关（初始值来自 manifest.layers[].default） */
  layersEnabled: Record<string, boolean>
  /** 已加载的图层数据缓存：extent 来回切换不重复 fetch */
  layerData: Record<string, LayerCollection | null>
  /** 每个图层是否正在加载（面板显示 .layer-loading） */
  layerLoading: Record<string, boolean>
  /** 图层加载错误（面板显示 .layers-err） */
  layerError: string
}

export const state = reactive<PlannerState>({
  tab: 'map',
  origin: PRESET_ORIGINS[0],
  originSource: 'preset',
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
  extent: 'central',
  manifest: null,
  layersEnabled: {},
  layerData: {},
  layerLoading: {},
  layerError: '',
})

export const loopCount = computed(() => state.loops?.features.length ?? 0)

export const activeLoop = computed<LoopFeature | null>(() => {
  const features = state.loops?.features
  if (!features || features.length === 0) return null
  return features[Math.min(state.activeIndex, features.length - 1)] ?? null
})

export const targetOptions = [3000, 5000, 10000] as const

/** 开关 → POST /api/loops 的 prefs（facility 后端没有字段，见 G4） */
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
  controller?.abort()
  controller = new AbortController()
  const myId = ++requestId

  state.loading = true
  state.loops = null
  state.error = ''
  state.emptyMsg = ''
  try {
    const res = await fetchLoops(
      {
        lng: state.origin.lng,
        lat: state.origin.lat,
        target_m: state.targetM,
        mode: state.mode,
        prefs: prefsPayload(),
        max_candidates: 8,
      },
      controller.signal,
    )
    if (myId !== requestId) return
    state.loops = res
    state.activeIndex = 0
    const msg = (res as LoopCollection & { message?: string }).message
    if (!res.features || res.features.length === 0) {
      state.emptyMsg = msg || '没有找到符合条件的路线，试试调整目标距离或偏好。'
    }
  } catch (e) {
    if (myId !== requestId) return
    if ((e as Error).name === 'AbortError') return
    state.error = apiMessage(e)
  } finally {
    if (myId === requestId) state.loading = false
  }
}

export function setTarget(targetM: number): void {
  if (state.targetM === targetM) return
  state.targetM = targetM
  void generate()
}

export function setMode(mode: Mode): void {
  if (state.mode === mode) return
  state.mode = mode
  state.error = ''
  void generate()
}

export function setOrigin(origin: Origin, source: PlannerState['originSource'] = 'preset'): void {
  state.origin = origin
  state.originSource = source
  void generate()
}

export function togglePref(key: keyof PlannerState['prefs']): void {
  // 绿荫/安全/坡度至少保留一个：全关时后端偏好权重和为 0，综合分会退化成 0
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

/** 候选环线：首尾循环，键盘 ←/→ 与右栏按钮共用 */
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
  state.emptyMsg = ''
}

/* ------------------------------------------------------------------
 * 空间图层 / 地图范围（由 public/geo/manifest.json 驱动）
 * ------------------------------------------------------------------ */

/** 当前范围对应的投影视图：片区沿用 reference 的固定 VIEW，全城按数据 bbox 等比适配 */
export const currentView = computed<ViewBox>(() => {
  const manifest = state.manifest
  if (state.extent === 'city' && manifest) {
    const { lon0, lat0, lon1, lat1 } = manifest.view.city
    return fitViewBBox([lon0, lat0, lon1, lat1], VIEW_PADDING)
  }
  return VIEW
})

/** 当前范围下实际渲染的「适宜性路网」变体 */
export const activeRoadLayerId = computed<string>(() => {
  if (state.extent === 'central') return 'roads_central'
  return state.layersEnabled['roads_all'] ? 'roads_all' : 'roads_arterial'
})

/** 图层面板「适宜性路网」行的开关状态（不含单独的“全量路网”行） */
export const roadSuitabilityEnabled = computed<boolean>(() => {
  return state.extent === 'central'
    ? !!state.layersEnabled['roads_central']
    : !!state.layersEnabled['roads_arterial']
})

/**
 * 当前应该显示的图层 id 列表（MapStage 懒加载 / 适配器渲染的依据）。
 * - 开关关闭的不要；
 * - 与当前 extent 不适配的不要（central 专属 / city 专属）；
 * - 路网三变体只保留 activeRoadLayerId 一个，避免 roads 组被多个数据覆盖。
 */
export const activeLayerIds = computed<string[]>(() => {
  const manifest = state.manifest
  if (!manifest) return []
  const out: string[] = []
  for (const def of manifest.layers) {
    if (def.variant === 'roads') {
      if (def.id === activeRoadLayerId.value && state.layersEnabled[def.id]) out.push(def.id)
      continue
    }
    if (!state.layersEnabled[def.id]) continue
    if (def.extent !== 'both' && def.extent !== state.extent) continue
    out.push(def.id)
  }
  return out
})

/** 图层文件 URL（manifest 只给文件名） */
export function layerFileUrl(file: string): string {
  return `/geo/${file}`
}

/** manifest 到达后初始化图层开关（default=true 首屏加载，其余懒加载） */
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

/** 切换片区 / 全城；路网变体开关状态跟随当前“适宜性路网”行 */
export function setExtent(extent: Extent): void {
  if (state.extent === extent) return
  if (extent === 'city') {
    state.layersEnabled['roads_arterial'] = !!state.layersEnabled['roads_central']
  } else {
    state.layersEnabled['roads_central'] = !!state.layersEnabled['roads_arterial']
    // 全量路网只在全城下有意义，切回片区自动关闭，避免 30 MB 数据常驻
    state.layersEnabled['roads_all'] = false
  }
  state.extent = extent
  state.layerError = ''
}

/** 图层面板开关：'roads' 是适宜性路网合成行，'roads_all' 是全量路网 */
export function toggleLayer(id: string): void {
  if (id === 'roads') {
    const target = state.extent === 'central' ? 'roads_central' : 'roads_arterial'
    state.layersEnabled[target] = !state.layersEnabled[target]
    state.layerError = ''
    return
  }
  const def = state.manifest?.layers.find((layer) => layer.id === id)
  if (id === 'roads_all') {
    const next = !state.layersEnabled['roads_all']
    state.layersEnabled['roads_all'] = next
    // 全量路网数据只在全城视野下有完整意义
    if (next) setExtent('city')
    state.layerError = ''
    return
  }
  if (!def) return
  state.layersEnabled[id] = !state.layersEnabled[id]
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
