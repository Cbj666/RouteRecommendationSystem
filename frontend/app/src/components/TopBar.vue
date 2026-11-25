<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  PRESET_ORIGINS,
  clearPlaces,
  pickOriginOrDest,
  searchPlaces,
  selectPlace,
  state,
  type Origin,
} from '../stores/planner'
import type { Place } from '../types'

const tabs = [
  { key: 'map', label: '适宜性地图' },
  { key: 'loops', label: '环线推荐' },
] as const

type Option =
  | { kind: 'preset'; key: string; origin: Origin }
  | { kind: 'place'; key: string; index: number; place: Place }

const query = ref('')
const open = ref(false)
const active = ref(0)
let debounce = 0
/** 选中后回填地点名时，跳过 query watcher 的一次触发，避免又搜一遍。 */
let suppress = false

const keywords = computed(() => query.value.trim())

/**
 * 空关键词：本地预设起点；有词：只展示与当前词一致的搜索结果。
 * 输入还在 280ms 防抖窗口内（placeQuery 落后）时先不展示旧结果，避免张冠李戴。
 */
const options = computed<Option[]>(() => {
  const k = keywords.value
  if (!k) {
    return PRESET_ORIGINS.map((origin) => ({ kind: 'preset', key: `preset:${origin.name}`, origin }))
  }
  if (state.placeLoading || k !== state.placeQuery) return []
  return state.places.map((place, index) => ({
    kind: 'place',
    key: `place:${place.id}:${index}`,
    index,
    place,
  }))
})

const status = computed<'idle' | 'loading' | 'pending' | 'error' | 'empty'>(() => {
  const k = keywords.value
  if (!k) return 'idle'
  if (state.placeLoading) return 'loading'
  if (k !== state.placeQuery) return 'pending'
  if (state.placeError) return 'error'
  return state.places.length ? 'idle' : 'empty'
})

function subtitle(option: Option): string {
  if (option.kind === 'preset') {
    return `${option.origin.lng.toFixed(4)}, ${option.origin.lat.toFixed(4)}`
  }
  const p = option.place
  return [p.district, p.address].filter(Boolean).join(' · ') || p.city || '高德地点'
}

function show(): void {
  open.value = true
  active.value = 0
}

function hide(event: FocusEvent): void {
  const input = event.currentTarget
  window.setTimeout(() => {
    if (document.activeElement !== input) open.value = false
  }, 120)
}

function choose(option: Option): void {
  window.clearTimeout(debounce)
  debounce = 0
  const name = option.kind === 'preset' ? option.origin.name : option.place.name
  // 预设起点与搜索结果都走同一入口：环线设起点，单行线依次设 A / B
  if (option.kind === 'preset') pickOriginOrDest(option.origin, 'preset')
  else selectPlace(option.place)

  suppress = true
  query.value = name
  open.value = false
  active.value = 0
  ;(document.activeElement as HTMLElement | null)?.blur()
  void nextTick(() => {
    suppress = false
  })
}

async function submit(): Promise<void> {
  const pick = options.value[active.value] ?? options.value[0]
  if (pick) {
    choose(pick)
    return
  }
  const k = keywords.value
  if (!k) return
  // 防抖还没触发（或上次失败）时按回车：立即搜一次，有结果就选中第一条
  window.clearTimeout(debounce)
  debounce = 0
  await searchPlaces(k)
  const first = options.value[0]
  if (first) choose(first)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.isComposing) return
  if (!open.value) show()
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!options.value.length) return
    active.value = (active.value + 1) % options.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (!options.value.length) return
    active.value = (active.value - 1 + options.value.length) % options.value.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    void submit()
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

watch(keywords, (k) => {
  if (suppress) return
  window.clearTimeout(debounce)
  debounce = 0
  active.value = 0
  if (!k) {
    clearPlaces()
    open.value = true
    return
  }
  debounce = window.setTimeout(() => {
    debounce = 0
    void searchPlaces(k)
  }, 280)
})

watch(options, (list) => {
  if (active.value >= list.length) active.value = 0
})

onBeforeUnmount(() => {
  window.clearTimeout(debounce)
})
</script>

<template>
  <header class="topbar">
    <div class="brand"><span class="dot" aria-hidden="true"></span>跑步友好度 · 武汉</div>

    <nav class="tabs" aria-label="页面导航">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="tab"
        :class="{ on: t.key === state.tab }"
        :aria-current="t.key === state.tab ? 'page' : undefined"
        @click="state.tab = t.key"
      >
        {{ t.label }}
      </button>
    </nav>
    <div v-if="state.tab === 'loops'" class="search-wrap">
      <input
        v-model="query"
        class="search"
        type="search"
        role="combobox"
        aria-label="搜索地点并设为起点"
        aria-controls="origin-list"
        aria-autocomplete="list"
        :aria-expanded="open"
        :aria-activedescendant="open && options.length ? `origin-opt-${active}` : undefined"
        :maxlength="64"
        autocomplete="off"
        placeholder="搜索地点：武汉大学 / 东湖 / 黄鹤楼…"
        @focus="show"
        @input="show"
        @blur="hide"
        @keydown="onKeydown"
      />
      <ul
        v-if="open"
        id="origin-list"
        class="options"
        role="listbox"
        :aria-label="keywords ? '地点搜索结果' : '内置起点'"
      >
        <li v-if="status === 'loading'" class="option empty">正在搜索「{{ keywords }}」…</li>
        <li v-else-if="status === 'pending'" class="option empty">正在输入…</li>
        <li v-else-if="status === 'error'" class="option empty error">{{ state.placeError }}</li>
        <li v-else-if="status === 'empty'" class="option empty">
          没有找到「{{ keywords }}」，换个关键词试试
        </li>
        <template v-else>
          <li
            v-for="(option, i) in options"
            :id="`origin-opt-${i}`"
            :key="option.key"
            class="option"
            :class="{ active: i === active }"
            role="option"
            :aria-selected="i === active"
            @mousedown.prevent="choose(option)"
            @mouseenter="active = i"
          >
            <span class="row">
              <span v-if="option.kind === 'place'" class="badge">{{ option.index + 1 }}</span>
              <span v-else class="badge preset">预</span>
              <b>{{ option.kind === 'preset' ? option.origin.name : option.place.name }}</b>
            </span>
            <span class="num">{{ subtitle(option) }}</span>
          </li>
          <li v-if="options.length && options[0].kind === 'place'" class="hint">
            编号与地图标记一致，选中即设为起点
          </li>
        </template>
      </ul>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 64px;
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 0 28px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(21, 80, 60, 0.08);
  z-index: 5;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.dot {
  width: 22px;
  height: 22px;
  background: var(--accent);
  position: relative;
}

.dot::after {
  content: '';
  position: absolute;
  inset: 6px;
  background: #fff;
}

.tabs {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.tab {
  padding: 7px 16px;
  font-size: 15px;
  color: var(--sub);
}

.tab.on {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}

.tab:not(.on):hover { background: var(--accent-weak); }

.search-wrap {
  position: relative;
  margin-left: auto;
  width: 320px;
}

.search {
  width: 320px;
  height: 38px;
  padding: 0 14px;
  font-size: 14px;
  color: var(--ink);
  border: 1px solid #e2eae5;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 0;
  outline: none;
}

.search::placeholder {
  color: var(--muted);
}

.search:focus {
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.86);
}

.options {
  position: absolute;
  top: 44px;
  right: 0;
  width: 320px;
  max-height: min(420px, 62vh);
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.97);
  backdrop-filter: blur(18px);
  border: 1px solid var(--line);
  box-shadow: 0 14px 44px rgba(18, 58, 44, 0.13);
  z-index: 20;
}

.option {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 9px 14px;
  cursor: pointer;
}

.option + .option {
  border-top: 1px dashed var(--dash);
}

.option .row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.option b {
  font-size: 13.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
}

.badge.preset {
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--line);
  font-weight: 500;
}

.option .num {
  padding-left: 26px;
  font-size: 11.5px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option.active {
  background: var(--accent-weak);
}

.option.empty {
  font-size: 12.5px;
  color: var(--muted);
  cursor: default;
}

.option.error {
  color: #a33b2f;
}

.hint {
  padding: 6px 14px;
  border-top: 1px dashed var(--dash);
  font-size: 11px;
  color: var(--faint);
  cursor: default;
}

/* search 元素自带的清除按钮在窄框里会挤占文字 */
.search::-webkit-search-cancel-button {
  display: none;
}
</style>
