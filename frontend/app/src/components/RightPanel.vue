<script setup lang="ts">
import { computed } from 'vue'
import {
  activeLoop,
  loopCount,
  nextLoop,
  prevLoop,
  state,
} from '../stores/planner'
import {
  fmtKm,
  fmtMeters,
  fmtMinutes,
  fmtPercent,
  fmtScore,
  fmtSlope,
  haversineMeters,
  isClosed,
  loopBadge,
  parseSub,
} from '../lib/format'

const loop = activeLoop
const props = computed(() => loop.value?.properties ?? null)
const sub = computed(() => parseSub(props.value?.sub))

const isOneway = computed(() => state.mode === 'oneway')

const heading = computed(() => {
  if (!props.value) return ''
  if (isOneway.value) return '单行线 · A → B'
  const back = isClosed(loop.value?.geometry.coordinates) ? '　回到起点' : '　A → B'
  return `环线 · 第 ${state.activeIndex + 1} 条${back}`
})

const badge = computed(() => (props.value ? loopBadge(props.value.score) : ''))

const endpoints = computed(() => {
  const p = props.value
  const coords = loop.value?.geometry.coordinates
  const startLng =
    p?.start_lng ?? state.loops?.origin?.snapped_lng ?? coords?.[0]?.[0] ?? state.onewayA?.lng
  const startLat =
    p?.start_lat ?? state.loops?.origin?.snapped_lat ?? coords?.[0]?.[1] ?? state.onewayA?.lat
  const endLng =
    p?.end_lng ??
    state.loops?.destination?.snapped_lng ??
    coords?.[coords.length - 1]?.[0] ??
    state.onewayB?.lng
  const endLat =
    p?.end_lat ??
    state.loops?.destination?.snapped_lat ??
    coords?.[coords.length - 1]?.[1] ??
    state.onewayB?.lat

  if (startLng == null || startLat == null || endLng == null || endLat == null) {
    return null
  }
  const straightM = haversineMeters(startLng, startLat, endLng, endLat)
  const detour = p && straightM >= 1 ? p.length_m / straightM : null
  return {
    startText: `${startLng.toFixed(4)}, ${startLat.toFixed(4)}`,
    endText: `${endLng.toFixed(4)}, ${endLat.toFixed(4)}`,
    straightM,
    detour,
  }
})
</script>

<template>
  <aside class="right glass" aria-label="路线结果" aria-live="polite">
    <template v-if="props">
      <div class="rhead">
        <div class="rt">{{ heading }}</div>
        <div v-if="!isOneway && loopCount > 1" class="cand">
          <button class="cbtn" aria-label="上一条环线" title="上一条（←）" @click="prevLoop">
            ‹
          </button>
          <span class="cidx num">{{ state.activeIndex + 1 }}/{{ loopCount }}</span>
          <button class="cbtn" aria-label="下一条环线" title="下一条（→）" @click="nextLoop">
            ›
          </button>
        </div>
      </div>

      <div class="score">
        <b class="num">{{ fmtScore(props.score) }}</b>
        <i>/ 100</i>
        <span class="badge">{{ badge }}</span>
      </div>
      <p class="subnote">路线偏好匹配分</p>

      <!-- F2 单行线：展示实际起终点 + 偏差温和提示（非报错） -->
      <template v-if="isOneway">
        <div v-if="endpoints" class="ab-summary">
          <div>
            <span class="ab-tag a">A</span>
            <span class="num">{{ endpoints.startText }}</span>
          </div>
          <div>
            <span class="ab-tag b">B</span>
            <span class="num">{{ endpoints.endText }}</span>
          </div>
        </div>
        <div v-if="state.routeNotice" class="route-notice" role="status">
          {{ state.routeNotice }}
        </div>
        <div class="grid2">
          <div class="cell"><u>路线长度</u><b class="num">{{ fmtKm(props.length_m) }}</b></div>
          <div class="cell">
            <u>直线距离</u>
            <b class="num">{{ endpoints ? fmtKm(endpoints.straightM) : '—' }}</b>
          </div>
          <div class="cell">
            <u>绕行系数</u>
            <b class="num">{{ endpoints?.detour ? `${endpoints.detour.toFixed(2)}×` : '—' }}</b>
          </div>
          <div class="cell"><u>预计用时</u><b class="num">{{ fmtMinutes(props.minutes) }}</b></div>
          <div class="cell"><u>树冠覆盖</u><b class="num">{{ fmtPercent(props.tree_share) }}</b></div>
          <div class="cell"><u>平均坡度</u><b class="num">{{ fmtSlope(props.slope_mean_pct) }}</b></div>
        </div>
      </template>

      <!-- 环线模式指标 -->
      <div v-else class="grid2">
        <div class="cell"><u>距离</u><b class="num">{{ fmtKm(props.length_m) }}</b></div>
        <div class="cell"><u>预计用时</u><b class="num">{{ fmtMinutes(props.minutes) }}</b></div>
        <div class="cell"><u>树冠覆盖</u><b class="num">{{ fmtPercent(props.tree_share) }}</b></div>
        <div class="cell"><u>平均坡度</u><b class="num">{{ fmtSlope(props.slope_mean_pct) }}</b></div>
        <div class="cell"><u>设施距离</u><b class="num">{{ fmtMeters(props.facility_m) }}</b></div>
        <div class="cell"><u>起点偏差</u><b class="num">{{ fmtMeters(props.origin_snap_m) }}</b></div>
      </div>

      <div class="bars">
        <div class="bar">
          <span>安全</span>
          <span class="track"
            ><span class="fill" :style="{ width: `${Math.round(sub.s_safety)}%` }"></span
          ></span>
          <span class="num">{{ Math.round(sub.s_safety) }}</span>
        </div>
        <div class="bar">
          <span>绿化与滨水</span>
          <span class="track"
            ><span class="fill" :style="{ width: `${Math.round(sub.s_green)}%` }"></span
          ></span>
          <span class="num">{{ Math.round(sub.s_green) }}</span>
        </div>
        <div class="bar">
          <span>坡度平缓</span>
          <span class="track"
            ><span class="fill amber" :style="{ width: `${Math.round(sub.s_slope)}%` }"></span
          ></span>
          <span class="num">{{ Math.round(sub.s_slope) }}</span>
        </div>
      </div>

      <div class="note">
        匹配分由安全、绿化和平坦偏好计算。预计用时未计红绿灯停留。
        路段六维综合分、年度空气数据和代理指标说明可在适宜性地图中查看。
      </div>
    </template>

    <template v-else>
      <div class="rt">{{ isOneway ? '单行线结果' : '路线结果' }}</div>
      <p class="empty">
        {{
          isOneway
            ? '先点击地图选择起点 A，再点击地图选择终点 B，系统将自动生成 A→B 单行线。'
            : '在左侧选择目标距离与偏好，点「生成路线」查看结果。'
        }}
      </p>
    </template>
  </aside>
</template>

<style scoped>
.right {
  position: absolute;
  right: 24px;
  top: 88px;
  width: 330px;
  padding: 22px 24px;
  z-index: 4;
}

.rt {
  font-size: 13px;
  color: var(--muted);
  letter-spacing: 1px;
}

.rhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 18px;
}

.cand {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.cbtn {
  width: 18px;
  height: 18px;
  line-height: 16px;
  font-size: 14px;
  color: var(--muted);
  border: 1px solid transparent;
}

.cbtn:hover,
.cbtn:focus-visible {
  color: var(--accent);
  border-color: var(--line);
  background: rgba(255, 255, 255, 0.7);
}

.cidx {
  font-size: 11.5px;
  color: var(--muted);
  letter-spacing: 0.5px;
}

.score {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin: 6px 0 2px;
}

.score b {
  font-size: 52px;
  line-height: 0.95;
  color: var(--accent);
  font-weight: 700;
  letter-spacing: -1px;
}

.score i {
  font-style: normal;
  font-size: 15px;
  color: var(--muted);
  padding-bottom: 6px;
}

.badge {
  margin-left: auto;
  background: var(--accent-weak);
  color: var(--accent);
  font-size: 12.5px;
  padding: 4px 10px;
  align-self: center;
}

.subnote {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--muted);
}

.ab-summary {
  margin-top: 12px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--sub);
}

.ab-summary > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ab-tag {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  flex: none;
}

.ab-tag.a {
  background: #15503c;
}

.ab-tag.b {
  background: #c2410c;
}

.route-notice {
  margin-top: 10px;
  padding: 7px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--accent);
  background: var(--accent-weak);
  border: 1px solid #c9dfd3;
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--line);
  margin: 14px 0 0;
}

.cell {
  background: rgba(255, 255, 255, 0.86);
  padding: 11px 12px 12px;
}

.cell u {
  display: block;
  font-size: 11.5px;
  color: var(--muted);
  text-decoration: none;
  margin-bottom: 4px;
}

.cell b {
  font-size: 17px;
  font-weight: 600;
}

.bars {
  margin-top: 16px;
}

.bar {
  display: grid;
  grid-template-columns: 74px 1fr 32px;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 12.5px;
  color: var(--sub);
}

.track {
  display: block;
  height: 7px;
  background: #e3eae6;
}

.fill {
  display: block;
  height: 7px;
  background: var(--accent);
}

.fill.amber {
  background: var(--slope);
}

.num {
  text-align: right;
  font-weight: 600;
  color: var(--ink);
}

.note {
  margin-top: 14px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
  border-top: 1px solid var(--line);
  padding-top: 10px;
}

.empty {
  margin-top: 14px;
  font-size: 13px;
  color: var(--sub);
  line-height: 1.8;
}
</style>
