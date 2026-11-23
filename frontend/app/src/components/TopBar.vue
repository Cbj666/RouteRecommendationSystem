<script setup lang="ts">
import { computed, ref } from 'vue'
import { PRESET_ORIGINS, setOrigin, state, type Origin } from '../stores/planner'

const tabs = [
  { key: 'map', label: '适宜性地图' },
  { key: 'loops', label: '环线推荐' },
  { key: 'compare', label: '起点对比' },
] as const

const query = ref('')
const open = ref(false)
const active = ref(0)

/** 无 AK 时的降级搜索：内置起点模糊匹配（M3 换 LocalSearch） */
const matches = computed<Origin[]>(() => {
  const k = query.value.trim()
  const list = k ? PRESET_ORIGINS.filter((o) => o.name.includes(k)) : PRESET_ORIGINS
  return list.slice(0, 5)
})

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

function choose(o: Origin): void {
  setOrigin(o, 'preset')
  query.value = ''
  open.value = false
  ;(document.activeElement as HTMLElement | null)?.blur()
}

function onKeydown(e: KeyboardEvent): void {
  if (!open.value) show()
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = Math.min(active.value + 1, matches.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = Math.max(active.value - 1, 0)
  } else if (e.key === 'Enter') {
    const pick = matches.value[active.value]
    if (pick) choose(pick)
  } else if (e.key === 'Escape') {
    open.value = false
  }
}
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
        aria-label="搜索起点"
        aria-controls="origin-list"
        :aria-expanded="open"
        autocomplete="off"
        placeholder="搜索起点：东湖绿道 / 珞珈山 / 江滩…"
        @focus="show"
        @input="show"
        @blur="hide"
        @keydown="onKeydown"
      />
      <ul v-if="open" id="origin-list" class="options" role="listbox" aria-label="内置起点">
        <li
          v-for="(o, i) in matches"
          :key="o.name"
          class="option"
          :class="{ active: i === active }"
          role="option"
          :aria-selected="i === active"
          @mousedown.prevent="choose(o)"
          @mouseenter="active = i"
        >
          <b>{{ o.name }}</b>
          <span class="num">{{ o.lng.toFixed(4) }}, {{ o.lat.toFixed(4) }}</span>
        </li>
        <li v-if="matches.length === 0" class="option empty">没有匹配的起点，试试「武大」「东湖」</li>
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
  width: 300px;
}

.search {
  width: 300px;
  height: 38px;
  padding: 0 18px;
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
  width: 300px;
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

.option b {
  font-size: 13.5px;
  font-weight: 600;
}

.option .num {
  font-size: 11.5px;
  color: var(--muted);
}

.option.active {
  background: var(--accent-weak);
}

.option.empty {
  font-size: 12.5px;
  color: var(--muted);
  cursor: default;
}

/* search 元素自带的清除按钮在窄框里会挤占文字 */
.search::-webkit-search-cancel-button {
  display: none;
}
</style>
