import { computed, reactive } from 'vue'
import { ApiError, fetchLoops } from '../api/client'
import type { LoopCollection, LoopFeature } from '../types'

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
  { name: '东湖绿道 · 湖光序曲', lng: 114.3805, lat: 30.549 },
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
  if (state.mode === 'oneway') {
    state.error = '单行线 A→B 需要后端新增 mode 参数（契约缺口 G1），当前版本只支持环线。'
    return
  }
  controller?.abort()
  controller = new AbortController()
  const myId = ++requestId

  state.loading = true
  state.error = ''
  state.emptyMsg = ''
  try {
    const res = await fetchLoops(
      {
        lng: state.origin.lng,
        lat: state.origin.lat,
        target_m: state.targetM,
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
    state.error =
      e instanceof ApiError
        ? `生成路线失败（HTTP ${e.status}）：${e.body.slice(0, 180)}`
        : `生成路线失败：${(e as Error).message}`
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
