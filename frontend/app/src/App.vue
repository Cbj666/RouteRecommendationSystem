<script setup lang="ts">
import { ref } from 'vue'
import ControlPanel from './components/ControlPanel.vue'
import MapPanel from './components/MapPanel.vue'
import ResultPanel from './components/ResultPanel.vue'
import { state, requestPayload } from './store'
import { fetchLoops } from './api/client'

const mapRef = ref<InstanceType<typeof MapPanel> | null>(null)

async function generate() {
  state.loading = true
  state.error = null
  const t0 = performance.now()
  try {
    const fc = await fetchLoops(requestPayload())
    state.loops = fc.features ?? []
    state.activeIndex = 0
    state.lastMs = Math.round(performance.now() - t0)
    mapRef.value?.drawLoops(state.loops)
    if (!state.loops.length && fc.message) state.error = fc.message
  } catch (e) {
    state.error = e instanceof Error ? e.message : String(e)
  } finally {
    state.loading = false
  }
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand"><span class="dot">跑</span> 跑步友好度 · 武汉</div>
      <nav>
        <a class="on">适宜性地图</a>
        <a>环线推荐</a>
        <a>起点对比</a>
      </nav>
      <div class="search">🔍 搜索起点：东湖绿道 / 珞珈山 / 江滩…</div>
    </header>

    <main>
      <ControlPanel class="card" :loading="state.loading" @generate="generate" />
      <MapPanel ref="mapRef" class="card" />
      <ResultPanel class="card" />
    </main>

    <footer v-if="state.error" class="err">{{ state.error }}</footer>
  </div>
</template>

<style scoped>
.shell { display: flex; flex-direction: column; height: 100%; }

.topbar {
  height: 62px; display: flex; align-items: center; gap: 26px;
  padding: 0 22px; background: var(--panel); border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; }
.brand .dot {
  width: 22px; height: 22px; border-radius: 7px; background: var(--accent);
  display: grid; place-items: center; color: #fff; font-size: 13px;
}
nav { display: flex; gap: 4px; margin-left: 6px; }
nav a { padding: 7px 13px; border-radius: 9px; color: var(--muted); font-size: 14px; cursor: default; }
nav a.on { background: var(--accent-weak); color: var(--accent); font-weight: 600; }
.search {
  margin-left: auto; background: var(--bg); border: 1px solid var(--line);
  border-radius: 10px; padding: 8px 12px; width: 300px; color: var(--muted); font-size: 13px;
}

main {
  display: grid;
  grid-template-columns: 314px minmax(0, 1fr) 292px;
  gap: 14px; padding: 14px;
  flex: 1; min-height: 0;
}
.err {
  padding: 8px 16px; background: #fdecea; color: var(--warn);
  font-size: 12.5px; border-top: 1px solid #f5c6bd;
}
</style>
