<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import FooterBar from './components/FooterBar.vue'
import HotspotPage from './components/HotspotPage.vue'
import LayerPanel from './components/LayerPanel.vue'
import LeftPanel from './components/LeftPanel.vue'
import LegendBox from './components/LegendBox.vue'
import MapStage from './components/MapStage.vue'
import MapDetails from './components/MapDetails.vue'
import RightPanel from './components/RightPanel.vue'
import StatusOverlay from './components/StatusOverlay.vue'
import TopBar from './components/TopBar.vue'
import { generate, loopCount, nextLoop, prevLoop, state } from './stores/planner'

/** 空间足够时沿用答辩画布，小窗口使用原字号的单列文档流。 */
const scale = ref(1)
const mobile = ref(false)

function fit(): void {
  mobile.value = window.matchMedia('(max-width: 1100px), (max-height: 680px)').matches
  scale.value = Math.min(window.innerWidth / 1600, window.innerHeight / 1000)
}

const stageStyle = computed<CSSProperties>(() =>
  mobile.value ? {} : { transform: `translate(-50%, -50%) scale(${scale.value})` },
)

/** ←/→ 切换候选环线；输入框里不拦截 */
function onKeydown(e: KeyboardEvent): void {
  if (e.metaKey || e.ctrlKey || e.altKey) return
  if (state.tab !== 'loops' || state.mode !== 'loop') return
  const el = e.target as HTMLElement | null
  if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return
  if (loopCount.value < 2) return
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    prevLoop()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    nextLoop()
  }
}

onMounted(() => {
  fit()
  window.addEventListener('resize', fit)
  window.addEventListener('keydown', onKeydown)
})

watch(() => state.tab, (tab) => {
  if (tab === 'loops' && state.mode === 'loop' && !state.loops && !state.loading && !state.error) {
    void generate()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', fit)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="viewport">
    <div class="stage" :class="{ mobile, 'map-mode': state.tab === 'map' }" :style="stageStyle">
      <TopBar />
      <HotspotPage v-if="state.tab === 'hotspots'" />
      <template v-else>
        <MapStage :browse="state.tab === 'map'" />
        <MapDetails v-if="state.tab === 'map'" />
        <template v-if="state.tab === 'loops'">
          <LeftPanel />
          <RightPanel />
        </template>
        <LayerPanel />
        <LegendBox />
        <FooterBar />
        <StatusOverlay />
      </template>
    </div>
  </div>
</template>

<style scoped>
.stage:not(.mobile).map-mode :deep(.layers) {
  top: 88px;
  bottom: auto;
  max-height: 660px;
}

@media (max-width: 1100px), (max-height: 680px) {
/* 移动端：单列、地图 16:10 置顶；覆盖各组件的 absolute 定位 */
.stage {
  position: static;
  width: 100%;
  height: auto;
  transform: none !important;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 10px 18px;
}

.stage :deep(.topbar) {
  position: sticky;
  top: 0;
  left: auto;
  right: auto;
  height: auto;
  min-height: 56px;
  flex-wrap: wrap;
  gap: 8px 10px;
  padding: 8px 12px;
  margin: -8px -10px 2px;
  order: -3;
  z-index: 10;
}

.stage :deep(.brand) {
  font-size: 16px;
  gap: 8px;
}

.stage :deep(.dot) {
  width: 18px;
  height: 18px;
}

.stage :deep(.dot::after) {
  inset: 5px;
}

.stage :deep(.tabs) { order: 2; width: 100%; margin: 0; }
.stage :deep(.tab) {
  flex: 1;
  padding-inline: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.stage :deep(.search-wrap),
.stage :deep(.search) {
  width: auto;
  flex: 1;
  min-width: 0;
}

.stage :deep(.search) {
  width: 100%;
  padding-inline: 10px;
}

.stage :deep(.options) {
  width: 100%;
  min-width: min(180px, 75vw);
}

.stage :deep(.map-frame) {
  position: relative;
  inset: auto;
  width: min(100%, 72svh);
  aspect-ratio: 16 / 10;
  align-self: center;
  order: -2;
}

.stage :deep(.map-controls) {
  bottom: 8px;
  left: auto;
  right: 8px;
  transform: none !important;
}

.stage :deep(.left),
.stage :deep(.right),
.stage :deep(.map-details),
.stage :deep(.legend) {
  position: static;
  inset: auto;
  width: auto;
  padding: 16px;
}
.stage :deep(.map-details) { max-height: none; }

.stage :deep(.left) {
  padding-bottom: 0;
}

.stage :deep(.left .origin) {
  padding-bottom: 10px;
}

.stage :deep(.left .row) {
  margin-top: 12px;
}

.stage :deep(.left .label) {
  margin-bottom: 6px;
}

.stage :deep(.left .pref) {
  min-height: 40px;
  padding-block: 8px;
}

.stage :deep(.right) {
  margin-top: 0;
}

.stage :deep(.cta) {
  width: calc(100% + 32px);
  margin-left: -16px;
  margin-top: 12px;
  padding-block: 12px;
}

.stage :deep(.legend) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 图层面板放在路线设置与结果之后。 */
.stage :deep(.layers) {
  position: static;
  inset: auto;
  width: auto;
  max-height: none;
  overflow: visible;
  padding: 16px;
}

.stage :deep(.layers-body) {
  overflow: visible;
  margin-right: 0;
  padding-right: 0;
}

.stage :deep(.foot) {
  position: static;
  inset: auto;
  padding: 2px 2px 0;
}

.stage :deep(.overlay) {
  position: fixed;
  top: 64px;
  left: 12px;
  right: 12px;
  transform: none !important;
  max-width: none;
  z-index: 40;
}
}
</style>
