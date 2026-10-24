<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { LoopFeature } from '../types'
import { state } from '../store'

/**
 * 百度地图面板（卡片 1 的核心）。
 *
 * 现在只有一个占位 div + SVG 预览：不依赖 AK 也能看到环线形状。
 * TODO(卡片 1)：
 *   1. index.html 里启用百度脚本，用 import.meta.env.VITE_BAIDU_AK；
 *   2. new BMapGL.Map(el)，设置中心为 state.origin，缩放 14；
 *   3. loops.forEach → new BMapGL.Polyline(points)，颜色按 rank；
 *   4. 点击地图 → map.addEventListener('click') → 更新 state.origin；
 *   5. 坐标转换：WGS84 → BD-09（只在这里做一次）。
 */

const el = ref<HTMLDivElement | null>(null)
const svgPaths = ref<string[]>([])

/** 把经纬度投到 0–100 的 SVG 视口，仅用于占位预览 */
function project(loops: LoopFeature[]) {
  if (!loops.length || !el.value) return
  const all = loops.flatMap((l) => l.geometry.coordinates)
  const lngs = all.map((c) => c[0])
  const lats = all.map((c) => c[1])
  const minX = Math.min(...lngs), maxX = Math.max(...lngs)
  const minY = Math.min(...lats), maxY = Math.max(...lats)
  const sx = (x: number) => ((x - minX) / (maxX - minX || 1)) * 90 + 5
  const sy = (y: number) => 95 - ((y - minY) / (maxY - minY || 1)) * 90
  svgPaths.value = loops.map((l) =>
    l.geometry.coordinates.map((c, i) => `${i ? 'L' : 'M'}${sx(c[0]).toFixed(2)},${sy(c[1]).toFixed(2)}`).join(' '),
  )
}

function drawLoops(loops: LoopFeature[]) {
  project(loops)
  // TODO(卡片 1): 这里是接百度地图 Polyline 的位置
}

onMounted(() => drawLoops(state.loops))

defineExpose({ drawLoops })
</script>

<template>
  <section class="map" ref="el">
    <div class="placeholder">
      <p><b>百度地图占位</b></p>
      <p>接入 AK 后，这里替换为 <code>BMapGL.Map</code>，并把环线画成 Polyline。</p>
      <p class="hint">下方是当前接口返回的环线形状预览（SVG，仅用于验证数据）。</p>
    </div>

    <svg class="preview" viewBox="0 0 100 100" preserveAspectRatio="none">
      <path
        v-for="(d, i) in svgPaths"
        :key="i"
        :d="d"
        fill="none"
        :stroke="['#111111', '#2f7d5d', '#8c6d1f'][i % 3]"
        stroke-width="1.4"
        stroke-linejoin="round"
      />
    </svg>

    <div class="legend">
      <b>慢跑适宜性</b>
      <div class="bar"></div>
      <div class="row"><span class="num">30 差</span><span class="num">60 中</span><span class="num">85 好</span></div>
    </div>

    <div class="tag" v-if="state.loops.length">
      <b>{{ state.loops.length }}</b> 条候选 · 耗时 {{ state.lastMs }} ms
    </div>
  </section>
</template>

<style scoped>
.map { position: relative; overflow: hidden; min-height: 0; }
.placeholder {
  position: absolute; inset: 0; display: grid; place-content: center;
  text-align: center; color: var(--muted); font-size: 13px; line-height: 1.8;
  background: repeating-linear-gradient(45deg, #f7f8fa, #f7f8fa 12px, #f2f4f7 12px, #f2f4f7 24px);
  padding: 24px;
}
.placeholder code { background: #eef1f5; padding: 1px 5px; border-radius: 4px; }
.hint { font-size: 12px; opacity: .8; }

.preview { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }

.legend {
  position: absolute; left: 16px; bottom: 16px; width: 196px;
  background: rgba(255, 255, 255, .95); border: 1px solid var(--line);
  border-radius: 11px; padding: 10px 12px; font-size: 12px; box-shadow: var(--shadow);
}
.legend .bar {
  height: 9px; border-radius: 5px; margin: 7px 0 4px;
  background: linear-gradient(90deg, #c8553d, #f0a35e, #e8dc7a, #8fc98a, #2f7d5d);
}
.legend .row { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px; }

.tag {
  position: absolute; top: 14px; left: 16px; background: rgba(255, 255, 255, .95);
  border: 1px solid var(--line); border-radius: 10px; padding: 8px 11px;
  font-size: 12.5px; box-shadow: var(--shadow);
}
</style>
