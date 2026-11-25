<script setup lang="ts">
import { computed, ref } from 'vue'
import { LAYER_GROUP_LABELS, SWATCH } from '../map/layerConfig'
import {
  roadSuitabilityEnabled,
  state,
  toggleLayer,
} from '../stores/planner'
import type { LayerStyle } from '../types'

interface LayerRow {
  id: string
  label: string
  count: number
  enabled: boolean
  loading: boolean
  style: LayerStyle
  title?: string
}

interface LayerGroup {
  label: string
  rows: LayerRow[]
}

const expanded = ref(true)

const manifest = computed(() => state.manifest)

const errorText = computed(() => {
  if (state.layerError) return state.layerError
  if (state.mapError) return `图层清单加载失败：${state.mapError}`
  return ''
})

const groups = computed<LayerGroup[]>(() => {
  const current = state.manifest
  if (!current) return []
  const rowsByGroup = new Map<string, LayerRow[]>()
  const groupOrder: string[] = []

  const push = (group: string, row: LayerRow): void => {
    let rows = rowsByGroup.get(group)
    if (!rows) {
      rows = []
      rowsByGroup.set(group, rows)
      groupOrder.push(group)
    }
    rows.push(row)
  }

  for (const def of current.layers) {
    if (def.variant === 'roads') {
      push(def.group, {
        id: 'roads',
        label: '适宜性路网',
        count: def.count,
        enabled: roadSuitabilityEnabled.value,
        loading: !!state.layerLoading[def.id] || state.roadsDetailLoading,
        style: 'score',
        title: '低缩放显示全市概览路网，放大后按当前视口自动加载细粒度评分路段',
      })
      continue
    }
    push(def.group, {
      id: def.id,
      label: def.label,
      count: def.count,
      enabled: !!state.layersEnabled[def.id],
      loading: !!state.layerLoading[def.id],
      style: def.style,
    })
  }

  const orderedGroups: LayerGroup[] = []
  for (const label of LAYER_GROUP_LABELS) {
    const rows = rowsByGroup.get(label)
    if (rows) orderedGroups.push({ label, rows })
  }
  for (const label of groupOrder) {
    if (!orderedGroups.some((group) => group.label === label)) {
      const rows = rowsByGroup.get(label)
      if (rows) orderedGroups.push({ label, rows })
    }
  }
  return orderedGroups
})

const countText = computed(() => {
  const summary = state.manifest?.summary
  if (!summary) return '正在读取图层清单…'
  const roadMode = state.roadsDetailed ? '视口细粒度路网' : '全市概览路网'
  return `${summary.layers} 个图层 · ${roadMode}`
})

function fmtCount(n: number): string {
  return n.toLocaleString('en-US')
}

function swatchStyle(style: LayerStyle): Record<string, string> {
  return { background: SWATCH[style] }
}
</script>

<template>
  <section class="layers glass" aria-label="数据图层">
    <div class="layers-head">
      <h4 class="layers-title">数据图层</h4>
      <button
        type="button"
        class="layers-toggle"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>
    <div class="layers-count">{{ countText }}</div>

    <div v-if="!manifest && !errorText" class="layers-loading">正在读取图层清单…</div>
    <div v-else-if="errorText" class="layers-err">{{ errorText }}</div>
    <div v-else v-show="expanded" class="layers-body">
      <div v-for="group in groups" :key="group.label" class="layer-group">
        <div class="group-name">{{ group.label }}</div>
        <template v-for="row in group.rows" :key="row.id">
          <div class="layer-row" :data-layer="row.id" :title="row.title">
            <button
              type="button"
              class="layer-check"
              role="switch"
              :aria-checked="row.enabled"
              :aria-label="row.label"
              @click="toggleLayer(row.id)"
            >
              <span class="knob" aria-hidden="true"></span>
            </button>
            <span
              class="swatch"
              :class="{
                'swatch-facility': row.style === 'facility',
                'swatch-toilet': row.style === 'toilet',
              }"
              :style="swatchStyle(row.style)"
              aria-hidden="true"
            ></span>
            <span class="layer-name">{{ row.label }}</span>
            <span v-if="row.loading" class="layer-loading" aria-label="加载中">…</span>
            <span class="layer-n">{{ fmtCount(row.count) }}</span>
          </div>
          <!-- 公厕无障碍子筛选 -->
          <label v-if="row.id === 'toilets' && row.enabled" class="sub-filter">
            <input v-model="state.accessibleOnly" type="checkbox" />
            <span>仅显示无障碍标注</span>
          </label>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.layers {
  position: absolute;
  left: 24px;
  bottom: 44px;
  width: 306px;
  z-index: 4;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 248px;
  overflow: hidden;
}

.layers-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.layers-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.5px;
}

.layers-toggle {
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
}

.layers-toggle:hover {
  color: var(--accent);
}

.layers-count {
  margin-top: -2px;
  font-size: 10.5px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.layers-loading {
  padding: 6px 0;
  font-size: 12px;
  color: var(--muted);
}

.layers-err {
  padding: 4px 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: #a33333;
}

.layers-body {
  min-height: 0;
  overflow-y: auto;
  margin: 2px -4px 0 0;
  padding-right: 4px;
}

.layer-group {
  margin-top: 6px;
}

.layer-group:first-child {
  margin-top: 0;
}

.group-name {
  margin-bottom: 2px;
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--muted);
}

.layer-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  font-size: 12px;
  color: var(--sub);
}

.layer-row:hover {
  color: var(--ink);
}

.layer-check {
  position: relative;
  flex: none;
  width: 26px;
  height: 14px;
  padding: 0;
  border: 0;
  background: #d7e0da;
  cursor: pointer;
}

.layer-check .knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  background: #fff;
  transition: left 0.12s ease;
}

.layer-check[aria-checked='true'] {
  background: var(--accent);
}

.layer-check[aria-checked='true'] .knob {
  left: 14px;
}

.swatch {
  flex: none;
  width: 10px;
  height: 10px;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}

.swatch-facility {
  border-radius: 2px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.9);
}

.swatch-toilet {
  border-radius: 50%;
  box-shadow: 0 0 0 1.5px #fff, 0 0 0 2px rgba(29, 78, 216, 0.3);
}

.sub-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0 3px 32px;
  font-size: 11px;
  color: var(--muted);
  cursor: pointer;
}

.sub-filter input {
  accent-color: #1d4ed8;
}

.layer-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layer-n {
  flex: none;
  font-size: 10.5px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.layer-loading {
  flex: none;
  font-size: 10.5px;
  color: var(--accent);
}
</style>
