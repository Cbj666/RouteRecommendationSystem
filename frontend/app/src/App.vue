<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { CSSProperties } from 'vue'
import FooterBar from './components/FooterBar.vue'
import LeftPanel from './components/LeftPanel.vue'
import LegendBox from './components/LegendBox.vue'
import MapStage from './components/MapStage.vue'
import RightPanel from './components/RightPanel.vue'
import StatusOverlay from './components/StatusOverlay.vue'
import TopBar from './components/TopBar.vue'
import { generate, loopCount, nextLoop, prevLoop } from './stores/planner'

/** 桌面：1600×1000 整体缩放（1440×900 → 0.9）；≤900px：单列文档流 */
const scale = ref(1)
const mobile = ref(false)

function fit(): void {
  mobile.value = window.innerWidth <= 900
  scale.value = Math.min(window.innerWidth / 1600, window.innerHeight / 1000)
}

const stageStyle = computed<CSSProperties>(() =>
  mobile.value ? {} : { transform: `translate(-50%, -50%) scale(${scale.value})` },
)

/** ←/→ 切换候选环线；输入框里不拦截 */
function onKeydown(e: KeyboardEvent): void {
  if (e.metaKey || e.ctrlKey || e.altKey) return
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
  void generate()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', fit)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="viewport">
    <div class="stage" :class="{ mobile }" :style="stageStyle">
      <MapStage />
      <TopBar />
      <LeftPanel />
      <RightPanel />
      <LegendBox />
      <FooterBar />
      <StatusOverlay />
    </div>
  </div>
</template>

<style scoped>
/* 移动端：单列、地图 16:10 置顶；覆盖各组件的 absolute 定位 */
.stage.mobile {
  position: static;
  width: 100%;
  height: auto;
  transform: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 10px 18px;
}

.stage.mobile :deep(.topbar) {
  position: sticky;
  top: 0;
  left: auto;
  right: auto;
  height: 56px;
  gap: 10px;
  padding: 0 12px;
  margin: -8px -10px 2px;
  order: -3;
  z-index: 10;
}

.stage.mobile :deep(.brand) {
  font-size: 16px;
  gap: 8px;
}

.stage.mobile :deep(.dot) {
  width: 18px;
  height: 18px;
}

.stage.mobile :deep(.dot::after) {
  inset: 5px;
}

.stage.mobile :deep(.tabs) {
  display: none;
}

.stage.mobile :deep(.search-wrap),
.stage.mobile :deep(.search) {
  width: auto;
  flex: 1;
  min-width: 0;
}

.stage.mobile :deep(.options) {
  width: 100%;
}

.stage.mobile :deep(.map-host) {
  position: relative;
  inset: auto;
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 10;
  order: -2;
}

.stage.mobile :deep(.map-host svg) {
  width: 100%;
  height: 100%;
}

.stage.mobile :deep(.left),
.stage.mobile :deep(.right),
.stage.mobile :deep(.legend) {
  position: static;
  inset: auto;
  width: auto;
  padding: 16px;
}

.stage.mobile :deep(.left) {
  padding-bottom: 0;
}

.stage.mobile :deep(.right) {
  margin-top: 0;
}

.stage.mobile :deep(.cta) {
  width: calc(100% + 32px);
  margin-left: -16px;
  margin-top: 18px;
}

.stage.mobile :deep(.legend) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stage.mobile :deep(.foot) {
  position: static;
  inset: auto;
  padding: 2px 2px 0;
}

.stage.mobile :deep(.overlay) {
  position: fixed;
  top: 64px;
  left: 12px;
  right: 12px;
  transform: none;
  max-width: none;
  z-index: 40;
}
</style>
