<script setup lang="ts">
import { computed, ref } from 'vue'
import { LAYER_GROUP_LABELS, SWATCH } from '../map/layerConfig'
import {
  roadSuitabilityEnabled,
  setExtent,
  state,
  toggleLayer,
} from '../stores/planner'
import type { LayerStyle } from '../types'

interface LayerRow {
  /** data-layer 值：普通图层 = 图层 id；适宜性路网 = "roads"；全量路网 = "roads_all" */
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

/**
 * 面板行：13 个 manifest 图层里 3 个路网变体合成 2 行
 * - 「适宜性路网」= 当前 extent 对应的核心 / 干道变体（单行，data-layer="roads"）
 * - 「全量路网（9 万段，加载较慢）」= roads_all 单独开关，开启自动切全城
 */
const groups = computed<LayerGroup[]>(() => {
  const current = state.manifest
  if (!current) return []
  const rowsByGroup = new Map<string, LayerRow[]>()
  const groupOrder: string[] = []
  let roadsRowAdded = false

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
      if (def.variantLevel === 'all') {
        push(def.group, {
          id: 'roads_all',
          label: '全量路网（9 万段，加载较慢）',
          count: def.count,
          enabled: !!state.layersEnabled['roads_all'],
          loading: !!state.layerLoading['roads_all'],
          style: 'score',
          title: '全量路网（约 9 万段，加载较慢），开启后自动切到全城',
        })
      } else if (!roadsRowAdded) {
        roadsRowAdded = true
        // 这一行的计数/加载态始终跟随当前 extent 的“适宜性路网”变体，
        // 与单独的“全量路网”开关解耦（否则开全量后两行都显示 90,193）
        const suitabilityId = state.extent === 'central' ? 'roads_central' : 'roads_arterial'
        const suitabilityDef = current.layers.find((layer) => layer.id === suitabilityId)
        push(def.group, {
          id: 'roads',
          label: '适宜性路网',
          count: suitabilityDef?.count ?? def.count,
          enabled: roadSuitabilityEnabled.value,
          loading: !!state.layerLoading[suitabilityId],
          style: 'score',
          title: '按慢跑适宜性分段着色；数据随「片区 / 全城」自动切换',
        })
      }
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
  return `${summary.spatial_files} 个空间文件 · ${summary.layers} 个图层`
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

    <div class="extent" role="group" aria-label="地图范围">
      <button
        type="button"
        class="extent-btn"
        :class="{ on: state.extent === 'central' }"
        data-extent="central"
        :aria-pressed="state.extent === 'central'"
        @click="setExtent('central')"
      >
        片区
      </button>
      <button
        type="button"
        class="extent-btn"
        :class="{ on: state.extent === 'city' }"
        data-extent="city"
        :aria-pressed="state.extent === 'city'"
        @click="setExtent('city')"
      >
        全城
      </button>
    </div>

    <div v-if="!manifest && !errorText" class="layers-loading">正在读取图层清单…</div>
    <div v-else-if="errorText" class="layers-err">{{ errorText }}</div>
    <div v-else v-show="expanded" class="layers-body">
      <div v-for="group in groups" :key="group.label" class="layer-group">
        <div class="group-name">{{ group.label }}</div>
        <div
          v-for="row in group.rows"
          :key="row.id"
          class="layer-row"
          :data-layer="row.id"
          :title="row.title"
        >
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
          <span class="swatch" :style="swatchStyle(row.style)" aria-hidden="true"></span>
          <span class="layer-name">{{ row.label }}</span>
          <span v-if="row.loading" class="layer-loading" aria-label="加载中">…</span>
          <span class="layer-n">{{ fmtCount(row.count) }}</span>
        </div>
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
  /* 左主面板 bottom=705，面板从 1000-44 向上最多 248px，保证不遮挡 */
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

.extent {
  display: flex;
  gap: 6px;
}

.extent-btn {
  flex: 1;
  padding: 4px 0;
  border: 1px solid #dfe8e3;
  background: transparent;
  color: var(--sub);
  font-size: 12px;
  cursor: pointer;
}

.extent-btn.on {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
  font-weight: 600;
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
