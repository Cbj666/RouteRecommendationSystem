<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { apiMessage, fetchMeta, fetchToilets, USE_MOCK } from '../api/client'
import { inspection } from '../stores/inspection'

const toiletError = ref('')
const toiletLoading = ref(false)
const meta = ref<{ weights?: Record<string, number>; grade_bins?: number[]; notes?: string[] }>({})
const metaError = ref('')
let disposed = false
let toiletRequest = 0

async function loadToilets(): Promise<void> {
  const id = ++toiletRequest
  toiletError.value = ''
  if (!inspection.toiletsEnabled) { toiletLoading.value = false; return }
  toiletLoading.value = true
  try {
    const data = await fetchToilets(inspection.accessible)
    if (!disposed && id === toiletRequest) inspection.toilets = data
  } catch (error) {
    if (!disposed && id === toiletRequest) {
      inspection.toilets = null
      toiletError.value = apiMessage(error)
    }
  } finally {
    if (!disposed && id === toiletRequest) toiletLoading.value = false
  }
}
watch(() => [inspection.toiletsEnabled, inspection.accessible], () => {
  inspection.toilets = null
  void loadToilets()
})
onMounted(() => {
  void fetchMeta().then((data) => { if (!disposed) meta.value = data }).catch(() => {
    if (!disposed) metaError.value = '评分说明暂不可用，请重试。'
  })
  if (inspection.toiletsEnabled) void loadToilets()
})
onBeforeUnmount(() => { disposed = true; toiletRequest++ })

const dimensions = [
  { label: '安全', key: 's_safety', weight: 'safety' },
  { label: '绿化', key: 's_green', weight: 'green' },
  { label: '坡度', key: 's_slope', weight: 'slope' },
  { label: '过街', key: 's_cross', weight: 'cross' },
  { label: '设施', key: 's_fac', weight: 'fac' },
  { label: '空气', key: 's_air', weight: 'air' },
]
const raw = [
  { key: 'slope_mean_pct', label: '平均坡度', unit: '%' },
  { key: 'tree_share', label: '树冠比例', unit: '%', factor: 100 },
  { key: 'd_main_m', label: '距主干道', unit: 'm' },
  { key: 'cross_200m', label: '200 m 内路口', unit: '个' },
  { key: 'd_fac_m', label: '距最近设施', unit: 'm' },
  { key: 'no2_ugm3', label: '年度 NO₂', unit: 'µg/m³' },
  { key: 'pm25_ugm3', label: '年度 PM₂.₅', unit: 'µg/m³' },
]
function number(value: unknown, factor = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? (value * factor).toFixed(1) : '—'
}
</script>

<template>
  <aside class="map-details glass" aria-label="路段详情">
    <h3>道路环境</h3>
    <p class="hint">点击道路查看六维评分与原始指标。</p>
    <div class="toilet-options">
      <label><input v-model="inspection.toiletsEnabled" type="checkbox" :disabled="USE_MOCK" /> 洗手间</label>
      <label><input v-model="inspection.accessible" type="checkbox" :disabled="USE_MOCK || !inspection.toiletsEnabled" /> 仅无障碍</label>
    </div>
    <p v-if="USE_MOCK" class="hint">洗手间图层需连接后端。</p>
    <p v-if="toiletLoading" role="status">正在加载洗手间…</p>
    <p v-if="toiletError" role="alert">{{ toiletError }} <button @click="loadToilets">重试图层</button></p>
    <p v-if="inspection.loading" role="status">正在查询路段…</p>
    <p v-if="inspection.message" role="status">{{ inspection.message }}</p>
    <section v-if="inspection.selected" class="road-detail" aria-live="polite">
      <h4>{{ inspection.selected.properties.name || '未命名道路' }}</h4>
      <p>路段综合分 <b>{{ number(inspection.selected.properties.score) }}</b> · {{ inspection.selected.properties.grade }}</p>
      <table><thead><tr><th>维度</th><th>子分</th><th>权重</th></tr></thead>
        <tbody><tr v-for="d in dimensions" :key="d.key"><th>{{ d.label }}</th><td>{{ number(inspection.selected.properties[d.key]) }}</td><td>{{ meta.weights?.[d.weight] ?? '—' }}</td></tr></tbody>
      </table>
      <dl><template v-for="item in raw" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ number(inspection.selected.properties[item.key], item.factor) }} {{ item.unit }}</dd></template></dl>
    </section>
    <details class="data-notes">
      <summary>评分与数据说明</summary>
      <p v-if="metaError">{{ metaError }}</p>
      <p v-if="meta.grade_bins">五档分界 {{ meta.grade_bins.join(' / ') }} 分，以当前数据集为准。</p>
      <p v-for="d in dimensions" :key="d.key">{{ d.label }}权重 {{ meta.weights?.[d.weight] ?? '—' }}</p>
      <p v-for="note in meta.notes" :key="note">{{ note }}</p>
      <p>路段综合分用于环境评价。路线偏好匹配分随个人偏好计算。空气采用年度数据，安全和过街指标为代理指标。</p>
    </details>
  </aside>
</template>

<style scoped>
.map-details { position: absolute; top: 88px; right: 24px; width: 306px; padding: 18px; z-index: 4; max-height: 740px; overflow: auto; font-size: 13px; line-height: 1.6; }
h3 { font-size: 17px; margin-bottom: 8px; }
.hint { color: var(--muted); }
.toilet-options { display: flex; gap: 12px; margin: 14px 0; }
input { accent-color: var(--accent); }
table { width: 100%; border-collapse: collapse; margin-block: 10px; }
th, td { padding: 3px; text-align: right; border-bottom: 1px solid var(--line); }
th:first-child { text-align: left; }
dl { display: grid; grid-template-columns: 1fr auto; }
dd { text-align: right; }
details { margin-top: 16px; }
summary { cursor: pointer; }
details p { margin-top: 6px; }
button { text-decoration: underline; }
</style>
