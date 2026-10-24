<script setup lang="ts">
import { computed } from 'vue'
import { state } from '../store'

const loop = computed(() => state.loops[state.activeIndex])

const sub = computed<Record<string, number>>(() => {
  const raw = loop.value?.properties.sub
  if (!raw) return {}
  try { return JSON.parse(raw) as Record<string, number> } catch { return {} }
})

const bars = computed(() => [
  { label: '安全（避开主干道）', value: sub.value.s_safety ?? 0 },
  { label: '绿化与滨水', value: sub.value.s_green ?? 0 },
  { label: '坡度平缓', value: sub.value.s_slope ?? 0 },
])
</script>

<template>
  <section class="panel">
    <div>
      <h3>推荐环线</h3>
      <div class="head">
        <span class="big num">{{ loop ? loop.properties.score.toFixed(1) : '—' }}</span>
        <span class="unit">/ 100</span>
        <span class="pill" v-if="loop">{{ loop.properties.length_m < 4500 ? '短距离' : '标准' }}</span>
      </div>
    </div>

    <div class="kpis">
      <div class="kpi"><span>距离</span><b class="num">{{ loop ? (loop.properties.length_m / 1000).toFixed(2) + ' km' : '—' }}</b></div>
      <div class="kpi"><span>预计用时</span><b class="num">{{ loop ? loop.properties.minutes + ' min' : '—' }}</b></div>
      <div class="kpi"><span>树冠覆盖</span><b class="num">{{ loop ? Math.round(loop.properties.tree_share * 100) + '%' : '—' }}</b></div>
      <div class="kpi"><span>平均坡度</span><b class="num">{{ loop ? loop.properties.slope_mean_pct.toFixed(1) + '%' : '—' }}</b></div>
      <div class="kpi"><span>最近场馆</span><b class="num">{{ loop ? Math.round(loop.properties.facility_m) + ' m' : '—' }}</b></div>
      <div class="kpi"><span>候选序号</span><b class="num">{{ loop ? '#' + loop.properties.rank : '—' }}</b></div>
    </div>

    <div class="bars">
      <div class="bar-row" v-for="b in bars" :key="b.label">
        <div class="t"><span>{{ b.label }}</span><span class="num">{{ Math.round(b.value) }}</span></div>
        <div class="track"><div class="fill" :style="{ width: b.value + '%' }"></div></div>
      </div>
    </div>

    <div class="switch" v-if="state.loops.length > 1">
      <button
        v-for="(l, i) in state.loops"
        :key="i"
        :class="{ on: i === state.activeIndex }"
        @click="state.activeIndex = i"
      >#{{ l.properties.rank }}</button>
    </div>

    <p class="note">
      环线由「半程折返 + 去程边双向惩罚」生成：先找目标距离一半处的折点，
      去程与回程禁止重走同一段。坡度来自 SRTM 30 m，城区精度约 ±1 个百分点。
    </p>
  </section>
</template>

<style scoped>
.panel { padding: 16px; display: flex; flex-direction: column; gap: 14px; min-height: 0; overflow: auto; }
.head { display: flex; align-items: baseline; gap: 8px; }
.big { font-size: 40px; font-weight: 700; line-height: 1; color: var(--accent); }
.unit { font-size: 13px; color: var(--muted); }
.pill { font-size: 11px; padding: 3px 8px; border-radius: 999px; background: var(--accent-weak); color: var(--accent); font-weight: 600; }

.kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.kpi { background: var(--bg); border-radius: 10px; padding: 9px 10px; }
.kpi span { display: block; font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.kpi b { font-size: 16px; }

.bars { display: flex; flex-direction: column; gap: 9px; }
.bar-row { font-size: 12px; color: var(--muted); }
.bar-row .t { display: flex; justify-content: space-between; margin-bottom: 4px; color: var(--ink); }
.track { height: 7px; border-radius: 5px; background: #eceff3; overflow: hidden; }
.fill { height: 100%; background: var(--accent); border-radius: 5px; }

.switch { display: flex; gap: 6px; }
.switch button {
  flex: 1; padding: 7px 0; border-radius: 9px; border: 1px solid var(--line);
  background: transparent; color: var(--muted); font-size: 12.5px;
}
.switch button.on { border-color: var(--accent); color: var(--accent); background: var(--accent-weak); font-weight: 600; }

.note { font-size: 11px; color: var(--muted); line-height: 1.6; border-top: 1px solid var(--line); padding-top: 10px; margin: auto 0 0; }
</style>
