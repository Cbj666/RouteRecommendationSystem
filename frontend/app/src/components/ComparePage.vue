<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { apiMessage, fetchLoops, USE_MOCK } from '../api/client'
import { comparisonColors, type ComparisonMark } from '../map/svgAdapter'
import { PRESET_ORIGINS, state, targetOptions, type Origin } from '../stores/planner'
import type { LoopCollection, LoopFeature, LoopProps, LoopRequest, LoopSubScores } from '../types'
import MapStage from './MapStage.vue'

const sides = ['A', 'B'] as const
type Side = typeof sides[number]
type Result =
  | { status: 'idle' | 'loading' }
  | { status: 'empty' | 'error'; message: string }
  | { status: 'success'; route: LoopFeature }

let previousExtent = state.extent
onActivated(() => {
  previousExtent = state.extent
  state.extent = 'city'
})
onDeactivated(() => { state.extent = previousExtent })
const presets = PRESET_ORIGINS
const origins = reactive<Record<Side, Origin | null>>({ A: { ...state.origin }, B: null })
const results = reactive<Record<Side, Result>>({ A: { status: 'idle' }, B: { status: 'idle' } })
const picking = ref<Side | null>(null)
const target = ref<number>(USE_MOCK ? 5000 : state.targetM)
const preferences = [
  { key: 'green', label: '绿荫' },
  { key: 'safe', label: '安全' },
  { key: 'flat', label: '平坦' },
] as const
const prefs = reactive({
  green: USE_MOCK || state.prefs.green,
  safe: USE_MOCK || state.prefs.safe,
  flat: !USE_MOCK && state.prefs.flat,
})
let controller: AbortController | null = null
let submitted: Record<Side, LoopRequest> | null = null

function presetIndex(origin: Origin | null): number {
  return presets.findIndex((p) => p.lng === origin?.lng && p.lat === origin?.lat)
}

const sameOrigin = computed(() =>
  !!origins.A && !!origins.B && origins.A.lng === origins.B.lng && origins.A.lat === origins.B.lat,
)
const mockUnsupported = computed(() =>
  USE_MOCK && sides.some((side) => origins[side] && presetIndex(origins[side]) < 0),
)
const busy = computed(() => sides.some((side) => results[side].status === 'loading'))
const canCompare = computed(() =>
  origins.A && origins.B && !sameOrigin.value && !mockUnsupported.value && !busy.value,
)

const marks = computed<ComparisonMark[]>(() => sides.flatMap((side) => {
  const origin = origins[side]
  const result = results[side]
  return origin ? [{ side, origin, route: result.status === 'success' ? result.route : null }] : []
}))

function startPicking(side: Side): void {
  picking.value = picking.value === side ? null : side
}

function choosePreset(side: Side, event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  if (value === '') return
  origins[side] = presets[Number(value)] ?? null
  picking.value = null
}

function pick(origin: Origin): void {
  if (!picking.value) return
  origins[picking.value] = origin
  picking.value = null
}

function clear(): void {
  controller?.abort()
  controller = null
  submitted = null
  for (const side of sides) results[side] = { status: 'idle' }
}

watch([origins, target, prefs], clear, { flush: 'sync' })
onBeforeUnmount(clear)

async function requestSide(side: Side): Promise<void> {
  if (!submitted || !controller) return
  const signal = controller.signal
  results[side] = { status: 'loading' }
  try {
    const response: LoopCollection & { message?: string } = await fetchLoops(submitted[side], signal)
    if (signal.aborted) return
    const route = response.features.find((feature) => feature.properties.rank === 1)
    results[side] = route
      ? { status: 'success', route }
      : { status: 'empty', message: response.message || '试试换一个起点或调整距离。' }
  } catch (error) {
    if (signal.aborted) return
    const message = apiMessage(error)
    results[side] = { status: 'error', message }
  }
}

function compare(): void {
  if (!canCompare.value || !origins.A || !origins.B) return
  clear()
  picking.value = null
  controller = new AbortController()
  const shared = {
    target_m: target.value,
    prefs: { green: prefs.green ? 1 : 0, safe: prefs.safe ? 1 : 0, flat: prefs.flat ? 0.6 : 0 },
    max_candidates: 8,
  }
  const request = ({ lng, lat }: Origin) => ({ lng, lat, ...shared })
  submitted = { A: request(origins.A), B: request(origins.B) }
  for (const side of sides) void requestSide(side)
}

const properties = computed(() => {
  function forSide(side: Side): LoopProps | null {
    const result = results[side]
    return result.status === 'success' ? result.route.properties : null
  }
  return { A: forSide('A'), B: forSide('B') }
})

const scoreDifference = computed(() => {
  const { A, B } = properties.value
  if (!A || !B) return ''
  const difference = A.score - B.score
  return difference === 0 ? '两侧偏好匹配分相同' :
    `${difference > 0 ? 'A' : 'B'} 高 ${Math.abs(difference).toFixed(1)} 分`
})

function scoreFor(side: Side, key: keyof LoopSubScores): string {
  const props = properties.value[side]
  if (!props) return '—'
  try {
    const score = (JSON.parse(props.sub) as Partial<LoopSubScores> | null)?.[key]
    return typeof score === 'number' ? score.toFixed(1) : '—'
  } catch {
    return '—'
  }
}

const metrics: { label: string; format: (p: LoopProps) => string }[] = [
  { label: '偏好匹配分', format: (p) => `${p.score.toFixed(1)} 分` },
  { label: '实际距离', format: (p) => `${(p.length_m / 1000).toFixed(2)} km` },
  { label: '预计用时', format: (p) => `${p.minutes.toFixed(1)} 分钟` },
  { label: '树冠比例', format: (p) => `${(p.tree_share * 100).toFixed(1)}%` },
  { label: '平均坡度', format: (p) => `${p.slope_mean_pct.toFixed(2)}%` },
  { label: '设施距离', format: (p) => `${p.facility_m.toFixed(0)} m` },
]
if (!USE_MOCK) metrics.push({ label: '起点吸附偏差', format: (p) => `${p.origin_snap_m.toFixed(1)} m` })
const subs = { s_safety: '安全', s_green: '绿化', s_slope: '坡度' } as const
</script>

<template>
  <main class="compare-page" :style="{ '--side-a': comparisonColors.A, '--side-b': comparisonColors.B }">
    <div class="compare-layout">
      <form class="side-panel controls" @submit.prevent="compare">
        <h2>选择两个起点</h2>
        <fieldset v-for="side in sides" :key="side">
          <legend><span class="side-key" :data-side="side">{{ side }}</span> 起点</legend>
          <select :aria-label="`起点 ${side}`" :value="presetIndex(origins[side]) < 0 ? '' : presetIndex(origins[side])" @change="choosePreset(side, $event)">
            <option value="" disabled>{{ origins[side]?.name ?? '选择预设起点' }}</option>
            <option v-for="(origin, index) in presets" :key="origin.name" :value="index">{{ origin.name }}</option>
          </select>
          <button type="button" class="pick" :aria-pressed="picking === side" :disabled="USE_MOCK || !state.mapReady" @click="startPicking(side)">
            {{ picking === side ? '取消地图选点' : '地图选点' }}
          </button>
          <small v-if="origins[side]" class="num">{{ origins[side]?.lng.toFixed(4) }}, {{ origins[side]?.lat.toFixed(4) }}</small>
        </fieldset>
        <fieldset :disabled="USE_MOCK">
          <legend>共同目标距离</legend>
          <div class="options">
            <label v-for="distance in targetOptions" :key="distance">
              <input v-model="target" type="radio" name="compare-distance" :value="distance" /> {{ distance / 1000 }} km
            </label>
          </div>
        </fieldset>
        <fieldset :disabled="USE_MOCK">
          <legend>共同路线偏好</legend>
          <div class="options">
            <label v-for="{ key, label } in preferences" :key="key">
              <input v-model="prefs[key]" type="checkbox" :disabled="prefs[key] && Object.values(prefs).filter(Boolean).length === 1" /> {{ label }}
            </label>
          </div>
        </fieldset>
        <p v-if="USE_MOCK" class="hint">当前使用武大与东湖的 5 km 示例。连接后端后可自由选点和调整条件。</p>
        <p v-if="sameOrigin" class="hint" role="status">两个起点相同，请换一个地点。</p>
        <button class="submit" type="submit" :disabled="!canCompare">{{ busy ? '正在计算…' : '比较路线' }}</button>
      </form>

      <section class="compare-map" aria-label="双起点路线地图">
        <div class="map-surface"><MapStage :comparison="marks" @pick="pick" /></div>
        <p v-if="picking" class="map-hint" role="status">点击地图设置起点 {{ picking }}</p>
        <p v-else-if="state.mapError" class="map-hint" role="status">底图暂不可用，仍可查看路线指标。</p>
        <div class="map-key">
          <span class="solid">A 路线</span><span class="dashed">B 路线</span>
        </div>
      </section>

      <section class="side-panel results" aria-live="polite">
        <h2>首选环线</h2>
        <p v-if="scoreDifference" class="difference">{{ scoreDifference }}</p>
        <table>
          <thead><tr><th scope="col">指标</th><th v-for="side in sides" :key="side" scope="col"><span class="side-key" :data-side="side">{{ side }}</span></th></tr></thead>
          <tbody>
            <tr v-for="metric in metrics" :key="metric.label">
              <th scope="row">{{ metric.label }}</th>
              <td v-for="side in sides" :key="side" class="num">{{ properties[side] ? metric.format(properties[side]!) : '—' }}</td>
            </tr>
          </tbody>
        </table>
        <details v-if="properties.A || properties.B">
          <summary>查看偏好子分</summary>
          <table>
            <thead><tr><th scope="col">子分</th><th v-for="side in sides" :key="side" scope="col">{{ side }}</th></tr></thead>
            <tbody><tr v-for="(label, key) in subs" :key="key"><th scope="row">{{ label }}</th><td v-for="side in sides" :key="side" class="num">{{ scoreFor(side, key) }}</td></tr></tbody>
          </table>
        </details>
        <div v-for="side in sides" :key="side" class="side-status">
          <p v-if="results[side].status === 'loading'">{{ side }} 正在计算路线…</p>
          <p v-else-if="results[side].status === 'empty'">{{ side }} 无合适路线。{{ results[side].message }}</p>
          <p v-else-if="results[side].status === 'error'">
            {{ side }} {{ results[side].message }}
            <button type="button" @click="requestSide(side)">重试 {{ side }}</button>
          </p>
          <p v-else-if="!USE_MOCK && (properties[side]?.origin_snap_m ?? 0) > 100">{{ side }} 起点离道路较远。</p>
        </div>
        <p v-if="results.A.status === 'idle' && results.B.status === 'idle'" class="hint">选好两个起点后，点击「比较路线」。</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.compare-page { position: absolute; inset: 64px 0 0; overflow: auto; background: #f1f3ed; }
.pick, .side-status button { color: #15503c; font-weight: 650; }
h2 { font-size: 17px; margin-bottom: 16px; }
.compare-layout { display: grid; grid-template-columns: minmax(220px, 255px) minmax(0, 1fr) minmax(260px, 305px); gap: 14px; align-items: start; max-width: 1800px; margin: 0 auto; padding: 16px; }
.side-panel { background: #fff; border: 1px solid #dce2d8; padding: 16px; min-width: 0; }
fieldset { border: 0; margin-bottom: 16px; }
legend { font-weight: 650; font-size: 14px; margin-bottom: 7px; }
select { width: 100%; padding: 8px; background: #f8f9f5; border: 1px solid #cbd5cb; font: inherit; font-size: 13px; }
.pick { padding: 7px 0; display: block; font-size: 13px; }
.pick[aria-pressed="true"] { text-decoration: underline; }
.pick:disabled { color: #59665e; }
small, .hint { color: #505e55; font-size: 12px; line-height: 1.5; }
.options { display: flex; gap: 8px; flex-wrap: wrap; font-size: 13px; }
input { accent-color: #15503c; }
.submit { width: 100%; padding: 10px; margin-top: 12px; color: #fff; background: #15503c; font-weight: 650; }
.submit:disabled { background: #647a6c; }
.compare-map { min-width: 0; position: relative; border: 1px solid #dce2d8; background: #fff; }
.map-surface { position: relative; aspect-ratio: 16 / 10; overflow: hidden; }
.map-key { display: flex; gap: 18px; padding: 10px 14px; font-size: 13px; border-top: 1px solid #dce2d8; }
.map-key span::before { content: ''; display: inline-block; width: 18px; margin-right: 6px; vertical-align: middle; border-top: 3px solid var(--side-a); }
.map-key .dashed::before { border-top: 3px dashed var(--side-b); }
.map-hint { position: absolute; top: 12px; left: 12px; padding: 6px 10px; background: #fff; font-size: 13px; pointer-events: none; }
.side-key { color: var(--side-a); font-weight: 750; }
.side-key[data-side="B"] { color: var(--side-b); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: right; padding: 8px 3px; border-bottom: 1px solid #e6eae3; }
th:first-child { text-align: left; font-weight: 550; }
.difference { color: #15503c; background: #edf4ee; padding: 8px; margin-bottom: 8px; font-size: 14px; }
details, .side-status p, .results .hint { margin-top: 10px; font-size: 13px; }
summary { cursor: pointer; }
@media (max-width: 1100px), (max-height: 680px) {
  .compare-page { position: static; overflow: visible; }
  .compare-layout { grid-template-columns: 1fr; max-width: 680px; }
  .compare-layout { padding: 0; }
}
</style>
